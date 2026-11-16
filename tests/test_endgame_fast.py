"""終盤の読み切りの速い版（endgame_fast.py）が、正解版（endgame.py）と同じ値・同じ判定を返すか。"""

import random

import pytest

from gem_merchant import endgame, fast, game
from gem_merchant import endgame_fast as ef
from gem_merchant.agents import make_agent, reduce_actions
from gem_merchant.game import BUY, TAKE3

from .test_endgame import _rich_state


def _late_states(n_games: int, seed0: int, min_points: int):
    """greedy 同士で指し、誰かが min_points 点以上の局面と、そこで greedy が選んだ手を返す。"""
    agent = make_agent("greedy")
    for g in range(n_games):
        s = game.new_game(seed0 + g)
        rng = random.Random(seed0 + g)
        while not s.done:
            a = agent.act(s, rng)
            if max(p.points for p in s.players) >= min_points:
                yield s.clone(), a
            game.apply(s, a)


def test_reduced_matches_reduce_actions():
    buf = fast.new_buffer()
    for s, _ in _late_states(3, 500, 0):
        m = ef.reduced(fast.from_state(s), buf)
        assert [fast.to_action(buf[i]) for i in range(m)] == reduce_actions(
            s, game.legal_actions(s)
        )


def _check_against_reference(n_games: int, seed0: int, min_points: int, extra: int) -> int:
    n = 0
    for s, a in _late_states(n_games, seed0, min_points):
        fs = fast.from_state(s)
        d = endgame.round_depth(s)
        assert ef.round_depth(fs) == d
        assert ef.solve(fs, d + extra) == endgame.solve(s, d + extra)
        r = ef.judge(fs, a, d)
        if r is not None:
            r.pop("nodes")
        assert r == endgame.judge(s, a, d)
        n += 1
    return n


def test_solve_and_judge_match_reference():
    assert _check_against_reference(3, 2000, 9, 0) > 20


@pytest.mark.slow
def test_solve_matches_reference_one_more_turn():
    assert _check_against_reference(2, 2000, 9, 1) > 10


def test_hand_made_positions():
    s = _rich_state()
    fs = fast.from_state(s)
    buy = next(a for a in game.legal_actions(s) if a.kind == BUY and a.arg == ("board", 1, 0))
    take = next(a for a in game.legal_actions(s) if a.kind == TAKE3)
    assert ef.judge(fs, buy, 2)["verdict"] == "best"
    assert ef.solve(fs, 2)[0] == 1.0
    assert ef.solve(fs, 4) == (1.0, 1.0)
    r = ef.judge(fs, take, 2)
    if r is not None:
        r.pop("nodes")
    assert r == endgame.judge(s, take, 2)


def test_far_from_the_end_is_cut_without_reading():
    fs = fast.from_state(game.new_game(0))  # 0点どうし。4手番では誰も15点に届かない
    acts, vals, stats = ef.action_values(fs, 4)
    assert (vals[:, 0] == 0).all() and (vals[:, 1] == 1).all()
    assert stats[0] == stats[1] >= len(acts)  # 根の各手のすぐ下で、読まずに切れている
