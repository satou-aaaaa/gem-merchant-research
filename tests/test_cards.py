from collections import Counter

from gem_merchant import rules
from gem_merchant.cards import CARDS, NOBLES


def test_counts_per_level_and_color():
    per = Counter((c.level, c.color) for c in CARDS)
    for level, n in rules.CARDS_PER_LEVEL.items():
        for color in range(5):
            assert per[(level, color)] == n // 5
    assert len(CARDS) == 90 and [c.id for c in CARDS] == list(range(90))


def test_costs_and_points_grow_with_level():
    for level, (lo, hi) in {1: (3, 6), 2: (5, 8), 3: (6, 14)}.items():
        for c in CARDS:
            if c.level == level:
                assert lo <= sum(c.cost) <= hi, c
    assert max(c.points for c in CARDS if c.level == 1) <= 1
    assert min(c.points for c in CARDS if c.level == 3) >= 3


def test_no_duplicate_cards():
    assert len({(c.level, c.color, c.cost) for c in CARDS}) == 90


def test_nobles():
    assert len(NOBLES) == rules.NOBLES_TOTAL
    assert all(n.points == 3 and sum(n.need) in (8, 9) for n in NOBLES)
    assert len({n.need for n in NOBLES}) == 10
