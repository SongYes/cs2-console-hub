'use strict';
/**
 * 离线可用性验证（确定性，无请求拦截竞态）。
 *
 * 做法：以 CS2HUB_NO_SERVER=1 启动应用 → 不启本地服务、直接以 file:// 加载页面。
 * 此时 api/* 必然不可达，只能走 assets/db.js 内嵌库 —— 正是「离线可用」的真实场景。
 *
 * 用法： node desktop/verify_offline.js "<应用目录>"
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const DIR = process.argv[2] || path.join(__dirname, '..', 'dist', 'win-unpacked');
const PORT = '9514';
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
  console.log('离线验证（不启本地服务，file:// 加载）\n');

  const app = spawn(EXE, [], {
    cwd: DIR,
    env: cleanEnv({ CS2HUB_NO_SERVER: '1', CS2HUB_DEBUG_PORT: PORT }),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let appErr = '';
  app.stderr.on('data', (c) => { appErr += c.toString(); });

  let page = null;
  for (let i = 0; i < 50 && !page; i++) {
    await sleep(500);
    if (app.exitCode !== null) break;
    try {
      const l = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
      page = l.find((t) => t.type === 'page' && t.webSocketDebuggerUrl &&
        (/^file:\/\//.test(t.url) || /127\.0\.0\.1:\d+/.test(t.url)));
    } catch (e) {}
  }
  if (!page) {
    console.error('应用未启动，退出码=' + app.exitCode);
    if (appErr) console.error(appErr.slice(0, 1200));
    process.exit(1);
  }
  check('以 file:// 加载页面（无本地服务）', /^file:\/\//.test(page.url), page.url);

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map(); const errs = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      errs.push((d.exception && d.exception.description) || d.text);
    }
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  };
  const cmd = (method, params) => {
    const i = ++id; const p = new Promise((r) => pend.set(i, r));
    ws.send(JSON.stringify({ id: i, method, params: params || {} })); return p;
  };
  const ev = async (expr) => {
    const m = await cmd('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (m.result && m.result.exceptionDetails) {
      const d = m.result.exceptionDetails;
      return 'ERR ' + ((d.exception && d.exception.description) || d.text).split('\n')[0];
    }
    return m.result && m.result.result && m.result.result.value;
  };
  await cmd('Runtime.enable');

  // 等应用就绪（内嵌库 1MB，解析 + 建索引需要时间）
  let ready = false;
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    if (await ev(`document.body.classList.contains('app-ready')`) === true) { ready = true; break; }
  }
  check('离线模式启动完成（app-ready）', ready === true);

  const st = await ev(`JSON.stringify({
    serverMode: S.serverMode,
    embedded: window.__CS2_DB__ ? window.__CS2_DB__.entries.length : null,
    embeddedCats: window.__CS2_DB__ ? window.__CS2_DB__.categories.length : null,
    entries: S.entries ? S.entries.length : null,
    rows: document.querySelectorAll('#list .row').length,
    cats: document.querySelectorAll('.cat-item').length,
    subs: document.querySelectorAll('.sub-item').length,
    helpCount: (document.getElementById('helpCount')||{}).textContent
  })`);
  const s = JSON.parse(st);
  check('未走服务模式（确认是离线）', s.serverMode === false, s.serverMode);
  check('内嵌库为 2802 条', s.embedded === 2802, s.embedded);
  check('内嵌库为 15 分类', s.embeddedCats === 15, s.embeddedCats);
  check('指令库已装载', s.entries === 2802, s.entries);
  check('列表已渲染', s.rows > 20, s.rows);
  check('分类树已渲染', s.cats === 16, s.cats);
  check('子分类已渲染', s.subs > 40, s.subs);
  check('条目数文案正确', /^2802 条/.test(String(s.helpCount)), s.helpCount);

  // 离线也要能用核心交互
  const search = await ev(`
    (async function(){
      var el = document.getElementById('search');
      el.value = '雷达';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(function(r){ setTimeout(r, 1400); });
      return document.querySelectorAll('#list .row').length;
    })()`);
  check('离线状态可搜索（雷达）', search > 0, search);

  const detail = await ev(`
    (async function(){
      document.querySelector('#list .row').click();
      await new Promise(function(r){ setTimeout(r, 400); });
      var d = document.getElementById('detail');
      return JSON.stringify({
        name: (d.querySelector('.d-name span')||{}).textContent,
        hasZh: /[\\u4e00-\\u9fa5]/.test((d.querySelector('.d-zh')||{}).textContent || ''),
        usage: !!((d.querySelector('.d-usage')||{}).textContent)
      });
    })()`);
  const dt = JSON.parse(detail);
  check('离线可打开详情', !!dt.name, dt);
  check('离线详情有中文释义', dt.hasZh === true);
  check('离线可生成用法示例', dt.usage === true);

  const favo = await ev(`
    (function(){
      var names = Array.from(document.querySelectorAll('#list .row')).slice(0,2)
        .map(function(r){ return r.dataset.name; });
      var nm = createFolder('离线夹', names);
      return JSON.stringify({ created: nm, count: (listFolders()[0]||{}).count });
    })()`);
  check('离线可建收藏夹', JSON.parse(favo).created === '离线夹', favo);

  const realErrs = errs.filter((e) => !/ERR_CONNECTION_REFUSED|Failed to load resource|api\//i.test(String(e)));
  check('无 JS 异常（网络失败已优雅兜底）', realErrs.length === 0, realErrs.slice(0, 2).join(' | '));

  try { app.kill(); } catch (e) {}
  await sleep(500);
  console.log(`\n===== 离线验证 通过 ${pass} / 失败 ${fail} =====`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
