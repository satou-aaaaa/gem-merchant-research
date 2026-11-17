// 公開ページ（docs/*.html）の UI 点検。スマホ幅と PC 幅で開き、機械で分かる問題を探す。
//
//   node scripts/ui_check.mjs               # 点検だけ（問題があれば終了コード 1）
//   node scripts/ui_check.mjs --shots DIR   # 各ページ・各幅のスクリーンショットも DIR に保存
//
// Playwright（npm の playwright）と Chromium が要る。クラウドセッションには入っている。
// CI は .github/workflows/test.yml の ui ジョブ。目で見る点検の手順は .claude/skills/ui-check/SKILL.md。
//
// 見ること（carcassonne-research の scripts/ui_check.mjs と同じ考え方）:
//   - コンソールのエラー・読み込み失敗がない
//   - 横方向にはみ出さない（ページ全体が横にスクロールしない）
//   - ボタン・入力欄・ナビのリンクは 24×24px 以上（WCAG 2.2 の 2.5.8）。スマホ幅では高さ 44px 以上（Apple HIG の目安）
//     （対戦ページの場のカード・宝石・予約札は 44px より大きいので同じ基準で見る）
//   - ボタン・入力欄に名前（文字・aria-label・label）がある
//   - 文字は 11px 以上、viewport の指定がある
//   - 対戦ページは「新しい対局」から宝石を取り、AI が1手返すまで動かす。カードを押すと選び方が出る。ヒントが出る
//   - クイズは盤が描かれ、選択肢を押すと答えが出て、次の問題へ進める
//   - 英語のページに日本語が残っていない（切り替えリンクの「日本語」は除く）。日本語のページで英語を選ぶと英語のページへ移る

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DOCS = path.join(ROOT, "docs");
const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = await import("playwright"));
}

const args = process.argv.slice(2);
const shotsDir = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : null;
const only = args.filter((a, i) => a.endsWith(".html") && args[i - 1] !== "--shots");
// 英語のページ（docs/en/）も同じに見る。英語のページは英語のブラウザとして開く（日本語だと日本語のページへ移るため）
const ALL = fs.readdirSync(DOCS).filter((f) => f.endsWith(".html")).sort();
const PAGES = only.length ? only : [...ALL, ...fs.readdirSync(path.join(DOCS, "en")).filter((f) => f.endsWith(".html")).sort().map((f) => "en/" + f)];
const SIZES = [
  { name: "phone", width: 390, height: 844, mobile: true },
  { name: "pc", width: 1280, height: 800, mobile: false },
];

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const f = path.join(DOCS, u === "/" ? "index.html" : u);
  if (!f.startsWith(DOCS) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) {
    res.writeHead(404);
    return res.end();
  }
  res.writeHead(200, { "content-type": TYPES[path.extname(f)] || "application/octet-stream" });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/`;

const problems = [];
const bad = (page, size, msg) => problems.push(`${page} [${size}] ${msg}`);

async function audit(page, name, size) {
  const r = await page.evaluate((mobile) => {
    const out = [];
    const de = document.documentElement;
    if (de.scrollWidth > window.innerWidth + 1) out.push(`横にはみ出し（幅 ${de.scrollWidth}px > ${window.innerWidth}px）`);
    if (!document.querySelector('meta[name="viewport"]')) out.push("viewport の指定がない");
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const st = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && st.visibility !== "hidden" && !el.closest("dialog:not([open])");
    };
    const label = (el) =>
      (el.getAttribute("aria-label") || el.textContent || el.title || (el.id && document.querySelector(`label[for="${el.id}"]`)?.textContent) || "").trim();
    for (const el of document.querySelectorAll("button, select, input, nav a, a.cta")) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      const what = `${el.tagName.toLowerCase()}「${label(el).slice(0, 16)}」`;
      if (!label(el)) out.push(`${what} に名前がない`);
      if (r.width < 24 || r.height < 24) out.push(`${what} が小さい（${Math.round(r.width)}×${Math.round(r.height)}）`);
      else if (mobile && r.height < 44) out.push(`${what} の高さが44px未満（${Math.round(r.height)}）`);
    }
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const small = new Set();
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (!n.textContent.trim()) continue;
      const el = n.parentElement;
      if (!visible(el)) continue;
      const fz = parseFloat(getComputedStyle(el).fontSize);
      if (fz < 11) small.add(`${el.tagName.toLowerCase()}.${el.className}（${fz}px）`);
    }
    for (const s of small) out.push(`文字が小さい: ${s}`);
    if (document.documentElement.lang === "en") {
      const ja = /[\u3040-\u30ff\u3400-\u9fff]/;
      const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const left = new Set();
      while (w.nextNode()) {
        const n = w.currentNode;
        if (ja.test(n.textContent) && !n.parentElement.closest('[lang="ja"], script, style')) left.add(n.textContent.trim().slice(0, 20));
      }
      for (const t of left) out.push(`英語のページに日本語が残っている: 「${t}」`);
    }
    return out;
  }, size.mobile);
  for (const m of r) bad(name, size.name, m);
}

async function playCheck(page, size, name) {
  // やさしい AI・あなたが先手で新しい対局 → 宝石3色を取る → AI が1手返す
  await page.selectOption("#level", "easy");
  await page.selectOption("#first", "me");
  await page.click("#btnNew");
  await page.waitForFunction(() => document.querySelectorAll(".bank button:not([disabled])").length >= 3);
  // 押すたびに描き直すので、毎回番号で探す
  for (const k of [1, 2, 3]) await page.click(`.bank button:nth-child(${k})`);
  await page.click("#btnTake");
  try {
    await page.waitForFunction(() => document.querySelectorAll("#log li").length >= 2, null, { timeout: 15000 });
  } catch {
    bad(name, size.name, "宝石を取ったあと、AI が手を返さない");
    return;
  }
  // カードを押すと選び方の画面が出て、「やめる」で閉じられる
  await page.click(".lvl .card:not(.empty)");
  const open = await page.$eval("#dlg", (d) => d.open);
  if (!open) bad(name, size.name, "カードを押しても、買う・予約の選び方が出ない");
  else {
    await audit(page, name + "（カードの選び方）", size);
    if (shotsDir) await page.screenshot({ path: path.join(shotsDir, `${name.replace("/", "-").replace(".html", "")}-dialog-${size.name}.png`) });
    await page.click("#dlgOpts button:last-child");
  }
  // ヒントが出る
  await page.click("#btnHint");
  try {
    await page.waitForFunction(() => document.querySelectorAll("#hintBox li").length >= 1, null, { timeout: 30000 });
  } catch {
    bad(name, size.name, "ヒントが出ない");
  }
}

async function quizCheck(page, size, name) {
  // 盤が描かれ、選択肢を押すと答えと解説が出る。次の問題へ進める
  const n = await page.$$eval("#board .card:not(.empty)", (l) => l.length);
  if (n < 6) bad(name, size.name, `盤のカードが少ない（${n}枚）`);
  await page.click("#choices button:first-child");
  if (await page.$eval("#answer", (e) => e.hidden)) bad(name, size.name, "選択肢を押しても答えが出ない");
  if (shotsDir) await page.screenshot({ path: path.join(shotsDir, `${name.replace("/", "-").replace(".html", "")}-answer-${size.name}.png`), fullPage: true });
  await page.click("#next");
  if (!(await page.$eval("#answer", (e) => e.hidden))) bad(name, size.name, "次の問題で前の答えが残る");
}

async function langCheck(page, size) {
  // 「English」を押すと英語のページへ移り、選んだ言語を覚える（日本語のブラウザでも戻されない）
  await page.click('a[data-lang="en"]');
  await page.waitForLoadState("networkidle");
  if (!page.url().endsWith("/en/index.html")) bad("index.html", size.name, `English を押しても英語のページへ移らない（${page.url()}）`);
  await page.goto(BASE + "en/play.html");
  await page.waitForLoadState("networkidle");
  if (!page.url().includes("/en/")) bad("index.html", size.name, "英語を選んだあと、英語のページが日本語へ戻される");
  await page.click('a[data-lang="ja"]');
  await page.waitForLoadState("networkidle");
  if (page.url().includes("/en/")) bad("index.html", size.name, "日本語を押しても日本語のページへ移らない");
  await page.goto(BASE + "index.html");
}

const browser = await chromium.launch();
for (const size of SIZES) {
  for (const name of PAGES) {
    const ctx = await browser.newContext({
      viewport: { width: size.width, height: size.height },
      isMobile: size.mobile,
      hasTouch: size.mobile,
      deviceScaleFactor: 1,
      locale: name.startsWith("en/") ? "en-US" : "ja-JP",
    });
    const page = await ctx.newPage();
    page.on("console", (m) => m.type() === "error" && bad(name, size.name, `コンソールのエラー: ${m.text()}`));
    page.on("pageerror", (e) => bad(name, size.name, `スクリプトのエラー: ${e.message}`));
    page.on("response", (q) => q.status() >= 400 && bad(name, size.name, `読み込み失敗 ${q.status()}: ${q.url()}`));
    await page.goto(BASE + name);
    await page.waitForLoadState("networkidle");
    const base = name.replace(/^en\//, "");
    if (base === "play.html") await playCheck(page, size, name);
    if (base === "quiz.html") await quizCheck(page, size, name);
    if (name === "index.html" && size.mobile) await langCheck(page, size);
    await audit(page, name, size);
    if (shotsDir) {
      fs.mkdirSync(shotsDir, { recursive: true });
      await page.screenshot({ path: path.join(shotsDir, `${name.replace("/", "-").replace(".html", "")}-${size.name}.png`), fullPage: true });
    }
    await ctx.close();
  }
}
await browser.close();
server.close();
if (problems.length) {
  console.log(`✗ ${problems.length} 件の問題:`);
  for (const p of problems) console.log("  - " + p);
  process.exit(1);
}
console.log(`✓ ${PAGES.length} ページ × ${SIZES.length} 幅で問題なし`);
