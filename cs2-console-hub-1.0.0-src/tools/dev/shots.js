/**
 * 文档截图脚本（开发用）：截主界面 + AI 面板两张图到 docs/
 * 前置： tools/server.py 正在运行
 * 用法： node tools/dev/shots.js
 */
const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const EDGE = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].find((p) => fs.existsSync(p));

const PORT = 9223;
const APP = 'http://127.0.0.1:8788/';
const OUT = path.join(__dirname, '..', '..', 'docs');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function get(url) {
  return new Promise((res, rej) => {
    http.get(url, (r) => { let d = ''; r.on('data', (c) => d += c); r.on('end', () => res(d)); }).on('error', rej);
  });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const userDir = path.join(process.env.TEMP, 'cs2hub-shots');
  fs.rmSync(userDir, { recursive: true, force: true });
  const proc = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars',
    '--window-size=1680,1000', `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: 'ignore' });

  let target = null;
  for (let i = 0; i < 40 && !target; i++) {
    await sleep(500);
    try {
      const list = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));
      target = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
    } catch (e) { /* 等待 */ }
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((res) => { ws.onopen = res; });
  let id = 0; const pending = new Map();
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  };
  const send = (method, params = {}) => {
    const i = ++id; ws.send(JSON.stringify({ id: i, method, params }));
    return new Promise((r) => pending.set(i, r));
  };
  const evalJs = (expr) => send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  const shot = async (name) => {
    const r = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(path.join(OUT, name), Buffer.from(r.data, 'base64'));
    console.log('  saved docs/' + name);
  };

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1680, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: APP });
  await sleep(4000);

  // 图 1：主界面
  await evalJs(`document.querySelector('#search').value='';
    document.querySelector('#search').dispatchEvent(new Event('input',{bubbles:true})); 1`);
  await sleep(700);
  await shot('screenshot-main.png');

  // 图 2：AI 面板（先写入占位 Key，否则会跳到接口设置抽屉）
  await evalJs(`localStorage.setItem('cs2hub.ai', JSON.stringify(
      { base_url:'https://api.deepseek.com/v1', api_key:'sk-demo-placeholder', model:'deepseek-chat' })); 1`);
  await send('Page.reload');
  await sleep(4000);
  await evalJs(`
    document.querySelector('#btnAI').click();
    document.querySelector('#aiInput').value = '\u6211\u662f 800 DPI\uff0c\u60f3\u628a\u51c6\u661f\u6539\u6210\u7eff\u8272\u5c0f\u5341\u5b57\u3001\u9759\u6001\u4e0d\u6269\u6563\uff0c\u518d\u8ba9\u96f7\u8fbe\u80fd\u770b\u5168\u56fe';
    document.querySelector('#btnAISend').click(); 1`);
  await sleep(1200);
  await evalJs(`
    document.querySelector('#aiStatus').className='ai-status ok';
    document.querySelector('#aiStatus').textContent='\u5b8c\u6210 \u00b7 \u6a21\u578b deepseek-chat \u00b7 \u7528\u91cf 812 tokens';
    document.querySelector('#aiOutput').innerHTML = \`
      <p>\u6309\u4f60\u7684\u9700\u6c42\uff0c\u9700\u8981\u52a8\u7528\u5230 <b>\u51c6\u661f</b>\u3001<b>\u96f7\u8fbe/HUD</b>\u3001<b>\u9f20\u6807</b> \u4e09\u5757\u8bbe\u7f6e\u3002</p>
      <h3>\u4e00\u3001\u76f8\u5173\u6307\u4ee4</h3>
      <table><tr><th>\u6307\u4ee4</th><th>\u63a8\u8350\u503c</th><th>\u4f5c\u7528</th></tr>
      <tr><td><code>cl_crosshaircolor</code></td><td>1</td><td>\u51c6\u661f\u53d8\u7eff</td></tr>
      <tr><td><code>cl_crosshairstyle</code></td><td>4</td><td>\u7ecf\u5178\u9759\u6001 + \u4e2d\u5fc3\u70b9</td></tr>
      <tr><td><code>cl_crosshairsize</code></td><td>2.5</td><td>\u5c0f\u5341\u5b57</td></tr>
      <tr><td><code>cl_crosshairgap</code></td><td>-1</td><td>\u6536\u7d27\u4e2d\u5fc3\u95f4\u8ddd</td></tr>
      <tr><td><code>cl_radar_always_centered</code></td><td>0</td><td>\u96f7\u8fbe\u663e\u793a\u5168\u56fe</td></tr>
      <tr><td><code>cl_radar_scale</code></td><td>0.35</td><td>\u7f29\u5c0f\u6bd4\u4f8b\uff0c\u770b\u5f97\u66f4\u8fdc</td></tr>
      <tr><td><code>sensitivity</code></td><td>1.55</td><td>800 DPI \u4e0b eDPI \u7ea6 1240</td></tr></table>
      <h3>\u4e8c\u3001\u53ef\u76f4\u63a5\u7c98\u8d34\u7684 cfg</h3>
      <pre><code>// \u51c6\u661f\uff1a\u7eff\u8272\u9759\u6001\u5c0f\u5341\u5b57
cl_crosshairstyle 4
cl_crosshaircolor 1
cl_crosshairsize 2.5
cl_crosshairgap -1
cl_crosshairthickness 1
cl_crosshair_drawoutline 1

// \u96f7\u8fbe\u770b\u5168\u56fe
cl_radar_always_centered 0
cl_radar_scale 0.35

// \u9f20\u6807
sensitivity 1.55
zoom_sensitivity_ratio 1
host_writeconfig</code></pre>
      <p><b>\u6ce8\u610f\uff1a</b>\u4ee5\u4e0a\u5168\u662f <code>cl_</code> \u5ba2\u6237\u7aef\u6307\u4ee4\uff0c\u5b98\u65b9\u5339\u914d\u4e0b\u76f4\u63a5\u751f\u6548\uff0c\u4e0d\u6d89\u53ca <code>sv_cheats</code>\u3002</p>\`;
    1`);
  await sleep(500);
  await shot('screenshot-ai.png');

  proc.kill();
  ws.close();
  process.exit(0);
})();
