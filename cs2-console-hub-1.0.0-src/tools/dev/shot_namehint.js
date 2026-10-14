// 专门截一张"无官方说明的条目"的详情图，用来检查释义 / 名字拆解区块的排版。
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].find((p) => fs.existsSync(p));
const PORT = 9223;
const APP = 'http://127.0.0.1:8788/';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const get = (url) => new Promise((res, rej) => {
  http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); })
    .on('error', rej);
});

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.waits = new Map();
    ws.onmessage = (ev) => { const d = JSON.parse(ev.data);
      if (d.id && this.waits.has(d.id)) { this.waits.get(d.id)(d.result || d); this.waits.delete(d.id); } }; }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res) => { this.waits.set(id, res);
      this.ws.send(JSON.stringify({ id, method, params })); });
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate',
      { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
    return r && r.result ? r.result.value : undefined;
  }
}

(async () => {
  const userDir = path.join(process.env.TEMP, 'cs2hub-shot-namehint');
  fs.rmSync(userDir, { recursive: true, force: true });
  const proc = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    '--window-size=1680,1000', `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: 'ignore' });

  let target = null;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(500);
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
      target = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    } catch (e) { /* 等待浏览器起来 */ }
  }
  if (!target) { console.error('browser not available'); process.exit(1); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res) => { ws.onopen = res; });
  const cdp = new CDP(ws);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride',
    { width: 1680, height: 1000, deviceScaleFactor: 1, mobile: false });
  await cdp.send('Page.navigate', { url: APP });
  await sleep(4000);

  await cdp.eval(`
    const el = document.querySelector('#search');
    el.value = 'tv_show_allchat';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise(r => setTimeout(r, 700));
    const row = Array.from(document.querySelectorAll('.row')).find(r => r.dataset.name === 'tv_show_allchat');
    if (row) row.click();
    await new Promise(r => setTimeout(r, 400));
    return 1;`);
  await sleep(800);
  const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
  const out = path.join(__dirname, '..', '..', 'docs', 'verify-name-hint.png');
  fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));
  console.log('  saved docs/verify-name-hint.png');
  ws.close();
  proc.kill();
  process.exit(0);
})();
