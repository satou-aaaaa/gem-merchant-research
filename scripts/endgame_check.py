"""AI の手を終盤の読み切りで採点する（GTO 研究の物差し、src/gem_merchant/endgame_fast.py）。

AI どうしを対局させ、各手番で読み切る。決着がついた局面だけを数え、AI が最善の手を選んだ割合と、
外した手の見込みの損（勝つ見込みの差）をまとめる。読む深さは「この一巡の終わり」＋ --extra 手番。
--extra 2 なら次の一巡の終わりまで（二巡先）。同じ局面を一巡先でも読み、増えた分も出す。
--max-nodes を付けると、1局面で読む節点の数に上限を置く（超えた局面は「上限で打ち切り」として数え、判定に入れない）。

    python scripts/endgame_check.py mcts400 --games 10 --extra 2 --workers 4
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant import fast, game
from gem_merchant.agents import make_agent
from gem_merchant.endgame_fast import judge, round_depth


def play_one(args: tuple[str, int, int, int, int]) -> list[dict]:
    """1局を指し、調べた手番ごとに {extra: 判定} を返す（判定には読んだ秒数 sec も入れる）。"""
    agent_name, seed, min_points, extra, max_nodes = args
    agent = make_agent(agent_name)
    s = game.new_game(seed)
    rng = random.Random(seed)
    rows = []
    while not s.done:
        a = agent.act(s, rng)
        if max(p.points for p in s.players) >= min_points:
            fs = fast.from_state(s)
            row = {"seed": seed, "turn": s.turn}
            for e in sorted({0, extra}):
                t = time.time()
                r = judge(fs, a, round_depth(fs) + e, max_nodes=max_nodes)
                row[e] = r
                row[f"sec{e}"] = round(time.time() - t, 3)
            rows.append(row)
        game.apply(s, a)
    return rows


class _NoPool:
    """--workers 1 のとき Pool の代わりに、同じプロセスで順に指す。"""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def imap_unordered(self, f, jobs, chunksize=1):
        return map(f, jobs)


def _row_json(r: dict) -> str:
    return json.dumps({str(k): v for k, v in r.items()}, ensure_ascii=False)


def summarize(rows: list[dict], extra: int) -> tuple[int, int, float, int]:
    """読み切れた手の数・確実な悪手の数・悪手の損の平均・上限で打ち切った手の数。"""
    rs = [r[extra] for r in rows if r[extra] is not None]
    over = sum(1 for v in rs if v["verdict"] == "over")
    rs = [v for v in rs if v["verdict"] in ("best", "mistake")]
    mistakes = [v["loss_min"] for v in rs if v["verdict"] == "mistake"]
    return len(rs), len(mistakes), statistics.mean(mistakes) if mistakes else 0.0, over


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--min-points", type=int, default=9, help="誰かがこの点以上の局面だけ調べる")
    ap.add_argument(
        "--extra", type=int, default=0, help="一巡の終わりより何手番先まで読むか（2で次の一巡まで）"
    )
    ap.add_argument(
        "--max-nodes", type=int, default=0, help="1局面で読む節点の上限（0 は上限なし）"
    )
    ap.add_argument("--workers", type=int, default=1, help="並べて指す局の数（CPU の数まで）")
    ap.add_argument(
        "--out",
        default=os.environ.get("RESEARCH_OUT"),
        help="結果（summary.txt と手ごとの判定 rows.jsonl）を書くフォルダ。既定は $RESEARCH_OUT",
    )
    args = ap.parse_args()
    t = time.time()
    jobs = [
        (args.agent, args.seed + g, args.min_points, args.extra, args.max_nodes)
        for g in range(args.games)
    ]
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "rows.jsonl").write_text("", encoding="utf-8")
    rows = []
    # 1局終わるごとに rows.jsonl に足す（時間切れで止まっても、終わった局の判定は残る）
    with Pool(args.workers) if args.workers > 1 else _NoPool() as pool:
        for game_rows in pool.imap_unordered(play_one, jobs, chunksize=1):
            rows.extend(game_rows)
            if out:
                with open(out / "rows.jsonl", "a", encoding="utf-8") as f:
                    f.writelines(_row_json(r) + "\n" for r in game_rows)
    rows.sort(key=lambda r: (r["seed"], r["turn"]))
    lines = []
    for e in sorted({0, args.extra}):
        judged, mistakes, mean_loss, over = summarize(rows, e)
        rate = 1 - mistakes / judged if judged else float("nan")
        secs = sorted(r[f"sec{e}"] for r in rows)
        median = statistics.median(secs) if secs else 0.0
        lines.append(
            f"{args.agent}（一巡の終わり＋{e}手番）: {args.games}局・調べた手 {len(rows)}・"
            f"読み切れた手 {judged}・最善を選んだ割合 {rate:.3f}・確実な悪手 {mistakes}・"
            f"悪手で失った勝つ見込み（少なくとも）の平均 {mean_loss:.3f}・"
            f"上限で打ち切り {over}・1局面の秒数 中央値 {median:.2f}・最大 {max(secs, default=0):.1f}"
        )
    for r in rows:
        v = r[args.extra]
        if v is not None and v["verdict"] == "mistake":  # 打ち切り（over）は数えない
            lines.append(
                f"  悪手: シード {r['seed']} の {r['turn']}手番目・損 {v['loss_min']:.3f}以上"
            )
    lines.append(f"（{time.time() - t:.0f}秒）")
    print("\n".join(lines))
    if out:
        (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
