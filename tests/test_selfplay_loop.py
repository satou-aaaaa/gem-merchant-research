"""自己対戦で評価の重みを学ぶループ（R-004、scripts/selfplay_loop.py）の部品を確かめる。"""

import importlib.util
import random
from pathlib import Path

import numpy as np
import pytest

from gem_merchant import fast, game
from gem_merchant import fast_mcts as fm
from gem_merchant.agents import make_agent

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("selfplay_loop", ROOT / "scripts/selfplay_loop.py")
loop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loop)


def _states(n_games: int, seed0: int):
    agent = make_agent("greedy")
    for g in range(n_games):
        s = game.new_game(seed0 + g)
        rng = random.Random(seed0 + g)
        while not s.done:
            yield fast.from_state(s)
            acts = game.legal_actions(s)
            a = rng.choice(acts) if rng.random() < 0.3 else agent.act(s, rng)
            game.apply(s, a)


def test_hand_weights_give_hand_evaluation():
    n = 0
    for fs in _states(3, 500):
        for i in (0, 1):
            assert fm.evaluate_w(fs, i, fm.HAND_WEIGHTS) == pytest.approx(
                fm.evaluate(fs, i), abs=1e-12
            )
        n += 1
    assert n > 100


def test_diff_features_are_antisymmetric_and_split_by_phase():
    x0 = np.empty(2 * fm.N_FEAT)
    x1 = np.empty(2 * fm.N_FEAT)
    for fs in _states(2, 510):
        fm.diff_features(fs, 0, x0)
        fm.diff_features(fs, 1, x1)
        assert np.allclose(x0, -x1)
        a = fm.phase(fs)
        f0 = np.empty(fm.N_FEAT)
        f1 = np.empty(fm.N_FEAT)
        fm.features(fs, 0, f0)
        fm.features(fs, 1, f1)
        assert np.allclose(x0[: fm.N_FEAT] + x0[fm.N_FEAT :], f0 - f1)
        assert np.allclose(x0[fm.N_FEAT :], a * (f0 - f1))


def test_fit_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    true = np.array([1.0, -0.5, 0.0, 2.0])
    x = rng.normal(size=(20000, 4))
    y = (rng.random(20000) < 1 / (1 + np.exp(-(x @ true)))).astype(float)
    b = loop.fit(x, y)
    assert np.allclose(b, true, atol=0.08)
    assert loop.log_loss(x, y, b) < loop.log_loss(x, y, np.zeros(4))


def test_selfplay_records_positions_and_outcomes():
    x, y, capped = loop.play(fm.HAND_WEIGHTS, fm.HAND_WEIGHTS, 30, 7, True)
    assert x.shape == (len(y), 2 * fm.N_FEAT)
    assert set(np.unique(y)) <= {0.0, 0.5, 1.0}
    assert len(y) > 20
    assert isinstance(capped, bool)


def test_agent_with_weight_file_plays_legal_moves(tmp_path):
    p = tmp_path / "w.npy"
    np.save(p, fm.HAND_WEIGHTS * 1.5)
    agent = make_agent(f"fmcts100@{p}")
    assert np.allclose(agent.weights, fm.HAND_WEIGHTS * 1.5)
    rng = random.Random(0)
    s = game.new_game(42)
    for _ in range(30):
        if s.done:
            break
        a = agent.act(s, rng)
        assert a in game.legal_actions(s)
        game.apply(s, a)
