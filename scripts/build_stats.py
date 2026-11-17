"""AI の自分同士の対局の記録から、データページの集計（data/stats.json）を作る。

    python scripts/selfplay_record.py fmcts2000 --games 1000 --workers 4   # 記録（data/selfplay/）
    python scripts/build_stats.py                                          # 集計 → data/stats.json
    python scripts/build_pages.py                                          # docs/stats.html を作り直す

本文の数字と言い切り（「〜の方が勝ちやすい」など）は、すべてここで集計から決める（手で書かない）。
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gem_merchant.arena import wilson
from gem_merchant.cards import CARDS, PATTERNS
from gem_merchant.rules import COLORS

COLOR_JA = ["白", "青", "緑", "赤", "黒"]
CHECK_ROUNDS = [5, 10, 15, 20, 25]
HIST_CAP = 40  # これより長い局は分布の図で1本にまとめる


def load(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pattern_of(cid: int) -> tuple[int, int]:
    """カードの (レベル, 値段の形の番号)。cards.make_cards の並び（レベル→色→形）から出す。"""
    c = CARDS[cid]
    first = min(x.id for x in CARDS if x.level == c.level)
    return c.level, (cid - first) % len(PATTERNS[c.level])


def pattern_label(level: int, k: int) -> str:
    """値段の形を言葉にする。例: 「自分の色以外4色×1」。0番（自分の色）は「同じ色」。"""
    pts, shape = PATTERNS[level][k]
    total = sum(shape.values())
    parts = sorted(shape.values(), reverse=True)
    form = "＋".join(str(x) for x in parts)
    same = "（自分の色を含む）" if 0 in shape else ""
    return f"{pts}点・宝石{total}個（{form}）{same}"


def build(games: list[dict]) -> dict:
    n = len(games)
    out: dict = {"agent": games[0]["agent"], "games": n}
    # 先手有利
    first = sum(1.0 if g["winner"] == 0 else 0.5 if g["winner"] < 0 else 0.0 for g in games)
    lo, hi = wilson(first, n)
    draws = sum(g["winner"] < 0 for g in games)
    out["first"] = {"rate": first / n, "lo": lo, "hi": hi, "draws": draws}
    out["first"]["verdict"] = (
        "先手が有利" if lo > 0.5 else "後手が有利" if hi < 0.5 else "先手と後手の差ははっきりしない"
    )
    # 長さ（ラウンド＝2人が1手ずつ指す一巡）
    rounds = [math.ceil(g["turns"] / 2) for g in games]
    capped = sum(g["turns"] >= 200 for g in games)  # game.MAX_TURNS で打ち切った局
    out["rounds"] = {
        "capped": capped,
        "mean": statistics.mean(rounds),
        "median": statistics.median(rounds),
        "min": min(rounds),
        "max": max(rounds),
        "hist": _hist([min(x, HIST_CAP) for x in rounds], 2),
        "hist_cap": HIST_CAP,
    }
    win_pts = [g["points"][g["winner"]] for g in games if g["winner"] >= 0]
    lose_pts = [g["points"][1 - g["winner"]] for g in games if g["winner"] >= 0]
    out["points"] = {"winner": statistics.mean(win_pts), "loser": statistics.mean(lose_pts)}

    # 点の入り方・カードの買い方（勝った人と負けた人）
    src = {"winner": defaultdict(float), "loser": defaultdict(float)}
    buys = {"winner": defaultdict(float), "loser": defaultdict(float)}
    nob = {"winner": 0.0, "loser": 0.0}
    reserves = blind = res_bought = takes = take2 = rets = moves_total = 0
    first_point_round = []
    first_l3_round = []
    pat = defaultdict(lambda: [0, 0])  # (lv, k) → [買われた回数, 買った人が勝った回数]
    color_buy = defaultdict(lambda: [0, 0])
    lead = {r: {"points": [0, 0], "cards": [0, 0], "both_differ": [0, 0]} for r in CHECK_ROUNDS}
    for g in games:
        w = g["winner"]
        cards = [0, 0]
        prev = [0, 0]
        got_point = False
        got_l3 = False
        for t, m in enumerate(g["moves"]):
            p = m["p"]
            moves_total += 1
            role = None if w < 0 else ("winner" if p == w else "loser")
            if m["k"] == "buy":
                c = CARDS[m["c"]]
                cards[p] += 1
                if role:
                    src[role][f"L{c.level}"] += c.points
                    buys[role][f"L{c.level}"] += 1
                key = pattern_of(m["c"])
                pat[key][0] += 1
                pat[key][1] += p == w
                color_buy[c.color][0] += 1
                color_buy[c.color][1] += p == w
                res_bought += m["res"]
                if c.points and not got_point:
                    got_point = True
                    first_point_round.append(t // 2 + 1)
                if c.level == 3 and not got_l3:
                    got_l3 = True
                    first_l3_round.append(t // 2 + 1)
            elif m["k"] == "reserve":
                reserves += 1
                blind += m["blind"]
            elif m["k"] in ("take3", "take2"):
                takes += 1
                take2 += m["k"] == "take2"
            rets += m["ret"] > 0
            if m["noble"] >= 0 and role:
                src[role]["noble"] += 3
                nob[role] += 1
            prev = m["pts"]
            r = t // 2 + 1
            if t % 2 == 1 and r in lead and w >= 0:
                _lead(lead[r]["points"], prev, w)
                _lead(lead[r]["cards"], cards, w)
                if (prev[0] - prev[1]) * (
                    cards[0] - cards[1]
                ) < 0:  # 点で勝る人と、カードで勝る人が違う
                    _lead(lead[r]["both_differ"], cards, w)
    decided = sum(g["winner"] >= 0 for g in games)
    out["sources"] = {role: {k: v / decided for k, v in d.items()} for role, d in src.items()}
    out["buys"] = {role: {k: v / decided for k, v in d.items()} for role, d in buys.items()}
    out["nobles"] = {role: v / decided for role, v in nob.items()}
    out["actions"] = {
        "reserve_per_game": reserves / n / 2,
        "blind_share": blind / reserves if reserves else 0.0,
        "reserved_bought_share": res_bought / reserves if reserves else 0.0,
        "take2_share": take2 / takes if takes else 0.0,
        "return_share": rets / moves_total,
    }
    out["first_point_round"] = statistics.mean(first_point_round)
    out["first_l3_round"] = statistics.mean(first_l3_round)
    out["lead"] = [
        {
            "round": r,
            "points": _rate(lead[r]["points"]),
            "points_n": lead[r]["points"][1],
            "cards": _rate(lead[r]["cards"]),
            "cards_n": lead[r]["cards"][1],
            "differ": _rate(lead[r]["both_differ"]),
            "differ_n": lead[r]["both_differ"][1],
        }
        for r in CHECK_ROUNDS
    ]
    # 序盤（10ラウンド目）に点ではなくカード（割引）で勝っている人が勝つ割合
    early = next(x for x in out["lead"] if x["round"] == 10)
    out["early_cards_vs_points"] = (
        "カード（割引）の多い方" if early["cards"] > early["points"] else "点の多い方"
    )
    out["patterns"] = []
    for (lv, k), (cnt, won) in sorted(pat.items()):
        copies = sum(1 for c in CARDS if pattern_of(c.id) == (lv, k))
        out["patterns"].append(
            {
                "level": lv,
                "k": k,
                "label": pattern_label(lv, k),
                "points": PATTERNS[lv][k][0],
                "cost": sum(PATTERNS[lv][k][1].values()),
                "per_game": cnt / copies / n * 5,  # 5色の札を合わせて、1局に何枚買われたか
                "buyer_win": won / cnt,
                "count": cnt,
            }
        )
    out["colors"] = [
        {"color": COLOR_JA[c], "key": COLORS[c], "per_game": color_buy[c][0] / n, "buyer_win": color_buy[c][1] / max(1, color_buy[c][0])}
        for c in range(5)
    ]  # fmt: skip
    return out


def _lead(acc: list[int], vals: list[int], w: int) -> None:
    if vals[0] == vals[1]:
        return
    leader = 0 if vals[0] > vals[1] else 1
    acc[0] += leader == w
    acc[1] += 1


def _rate(acc: list[int]) -> float | None:
    return acc[0] / acc[1] if acc[1] else None


def _hist(xs: list[int], width: int) -> list[list[int]]:
    lo = min(xs) // width * width
    out = []
    b = lo
    while b <= max(xs):
        out.append([b, sum(b <= x < b + width for x in xs)])
        b += width
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data" / "selfplay" / "fmcts2000.jsonl.gz"))
    ap.add_argument("--out", default=str(ROOT / "data" / "stats.json"))
    args = ap.parse_args()
    games = load(Path(args.src))
    stats = build(games)
    Path(args.out).write_text(
        json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    f = stats["first"]
    print(
        f"{stats['games']}局: 先手の勝率 {f['rate']:.3f} [{f['lo']:.3f}, {f['hi']:.3f}]、"
        f"平均 {stats['rounds']['mean']:.1f} ラウンド → {args.out}"
    )


if __name__ == "__main__":
    main()
