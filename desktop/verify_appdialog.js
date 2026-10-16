'use strict';
/**
 * 在打包版里验证应用内对话框可用（对应「点新建收藏夹报 prompt() is not supported」的回归）。
 * 用法： node desktop/verify_appdialog.js "<应用目录>"
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const DIR = process.argv[2] || path.join(__dirname, '..', 'dist', 'win-unpacked');
const PORT = '9520';
const EXE = path.join(DIR, 'CS2 控制台指令查询中心.exe');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const get = (u) => new Promise((res, rej) => {
  http.get(u, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); })
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
const check = (n, ok, x) => { if (ok) { pass++; console.log('  ✓ ' + n); }
  else { fail++; console.log('  ✗ ' + n + (x !== undefined ? '  → ' + JSON.stringify(x) : '')); } };

(async () => {
  if (!fs.existsSync(EXE)) { console.error('找不到 exe：' + EXE); process.exit(1); }
  console.log('打包版: ' + EXE + '\n');
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

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => { ws.onopen = r; });
  let id = 0; const pend = new Map(); const errs = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.method === 'Runtime.exceptionThrown') {
      const d = m.params.exceptionDetails;
      errs.push((d.exception && (d.exception.description || d.exception.value)) || d.text);
    }
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  };
  const cmd = (method, params) => {
    const i = ++id; const p = new Promise((r) => pend.set(i, r));
    ws.send(JSON.stringify({ id: i, method, params: params || {} })); return p;
  };
  const ev = async (expr) => {
    const m = await cmd('Runtime.evaluate', { expression: expr, returnByValue: true });
    if (m.result && m.result.exceptionDetails) {
      const d = m.result.exceptionDetails;
      return 'ERR ' + ((d.exception && (d.exception.description || d.exception.value)) || d.text)
        .split('\n')[0];
    }
    return m.result && m.result.result ? m.result.result.value : undefined;
  };
  await cmd('Runtime.enable');

  let ready = false;
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    if (await ev(`document.body.classList.contains('app-ready')`) === true) { ready = true; break; }
  }
  check('应用就绪', ready === true);

  // 清一个干净状态
  await ev(`localStorage.removeItem('cs2hub.favItems');
            localStorage.removeItem('cs2hub.folders');
            localStorage.removeItem('cs2hub.plans');`);
  await cmd('Page.navigate', { url: page.url });
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    if (await ev(`document.body.classList.contains('app-ready')`) === true) break;
  }

  console.log('\n[1] 打包版不支持 prompt —— 确认代码里已无原生调用');
  check('appPrompt / appConfirm 已发布',
    await ev(`typeof appPrompt === 'function' && typeof appConfirm === 'function'`) === true);
  // 直接调 window.prompt 看 Electron 的真实行为（作为对照证据）
  const native = await ev(`(function(){
    try { var v = window.prompt('x'); return 'returned:' + v; }
    catch (e) { return 'throw:' + e.message; }
  })()`);
  console.log('  （对照）打包版调用原生 window.prompt 的结果：' + native);
  check('确认原生 prompt 在 Electron 里不可用', /throw|not supported/i.test(String(native)), native);

  console.log('\n[2] 原 bug 场景：点「新建收藏夹」');
  await ev(`(function(){
    window.__dlgNext = function (value, ok) {
      window.__dlg = { value: value, ok: ok === undefined ? (value !== null) : ok, done: false };
    };
    var mo = new MutationObserver(function () {
      var el = document.getElementById('appDialog');
      if (!el || el.classList.contains('hidden') || !window.__dlg || window.__dlg.done) return;
      window.__dlg.done = true;
      setTimeout(function () {
        var inp = document.getElementById('adInput');
        if (inp && !inp.classList.contains('hidden') && typeof window.__dlg.value === 'string') {
          inp.value = window.__dlg.value;
          inp.dispatchEvent(new Event('input', { bubbles: true }));
        }
        var b = window.__dlg.ok ? document.getElementById('adOk')
                                : document.getElementById('adCancel');
        if (b) b.click();
      }, 40);
    });
    mo.observe(document.body, { childList: true, subtree: true, attributes: true,
                                attributeFilter: ['class'] });
    return 'ok';
  })()`);

  await ev(`__dlgNext('打包版测试夹'); document.getElementById('btnFavAdd').click();`);
  await sleep(1000);
  const mk = await ev(`JSON.stringify({
    names: listFolders().map(function(f){ return f.name; }),
    closed: document.getElementById('appDialog').classList.contains('hidden')
  })`);
  const mko = JSON.parse(mk);
  check('★ 新建收藏夹成功（原 bug）', (mko.names || []).indexOf('打包版测试夹') >= 0, mko.names);
  check('对话框已关闭', mko.closed === true);

  console.log('\n[3] 其他原先依赖 prompt 的流程');
  await ev(`(function(){ Fav.folder='打包版测试夹'; favOpenPanel(); })()`);
  await sleep(800);
  await ev(`__dlgNext('改名后'); document.getElementById('favRename').click();`);
  await sleep(900);
  check('★ 重命名收藏夹成功', await ev(`
    listFolders().some(function(f){ return f.name === '改名后'; })`) === true,
    await ev(`JSON.stringify(listFolders().map(function(f){ return f.name; }))`));

  await ev(`__dlgNext('打包版方案注释'); document.getElementById('favSavePlan').click();`);
  await sleep(900);
  const emptyPlan = await ev(`!document.getElementById('adInput') || document.getElementById('appDialog').classList.contains('hidden')`);
  check('空收藏夹提示而非弹框（预期行为）', emptyPlan !== 'ERR', String(emptyPlan));

  console.log('\n[4] 关键：不应出现 prompt 不支持异常');
  const bad = errs.filter((e) => /prompt\(\) is not supported/i.test(String(e)));
  check('★ 无「prompt() is not supported」', bad.length === 0, bad.slice(0, 2));
  const real = errs.filter((e) => !/ERR_CONNECTION_REFUSED|Failed to load resource/i.test(String(e)));
  check('无其它 JS 异常', real.length === 0, real.slice(0, 2).join(' | '));

  try { app.kill(); } catch (e) {}
  await sleep(500);
  console.log(`\n===== 打包版对话框验证 通过 ${pass} / 失败 ${fail} =====`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
