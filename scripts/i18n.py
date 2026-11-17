"""英語のページを作るための道具（scripts/build_pages.py が使う）。

- 対訳表 web/i18n/en.json: {"日本語の文": "English"}。ページの文（タグの間・title・aria-label・content・alt）と、
  JS の T("…") の文と、集計から作る文（scripts/stats_page.py の t("…")）が同じ表を使う。
- 文の中の {{名前}}（テンプレートの値）・{0}（JS の値）・{名前}（Python の値）はそのまま英語にも書く。
- 訳の無い文があると build_pages.py が止まる。足りない文のひな形:

    python scripts/i18n.py todo            # 足りない文を JSON で出す（en.json に足して訳す）
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_PATH = ROOT / "web" / "i18n" / "en.json"
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uff01-\uff60\u3000-\u303f]")
ATTRS = ("title", "aria-label", "content", "alt", "placeholder")


def load_en() -> dict[str, str]:
    return json.loads(EN_PATH.read_text(encoding="utf-8")) if EN_PATH.exists() else {}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class Missing(Exception):
    pass


def translate_html(html: str, d: dict[str, str], missing: set[str]) -> str:
    """タグの間の文と属性の文を訳す。<script>・<style> の中は触らない（JS は T() で訳す）。"""
    parts = re.split(r"(<script\b.*?</script>|<style\b.*?</style>|<[^>]+>)", html, flags=re.DOTALL)
    out = []
    for part in parts:
        if not part:
            continue
        if part.startswith(("<script", "<style")):
            out.append(part)
        elif part.startswith("<"):
            out.append(_tag(part, d, missing))
        else:
            out.append(_text(part, d, missing))
    return "".join(out)


def _lookup(key: str, d: dict[str, str], missing: set[str]) -> str:
    if key in d:
        return d[key]
    missing.add(key)
    return key


def _text(s: str, d: dict[str, str], missing: set[str]) -> str:
    if not CJK.search(s):
        return s
    key = norm(s)
    lead = s[: len(s) - len(s.lstrip())]
    trail = s[len(s.rstrip()) :]
    return lead + _lookup(key, d, missing) + trail


def _tag(tag: str, d: dict[str, str], missing: set[str]) -> str:
    def rep(m: re.Match) -> str:
        name, val = m.group(1), m.group(2)
        if name.lower() in ATTRS and CJK.search(val):
            return f'{name}="{_lookup(norm(val), d, missing)}"'
        return m.group(0)

    return re.sub(r'([\w-]+)="([^"]*)"', rep, tag)


def strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    return re.sub(r"(^|[^:\"'\\])//[^\n]*", r"\1", src)


JS_STR = re.compile(r"""(T\(\s*)?("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)""")


def js_strings(src: str) -> tuple[set[str], list[str]]:
    """JS の T("…") の文の集まりと、T() に入っていない日本語の文字列（訳し漏れ）。"""
    keys: set[str] = set()
    bare: list[str] = []
    for m in JS_STR.finditer(strip_js_comments(src)):
        lit = m.group(2)
        if not CJK.search(lit):
            continue
        if m.group(1) and lit[0] == '"':
            keys.add(json.loads(lit))
        else:
            bare.append(lit[:40])
    return keys, bare


def html_scripts(html: str) -> str:
    return "\n".join(re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.DOTALL))


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "todo":
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_pages

        missing = build_pages.missing_translations()
        print(json.dumps({k: "" for k in sorted(missing)}, ensure_ascii=False, indent=1))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
