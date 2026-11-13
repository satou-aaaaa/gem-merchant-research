"""速いエンジン（fast.py）を、正解版（game.py）とランダム対局の毎手で照合する。"""

import random

import numpy as np
import pytest

from gem_merchant import fast, game


def _check_games(n_games: int, seed0: int) -> int:
    """n_games 局をランダムに指し、毎手で合法手の並び・局面・終わり・勝ち負けが一致するかを見る。"""
    buf = fast.new_buffer()
    moves = 0
    for g in range(n_games):
        ref = game.new_game(seed0 + g)
        s = fast.from_state(ref)
        rng = random.Random(seed0 + g)
        while True:
            acts = game.legal_actions(ref)
            n = fast.legal(s, buf)
            if ref.done:
                assert n == 0
                break
            assert [fast.to_action(buf[i]) for i in range(n)] == acts
            i = rng.randrange(n)
            game.apply(ref, acts[i])
            fast.apply(s, buf[i])
            assert np.array_equal(s, fast.from_state(ref))
            moves += 1
        assert fast.result(s) == game.result(ref)
    return moves


def test_matches_reference_quick():
    assert _check_games(40, 0) > 40 * 30


@pytest.mark.slow
def test_matches_reference_1000_games():
    assert _check_games(1000, 10_000) > 1000 * 30


def test_rare_cases():
    """払えないときのパス・10枚超えの戻し・貴族2枚から選ぶ、を正解版と比べる。"""
    buf = fast.new_buffer()
    # 場が空で何も取れない → パス
    s = game.new_game(3)
    s.bank = [0, 0, 0, 0, 0, 0]
    for lv in (1, 2, 3):
        s.board[lv] = [-1] * 4
        s.decks[lv] = []
    f = fast.from_state(s)
    n = fast.legal(f, buf)
    assert [fast.to_action(buf[i]) for i in range(n)] == game.legal_actions(s)
    # 9枚持って3色取る → 2枚戻す組み合わせ
    s = game.new_game(4)
    s.players[0].tokens = [2, 2, 2, 1, 1, 1]
    f = fast.from_state(s)
    n = fast.legal(f, buf)
    assert [fast.to_action(buf[i]) for i in range(n)] == game.legal_actions(s)
    assert any(buf[i, fast.A_RET : fast.A_RET + 6].sum() == 2 for i in range(n))
    # 貴族の条件を2枚同時に満たす
    s = game.new_game(5)
    s.players[0].bonus = [4, 4, 4, 4, 4]
    s.players[0].tokens = [3, 3, 3, 0, 0, 1]
    f = fast.from_state(s)
    n = fast.legal(f, buf)
    acts = game.legal_actions(s)
    assert [fast.to_action(buf[i]) for i in range(n)] == acts
    assert len({a.noble for a in acts}) >= 2


def test_random_playout_finishes():
    s = fast.from_state(game.new_game(7))
    assert fast.random_playout(s, fast.new_buffer(), 7) in (-1, 0, 1)
    assert s[fast.DONE] == 1
