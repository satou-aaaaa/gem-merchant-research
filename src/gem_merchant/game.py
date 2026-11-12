"""ルールエンジン（2人対戦、正解版）。分かりやすさを優先し、速さは後で別に作る。

ルールは docs/RESEARCH.md「ルールの要点」（公式ルールブックと公式 FAQ で確かめたもの）。
エンジンが決めている細部:
- 違う色を取る手は、場に3色以上あれば必ず3枚。2色以下しかなければ、ある色から1〜2枚。
- 払うときは、割引のあと手持ちの宝石を先に使い、足りない分だけ金を使う
  （金は宝石があっても使えるが、宝石を残して金を使って得をする場面はほぼ無いので、手を減らすために省く）。
- 10枚を超えたら、戻すチップの組み合わせ（金も含む）を手の一部として選ぶ。
- 貴族は手番の終わりに、条件を満たしていれば必ず1枚来る（断れない、公式 FAQ）。2枚以上なら手の一部として選ぶ。
- 指せる手が無いときはパス。全員が続けてパスしたら、そこで終わる（ルールに無いので決めた）。
- 15点以上の人が出たら、その一巡（後手の手番）まで指して終わる。
- 誰も買えずにチップを取って戻すだけになると終わらないので、MAX_TURNS 手番で打ち切り、その時の点で勝ち負けを決める（ルールに無いので決めた）。
"""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import NamedTuple

from . import rules
from .cards import CARDS, NOBLES

GOLD = 5  # チップの配列の6番目が金
N = 5  # 宝石の色の数
N_PLAYERS = 2

TAKE3, TAKE2, RESERVE, BUY, PASS = "take3", "take2", "reserve", "buy", "pass"
NO_RET = (0, 0, 0, 0, 0, 0)
MAX_TURNS = 200  # 打ち切りの手番の数（ふつうの対局は30〜70手番で終わる）


class Action(NamedTuple):
    kind: str
    # take3: 色の組 / take2: 色 / reserve: (レベル, 場の位置。-1 は山札の一番上)
    # buy: ("board", レベル, 位置) か ("reserved", 予約札の番号)
    arg: object = None
    ret: tuple[int, ...] = NO_RET  # 10枚を超えた分として戻すチップ（6色）
    noble: int = -1  # この手番に来る貴族の id（来ないときは -1）


@dataclass
class Player:
    tokens: list[int] = field(default_factory=lambda: [0] * 6)
    bonus: list[int] = field(default_factory=lambda: [0] * N)
    points: int = 0
    reserved: list[tuple[int, bool]] = field(default_factory=list)  # (カード id, 伏せて取ったか)
    bought: int = 0
    nobles: list[int] = field(default_factory=list)


@dataclass
class State:
    bank: list[int]
    decks: dict[int, list[int]]  # レベルごとの山札（末尾が一番上）。相手には見えない
    board: dict[int, list[int]]  # レベルごとの表向き4枚（空きは -1）
    nobles: list[int]
    players: list[Player]
    turn: int = 0  # これまでの手番の数
    passes: int = 0  # 続けてパスした回数
    done: bool = False

    @property
    def current(self) -> int:
        return self.turn % N_PLAYERS

    def clone(self) -> State:
        return State(
            self.bank[:],
            {k: v[:] for k, v in self.decks.items()},
            {k: v[:] for k, v in self.board.items()},
            self.nobles[:],
            [
                Player(p.tokens[:], p.bonus[:], p.points, p.reserved[:], p.bought, p.nobles[:])
                for p in self.players
            ],
            self.turn,
            self.passes,
            self.done,
        )


def new_game(seed: int) -> State:
    rng = random.Random(seed)
    decks: dict[int, list[int]] = {}
    board: dict[int, list[int]] = {}
    for level in (1, 2, 3):
        ids = [c.id for c in CARDS if c.level == level]
        rng.shuffle(ids)
        board[level] = [ids.pop() for _ in range(rules.FACE_UP_PER_LEVEL)]
        decks[level] = ids
    nobles = [n.id for n in NOBLES]
    rng.shuffle(nobles)
    bank = [rules.GEMS_PER_COLOR_2P] * N + [rules.GOLD]
    return State(
        bank, decks, board, nobles[: rules.NOBLES_2P], [Player() for _ in range(N_PLAYERS)]
    )


def effective_cost(p: Player, card_id: int) -> list[int]:
    """割引のあとに払う宝石の枚数（色ごと）。"""
    cost = CARDS[card_id].cost
    return [max(0, cost[c] - p.bonus[c]) for c in range(N)]


def payment(p: Player, card_id: int) -> list[int] | None:
    """払うチップ（6色）。払えないときは None。宝石を先に使い、足りない分を金で払う。"""
    need = effective_cost(p, card_id)
    pay = [min(need[c], p.tokens[c]) for c in range(N)]
    short = sum(need) - sum(pay)
    if short > p.tokens[GOLD]:
        return None
    return pay + [short]


def _returns(tokens: list[int], excess: int) -> list[tuple[int, ...]]:
    """10枚を超えた分 excess 枚を戻す組み合わせ（6色）。"""
    if excess <= 0:
        return [NO_RET]
    out = []
    for combo in itertools.product(*(range(min(t, excess) + 1) for t in tokens)):
        if sum(combo) == excess:
            out.append(combo)
    return out


def _eligible_nobles(state: State, bonus: list[int]) -> list[int]:
    return [n for n in state.nobles if all(bonus[c] >= NOBLES[n].need[c] for c in range(N))]


def _main_actions(state: State) -> list[Action]:
    p = state.players[state.current]
    bank = state.bank
    acts: list[Action] = []
    avail = [c for c in range(N) if bank[c] > 0]
    if len(avail) >= 3:
        acts += [Action(TAKE3, combo) for combo in itertools.combinations(avail, 3)]
    else:
        for k in range(1, len(avail) + 1):
            acts += [Action(TAKE3, combo) for combo in itertools.combinations(avail, k)]
    acts += [Action(TAKE2, c) for c in range(N) if bank[c] >= rules.TAKE_TWO_MIN_PILE]
    if len(p.reserved) < rules.MAX_RESERVED:
        for level in (1, 2, 3):
            acts += [
                Action(RESERVE, (level, i)) for i, cid in enumerate(state.board[level]) if cid >= 0
            ]
            if state.decks[level]:
                acts.append(Action(RESERVE, (level, -1)))
    for level in (1, 2, 3):
        for i, cid in enumerate(state.board[level]):
            if cid >= 0 and payment(p, cid) is not None:
                acts.append(Action(BUY, ("board", level, i)))
    for i, (cid, _) in enumerate(p.reserved):
        if payment(p, cid) is not None:
            acts.append(Action(BUY, ("reserved", i)))
    return acts


def _after_main(state: State, a: Action) -> tuple[list[int], list[int]]:
    """手の主な部分を指したあとの、手番の人のチップと割引（戻す・貴族の前）。"""
    p = state.players[state.current]
    tokens, bonus = p.tokens[:], p.bonus[:]
    if a.kind == TAKE3:
        for c in a.arg:
            tokens[c] += 1
    elif a.kind == TAKE2:
        tokens[a.arg] += 2
    elif a.kind == RESERVE:
        if state.bank[GOLD] > 0:
            tokens[GOLD] += 1
    elif a.kind == BUY:
        cid = _buy_card_id(state, a)
        pay = payment(p, cid)
        tokens = [t - x for t, x in zip(tokens, pay)]
        bonus[CARDS[cid].color] += 1
    return tokens, bonus


def _buy_card_id(state: State, a: Action) -> int:
    if a.arg[0] == "board":
        return state.board[a.arg[1]][a.arg[2]]
    return state.players[state.current].reserved[a.arg[1]][0]


def legal_actions(state: State) -> list[Action]:
    if state.done:
        return []
    out: list[Action] = []
    for a in _main_actions(state):
        tokens, bonus = _after_main(state, a)
        nobles = _eligible_nobles(state, bonus) or [-1]
        for ret in _returns(tokens, sum(tokens) - rules.MAX_TOKENS):
            for n in nobles:
                out.append(a._replace(ret=ret, noble=n))
    return out or [Action(PASS)]


def _refill(state: State, level: int, slot: int) -> None:
    deck = state.decks[level]
    state.board[level][slot] = deck.pop() if deck else -1


def apply(state: State, a: Action) -> None:
    """手を指す（state を書き換える）。合法かは確かめない（legal_actions から選ぶ）。"""
    p = state.players[state.current]
    bank = state.bank
    if a.kind == TAKE3:
        for c in a.arg:
            bank[c] -= 1
            p.tokens[c] += 1
    elif a.kind == TAKE2:
        bank[a.arg] -= 2
        p.tokens[a.arg] += 2
    elif a.kind == RESERVE:
        level, slot = a.arg
        if slot < 0:
            p.reserved.append((state.decks[level].pop(), True))
        else:
            p.reserved.append((state.board[level][slot], False))
            _refill(state, level, slot)
        if bank[GOLD] > 0:
            bank[GOLD] -= 1
            p.tokens[GOLD] += 1
    elif a.kind == BUY:
        cid = _buy_card_id(state, a)
        pay = payment(p, cid)
        for c in range(6):
            p.tokens[c] -= pay[c]
            bank[c] += pay[c]
        if a.arg[0] == "board":
            _refill(state, a.arg[1], a.arg[2])
        else:
            del p.reserved[a.arg[1]]
        card = CARDS[cid]
        p.bonus[card.color] += 1
        p.points += card.points
        p.bought += 1
    for c in range(6):
        p.tokens[c] -= a.ret[c]
        bank[c] += a.ret[c]
    if a.noble >= 0:
        state.nobles.remove(a.noble)
        p.nobles.append(a.noble)
        p.points += NOBLES[a.noble].points
    state.passes = state.passes + 1 if a.kind == PASS else 0
    last_in_round = state.current == N_PLAYERS - 1
    state.turn += 1
    if (
        state.passes >= N_PLAYERS
        or state.turn >= MAX_TURNS
        or last_in_round
        and any(q.points >= rules.WIN_POINTS for q in state.players)
    ):
        state.done = True


def result(state: State) -> int:
    """勝った人の番号。引き分けは -1。点が多い人、同点なら買ったカードが少ない人。"""
    keys = [(q.points, -q.bought) for q in state.players]
    best = max(keys)
    winners = [i for i, k in enumerate(keys) if k == best]
    return winners[0] if len(winners) == 1 else -1


def tokens_total(state: State) -> list[int]:
    """場と全員のチップの合計（色ごと）。いつも最初と同じになる。"""
    return [state.bank[c] + sum(q.tokens[c] for q in state.players) for c in range(6)]
