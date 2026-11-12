"""自作のカード90枚と貴族10枚。

元のゲームのカードを写さず、レベルごとの「値段の形」から機械的に作る（NOTICE.md）。
枚数と割合は元のゲームと同じ: レベル1は各色8枚、レベル2は各色6枚、レベル3は各色4枚。
値段の形は、自分の色を0番として「何番先の色を何枚」で書き、5色に回して使う。
点と値段の釣り合いは、段階4の自己対戦で偏りが分かったら直す（直したらテストの数も直す）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .rules import COLORS

N_COLORS = len(COLORS)


@dataclass(frozen=True)
class Card:
    id: int
    level: int
    color: int  # 割引の色（COLORS の番号）
    points: int
    cost: tuple[int, int, int, int, int]  # 色ごとの値段


@dataclass(frozen=True)
class Noble:
    id: int
    need: tuple[int, int, int, int, int]  # 色ごとに要るカードの枚数
    points: int = 3


# (点, {何番先の色: 枚数})。0番は自分の色
PATTERNS: dict[int, list[tuple[int, dict[int, int]]]] = {
    1: [
        (0, {1: 1, 2: 1, 3: 1, 4: 1}),
        (0, {1: 1, 2: 2, 3: 1, 4: 1}),
        (0, {2: 2, 4: 2}),
        (0, {1: 2, 3: 1}),
        (0, {3: 3}),
        (0, {0: 1, 1: 1, 4: 3}),
        (0, {1: 1, 2: 2, 3: 2}),
        (1, {2: 4}),
    ],
    2: [
        (1, {1: 3, 3: 2, 4: 2}),
        (1, {0: 2, 2: 3, 4: 3}),
        (2, {1: 4, 2: 2, 3: 1}),
        (2, {3: 5}),
        (2, {0: 3, 4: 5}),
        (3, {0: 6}),
    ],
    3: [
        (3, {1: 3, 2: 3, 3: 5, 4: 3}),
        (4, {4: 7}),
        (4, {0: 3, 3: 6, 4: 3}),
        (5, {0: 3, 4: 7}),
    ],
}


def make_cards() -> list[Card]:
    cards: list[Card] = []
    for level in (1, 2, 3):
        for color in range(N_COLORS):
            for points, shape in PATTERNS[level]:
                cost = [0] * N_COLORS
                for step, n in shape.items():
                    cost[(color + step) % N_COLORS] += n
                cards.append(Card(len(cards), level, color, points, tuple(cost)))
    return cards


def make_nobles() -> list[Noble]:
    """2色を4枚ずつ（5枚）と、3色を3枚ずつ（5枚）。どれも3点。"""
    nobles: list[Noble] = []
    for c in range(N_COLORS):
        need = [0] * N_COLORS
        need[c] = need[(c + 2) % N_COLORS] = 4
        nobles.append(Noble(len(nobles), tuple(need)))
    for c in range(N_COLORS):
        need = [0] * N_COLORS
        for step in (0, 1, 3):
            need[(c + step) % N_COLORS] = 3
        nobles.append(Noble(len(nobles), tuple(need)))
    return nobles


CARDS: list[Card] = make_cards()
NOBLES: list[Noble] = make_nobles()
