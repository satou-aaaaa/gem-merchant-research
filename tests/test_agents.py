import random
from collections import Counter

from gem_merchant import game
from gem_merchant.agents import (
    GreedyAgent,
    MCTSAgent,
    RandomAgent,
    determinize,
    evaluate,
    reduce_actions,
)
from gem_merchant.arena import match, wilson
from gem_merchant.cards import CARDS
from gem_merchant.game import RESERVE, Action


def _play(agents, seed, plies):
    s = game.new_game(seed)
    rng = random.Random(seed)
    for _ in range(plies):
        if s.done:
            break
        a = agents[s.current].act(s, rng)
        assert a in game.legal_actions(s)
        game.apply(s, a)
    return s


def test_agents_choose_legal_actions():
    _play([GreedyAgent(), MCTSAgent(30)], 3, 40)
    _play([RandomAgent(), GreedyAgent()], 4, 40)


def test_reduce_keeps_one_return_per_move():
    s = game.new_game(1)
    s.players[0].tokens = [2, 2, 2, 2, 2, 0]
    s.bank = [2, 2, 2, 2, 2, 5]
    acts = game.legal_actions(s)
    red = reduce_actions(s, acts)
    assert len(red) < len(acts)
    assert len({(a.kind, a.arg, a.noble) for a in red}) == len(red)


def test_determinize_hides_only_unknown_cards():
    s = game.new_game(2)
    game.apply(s, Action(RESERVE, (2, -1)))  # 先手が伏せて予約
    game.apply(s, Action(RESERVE, (1, -1)))  # 後手も伏せて予約
    d = determinize(s, 0, random.Random(0))
    assert d.players[0].reserved == s.players[0].reserved  # 自分の札はそのまま
    assert d.board == s.board
    for level in (1, 2, 3):
        before = Counter(s.decks[level]) + Counter(
            c for c, _ in s.players[1].reserved if CARDS[c].level == level
        )
        after = Counter(d.decks[level]) + Counter(
            c for c, _ in d.players[1].reserved if CARDS[c].level == level
        )
        assert before == after
    assert CARDS[d.players[1].reserved[0][0]].level == 1


def test_evaluate_is_symmetric():
    s = _play([GreedyAgent(), GreedyAgent()], 5, 20)
    assert abs(evaluate(s, 0) + evaluate(s, 1) - 1) < 1e-9


def test_match_and_wilson():
    summary = match(GreedyAgent(), RandomAgent(), pairs=3, seed=0)
    assert summary.games == 6 and 0 <= summary.wins_a <= 6
    lo, hi = wilson(30, 40)
    assert 0.58 < lo < 0.62 and 0.85 < hi < 0.87
