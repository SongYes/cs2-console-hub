// AI 检索评测：给一批"玩家的中文说法"，看正确指令是否被检索进上下文前 10。
// 用法: node tools/dev/eval_ai_ctx.js
const fs = require('fs');
const path = require('path');

const db = JSON.parse(fs.readFileSync(
  path.join(__dirname, '..', '..', 'data', 'commands.json'), 'utf8'));
const E = db.entries;

const searchIndex = (e) => (e.n + ' ' + (e.z || '') + ' ' + (e.en || '') + ' ' + (e.u || '')).toLowerCase();

function cnBigrams(text) {
  const chars = (text || '').replace(/[^\u4e00-\u9fff]/g, '');
  const out = [];
  for (let i = 0; i + 1 < chars.length; i++) out.push(chars.slice(i, i + 2));
  return out;
}

// 与 assets/app.js 保持同步的同义词表（这里是评测副本）
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

function synonymBoost(hay, query) {
  const q = (query || '').toLowerCase();
  let boost = 0;
  for (const [cnWords, enWords] of SYNONYMS) {
    if (!cnWords.split(/\s+/).some((w) => w && q.includes(w))) continue;
    if (enWords.split(/\s+/).some((w) => w && hay.includes(w))) boost += 22;
  }
  return boost;
}

function rank(query, limit = 46) {
  const q = (query || '').toLowerCase();
  const asciiTerms = q.split(/[^a-z0-9_+]+/).filter((t) => t.length >= 2);
  const bigrams = cnBigrams(query);
  return E.map((e) => {
    const hay = searchIndex(e);
    const name = e.n.toLowerCase();
    let s = 0;
    asciiTerms.forEach((t) => { if (hay.includes(t)) s += 14; });
    if (bigrams.length) {
      let hit = 0;
      for (const bg of bigrams) if (hay.includes(bg)) hit++;
      s += (hit / bigrams.length) * 60;
      let nHit = 0;
      for (const bg of bigrams) if (name.includes(bg)) nHit++;
      if (nHit) s += nHit * 8;
    }
    s += synonymBoost(hay, query);
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
    return { n: e.n, s };
  }).filter((x) => x.s > 12).sort((a, b) => b.s - a.s).slice(0, limit);
}

// 评测集：玩家会怎么说 → 期望被检索到的指令（命中任一即算通过）
const CASES = [
  ['怎么设置可以随地安放炸弹', ['mp_plant_c4_anywhere', 'mp_plant_c4_anywhere']],
  ['我想无限子弹', ['sv_infinite_ammo', 'ammo_grenade_limit_total']],
  ['怎么开穿墙飞', ['noclip']],
  ['怎么变无敌', ['god', 'buddha']],
  ['准星改成绿色小十字', ['cl_crosshaircolor', 'cl_crosshairstyle', 'cl_crosshaircolor_g']],
  ['雷达缩放到全图', ['cl_radar_scale', 'cl_radar_scale_alternate', 'cl_radar_scale_dynamic']],
  ['鼠标灵敏度太高了', ['sensitivity', 'zoom_sensitivity_ratio']],
  ['关掉手臂模型', ['r_drawviewmodel', 'viewmodel_fov', 'cl_draw_only_deathnotices']],
  ['每回合多久', ['mp_roundtime', 'mp_roundtime_defuse', 'mp_roundtime_hostage']],
  ['热身时间太长', ['mp_warmuptime', 'mp_warmup_start', 'mp_warmup_end']],
  ['冻结时间缩短', ['mp_freezetime']],
  ['死后重生', ['mp_respawn_on_death_ct', 'mp_respawn_on_death_t', 'mp_respawn_immunitytime']],
  ['闪光弹多久消失', ['inferno_flame_lifetime', 'ammo_grenade_limit_flashbang']],
  ['拆弹器怎么给', ['mp_defuser_allocation', 'mp_death_drop_defuser']],
  ['加钱 起始金钱', ['mp_startmoney', 'mp_maxmoney', 'cash_team_loser_bonus']],
  ['帧数显示在屏幕上', ['cl_showfps', 'fps_max']],
  ['网络延迟显示', ['cl_hud_telemetry_ping_show', 'ping', 'net_graph', 'cl_showfps']],
  ['音量调小', ['volume', 'snd_gamevolume', 'snd_musicvolume']],
  ['语音听不到队友', ['voice_modenable', 'sv_voiceenable', 'snd_voipvolume']],
  ['文字聊天屏蔽敌人', ['cl_mute_enemy_team', 'cl_chat', 'sv_allchat']],
  ['跳过皮肤 关闭皮肤', ['weapon_skins', 'cl_weapon_selection_rarity_color']],
  ['机器人难度', ['bot_difficulty', 'custom_bot_difficulty', 'sv_auto_adjust_bot_difficulty']],
  ['摇杆手柄灵敏度', ['joy_yaw_sensitivity', 'joy_pitch_sensitivity', 'joy_side_sensitivity']],
  ['阴影关掉提升帧数', ['r_shadows', 'sc_disable_shadow_fastpath']],
  ['降低画质提升fps', ['r_texture_lod_scale', 'r_farz', 'fps_max']],
];

let pass = 0;
const fails = [];
for (const [q, expect] of CASES) {
  const top = rank(q);
  const names = top.map((x) => x.n);
  const hit = expect.find((n) => names.includes(n));
  const pos = hit ? names.indexOf(hit) + 1 : -1;
  if (hit) { pass++; console.log(`  [OK]   ${q}  →  ${hit}（第 ${pos} 位）`); }
  else {
    fails.push([q, expect, names.slice(0, 6)]);
    console.log(`  [MISS] ${q}  →  期望 ${expect.join('/')}，实际前 6：${names.slice(0, 6).join(', ')}`);
  }
}
console.log(`\n检索评测：${pass}/${CASES.length} 通过`);
if (fails.length) {
  console.log('\n未通过明细：');
  fails.forEach(([q, ex, got]) => console.log(`  ${q}\n    期望 ${ex.join('/')}\n    实际 ${got.join(', ')}`));
  process.exit(1);
}
