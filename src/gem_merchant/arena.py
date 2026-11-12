"""対戦と集計。

同じシード（山札の順）で先手・後手を入れ替えた2局を1組にして、山札の運の差を打ち消す
（carcassonne-research の arena.py と同じ考え方）。勝率は Wilson の95%区間で出す。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .game import apply, new_game, result


@dataclass
class GameResult:
    seed: int
    p0: str
    p1: str
    winner: int  # -1 は引き分け
    points: tuple[int, int]
    turns: int


def play_game(seed: int, a0, a1) -> GameResult:
    s = new_game(seed)
    agents = (a0, a1)
    rngs = [random.Random(seed * 2 + i) for i in (0, 1)]
    while not s.done:
        i = s.current
        apply(s, agents[i].act(s, rngs[i]))
    return GameResult(
        seed, a0.name, a1.name, result(s), (s.players[0].points, s.players[1].points), s.turn
    )


def wilson(wins: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


@dataclass
class Summary:
    games: int
    wins_a: float  # 引き分けは0.5勝
    diff_a: float  # A の平均点差（A−B）
    first_wins: float  # 先手の勝ち（引き分け0.5）

    @property
    def rate(self) -> float:
        return self.wins_a / self.games

    def __str__(self) -> str:
        lo, hi = wilson(self.wins_a, self.games)
        return (
            f"{self.games}局 A の勝率 {self.rate:.3f} [{lo:.3f}, {hi:.3f}] "
            f"平均点差 {self.diff_a:+.2f} 先手の勝率 {self.first_wins / self.games:.3f}"
        )


def match(a, b, pairs: int, seed: int = 0) -> Summary:
    """A と B を pairs 組（2*pairs 局）戦わせる。"""
    wins = diff = first = 0.0
    for k in range(pairs):
        for a_first in (True, False):
            r = play_game(seed + k, a, b) if a_first else play_game(seed + k, b, a)
            ia = 0 if a_first else 1
            wins += 0.5 if r.winner < 0 else float(r.winner == ia)
            first += 0.5 if r.winner < 0 else float(r.winner == 0)
            diff += r.points[ia] - r.points[1 - ia]
    n = 2 * pairs
    return Summary(n, wins, diff / n, first)
