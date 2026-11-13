"""速いエンジン（numba）。中身は正解版（game.py）と同じで、毎手を照合するテストで確かめる。

局面は int32 の1次元配列、手は int32 の11個組で持つ。並びは下の定数のとおり。
合法手の並び順も正解版と同じにしてある（同じ番号の手が同じ手になる）。

    s = fast.from_state(game.new_game(0))
    buf = fast.new_buffer()
    n = fast.legal(s, buf)          # buf[:n] が合法手
    fast.apply(s, buf[0])            # s を書き換える
    fast.to_action(buf[0])           # 正解版の Action に戻す
"""

from __future__ import annotations

import numpy as np
from numba import njit

from . import rules
from .cards import CARDS, NOBLES
from .game import BUY, MAX_TURNS, PASS, RESERVE, TAKE2, TAKE3, Action, State

# --- 局面の並び ---
BANK = 0  # 6
BOARD = 6  # 3レベル×4
DECK = (18, 58, 88)  # レベルごとの山札（末尾が一番上）。入れ物は40・30・20
DECK_CAP = (40, 30, 20)
DECKN = 108  # 3
NOB = 111  # 場の貴族 3（空きは -1、前に詰める）
NOBN = 114
PL = (115, 139)  # 人ごとの先頭
P_TOK, P_BON, P_PTS, P_RES, P_HID, P_RESN, P_BOUGHT, P_NOB, P_NOBN = (
    0,
    6,
    11,
    12,
    15,
    18,
    19,
    20,
    23,
)
P_SIZE = 24
TURN, PASSES, DONE = 163, 164, 165
SIZE = 166

# --- 手の並び: [種類, a0, a1, a2, 戻す6色, 貴族] ---
K_TAKE3, K_TAKE2, K_RESERVE, K_BUY, K_PASS = 0, 1, 2, 3, 4
A_RET, A_NOBLE, A_SIZE = 4, 10, 11
MAX_ACTIONS = 2048  # 多くても千に届かない（取る10通り×戻す56通りが最大の山）

_KIND = (TAKE3, TAKE2, RESERVE, BUY, PASS)
_KIND_ID = {k: i for i, k in enumerate(_KIND)}

CARD_COST = np.array([c.cost for c in CARDS], dtype=np.int32)
CARD_COLOR = np.array([c.color for c in CARDS], dtype=np.int32)
CARD_POINTS = np.array([c.points for c in CARDS], dtype=np.int32)
NOBLE_NEED = np.array([n.need for n in NOBLES], dtype=np.int32)
NOBLE_POINTS = np.array([n.points for n in NOBLES], dtype=np.int32)

_MAX_TOKENS = rules.MAX_TOKENS
_MAX_RESERVED = rules.MAX_RESERVED
_TAKE2_MIN = rules.TAKE_TWO_MIN_PILE
_WIN = rules.WIN_POINTS


# --- 正解版との行き来 ---


def from_state(state: State) -> np.ndarray:
    s = np.full(SIZE, 0, dtype=np.int32)
    s[BANK : BANK + 6] = state.bank
    for lv in (1, 2, 3):
        s[BOARD + 4 * (lv - 1) : BOARD + 4 * lv] = state.board[lv]
        deck = state.decks[lv]
        s[DECK[lv - 1] : DECK[lv - 1] + DECK_CAP[lv - 1]] = -1
        s[DECK[lv - 1] : DECK[lv - 1] + len(deck)] = deck
        s[DECKN + lv - 1] = len(deck)
    s[NOB : NOB + 3] = -1
    s[NOB : NOB + len(state.nobles)] = state.nobles
    s[NOBN] = len(state.nobles)
    for i, p in enumerate(state.players):
        b = PL[i]
        s[b + P_TOK : b + P_TOK + 6] = p.tokens
        s[b + P_BON : b + P_BON + 5] = p.bonus
        s[b + P_PTS] = p.points
        s[b + P_RES : b + P_RES + 3] = -1
        s[b + P_HID : b + P_HID + 3] = 0
        for k, (cid, hid) in enumerate(p.reserved):
            s[b + P_RES + k] = cid
            s[b + P_HID + k] = int(hid)
        s[b + P_RESN] = len(p.reserved)
        s[b + P_BOUGHT] = p.bought
        s[b + P_NOB : b + P_NOB + 3] = -1
        s[b + P_NOB : b + P_NOB + len(p.nobles)] = p.nobles
        s[b + P_NOBN] = len(p.nobles)
    s[TURN] = state.turn
    s[PASSES] = state.passes
    s[DONE] = int(state.done)
    return s


def to_action(row: np.ndarray) -> Action:
    k = int(row[0])
    if k == K_TAKE3:
        arg: object = tuple(int(c) for c in row[1:4] if c >= 0)
    elif k == K_TAKE2:
        arg = int(row[1])
    elif k == K_RESERVE:
        arg = (int(row[1]), int(row[2]))
    elif k == K_BUY:
        arg = ("board", int(row[1]), int(row[2])) if row[3] == 0 else ("reserved", int(row[1]))
    else:
        return Action(PASS)
    ret = tuple(int(x) for x in row[A_RET : A_RET + 6])
    return Action(_KIND[k], arg, ret, int(row[A_NOBLE]))


def new_buffer() -> np.ndarray:
    return np.zeros((MAX_ACTIONS, A_SIZE), dtype=np.int32)


# --- numba の中身 ---


@njit(cache=True)
def _shortfall_pay(s, b, cid, pay):
    """払うチップを pay（6色）に入れる。払えれば True。"""
    short = 0
    for c in range(5):
        need = CARD_COST[cid, c] - s[b + P_BON + c]
        need = max(need, 0)
        have = s[b + P_TOK + c]
        x = min(have, need)
        pay[c] = x
        short += need - x
    pay[5] = short
    return short <= s[b + P_TOK + 5]


@njit(cache=True)
def _emit(s, out, n, kind, a0, a1, a2, tok, bon):
    """主な手1つについて、戻し方×貴族の組を正解版と同じ順で out に足す。"""
    total = 0
    for c in range(6):
        total += tok[c]
    excess = total - _MAX_TOKENS
    # 来られる貴族（場の並び順）
    nobles = np.empty(3, dtype=np.int32)
    nn = 0
    for k in range(s[NOBN]):
        nid = s[NOB + k]
        ok = True
        for c in range(5):
            if bon[c] < NOBLE_NEED[nid, c]:
                ok = False
                break
        if ok:
            nobles[nn] = nid
            nn += 1
    if nn == 0:
        nobles[0] = -1
        nn = 1
    if excess <= 0:
        for j in range(nn):
            r = out[n]
            r[0], r[1], r[2], r[3] = kind, a0, a1, a2
            for c in range(6):
                r[A_RET + c] = 0
            r[A_NOBLE] = nobles[j]
            n += 1
        return n
    m = np.empty(6, dtype=np.int32)
    for c in range(6):
        m[c] = min(excess, tok[c])
    # itertools.product の順（最後の色がいちばん速く回る）
    for r0 in range(m[0] + 1):
        for r1 in range(m[1] + 1):
            s1 = r0 + r1
            if s1 > excess:
                break
            for r2 in range(m[2] + 1):
                s2 = s1 + r2
                if s2 > excess:
                    break
                for r3 in range(m[3] + 1):
                    s3 = s2 + r3
                    if s3 > excess:
                        break
                    for r4 in range(m[4] + 1):
                        s4 = s3 + r4
                        if s4 > excess:
                            break
                        r5 = excess - s4
                        if r5 > m[5]:
                            continue
                        for j in range(nn):
                            r = out[n]
                            r[0], r[1], r[2], r[3] = kind, a0, a1, a2
                            r[A_RET], r[A_RET + 1], r[A_RET + 2] = r0, r1, r2
                            r[A_RET + 3], r[A_RET + 4], r[A_RET + 5] = r3, r4, r5
                            r[A_NOBLE] = nobles[j]
                            n += 1
    return n


@njit(cache=True)
def legal(s, out):
    """合法手を out に入れて数を返す。終わった局面は0。"""
    if s[DONE]:
        return 0
    b = PL[s[TURN] % 2]
    tok = np.empty(6, dtype=np.int32)
    bon = np.empty(5, dtype=np.int32)
    base_tok = s[b + P_TOK : b + P_TOK + 6]
    base_bon = s[b + P_BON : b + P_BON + 5]
    pay = np.empty(6, dtype=np.int32)
    n = 0
    # 違う色を取る
    avail = np.empty(5, dtype=np.int32)
    na = 0
    for c in range(5):
        if s[BANK + c] > 0:
            avail[na] = c
            na += 1
    bon[:] = base_bon
    if na >= 3:
        for i in range(na):
            for j in range(i + 1, na):
                for k in range(j + 1, na):
                    tok[:] = base_tok
                    tok[avail[i]] += 1
                    tok[avail[j]] += 1
                    tok[avail[k]] += 1
                    n = _emit(s, out, n, K_TAKE3, avail[i], avail[j], avail[k], tok, bon)
    else:
        for i in range(na):  # 1枚
            tok[:] = base_tok
            tok[avail[i]] += 1
            n = _emit(s, out, n, K_TAKE3, avail[i], -1, -1, tok, bon)
        if na == 2:  # 2枚
            tok[:] = base_tok
            tok[avail[0]] += 1
            tok[avail[1]] += 1
            n = _emit(s, out, n, K_TAKE3, avail[0], avail[1], -1, tok, bon)
    # 同じ色を2枚
    for c in range(5):
        if s[BANK + c] >= _TAKE2_MIN:
            tok[:] = base_tok
            tok[c] += 2
            n = _emit(s, out, n, K_TAKE2, c, -1, -1, tok, bon)
    # 予約
    if s[b + P_RESN] < _MAX_RESERVED:
        tok[:] = base_tok
        if s[BANK + 5] > 0:
            tok[5] += 1
        for lv in range(3):
            for i in range(4):
                if s[BOARD + 4 * lv + i] >= 0:
                    n = _emit(s, out, n, K_RESERVE, lv + 1, i, -1, tok, bon)
            if s[DECKN + lv] > 0:
                n = _emit(s, out, n, K_RESERVE, lv + 1, -1, -1, tok, bon)
    # 場から買う
    for lv in range(3):
        for i in range(4):
            cid = s[BOARD + 4 * lv + i]
            if cid >= 0 and _shortfall_pay(s, b, cid, pay):
                for c in range(6):
                    tok[c] = base_tok[c] - pay[c]
                bon[:] = base_bon
                bon[CARD_COLOR[cid]] += 1
                n = _emit(s, out, n, K_BUY, lv + 1, i, 0, tok, bon)
    # 予約札を買う
    for k in range(s[b + P_RESN]):
        cid = s[b + P_RES + k]
        if _shortfall_pay(s, b, cid, pay):
            for c in range(6):
                tok[c] = base_tok[c] - pay[c]
            bon[:] = base_bon
            bon[CARD_COLOR[cid]] += 1
            n = _emit(s, out, n, K_BUY, k, -1, 1, tok, bon)
    if n == 0:
        r = out[0]
        r[:] = 0
        r[0] = K_PASS
        r[1] = r[2] = r[3] = -1
        r[A_NOBLE] = -1
        n = 1
    return n


@njit(cache=True)
def _refill(s, lv, slot):
    dn = s[DECKN + lv]
    if dn > 0:
        s[BOARD + 4 * lv + slot] = s[DECK[lv] + dn - 1]
        s[DECK[lv] + dn - 1] = -1
        s[DECKN + lv] = dn - 1
    else:
        s[BOARD + 4 * lv + slot] = -1


@njit(cache=True)
def apply(s, a):
    """手を指す（s を書き換える）。合法かは確かめない（legal から選ぶ）。"""
    cur = s[TURN] % 2
    b = PL[cur]
    kind = a[0]
    if kind == K_TAKE3:
        for j in range(1, 4):
            c = a[j]
            if c >= 0:
                s[BANK + c] -= 1
                s[b + P_TOK + c] += 1
    elif kind == K_TAKE2:
        s[BANK + a[1]] -= 2
        s[b + P_TOK + a[1]] += 2
    elif kind == K_RESERVE:
        lv = a[1] - 1
        slot = a[2]
        k = s[b + P_RESN]
        if slot < 0:
            dn = s[DECKN + lv]
            s[b + P_RES + k] = s[DECK[lv] + dn - 1]
            s[DECK[lv] + dn - 1] = -1
            s[DECKN + lv] = dn - 1
            s[b + P_HID + k] = 1
        else:
            s[b + P_RES + k] = s[BOARD + 4 * lv + slot]
            s[b + P_HID + k] = 0
            _refill(s, lv, slot)
        s[b + P_RESN] = k + 1
        if s[BANK + 5] > 0:
            s[BANK + 5] -= 1
            s[b + P_TOK + 5] += 1
    elif kind == K_BUY:
        pay = np.empty(6, dtype=np.int32)
        if a[3] == 0:
            cid = s[BOARD + 4 * (a[1] - 1) + a[2]]
        else:
            cid = s[b + P_RES + a[1]]
        _shortfall_pay(s, b, cid, pay)
        for c in range(6):
            s[b + P_TOK + c] -= pay[c]
            s[BANK + c] += pay[c]
        if a[3] == 0:
            _refill(s, a[1] - 1, a[2])
        else:
            rn = s[b + P_RESN]
            for k in range(a[1], rn - 1):
                s[b + P_RES + k] = s[b + P_RES + k + 1]
                s[b + P_HID + k] = s[b + P_HID + k + 1]
            s[b + P_RES + rn - 1] = -1
            s[b + P_HID + rn - 1] = 0
            s[b + P_RESN] = rn - 1
        s[b + P_BON + CARD_COLOR[cid]] += 1
        s[b + P_PTS] += CARD_POINTS[cid]
        s[b + P_BOUGHT] += 1
    for c in range(6):
        s[b + P_TOK + c] -= a[A_RET + c]
        s[BANK + c] += a[A_RET + c]
    nid = a[A_NOBLE]
    if nid >= 0:
        nn = s[NOBN]
        k = 0
        while s[NOB + k] != nid:
            k += 1
        for j in range(k, nn - 1):
            s[NOB + j] = s[NOB + j + 1]
        s[NOB + nn - 1] = -1
        s[NOBN] = nn - 1
        pn = s[b + P_NOBN]
        s[b + P_NOB + pn] = nid
        s[b + P_NOBN] = pn + 1
        s[b + P_PTS] += NOBLE_POINTS[nid]
    if kind == K_PASS:
        s[PASSES] += 1
    else:
        s[PASSES] = 0
    last_in_round = cur == 1
    s[TURN] += 1
    if (
        s[PASSES] >= 2
        or s[TURN] >= MAX_TURNS
        or last_in_round
        and (s[PL[0] + P_PTS] >= _WIN or s[PL[1] + P_PTS] >= _WIN)
    ):
        s[DONE] = 1


@njit(cache=True)
def result(s):
    """勝った人の番号。引き分けは -1（正解版の result と同じ決め方）。"""
    p0, p1 = s[PL[0] + P_PTS], s[PL[1] + P_PTS]
    if p0 != p1:
        return 0 if p0 > p1 else 1
    b0, b1 = s[PL[0] + P_BOUGHT], s[PL[1] + P_BOUGHT]
    if b0 != b1:
        return 0 if b0 < b1 else 1
    return -1


@njit(cache=True)
def random_playout(s, buf, seed):
    """終わるまで一様ランダムに指す（s を書き換える）。勝った人を返す。速さの物差し用。"""
    np.random.seed(seed)
    while not s[DONE]:
        n = legal(s, buf)
        apply(s, buf[np.random.randint(n)])
    return result(s)
