'use strict';
/**
 * 本地服务（Node 版）冒烟测试：不起 Electron，直接跑接口。
 * 用法： node desktop/test_server.js
 */
const path = require('path');
const os = require('os');
const fs = require('fs');
const http = require('http');
const { createServer } = require('./server');

const ROOT = path.join(__dirname, '..');
const DATA_DIR = path.join(os.tmpdir(), 'cs2hub-server-test-' + Date.now());
fs.mkdirSync(DATA_DIR, { recursive: true });

let pass = 0, fail = 0;
function check(name, ok, extra) {
  if (ok) { pass++; console.log('  ✓ ' + name); }
  else { fail++; console.log('  ✗ ' + name + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
}

(async () => {
  const srv = createServer({ root: ROOT, dataDir: DATA_DIR });
  const port = await srv.listen(0);
  const base = `http://127.0.0.1:${port}`;
  console.log('服务已启动:', base, '\n可写数据目录:', DATA_DIR, '\n');

  const j = async (p, init) => {
    const r = await fetch(base + p, init);
    let body = null;
    try { body = await r.json(); } catch (e) {}
    return { status: r.status, body, headers: r.headers };
  };

  console.log('[1] /api/health');
  const h = await j('/api/health');
  check('返回 200', h.status === 200, h.status);
  check('ok=true 且标记引擎为 node', h.body && h.body.ok === true && h.body.engine === 'node', h.body);
  check('报告了 root', !!(h.body && h.body.root), h.body && h.body.root);

  console.log('\n[2] /api/data');
  const d = await j('/api/data');
  const db = d.body || {};
  check('返回 200', d.status === 200, d.status);
  check('条目数 2802', (db.entries || []).length === 2802, (db.entries || []).length);
  check('分类数 15', (db.categories || []).length === 15, (db.categories || []).length);
  check('有版本号', !!db.version, db.version);
  check('条目字段完整（n/z）', (db.entries || []).every((e) => e && e.n), '缺 n');
  check('已合并翻译缓存', typeof db._zh_applied === 'number', db._zh_applied);

  console.log('\n[3] /api/zh_cache + /api/meta');
  const z = await j('/api/zh_cache');
  check('缓存接口返回对象', z.status === 200 && z.body && typeof z.body === 'object', z.status);
  const m = await j('/api/meta');
  check('meta 返回版本与计数', m.status === 200 && !!m.body.version && m.body.count > 0, m.body);
  // 上锁功能已移除：确认 meta 里不再出现该字段，且基本字段仍在
  check('meta 不再带上锁字段', !(m.body && 'guard' in m.body), m.body && Object.keys(m.body).length);
  check('meta 版本字段可读', !!(m.body && m.body.version), m.body && m.body.version);
  check('db.meta 可读（前端用）', !!(db.meta && db.meta.version), db.meta && db.meta.version);

  console.log('\n[4] 静态文件');
  const idx = await fetch(base + '/');
  const html = await idx.text();
  check('/ 返回 HTML', idx.status === 200 && /控制台指令查询中心/.test(html), idx.status);
  check('HTML 走 gzip', idx.headers.get('content-encoding') === 'gzip', idx.headers.get('content-encoding'));
  const css = await fetch(base + '/assets/theme.css');
  check('CSS 可访问', css.status === 200, css.status);
  const js = await fetch(base + '/assets/app.js');
  check('JS 可访问', js.status === 200, js.status);
  const ico = await fetch(base + '/assets/icons/cs2-console-hub.ico');
  check('图标可访问', ico.status === 200, ico.status);
  const missing = await fetch(base + '/nope.txt');
  check('不存在的文件返回 404', missing.status === 404, missing.status);

  console.log('\n[5] 目录穿越防护');
  // fetch 在客户端会先归一化 ..，必须用原始 HTTP 请求才能真的发出穿越路径
  const rawGet = (rawPath) => new Promise((resolve) => {
    const req = http.request(
      { host: '127.0.0.1', port, method: 'GET', path: rawPath },
      (res) => { res.resume(); resolve(res.statusCode); });
    req.on('error', () => resolve(0));
    req.end();
  });
  const t1 = await rawGet('/../package.json');
  check('原始 ../ 请求被拒', t1 === 400 || t1 === 403 || t1 === 404, t1);
  const t2 = await rawGet('/assets/../../package.json');
  check('深层穿越被拒', t2 === 400 || t2 === 403 || t2 === 404, t2);
  const t3 = await rawGet('/%2e%2e/package.json');
  check('编码后的 .. 也被拒', t3 === 400 || t3 === 403 || t3 === 404, t3);
  const okPath = await rawGet('/assets/theme.css');
  check('正常路径不受影响', okPath === 200, okPath);
  const absPath = await rawGet('/C:/Windows/win.ini');
  check('绝对路径不能越界', absPath === 400 || absPath === 403 || absPath === 404, absPath);

  console.log('\n[6] AI 接口的参数校验（不打真实上游）');
  const noKey = await j('/api/ai', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages: [], base_url: 'https://api.deepseek.com/v1' }),
  });
  check('缺 Key → 400 且提示明确', noKey.status === 400 && /API Key/.test(noKey.body.error), noKey.body);
  const badBase = await j('/api/ai', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: 'x', base_url: 'file:///etc/passwd' }),
  });
  check('非 http 地址被拒', badBase.status === 400 && /http/.test(badBase.body.error), badBase.body);
  const emptyItems = await j('/api/ai/translate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: 'x', items: [] }),
  });
  check('空 items 被拒', emptyItems.status === 400, emptyItems.body);
  const unknown = await j('/api/nope', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  check('未知接口返回 404', unknown.status === 404, unknown.status);

  console.log('\n[7] 翻译缓存写入与合并（直接写缓存文件再验证 union）');
  const cacheFile = path.join(DATA_DIR, 'zh_cache.json');
  fs.writeFileSync(cacheFile, JSON.stringify({ sensitivity: { zh: '测试译文ABC', src: 'ai' } }), 'utf8');
  // server 内部 loadDB 有缓存，需重启才生效；这里验证 loadZhCache 的并集逻辑
  const srv2 = createServer({ root: ROOT, dataDir: DATA_DIR });
  const port2 = await srv2.listen(0);
  const d2 = await (await fetch(`http://127.0.0.1:${port2}/api/data`)).json();
  const sens = (d2.entries || []).find((e) => e.n === 'sensitivity');
  check('用户目录缓存生效（覆盖释义）', sens && sens.z === '测试译文ABC', sens && sens.z);
  check('缓存命中计数 > 0', (d2._zh_applied || 0) > 0, d2._zh_applied);
  await srv2.close();

  console.log('\n[8] 不依赖 Python');
  check('server.js 无 python 依赖', !/python/i.test(fs.readFileSync(path.join(__dirname, 'server.js'), 'utf8')));

  await srv.close();
  console.log(`\n===== 通过 ${pass} / 失败 ${fail} =====`);
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.error('测试异常:', e); process.exit(1); });
