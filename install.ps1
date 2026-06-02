param (
    [string]$Mode = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "    Orion Router Native Kurulum Araci    " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

if ($Mode -notin @("local", "docker")) {
    Write-Host "`nHATA: Kurulum modunu belirtmediniz!" -ForegroundColor Red
    Write-Host "Lutfen terminalde scripti asagidaki gibi parametre vererek calistirin:`n" -ForegroundColor Yellow
    Write-Host "  1. Local Kurulum:" -ForegroundColor White
    Write-Host "     . .\install.ps1 local`n" -ForegroundColor Green
    Write-Host "  2. Docker Kurulum:" -ForegroundColor White
    Write-Host "     . .\install.ps1 docker`n" -ForegroundColor Green
    exit 1
}

Write-Host "Kurulum Modu: $Mode" -ForegroundColor Yellow
$TargetFolder = Join-Path $env:LOCALAPPDATA "OrionRouter"
Write-Host "Hedef Dizin:  $TargetFolder`n" -ForegroundColor DarkGray

# 1. Gereksinim Kontrolleri
Write-Host "[1/5] Sistem gereksinimleri kontrol ediliyor..."
if ($Mode -eq "local") { $requiredCommands = @("git", "python", "npm") } 
else { $requiredCommands = @("git", "docker") }

foreach ($cmd in $requiredCommands) {
  try { Get-Command $cmd -ErrorAction Stop | Out-Null } 
  catch { Write-Error "Hata: '$cmd' bulunamadi! Lutfen kurup tekrar deneyin."; exit 1 }
}
Write-Host "[OK] Gereksinimler karsilandi ($($requiredCommands -join ', ')).`n" -ForegroundColor Green

# 2. Repo Klonlama veya Guncelleme
Write-Host "[2/5] Orion Router AppData klasorune ayarlaniyor..."
$GitPath = Join-Path $TargetFolder ".git"
if (-not (Test-Path $TargetFolder) -or -not (Test-Path $GitPath)) {
  if (Test-Path $TargetFolder) { Remove-Item -Path $TargetFolder -Recurse -Force -ErrorAction SilentlyContinue }
  git clone https://github.com/krstalacam/orion-router.git $TargetFolder
} else {
  Write-Host "[OK] Klasor var, en guncel kodlar cekiliyor (git pull)..." -ForegroundColor Yellow
  Set-Location -Path $TargetFolder
  git pull
}
Set-Location -Path $TargetFolder
Write-Host ""

# 3 & 4. Bagimliliklar
if ($Mode -eq "local") {
    Write-Host "[3/5] Python paketleri (pip) yukleniyor..."
    python -m pip install -e .
    Write-Host "`n[4/5] Dashboard bagimliliklari (NPM) yukleniyor..."
    if (Test-Path "dashboard") { Set-Location -Path "dashboard"; npm install; Set-Location -Path ".." }
    Write-Host ""
} else {
    Write-Host "[3/5] ve [4/5] Adimlari Atlaniyor..." -ForegroundColor DarkGray
    Write-Host "Docker modu secildigi icin local bagimliliklar indirilmeyecek.`n" -ForegroundColor DarkGray
}

# 5. Global Komutun Yuklenmesi
Write-Host "[5/5] Global 'orion-router' komutu sisteme yukleniyor..."

if ($Mode -eq "local") {
$ProfileCode = @"
function Global:Invoke-OrionRouter {
    param ([Parameter(Position=0)][string]`$Action = "help")
    `$ProjectPath = "`$env:LOCALAPPDATA\OrionRouter"
    `$PidFile = Join-Path `$ProjectPath ".orion.pid"
    `$LogFile = Join-Path `$ProjectPath "orion_output.log"
    `$ErrorLogFile = Join-Path `$ProjectPath "orion_error.log"

    if (`$Action -in @("help", "")) {
        Write-Host ""
        Write-Host "  Orion Router CLI" -ForegroundColor Cyan
        Write-Host "  --------------------------------" -ForegroundColor DarkGray
        Write-Host "  Kullanim: " -NoNewline; Write-Host "orion-router <komut>" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Komutlar:"
        Write-Host "    start   " -NoNewline -ForegroundColor Green; Write-Host "  Sunucuyu arka planda baslatir"
        Write-Host "    stop    " -NoNewline -ForegroundColor Red; Write-Host "  Calisan sunucuyu ve tum alt surecleri durdurur"
        Write-Host "    logs    " -NoNewline -ForegroundColor Magenta; Write-Host "  Arka plan loglarini ve hatalari gosterir"
        Write-Host "    help    " -NoNewline -ForegroundColor Cyan; Write-Host "  Bu yardim menusunu gosterir"
        Write-Host ""
    }
    elseif (`$Action -eq "start") {
        if (Test-Path `$PidFile) { 
            `$pidContent = Get-Content `$PidFile
            if (Get-Process -Id `$pidContent -ErrorAction SilentlyContinue) {
                Write-Host "[OK] Orion Router zaten arka planda calisiyor!" -ForegroundColor Yellow
                Write-Host "Loglari gormek icin: orion-router logs" -ForegroundColor Cyan
                return 
            } else {
                Remove-Item -Path `$PidFile -ErrorAction SilentlyContinue
            }
        }

        Write-Host "Orion Router local olarak baslatiliyor..." -ForegroundColor Cyan
        Set-Location `$ProjectPath
        
        `$process = Start-Process -FilePath "python" -ArgumentList "orion.py", "prod" -RedirectStandardOutput `$LogFile -RedirectStandardError `$ErrorLogFile -PassThru -WindowStyle Hidden
        `$process.Id | Out-File -FilePath `$PidFile
        
        Write-Host "[OK] Orion Router arka planda calismaya basladi!" -ForegroundColor Green
        Write-Host "[OK] Artik su komutlari kullanabilirsiniz: orion-router start | stop | logs | help" -ForegroundColor Cyan
        Write-Host "[OK] Bu terminali kapatabilirsiniz; Orion Router arka planda calismaya devam eder." -ForegroundColor Cyan
        Write-Host "----------------------------------------------------" -ForegroundColor Gray
        Write-Host "  Canli loglar basliyor... (Cikmak icin Ctrl+C basabilirsiniz)" -ForegroundColor Magenta
        Write-Host "----------------------------------------------------" -ForegroundColor Gray
        Get-Content `$LogFile -Wait -Tail 10 -Encoding UTF8
    }
    elseif (`$Action -eq "stop") {
        if (Test-Path `$PidFile) {
            `$pidToStop = Get-Content `$PidFile
            try { 
                # /F zorla, /T agac yapisiyla tum alt surecleri temizler.
                taskkill /F /T /PID `$pidToStop | Out-Null
                Write-Host "[OK] Orion Router ana sureci ve bagli alt surecleri sonlandirildi." -ForegroundColor Green
            } 
            catch { Write-Host "Surec durdurulurken bir hata oldu veya zaten sonlanmis." -ForegroundColor DarkGray } 
            finally { 
                Remove-Item -Path `$PidFile -ErrorAction SilentlyContinue 
            }
        } else {
            Write-Host "Calisan etkin bir Orion Router sureci (.orion.pid) bulunamadi." -ForegroundColor Red
        }
    }
    elseif (`$Action -eq "logs") {
        if (Test-Path `$ErrorLogFile) {
            `$errContent = Get-Content `$ErrorLogFile -Tail 15 -ErrorAction SilentlyContinue -Encoding UTF8
            if (`$errContent) {
                Write-Host "`n[!] SON HATALAR (orion_error.log):" -ForegroundColor Red
                `$errContent | ForEach-Object { Write-Host "  `$_" -ForegroundColor DarkRed }
                Write-Host "----------------------------------------------------" -ForegroundColor Gray
            }
        }
        if (Test-Path `$LogFile) {
            Write-Host "  Canli loglar basliyor... (Cikmak icin Ctrl+C basabilirsiniz)" -ForegroundColor Magenta
            Get-Content `$LogFile -Wait -Tail 20 -Encoding UTF8
        } else { Write-Host "Henuz bir log dosyasi yok." -ForegroundColor Red }
    }
    else { Write-Host "Gecersiz komut. Yardim icin 'orion-router' yazabilirsiniz." -ForegroundColor Red }
}
"@
} else {
$ProfileCode = @"
function Global:Invoke-OrionRouter {
    param ([Parameter(Position=0)][string]`$Action = "help")
    `$ProjectPath = "`$env:LOCALAPPDATA\OrionRouter"

    if (`$Action -in @("help", "")) {
        Write-Host ""
        Write-Host "  Orion Router CLI (Docker Mode)" -ForegroundColor Cyan
        Write-Host "  --------------------------------" -ForegroundColor DarkGray
        Write-Host "  Kullanim: " -NoNewline; Write-Host "orion-router <komut>" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Komutlar:"
        Write-Host "    start   " -NoNewline -ForegroundColor Green; Write-Host "  Container'i arka planda baslatir"
        Write-Host "    stop    " -NoNewline -ForegroundColor Red; Write-Host "  Calisan container'i durdurur"
        Write-Host "    logs    " -NoNewline -ForegroundColor Magenta; Write-Host "  Container loglarini canli olarak gosterir"
        Write-Host "    help    " -NoNewline -ForegroundColor Cyan; Write-Host "  Bu yardim menusunu gosterir"
        Write-Host ""
    }
    elseif (`$Action -eq "start") {
        Write-Host "Orion Router Docker uzerinde baslatiliyor..." -ForegroundColor Cyan
        Set-Location `$ProjectPath
        docker compose -p orion-router up -d
        Write-Host "[OK] Container basladi! Kapatmak icin 'orion-router stop' yazabilirsiniz." -ForegroundColor Green
        Write-Host "[OK] Artik su komutlari kullanabilirsiniz: orion-router start | stop | logs | help" -ForegroundColor Cyan
        Write-Host "[OK] Bu terminali kapatabilirsiniz; Orion Router Docker'da arka planda calismaya devam eder." -ForegroundColor Cyan
        Write-Host "----------------------------------------------------" -ForegroundColor Gray
        Write-Host "  Canli loglar basliyor... (Cikmak icin Ctrl+C basabilirsiniz)" -ForegroundColor Magenta
        Write-Host "----------------------------------------------------" -ForegroundColor Gray
        docker compose -p orion-router logs -f
    }
    elseif (`$Action -eq "stop") {
        Write-Host "Orion Router Docker uzerinde durduruluyor..." -ForegroundColor Yellow
        Set-Location `$ProjectPath
        docker compose -p orion-router stop
        Write-Host "[OK] Container basariyla durduruldu." -ForegroundColor Green
    }
    elseif (`$Action -eq "logs") {
        Set-Location `$ProjectPath
        docker compose -p orion-router logs -f
    }
    else { Write-Host "Gecersiz komut. Yardim icin 'orion-router' yazabilirsiniz." -ForegroundColor Red }
}
"@
}

# Güvenli Profil Yönetimi (Marker Tabanlı)
$ProfileDir = Split-Path $PROFILE
if (-not (Test-Path $ProfileDir)) { New-Item -Type Directory -Path $ProfileDir -Force | Out-Null }
if (-not (Test-Path $PROFILE)) { New-Item -Type File -Path $PROFILE -Force | Out-Null }

$CurrentProfile = Get-Content $PROFILE -Raw
if ($null -eq $CurrentProfile) { $CurrentProfile = "" }

# Eski kirli kalintilari temizle
$CurrentProfile = $CurrentProfile -replace "(?s)function .*?Invoke-OrionRouter.*?Set-Alias .*?orion-router .*?(?:`r?`n|)", ""
$CurrentProfile = $CurrentProfile -replace "(?m)^\s*Invoke-OrionRouter(?:\s+start)?\s*$", ""
$CurrentProfile = $CurrentProfile -replace "(?m)^orion-router.*$", ""
$CurrentProfile = $CurrentProfile -replace "(?s)# --- ORION ROUTER CLI START ---.*?# --- ORION ROUTER CLI END ---\r?\n?", ""

$MarkerBlock = @"
# --- ORION ROUTER CLI START ---
$ProfileCode
Set-Alias -Scope Global orion-router Invoke-OrionRouter
# --- ORION ROUTER CLI END ---
"@

$CurrentProfile = $CurrentProfile.Trim() + "`n`n" + $MarkerBlock
Set-Content -Path $PROFILE -Value $CurrentProfile.Trim()

# Yeni kodu mevcut oturuma zorla besle
Invoke-Expression $MarkerBlock

Write-Host ""
Write-Host "[OK] Kurulum tamamlandi." -ForegroundColor Green
Write-Host "[OK] 'orion-router' komutu bu terminalde ve yeni terminallerde hazir." -ForegroundColor Cyan
Write-Host "     Kullanabileceginiz komutlar: orion-router start | stop | logs | help" -ForegroundColor Cyan
Write-Host "     Baslattiktan sonra bu terminali kapatabilirsiniz." -ForegroundColor Cyan
Write-Host "[OK] Orion Router baslatiliyor..." -ForegroundColor Green

Invoke-OrionRouter start
