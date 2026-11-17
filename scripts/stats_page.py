"""データページ（docs/stats.html）とコツ集（docs/tips.html）の本文を data/stats.json から組み立てる（build_pages.py が呼ぶ）。

数字と「〜の方が勝ちやすい」などの言い切りは、すべて集計から決める。本文に数字を手で書かない。
図は1系列の横棒（色は1つ）と表。棒には title で値を出す（指で押すと読める）。
文は t("日本語の文").format(値=…) で書く。英語のページでは t が対訳表（web/i18n/en.json）から引く。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gem_merchant.cards import PATTERNS

Tr = Callable[[str], str]


def ident(s: str) -> str:
    return s


def pct(x: float | None, digits: int = 0) -> str:
    return "—" if x is None else f"{x * 100:.{digits}f}%"


def bar(value: float, vmax: float, label: str, title: str) -> str:
    w = 0 if vmax <= 0 else max(0.5, value / vmax * 100)
    return (
        f'<div class="bar"><span class="bl">{escape(label)}</span>'
        f'<span class="bt"><span class="bf" style="width:{w:.1f}%" title="{escape(title)}"></span></span>'
        f'<span class="bv">{escape(title)}</span></div>'
    )


def pattern_label(p: dict, t: Tr) -> str:
    """値段の形を言葉にする。例: 「0点・宝石4個（1＋1＋1＋1）」。"""
    pts, shape = PATTERNS[p["level"]][p["k"]]
    form = "＋".join(str(x) for x in sorted(shape.values(), reverse=True))
    label = t("{pts}点・宝石{total}個（{form}）").format(
        pts=pts, total=sum(shape.values()), form=form
    )
    return label + (t("（自分の色を含む）") if 0 in shape else "")


def render(s: dict, t: Tr = ident) -> dict[str, str]:
    """テンプレートの {{名前}} に入れる文字列を返す。"""
    f = s["first"]
    r = s["rounds"]
    out: dict[str, str] = {
        "games": f"{s['games']:,}",
        "agent": escape(s["agent"]),
        "first_rate": pct(f["rate"], 1),
        "first_ci": f"{pct(f['lo'], 1)}〜{pct(f['hi'], 1)}",
        "first_verdict": t(f["verdict"]),
        "draws": str(f["draws"]),
        "rounds_mean": f"{r['mean']:.1f}",
        "rounds_median": f"{r['median']:g}",
        "rounds_min": str(r["min"]),
        "rounds_max": str(r["max"]),
        "win_points": f"{s['points']['winner']:.1f}",
        "lose_points": f"{s['points']['loser']:.1f}",
        "first_point_round": f"{s['first_point_round']:.1f}",
        "first_l3_round": f"{s['first_l3_round']:.1f}",
        "early_leader": t(s["early_cards_vs_points"]),
    }
    if f["lo"] > 0.5:
        out["first_note"] = t(
            "先に指せる分だけ得をしています。AI と対戦するときは、先手・後手を入れ替えて遊ぶと公平です。"
        )
    elif f["hi"] < 0.5:
        out["first_note"] = t(
            "最後の一巡まで指せる後手の方が得をしています（15点に届いた一巡は後手まで指すので、後手は相手の点を見てから最後の手を選べる）。"
        )
    else:
        out["first_note"] = t("このくらいの差なら、先手・後手どちらでも勝負になります。")
    # 長さの分布
    vmax = max(c for _, c in r["hist"])
    cap = r["hist_cap"]
    out["rounds_hist"] = "".join(
        bar(
            c,
            vmax,
            t("{b}以上").format(b=b) if b >= cap else f"{b}–{b + 1}",
            t("{n}局").format(n=c),
        )
        for b, c in r["hist"]
        if c
    )
    out["capped"] = str(r["capped"])
    # 点の入り方
    names = {
        "L1": t("レベル1のカード"),
        "L2": t("レベル2のカード"),
        "L3": t("レベル3のカード"),
        "noble": t("貴族"),
    }
    pts = t("{x}点")
    cards = t("{x}枚")
    rows = []
    for k in ("L1", "L2", "L3", "noble"):
        w = s["sources"]["winner"].get(k, 0.0)
        lo = s["sources"]["loser"].get(k, 0.0)
        rows.append(
            f"<tr><th>{names[k]}</th><td>{pts.format(x=f'{w:.1f}')}</td><td>{pts.format(x=f'{lo:.1f}')}</td></tr>"
        )
    out["sources_table"] = "".join(rows)
    srcw = s["sources"]["winner"]
    top = max(("L1", "L2", "L3", "noble"), key=lambda k: srcw.get(k, 0.0))
    out["top_source"] = names[top]
    vmax = max(srcw.values())
    short = {"L1": t("レベル1"), "L2": t("レベル2"), "L3": t("レベル3"), "noble": t("貴族")}
    out["sources_bars"] = "".join(
        bar(srcw.get(k, 0.0), vmax, short[k], pts.format(x=f"{srcw.get(k, 0.0):.1f}"))
        for k in ("L1", "L2", "L3", "noble")
    )
    bw, bl = s["buys"]["winner"], s["buys"]["loser"]
    out["buys_table"] = "".join(
        f"<tr><th>{names[k]}</th><td>{cards.format(x=f'{bw.get(k, 0):.1f}')}</td>"
        f"<td>{cards.format(x=f'{bl.get(k, 0):.1f}')}</td></tr>"
        for k in ("L1", "L2", "L3")
    )
    out["nobles_w"] = f"{s['nobles']['winner']:.2f}"
    out["nobles_l"] = f"{s['nobles']['loser']:.2f}"
    # 点かカードか
    out["lead_table"] = "".join(
        f"<tr><th>{x['round']}</th>"
        f"<td>{_meter(x['points'], x['points_n'], t)}</td>"
        f"<td>{_meter(x['cards'], x['cards_n'], t)}</td>"
        f"<td>{_meter(x['differ'], x['differ_n'], t)}</td></tr>"
        for x in s["lead"]
    )
    # 点の多い方が、カードの多い方より勝ちにつながるようになる最初の時点
    cross = next(
        (
            x["round"]
            for x in s["lead"]
            if x["round"] > 10
            and x["points"] is not None
            and x["cards"] is not None
            and x["points"] > x["cards"]
        ),
        None,
    )
    if s["early_cards_vs_points"] != "カード（割引）の多い方":
        out["crossover"] = ""
    elif cross:
        out["crossover"] = t(
            "ところが {r}ラウンド目には逆になり、点の多い方が勝ちやすくなります。序盤はカード（割引）を増やし、終盤は点に切り替える、という流れが数字に出ています。"
        ).format(r=cross)
    else:
        out["crossover"] = t("最後まで、カードの多い方が勝ちにつながっています。")
    # カードの形
    blocks = []
    for lv in (1, 2, 3):
        ps = sorted((p for p in s["patterns"] if p["level"] == lv), key=lambda p: -p["per_game"])
        vmax = max(p["per_game"] for p in ps)
        rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                escape(pattern_label(p, t)),
                _barcell(p["per_game"], vmax, cards.format(x=f"{p['per_game']:.2f}")),
                pct(p["buyer_win"]),
            )
            for p in ps
        )
        blocks.append(
            f'<h3>{t("レベル{lv}").format(lv=lv)}</h3><div class="tablewrap"><table class="pat"><thead><tr>'
            f"<th>{t('カードの形（点・値段）')}</th><th>{t('1局に買われる数')}</th><th>{t('買った人の勝率')}</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>"
        )
    out["patterns"] = "".join(blocks)
    best1 = max((p for p in s["patterns"] if p["level"] == 1), key=lambda p: p["per_game"])
    out["best_l1"] = escape(pattern_label(best1, t))
    a = s["actions"]
    out["reserve_per_game"] = f"{a['reserve_per_game']:.1f}"
    out["blind_share"] = pct(a["blind_share"])
    out["reserved_bought"] = pct(a["reserved_bought_share"])
    out["take2_share"] = pct(a["take2_share"])
    out["return_share"] = pct(a["return_share"], 1)
    return out


def _meter(x: float | None, n: int, t: Tr) -> str:
    if x is None or n < 30:  # 30局に満たない割合は出さない
        return "—"
    title = t("{p}（{n}局）").format(p=pct(x), n=n)
    return f'<span class="meter" title="{title}"><span style="width:{x * 100:.0f}%"></span></span>{pct(x)}'


def _barcell(v: float, vmax: float, label: str) -> str:
    w = 0 if vmax <= 0 else max(0.5, v / vmax * 100)
    return f'<span class="meter wide" title="{label}"><span style="width:{w:.0f}%"></span></span>{label}'


def tips(s: dict, t: Tr = ident) -> dict[str, str]:
    """コツ集（tips.html）の本文。どのコツも集計で確かめ、成り立たないコツは出さない（check_claims と同じ考え方）。"""
    L = {x["round"]: x for x in s["lead"]}
    sw, sl = s["sources"]["winner"], s["sources"]["loser"]
    bw, bl = s["buys"]["winner"], s["buys"]["loser"]
    a = s["actions"]
    l2 = sorted((p for p in s["patterns"] if p["level"] == 2), key=lambda p: -p["per_game"])
    items: list[tuple[str, str]] = []
    if L[10]["cards"] > L[10]["points"] and L[25]["points"] > L[25]["cards"]:
        items.append((
            t("序盤はカード（割引）、終盤は点"),
            t("10ラウンド目にカードの多い方が勝った割合は {c10}、点の多い方は {p10}。"
              "25ラウンド目には逆に、点の多い方 {p25}・カードの多い方 {c25}。"
              "はじめは0点のカードでも割引を増やし、相手が15点に近づいたら点の取れる手に切り替えましょう。").format(
                c10=pct(L[10]["cards"]), p10=pct(L[10]["points"]), p25=pct(L[25]["points"]), c25=pct(L[25]["cards"])),
        ))  # fmt: skip
    if max(sw, key=sw.get) == "L2":
        items.append((
            t("点の柱はレベル2のカード"),
            t("勝った人の {w}点のうち {l2}点がレベル2のカードから。"
              "AI がいちばんよく買うのは「{shape}」の形です。"
              "割引が3〜4色そろったら、レベル2を続けて買える形を目指します。").format(
                w=f"{s['points']['winner']:.1f}", l2=f"{sw['L2']:.1f}", shape=pattern_label(l2[0], t)),
        ))  # fmt: skip
    if bw["L3"] >= 1.5 * bl["L3"] and sw["L3"] > sl["L3"]:
        items.append((
            t("レベル3は勝負を決める1枚"),
            t("レベル3のカードを買った枚数は、勝った人 {w3}枚・負けた人 {l3}枚。"
              "レベル1は {w1}枚と {l1}枚で差がありません。"
              "終盤に割引で安くなったレベル3を1枚買えるかが勝ち負けを分けます。").format(
                w3=f"{bw['L3']:.1f}", l3=f"{bl['L3']:.1f}", w1=f"{bw['L1']:.1f}", l1=f"{bl['L1']:.1f}"),
        ))  # fmt: skip
    if a["reserved_bought_share"] >= 0.3 and a["blind_share"] < 0.25:
        items.append((
            t("予約は「あとで買う札」を押さえるために"),
            t("AI は1局に1人 {n}回予約し、その {b} をあとで買っています。"
              "山札から伏せて予約するのは {bl} だけ。"
              "見えている札の中から、割引がそろえば買える札を予約し、金ももらう使い方が中心です。").format(
                n=f"{a['reserve_per_game']:.1f}", b=pct(a["reserved_bought_share"]), bl=pct(a["blind_share"])),
        ))  # fmt: skip
    if a["take2_share"] < 0.2:
        items.append((
            t("宝石は基本、違う色を3つ"),
            t("宝石を取る手のうち、同じ色を2つ取るのは {x}。"
              "1手で3つ取れる方が得なので、同じ色2つは「その色だけあと2つ足りない」ときの手です。").format(
                x=pct(a["take2_share"])),
        ))  # fmt: skip
    if s["nobles"]["winner"] < 1 and sw.get("noble", 0) < sw["L2"]:
        items.append((
            t("貴族はねらうより、ついでに"),
            t("勝った人に貴族が来た数は平均 {w}人（負けた人 {l}人）、点にして {p}点。"
              "貴族のために割引の色をそろえるより、買いたいカードの割引が結果として貴族の条件に近づく形が強い指し方です。").format(
                w=f"{s['nobles']['winner']:.2f}", l=f"{s['nobles']['loser']:.2f}", p=f"{sw.get('noble', 0):.1f}"),
        ))  # fmt: skip
    if a["return_share"] < 0.2:
        items.append((
            t("チップを抱えすぎない"),
            t("10枚を超えてチップを戻した手番は {x}。"
              "戻すと1手分の宝石がむだになるので、9〜10枚になったら買う・予約する手に切り替えます。").format(
                x=pct(a["return_share"])),
        ))  # fmt: skip
    html = "".join(
        f'<section class="tip"><h2><span class="no">{i}</span>{escape(h)}</h2><p>{escape(b)}</p></section>'
        for i, (h, b) in enumerate(items, 1)
    )
    return {
        "tips": html,
        "tip_count": str(len(items)),
        "games": f"{s['games']:,}",
        "agent": escape(s["agent"]),
    }
