from gem_merchant import rules


def test_card_and_token_counts():
    assert sum(rules.CARDS_PER_LEVEL.values()) == 90
    assert len(rules.COLORS) == 5
    assert rules.GEMS_PER_COLOR_2P * len(rules.COLORS) + rules.GOLD == 25


def test_two_player_setup():
    assert rules.NOBLES_2P == 2 + 1  # 貴族は人数+1枚
    assert rules.NOBLES_2P < rules.NOBLES_TOTAL
    assert rules.TAKE_TWO_MIN_PILE == rules.GEMS_PER_COLOR_2P
