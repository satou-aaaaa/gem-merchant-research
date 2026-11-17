// 宝石商の工房: 局面を描く部品（クイズ・コツ集で使う。見た目は gem.css）。
// 対戦ページ（play.html）は操作つきの描き方を中に持つ。手の言葉（describe）は同じ言い方にそろえる。
(function (root) {
  "use strict";
  const E = root.GemEngine;
  const COLOR_NAMES = ["白", "青", "緑", "赤", "黒", "金"];

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function gemEl(c, text) {
    return el("span", "gem c" + c, text === undefined ? COLOR_NAMES[c] : text);
  }

  function cardName(cid) {
    const c = E.CARDS[cid];
    return `${COLOR_NAMES[c.color]}のカード（Lv${c.level}・${c.points}点）`;
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
    if (opts && opts.player && E.payment(opts.player, cid) !== null) b.classList.add("can");
    if (opts && opts.blind) b.appendChild(el("span", "blindmark", "伏せ"));
    b.setAttribute("role", "img");
    b.setAttribute("aria-label", cardName(cid) + "、値段 " + c.cost.map((x, k) => (x ? COLOR_NAMES[k] + x : "")).filter(Boolean).join("・"));
    return b;
  }

  function nobleEl(n) {
    const d = el("div", "noble");
    d.appendChild(el("b", "", "3"));
    const need = el("span", "need");
    E.NOBLES[n].need.forEach((x, c) => {
      if (!x) return;
      const sp = el("span", "c" + c, String(x));
      sp.title = `${COLOR_NAMES[c]}の割引${x}枚`;
      need.appendChild(sp);
    });
    d.appendChild(need);
    d.setAttribute("aria-label", "貴族 3点、条件 " + E.NOBLES[n].need.map((x, c) => (x ? COLOR_NAMES[c] + x : "")).filter(Boolean).join("・"));
    return d;
  }

  function playerEl(s, i, name, cls) {
    const p = s.players[i];
    const d = el("div", "pl " + cls);
    const top = el("div", "top");
    top.appendChild(el("span", "", name));
    top.appendChild(el("b", "", String(p.points)));
    top.appendChild(el("small", "", "点" + (i === 0 ? "・先手" : "・後手")));
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
    d.appendChild(el("div", "meta", `チップ${tok}/10・カード${p.bought}・貴族${p.nobles.length}`));
    if (p.reserved.length) {
      const res = el("div", "res");
      p.reserved.forEach(([cid, blind]) => res.appendChild(cardEl(cid, { player: p, blind })));
      d.appendChild(el("div", "meta", "予約札:"));
      d.appendChild(res);
    }
    return d;
  }

  // 局面を読むだけの形で描く（me の人を「あなた」として上に）
  function renderBoard(box, s, me) {
    box.innerHTML = "";
    const pls = el("div", "players");
    pls.appendChild(playerEl(s, me, "あなた", "me" + (E.current(s) === me ? " turn" : "")));
    pls.appendChild(playerEl(s, 1 - me, "相手", "ai" + (E.current(s) !== me ? " turn" : "")));
    box.appendChild(pls);
    box.appendChild(el("div", "note", "色ごとに、上の数＝手持ちのチップ、下の「+数」＝カードの割引。相手の予約札も見えています。"));
    const nb = el("div", "nobles");
    if (!s.nobles.length) nb.appendChild(el("span", "note", "貴族はもう残っていない"));
    s.nobles.forEach((n) => nb.appendChild(nobleEl(n)));
    box.appendChild(nb);
    for (const level of [3, 2, 1]) {
      const row = el("div", "lvl");
      const deck = el("div", "deck");
      deck.appendChild(el("span", "", "Lv" + level));
      deck.appendChild(el("b", "", String(s.decks[level].length)));
      deck.setAttribute("role", "img");
      deck.setAttribute("aria-label", `レベル${level}の山札 ${s.decks[level].length}枚`);
      row.appendChild(deck);
      s.board[level].forEach((cid) => row.appendChild(cardEl(cid, { player: s.players[me] })));
      box.appendChild(row);
    }
    const bank = el("div", "bank");
    bank.appendChild(el("span", "note", "場の宝石:"));
    for (let c = 0; c < 6; c++) {
      const g = el("span", "bankgem");
      g.appendChild(gemEl(c));
      g.appendChild(el("small", "", `${s.bank[c]}枚`));
      bank.appendChild(g);
    }
    box.appendChild(bank);
  }

  // 手を言葉にする（s は指す前の局面）。play.html の describe と同じ言い方
  function describe(s, a) {
    let t;
    if (a.kind === "take3") t = "宝石を取る: " + a.arg.map((c) => COLOR_NAMES[c]).join("・");
    else if (a.kind === "take2") t = `宝石を取る: ${COLOR_NAMES[a.arg]}2つ`;
    else if (a.kind === "reserve") {
      const [lv, i] = a.arg;
      t = i < 0 ? `Lv${lv}の山札から伏せて予約` : `${cardName(s.board[lv][i])}を予約`;
    } else if (a.kind === "buy") {
      const cid = a.arg[0] === "board" ? s.board[a.arg[1]][a.arg[2]] : s.players[E.current(s)].reserved[a.arg[1]][0];
      t = `${cardName(cid)}を買う` + (a.arg[0] === "reserved" ? "（予約札から）" : "");
    } else t = "パス（指せる手がない）";
    const r = a.ret.reduce((x, y) => x + y, 0);
    if (r) t += "、" + a.ret.map((n, c) => (n ? COLOR_NAMES[c] + n : "")).filter(Boolean).join("・") + "を戻す";
    if (a.noble >= 0) t += "、貴族が来る（+3点）";
    return t;
  }

  root.GemUI = { COLOR_NAMES, gemEl, cardEl, nobleEl, playerEl, renderBoard, describe, cardName };
})(typeof self !== "undefined" ? self : this);
