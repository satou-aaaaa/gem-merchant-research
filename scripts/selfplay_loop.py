"""自己対戦で葉の評価の重みを学ぶループ（R-004）。

1世代 = ①チャンピオンの重みで自分同士の対局（fmcts）→ ②全局面の「特徴の差」と勝ち負けで
ロジスティック回帰 → ③学んだ重み（挑戦者）とチャンピオンを先後入れ替えで対戦 →
④勝率が --accept（0.55）以上なら挑戦者を新しいチャンピオンにする。

    python scripts/selfplay_loop.py --generations 1 --games 400 --pairs 100 --workers 4
    # → models/eval_champion.npy（チャンピオンの重み）・models/loop_log.jsonl（世代ごとの記録）
    #   最初のチャンピオンは手作りの評価（fast_mcts.HAND_WEIGHTS）

重い回し方（Actions）: research-run.yml の command に
`python scripts/selfplay_loop.py --generations 5 --out $RESEARCH_OUT` を渡す。
学ぶ重みは序盤・終盤の2組（fast_mcts.diff_features）。評価は sigmoid(差/4) なので、
回帰の係数を4倍したものが重みになる。対局の乱数はすべて種から決まるので、同じ引数なら同じ結果になる。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gem_merchant import fast
from gem_merchant import fast_mcts as fm
from gem_merchant.arena import wilson
from gem_merchant.game import new_game


def _outcome(s, i: int) -> float:
    r = fast.result(s)
    return 0.5 if r < 0 else float(r == i)


def play(w0: np.ndarray, w1: np.ndarray, iters: int, seed: int, record: bool):
    """w0（先手）と w1（後手）で1局。record なら毎手番の（特徴の差, 手番の人）も返す。"""
    s = fast.from_state(new_game(seed))
    ws = (w0, w1)
    xs, who = [], []
    k = 0
    while not s[fast.DONE]:
        i = int(s[fast.TURN]) % 2
        if record:
            x = np.empty(2 * fm.N_FEAT)
            fm.diff_features(s, i, x)
            xs.append(x)
            who.append(i)
        a, _ = fm.search(s, iters, 0.7, 6, (seed * 1000003 + k) % (2**31), ws[i])
        fast.apply(s, a)
        k += 1
    winner = int(fast.result(s))
    pts = (int(s[fast.PL[0] + fast.P_PTS]), int(s[fast.PL[1] + fast.P_PTS]))
    capped = winner < 0 or max(pts) < 15
    if not record:
        return winner, pts, capped
    y = [_outcome(s, i) for i in who]
    return np.array(xs), np.array(y), capped


def _selfplay_job(args):
    w, iters, seed = args
    return play(w, w, iters, seed, True)


def _gate_job(args):
    wa, wb, iters, seed = args
    out = []
    for a_first in (True, False):
        winner, pts, _ = (
            play(wa, wb, iters, seed, False) if a_first else play(wb, wa, iters, seed, False)
        )
        ia = 0 if a_first else 1
        out.append((0.5 if winner < 0 else float(winner == ia), pts[ia] - pts[1 - ia]))
    return out


def fit(x: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 30) -> np.ndarray:
    """切片なしのロジスティック回帰（ニュートン法、L2 つき）。特徴の差は符号を変えると勝ち負けも
    入れ替わる（対称）ので、切片は入れない。返すのは係数（長さ 2*N_FEAT）。"""
    b = np.zeros(x.shape[1])
    for _ in range(steps):
        p = 1.0 / (1.0 + np.exp(-(x @ b)))
        g = x.T @ (p - y) + l2 * b
        h = (x * (p * (1 - p))[:, None]).T @ x + l2 * np.eye(x.shape[1])
        step = np.linalg.solve(h, g)
        b -= step
        if np.abs(step).max() < 1e-8:
            break
    return b


def log_loss(x: np.ndarray, y: np.ndarray, b: np.ndarray) -> float:
    p = np.clip(1.0 / (1.0 + np.exp(-(x @ b))), 1e-9, 1 - 1e-9)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def gate(ex, wa, wb, iters: int, pairs: int, seed: int) -> dict:
    parts = list(ex.map(_gate_job, [(wa, wb, iters, seed + k) for k in range(pairs)]))
    flat = [r for p in parts for r in p]
    wins = sum(r[0] for r in flat)
    n = len(flat)
    lo, hi = wilson(wins, n)
    return {
        "games": n,
        "rate": wins / n,
        "ci": [lo, hi],
        "diff": sum(r[1] for r in flat) / n,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--games", type=int, default=400, help="1世代の自分同士の局数")
    ap.add_argument("--iters", type=int, default=1000, help="自分同士の対局の探索回数")
    ap.add_argument("--pairs", type=int, default=100, help="入れ替え戦の組（2倍の局数）")
    ap.add_argument("--gate-iters", type=int, default=2000)
    ap.add_argument("--accept", type=float, default=0.55)
    ap.add_argument("--window", type=int, default=2, help="学習に使う直近の世代数")
    ap.add_argument("--seed", type=int, default=100000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "models"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    champ_path = out / "eval_champion.npy"
    log_path = out / "loop_log.jsonl"
    champ = np.load(champ_path) if champ_path.exists() else fm.HAND_WEIGHTS.copy()
    gen0 = sum(1 for _ in log_path.open()) if log_path.exists() else 0
    data: list[tuple[np.ndarray, np.ndarray]] = []

    with ProcessPoolExecutor(max(1, args.workers)) as ex:
        for g in range(gen0, gen0 + args.generations):
            t = time.time()
            seed = args.seed + g * 10000
            jobs = [(champ, args.iters, seed + k) for k in range(args.games)]
            games = list(ex.map(_selfplay_job, jobs, chunksize=2))
            capped = sum(c for _, _, c in games)
            data.append(
                (np.concatenate([x for x, _, _ in games]), np.concatenate([y for _, y, _ in games]))
            )
            data = data[-args.window :]
            x = np.concatenate([d[0] for d in data])
            y = np.concatenate([d[1] for d in data])
            b = fit(x, y)
            cand = (4.0 * b).reshape(2, fm.N_FEAT)
            loss_champ = log_loss(x, y, champ.reshape(-1) / 4.0)
            loss_cand = log_loss(x, y, b)
            r = gate(ex, cand, champ, args.gate_iters, args.pairs, seed + 5000)
            accepted = r["rate"] >= args.accept
            if accepted:
                champ = cand
                np.save(champ_path, champ)
            rec = {
                "generation": g,
                "selfplay_games": args.games,
                "selfplay_iters": args.iters,
                "capped_games": capped,
                "positions": len(y),
                "loss_champion": round(loss_champ, 4),
                "loss_candidate": round(loss_cand, 4),
                "candidate": np.round(cand, 4).tolist(),
                "gate_iters": args.gate_iters,
                "gate": {
                    k: (np.round(v, 4).tolist() if k == "ci" else round(v, 4)) for k, v in r.items()
                },
                "accepted": accepted,
                "seconds": round(time.time() - t),
            }
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            lo, hi = r["ci"]
            print(
                f"世代{g}: 局面{len(y)} 損失 {loss_champ:.4f}→{loss_cand:.4f} "
                f"挑戦者の勝率 {r['rate']:.3f} [{lo:.3f}, {hi:.3f}] 点差 {r['diff']:+.2f} "
                f"{'採用' if accepted else '不採用'}（{rec['seconds']}秒）",
                flush=True,
            )
    if not champ_path.exists():
        np.save(champ_path, champ)


if __name__ == "__main__":
    main()
