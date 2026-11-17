# AGENTS.md

宝石カードゲーム（2人対戦）の強い AI と学習サイト「宝石商の工房」を作る研究リポジトリ。背景と計画は README.md・docs/RESEARCH.md・docs/ROADMAP.md。

## 準備（最初に一度）

```bash
bash scripts/setup.sh   # .venv を作り requirements.txt を入れる（Python の版は .python-version）。何度実行してもよい（Windows は Git Bash で）
```

以後のコマンドは .venv の Python で動かす。Claude Code のクラウドセッションでは `.claude/settings.json` のフックが自動で実行し、.venv を PATH の先頭に置く。

## push する前の確認

```bash
python scripts/check.py --quick   # ruff・整形・slow 以外のテスト
```

このリポジトリだけの PR の決まりは `.claude/skills/steward/SKILL.md`（共通の手順より優先）。

## 公開

- GitHub Pages は `main` の `/docs` を公開する。ページの元は `web/`（`index.html`・`play.html`・`rules.html`・`site.css`・`gem.css`・`gem_ui.js`・`gem_engine.js`・`play_worker.js`）。直したら `python scripts/build_pages.py` で docs/ に写す（`check.py` が古いと止まる）。
- データページ（`stats.html`）とコツ集（`tips.html`）は `data/stats.json`（`scripts/build_stats.py` が `data/selfplay/` の記録から作る）だけから組み立てる。本文に数字や言い切りを手で書かない（`scripts/stats_page.py` で集計から決める）。
- 英語版は `docs/en/`（同じファイル名）。`build_pages.py` が日本語のページから作る。日本語の文を変えたら対訳表 `web/i18n/en.json` も直す（訳し漏れ・`T()` に入っていない JS の日本語・CSS の `content` の日本語があると止まる。`python scripts/i18n.py todo` でひな形が出る）。言語はブラウザの設定で自動で選び、切り替えリンクで選んだ言語を覚える（`web/i18n.js`）。
- クイズ（`quiz.html`）は `data/endgame_puzzles.json`（`scripts/make_puzzles.py` が読み切りで作る）から組み立てる。作り直したら `tests/test_puzzles.py`（遅いテストも）で正解と選択肢の値を確かめる。
- 対戦ページのエンジンと AI（`web/gem_engine.js`）は `game.py`・`agents.py` の JS 版。ルールや評価を Python で変えたら JS も直す（`tests/test_play_js.py` が毎手を照合）。
- ページを変えたら毎回、スマホ幅とPC幅で UI を点検して直す（`node scripts/ui_check.mjs --shots ui-shots`、手順は `.claude/skills/ui-check/SKILL.md`）。CI の test.yml `ui` ジョブも同じ点検をする。

## 権利（必ず守る）

- 元のゲームの名前・ロゴ・絵・ルールの文章を、コード・ページ・コミットの題に使わない。名前は「宝石商の工房」。カード90枚は自作（NOTICE.md）。
- 非商用ライセンスの公開実装のコードは取り込まない（比べる相手として別に動かすだけ）。

## 研究の進め方

- 研究の「次にやること」は `docs/BACKLOG.md`。毎日の研究の回（shared-workflows の `routines/research-loop.md`）がここから1件ずつ進める。
- 人に頼まれた研究も、始める前に一覧へ項目を足し（または「作業中」にし）、終わったら「済み」と結果を書く。結果は効かなかったものも `docs/EXPERIMENTS.md` に残す。
- 重い対局・学習は `research-run.yml`（Actions、結果はブランチ `research-results`）で回す。

## 共通のきまり

- PR の作り方・マージの仕方は satou-aaaaa/shared-workflows の `routines/pr.md`、全体のきまりは `routines/common.md` に従う。
- CI の部品（CI失敗Issue・ブランチ片付け）は shared-workflows の共通部品を呼ぶ。
  リポジトリ側の .github/workflows には呼び出しと設定値だけを書く。
- Claude 以外の AI・人が作業するときは、shared-workflows の `routines/tool-map.md`（道具の置き換え）と `routines/without-claude.md` を読む。
