# CS2 控制台指令查询中心 —— 启动器
# 优先使用 DSH 运行时自带的 Python；找不到就退回系统 python / py
# 用法：
#   .\start.ps1                  默认 8788 端口并自动开浏览器
#   .\start.ps1 --port 8899      换端口
#   .\start.ps1 --no-browser     不开浏览器
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 解析 --port / --no-browser（server.py 通过 CS2HUB_PORT 环境变量取端口）
$serverArgs = @()
for ($i = 0; $i -lt $args.Count; $i++) {
  $a = [string]$args[$i]
  if ($a -eq '--port' -and $i + 1 -lt $args.Count) {
    $env:CS2HUB_PORT = [string]$args[$i + 1]
    $i++
  } elseif ($a -like '--port=*') {
    $env:CS2HUB_PORT = $a.Substring(7)
  } else {
    $serverArgs += $a
  }
}

$candidates = @(
  (Join-Path $env:USERPROFILE '.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe')
) + @(Get-Command python -ErrorAction SilentlyContinue | ForEach-Object { $_.Source }) +
    @(Get-Command py -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })

$py = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $py) {
  Write-Host '[!] 未找到 Python。' -ForegroundColor Red
  Write-Host '    可安装 Python 3.8+ 后重试；也可以直接双击 index.html 使用离线模式。' -ForegroundColor Yellow
  Read-Host '按回车退出'
  exit 1
}

$port = if ($env:CS2HUB_PORT) { $env:CS2HUB_PORT } else { '8788' }
Write-Host '============================================================' -ForegroundColor DarkGray
Write-Host '  CS2 控制台指令查询中心' -ForegroundColor Yellow
Write-Host ('  地址： http://127.0.0.1:' + $port + '/') -ForegroundColor Green
Write-Host '  正在启动本地服务，稍后会自动打开浏览器…' -ForegroundColor Gray
Write-Host ('  Python: ' + $py) -ForegroundColor DarkGray
Write-Host '  关闭本窗口即可退出。' -ForegroundColor Gray
Write-Host '============================================================' -ForegroundColor DarkGray

& $py (Join-Path $root 'tools\server.py') @serverArgs

if ($LASTEXITCODE -ne 0) {
  Write-Host ''
  Write-Host '[!] 服务异常退出。若提示端口被占用，换一个端口再试：' -ForegroundColor Yellow
  Write-Host '    .\start.ps1 --port 8899' -ForegroundColor Gray
  Read-Host '按回车退出'
}
