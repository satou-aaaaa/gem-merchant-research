// 宝石商の工房: 局面を描く部品（クイズ・コツ集で使う。見た目は gem.css）。
// 対戦ページ（play.html）は操作つきの描き方を中に持つ。手の言葉（describe）は同じ言い方にそろえる。
(function (root) {
  "use strict";
  const E = root.GemEngine;
  const COLOR_NAMES = [T("白"), T("青"), T("緑"), T("赤"), T("黒"), T("金")];

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function gemEl(c, text) {
    const g = el("span", "gem c" + c, text === undefined ? (root.GEM_MARK ? root.GEM_MARK[c] : COLOR_NAMES[c]) : text);
    if (root.GEM_MARK) g.title = COLOR_NAMES[c];
    return g;
  }

  function cardName(cid) {
    const c = E.CARDS[cid];
    return T("{0}のカード（Lv{1}・{2}点）", COLOR_NAMES[c.color], c.level, c.points);
  }

  function cardEl(cid, opts) {
    const b = el("div", "card");
    if (cid < 0) {
      b.classList.add("empty");
      return b;
    }
    const c = E.CARDS[cid];
    const band = el("div", "band c" + c.color);
    band.appendChild(el("b", "", c.points ? String(c.points) : ""));
    band.appendChild(gemEl(c.color));
    b.appendChild(band);
    const cost = el("div", "cost");
    c.cost.forEach((x, k) => {
      if (!x) return;
      const sp = el("span");
      sp.appendChild(gemEl(k, ""));
      sp.appendChild(document.createTextNode("×" + x));
      cost.appendChild(sp);
    });
    b.appendChild(cost);
    if (opts && opts.player && E.payment(opts.player, cid) !== null) {
      b.classList.add("can");
      b.appendChild(el("span", "canmark", T("買える")));
    }
    if (opts && opts.blind) b.appendChild(el("span", "blindmark", T("伏せ")));
    b.setAttribute("role", "img");
    b.setAttribute("aria-label", cardName(cid) + T("、値段 ") + c.cost.map((x, k) => (x ? COLOR_NAMES[k] + x : "")).filter(Boolean).join(T("・")));
    return b;
  }

  function nobleEl(n) {
    const d = el("div", "noble");
    d.appendChild(el("b", "", "3"));
    const need = el("span", "need");
    E.NOBLES[n].need.forEach((x, c) => {
      if (!x) return;
      const sp = el("span", "c" + c, String(x));
      sp.title = T("{0}の割引{1}枚", COLOR_NAMES[c], x);
      need.appendChild(sp);
    });
    d.appendChild(need);
    d.setAttribute("aria-label", T("貴族 3点、条件 ") + E.NOBLES[n].need.map((x, c) => (x ? COLOR_NAMES[c] + x : "")).filter(Boolean).join(T("・")));
    return d;
  }

  function playerEl(s, i, name, cls) {
    const p = s.players[i];
    const d = el("div", "pl " + cls);
    const top = el("div", "top");
    top.appendChild(el("span", "", name));
    top.appendChild(el("b", "", String(p.points)));
    top.appendChild(el("small", "", T("点") + (i === 0 ? T("・先手") : T("・後手"))));
    d.appendChild(top);
    const inv = el("div", "inv");
    for (let c = 0; c < 6; c++) {
      const cell = el("div");
      cell.appendChild(gemEl(c));
      const n = el("span", "n");
      n.appendChild(el("b", "", String(p.tokens[c])));
      if (c < 5) n.appendChild(el("i", "", "+" + p.bonus[c]));
      cell.appendChild(n);
      inv.appendChild(cell);
    }
    d.appendChild(inv);
    const tok = p.tokens.reduce((x, y) => x + y, 0);
    d.appendChild(el("div", "meta", T("チップ{0}/10・カード{1}・貴族{2}", tok, p.bought, p.nobles.length)));
    if (p.reserved.length) {
      const res = el("div", "res");
      p.reserved.forEach(([cid, blind]) => res.appendChild(cardEl(cid, { player: p, blind })));
      d.appendChild(el("div", "meta", T("予約札:")));
      d.appendChild(res);
    }
    return d;
  }

  // 局面を読むだけの形で描く（me の人を「あなた」として上に）
  function renderBoard(box, s, me) {
    box.innerHTML = "";
    const pls = el("div", "players");
    pls.appendChild(playerEl(s, me, T("あなた"), "me" + (E.current(s) === me ? " turn" : "")));
    pls.appendChild(playerEl(s, 1 - me, T("相手"), "ai" + (E.current(s) !== me ? " turn" : "")));
    box.appendChild(pls);
    box.appendChild(el("div", "note", T("色ごとに、上の数＝手持ちのチップ、下の「+数」＝カードの割引。相手の予約札も見えています。")));
    const nb = el("div", "nobles");
    if (!s.nobles.length) nb.appendChild(el("span", "note", T("貴族はもう残っていない")));
    s.nobles.forEach((n) => nb.appendChild(nobleEl(n)));
    box.appendChild(nb);
    for (const level of [3, 2, 1]) {
      const row = el("div", "lvl");
      const deck = el("div", "deck");
      deck.appendChild(el("span", "", "Lv" + level));
      deck.appendChild(el("b", "", String(s.decks[level].length)));
      deck.setAttribute("role", "img");
      deck.setAttribute("aria-label", T("レベル{0}の山札 {1}枚", level, s.decks[level].length));
      row.appendChild(deck);
      s.board[level].forEach((cid) => row.appendChild(cardEl(cid, { player: s.players[me] })));
      box.appendChild(row);
    }
    const bank = el("div", "bank");
    bank.appendChild(el("span", "note", T("場の宝石:")));
    for (let c = 0; c < 6; c++) {
      const g = el("span", "bankgem");
      g.appendChild(gemEl(c));
      g.appendChild(el("small", "", T("{0}枚", s.bank[c])));
      bank.appendChild(g);
    }
    box.appendChild(bank);
  }

  // 手を言葉にする（s は指す前の局面）。play.html の describe と同じ言い方
  function describe(s, a) {
    let t;
    if (a.kind === "take3") t = T("宝石を取る: ") + a.arg.map((c) => COLOR_NAMES[c]).join(T("・"));
    else if (a.kind === "take2") t = T("宝石を取る: {0}2つ", COLOR_NAMES[a.arg]);
    else if (a.kind === "reserve") {
      const [lv, i] = a.arg;
      t = i < 0 ? T("Lv{0}の山札から伏せて予約", lv) : T("{0}を予約", cardName(s.board[lv][i]));
    } else if (a.kind === "buy") {
      const cid = a.arg[0] === "board" ? s.board[a.arg[1]][a.arg[2]] : s.players[E.current(s)].reserved[a.arg[1]][0];
      t = T("{0}を買う", cardName(cid)) + (a.arg[0] === "reserved" ? T("（予約札から）") : "");
    } else t = T("パス（指せる手がない）");
    const r = a.ret.reduce((x, y) => x + y, 0);
    if (r) t += T("、") + a.ret.map((n, c) => (n ? COLOR_NAMES[c] + n : "")).filter(Boolean).join(T("・")) + T("を戻す");
    if (a.noble >= 0) t += T("、貴族が来る（+3点）");
    return t;
  }

  root.GemUI = { COLOR_NAMES, gemEl, cardEl, nobleEl, playerEl, renderBoard, describe, cardName };
})(typeof self !== "undefined" ? self : this);
