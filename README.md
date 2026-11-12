# gem-merchant-research（宝石商の工房）

宝石を集めてカードを買い、カードの割引で強くなっていく2人用カードゲームの、強い AI と学習サイトを作る研究リポジトリ。
遊び方は既存の宝石カードゲームと同じだが、名前・絵・カードの中身は自作（[NOTICE.md](NOTICE.md)）。
姉妹プロジェクト: [carcassonne-research](https://github.com/satou-aaaaa/carcassonne-research)（仕組みの多くをここから写す）。

- 調べたこと: [docs/RESEARCH.md](docs/RESEARCH.md)
- 進め方: [docs/ROADMAP.md](docs/ROADMAP.md)（段階1「土台」と段階2「ルールエンジン」まで済み）

## 準備

```bash
bash scripts/setup.sh                 # .venv を作って requirements.txt を入れる（何度実行してもよい。Windows は Git Bash で）
.venv/bin/python scripts/check.py --quick   # ruff・整形・テスト（Windows は .venv\Scripts\python）
.venv/bin/python scripts/play_random.py      # ランダムな手どうしの対局で、終わり方・手数・手の候補の数を見る
```
