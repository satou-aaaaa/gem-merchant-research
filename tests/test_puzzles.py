"""次の一手クイズ（data/endgame_puzzles.json）が、書いてある局面で正しいかを確かめる。

2026-11-17: 局面を写さずに残したため、あとの手で書き換わった局面が問題になっていた（make_puzzles.state_json で直した）。
同じ種類の間違いを止めるため、問題の局面で正解・選択肢が指せる手か、読み切りの値が書いてある値と同じかを見る。
"""

import json
from pathlib import Path

import pytest

from gem_merchant import fast, game
from gem_merchant.endgame_fast import action_values, round_depth

ROOT = Path(__file__).resolve().parents[1]
PUZZLES = json.loads((ROOT / "data" / "endgame_puzzles.json").read_text(encoding="utf-8"))
EXTRA = 2  # scripts/make_puzzles.py と同じ


def to_state(st: dict) -> game.State:
    return game.State(
        st["bank"][:],
        {int(k): v[:] for k, v in st["decks"].items()},
        {int(k): v[:] for k, v in st["board"].items()},
        st["nobles"][:],
        [
            game.Player(q["tokens"][:], q["bonus"][:], q["points"], [tuple(r) for r in q["reserved"]], q["bought"], q["nobles"][:])
            for q in st["players"]
        ],
        st["turn"],
        st["passes"],
        st["done"],
    )  # fmt: skip


def to_action(a: list) -> game.Action:
    arg = tuple(a[1]) if isinstance(a[1], list) else a[1]
    return game.Action(a[0], arg, tuple(a[2]), a[3])


def test_puzzles_are_legal_and_well_formed():
    assert len(PUZZLES) >= 20
    for p in PUZZLES:
        s = to_state(p["state"])
        assert not s.done and s.current == p["me"]
        legal = game.legal_actions(s)
        acts = [to_action(c["action"]) for c in p["choices"]]
        assert acts[0] == to_action(p["answer"])
        assert all(a in legal for a in acts), p["id"]
        assert len(set(acts)) == len(acts) >= 3
        best = p["choices"][0]
        assert all(c["hi"] <= best["lo"] - 0.15 + 1e-9 for c in p["choices"][1:]), p["id"]
        cards = sorted(c for v in s.decks.values() for c in v) + [
            c for v in s.board.values() for c in v if c >= 0
        ]
        cards += [c for q in s.players for c, _ in q.reserved]
        assert len(cards) + sum(q.bought for q in s.players) == 90  # 札が増えたり消えたりしていない


@pytest.mark.slow
def test_puzzle_values_match_solver():
    """書いてある勝つ見込みの区間が、その局面を読み切り直した値と同じ。"""
    for p in PUZZLES:
        s = to_state(p["state"])
        fs = fast.from_state(s)
        acts, vals, _ = action_values(fs, round_depth(fs) + EXTRA)
        if p["me"] == 1:
            vals = 1.0 - vals[:, ::-1]
        got = {
            fast.to_action(a)[:2] + (fast.to_action(a).noble,): (
                round(float(v[0]), 3),
                round(float(v[1]), 3),
            )
            for a, v in zip(acts, vals)
        }
        for c in p["choices"]:
            a = to_action(c["action"])
            assert got[(a.kind, a.arg, a.noble)] == (c["lo"], c["hi"]), p["id"]


def test_seed_list_is_used():
    # --seed-list を読んでも使わず、いつも 3000 からの局を作っていたことがある
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import make_puzzles

    assert make_puzzles.pick_seeds("3067, 3075", 3000, 60) == [3067, 3075]
    assert make_puzzles.pick_seeds("", 3000, 3) == [3000, 3001, 3002]
