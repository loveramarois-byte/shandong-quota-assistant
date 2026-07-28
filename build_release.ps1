[CmdletBinding()]
param(
    [switch]$InternalEvaluation,
    [switch]$AuthorizedInternalDistribution,
    [string]$DistributionAuthorizationId,
    [string]$SigningCertificateThumbprint,
    [switch]$PreflightOnly,
    [switch]$SkipArchive,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pyinstaller = Join-Path $projectRoot ".venv\Scripts\pyinstaller.exe"
$sevenZip = Join-Path $projectRoot "tools\7zip\7z.exe"
$innoCompiler = Join-Path $projectRoot "tools\InnoSetup\ISCC.exe"
$catalogManifestPath = Join-Path $projectRoot "manifests\catalog-baseline.json"
$database = Join-Path $projectRoot "data\shandong_quota.sqlite"
$stageRoot = Join-Path $projectRoot "build\release-dist"
$workRoot = Join-Path $projectRoot "build\release-work"
$bundleName = if ($InternalEvaluation) { "山东定额助手-内部评估" } else { "山东定额助手-便携版" }
$releaseRoot = if ($InternalEvaluation) {
    Join-Path $projectRoot "build\internal-evaluation"
} elseif ($AuthorizedInternalDistribution) {
    Join-Path $projectRoot "build\authorized-internal"
} else {
    Join-Path $projectRoot "release"
}
$bundleRoot = Join-Path $releaseRoot $bundleName
$requiresSigning = -not ($InternalEvaluation -or $AuthorizedInternalDistribution)

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Get-HardLinkCount([string]$Path) {
    $links = @(& fsutil hardlink list $Path 2>$null)
    if ($LASTEXITCODE -ne 0 -or $links.Count -eq 0) {
        throw "无法检查硬链接: $Path"
    }
    return @($links | Where-Object { $_.Trim() }).Count
}

function Invoke-CatalogGate([object]$Manifest) {
    $expectedHash = [string]$Manifest.database.sha256
    if (-not $expectedHash) { throw "catalog manifest 缺少数据库 SHA-256" }
    if ((Get-FileSha256 $database) -ne $expectedHash.ToUpperInvariant()) {
        throw "资料库 SHA-256 与 catalog manifest 不一致，拒绝构建"
    }
    $quickCheck = & $python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA quick_check').fetchone()[0]); print(c.execute('PRAGMA user_version').fetchone()[0]); c.close()" $database
    if ($LASTEXITCODE -ne 0 -or $quickCheck.Count -lt 2 -or $quickCheck[0].Trim() -ne "ok") {
        throw "SQLite quick_check 失败，拒绝构建"
    }
    if ([int]$quickCheck[1].Trim() -ne [int]$Manifest.catalog_schema_version) {
        throw "资料库 schema 与 catalog manifest 不兼容，拒绝构建"
    }
}

function Invoke-SourceTests {
    & $python -m unittest discover -s (Join-Path $projectRoot "tests") -v
    if ($LASTEXITCODE -ne 0) { throw "自动测试失败，拒绝构建" }
    & $python -m compileall -q (Join-Path $projectRoot "app") (Join-Path $projectRoot "components") (Join-Path $projectRoot "controllers") (Join-Path $projectRoot "themes") (Join-Path $projectRoot "utils")
    if ($LASTEXITCODE -ne 0) { throw "Python 编译检查失败，拒绝构建" }
}

function Get-SourceRevision {
    try {
        $revision = (& git -C $projectRoot rev-parse HEAD 2>$null).Trim()
        if ($LASTEXITCODE -eq 0 -and $revision) { return $revision }
    } catch { }
    return "UNVERSIONED"
}

function Invoke-CodeSigning([string]$Path) {
    $certificate = Get-ChildItem -Path "Cert:\CurrentUser\My\$SigningCertificateThumbprint" -ErrorAction SilentlyContinue
    if (-not $certificate) { throw "找不到代码签名证书：$SigningCertificateThumbprint" }
    $signature = Set-AuthenticodeSignature -FilePath $Path -Certificate $certificate -TimestampServer "http://timestamp.digicert.com"
    if ($signature.Status -ne "Valid") { throw "代码签名失败：$Path ($($signature.Status))" }
}

foreach ($required in @($python, $pyinstaller, $database, $catalogManifestPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "缺少构建依赖: $required" }
}

$catalogManifest = Get-Content -LiteralPath $catalogManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$appVersion = [string]$catalogManifest.app_version
if ($AuthorizedInternalDistribution) {
    # Keep a running colleague build intact while preparing the next version.
    $releaseRoot = Join-Path $releaseRoot "v$appVersion"
    $bundleRoot = Join-Path $releaseRoot $bundleName
}
$sourceRevision = Get-SourceRevision
if ($InternalEvaluation -and $AuthorizedInternalDistribution) {
    throw "InternalEvaluation 与 AuthorizedInternalDistribution 不能同时使用"
}
if ($InternalEvaluation) {
    if (-not $SkipArchive -or -not $SkipInstaller) {
        throw "内部评估构建不得生成压缩包或安装器；请同时传入 -SkipArchive -SkipInstaller"
    }
} elseif ($AuthorizedInternalDistribution) {
    if (-not $DistributionAuthorizationId.Trim()) {
        throw "授权内部构建需要 DistributionAuthorizationId"
    }
    if (-not [bool]$catalogManifest.database.distribution_authorized) {
        throw "catalog manifest 表明资料库未获分发授权；拒绝生成内部安装包"
    }
    if ([string]$catalogManifest.database.distribution_scope -ne "internal_colleagues_only") {
        throw "资料库授权范围不是 internal_colleagues_only，拒绝生成内部安装包"
    }
} else {
    if (-not $DistributionAuthorizationId.Trim()) { throw "正式发布需要 DistributionAuthorizationId" }
    if (-not [bool]$catalogManifest.database.distribution_authorized) { throw "catalog manifest 表明资料库未获分发授权；拒绝生成正式发布物" }
    if ($sourceRevision -eq "UNVERSIONED") { throw "正式发布需要已冻结的 Git revision" }
    if (-not $SigningCertificateThumbprint.Trim()) { throw "正式发布需要代码签名证书" }
    foreach ($legalFile in @("legal\EULA.md", "legal\PRIVACY.md", "legal\THIRD_PARTY_NOTICES.md")) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $legalFile))) { throw "正式发布缺少必需文件: $legalFile" }
    }
}

Invoke-SourceTests
Invoke-CatalogGate $catalogManifest
if ($PreflightOnly) {
    Write-Host "预检通过：测试、compileall、数据库 SHA-256、quick_check 和 schema 均有效"
    return
}
& $python (Join-Path $projectRoot "tools\build_icon.py")
if ($LASTEXITCODE -ne 0) { throw "应用图标生成失败" }

foreach ($target in @($stageRoot, $workRoot, $bundleRoot)) {
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

$fontFiles = @("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf")
$pyinstallerArgs = @(
    "--noconfirm", "--clean", "--windowed", "--onedir",
    "--name", "山东定额助手",
    "--icon", (Join-Path $projectRoot "assets\images\app.ico"),
    "--version-file", (Join-Path $projectRoot "packaging\windows_version_info.txt"),
    "--distpath", $stageRoot,
    "--workpath", $workRoot,
    "--specpath", $workRoot,
    "--add-data", ((Join-Path $projectRoot "assets\icons") + ";assets\icons"),
    "--add-data", ((Join-Path $projectRoot "assets\animations") + ";assets\animations"),
    "--add-data", ((Join-Path $projectRoot "assets\images\app.ico") + ";assets\images"),
    "--collect-all", "customtkinter"
)
foreach ($font in $fontFiles) { $pyinstallerArgs += @("--add-data", ((Join-Path $projectRoot "assets\fonts\$font") + ";assets\fonts")) }
$pyinstallerArgs += (Join-Path $projectRoot "run.py")

& $pyinstaller @pyinstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }

Move-Item -LiteralPath (Join-Path $stageRoot "山东定额助手") -Destination $bundleRoot
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "data") -Force | Out-Null
$stagedDatabase = Join-Path $bundleRoot "data\shandong_quota.sqlite"
# A release copy must be a new file. Hard links make a shipped database mutate
# when the working catalog changes, so they are categorically forbidden here.
Copy-Item -LiteralPath $database -Destination $stagedDatabase
if ((Get-FileSha256 $stagedDatabase) -ne (Get-FileSha256 $database)) { throw "staging 数据库复制校验失败" }
if ((Get-HardLinkCount $stagedDatabase) -ne 1) { throw "staging 数据库不是独立文件，拒绝构建" }
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "manifests") -Force | Out-Null
Copy-Item -LiteralPath $catalogManifestPath -Destination (Join-Path $bundleRoot "manifests\catalog-baseline.json")
Copy-Item -LiteralPath (Join-Path $projectRoot "使用说明.txt") -Destination $bundleRoot

$evidenceSourceCount = 0
if ($AuthorizedInternalDistribution) {
    $sourceListPath = Join-Path $workRoot "evidence-sources.json"
    & $python -c 'import json,sqlite3,sys; c=sqlite3.connect(sys.argv[1]); p=[r[0] for r in c.execute("select distinct source_path from chunks where source_path is not null and length(source_path)>0 order by source_path")]; c.close(); open(sys.argv[2],"w",encoding="utf-8").write(json.dumps(p,ensure_ascii=False))' $database $sourceListPath
    $registeredSources = @(Get-Content -LiteralPath $sourceListPath -Raw -Encoding UTF8 | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0 -or $registeredSources.Count -eq 0) {
        throw "未能读取原书证据文件清单"
    }
    $sourceBundle = Join-Path $bundleRoot "sources"
    New-Item -ItemType Directory -Path $sourceBundle -Force | Out-Null
    $seenNames = @{}
    foreach ($registeredSource in $registeredSources) {
        $sourcePath = [string]$registeredSource
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "原书证据文件缺失: $sourcePath"
        }
        $name = Split-Path -Leaf $sourcePath
        if ($seenNames.ContainsKey($name.ToLowerInvariant())) {
            throw "原书证据文件重名，不能平铺打包: $name"
        }
        $seenNames[$name.ToLowerInvariant()] = $true
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $sourceBundle $name)
        $evidenceSourceCount += 1
    }
}

$portableExe = Join-Path $bundleRoot "山东定额助手.exe"
if (-not (Test-Path -LiteralPath $portableExe)) { throw "便携版 EXE 未生成" }
if ($requiresSigning) { Invoke-CodeSigning $portableExe }

$releaseNote = @"
山东定额助手 v$($catalogManifest.app_version)

启动：双击“山东定额助手.exe”。
本地检索只可用于已获授权的资料范围内的受控核验。
AI 辅助解释默认关闭；启用前须确认施工描述和本地候选摘要的发送权限。
内部授权安装包包含已登记原书资料，可在候选和 AI 引用中打开对应 PDF 页。
"@
Set-Content -LiteralPath (Join-Path $bundleRoot "发布说明.txt") -Value $releaseNote -Encoding UTF8
if ($InternalEvaluation) {
    Set-Content -LiteralPath (Join-Path $bundleRoot "仅限内部评估.txt") -Value "此构建未获分发授权，不得传输、安装或对外发布。" -Encoding UTF8
} elseif ($AuthorizedInternalDistribution) {
    Set-Content -LiteralPath (Join-Path $bundleRoot "内部授权与签名说明.txt") -Value "授权编号：$DistributionAuthorizationId`r`n授权范围：仅限内部同事使用。`r`n此安装包未进行 Windows 代码签名，首次运行可能显示未知发布者提示。" -Encoding UTF8
}

if (-not $SkipArchive) {
    if (-not (Test-Path -LiteralPath $sevenZip)) { throw "缺少 7-Zip: $sevenZip" }
    $archive = Join-Path $releaseRoot "$bundleName.7z"
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    Push-Location $releaseRoot
    try {
        & $sevenZip a -t7z $archive $bundleName -m0=lzma2 -mx=7 -mmt=on -ms=on "-xr!*.sqlite-shm" "-xr!*.sqlite-wal"
        if ($LASTEXITCODE -ne 0) { throw "便携包压缩失败" }
    } finally { Pop-Location }
}

$expectedInstaller = $null
if (-not $SkipInstaller) {
    if (-not (Test-Path -LiteralPath $innoCompiler)) { throw "缺少 Inno Setup: $innoCompiler" }
    $expectedInstaller = Join-Path $releaseRoot "山东定额助手-Setup-$appVersion.exe"
    if (Test-Path -LiteralPath $expectedInstaller) { Remove-Item -LiteralPath $expectedInstaller -Force }
    $innoDefines = @(
        "/DBuildSourceDir=$bundleRoot",
        "/DBuildOutputDir=$releaseRoot",
        "/DBuildOutputBaseFilename=山东定额助手-Setup-$appVersion"
    )
    & $innoCompiler @innoDefines (Join-Path $projectRoot "packaging\ShandongQuotaAssistant.iss")
    if ($LASTEXITCODE -ne 0) { throw "安装包编译失败" }
    if (-not (Test-Path -LiteralPath $expectedInstaller)) { throw "安装包未生成: $expectedInstaller" }
    if ($requiresSigning) { Invoke-CodeSigning $expectedInstaller }
}

$artifacts = @(
    Get-ChildItem -LiteralPath $bundleRoot -Recurse -File
    if (-not $SkipArchive -and (Test-Path -LiteralPath $archive)) { Get-Item -LiteralPath $archive }
    if ($expectedInstaller -and (Test-Path -LiteralPath $expectedInstaller)) { Get-Item -LiteralPath $expectedInstaller }
) | Sort-Object FullName -Unique
$artifactManifest = @($artifacts | ForEach-Object {
    [ordered]@{ path = $_.FullName.Substring($releaseRoot.Length).TrimStart("\\"); bytes = $_.Length; sha256 = Get-FileSha256 $_.FullName }
})
$releaseManifest = [ordered]@{
    build_type = if ($InternalEvaluation) { "internal_evaluation" } elseif ($AuthorizedInternalDistribution) { "authorized_internal_unsigned" } else { "distribution" }
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    app_version = [string]$catalogManifest.app_version
    source_revision = $sourceRevision
    catalog = [ordered]@{
        build_id = [string]$catalogManifest.catalog_build_id
        schema_version = [int]$catalogManifest.catalog_schema_version
        database_sha256 = Get-FileSha256 $stagedDatabase
        source_database_sha256 = Get-FileSha256 $database
        hardlinks_forbidden = $true
        evidence_source_files = $evidenceSourceCount
    }
    gates = [ordered]@{
        unit_tests = "passed"
        compileall = "passed"
        sqlite_quick_check = "ok"
        schema_compatible = $true
        code_signing = if ($AuthorizedInternalDistribution) { "unsigned_user_accepted" } elseif ($InternalEvaluation) { "not_applicable" } else { "passed" }
    }
    authorization_id = if ($InternalEvaluation) { $null } else { $DistributionAuthorizationId }
    artifacts = $artifactManifest
}
$releaseManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "release-manifest.json") -Encoding UTF8
$hashes = $artifactManifest | ForEach-Object { "$($_.sha256) *$($_.path)" }
Set-Content -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") -Value $hashes -Encoding UTF8

Write-Host "构建完成: $releaseRoot"
Get-ChildItem -LiteralPath $releaseRoot | Select-Object Name, Length, LastWriteTime
