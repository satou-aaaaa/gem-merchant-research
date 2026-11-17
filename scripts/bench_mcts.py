"""MCTS の正解版（mcts）と速い版（fmcts）の1手の時間を、同じ局面で比べる。

python scripts/bench_mcts.py --iterations 2000 --states 20
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant import game
from gem_merchant.agents import make_agent


def sample_states(n: int, seed: int = 0) -> list[game.State]:
    """greedy 同士の対局から、序盤から終盤まで等間隔に n 局面を取る。"""
    g = make_agent("greedy")
    states: list[game.State] = []
    k = 0
    while len(states) < 4 * n:
        s = game.new_game(seed + k)
        rng = random.Random(seed + k)
        while not s.done:
            states.append(s.clone())
            game.apply(s, g.act(s, rng))
        k += 1
    step = len(states) // n
    return states[::step][:n]


def per_move(name: str, states: list[game.State]) -> float:
    agent = make_agent(name)
    rng = random.Random(1)
    agent.act(states[0], rng)  # numba の翻訳を先に済ませる
    t = time.perf_counter()
    for s in states:
        agent.act(s, rng)
    return (time.perf_counter() - t) / len(states)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=2000)
    ap.add_argument("--states", type=int, default=20)
    args = ap.parse_args()
    states = sample_states(args.states)
    slow = per_move(f"mcts{args.iterations}", states)
    fast = per_move(f"fmcts{args.iterations}", states)
    print(
        f"{len(states)}局面・{args.iterations}回: 正解版 {slow:.3f}秒/手、速い版 {fast:.4f}秒/手、{slow / fast:.0f}倍"
    )


if __name__ == "__main__":
    main()
