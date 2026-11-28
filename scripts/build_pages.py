"""公開ページ（GitHub Pages が main の /docs を出す）を web/ から作り直す。

    py scripts/build_pages.py           # web/ の公開ファイルを docs/ に写す
    py scripts/build_pages.py --check   # docs/ が web/ と同じかだけを見る（違えば終了コード 1。check.py が使う）

ページを直すときは web/ の方を直してから、これで docs/ を作り直す（docs/*.html を直に直さない）。
集計から組み立てるページ（stats.html・tips.html・quiz.html）は web/<名前>_template.html の {{名前}} を埋めて作る。

英語のページ（docs/en/<同じ名前>）も同時に作る。日本語の文は対訳表 web/i18n/en.json で英語にする
（作り方と決まりは scripts/i18n.py）。訳の無い文・T() に入っていない JS の日本語があると止まる。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DOCS = ROOT / "docs"
FILES = [
    "index.html",
    "play.html",
    "rules.html",
    "site.css",
    "gem.css",
    "gem_engine.js",
    "gem_ui.js",
    "play_worker.js",
    "i18n.js",
]
GEM_MARK = ["W", "Bu", "G", "R", "Bk", "Au"]
# 英語のページを作る HTML（docs/en/ に同じ名前で置く）
PAGES = ["index.html", "play.html", "rules.html", "stats.html", "tips.html", "quiz.html"]
# 日本語を T() で包んでいるか確かめる JS
JS_FILES = ["gem_engine.js", "gem_ui.js", "play_worker.js"]


WEIGHTS = ROOT / "models" / "eval_champion.npy"
EVAL_W_LINE = re.compile(r"^  const EVAL_W = .*; // EVAL_W$", re.MULTILINE)


def engine_with_weights(src: str) -> str:
    """gem_engine.js の学んだ重みの行を models/eval_champion.npy の値にする（AI はいつもチャンピオンの評価）。"""
    import numpy as np

    w = np.load(WEIGHTS)
    line = "  const EVAL_W = " + json.dumps(w.tolist()) + "; // EVAL_W"
    if len(EVAL_W_LINE.findall(src)) != 1:
        raise SystemExit(
            "web/gem_engine.js に学んだ重みの行（const EVAL_W = …; // EVAL_W）が1つだけあるはず"
        )
    return EVAL_W_LINE.sub(lambda _: line, src)


def fill(template: str, values: dict[str, str]) -> str:
    def rep(m: re.Match) -> str:
        if m.group(1) not in values:
            raise SystemExit(f"テンプレートの {{{{{m.group(1)}}}}} に入れる値が無い")
        return values[m.group(1)]

    return re.sub(r"\{\{(\w+)\}\}", rep, template)


def built() -> dict[str, str]:
    out, missing = _build()
    if missing:
        raise SystemExit(
            f"英語の訳が無い文が {len(missing)} 件: "
            + " / ".join(sorted(missing)[:8])
            + "（py scripts/i18n.py todo でひな形を出し、web/i18n/en.json に足す）"
        )
    return out


def missing_translations() -> set[str]:
    return _build()[1]


def _build() -> tuple[dict[str, str], set[str]]:
    sys.path.insert(0, str(ROOT / "scripts"))
    import i18n
    import stats_page

    en = i18n.load_en()
    missing: set[str] = set()

    def t(key: str) -> str:
        if key in en:
            return en[key]
        missing.add(key)
        return key

    ja = {name: (WEB / name).read_text(encoding="utf-8") for name in FILES}
    ja["gem_engine.js"] = engine_with_weights(ja["gem_engine.js"])
    stats = json.loads((ROOT / "data" / "stats.json").read_text(encoding="utf-8"))
    puzzles = json.loads((ROOT / "data" / "endgame_puzzles.json").read_text(encoding="utf-8"))
    hard = sum(not p["greedy_correct"] for p in puzzles)
    filled = {
        "stats.html": (
            "stats_template.html",
            stats_page.render(stats),
            stats_page.render(stats, t),
        ),
        "tips.html": ("tips_template.html", stats_page.tips(stats), stats_page.tips(stats, t)),
        "quiz.html": ("quiz_template.html",)
        + ({"count": str(len(puzzles)), "hard": str(hard)},) * 2,
    }
    templates = {}
    for name, (tpl_name, vja, ven) in filled.items():
        tpl = (WEB / tpl_name).read_text(encoding="utf-8")
        templates[name] = (tpl, ven)
        ja[name] = fill(tpl, vja)
    ja["puzzles.js"] = (
        "// data/endgame_puzzles.json から scripts/build_pages.py が作る（手で直さない）\n"
        "window.GEM_PUZZLES = "
        + json.dumps(puzzles, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    out = dict(ja)
    # JS の文: T("…") の文は訳があるか、T() に入っていない日本語が無いか
    # CSS の content: に日本語を書くと訳せない（英語のページに日本語が残る）。文は JS の T() か HTML に置く
    for name, text in ja.items():
        src = (
            text
            if name.endswith(".css")
            else "\n".join(
                re.findall(r"<style\b.*?</style\b[^>]*>", text, flags=re.DOTALL | re.IGNORECASE)
            )
        )
        for m in re.finditer(r'content:\s*"([^"]*)"', src):
            if i18n.CJK.search(m.group(1)):
                raise SystemExit(
                    f"{name}: CSS の content に日本語「{m.group(1)}」（訳せないので JS の T() で入れる）"
                )
    for name in JS_FILES:
        keys, bare = i18n.js_strings(ja[name])
        _check_js(name, keys, bare, t)
    for name in PAGES:
        src = templates[name][0] if name in templates else ja[name]
        keys, bare = i18n.js_strings(i18n.html_scripts(src))
        _check_js(name, keys, bare, t)
        out[name] = _with_lang(ja[name], name, "ja")
        html = i18n.translate_html(src, en, missing)
        if name in templates:
            html = fill(html, templates[name][1])
        out["en/" + name] = _with_lang(html, name, "en")
    out["i18n_en.js"] = (
        "// web/i18n/en.json から scripts/build_pages.py が作る（手で直さない）。英語のページの JS の文\n"
        "window.GEM_EN = " + json.dumps(en, ensure_ascii=False, separators=(",", ":")) + ";\n"
    )
    return out, missing


def _check_js(name: str, keys: set[str], bare: list[str], t) -> None:
    if bare:
        raise SystemExit(f'{name}: T() に入っていない日本語の文字列: {bare[:5]}（T("…") で包む）')
    for k in keys:
        t(k)


def _with_lang(html: str, name: str, lang: str) -> str:
    """言葉の切り替え（i18n.js・切り替えリンク）を入れる。英語は資料の場所を一つ上にする。"""
    if lang == "ja":
        head = '<script src="i18n.js"></script>\n'
        link = f'<a href="en/{name}" data-lang="en" lang="en" hreflang="en">English</a>'
    else:
        html = html.replace('<html lang="ja">', '<html lang="en" data-base="../">', 1)
        html = re.sub(
            r'(src|href)="(?!https?:|#|mailto:|\.\./)([\w./-]+\.(?:js|css|json|svg|png))"',
            r'\1="../\2"',
            html,
        )
        # 本文の宝石の丸（<span class="gem cN">名前</span>）は、丸からはみ出さないよう短い印にする（web/i18n.js の GEM_MARK と同じ）
        html = re.sub(
            r'<span class="gem c(\d)">([^<]*)</span>',
            lambda m: (
                f'<span class="gem c{m.group(1)}" title="{m.group(2)}">{GEM_MARK[int(m.group(1))]}</span>'
            ),
            html,
        )
        head = '<script src="../i18n_en.js"></script>\n<script src="../i18n.js"></script>\n'
        link = f'<a href="../{name}" data-lang="ja" lang="ja" hreflang="ja">日本語</a>'
    html = html.replace("</head>", head + "</head>", 1)
    if "</nav>" not in html:
        raise SystemExit(f"{name}: ナビ（<nav>）が無いので言葉の切り替えを置けない")
    return html.replace("</nav>", link + "</nav>", 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = built()
    engine = WEB / "gem_engine.js"
    engine_old = engine.read_text(encoding="utf-8")
    engine_new = engine_with_weights(engine_old)
    if args.check and engine_new != engine_old:
        sys.exit(
            "web/gem_engine.js の学んだ重みが models/eval_champion.npy と違う（py scripts/build_pages.py で写す）"
        )
    if engine_new != engine_old:
        engine.write_text(engine_new, encoding="utf-8", newline="\n")
        print("書いた: web/gem_engine.js（学んだ重み）")
    stale = [
        n
        for n, text in out.items()
        if not (DOCS / n).exists() or (DOCS / n).read_text(encoding="utf-8") != text
    ]
    if args.check:
        if stale:
            sys.exit(
                "docs/ が古い: " + ", ".join(stale) + "（py scripts/build_pages.py で作り直す）"
            )
        print("docs/ は最新")
        return
    for n in stale:
        (DOCS / n).parent.mkdir(parents=True, exist_ok=True)
        (DOCS / n).write_text(out[n], encoding="utf-8", newline="\n")
        print("書いた:", "docs/" + n)
    nojekyll = DOCS / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("")


if __name__ == "__main__":
    main()
