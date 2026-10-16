'use strict';
/**
 * 验证【已安装的应用】能正常启动与工作（只做核心自检，不跑全套 e2e）。
 * 用法： node desktop/verify_installed.js "<安装目录>"
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const DIR = process.argv[2];
const DEBUG_PORT = '9504';
const EXE = path.join(DIR, 'CS2 控制台指令查询中心.exe');

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

let pass = 0, fail = 0;
const check = (n, ok, x) => {
  if (ok) { pass++; console.log('  ✓ ' + n); }
  else { fail++; console.log('  ✗ ' + n + (x !== undefined ? '  → ' + JSON.stringify(x) : '')); }
};

(async () => {
  if (!fs.existsSync(EXE)) { console.error('找不到 exe：' + EXE); process.exit(1); }
  console.log('[自检] ' + EXE + '\n');

  const app = spawn(EXE, [], {
    cwd: DIR, env: cleanEnv({ CS2HUB_DEBUG_PORT: DEBUG_PORT }),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let err = '';
  app.stderr.on('data', (c) => { err += c.toString(); });

  let page = null;
  for (let i = 0; i < 50 && !page; i++) {
    await sleep(500);
    if (app.exitCode !== null) break;
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${DEBUG_PORT}/json/list`));
      page = list.find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+/.test(t.url));
    } catch (e) {}
  }
  check('应用启动并打开窗口', !!page, app.exitCode);
  if (!page) {
    if (err) console.error(err.slice(0, 1500));
    try { app.kill(); } catch (e) {}
    process.exit(1);
  }

  const url = page.url.split('#')[0];
  console.log('  地址: ' + url + '\n');

  console.log('[接口]');
  const h = JSON.parse(await get(url + 'api/health'));
  check('本地服务（Node 引擎）', h.ok === true && h.engine === 'node', h);
  check('从 asar 内提供资源', /app\.asar/.test(h.root), h.root);
  const db = JSON.parse(await get(url + 'api/data'));
  check('指令库 2802 条', db.entries.length === 2802, db.entries.length);
  check('分类 15 个', db.categories.length === 15, db.categories.length);
  check('meta 版本可用', !!(db.meta && db.meta.version), db.meta && db.meta.version);
  check('上锁字段已移除', !(db.meta && 'guard' in db.meta), db.meta && Object.keys(db.meta).length);
  check('翻译缓存接口', typeof (await get(url + 'api/zh_cache')).length === 'number' ||
    !!(await get(url + 'api/zh_cache')));

  console.log('\n[界面]');
  const cdp = await attach(page.webSocketDebuggerUrl);

  // 等应用真正就绪：首屏要装载指令库 + 建索引，别抢在渲染前断言
  let ready = false;
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const r = await cdp(`document.body.classList.contains('app-ready')`).catch(() => false);
    if (r === true) { ready = true; break; }
  }
  check('应用已就绪（app-ready）', ready === true);

  const winTitle = await cdp(`document.title`).catch(() => '');

  const ui = JSON.parse(await cdp(`
    (function(){
      return JSON.stringify({
        ready: document.body.classList.contains('app-ready'),
        rows: document.querySelectorAll('#list .row').length,
        cats: document.querySelectorAll('.cat-item').length,
        helpCount: (document.getElementById('helpCount')||{}).textContent,
        err: (document.getElementById('errBox')||{}).style ?
             (document.getElementById('errBox').style.display === 'block'
               ? document.getElementById('errBox').textContent : '') : '',
        serverMode: typeof S !== 'undefined' ? S.serverMode : null,
        hasDrawer: !!document.getElementById('discDrawer'),
        hasAbout: !!document.getElementById('aboutDrawer'),
        favPanel: !!document.getElementById('favPanel'),
      });
    })()`));
  check('列表已渲染', ui.rows > 20, ui.rows);
  check('分类树已渲染', ui.cats === 16, ui.cats);
  check('走本地服务模式', ui.serverMode === true, ui.serverMode);
  check('无 JS 报错', !ui.err, ui.err);
  check('免责声明文档在', ui.hasDrawer === true);
  check('关于文档在', ui.hasAbout === true);

  console.log('\n[窗口]');
  check('窗口标题正确', /控制台指令查询中心/.test(String(winTitle)), winTitle);

  try { app.kill(); } catch (e) {}
  await sleep(600);
  console.log(`\n===== 通过 ${pass} / 失败 ${fail} =====`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });

/* 极简 CDP */
function attach(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 0;
    const pending = new Map();
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    };
    ws.onerror = reject;
    ws.onopen = () => {
      resolve(async (expr) => {
        const i = ++id;
        const p = new Promise((r) => pending.set(i, r));
        ws.send(JSON.stringify({
          id: i, method: 'Runtime.evaluate',
          params: { expression: expr, returnByValue: true, awaitPromise: true },
        }));
        const m = await p;
        if (m.result && m.result.exceptionDetails) {
          throw new Error(m.result.exceptionDetails.text);
        }
        return m.result && m.result.result && m.result.result.value;
      });
    };
  });
}
