# One-command Orion Router installer (Router only, no Hub): downloads the signed installer bundle from the
# Router's own GitHub Release feed and installs %LOCALAPPDATA%\Orion\Router.
#   PowerShell: irm https://raw.githubusercontent.com/orion-ai-assistant/orion-router/main/get-orion-router.ps1 | iex
# The bundle carries the public trust root; every package is signature-verified by the installer before
# anything is extracted or run. Updates come from this same Router feed only.
#
# Already have Orion (Hub)? The same command ADDS the Router next to it and leaves Hub, Client and their data
# untouched. Hub/Client can later be added to a Router-only installation with get-orion.ps1 of the Hub
# repository; the Router is adopted as it is (no reinstall; its data, identity and releases are kept).
param(
    [string]$Repo = 'orion-ai-assistant/orion-router',
    [string]$Tag = 'feed',
    [switch]$NoStart,
    [switch]$NoStartWithWindows,
    [switch]$NoAutoUpdate,
    [switch]$NoFirewall
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

if ($env:OS -ne 'Windows_NT' -or $env:PROCESSOR_ARCHITECTURE -notin 'AMD64') {
    throw 'Orion Router requires 64-bit Windows 10 (1903) or later.'
}
$orion = Join-Path $env:LOCALAPPDATA 'Orion'
$existing = Test-Path (Join-Path $orion 'install.json')
$base = "https://github.com/$Repo/releases/download/$Tag/"
$bundle = Join-Path $env:TEMP ('orion-router-bootstrap-' + [guid]::NewGuid().ToString('N') + '.zip')
# A first installation keeps its bundle as the retained bootstrap; an addition runs from a throw-away copy.
if ($existing) { $target = Join-Path $env:TEMP ('orion-router-installer-' + [guid]::NewGuid().ToString('N')) }
else { $target = Join-Path $orion 'Bootstrap-Installer' }
if (-not $existing -and (Test-Path -LiteralPath $target)) {
    # No registered installation: this is left over from an earlier removed or failed Orion install. Replace it; if a
    # closing process still holds it, use a fresh folder next to it (the installer removes the old one later).
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $target) { $target = Join-Path $orion ('Bootstrap-Installer-' + [guid]::NewGuid().ToString('N').Substring(0, 8)) }
}
try {
    Write-Host 'Downloading the Orion Router installer...'
    Invoke-WebRequest -UseBasicParsing -Uri ($base + 'orion-bootstrap-windows-x64.zip') -OutFile $bundle
    New-Item -ItemType Directory -Force -Path $orion | Out-Null
    Expand-Archive -LiteralPath $bundle -DestinationPath $target
} finally {
    Remove-Item -LiteralPath $bundle -Force -ErrorAction SilentlyContinue
}
try {
    $arguments = @{ Components = @('router'); Root = $orion }
    if ($existing) { $arguments.AddMissing = $true }
    # Never start Orion from an administrator window: services started elevated cannot be managed by the normal
    # shortcut afterwards. Install elevated if needed, start through Explorer (normal rights).
    $elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (($elevated -and -not $NoStart -and -not $existing)) {
        Write-Host 'Administrator window detected: Orion Router will be started through the desktop shortcut with normal rights.'
        $arguments.NoStart = $true
    }
    if ($NoStart -or $existing) { $arguments.NoStart = $true }
    if ($NoStartWithWindows) { $arguments.NoStartWithWindows = $true }
    if ($NoAutoUpdate) { $arguments.NoAutoUpdate = $true }
    if ($NoFirewall) { $arguments.NoFirewall = $true }
    if ($existing) { Write-Host 'Mevcut Orion kurulumu bulundu: yalnizca Router eklenecek, kurulu olanlara dokunulmaz.' }
    else { Write-Host 'Installing the Router (this takes a few minutes)...' }
    & (Join-Path $target 'Install-Orion.ps1') @arguments
    if ($LASTEXITCODE -eq 3) { Write-Host 'Hicbir sey degistirilmedi.'; return }
    if ($LASTEXITCODE -ne 0) { throw "Orion Router installation failed (exit $LASTEXITCODE). Your data is kept; see $orion." }
} finally {
    if ($existing) { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue }
}
if ($existing) {
    Write-Host 'Router eklendi. Orion''u masaustu kisayolundan acin.'
} elseif ($elevated -and -not $NoStart) {
    $shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Orion Router.lnk'
    if (Test-Path -LiteralPath $shortcut) { Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $shortcut + '"') }
    else { Write-Host 'Open Orion Router from the Start menu or the desktop shortcut (not from an administrator window).' }
}
