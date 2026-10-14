'use strict';
/**
 * 在【打包后的应用】内跑 e2e，验证 asar 路径、资源查找、服务启动都正常。
 * 用法： node desktop/run_e2e_packaged.js
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const ROOT = path.join(__dirname, '..');
const DEBUG_PORT = '9502';
const EXE = path.join(ROOT, 'dist', 'win-unpacked', 'CS2 控制台指令查询中心.exe');

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
  if (!fs.existsSync(EXE)) { console.error('找不到打包后的 exe：' + EXE); process.exit(1); }
  console.log('[1] 启动打包后的应用：' + path.basename(EXE));

  const app = spawn(EXE, [], {
    cwd: path.dirname(EXE),
    env: cleanEnv({ CS2HUB_DEBUG_PORT: DEBUG_PORT }),
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
  if (!page) {
    console.error('[!] 应用未就绪，退出码=' + app.exitCode);
    if (err) console.error(err.slice(0, 2000));
    try { app.kill(); } catch (e) {}
    process.exit(1);
  }
  const appUrl = page.url.split('#')[0];
  console.log('[2] 应用地址：' + appUrl);

  // 直接验一下服务与数据（打包后最容易出问题的就是资源路径）
  const health = JSON.parse(await get(appUrl + 'api/health'));
  console.log('[3] /api/health →', JSON.stringify(health));
  const db = JSON.parse(await get(appUrl + 'api/data'));
  console.log('[4] /api/data →', db.entries.length, '条 ·', db.categories.length, '分类 ·',
    'meta.guard=' + ((db.meta && db.meta.guard && db.meta.guard.state) || 'n/a'));

  const okRes = health.ok === true && db.entries.length === 2802 && !!(db.meta && db.meta.guard);
  console.log('[5] 打包后资源与接口自检：' + (okRes ? '通过' : '失败'));
  if (!okRes) { try { app.kill(); } catch (e) {} process.exit(1); }

  console.log('[6] 在该窗口内跑 e2e …\n' + '-'.repeat(60));
  const e2e = spawn(process.execPath, [path.join(ROOT, 'tools', 'dev', 'e2e.js')], {
    cwd: ROOT,
    env: cleanEnv({ CS2HUB_E2E_ATTACH: '1', CS2HUB_E2E_PORT: DEBUG_PORT, CS2HUB_E2E_URL: appUrl }),
    stdio: 'inherit',
  });
  const code = await new Promise((r) => e2e.on('exit', r));
  console.log('-'.repeat(60));
  try { app.kill(); } catch (e) {}
  console.log('\n[e2e 退出码] ' + code);
  process.exit(code || 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
