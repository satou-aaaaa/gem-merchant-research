---
name: ui-check
description: 公開ページ（docs/ の対戦ページ・遊び方など）や、それを作る web/・scripts/build_pages.py を変えたときに、スマホ幅とPC幅で表示と使いやすさを点検して直す手順。
---

# サイトの UI/UX 点検（gem-merchant-research）

サイト「宝石商の工房」の目的はプレイヤーの教育。ページを変えたら毎回、同じ作業の中で点検して直す。

## 1. 機械の点検（必ず）
```bash
python scripts/build_pages.py                  # web/ → docs/ を作り直す（docs/*.html を直に直さない）
node scripts/ui_check.mjs --shots ui-shots     # 全ページ × スマホ幅390px・PC幅1280px
node scripts/ui_check.mjs play.html            # 1ページだけ
```
- ✗ は直す（CI の test.yml `ui` ジョブも同じ点検で落ちる）。
  - コンソールエラー・読み込み失敗、横のはみ出し
  - 押す場所が 24×24px 未満、スマホ幅で高さ 44px 未満、名前のないボタン・入力欄
  - 11px 未満の文字
  - 対戦ページ: 新しい対局→宝石3色を取る→AI が返す、カードを押すと選び方が出る、ヒントが出る
- Playwright と Chromium はクラウドセッションに入っている。

## 2. 目で見る点検（ui-shots/*.png を開く）
- スマホ幅で、場のカード（値段の数字）・宝石・得点の欄が読めるか。
- 対戦ページ: 宝石の選び方・カードの買い方・戻し方・貴族の選び方が迷わず分かるか（ルールを知らない人の目で）。
- ページ間の行き来ができるか（ヘッダーのナビ）。
- ダーク表示（prefers-color-scheme: dark）で読めない色がないか（色を変えたとき）。

## 3. 直し方
- 元（`web/*.html`, `web/site.css`, `web/gem_engine.js`）を直して `python scripts/build_pages.py`。
- エンジン（`web/gem_engine.js`）を直したら `tests/test_play_js.py`（Python と全手一致）も回す。

## 4. 報告
- 直した点を「問題: 何をどう直したか」で短く書く。
