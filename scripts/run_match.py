"""2つの AI を先後入れ替えで対戦させる。

python scripts/run_match.py mcts400 greedy --pairs 50
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant.agents import make_agent
from gem_merchant.arena import match


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--pairs", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    t = time.time()
    s = match(make_agent(args.a), make_agent(args.b), args.pairs, args.seed)
    print(f"A={args.a} B={args.b}: {s}（{time.time() - t:.0f}秒）")


if __name__ == "__main__":
    main()
