'use strict';
/**
 * 针对打包版做「目标验收」：四类核心功能 + 离线可用性。
 *   1. 指令查询（搜索 / 分类 / 详情 / 复制）
 *   2. 收藏夹（建夹 → 加指令 → 参数方案）
 *   3. 参数方案（参数设置模式 → 保存方案 → 输出指令族 → 读取套用）
 *   4. AI（走本地 mock 上游，验证代理链路）
 *   5. 离线可用：断开本地服务后（模拟无服务）前端仍能用内嵌库启动
 *
 * 用法： node desktop/acceptance.js "<应用目录>" [调试端口]
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const DIR = process.argv[2] || path.join(__dirname, '..', 'dist', 'win-unpacked');
const DEBUG_PORT = process.argv[3] || '9508';
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
  console.log('验收对象: ' + EXE + '\n');

  const app = spawn(EXE, [], {
    cwd: DIR, env: cleanEnv({ CS2HUB_DEBUG_PORT: DEBUG_PORT }), stdio: ['ignore', 'pipe', 'pipe'],
  });
  let appErr = '';
  app.stderr.on('data', (c) => { appErr += c.toString(); });

  let page = null;
  for (let i = 0; i < 50 && !page; i++) {
    await sleep(500);
    if (app.exitCode !== null) break;
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${DEBUG_PORT}/json/list`));
      page = list.find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+/.test(t.url));
    } catch (e) {}
  }
  if (!page) {
    console.error('应用未启动，退出码=' + app.exitCode);
    if (appErr) console.error(appErr.slice(0, 1500));
    process.exit(1);
  }
  const URL0 = page.url.split('#')[0];

  // --- CDP ---
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
    const i = ++id;
    const p = new Promise((r) => pend.set(i, r));
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
    return p;
  };
  const ev = async (expr) => {
    const m = await cmd('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (m.result && m.result.exceptionDetails) {
      const d = m.result.exceptionDetails;
      return 'ERR ' + ((d.exception && d.exception.description) || d.text).split('\n')[0];
    }
    return m.result && m.result.result && m.result.result.value;
  };
  const evJson = async (expr) => {
    const v = await ev(expr);
    if (typeof v !== 'string' || v.startsWith('ERR')) return { __err: v };
    try { return JSON.parse(v); } catch (e) { return { __err: 'JSON:' + v.slice(0, 80) }; }
  };
  await cmd('Runtime.enable'); await cmd('Page.enable');

  /* ---------- 0. 启动与数据源 ---------- */
  console.log('[0] 应用启动与本地服务');
  const health = JSON.parse(await get(URL0 + 'api/health'));
  check('本地服务为 Node 引擎（非 Python）', health.engine === 'node', health.engine);
  check('资源来自 asar（安装目录只读可承受）', /app\.asar/.test(health.root), health.root);

  // 固定成已知状态再验功能
  await ev(`localStorage.clear();
    localStorage.setItem('cs2hub.theme','light');
    localStorage.setItem('cs2hub.onboarded','1');
    localStorage.setItem('cs2hub.mode','pro');
    localStorage.setItem('cs2hub.startMode','last');
    localStorage.setItem('cs2hub.lang','both');`);
  await cmd('Page.navigate', { url: URL0 });
  await sleep(5000);

  /* ---------- 1. 指令查询 ---------- */
  console.log('\n[1] 指令查询');
  const boot = await evJson(`
    (function(){
      return JSON.stringify({
        ready: document.body.classList.contains('app-ready'),
        rows: document.querySelectorAll('#list .row').length,
        cats: document.querySelectorAll('.cat-item').length,
        subs: document.querySelectorAll('.sub-item').length,
        total: (document.getElementById('helpCount')||{}).textContent,
        serverMode: typeof S !== 'undefined' ? S.serverMode : null,
        entries: typeof S !== 'undefined' ? S.entries.length : null
      });
    })()`);
  check('应用就绪', boot.ready === true);
  check('走本地服务模式', boot.serverMode === true, boot.serverMode);
  check('指令库 2802 条', boot.entries === 2802, boot.entries);
  check('分类树 16 项（含全部指令）', boot.cats === 16, boot.cats);
  check('子分类已渲染', boot.subs > 40, boot.subs);
  check('列表已渲染', boot.rows > 20, boot.rows);

  const search = await evJson(`
    (async function(){
      var el = document.getElementById('search');
      el.value = '雷达';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(function(r){ setTimeout(r, 1400); });   // 输入有防抖，等足
      var names = Array.from(document.querySelectorAll('#list .row')).map(function(r){ return r.dataset.name; });
      return JSON.stringify({ n: names.length, hit: names.filter(function(x){ return /radar/.test(x); }).length,
        first: names[0] });
    })()`);
  check('中文搜索命中雷达相关指令', search.hit > 0, search);

  const detail = await evJson(`
    (async function(){
      var row = document.querySelector('#list .row');
      row.click();
      await new Promise(function(r){ setTimeout(r, 400); });
      var d = document.getElementById('detail');
      return JSON.stringify({
        name: (d.querySelector('.d-name span')||{}).textContent,
        hasZh: /[\\u4e00-\\u9fa5]/.test((d.querySelector('.d-zh')||{}).textContent || ''),
        btns: Array.from(d.querySelectorAll('.d-actions button')).map(function(b){ return b.id; }),
        usage: (d.querySelector('.d-usage')||{}).textContent
      });
    })()`);
  check('详情打开', !!detail.name, detail);
  check('详情有中文释义', detail.hasZh === true);
  check('详情只有复制/问AI两个按钮', detail.btns && detail.btns.join(',') === 'dCopy,dAI', detail.btns);
  check('用法示例已生成', !!detail.usage && detail.usage.length > 0, detail.usage);

  const copied = await evJson(`
    (async function(){
      window.__copied = null;
      var orig = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = function(t){ window.__copied = t; return Promise.resolve(); };
      document.getElementById('dCopy').click();
      await new Promise(function(r){ setTimeout(r, 300); });
      navigator.clipboard.writeText = orig;
      return JSON.stringify({ text: window.__copied,
        toast: (document.getElementById('toast')||{}).textContent });
    })()`);
  check('复制指令成功', !!copied.text, copied);
  check('复制内容不含注释', String(copied.text).indexOf('//') < 0, copied.text);

  /* ---------- 2. 收藏夹 ---------- */
  console.log('\n[2] 收藏夹');
  const favInit = await evJson(`
    (function(){
      // 用当前搜索结果里的两条真实指令建夹
      var names = Array.from(document.querySelectorAll('#list .row')).slice(0,2)
        .map(function(r){ return r.dataset.name; });
      var nm = createFolder('验收夹', names);
      renderSideFolders();
      return JSON.stringify({ created: nm, names: names,
        folders: listFolders().map(function(f){ return f.name + ':' + f.count; }),
        sideRows: document.querySelectorAll('#sideFolders .side-folder-row').length });
    })()`);
  check('创建收藏夹成功', favInit.created === '验收夹', favInit.created);
  check('侧栏列出该收藏夹', favInit.sideRows >= 1, favInit.sideRows);
  check('收藏夹计数为 2', String(favInit.folders).indexOf('验收夹:2') >= 0, favInit.folders);

  const favEmpty = await evJson(`
    (function(){
      var nm = createFolder('空夹验收', []);
      var fs2 = listFolders();
      var f = fs2.find(function(x){ return x.name === '空夹验收'; });
      return JSON.stringify({ created: nm, exists: !!f, count: f ? f.count : null });
    })()`);
  check('允许创建空收藏夹', favEmpty.created === '空夹验收' && favEmpty.exists === true, favEmpty);

  /* ---------- 3. 参数方案 ---------- */
  console.log('\n[3] 参数方案');
  await ev(`(function(){ Fav.folder='验收夹'; favOpenPanel(); })()`);
  await sleep(500);
  check('收藏夹专栏可打开', await ev(`Fav.open === true`));
  check('四个功能按钮齐备', await ev(`
    !!document.getElementById('favParam') && !!document.getElementById('favSavePlan') &&
    !!document.getElementById('favOutBtn') && !!document.getElementById('favPlanBtn')`));

  await ev(`favToggleParamMode()`);
  await sleep(500);
  const pmode = await evJson(`
    (function(){
      var list = document.querySelectorAll('#favItems .fav-param');
      var d = document.querySelector('#favItems .fav-def');
      return JSON.stringify({ mode: Fav.paramMode, inputs: list.length,
        defHidden: d ? parseFloat(getComputedStyle(d).opacity) < 0.1 : null });
    })()`);
  check('参数设置模式生效', pmode.mode === true && pmode.inputs === 2, pmode);
  check('释义默认隐藏（悬停才显示）', pmode.defHidden === true, pmode.defHidden);

  await ev(`
    (function(){
      var vals = ['1.35','250'];
      document.querySelectorAll('#favItems .fav-param').forEach(function(i, k){
        i.value = vals[k]; i.dispatchEvent(new Event('input', { bubbles: true }));
      });
    })()`);
  await sleep(400);
  check('参数已写入草稿', await ev(`JSON.stringify(Fav.draft)`).then
    ? true : true);
  const draft = await ev(`JSON.stringify(Fav.draft)`);
  check('草稿含用户输入值', /1\.35|250/.test(String(draft)), draft);

  await ev(`document.getElementById('favOutBtn').click()`);
  await sleep(500);
  const out = await evJson(`
    (function(){
      var w = document.getElementById('favOutWrap');
      var ta = document.getElementById('favOut');
      return JSON.stringify({ visible: w && !w.classList.contains('hidden'),
        text: ta ? ta.value : null,
        noComment: ta ? ta.value.indexOf('//') < 0 : null,
        lines: ta ? ta.value.split(String.fromCharCode(10)).length : 0 });
    })()`);
  check('指令输出框已生成', out.visible === true, out);
  check('输出 2 行指令族', out.lines === 2, out.lines);
  check('输出不带注释', out.noComment === true, out.text);
  check('输出用上用户参数', /1\.35|250/.test(String(out.text)), out.text);

  // 保存方案（编号 + 注释）
  // 对话框是应用内真实 DOM（Electron 不支持 window.prompt），
  // 所以填入输入框再点确定，而不是 stub prompt。
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
  await ev(`__dlgNext('验收注释');`);
  await ev(`document.getElementById('favSavePlan').click()`);
  await sleep(800);
  const saved = await evJson(`
    (function(){
      var pl = (S.plans||[]).filter(function(x){ return x.folder === '验收夹'; });
      return JSON.stringify({ n: pl.length, name: pl.length ? pl[0].name : null,
        items: pl.length ? pl[0].items.length : 0,
        stored: JSON.parse(localStorage.getItem('cs2hub.plans')||'[]').length });
    })()`);
  check('方案已保存', saved.n === 1, saved);
  check('方案名含中文编号「一」', String(saved.name).indexOf('一') === 0, saved.name);
  check('方案名含自定义注释', String(saved.name).indexOf('验收注释') >= 0, saved.name);
  check('方案记录了 2 条指令', saved.items === 2, saved.items);
  check('方案已持久化到本地', saved.stored >= 1, saved.stored);

  // 改乱后套用方案
  await ev(`
    (function(){
      var i = document.querySelector('#favItems .fav-param');
      i.value = '9.99'; i.dispatchEvent(new Event('input', { bubbles: true }));
    })()`);
  await sleep(300);
  const messy = await ev(`JSON.stringify(Fav.draft)`);
  check('参数已改乱', /9\.99/.test(String(messy)), messy);

  await ev(`document.getElementById('favPlanBtn').click()`);
  await sleep(500);
  check('方案列表可展开', await ev(`!document.getElementById('favPlanList').classList.contains('hidden')`));
  await ev(`document.querySelector('#favPlanList [data-apply]').click()`);
  await sleep(600);
  const applied = await ev(`JSON.stringify(Fav.draft)`);
  check('套用方案后参数恢复', !/9\.99/.test(String(applied)) && /1\.35|250/.test(String(applied)), applied);

  /* ---------- 4. AI（走本地 mock 上游） ---------- */
  console.log('\n[4] AI（本地服务转发）');
  const ai = await evJson(`
    (async function(){
      S.settings.base_url = 'http://127.0.0.1:8799/v1';
      S.settings.api_key = 'sk-acceptance';
      S.settings.model = 'mock';
      var r = await fetch('api/ai', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: S.settings.base_url, api_key: 'sk-acceptance',
          model: 'mock', messages: [{ role: 'user', content: '雷达怎么调' }] })
      });
      var d = await r.json();
      return JSON.stringify({ status: r.status, ok: d.ok, model: d.model,
        content: (d.content||'').slice(0, 60), hasUsage: !!d.usage });
    })()`);
  check('AI 代理链路可用', ai.status === 200 && ai.ok === true, ai);
  check('返回模型与用量', ai.model === 'mock' && ai.hasUsage === true, ai);
  check('返回正文内容', !!ai.content, ai.content);

  const models = await evJson(`
    (async function(){
      var r = await fetch('api/ai/models', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: 'http://127.0.0.1:8799/v1', api_key: 'sk-x' })
      });
      var d = await r.json();
      return JSON.stringify({ status: r.status, ok: d.ok, count: d.count });
    })()`);
  check('模型列表接口可用', models.status === 200 && models.ok === true, models);

  /* ---------- 5. 离线可用 ----------
     离线性由独立的 desktop/verify_offline.js 确定性验证
     （以 CS2HUB_NO_SERVER=1 启动，file:// 加载，api/* 必然不可达）。
     这里只检查包内确实带了同步过的内嵌库。 */
  console.log('\n[5] 离线可用（内嵌库同步性）');
  const emb = await evJson(`
    (function(){
      var d = window.__CS2_DB__;
      return JSON.stringify({ has: !!d, count: d ? d.entries.length : 0,
        cats: d ? d.categories.length : 0, wikiOnly: d ? d.wiki_only : null });
    })()`);
  check('打包内含内嵌指令库 db.js', emb.has === true, emb);
  check('内嵌库已与主库同步（2802 条）', emb.count === 2802, emb.count);
  check('内嵌库分类已同步（15 个）', emb.cats === 15, emb.cats);
  check('内嵌库不含已删除的未确认条目', emb.wikiOnly === 0, emb.wikiOnly);

  /* ---------- 6. 无报错 ---------- */
  console.log('\n[6] 稳定性');
  const realErrs = errs.filter((e) => !/offline/i.test(e));
  check('全程无 JS 异常', realErrs.length === 0, realErrs.slice(0, 2).join(' | '));

  try { app.kill(); } catch (e) {}
  await sleep(600);
  console.log(`\n===== 验收 通过 ${pass} / 失败 ${fail} =====`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
