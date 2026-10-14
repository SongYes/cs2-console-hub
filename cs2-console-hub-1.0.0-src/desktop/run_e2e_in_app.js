'use strict';
/**
 * 在 Electron 应用内跑完整 e2e（附加模式）。
 *
 * 关键：本机环境变量 ELECTRON_RUN_AS_NODE=1 会让 Electron 退化成纯 Node 进程，
 * 必须在子进程里清掉，否则 require('electron').app 为 undefined。
 *
 * 用法： node desktop/run_e2e_in_app.js
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const ROOT = path.join(__dirname, '..');
const DEBUG_PORT = process.env.CS2HUB_E2E_PORT || '9500';
const ELECTRON = path.join(ROOT, 'node_modules', 'electron', 'dist', 'electron.exe');

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
  if (!fs.existsSync(ELECTRON)) {
    console.error('找不到 electron.exe：' + ELECTRON);
    process.exit(1);
  }

  console.log('[1] 启动 Electron（清掉 ELECTRON_RUN_AS_NODE）…');
  const app = spawn(ELECTRON, ['.'], {
    cwd: ROOT,
    env: cleanEnv({ CS2HUB_DEBUG_PORT: DEBUG_PORT }),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let appErr = '';
  app.stderr.on('data', (c) => { appErr += c.toString(); });
  app.stdout.on('data', () => {});

  let ready = false;
  for (let i = 0; i < 40 && !ready; i++) {
    await sleep(500);
    if (app.exitCode !== null) break;
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${DEBUG_PORT}/json/list`));
      ready = list.some((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    } catch (e) {}
  }

  if (!ready) {
    console.error('[!] Electron 未就绪。退出码=' + app.exitCode);
    if (appErr) console.error(appErr.slice(0, 2000));
    try { app.kill(); } catch (e) {}
    process.exit(1);
  }
  console.log('[2] 窗口已就绪，调试端口 ' + DEBUG_PORT);

  // 取出实际 URL（随机端口）
  const list = JSON.parse(await get(`http://127.0.0.1:${DEBUG_PORT}/json/list`));
  const page = list.find((t) => t.type === 'page' && /^http:\/\/127\.0\.0\.1:\d+/.test(t.url));
  const appUrl = page ? page.url.split('#')[0] : null;
  console.log('[3] 应用地址：' + appUrl);
  if (!appUrl) { try { app.kill(); } catch (e) {} process.exit(1); }

  console.log('[4] 在该窗口内跑 e2e …\n' + '-'.repeat(60));
  const e2e = spawn(process.execPath, [path.join(ROOT, 'tools', 'dev', 'e2e.js')], {
    cwd: ROOT,
    env: cleanEnv({
      CS2HUB_E2E_ATTACH: '1',
      CS2HUB_E2E_PORT: DEBUG_PORT,
      CS2HUB_E2E_URL: appUrl,
    }),
    stdio: 'inherit',
  });
  const code = await new Promise((r) => e2e.on('exit', r));
  console.log('-'.repeat(60));

  try { app.kill(); } catch (e) {}
  await sleep(800);
  console.log('\n[e2e 退出码] ' + code);
  process.exit(code || 0);
})().catch((e) => { console.error('异常:', e); process.exit(1); });
