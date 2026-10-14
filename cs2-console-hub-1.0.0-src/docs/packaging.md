# 打包与分发

把「CS2 控制台指令查询中心」打包成 Windows 桌面应用（Electron + NSIS 安装包）。

## 产物

| 文件 | 说明 |
|---|---|
| `dist/CS2控制台指令查询中心-<版本>-安装包.exe` | 安装程序（中文界面，可选安装目录） |
| `dist/win-unpacked/` | 免安装的完整程序目录，解压即用 |

安装后会创建**桌面快捷方式**与**开始菜单项**，并注册卸载项（可从「设置 → 应用」卸载）。

## 构建

```powershell
npm install          # 首次
npm run dist         # 产出安装包
```

构建过程：

1. `electron-builder` 打包 → `dist/win-unpacked`
2. `desktop/afterpack-icon.js` 钩子给 exe 嵌入图标
3. NSIS 生成安装包

## 架构

```
desktop/
  main.js               Electron 主进程：窗口、单实例、外链、下载、菜单
  server.js             本地服务（Node 实现，替代 tools/server.py）
  afterpack-icon.js     构建钩子：嵌入 exe 图标
  test_server.js        本地服务冒烟测试（不起 Electron）
  verify_installed.js   已安装应用的启动自检
  run_e2e_in_app.js     在开发模式的 Electron 里跑完整 e2e
  run_e2e_packaged.js   在打包后的应用里跑完整 e2e
  shot_app.js           给打包后的应用截图
```

### 为什么要用 Node 重写服务

原来的 `tools/server.py` 提供四类能力，桌面端需要其中三类：

| 接口 | 用途 | 桌面端 |
|---|---|---|
| `/api/health` | 前端判断「服务模式 / 离线模式」 | ✅ 已移植 |
| `/api/data` | 指令库 + meta（含上锁状态） | ✅ 已移植 |
| `/api/ai` | 代理 `chat/completions` | ✅ 已移植 |
| `/api/ai/models` | 列出上游可用模型 | ✅ 已移植 |
| `/api/ai/translate` | 批量翻译并写缓存 | ✅ 已移植 |
| `/api/zh_cache` | 翻译缓存 | ✅ 已移植 |
| `/api/update/*` | 检查/执行上游更新 | ❌ 不做（更新功能已按需求移除） |

用 Node 而不是捆绑 Python：体积少约 15MB，不依赖外部运行时，也不会因捆绑解释器被杀软误报。

### 目录可写性

安装目录是**只读**的（资源在 `app.asar` 内），因此：

- 指令库、上锁基线：从安装目录**只读**加载
- AI 翻译缓存：写入 `%APPDATA%\CS2 控制台指令查询中心\zh_cache.json`
- 读取时把「程序目录自带的缓存」与「用户目录新增的缓存」**取并集**（用户目录优先），老数据不丢

### 端口

本地服务监听 **随机空闲端口**（而非固定 8788），避免与开发服务器或其它程序冲突，
窗口加载 `http://127.0.0.1:<随机端口>/`，前端的 `api/*` 相对路径因此可直接工作。

## 离线模式

设环境变量 `CS2HUB_NO_SERVER=1` 启动，则**不启本地服务**，直接以 `file://` 加载页面。
此时 `api/*` 必然不可达，只能走 `assets/db.js` 内嵌库 —— 即「双击 index.html 离线使用」的场景。

用途：验证离线可用性；或在怀疑本地服务有问题时用最小依赖方式启动排查。

```powershell
$env:CS2HUB_NO_SERVER=1
& ".\dist\win-unpacked\CS2 控制台指令查询中心.exe"
```

**内嵌库必须与主库同步。** `assets/db.js` 由 `tools/build_db.py` 生成；
若之后直接改过 `data/commands.json`（例如删条目、删空分类）而没重跑 build_db.py，
内嵌库就会停留在旧状态、离线模式放出已删除的条目。同步脚本：

```powershell
python design\dev\sync_embedded_db.py
```

它会用 `commands.json` 重建 `db.js` 并同步 `count / game_verified / wiki_only / new_count / cmd_count`，
写完自检两者完全一致。

## 方案导出 cfg（写游戏目录的唯一入口）

POST /api/game/cfg 是桌面版**唯一会往游戏目录写文件**的接口，安全约束：

- 目标目录由 data/integrity_baseline.json 的 game_dir 推出，再定位到 game/csgo/cfg；
  找不到则直接报错，**不会乱猜路径**。
- 文件名先剥掉一切路径成分与非法字符，再 path.resolve 二次校验必须落在 cfg 目录内。
- 已存在且是符号链接的目标**拒绝覆写**（防跟随链接写到别处）。
- 内容上限 2 MB；空内容拒绝；写入带 BOM，与配置生成器下载的内容一致。

GET /api/game/cfgdir 只做探测，供设置界面显示目录位置。

导出方式由设置里的「cfg 导出方式」决定，存在 cs2hub.cfgMode：

| 取值 | 行为 |
|---|---|
| manual（默认） | 走系统保存对话框，用户自己放进游戏目录 |
| uto | 直接写入游戏 cfg 目录，写失败会提示并询问是否改用手动 |

默认 manual：游戏目录通常需要管理员权限，不擅自写入。

## 已知构建问题

### winCodeSign 解压失败（符号链接权限）

现象：

```
ERROR: Cannot create symbolic link : 客户端没有所需的特权 :
  ...\winCodeSign\<hash>\darwin\10.12\lib\libcrypto.dylib
```

原因：`winCodeSign` 工具包内含指向 `libcrypto.1.0.0.dylib` 的**符号链接**，
在未开启「开发者模式」的 Windows 上，非管理员无法创建符号链接。

处理：构建配置里设置了 `win.signAndEditExecutable: false` 跳过 exe 资源改写，
图标改由 `afterPack` 钩子用工具包内的 `rcedit` 补上。
`rcedit` 只改图标/版本信息类 PE 资源，不动 `app.asar`，
不影响 Electron 的 asar 完整性校验（已实测启动正常）。

**若要让 electron-builder 自己改写 exe**（例如以后要加版本号资源）：
开启「设置 → 系统 → 开发者选项 → 开发人员模式」后，
删掉 `package.json` 里的 `"signAndEditExecutable": false` 与 `afterPack` 即可。

## 验证

```powershell
npm run test:server    # 本地服务 32 项（含路径穿越、AI 参数校验）
npm run test:app       # 打包后的应用里跑完整 e2e
npm run verify:app     # win-unpacked 启动自检 15 项
node desktop/acceptance.js dist/win-unpacked      # 目标验收 46 项
node desktop/verify_offline.js dist/win-unpacked  # 离线验证 16 项
```

| 脚本 | 覆盖 |
|---|---|
| `test_server.js` | 接口、静态资源、路径穿越、AI 参数校验、缓存并集 |
| `run_e2e_packaged.js` | 打包后应用内的完整 e2e（= Web 端全套用例） |
| `verify_installed.js` | 已安装 / 解包应用的启动自检 |
| `acceptance.js` | **目标验收**：指令查询 / 收藏夹 / 参数方案 / AI 四类功能 |
| `verify_offline.js` | **离线可用性**：`CS2HUB_NO_SERVER=1` + `file://` |

这些脚本会自行启动应用并连接远程调试端口，验证完自动关闭。
注意它们会**清掉本机环境变量 `ELECTRON_RUN_AS_NODE`**
（DSH 环境默认设置它，会让 Electron 退化成纯 Node 进程而拿不到 `app`）。

### 调试端口

设 `CS2HUB_DEBUG_PORT=<端口>` 可让应用打开远程调试端口，便于外部脚本连接：

```powershell
$env:CS2HUB_DEBUG_PORT=9333
& ".\dist\win-unpacked\CS2 控制台指令查询中心.exe"
# 然后访问 http://127.0.0.1:9333/json/list
```

## 未签名说明

安装包与 exe **未做代码签名**（无证书）。因此首次运行 Windows SmartScreen
可能提示「Windows 已保护你的电脑」，需点「更多信息 → 仍要运行」。
如需消除，需购买代码签名证书并在 `package.json` 的 `win` 里配置 `certificateFile`。
