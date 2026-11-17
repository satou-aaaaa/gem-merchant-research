"""英語のページを作る道具（scripts/i18n.py・build_pages.py）の確かめ。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_pages
import i18n


def test_translate_html_text_and_attrs_but_not_scripts():
    d = {"遊び方": "How to play", "サイト内": "Site"}
    missing: set[str] = set()
    html = '<nav aria-label="サイト内"><a>遊び方</a></nav><script>const x = "遊び方";</script><p>未訳</p>'
    out = i18n.translate_html(html, d, missing)
    assert '<nav aria-label="Site"><a>How to play</a></nav>' in out
    assert 'const x = "遊び方";' in out  # JS は T() で訳す
    assert missing == {"未訳"}
    # 大文字のタグ・閉じタグの空白でも JS の中は触らない（CodeQL の指摘）
    upper = i18n.translate_html('<SCRIPT>const y = "遊び方";</SCRIPT ><p>遊び方</p>', d, set())
    assert 'const y = "遊び方";' in upper and "<p>How to play</p>" in upper
    assert i18n.html_scripts('<Script src="a"></Script><SCRIPT>x()</SCRIPT >') == "\nx()"


def test_js_strings_finds_untranslated_literals():
    keys, bare = i18n.js_strings('T("色{0}", c); const a = "白"; // コメントの日本語はよい\n')
    assert keys == {"色{0}"}
    assert bare == ['"白"']


def test_every_text_has_a_translation():
    # 訳し漏れがあると build_pages.py が止まる（check.py の --check でも見る）
    assert build_pages.missing_translations() == set()


def test_english_pages_use_parent_assets():
    out = build_pages.built()
    for name in build_pages.PAGES:
        html = out["en/" + name]
        assert '<html lang="en" data-base="../">' in html
        assert 'src="gem_engine.js"' not in html and 'href="site.css"' not in html
        assert 'data-lang="ja"' in html and 'data-lang="en"' in out[name]
