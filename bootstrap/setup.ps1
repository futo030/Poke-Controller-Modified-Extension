# 初めて起動するときの用意(PokeConExtension.bat から呼ぶ。Python が入っていなくても動く)
#   uv を探す(なければ、尋ねてから公式サイトから入れる) -> 環境(.venv)を作る(Python も uv が取得する)
# 2 回目からは、.venv の Python で bootstrap(Python で書いた方)が動くので、このファイルは使わない。
# uv の探し方は、bootstrap/uv_tool.py と同じ(pip で入れた uv は使わない)。

$root = Split-Path -Parent $PSScriptRoot

function Get-OfficialCandidates {
    $folders = @()
    $receipt = Join-Path $env:LOCALAPPDATA "uv\uv-receipt.json"
    if (Test-Path $receipt) {
        try { $folders += (Get-Content $receipt -Raw -Encoding UTF8 | ConvertFrom-Json).install_prefix } catch {}
    }
    $folders += (Join-Path $env:USERPROFILE ".local\bin")
    $folders | Where-Object { $_ } | Select-Object -Unique | ForEach-Object { Join-Path $_ "uv.exe" }
}

function Test-PipInstalled($path) {
    $folder = Split-Path -Parent $path
    $parent = Split-Path -Parent $folder
    if (@("scripts", "bin") -notcontains (Split-Path -Leaf $folder).ToLower()) { return $false }
    if ((Test-Path (Join-Path $parent "python.exe")) -or (Test-Path (Join-Path $folder "python.exe"))) { return $true }
    if (Test-Path (Join-Path $parent "pyvenv.cfg")) { return $true }
    foreach ($packages in @((Join-Path $parent "site-packages"), (Join-Path $parent "Lib\site-packages"))) {
        if (Test-Path (Join-Path $packages "uv-*.dist-info")) { return $true }
    }
    return $false
}

function Find-Uv {
    foreach ($path in Get-OfficialCandidates) {
        if (Test-Path $path -PathType Leaf) { return $path }
    }
    foreach ($folder in ($env:PATH -split ";")) {
        $folder = $folder.Trim('"')
        if (-not $folder) { continue }
        $path = Join-Path $folder "uv.exe"
        if ((Test-Path $path -PathType Leaf) -and -not (Test-PipInstalled $path)) { return $path }
    }
    return $null
}

$uv = Find-Uv
if (-not $uv) {
    Write-Host "uv (Python と、必要なライブラリを用意する道具) が見つかりません。"
    $answer = Read-Host "公式サイトからダウンロードして、インストールしますか? [y/N]"
    if ($answer -notmatch "^[Yy]") {
        Write-Host "uv がないので、環境を用意できません。"
        exit 1
    }
    Write-Host "uv をインストールしています..."
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $uv = Find-Uv
    if (-not $uv) {
        Write-Host "uv をインストールできませんでした。https://docs.astral.sh/uv/ の手順で入れてから、もう一度実行してください。"
        exit 1
    }
}

# 証明書は、Windows の一覧を使う(ウイルス対策ソフトが HTTPS の通信を調べている PC のため)
if (-not $env:UV_SYSTEM_CERTS) { $env:UV_SYSTEM_CERTS = "1" }
Set-Location $root
Write-Host "Python と、必要なライブラリを用意しています (初回は、数分かかります)..."
& $uv sync --inexact
if ($LASTEXITCODE -ne 0 -and ((Get-OfficialCandidates) -contains $uv)) {
    # uv が古い場合がある: 公式のスクリプトで入れた uv なら、更新してもう一度
    Write-Host "uv を更新して、もう一度試します..."
    & $uv self update
    & $uv sync --inexact
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) {
    Write-Host "環境を用意できませんでした。上に表示された内容を確かめてください。"
    exit 1
}
exit 0
