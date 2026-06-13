# Windows Orion Router CLI Uninstaller
# Bu betik, orionrouter CLI aracının sisteminizde bıraktığı ortam değişkenlerini, profil ayarlarını ve standalone dosyaları temizler.

$TargetFolder = Join-Path $env:LOCALAPPDATA "OrionRouter"

Write-Host "Orion Router CLI kalintilari temizleniyor..." -ForegroundColor Yellow

# 1. Standalone dosyaları temizle
$FilesToRemove = @("orionrouter.ps1", "orionrouter.cmd", "orionrouter", "orion-router.ps1", "orion-router.cmd", "orion-router")
foreach ($file in $FilesToRemove) {
    $filePath = Join-Path $TargetFolder $file
    if (Test-Path $filePath) {
        Remove-Item -Path $filePath -Force -ErrorAction SilentlyContinue
        Write-Host "Silindi: $file" -ForegroundColor DarkGray
    }
}

# 2. PATH Ortam Değişkeninden Kaldır (Kullanıcı bazlı)
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$CleanFolder = $TargetFolder.TrimEnd('\')
if ($UserPath) {
    $PathParts = $UserPath -split ";" | ForEach-Object { $_.Trim().TrimEnd('\') } | Where-Object { $_ -and $_ -ne $CleanFolder }
    $NewUserPath = $PathParts -join ";"
    [Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")
    Write-Host "[OK] PATH ortam degiskeninden hedef dizin ($CleanFolder) kaldirildi." -ForegroundColor Green
}

# Mevcut PowerShell oturumunun PATH'ini güncelle (bu pencerede de etkisini yitirmesi için)
$CurrentPathParts = $env:Path -split ";" | ForEach-Object { $_.Trim().TrimEnd('\') } | Where-Object { $_ -and $_ -ne $CleanFolder }
$env:Path = $CurrentPathParts -join ";"

# 3. PowerShell Profilinden Temizle
if (Test-Path $PROFILE) {
    $CurrentProfile = Get-Content $PROFILE -Raw
    if ($CurrentProfile) {
        # Eski ve yeni tüm fonksiyon ve alias kalıntılarını temizle
        $CurrentProfile = $CurrentProfile -replace "(?s)function .*?Invoke-OrionRouter.*?Set-Alias .*?orion-?router .*?(?:`r?`n|)", ""
        $CurrentProfile = $CurrentProfile -replace "(?m)^\s*Invoke-OrionRouter(?:\s+start)?\s*$", ""
        $CurrentProfile = $CurrentProfile -replace "(?m)^orion-?router.*$", ""
        $CurrentProfile = $CurrentProfile -replace "(?s)# --- ORION ROUTER CLI START ---.*?# --- ORION ROUTER CLI END ---\r?\n?", ""
        Set-Content -Path $PROFILE -Value $CurrentProfile.Trim()
        Write-Host "[OK] PowerShell profilinden ($PROFILE) kalintilar temizlendi." -ForegroundColor Green
    }
}

Write-Host "[OK] Temizlik tamamlandi! Değişikliklerin CMD ve yeni PowerShell pencerelerine yansıması için açık olan terminalleri yeniden başlatmanız gerekir." -ForegroundColor Green

"""
Windows üzerinde temizlemek için:

.\dev\uninstall\uninstall.ps1

*********

macOS / Linux üzerinde temizlemek için:

chmod +x ./dev/uninstall/uninstall.sh
./dev/uninstall/uninstall.sh

"""