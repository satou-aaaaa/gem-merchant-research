"""速いエンジン（fast.py）と正解版（game.py）の速さを比べる。

    python scripts/bench_fast.py --games 200

同じ種のランダム対局を3通りで指し、1手（合法手の生成＋手の適用）あたりの時間を出す。
- 正解版: game.legal_actions と game.apply を Python から呼ぶ。
- 速い版（1手ずつ）: fast.legal と fast.apply を Python から1手ずつ呼ぶ（探索を Python で書くときの速さ）。
- 速い版（まとめて）: fast.random_playout で numba の中で対局を最後まで回す（探索も numba で書くときの速さ）。
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant import fast, game


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=200)
    args = ap.parse_args()
    buf = fast.new_buffer()
    fast.random_playout(fast.from_state(game.new_game(0)), buf, 0)  # 先に一度コンパイルする

    t, moves = time.perf_counter(), 0
    for g in range(args.games):
        s, rng = game.new_game(g), random.Random(g)
        while not s.done:
            acts = game.legal_actions(s)
            game.apply(s, acts[rng.randrange(len(acts))])
            moves += 1
    ref = (time.perf_counter() - t) / moves

    t, moves2 = time.perf_counter(), 0
    for g in range(args.games):
        s, rng = fast.from_state(game.new_game(g)), random.Random(g)
        while not s[fast.DONE]:
            n = fast.legal(s, buf)
            fast.apply(s, buf[rng.randrange(n)])
            moves2 += 1
    step = (time.perf_counter() - t) / moves2
    assert moves2 == moves  # 同じ種なら同じ対局になる

    starts = [fast.from_state(game.new_game(g)) for g in range(args.games)]
    t, moves3 = time.perf_counter(), 0
    for g, s in enumerate(starts):
        fast.random_playout(s, buf, g)
        moves3 += int(s[fast.TURN])
    batch = (time.perf_counter() - t) / moves3

    print(f"局数 {args.games}、手の数 {moves}（まとめては {moves3}）")
    print(f"正解版             {ref * 1e6:8.1f} µs/手")
    print(f"速い版（1手ずつ）  {step * 1e6:8.1f} µs/手  {ref / step:6.1f} 倍")
    print(f"速い版（まとめて） {batch * 1e6:8.1f} µs/手  {ref / batch:6.1f} 倍")


if __name__ == "__main__":
    main()
