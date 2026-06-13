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
    Write-Host "Please run the script in the terminal with one of the following parameters:`n" -ForegroundColor Yellow
    Write-Host "  1. Local Installation:" -ForegroundColor White
    Write-Host "     .\install.ps1 local`n" -ForegroundColor Green
    Write-Host "  2. Docker Installation:" -ForegroundColor White
    Write-Host "     .\install.ps1 docker`n" -ForegroundColor Green
    exit 1
}

Write-Host "Installation Mode: $Mode" -ForegroundColor Yellow
$TargetFolder = Join-Path $env:LOCALAPPDATA "OrionRouter"
$RepoUrl = "https://github.com/krstalacam/orion-router.git"
Write-Host "Target Directory:  $TargetFolder`n" -ForegroundColor DarkGray

function Install-FreshCopy {
  param ([string]$Reason)

  Write-Host ""
  Write-Host "[!] $Reason" -ForegroundColor Yellow
  Write-Host "[OK] Installing a fresh copy." -ForegroundColor Yellow

  if (Test-Path $TargetFolder) {
    Set-Location -Path $env:TEMP
    Remove-Item -Path $TargetFolder -Recurse -Force
  }

  git clone $RepoUrl $TargetFolder
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Fresh clone failed." -ForegroundColor Red
    exit $LASTEXITCODE
  }
}

# 1. Requirement Checks
Write-Host "[1/5] Checking system requirements..."
if ($Mode -eq "local") { $requiredCommands = @("git", "python", "npm") } 
else { $requiredCommands = @("git", "docker") }

foreach ($cmd in $requiredCommands) {
  try { Get-Command $cmd -ErrorAction Stop | Out-Null } 
  catch { Write-Error "Error: '$cmd' not found! Please install it and try again."; exit 1 }
}
Write-Host "[OK] Requirements met ($($requiredCommands -join ', ')).`n" -ForegroundColor Green

# 2. Repo Clone or Update
Write-Host "[2/5] Setting up Orion Router AppData directory..."

# Stop old background process to free locked files
$PidFile = Join-Path $TargetFolder ".orion.pid"
if (Test-Path $PidFile) {
  $pidToStop = Get-Content $PidFile
  Start-Process -FilePath "taskkill" -ArgumentList "/F", "/T", "/PID", $pidToStop -NoNewWindow -Wait -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1
  Remove-Item -Path $PidFile -ErrorAction SilentlyContinue
  Write-Host "[!] Stale background Orion Router process terminated." -ForegroundColor DarkGray
}

$GitPath = Join-Path $TargetFolder ".git"
if (-not (Test-Path $TargetFolder) -or -not (Test-Path $GitPath)) {
  Install-FreshCopy "Target directory does not exist or is not a git repository."
} else {
  Write-Host "[OK] Directory exists, forcing updates from GitHub..." -ForegroundColor Yellow
  Set-Location -Path $TargetFolder
  
  git fetch origin main
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] git fetch failed. There might be a connection issue." -ForegroundColor Red
    exit $LASTEXITCODE
  }

  git reset --hard origin/main
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Resetting/updating code failed." -ForegroundColor Red
    exit $LASTEXITCODE
  }
}
Set-Location -Path $TargetFolder
Write-Host ""

# --- Smart .env Check ---
Write-Host "[*] Checking .env file..."
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[OK] .env file not found. Created a new .env file from .env.example to prevent Docker warnings." -ForegroundColor Green
    } else {
        Write-Host "[!] .env.example not found, creating an empty .env file..." -ForegroundColor Yellow
        New-Item -Path ".env" -ItemType File | Out-Null
    }
} else {
    Write-Host "[OK] Existing .env file detected. Kept intact to preserve configurations." -ForegroundColor Green
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
    Write-Host "Docker mode selected; local dependencies will not be installed. Only GHCR images will be pulled.`n" -ForegroundColor DarkGray
}

# 5. Global Command Installation
Write-Host "[5/5] Installing global 'orionrouter' command..." -ForegroundColor Yellow

if ($Mode -eq "local") {
$ScriptCode = @'
param (
    [Parameter(Position=0)][string]$Action = "help"
)

$ProjectPath = "$env:LOCALAPPDATA\OrionRouter"
$PidFile = Join-Path $ProjectPath ".orion.pid"
$LogFile = Join-Path $ProjectPath "orion_output.log"
$ErrorLogFile = Join-Path $ProjectPath "orion_error.log"

if ($Action -in @("help", "")) {
    Write-Host ""
    Write-Host "  Orion Router CLI" -ForegroundColor Cyan
    Write-Host "  --------------------------------" -ForegroundColor DarkGray
    Write-Host "  Usage: " -NoNewline; Write-Host "orionrouter <command>" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Commands:"
    Write-Host "    start   " -NoNewline -ForegroundColor Green; Write-Host "  Starts the server in the background"
    Write-Host "    stop    " -NoNewline -ForegroundColor Red; Write-Host "  Stops the running server and all child processes"
    Write-Host "    logs    " -NoNewline -ForegroundColor Magenta; Write-Host "  Shows background logs and errors"
    Write-Host "    help    " -NoNewline -ForegroundColor Cyan; Write-Host "  Shows this help menu"
    Write-Host ""
}
elseif ($Action -eq "start") {
    if (Test-Path $PidFile) { 
        $pidContent = Get-Content $PidFile
        if (Get-Process -Id $pidContent -ErrorAction SilentlyContinue) {
            Write-Host "[OK] Orion Router is already running in the background!" -ForegroundColor Yellow
            Write-Host "To view logs: orionrouter logs" -ForegroundColor Cyan
            return 
        } else {
            Remove-Item -Path $PidFile -ErrorAction SilentlyContinue
        }
    }

    Write-Host "Starting Orion Router locally..." -ForegroundColor Cyan
    Set-Location $ProjectPath
    
    $process = Start-Process -FilePath "python" -ArgumentList "orion.py", "prod" -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLogFile -PassThru -WindowStyle Hidden
    $process.Id | Out-File -FilePath $PidFile
    
    Write-Host "[OK] Orion Router started running in the background!" -ForegroundColor Green
    Write-Host "[OK] You can now use these commands: orionrouter start | stop | logs | help" -ForegroundColor Cyan
    Write-Host "[OK] You can close this terminal; Orion Router will continue running in the background." -ForegroundColor Cyan
    Write-Host "----------------------------------------------------" -ForegroundColor Gray
    Write-Host "  Streaming live logs... (Press Ctrl+C to exit)" -ForegroundColor Magenta
    Write-Host "----------------------------------------------------" -ForegroundColor Gray
    Get-Content $LogFile -Wait -Tail 10 -Encoding UTF8
}
elseif ($Action -eq "stop") {
    if (Test-Path $PidFile) {
        $pidToStop = Get-Content $PidFile
        try { 
            Start-Process -FilePath "taskkill" -ArgumentList "/F", "/T", "/PID", $pidToStop -NoNewWindow -Wait -ErrorAction SilentlyContinue
            Write-Host "[OK] Orion Router main and child processes stopped." -ForegroundColor Green
        } 
        catch { Write-Host "Error stopping the process, or it has already terminated." -ForegroundColor DarkGray } 
        finally { 
            Remove-Item -Path $PidFile -ErrorAction SilentlyContinue 
        }
    } else {
        Write-Host "No active running Orion Router process (.orion.pid) found." -ForegroundColor Red
    }
}
elseif ($Action -eq "logs") {
    if (Test-Path $ErrorLogFile) {
        $errContent = Get-Content $ErrorLogFile -Tail 15 -ErrorAction SilentlyContinue -Encoding UTF8
        if ($errContent) {
            Write-Host "`n[!] RECENT ERRORS (orion_error.log):" -ForegroundColor Red
            $errContent | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkRed }
            Write-Host "----------------------------------------------------" -ForegroundColor Gray
        }
    }
    if (Test-Path $LogFile) {
        Write-Host "  Streaming live logs... (Press Ctrl+C to exit)" -ForegroundColor Magenta
        Get-Content $LogFile -Wait -Tail 20 -Encoding UTF8
    } else { Write-Host "No log file exists yet." -ForegroundColor Red }
}
else { Write-Host "Invalid command. Type 'orionrouter help' for assistance." -ForegroundColor Red }
'@
} else {
$ScriptCode = @'
param (
    [Parameter(Position=0)][string]$Action = "help"
)

$ProjectPath = "$env:LOCALAPPDATA\OrionRouter"
$ComposeFile = "docker-compose.ghcr.yml"

if ($Action -in @("help", "")) {
    Write-Host ""
    Write-Host "  Orion Router CLI (Docker Mode)" -ForegroundColor Cyan
    Write-Host "  --------------------------------" -ForegroundColor DarkGray
    Write-Host "  Usage: " -NoNewline; Write-Host "orionrouter <command>" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Commands:"
    Write-Host "    start   " -NoNewline -ForegroundColor Green; Write-Host "  Starts container in the background"
    Write-Host "    stop    " -NoNewline -ForegroundColor Red; Write-Host "  Stops the running container"
    Write-Host "    logs    " -NoNewline -ForegroundColor Magenta; Write-Host "  Shows live container logs"
    Write-Host "    help    " -NoNewline -ForegroundColor Cyan; Write-Host "  Shows this help menu"
    Write-Host ""
}
elseif ($Action -eq "start") {
    # --- Smart Docker Daemon Check and Auto-start ---
    Write-Host "Checking Docker status..." -ForegroundColor Cyan
    $DockerReady = $false
    try {
        docker info --format '{{.Name}}' 2>$null | Out-Null
        $DockerReady = $true
    } catch {
        $DockerReady = $false
    }

    if (-not $DockerReady) {
        Write-Host "[!] Docker Daemon is not active. Attempting to start Docker Desktop..." -ForegroundColor Yellow
        $DockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        
        if (Test-Path $DockerDesktopPath) {
            Start-Process -FilePath $DockerDesktopPath
            Write-Host "[*] Docker Desktop triggered. Waiting for Docker Engine to be ready (max 30 seconds)..." -ForegroundColor Cyan
            
            for ($i = 1; $i -le 6; $i++) {
                Start-Sleep -Seconds 5
                try {
                    docker info --format '{{.Name}}' 2>$null | Out-Null
                    $DockerReady = $true
                    Write-Host "[OK] Docker Engine is active and ready!" -ForegroundColor Green
                    break
                } catch {
                    Write-Host "    Initializing... ($($i * 5) seconds elapsed)" -ForegroundColor DarkGray
                }
            }
        }
        
        if (-not $DockerReady) {
            Write-Host "`n[ERROR] Docker Desktop could not be started automatically, or the engine failed to respond in time." -ForegroundColor Red
            Write-Host "Please open Docker Desktop manually, wait for the indicator to turn GREEN, and try again.`n" -ForegroundColor Yellow
            return
        }
    }
    # ----------------------------------------------------------

    Write-Host "Starting Orion Router on Docker (with GHCR Images)..." -ForegroundColor Cyan
    Set-Location $ProjectPath
    docker compose -f $ComposeFile -p orion-router up -d
    Write-Host "[OK] Container started! To stop, type 'orionrouter stop'." -ForegroundColor Green
    Write-Host "[OK] You can now use these commands: orionrouter start | stop | logs | help" -ForegroundColor Cyan
    Write-Host "[OK] You can close this terminal; Orion Router will continue running on Docker in the background." -ForegroundColor Cyan
    Write-Host "----------------------------------------------------" -ForegroundColor Gray
    Write-Host "  Streaming live logs... (Press Ctrl+C to exit)" -ForegroundColor Magenta
    Write-Host "----------------------------------------------------" -ForegroundColor Gray
    docker compose -f $ComposeFile -p orion-router logs -f
}
elseif ($Action -eq "stop") {
    Write-Host "Stopping Orion Router on Docker..." -ForegroundColor Yellow
    Set-Location $ProjectPath
    docker compose -f $ComposeFile -p orion-router stop
    Write-Host "[OK] Container stopped successfully." -ForegroundColor Green
}
elseif ($Action -eq "logs") {
    Set-Location $ProjectPath
    docker compose -f $ComposeFile -p orion-router logs -f
}
else { Write-Host "Invalid command. Type 'orionrouter help' for assistance." -ForegroundColor Red }
'@
}

# Write standalone CLI scripts to target folder
Write-Host "Creating standalone CLI files..." -ForegroundColor Yellow
[System.IO.File]::WriteAllText((Join-Path $TargetFolder "orionrouter.ps1"), $ScriptCode, (New-Object System.Text.UTF8Encoding $false))

$CmdContent = @'
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0orionrouter.ps1" %*
'@
[System.IO.File]::WriteAllText((Join-Path $TargetFolder "orionrouter.cmd"), $CmdContent, (New-Object System.Text.UTF8Encoding $false))

$BashContent = @'
#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/orionrouter.ps1" "$@"
'@
[System.IO.File]::WriteAllText((Join-Path $TargetFolder "orionrouter"), $BashContent, (New-Object System.Text.UTF8Encoding $false))

# Update PATH
Write-Host "Updating PATH environment variable..." -ForegroundColor Yellow
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$CleanFolder = $TargetFolder.TrimEnd('\')
$PathParts = $UserPath -split ";" | ForEach-Object { $_.Trim().TrimEnd('\') } | Where-Object { $_ }
if ($CleanFolder -notin $PathParts) {
    $NewUserPath = ($PathParts + $CleanFolder) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    Write-Host "[OK] Target directory added to User PATH environment variable." -ForegroundColor Green
} else {
    Write-Host "[OK] Target directory is already in User PATH environment variable." -ForegroundColor Green
}

# Update current session path immediately
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

$CurrentProfile = $CurrentProfile -replace "(?s)function .*?Invoke-OrionRouter.*?Set-Alias .*?orion-?router .*?(?:`r?`n|)", ""
$CurrentProfile = $CurrentProfile -replace "(?m)^\s*Invoke-OrionRouter(?:\s+start)?\s*$", ""
$CurrentProfile = $CurrentProfile -replace "(?m)^orion-?router.*$", ""
$CurrentProfile = $CurrentProfile -replace "(?s)# --- ORION ROUTER CLI START ---.*?# --- ORION ROUTER CLI END ---\r?\n?", ""

Set-Content -Path $PROFILE -Value $CurrentProfile.Trim()

Write-Host ""
Write-Host "[OK] Installation complete." -ForegroundColor Green
Write-Host "[OK] 'orionrouter' command is ready in this terminal and new ones (CMD, PowerShell, etc.)." -ForegroundColor Cyan
Write-Host "     Available commands: orionrouter start | stop | logs | help" -ForegroundColor Cyan
Write-Host "     You can close this terminal after starting." -ForegroundColor Cyan
Write-Host "[OK] Starting Orion Router..." -ForegroundColor Green

& (Join-Path $TargetFolder "orionrouter.ps1") start