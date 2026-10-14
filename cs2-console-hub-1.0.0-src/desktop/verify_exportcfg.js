'use strict';
/**
 * 在打包版里验证「导出 cfg」：接口可用 + 前端按钮/设置项在位 + 真写一次再清理。
 * 用法： node desktop/verify_exportcfg.js "<应用目录>"
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const DIR = process.argv[2] || path.join(__dirname, '..', 'dist', 'win-unpacked');
const PORT = '9516';
const EXE = path.join(DIR, 'CS2 控制台指令查询中心.exe');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const get = (u) => new Promise((res, rej) => {
  http.get(u, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); })
    .on('error', rej);
});
const post = (u, body) => new Promise((res, rej) => {
  const data = JSON.stringify(body);
  const req = http.request(u, { method: 'POST', headers: {
    'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } },
    (r) => { let d = ''; r.on('data', (c) => d += c);
      r.on('end', () => res({ status: r.statusCode, body: JSON.parse(d || '{}') })); });
  req.on('error', rej); req.write(data); req.end();
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
const check = (n, ok, x) => { if (ok) { pass++; console.log('  ✓ ' + n); }
  else { fail++; console.log('  ✗ ' + n + (x !== undefined ? '  → ' + JSON.stringify(x) : '')); } };

(async () => {
  if (!fs.existsSync(EXE)) { console.error('找不到 exe：' + EXE); process.exit(1); }
  const app = spawn(EXE, [], { cwd: DIR, env: cleanEnv({ CS2HUB_DEBUG_PORT: PORT }), stdio: 'ignore' });
  let page = null;
  for (let i = 0; i < 50 && !page; i++) {
    await sleep(500);
    try {
      const l = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
      page = l.find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+/.test(t.url));
    } catch (e) {}
  }
  if (!page) { console.error('应用未启动'); process.exit(1); }
  const base = page.url.split('#')[0].replace(/\/$/, '');
  console.log('打包版: ' + base + '\n');

  console.log('[1] 服务端接口（asar 内）');
  const dir = JSON.parse(await get(base + '/api/game/cfgdir'));
  check('cfg 目录探测可用', dir.ok === true && /csgo\\cfg$/i.test(String(dir.dir)), dir);
  console.log('  ' + dir.dir);

  const w = await post(base + '/api/game/cfg',
    { name: '__cs2hub_pkg_test__', data: 'sensitivity 1.5\n' });
  check('写入接口可用', w.status === 200 && w.body.ok === true, w.body);
  if (w.body && w.body.path && fs.existsSync(w.body.path)) {
    check('内容落盘正确', fs.readFileSync(w.body.path, 'utf8').indexOf('sensitivity 1.5') >= 0);
    fs.unlinkSync(w.body.path);
    check('测试文件已清理', !fs.existsSync(w.body.path));
  }
  const bad = await post(base + '/api/game/cfg', { name: 'x', data: '' });
  check('空内容被拒（安全校验在包内同样生效）', bad.status === 400, bad.body);

  console.log('\n[2] 前端');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map(); const errs = [];
  ws.onmessage = (e) => { const m = JSON.parse(e.data);
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      errs.push((d.exception && d.exception.description) || d.text); }
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
  const cmd = (method, params) => { const i = ++id;
    const p = new Promise((r) => pend.set(i, r));
    ws.send(JSON.stringify({ id: i, method, params: params || {} })); return p; };
  const ev = async (expr) => {
    const m = await cmd('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (m.result && m.result.exceptionDetails) {
      const d = m.result.exceptionDetails;
      return 'ERR ' + ((d.exception && d.exception.description) || d.text).split('\n')[0]; }
    return m.result && m.result.result && m.result.result.value; };
  const evJson = async (expr) => {
    const v = await ev(expr);
    if (typeof v !== 'string' || v.startsWith('ERR')) return { __err: v };
    try { return JSON.parse(v); } catch (e) { return { __err: 'JSON' }; } };
  await cmd('Runtime.enable');

  let ready = false;
  for (let i = 0; i < 40; i++) { await sleep(500);
    if (await ev(`document.body.classList.contains('app-ready')`) === true) { ready = true; break; } }
  check('应用已就绪', ready === true);

  check('导出相关函数已随包发布', await ev(`
    typeof planExportCfg === 'function' && typeof planFileName === 'function' &&
    typeof getCfgMode === 'function'`));
  const mode = await ev(`getCfgMode()`);
  check('默认导出方式为手动', mode === 'manual', mode);

  // 造方案 → 打开方案列表 → 确认按钮
  const mk = await evJson(`
    (function(){
      var names = Array.from(document.querySelectorAll('#list .row')).slice(0,2)
        .map(function(r){ return r.dataset.name; });
      createFolder('包内导出夹', names);
      var pl = addPlan('一 · 包内方案', '包内导出夹',
        [{ n: names[0], v: '1.5' }, { n: names[1], v: '300' }]);
      Fav.folder = '包内导出夹';
      favOpenPanel();
      document.getElementById('favPlanBtn').click();
      return JSON.stringify({ plan: pl.id, fname: planFileName(pl) });
    })()`);
  await sleep(700);
  check('文件名已净化', mk.fname === '一_包内方案.cfg', mk.fname);
  const row = await evJson(`
    (function(){
      var r = document.querySelector('#favPlanList .fp-row');
      if (!r) return JSON.stringify({ err: 'no row' });
      return JSON.stringify({ btns: Array.from(r.querySelectorAll('button'))
        .map(function(b){ return b.textContent.trim(); }) });
    })()`);
  check('方案行含「导出 cfg」且位于「套用」后', (row.btns || []).join(',') === '套用,导出 cfg,✕', row.btns);

  console.log('\n[3] 包内实际导出一次（auto 模式）');
  await ev(`setCfgMode('auto')`);
  await sleep(300);
  const before = new Set(fs.readdirSync(dir.dir).filter((f) => /\.cfg$/i.test(f)));
  await ev(`planExportCfg(${JSON.stringify(mk.plan)})`);
  await sleep(2200);
  const now = fs.readdirSync(dir.dir).filter((f) => /\.cfg$/i.test(f));
  const added = now.filter((f) => !before.has(f));
  check('确实写进了游戏目录', added.length >= 1, added);
  if (added.length) {
    const full = path.join(dir.dir, added[0]);
    const c = fs.readFileSync(full, 'utf8');
    check('内容为纯指令', c.indexOf('//') < 0, JSON.stringify(c.slice(0, 60)));
    check('带上了方案参数', c.indexOf('1.5') >= 0 && c.indexOf('300') >= 0, JSON.stringify(c));
    console.log('  ' + added[0] + ' → ' + JSON.stringify(c));
    fs.unlinkSync(full);
    check('已清理', !fs.existsSync(full));
  }

  const real = errs.filter((e) => !/ERR_CONNECTION_REFUSED|Failed to load resource/i.test(String(e)));
  check('无 JS 异常', real.length === 0, real.slice(0, 2).join(' | '));

  try { app.kill(); } catch (e) {}
  await sleep(500);
  console.log(`\n===== 打包版导出验证 通过 ${pass} / 失败 ${fail} =====`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
