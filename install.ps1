param (
    [string]$Mode = "docker"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "     Orion Router Native Installer        " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

if ($Mode -notin @("local", "docker")) {
    Write-Host "`nERROR: You did not specify the installation mode!" -ForegroundColor Red
    Write-Host "Please run the script with one of the following parameters:`n" -ForegroundColor Yellow
    Write-Host "  1. Local Installation:" -ForegroundColor White
    Write-Host "     .\install.ps1 local`n" -ForegroundColor Green
    Write-Host "  2. Docker Installation:" -ForegroundColor White
    Write-Host "     .\install.ps1 docker`n" -ForegroundColor Green
    exit 1
}

Write-Host "Installation Mode: $Mode" -ForegroundColor Yellow
$TargetFolder = Join-Path $env:LOCALAPPDATA "OrionRouter"
$RepoUrl = "https://github.com/orion-ai-assistant/orion-router.git"
Write-Host "Target Directory:  $TargetFolder`n" -ForegroundColor DarkGray

# 1. Requirement Checks
Write-Host "[1/5] Checking system requirements..."
if ($Mode -eq "local") { $requiredCommands = @("git", "python", "npm") }
else { $requiredCommands = @("git", "docker") }

foreach ($cmd in $requiredCommands) {
    try { Get-Command $cmd -ErrorAction Stop | Out-Null }
    catch { Write-Error "Error: '$cmd' not found! Please install it and try again."; exit 1 }
}
$joinedCmds = $requiredCommands -join ', '
Write-Host "[OK] Requirements met ($joinedCmds)." -ForegroundColor Green
Write-Host ""

# 2. Repo Clone or Update
Write-Host "[2/5] Setting up Orion Router AppData directory..."

$StopScript = Join-Path $TargetFolder "bin\stop.py"
if (Test-Path $StopScript) {
    try {
        Start-Process -FilePath "python" -ArgumentList $StopScript, "--quiet" -NoNewWindow -Wait -ErrorAction SilentlyContinue
    } catch {}
}


$GitPath = Join-Path $TargetFolder ".git"

if (-not (Test-Path $TargetFolder)) {
    # Case 1: No folder at all — fresh clone
    Write-Host "[OK] Cloning fresh copy from GitHub..." -ForegroundColor Yellow
    git clone $RepoUrl $TargetFolder
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] Clone failed." -ForegroundColor Red; exit 1 }

} elseif (-not (Test-Path $GitPath)) {
    # Case 2: Folder exists but no .git — init in-place (avoids locked-folder delete)
    Write-Host "[!] Folder exists but has no git repository. Initializing in-place..." -ForegroundColor Yellow
    Set-Location -Path $TargetFolder
    git init | Out-Null
    # Safely set remote regardless of whether it already exists
    $ErrorActionPreference = "Continue"
    $remotes = git remote 2>$null
    $ErrorActionPreference = "Stop"
    if ($remotes -contains "origin") {
        git remote set-url origin $RepoUrl
    } else {
        git remote add origin $RepoUrl
    }
    git fetch origin main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git fetch failed." -ForegroundColor Red; exit 1 }
    git reset --hard origin/main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git reset failed." -ForegroundColor Red; exit 1 }
    Write-Host "[OK] Repository initialized and updated." -ForegroundColor Green

} else {
    # Case 3: Folder + .git exist — ensure remote is correct then update
    Write-Host "[OK] Directory exists, forcing updates from GitHub..." -ForegroundColor Yellow
    Set-Location -Path $TargetFolder
    # Ensure origin points to the right URL (fixes broken state from previous failed installs)
    $ErrorActionPreference = "Continue"
    $remotes = git remote 2>$null
    $ErrorActionPreference = "Stop"
    if ($remotes -contains "origin") {
        git remote set-url origin $RepoUrl
    } else {
        git remote add origin $RepoUrl
    }
    git fetch origin main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git fetch failed. Check your connection." -ForegroundColor Red; exit 1 }
    git reset --hard origin/main
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git reset failed." -ForegroundColor Red; exit 1 }
}

Set-Location -Path $TargetFolder
Write-Host ""

# --- Smart .env Check ---
Write-Host "[*] Checking .env file..."
$SysLang = (Get-Culture).TwoLetterISOLanguageName
if (-not $SysLang) { $SysLang = "en" }

# .env.example'daki aktif (yorum olmayan) anahtarları mevcut .env'ye ekleyen yardımcı fonksiyon
function Merge-EnvFromExample {
    param([string]$EnvPath, [string]$ExamplePath)
    $envContent = Get-Content $EnvPath -Raw
    $appended = 0
    foreach ($line in Get-Content $ExamplePath) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith("#")) { continue }
        if ($line -match "^([A-Za-z_][A-Za-z0-9_]*)=(.*)$") {
            $key = $Matches[1]
            $val = $Matches[2]
            if ($envContent -notmatch "(?m)^$key=") {
                Add-Content -Path $EnvPath -Value "$key=$val" -Encoding UTF8
                Write-Host "    + '$key' .env'de bulunamadi, otomatik eklendi." -ForegroundColor Cyan
                $appended++
            }
        }
    }
    return $appended
}

if (-not (Test-Path ".env")) {
    # --- Yeni kurulum: example'dan kopyala, ardından CLI_LANG ekle ---
    Write-Host "[*] .env not found. Creating..." -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    } else {
        New-Item -Path ".env" -ItemType File | Out-Null
    }
    Add-Content -Path ".env" -Value "`nCLI_LANG=$SysLang" -Encoding UTF8
    Write-Host "[OK] .env created (Language: $SysLang)." -ForegroundColor Green
} else {
    # --- Mevcut kurulum: eksik anahtarları ekle, CLI_LANG yoksa ekle ---
    Write-Host "[OK] Existing .env file detected. Checking for missing keys..." -ForegroundColor Green
    $added = 0
    if (Test-Path ".env.example") {
        $added = Merge-EnvFromExample -EnvPath ".env" -ExamplePath ".env.example"
    }
    $envContent = Get-Content ".env" -Raw
    if ($envContent -notmatch "(?m)^CLI_LANG=") {
        Add-Content -Path ".env" -Value "CLI_LANG=$SysLang" -Encoding UTF8
        Write-Host "    + 'CLI_LANG' .env'de bulunamadi, otomatik eklendi ($SysLang)." -ForegroundColor Cyan
        $added++
    }
    if ($added -gt 0) {
        Write-Host "[OK] $added eksik ayar .env dosyaniza eklendi." -ForegroundColor Green
    } else {
        Write-Host "[OK] .env dosyasi guncel, eksik ayar yok." -ForegroundColor Green
    }
}
Write-Host ""

# 3 & 4. Dependencies
if ($Mode -eq "local") {
    Write-Host "[3/5] Installing Python packages (pip)..."
    python -m pip install -e .
    Write-Host "`n[4/5] Installing Dashboard dependencies (NPM)..."
    if (Test-Path "dashboard") { Set-Location -Path "dashboard"; npm install; Set-Location -Path ".." }
    Write-Host ""
} else {
    Write-Host "[3/5] and [4/5] Steps Skipped..." -ForegroundColor DarkGray
    Write-Host "Docker mode selected; local dependencies will not be installed.`n" -ForegroundColor DarkGray
}

# 5. Global Command Installation
Write-Host "[5/5] Installing global 'orionrouter' command..." -ForegroundColor Yellow

# Build wrapper script lines as an array to avoid here-string encoding issues
if ($Mode -eq "local") {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('param ([Parameter(Position=0)][string]$Action = "help")')
    $lines.Add('[Console]::OutputEncoding = [System.Text.Encoding]::UTF8')
    $lines.Add('')
    $lines.Add('$ProjectPath = "$env:LOCALAPPDATA\OrionRouter"')
    $lines.Add('$PidFile    = Join-Path $ProjectPath ".orion.pid"')
    $lines.Add('$LogFile    = Join-Path $ProjectPath "orion_output.log"')
    $lines.Add('$ErrFile    = Join-Path $ProjectPath "orion_error.log"')
    $lines.Add('')
    $lines.Add('$PreviousLocation = Get-Location')
    $lines.Add('try {')
    $lines.Add('if ($Action -in @("help","")) {')
    $lines.Add('    Write-Host ""')
    $lines.Add('    Write-Host "  Orion Router CLI" -ForegroundColor Cyan')
    $lines.Add('    Write-Host "  --------------------------------" -ForegroundColor DarkGray')
    $lines.Add('    Write-Host "  Usage: orionrouter [start|stop|logs|help]" -ForegroundColor Yellow')
    $lines.Add('    Write-Host ""')
    $lines.Add('    Write-Host "  Commands:"')
    $lines.Add('    Write-Host "    start   Starts the server in the background"')
    $lines.Add('    Write-Host "    stop    Stops the running server and child processes"')
    $lines.Add('    Write-Host "    logs    Shows background logs and errors"')
    $lines.Add('    Write-Host "    help    Shows this help menu"')
    $lines.Add('    Write-Host ""')
    $lines.Add('} elseif ($Action -eq "start") {')
    $lines.Add('    if (Test-Path $PidFile) {')
    $lines.Add('        $existingPid = Get-Content $PidFile')
    $lines.Add('        if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {')
    $lines.Add('            Write-Host "[OK] Orion Router is already running!" -ForegroundColor Yellow')
    $lines.Add('            Write-Host "To view logs: orionrouter logs" -ForegroundColor Cyan')
    $lines.Add('            return')
    $lines.Add('        } else { Remove-Item -Path $PidFile -ErrorAction SilentlyContinue }')
    $lines.Add('    }')
    $lines.Add('    Write-Host "Starting Orion Router locally..." -ForegroundColor Cyan')
    $lines.Add('    Set-Location $ProjectPath')
    $lines.Add('    $p = Start-Process -FilePath "python" -ArgumentList "orion.py","prod" -RedirectStandardOutput $LogFile -RedirectStandardError $ErrFile -PassThru -WindowStyle Hidden')
    $lines.Add('    $p.Id | Out-File -FilePath $PidFile')
    $lines.Add('    Write-Host "Streaming live logs... (Ctrl+C to exit)" -ForegroundColor Magenta')
    $lines.Add('    Get-Content $LogFile -Wait -Tail 10 -Encoding UTF8')
    $lines.Add('} elseif ($Action -eq "stop") {')
    $lines.Add('    $StopScript = Join-Path $ProjectPath "bin\stop.py"')
    $lines.Add('    if (Test-Path $StopScript) {')
    $lines.Add('        try {')
    $lines.Add('            Start-Process -FilePath "python" -ArgumentList $StopScript -NoNewWindow -Wait -ErrorAction SilentlyContinue')
    $lines.Add('        } catch {}')
    $lines.Add('    }')
    $lines.Add('    Write-Host "[OK] Orion Router stopped (any background databases/ports cleared)." -ForegroundColor Green')
    $lines.Add('} elseif ($Action -eq "logs") {')
    $lines.Add('    if (Test-Path $ErrFile) {')
    $lines.Add('        $errs = Get-Content $ErrFile -Tail 15 -ErrorAction SilentlyContinue -Encoding UTF8')
    $lines.Add('        if ($errs) {')
    $lines.Add('            Write-Host "`n[!] RECENT ERRORS:" -ForegroundColor Red')
    $lines.Add('            $errs | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkRed }')
    $lines.Add('            Write-Host "----------------------------------------------------" -ForegroundColor Gray')
    $lines.Add('        }')
    $lines.Add('    }')
    $lines.Add('    if (Test-Path $LogFile) {')
    $lines.Add('        Write-Host "  Streaming live logs... (Ctrl+C to exit)" -ForegroundColor Magenta')
    $lines.Add('        Get-Content $LogFile -Wait -Tail 20 -Encoding UTF8')
    $lines.Add('    } else { Write-Host "No log file exists yet." -ForegroundColor Red }')
    $lines.Add('} else { Write-Host "Invalid command. Type: orionrouter help" -ForegroundColor Red }')
    $lines.Add('} finally {')
    $lines.Add('    Set-Location $PreviousLocation')
    $lines.Add('}')
} else {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('param ([Parameter(Position=0)][string]$Action = "help")')
    $lines.Add('[Console]::OutputEncoding = [System.Text.Encoding]::UTF8')
    $lines.Add('')
    $lines.Add('$ProjectPath = "$env:LOCALAPPDATA\OrionRouter"')
    $lines.Add('$ComposeFile = "docker-compose.ghcr.yml"')
    $lines.Add('')
    $lines.Add('$PreviousLocation = Get-Location')
    $lines.Add('try {')
    $lines.Add('if ($Action -in @("help","")) {')
    $lines.Add('    Write-Host ""')
    $lines.Add('    Write-Host "  Orion Router CLI (Docker Mode)" -ForegroundColor Cyan')
    $lines.Add('    Write-Host "  --------------------------------" -ForegroundColor DarkGray')
    $lines.Add('    Write-Host "  Usage: orionrouter [start|stop|logs|help]" -ForegroundColor Yellow')
    $lines.Add('    Write-Host ""')
    $lines.Add('    Write-Host "  Commands:"')
    $lines.Add('    Write-Host "    start   Starts container in the background"')
    $lines.Add('    Write-Host "    stop    Stops the running container"')
    $lines.Add('    Write-Host "    logs    Shows live container logs"')
    $lines.Add('    Write-Host "    help    Shows this help menu"')
    $lines.Add('    Write-Host ""')
    $lines.Add('} elseif ($Action -eq "start") {')
    $lines.Add('    Write-Host "Checking Docker status..." -ForegroundColor Cyan')
    $lines.Add('    $DockerReady = $false')
    $lines.Add('    try { docker info 2>$null | Out-Null; $DockerReady = $true } catch { $DockerReady = $false }')
    $lines.Add('    if (-not $DockerReady) {')
    $lines.Add('        Write-Host "[!] Docker Daemon not active. Attempting to start Docker Desktop..." -ForegroundColor Yellow')
    $lines.Add('        $dp = "C:\Program Files\Docker\Docker\Docker Desktop.exe"')
    $lines.Add('        if (Test-Path $dp) {')
    $lines.Add('            Start-Process -FilePath $dp')
    $lines.Add('            Write-Host "[*] Docker Desktop triggered. Waiting up to 30 seconds..." -ForegroundColor Cyan')
    $lines.Add('            for ($i = 1; $i -le 6; $i++) {')
    $lines.Add('                Start-Sleep -Seconds 5')
    $lines.Add('                try { docker info 2>$null | Out-Null; $DockerReady = $true; Write-Host "[OK] Docker Engine ready!" -ForegroundColor Green; break }')
    $lines.Add('                catch { $elapsed = $i * 5; Write-Host "    Initializing... ($elapsed seconds elapsed)" -ForegroundColor DarkGray }')
    $lines.Add('            }')
    $lines.Add('        }')
    $lines.Add('        if (-not $DockerReady) {')
    $lines.Add('            Write-Host "[ERROR] Docker could not start. Open Docker Desktop manually and try again." -ForegroundColor Red')
    $lines.Add('            return')
    $lines.Add('        }')
    $lines.Add('    }')
    $lines.Add('    Write-Host "Starting Orion Router on Docker (GHCR Images)..." -ForegroundColor Cyan')
    $lines.Add('    Set-Location $ProjectPath')
    $lines.Add('    docker compose -f $ComposeFile -p orion-router up -d')
    $lines.Add('    Write-Host "Streaming live logs... (Ctrl+C to exit)" -ForegroundColor Magenta')
    $lines.Add('    docker compose -f $ComposeFile -p orion-router logs -f')
    $lines.Add('} elseif ($Action -eq "stop") {')
    $lines.Add('    Write-Host "Stopping Orion Router on Docker..." -ForegroundColor Yellow')
    $lines.Add('    Set-Location $ProjectPath')
    $lines.Add('    docker compose -f $ComposeFile -p orion-router stop')
    $lines.Add('    Write-Host "[OK] Container stopped." -ForegroundColor Green')
    $lines.Add('} elseif ($Action -eq "logs") {')
    $lines.Add('    Set-Location $ProjectPath')
    $lines.Add('    docker compose -f $ComposeFile -p orion-router logs -f')
    $lines.Add('} else { Write-Host "Invalid command. Type: orionrouter help" -ForegroundColor Red }')
    $lines.Add('} finally {')
    $lines.Add('    Set-Location $PreviousLocation')
    $lines.Add('}')
}

$ScriptCode = $lines -join "`r`n"

Write-Host "Creating standalone CLI files..." -ForegroundColor Yellow
[System.IO.File]::WriteAllText((Join-Path $TargetFolder "orionrouter.ps1"), $ScriptCode, (New-Object System.Text.UTF8Encoding $false))

$CmdContent = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0orionrouter.ps1`" %*"
[System.IO.File]::WriteAllText((Join-Path $TargetFolder "orionrouter.cmd"), $CmdContent, (New-Object System.Text.UTF8Encoding $false))

$BashLines = @(
    "#!/usr/bin/env bash",
    'SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"',
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/orionrouter.ps1" "$@"'
)
$BashContent = $BashLines -join "`n"
[System.IO.File]::WriteAllText((Join-Path $TargetFolder "orionrouter"), $BashContent, (New-Object System.Text.UTF8Encoding $false))

# Update PATH
Write-Host "Updating PATH environment variable..." -ForegroundColor Yellow
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$CleanFolder = $TargetFolder.TrimEnd('\')
$PathParts = $UserPath -split ";" | ForEach-Object { $_.Trim().TrimEnd('\') } | Where-Object { $_ }
if ($CleanFolder -notin $PathParts) {
    $NewUserPath = ($PathParts + $CleanFolder) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    Write-Host "[OK] Target directory added to User PATH." -ForegroundColor Green
} else {
    Write-Host "[OK] Target directory already in User PATH." -ForegroundColor Green
}

$CurrentPathParts = $env:Path -split ";" | ForEach-Object { $_.Trim().TrimEnd('\') } | Where-Object { $_ }
if ($CleanFolder -notin $CurrentPathParts) {
    $env:Path = ($CurrentPathParts + $CleanFolder) -join ";"
}

# Clean old profile remains
$ProfileDir = Split-Path $PROFILE
if (-not (Test-Path $ProfileDir)) { New-Item -Type Directory -Path $ProfileDir -Force | Out-Null }
if (-not (Test-Path $PROFILE)) { New-Item -Type File -Path $PROFILE -Force | Out-Null }
$CurrentProfile = Get-Content $PROFILE -Raw
if ($null -eq $CurrentProfile) { $CurrentProfile = "" }
$CurrentProfile = $CurrentProfile -replace "(?s)# --- ORION ROUTER CLI START ---.*?# --- ORION ROUTER CLI END ---`r?`n?", ""
$CurrentProfile = $CurrentProfile -replace "(?m)^orion-?router.*`$", ""
Set-Content -Path $PROFILE -Value $CurrentProfile.Trim()

Write-Host ""
if ($Mode -eq "local") {
    Write-Host "[*] Pre-fetching resources (PostgreSQL) to display live progress..." -ForegroundColor Cyan
    python -c "import sys; sys.path.insert(0, '.'); from bin.prod import download_postgres; download_postgres(); from bin.npm_integrity import record_npm_install; from pathlib import Path; record_npm_install(Path('dashboard'))"
}
Write-Host ""
Write-Host "[OK] Installation complete." -ForegroundColor Green
Write-Host "[OK] 'orionrouter' command is ready in this terminal and new ones." -ForegroundColor Cyan
Write-Host "[OK] Starting Orion Router..." -ForegroundColor Yellow

& (Join-Path $TargetFolder "orionrouter.ps1") start