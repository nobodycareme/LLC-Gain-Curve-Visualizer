# 生成 LLC 增益曲线 审查包（zip + SHA-256 清单）
# 用法: powershell -ExecutionPolicy Bypass -File scripts\build_review_package.ps1
# 产物: LLC增益曲线_审查包_v<VER>_YYYYMMDD.zip  (项目根目录)
param(
    [string]$Ver = "v6",
    [string]$Date = (Get-Date -Format "yyyyMMdd")
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root   = Split-Path -Parent $PSScriptRoot
$zipName = "LLC增益曲线_审查包_${Ver}_${Date}.zip"
$zipPath = Join-Path $root $zipName
$fold    = "LLC增益曲线_审查包_${Ver}"
$stage   = Join-Path $root "_review_stage"
$stageF  = Join-Path $stage $fold

# 清理旧产物
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stageF -Force | Out-Null

function Copy-Files($src, $dst, $pattern) {
    New-Item -ItemType Directory -Path $dst -Force | Out-Null
    Copy-Item (Join-Path $src $pattern) -Destination $dst -Recurse -Force
}

# ---------- 根目录文档 ----------
foreach ($f in @("LLC_Gain_Curve.spec", "requirements.txt", "README.md",
                "OPTIMIZATION_REPORT.md",
                "LLC工程开发_最终交付报告_20260820.md",
                "LLC工程开发_问题修复与瘦身_交付报告_20260821.md",
                "LLC工程开发_UI重构与预览隔离_交付报告_20260821.md",
                "LLC增益曲线_UI结构收敛_交付报告_20260821.md",
                "LLC增益曲线_曲线主导重构_交付报告_20260821.md",
                "LLC增益曲线_v8修复_交付报告_20260822.md",
                "CHANGELOG.md")) {
    $p = Join-Path $root $f
    if (Test-Path $p) { Copy-Item $p -Destination $stageF -Force }
}

# ---------- src ----------
Copy-Files (Join-Path $root "src") (Join-Path $stageF "src") "*.py"

# ---------- tests ----------
Copy-Files (Join-Path $root "tests") (Join-Path $stageF "tests") "*.py"

# ---------- scripts ----------
$scriptsDst = Join-Path $stageF "scripts"
New-Item -ItemType Directory -Path $scriptsDst -Force | Out-Null
Get-ChildItem (Join-Path $root "scripts") -File | Where-Object {
    $_.Extension -in ".py",".ps1",".bat" -and $_.Name -ne "probe_toc.py"
} | Copy-Item -Destination $scriptsDst -Force

# ---------- dist: onefile + onedir ----------
$distDst = Join-Path $stageF "dist"
New-Item -ItemType Directory -Path $distDst -Force | Out-Null
Get-ChildItem (Join-Path $root "dist") -File -Filter "*.exe" | Copy-Item -Destination $distDst -Force
$onedir = Join-Path $root "dist\LLC增益曲线_onedir"
if (Test-Path $onedir) {
    Copy-Item $onedir -Destination $distDst -Recurse -Force
}

# ---------- review_shots: 验收场景截图 ----------
$shotsDst = Join-Path $stageF "review_shots"
New-Item -ItemType Directory -Path $shotsDst -Force | Out-Null
# 优先使用最新 _accept_v8，回退到 _accept_v7，再回退到 _accept_v6，再回退到 _accept
$acceptDir = Join-Path $root "_accept_v8"
if (-not (Test-Path $acceptDir)) { $acceptDir = Join-Path $root "_accept_v7" }
if (-not (Test-Path $acceptDir)) { $acceptDir = Join-Path $root "_accept_v6" }
if (-not (Test-Path $acceptDir)) { $acceptDir = Join-Path $root "_accept" }
if (Test-Path $acceptDir) {
    Get-ChildItem $acceptDir -File -Filter "*.png" | Copy-Item -Destination $shotsDst -Force
    # 包含 canvas 尺寸测量数据
    Get-ChildItem $acceptDir -File -Filter "*.json" | Copy-Item -Destination $shotsDst -Force
}
# 同时收集 scripts 下的场景截图
Get-ChildItem (Join-Path $root "scripts") -Filter "_sc_*.png" -ErrorAction SilentlyContinue |
    Copy-Item -Destination $shotsDst -Force

# ---------- 生成 SHA-256 清单 ----------
$relList   = Get-ChildItem $stageF -Recurse -File
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("LLC 增益曲线 审查包 SHA-256")
$lines.Add("生成日期: $Date")
$lines.Add("")
foreach ($f in ($relList | Sort-Object FullName)) {
    $rel = $f.FullName.Substring((Join-Path $stageF "").Length).Replace("\","/")
    $h   = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    $lines.Add("$h  $rel")
}
$manifest = Join-Path $stageF "REVIEW_SHA256.txt"
[System.IO.File]::WriteAllLines($manifest, $lines, (New-Object System.Text.UTF8Encoding($false)))

# ---------- 压缩 ----------
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
[System.IO.Compression.ZipFile]::CreateFromDirectory($stage, $zipPath,
    [System.IO.Compression.CompressionLevel]::Optimal, $false)

# 清理临时目录
Remove-Item $stage -Recurse -Force

$info = Get-Item $zipPath
Write-Host ("OK: {0}  ({1} bytes, {2:N2} MB)" -f $zipName, $info.Length, ($info.Length/1MB))
Write-Host ("    文件数(去重后): {0}" -f $relList.Count)