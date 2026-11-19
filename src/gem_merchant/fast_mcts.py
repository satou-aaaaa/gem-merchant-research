"""情報集合 MCTS の速い版（numba）。考え方は agents.MCTSAgent と同じ。

- 見えない札（山札の中身と順・相手の伏せ予約）を、反復ごとに見える情報と矛盾しないよう仮に決める。
- 手は agents.reduce_actions と同じく、10枚を超えたときの戻し方を1通りに減らす。
- 根から depth 手まで木を伸ばし、葉は手作りの評価（agents.evaluate と同じ式）で値を出す。
- 子の選び方は UCB（親の回数の代わりに「その手が指せた回数」を使う、SO-ISMCTS の形）。

木の操作も評価も numba の中で回すので、正解版の MCTSAgent より何十倍も速い。
乱数の列は Python の random と違うので、同じシードでも同じ手になるとは限らない（強さで比べる）。

    agent = FastMCTSAgent(2000)
    a = agent.act(state, rng)   # 正解版の Action を返す
"""

from __future__ import annotations

import math
import random

import numpy as np
from numba import njit

from .cards import CARDS
from .fast import (
    A_NOBLE,
    A_RET,
    A_SIZE,
    BOARD,
    CARD_COST,
    CARD_POINTS,
    DECK,
    DECKN,
    DONE,
    MAX_ACTIONS,
    NOB,
    NOBLE_NEED,
    NOBN,
    P_BON,
    P_HID,
    P_PTS,
    P_RES,
    P_RESN,
    P_TOK,
    PL,
    TURN,
    apply,
    from_state,
    legal,
    result,
    to_action,
)
from .game import Action, State

CARD_LEVEL = np.array([c.level for c in CARDS], dtype=np.int32)


# --- 手作りの評価（agents.player_value・evaluate と同じ式） ---


@njit(cache=True)
def _shortfall(s, b, cid):
    short = 0
    for c in range(5):
        x = CARD_COST[cid, c] - s[b + P_BON + c] - s[b + P_TOK + c]
        if x > 0:
            short += x
    short -= s[b + P_TOK + 5]
    return max(0, short)


@njit(cache=True)
def player_value(s, i):
    b = PL[i]
    v = float(s[b + P_PTS])
    bon = 0
    for c in range(5):
        bon += s[b + P_BON + c]
    v += 0.8 * bon
    tok = 0
    for c in range(5):
        tok += s[b + P_TOK + c]
    v += 0.1 * tok + 0.2 * s[b + P_TOK + 5]
    for k in range(s[NOBN]):
        nid = s[NOB + k]
        need = 0
        for c in range(5):
            x = NOBLE_NEED[nid, c] - s[b + P_BON + c]
            if x > 0:
                need += x
        v += 3.0 / (1 + need) ** 1.5
    # 買えそうな札の上位3つ
    t1 = t2 = t3 = 0.0
    for j in range(12 + s[b + P_RESN]):
        cid = s[BOARD + j] if j < 12 else s[b + P_RES + j - 12]
        if cid < 0:
            continue
        x = (CARD_POINTS[cid] + 0.8) / (1 + _shortfall(s, b, cid))
        if x > t1:
            t1, t2, t3 = x, t1, t2
        elif x > t2:
            t2, t3 = x, t2
        elif x > t3:
            t3 = x
    v += 0.5 * (t1 + t2 + t3)
    return v


# --- 重みつきの評価（R-004 自己対戦で学ぶ） ---
# 1人分の特徴（手作りの評価の項を分けたもの＋2つ）。手作りの評価は HAND_WEIGHTS をかけた和と同じ。
FEATURES = (
    "点",
    "割引の数",
    "宝石チップの数",
    "金チップの数",
    "貴族の近さ",
    "買えそうな札の上位3つ",
    "割引の色の数",
    "予約の数",
)
N_FEAT = len(FEATURES)
PHASE_TURNS = 60  # 手番の数。0 で序盤の重み、これ以降は終盤の重み、間は直線でまぜる
HAND_WEIGHTS = np.array([[1.0, 0.8, 0.1, 0.2, 3.0, 0.5, 0.0, 0.0]] * 2, dtype=np.float64)


@njit(cache=True)
def features(s, i, out):
    """i 番の人の特徴を out（長さ N_FEAT）に書く。"""
    b = PL[i]
    for k in range(N_FEAT):
        out[k] = 0.0
    out[0] = s[b + P_PTS]
    for c in range(5):
        out[1] += s[b + P_BON + c]
        out[2] += s[b + P_TOK + c]
        if s[b + P_BON + c] > 0:
            out[6] += 1.0
    out[3] = s[b + P_TOK + 5]
    for k in range(s[NOBN]):
        nid = s[NOB + k]
        need = 0
        for c in range(5):
            x = NOBLE_NEED[nid, c] - s[b + P_BON + c]
            if x > 0:
                need += x
        out[4] += 1.0 / (1 + need) ** 1.5
    t1 = t2 = t3 = 0.0
    for j in range(12 + s[b + P_RESN]):
        cid = s[BOARD + j] if j < 12 else s[b + P_RES + j - 12]
        if cid < 0:
            continue
        x = (CARD_POINTS[cid] + 0.8) / (1 + _shortfall(s, b, cid))
        if x > t1:
            t1, t2, t3 = x, t1, t2
        elif x > t2:
            t2, t3 = x, t2
        elif x > t3:
            t3 = x
    out[5] = t1 + t2 + t3
    out[7] = s[b + P_RESN]


@njit(cache=True)
def phase(s):
    """序盤 0 → 終盤 1。"""
    return min(1.0, s[TURN] / PHASE_TURNS)


@njit(cache=True)
def diff_features(s, i, out):
    """学習の入力（長さ 2*N_FEAT）: i 番から見た特徴の差を、序盤・終盤の重みに分けたもの。"""
    f0 = np.empty(N_FEAT)
    f1 = np.empty(N_FEAT)
    features(s, i, f0)
    features(s, 1 - i, f1)
    a = phase(s)
    for k in range(N_FEAT):
        d = f0[k] - f1[k]
        out[k] = (1.0 - a) * d
        out[N_FEAT + k] = a * d


@njit(cache=True)
def evaluate_w(s, i, w):
    """evaluate の重みつき版。w は (2, N_FEAT)。HAND_WEIGHTS なら evaluate と同じ値。"""
    if s[DONE]:
        r = result(s)
        if r < 0:
            return 0.5
        return 1.0 if r == i else 0.0
    x = np.empty(2 * N_FEAT)
    diff_features(s, i, x)
    d = 0.0
    for k in range(N_FEAT):
        d += w[0, k] * x[k] + w[1, k] * x[N_FEAT + k]
    return 1.0 / (1.0 + math.exp(-d / 4))


@njit(cache=True)
def evaluate(s, i):
    """i 番の人から見た勝ちやすさ（0〜1）。終わっていれば勝ち1・引き分け0.5・負け0。"""
    if s[DONE]:
        r = result(s)
        if r < 0:
            return 0.5
        return 1.0 if r == i else 0.0
    d = player_value(s, i) - player_value(s, 1 - i)
    return 1.0 / (1.0 + math.exp(-d / 4))


# --- 見えない札を仮に決める ---


@njit(cache=True)
def determinize(s, viewer):
    """s を書き換える。viewer に見えない札を、山札と相手の伏せ予約の中で混ぜ直す。"""
    opp = PL[1 - viewer]
    pool = np.empty(43, dtype=np.int32)
    slots = np.empty(3, dtype=np.int32)
    for lv in range(3):
        dn = s[DECKN + lv]
        n = 0
        for k in range(dn):
            pool[n] = s[DECK[lv] + k]
            n += 1
        nh = 0
        for k in range(s[opp + P_RESN]):
            cid = s[opp + P_RES + k]
            if s[opp + P_HID + k] and CARD_LEVEL[cid] == lv + 1:
                pool[n] = cid
                n += 1
                slots[nh] = k
                nh += 1
        if nh == 0 and dn <= 1:
            continue
        np.random.shuffle(pool[:n])
        for h in range(nh):
            n -= 1
            s[opp + P_RES + slots[h]] = pool[n]
        for k in range(n):
            s[DECK[lv] + k] = pool[k]


# --- 手を減らす（agents.reduce_actions と同じ。作業用の入れ物を使い回す） ---


@njit(cache=True)
def _same_main(a, b):
    for j in range(4):
        if a[j] != b[j]:
            return False
    return a[A_NOBLE] == b[A_NOBLE]


@njit(cache=True)
def _ret_better(a, b):
    if a[A_RET + 5] != b[A_RET + 5]:
        return a[A_RET + 5] < b[A_RET + 5]
    for c in range(5):
        if a[A_RET + c] != b[A_RET + c]:
            return a[A_RET + c] > b[A_RET + c]
    return False


@njit(cache=True)
def reduced(s, buf, out):
    n = legal(s, buf)
    m = 0
    for i in range(n):
        found = -1
        for j in range(m):
            if _same_main(buf[i], out[j]):
                found = j
                break
        if found < 0:
            out[m] = buf[i]
            m += 1
        elif _ret_better(buf[i], out[found]):
            out[found] = buf[i]
    return m


# --- 木 ---


@njit(cache=True)
def _same(a, b):
    for j in range(A_SIZE):
        if a[j] != b[j]:
            return False
    return True


@njit(cache=True)
def search(root_state, iterations, c, depth, seed, ew):
    """根の手番の人の手を選び、その手（11個の整数）と、根の手ごとの回数を返す。ew は評価の重み（(2, N_FEAT)）。"""
    np.random.seed(seed)
    me = root_state[TURN] % 2
    cap = iterations + 2
    n_vis = np.zeros(cap, dtype=np.int64)
    w = np.zeros(cap, dtype=np.float64)
    avail = np.zeros(cap, dtype=np.int64)
    player = np.zeros(cap, dtype=np.int32)
    first = np.full(cap, -1, dtype=np.int32)
    nxt = np.full(cap, -1, dtype=np.int32)
    act = np.zeros((cap, A_SIZE), dtype=np.int32)
    player[0] = 1 - me
    used = 1

    buf = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    acts = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    kid = np.empty(MAX_ACTIONS, dtype=np.int32)
    untried = np.empty(MAX_ACTIONS, dtype=np.int32)
    path = np.empty(depth + 2, dtype=np.int32)

    root_acts = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    nr = reduced(root_state, buf, root_acts)
    counts = np.zeros(nr, dtype=np.int64)
    if nr == 1:
        return root_acts[0].copy(), counts

    for _ in range(iterations):
        s = root_state.copy()
        determinize(s, me)
        node = 0
        path[0] = 0
        plen = 1
        d = 0
        while not s[DONE] and d < depth:
            m = reduced(s, buf, acts)
            nu = 0
            for i in range(m):
                ch = first[node]
                while ch >= 0 and not _same(act[ch], acts[i]):
                    ch = nxt[ch]
                kid[i] = ch
                if ch >= 0:
                    avail[ch] += 1
                else:
                    untried[nu] = i
                    nu += 1
            mover = s[TURN] % 2
            if nu > 0:
                i = untried[np.random.randint(nu)]
                ch = used
                used += 1
                player[ch] = mover
                avail[ch] = 1
                act[ch] = acts[i]
                nxt[ch] = first[node]
                first[node] = ch
                apply(s, acts[i])
                path[plen] = ch
                plen += 1
                break
            best = -1
            best_v = -1e300
            for i in range(m):
                ch = kid[i]
                a_ = max(1, avail[ch])
                v = w[ch] / n_vis[ch] + c * math.sqrt(math.log(a_) / n_vis[ch])
                if v > best_v:
                    best_v = v
                    best = i
            node = kid[best]
            apply(s, acts[best])
            path[plen] = node
            plen += 1
            d += 1
        v_me = evaluate_w(s, me, ew)
        for k in range(plen):
            nd = path[k]
            n_vis[nd] += 1
            w[nd] += v_me if player[nd] == me else 1.0 - v_me
    # 根の手のうち、いちばん多く通った手（同じなら先の手）
    best = 0
    best_n = -1
    for i in range(nr):
        ch = first[0]
        while ch >= 0 and not _same(act[ch], root_acts[i]):
            ch = nxt[ch]
        counts[i] = n_vis[ch] if ch >= 0 else 0
        x = n_vis[ch] if ch >= 0 else -1
        if x > best_n:
            best_n = x
            best = i
    return root_acts[best].copy(), counts


class FastMCTSAgent:
    """agents.MCTSAgent と同じ考え方の速い版。名前は fmcts<回数>（例 fmcts2000）。"""

    def __init__(
        self,
        iterations: int = 400,
        c: float = 0.7,
        depth: int = 6,
        weights: np.ndarray | None = None,
        name: str | None = None,
    ) -> None:
        self.iterations = iterations
        self.c = c
        self.depth = depth
        self.weights = np.ascontiguousarray(
            HAND_WEIGHTS if weights is None else weights, dtype=np.float64
        ).reshape(2, N_FEAT)
        self.name = name or f"fmcts{iterations}"

    def act(self, state: State, rng: random.Random) -> Action:
        a, _ = search(
            from_state(state),
            self.iterations,
            self.c,
            self.depth,
            rng.getrandbits(31),
            self.weights,
        )
        return to_action(a)
