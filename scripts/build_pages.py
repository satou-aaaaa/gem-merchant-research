"""公開ページ（GitHub Pages が main の /docs を出す）を web/ から作り直す。

    py scripts/build_pages.py           # web/ の公開ファイルを docs/ に写す
    py scripts/build_pages.py --check   # docs/ が web/ と同じかだけを見る（違えば終了コード 1。check.py が使う）

ページを直すときは web/ の方を直してから、これで docs/ を作り直す（docs/*.html を直に直さない）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
DOCS = ROOT / "docs"
FILES = ["index.html", "play.html", "rules.html", "site.css", "gem_engine.js", "play_worker.js"]


def built() -> dict[str, str]:
    return {name: (WEB / name).read_text(encoding="utf-8") for name in FILES}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = built()
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
        (DOCS / n).write_text(out[n], encoding="utf-8", newline="\n")
        print("書いた:", "docs/" + n)
    nojekyll = DOCS / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("")


if __name__ == "__main__":
    main()
