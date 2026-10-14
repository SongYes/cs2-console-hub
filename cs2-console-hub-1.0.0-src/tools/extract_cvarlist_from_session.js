// 从 DSH 会话原始记录（session.v4.jsonl.zstd）里抽出用户粘贴的完整 cvarlist 输出。
// 用法： node tools/extract_cvarlist_from_session.js <session.v4.jsonl.zstd> [输出路径]
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const src = process.argv[2];
const dst = process.argv[3] || path.join(__dirname, '..', '_dumps', 'cs2_cvarlist_full.txt');
if (!src) {
  console.error('用法: node extract_cvarlist_from_session.js <session.v4.jsonl.zstd> [out.txt]');
  process.exit(1);
}

const raw = zlib.zstdDecompressSync(fs.readFileSync(src));
const text = raw.toString('utf8');
console.log(`[i] 解压 ${(raw.length / 1048576).toFixed(1)} MB，${text.split('\n').length} 行`);

// cvarlist 记录：名称(左对齐补空格) : 值或 cmd : 权限 : 说明
const REC = /^\s{1,4}([A-Za-z_+][A-Za-z0-9_+]{1,60})\s+:\s+([^:]{0,80}?)\s+:\s+([a-z_,\s]{0,80}?)\s+:\s?(.{0,500})$/;

let best = null;   // 最长的一段连续记录
let cur = new Map();  // 当前段：name -> 行
let started = false;

function flush() {
  if (cur.size && (!best || cur.size > best.size)) best = cur;
  cur = new Map();
}

const lines = text.split('\n');
for (let i = 0; i < lines.length; i++) {
  let line = lines[i];
  // jsonl 转义：把 \n \t \" \\ 还原，便于按行匹配
  line = line.replace(/\\n/g, '\n').replace(/\\t/g, '\t').replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  for (const sub of line.split('\n')) {
    const m = REC.exec(sub.replace(/\r$/, ''));
    if (m) {
      const name = m[1];
      const flags = m[3].trim();
      const val = m[2].trim();
      if (!flags && val.toLowerCase() !== 'cmd') { continue; }
      if (!cur.has(name)) cur.set(name, sub.trimEnd());
      started = true;
      continue;
    }
    // 非记录行：如果已经积累成段，就结算
    if (started && cur.size > 50) flush();
    else if (started && cur.size <= 50) cur = new Map();
    started = cur.size > 0;
    if (/total convars|convars\/concommands/.test(sub)) {
      console.log(`[i] 找到总表结尾: ${sub.trim().slice(0, 80)}`);
    }
  }
}
if (cur.size > 50) flush();

if (!best) {
  console.error('[!] 会话记录里没找到 cvarlist 段落');
  process.exit(1);
}
const names = [...best.keys()].sort();
fs.mkdirSync(path.dirname(dst), { recursive: true });
fs.writeFileSync(dst, names.map((n) => best.get(n)).join('\n') + '\n', 'utf8');
console.log(`[OK] 抽出 ${names.length} 条 -> ${dst}`);
