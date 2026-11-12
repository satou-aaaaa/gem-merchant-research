from gem_merchant import game
from gem_merchant.cards import CARDS
from gem_merchant.endgame import judge, outcomes, solve
from gem_merchant.game import BUY, RESERVE, TAKE3, Action


def _rich_state():
    """先手が場の1点の札を買えば15点に届き、後手はもう届かない局面。"""
    s = game.new_game(3)
    cid = next(c.id for c in CARDS if c.level == 1 and c.points == 1)
    for level in (1, 2, 3):  # 同じ札が山札・場にあれば取り除いてから置く
        if cid in s.decks[level]:
            s.decks[level].remove(cid)
        s.board[level] = [x if x != cid else -1 for x in s.board[level]]
    s.board[1][0] = cid
    p = s.players[0]
    p.points = 14
    p.tokens = list(CARDS[cid].cost) + [0]
    s.bank = [4 - p.tokens[c] for c in range(5)] + [5]
    return s


def test_terminal_and_unknown_values():
    s = game.new_game(1)
    assert solve(s, 0) == (0.0, 1.0)
    s.players[0].points = 15
    s.turn = 1
    game.apply(s, Action(TAKE3, (0, 1, 2)))  # 後手が指して一巡が終わる
    assert s.done and solve(s, 3) == (1.0, 1.0)


def test_outcomes_cover_every_possible_draw():
    s = game.new_game(1)
    outs = outcomes(s, Action(RESERVE, (2, 0)))
    assert len(outs) == len(set(s.decks[2]))
    assert {o.board[2][0] for o in outs} == set(s.decks[2])


def test_buying_the_winning_card_is_judged_best():
    s = _rich_state()
    buy = next(a for a in game.legal_actions(s) if a.kind == BUY and a.arg == ("board", 1, 0))
    assert judge(s, buy)["verdict"] == "best"
    assert solve(s, 2)[0] == 1.0  # 先手の勝ちが確定


def test_lost_position_every_move_is_equal():
    s = game.new_game(3)
    s.players[0].points = 15  # 先手はもう15点。後手は何をしても届かない
    s.turn = 1
    take = next(a for a in game.legal_actions(s) if a.kind == TAKE3)
    r = judge(s, take)
    assert r is not None and r["verdict"] == "best"  # 後手はどの手でも負け＝どれも同じ


def test_not_buying_the_tying_card_is_a_proven_mistake():
    s = _rich_state()
    s.players[1], s.players[0] = s.players[0], s.players[1]  # 札を買える人を後手にする
    s.players[0].points, s.players[0].bought = 15, 6  # 先手はもう15点（買った札6枚）
    s.players[1].bought = 3  # 同点なら買った札が少ない後手の勝ち
    s.turn = 1
    acts = game.legal_actions(s)
    buy = next(a for a in acts if a.kind == BUY and a.arg == ("board", 1, 0))
    take = next(a for a in acts if a.kind == TAKE3)
    assert judge(s, buy)["verdict"] == "best"
    r = judge(s, take)
    assert r["verdict"] == "mistake" and r["loss_min"] == 1.0
