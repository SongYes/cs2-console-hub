# 发布到 GitHub 指引

本目录已分成两套，**不要混在一起上传**：

```
release/
  source/     ← 源码，传到 GitHub 仓库（或新建仓库后上传）
  win-x64/    ← 可执行文件，传到 GitHub Releases 附件
```

---

## 一、源码 → GitHub 仓库

`cs2-console-hub-1.0.0-src/` 是干净的源码目录（`node_modules`、`dist`、备份、
开发截图、数据库中间产物都已剔除），也可以直接用 `cs2-console-hub-1.0.0-src.zip`。

### 方式 A：网页上传（本机没装 git 也能用）

1. GitHub 右上角 **+** → **New repository**
   - Repository name 例如 `cs2-console-hub`
   - 选 **Public**，**不要**勾选 "Add a README file"（我们自带 README）
   - Create repository
2. 进入空仓库页，点 **uploading an existing file**
3. 把 `cs2-console-hub-1.0.0-src/` **里面的所有内容**（含 `.gitignore`、`.gitattributes`
   这两个隐藏文件）拖进去
   - 注意：拖「目录里的内容」，不是拖外层文件夹，否则仓库会多一层嵌套
   - 若隐藏文件没被拖入，可在文件管理器里开启「显示隐藏的项目」再操作
4. 填提交信息，例如 `v1.0.0: 首次发布`，点 **Commit changes**

> 网页上传单次约 100 个文件，本源码包约 103 个，若被拆成两次提交也能正常合并。

### 方式 B：装了 git 的话

```bash
cd cs2-console-hub-1.0.0-src
git init
git add .
git commit -m "v1.0.0: 首次发布"
git branch -M main
git remote add origin https://github.com/SongYes/<仓库名>.git
git push -u origin main
```

`.gitignore` 已配好，以后本地构建产生的 `node_modules/`、`dist/`、`release/`、
`data/` 中间产物、`_dumps/`、`_raw/` 都不会被误提交。

---

## 二、发布版 → GitHub Releases

1. 仓库页 → 右侧 **Releases** → **Draft a new release**
2. **Choose a tag** 填 `v1.0.0` → 选 `Create new tag: v1.0.0 on publish`
3. **Release title** 填：`v1.0.0 —— 中文释义 / 参数方案 / AI 辅助`
4. **Describe this release** 里粘贴 `win-x64/RELEASE_NOTES.md` 的内容
5. **Attach binaries** 上传这两个文件：

   | 文件 | 给谁 |
   |---|---|
   | `CS2控制台指令查询中心-1.0.0-安装包.exe` | 大多数人（可安装、有快捷方式、可卸载） |
   | `CS2控制台指令查询中心-1.0.0-便携版.exe` | 想免安装 / 放 U 盘（单文件双击即用） |

   `SHA256SUMS.txt` 与 `RELEASE_NOTES.md` 也建议一并附上。
6. 点 **Publish release**

### 为什么 exe 不进仓库

两个 exe 各约 79 MB，会把仓库撑大（且 GitHub 有单文件 100 MB 限制），
所以走 Releases 附件而不是提交进仓库。

### 目录里的 start.cmd / start.ps1 是什么

它们是**网页版**启动器（需要本机有 Python 3.8+，启动 `tools/server.py` 后开浏览器），
与桌面版（安装包 / 便携版，Electron，无需 Python）是**并列的两种用法**，功能一致：

| | 桌面版 | 网页版 |
|---|---|---|
| 入口 | 安装包 / 便携版 exe | `start.cmd` 或双击 `index.html` |
| 依赖 | 无 | 需要 Python（`start.cmd`）；双击 `index.html` 则不要 |
| 本地服务 | 内置 Node（随机端口） | `tools/server.py`（默认 8788） |

`start.cmd` 特意写成**纯 ASCII**：cmd.exe 按控制台代码页（简中为 GBK）读取 .cmd，
含 UTF-8 中文会显示成乱码。中文提示都在 `start.ps1`（带 UTF-8 BOM，PowerShell 能正确识别）。

---

## 三、发布前建议自查

本仓库自带核对脚本，改完 README 或文档后跑一遍：

```powershell
npm run verify:readme      # README 每条事实是否与仓库一致
npm run verify:release     # 发布包内容是否齐备、有无产物混入
```

- [ ] 上面两个脚本通过
- [ ] 安装包能装、能启动、能卸载（`npm run verify:app` / `npm run test:accept`）
- [ ] 便携版双击能直接用
- [ ] 软件内「设置 → 关于本软件」的版本号与许可信息为最新
- [ ] `LICENSE`（GPLv3）与 `NOTICE` 随源码包提供
- [ ] 仓库 About 区填好简介与话题标签（见 `docs/repo-description.md`）

## 四、校验下载完整性

发布后可在 Release 说明里提示用户校验：

```powershell
# 下载两个 exe 与 SHA256SUMS.txt 到同一目录后
Get-FileHash *.exe -Algorithm SHA256 | Format-List
# 与 SHA256SUMS.txt 里的值比对
```
