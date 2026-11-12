"""ゲームの決まりの数（2人対戦）。

遊び方は既存の宝石カードゲームの公式ルールと同じにする（docs/RESEARCH.md「ルールの要点」）。
カード90枚の中身は自作する（公式と同じ枚数・同じ割合。NOTICE.md）。数を変えたらテストも直す。
"""

from __future__ import annotations

COLORS = ("white", "blue", "green", "red", "black")  # 宝石5色
GEMS_PER_COLOR_2P = 4  # 2人では各色4枚（7枚から3枚抜く）
GOLD = 5  # 金（万能）。人数によらず5枚
CARDS_PER_LEVEL = {1: 40, 2: 30, 3: 20}  # 合計90枚
FACE_UP_PER_LEVEL = 4  # 各レベル4枚を表向きに並べる
NOBLES_TOTAL = 10
NOBLES_2P = 3  # 2人では3枚並べる
MAX_RESERVED = 3  # 予約は3枚まで
MAX_TOKENS = 10  # 手番の終わりに10枚を超えたら戻す
TAKE_TWO_MIN_PILE = 4  # 同じ色2枚は、取る前にその色が4枚以上あるときだけ
WIN_POINTS = 15  # 手番の終わりに15点以上で、その一巡を最後までやって終わる
