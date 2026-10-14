'use strict';
/**
 * 本地服务（Node 版，替代 tools/server.py）
 *
 * 只保留桌面端真正需要的接口：
 *   GET  /api/health        健康检查（前端据此判断用服务模式还是离线模式）
 *   GET  /api/data          指令库（已合并 AI 翻译缓存）
 *   GET  /api/zh_cache      翻译缓存
 *   POST /api/ai/models     列出上游可用模型
 *   POST /api/ai            代理 chat/completions
 *   POST /api/ai/translate  批量翻译英文释义并写入缓存
 *
 * 设计要点：
 *   - 目录可写性分离：程序目录只读（打包进 asar），用户数据写到 userData
 *   - 翻译缓存在程序目录的 data/zh_cache.json 与 userData 之间取并集，老数据不丢
 *   - API Key 只在前端 localStorage，这里只做一次性转发，不落盘、不记日志
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.ico': 'image/x-icon',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
};

/* 可压缩的文本类型 */
const COMPRESSIBLE = /^(text\/|application\/(json|javascript|xml)|image\/svg)/;

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    return fallback;
  }
}

function writeJson(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj), 'utf8');
  fs.renameSync(tmp, file);   // 原子替换，避免写坏
}

/**
 * @param {object} opts
 * @param {string} opts.root      程序目录（含 index.html / assets）
 * @param {string} opts.dataDir   可写数据目录（userData）
 * @param {string} [opts.host]
 * @param {number} [opts.port]    0 = 自动选空闲端口
 */
function createServer(opts) {
  const root = opts.root;
  const dataDir = opts.dataDir;
  const host = opts.host || '127.0.0.1';

  const dbFile = path.join(root, 'data', 'commands.json');
  const cacheWritable = path.join(dataDir, 'zh_cache.json');
  const cacheShipped = path.join(root, 'data', 'zh_cache.json');

  /* ---------- 指令库（缓存 + 合并翻译缓存） ---------- */
  let dbCache = null;
  function loadDB() {
    if (dbCache) return dbCache;
    let db = readJson(dbFile, null);
    if (!db) {
      // 打包后 commands.json 若缺失，退回内嵌库（assets/db.js）
      db = readEmbeddedDB();
    }
    if (!db) throw new Error('未找到指令库：' + dbFile);
    applyZhCache(db);
    dbCache = db;
    return db;
  }

  function readEmbeddedDB() {
    try {
      const src = fs.readFileSync(path.join(root, 'assets', 'db.js'), 'utf8');
      const m = src.match(/window\.__CS2_DB__\s*=\s*(\{[\s\S]*\})\s*;?\s*$/);
      if (m) return JSON.parse(m[1]);
    } catch (e) {}
    return null;
  }

  /* 翻译缓存：程序目录自带的 + 用户目录新增的，取并集（用户目录优先） */
  function loadZhCache() {
    const shipped = readJson(cacheShipped, {}) || {};
    const mine = readJson(cacheWritable, {}) || {};
    return Object.assign({}, shipped, mine);
  }

  function applyZhCache(db) {
    const cache = loadZhCache();
    let n = 0;
    (db.entries || []).forEach((e) => {
      const c = cache[e.n];
      const zh = c && (typeof c === 'string' ? c : c.zh);
      if (zh && String(zh).trim()) { e.z = String(zh).trim(); e.q = 3; n++; }
    });
    db._zh_applied = n;
    return n;
  }

  /* ---------- 上游请求 ---------- */
  async function upstreamJson(url, payload, headers, timeoutMs) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs || 120000);
    try {
      const init = { method: payload ? 'POST' : 'GET', headers: Object.assign({}, headers), signal: ctrl.signal };
      if (payload) {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(payload);
      }
      const r = await fetch(url, init);
      const text = await r.text();
      let data = null;
      try { data = JSON.parse(text); } catch (e) { data = null; }
      return { status: r.status, ok: r.ok, text, data };
    } finally {
      clearTimeout(timer);
    }
  }

  const HINTS = {
    401: 'API Key 无效或已失效，请到「接口设置」重新填写',
    402: '账户余额不足，请到服务商后台充值',
    404: '模型名或接口地址不对，检查 Base URL（要带 /v1）与模型名',
    429: '触发限流或配额用尽，稍后再试或换模型',
  };

  /* ---------- 游戏目录上锁状态 ----------
     只读：读 data/integrity_baseline.json 与游戏目录文件元信息，不写任何游戏文件。
     用「大小 + mtime」做快速判据（全量哈希留给定期的 guard_check.py）。 */
  const GUARD_SENSITIVE = new Set(['.vpk', '.dll', '.exe', '.asi']);
  const GUARD_NOISE = /\\_iconcache\\|\\logs?\\|console\.log$|\.tmp$|\\csgo\\cfg\\|\\_dumps\\/i;

  function guardState() {
    const base = path.join(root, 'data', 'integrity_baseline.json');
    if (!fs.existsSync(base)) return { state: 'none', text: '未记录基线' };
    let snap;
    try { snap = JSON.parse(fs.readFileSync(base, 'utf8')); }
    catch (e) { return { state: 'none', text: '基线文件损坏' }; }

    const gameDir = snap.game_dir || '';
    if (!gameDir || !fs.existsSync(gameDir)) return { state: 'none', text: '找不到游戏目录' };

    const files = snap.files || {};
    let changed = 0, added = 0, scanned = 0;

    const walk = (dir, depth) => {
      if (depth > 12) return;
      let items;
      try { items = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return; }
      for (const it of items) {
        const full = path.join(dir, it.name);
        if (it.isDirectory()) {
          const low = it.name.toLowerCase();
          if (low === 'downloading' || low === 'shadercache') continue;
          walk(full, depth + 1);
          continue;
        }
        if (!it.isFile()) continue;
        const ext = path.extname(it.name).toLowerCase();
        if (!GUARD_SENSITIVE.has(ext)) continue;
        let rel;
        try { rel = path.relative(gameDir, full); } catch (e) { continue; }
        if (GUARD_NOISE.test(rel)) continue;
        let st;
        try { st = fs.statSync(full); } catch (e) { continue; }
        scanned++;
        const old = files[rel];
        if (!old) added++;
        else if (old.size !== st.size || old.mtime !== Math.floor(st.mtimeMs / 1000)) changed++;
      }
    };
    walk(gameDir, 0);

    if (changed || added) {
      return { state: 'warn', changed, added, scanned,
               text: '有改动（' + changed + ' 改 / ' + added + ' 增）' };
    }
    return { state: 'ok', scanned, text: '与干净基线一致' };
  }

  /* ---------- meta（版本、统计、上锁状态） ---------- */
  let metaCache = null;
  function buildMeta(db) {
    if (metaCache) return metaCache;
    const entries = db.entries || [];
    const names = entries.map((e) => e.n);
    const crypto = require('crypto');
    metaCache = {
      ok: true,
      version: db.version,
      built_at: db.generated_at,
      count: entries.length,
      core_count: entries.filter((e) => e.k).length,
      release_count: entries.filter((e) => e.r).length,
      new_count: db.new_count || entries.filter((e) => e.st === 'new').length,
      tracked_at: db.tracked_at,
      hand_zh: entries.filter((e) => e.q === 2).length,
      auto_zh: entries.filter((e) => e.q === 1).length,
      game_verified: db.game_verified || entries.filter((e) => e.gv).length,
      wiki_only: entries.filter((e) => !e.gv).length,
      cmd_count: db.cmd_count || 0,
      guard: guardState(),
      source: db.source,
      sha256: crypto.createHash('sha256')
        .update(names.slice().sort().join(',')).digest('hex').slice(0, 16),
    };
    return metaCache;
  }

  /* ---------- 游戏 cfg 目录 ----------
     候选顺序与实际安装一致；只做「解析目录」与「写入 .cfg」两件事，
     写入前严格校验目标路径必须落在 cfg 目录内。 */
  function resolveGameDir() {
    const base = path.join(root, 'data', 'integrity_baseline.json');
    const snap = readJson(base, null);
    if (snap && snap.game_dir) return snap.game_dir;
    // 基线缺失时退回常见安装位置
    const guesses = [
      'C:\\Program Files (x86)\\Steam\\steamapps\\common\\Counter-Strike Global Offensive',
      'C:\\Program Files\\Steam\\steamapps\\common\\Counter-Strike Global Offensive',
    ];
    for (const g of guesses) { if (fs.existsSync(g)) return g; }
    return null;
  }

  function resolveCfgDir() {
    const game = resolveGameDir();
    if (!game || !fs.existsSync(game)) return null;
    const cands = [
      path.join(game, 'game', 'csgo', 'cfg'),
      path.join(game, 'csgo', 'cfg'),
      path.join(game, 'game', 'cs2', 'cfg'),
      path.join(game, 'cs2', 'cfg'),
    ];
    for (const c of cands) { if (fs.existsSync(c)) return c; }
    return null;
  }

  /* 把方案/配置写成 .cfg 到游戏目录。返回实际路径供界面显示。 */
  function writeCfgToGame(body, res) {
    const cfgDir = resolveCfgDir();
    if (!cfgDir) {
      return sendJson(res, {
        ok: false, error: '没找到游戏 cfg 目录',
        hint: '请确认已安装 CS2，或在设置里改用「手动选择位置」。',
      }, 400);
    }
    let name = String(body.name || 'cs2hub').trim();
    if (!name) name = 'cs2hub';
    // 去掉非法字符与任何路径成分，杜绝目录穿越
    name = name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').replace(/^\.+/, '');
    if (!name.toLowerCase().endsWith('.cfg')) name += '.cfg';
    if (name.length > 120) name = name.slice(0, 116) + '.cfg';

    const data = String(body.data == null ? '' : body.data);
    if (!data.trim()) return sendJson(res, { ok: false, error: '内容为空' }, 400);
    if (data.length > 2 * 1024 * 1024) {
      return sendJson(res, { ok: false, error: '内容过大（超过 2MB）' }, 400);
    }

    const target = path.resolve(cfgDir, name);
    // 双保险：解析后的路径必须仍在 cfg 目录内
    if (target !== path.resolve(cfgDir) &&
        !target.startsWith(path.resolve(cfgDir) + path.sep)) {
      return sendJson(res, { ok: false, error: '目标路径越界，已拒绝' }, 400);
    }
    // 不跟随已有符号链接（若目标已存在且是符号链接，宁可拒绝）
    try {
      const lst = fs.lstatSync(target);
      if (lst.isSymbolicLink()) {
        return sendJson(res, { ok: false, error: '目标已存在且是符号链接，已拒绝覆写' }, 400);
      }
    } catch (e) { /* 不存在，正常 */ }

    try {
      // 写入时带 BOM，与配置生成器的下载内容保持一致
      fs.writeFileSync(target, '\ufeff' + data, 'utf8');
    } catch (err) {
      const msg = String(err && err.message || err);
      const denied = /EACCES|EPERM|EROFS/i.test(msg);
      return sendJson(res, {
        ok: false, error: '写入失败：' + msg.slice(0, 200),
        hint: denied
          ? '游戏目录通常需要管理员权限。可用「以管理员身份运行」重启本程序，或在设置里改用「手动选择位置」。'
          : '',
      }, 500);
    }
    return sendJson(res, { ok: true, path: target, dir: cfgDir, bytes: Buffer.byteLength(data, 'utf8') });
  }

  /* ---------- 响应工具 ---------- */
  function sendJson(res, obj, code) {
    const body = Buffer.from(JSON.stringify(obj), 'utf8');
    const head = {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'Content-Length': body.length,
    };
    res.writeHead(code || 200, head);
    res.end(body);
  }

  function sendFile(req, res, abs) {
    let st;
    try { st = fs.statSync(abs); } catch (e) { return false; }
    if (!st.isFile()) return false;
    const ext = path.extname(abs).toLowerCase();
    const type = MIME[ext] || 'application/octet-stream';
    const etag = 'W/"' + st.size.toString(16) + '-' + st.mtimeMs.toString(16) + '"';
    if (req.headers['if-none-match'] === etag) {
      res.writeHead(304, { ETag: etag });
      res.end();
      return true;
    }
    const head = {
      'Content-Type': type,
      'Cache-Control': ext === '.html' ? 'no-store' : 'public, max-age=0, must-revalidate',
      ETag: etag,
    };
    res.setHeader('ETag', etag);
    if (COMPRESSIBLE.test(type) && /\bgzip\b/.test(req.headers['accept-encoding'] || '') && st.size > 1024) {
      const gz = zlib.gzipSync(fs.readFileSync(abs));
      res.writeHead(200, Object.assign(head, {
        'Content-Encoding': 'gzip',
        'Content-Length': gz.length,
      }));
      res.end(gz);
      return true;
    }
    res.writeHead(200, Object.assign(head, { 'Content-Length': st.size }));
    fs.createReadStream(abs).pipe(res);
    return true;
  }

  function readBody(req) {
    return new Promise((resolve) => {
      const chunks = [];
      let size = 0;
      req.on('data', (c) => {
        size += c.length;
        if (size > 20 * 1024 * 1024) { req.destroy(); return; }
        chunks.push(c);
      });
      req.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf8');
        if (!raw) return resolve({});
        try { resolve(JSON.parse(raw)); } catch (e) { resolve({}); }
      });
      req.on('error', () => resolve({}));
    });
  }

  /* ---------- 业务处理 ---------- */
  async function handleAiModels(body, res) {
    const base = String(body.base_url || 'https://api.deepseek.com/v1').replace(/\/+$/, '');
    const key = String(body.api_key || '');
    if (!key) return sendJson(res, { ok: false, error: '缺少 API Key（请在界面右上角设置）' }, 400);
    if (!/^https?:\/\//.test(base)) return sendJson(res, { ok: false, error: 'base_url 必须是 http(s) 地址' }, 400);
    const r = await upstreamJson(base + '/models', null, { Authorization: 'Bearer ' + key }, 60000)
      .catch((e) => ({ status: 0, error: String(e && e.message || e) }));
    if (r.error) return sendJson(res, { ok: false, error: '请求失败：' + r.error.slice(0, 200) }, 502);
    if (!r.ok) {
      return sendJson(res, {
        ok: false, error: '上游返回 ' + r.status,
        hint: { 401: 'API Key 无效或已失效', 402: '余额不足', 404: 'Base URL 不对（要带 /v1）', 429: '限流' }[r.status] || '',
        detail: (r.text || '').slice(0, 400),
      }, 502);
    }
    const names = ((r.data && r.data.data) || [])
      .map((it) => (it && it.id) || null).filter(Boolean).sort();
    return sendJson(res, { ok: true, base_url: base, count: names.length, models: names });
  }

  async function handleAi(body, res) {
    const base = String(body.base_url || 'https://api.deepseek.com/v1').replace(/\/+$/, '');
    const key = String(body.api_key || '');
    const model = String(body.model || 'deepseek-chat');
    const messages = body.messages || [];
    const temperature = body.temperature == null ? 0.2 : body.temperature;
    // 推理型模型会把预算用于"思考"，给太小会让正文为空被误判成 Key 失效
    const maxTokens = parseInt(body.max_tokens, 10) || 4096;
    if (!key) return sendJson(res, { ok: false, error: '缺少 API Key（请在界面右上角设置）' }, 400);
    if (!/^https?:\/\//.test(base)) return sendJson(res, { ok: false, error: 'base_url 必须是 http(s) 地址' }, 400);

    const r = await upstreamJson(base + '/chat/completions', {
      model, messages, temperature, max_tokens: maxTokens, stream: false,
    }, { Authorization: 'Bearer ' + key }, 180000)
      .catch((e) => ({ status: 0, error: String(e && e.message || e) }));

    if (r.error) {
      return sendJson(res, {
        ok: false, error: '请求失败：' + r.error.slice(0, 300),
        hint: '多为中心网络问题或接口地址不可达；可先用「测试连接」确认',
        request: { base_url: base, model },
      }, 502);
    }
    if (!r.ok) {
      return sendJson(res, {
        ok: false, error: '上游返回 ' + r.status, hint: HINTS[r.status] || '',
        detail: (r.text || '').slice(0, 500),
        request: { base_url: base, model, messages: messages.length },
      }, 502);
    }
    const choice = r.data && r.data.choices && r.data.choices[0];
    const content = choice && choice.message && choice.message.content;
    if (content == null) {
      return sendJson(res, { ok: false, error: '上游响应格式异常', detail: String(r.text).slice(0, 500) }, 502);
    }
    const usage = (r.data && r.data.usage) || {};
    const finish = (choice && choice.finish_reason) || '';
    const detail = usage.completion_tokens_details || {};
    const reasoning = parseInt(detail.reasoning_tokens, 10) || 0;
    const completion = parseInt(usage.completion_tokens, 10) || 0;

    if (!String(content).trim() && (finish === 'length' || (completion && reasoning >= completion))) {
      return sendJson(res, {
        ok: true, content: '', usage, model, truncated_by_reasoning: true,
        hint: '输出预算被推理过程吃光了（推理 ' + reasoning + ' / 输出 ' + completion +
          ' token，max_tokens=' + maxTokens + '）。这不是 Key 或余额的问题：' +
          '要么把 max_tokens 调大（推理模型建议 ≥ 1024），要么换非推理模型（如 deepseek-chat）。',
      });
    }
    if (!String(content).trim()) {
      return sendJson(res, {
        ok: true, content: '', usage, model, empty_content: true,
        hint: '上游返回 200 但正文为空。常见原因：模型名不存在（网关静默返回空）、' +
          '内容被安全策略拦截、或该模型只产出推理内容。换 deepseek-chat 试一次即可区分。',
      });
    }
    return sendJson(res, { ok: true, content, usage, model });
  }

  const ZH_SYS = [
    '你是 CS2（反恐精英2）控制台指令专家。用户给出若干条 cvar/命令的英文官方说明，',
    '请为每一条翻译成简洁、准确、面向中文玩家的释义。要求：',
    '1. 保留指令名与技术缩写（如 FOV、HUD、HRTF、tick）；',
    '2. 如果说明里有默认值/取值范围，保留其数值含义；',
    '3. 每条不超过 60 个汉字，不要添加原文没有的信息；',
    '4. 严格输出 JSON 对象，键为指令名，值为中文释义字符串，不要输出多余文字。',
  ].join('\n');

  async function handleTranslate(body, res) {
    const items = body.items || [];
    const base = String(body.base_url || 'https://api.deepseek.com/v1').replace(/\/+$/, '');
    const key = String(body.api_key || '');
    const model = String(body.model || 'deepseek-chat');
    if (!key) return sendJson(res, { ok: false, error: '缺少 API Key' }, 400);
    if (!items.length) return sendJson(res, { ok: false, error: 'items 为空' }, 400);
    if (!/^https?:\/\//.test(base)) return sendJson(res, { ok: false, error: 'base_url 必须是 http(s) 地址' }, 400);

    const compact = items.slice(0, 40).map((it) => ({
      name: it.n, desc: String(it.en || '').slice(0, 400),
    }));

    const r = await upstreamJson(base + '/chat/completions', {
      model,
      messages: [
        { role: 'system', content: ZH_SYS },
        { role: 'user', content: '请翻译以下指令说明并返回 JSON：\n' + JSON.stringify(compact) },
      ],
      temperature: 0.1, max_tokens: 4096,
      response_format: { type: 'json_object' },
    }, { Authorization: 'Bearer ' + key }, 240000)
      .catch((e) => ({ status: 0, error: String(e && e.message || e) }));

    if (r.error) return sendJson(res, { ok: false, error: '请求失败：' + r.error.slice(0, 300) }, 502);
    if (!r.ok) return sendJson(res, { ok: false, error: '上游返回 ' + r.status, detail: (r.text || '').slice(0, 400) }, 502);

    let text = String(((r.data.choices || [])[0] || {}).message ? r.data.choices[0].message.content : '').trim();
    text = text.replace(/^```(?:json)?/gm, '').replace(/```$/gm, '').trim();
    let mapping = null;
    try { mapping = JSON.parse(text); } catch (e) {
      const m = text.match(/\{[\s\S]*\}/);
      if (m) { try { mapping = JSON.parse(m[0]); } catch (e2) { mapping = null; } }
    }
    if (!mapping || typeof mapping !== 'object' || Array.isArray(mapping)) {
      return sendJson(res, { ok: false, error: '模型未返回 JSON 对象', raw: text.slice(0, 400) }, 502);
    }

    const cache = readJson(cacheWritable, {}) || {};
    let saved = 0;
    const at = new Date().toISOString().replace(/\.\d+Z$/, '');
    Object.keys(mapping).forEach((name) => {
      const zh = mapping[name];
      if (typeof zh === 'string' && zh.trim()) {
        cache[name] = { zh: zh.trim(), src: 'ai', model, at };
        saved++;
      }
    });
    try { writeJson(cacheWritable, cache); } catch (e) {
      return sendJson(res, { ok: false, error: '写入缓存失败：' + String(e.message).slice(0, 200) }, 500);
    }
    // 让后续 /api/data 立即带上新翻译
    dbCache = null;
    return sendJson(res, { ok: true, saved, total_cached: Object.keys(cache).length });
  }

  /* ---------- 路由 ---------- */
  const server = http.createServer(async (req, res) => {
    const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);

    if (urlPath.startsWith('/api/')) {
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
      if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
    }

    try {
      /* ---- API ---- */
      if (urlPath === '/api/health') {
        return sendJson(res, { ok: true, root, data_dir: dataDir, engine: 'node' });
      }
      if (urlPath === '/api/data') {
        const db = loadDB();
        // 前端从 db.meta 读版本与上锁状态
        if (!db.meta) db.meta = buildMeta(db);
        return sendJson(res, db);
      }
      if (urlPath === '/api/zh_cache') {
        return sendJson(res, loadZhCache());
      }
      if (urlPath === '/api/meta') {
        const db = loadDB();
        return sendJson(res, buildMeta(db));
      }
      if (urlPath === '/api/game/cfgdir') {
        const dir = resolveCfgDir();
        return sendJson(res, {
          ok: !!dir, dir: dir || null, game_dir: resolveGameDir(),
        });
      }
      if (req.method === 'POST') {
        const body = await readBody(req);
        if (urlPath === '/api/game/cfg') return writeCfgToGame(body, res);
        if (urlPath === '/api/ai/models') return handleAiModels(body, res);
        if (urlPath === '/api/ai') return handleAi(body, res);
        if (urlPath === '/api/ai/translate') return handleTranslate(body, res);
        return sendJson(res, { ok: false, error: '未知接口：' + urlPath }, 404);
      }

      /* ---- 静态文件 ---- */
      // 显式拒绝路径穿越：URL 解码后仍含 .. 段的一律挡掉
      const segments = urlPath.split('/');
      if (segments.includes('..')) {
        res.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
        return res.end('400 Bad Request');
      }
      const rel = urlPath === '/' ? '/index.html' : urlPath;
      const abs = path.resolve(root, '.' + rel);
      if (abs !== root && !abs.startsWith(root + path.sep)) {
        res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
        return res.end('403 Forbidden');
      }
      if (sendFile(req, res, abs)) return;

      // 目录 → index.html
      if (sendFile(req, res, path.join(abs, 'index.html'))) return;

      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('404 Not Found: ' + urlPath);
    } catch (err) {
      sendJson(res, { ok: false, error: String(err && err.message || err) }, 500);
    }
  });

  return {
    server,
    loadDB,
    loadZhCache,
    listen(port) {
      return new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(port || 0, host, () => {
          server.removeListener('error', reject);
          resolve(server.address().port);
        });
      });
    },
    close() {
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

module.exports = { createServer };
