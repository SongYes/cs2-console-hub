'use strict';
/**
 * Electron 主进程
 *
 * - 单实例：第二次启动直接聚焦已有窗口，不新开
 * - 启动内置本地服务（随机空闲端口），窗口加载它，这样前端 api/* 相对路径可用
 * - 外链一律交给系统浏览器，不在应用内打开
 * - 前端「下载 .cfg」等下载动作走系统保存对话框
 */

const { app, BrowserWindow, shell, dialog, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const { createServer } = require('./server');

const APP_NAME = 'CS2 控制台指令查询中心';

/* 自动化测试用：顶层设置远程调试端口（必须早于 ready，否则不生效）。
   注意：若环境里带了 ELECTRON_RUN_AS_NODE=1，Electron 会退化成纯 Node，
   此处 app 为 undefined，直接跳过即可（正常运行时不会发生）。 */
if (app && app.commandLine && process.env.CS2HUB_DEBUG_PORT) {
  app.commandLine.appendSwitch('remote-debugging-port', String(process.env.CS2HUB_DEBUG_PORT));
  app.commandLine.appendSwitch('remote-allow-origins', '*');
}

/* 程序目录：开发时是仓库根；打包后是 app.asar 所在资源目录 */
const ROOT = app.isPackaged
  ? path.join(process.resourcesPath, 'app.asar')
  : path.join(__dirname, '..');

let mainWindow = null;
let localServer = null;
let baseUrl = null;

/* 只允许开一个实例 */
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

/* 关掉菜单栏里用不到的项，但保留复制/粘贴等编辑快捷键 */
function buildMenu() {
  const isDev = !app.isPackaged;
  const template = [
    {
      label: '文件',
      submenu: [
        {
          label: '在浏览器中打开',
          click: () => { if (baseUrl) shell.openExternal(baseUrl); },
        },
        { type: 'separator' },
        { role: 'quit', label: '退出' },
      ],
    },
    {
      label: '编辑',
      submenu: [
        { role: 'undo', label: '撤销' },
        { role: 'redo', label: '重做' },
        { type: 'separator' },
        { role: 'cut', label: '剪切' },
        { role: 'copy', label: '复制' },
        { role: 'paste', label: '粘贴' },
        { role: 'selectAll', label: '全选' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '重新加载' },
        { role: 'forceReload', label: '强制重新加载' },
        { type: 'separator' },
        { role: 'resetZoom', label: '实际大小' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '全屏' },
        ...(isDev ? [{ type: 'separator' }, { role: 'toggleDevTools', label: '开发者工具' }] : []),
      ],
    },
    {
      label: '帮助',
      submenu: [
        {
          label: '关于 ' + APP_NAME,
          click: () => {
            const pkg = require('../package.json');
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: '关于',
              message: APP_NAME,
              detail: [
                '版本号：v' + pkg.version,
                '开源免费 · 任何收费倒卖行为均为诈骗',
                '',
                '作者邮箱：songyuanuwu@gmail.com',
                'GitHub：https://github.com/SongYes',
                'B 站主页：https://space.bilibili.com/1214830446',
                '',
                '本软件与 Valve 无关，不修改游戏文件本体，不承担任何 VAC 责任。',
              ].join('\n'),
              buttons: ['确定'],
              noLink: true,
            });
          },
        },
        {
          label: '打开使用说明',
          click: () => { mainWindow && mainWindow.webContents.executeJavaScript(
            "openDrawer('help')").catch(() => {}); },
        },
        {
          label: '打开免责声明',
          click: () => { mainWindow && mainWindow.webContents.executeJavaScript(
            "openDrawer('disc')").catch(() => {}); },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1680,
    height: 1000,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    backgroundColor: '#eef2f8',
    title: APP_NAME,
    autoHideMenuBar: false,
    icon: path.join(__dirname, 'build', 'icon.ico'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());

  /* 外链 → 系统浏览器 */
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });

  /* 站内导航之外的跳转也交给系统浏览器 */
  mainWindow.webContents.on('will-navigate', (ev, url) => {
    if (baseUrl && url.startsWith(baseUrl)) return;
    ev.preventDefault();
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
  });

  /* 下载（下载 .cfg / 导出收藏夹）→ 系统保存对话框 */
  mainWindow.webContents.session.on('will-download', (ev, item) => {
    const suggested = item.getFilename();
    const target = dialog.showSaveDialogSync(mainWindow, {
      title: '保存文件',
      defaultPath: path.join(app.getPath('downloads'), suggested),
    });
    if (!target) { item.cancel(); return; }
    item.setSavePath(target);
    item.once('done', (e, state) => {
      if (state === 'completed') {
        dialog.showMessageBox(mainWindow, {
          type: 'info', title: '保存成功',
          message: '已保存到：\n' + target, buttons: ['确定'], noLink: true,
        });
      }
    });
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  mainWindow.loadURL(baseUrl);
}

/* 日志落到 userData，方便排查（不记录 API Key） */
function log(...args) {
  try {
    const line = new Date().toISOString() + ' ' + args.join(' ') + '\n';
    fs.appendFileSync(path.join(app.getPath('userData'), 'app.log'), line, 'utf8');
  } catch (e) {}
}

app.whenReady().then(async () => {
  app.setAppUserModelId('com.songyes.cs2consolehub');

  /* 纯离线模式：不启本地服务，直接以 file:// 加载页面。
     用途：
       - 验证「前端离线可用」（api/* 必然不可达，只能走 assets/db.js 内嵌库）
       - 排查「本地服务疑似有问题」时，用最小依赖方式启动
     开启方式：设环境变量 CS2HUB_NO_SERVER=1 */
  const noServer = process.env.CS2HUB_NO_SERVER === '1';

  if (noServer) {
    baseUrl = 'file:///' + path.join(ROOT, 'index.html').replace(/\\/g, '/');
    log('offline mode (no local server), loading', baseUrl);
    buildMenu();
    createWindow();
    return;
  }

  try {
    localServer = createServer({
      root: ROOT,
      dataDir: app.getPath('userData'),
    });
    const port = await localServer.listen(0);   // 自动选空闲端口，避免 8788 被占
    baseUrl = 'http://127.0.0.1:' + port + '/';
    log('server started at', baseUrl, 'root=' + ROOT);
  } catch (err) {
    log('server failed:', String(err && err.message || err));
    dialog.showErrorBox('启动失败', '本地服务无法启动：\n' + String(err && err.message || err));
    app.quit();
    return;
  }

  buildMenu();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (localServer) { try { localServer.close(); } catch (e) {} }
  app.quit();
});
