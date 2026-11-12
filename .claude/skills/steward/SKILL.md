---
name: steward
description: このリポジトリでPRを作る・直す・CIを通す・マージするときの手順。push前の確認とマージの仕方を決めている。
---

# PR の手順（gem-merchant-research）

共通の手順（PR の書き方・CI・コンフリクト・マージ）は satou-aaaaa/shared-workflows の `routines/pr.md`。ここにはこのリポジトリだけの決まりを書く（食い違ったらこちらが優先）。

## push する前
1. `python scripts/check.py --quick` を実行する（ruff・整形・slow 以外のテスト）。
   - lint や整形で落ちたら `python scripts/check.py --fix --quick` で直してから見直す。
   - ルールエンジン（`src/gem_merchant/`）を触ったときは `--quick` を付けずに全テストを回す。
2. ページやコミットの題に、元のゲームの名前・絵・ルール文を入れていないか見る（AGENTS.md「権利」）。

## CI
- `.github/workflows/test.yml` が `python scripts/check.py`（全テスト込み）と actionlint を実行する。
- 落ちたら、ローカルで同じ `scripts/check.py` を再現してから直す。テストを飛ばしたり無効にしたりしない。

## マージ
- CI が緑で未解決のレビューが無ければ squash マージしてよい（satou さんはマージまで任せている）。
