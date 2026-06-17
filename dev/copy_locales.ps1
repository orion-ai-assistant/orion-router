# Orion Dashboard - Locales Kopyalama Scripti
# Bu script, dashboard/public/locales klasöründeki tüm dil JSON dosyalarını okur ve panoya (clipboard) kopyalar.
# Kullanım: .\dev\copy_locales.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = $PSScriptRoot
}

# Locales klasörünün dinamik yolunu bul
$LocalesDir = Join-Path (Split-Path $ScriptDir -Parent) "dashboard\public\locales"

$languages = @(
    "ar", "bg", "bn", "cs", "da", "de", "el", "en", "es", "fa", "fi", "fr", "he", "hi",
    "hr", "hu", "id", "it", "ja", "ko", "mr", "ms", "nl", "no", "pl", "pt-BR", "pt-PT",
    "ro", "ru", "sk", "sr", "sv", "sw", "ta", "te", "th", "tl", "tr", "uk", "ur", "vi",
    "zh-CN", "zh-TW"
)

$filePaths = $languages | ForEach-Object { Join-Path $LocalesDir "$_.json" }

$output = foreach ($path in $filePaths) {
    if (Test-Path $path) {
        $fileName = Split-Path $path -Leaf
        
        # Karakterlerin bozulmaması için UTF8 kodlaması kullanılıyor
        $content = Get-Content -Path $path -Raw -Encoding UTF8
        
        "=== $fileName ==="
        $content
        ""
    } else {
        "=== HATA: $path bulunamadı ==="
        ""
    }
}

$output | Out-String | Set-Clipboard
Write-Host "İşlem başarılı! dashboard/public/locales klasöründeki JSON dosyaları panoya kopyalandı." -ForegroundColor Green
