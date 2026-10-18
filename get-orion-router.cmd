@echo off
rem One-command Orion Router installer for cmd.exe (forwards arguments such as -NoStartWithWindows).
rem   curl -L -o get-orion-router.cmd https://raw.githubusercontent.com/orion-ai-assistant/orion-router/main/get-orion-router.cmd && get-orion-router.cmd
if exist "%~dp0get-orion-router.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0get-orion-router.ps1" %*
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; & ([scriptblock]::Create((Invoke-RestMethod 'https://raw.githubusercontent.com/orion-ai-assistant/orion-router/main/get-orion-router.ps1'))) %*"
)
exit /b %ERRORLEVEL%
