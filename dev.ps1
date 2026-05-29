# Orion Router - Hybrid Development Environment
$Host.UI.RawUI.WindowTitle = "Orion Router Dev Environment"
Clear-Host

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "   Orion Router - Hybrid Development Environment" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Checks ---
Write-Host "Checking for Node.js (npm)..." -ForegroundColor Yellow
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] npm bulunamadi! https://nodejs.org adresinden Node.js kur." -ForegroundColor Red
    Read-Host "Devam etmek icin Enter'a bas"
    exit 1
}

Write-Host "Checking for Python dependencies (fastapi, uvicorn, asyncpg)..." -ForegroundColor Yellow
python -c "import fastapi, uvicorn, asyncpg" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[INFO] Python bagimliliklari eksik, yukleniyor..." -ForegroundColor Yellow
    python -m pip install -e .
    python -c "import fastapi, uvicorn, asyncpg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Python bagimliliklari yuklenemedi!" -ForegroundColor Red
        Read-Host "Devam etmek icin Enter'a bas"
        exit 1
    }
}
Write-Host "Python dependencies verified." -ForegroundColor Green

# --- 1.5. Stop existing dev compose stack if running ---
Write-Host "" 
Write-Host "Stopping existing dev compose stack (if any)..." -ForegroundColor Yellow
try { docker compose -f docker-compose.dev.yml down 2>$null | Out-Null } catch {}

# --- 1.6. .env yoksa .env.example'dan oluştur ---
python -c "import core.config" 2>$null | Out-Null

# --- 1.7. Dev backend port (.env ROUTER_DEV_PORT, yoksa 20129) ---
$routerPort = "20129"
if (Test-Path ".env") {
    Get-Content ".env" -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match "^([^=]+)=(.*)$") {
            if ($matches[1].Trim() -eq "ROUTER_DEV_PORT") {
                $routerPort = $matches[2].Trim().Trim('"').Trim("'")
            }
        }
    }
}
$env:ROUTER_PORT = $routerPort

# --- 2. Kill processes using our ports ---
Write-Host ""
Write-Host "Freeing ports 3001 and $routerPort if already in use..." -ForegroundColor Yellow
@(3001, [int]$routerPort) | ForEach-Object {
    $port = $_
    $pids = netstat -aon | Select-String ":$port\s" | Select-String "LISTENING" |
        ForEach-Object { ($_ -split '\s+')[-1] } | Select-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$' -and $p -ne '0') {
            try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue; Write-Host "  Killed PID $p (port $port)" -ForegroundColor DarkGray } catch {}
        }
    }
}

# --- 3. npm install if needed ---
if (-not (Test-Path "dashboard\node_modules")) {
    Write-Host ""
    Write-Host "[INFO] node_modules bulunamadi, npm install yapiliyor (sadece bir kez)..." -ForegroundColor Yellow
    Push-Location dashboard
    npm install
    Pop-Location
}

# --- 4. Set environment variables (inherited by all child processes) ---
$env:POSTGRES_HOST     = "localhost"
$env:POSTGRES_PORT     = "5444"
$env:POSTGRES_DB       = "orion_router_dev"
$env:POSTGRES_USER     = "router_user_dev"
$env:POSTGRES_PASSWORD = "router_pass_dev"
$env:BACKEND_URL       = "http://localhost:$routerPort"

# --- 5. Launch all services ---
Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "   Tum sistemler baslatiliyor..." -ForegroundColor Cyan
Write-Host "   Durdurmak icin CTRL+C'ye basin." -ForegroundColor Cyan
Write-Host ""
Write-Host "   Dashboard UI : http://localhost:3001/dashboard" -ForegroundColor White
Write-Host "   Backend API  : http://localhost:$routerPort" -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

$dashboardPath = Join-Path (Get-Location).Path "dashboard"
$processes = @()

# 1) Docker Database
$processes += Start-Process -NoNewWindow -PassThru -FilePath "docker" `
    -ArgumentList "compose","-f","docker-compose.dev.yml","up"

Start-Sleep -Seconds 3  # DB'nin ayaga kalkmasini bekle

# 2) FastAPI Backend (python main.py — port ROUTER_PORT from .env)
$env:UVICORN_RELOAD = "1"
$processes += Start-Process -NoNewWindow -PassThru -FilePath "python" `
    -ArgumentList "main.py"

# 3) Next.js Frontend
$processes += Start-Process -NoNewWindow -PassThru -FilePath "cmd.exe" `
    -ArgumentList "/c","cd /d `"$dashboardPath`" && npm run dev -- -p 3001"

# --- 6. Wait and handle Ctrl+C ---
try {
    Write-Host ""
    Write-Host "Loglar yukarida akmaya baslayacak. CTRL+C ile hepsini kapat." -ForegroundColor DarkGray
    Write-Host ""

    while ($true) {
        $alive = $processes | Where-Object { -not $_.HasExited }
        if ($alive.Count -eq 0) { break }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "Durdurma sinyali alindi, tum servisler kapatiliyor..." -ForegroundColor Red

    foreach ($p in $processes) {
        if (-not $p.HasExited) {
            # Kill the process tree (parent + children)
            try { taskkill /f /t /pid $p.Id 2>$null } catch {}
        }
    }

    # Docker containerlarini da durdur
    docker compose -f docker-compose.dev.yml down 2>$null
    Write-Host "Tum servisler durduruldu." -ForegroundColor Green
}
