"""AI の手を終盤の読み切りで採点する（GTO 研究の物差し、src/gem_merchant/endgame.py）。

AI どうしを対局させ、各手番で「この一巡の終わりまで」を読み切る。決着がついた局面だけを数え、
AI が最善の手を選んだ割合と、外した手の見込みの損（勝つ見込みの差）をまとめる。

    python scripts/endgame_check.py mcts400 --games 10
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant import game
from gem_merchant.agents import make_agent
from gem_merchant.endgame import judge, round_depth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent")
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--min-points", type=int, default=9, help="誰かがこの点以上の局面だけ調べる")
    ap.add_argument(
        "--extra", type=int, default=0, help="一巡の終わりより何手番先まで読むか（2で次の一巡まで）"
    )
    args = ap.parse_args()
    t = time.time()
    agent = make_agent(args.agent)
    judged, mistakes, losses = 0, 0, []
    for g in range(args.games):
        s = game.new_game(args.seed + g)
        rng = random.Random(args.seed + g)
        while not s.done:
            a = agent.act(s, rng)
            if max(p.points for p in s.players) >= args.min_points:
                r = judge(s, a, round_depth(s) + args.extra)
                if r is not None:
                    judged += 1
                    if r["verdict"] == "mistake":
                        mistakes += 1
                        losses.append(r["loss_min"])
            game.apply(s, a)
    rate = 1 - mistakes / judged if judged else float("nan")
    mean_loss = statistics.mean(losses) if losses else 0.0
    print(
        f"{args.agent}: {args.games}局・読み切れた手 {judged}・最善を選んだ割合 {rate:.3f}・"
        f"確実な悪手 {mistakes}・悪手で失った勝つ見込み（少なくとも）の平均 {mean_loss:.3f}"
        f"（{time.time() - t:.0f}秒）"
    )


if __name__ == "__main__":
    main()
