"""AI の自分同士の対局を記録する（データページ・先手有利・コツ集の材料）。

    python scripts/selfplay_record.py fmcts2000 --games 600 --workers 4
    # → data/selfplay/fmcts2000.jsonl.gz（1行1局。追記ではなく作り直す）

1局の記録: seed・勝った人（-1 は引き分け）・最後の点・手番の数・毎手番の手
（種類・買った/予約した札・来た貴族・指したあとの点）。乱数の種は局ごとに決まっているので同じ結果になる
（fmcts は numba の中の乱数も種から決める）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gem_merchant.agents import make_agent
from gem_merchant.game import BUY, RESERVE, apply, new_game, result


def play(args: tuple[str, int]) -> dict:
    name, seed = args
    agent = make_agent(name)
    s = new_game(seed)
    rngs = [random.Random(seed * 2 + i) for i in (0, 1)]
    moves = []
    while not s.done:
        i = s.current
        a = agent.act(s, rngs[i])
        card = -1
        blind = False
        if a.kind == BUY:
            card = (
                s.board[a.arg[1]][a.arg[2]]
                if a.arg[0] == "board"
                else s.players[i].reserved[a.arg[1]][0]
            )
        elif a.kind == RESERVE:
            blind = a.arg[1] < 0
            card = -1 if blind else s.board[a.arg[0]][a.arg[1]]
        from_res = a.kind == BUY and a.arg[0] == "reserved"
        apply(s, a)
        moves.append(
            {
                "p": i,
                "k": a.kind,
                "c": card,
                "lv": a.arg[0] if a.kind == RESERVE else -1,
                "blind": blind,
                "res": from_res,
                "noble": a.noble,
                "ret": sum(a.ret),
                "pts": [q.points for q in s.players],
            }
        )
    return {
        "seed": seed,
        "agent": name,
        "winner": result(s),
        "points": [q.points for q in s.players],
        "bought": [q.bought for q in s.players],
        "turns": s.turn,
        "moves": moves,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = Path(args.out or ROOT / "data" / "selfplay" / f"{args.agent}.jsonl.gz")
    jobs = [(args.agent, args.seed + k) for k in range(args.games)]
    t = time.time()
    with ProcessPoolExecutor(max(1, args.workers)) as ex:
        games = list(ex.map(play, jobs, chunksize=4))
    out.parent.mkdir(
        parents=True, exist_ok=True
    )  # 長く回すので、書く直前に作る（途中で消えても困らないように）
    with (
        gzip.open(out, "wt", encoding="utf-8")
        if out.suffix == ".gz"
        else out.open("w", encoding="utf-8")
    ) as f:
        for g in games:
            f.write(json.dumps(g, separators=(",", ":")) + "\n")
    first = sum(1.0 if g["winner"] == 0 else 0.5 if g["winner"] < 0 else 0.0 for g in games)
    print(f"{len(games)}局 → {out}（先手の勝率 {first / len(games):.3f}、{time.time() - t:.0f}秒）")


if __name__ == "__main__":
    main()
