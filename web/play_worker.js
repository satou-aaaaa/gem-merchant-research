// AI の考えをページの外（別スレッド）で回す。考えている間も画面が止まらないように
importScripts("gem_engine.js");
self.onmessage = (e) => {
  const { id, state, level, seed, iterations } = e.data;
  const s = GemEngine.clone(state);
  let out;
  if (iterations) out = GemEngine.mctsSearch(s, iterations, GemEngine.makeRng(seed));
  else out = GemEngine.aiAct(s, level, seed);
  self.postMessage({ id, best: out.best, stats: out.stats ? out.stats.slice(0, 5) : null, value: out.value });
};
