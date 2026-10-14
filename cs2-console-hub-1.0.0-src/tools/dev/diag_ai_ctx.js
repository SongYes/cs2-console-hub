// 诊断：AI 检索到底把哪些指令喂给了模型（复刻 app.js 的 relevantContext）。
// 用法: node tools/dev/diag_ai_ctx.js "怎么设置可以随地安放炸弹"
const fs = require('fs');
const path = require('path');

const db = JSON.parse(fs.readFileSync(
  path.join(__dirname, '..', '..', 'data', 'commands.json'), 'utf8'));
const E = db.entries;

const searchIndex = (e) => ((e.n + ' ' + (e.z || '') + ' ' + (e.en || '')).toLowerCase());

// === 现状实现（app.js relevantContext）===
function cnBigrams(text) {
  const chars = (text || '').replace(/[^\u4e00-\u9fff]/g, '');
  const out = [];
  for (let i = 0; i + 1 < chars.length; i++) out.push(chars.slice(i, i + 2));
  return out;
}
const SYN_RE = [
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
  ['音量 声音大小', 'volume'],
  ['机器人 电脑人', 'bot bots'],
];
function synBoost(hay, query) {
  const q = (query || '').toLowerCase();
  let b = 0;
  for (const [cn, en] of SYN_RE) {
    if (!cn.split(/\s+/).some((w) => w && q.includes(w))) continue;
    if (en.split(/\s+/).some((w) => w && hay.includes(w))) b += 22;
  }
  return b;
}

function currentCtx(query, limit = 46) {
  const q = (query || '').toLowerCase();
  const asciiTerms = q.split(/[^a-z0-9_+]+/).filter((t) => t.length >= 2);
  const bigrams = cnBigrams(query);
  const scored = E.map((e) => {
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
    s += synBoost(hay, query);
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
  }).filter((x) => x.s > 12).sort((a, b) => b.s - a.s).slice(0, limit);
  return scored;
}

const q = process.argv[2] || '怎么设置可以随地安放炸弹';
console.log('查询:', q);
const terms = q.toLowerCase().split(/[\s,，。、；;：:]+/).filter((t) => t.length >= 1);
console.log('被拆成的检索词:', JSON.stringify(terms));

const top = currentCtx(q);
console.log('\n当前实现返回', top.length, '条，前 15 名：');
top.slice(0, 15).forEach((x, i) =>
  console.log(`  ${String(i + 1).padStart(2)}. ${x.s.toFixed(1).padStart(6)}  ${x.e.n}`));

const target = process.argv[3] || 'mp_plant_c4_anywhere';
const pos = top.findIndex((x) => x.e.n === target);
// 全库排名：直接复用同一套打分（不另写一份，避免"诊断和实现对不上"）
const allCtx = currentCtx(q, E.length);
const rank = allCtx.findIndex((x) => x.e.n === target);
const score = pos >= 0 ? top[pos].s : (rank >= 0 ? allCtx[rank].s : 0);
console.log(`\n目标 ${target}:`);
console.log(`  得分 ${score.toFixed(1)}，全库排名第 ${rank === -1 ? '（未过阈值）' : rank + 1}`);
console.log(`  在喂给模型的 ${top.length} 条上下文里：${pos === -1 ? '❌ 未进入（模型看不到它）' : `✅ 第 ${pos + 1} 位`}`);
console.log(`\n喂给模型的前 12 条：`);
top.slice(0, 12).forEach((x, i) =>
  console.log(`  ${String(i + 1).padStart(2)}. ${x.s.toFixed(1).padStart(6)}  ${x.e.n}`));
