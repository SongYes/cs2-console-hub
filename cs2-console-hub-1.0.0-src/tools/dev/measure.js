/**
 * 开发用：窄窗口下测量侧栏各元素的盒子，定位重叠/溢出问题。
 * 用法： node tools/dev/measure.js [宽度] [高度]
 */
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].find((p) => fs.existsSync(p));

const PORT = 9224;
const APP = 'http://127.0.0.1:8788/';
const W = Number(process.argv[2] || 500);
const H = Number(process.argv[3] || 700);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function get(url) {
  return new Promise((res, rej) => {
    http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); }).on('error', rej);
  });
}

(async () => {
  const userDir = path.join(process.env.TEMP, 'cs2hub-measure');
  fs.rmSync(userDir, { recursive: true, force: true });
  const proc = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: 'ignore' });

  let target = null;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(500);
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
      target = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    } catch (e) { /* 等待 */ }
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res) => { ws.onopen = res; });
  let id = 0; const pending = new Map();
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  };
  const send = (method, params = {}) => {
    const i = ++id; ws.send(JSON.stringify({ id: i, method, params }));
    return new Promise((r) => pending.set(i, r));
  };
  const evalJs = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: `(() => { ${expr} })()`, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
    return r.result.value;
  };

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',
    { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: APP });
  await sleep(4500);

  const data = await evalJs(`
    const pick = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height),
               scrollH: el.scrollHeight, clientH: el.clientHeight,
               overflow: cs.overflow, minH: cs.minHeight, flex: cs.flex, pos: cs.position };
    };
    // 元素被最近的可滚动/裁切祖先裁掉的比例
    const clipInfo = (el) => {
      const r = el.getBoundingClientRect();
      let p = el.parentElement, clip = null;
      while (p) {
        const cs = getComputedStyle(p);
        if (cs.overflowY !== 'visible' || cs.overflowX !== 'visible') { clip = p; break; }
        p = p.parentElement;
      }
      if (!clip) return { visible: 1, rect: [Math.round(r.top), Math.round(r.bottom)] };
      const cr = clip.getBoundingClientRect();
      const top = Math.max(r.top, cr.top), bottom = Math.min(r.bottom, cr.bottom);
      const shown = Math.max(0, bottom - top);
      return { visible: +(shown / Math.max(1, r.height)).toFixed(3),
               rect: [Math.round(r.top), Math.round(r.bottom)],
               clip: [Math.round(cr.top), Math.round(cr.bottom)] };
    };
    const chips = Array.from(document.querySelectorAll('#quickNav button')).map(b => {
      const r = b.getBoundingClientRect();
      return Object.assign({ t: b.textContent, top: Math.round(r.top), bottom: Math.round(r.bottom) },
                           clipInfo(b));
    });
    const cats = Array.from(document.querySelectorAll('.cat-item')).map(b => {
      const r = b.getBoundingClientRect();
      return Object.assign({ t: b.textContent.trim().slice(0, 10), top: Math.round(r.top),
                             bottom: Math.round(r.bottom) }, clipInfo(b));
    });
    // 真正画出来的 chip 与真正画出来的分类行是否存在几何相交
    const painted = (o) => o.visible > 0.01;
    const overlap = chips.some(c => painted(c) && cats.some(k => painted(k) &&
      c.bottom > k.top && c.top < k.bottom));
    return {
      win: [innerWidth, innerHeight],
      sidebar: pick('.sidebar'),
      quickBlock: pick('.side-block.quick'),
      quickNav: pick('#quickNav'),
      treeBlock: pick('.side-block.grow'),
      catTree: pick('#catTree'),
      sideFoot: pick('.side-foot'),
      chipsHidden: chips.filter(c => c.visible < 0.99).length,
      chipsTotal: chips.length,
      catsVisible: cats.filter(painted).length,
      overlapChipsAndCats: overlap,
      chips: chips.map(c => [c.t, c.rect, c.visible]),
      cats: cats.slice(0, 4).map(k => [k.t, k.rect, k.visible]),
    };`);

  console.log(JSON.stringify(data, null, 1));
  proc.kill();
  ws.close();
  process.exit(0);
})();
