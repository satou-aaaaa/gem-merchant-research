"""終盤の読み切りで「正解つきの次の一手問題」を作る（R-008、GTO 研究の3歩目）。

    python scripts/make_puzzles.py --workers 4                 # 150局（シード3000〜）→ data/endgame_puzzles.json
    python scripts/make_puzzles.py --seed-list 3060,3061 --out x.json   # 一部の局だけ（分けて回して足すとき）

作り方:
1. 1手先だけを見る AI（greedy）どうしで対局し、だれかが9点以上の局面を集める
   （強い AI どうしだと点差がついて一方的になりやすく、勝ち切る手が1つに決まる局面が少ない）。
2. 読み切り（endgame_fast.action_values）で、この一巡の終わり＋2手番（二巡先）まで読む。
   山札から出る札は残りから等しい確率で出るとして平均し、読み切れない局面は勝つ見込みを区間で持つ。
3. いちばん良い手（下限が最大）と、「どう転んでもその下限より 0.15 以上低い」確実に悪い手が2つ以上ある局面を問題にする。
   選択肢は正解と確実に悪い手だけ（読み切れない手は出さない）なので、選択肢の中の正解は1つに決まる。
   最善と同じ見込みの手が4つ以上ある局面は、ほかにも正解が多いので使わない。
4. 読み切りは相手の伏せ予約が見えるとして読むので、問題でも相手の予約札は全部見せる（ページに前提として書く）。
5. 選択肢は、正解・1手先だけを見る AI（greedy）の手（確実に悪いとき）・確実に悪い手のうち上限の高いものから、合わせて最大4つ。
   greedy が確実に悪い手を選ぶ問題を「むずかしい」とする。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gem_merchant import fast, game
from gem_merchant.agents import GreedyAgent, make_agent
from gem_merchant.endgame_fast import action_values, round_depth

MARGIN = 0.15
MAX_BEST = 3
MIN_POINTS = 9
EXTRA = 2


def main_key(a: game.Action) -> tuple:
    return (a.kind, a.arg, a.noble)


def act_json(a: game.Action) -> list:
    arg = list(a.arg) if isinstance(a.arg, tuple) else a.arg
    return [a.kind, arg, list(a.ret), a.noble]


def state_json(s: game.State) -> dict:
    """局面の写し（JSON にできる形）。リストを写さないと、あとの手で書き換わった局面が残る。"""
    return json.loads(json.dumps(_state_dict(s)))


def _state_dict(s: game.State) -> dict:
    return {
        "bank": s.bank,
        "decks": {str(k): v for k, v in s.decks.items()},
        "board": {str(k): v for k, v in s.board.items()},
        "nobles": s.nobles,
        "players": [
            {
                "tokens": p.tokens,
                "bonus": p.bonus,
                "points": p.points,
                "reserved": [[c, b] for c, b in p.reserved],
                "bought": p.bought,
                "nobles": p.nobles,
            }
            for p in s.players
        ],
        "turn": s.turn,
        "passes": s.passes,
        "done": s.done,
    }


def examine(s: game.State, rng: random.Random) -> dict | None:
    me = s.current
    fs = fast.from_state(s)
    acts, vals, stats = action_values(fs, round_depth(fs) + EXTRA)
    if len(acts) < 5:
        return None
    if me == 1:  # 手番の人から見た区間にする
        vals = 1.0 - vals[:, ::-1]
    order = sorted(range(len(acts)), key=lambda i: -vals[i, 0])
    b = order[0]
    best_lo = vals[b, 0]
    # 最善と同じ下限の手（同じくらい良い手）は3つまで許し、選択肢には1つだけ出す
    tops = [i for i in order if vals[i, 0] >= best_lo - 1e-9]
    # 確実に悪い手: どう転んでも最善の下限より MARGIN 以上低い。読み切れない手（どちらとも言えない）は選択肢に出さない
    worse = [i for i in order if vals[i, 1] <= best_lo - MARGIN]
    if len(tops) > MAX_BEST or len(worse) < 2:
        return None
    best = fast.to_action(acts[b])
    greedy = GreedyAgent().act(s, rng)
    gi = next(i for i in range(len(acts)) if main_key(fast.to_action(acts[i])) == main_key(greedy))
    greedy_wrong = gi in worse
    choices = [b]
    if greedy_wrong:
        choices.append(gi)
    for i in sorted(worse, key=lambda i: -vals[i, 1]):
        if len(choices) >= 4:
            break
        if i not in choices:
            choices.append(i)
    return {
        "state": state_json(s),
        "me": me,
        "answer": act_json(best),
        "choices": [
            {"action": act_json(fast.to_action(acts[i])), "lo": round(float(vals[i, 0]), 3), "hi": round(float(vals[i, 1]), 3)}
            for i in choices
        ],
        "greedy_correct": not greedy_wrong,
        "n_best": len(tops),
        "nodes": int(stats[0]),
    }  # fmt: skip


def play_one(args: tuple[str, int]) -> list[dict]:
    name, seed = args
    agent = make_agent(name)
    s = game.new_game(seed)
    rng = random.Random(seed)
    out = []
    while not s.done:
        if max(p.points for p in s.players) >= MIN_POINTS:
            pz = examine(s, random.Random(seed * 1000 + s.turn))
            if pz:
                pz["seed"] = seed
                out.append(pz)
        game.apply(s, agent.act(s, rng))
    return out


def pick_seeds(seed_list: str, seed: int, games: int) -> list[int]:
    """--seed-list があればその種だけ、なければ seed から games 局。"""
    if seed_list:
        return [int(x) for x in seed_list.split(",") if x.strip()]
    return [seed + k for k in range(games)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="greedy")
    ap.add_argument("--games", type=int, default=150)
    ap.add_argument("--seed", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument(
        "--seed-list", default="", help="この種の局だけ（カンマ区切り。作り直しの時間を省く）"
    )
    ap.add_argument("--out", default=str(ROOT / "data" / "endgame_puzzles.json"))
    args = ap.parse_args()
    t = time.time()
    seeds = pick_seeds(args.seed_list, args.seed, args.games)
    with Pool(args.workers) as pool:
        parts = pool.map(play_one, [(args.agent, sd) for sd in seeds], chunksize=1)
    puzzles = []
    for part in parts:
        # 同じ局の続きの局面は似るので、1局から最大2問（むずかしい問題を先に）
        part.sort(key=lambda p: p["greedy_correct"])
        puzzles += part[:2]
    # むずかしい問題、買う以外が正解の問題（見落としやすい）、の順に並べる
    puzzles.sort(
        key=lambda p: (p["greedy_correct"], p["answer"][0] == "buy", p["seed"], p["state"]["turn"])
    )
    for k, p in enumerate(puzzles):
        p["id"] = k + 1
    Path(args.out).write_text(
        json.dumps(puzzles, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    hard = sum(not p["greedy_correct"] for p in puzzles)
    print(f"{len(puzzles)}問（むずかしい {hard}問）→ {args.out}（{time.time() - t:.0f}秒）")


if __name__ == "__main__":
    main()
