// tests/test_play_js.py から呼ぶ: 標準入力の JSON の指示どおりに web/gem_engine.js を動かし、結果を JSON で出す。
"use strict";
const E = require("../web/gem_engine.js");

const input = JSON.parse(require("fs").readFileSync(0, "utf8"));

function act(a) {
  return [a.kind, a.arg, a.ret, a.noble];
}

function snap(s) {
  return {
    bank: s.bank,
    decks: [s.decks[1], s.decks[2], s.decks[3]],
    board: [s.board[1], s.board[2], s.board[3]],
    nobles: s.nobles,
    players: s.players.map((p) => [p.tokens, p.bonus, p.points, p.reserved.map((r) => [r[0], r[1]]), p.bought, p.nobles]),
    turn: s.turn,
    passes: s.passes,
    done: s.done,
  };
}

let out;
if (input.cmd === "cards") {
  out = { cards: E.CARDS.map((c) => [c.level, c.color, c.points, c.cost]), nobles: E.NOBLES.map((n) => [n.need, n.points]) };
} else if (input.cmd === "replay") {
  // Python が選んだ手の番号の列を、同じ最初の局面から指す。毎手の合法手・評価・指したあとの局面を返す
  out = input.games.map((g) => {
    const s = E.fromJSON(g.start);
    const steps = [];
    for (const k of g.picks) {
      const legal = E.legalActions(s);
      const reduced = E.reduceActions(legal);
      steps.push({ legal: legal.map(act), reduced: reduced.map(act), eval: [E.evaluate(s, 0), E.evaluate(s, 1)] });
      if (k >= legal.length) break; // 合法手が食い違った（Python 側の比較で分かる）
      E.apply(s, legal[k]);
      steps[steps.length - 1].after = JSON.parse(JSON.stringify(snap(s)));
    }
    return { steps, result: E.result(s) };
  });
} else if (input.cmd === "match") {
  // JS の AI 同士を先後入れ替えで対局させる（強さの確かめ）
  const res = [];
  for (const seed of input.seeds) {
    for (const first of [0, 1]) {
      const s = E.newGame(seed);
      const names = first === 0 ? [input.a, input.b] : [input.b, input.a];
      let k = 0;
      while (!s.done) {
        const who = names[E.current(s)];
        const a = E.aiAct(s, who, seed * 1000 + k++).best;
        E.apply(s, a);
      }
      const r = E.result(s);
      const aSeat = first === 0 ? 0 : 1;
      res.push(r < 0 ? 0.5 : r === aSeat ? 1 : 0);
    }
  }
  out = res;
} else if (input.cmd === "newgame") {
  out = input.seeds.map((seed) => {
    const s = E.newGame(seed);
    const legal = E.legalActions(s);
    return { snap: snap(s), nlegal: legal.length };
  });
}
process.stdout.write(JSON.stringify(out));
