# CS2 控制台指令查询中心 · CS2 Console Command Hub

> 中英对照工具介绍 / Bilingual tool introduction

---

## 中文

### 这是什么

给中文玩家用的 **CS2（Counter-Strike 2）控制台指令查询工具**。它把游戏自带的几千条控制台指令整理成一份可搜索、带中文释义、按效果分类的本地库，并且能用自然语言帮你把「想要的游戏效果」翻成具体指令与 `.cfg` 配置。

**全量指令库 + 中文释义 + 按效果分类 + AI 辅助 + 参数方案**，一个本地程序搞定，不修改游戏文件。

### 解决什么问题

CS2 有 **2802 条**控制台指令，官方说明全是英文、散落在 `cvarlist` 输出里。想改个准星或雷达，得先知道指令叫什么、值该填多少、会不会有风险——对中文玩家门槛很高。这个工具把这些麻烦一次性解决：

- 不用记英文指令名，**搜中文就行**
- 不用猜取值范围，每条都有**默认值、类型、作用域**
- 不用怕踩坑，高风险指令**明确标注**
- 不用手动凑配置，改好的数值可**存成方案**，一键导出 `.cfg`

### 主要功能

| 功能 | 说明 |
|---|---|
| **中文搜索** | 搜「随地安放炸弹」直接出 `mp_plant_c4_anywhere`；支持模糊与拼音式匹配 |
| **按效果分类** | 15 个分类、66 个子类，按「准星与瞄准 / HUD 与界面 / 性能与网络」这类**玩家意图**组织，而不是按字母表 |
| **完整释义** | 2802 条**全部有中文释义**，并标注默认值、类型、作用域、风险等级、是否需 `sv_cheats` |
| **参数方案** | 把多条指令凑成一套、逐条改数值，保存为「编号 + 注释」的方案，随时读取套用 |
| **导出 cfg** | 方案可一键导出 `.cfg`：直接写进游戏 `cfg` 目录（控制台 `exec 文件名` 即生效），或生成到指定位置自己拖进去 |
| **AI 辅助** | 用大白话说需求，AI 结合本地指令库给出方案；支持 DeepSeek / OpenAI / 通义 / 智谱 / 本地 Ollama |
| **收藏夹** | 多收藏夹管理，支持空夹与导出 |
| **中英对照** | 仅中文 / 仅英文 / 中英对照，三选一 |
| **卡片 / 专业模式** | 卡片适合浏览，表格适合批量操作 |

### 数据来源与可信度

指令库以**游戏自身 `cvarlist` 的完整导出**为权威来源，逐条核对：

- **2802 条**全部在游戏本体里确认存在（不是从 wiki 抄来的）
- 其中 **675 条**是控制台命令（`getpos` / `noclip` / `give` / `slot1` …）
- **1253 条**为正式版客户端下发
- **100%** 有中文释义
- 数据更新截止：**2026 年 9 月 25 日**

### 安全与隐私

- **不修改游戏文件本体**：不注入、不反编译、不替换资源。唯一读取的是游戏自身输出的控制台指令清单（`cvarlist`）。
- **不修改不读取游戏文件本体，不承担任何 VAC 责任。** 任何修改游戏文件本体的行为都可能导致 VAC 封禁。
- 部分指令（标 **cheat**）**只能在本地或自建房使用**，官方匹配服强制 `sv_cheats 0`。
- 收藏夹、方案、设置与 AI 翻译缓存**全部保存在本机**，不上传。
- **不读取、不存储**任何 Steam 账号信息。API Key 只存本机，请求经本地服务转发。

完整条款见软件内「**设置 → 免责声明与安全使用规范**」。

### 怎么获取

- **免安装便携版**：单个 `.exe`，双击即用
- **安装包**：可选安装目录，自动建快捷方式，可正常卸载

两者都**无需 Python 或任何运行时**。Windows 10 / 11 x64，约 300 MB 空间。

> 首次运行可能提示「Windows 已保护你的电脑」——本程序未做代码签名，点「更多信息 → 仍要运行」即可。

### 开源免费

**本软件开源免费，任何收费倒卖行为均为诈骗。**

作者从未授权任何第三方以本软件名义收费。不含付费解锁内容、会员体系或广告。

以 **GNU GPL v3** 发布：你可以自由使用、修改、再发布，甚至商用；但**再发布的衍生作品必须同样以 GPL v3 开源**，不得改为闭源专有。

### 联系

- 邮箱：songyuanuwu@gmail.com
- GitHub：<https://github.com/SongYes>
- B 站：<https://space.bilibili.com/1214830446>

---

## English

### What it is

A **console command browser for CS2 (Counter-Strike 2)**, built for Chinese-speaking players. It turns the game's several thousand console commands into a local, searchable library with Chinese translations and effect-based categories — and it can translate a plain-language description of what you want into actual commands and a `.cfg` file.

**Full command database + Chinese glosses + effect-based categories + AI assistance + parameter presets**, all in one local app that never modifies your game files.

### The problem it solves

CS2 ships **2,802 console commands**, documented only in English and scattered across raw `cvarlist` output. Tweaking your crosshair or radar means knowing the exact command name, the valid value range, and whether it carries a risk — a high barrier if English isn't your first language. This tool removes that friction:

- **Search in Chinese** instead of memorizing English command names
- Every entry shows its **default value, type, and scope** — no guessing
- High-risk commands are **clearly flagged**
- Tune values once, **save them as a preset**, and export a ready-to-use `.cfg`

### Features

| Feature | Details |
|---|---|
| **Chinese search** | Type 「随地安放炸弹」 to find `mp_plant_c4_anywhere`; fuzzy matching included |
| **Effect-based categories** | 15 categories, 66 subcategories, organized by **player intent** (crosshair / HUD / performance) rather than alphabetically |
| **Complete glosses** | All 2,802 entries **have Chinese descriptions**, plus default value, type, scope, risk level, and `sv_cheats` requirement |
| **Parameter presets** | Group commands into a set, tune each value, save as a named preset with notes, reload it anytime |
| **Export `.cfg`** | One click to export a preset: write it straight into the game's `cfg` folder (then `exec <name>` in console), or generate it anywhere and drag it in yourself |
| **AI assistance** | Describe what you want in plain language; the AI answers using the local command database. Supports DeepSeek / OpenAI / Ollama, etc. |
| **Favourites** | Multiple folders, including empty ones, with export |
| **Bilingual display** | Chinese only / English only / both |
| **Integrity check** | Compare against a clean baseline before joining a protected server |
| **Card / table mode** | Cards for browsing, table for bulk work |

### Data & trustworthiness

The database is sourced from the game's **own `cvarlist` export**, verified entry by entry:

- **2,802 entries**, every one confirmed present in the game itself (not scraped from a wiki)
- **675** are console commands (`getpos`, `noclip`, `give`, `slot1`, …)
- **1,253** are shipped by the release client
- **100%** have Chinese descriptions
- Database updated through **25 September 2026**

### Safety & privacy

- **Does not modify game files.** No injection, no decompilation, no asset replacement. The only thing read is the game's own console command listing (`cvarlist`).
- **It neither modifies nor reads game file contents, and accepts no VAC liability.** Modifying game files can result in a VAC ban.
- Some commands (marked **cheat**) **only work locally or on your own server**; official matchmaking enforces `sv_cheats 0`.
- Favourites, presets, settings, and AI translation cache are stored **entirely on your machine** and never uploaded.
- **Never reads or stores** any Steam account information. API keys stay local; requests are proxied through a bundled local service.

Full terms are in the app under **Settings → Disclaimer & Safe Use**.

### Getting it

- **Portable**: a single `.exe`, double-click to run
- **Installer**: choose the install location, shortcuts created automatically, clean uninstall

Neither requires Python or any runtime. Windows 10 / 11 x64, roughly 300 MB.

> On first launch Windows SmartScreen may warn you — the binary is not code-signed. Click "More info" → "Run anyway".

### Open source & free

**This software is open source and free. Any paid resale is a scam.**

The author has never authorised anyone to charge for this software. There are no paid unlocks, memberships, or ads.

Released under the **GNU GPL v3**: you are free to use, modify and redistribute it, commercially included — but any **derivative work you distribute must also be open-sourced under the GPL v3**, not relicensed as closed-source proprietary software.

### Contact

- Email: songyuanuwu@gmail.com
- GitHub: <https://github.com/SongYes>
- Bilibili: <https://space.bilibili.com/1214830446>
