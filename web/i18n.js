// 言葉の切り替え（日本語・英語）。ページの JS の文は T("日本語の文", 値…) で書き、英語のページでは対訳表から引く。
// 対訳表は web/i18n/en.json（scripts/build_pages.py が docs/i18n_en.js にして英語のページで先に読む）。
// 文の中の値は {0} {1} … で書く（英語で語順が変わってもよいように）。
// 言語は、選んだことがあればそれ、なければブラウザの言語で決め、合わないページなら移る。
(function (root) {
  "use strict";
  const lang = (root.document && document.documentElement.lang) || "ja";
  const dict = lang === "en" ? root.GEM_EN || {} : null;
  function T(key) {
    let s = dict && Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : key;
    for (let i = 1; i < arguments.length; i++) s = s.split("{" + (i - 1) + "}").join(String(arguments[i]));
    return s;
  }
  root.T = T;
  // 宝石の丸の中の字。日本語は色の名前（1文字）、英語は名前が長くて丸からはみ出すので短い印にする
  root.GEM_MARK = lang === "en" ? ["W", "Bu", "G", "R", "Bk", "Au"] : null;
  root.GEM_LANG = lang;
  // 資料（js・css）の置き場所。英語のページは docs/en/ にあるので一つ上
  root.GEM_BASE = (root.document && document.documentElement.dataset.base) || "";

  if (!root.document) return;
  const KEY = "gem-lang";
  let chosen = null;
  try {
    chosen = localStorage.getItem(KEY);
  } catch (e) {
    chosen = null;
  }
  // 切り替えリンクを押したら、その言語を覚える
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[data-lang]");
    if (!a) return;
    try {
      localStorage.setItem(KEY, a.dataset.lang);
    } catch (err) {
      /* 覚えられなくても移れる */
    }
  });
  const want = chosen || ((navigator.language || "ja").toLowerCase().startsWith("ja") ? "ja" : "en");
  if (want !== lang) {
    const page = location.pathname.split("/").pop() || "index.html";
    const to = lang === "ja" ? "en/" + page : "../" + page;
    location.replace(to + location.search + location.hash);
  }
})(typeof self !== "undefined" ? self : this);
