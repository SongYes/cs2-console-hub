'use strict';
/**
 * 给【已安装/打包后的应用】截图（用于交付确认）。
 * 用法： node desktop/shot_app.js "<安装目录>" [输出名]
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const DIR = process.argv[2] || path.join(__dirname, '..', 'dist', 'win-unpacked');
const OUTNAME = process.argv[3] || 'app-packaged.png';
const DEBUG_PORT = '9506';
const EXE = path.join(DIR, 'CS2 控制台指令查询中心.exe');
const OUT = path.join(__dirname, '..', 'design', 'shots_live', OUTNAME);

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const get = (url) => new Promise((res, rej) => {
  http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); })
    .on('error', rej);
});
function cleanEnv(extra) {
  const env = {};
  Object.keys(process.env).forEach((k) => {
    const up = k.toUpperCase();
    if (up.startsWith('ELECTRON') || up === 'NODE_OPTIONS') return;
    env[k] = process.env[k];
  });
  return Object.assign(env, extra || {});
}

(async () => {
  const app = spawn(EXE, [], {
    cwd: DIR, env: cleanEnv({ CS2HUB_DEBUG_PORT: DEBUG_PORT }),
    stdio: 'ignore',
  });
  let page = null;
  for (let i = 0; i < 50 && !page; i++) {
    await sleep(500);
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${DEBUG_PORT}/json/list`));
      page = list.find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+/.test(t.url));
    } catch (e) {}
  }
  if (!page) { console.error('应用未就绪'); try { app.kill(); } catch (e) {} process.exit(1); }

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
  const cmd = (method, params) => {
    const i = ++id;
    const p = new Promise((r) => pend.set(i, r));
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
    return p;
  };
  const ev = async (expr) => {
    const m = await cmd('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    return m.result && m.result.result && m.result.result.value;
  };

  await cmd('Emulation.setDeviceMetricsOverride',
    { width: 1680, height: 1000, deviceScaleFactor: 1, mobile: false });
  await sleep(1500);
  // 用清爽的默认状态截图
  await ev(`localStorage.clear();
    localStorage.setItem('cs2hub.theme','light');
    localStorage.setItem('cs2hub.onboarded','1');
    localStorage.setItem('cs2hub.mode','pro');
    localStorage.setItem('cs2hub.startMode','last')`);
  await cmd('Page.navigate', { url: page.url });
  await sleep(5000);

  const s = await cmd('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, Buffer.from(s.result.data, 'base64'));
  console.log('saved ' + OUTNAME);

  // 再截一张「关于本软件」抽屉，体现打包版内容完整
  await ev(`openDrawer('about')`);
  await sleep(900);
  const s2 = await cmd('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(path.join(path.dirname(OUT), 'app-packaged-about.png'),
    Buffer.from(s2.result.data, 'base64'));
  console.log('saved app-packaged-about.png');

  try { app.kill(); } catch (e) {}
  process.exit(0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
