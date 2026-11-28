"""ブラウザ版のエンジンと AI（web/gem_engine.js）が Python 版（game.py・agents.py）と一致するかの検証。

node で tests/play_js_harness.js を動かし、同じ最初の局面・同じ手の列で、毎手の合法手の並び・
手の減らし方・評価の値・指したあとの局面が同じかを見る。node が無い環境では飛ばす
（GitHub Actions の ubuntu-latest には入っている）。
"""

import json
import random
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from gem_merchant import game
from gem_merchant.agents import GreedyAgent, evaluate, reduce_actions
from gem_merchant.cards import CARDS, NOBLES
from gem_merchant.fast import from_state
from gem_merchant.fast_mcts import evaluate_w

ROOT = Path(__file__).resolve().parents[1]
CHAMPION = np.load(ROOT / "models" / "eval_champion.npy")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node が必要")


def run_js(args: dict, timeout: int = 600):
    r = subprocess.run(
        [NODE, str(ROOT / "tests" / "play_js_harness.js")],
        input=json.dumps(args), capture_output=True, text=True, check=True, timeout=timeout,
    )  # fmt: skip
    return json.loads(r.stdout)


def state_json(s: game.State) -> dict:
    return {
        "bank": s.bank,
        "decks": {str(k): v for k, v in s.decks.items()},
        "board": {str(k): v for k, v in s.board.items()},
        "nobles": s.nobles,
        "players": [
            {
                "tokens": p.tokens,
                "bonus": p.bonus,
                "points": p.points,
                "reserved": [[c, b] for c, b in p.reserved],
                "bought": p.bought,
                "nobles": p.nobles,
            }
            for p in s.players
        ],
        "turn": s.turn,
        "passes": s.passes,
        "done": s.done,
    }


def snap(s: game.State) -> dict:
    return {
        "bank": s.bank,
        "decks": [s.decks[k] for k in (1, 2, 3)],
        "board": [s.board[k] for k in (1, 2, 3)],
        "nobles": s.nobles,
        "players": [
            [p.tokens, p.bonus, p.points, [[c, b] for c, b in p.reserved], p.bought, p.nobles]
            for p in s.players
        ],
        "turn": s.turn,
        "passes": s.passes,
        "done": s.done,
    }


def act(a: game.Action) -> list:
    arg = list(a.arg) if isinstance(a.arg, tuple) else a.arg
    return [a.kind, arg, list(a.ret), a.noble]


def test_cards_match():
    out = run_js({"cmd": "cards"})
    assert out["cards"] == [[c.level, c.color, c.points, list(c.cost)] for c in CARDS]
    assert out["nobles"] == [[list(n.need), n.points] for n in NOBLES]


def _games(n: int, seed0: int):
    """ランダムな手の局と greedy 同士の局を混ぜる（貴族・10枚超え・予約札の購入が十分に出るように）。"""
    out = []
    greedy = GreedyAgent()
    for g in range(n):
        s = game.new_game(seed0 + g)
        start = json.loads(json.dumps(state_json(s)))  # 指す前の写し
        rng = random.Random(seed0 + g)
        picks, states = [], []
        while not s.done:
            acts = game.legal_actions(s)
            if g % 2 and rng.random() < 0.8:
                a = greedy.act(s, rng)
                k = acts.index(a)
            else:
                k = rng.randrange(len(acts))
            states.append(s.clone())
            picks.append(k)
            game.apply(s, acts[k])
        out.append((start, picks, states, s))
    return out


def test_engine_matches_python():
    games = _games(16, 0)
    js = run_js({"cmd": "replay", "games": [{"start": st, "picks": pk} for st, pk, _, _ in games]})
    seen = {"noble": 0, "ret": 0, "buy_reserved": 0, "blind": 0}
    for (_, picks, states, end), jg in zip(games, js):
        assert len(jg["steps"]) == len(picks)
        for s, k, step in zip(states, picks, jg["steps"]):
            acts = game.legal_actions(s)
            assert step["legal"] == [act(a) for a in acts]
            assert step["reduced"] == [act(a) for a in reduce_actions(s, acts)]
            # AI の評価は学んだ重み（fast_mcts.evaluate_w とチャンピオン）、手作りの評価も残して照合する
            fs = from_state(s)
            want = [evaluate_w(fs, 0, CHAMPION), evaluate_w(fs, 1, CHAMPION)]
            assert step["eval"] == pytest.approx(want, abs=1e-12)
            assert step["hand"] == pytest.approx([evaluate(s, 0), evaluate(s, 1)], abs=1e-12)
            assert step["handW"] == pytest.approx(step["hand"], abs=1e-9)  # やさしいの重み
            t = s.clone()
            game.apply(t, acts[k])
            assert step["after"] == snap(t)
            a = acts[k]
            seen["noble"] += a.noble >= 0
            seen["ret"] += sum(a.ret) > 0
            seen["buy_reserved"] += a.kind == game.BUY and a.arg[0] == "reserved"
            seen["blind"] += a.kind == game.RESERVE and a.arg[1] < 0
        assert jg["result"] == game.result(end)
    assert all(v > 0 for v in seen.values()), seen  # 珍しい手も確かめている


def test_weights_are_champion():
    """対戦ページの AI の重みは models/eval_champion.npy と同じ（違えば py scripts/build_pages.py で写す）。"""
    assert run_js({"cmd": "weights"}) == CHAMPION.tolist()


def test_new_game_is_valid():
    """JS の新しい局（乱数は Python と別）も、Python のエンジンで正しい最初の局面になっている。"""
    for g in run_js({"cmd": "newgame", "seeds": [1, 2, 3]}):
        sn = g["snap"]
        cards = sorted(c for row in sn["decks"] + sn["board"] for c in row)
        assert cards == list(range(len(CARDS)))
        assert [len(b) for b in sn["board"]] == [4, 4, 4]
        assert len(sn["nobles"]) == 3 and len(set(sn["nobles"])) == 3
        assert sn["bank"] == [4, 4, 4, 4, 4, 5]
        assert g["nlegal"] == 10 + 5 + 15  # 3色の組10・同じ色2枚5・予約（表12＋山3）


@pytest.mark.slow
def test_js_mcts_beats_greedy():
    """ブラウザの「ふつう」（mcts600）は「やさしい」（greedy）に勝ち越す（Python 版の mcts400 は 0.83）。"""
    res = run_js({"cmd": "match", "a": "normal", "b": "easy", "seeds": list(range(10))})
    assert sum(res) / len(res) >= 0.65
