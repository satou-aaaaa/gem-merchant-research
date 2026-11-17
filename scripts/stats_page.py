"""データページ（docs/stats.html）の本文を data/stats.json から組み立てる（build_pages.py が呼ぶ）。

数字と「〜の方が勝ちやすい」などの言い切りは、すべて集計から決める。本文に数字を手で書かない。
図は1系列の横棒（色は1つ）と表。棒には title で値を出す（指で押すと読める）。
"""

from __future__ import annotations

from html import escape


def pct(x: float | None, digits: int = 0) -> str:
    return "—" if x is None else f"{x * 100:.{digits}f}%"


def bar(value: float, vmax: float, label: str, title: str) -> str:
    w = 0 if vmax <= 0 else max(0.5, value / vmax * 100)
    return (
        f'<div class="bar"><span class="bl">{escape(label)}</span>'
        f'<span class="bt"><span class="bf" style="width:{w:.1f}%" title="{escape(title)}"></span></span>'
        f'<span class="bv">{escape(title)}</span></div>'
    )


def render(s: dict) -> dict[str, str]:
    """テンプレートの {{名前}} に入れる文字列を返す。"""
    f = s["first"]
    r = s["rounds"]
    out: dict[str, str] = {
        "games": f"{s['games']:,}",
        "agent": escape(s["agent"]),
        "first_rate": pct(f["rate"], 1),
        "first_ci": f"{pct(f['lo'], 1)}〜{pct(f['hi'], 1)}",
        "first_verdict": f["verdict"],
        "draws": str(f["draws"]),
        "rounds_mean": f"{r['mean']:.1f}",
        "rounds_median": f"{r['median']:g}",
        "rounds_min": str(r["min"]),
        "rounds_max": str(r["max"]),
        "win_points": f"{s['points']['winner']:.1f}",
        "lose_points": f"{s['points']['loser']:.1f}",
        "first_point_round": f"{s['first_point_round']:.1f}",
        "first_l3_round": f"{s['first_l3_round']:.1f}",
        "early_leader": s["early_cards_vs_points"],
    }
    if f["lo"] > 0.5:
        out["first_note"] = (
            "先に指せる分だけ得をしています。AI と対戦するときは、先手・後手を入れ替えて遊ぶと公平です。"
        )
    elif f["hi"] < 0.5:
        out["first_note"] = (
            "最後の一巡まで指せる後手の方が得をしています（15点に届いた一巡は後手まで指すので、後手は相手の点を見てから最後の手を選べる）。"
        )
    else:
        out["first_note"] = "このくらいの差なら、先手・後手どちらでも勝負になります。"
    # 長さの分布
    vmax = max(c for _, c in r["hist"])
    cap = r["hist_cap"]
    out["rounds_hist"] = "".join(
        bar(c, vmax, f"{b}以上" if b >= cap else f"{b}〜{b + 1}", f"{c}局")
        for b, c in r["hist"]
        if c
    )
    out["capped"] = str(r["capped"])
    # 点の入り方
    names = {
        "L1": "レベル1のカード",
        "L2": "レベル2のカード",
        "L3": "レベル3のカード",
        "noble": "貴族",
    }
    rows = []
    for k in ("L1", "L2", "L3", "noble"):
        w = s["sources"]["winner"].get(k, 0.0)
        lo = s["sources"]["loser"].get(k, 0.0)
        rows.append(f"<tr><th>{names[k]}</th><td>{w:.1f}点</td><td>{lo:.1f}点</td></tr>")
    out["sources_table"] = "".join(rows)
    srcw = s["sources"]["winner"]
    top = max(("L1", "L2", "L3", "noble"), key=lambda k: srcw.get(k, 0.0))
    out["top_source"] = names[top]
    vmax = max(srcw.values())
    short = {"L1": "レベル1", "L2": "レベル2", "L3": "レベル3", "noble": "貴族"}
    out["sources_bars"] = "".join(
        bar(srcw.get(k, 0.0), vmax, short[k], f"{srcw.get(k, 0.0):.1f}点")
        for k in ("L1", "L2", "L3", "noble")
    )
    bw, bl = s["buys"]["winner"], s["buys"]["loser"]
    out["buys_table"] = "".join(
        f"<tr><th>{names[k]}</th><td>{bw.get(k, 0):.1f}枚</td><td>{bl.get(k, 0):.1f}枚</td></tr>"
        for k in ("L1", "L2", "L3")
    )
    out["nobles_w"] = f"{s['nobles']['winner']:.2f}"
    out["nobles_l"] = f"{s['nobles']['loser']:.2f}"
    # 点かカードか
    rows = []
    for x in s["lead"]:
        rows.append(
            f"<tr><th>{x['round']}</th>"
            f"<td>{_meter(x['points'], x['points_n'])}</td>"
            f"<td>{_meter(x['cards'], x['cards_n'])}</td>"
            f"<td>{_meter(x['differ'], x['differ_n'])}</td></tr>"
        )
    out["lead_table"] = "".join(rows)
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
    out["crossover"] = (
        ""
        if s["early_cards_vs_points"] != "カード（割引）の多い方"
        else f"ところが {cross}ラウンド目には逆になり、点の多い方が勝ちやすくなります。序盤はカード（割引）を増やし、終盤は点に切り替える、という流れが数字に出ています。"
        if cross
        else "最後まで、カードの多い方が勝ちにつながっています。"
    )
    # カードの形
    blocks = []
    for lv in (1, 2, 3):
        ps = sorted((p for p in s["patterns"] if p["level"] == lv), key=lambda p: -p["per_game"])
        vmax = max(p["per_game"] for p in ps)
        rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                escape(p["label"]),
                _barcell(p["per_game"], vmax, "{:.2f}枚".format(p["per_game"])),
                pct(p["buyer_win"]),
            )
            for p in ps
        )
        blocks.append(
            f'<h3>レベル{lv}</h3><div class="tablewrap"><table class="pat"><thead><tr><th>カードの形（点・値段）</th>'
            f"<th>1局に買われる数</th><th>買った人の勝率</th></tr></thead><tbody>{rows}</tbody></table></div>"
        )
    out["patterns"] = "".join(blocks)
    best1 = max((p for p in s["patterns"] if p["level"] == 1), key=lambda p: p["per_game"])
    out["best_l1"] = escape(best1["label"])
    a = s["actions"]
    out["reserve_per_game"] = f"{a['reserve_per_game']:.1f}"
    out["blind_share"] = pct(a["blind_share"])
    out["reserved_bought"] = pct(a["reserved_bought_share"])
    out["take2_share"] = pct(a["take2_share"])
    out["return_share"] = pct(a["return_share"], 1)
    return out


def _meter(x: float | None, n: int = 0) -> str:
    if x is None or n < 30:  # 30局に満たない割合は出さない
        return "—"
    return f'<span class="meter" title="{pct(x)}（{n}局）"><span style="width:{x * 100:.0f}%"></span></span>{pct(x)}'


def _barcell(v: float, vmax: float, label: str) -> str:
    w = 0 if vmax <= 0 else max(0.5, v / vmax * 100)
    return f'<span class="meter wide" title="{label}"><span style="width:{w:.0f}%"></span></span>{label}'
