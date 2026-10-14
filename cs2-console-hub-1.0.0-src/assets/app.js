/* ============================================================
   CS2 控制台指令查询中心 —— 前端逻辑
   纯原生 JS，无依赖。支持两种运行方式：
     A. 通过 tools/server.py 打开（可用 AI 辅助 / 自动更新）
     B. 直接双击 index.html（离线浏览 + 收藏 + 配置生成）
   ============================================================ */
'use strict';

/* ============================================================
   收藏夹（多收藏夹）与指令集（配置方案）
   ------------------------------------------------------------
   favItems: { 指令名: [收藏夹名, ...] }   收藏夹列表由指令反推，不会出现空夹
   plans:    [ { id, folder, name, updated, items: [{n, v}] } ]
   ============================================================ */
const FAV_ITEMS_KEY = 'cs2hub.favItems';
const FAV_FOLDERS_KEY = 'cs2hub.folders';   // 收藏夹名单（含空夹）
const DEFAULT_FOLDER = '我的收藏';

/* 载入收藏夹名单；历史数据里没有这个键时，从 items 反推补全 */
function loadFavFolders(items) {
  let list = [];
  try {
    const v = JSON.parse(localStorage.getItem(FAV_FOLDERS_KEY) || '[]');
    if (Array.isArray(v)) list = v.filter((x) => typeof x === 'string' && x.trim());
  } catch (e) {}
  const seen = new Set(list);
  // 从指令归属里补出缺失的夹子（老数据迁移）
  Object.keys(items || {}).forEach((n) => {
    (items[n] || []).forEach((f) => { if (f && !seen.has(f)) { seen.add(f); list.push(f); } });
  });
  if (list.length) {
    try { localStorage.setItem(FAV_FOLDERS_KEY, JSON.stringify(list)); } catch (e) {}
  }
  return list;
}

function loadFavItems() {
  try {
    const raw = localStorage.getItem(FAV_ITEMS_KEY);
    if (raw) {
      const o = JSON.parse(raw);
      if (o && typeof o === 'object' && !Array.isArray(o)) return o;
    }
  } catch (e) {}
  // 老格式迁移：cs2hub.fav 是一个指令名数组
  let old = [];
  try { old = JSON.parse(localStorage.getItem('cs2hub.fav') || '[]'); } catch (e) {}
  const out = {};
  if (Array.isArray(old)) old.forEach((n) => { if (n) out[n] = [DEFAULT_FOLDER]; });
  if (Object.keys(out).length) {
    try {
      localStorage.setItem(FAV_ITEMS_KEY, JSON.stringify(out));
      localStorage.removeItem('cs2hub.fav');
    } catch (e) {}
  }
  return out;
}

/* 侧栏收藏夹列表：点一下即打开该收藏夹 */
function renderSideFolders() {
  const box = document.getElementById('sideFolders');
  if (!box) return;
  const folders = listFolders();
  const rows = folders.map((f) => {
    const on = Fav.addTarget === f.name ? ' on' : '';
    const btn = Fav.addTarget === f.name
      ? '<button class="side-add" data-add="' + esc(f.name) + '" title="把指令加入这个收藏夹">＋ 添加</button>'
      : '';
    return '<div class="side-folder-row' + on + '">'
      + '<button data-folder="' + esc(f.name) + '">'
      + '<span>📁</span><span class="nm">' + esc(f.name) + '</span>'
      + '<span class="ct">' + f.count + '</span></button>'
      + btn + '</div>';
  }).join('');
  // 超过 3 个时列表限高滚动（见 .side-folders 样式）
  box.classList.toggle('scrollable', folders.length > 3);
  box.innerHTML = rows;
  box.onclick = (ev) => {
    // 「＋ 添加」→ 进入添加模式（卡片出现星号，确认按钮常驻）
    const add = ev.target.closest('[data-add]');
    if (add) { ev.stopPropagation(); favBeginEdit(add.dataset.add); return; }
    const b = ev.target.closest('button[data-folder]');
    if (!b) return;
    // 单击具体收藏夹：不展开右侧专栏，只在该夹右侧就地显示「＋ 添加」
    const name = b.dataset.folder;
    Fav.addTarget = (Fav.addTarget === name) ? null : name;
    Fav.folder = name;
    renderSideFolders();
  };
}

function saveFavItems() {
  try {
    localStorage.setItem(FAV_ITEMS_KEY, JSON.stringify(S.favItems));
    localStorage.setItem(FAV_FOLDERS_KEY, JSON.stringify(S.favFolders || []));
  } catch (e) { toast('保存失败：浏览器存储空间不足'); }
  S.fav = new Set(Object.keys(S.favItems).filter((k) => (S.favItems[k] || []).length));
  const cnt = $('#favCount'); if (cnt) cnt.textContent = S.fav.size;
  const badge = $('#favBadge');
  if (badge) { badge.textContent = S.fav.size; badge.classList.toggle('hidden', S.fav.size === 0); }
  try { renderSideFolders(); } catch (e) {}
}

/* 列出所有收藏夹及其条目数；"我的收藏"始终排在最前 */
function listFolders() {
  // 夹子名单是权威来源（允许空夹）；计数从指令归属算
  const counts = new Map();
  Object.keys(S.favItems).forEach((n) => {
    (S.favItems[n] || []).forEach((f) => {
      if (!f) return;
      counts.set(f, (counts.get(f) || 0) + 1);
    });
  });
  const names = new Set([...(S.favFolders || []), ...counts.keys()]);
  const arr = Array.from(names, (name) => ({ name, count: counts.get(name) || 0 }));
  arr.sort((a, b) => {
    if (a.name === DEFAULT_FOLDER) return -1;
    if (b.name === DEFAULT_FOLDER) return 1;
    return a.name.localeCompare(b.name, 'zh');
  });
  return arr;
}
const folderNames = () => listFolders().map((f) => f.name);
const foldersOf = (n) => (S.favItems[n] || []).slice();
const isStarred = (n) => foldersOf(n).length > 0;

/* 新建收藏夹：立即把 items 放进去，避免出现空夹 */
function createFolder(name, items) {
  const nm = String(name || '').trim();
  if (!nm) { toast('请填写收藏夹名字'); return null; }
  if (folderNames().includes(nm)) { toast('已经有同名收藏夹了'); return null; }
  // 允许建空收藏夹：先登记名字，之后再往里加指令
  S.favFolders = (S.favFolders || []).concat(nm);
  const list = (items || []).slice();
  list.forEach((n) => {
    const cur = S.favItems[n] || [];
    if (!cur.includes(nm)) S.favItems[n] = cur.concat(nm);
  });
  saveFavItems();
  toast(list.length ? ('已创建收藏夹「' + nm + '」') : ('已创建空收藏夹「' + nm + '」，用「＋ 添加」放指令'));
  return nm;
}

/* 把指令加入 / 移出收藏夹 */
function addToFolder(names, folder) {
  const list = Array.isArray(names) ? names : [names];
  list.forEach((n) => {
    const cur = S.favItems[n] || [];
    if (!cur.includes(folder)) S.favItems[n] = cur.concat(folder);
  });
  saveFavItems();
}
function removeFromFolder(names, folder) {
  const list = Array.isArray(names) ? names : [names];
  list.forEach((n) => {
    const cur = (S.favItems[n] || []).filter((f) => f !== folder);
    if (cur.length) S.favItems[n] = cur; else delete S.favItems[n];
  });
  saveFavItems();
}
/* 删除收藏夹：只移除归属，不删指令本身 */
function deleteFolder(folder) {
  Object.keys(S.favItems).forEach((n) => {
    const cur = (S.favItems[n] || []).filter((f) => f !== folder);
    if (cur.length) S.favItems[n] = cur; else delete S.favItems[n];
  });
  S.favFolders = (S.favFolders || []).filter((f) => f !== folder);
  saveFavItems();
}
function renameFolder(oldName, newName) {
  const nm = String(newName || '').trim();
  if (!nm) { toast('名字不能为空'); return false; }
  if (nm === oldName) return true;
  if (folderNames().includes(nm)) { toast('已经有同名收藏夹了'); return false; }
  Object.keys(S.favItems).forEach((n) => {
    S.favItems[n] = (S.favItems[n] || []).map((f) => (f === oldName ? nm : f));
  });
  S.favFolders = (S.favFolders || []).map((f) => (f === oldName ? nm : f));
  (S.plans || []).forEach((pl) => { if (pl.folder === oldName) pl.folder = nm; });
  saveFavItems(); savePlans();
  return true;
}

/* ---------------- 指令集 / 配置方案 ---------------- */
const PLANS_KEY = 'cs2hub.plans';
function loadPlans() {
  try {
    const v = JSON.parse(localStorage.getItem(PLANS_KEY) || '[]');
    return Array.isArray(v) ? v : [];
  } catch (e) { return []; }
}
function savePlans() {
  try { localStorage.setItem(PLANS_KEY, JSON.stringify(S.plans || [])); }
  catch (e) { toast('保存失败：浏览器存储空间不足'); }
}
const plansOf = (folder) => (S.plans || []).filter((p) => (folder ? p.folder === folder : true));
function addPlan(name, folder, items) {
  const pl = {
    id: 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    folder: folder || null,
    name: String(name || '未命名方案').trim() || '未命名方案',
    updated: Date.now(),
    items: (items || []).map((x) => ({ n: x.n, v: String(x.v == null ? '' : x.v) })),
  };
  S.plans.push(pl);
  savePlans();
  return pl;
}
function removePlan(id) {
  S.plans = S.plans.filter((p) => p.id !== id);
  savePlans();
}
/* 复制内容：纯指令，不带注释行 */
function planText(pl) {
  return (pl.items || []).map((x) => x.n + ' ' + x.v).join('\n');
}



/* ---------------- 全局状态 ---------------- */
const S = {
  db: null,            // 指令库
  entries: [],         // 全部条目
  view: [],            // 当前筛选结果
  shown: 0,
  pageSize: 120,
  cat: '',             // 当前类别
  sub: '',             // 当前子类
  kw: '',              // 搜索词
  special: '',         // fav | cfg | ''
  current: null,       // 当前详情条目
  serverMode: false,   // 是否在本地服务下运行
  meta: null,
  favItems: loadFavItems(),          // { 指令名: [收藏夹, ...] }
  favFolders: [],                    // 收藏夹名单（含空夹），载入后立即补全
  plans: loadPlans(),                // 指令集 / 配置方案
  fav: new Set(),                    // 由 favItems 派生（下面立即同步）
  cfg: JSON.parse(localStorage.getItem('cs2hub.cfg') || '[]'),
  aiCache: JSON.parse(localStorage.getItem('cs2hub.aiZh') || '{}'),
  lang: loadLang(),   // 'zh' 仅中文 | 'en' 仅英文 | 'both' 中英对照
  settings: Object.assign(
    { base_url: 'https://api.deepseek.com/v1', api_key: '', model: 'deepseek-chat' },
    JSON.parse(localStorage.getItem('cs2hub.ai') || '{}')
  ),
};
/* 语言显示：三选一；兼容老的 cs2hub.showEn（'0'/'1'） */
function loadLang() {
  const v = String(localStorage.getItem('cs2hub.lang') || '').replace(/"/g, '');
  if (v === 'zh' || v === 'en' || v === 'both') return v;
  const old = localStorage.getItem('cs2hub.showEn');
  if (old === '0') { localStorage.setItem('cs2hub.lang', 'zh'); return 'zh'; }
  localStorage.setItem('cs2hub.lang', 'both');
  return 'both';
}

/* fav 由 favItems 派生，启动即可用 */
S.fav = new Set(Object.keys(S.favItems).filter((k) => (S.favItems[k] || []).length));
/* 收藏夹名单（含空夹），从已存名单 + 指令归属补全 */
S.favFolders = loadFavFolders(S.favItems);

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
const MONO = (s) => `<code>${esc(s)}</code>`;

function save(k, v) { localStorage.setItem('cs2hub.' + k, JSON.stringify(v)); }

function toast(msg, ms = 1900) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), ms);
}

/* 全局错误落地面板：出问题时把信息留在页面上，方便自查 */
window.addEventListener('error', (ev) => {
  const box = document.getElementById('errBox');
  if (!box) return;
  box.style.display = 'block';
  box.textContent += `[错误] ${ev.message} @ ${ev.filename}:${ev.lineno}\n`;
});
window.addEventListener('unhandledrejection', (ev) => {
  const box = document.getElementById('errBox');
  if (!box) return;
  box.style.display = 'block';
  box.textContent += `[未处理的 Promise] ${(ev.reason && ev.reason.message) || ev.reason}\n`;
});

/* ---------------- 数据加载 ---------------- */
async function loadDB() {
  // A. 本地服务
  try {
    const r = await fetch('api/health', { cache: 'no-store' });
    if (r.ok) {
      S.serverMode = true;
      const d = await (await fetch('api/data', { cache: 'no-store' })).json();
      S.db = d; S.meta = d.meta || null;
      return;
    }
  } catch (e) { /* 落到离线模式 */ }

  // B. 离线：使用 assets/db.js 内嵌数据
  if (window.__CS2_DB__) {
    S.db = window.__CS2_DB__;
    S.meta = {
      version: S.db.version, count: S.db.count,
      core_count: (S.db.entries || []).filter((e) => e.k).length,
      built_at: S.db.generated_at,
    };
    populateFromCache();
    return;
  }
  throw new Error('未找到指令库。请通过 start.cmd 启动本地服务，或确认 assets/db.js 存在。');
}

/* 离线模式下也应用本地 AI 翻译缓存 */
function populateFromCache() {
  if (!S.db) return;
  let n = 0;
  S.db.entries.forEach((e) => {
    const c = S.aiCache[e.n];
    if (c) { e.z = c; e.q = 3; n++; }
  });
  return n;
}

/* ---------------- 分类与索引 ---------------- */
function buildSidebar() {
  const cats = S.db.categories || [];
  // 库里只保留游戏内确认存在的指令，计数直接用全集
  const pool = S.entries;
  const counts = {};
  pool.forEach((e) => {
    counts[e.c] = counts[e.c] || { total: 0, core: 0, subs: {} };
    counts[e.c].total++;
    if (e.k) counts[e.c].core++;
    counts[e.c].subs[e.u] = (counts[e.c].subs[e.u] || 0) + 1;
  });

  const tree = $('#catTree');
  tree.innerHTML = '';

  // 「全部指令」入口
  const all = document.createElement('div');
  all.className = 'cat-group';
  all.innerHTML = `<button class="cat-item" data-cat="" data-sub="">
      <span class="ico">🗂️</span><span class="nm">全部指令</span>
      <span class="ct">${pool.length}</span></button>`;
  tree.appendChild(all);

  cats.forEach((c) => {
    // 分类必须恒定存在：即使当前筛选下该分类为 0 条也要显示（计数 0），
    // 否则切换「仅游戏内确认」时分类会凭空消失，用户会以为分类丢了。
    const cnt = counts[c.id] || { total: 0, core: 0, subs: {} };
    const g = document.createElement('div');
    g.className = 'cat-group';
    g.dataset.cat = c.id;
    if (!cnt.total) g.classList.add('empty');
    const subs = c.subs
      .filter((s) => cnt.subs[s.id])
      .map((s) => `<button class="sub-item" data-cat="${c.id}" data-sub="${s.id}">
          ${esc(s.name)} <span class="dim">${cnt.subs[s.id]}</span></button>`)
      .join('');
    g.innerHTML = `
      <button class="cat-item" data-cat="${c.id}" data-sub="" data-toggle="1">
        <span class="ico">${c.icon}</span>
        <span class="nm">${esc(c.name)}</span>
        <span class="ct">${cnt.total}</span>
      </button>
      <div class="sub-list">${subs}</div>`;
    tree.appendChild(g);
  });

  tree.addEventListener('click', (ev) => {
    const btn = ev.target.closest('button[data-cat]');
    if (!btn) return;
    const cat = btn.dataset.cat, sub = btn.dataset.sub || '';
    const grp = btn.closest('.cat-group');
    if (btn.dataset.toggle && grp && cat) {
      const isSame = S.cat === cat && !S.sub;
      $$('.cat-group').forEach((x) => x.classList.remove('open'));
      if (!isSame) grp.classList.add('open');
    }
    S.special = '';
    selectCategory(cat, sub);
  });
}

function selectCategory(cat, sub, keepScroll) {
  S.cat = cat || '';
  S.sub = sub || '';
  if (!keepScroll) $('#listPane').scrollTop = 0;
  $$('.cat-item').forEach((b) => b.classList.toggle('on',
    (b.dataset.cat || '') === S.cat && !(b.dataset.sub)));
  $$('.sub-item').forEach((b) => b.classList.toggle('on',
    b.dataset.cat === S.cat && b.dataset.sub === S.sub));
  if (S.special === 'fav' || S.special === 'cfg') S.special = '';
  applyFilter();
}
/* ---------------- 过滤与渲染 ---------------- */
function searchIndex(e) {
  if (e._idx) return e._idx;
  e._idx = (e.n + ' ' + (e.z || '') + ' ' + (e.en || '') + ' ' + (e.u || '')).toLowerCase();
  return e._idx;
}

/* 中文没有空格分词，用「二元字组」当词，比分字更准、比整句匹配从不出错强得多。
   例："随地安放炸弹" → 随地/地安/安放/放炸/炸弹 —— "安放""炸弹"能命中 mp_plant_c4_anywhere。*/
function cnBigrams(text) {
  const chars = (text || '').replace(/[^\u4e00-\u9fff]/g, '');
  const out = [];
  for (let i = 0; i + 1 < chars.length; i++) out.push(chars.slice(i, i + 2));
  return out;
}

/* 需求词 → 指令名/释义里可能出现的写法。跨语言、行业黑话都靠它兜住。*/
const SYNONYMS = [
  ['炸弹 安放 放置 下包 埋包 安装 c4', 'c4 plant bomb planted defuse'],
  ['随便 随地 任意 任何地方 随处 到处', 'anywhere everywhere'],
  ['无限 无穷 用不完', 'infinite unlimited'],
  ['连跳 兔子跳 bhop', 'bunnyhopping bhop jump'],
  ['穿墙 飞 飞行 无碰撞', 'noclip'],
  ['无敌 不死 不受伤', 'god buddha invulnerable'],
  ['买枪 购买 买东西', 'buy buymenu purchase'],
  ['准星 十字准心', 'crosshair'],
  ['后坐力 后座 枪口上跳', 'recoil'],
  ['弹道 曳光弹 子弹轨迹', 'tracer tracers'],
  ['小地图 雷达', 'radar minimap'],
  ['灵敏度 鼠标速度', 'sensitivity'],
  ['手雷 投掷物 雷', 'grenade hegrenade flashbang smoke molotov decoy'],
  ['闪光弹', 'flashbang'],
  ['烟雾弹', 'smoke'],
  ['燃烧瓶 燃烧弹 火', 'molotov incgrenade inferno'],
  ['拆弹 拆包', 'defuse defuser'],
  ['人质', 'hostage rescue'],
  ['重机枪 机枪', 'machinegun'],
  ['狙击枪 大狙 awp', 'sniper awp'],
  ['经济 钱 金钱 加钱', 'money cash economy'],
  ['回合 每局', 'round rounds'],
  ['热身', 'warmup'],
  ['冻结 静止 不能动', 'freeze freezetime'],
  ['重生 复活', 'respawn'],
  ['掉血 伤害 扣血', 'damage hurt'],
  ['血量 生命 加血', 'health heal'],
  ['自瞄 挂', 'aimbot cheat'],
  ['说话 语音 麦克风', 'voice mic'],
  ['文字聊天 打字', 'chat say'],
  ['枪口火光 火光', 'muzzleflash'],
  ['天空 天空盒', 'skybox sky'],
  ['阴影 影子', 'shadow shadows'],
  ['帧数 帧率 卡', 'fps framerate'],
  ['延迟 卡顿 ping 网络', 'ping latency net'],
  ['音量 声音大小', 'volume'],
  ['狙击开镜 开镜 瞄准镜', 'zoom scope'],
  ['视角 第一人称 第三人称', 'view camera thirdperson firstperson'],
  ['手臂 视角模型 持枪模型', 'viewmodel'],
];

function synonymScore(hay, query) {
  const q = (query || '').toLowerCase();
  let boost = 0;
  for (const [cnWords, enWords] of SYNONYMS) {
    const cnHit = cnWords.split(/\s+/).some((w) => w && q.includes(w));
    if (!cnHit) continue;
    const enHit = enWords.split(/\s+/).some((w) => w && hay.includes(w));
    if (enHit) boost += 22;
  }
  return boost;
}
// 兼容旧调用名
const synonymBoost = synonymScore;

function matchKw(e, kw) {
  if (!kw) return true;
  const terms = kw.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = searchIndex(e);
  // 空格分隔的多关键词：仍然要求全部命中（这是用户明确的 AND 意图）
  if (terms.length > 1) return terms.every((t) => hay.includes(t));

  const t = terms[0];
  if (hay.includes(t)) return true;
  // 单个中文长句直接子串匹配会全灭（"随地安放炸弹"不是任何释义的子串），
  // 放宽为：二元字组覆盖率 ≥ 0.4，或命中同义词桥接。短词（≤3 字）不放宽，保持精确。
  const cn = t.replace(/[^\u4e00-\u9fff]/g, '');
  if (cn.length >= 4) {
    const bgs = cnBigrams(t);
    const hit = bgs.filter((bg) => hay.includes(bg)).length;
    if (bgs.length && hit / bgs.length >= 0.4) return true;
    if (synonymScore(hay, t) > 0) return true;
  }
  return false;
}

function scoreEntry(e, kw) {
  if (!kw) return 0;
  const n = e.n.toLowerCase(), z = (e.z || '').toLowerCase();
  const hay = searchIndex(e);
  let s = 0;
  const t = kw.toLowerCase();
  if (n === t) s += 220;
  if (n.startsWith(t)) s += 110;
  if (n.includes(t)) s += 70;
  if (z.startsWith(t)) s += 30;
  if (z.includes(t)) s += 24;
  // 中文长句：按二元字组覆盖率给分（否则这些条目虽然被 matchKw 放行，排序会乱）
  const cn = t.replace(/[^\u4e00-\u9fff]/g, '');
  if (!hay.includes(t) && cn.length >= 4) {
    const bgs = cnBigrams(t);
    const hit = bgs.filter((bg) => hay.includes(bg)).length;
    if (bgs.length) s += (hit / bgs.length) * 34;
  }
  s += Math.max(0, 22 - e.n.length) * 0.4;
  // 用户要的多半是「能改的指令」，而不是 contributionscore_* 这种内部计分变量
  if (e.t === 'bool' || e.t === 'command') s += 8;
  if (e.k) s += 6;
  if (e.r) s += 3;
  return s;
}

/* 筛选开关现在只存在于设置面板，统一从这里读 */
const _on = (id, dflt) => {
  const el = document.getElementById(id);
  return el ? el.checked : dflt;
};
const isOnlyCore = () => _on('setOnlyCore', true);
const isOnlyRelease = () => _on('setOnlyRelease', false);

function applyFilter() {
  const onlyCore = isOnlyCore();
  const onlyRelease = isOnlyRelease();
  const kw = S.kw.trim().toLowerCase();

  let list = S.entries;

  if (S.special === 'fav') list = list.filter((e) => S.fav.has(e.n));
  else if (S.special === 'cfg') list = list.filter((e) => S.cfg.some((c) => c.n === e.n));
  else {
    if (S.cat) list = list.filter((e) => e.c === S.cat);
    if (S.sub) list = list.filter((e) => e.u === S.sub);
  }
  // 数据里已只保留游戏内确认存在的指令，无需再过滤
  if (onlyCore) list = list.filter((e) => e.k);
  if (onlyRelease) list = list.filter((e) => e.r);
  if (kw) {
    list = list.filter((e) => matchKw(e, kw))
      .map((e) => ({ e, s: scoreEntry(e, kw) }))
      .sort((a, b) => b.s - a.s)
      .map((x) => x.e);
  }

  S.view = list;
  S.shown = 0;
  renderList(true);
  renderCrumbs();
}

function renderCrumbs() {
  const parts = [];
  if (S.special === 'fav') parts.push('<b>⭐ 我的收藏</b>');
  else if (S.special === 'cfg') parts.push('<b>📄 待生成的配置</b>');
  else {
    const cat = (S.db.categories || []).find((c) => c.id === S.cat);
    if (cat) {
      const sub = (cat.subs || []).find((s) => s.id === S.sub);
      parts.push(`<b>${cat.icon} ${esc(cat.name)}</b>` + (sub ? ` › ${esc(sub.name)}` : ''));
    } else parts.push('<b>全部指令</b>');
  }
  // 搜索词不再写进面包屑：搜索框里已经有内容，重复显示是噪音
  $('#crumbs').innerHTML = parts.join(' <span class="dim">·</span> ');
}

function highlight(text, kw) {
  const t = esc(text);
  if (!kw) return t;
  const terms = kw.split(/\s+/).filter(Boolean).map((x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!terms.length) return t;
  return t.replace(new RegExp('(' + terms.join('|') + ')', 'gi'), '<span class="hl">$1</span>');
}

function renderList(reset) {
  const box = $('#list');
  if (reset) box.innerHTML = '';
  const kw = S.kw.trim();
  const LANG = S.lang;
  const slice = S.view.slice(S.shown, S.shown + S.pageSize);
  S.shown += slice.length;

  const frag = document.createDocumentFragment();
  slice.forEach((e) => {
    const row = document.createElement('div');
    row.className = 'row' + (S.current && S.current.n === e.n ? ' on' : '');
    row.dataset.name = e.n;
    const enOnly = e.q === 0 && !!e.en;          // 只有英文原文，尚未翻译
    // 中文面（没有中文时退回英文，避免空白）
    const zhDesc = (enOnly ? '' : e.z) || (LANG === 'zh' ? e.en : '') || e.z || e.en || '';
    const enDesc = e.en || '';
    const tags = [];
    if (e.s === 'client') tags.push('<span class="tag client">客户端</span>');
    else if (e.s === 'server') tags.push('<span class="tag server">服务器</span>');
    else if (e.s === 'both') tags.push('<span class="tag both">双端</span>');
    if (e.q === 2) tags.push('<span class="tag core">精校</span>');
    else if (e.q === 3) tags.push('<span class="tag ai">AI 译</span>');
    else if (enOnly) tags.push('<span class="tag">英文原文</span>');
    if (e.st === 'new') tags.push('<span class="tag both">新增</span>');
    if (e.x === 'high') tags.push('<span class="tag warn">风险</span>');
    const hasEn = !!(e.en && e.en.trim());
    row.innerHTML = `
      <div class="nm">${highlight(e.n, kw)}</div>
      <div class="defs">
        ${LANG !== 'en' ? `<div class="zh">${highlight(zhDesc.slice(0, 150), kw)}</div>` : ''}
        ${LANG === 'en'
            ? `<div class="en-line${hasEn ? '' : ' en-none'}" title="${esc(e.en)}">${
                 hasEn ? highlight(enDesc.slice(0, 220), kw)
                       : esc(e.n) + ' · 变量名（官方未提供说明）'}</div>`
            : (LANG === 'both'
                ? (hasEn
                    ? `<div class="en-line" title="${esc(e.en)}">${highlight(enDesc.slice(0, 220), kw)}</div>`
                    : `<div class="en-line en-none" title="上游数据源未提供英文说明">${esc(e.n)} · 变量名（官方未提供说明）</div>`)
                : '')}
      </div>
      <div class="tags">${tags.join('')}
        <span class="star ${S.fav.has(e.n) ? 'on' : ''}" data-star="${esc(e.n)}"
              title="收藏">${S.fav.has(e.n) ? '★' : '☆'}</span></div>`;
    frag.appendChild(row);
  });
  box.appendChild(frag);

  $('#listEmpty').classList.toggle('hidden', S.view.length !== 0);
  $('#more').classList.toggle('hidden', S.shown >= S.view.length);
  const coreN = S.view.filter((e) => e.k).length;
  $('#listInfo').innerHTML = S.view.length
    ? `共 <b>${S.view.length}</b> 条匹配（其中实用指令 <b>${coreN}</b> 条），已显示 ${Math.min(S.shown, S.view.length)} 条`
    : '';
}

/* 切换某条指令的"待加入"状态（添加模式下） */
function favTogglePick(name, starEl) {
  if (Fav.picked.has(name)) Fav.picked.delete(name); else Fav.picked.add(name);
  const on = Fav.picked.has(name);
  const star = starEl || document.querySelector(
    '#list .row[data-name="' + CSS.escape(name) + '"] .star');
  if (star) {
    star.classList.toggle('on', on);
    star.textContent = on ? '★' : '☆';
  }
  const row = document.querySelector('#list .row[data-name="' + CSS.escape(name) + '"]');
  if (row) row.classList.toggle('fav-on', on);   // 卡片整体也给个选中反馈
  favUpdateEditBar();
  if (Fav.open) favRender();
}

$('#list').addEventListener('click', (ev) => {
  const row = ev.target.closest('.row');
  const star = ev.target.closest('[data-star]');

  // 添加模式：点卡片任意区域都切换添加状态（不再只认 ☆）
  if (Fav.editMode && row) {
    ev.stopPropagation();
    favTogglePick(row.dataset.name, star);
    return;
  }

  if (star) {
    ev.stopPropagation();
    // 普通态 → 弹出「收藏到」菜单（可多选）
    showStarMenu(star.dataset.star, star);
    return;
  }

  if (!row) return;
  const e = S.entries.find((x) => x.n === row.dataset.name);
  if (e) showDetail(e);
});

$('#more').addEventListener('click', () => renderList(false));

/* ---------------- 详情 ---------------- */
function scopeName(s) {
  return { client: '客户端（只影响自己）', server: '服务器端（需服务器权限）',
           both: '客户端 + 服务器端', unknown: '未标注（多为引擎内部变量）' }[s] || s;
}
function typeName(t) {
  return { command: '控制台命令', bool: '开关 0/1', int: '整数', float: '小数', string: '文本',
           number: '数字', unknown: '未知' }[t] || t;
}
function dangerName(x) {
  return { high: '高风险 / 作弊类', medium: '中等风险', low: '仅调试用途' }[x] || x;
}

function usageExample(e) {
  const n = e.n;
  const argHint = (e.z.match(/（参数：([^）]+)）/) || [])[1];
  if (e.t === 'command' || (!e.d && e.t !== 'bool' && e.t !== 'int' && e.t !== 'float')) {
    return argHint ? `${n} ${argHint}` : n;
  }
  // 注释单独包一层，好让它比命令主体更暗（命令是要读的，注释是补充）
  const cmt = (x) => `        <span class="cmt">// ${esc(x)}</span>`;
  if (e.t === 'bool') return `${n} 1${cmt('开启；0 = 关闭')}`;
  if (e.d != null) return `${n} ${e.d}${cmt('当前默认值 ' + e.d)}`;
  return `${n} <值>`;
}

async function copy(text, okMsg) {
  try {
    await navigator.clipboard.writeText(text);
    toast(okMsg || '已复制');
  } catch (err) {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove();
    toast(okMsg || '已复制');
  }
}

function showDetail(e) {
  S.current = e;
  $$('.row').forEach((r) => r.classList.toggle('on', r.dataset.name === e.n));
  const cat = (S.db.categories || []).find((c) => c.id === e.c);
  const sub = cat ? (cat.subs || []).find((s) => s.id === e.u) : null;
  const qTag = e.q === 2 ? '<span class="tag core">人工精校释义</span>'
    : e.q === 3 ? '<span class="tag ai">AI 翻译释义</span>'
      : e.q === 1 ? '<span class="tag">术语表规则翻译</span>'
        : '<span class="tag">仅英文原文（可用 AI 翻译）</span>';
  // 数据全部来自游戏内 cvarlist 导出
  const gvTag = '<span class="tag gv-ok" title="该指令在 CS2 当前版本的 cvarlist 输出里出现过">游戏内已确认</span>';

  // 中文质量不佳时，以英文原文为主，中文仅作参考。
  // 注意：不能只看 q —— 很多条目 q=0（没有高质量中文）但其实有可读的中文释义，
  // 只有"中文确实为空"或"中文就是英文原文"时才降级为以英文为主。
  const zhMissing = !e.z || !e.z.trim();
  const zhIsEnglish = !zhMissing && e.en && e.z.trim() === e.en.trim();
  const zhWeak = zhMissing || !!zhIsEnglish;
  const zhMain = zhWeak
    ? (e.en || '（官方未提供说明）')
    : e.z;

  $('#detail').innerHTML = `
    <div class="d-name">
      <span>${esc(e.n)}</span>
      ${e.r ? '<span class="tag core">正式版下发</span>' : ''}
      <span class="tag ${e.s}">${scopeName(e.s).split('（')[0]}</span>
    </div>
    <div class="d-sub">${cat ? cat.icon + ' ' + esc(cat.name) : ''}${sub ? ' › ' + esc(sub.name) : ''}
      · ${typeName(e.t)} · ${qTag} · ${gvTag}</div>

    <div class="d-card"><h5>释义</h5>
      ${S.lang !== 'en'
          ? `<p class="d-zh" ${zhWeak ? 'style="font-family:var(--mono);font-size:13.2px;color:var(--fg-dim)"' : ''}>${esc(zhMain)}</p>`
          : ''}
      ${S.lang === 'zh' ? '' : (e.en && e.en.trim()
          ? `<div class="d-en-block">
               <div class="d-en-label">英文原文</div>
               <p class="d-en">${esc(e.en)}</p></div>`
          : `<div class="d-en-block">
               <div class="d-en-label">英文原文</div>
               <p class="d-en dim">（上游数据源未提供英文说明；变量名 ${esc(e.n)}，可用控制台 help ${esc(e.n)} 查看）</p></div>`)}
      ${zhWeak && e.z ? `<p class="d-ai-note">规则翻译参考：${esc(e.z)}</p>` : ''}
      ${e.nh ? `<p class="d-name-hint"><b>名字语义拆解</b>：${esc(e.nh)}
        <span class="dim">（官方没给说明时，从变量名逐段推断的含义，仅作参考）</span></p>` : ''}
      ${e.q === 3 && e.ai_note ? `<p class="d-ai-note">${esc(e.ai_note)}</p>` : ''}
    </div>

    ${e.x ? `<div class="d-card d-warn"><h5>风险提示 · ${dangerName(e.x)}</h5>
        <p style="font-size:13px">${esc(e.xn || '')}</p></div>` : ''}

    <div class="d-card"><h5>参数信息</h5>
      <dl class="d-kv">
        <dt>默认值</dt><dd>${e.d != null ? esc(e.d) : '—'}</dd>
        <dt>类型</dt><dd>${typeName(e.t)}</dd>
        <dt>作用域</dt><dd>${esc(scopeName(e.s))}</dd>
        <dt>标记</dt><dd>${e.f ? esc(e.f) : '—'}</dd>
      </dl>
    </div>

    <div class="d-card"><h5>用法示例</h5>
      <div class="d-usage">${usageExample(e)}</div>
      <div class="d-ai-note">写进 cfg 文件可长期生效；在控制台输入则只对本次生效。</div>
    </div>

    <div class="d-actions">
      <button class="btn tiny" id="dCopy">📋 复制指令</button>
      <button class="btn tiny" id="dAI">✨ 问 AI 怎么用</button>
    </div>`;

  $('#dCopy').onclick = () => copy(
    usageExample(e).replace(/<[^>]*>/g, '').split('//')[0].trim(), '已复制指令');
  $('#dAI').onclick = () => {
    openDrawer('ai');
    $('#aiInput').value = `请解释 ${e.n} 这条指令的作用、取值范围，并给出一份适合竞技玩家的推荐配置与注意事项。`;
    $('#aiMode').value = 'explain';
    sendAI();
  };
}

/* ---------------- 配置生成器 ---------------- */
function toggleCfg(e) {
  const i = S.cfg.findIndex((c) => c.n === e.n);
  if (i >= 0) S.cfg.splice(i, 1);
  else S.cfg.push({ n: e.n, v: e.t === 'bool' ? '1' : (e.d != null ? e.d : ''),
                    z: e.z || '', en: e.en || '' });
  save('cfg', S.cfg);
  $('#cfgCount').textContent = S.cfg.length;
  renderCfg();
  toast(i >= 0 ? '已从配置移除' : '已加入配置');
}

function cfgText() {
  const name = ($('#cfgName').value || 'my_cs2_setup').trim();
  const head = [
    `// ===== ${name}.cfg =====`,
    '// 由 CS2 控制台指令查询中心生成',
    `// 生成时间：${new Date().toLocaleString('zh-CN')}`,
    '// 用法：把本文件放到 ...\\Counter-Strike Global Offensive\\game\\csgo\\cfg\\',
    `//       然后在控制台执行：exec ${name}`,
    '',
    '// —— 指令说明 ——',
  ];
  const body = S.cfg.map((c) => {
    const line = `${c.n} ${c.v}`.trim();
    const note = S.lang === 'en' ? (c.en || c.z || '')
      : (S.lang === 'both' && c.en ? `${c.z || ''} ／ ${c.en}` : (c.z || ''));
    return line.padEnd(46) + `// ${note.slice(0, 110)}`;
  });
  const foot = ['', '// —— 让绑定在每次启动时生效 ——', 'host_writeconfig'];
  return head.concat(body, foot).join('\r\n');
}

function renderCfg() {
  const box = $('#cfgList');
  if (!S.cfg.length) {
    box.innerHTML = '<div class="dim" style="font-size:12.5px;padding:6px 2px">还没有指令。去列表里点某条指令，在详情中「加入配置」。</div>';
  } else {
    box.innerHTML = S.cfg.map((c, i) => `
      <div class="cfg-item">
        <code>${esc(c.n)}</code>
        <input value="${esc(c.v)}" data-cfgval="${i}" style="width:90px;background:var(--bg-4);border:1px solid var(--line-2);border-radius:5px;padding:3px 6px;font-family:var(--mono);font-size:12px" />
        <span class="zh" title="${esc(c.en || '')}">${esc((S.lang === 'en' ? (c.en || c.z || '') : (c.z || '')).slice(0, 40))}${
            S.lang === 'both' && c.en ? ' <span class="dim">／ ' + esc(c.en.slice(0, 46)) + '</span>' : ''}</span>
        <button data-cfgdel="${i}" title="移除">✕</button>
      </div>`).join('');
  }
  $('#cfgText').value = cfgText();
}

$('#cfgList').addEventListener('input', (ev) => {
  const i = ev.target.dataset.cfgval;
  if (i == null) return;
  S.cfg[+i].v = ev.target.value;
  save('cfg', S.cfg);
  $('#cfgText').value = cfgText();
});
$('#cfgList').addEventListener('click', (ev) => {
  const i = ev.target.dataset.cfgdel;
  if (i == null) return;
  S.cfg.splice(+i, 1);
  save('cfg', S.cfg);
  $('#cfgCount').textContent = S.cfg.length;
  renderCfg();
});
$('#cfgName').addEventListener('input', () => { $('#cfgText').value = cfgText(); });
$('#btnCfgCopy').onclick = () => copy($('#cfgText').value, '配置已复制到剪贴板');
$('#btnCfgDownload').onclick = () => {
  const name = ($('#cfgName').value || 'my_cs2_setup').trim().replace(/[\\/:*?"<>|]/g, '_');
  const blob = new Blob(['\ufeff' + $('#cfgText').value], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name + '.cfg';
  a.click();
  URL.revokeObjectURL(a.href);
  toast('已下载 ' + name + '.cfg');
};

/* ============================================================
   主题 / 模式 / 主页 / 设置面板
   ============================================================ */
const THEME_KEY = 'cs2hub.theme';
const MODE_KEY = 'cs2hub.mode';
const ONBOARD_KEY = 'cs2hub.onboarded';

const themeMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function getTheme() {
  // 归一化引号：兼容以 JSON 形式写入的值（"dark" 而不是 dark）
  const v = String(localStorage.getItem(THEME_KEY) || '').replace(/"/g, '');
  return (v === 'light' || v === 'dark' || v === 'system') ? v : 'system';
}
function resolvedTheme() {
  const t = getTheme();
  if (t === 'dark' || t === 'light') return t;
  return (themeMedia && themeMedia.matches) ? 'dark' : 'light';
}
/* 换主题：淡出 → 换 class → 淡入，避免生硬闪一下 */
function applyTheme(animate) {
  const root = document.documentElement;
  const next = resolvedTheme();
  const cur = root.classList.contains('t-light') ? 'light' : 'dark';
  const doIt = () => {
    root.classList.remove('t-dark', 't-light');
    root.classList.add(next === 'dark' ? 't-dark' : 't-light');
    const b = document.body;
    if (b) b.style.opacity = '';
  };
  if (animate && next !== cur) {
    document.body.style.opacity = '0';
    setTimeout(doIt, 150);
  } else {
    doIt();
  }
  // 同步所有主题按钮 / 分段控件的状态
  const seg = $('#segTheme');
  if (seg) seg.querySelectorAll('button').forEach((b) => {
    b.classList.toggle('on', b.dataset.theme === getTheme());
  });
  applyAccent();
  const face = { light: '☀', dark: '☾', system: '◐' }[getTheme()] || '◐';
  ['#btnTheme', '#homeTheme'].forEach((sel) => {
    const el = $(sel);
    if (el) {
      el.textContent = face;
      el.title = '主题：' + ({ light: '浅色', dark: '深色', system: '跟随系统' }[getTheme()]);
    }
  });
}
function cycleTheme() {
  const order = ['system', 'light', 'dark'];
  const i = order.indexOf(getTheme());
  localStorage.setItem(THEME_KEY, order[(i + 1) % order.length]);
  applyTheme(true);
}
if (themeMedia) {
  const onSys = () => { if (getTheme() === 'system') applyTheme(true); };
  if (themeMedia.addEventListener) themeMedia.addEventListener('change', onSys);
  else if (themeMedia.addListener) themeMedia.addListener(onSys);
}

/* ---------- 强调色（主题色）：默认蓝，与深浅模式解耦 ---------- */
const ACCENT_KEY = 'cs2hub.accent';
const ACCENT_DEFAULT = '#2f6fed';
/* 常见色预设（附中文名，设置面板里直接点选） */
const ACCENT_PRESETS = [
  { name: '蓝', hex: '#2f6fed' },
  { name: '青', hex: '#0f9d8a' },
  { name: '紫', hex: '#7c5cf0' },
  { name: '绿', hex: '#18a058' },
  { name: '橙', hex: '#e8850c' },
  { name: '红', hex: '#e5484d' },
];

function normHex(v) {
  let s = String(v || '').trim();
  if (!s) return null;
  if (s[0] !== '#') s = '#' + s;
  if (/^#[0-9a-fA-F]{3}$/.test(s)) {
    s = '#' + s[1] + s[1] + s[2] + s[2] + s[3] + s[3];
  }
  return /^#[0-9a-fA-F]{6}$/.test(s) ? s.toLowerCase() : null;
}
function hexToRgb(h) {
  const s = normHex(h) || ACCENT_DEFAULT;
  return [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)];
}
const rgbaOf = (h, a) => {
  const [r, g, b] = hexToRgb(h);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
};
/* 按亮度选对比文字色，保证按钮文字可读 */
function contrastFg(h) {
  const [r, g, b] = hexToRgb(h);
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return lum > 0.62 ? '#0b1220' : '#ffffff';
}
/* hover 用色：深色模式下提亮，浅色模式下压暗 */
function hoverOf(h, dark) {
  let [r, g, b] = hexToRgb(h);
  const f = dark ? 1.16 : 0.86;
  r = Math.max(0, Math.min(255, Math.round(r * f)));
  g = Math.max(0, Math.min(255, Math.round(g * f)));
  b = Math.max(0, Math.min(255, Math.round(b * f)));
  return '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
}
function getAccent() {
  return normHex(localStorage.getItem(ACCENT_KEY)) || ACCENT_DEFAULT;
}
/* 把强调色写进当前主题的 CSS 变量 */
function applyAccent() {
  const a = getAccent();
  const dark = document.documentElement.classList.contains('t-light') ? false : true;
  const root = document.documentElement;
  root.style.setProperty('--accent', a);
  root.style.setProperty('--accent-2', hoverOf(a, dark));
  root.style.setProperty('--accent-dim', rgbaOf(a, dark ? 0.16 : 0.12));
  root.style.setProperty('--accent-30', rgbaOf(a, dark ? 0.34 : 0.30));
  root.style.setProperty('--accent-fg', contrastFg(a));
  // 分段控件与色板选中态
  const seg = document.getElementById('accentPresets');
  if (seg) {
    seg.querySelectorAll('[data-accent]').forEach((b) => {
      b.classList.toggle('on', normHex(b.dataset.accent) === a);
    });
  }
  const pick = document.getElementById('accentCustom');
  if (pick && normHex(pick.value) !== a) pick.value = a;
  const lab = document.getElementById('accentLabel');
  if (lab) lab.textContent = a.toUpperCase();
}
function setAccent(h) {
  const v = normHex(h);
  if (!v) { toast('颜色格式不对，应该是 #RRGGBB'); return; }
  localStorage.setItem(ACCENT_KEY, v);
  applyAccent();
}
function resetAccent() {
  localStorage.removeItem(ACCENT_KEY);
  applyAccent();
  toast('主题色已恢复默认蓝');
}

/* ---------- 模式 ---------- */
function getMode() {
  const v = localStorage.getItem(MODE_KEY);
  return v === 'pro' ? 'pro' : 'card';
}
function setMode(m) {
  localStorage.setItem(MODE_KEY, m === 'pro' ? 'pro' : 'card');
  syncModeUI();
}
function syncModeUI() {
  const m = getMode();
  const modeName = (x) => (x === 'pro' ? '专业模式' : '卡片模式');
  const now = $('#modeNow'); const alt = $('#modeAlt');
  if (now) now.textContent = modeName(m);
  if (alt) alt.textContent = '切到' + modeName(m === 'pro' ? 'card' : 'pro');
  $$('#menuMode .mi[data-mode]').forEach((el) => {
    el.classList.toggle('on', el.dataset.mode === m);
  });
  const list = $('#list');
  if (list) list.classList.toggle('as-cards', m === 'card');
  document.body.classList.toggle('m-card', m === 'card');
  document.body.classList.toggle('m-pro', m === 'pro');
}

/* ---------- 主页 / 工作区 切换（带渐隐渐显） ---------- */
function showHome() {
  const home = $('#home'); const top = $('.topbar'); const body = $('.body');
  if (!home) return;
  document.body.dataset.view = 'home';
  if (top) top.classList.add('hidden');
  if (body) body.classList.add('hidden');
  home.classList.remove('hidden');
  home.classList.remove('view-anim');
  void home.offsetWidth;
  home.classList.add('view-anim');
  syncModeUI();
}
function showWorkspace(mode) {
  const home = $('#home'); const top = $('.topbar'); const body = $('.body');
  if (mode) setMode(mode);
  if (home) home.classList.add('hidden');
  if (top) top.classList.remove('hidden');
  if (body) {
    body.classList.remove('hidden');
    body.classList.remove('view-anim');
    void body.offsetWidth;
    body.classList.add('view-anim');
  }
  document.body.dataset.view = 'workspace';
  syncModeUI();
  renderList(true);
}

/* 启动行为：统一读取并归一化（兼容带引号的旧值） */
function getStartMode() {
  const v = String(localStorage.getItem('cs2hub.startMode') || '').replace(/"/g, '');
  return v === 'home' ? 'home' : 'last';
}

/* 首次启动必须手选模式；之后按设置决定回主页还是回上次状态 */
function bootView() {
  const onboarded = localStorage.getItem(ONBOARD_KEY) === '1';
  const start = getStartMode();
  if (!onboarded || start === 'home') showHome();
  else showWorkspace();
}

/* ---------- 设置面板 ---------- */
function openSettings() {
  const p = $('#settingsPanel'); const m = $('#settingsMask');
  if (!p) return;
  if (m) m.classList.remove('hidden');
  p.classList.remove('hidden');
  p.classList.remove('pop-anim');
  void p.offsetWidth;
  p.classList.add('pop-anim');
  loadSettings();
}
function closeSettings() {
  const p = $('#settingsPanel'); const m = $('#settingsMask');
  if (p) p.classList.add('hidden');
  if (m) m.classList.add('hidden');
}

/* ============================================================
   收藏夹面板：浏览 / 添加（6 步流程） / 重命名 / 删除 / 导出
   ------------------------------------------------------------
   添加流程（按需求）：
     1 侧栏点「＋ 添加收藏夹」
     2 选择目标收藏夹
     3 按「＋ 添加」确认
     4 星号与选择态出现，用户自行搜索勾选
     5 点「确认收藏」写回
     6 之后可继续添加或删除
   ============================================================ */
const Fav = {
  open: false,
  folder: null,        // 当前选中的收藏夹
  editMode: false,     // 是否处于"添加/移除"编辑态
  picked: new Set(),   // 编辑态下勾选的指令名
  confirmMode: null,   // 待确认的目标收藏夹（选了但还没按「添加」）
  paramMode: false,    // 参数设置模式
  draft: {},           // { 指令名: 参数值 } 本次调好的参数（未保存）
  outText: '',         // 指令输出的文本框内容
};

/* cfg 导出方式：'auto' 直接写进游戏 cfg 目录 | 'manual' 生成到指定位置 */
const CFGMP_KEY = 'cs2hub.cfgMode';
function getCfgMode() {
  const v = String(localStorage.getItem(CFGMP_KEY) || '').replace(/"/g, '');
  return (v === 'auto' || v === 'manual') ? v : 'manual';   // 默认手动，不擅自写游戏目录
}
function setCfgMode(v) {
  localStorage.setItem(CFGMP_KEY, v);
  const seg = document.getElementById('segCfgMode');
  if (seg) seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.mode === v));
  const line = document.getElementById('cfgModeLine');
  if (line) {
    line.textContent = (v === 'auto')
      ? '导出时直接写入游戏 cfg 目录'
      : '导出时走保存对话框，由你自己放到游戏目录';
  }
}

/* 生成某方案的 .cfg 文本（不带注释，可直接被 exec 使用） */
function planCfgText(pl) {
  const lines = (pl.items || []).map((it) => {
    const v = String(it.v == null ? '' : it.v).trim();
    return v === '' ? it.n : (it.n + ' ' + v);
  });
  return lines.join('\n') + '\n';
}

/* 方案文件名：优先方案名，其次收藏夹名。
   用户要在控制台里 exec 这个文件名，所以只保留字母/数字/下划线/汉字，
   其余（空格、·、括号等）统一折成下划线，避免 exec 时因空格或标点出错。 */
function planFileName(pl) {
  let raw = String(pl.name || pl.folder || 'cs2hub').trim();
  raw = raw.replace(/[^0-9A-Za-z_\u4e00-\u9fa5]/g, '_')
           .replace(/_+/g, '_')
           .replace(/^_+|_+$/g, '');
  if (!raw) raw = 'cs2hub';
  if (raw.length > 60) raw = raw.slice(0, 60).replace(/_+$/, '');
  return raw + '.cfg';
}

/* exec 时用的名字（不含扩展名） */
function planExecName(pl) {
  return planFileName(pl).replace(/\.cfg$/i, '');
}

/* 导出某方案为 cfg */
async function planExportCfg(planId) {
  const pl = (S.plans || []).find((x) => x.id === planId);
  if (!pl) return;
  if (!pl.items || !pl.items.length) { toast('这个方案是空的'); return; }
  const data = planCfgText(pl);
  const fname = planFileName(pl);

  if (getCfgMode() === 'auto') {
    toast('正在写入游戏 cfg 目录…');
    let r = null;
    try {
      r = await (await fetch('api/game/cfg', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: fname, data: data }),
      })).json();
    } catch (e) {
      r = { ok: false, error: String(e.message || e) };
    }
    if (r && r.ok) {
      const exec = planExecName(pl);
      // 不用 alert：会阻塞页面；改用轻提示，路径给足显示时间便于核对
      toast('已写到 ' + r.path, 6000);
      setTimeout(() => toast('在控制台执行：exec ' + exec, 6000), 1100);
      return;
    }
    const why = (r && (r.error + (r.hint ? '\n' + r.hint : ''))) || '未知错误';
    if (confirm('自动写入游戏目录失败：\n' + why +
                '\n\n要改用「生成到指定位置」吗？（生成后自己拖进游戏文件夹）')) {
      downloadCfg(fname, data);
    }
    return;
  }

  downloadCfg(fname, data);
  toast('已生成 ' + fname + '，请放到游戏 cfg 目录');
}

/* 走浏览器下载（Electron 下是系统保存对话框） */
function downloadCfg(fname, data) {
  const blob = new Blob(['\ufeff' + data], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = fname;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

/* 中文编号：一、二、三…（方案自动编号用） */
const CN_NUM = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
  '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十'];
const cnNum = (i) => CN_NUM[i - 1] || String(i);

/* 取某条指令的当前参数值：草稿优先，其次默认值 */
function favParamOf(name) {
  if (Fav.draft && Object.prototype.hasOwnProperty.call(Fav.draft, name)) {
    return Fav.draft[name];
  }
  const e = S.entries.find((x) => x.n === name);
  return (e && e.d != null) ? String(e.d) : '';
}

/* 进入/退出参数设置模式 */
function favToggleParamMode() {
  Fav.paramMode = !Fav.paramMode;
  if (Fav.paramMode && !Object.keys(Fav.draft).length) {
    // 首次进入：用当前收藏夹里的默认值初始化草稿
    const names = Object.keys(S.favItems)
      .filter((n) => (S.favItems[n] || []).includes(Fav.folder));
    names.forEach((n) => { Fav.draft[n] = favParamOf(n); });
  }
  favRender();
}

/* 输出：把当前参数套进指令族（不带注释） */
function favBuildOutput() {
  const names = Object.keys(S.favItems)
    .filter((n) => (S.favItems[n] || []).includes(Fav.folder));
  if (!names.length) return '';
  return names.map((n) => {
    const v = favParamOf(n);
    return v === '' ? n : (n + ' ' + v);
  }).join('\n');
}

function favToggleOutput() {
  if (Fav.outText) { Fav.outText = ''; }
  else { Fav.outText = favBuildOutput(); }
  favRender();
  if (Fav.outText) {
    const ta = document.getElementById('favOut');
    if (ta) { ta.focus(); ta.select(); }
  }
}

/* 保存参数方案：编号（一/二/三…）+ 自定义注释 */
function favSavePlan() {
  const names = Object.keys(S.favItems)
    .filter((n) => (S.favItems[n] || []).includes(Fav.folder));
  if (!names.length) { toast('这个收藏夹还是空的'); return; }
  const used = (S.plans || []).filter((x) => x.folder === Fav.folder).length;
  const auto = '方案' + cnNum(used + 1);
  const note = prompt('给这个方案加一句注释（可留空）：\n编号自动为「' + cnNum(used + 1) + '」', '');
  if (note === null) return;                        // 取消
  const nm = note.trim() ? (cnNum(used + 1) + ' · ' + note.trim()) : auto;
  const items = names.map((n) => ({ n, v: favParamOf(n) }));
  addPlan(nm, Fav.folder, items);
  toast('已保存方案「' + nm + '」（' + items.length + ' 条）');
  favRender();
}

/* 已存方案：列出本地保存的方案，可套用或删除 */
function favShowPlans() {
  const box = document.getElementById('favPlanList');
  if (!box) return;
  if (!box.classList.contains('hidden')) { box.classList.add('hidden'); return; }
  const mine = (S.plans || []).filter((x) => x.folder === Fav.folder);
  const others = (S.plans || []).filter((x) => x.folder !== Fav.folder);
  const row = (pl, dim) => `
    <div class="fp-row${dim ? ' dim' : ''}" data-plan="${pl.id}">
      <span class="fp-nm">${esc(pl.name)}</span>
      <span class="fp-ct">${pl.items.length} 条</span>
      <button class="btn tiny ghost" data-apply="${pl.id}">套用</button>
      <button class="btn tiny ghost" data-exportcfg="${pl.id}"
        title="导出为 .cfg，可按设置直接放进游戏 cfg 目录">导出 cfg</button>
      <button class="btn tiny ghost" data-delplan="${pl.id}" title="删除这个方案">✕</button>
    </div>`;
  box.innerHTML =
    (mine.length ? mine.map((x) => row(x, false)).join('')
      : '<div class="fav-empty">这个收藏夹还没有保存过方案。</div>')
    + (others.length ? '<div class="fp-sep">其他收藏夹的方案</div>' + others.map((x) => row(x, true)).join('') : '');
  box.classList.remove('hidden');
  box.onclick = (ev) => {
    const ap = ev.target.closest('[data-apply]');
    if (ap) { favApplyPlan(ap.dataset.apply); box.classList.add('hidden'); return; }
    const ex = ev.target.closest('[data-exportcfg]');
    if (ex) { planExportCfg(ex.dataset.exportcfg); return; }
    const dp = ev.target.closest('[data-delplan]');
    if (dp) {
      if (!confirm('删除这个方案？（只删方案，不影响收藏夹里的指令）')) return;
      removePlan(dp.dataset.delplan);
      toast('已删除方案');
      favShowPlans();
      favRender();
      return;
    }
  };
}

/* 套用已保存的方案 */
function favApplyPlan(planId) {
  const pl = (S.plans || []).find((x) => x.id === planId);
  if (!pl) return;
  Fav.draft = {};
  (pl.items || []).forEach((it) => { Fav.draft[it.n] = it.v; });
  Fav.paramMode = true;
  Fav.outText = '';
  favRender();
  toast('已套用方案「' + pl.name + '」，可直接输出或再改');
}

function favEl() { return $('#favPanel'); }

function favEnsurePanel() {
  let p = favEl();
  if (p) return p;
  p = document.createElement('div');
  p.id = 'favPanel';
  p.className = 'settings-mask hidden';
  p.innerHTML = `
    <div class="fav-panel" role="dialog" aria-label="我的收藏夹">
      <div class="fav-head">
        <b>⭐ 我的收藏夹</b>
        <span class="fav-sub" id="favSub">查看与整理；添加指令请用侧栏收藏夹旁的「＋ 添加」</span>
        <div class="fav-head-acts">
          <button class="btn tiny ghost" id="favExport">导出</button>
          <button class="btn tiny ghost" id="favClose">✕</button>
        </div>
      </div>
      <div class="fav-body">
        <aside class="fav-list" id="favList"></aside>
        <div class="fav-main">
          <div class="fav-bar">
            <div class="fav-title" id="favTitle"><span class="ic">📁</span><b>—</b>
              <span class="fav-cnt" id="favItemsCount"></span></div>
            <div class="fav-bar-acts" id="favBarActs"></div>
          </div>
          <div class="fav-plan-list hidden" id="favPlanList"></div>
          <div class="fav-items" id="favItems"></div>
          <div class="fav-out-wrap hidden" id="favOutWrap">
            <div class="fav-out-head">
              <b>📤 指令输出</b>
              <span class="fav-out-tip">不带注释，可直接粘进游戏控制台</span>
              <div class="sp"></div>
              <button class="btn tiny ghost" id="favOutCopy">复制</button>
              <button class="btn tiny ghost" id="favOutHide">收起</button>
            </div>
            <textarea id="favOut" class="fav-out" spellcheck="false" readonly></textarea>
          </div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(p);
  // 关闭
  p.addEventListener('click', (ev) => {
    if (ev.target === p) favClosePanel();
  });
  p.querySelector('#favClose').onclick = favClosePanel;
  return p;
}

/* 同步常驻条的状态（每次勾选都调用，保证「已选 N 条」实时） */
function favUpdateEditBar() {
  const bar = document.getElementById('favEditBar');
  if (!bar) return;
  bar.classList.toggle('hidden', !Fav.editMode);
  if (!Fav.editMode) return;
  const f = document.getElementById('favEditFolder');
  if (f) f.textContent = Fav.folder || '—';
  const pk = document.getElementById('favPicked');
  if (pk) pk.textContent = Fav.picked.size;
  const cm = document.getElementById('favEditCommit');
  if (cm) cm.textContent = Fav.picked.size ? ('确认收藏 ' + Fav.picked.size + ' 条') : '确认';
}

/* 添加模式：常驻底栏（不依赖右侧面板是否打开） */
function favEditBarEl() {
  let bar = document.getElementById('favEditBar');
  if (bar) return bar;
  bar = document.createElement('div');
  bar.id = 'favEditBar';
  bar.className = 'fav-edit-bar hidden';
  bar.innerHTML = `
    <span class="fe-ic">⭐</span>
    <span class="fe-txt">添加模式 · 目标收藏夹 <b id="favEditFolder">—</b></span>
    <span class="fe-cnt">已选 <b id="favPicked">0</b> 条</span>
    <span class="sp"></span>
    <button class="btn tiny ghost" id="favEditCancel">取消</button>
    <button class="btn tiny primary" id="favEditCommit">确认</button>`;
  document.body.appendChild(bar);
  bar.querySelector('#favEditCancel').onclick = favCancelEdit;
  bar.querySelector('#favEditCommit').onclick = favCommitEdit;
  return bar;
}

/* 退出添加模式（取消 / 确认都走这里） */
function favEndEdit() {
  Fav.editMode = false;
  Fav.picked.clear();
  document.body.classList.remove('fav-editing');
  const bar = document.getElementById('favEditBar');
  if (bar) bar.classList.add('hidden');
  if (Fav.open) favRender();
  renderList(true);
}

function favCancelEdit() {
  favEndEdit();
  toast('已取消添加');
}

function favClosePanel() {
  const p = favEl();
  if (p) p.classList.add('hidden');
  Fav.open = false;
  Fav.editMode = false;
  Fav.picked.clear();
  document.body.classList.remove('fav-editing');
  renderList(true);
}

function favOpenPanel() {
  favEnsurePanel().classList.remove('hidden');
  Fav.open = true;
  const folders = listFolders();
  if (!Fav.folder || !folders.some((f) => f.name === Fav.folder)) {
    Fav.folder = folders.length ? folders[0].name : null;
  }
  favRender();
}

/* 侧栏「＋ 添加收藏夹」：打开选择目标收藏夹（第 1 步） */
/* 兼容入口：没有收藏夹就先建，只有一个就直接进添加模式，否则让用户选夹子 */
function favStartAdd() {
  const folders = listFolders();
  if (!folders.length) { favNewFolderFlow(); return; }
  if (folders.length === 1) { favBeginEdit(folders[0].name); return; }
  Fav.addTarget = Fav.folder && folders.some((f) => f.name === Fav.folder)
    ? Fav.folder : folders[0].name;
  renderSideFolders();
  toast('选择收藏夹旁的「＋ 添加」把指令放进去');
}

/* 选好收藏夹后，按「添加」才进入编辑态（第 3 步 → 第 4 步） */
function favBeginEdit(folder) {
  Fav.folder = folder;
  Fav.editMode = true;
  Fav.picked.clear();
  document.body.classList.add('fav-editing');
  favEditBarEl();
  favUpdateEditBar();
  if (Fav.open) favRender();
  renderList(true);
  toast('添加模式：点卡片上的 ☆ 加入「' + folder + '」，完成按「确认」');
}

function favCommitEdit() {
  if (!Fav.picked.size) { toast('还没有选任何指令'); return; }
  const names = Array.from(Fav.picked);
  const folder = Fav.folder;
  addToFolder(names, folder);
  favEndEdit();
  toast('已把 ' + names.length + ' 条加入「' + folder + '」');
}

function favNewFolderFlow() {
  const name = prompt('新收藏夹的名字：', '我的收藏夹');
  if (!name) return;
  // 添加模式下若有已选指令就一并放入；否则建一个空夹
  const items = Fav.editMode ? Array.from(Fav.picked) : [];
  const nm = createFolder(name, items);
  if (!nm) return;
  Fav.folder = nm;
  Fav.addTarget = nm;
  if (Fav.open) favRender();
  renderSideFolders();
  renderList(true);
}

function favRender() {
 try {
  const folders = listFolders();
  const listBox = $('#favList');
  if (!listBox) return;

  // 左列：收藏夹 + 新建
  listBox.innerHTML = `
    <div class="fav-new" id="favNewFolder"><span>＋</span>新建收藏夹</div>
    <div id="favSuggest" class="hidden"></div>
    ${folders.map((f) => `
      <div class="fav-folder ${f.name === Fav.folder ? 'on' : ''}" data-folder="${esc(f.name)}">
        <span class="ic">📁</span><span class="nm">${esc(f.name)}</span>
        <span class="ct">${f.count}</span>
      </div>`).join('')}
    ${folders.length ? '' : '<div class="fav-empty">还没有收藏夹</div>'}`;

  listBox.onclick = (ev) => {
    if (ev.target.closest('#favNewFolder')) { favNewFolderFlow(); return; }
    const f = ev.target.closest('.fav-folder');
    if (!f) return;
    // 专栏只看内容；添加指令请走侧栏的「＋ 添加」
    Fav.folder = f.dataset.folder;
    const pl = document.getElementById('favPlanList');
    if (pl) pl.classList.add('hidden');
    favRender();
  };

  // 右侧标题与操作
  const title = $('#favTitle');
  const acts = $('#favBarActs');
  const itemsBox = $('#favItems');
  if (!Fav.folder) {
    title.innerHTML = '<span class="ic">📁</span><b>还没有收藏夹</b>';
    acts.innerHTML = '<button class="btn tiny primary" id="favCreateFirst">＋ 新建收藏夹</button>';
    itemsBox.innerHTML = '<div class="fav-empty">先新建一个收藏夹，再把指令放进去。</div>';
    const cb = $('#favCreateFirst');
    if (cb) cb.onclick = favNewFolderFlow;
  } else {
    const names = Object.keys(S.favItems).filter((n) => (S.favItems[n] || []).includes(Fav.folder));
    title.innerHTML = `<span class="ic">📁</span><b>${esc(Fav.folder)}</b>
      <span class="fav-cnt">${names.length} 条</span>`;
    acts.innerHTML = `
      <button class="btn tiny ${Fav.paramMode ? 'primary' : 'ghost'}" id="favParam"
        title="进入参数设置模式：每条指令后可改参数，鼠标悬停可看释义">⚙ 参数设置</button>
      <button class="btn tiny ghost" id="favSavePlan"
        title="把当前参数存为方案（编号 + 自定义注释），保存在本地">💾 保存方案</button>
      <button class="btn tiny ghost" id="favOutBtn"
        title="在下方生成文本框，输出可直接粘进控制台的指令（不带注释）">📤 指令输出</button>
      <button class="btn tiny ghost" id="favPlanBtn"
        title="读取本地已保存的方案">📂 方案</button>
      <button class="btn tiny ghost" id="favRename">重命名</button>
      <button class="btn tiny ghost" id="favDel">删除收藏夹</button>
      <button class="btn tiny ghost hidden" id="favToPlan">存为指令集</button>`;
    $('#favParam').onclick = () => favToggleParamMode();
    $('#favSavePlan').onclick = () => favSavePlan();
    $('#favOutBtn').onclick = () => favToggleOutput();
    $('#favPlanBtn').onclick = () => favShowPlans();
    $('#favRename').onclick = () => {
      const nn = prompt('新的名字：', Fav.folder);
      if (nn && renameFolder(Fav.folder, nn)) { Fav.folder = nn.trim(); favRender(); renderList(true); }
    };
    $('#favDel').onclick = () => {
      if (!confirm('删除收藏夹「' + Fav.folder + '」？\n里面的指令不会被删除，只是从这个夹移出。')) return;
      deleteFolder(Fav.folder);
      Fav.folder = null;
      toast('已删除收藏夹');
      favRender(); renderList(true);
    };
    $('#favToPlan').onclick = () => {
      const items = names.map((n) => {
        const e = S.entries.find((x) => x.n === n);
        return { n, v: (e && e.d != null) ? String(e.d) : '' };
      });
      if (!items.length) { toast('这个收藏夹还是空的'); return; }
      const nm = prompt('指令集名字：', Fav.folder + ' 方案');
      if (!nm) return;
      addPlan(nm, Fav.folder, items);
      toast('已存为指令集「' + nm + '」');
    };

    itemsBox.innerHTML = names.length ? names.map((n) => {
      const e = S.entries.find((x) => x.n === n) || { n, z: '' };
      const picked = Fav.picked.has(n);
      const hint = esc([e.z || '', e.t ? ('类型 ' + typeName(e.t)) : '',
        e.d != null ? ('默认 ' + e.d) : ''].filter(Boolean).join(' · '));
      if (Fav.paramMode) {
        // 参数模式：输入框；悬停才显示释义（作为参数提示）
        return `<div class="fav-row param ${picked ? 'on' : ''}" data-n="${esc(n)}"
              data-hint="${hint}" title="${hint}">
          <span class="fn">${esc(n)}</span>
          <input class="fav-param" data-param="${esc(n)}"
                 value="${esc(favParamOf(n))}" spellcheck="false"
                 placeholder="${esc(e.d != null ? String(e.d) : '参数')}">
          <span class="fav-def">${esc(e.z || '')}</span>
          <span class="fx" data-remove="${esc(n)}" title="从这个收藏夹移除">✕</span>
        </div>`;
      }
      return `<div class="fav-row ${picked ? 'on' : ''}" data-n="${esc(n)}">
        ${Fav.editMode ? `<span class="fav-pick" data-pick="${esc(n)}">${picked ? '★' : '☆'}</span>` : ''}
        <span class="fn">${esc(n)}</span>
        <span class="fz">${esc(e.z || '')}</span>
        <span class="fx" data-remove="${esc(n)}" title="从这个收藏夹移除">✕</span>
      </div>`;
    }).join('') : '<div class="fav-empty">这个收藏夹还是空的。点左侧「＋ 添加收藏夹」放入指令。</div>'
      + (Fav.paramMode ? '' : '');

    // 参数输入：实时写进草稿，并同步输出框内容
    itemsBox.oninput = (ev) => {
      const inp = ev.target.closest('[data-param]');
      if (!inp) return;
      Fav.draft[inp.dataset.param] = inp.value;
      if (Fav.outText) {
        Fav.outText = favBuildOutput();
        const ta = document.getElementById('favOut');
        if (ta) ta.value = Fav.outText;
      }
    };
    itemsBox.onclick = (ev) => {
      // 参数输入框内点击（聚焦、选中文字、移动光标）不应跳详情或关闭专栏
      if (ev.target.closest('.fav-param')) return;
      const pk = ev.target.closest('[data-pick]');
      if (pk) {
        const n = pk.dataset.pick;
        if (Fav.picked.has(n)) Fav.picked.delete(n); else Fav.picked.add(n);
        favRender();
        return;
      }
      const rm = ev.target.closest('[data-remove]');
      if (rm) {
        removeFromFolder(rm.dataset.remove, Fav.folder);
        favRender(); renderList(true);
        return;
      }
      // 参数模式下点行内空白也只是聚焦输入框，不跳走
      if (Fav.paramMode) {
        const inp = ev.target.closest('.fav-row') && ev.target.closest('.fav-row').querySelector('.fav-param');
        if (inp) { inp.focus(); return; }
        return;
      }
      const row = ev.target.closest('.fav-row');
      if (row) {
        const e = S.entries.find((x) => x.n === row.dataset.n);
        if (e) { favClosePanel(); showDetail(e); }
      }
    };
  }

  // 编辑提示条
  // 输出区
  const wrap = $('#favOutWrap');
  if (wrap) {
    const show = !!Fav.outText;
    wrap.classList.toggle('hidden', !show);
    if (show) {
      const ta = $('#favOut');
      if (ta && ta.value !== Fav.outText) ta.value = Fav.outText;
      const cp = $('#favOutCopy');
      if (cp) cp.onclick = () => copy(Fav.outText, '已复制 ' + Fav.outText.split('\n').length + ' 条指令');
      const hd = $('#favOutHide');
      if (hd) hd.onclick = () => { Fav.outText = ''; favRender(); };
    }
  }

  // 常驻编辑条只由 favBeginEdit / favEndEdit / favUpdateEditBar 控制
  favUpdateEditBar();
  // 导出
  const ex = $('#favExport');
  if (ex) ex.onclick = () => {
    const data = JSON.stringify({ favItems: S.favItems, plans: S.plans || [] }, null, 2);
    const blob = new Blob([data], { type: 'application/json;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cs2hub-favorites.json';
    a.click();
    URL.revokeObjectURL(a.href);
    toast('已导出收藏夹');
  };
 } catch (err) {
   window.__favRenderErr = String(err && err.message || err);
   console.error('[favRender]', err);
   const s = document.getElementById('favSub');
   if (s) s.textContent = '渲染出错：' + window.__favRenderErr;
 }
}

/* 星标归属菜单：列表里点 ☆ 时弹出 */
let starMenuEl = null;
function closeStarMenu() {
  if (starMenuEl) { starMenuEl.remove(); starMenuEl = null; }
}
function showStarMenu(name, anchorEl) {
  closeStarMenu();
  const folders = listFolders();
  const mine = foldersOf(name);
  const el = document.createElement('div');
  el.className = 'menu star-menu';
  el.style.position = 'fixed';
  el.innerHTML = `
    <div class="mh">收藏到</div>
    ${folders.map((f) => `
      <div class="mi ${mine.includes(f.name) ? 'on' : ''}" data-f="${esc(f.name)}">
        <span class="cb">${mine.includes(f.name) ? '✓' : ''}</span>${esc(f.name)}
      </div>`).join('')}
    ${folders.length ? '' : '<div class="mi dim">还没有收藏夹</div>'}
    <div class="sep"></div>
    <div class="mi" data-new="1"><span class="cb">＋</span>新建收藏夹…</div>
    ${mine.length ? '<div class="mi" data-clear="1"><span class="cb">✕</span>从所有收藏夹移除</div>' : ''}`;
  document.body.appendChild(el);
  const r = anchorEl.getBoundingClientRect();
  const w = el.offsetWidth, h = el.offsetHeight;
  let left = Math.min(r.right - w, window.innerWidth - w - 8);
  let top = r.bottom + 6;
  if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
  el.style.left = Math.max(8, left) + 'px';
  el.style.top = top + 'px';
  starMenuEl = el;

  el.onclick = (ev) => {
    const mi = ev.target.closest('.mi');
    if (!mi) return;
    if (mi.dataset.new) {
      const nm = prompt('新收藏夹的名字：', '我的收藏夹');
      if (nm) { const f = createFolder(nm, [name]); if (f) { closeStarMenu(); renderList(true); } }
      return;
    }
    if (mi.dataset.clear) {
      folderNames().forEach((f) => removeFromFolder([name], f));
      closeStarMenu(); renderList(true);
      toast('已从所有收藏夹移除');
      return;
    }
    const f = mi.dataset.f;
    if (!f) return;
    if (mine.includes(f)) removeFromFolder([name], f); else addToFolder([name], f);
    closeStarMenu();
    renderList(true);
    toast(mine.includes(f) ? ('已从「' + f + '」移出') : ('已加入「' + f + '」'));
  };
}
document.addEventListener('click', closeStarMenu);

/* ============================================================
   指令集 / 配置方案 界面
   ============================================================ */
let planCurrent = null;      // 当前方案 id

function planOpen() {
  if (!S.plans || !S.plans.length) {
    // 没有方案时，用当前配置生成器里的指令先建一个
    const items = (S.cfg || []).map((c) => ({ n: c.n, v: String(c.v == null ? '' : c.v) }));
    if (items.length) addPlan('方案 1', null, items);
    else {
      const one = S.current ? [{ n: S.current.n, v: String(S.current.d == null ? '' : S.current.d) }] : [];
      if (one.length) addPlan('方案 1', null, one);
    }
  }
  if (!planCurrent || !S.plans.some((x) => x.id === planCurrent)) {
    planCurrent = S.plans.length ? S.plans[0].id : null;
  }
  renderPlans();
  openDrawer('plan');
}

function renderPlans() {
  const tabs = $('#planTabs');
  const box = $('#planEditor');
  if (!tabs || !box) return;

  tabs.innerHTML = (S.plans || []).map((pl) => `
    <span class="plan-tab ${pl.id === planCurrent ? 'on' : ''}" data-plan="${pl.id}">
      ${esc(pl.name)}<span class="ct">${pl.items.length}</span></span>`).join('')
    + '<span class="plan-tab add" id="planTabNew">＋ 新方案</span>';

  tabs.onclick = (ev) => {
    const add = ev.target.closest('#planTabNew');
    if (add) { planNew(); return; }
    const tab = ev.target.closest('[data-plan]');
    if (!tab) return;
    planCurrent = tab.dataset.plan;
    renderPlans();
  };

  const pl = (S.plans || []).find((x) => x.id === planCurrent);
  if (!pl) {
    box.innerHTML = '<div class="plan-card"><div class="fav-empty">还没有指令集。点「＋ 新方案」开始。</div></div>';
    return;
  }

  box.innerHTML = `
    <div class="plan-card">
      <div class="plan-head">
        <b>${esc(pl.name)}</b>
        <span class="plan-meta">${pl.items.length} 条${pl.folder ? ' · 来自「' + esc(pl.folder) + '」' : ''}</span>
      </div>
      <div class="plan-list">
        ${pl.items.length ? pl.items.map((it, i) => {
          const e = S.entries.find((x) => x.n === it.n) || {};
          return `<div class="plan-row" data-i="${i}">
            <span class="pn" title="${esc(it.n)}">${esc(it.n)}</span>
            <input class="pv" value="${esc(it.v)}" data-val="${i}" spellcheck="false">
            <span class="px" data-del="${i}" title="移除">✕</span>
            <span class="pz">${esc(e.z || '')}</span>
          </div>`;
        }).join('') : '<div class="fav-empty">这套还是空的，点下面「从收藏夹添加」或「手动添加」。</div>'}
      </div>
      <div class="plan-actions">
        <button class="btn tiny ghost" id="planAddFav">＋ 从收藏夹添加</button>
        <button class="btn tiny ghost" id="planAddOne">＋ 手动添加</button>
        <button class="btn tiny ghost" id="planRename">重命名</button>
        <button class="btn tiny ghost" id="planSaveCfg">写进 cfg</button>
        <button class="btn tiny ghost" id="planDel">删除方案</button>
      </div>
      <div class="console-pre" id="planPre">${esc(planText(pl))}</div>
      <button class="big-cta" id="planCopy">📋 复制全部指令（一次输入控制台）</button>
    </div>`;

  const sync = () => {
    const pre = $('#planPre');
    if (pre) pre.textContent = planText(pl);
  };

  box.oninput = (ev) => {
    const inp = ev.target.closest('[data-val]');
    if (!inp) return;
    const i = Number(inp.dataset.val);
    pl.items[i].v = inp.value;
    pl.updated = Date.now();
    savePlans();
    sync();
  };
  box.onclick = (ev) => {
    const del = ev.target.closest('[data-del]');
    if (del) {
      pl.items.splice(Number(del.dataset.del), 1);
      pl.updated = Date.now();
      savePlans();
      renderPlans();
      return;
    }
    if (ev.target.closest('#planCopy')) {
      copy(planText(pl), '已复制 ' + pl.items.length + ' 条指令，粘进控制台即可');
      return;
    }
    if (ev.target.closest('#planSaveCfg')) {
      pl.items.forEach((it) => {
        if (!S.cfg.some((c) => c.n === it.n)) S.cfg.push({ n: it.n, v: it.v });
      });
      save('cfg', S.cfg);
      renderCfg();
      toast('已加入配置生成器');
      return;
    }
    if (ev.target.closest('#planRename')) {
      const nm = prompt('新的方案名：', pl.name);
      if (nm) { pl.name = nm.trim() || pl.name; savePlans(); renderPlans(); }
      return;
    }
    if (ev.target.closest('#planDel')) {
      if (!confirm('删除方案「' + pl.name + '」？')) return;
      removePlan(pl.id);
      planCurrent = S.plans.length ? S.plans[0].id : null;
      renderPlans();
      return;
    }
    if (ev.target.closest('#planAddFav')) {
      const folders = listFolders();
      if (!folders.length) { toast('还没有收藏夹，先去添加'); return; }
      const pick = prompt('从哪个收藏夹添加？\n' + folders.map((f, i) => (i + 1) + '. ' + f.name).join('\n'), '1');
      const idx = Number(pick) - 1;
      if (!(idx >= 0 && idx < folders.length)) return;
      const fname = folders[idx].name;
      const names = Object.keys(S.favItems).filter((n) => (S.favItems[n] || []).includes(fname));
      let added = 0;
      names.forEach((n) => {
        if (pl.items.some((x) => x.n === n)) return;
        const e = S.entries.find((x) => x.n === n) || {};
        pl.items.push({ n, v: String(e.d == null ? '' : e.d) });
        added++;
      });
      pl.folder = fname;
      savePlans(); renderPlans();
      toast('从「' + fname + '」添加了 ' + added + ' 条');
      return;
    }
    if (ev.target.closest('#planAddOne')) {
      const n = prompt('指令名（例如 sv_airaccelerate）：', '');
      if (!n) return;
      const e = S.entries.find((x) => x.n === n.trim());
      if (!e) { toast('指令库里没有这条指令'); return; }
      pl.items.push({ n: e.n, v: String(e.d == null ? '' : e.d) });
      savePlans(); renderPlans();
      return;
    }
  };
}

function planNew() {
  const nm = prompt('新指令集的名字：', '方案 ' + ((S.plans || []).length + 1));
  if (!nm) return;
  const one = S.current ? [{ n: S.current.n, v: String(S.current.d == null ? '' : S.current.d) }] : [];
  if (!one.length) { toast('请先在列表里选中一条指令'); return; }
  const pl = addPlan(nm, null, one);
  planCurrent = pl.id;
  renderPlans();
  toast('已新建指令集「' + nm + '」');
}

/* ---------------- 抽屉控制 ---------------- */
function openDrawer(which) {
  if (which === 'set') { openSettings(); return; }
  const map = { ai: '#aiDrawer', cfg: '#cfgDrawer', help: '#helpDrawer',
                plan: '#planDrawer', disc: '#discDrawer', about: '#aboutDrawer' };
  Object.values(map).forEach((s) => { const el = $(s); if (el) el.classList.add('hidden'); });
  const el = $(map[which]);
  if (el) el.classList.remove('hidden');
}

/* ---------- 新按钮接线 ---------- */
(function wireShell() {
  // 主页：选模式
  const pick = (m) => {
    localStorage.setItem(ONBOARD_KEY, '1');
    showWorkspace(m);
  };
  const pc = $('#pickCard'); const pp = $('#pickPro');
  if (pc) {
    pc.onclick = () => pick('card');
    pc.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick('card'); } };
  }
  if (pp) {
    pp.onclick = () => pick('pro');
    pp.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick('pro'); } };
  }

  // 主页悬浮按钮
  const ht = $('#homeTheme'); if (ht) ht.onclick = cycleTheme;
  const hs = $('#homeSettings'); if (hs) hs.onclick = openSettings;

  // 顶栏控制组
  const bh = $('#btnHome'); if (bh) bh.onclick = showHome;
  const bt = $('#btnTheme'); if (bt) bt.onclick = cycleTheme;
  const bs = $('#btnSettings'); if (bs) bs.onclick = openSettings;
  const bcTop = $('#btnCfgTop'); if (bcTop) bcTop.onclick = () => { renderCfg(); openDrawer('cfg'); };
  const bgTop = $('#btnGuardTop'); if (bgTop) bgTop.onclick = () => { renderGuard(); };

  // 侧栏：＋ 添加收藏夹（第 1 步）
  const bfa = $('#btnFavAdd'); if (bfa) bfa.onclick = () => favNewFolderFlow();

  // 模式切换按钮 + 下拉
  const bm = $('#btnMode'); const mm = $('#menuMode');
  if (bm && mm) {
    bm.onclick = (e) => {
      e.stopPropagation();
      const was = mm.classList.contains('hidden');
      closeMenus();
      if (was) { mm.classList.remove('hidden'); placeMenu(mm, bm); }
    };
  }
  const bMore = $('#btnMore'); const mMore = $('#menuMore');
  if (bMore && mMore) {
    bMore.onclick = (e) => {
      e.stopPropagation();
      const was = mMore.classList.contains('hidden');
      closeMenus();
      if (was) { mMore.classList.remove('hidden'); placeMenu(mMore, bMore); }
    };
  }
  if (mm) mm.onclick = (e) => {
    const mi = e.target.closest('.mi');
    if (!mi) return;
    closeMenus();
    if (mi.dataset.mode) { setMode(mi.dataset.mode); renderList(true); }
    else if (mi.dataset.act === 'home') showHome();
  };
  if (mMore) mMore.onclick = (e) => {
    const mi = e.target.closest('.mi');
    if (!mi) return;
    closeMenus();
    const a = mi.dataset.act;
    if (a === 'cfg') { planOpen(); }
    else if (a === 'ai') { const b = $('#btnAI'); if (b) b.click(); }
    else if (a === 'help') { openDrawer('help'); }
    else if (a === 'toggleEn') {
      const order = ['zh', 'both', 'en'];
      const next = order[(order.indexOf(S.lang) + 1) % order.length];
      applyLang(next);
      toast('语言显示：' + ({ zh: '仅中文', en: '仅英文', both: '中英对照' }[next]));
    }
  };

  // 设置面板
  const sc = $('#settingsClose'); if (sc) sc.onclick = closeSettings;
  const sm = $('#settingsMask'); if (sm) sm.onclick = closeSettings;
  const gs = $('#btnGuardSet'); if (gs) gs.onclick = () => { renderGuard(); };
  const hset = $('#btnHelpSet'); if (hset) hset.onclick = () => { closeSettings(); openDrawer('help'); };
  const dset = $('#btnDiscSet'); if (dset) dset.onclick = () => { closeSettings(); openDrawer('disc'); };
  // cfg 导出方式
  const segm = $('#segCfgMode');
  if (segm) {
    setCfgMode(getCfgMode());   // 回填高亮与说明
    segm.onclick = (ev) => {
      const btn = ev.target.closest('button[data-mode]');
      if (btn) setCfgMode(btn.dataset.mode);
    };
  }
  // 打开设置时顺便显示游戏 cfg 目录
  (async () => {
    const line = $('#cfgDirLine');
    if (!line) return;
    try {
      const r = await (await fetch('api/game/cfgdir', { cache: 'no-store' })).json();
      line.textContent = r && r.dir ? ('游戏 cfg 目录：' + r.dir) : '没找到游戏 cfg 目录（可改用手动放置）';
    } catch (e) {
      line.textContent = '游戏 cfg 目录：需本地服务（离线模式下不可用）';
    }
  })();
  const aset = $('#btnAboutSet'); if (aset) aset.onclick = () => { closeSettings(); openDrawer('about'); };

  // 主题色板
  const pre = $('#accentPresets');
  if (pre) {
    pre.innerHTML = ACCENT_PRESETS.map((p) =>
      '<button data-accent="' + p.hex + '" title="' + p.name + ' ' + p.hex + '" '
      + 'style="background:' + p.hex + '"></button>').join('');
    pre.onclick = (ev) => {
      const b = ev.target.closest('[data-accent]');
      if (b) setAccent(b.dataset.accent);
    };
  }
  const ac = $('#accentCustom');
  if (ac) ac.addEventListener('input', () => setAccent(ac.value));
  const ar = $('#accentReset');
  if (ar) ar.onclick = resetAccent;
  applyAccent();

  // 主题分段控件
  const seg = $('#segTheme');
  if (seg) seg.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    localStorage.setItem(THEME_KEY, b.dataset.theme);
    applyTheme(true);
  };

  // 启动行为
  $$('input[name="startMode"]').forEach((r) => {
    r.addEventListener('change', () => {
      if (!r.checked) return;
      // 只在值真的变化时写入，避免回填 checked 时把设置改掉
      const cur = localStorage.getItem('cs2hub.startMode') || 'last';
      if (cur !== r.value) localStorage.setItem('cs2hub.startMode', r.value);
    });
  });

  // 顶栏入口显隐
  const topMap = [
    ['#setTopGuard', '#btnGuardTop', 'topGuard'],
    ['#setTopTheme', '#btnTheme', 'topTheme'],
    ['#setTopCfg', '#btnCfgTop', 'topCfg'],
  ];
  const applyTopVis = () => {
    topMap.forEach(([inp, sel, key]) => {
      const on = localStorage.getItem('cs2hub.' + key) !== '0';
      const el = $(sel);
      if (el) el.classList.toggle('hidden', !on);
      const cb = $(inp);
      if (cb) cb.checked = on;
    });
  };
  topMap.forEach(([inp, , key]) => {
    const cb = $(inp);
    if (!cb) return;
    cb.addEventListener('change', () => {
      localStorage.setItem('cs2hub.' + key, cb.checked ? '1' : '0');
      applyTopVis();
    });
  });
  applyTopVis();

  // 快捷键
  document.addEventListener('keydown', (ev) => {
    const inField = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (ev.key === 'Escape') { closeMenus(); closeSettings(); return; }
    if ((ev.ctrlKey || ev.metaKey) && ev.key === ',') {
      ev.preventDefault(); openSettings(); return;
    }
    if (inField) return;
    if (ev.key === 'm' || ev.key === 'M') {
      const next = getMode() === 'pro' ? 'card' : 'pro';
      setMode(next); renderList(true);
      toast('已切到' + (next === 'pro' ? '专业模式' : '卡片模式'));
    } else if (ev.key === 'h' || ev.key === 'H') {
      showHome();
    } else if (ev.key === 's' || ev.key === 'S') {
      favOpenPanel();
    } else if (ev.key === 'l' || ev.key === 'L') {
      renderGuard();
    }
  });
})();

/* 把菜单摆到触发按钮的正下方（超出视口时自动回收） */
function placeMenu(menu, btn) {
  if (!menu || !btn) return;
  menu.style.position = 'fixed';
  menu.style.right = 'auto';
  menu.style.bottom = 'auto';
  const r = btn.getBoundingClientRect();
  const w = menu.offsetWidth || 200;
  const h = menu.offsetHeight || 200;
  let left = r.left;                      // 与按钮左边缘对齐
  let top = r.bottom + 6;                 // 按钮下方 6px
  if (left + w > window.innerWidth - 8) left = window.innerWidth - w - 8;
  if (left < 8) left = 8;
  if (top + h > window.innerHeight - 8) {
    top = Math.max(8, r.top - h - 6);     // 放不下就翻到按钮上方
  }
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
}

function closeMenus() { $$('.menu').forEach((m) => m.classList.add('hidden')); }
/* 「复制」按钮：任何带 data-copy 的元素，点了就复制它的内容 */
document.addEventListener('click', (ev) => {
  const c = ev.target.closest('[data-copy]');
  if (!c) return;
  ev.stopPropagation();
  copy(c.dataset.copy, '已复制：' + c.dataset.copy);
});

/* 窗口尺寸变化 / 滚动时，锚定位置会失效，直接收起菜单 */
window.addEventListener('resize', closeMenus);
window.addEventListener('scroll', closeMenus, { passive: true, capture: true });
document.addEventListener('click', closeMenus);

function closeDrawers() { $$('.drawer').forEach((d) => d.classList.add('hidden')); }
document.addEventListener('click', (ev) => {
  const c = ev.target.closest('[data-close]');
  if (c) closeDrawers();
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape') closeDrawers();
  if (ev.key === '/' && document.activeElement.tagName !== 'INPUT'
      && document.activeElement.tagName !== 'TEXTAREA') {
    ev.preventDefault(); $('#search').focus();
  }
});

/* ---------------- 搜索与筛选事件 ---------------- */
let searchTimer = null;
$('#search').addEventListener('input', (ev) => {
  S.kw = ev.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (S.kw.trim()) { S.cat = ''; S.sub = ''; S.special = ''; }
    applyFilter();
  }, 130);
});
// 筛选开关（设置面板）：仅游戏内确认 / 仅实用指令 / 仅正式版下发
['#setOnlyCore', '#setOnlyRelease'].forEach((s) => {
  const el = $(s);
  if (!el) return;
  el.addEventListener('change', () => applyFilter());
});
// 语言显示：三选一（记忆在本地）
function applyLang(v) {
  S.lang = v;
  localStorage.setItem('cs2hub.lang', v);
  const seg = $('#segLang');
  if (seg) seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.lang === v));
  const k = $('#mmEn');
  if (k) k.textContent = { zh: '仅中文', en: '仅英文', both: '中英对照' }[v] || v;
  renderList(true);
  if (S.current) showDetail(S.current);
  renderCfg();
}
{
  const seg = $('#segLang');
  if (seg) {
    seg.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.lang === S.lang));
    seg.onclick = (ev) => {
      const btn = ev.target.closest('button[data-lang]');
      if (btn) applyLang(btn.dataset.lang);
    };
  }
  const k = $('#mmEn');
  if (k) k.textContent = { zh: '仅中文', en: '仅英文', both: '中英对照' }[S.lang] || S.lang;
}
/* 把某条指令的卡片滚进视野并高亮。
   注意：列表是分片渲染的（pageSize 条一批），目标可能还没渲染出来，
   所以先在 view 里定位它的下标，需要的话把那之前的条目也渲染出来。 */
function revealEntry(name) {
  const idx = S.view.findIndex((x) => x.n === name);
  if (idx < 0) return false;
  // renderList 的语义：reset=true 会清空 DOM，但只渲染 [S.shown, S.shown+pageSize)，
  // 所以必须先把 S.shown 归零重来，再一页页追加到覆盖目标位置为止。
  S.shown = 0;
  renderList(true);                              // 清空 + 第 1 页
  let guard = 0;
  while (S.shown <= idx && S.shown < S.view.length && guard++ < 200) {
    renderList(false);                           // 追加下一页，直到目标被渲染出来
  }
  const paint = () => {
    const row = document.querySelector('#list .row[data-name="' + CSS.escape(name) + '"]');
    if (!row) return false;
    row.scrollIntoView({ block: 'center' });
    row.classList.remove('picked');
    void row.offsetWidth;          // 强制重排，保证动画重放
    row.classList.add('picked');
    setTimeout(() => row.classList.remove('picked'), 1800);
    return true;
  };
  // 等一帧让布局稳定再滚（卡片模式下 content-visibility 也要先算好高度）
  if (!paint()) requestAnimationFrame(paint);
  return true;
}

$('#btnRandom').onclick = () => {
  const pool = S.entries.filter((e) => e.k);
  const e = pool[Math.floor(Math.random() * pool.length)];
  S.kw = ''; $('#search').value = '';
  S.cat = e.c; S.sub = '';
  applyFilter();
  showDetail(e);
  revealEntry(e.n);
};

$('#btnFav').onclick = () => favOpenPanel();
$('#btnCfg').onclick = () => { renderCfg(); openDrawer('cfg'); };
$('#btnHelp').onclick = () => openDrawer('help');
$('#btnAI').onclick = () => openDrawer('ai');

/* ---------------- AI 接口设置 ---------------- */
function loadSettings() {
  $('#setBase').value = S.settings.base_url || '';
  $('#setKey').value = S.settings.api_key || '';
  $('#setModel').value = S.settings.model || '';
  $('#setMaxTokens').value = budgetOf();
}
const BASES = [
  ['DeepSeek', 'https://api.deepseek.com/v1'],
  ['OpenAI', 'https://api.openai.com/v1'],
  ['通义千问', 'https://dashscope.aliyuncs.com/compatible-mode/v1'],
  ['智谱 GLM', 'https://open.bigmodel.cn/api/paas/v4'],
  ['本地 Ollama', 'http://127.0.0.1:11434/v1'],
];
$('#basePresets').innerHTML = BASES
  .map(([n, u]) => `<button data-base="${u}">${n}</button>`).join('');
$('#basePresets').addEventListener('click', (ev) => {
  const b = ev.target.closest('button');
  if (b) $('#setBase').value = b.dataset.base;
});

$('#btnAISettings').onclick = () => { loadSettings(); openDrawer('set'); };
$('#btnSetSave').onclick = () => {
  S.settings = {
    base_url: $('#setBase').value.trim() || 'https://api.deepseek.com/v1',
    api_key: $('#setKey').value.trim(),
    model: $('#setModel').value.trim() || 'deepseek-chat',
  };
  save('ai', S.settings);
  const mt = parseInt($('#setMaxTokens').value, 10);
  if (Number.isFinite(mt) && mt >= 256) localStorage.setItem('cs2hub.maxTokens', String(mt));
  else localStorage.removeItem('cs2hub.maxTokens');
  $('#setStatus').className = 'ai-status ok';
  $('#setStatus').textContent = '已保存到本机浏览器（输出预算 ' + budgetOf() + '）。';
  toast('AI 设置已保存');
};
$('#btnSetClear').onclick = () => {
  localStorage.removeItem('cs2hub.ai');
  S.settings = { base_url: 'https://api.deepseek.com/v1', api_key: '', model: 'deepseek-chat' };
  loadSettings();
  $('#setStatus').className = 'ai-status';
  $('#setStatus').textContent = '已清除。';
};
$('#btnSetTest').onclick = async () => {
  const st = $('#setStatus');
  st.className = 'ai-status';
  st.textContent = '正在测试…';
  save('ai', {
    base_url: $('#setBase').value.trim(), api_key: $('#setKey').value.trim(),
    model: $('#setModel').value.trim() || 'deepseek-chat',
  });
  S.settings = JSON.parse(localStorage.getItem('cs2hub.ai'));
  try {
    const r = await aiCall([{ role: 'user', content: '只回复两个字：可用' }], { max_tokens: 512 });
    st.className = 'ai-status ok';
    st.textContent = '连接成功：' + r.content.slice(0, 40);
  } catch (err) {
    st.className = 'ai-status err';
    st.textContent = '失败：' + err.message;
  }
};

/* AI 自检：把每一步的结果摊开，出问题时可直接把报告贴给我。
   注意：直接用输入框里的值，不要求先保存，避免「刚填完 Key 就报缺 Key」。*/
$('#btnSetDiag').onclick = async () => {
  const out = $('#diagOut');
  out.classList.remove('hidden');
  $('#btnDiagCopy').classList.remove('hidden');
  const lines = [];
  const log = (s) => { lines.push(s); out.textContent = lines.join('\n'); };
  const key = $('#setKey').value.trim();
  const base = $('#setBase').value.trim() || 'https://api.deepseek.com/v1';
  const model = $('#setModel').value.trim() || 'deepseek-chat';
  // 用输入框的值临时覆盖设置（并顺手保存，省得用户再点一次）
  S.settings = { base_url: base, api_key: key, model: model };
  save('ai', S.settings);

  log('=== CS2 指令查询中心 · AI 自检 ===');
  log('时间：' + new Date().toLocaleString('zh-CN'));
  log('页面版本：' + (S.meta && S.meta.version ? S.meta.version : '未知') +
      ' | 指令库：' + (S.entries.length || 0) + ' 条');
  log('运行模式：' + (S.serverMode ? '本地服务' : '离线 file://（AI 不可用）'));
  log('接口地址：' + base);
  log('模型：' + model);
  log('Key：' + (key ? key.slice(0, 6) + '…' + key.slice(-4) + '（长度 ' + key.length + '）' : '（空，请填写）'));
  log('');
  if (!key) {
    log('已停止：没有填写 API Key。');
    return finish();
  }

  log('[1/4] 本地服务连通性 …');
  try {
    const h = await (await fetch('api/health', { cache: 'no-store' })).json();
    log('    OK  服务正常，Python ' + h.python + '，根目录 ' + h.root);
  } catch (e) {
    log('    失败  连不上本地服务：' + e.message);
    log('    → 请确认 start.cmd 的窗口还开着，再刷新页面');
    return finish();
  }
  log('[2/4] 本地服务 -> 上游接口 …');
  log('    本次输出预算：' + budgetOf() + ' tokens（推理型模型的"思考"也占这个预算）');
  try {
    // 推理型模型光"思考"就能吃掉几百 token，探测预算给足，否则会误报成"Key 失效"
    const d = await aiCall([{ role: 'user', content: 'ping' }], { max_tokens: 512 });
    log('    OK  上游可用，模型 ' + d.model + '，用量 ' + JSON.stringify(d.usage || {}));
    log('    返回内容：' + String(d.content).slice(0, 60));
  } catch (e) {
    log('    失败  ' + e.message);
    if (e.detail) log('    原始响应：' + JSON.stringify(e.detail).slice(0, 400));
    const det = ((e.detail || {}).usage || {}).completion_tokens_details || {};
    if ((e.detail || {}).truncated_by_reasoning || det.reasoning_tokens) {
      log('    → 判定：这是**推理型模型把输出预算用光了**，不是 Key / 余额 / 地址的问题');
      log('      处理：换 deepseek-chat；或在接口设置里把「输出预算 max_tokens」调大');
    } else {
      log('    → 常见原因：Key 失效（401）、余额不足（402）、模型名或 Base URL 写错（404）、限流（429）');
    }
    return finish();
  }
  log('[3/4] 账户可用模型列表（用来排除"模型名写错"）…');
  try {
    const r = await fetch('api/ai/models', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: base, api_key: key }),
    });
    const d = await r.json();
    if (!d.ok) {
      log('    跳过  ' + (d.error || '读取失败') + (d.hint ? '（' + d.hint + '）' : ''));
    } else if (!d.count) {
      log('    注意  上游没有返回任何模型名（有些网关不提供 /models 接口）');
    } else {
      log('    OK  共 ' + d.count + ' 个：' + d.models.slice(0, 12).join(', ') +
          (d.count > 12 ? ' …' : ''));
      if (d.models.indexOf(model) >= 0) {
        log('    当前模型 ' + model + ' 在列表中 ✅');
      } else {
        log('    ⚠ 当前模型 ' + model + ' **不在**这个列表里');
        log('      → 要么模型名写错了，要么该网关用了别名。建议从上面挑一个填进「模型」框');
      }
    }
  } catch (e) {
    log('    跳过  取模型列表失败：' + e.message);
  }
  log('[4/4] 真实问答链路（带指令库上下文）…');
  try {
    const t0 = Date.now();
    const d = await aiCall(buildMessages('plan', '把准星改成绿色小十字'));
    log('    OK  ' + ((Date.now() - t0) / 1000).toFixed(1) + ' 秒，' +
        (d.usage && d.usage.total_tokens ? d.usage.total_tokens + ' tokens，' : '') +
        '正文 ' + String(d.content).length + ' 字符');
  } catch (e) {
    log('    失败  ' + e.message);
    if (e.detail) log('    原始响应：' + JSON.stringify(e.detail).slice(0, 400));
    const det2 = ((e.detail || {}).usage || {}).completion_tokens_details || {};
    if ((e.detail || {}).truncated_by_reasoning || det2.reasoning_tokens) {
      log('    → 判定：推理型模型把输出预算用光，正文为空。换 deepseek-chat 或调大 max_tokens');
    }
    return finish();
  }
  log('');
  log('结论：AI 通路完全正常。若界面里仍看不到回答，请把这份报告贴给我。');
  finish();

  function finish() {
    lines.push('');
    lines.push('（以上内容可点下方按钮复制，直接发给我排查）');
    out.textContent = lines.join('\n');
    if (/结论：AI 通路完全正常/.test(lines.join('\n'))) {
      $('#setStatus').className = 'ai-status ok';
      $('#setStatus').textContent = '自检通过：AI 通路正常，设置已保存。';
      loadSettings();
    }
  }
};
$('#btnDiagCopy').onclick = () => copy($('#diagOut').textContent, '自检报告已复制');

/* 输出预算默认值。
   推理型模型（deepseek-reasoner / v4-pro 之类）会先"思考"再作答，思考也占输出预算。
   我们的 system prompt 里带几十条指令库摘录，光思考就可能上千 token，
   所以默认给足；不够时 aiCall 还会自动升档重试。*/
const DEFAULT_MAX_TOKENS = 8192;
const MAX_TOKENS_CEILING = 32768;

function budgetOf() {
  const n = parseInt(localStorage.getItem('cs2hub.maxTokens') || '', 10);
  return Number.isFinite(n) && n >= 256 ? n : DEFAULT_MAX_TOKENS;
}

async function aiCallOnce(messages, maxTokens, opts) {
  let r;
  try {
    r = await fetch('api/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: S.settings.base_url,
        api_key: S.settings.api_key,
        model: S.settings.model,
        messages,
        temperature: opts.temperature != null ? opts.temperature : 0.25,
        max_tokens: maxTokens,
      }),
    });
  } catch (err) {
    throw new Error('连不上本地服务（' + err.message + '）。请确认 start.cmd 的窗口还开着。');
  }
  const text = await r.text();
  let d = null;
  try { d = JSON.parse(text); } catch (e) { /* 非 JSON */ }
  if (!d) {
    throw new Error(`本地服务返回了非 JSON 响应（HTTP ${r.status}）：${text.slice(0, 160)}`);
  }
  if (!d.ok) {
    const parts = [d.error || '请求失败'];
    if (d.hint) parts.push(d.hint);
    if (d.detail) parts.push('上游信息：' + String(d.detail).slice(0, 200));
    const err = new Error(parts.join(' —— '));
    err.detail = d;
    throw err;
  }
  d.__maxTokens = maxTokens;
  return d;
}

async function aiCall(messages, opts = {}) {
  if (!S.serverMode) {
    throw new Error('AI 功能需要通过本地服务运行（双击 start.cmd 启动），离线模式不可用。');
  }
  if (!S.settings.api_key) {
    openDrawer('set'); loadSettings();
    throw new Error('请先填写 API Key（右上角 ✨ → ⚙ 接口设置）。');
  }

  let budget = opts.max_tokens || budgetOf();
  for (let attempt = 0; attempt < 4; attempt++) {
    const d = await aiCallOnce(messages, budget, opts);
    if (d.content && String(d.content).trim()) return d;

    // 正文为空：如果是"预算被推理吃光"，直接跳到足量预算重试——
    // 慢吞吞地翻倍（512→1024→2048）会连着失败好几次，白白多等好几轮。
    const u = d.usage || {};
    const det = u.completion_tokens_details || {};
    const usedReasoning = !!d.truncated_by_reasoning || !!det.reasoning_tokens;
    const next = Math.min(
      Math.max(budget * 2, 4096, budgetOf()),
      MAX_TOKENS_CEILING);
    if (usedReasoning && next > budget) {
      if (S.onBudgetBump) S.onBudgetBump(budget, next, det.reasoning_tokens || 0);
      budget = next;
      continue;
    }

    let msg = d.hint;
    if (!msg) {
      if (usedReasoning) {
        msg = '模型把 ' + (det.reasoning_tokens || '') + ' 个输出 token 全用在推理上了，正文没轮到'
            + '（max_tokens=' + budget + '，已尝试升到上限 ' + MAX_TOKENS_CEILING + '）。'
            + '建议改用 deepseek-chat 这类非推理模型。';
      } else {
        msg = '模型返回了空内容（可能被安全策略拦截、或模型名不存在被网关静默返回空）。'
            + '换个说法或换 deepseek-chat 试一次即可区分。';
      }
    }
    const err = new Error(msg);
    err.detail = d;
    throw err;
  }
  throw new Error('已多次升档重试仍未得到正文，建议改用 deepseek-chat。');
}

/* ---------------- AI 辅助主流程 ---------------- */
const AI_EXAMPLES = [
  '准星改成绿色小十字，静态不扩散',
  '我想让画面更亮但帧率更高',
  '练习米拉吉烟雾弹，需要显示投掷轨迹',
  '把雷达调到能看全图、队友头顶常显 ID',
  '鼠标是 800 DPI，帮我算个合适的灵敏度',
  '练枪服：无限弹药 + 电脑玩家不动',
  '我的游戏有点卡，帮我看网络和帧率相关的指令',
  '做一个一键跳投的按键绑定',
];
$('#aiExamples').innerHTML = AI_EXAMPLES
  .map((t) => `<button data-ex="${esc(t)}">${esc(t)}</button>`).join('');
$('#aiExamples').addEventListener('click', (ev) => {
  const b = ev.target.closest('button');
  if (!b) return;
  $('#aiInput').value = b.dataset.ex;
  sendAI();
});
$('#btnAISend').onclick = () => sendAI();
$('#aiInput').addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) sendAI();
});

/* 以用户需求为关键词，从本地库检索最相关的指令作为上下文。
   中文需求必须走「二元字组 + 同义词」，否则整句会被当成一个词、一条都命中不了。*/
function relevantContext(query, limit = 46) {
  const q = (query || '').toLowerCase();
  const asciiTerms = q.split(/[^a-z0-9_+]+/).filter((t) => t.length >= 2);
  const bigrams = cnBigrams(query);
  const scored = S.entries.map((e) => {
    const hay = searchIndex(e);
    const name = e.n.toLowerCase();
    let s = 0;
    // 1) 英文关键词：按词命中
    asciiTerms.forEach((t) => { if (hay.includes(t)) s += 14; });
    // 2) 中文词：二元字组覆盖率
    if (bigrams.length) {
      let hit = 0;
      for (const bg of bigrams) if (hay.includes(bg)) hit++;
      s += (hit / bigrams.length) * 60;
      // 指令名本身含这些字（极少见，命中就是强信号）
      let nHit = 0;
      for (const bg of bigrams) if (name.includes(bg)) nHit++;
      if (nHit) s += nHit * 8;
    }
    // 3) 同义词桥接（"随地安放炸弹" → anywhere + c4 + plant）
    s += synonymBoost(hay, query);
    // 4) 短名优先 + 同族加成：问"音量"时 volume 应该压过 snd_deathcamera_volume_armsrace
    s += Math.max(0, 22 - e.n.length) * 0.5;
    if (asciiTerms.length) {
      const first = asciiTerms[0];
      if (name === first) s += 45;
      else if (name.startsWith(first + '_')) s += 26;
      else if (name.includes(first)) s += 12;
    }
    if (e.k) s += 4;
    if (e.q === 2) s += 6;
    if (e.r) s += 2;
    return { e, s };
  }).filter((x) => x.s > 12).sort((a, b) => b.s - a.s).slice(0, limit).map((x) => x.e);

  // 若关键词几乎没命中，退化为热门实用指令
  const pool = scored.length >= 6 ? scored : S.entries.filter((e) => e.q === 2).slice(0, limit);
  return pool.map((e) => `${e.n} (${e.s}, 默认${e.d != null ? e.d : '—'}): ${(e.z || e.en || '').slice(0, 90)}`).join('\n');
}

function buildMessages(mode, input) {
  const ctx = relevantContext(input);
  const sys = `你是 CS2（Counter-Strike 2）控制台与配置专家，服务中文玩家。当前时间背景下最新版本为 CS2。` +
    `回答必须基于下面给出的「本地指令库摘录」，不要虚构不存在的指令；若确实需要库中没有的指令，明确标注「需自行核实」。\n` +
    `建议的指令要有：指令名、推荐值、作用。给出可直接粘贴的 cfg 片段时用 \`\`\` 代码块。\n` +
    `注意区分客户端指令（cl_，只影响自己）与服务器端指令（sv_/mp_，需要自建服或本地），` +
    `涉及 sv_cheats 的作弊类指令要提醒「仅本地/私人服有效，官方匹配无效」。\n\n` +
    `【本地指令库摘录】\n${ctx}`;

  const modes = {
    plan: '用户想要的游戏效果如下，请给出实现方案：先列出相关指令表（指令｜推荐值｜作用），再给一段 cfg 配置代码块，最后写注意事项。',
    explain: '请解释下面这条/这些指令：作用、取值范围、默认值、对游戏的影响、推荐设置与常见坑。',
    cfg: '请生成一份完整的 cfg 配置文件内容（含注释），满足下面的需求，并说明保存路径与 exec 用法。',
    fix: '用户遇到了一个问题，请先判断常见原因，再给出可能相关的指令与排查步骤，按可能性排序。',
  };
  return [
    { role: 'system', content: sys },
    { role: 'user', content: modes[mode] + '\n\n用户需求：' + input },
  ];
}

let aiBusy = false;
async function sendAI() {
  const input = $('#aiInput').value.trim();
  if (!input) { toast('先描述一下你想要的效果'); return; }
  if (aiBusy) return;
  const mode = $('#aiMode').value;
  const out = $('#aiOutput'), st = $('#aiStatus');
  aiBusy = true;
  $('#btnAISend').disabled = true;
  st.className = 'ai-status';
  st.textContent = 'AI 正在思考…（输出预算 ' + budgetOf() + ' tokens）';
  out.innerHTML = '<p class="typing dim">正在检索本地指令库并请求模型…</p>';
  // 预算被推理吃光时自动升档：把过程说清楚，用户不必自己猜
  S.onBudgetBump = (from, to, reasoning) => {
    st.className = 'ai-status';
    st.textContent = `模型把 ${reasoning} 个 token 用在推理上了，正文没轮到 —— 已自动把输出预算从 ${from} 提到 ${to} 重试…`;
  };
  try {
    const r = await aiCall(buildMessages(mode, input));
    st.className = 'ai-status ok';
    st.textContent = `完成 · 模型 ${r.model}` +
      (r.usage && r.usage.total_tokens ? ` · 用量 ${r.usage.total_tokens} tokens` : '') +
      (r.__maxTokens && r.__maxTokens !== budgetOf() ? ` · 本次预算升到 ${r.__maxTokens}` : '');
    renderAI(r.content);
  } catch (err) {
    st.className = 'ai-status err';
    st.textContent = '出错：' + err.message;
    const det = err.detail ? JSON.stringify(err.detail).slice(0, 400) : '';
    out.innerHTML = `<p class="dim">排错建议：</p><ul class="dim">
        <li>打开 <b>⚙ 接口设置 → 🩺 AI 自检</b>，把报告复制出来就能定位问题。</li>
        <li>若是「推理吃光预算」：把 <b>输出预算</b> 调大（推理模型建议 ≥ 8192），或改用 <code>deepseek-chat</code>。</li>
        <li>确认代理/VPN 与网络可达 <code>${esc(S.settings.base_url || '')}</code>。</li>
        <li>确认 <b>start.cmd</b> 的窗口还开着（关掉窗口 AI 就用不了）。</li>
      </ul>
      <p class="dim">错误详情：<code>${esc(err.message)}</code></p>
      ${det ? `<details><summary class="dim" style="cursor:pointer">查看原始响应</summary><pre>${esc(det)}</pre></details>` : ''}`;
  } finally {
    S.onBudgetBump = null;
    aiBusy = false;
    $('#btnAISend').disabled = false;
  }
}

/* 轻量 Markdown 渲染（标题/列表/代码块/表格/加粗/行内代码） */
function renderAI(md) {
  const out = $('#aiOutput');
  const blocks = [];
  const MARK = '\u0001BLOCK';
  // 先抽出代码块，避免其中的内容被当成 Markdown 处理
  let text = String(md).replace(/```[ \t]*[\w+-]*[ \t]*\r?\n?([\s\S]*?)```/g, (m, code) => {
    blocks.push(code.replace(/\s+$/, ''));
    return `${MARK}${blocks.length - 1}\u0001`;
  });
  // 未闭合的代码块（模型输出被截断）也当作代码块处理
  if (/```/.test(text)) {
    const idx = text.indexOf('```');
    blocks.push(text.slice(idx + 3).replace(/^[ \t]*[\w+-]*[ \t]*\r?\n?/, '').replace(/\s+$/, ''));
    text = text.slice(0, idx) + `${MARK}${blocks.length - 1}\u0001`;
  }

  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');

  const lines = text.split('\n');
  const parts = [];           // 交替的 html 片段
  let html = '', inList = false, table = [];

  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r));
    const cells = rows.map((r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim()));
    html += '<table>' + cells.map((cs, i) =>
      '<tr>' + cs.map((c) => (i === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`)).join('') + '</tr>'
    ).join('') + '</table>';
    table = [];
  };
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  const cutBlock = (line) => {
    // 该行含代码块占位符：切分并原样插入 <pre>
    const segs = line.split(new RegExp(`${MARK}(\\d+)\u0001`));
    for (let i = 0; i < segs.length; i++) {
      if (i % 2 === 0) { html += inline(segs[i]); }
      else {
        closeList(); flushTable();
        if (html) { parts.push(html); html = ''; }
        parts.push(`<pre><code>${esc(blocks[+segs[i]] || '')}</code></pre>`);
      }
    }
  };

  lines.forEach((line) => {
    if (line.includes(MARK)) { cutBlock(line); return; }
    if (/^\s*\|.*\|\s*$/.test(line)) { closeList(); table.push(line); return; }
    flushTable();
    if (/^#{1,6}\s/.test(line)) {
      closeList();
      const lv = Math.min(4, line.match(/^#+/)[0].length + 1);
      html += `<h${lv}>${inline(line.replace(/^#+\s*/, ''))}</h${lv}>`;
    } else if (/^\s*[-*+]\s+/.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inline(line.replace(/^\s*[-*+]\s+/, ''))}</li>`;
    } else if (/^\s*\d+[.)]\s+/.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inline(line.replace(/^\s*\d+[.)]\s+/, ''))}</li>`;
    } else if (line.trim() === '') {
      closeList();
    } else {
      closeList();
      html += `<p>${inline(line)}</p>`;
    }
  });
  closeList(); flushTable();
  if (html) parts.push(html);

  out.innerHTML = parts.join('');
  out.querySelectorAll('pre').forEach((pre) => {
    const bar = document.createElement('div');
    const btn = document.createElement('button');
    btn.className = 'btn tiny ghost';
    btn.textContent = '📋 复制代码';
    btn.onclick = () => copy(pre.textContent, '代码已复制');
    bar.appendChild(btn);
    pre.parentNode.insertBefore(bar, pre);
  });
}

/* ---------------- AI 批量翻译（写入本地缓存） ---------------- */
async function translateEntries(list) {
  const st = $('#aiStatus');
  if (!S.serverMode) { toast('翻译需要本地服务，请用 start.cmd 启动'); return; }
  if (!S.settings.api_key) { openDrawer('set'); loadSettings(); toast('请先填写 API Key'); return; }
  const items = list.filter((e) => e.en && e.q !== 2).map((e) => ({ n: e.n, en: e.en }));
  if (!items.length) { toast('这些条目已经有精校释义了'); return; }
  openDrawer('ai');
  st.className = 'ai-status';
  st.textContent = `正在翻译 ${items.length} 条…`;
  let saved = 0;
  try {
    for (let i = 0; i < items.length; i += 20) {
      const chunk = items.slice(i, i + 20);
      const r = await fetch('api/ai/translate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ items: chunk }, S.settings)),
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error + (d.detail ? '：' + String(d.detail).slice(0, 160) : ''));
      saved += d.saved;
      st.textContent = `已翻译 ${saved}/${items.length}…`;
    }
    // 重新拉取数据以应用缓存
    const fresh = await (await fetch('api/data', { cache: 'no-store' })).json();
    S.db = fresh; indexEntries();
    S.aiCache = await (await fetch('api/zh_cache')).json();
    save('aiZh', S.aiCache);
    applyFilter();
    if (S.current) {
      const again = S.entries.find((e) => e.n === S.current.n);
      if (again) showDetail(again);
    }
    st.className = 'ai-status ok';
    st.textContent = `翻译完成，共缓存 ${saved} 条（已写入 data/zh_cache.json）`;
  } catch (err) {
    st.className = 'ai-status err';
    st.textContent = '翻译失败：' + err.message;
  }
}

/* 给列表批量翻译按钮：翻译当前筛选里前 40 条英文释义 */
function translateCurrentView() {
  const targets = S.view.filter((e) => e.q !== 2 && e.en).slice(0, 40);
  if (!targets.length) { toast('当前结果里的条目都已是精校释义'); return; }
  translateEntries(targets);
}


/* ---------------- 启动 ---------------- */
function indexEntries() {
  S.entries = (S.db.entries || []);
  S.entries.forEach((e) => { e._idx = null; });
  searchIndex(S.entries[0] || {});
}

async function boot() {
  applyTheme(false);
  applyAccent();
  try {
    await loadDB();
  } catch (err) {
    document.body.innerHTML =
      `<div style="padding:60px;text-align:center;font-size:15px;line-height:2">
        <h2>❌ 加载失败</h2><p>${esc(err.message)}</p>
        <p class="dim">请双击项目里的 start.cmd 启动本地服务后再访问。</p></div>`;
    return;
  }
  indexEntries();
  $('#favCount').textContent = S.fav.size;
  $('#cfgCount').textContent = S.cfg.length;
  $('#helpCount').textContent = `${S.entries.length} 条，全部来自本机 CS2 的 cvarlist 实测`;
  buildSidebar();
  renderCfg();
  loadSettings();

  // 就绪标记：不依赖界面上任何文字，供自检与外部脚本判断加载完成
  document.body.classList.add('app-ready');

  renderSideFolders();
  S.special = '';
  selectCategory('', '');
  // 默认选中第一条核心指令
  const first = S.entries.find((e) => e.k);
  if (first) showDetail(first);
  const pool = $('#list');
  pool.addEventListener('scroll', () => {}, { passive: true });

  // 主题分段控件 & 启动行为回填
  const seg = $('#segTheme');
  if (seg) seg.querySelectorAll('button').forEach((b) => {
    b.classList.toggle('on', b.dataset.theme === getTheme());
  });
  const start = getStartMode();
  $$('input[name="startMode"]').forEach((r) => { r.checked = r.value === start; });
  applyTheme(false);

  // 首次启动 / 设置要求回主页 → 显示主页；否则直接进上次的模式
  bootView();
  syncModeUI();
  _setFavBadge();

  renderGuard();
}

/* ---------------- 上锁状态（游戏目录完整性） ---------------- */
function renderGuard() {
  const btn = $('#btnGuard');
  if (!btn) return;
  const g = (S.meta && S.meta.guard) || null;
  if (!S.serverMode) {
    btn.classList.add('off');
    btn.title = '离线模式：上锁检查需要本地服务（python tools/guard_check.py）';
    btn.querySelector('span').textContent = '上锁检查';
    return;
  }
  if (!g || g.state === 'none') {
    btn.classList.add('warn');
    btn.querySelector('span').textContent = '未记录基线';
    btn.title = '还没有干净基线。确认游戏文件干净后运行：python tools\\guard_check.py --baseline';
    return;
  }
  if (g.state === 'warn') {
    btn.classList.add('warn');
    btn.querySelector('span').textContent = g.text || '有改动';
    btn.title = '游戏目录与干净基线不一致，进受保护服务器前请先跑：'
      + 'python tools\\guard_check.py（或验证游戏文件完整性）。详见 docs/safety-guard.md';
    return;
  }
  btn.classList.add('ok');
  btn.querySelector('span').textContent = '已上锁';
  btn.title = '游戏目录与干净基线一致，可以正常进服';
}

$('#btnGuard').onclick = async () => {
  const g = (S.meta && S.meta.guard) || null;
  const lines = [];
  lines.push('🛡 游戏目录上锁状态');
  lines.push('');
  if (!S.serverMode) {
    lines.push('当前是离线模式（直接打开 index.html）。');
    lines.push('上锁检查需要本地服务，请在项目里执行：');
    lines.push('    python tools\\guard_check.py');
  } else if (!g || g.state === 'none') {
    lines.push('还没有干净基线。');
    lines.push('1) 用 Steam 验证一次游戏文件完整性，确认干净；');
    lines.push('2) 执行： python tools\\guard_check.py --baseline');
  } else if (g.state === 'warn') {
    lines.push(`⚠ ${g.text}`);
    lines.push('');
    lines.push('说明：游戏目录里出现了与干净基线不一致的敏感文件');
    lines.push('（vpk / dll / exe），可能是你做的实验，也可能是 Steam 更新。');
    lines.push('');
    lines.push('要做的事：');
    lines.push('1) python tools\\guard_check.py   ← 看具体是哪些文件');
    lines.push('2) 若是实验残留 → 删掉；若是 Steam 更新 → 重记基线');
    lines.push('3) 未确认干净前，启动选项保留 -insecure，不要进官方服务器');
  } else {
    lines.push('✅ 与干净基线一致，可以正常进服。');
    lines.push('进官方服务器时，启动选项里不要带 -insecure。');
  }
  lines.push('');
  lines.push('完整策略见 docs/safety-guard.md');
  alert(lines.join('\n'));
};

/* 顶栏的上锁小按钮同步一份状态文字 */
const _renderGuard0 = renderGuard;
renderGuard = function () {
  _renderGuard0.apply(this, arguments);
  const t = $('#guardText');
  const btn = $('#btnGuard');
  if (t && btn) {
    t.textContent = btn.querySelector('span').textContent;
    const top = $('#btnGuardTop');
    if (top) {
      top.classList.remove('ok', 'warn');
      if (btn.classList.contains('ok')) top.classList.add('ok');
      if (btn.classList.contains('warn')) top.classList.add('warn');
      top.title = btn.title;
    }
    const line = $('#guardLine');
    if (line) line.textContent = btn.title;
  }
};

/* 收藏数同步到顶栏徽标 */
const _setFavBadge = () => {
  const n = (S.fav && S.fav.size) || 0;
  const b = $('#favBadge');
  if (b) { b.textContent = n; b.classList.toggle('hidden', n === 0); }
};
const _renderList0 = renderList;
renderList = function () {
  const r = _renderList0.apply(this, arguments);
  _setFavBadge();
  syncModeUI();
  return r;
};

boot();
