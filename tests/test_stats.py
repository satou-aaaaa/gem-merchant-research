"""データページの集計（data/stats.json）が、記録（data/selfplay/）から作り直したものと同じかを見る。

本文の数字は集計からだけ組み立てるので、ここが一致していれば手書きの数字は入っていない。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_stats
import stats_page


def test_stats_json_is_up_to_date():
    games = build_stats.load(ROOT / "data" / "selfplay" / "fmcts2000.jsonl.gz")
    fresh = json.loads(json.dumps(build_stats.build(games), ensure_ascii=False))
    saved = json.loads((ROOT / "data" / "stats.json").read_text(encoding="utf-8"))
    assert fresh == saved, "python scripts/build_stats.py で作り直す"


def test_page_values_cover_template():
    saved = json.loads((ROOT / "data" / "stats.json").read_text(encoding="utf-8"))
    vals = stats_page.render(saved)
    tpl = (ROOT / "web" / "stats_template.html").read_text(encoding="utf-8")
    import re

    assert set(re.findall(r"\{\{(\w+)\}\}", tpl)) <= set(vals)
