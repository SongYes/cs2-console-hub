# CS2 控制台指令查询中心 —— 创建桌面快捷方式（带创建后自校验）
# 用法： powershell -ExecutionPolicy Bypass -File tools\make_shortcut.ps1
param(
  [string]$Name = 'CS2 指令查询中心',
  [string]$IconName = 'cs2-console-hub.ico',
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$target = Join-Path $root 'start.cmd'
$icon = Join-Path $root ('assets\icons\' + $IconName)
if (-not (Test-Path $target)) { throw "找不到启动器：$target" }
if (-not (Test-Path $icon))   { throw "找不到图标：$icon" }

# 桌面可能被 OneDrive 重定向；候选都试，取真实存在的那个
$cands = @([Environment]::GetFolderPath('Desktop'),
           (Join-Path $env:USERPROFILE 'Desktop'),
           (Join-Path $env:USERPROFILE 'OneDrive\Desktop')) |
         Where-Object { $_ } | Select-Object -Unique
$desktop = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $desktop) { throw '找不到桌面目录' }

$link = Join-Path $desktop ($Name + '.lnk')
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $target
$sc.WorkingDirectory = $root
$sc.IconLocation = "$icon,0"
$sc.Description = 'CS2 控制台指令查询中心：全量指令库 + 中文释义 + 分类检索 + AI 辅助出 cfg'
$sc.WindowStyle = 1
$sc.Save()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($sc) | Out-Null
Start-Sleep -Milliseconds 400

# ---- 创建后自校验 ----
$exists = Test-Path -LiteralPath $link
$ok = $exists
$detail = @()
if ($exists) {
  $chk = $shell.CreateShortcut($link)
  $ok = ($chk.TargetPath -eq $target) -and ($chk.IconLocation -like "$icon*")
  $detail += "TargetPath = $($chk.TargetPath)"
  $detail += "IconLocation = $($chk.IconLocation)"
  $detail += "WorkingDirectory = $($chk.WorkingDirectory)"
} else {
  $detail += '文件未出现在桌面'
}

if (-not $Quiet) {
  Write-Host ("[桌面] " + $desktop) -ForegroundColor DarkGray
  Write-Host ("[链接] " + $link) -ForegroundColor DarkGray
  foreach ($d in $detail) { Write-Host ("  " + $d) -ForegroundColor DarkGray }
}
if ($ok) {
  Write-Host '[OK] 桌面快捷方式已创建并校验通过' -ForegroundColor Green
  exit 0
} else {
  Write-Host '[!] 快捷方式创建后校验失败' -ForegroundColor Red
  exit 1
}
