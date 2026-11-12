"""AI（手を選ぶもの）。どれも act(state, rng) で手を1つ返す。

- RandomAgent: 合法手から一様に選ぶ（エンジンの確かめ用）。
- GreedyAgent: 1手だけ先を見て、手作りの評価がいちばん良くなる手（比べる基準）。
- MCTSAgent: 見えない情報（山札の順・相手の伏せ予約）を毎回仮に決めて探す、情報集合 MCTS（SO-ISMCTS）。
  葉は手作りの評価で値を出す（最後まで指し切らない）。
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

from .cards import CARDS, NOBLES
from .game import BUY, GOLD, Action, State, apply, legal_actions, result

N = 5


# --- 手を減らす: 10枚を超えたときの戻し方は、余りの多い色から戻す1通りだけにする ---


def _ret_cost(state: State, a: Action) -> tuple:
    """戻し方の良し悪し（小さいほど良い）。金はなるべく残し、多く持っている色から戻す。"""
    return (a.ret[GOLD], tuple(-x for x in a.ret[:N]))


def reduce_actions(state: State, acts: Sequence[Action]) -> list[Action]:
    best: dict[tuple, Action] = {}
    for a in acts:
        key = (a.kind, a.arg, a.noble)
        if key not in best or _ret_cost(state, a) < _ret_cost(state, best[key]):
            best[key] = a
    return list(best.values())


# --- 手作りの評価 ---


def _shortfall(p, cid: int) -> int:
    """あと何枚のチップがあれば買えるか（金も数える）。"""
    cost = CARDS[cid].cost
    short = sum(max(0, cost[c] - p.bonus[c] - p.tokens[c]) for c in range(N))
    return max(0, short - p.tokens[GOLD])


def player_value(state: State, i: int) -> float:
    """i 番の人の持ち物の値打ち（点に換算）。"""
    p = state.players[i]
    v = float(p.points)
    v += 0.8 * sum(p.bonus)
    v += 0.1 * sum(p.tokens[:N]) + 0.2 * p.tokens[GOLD]
    for n in state.nobles:  # 来そうな貴族
        need = sum(max(0, NOBLES[n].need[c] - p.bonus[c]) for c in range(N))
        v += 3.0 / (1 + need) ** 1.5
    # 買えそうなカード（場と自分の予約札）: 点が高く、あと少しで買えるものほど値打ちがある
    targets = [cid for row in state.board.values() for cid in row if cid >= 0]
    targets += [cid for cid, _ in p.reserved]
    near = sorted(((CARDS[c].points + 0.8) / (1 + _shortfall(p, c)) for c in targets), reverse=True)
    v += 0.5 * sum(near[:3])
    return v


def evaluate(state: State, i: int) -> float:
    """i 番の人から見た勝ちやすさ（0〜1）。終わっていれば勝ち1・引き分け0.5・負け0。"""
    if state.done:
        r = result(state)
        return 0.5 if r < 0 else float(r == i)
    d = player_value(state, i) - player_value(state, 1 - i)
    return 1 / (1 + math.exp(-d / 4))


class RandomAgent:
    name = "random"

    def act(self, state: State, rng: random.Random) -> Action:
        return rng.choice(legal_actions(state))


class GreedyAgent:
    name = "greedy"

    def act(self, state: State, rng: random.Random) -> Action:
        me = state.current
        acts = reduce_actions(state, legal_actions(state))
        rng.shuffle(acts)
        best, best_v = acts[0], -1.0
        for a in acts:
            s = state.clone()
            apply(s, a)
            v = evaluate(s, me)
            if a.kind == BUY:
                v += 1e-6  # 同じ値なら買う
            if v > best_v:
                best, best_v = a, v
        return best


# --- 情報集合 MCTS ---


def determinize(state: State, viewer: int, rng: random.Random) -> State:
    """viewer に見えない札（山札の中身と順・相手の伏せ予約）を、見える情報と矛盾しないよう仮に決める。"""
    s = state.clone()
    for level in (1, 2, 3):
        pool = s.decks[level][:]
        hidden = []  # (人, 予約札の番号)
        for j, p in enumerate(s.players):
            if j == viewer:
                continue
            for k, (cid, blind) in enumerate(p.reserved):
                if blind and CARDS[cid].level == level:
                    pool.append(cid)
                    hidden.append((j, k))
        rng.shuffle(pool)
        for j, k in hidden:
            s.players[j].reserved[k] = (pool.pop(), True)
        s.decks[level] = pool
    return s


class _Node:
    __slots__ = ("avail", "children", "n", "player", "w")

    def __init__(self, player: int) -> None:
        self.children: dict[Action, _Node] = {}
        self.n = 0
        self.w = 0.0  # この節点に入る手を指した人から見た価値の合計
        self.avail = 0
        self.player = player  # この節点に入る手を指した人


class MCTSAgent:
    def __init__(self, iterations: int = 400, c: float = 0.7, depth: int = 6) -> None:
        self.iterations = iterations
        self.c = c
        self.depth = depth  # 根から何手まで木を伸ばすか（その先は評価で止める）
        self.name = f"mcts{iterations}"

    def act(self, state: State, rng: random.Random) -> Action:
        root_acts = reduce_actions(state, legal_actions(state))
        if len(root_acts) == 1:
            return root_acts[0]
        me = state.current
        root = _Node(1 - me)
        for _ in range(self.iterations):
            s = determinize(state, me, rng)
            node, path, d = root, [root], 0
            while not s.done and d < self.depth:
                acts = reduce_actions(s, legal_actions(s))
                for a in acts:
                    if a in node.children:
                        node.children[a].avail += 1
                untried = [a for a in acts if a not in node.children]
                mover = s.current
                if untried:
                    a = rng.choice(untried)
                    child = _Node(mover)
                    child.avail = 1
                    node.children[a] = child
                    apply(s, a)
                    path.append(child)
                    break
                a = max(acts, key=lambda x: self._ucb(node.children[x]))
                node = node.children[a]
                apply(s, a)
                path.append(node)
                d += 1
            v_me = evaluate(s, me)
            for nd in path:
                nd.n += 1
                nd.w += v_me if nd.player == me else 1 - v_me
        return max(root_acts, key=lambda a: root.children[a].n if a in root.children else -1)

    def _ucb(self, nd: _Node) -> float:
        return nd.w / nd.n + self.c * math.sqrt(math.log(max(nd.avail, 1)) / nd.n)


def make_agent(name: str):
    """名前から AI を作る: random / greedy / mcts<回数>（例 mcts400）。"""
    if name == "random":
        return RandomAgent()
    if name == "greedy":
        return GreedyAgent()
    if name.startswith("mcts"):
        return MCTSAgent(int(name[4:] or 400))
    raise ValueError(f"知らない AI の名前: {name}")
