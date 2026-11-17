"""MCTS の速い版（fast_mcts.py）の部品が正解版と同じかと、指す手が合法かを確かめる。"""

import random
from collections import Counter

import pytest

from gem_merchant import fast, game
from gem_merchant import fast_mcts as fm
from gem_merchant.agents import evaluate, make_agent, reduce_actions
from gem_merchant.arena import match
from gem_merchant.cards import CARDS


def _states(n_games: int, seed0: int):
    """greedy 同士（ときどきランダム）で指した局面を全部返す。予約も混ざるようにする。"""
    agent = make_agent("greedy")
    for g in range(n_games):
        s = game.new_game(seed0 + g)
        rng = random.Random(seed0 + g)
        while not s.done:
            yield s.clone()
            acts = game.legal_actions(s)
            a = rng.choice(acts) if rng.random() < 0.3 else agent.act(s, rng)
            game.apply(s, a)
        yield s.clone()


def test_evaluate_matches_reference():
    n = 0
    for s in _states(4, 300):
        fs = fast.from_state(s)
        for i in (0, 1):
            assert fm.evaluate(fs, i) == pytest.approx(evaluate(s, i), abs=1e-12)
        n += 1
    assert n > 100


def test_reduced_matches_reduce_actions():
    buf, out = fast.new_buffer(), fast.new_buffer()
    for s in _states(2, 310):
        m = fm.reduced(fast.from_state(s), buf, out)
        assert [fast.to_action(out[i]) for i in range(m)] == reduce_actions(
            s, game.legal_actions(s)
        )


def _hidden(fs, viewer: int, lv: int) -> Counter:
    """viewer に見えない札（山札と相手の伏せ予約）のうち、レベル lv のもの。"""
    cards = list(fs[fast.DECK[lv - 1] : fast.DECK[lv - 1] + fs[fast.DECKN + lv - 1]])
    b = fast.PL[1 - viewer]
    for k in range(fs[b + fast.P_RESN]):
        cid = fs[b + fast.P_RES + k]
        if fs[b + fast.P_HID + k] and CARDS[cid].level == lv:
            cards.append(cid)
    return Counter(int(c) for c in cards)


def test_determinize_keeps_what_viewer_sees():
    n_hidden = 0
    for s in _states(4, 320):
        fs = fast.from_state(s)
        viewer = s.current
        d = fs.copy()
        fm.determinize(d, viewer)
        opp = fast.PL[1 - viewer]
        same = (d != fs).nonzero()[0]
        for j in same:  # 変わってよいのは山札と相手の伏せ予約の札だけ
            in_deck = any(fast.DECK[k] <= j < fast.DECK[k] + 40 for k in range(3))
            in_res = opp + fast.P_RES <= j < opp + fast.P_RES + 3
            assert in_deck or in_res
            if in_res:
                assert fs[opp + fast.P_HID + (j - opp - fast.P_RES)]
        for lv in (1, 2, 3):
            assert _hidden(d, viewer, lv) == _hidden(fs, viewer, lv)
        n_hidden += int(fs[opp + fast.P_HID : opp + fast.P_HID + 3].sum())
    assert n_hidden > 0  # 伏せ予約のある局面も調べた


def test_agent_plays_legal_moves():
    agent = make_agent("fmcts200")
    rng = random.Random(0)
    for g in range(2):
        s = game.new_game(400 + g)
        while not s.done:
            a = agent.act(s, rng)
            assert a in game.legal_actions(s)
            game.apply(s, a)


def test_beats_greedy():
    r = match(make_agent("fmcts400"), make_agent("greedy"), pairs=5, seed=900)
    assert r.rate >= 0.6
