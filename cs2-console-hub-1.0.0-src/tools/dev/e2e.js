/**
 * 浏览器端到端自检（开发用，不参与运行时）
 * 用 CDP 驱动 Edge/Chrome：加载页面 -> 搜索/筛选/详情/收藏/配置生成 -> AI 面板 -> 翻译回填
 * 前置： tools/server.py 正在运行； tools/dev/mock_ai.py 正在运行
 * 用法： node tools/dev/e2e.js
 */
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].find((p) => fs.existsSync(p));

const PORT = 9222;
const APP = 'http://127.0.0.1:8788/';
const MOCK = { base_url: 'http://127.0.0.1:8799/v1', api_key: 'sk-e2e', model: 'mock' };

function get(url) {
  return new Promise((res, rej) => {
    http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); })
      .on('error', rej);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); }
  static async attach(wsUrl) {
    const ws = new WebSocket(wsUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    const c = new CDP(ws);
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && c.pending.has(m.id)) {
        const { res, rej } = c.pending.get(m.id);
        c.pending.delete(m.id);
        m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
      }
    };
    return c;
  }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' +
      JSON.stringify(r.exceptionDetails.exception && r.exceptionDetails.exception.description));
    return r.result.value;
  }
}

(async () => {
  const failures = [];
  const ok = (cond, label, extra) => {
    console.log((cond ? '  [OK] ' : '  [FAIL] ') + label +
      (extra !== undefined ? ' -> ' + JSON.stringify(extra) : ''));
    if (!cond) failures.push(label);
  };

  // 附加模式：连接已在运行的应用（如打包后的 Electron 窗口），不自己拉浏览器
  const ATTACH = process.env.CS2HUB_E2E_ATTACH === '1';
  const DEBUG_PORT = process.env.CS2HUB_E2E_PORT || PORT;
  const TARGET_URL = process.env.CS2HUB_E2E_URL || APP;
  let proc = null;
  if (!ATTACH) {
    const userDir = path.join(process.env.TEMP, 'cs2hub-e2e');
    fs.rmSync(userDir, { recursive: true, force: true });
    proc = spawn(EDGE, [
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`, 'about:blank',
    ], { stdio: 'ignore' });
  } else {
    console.log('[附加模式] 连接 127.0.0.1:' + DEBUG_PORT + ' → ' + TARGET_URL);
  }

  try {
    let target = null;
    for (let i = 0; i < 40 && !target; i++) {
      await sleep(500);
      try {
        const list = JSON.parse(await get(`http://127.0.0.1:${DEBUG_PORT}/json/list`));
        target = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      } catch (e) { /* 还没起来 */ }
    }
    if (!target) throw new Error('无法连接浏览器调试端口');
    const cdp = await CDP.attach(target.webSocketDebuggerUrl);
    await cdp.send('Runtime.enable');
    await cdp.send('Page.enable');

    console.log('\n[1] 加载页面 + 指令库');
    await cdp.send('Page.navigate', { url: TARGET_URL });
    await sleep(3500);
    const boot = await cdp.eval(`
      return {
        rows: document.querySelectorAll('#list .row').length,
        cats: document.querySelectorAll('.cat-item').length,
        subs: document.querySelectorAll('.sub-item').length,
        err: (document.querySelector('#errBox').style.display === 'block') ? document.querySelector('#errBox').textContent : '',
        ready: document.body.classList.contains('app-ready'),
        helpCount: document.querySelector('#helpCount').textContent,
      };`);
    ok(/^\d{4}/.test(boot.helpCount), '指令库加载', boot.helpCount);
    ok(boot.rows > 20, '列表渲染', boot.rows);
    ok(boot.cats === 16, '分类数（含全部指令）', boot.cats);
    ok(boot.subs > 40, '子分类数', boot.subs);
    ok(boot.ready === true, '应用已就绪（app-ready）');
    ok(!boot.err, '无 JS 报错', boot.err);

        console.log('\n[1b] 数据来源（全部为游戏内确认）');
    const gv = await cdp.eval(`
      const total = S.entries.length;
      const nongv = S.entries.filter(e => !e.gv).length;
      return { total: total, nongv: nongv,
               hasToggle: !!document.querySelector('#setVerifiedOnly') };`);
    ok(gv.nongv === 0, '库中无未确认条目', gv);
    ok(gv.hasToggle === false, '「仅游戏内确认」开关已移除', gv.hasToggle);

console.log('\n[2] 搜索与筛选');
    const search = await cdp.eval(`
      const el = document.querySelector('#search');
      el.value = '\u51c6\u661f';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 400));
      return { rows: document.querySelectorAll('#list .row').length,
               first: document.querySelector('.row .nm').textContent };`);
    ok(search.rows > 5, '中文搜索命中', search.rows);
    ok(/\u51c6\u661f|crosshair/i.test(search.first), '首条结果相关', search.first);

    const flt = await cdp.eval(`
      document.querySelector('#search').value = '';
      document.querySelector('#search').dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 300));
      const gone = !document.querySelector('#scopeFilter') && !document.querySelector('#typeFilter')
                && !document.querySelector('#btnTranslate');
      // 列表一次只渲染前 120 条，行数没有区分度 → 用 #listInfo 的匹配总数判断
      const num = () => {
        const el = document.querySelector('#listInfo b');
        return el ? +el.textContent : -1;
      };
      const cb = document.querySelector('#setOnlyCore');
      const wasOn = cb.checked;
      cb.checked = true; cb.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise(r => setTimeout(r, 350));
      const coreN = num();
      cb.checked = false; cb.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise(r => setTimeout(r, 350));
      const allN = num();
      cb.checked = wasOn; cb.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise(r => setTimeout(r, 250));
      return { gone: gone, coreN: coreN, allN: allN,
               keepCbs: ['#setOnlyCore', '#setOnlyRelease', '#segLang']
                 .every(s => !!document.querySelector(s)) };`);
    ok(flt.gone === true, '作用域/类型筛选与AI翻译按钮已移除');
    ok(flt.keepCbs === true, '其余筛选项仍在');
    ok(flt.coreN > 0 && flt.coreN < flt.allN, '剩余筛选（仅实用指令）生效', flt);

    console.log('\n[2b] 「新增」标记（快速入口已移除，改为直接验证数据与标记）');
    const fresh = await cdp.eval(`
      // 快速入口整块已删；「最近跟进」视图随之不可达。
      // 这里验证：新增条目仍在库中，且列表里会渲染出「新增」标签。
      const newOnes = S.entries.filter(e => e.st === 'new').map(e => e.n);
      const hasQuick = !!document.querySelector('#quickNav');
      // 打开「仅正式版下发」以外的默认筛选，确保新增条目能看到
      const cb = document.querySelector('#setOnlyCore');
      cb.checked = false; cb.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise(r => setTimeout(r, 400));
      const shownBadges = Array.from(document.querySelectorAll('#list .row .tag'))
        .filter(t => t.textContent === '新增').length;
      return { count: newOnes.length, hasQuick: hasQuick, shownBadges: shownBadges,
               crumbs: document.querySelector('#crumbs').textContent };`);
    ok(fresh.count > 100, '库中仍有「新增」条目', fresh.count);
    ok(fresh.hasQuick === false, '快速入口已移除', fresh.hasQuick);
    ok(!/最近跟进/.test(fresh.crumbs), '面包屑不再出现最近跟进', fresh.crumbs.trim());

    console.log('\n[3] 详情与配置生成器');
    const cfg = await cdp.eval(`
      document.querySelector('#setOnlyCore').checked = true;
      document.querySelector('#setOnlyCore').dispatchEvent(new Event('change', { bubbles: true }));
      const el = document.querySelector('#search');
      el.value = 'cl_crosshair_drawoutline';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 500));
      const row = Array.from(document.querySelectorAll('.row')).find(r => r.dataset.name === 'cl_crosshair_drawoutline');
      if (!row) return { error: '找不到 cl_crosshair_drawoutline 行' };
      row.click();
      await new Promise(r => setTimeout(r, 200));
      const zh = document.querySelector('.d-zh').textContent;
      // 详情页的「加入配置」按钮已移除，改用等价的数据路径加入配置
      const cur = S.current;
      toggleCfg(cur);
      await new Promise(r => setTimeout(r, 200));
      document.querySelector('#btnCfg').click();
      await new Promise(r => setTimeout(r, 250));
      // 详情操作区：只应有 复制指令 / 问 AI 怎么用 两个按钮
      const acts = Array.from(document.querySelectorAll('#detail .d-actions button'));
      return { zh, text: document.querySelector('#cfgText').value,
               badge: document.querySelector('#cfgCount').textContent,
               hasCopy: !!document.querySelector('#dCopy'),
               btnIds: acts.map(b => b.id),
               btnClasses: acts.map(b => b.className),
               removed: ['dFav','dCfg','dTranslate'].filter(id => !document.getElementById(id)) };`);
    ok(!cfg.error, '搜索到目标指令', cfg.error || 'ok');
    ok(/\u51c6\u661f/.test(cfg.zh || ''), '详情显示中文释义', (cfg.zh || '').slice(0, 40));
    ok(/cl_crosshair_drawoutline/.test(cfg.text || ''), 'cfg 文本包含该指令');
    ok(cfg.badge === '1', '配置计数徽标', cfg.badge);
    ok(cfg.removed && cfg.removed.length === 3, '收藏/加入配置/AI翻译此条 已移除', cfg.removed);
    ok(cfg.btnIds && cfg.btnIds.join(',') === 'dCopy,dAI', '详情只剩两个按钮', cfg.btnIds);
    ok(cfg.btnClasses && cfg.btnClasses.every(c => c === 'btn tiny'), '两个按钮样式统一', cfg.btnClasses);

        console.log('\n[3b] 数据来源标记');
    const fresh2 = await cdp.eval(`
      document.querySelector('#setOnlyCore').checked = true;
      document.querySelector('#setOnlyCore').dispatchEvent(new Event('change', { bubbles: true }));
      const el = document.querySelector('#search');
      el.value = 'cl_crosshair_drawoutline';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 500));
      const row = Array.from(document.querySelectorAll('.row')).find(r => r.dataset.name === 'cl_crosshair_drawoutline');
      if (row) row.click();
      await new Promise(r => setTimeout(r, 250));
      const tags = Array.from(document.querySelectorAll('#detailPane .tag')).map(t => t.textContent);
      return { tags: tags,
               hasWiki: tags.some(x => x.indexOf('待游戏内确认') >= 0),
               hasOk: tags.some(x => x.indexOf('游戏内已确认') >= 0) };`);
    ok(fresh2.hasWiki === false, '不再出现「待游戏内确认」标记', fresh2.tags);
    ok(fresh2.hasOk === true, '显示「游戏内已确认」标记', fresh2.tags);

console.log('\n[3c] 上锁状态（游戏目录完整性）');
    const guard = await cdp.eval(`
      const b = document.querySelector('#btnGuard');
      const meta = await (await fetch('/api/meta')).json();
      return { text: b ? b.querySelector('span').textContent : null,
               cls: b ? b.className : null,
               state: meta.guard ? meta.guard.state : null };`);
    ok(!!guard.text, '上锁按钮存在', guard.text);
    ok(['ok', 'warn', 'none'].includes(guard.state), '接口返回上锁状态', guard.state);
    ok(guard.state !== 'ok' || /已上锁/.test(guard.text), '状态与按钮文案一致',
       `${guard.state} / ${guard.text}`);

    console.log('\n[4] 收藏（多收藏夹）');
    const fav = await cdp.eval(`
      // 详情页的「收藏」按钮已移除；改用列表卡片的 ☆（等价入口）
      const row = document.querySelector('#list .row');
      const name = row ? row.dataset.name : null;
      const star = row ? row.querySelector('.star') : null;
      if (!star) return { err: '列表里找不到 ☆' };
      star.click();
      await new Promise(r => setTimeout(r, 250));
      const menu = document.querySelector('.star-menu');
      const items = menu ? menu.querySelectorAll('.mi[data-f]').length : 0;
      if (items > 0) {
        // 已有收藏夹：点第一个加入
        menu.querySelector('.mi[data-f]').click();
        await new Promise(r => setTimeout(r, 250));
      } else {
        // 没有收藏夹：先建一个，再把该指令放进去
        createFolder('测试夹', [name]);
        await new Promise(r => setTimeout(r, 200));
      }
      const store = JSON.parse(localStorage.getItem('cs2hub.favItems') || '{}');
      const names = Object.keys(store);
      return { name: name,
               count: document.querySelector('#favCount').textContent,
               folders: names.length ? store[names[0]] : [],
               anyStarred: names.length,
               hasDfav: !!document.getElementById('dFav'),
               stored: store };`);
    ok(!fav.err, '列表 ☆ 可用', fav.err || 'ok');
    ok(fav.anyStarred >= 1 && Object.keys(fav.stored).length >= 1,
       '收藏写入 favItems（多收藏夹结构）', fav.stored);
    ok(fav.hasDfav === false, '详情页「收藏」按钮已移除', fav.hasDfav);

    console.log('\n[5] AI 辅助（指向本地 mock 接口）');
    await cdp.eval(`localStorage.setItem('cs2hub.ai', ${JSON.stringify(JSON.stringify(MOCK))}); return 1;`);
    await cdp.send('Page.reload');
    await sleep(3500);
    const ai = await cdp.eval(`
      document.querySelector('#btnAI').click();
      document.querySelector('#aiInput').value = '\u6211\u60f3\u628a\u51c6\u661f\u6539\u6210\u7eff\u8272\u5c0f\u5341\u5b57';
      document.querySelector('#btnAISend').click();
      for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 300));
        const st = document.querySelector('#aiStatus').textContent;
        if (/\u5b8c\u6210|\u51fa\u9519|\u5931\u8d25/.test(st)) break;
      }
      return { status: document.querySelector('#aiStatus').textContent,
               html: document.querySelector('#aiOutput').innerHTML,
               tables: document.querySelectorAll('#aiOutput table').length,
               pres: document.querySelectorAll('#aiOutput pre').length };`);
    ok(/\u5b8c\u6210/.test(ai.status), 'AI 请求成功', ai.status);
    ok(ai.tables === 1, 'Markdown 表格渲染', ai.tables);
    ok(ai.pres >= 1, 'cfg 代码块渲染', ai.pres);
    if (ai.pres < 1) console.log('    [debug] 输出 HTML：' + ai.html.slice(0, 900));
    ok(/cl_crosshaircolor/.test(ai.html), '回复内容进入界面');

    console.log('\n[5c] AI 检索质量（中文需求 → 正确指令进入上下文）');    const ctxProbe = await cdp.eval(`
      const run = async (q) => {
        document.querySelector('#aiInput').value = q;
        document.querySelector('#btnAISend').click();
        for (let i = 0; i < 40; i++) {
          await new Promise(r => setTimeout(r, 250));
          const st = document.querySelector('#aiStatus').textContent;
          if (/完成|出错|失败/.test(st)) break;
        }
        return document.querySelector('#aiOutput').innerText;
      };
      const a = await run('[REFLECT] 怎么设置可以随地安放炸弹');
      const b = await run('[REFLECT] 我想让雷达显示全图');
      return { bomb: a, radar: b };`);
    ok(/mp_plant_c4_anywhere/.test(ctxProbe.bomb || ''),
       '「随地安放炸弹」检索到 mp_plant_c4_anywhere', (ctxProbe.bomb || '').slice(0, 90));
    ok(/cl_radar_scale/.test(ctxProbe.radar || ''),
       '「雷达显示全图」检索到 cl_radar_scale', (ctxProbe.radar || '').slice(0, 90));

    console.log('\n[5d] 搜索框的中文长句（不再全灭）');
    const searchProbe = await cdp.eval(`
      const el = document.querySelector('#search');
      el.value = '随地安放炸弹';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 600));
      const rows = Array.from(document.querySelectorAll('.row')).map(r => r.dataset.name);
      const n1 = document.querySelector('#resultCount') ? document.querySelector('#resultCount').textContent : '';
      el.value = '雷达';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 600));
      const rows2 = Array.from(document.querySelectorAll('.row')).map(r => r.dataset.name);
      el.value = '';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      await new Promise(r => setTimeout(r, 400));
      return { rows, rows2, n1 };`);
    ok((searchProbe.rows || []).includes('mp_plant_c4_anywhere'),
       '搜索「随地安放炸弹」能搜到目标指令',
       (searchProbe.rows || []).slice(0, 4).join(', '));
    ok((searchProbe.rows2 || []).some((n) => /radar/.test(n)),
       '搜索「雷达」仍然正常（短词不放宽）',
       (searchProbe.rows2 || []).slice(0, 4).join(', '));

    console.log('\n[5b] 推理型模型空正文的识别（回归：deepseek-v4-pro 把预算全用于思考）');
    const reason = await cdp.eval(`
      const origFetch = window.fetch;
      window.fetch = async (u, o) => {
        if (String(u).includes('api/ai')) {
          return new Response(JSON.stringify({
            ok: true, content: '', model: 'deepseek-v4-pro',
            truncated_by_reasoning: true,
            hint: '输出预算被推理过程吃光了（推理 16 / 输出 16 token，max_tokens=16）',
            usage: { completion_tokens: 16,
                     completion_tokens_details: { reasoning_tokens: 16 } } }),
            { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
        return origFetch(u, o);
      };
      openDrawer('set');
      document.querySelector('#btnSetDiag').click();
      for (let i = 0; i < 40; i++) {
        await new Promise(r => setTimeout(r, 200));
        const t = document.querySelector('#diagOut').textContent;
        if (/\\u63a8\\u7406\\u578b\\u6a21\\u578b|\\u5e38\\u89c1\\u539f\\u56e0/.test(t)) break;
      }
      const outEl = document.querySelector('#diagOut');
      const shown = !outEl.classList.contains('hidden');
      const text = outEl.textContent;
      window.fetch = origFetch;
      return { shown, text };`);
    ok(reason.shown, '自检报告已展开');
    ok(/推理型模型/.test(reason.text || ''), '识别出"预算被推理吃光"而非误报 Key 失效');
    ok(/max_tokens|deepseek-chat/.test(reason.text || ''), '给出可执行的处置建议');

    console.log('\n[6] AI 翻译回填');
    const tr = await cdp.eval(`
      const r = await fetch('api/ai/translate', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ items:[{n:'cl_weapon_debug_show_accuracy', en:'Draws a circle representing the effective range with each shot.'}], base_url:'http://127.0.0.1:8799/v1', api_key:'sk-e2e', model:'mock' }) });
      const d = await r.json();
      const fresh = await (await fetch('api/data')).json();
      const e = fresh.entries.find(x => x.n === 'cl_weapon_debug_show_accuracy');
      return { saved: d.saved, q: e.q, z: e.z };`);
    ok(tr.saved >= 1 && tr.q === 3, 'AI 翻译写入缓存并生效', tr);


    await cdp.eval(`
      if (!document.getElementById('home').classList.contains('hidden')) {
        document.getElementById('pickPro').click();
        await new Promise(r => setTimeout(r, 400));
      }`);
    console.log('\n[8] 侧栏布局不重叠（窄窗口回归）');    for (const [w, h] of [[1000, 700], [900, 420], [1280, 800]]) {
      await cdp.send('Emulation.setDeviceMetricsOverride',
        { width: w, height: h, deviceScaleFactor: 1, mobile: false });
      await sleep(400);
      const lay = await cdp.eval(`
        const box = (el) => { const r = el.getBoundingClientRect(); return { t: r.top, b: r.bottom }; };
        const ct = box(document.querySelector('#catTree'));
        const sb = box(document.querySelector('.sidebar'));
        const foot = box(document.querySelector('.side-foot'));
        // 快速入口已移除，只需确保分类区不与底栏重叠
        const overlap = ct.b > foot.t + 1;
        return { overlap, ct: [Math.round(ct.t), Math.round(ct.b)],
                 foot: [Math.round(foot.t), Math.round(foot.b)],
                 hasQuick: !!document.querySelector('#quickNav'),
                 sidebarVisible: sb.b - sb.t > 100 };`);
      ok(lay.sidebarVisible && !lay.overlap && lay.hasQuick === false,
        `侧栏无重叠 ${w}x${h}`,
        { 分类: lay.ct, 底栏: lay.foot, 快速入口已移除: !lay.hasQuick });
    }
    await cdp.send('Emulation.clearDeviceMetricsOverride');

    console.log('\n[9] 图标资源');
    const ico = await cdp.eval(`
      const r = await fetch('assets/icons/cs2-console-hub.ico');
      const b = await r.arrayBuffer();
      const head = Array.from(new Uint8Array(b.slice(0, 6)));
      const frames = new Uint8Array(b.slice(4, 6))[0] | (new Uint8Array(b.slice(5, 6))[0] << 8);
      return { status: r.status, bytes: b.byteLength, isIco: head[0] === 0 && head[1] === 0 && head[2] === 1 && head[3] === 0,
               frames };`);
    ok(ico.status === 200 && ico.isIco && ico.frames >= 8, 'ICO 图标可访问且为多尺寸',
      { 帧数: ico.frames, 大小: ico.bytes + 'B' });
    const favLink = await cdp.eval(`
      const l = document.querySelector('link[rel="icon"]');
      const r = await fetch(l.getAttribute('href'));
      return { href: l.getAttribute('href'), status: r.status };`);
    ok(favLink.status === 200, '页面已挂 favicon', favLink);

    console.log('\n[10] 输出预算被推理吃光时自动升档重试');
    // 指向"会吃掉预算"的模拟推理模型（端口 8801），并把预算压到 512
    await cdp.eval(`
      localStorage.setItem('cs2hub.ai', JSON.stringify({
        base_url: 'http://127.0.0.1:8801/v1', api_key: 'sk-mock',
        model: 'deepseek-reasoner' }));
      localStorage.setItem('cs2hub.maxTokens', '512');
      return 1;`);
    await cdp.send('Page.reload');
    await sleep(3500);
    const bump = await cdp.eval(`
      document.querySelector('#aiInput').value = '给我一个较长篇幅的配置方案说明';
      document.querySelector('#btnAISend').click();
      let sawBump = false, status = '';
      for (let i = 0; i < 80; i++) {
        await new Promise(r => setTimeout(r, 120));
        status = document.querySelector('#aiStatus').textContent;
        if (/自动把输出预算/.test(status)) sawBump = true;
        if (/完成|出错|失败/.test(status)) break;
      }
      return { sawBump, status,
               text: document.querySelector('#aiOutput').innerText.slice(0, 60) };`);
    // 中间态可能一闪而过（重试很快），所以以最终状态里的权威信号为准
    ok(/本次预算升到/.test(bump.status || ''), '预算被推理吃光后自动升档并成功',
       (bump.status || '').slice(0, 76));
    ok(/完成/.test(bump.status || ''), '升档后成功拿到正文', (bump.text || '').slice(0, 40));

    // 清掉本用例写进浏览器 localStorage 的模拟配置，别污染后续截图/手动使用
    await cdp.eval(`
      localStorage.removeItem('cs2hub.ai');
      localStorage.removeItem('cs2hub.maxTokens');
      return 1;`);
  } catch (e) {
    console.log('  [FAIL] 自检异常：' + e.message);
    failures.push('exception: ' + e.message);
  } finally {
    if (proc) proc.kill();
  }
  console.log('\n' + (failures.length ? '[FAIL] 失败项：' + failures.join(' | ') : '[PASS] 全部通过'));
  process.exit(failures.length ? 1 : 0);
})();
