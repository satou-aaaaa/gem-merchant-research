// 宝石商の工房: ルールエンジンと AI（ブラウザ・Web Worker・node で同じものを使う）。
// src/gem_merchant/game.py（正解版）・cards.py・agents.py をそのまま写したもの。
// 合法手の並び順・指したあとの局面・評価の値が Python と同じかを tests/test_play_js.py が確かめる。
// ルールや評価の式を Python 側で変えたら、ここも同じように直す。
(function (root) {
  "use strict";

  // --- 決まりの数（rules.py） ---
  const N = 5; // 宝石の色の数
  const GOLD = 5; // チップの配列の6番目が金
  const GEMS_PER_COLOR = 4;
  const GOLD_TOKENS = 5;
  const FACE_UP = 4;
  const NOBLES_IN_GAME = 3;
  const MAX_RESERVED = 3;
  const MAX_TOKENS = 10;
  const TAKE_TWO_MIN_PILE = 4;
  const WIN_POINTS = 15;
  const MAX_TURNS = 200;
  const NO_RET = [0, 0, 0, 0, 0, 0];

  // --- 自作のカード90枚と貴族10枚（cards.py） ---
  const PATTERNS = {
    1: [
      [0, { 1: 1, 2: 1, 3: 1, 4: 1 }],
      [0, { 1: 1, 2: 2, 3: 1, 4: 1 }],
      [0, { 2: 2, 4: 2 }],
      [0, { 1: 2, 3: 1 }],
      [0, { 3: 3 }],
      [0, { 0: 1, 1: 1, 4: 3 }],
      [0, { 1: 1, 2: 2, 3: 2 }],
      [1, { 2: 4 }],
    ],
    2: [
      [1, { 1: 3, 3: 2, 4: 2 }],
      [1, { 0: 2, 2: 3, 4: 3 }],
      [2, { 1: 4, 2: 2, 3: 1 }],
      [2, { 3: 5 }],
      [2, { 0: 3, 4: 5 }],
      [3, { 0: 6 }],
    ],
    3: [
      [3, { 1: 3, 2: 3, 3: 5, 4: 3 }],
      [4, { 4: 7 }],
      [4, { 0: 3, 3: 6, 4: 3 }],
      [5, { 0: 3, 4: 7 }],
    ],
  };

  function makeCards() {
    const cards = [];
    for (const level of [1, 2, 3]) {
      for (let color = 0; color < N; color++) {
        for (const [points, shape] of PATTERNS[level]) {
          const cost = [0, 0, 0, 0, 0];
          for (const step in shape) cost[(color + Number(step)) % N] += shape[step];
          cards.push({ id: cards.length, level, color, points, cost });
        }
      }
    }
    return cards;
  }

  function makeNobles() {
    const nobles = [];
    for (let c = 0; c < N; c++) {
      const need = [0, 0, 0, 0, 0];
      need[c] = need[(c + 2) % N] = 4;
      nobles.push({ id: nobles.length, need, points: 3 });
    }
    for (let c = 0; c < N; c++) {
      const need = [0, 0, 0, 0, 0];
      for (const step of [0, 1, 3]) need[(c + step) % N] = 3;
      nobles.push({ id: nobles.length, need, points: 3 });
    }
    return nobles;
  }

  const CARDS = makeCards();
  const NOBLES = makeNobles();

  // --- 乱数（種から同じ列を出す。Python の random とは違う列） ---
  function makeRng(seed) {
    let a = seed >>> 0 || 0x9e3779b9;
    const next = () => {
      // mulberry32
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    return {
      random: next,
      int: (n) => Math.floor(next() * n),
      shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
          const j = Math.floor(next() * (i + 1));
          [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
      },
    };
  }

  // --- 局面 ---
  function newPlayer() {
    return { tokens: [0, 0, 0, 0, 0, 0], bonus: [0, 0, 0, 0, 0], points: 0, reserved: [], bought: 0, nobles: [] };
  }

  function newGame(seed) {
    const rng = makeRng(seed);
    const decks = {};
    const board = {};
    for (const level of [1, 2, 3]) {
      const ids = rng.shuffle(CARDS.filter((c) => c.level === level).map((c) => c.id));
      board[level] = [];
      for (let i = 0; i < FACE_UP; i++) board[level].push(ids.pop());
      decks[level] = ids;
    }
    const nobles = rng.shuffle(NOBLES.map((n) => n.id)).slice(0, NOBLES_IN_GAME);
    const bank = [GEMS_PER_COLOR, GEMS_PER_COLOR, GEMS_PER_COLOR, GEMS_PER_COLOR, GEMS_PER_COLOR, GOLD_TOKENS];
    return { bank, decks, board, nobles, players: [newPlayer(), newPlayer()], turn: 0, passes: 0, done: false };
  }

  // Python の局面（JSON）からも作れる（照合用）
  function fromJSON(o) {
    return clone({
      bank: o.bank,
      decks: { 1: o.decks[1] || o.decks["1"], 2: o.decks[2] || o.decks["2"], 3: o.decks[3] || o.decks["3"] },
      board: { 1: o.board[1] || o.board["1"], 2: o.board[2] || o.board["2"], 3: o.board[3] || o.board["3"] },
      nobles: o.nobles,
      players: o.players.map((p) => ({
        tokens: p.tokens,
        bonus: p.bonus,
        points: p.points,
        reserved: p.reserved.map((r) => [r[0], !!r[1]]),
        bought: p.bought,
        nobles: p.nobles,
      })),
      turn: o.turn,
      passes: o.passes,
      done: o.done,
    });
  }

  function clone(s) {
    return {
      bank: s.bank.slice(),
      decks: { 1: s.decks[1].slice(), 2: s.decks[2].slice(), 3: s.decks[3].slice() },
      board: { 1: s.board[1].slice(), 2: s.board[2].slice(), 3: s.board[3].slice() },
      nobles: s.nobles.slice(),
      players: s.players.map((p) => ({
        tokens: p.tokens.slice(),
        bonus: p.bonus.slice(),
        points: p.points,
        reserved: p.reserved.map((r) => [r[0], r[1]]),
        bought: p.bought,
        nobles: p.nobles.slice(),
      })),
      turn: s.turn,
      passes: s.passes,
      done: s.done,
    };
  }

  const current = (s) => s.turn % 2;

  // --- 手 ---
  // { kind: "take3"|"take2"|"reserve"|"buy"|"pass", arg, ret: [6], noble }
  // take3: 色の配列 / take2: 色 / reserve: [レベル, 位置（-1 は山札）] / buy: ["board", レベル, 位置] か ["reserved", 番号]

  function effectiveCost(p, cid) {
    const cost = CARDS[cid].cost;
    const out = [];
    for (let c = 0; c < N; c++) out.push(Math.max(0, cost[c] - p.bonus[c]));
    return out;
  }

  function payment(p, cid) {
    const need = effectiveCost(p, cid);
    const pay = [];
    let short = 0;
    for (let c = 0; c < N; c++) {
      const x = Math.min(need[c], p.tokens[c]);
      pay.push(x);
      short += need[c] - x;
    }
    if (short > p.tokens[GOLD]) return null;
    pay.push(short);
    return pay;
  }

  function combinations(arr, k) {
    const out = [];
    const rec = (start, cur) => {
      if (cur.length === k) {
        out.push(cur.slice());
        return;
      }
      for (let i = start; i < arr.length; i++) {
        cur.push(arr[i]);
        rec(i + 1, cur);
        cur.pop();
      }
    };
    rec(0, []);
    return out;
  }

  // itertools.product の順（最後の色がいちばん速く回る）で、合計が excess になる戻し方
  function returns(tokens, excess) {
    if (excess <= 0) return [NO_RET];
    const out = [];
    const cur = [0, 0, 0, 0, 0, 0];
    const rec = (i, sum) => {
      if (i === 6) {
        if (sum === excess) out.push(cur.slice());
        return;
      }
      const lim = Math.min(tokens[i], excess);
      for (let x = 0; x <= lim; x++) {
        cur[i] = x;
        rec(i + 1, sum + x);
      }
      cur[i] = 0;
    };
    rec(0, 0);
    return out;
  }

  function eligibleNobles(s, bonus) {
    return s.nobles.filter((n) => NOBLES[n].need.every((x, c) => bonus[c] >= x));
  }

  function buyCardId(s, a) {
    if (a.arg[0] === "board") return s.board[a.arg[1]][a.arg[2]];
    return s.players[current(s)].reserved[a.arg[1]][0];
  }

  function mainActions(s) {
    const p = s.players[current(s)];
    const bank = s.bank;
    const acts = [];
    const avail = [];
    for (let c = 0; c < N; c++) if (bank[c] > 0) avail.push(c);
    if (avail.length >= 3) {
      for (const combo of combinations(avail, 3)) acts.push({ kind: "take3", arg: combo });
    } else {
      for (let k = 1; k <= avail.length; k++)
        for (const combo of combinations(avail, k)) acts.push({ kind: "take3", arg: combo });
    }
    for (let c = 0; c < N; c++) if (bank[c] >= TAKE_TWO_MIN_PILE) acts.push({ kind: "take2", arg: c });
    if (p.reserved.length < MAX_RESERVED) {
      for (const level of [1, 2, 3]) {
        s.board[level].forEach((cid, i) => {
          if (cid >= 0) acts.push({ kind: "reserve", arg: [level, i] });
        });
        if (s.decks[level].length) acts.push({ kind: "reserve", arg: [level, -1] });
      }
    }
    for (const level of [1, 2, 3]) {
      s.board[level].forEach((cid, i) => {
        if (cid >= 0 && payment(p, cid) !== null) acts.push({ kind: "buy", arg: ["board", level, i] });
      });
    }
    p.reserved.forEach(([cid], i) => {
      if (payment(p, cid) !== null) acts.push({ kind: "buy", arg: ["reserved", i] });
    });
    return acts;
  }

  function afterMain(s, a) {
    const p = s.players[current(s)];
    const tokens = p.tokens.slice();
    const bonus = p.bonus.slice();
    if (a.kind === "take3") for (const c of a.arg) tokens[c] += 1;
    else if (a.kind === "take2") tokens[a.arg] += 2;
    else if (a.kind === "reserve") {
      if (s.bank[GOLD] > 0) tokens[GOLD] += 1;
    } else if (a.kind === "buy") {
      const cid = buyCardId(s, a);
      const pay = payment(p, cid);
      for (let c = 0; c < 6; c++) tokens[c] -= pay[c];
      bonus[CARDS[cid].color] += 1;
    }
    return [tokens, bonus];
  }

  function legalActions(s) {
    if (s.done) return [];
    const out = [];
    for (const a of mainActions(s)) {
      const [tokens, bonus] = afterMain(s, a);
      const el = eligibleNobles(s, bonus);
      const nobles = el.length ? el : [-1];
      const total = tokens.reduce((x, y) => x + y, 0);
      for (const ret of returns(tokens, total - MAX_TOKENS))
        for (const n of nobles) out.push({ kind: a.kind, arg: a.arg, ret, noble: n });
    }
    return out.length ? out : [{ kind: "pass", arg: null, ret: NO_RET, noble: -1 }];
  }

  function refill(s, level, slot) {
    const deck = s.decks[level];
    s.board[level][slot] = deck.length ? deck.pop() : -1;
  }

  // 手を指す（s を書き換える）。合法かは確かめない
  function apply(s, a) {
    const p = s.players[current(s)];
    const bank = s.bank;
    if (a.kind === "take3") {
      for (const c of a.arg) {
        bank[c] -= 1;
        p.tokens[c] += 1;
      }
    } else if (a.kind === "take2") {
      bank[a.arg] -= 2;
      p.tokens[a.arg] += 2;
    } else if (a.kind === "reserve") {
      const [level, slot] = a.arg;
      if (slot < 0) p.reserved.push([s.decks[level].pop(), true]);
      else {
        p.reserved.push([s.board[level][slot], false]);
        refill(s, level, slot);
      }
      if (bank[GOLD] > 0) {
        bank[GOLD] -= 1;
        p.tokens[GOLD] += 1;
      }
    } else if (a.kind === "buy") {
      const cid = buyCardId(s, a);
      const pay = payment(p, cid);
      for (let c = 0; c < 6; c++) {
        p.tokens[c] -= pay[c];
        bank[c] += pay[c];
      }
      if (a.arg[0] === "board") refill(s, a.arg[1], a.arg[2]);
      else p.reserved.splice(a.arg[1], 1);
      const card = CARDS[cid];
      p.bonus[card.color] += 1;
      p.points += card.points;
      p.bought += 1;
    }
    for (let c = 0; c < 6; c++) {
      p.tokens[c] -= a.ret[c];
      bank[c] += a.ret[c];
    }
    if (a.noble >= 0) {
      s.nobles.splice(s.nobles.indexOf(a.noble), 1);
      p.nobles.push(a.noble);
      p.points += NOBLES[a.noble].points;
    }
    s.passes = a.kind === "pass" ? s.passes + 1 : 0;
    const lastInRound = current(s) === 1;
    s.turn += 1;
    if (s.passes >= 2 || s.turn >= MAX_TURNS || (lastInRound && s.players.some((q) => q.points >= WIN_POINTS)))
      s.done = true;
  }

  // 勝った人の番号。引き分けは -1。点が多い人、同点なら買ったカードが少ない人
  function result(s) {
    const [a, b] = s.players;
    if (a.points !== b.points) return a.points > b.points ? 0 : 1;
    if (a.bought !== b.bought) return a.bought < b.bought ? 0 : 1;
    return -1;
  }

  // --- 手作りの評価（agents.py） ---
  function shortfall(p, cid) {
    const cost = CARDS[cid].cost;
    let short = 0;
    for (let c = 0; c < N; c++) short += Math.max(0, cost[c] - p.bonus[c] - p.tokens[c]);
    return Math.max(0, short - p.tokens[GOLD]);
  }

  function playerValue(s, i) {
    const p = s.players[i];
    let v = p.points;
    let bon = 0;
    let tok = 0;
    for (let c = 0; c < N; c++) {
      bon += p.bonus[c];
      tok += p.tokens[c];
    }
    v += 0.8 * bon;
    v += 0.1 * tok + 0.2 * p.tokens[GOLD];
    for (const n of s.nobles) {
      let need = 0;
      for (let c = 0; c < N; c++) need += Math.max(0, NOBLES[n].need[c] - p.bonus[c]);
      v += 3.0 / Math.pow(1 + need, 1.5);
    }
    const near = [];
    for (const level of [1, 2, 3])
      for (const cid of s.board[level]) if (cid >= 0) near.push((CARDS[cid].points + 0.8) / (1 + shortfall(p, cid)));
    for (const [cid] of p.reserved) near.push((CARDS[cid].points + 0.8) / (1 + shortfall(p, cid)));
    near.sort((x, y) => y - x);
    v += 0.5 * near.slice(0, 3).reduce((x, y) => x + y, 0);
    return v;
  }

  // i 番の人から見た勝ちやすさ（0〜1）
  function evaluate(s, i) {
    if (s.done) {
      const r = result(s);
      return r < 0 ? 0.5 : r === i ? 1 : 0;
    }
    const d = playerValue(s, i) - playerValue(s, 1 - i);
    return 1 / (1 + Math.exp(-d / 4));
  }

  // --- 手を減らす: 10枚を超えたときの戻し方は1通り（agents.reduce_actions） ---
  function mainKey(a) {
    return a.kind + "|" + JSON.stringify(a.arg) + "|" + a.noble;
  }

  function retBetter(a, b) {
    // (金を戻す枚数, 多く持つ色から戻す) が小さいほど良い。Python の tuple 比較と同じ
    if (a.ret[GOLD] !== b.ret[GOLD]) return a.ret[GOLD] < b.ret[GOLD];
    for (let c = 0; c < N; c++) if (a.ret[c] !== b.ret[c]) return -a.ret[c] < -b.ret[c];
    return false;
  }

  function reduceActions(acts) {
    const best = new Map();
    for (const a of acts) {
      const k = mainKey(a);
      const cur = best.get(k);
      if (cur === undefined || retBetter(a, cur)) best.set(k, a);
    }
    return Array.from(best.values());
  }

  function actionKey(a) {
    return mainKey(a) + "|" + a.ret.join(",");
  }

  // --- AI ---
  function greedyAct(s, rng) {
    const me = current(s);
    const acts = rng.shuffle(reduceActions(legalActions(s)));
    let best = acts[0];
    let bestV = -1;
    for (const a of acts) {
      const t = clone(s);
      apply(t, a);
      let v = evaluate(t, me);
      if (a.kind === "buy") v += 1e-6;
      if (v > bestV) {
        best = a;
        bestV = v;
      }
    }
    return best;
  }

  // viewer に見えない札（山札の中身と順・相手の伏せ予約）を仮に決める
  function determinize(s, viewer, rng) {
    const t = clone(s);
    for (const level of [1, 2, 3]) {
      const pool = t.decks[level].slice();
      const hidden = [];
      t.players.forEach((p, j) => {
        if (j === viewer) return;
        p.reserved.forEach(([cid, blind], k) => {
          if (blind && CARDS[cid].level === level) {
            pool.push(cid);
            hidden.push([j, k]);
          }
        });
      });
      rng.shuffle(pool);
      for (const [j, k] of hidden) t.players[j].reserved[k] = [pool.pop(), true];
      t.decks[level] = pool;
    }
    return t;
  }

  // 情報集合 MCTS（agents.MCTSAgent と同じ考え方）。stats に根の手ごとの回数と勝ちやすさを返す
  function mctsSearch(s, iterations, rng, opts) {
    const c = (opts && opts.c) || 0.7;
    const depth = (opts && opts.depth) || 6;
    const rootActs = reduceActions(legalActions(s));
    const me = current(s);
    const newNode = (player) => ({ children: new Map(), n: 0, w: 0, avail: 0, player });
    const root = newNode(1 - me);
    if (rootActs.length > 1) {
      for (let it = 0; it < iterations; it++) {
        const t = determinize(s, me, rng);
        let node = root;
        const path = [root];
        let d = 0;
        while (!t.done && d < depth) {
          const acts = reduceActions(legalActions(t));
          const untried = [];
          let bestA = null;
          let bestU = -Infinity;
          for (const a of acts) {
            const k = actionKey(a);
            const ch = node.children.get(k);
            if (ch) ch.avail += 1;
            else untried.push([k, a]);
          }
          const mover = current(t);
          if (untried.length) {
            const [k, a] = untried[rng.int(untried.length)];
            const child = newNode(mover);
            child.avail = 1;
            node.children.set(k, child);
            apply(t, a);
            path.push(child);
            break;
          }
          for (const a of acts) {
            const ch = node.children.get(actionKey(a));
            const u = ch.w / ch.n + c * Math.sqrt(Math.log(Math.max(ch.avail, 1)) / ch.n);
            if (u > bestU) {
              bestU = u;
              bestA = a;
            }
          }
          node = node.children.get(actionKey(bestA));
          apply(t, bestA);
          path.push(node);
          d += 1;
        }
        const vMe = evaluate(t, me);
        for (const nd of path) {
          nd.n += 1;
          nd.w += nd.player === me ? vMe : 1 - vMe;
        }
      }
    }
    const stats = rootActs.map((a) => {
      const ch = root.children.get(actionKey(a));
      return { action: a, n: ch ? ch.n : 0, value: ch && ch.n ? ch.w / ch.n : null };
    });
    stats.sort((x, y) => y.n - x.n);
    return { best: stats[0].action, stats, value: root.n ? 1 - root.w / root.n : evaluate(s, me) };
  }

  // 強さの段: 名前 → 手を選ぶ関数
  const LEVELS = {
    // iterations 0 は greedy（1手先だけを見る）。強い・最強は PC で約1秒・約4秒（スマホはその2〜3倍）
    easy: { iterations: 0 },
    normal: { iterations: 600 },
    strong: { iterations: 5000 },
    max: { iterations: 20000 },
  };

  function aiAct(s, level, seed) {
    const rng = makeRng(seed);
    const lv = LEVELS[level] || LEVELS.normal;
    if (!lv.iterations) return { best: greedyAct(s, rng), stats: null };
    return mctsSearch(s, lv.iterations, rng);
  }

  function sameAction(a, b) {
    return actionKey(a) === actionKey(b);
  }

  const api = {
    N,
    GOLD,
    MAX_TOKENS,
    MAX_RESERVED,
    WIN_POINTS,
    CARDS,
    NOBLES,
    LEVELS,
    makeRng,
    newGame,
    fromJSON,
    clone,
    current,
    payment,
    effectiveCost,
    legalActions,
    apply,
    result,
    playerValue,
    evaluate,
    reduceActions,
    greedyAct,
    determinize,
    mctsSearch,
    aiAct,
    actionKey,
    sameAction,
    eligibleNobles,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GemEngine = api;
})(typeof self !== "undefined" ? self : this);
