"""終盤の読み切り（GTO 研究の物差し）。

2人・ゼロ和なので、先手の勝つ見込み（勝ち1・引き分け0.5・負け0）を、先手は大きく・後手は小さくしようとする。
山札から何が出るかは、残りの山札から等しい確率で出るとして平均する（期待値つきのミニマックス）。
読みの深さで終わらない局面は「0〜1 のどれか」として扱い、見込みを区間 [下限, 上限] で返す。
区間の幅が0なら、その局面は（下の前提のもとで）正確に解けている。

前提（ここが厳密でない所）:
- 相手の伏せ予約札は、本当の札が分かっているものとして読む（神の目の上限）。
- 10枚を超えたときの戻し方は、agents.reduce_actions と同じ1通りだけを読む。
"""

from __future__ import annotations

from collections.abc import Callable

from .agents import reduce_actions
from .game import BUY, RESERVE, Action, State, apply, legal_actions, result

Interval = tuple[float, float]


def terminal_value(s: State) -> float:
    r = result(s)
    return 0.5 if r < 0 else float(r == 0)


def _draws(s: State, a: Action) -> tuple[int, list[int]] | None:
    """この手で山札から札が出るなら (レベル, 出うる札)。出ないなら None。"""
    if a.kind == RESERVE:
        level = a.arg[0]
    elif a.kind == BUY and a.arg[0] == "board":
        level = a.arg[1]
    else:
        return None
    deck = s.decks[level]
    return (level, sorted(set(deck))) if deck else None


def outcomes(s: State, a: Action) -> list[State]:
    """手を指したあとの局面（山札から出る札ごとに1つ。どれも同じ確率）。"""
    d = _draws(s, a)
    if d is None:
        c = s.clone()
        apply(c, a)
        return [c]
    level, cards = d
    out = []
    for cid in cards:
        c = s.clone()
        deck = c.decks[level]
        deck.remove(cid)
        deck.append(cid)  # この札が一番上（次に出る）
        apply(c, a)
        out.append(c)
    return out


def solve(s: State, depth: int, moves: Callable[[State], list[Action]] | None = None) -> Interval:
    """先手から見た勝つ見込みの区間。depth は読む手番の数。"""
    if s.done:
        v = terminal_value(s)
        return v, v
    if depth == 0:
        return 0.0, 1.0
    gen = moves or (lambda x: reduce_actions(x, legal_actions(x)))
    acts = sorted(gen(s), key=lambda a: a.kind != BUY)  # 買う手から読む（早く決着がつきやすい）
    sure = 1.0 if s.current == 0 else 0.0  # 手番の人にとって確実な勝ち
    vals = []
    for a in acts:
        v = action_value(s, a, depth, gen)
        vals.append(v)
        if v[0] == v[1] == sure:
            break  # これより良い手は無い
    pick = max if s.current == 0 else min
    return pick(v[0] for v in vals), pick(v[1] for v in vals)


def action_value(s: State, a: Action, depth: int, moves=None) -> Interval:
    gen = moves or (lambda x: reduce_actions(x, legal_actions(x)))
    if depth == 1:
        # 最後の1手のあとは、山札から何が出ても値が変わらない（終わっているか、0〜1 のどれか）
        c = s.clone()
        apply(c, a)
        return solve(c, 0, gen)
    vals = [solve(c, depth - 1, gen) for c in outcomes(s, a)]
    n = len(vals)
    return sum(v[0] for v in vals) / n, sum(v[1] for v in vals) / n


def round_depth(s: State) -> int:
    """この一巡の終わりまでの手番の数（先手番なら2、後手番なら1）。"""
    return 2 - s.current


def judge(s: State, chosen: Action, depth: int | None = None) -> dict | None:
    """chosen が最善かを読み切りで調べる。決着がつかないときは None。

    返す値: verdict が "best"（どの手より悪くないと確か）か "mistake"（ほかの手より確実に悪い）、
    loss_min は悪手のとき、勝つ見込みを少なくともどれだけ損したか（手番の人から見て）。
    """
    depth = depth or round_depth(s)
    acts = reduce_actions(s, legal_actions(s))
    key = (chosen.kind, chosen.arg, chosen.noble)
    vals = {(a.kind, a.arg, a.noble): action_value(s, a, depth) for a in acts}
    if key not in vals:
        return None
    sign = 1 if s.current == 0 else -1

    def me(v: Interval) -> Interval:  # 手番の人から見た区間
        return (v[0], v[1]) if sign > 0 else (1 - v[1], 1 - v[0])

    mine = {k: me(v) for k, v in vals.items()}
    best_lo = max(v[0] for v in mine.values())
    best_hi = max(v[1] for v in mine.values())
    c_lo, c_hi = mine[key]
    if c_hi < best_lo:  # ほかの手より確実に悪い
        return {"verdict": "mistake", "loss_min": best_lo - c_hi}
    if c_lo >= best_hi:  # どの手より悪くないことが確か
        return {"verdict": "best", "loss_min": 0.0}
    return None  # 読みの深さでは言い切れない
