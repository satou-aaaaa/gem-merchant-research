"""ランダムな手どうしで対局し、終わり方と手数をまとめる（エンジンの確かめ用）。

python scripts/play_random.py --games 200
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant import game, rules


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    ends, turns, branching, winners = Counter(), [], [], Counter()
    for g in range(args.games):
        s = game.new_game(args.seed + g)
        rng = random.Random(args.seed + g)
        while not s.done:
            acts = game.legal_actions(s)
            branching.append(len(acts))
            game.apply(s, rng.choice(acts))
        ended_by_points = any(p.points >= rules.WIN_POINTS for p in s.players)
        ends["15点" if ended_by_points else "パス"] += 1
        turns.append(s.turn)
        winners[game.result(s)] += 1
    print(f"対局数: {args.games}  終わり方: {dict(ends)}  勝者(-1は引き分け): {dict(winners)}")
    print(f"手番の数: 平均 {statistics.mean(turns):.1f}  最小 {min(turns)}  最大 {max(turns)}")
    print(f"手の候補の数: 平均 {statistics.mean(branching):.1f}  最大 {max(branching)}")


if __name__ == "__main__":
    main()
