"""終盤の読み切りの速い版（numba）。考え方と前提は endgame.py と同じで、同じ局面で同じ区間を返す。

速いエンジン（fast.py）の局面の配列の上で、期待値つきミニマックスを区間 [下限, 上限] で読む。
- 手は agents.reduce_actions と同じく、10枚を超えたときの戻し方を1通りに減らす（金を残し、多い色から戻す）。
- 山札から出る札は、残りの札から等しい確率で出るとして平均する。
- 相手の伏せ予約は本当の札が分かっているものとして読む（神の目の上限）。

正解版（endgame.py）より約20倍速く、手番の数では届かない局面を読まずに切るので、二巡先まで読める。

    s = fast.from_state(state)
    r = judge(s, action, depth)   # endgame.judge と同じ形の dict か None
"""

from __future__ import annotations

import numpy as np
from numba import njit

from .fast import (
    A_NOBLE,
    A_RET,
    A_SIZE,
    DECK,
    DECKN,
    DONE,
    K_BUY,
    K_RESERVE,
    MAX_ACTIONS,
    NOB,
    NOBLE_NEED,
    NOBN,
    P_BON,
    P_PTS,
    PASSES,
    PL,
    TURN,
    apply,
    legal,
    result,
    to_action,
)
from .game import MAX_TURNS, Action
from .rules import WIN_POINTS as _WIN

_N_STATS = 2  # 読んだ節点の数・枝刈りで切った数


@njit(cache=True)
def _terminal(s):
    r = result(s)
    if r < 0:
        return 0.5
    return 1.0 if r == 0 else 0.0


@njit(cache=True)
def _same_main(a, b):
    """戻し方を除いて同じ手か（種類・引数・貴族）。"""
    for j in range(4):
        if a[j] != b[j]:
            return False
    return a[A_NOBLE] == b[A_NOBLE]


@njit(cache=True)
def _ret_better(a, b):
    """戻し方 a が b より良いか（agents._ret_cost が小さい）。金を残し、多く戻せる色から。"""
    if a[A_RET + 5] != b[A_RET + 5]:
        return a[A_RET + 5] < b[A_RET + 5]
    for c in range(5):
        if a[A_RET + c] != b[A_RET + c]:
            return a[A_RET + c] > b[A_RET + c]
    return False


@njit(cache=True)
def reduced(s, out):
    """agents.reduce_actions(legal_actions) と同じ手を、同じ順で out に入れて数を返す。"""
    buf = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
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


@njit(cache=True)
def _draw_level(s, a):
    """この手で山札から札が出るならそのレベル（0〜2）、出ないなら -1。"""
    if a[0] == K_RESERVE or (a[0] == K_BUY and a[3] == 0):
        lv = a[1] - 1
        if s[DECKN + lv] > 0:
            return lv
    return -1


@njit(cache=True)
def _cannot_end(s, depth):
    """depth 手番のうちに対局が終わりえないことが確かか（確かなときだけ True）。

    終わり方は 15点・打ち切りの手番・2人続けてパスの3つ。1手番で増える点は札の5点＋貴族3点まで。
    パスは合法手が無いときだけで、場のチップが残るうちは取る手があるので、チップの数で見積もる。
    """
    if s[TURN] + depth >= MAX_TURNS:
        return False
    bank = 0
    for c in range(5):
        bank += s[c]
    if bank <= 3 * depth:
        return False
    # 各人の残りの手番の数（手番の人は切り上げ、もう1人は切り捨て）
    cur = s[TURN] % 2
    for i in range(2):
        turns = (depth + 1) // 2 if i == cur else depth // 2
        b = PL[i]
        # 1手番で買える札は1枚（5点まで）、増えるボーナスも1つ。貴族はボーナスの不足が turns 以下なら来うる
        nobles = 0
        for k in range(s[NOBN]):
            nid = s[NOB + k]
            short = 0
            for c in range(5):
                short += max(0, NOBLE_NEED[nid, c] - s[b + P_BON + c])
            if short <= turns:
                nobles += 1
        gain = 5 * turns + 3 * min(nobles, turns)
        if s[b + P_PTS] + gain >= _WIN:
            return False
    return True


@njit  # 再帰する関数はキャッシュから読むと落ちる（numba 0.68）ので cache しない
def _solve(s, depth, stats):
    """先手から見た勝つ見込みの区間 (下限, 上限)。endgame.solve と同じ値。"""
    stats[0] += 1
    if s[DONE]:
        v = _terminal(s)
        return v, v
    if depth == 0:
        return 0.0, 1.0
    if s[PASSES] == 0 and _cannot_end(s, depth):
        stats[1] += 1
        return 0.0, 1.0
    acts = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    m = reduced(s, acts)
    # 買う手から読む（順は保ったまま）
    order = np.empty(m, dtype=np.int64)
    k = 0
    for i in range(m):
        if acts[i, 0] == K_BUY:
            order[k] = i
            k += 1
    for i in range(m):
        if acts[i, 0] != K_BUY:
            order[k] = i
            k += 1
    maxer = s[TURN] % 2 == 0
    sure = 1.0 if maxer else 0.0
    best_lo = -1.0 if maxer else 2.0
    best_hi = -1.0 if maxer else 2.0
    for t in range(m):
        a = acts[order[t]]
        lo, hi = _action_value(s, a, depth, stats)
        if maxer:
            best_lo = max(best_lo, lo)
            best_hi = max(best_hi, hi)
        else:
            best_lo = min(best_lo, lo)
            best_hi = min(best_hi, hi)
        if lo == sure and hi == sure:
            break
    return best_lo, best_hi


@njit  # 再帰する関数はキャッシュから読むと落ちる（numba 0.68）ので cache しない
def _action_value(s, a, depth, stats):
    """手 a を指したあとの区間。山札から出る札ごとに読んで平均する。"""
    lv = _draw_level(s, a)
    if depth == 1 or lv < 0:
        c = s.copy()
        apply(c, a)
        return _solve(c, depth - 1, stats)
    base = DECK[lv]
    dn = s[DECKN + lv]
    top = base + dn - 1
    lo_sum = 0.0
    hi_sum = 0.0
    for j in range(dn):
        c = s.copy()
        # j 番目の札を一番上（次に出る）にする
        x = c[base + j]
        c[base + j] = c[top]
        c[top] = x
        apply(c, a)
        lo, hi = _solve(c, depth - 1, stats)
        lo_sum += lo
        hi_sum += hi
    return lo_sum / dn, hi_sum / dn


@njit  # 再帰する関数はキャッシュから読むと落ちる（numba 0.68）ので cache しない
def action_values(s, depth):
    """根の各手（reduced の順）の区間と、読んだ節点の数。"""
    acts = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    m = reduced(s, acts)
    vals = np.empty((m, 2), dtype=np.float64)
    stats = np.zeros(_N_STATS, dtype=np.int64)
    for i in range(m):
        lo, hi = _action_value(s, acts[i], depth, stats)
        vals[i, 0] = lo
        vals[i, 1] = hi
    return acts[:m].copy(), vals, stats


# ---- 枝刈りつきの読み（R-007） ----
# 区間 [下限, 上限] は「読み切れない葉を 0 とした期待値つきミニマックスの値」と「1 とした値」の組なので、
# 2つを別々に、窓（alpha, beta）つきで読める。判定に要るのは窓の外か内かだけなので、要らない枝を読まずに切る。
# 手番の節点はふつうの αβ、山札の節点は Ballard の Star1（残りの札の値を 0〜1 と見て、平均が窓の外に出たら切る）。
# 返す値 v は fail-soft: v <= alpha なら本当の値 <= v、v >= beta なら本当の値 >= v、その間なら本当の値そのもの。
# 窓の中で返る値は、足す順まで全部読みと同じなので、浮動小数点でも全部読みと同じ値になる。

_EPS = 1e-9  # Star1 の窓を、丸めの誤差より十分大きく外側へ広げる幅


@njit  # 再帰する関数はキャッシュから読むと落ちる（numba 0.68）ので cache しない
def _ab(s, depth, unk, alpha, beta, stats):
    """先手から見た値（読み切れない葉を unk とする）を窓 (alpha, beta) で読む。"""
    stats[0] += 1
    if s[DONE]:
        return _terminal(s)
    if depth == 0:
        return unk
    if s[PASSES] == 0 and _cannot_end(s, depth):
        stats[1] += 1
        return unk
    acts = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    m = reduced(s, acts)
    order = np.empty(m, dtype=np.int64)
    k = 0
    for i in range(m):
        if acts[i, 0] == K_BUY:
            order[k] = i
            k += 1
    for i in range(m):
        if acts[i, 0] != K_BUY:
            order[k] = i
            k += 1
    if s[TURN] % 2 == 0:
        best = -1.0
        for t in range(m):
            v = _action_ab(s, acts[order[t]], depth, unk, max(alpha, best), beta, stats)
            best = max(best, v)
            if best >= beta:
                break
        return best
    best = 2.0
    for t in range(m):
        v = _action_ab(s, acts[order[t]], depth, unk, alpha, min(beta, best), stats)
        best = min(best, v)
        if best <= alpha:
            break
    return best


@njit  # 再帰する関数はキャッシュから読むと落ちる（numba 0.68）ので cache しない
def _action_ab(s, a, depth, unk, alpha, beta, stats):
    """手 a を指したあとの値を窓 (alpha, beta) で読む。山札から札が出るなら Star1 で平均する。"""
    lv = _draw_level(s, a)
    if depth == 1 or lv < 0:
        c = s.copy()
        apply(c, a)
        return _ab(c, depth - 1, unk, alpha, beta, stats)
    base = DECK[lv]
    dn = s[DECKN + lv]
    top = base + dn - 1
    total = 0.0
    for j in range(dn):
        rest = dn - 1 - j  # まだ読んでいない札の数（値は 0〜1）
        lo_j = dn * alpha - total - rest - dn * _EPS
        hi_j = dn * beta - total + dn * _EPS
        c = s.copy()
        x = c[base + j]
        c[base + j] = c[top]
        c[top] = x
        apply(c, a)
        # 値は 0〜1 なので、子の窓は [0, 1] に収める（端で返った値は本当の値。0 と 1 で切れる）
        v = _ab(c, depth - 1, unk, max(lo_j, 0.0), min(hi_j, 1.0), stats)
        if v <= lo_j:
            return (total + v + rest) / dn  # 残りが全部 1 でも alpha に届かない
        if v >= hi_j:
            return (total + v) / dn  # 残りが全部 0 でも beta を超える
        total += v
    return total / dn


def _value(
    s: np.ndarray,
    a: np.ndarray,
    depth: int,
    unk: float,
    alpha: float,
    beta: float,
    stats: np.ndarray,
) -> float:
    return float(_action_ab(s, a, depth, unk, alpha, beta, stats))


def _judge_pruned(s: np.ndarray, chosen: Action, depth: int) -> dict | None:
    """judge と同じ判定を、窓つきの読みで出す（下の judge の説明を見る）。

    値は先手から見たもので、v0 は読み切れない葉を 0、v1 は 1 としたもの（区間の下限と上限）。
    窓 (0, 1) なら端に出ても本当の値（値は 0〜1 なので）。判定に要らない値は狭い窓で読む。
    """
    acts = np.empty((MAX_ACTIONS, A_SIZE), dtype=np.int32)
    m = int(reduced(s, acts))
    key = (chosen.kind, chosen.arg, chosen.noble)
    keys = [(a.kind, a.arg, a.noble) for a in (to_action(acts[i]) for i in range(m))]
    if key not in keys:
        return None
    idx = keys.index(key)
    others = [i for i in range(m) if i != idx]
    stats = np.zeros(_N_STATS, dtype=np.int64)

    def value(i: int, unk: float, alpha: float, beta: float) -> float:
        return float(_action_ab(s, acts[i], depth, unk, alpha, beta, stats))

    def out(r: dict) -> dict:
        r["nodes"] = int(stats[0])
        return r

    if s[TURN] % 2 == 0:
        # 手番の人＝先手。悪手: 選んだ手の上限 c1 < ほかの手の下限の最大（選んだ手の下限は c1 以下なので要らない）
        c1 = value(idx, 1.0, 0.0, 1.0)
        best_lo = -1.0
        for i in others:
            a = max(c1, best_lo) - _EPS
            v = value(i, 0.0, a, 1.0)
            if v > a:  # 窓の中なので本当の値
                best_lo = max(best_lo, v)
        if c1 < best_lo:
            return out({"verdict": "mistake", "loss_min": best_lo - c1})
        # 最善: 選んだ手の下限 c0 >= どの手の上限（選んだ手自身の上限 c1 も含む）
        c0 = value(idx, 0.0, c1 - _EPS, 1.0)
        if not c0 >= c1:
            return None
        if c0 >= 1.0:  # 選んだ手で必ず勝つ。上限は 1 を超えないので、ほかの手を読むまでもない
            return out({"verdict": "best", "loss_min": 0.0})
        for i in others:
            v = value(i, 1.0, c0 - _EPS, c0 + _EPS)
            if v >= c0 + _EPS or (v > c0 - _EPS and not c0 >= v):
                return None
        return out({"verdict": "best", "loss_min": 0.0})
    # 手番の人＝後手。後手から見た区間は [1 - 上限, 1 - 下限] = [1 - v1, 1 - v0]
    c0 = value(idx, 0.0, 0.0, 1.0)
    c_hi = 1 - c0
    best_lo = -1.0
    low = c0  # 読んだほかの手の上限（先手から見て）の最小。これ以上の手は悪手の判定に効かない
    for i in others:
        b = low + _EPS
        v = value(i, 1.0, 0.0, b)
        if v < b:  # 窓の中なので本当の値
            low = min(low, v)
            best_lo = max(best_lo, 1 - v)
    if c_hi < best_lo:
        return out({"verdict": "mistake", "loss_min": best_lo - c_hi})
    c1 = value(idx, 1.0, 0.0, c0 + _EPS)
    if not (c1 < c0 + _EPS and 1 - c1 >= c_hi):
        return None
    c_lo = 1 - c1
    if c_lo >= 1.0:  # 後手が必ず勝つ（同じ理由で、ほかの手を読むまでもない）
        return out({"verdict": "best", "loss_min": 0.0})
    for i in others:
        v = value(i, 0.0, c1 - _EPS, c1 + _EPS)
        if v <= c1 - _EPS or (v < c1 + _EPS and not c_lo >= 1 - v):
            return None
    return out({"verdict": "best", "loss_min": 0.0})


def solve(s: np.ndarray, depth: int) -> tuple[float, float]:
    stats = np.zeros(_N_STATS, dtype=np.int64)
    lo, hi = _solve(s, depth, stats)
    return float(lo), float(hi)


def judge(s: np.ndarray, chosen: Action, depth: int, prune: bool = True) -> dict | None:
    """endgame.judge と同じ判定（chosen は正解版の手）。決着がつかないときは None。

    返す dict には、読んだ節点の数 nodes も入れる。prune=True（既定）は窓つきの読み（R-007）で、
    判定と loss_min は prune=False（根の区間を全部読む）と同じ。
    """
    if prune:
        return _judge_pruned(s, chosen, depth)
    acts, vals, stats = action_values(s, depth)
    key = (chosen.kind, chosen.arg, chosen.noble)
    keys = [(a.kind, a.arg, a.noble) for a in map(to_action, acts)]
    if key not in keys:
        return None
    idx = keys.index(key)
    if s[TURN] % 2 == 1:  # 手番の人から見た区間にする
        vals = np.stack([1 - vals[:, 1], 1 - vals[:, 0]], axis=1)
    best_lo = float(vals[:, 0].max())
    best_hi = float(vals[:, 1].max())
    c_lo, c_hi = float(vals[idx, 0]), float(vals[idx, 1])
    nodes = int(stats[0])
    if c_hi < best_lo:
        return {"verdict": "mistake", "loss_min": best_lo - c_hi, "nodes": nodes}
    if c_lo >= best_hi:
        return {"verdict": "best", "loss_min": 0.0, "nodes": nodes}
    return None


def round_depth(s: np.ndarray) -> int:
    """この一巡の終わりまでの手番の数（先手番なら2、後手番なら1）。"""
    return 2 - int(s[TURN]) % 2
