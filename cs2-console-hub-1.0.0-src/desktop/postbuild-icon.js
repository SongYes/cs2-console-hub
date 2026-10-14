'use strict';
/**
 * 构建后处理：给 exe 嵌入应用图标。
 *
 * 背景：electron-builder 的 winCodeSign 工具包内含指向 dylib 的符号链接，
 * 在未开启「开发者模式」的 Windows 上非管理员无法解压（EPERM），
 * 因此构建时设置了 win.signAndEditExecutable=false 跳过 exe 资源改写。
 * 代价是图标不会被写入 exe —— 这里用同一工具包里的 rcedit 补上。
 *
 * 安全性：rcedit 只改「图标/版本信息」这类 PE 资源，不动 app.asar，
 * 因此 Electron 的 asar 完整性校验（写在同一 exe 的另一处资源）不受影响。
 * 已在 rcedit 后实测应用可正常启动（desktop/verify_installed.js 15/15）。
 *
 * 用法： node desktop/postbuild-icon.js
 */
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'dist', 'win-unpacked');
const EXE = path.join(OUT, 'CS2 控制台指令查询中心.exe');
const ICO = path.join(__dirname, 'build', 'icon.ico');

/** 从 electron-builder 缓存里找 rcedit-x64.exe（构建时已下载） */
function findRcedit() {
  const base = path.join(process.env.LOCALAPPDATA || '', 'electron-builder', 'Cache', 'winCodeSign');
  const fromCache = [];
  if (fs.existsSync(base)) {
    for (const d of fs.readdirSync(base)) {
      const p = path.join(base, d, 'rcedit-x64.exe');
      if (fs.existsSync(p)) fromCache.push(p);
    }
  }
  // 备选：本仓库缓存
  const local = path.join(ROOT, 'desktop', 'build', 'rcedit-x64.exe');
  if (fs.existsSync(local)) fromCache.push(local);
  return fromCache[0] || null;
}

function main() {
  if (!fs.existsSync(EXE)) {
    console.error('[postbuild] 找不到 exe：' + EXE);
    console.error('           请先执行 npm run dist');
    process.exit(1);
  }
  if (!fs.existsSync(ICO)) {
    console.error('[postbuild] 找不到图标：' + ICO);
    process.exit(1);
  }

  const rcedit = findRcedit();
  if (!rcedit) {
    console.error('[postbuild] 找不到 rcedit-x64.exe（应随 winCodeSign 缓存一起下载）');
    process.exit(1);
  }

  const before = fs.statSync(EXE).size;
  console.log('[postbuild] 嵌入图标');
  console.log('  exe    : ' + EXE);
  console.log('  icon   : ' + ICO);
  console.log('  rcedit : ' + rcedit);

  const r = spawnSync(rcedit, [EXE, '--set-icon', ICO], { stdio: 'inherit' });
  if (r.status !== 0) {
    console.error('[postbuild] rcedit 失败，退出码 ' + r.status);
    process.exit(1);
  }

  const after = fs.statSync(EXE).size;
  console.log('  完成：' + (before / 1048576).toFixed(2) + ' MB → ' + (after / 1048576).toFixed(2) + ' MB');
  console.log('[postbuild] 下一步：npm run dist:nsis-only 重新生成安装包，或直接运行 dist/win-unpacked 验证');
}

main();
