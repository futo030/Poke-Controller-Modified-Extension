@echo off
rem Poke-Controller Modified Extension installer (this single file is all you need; Python and git are not required).
rem   It downloads the latest release into a folder you choose, then starts PokeConExtension.bat,
rem   which prepares Python and the libraries with uv.
rem The rest of this file (after the marker line) is a PowerShell script written in UTF-8.
set "POKECON_INSTALLER=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = Get-Content -LiteralPath $env:POKECON_INSTALLER -Raw -Encoding UTF8; Invoke-Expression $s.Substring($s.IndexOf('#PS' + '1-BEGIN'))"
pause & exit /b
#PS1-BEGIN
# ここから下は PowerShell。上の powershell の行が、このファイルの目印の行より後ろを読み込んで実行する。
# 確認用の環境変数(ふつうは使わない):
#   POKECON_INSTALL_DIR      導入先のフォルダー(尋ねない)
#   POKECON_INSTALL_ZIP      取得する ZIP の URL、または手元の ZIP のファイル(最新の Release を調べない)
#   POKECON_INSTALL_NO_START 1 にすると、導入の後に起動するかを尋ねない
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repository = "futo030/Poke-Controller-Modified-Extension"
$folderName = "Poke-Controller-Modified-Extension"

function Stop-Install($message) {
    Write-Host ""
    Write-Host $message
    exit 1
}

Write-Host "Poke-Controller Modified Extension をインストールします。"
Write-Host "(Python と git は不要です。初回の起動のときに、uv が Python と必要なライブラリを用意します)"
Write-Host ""

# 1. 導入先
$target = $env:POKECON_INSTALL_DIR
if (-not $target) {
    $default = Join-Path (Split-Path -Parent $env:POKECON_INSTALLER) $folderName
    Write-Host "インストール先のフォルダーを入力してください(何も入力せずに Enter を押すと、次の場所になります)。"
    Write-Host "  $default"
    $target = Read-Host ">"
    if (-not $target) { $target = $default }
}
$target = [IO.Path]::GetFullPath($target)
if ((Test-Path $target) -and (Get-ChildItem -LiteralPath $target -Force | Select-Object -First 1)) {
    Stop-Install "フォルダーが空ではありません: $target`n別の場所を指定するか、フォルダーを空にしてから、もう一度実行してください。"
}
if ($target.Length -gt 100) {
    Write-Host "注意: フォルダーの場所が長いと、音声のライブラリを読み込めないことがあります。短い場所をおすすめします。"
}

# 2. 取得する ZIP(最新の Release)
$zipSource = $env:POKECON_INSTALL_ZIP
if (-not $zipSource) {
    Write-Host "最新の版を調べています..."
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$repository/releases/latest" -Headers @{ "User-Agent" = $folderName } -TimeoutSec 30
    } catch {
        Stop-Install "最新の版を調べられませんでした: $($_.Exception.Message)`nhttps://github.com/$repository/releases から、ZIP をダウンロードしてください。"
    }
    Write-Host "  $($release.tag_name)"
    $zipSource = "https://github.com/$repository/archive/refs/tags/$($release.tag_name).zip"
}

# 3. ダウンロードして、展開する
$work = Join-Path ([IO.Path]::GetTempPath()) ("pokecon_install_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $zip = Join-Path $work "source.zip"
    if (Test-Path -LiteralPath $zipSource -PathType Leaf) {
        Copy-Item -LiteralPath $zipSource -Destination $zip
    } else {
        Write-Host "ダウンロードしています..."
        try {
            Invoke-WebRequest -Uri $zipSource -OutFile $zip -UseBasicParsing -Headers @{ "User-Agent" = $folderName }
        } catch {
            Stop-Install "ダウンロードできませんでした: $($_.Exception.Message)"
        }
    }
    Write-Host "展開しています..."
    Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $work "source")
    $tops = @(Get-ChildItem -LiteralPath (Join-Path $work "source") -Directory)
    if ($tops.Count -ne 1 -or -not (Test-Path (Join-Path $tops[0].FullName "PokeConExtension.bat"))) {
        Stop-Install "ZIP の中身が、想定した形ではありません(PokeConExtension.bat が見つかりません)。"
    }
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Get-ChildItem -LiteralPath $tops[0].FullName -Force | Move-Item -Destination $target
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "インストールしました: $target"
Write-Host "起動するには、このフォルダーの PokeConExtension.bat を実行してください。"
Write-Host "(初回は、Python と必要なライブラリを用意するので、数分かかります)"
if ($env:POKECON_INSTALL_NO_START -ne "1") {
    $answer = Read-Host "このまま起動しますか? [y/N]"
    if ($answer -match "^[Yy]") {
        Start-Process -FilePath (Join-Path $target "PokeConExtension.bat") -WorkingDirectory $target
    }
}
exit 0
