import random

import pytest

from gem_merchant import game, rules
from gem_merchant.cards import CARDS, NOBLES
from gem_merchant.game import BUY, PASS, RESERVE, TAKE2, TAKE3, Action

START = [4, 4, 4, 4, 4, 5]


def kinds(state):
    return {a.kind for a in game.legal_actions(state)}


def test_setup():
    s = game.new_game(1)
    assert s.bank == START
    assert len(s.nobles) == 3
    for level in (1, 2, 3):
        assert len(s.board[level]) == 4
        assert len(s.decks[level]) == rules.CARDS_PER_LEVEL[level] - 4


def test_take3_must_be_three_when_three_colors_left():
    s = game.new_game(1)
    takes = [a for a in game.legal_actions(s) if a.kind == TAKE3]
    assert len(takes) == 10 and all(len(a.arg) == 3 for a in takes)
    s.bank = [0, 0, 0, 1, 2, 5]
    takes = {a.arg for a in game.legal_actions(s) if a.kind == TAKE3}
    assert takes == {(3,), (4,), (3, 4)}  # 2色しかなければ1〜2枚


def test_take2_needs_four():
    s = game.new_game(1)
    assert {a.arg for a in game.legal_actions(s) if a.kind == TAKE2} == set(range(5))
    s.bank[0] = 3
    assert 0 not in {a.arg for a in game.legal_actions(s) if a.kind == TAKE2}


def test_reserve_gives_gold_and_limit_three():
    s = game.new_game(1)
    game.apply(s, Action(RESERVE, (1, 0)))
    assert s.players[0].tokens[5] == 1 and s.bank[5] == 4
    assert s.board[1][0] >= 0  # 山札から補充
    s.turn = 0
    game.apply(s, Action(RESERVE, (2, -1)))
    assert s.players[0].reserved[-1][1] is True  # 伏せて取った
    s.turn = 0
    s.bank[5] = 0
    game.apply(s, Action(RESERVE, (3, 1)))  # 金が無くても予約できる
    assert s.players[0].tokens[5] == 2 and len(s.players[0].reserved) == 3
    s.turn = 0
    assert RESERVE not in kinds(s)


def test_buy_with_bonus_and_gold():
    s = game.new_game(1)
    p = s.players[0]
    cid = s.board[2][0]
    cost = CARDS[cid].cost
    color = max(range(5), key=lambda c: cost[c])
    p.bonus[color] = 1  # 1枚分の割引
    need = [max(0, cost[c] - p.bonus[c]) for c in range(5)]
    p.tokens = need[:]
    p.tokens[color] -= 1  # 1枚足りない分を金で払う
    p.tokens.append(1)
    s.bank = [START[c] - p.tokens[c] for c in range(6)]
    buys = [a for a in game.legal_actions(s) if a.kind == BUY and a.arg == ("board", 2, 0)]
    assert buys
    game.apply(s, buys[0])
    assert p.tokens == [0] * 6 and s.bank == START
    assert p.bought == 1 and p.points == CARDS[cid].points and p.bonus[CARDS[cid].color] >= 1


def test_cannot_buy_without_enough():
    s = game.new_game(1)
    assert BUY not in kinds(s)


def test_return_over_ten():
    s = game.new_game(1)
    s.players[0].tokens = [2, 2, 2, 2, 1, 0]  # 9枚
    s.bank = [START[c] - s.players[0].tokens[c] for c in range(6)]
    for a in game.legal_actions(s):
        if a.kind == TAKE3:
            assert sum(a.ret) == 2
        if a.kind == TAKE2:
            assert sum(a.ret) == 1
    a = next(a for a in game.legal_actions(s) if a.kind == TAKE3)
    game.apply(s, a)
    assert sum(s.players[0].tokens) == 10
    assert game.tokens_total(s) == START


def test_noble_is_mandatory_one_per_turn_and_chosen():
    s = game.new_game(1)
    s.nobles = [0, 1, 2]
    p = s.players[0]
    p.bonus = [4, 4, 4, 4, 4]  # 3枚とも条件を満たす
    acts = game.legal_actions(s)
    assert {a.noble for a in acts} == {0, 1, 2}  # 選べる。来ない手は無い
    game.apply(s, acts[0])
    assert len(p.nobles) == 1 and p.points == NOBLES[p.nobles[0]].points


def test_end_after_round_and_tiebreak():
    s = game.new_game(1)
    s.players[0].points = 15
    game.apply(s, Action(TAKE3, (0, 1, 2)))
    assert not s.done  # 後手も指してから終わる
    s.players[1].points = 15
    s.players[0].bought, s.players[1].bought = 6, 5
    game.apply(s, Action(TAKE3, (0, 1, 2)))
    assert s.done and game.result(s) == 1  # 同点なら買ったカードが少ない方
    s.players[1].bought = 6
    assert game.result(s) == -1


def test_pass_when_nothing_is_legal_and_double_pass_ends():
    s = game.new_game(1)
    s.bank = [0, 0, 0, 0, 0, 0]
    for p in s.players:
        p.reserved = [(0, False), (1, False), (2, False)]
    assert game.legal_actions(s) == [Action(PASS)]
    game.apply(s, Action(PASS))
    game.apply(s, Action(PASS))
    assert s.done


@pytest.mark.parametrize("seed", range(30))
def test_random_games_keep_invariants(seed):
    s = game.new_game(seed)
    rng = random.Random(seed)
    while not s.done:
        acts = game.legal_actions(s)
        assert len(set(acts)) == len(acts)
        game.apply(s, rng.choice(acts))
        assert game.tokens_total(s) == START
        assert all(sum(p.tokens) <= rules.MAX_TOKENS for p in s.players)
        assert all(len(p.reserved) <= rules.MAX_RESERVED for p in s.players)
        assert min(s.bank) >= 0 and all(min(p.tokens) >= 0 for p in s.players)
        cards = sum(len(d) for d in s.decks.values()) + sum(
            cid >= 0 for row in s.board.values() for cid in row
        )
        cards += sum(len(p.reserved) + p.bought for p in s.players)
        assert cards == 90
        assert s.turn < 1000
    assert game.result(s) in (-1, 0, 1)
