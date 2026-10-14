@echo off
rem CS2 Console Command Hub - web version launcher (logic lives in start.ps1)
rem Keep this file ASCII-only: cmd.exe reads a .cmd using the console codepage
rem (GBK on zh-CN), so UTF-8 Chinese text here would show as mojibake.
setlocal
cd /d "%~dp0"
where pwsh >nul 2>nul && (pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %* & goto :done)
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
:done
endlocal
