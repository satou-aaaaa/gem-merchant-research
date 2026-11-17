"""2つの AI を先後入れ替えで対戦させる。

python scripts/run_match.py mcts400 greedy --pairs 50
python scripts/run_match.py fmcts2000 mcts2000 --pairs 60 --workers 4   # 組ごとに並べて回す
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant.agents import make_agent
from gem_merchant.arena import Summary, match


def _one(args: tuple[str, str, int]) -> Summary:
    a, b, seed = args
    return match(make_agent(a), make_agent(b), 1, seed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    t = time.time()
    if args.workers <= 1:
        s = match(make_agent(args.a), make_agent(args.b), args.pairs, args.seed)
    else:
        jobs = [(args.a, args.b, args.seed + k) for k in range(args.pairs)]
        with ProcessPoolExecutor(args.workers) as ex:
            parts = list(ex.map(_one, jobs))
        n = sum(p.games for p in parts)
        s = Summary(
            n,
            sum(p.wins_a for p in parts),
            sum(p.diff_a * p.games for p in parts) / n,
            sum(p.first_wins for p in parts),
        )
    print(f"A={args.a} B={args.b}: {s}（{time.time() - t:.0f}秒）")


if __name__ == "__main__":
    main()
