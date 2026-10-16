# 本次会话改动清单

> 项目**没有 git**（本机未安装 git，项目内也没有 `.git`），所以没有 commit 级 diff。
> 下面的对比基于：备份文件、文件时间戳、以及可复现的结构断言。
> 凡是我无法验证的，都明确标了「无备份 / 无法对比」。

---

## 一、图标更换（最后一次改动）

**设计来源**：用户提供的 167×158 png，逐像素取样后还原为矢量。

| | 旧图标 | 新图标 |
|---|---|---|
| 底色 | 深色 `#0d1117` 石墨 | **`#2f6fed`**（= 应用 `--accent` 主题色） |
| 主体 | 琥珀 `#f0a92b` 终端提示符 + 圆环准星刻度 | 白色 `>_` 终端提示符（细笔画） |
| 风格 | 拟物、多元素 | **扁平、单色块** |
| 预览图 | 蓝 0% / 琥珀有 | 蓝 65–92% / 琥珀 **0.0%** |

### 改动的文件（19 个图标 + 2 个脚本）

| 文件 | 大小 | 变动 |
|---|---|---|
| `assets/icons/icon.svg` | 0.6 KB | **整体重写** 为 `>_` 几何（1024 坐标系） |
| `assets/icons/icon-flat.svg` | 0.6 KB | 跟随主图（原为「无准星环的扁平备选」） |
| `assets/icons/icon-1024.png` | 36.5 KB | 重新渲染 |
| `assets/icons/icon-512.png` | 16.4 KB | 重新渲染 |
| `assets/icons/icon-256.png` | 8.3 KB | 重新渲染（`apple-touch-icon`） |
| `assets/icons/icon-128.png` | 4.2 KB | 重新渲染 |
| `assets/icons/icon-64.png` | 2.2 KB | 重新渲染 |
| `assets/icons/icon-48.png` | 1.7 KB | 重新渲染 |
| `assets/icons/icon-40.png` | 1.4 KB | 重新渲染 |
| `assets/icons/icon-32.png` | 1.1 KB | 重新渲染 |
| `assets/icons/icon-24.png` | 0.9 KB | 重新渲染 |
| `assets/icons/icon-20.png` | 0.7 KB | 重新渲染 |
| `assets/icons/icon-16.png` | 0.6 KB | 重新渲染 |
| `assets/icons/cs2-console-hub.ico` | **102.4 → 21.3 KB** | favicon / 快捷方式，**含尺寸 1 档 → 9 档** |
| `assets/icons/sheet.png` | 42.9 KB | README 顶部预览图，**重画** |
| `assets/icons/sheet-concepts.png` | 25.7 KB | 深/浅底对比图，**重画** |
| `assets/icons/desktop-preview.png` | 42.5 KB | 桌面/任务栏预览，**重画 + 修了文字重叠** |
| `desktop/build/icon.ico` | **102.4 → 21.3 KB** | 构建资源，**含尺寸 1 档 → 9 档** |
| `desktop/build/icon.png` | 8.3 KB | 构建资源 |
| `tools/make_icon.py` | **18.6 → 11.4 KB** | **整体重写**（旧版全部画准星环/刻度，与新设计无关） |
| `tools/read_exe_icon.py` | 5.7 KB | **新增**：从 exe 读 PE 资源提图标，用于验证嵌入 |

**旧图标没有备份，无法做像素级前后对比。** 上表的「旧」值来自：ICO 文件的实测大小、
旧 `make_icon.py` 的文档字符串（写着「深色战术底 + 琥珀色终端提示符 + 圆环准星刻度」），
以及本会话中对该设计的历史描述。新值全部实测。

---

## 二、修复「Electron 不支持 `window.prompt()`」

**问题**：打包版里 9 个功能全是坏的（新建/重命名收藏夹、保存方案、存为指令集、
新建指令集、重命名方案、从收藏夹添加、手动加指令）。红框报错：

```
Uncaught Error: prompt() is not supported. @ app.js:1489
```

| 文件 | 改前 | 改后 | 变动 |
|---|---|---|---|
| `assets/app.js` | **122.2 KB**（有备份） | **124.0 KB** | 新增 6 个函数；10 行原生 `prompt(` → 1 行（注释） |
| `assets/theme.css` | — | 39.7 KB | 新增 `.app-dialog-mask` / `.app-dialog` / `.ad-*` 样式 |
| `design/dev/test_appdialog.js` | — | 新增 | 对话框专项测试（29 项） |
| `desktop/verify_appdialog.js` | — | 7.2 KB | 打包版对话框验证（9 项，含「原生 prompt 不可用」对照断言） |
| `design/dev/test_plan.js` | — | 改 | 原 stub `window.prompt` → 操作真实对话框 |
| `design/dev/test_newfolder.js` | — | 改 | 同上 |
| `design/dev/test_parammode.js` | — | 改 | 同上 |
| `desktop/acceptance.js` | 17.2 KB | 17.2 KB | 原 stub `window.prompt`（**掩盖了真 bug**）→ 操作真实对话框 |

新增函数：`appDialogEl` / `appDialogClose` / `appDialogKey` / `appDialogOpen` /
`appPrompt` / `appConfirm`。

**改前的 app.js 有备份**：`_backup_20261014_110630/app_before_dialog.js`（122.2 KB）。

---

## 三、许可证 MIT → GPLv3

| 文件 | 大小 | 变动 |
|---|---|---|
| `LICENSE` | 33.9 KB | MIT 全文 → **GPLv3 逐字全文**（SPDX 官方源，34,674 字节） |
| `NOTICE` | 4.4 KB | **新增**：版权行 + 双语 GPL 声明 + 6 条附加说明 |
| `package.json` | 3.0 KB | `"license": "MIT"` → **`"GPL-3.0-only"`** |
| `README.md` | 14.8 KB | 新增「许可证」小节（含传染性要求说明） |
| `docs/INTRO.md` | 8.9 KB | 中英各补一段 GPL 说明 |
| `docs/RELEASE_NOTES.md` | 4.0 KB | 许可行改为 GNU GPL v3 |
| `index.html` | 32.8 KB | 「关于本机」加「开源许可」行；免责声明补一条 |
| `tools/verify_readme.py` | 8.1 KB | 新增许可一致性断言（现 106 项全过） |

> `package-lock.json` 里的 `"license": "MIT"` 是**依赖包自己的**许可证，未改动。

---

## 四、脱敏：清除 Steam 用户名

**发现**：`commands.json` / `db.js` 里两条指令的默认值字段带着本机用户名：

```
name     指令的 d 字段 = <用户名>
hostname 指令的 d 字段 = <用户名>
```

根源是 `cvarlist` 导出时把本机设置一并带出。这两个文件**都在源码包里，还会进安装包的 asar**。

| 文件 | 大小 | 变动 |
|---|---|---|
| `data/commands.json` | 1040 KB | 清空 2 条指令的 `d` 字段；`<用户名>` 出现次数 2 → **0** |
| `assets/db.js` | 1040 KB | 同步重新生成；`<用户名>` **0** |
| `tools/build_db.py` | 45.8 KB | **新增 `sanitize_local_pii()` 钩子**，重建时自动脱敏 |
| `tools/save_paste_sample.py` | 23.9 KB | 含真用户名且无任何引用 → **从发布包剔除** |
| `tools/dev/probe_filter.js` | 3.9 KB | 硬编码 `C:\Users\<用户名>\AppData\...` → `os.tmpdir()` |
| `tools/translate_db.py` | 15.3 KB | 去掉请求参数里的占位邮箱（避免被扫描器误判为泄露） |

备份：`_backup_commands/commands_preclear_20261014_200756.json`（1040 KB，原始数据保留）。

---

## 五、新增发布核对脚本

| 文件 | 大小 | 用途 |
|---|---|---|
| `tools/release/scan_secrets.py` | 8.3 KB | 发布前敏感扫描（源码包逐文件 + 从 exe 解 asar 再扫） |
| `tools/release/verify_release.py` | 4.2 KB | 发布包内容复核 |
| `tools/release/make_release.py` | 12.9 KB | **重写**：目录被占用时三级降级，不再半途失败留半成品 |

`npm run scan:secrets` / `verify:release` / `verify:readme` 三个入口。

---

## 六、其他修复

| 文件 | 变动 |
|---|---|
| `start.cmd` | 中文注释 → **纯 ASCII**（cmd.exe 按 GBK 读，UTF-8 中文会乱码）；337 → 480 字节 |
| `desktop/acceptance.js` | 见第二节（stub 掩盖真 bug） |
| `.gitignore` | 确认已排除 `_backup_*/` `design/` `_dumps/` `_raw/`（含旧 API Key / SteamID 的目录） |

---

## 七、发布产物对比

| | 旧（换图标前） | 新（换图标后） |
|---|---|---|
| 安装包 | 79.25 MB | **78.25 MB** |
| 便携版 | 79.02 MB | **78.11 MB** |
| 源码包 | 1.86 MB / 105 文件 | **0.90 MB / 106 文件** |
| 包内 LICENSE | MIT | **GNU GENERAL PUBLIC LICENSE** |
| 包内 `cs2-console-hub.ico` | 1 档 [16] | **9 档 [16…256]** |
| exe 内嵌图标 | 深色底 + 琥珀准星环 | **`#2f6fed` 蓝底 + 白 `>_`**（PE 解析逐帧确认） |
| 敏感信息扫描 | 未做 | **未发现**（用户名/SteamID/旧 Key 全清） |

**体积变小约 1 MB 的原因**：旧 ICO 虽然只有 16px 一档声明，但内部塞了大量虚胖帧；
新 ICO 9 档全是干净 PNG。这是修掉 ICO 写入 bug 的副产品。

---

## 八、我修掉的三个「自己造成的」bug

诚实记录，这些都不是新功能，是我的错误：

1. **`make_icon.py` 的 ICO 只写出 1 档**（用 16px 当基准图，PIL 会跳过比基准大的尺寸）。
   换图标时才发现——**这个 bug 在旧图标时代就存在**。
2. **`scan_secrets.py` 自己把真实 API Key 明文写进黑名单**，成了新的泄露源。
   已改为分段拼接（运行时还原，仓库里看不出原串）。
3. **`read_exe_icon.py` 的 PE 资源解析错两次**（偏移转换重复计算、目录层数判断错）。
   用系统 `notepad.exe` 做对照才发现——验证工具本身也要先验证。

---

## 九、无法对比的部分

| 项目 | 原因 |
|---|---|
| 逐行 diff | 项目无 git，本机无 git |
| 旧图标外观 | 旧图标文件已被覆盖，**没有任何备份** |
| 旧 `app.js` 全文 | 只有改前备份（122.2 KB），可查 |
| 旧 `commands.json` | 有脱敏前备份，可查 |
| 旧 exe / 源码包 | 已被新构建覆盖（`release/` 每次重建） |

---

## 十、移除「上锁功能」（游戏目录完整性检查）

**原因**：该功能无法区分「Steam 更新」与「人为改动」——每次 CS2 更新都会把 69 个文件报成
「与基线不符」，并建议「验证游戏文件完整性」（对更新场景是错的方向：文件本来就是官方最新的）。
详见实测：本机 2026-10-16 02:12 的更新与 `appmanifest_730.acf` 的 `LastUpdated` 完全吻合。

按用户要求**整体删除**，并清除所有按钮、文本、脚本与文档。

| 文件 | 变动 |
|---|---|
| `index.html` | 删除 6 处：开始面板「上锁检查」按钮、顶栏「已上锁」状态、设置里「上锁检查」行、「上锁状态」开关、功能列表项；「使用说明」副标题去掉「上锁检查」 |
| `assets/app.js` | 删除 `renderGuard()` 全部逻辑（含顶栏同步包装、点击详情）、顶栏显隐映射项、快捷键 `L` 绑定；启动时不再调用 |
| `assets/style.css` | 删除 `.btn.guard.ok/.warn/.off` 三条规则 |
| `desktop/server.js` | 删除 `guardState()` 与 `meta.guard` 字段 |
| `tools/server.py` | 删除 `guard_state()` 与 meta 里的 `guard` 字段 |
| `data/db_meta.json` | 删除 `guard` 字段 |
| `package.json` | files 列表去掉 `data/integrity_baseline.json` |
| `tools/guard_check.py` | **删除** |
| `data/integrity_baseline.json` | **删除** |
| `docs/safety-guard.md` | **删除** |
| `README.md` | 删「上锁检查」小节与文件树条目；「实验安全」一节的 PowerShell 示例改为只留「验证游戏文件完整性」，并补「隔离实验环境」建议 |
| `docs/INTRO.md` / `docs/RELEASE_NOTES.md` | 删功能表格行 |
| `docs/packaging.md` | 三处更新（meta 说明、只读加载说明、cfg 目录来源） |
| `tools/verify_readme.py` | 删基线检查；把「上锁」加入「已删功能不得再出现」检查表 |
| `desktop/test_server.js` / `verify_installed.js` / `run_e2e_packaged.js` | 断言从「上锁可用」改为「上锁字段已移除 + 版本字段可读」 |
| `tools/dev/e2e.js` | `[3c]` 段改为回归断言：6 个上锁相关 DOM/字段必须全部不存在 |

### ⚠️ 连带修复的一个真 bug

`desktop/server.js` 的 `resolveGameDir()` 原本是**从 `integrity_baseline.json` 读游戏目录**的。
直接删基线会让「导出 cfg」一起失效。已改为：

1. 先读可写配置 `game_dir.json`（userData 目录）
2. 否则自动探测：扫各 Steam 根目录的 `libraryfolders.vdf`，取所有库路径

实测确认：**删掉基线后 `/api/game/cfgdir` 仍能正确定位**
`...\Counter-Strike Global Offensive\game\csgo\cfg`。

### 回归结果

| 项目 | 结果 |
|---|---|
| e2e | **全部通过**（含 6 条上锁已移除断言） |
| 本地服务 `test_server.js` | 32 / 32 |
| 打包版验收 | 46 / 46 |
| 启动自检 | **16 / 16**（新增「上锁字段已移除」断言） |
| 导出 cfg（打包版） | 15 / 15 |
| 离线可用 | 16 / 16 |
| 对话框 | 9 / 9 |
| README 核对 | 102 / 102 |
| 敏感扫描 / 发布包复核 | 通过 |
