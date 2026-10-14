'use strict';
/**
 * electron-builder afterPack 钩子：给主程序 exe 嵌入图标。
 *
 * 为什么需要：winCodeSign 工具包含指向 dylib 的符号链接，
 * 在未开启「开发者模式」的 Windows 上非管理员无法解压（EPERM），
 * 故构建配置里设了 win.signAndEditExecutable=false 跳过 exe 资源改写，
 * 图标因此不会被写入 —— 这里在「打包完成、尚未生成安装包」的时机补上，
 * 这样 NSIS 打包进安装包的就是已带图标的 exe。
 *
 * rcedit 只改图标/版本信息类 PE 资源，不动 app.asar，
 * 不影响 Electron 的 asar 完整性校验（已实测启动正常）。
 */
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

function findRcedit() {
  const cands = [];
  const base = path.join(process.env.LOCALAPPDATA || '', 'electron-builder', 'Cache', 'winCodeSign');
  if (fs.existsSync(base)) {
    for (const d of fs.readdirSync(base)) {
      const p = path.join(base, d, 'rcedit-x64.exe');
      if (fs.existsSync(p)) cands.push(p);
    }
  }
  const local = path.join(__dirname, 'build', 'rcedit-x64.exe');
  if (fs.existsSync(local)) cands.push(local);
  return cands[0] || null;
}

module.exports = async function afterPack(context) {
  // 只处理 Windows
  if (context.electronPlatformName !== 'win32') return;

  const appOutDir = context.appOutDir;
  const productFilename = context.packager.appInfo.productFilename;
  const exe = path.join(appOutDir, productFilename + '.exe');
  const ico = path.join(__dirname, 'build', 'icon.ico');

  if (!fs.existsSync(exe)) {
    console.warn('[icon] 找不到 exe，跳过：' + exe);
    return;
  }
  if (!fs.existsSync(ico)) {
    console.warn('[icon] 找不到图标，跳过：' + ico);
    return;
  }

  const rcedit = findRcedit();
  if (!rcedit) {
    console.warn('[icon] 找不到 rcedit-x64.exe，跳过图标嵌入');
    return;
  }

  const before = fs.statSync(exe).size;
  const r = spawnSync(rcedit, [exe, '--set-icon', ico], { stdio: 'pipe' });
  if (r.status !== 0) {
    console.warn('[icon] rcedit 失败（退出码 ' + r.status + '）：' +
      String(r.stderr || '').slice(0, 300));
    return;
  }
  const after = fs.statSync(exe).size;
  console.log('  • 已嵌入应用图标  ' +
    (before / 1048576).toFixed(2) + ' MB → ' + (after / 1048576).toFixed(2) + ' MB');
};
