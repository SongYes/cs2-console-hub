/** 快速探针：确认「仅游戏内确认」筛选与侧栏计数是否生效。 */
const fs = require('fs');
const path = require('path');
const os = require('os');
const http = require('http');
const { spawn } = require('child_process');

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].find((p) => fs.existsSync(p));

const PORT = 9333;
const APP = 'http://127.0.0.1:8788/';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function get(url) {
  return new Promise((res, rej) => {
    http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); }).on('error', rej);
  });
}

(async () => {
  const udd = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-probe-'));
  const proc = spawn(EDGE, ['--headless=new', `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${udd}`, '--no-first-run', '--window-size=1680,1000', APP], { stdio: 'ignore' });
  let target = null;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(400);
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
      target = list.find((t) => t.type === 'page' && t.url.startsWith('http://127.0.0.1:8788'));
    } catch { /* not up yet */ }
  }
  if (!target) { console.log('无法连上调试端口'); proc.kill(); process.exit(1); }

  const WebSocket = globalThis.WebSocket;
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  };
  const send = (method, params) => new Promise((res) => {
    const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params }));
  });
  const evaluate = async (expr) => {
    const r = await send('Runtime.evaluate', {
      expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true,
    });
    if (r.error) throw new Error(JSON.stringify(r.error));
    if (r.result && r.result.exceptionDetails) {
      throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
    }
    return r.result ? r.result.result.value : undefined;
  };
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Page.navigate', { url: APP });
  await sleep(4500);

  const out = await evaluate(`(() => {
    const cb = document.querySelector('#verifiedOnly');
    const sideAll = document.querySelector('.cat-item[data-cat=""] .ct');
    const header = document.querySelector('#listInfo') ? document.querySelector('#listInfo').textContent : '';
    const shown = document.querySelector('#countLine') ? document.querySelector('#countLine').textContent : '';
    return {
      有筛选框: !!cb, 默认勾选: cb ? cb.checked : null,
      侧栏全部指令: sideAll ? sideAll.textContent : null,
      顶栏文案: header, 计数行: shown,
      列表行数: document.querySelectorAll('.row').length,
      首行: (document.querySelector('.row') || {}).dataset ? document.querySelector('.row').dataset.name : null,
    };
  })()`);
  console.log(JSON.stringify(out, null, 1));

  // 取消勾选后再看
  const out2 = await evaluate(`(async () => {
    const cb = document.querySelector('#verifiedOnly');
    cb.checked = false; cb.dispatchEvent(new Event('change', { bubbles: true }));
    await new Promise(r => setTimeout(r, 600));
    return {
      侧栏全部指令: document.querySelector('.cat-item[data-cat=""] .ct').textContent,
      列表行数: document.querySelectorAll('.row').length,
    };
  })()`);
  console.log('取消勾选后:', JSON.stringify(out2));

  ws.close(); proc.kill();
  process.exit(0);
})();
