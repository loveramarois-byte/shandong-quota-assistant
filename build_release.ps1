[CmdletBinding()]
param(
    [switch]$InternalEvaluation,
    [switch]$AuthorizedInternalDistribution,
    [switch]$AuthorizedPublicDistribution,
    [switch]$UnsignedReleaseAcknowledged,
    [string]$DistributionAuthorizationId,
    [string]$SigningCertificateThumbprint,
    [switch]$PreflightOnly,
    [switch]$SkipArchive,
    [switch]$SkipInstaller,
    [switch]$IncludeEvidenceSources
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
$bundleName = if ($InternalEvaluation) {
    "山东定额助手-内部评估"
} elseif ($AuthorizedPublicDistribution) {
    "山东定额助手-完整版"
} else {
    "山东定额助手-便携版"
}
$releaseRoot = if ($InternalEvaluation) {
    Join-Path $projectRoot "build\internal-evaluation"
} elseif ($AuthorizedPublicDistribution) {
    Join-Path $projectRoot "build\authorized-public"
} elseif ($AuthorizedInternalDistribution) {
    Join-Path $projectRoot "build\authorized-internal"
} else {
    Join-Path $projectRoot "release"
}
$bundleRoot = Join-Path $releaseRoot $bundleName
$requiresSigning = -not ($InternalEvaluation -or $AuthorizedInternalDistribution -or $AuthorizedPublicDistribution)
$signPublicArtifacts = $AuthorizedPublicDistribution -and -not [string]::IsNullOrWhiteSpace($SigningCertificateThumbprint)
$useCompactCatalog = -not $IncludeEvidenceSources

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
$sourceRevision = Get-SourceRevision
if ($InternalEvaluation -or $AuthorizedInternalDistribution -or $AuthorizedPublicDistribution) {
    # Keep a running colleague build intact while preparing the next version.
    $buildFolder = if ($InternalEvaluation -and $sourceRevision -ne "UNVERSIONED") {
        "v$appVersion-$($sourceRevision.Substring(0, 7))"
    } else {
        "v$appVersion"
    }
    $releaseRoot = Join-Path $releaseRoot $buildFolder
    $bundleRoot = Join-Path $releaseRoot $bundleName
}
if (@($InternalEvaluation, $AuthorizedInternalDistribution, $AuthorizedPublicDistribution).Where({ $_ }).Count -gt 1) {
    throw "InternalEvaluation、AuthorizedInternalDistribution 与 AuthorizedPublicDistribution 只能选择一个"
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
} elseif ($AuthorizedPublicDistribution) {
    if (-not $DistributionAuthorizationId.Trim()) {
        throw "授权公开构建需要 DistributionAuthorizationId"
    }
    if (-not [bool]$catalogManifest.database.distribution_authorized) {
        throw "catalog manifest 表明资料库未获分发授权；拒绝生成公开完整发行版"
    }
    if ([string]$catalogManifest.database.distribution_scope -ne "public_release") {
        throw "资料库授权范围不是 public_release，拒绝生成公开完整发行版"
    }
    if ([string]$catalogManifest.database.authorization_id -ne $DistributionAuthorizationId) {
        throw "DistributionAuthorizationId 与 catalog manifest 不一致"
    }
    if ($sourceRevision -eq "UNVERSIONED") {
        throw "授权公开构建需要已冻结的 Git revision"
    }
    if (-not $UnsignedReleaseAcknowledged -and -not $signPublicArtifacts) {
        throw "未签名公开构建必须显式传入 UnsignedReleaseAcknowledged"
    }
    foreach ($legalFile in @("legal\EULA.md", "legal\PRIVACY.md", "legal\THIRD_PARTY_NOTICES.md", "legal\DATA_NOTICE.md")) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $legalFile))) {
            throw "授权公开构建缺少必需文件: $legalFile"
        }
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

$fontFiles = @(
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "Inter-SemiBold.ttf",
    "Inter-Bold.ttf",
    "NotoSansSC-Regular.otf",
    "SourceHanSerifSC-Regular.otf",
    "SourceHanSerifSC-SemiBold.otf",
    "SourceHanSerifSC-LICENSE.txt",
    "SourceHanSansSC-Regular.otf",
    "SourceHanSansSC-Medium.otf",
    "SourceHanSansSC-LICENSE.txt"
)
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

$stagedApp = Join-Path $stageRoot "山东定额助手"
try {
    Move-Item -LiteralPath $stagedApp -Destination $bundleRoot -ErrorAction Stop
} catch {
    # Windows Defender can briefly hold a freshly-created PyInstaller folder.
    # Copying the completed tree keeps a valid release build instead of
    # leaving the source and the published directory out of sync.
    Write-Warning "移动构建目录失败，改用复制兜底：$($_.Exception.Message)"
    New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $stagedApp '*') -Destination $bundleRoot -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot '山东定额助手.exe'))) {
        throw "构建目录复制兜底失败，未找到主程序: $bundleRoot"
    }
}
# jieba ships optional POS/analyse/LAC data that this app never imports. Keep
# the dictionary used by query_terms, but remove the unused model payload from
# public bundles so the self-contained installer stays within hosting limits.
foreach ($optionalJiebaData in @("analyse", "lac_small", "posseg")) {
    $optionalPath = Join-Path $bundleRoot ("_internal\jieba\" + $optionalJiebaData)
    if (Test-Path -LiteralPath $optionalPath) { Remove-Item -LiteralPath $optionalPath -Recurse -Force }
}
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "data") -Force | Out-Null
$stagedDatabase = Join-Path $bundleRoot "data\shandong_quota.sqlite"
# A release copy must be a new file. Hard links make a shipped database mutate
# when the working catalog changes, so they are categorically forbidden here.
if ($useCompactCatalog) {
    & $python (Join-Path $projectRoot "tools\compact_catalog.py") $database $stagedDatabase
    if ($LASTEXITCODE -ne 0) { throw "紧凑资料库构建失败" }
} else {
    Copy-Item -LiteralPath $database -Destination $stagedDatabase
}
if (-not $useCompactCatalog -and (Get-FileSha256 $stagedDatabase) -ne (Get-FileSha256 $database)) { throw "staging 数据库复制校验失败" }
if ((Get-HardLinkCount $stagedDatabase) -ne 1) { throw "staging 数据库不是独立文件，拒绝构建" }
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "manifests") -Force | Out-Null
Copy-Item -LiteralPath $catalogManifestPath -Destination (Join-Path $bundleRoot "manifests\catalog-baseline.json")
Copy-Item -LiteralPath (Join-Path $projectRoot "使用说明.txt") -Destination $bundleRoot

$evidenceSourceCount = 0
if ($IncludeEvidenceSources -and ($AuthorizedInternalDistribution -or $AuthorizedPublicDistribution)) {
    $sourceListPath = Join-Path $workRoot "evidence-sources.json"
    & $python (Join-Path $projectRoot "tools\write_evidence_sources.py") $database $sourceListPath
    # Windows PowerShell 5 can wrap a JSON array as one nested array when @(...)
    # captures pipeline output. Expand each value explicitly so every source path
    # is validated and copied independently.
    $parsedSources = Get-Content -LiteralPath $sourceListPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $registeredSources = @()
    foreach ($item in $parsedSources) {
        $registeredSources += [string]$item
    }
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

if (Test-Path -LiteralPath (Join-Path $projectRoot "legal")) {
    Copy-Item -LiteralPath (Join-Path $projectRoot "legal") -Destination $bundleRoot -Recurse
}

$portableExe = Join-Path $bundleRoot "山东定额助手.exe"
if (-not (Test-Path -LiteralPath $portableExe)) { throw "便携版 EXE 未生成" }
if ($requiresSigning -or $signPublicArtifacts) { Invoke-CodeSigning $portableExe }

$evidenceLine = if ($IncludeEvidenceSources) { "此构建同时包含已登记原书证据，可在候选和 AI 引用中打开对应 PDF 页。" } else { "此紧凑构建不携带 PDF 原书，原书只作为有争议项目的外部复核资料。" }
$releaseNote = @"
山东定额助手 v$($catalogManifest.app_version)

启动：双击“山东定额助手.exe”。
本地检索只可用于已获授权的资料范围内的受控核验。
AI 辅助解释默认关闭；启用前须确认施工描述和本地候选摘要的发送权限。
结构化资料库已内置，普通套项不需要另装 PDF。
$evidenceLine
"@
Set-Content -LiteralPath (Join-Path $bundleRoot "发布说明.txt") -Value $releaseNote -Encoding UTF8
if ($InternalEvaluation) {
    Set-Content -LiteralPath (Join-Path $bundleRoot "仅限内部评估.txt") -Value "此构建未获分发授权，不得传输、安装或对外发布。" -Encoding UTF8
} elseif ($AuthorizedInternalDistribution) {
    Set-Content -LiteralPath (Join-Path $bundleRoot "内部授权与签名说明.txt") -Value "授权编号：$DistributionAuthorizationId`r`n授权范围：仅限内部同事使用。`r`n此安装包未进行 Windows 代码签名，首次运行可能显示未知发布者提示。" -Encoding UTF8
} elseif ($AuthorizedPublicDistribution) {
    $signatureNote = if ($signPublicArtifacts) { "安装程序和主程序已进行 Windows 代码签名。" } else { "此发行版未进行 Windows 代码签名，首次运行可能显示未知发布者提示。" }
    $dataNote = if ($IncludeEvidenceSources) { "资料范围：山东 2016/2025 定额、2013/2024 清单及已登记原书证据。" } else { "资料范围：山东 2016/2025 定额、2013/2024 清单、清单定额关联和人材机结构化资料；PDF 原书不随紧凑包分发。" }
    Set-Content -LiteralPath (Join-Path $bundleRoot "完整发行版说明.txt") -Value "授权编号：$DistributionAuthorizationId`r`n$dataNote`r`n$signatureNote" -Encoding UTF8
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
    if ($requiresSigning -or $signPublicArtifacts) { Invoke-CodeSigning $expectedInstaller }
}

$artifacts = @(
    Get-ChildItem -LiteralPath $bundleRoot -Recurse -File
    if (-not $SkipArchive -and (Test-Path -LiteralPath $archive)) { Get-Item -LiteralPath $archive }
    if ($expectedInstaller -and (Test-Path -LiteralPath $expectedInstaller)) {
        Get-ChildItem -LiteralPath $releaseRoot -File | Where-Object { $_.BaseName -like "山东定额助手-Setup-$appVersion*" }
    }
) | Sort-Object FullName -Unique
$artifactManifest = @($artifacts | ForEach-Object {
    [ordered]@{ path = $_.FullName.Substring($releaseRoot.Length).TrimStart("\\"); bytes = $_.Length; sha256 = Get-FileSha256 $_.FullName }
})
$releaseManifest = [ordered]@{
    build_type = if ($InternalEvaluation) { "internal_evaluation" } elseif ($AuthorizedInternalDistribution) { "authorized_internal_unsigned" } elseif ($AuthorizedPublicDistribution) { "authorized_public_distribution" } else { "distribution" }
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    app_version = [string]$catalogManifest.app_version
    source_revision = $sourceRevision
    catalog = [ordered]@{
        build_id = [string]$catalogManifest.catalog_build_id
        schema_version = [int]$catalogManifest.catalog_schema_version
        database_sha256 = Get-FileSha256 $stagedDatabase
        source_database_sha256 = Get-FileSha256 $database
        compact_runtime_catalog = $useCompactCatalog
        pdf_content_bundled = -not $useCompactCatalog
        evidence_source_files_bundled = $evidenceSourceCount
        hardlinks_forbidden = $true
        evidence_source_files = $evidenceSourceCount
    }
    gates = [ordered]@{
        unit_tests = "passed"
        compileall = "passed"
        sqlite_quick_check = "ok"
        schema_compatible = $true
        code_signing = if ($AuthorizedInternalDistribution) { "unsigned_user_accepted" } elseif ($AuthorizedPublicDistribution -and -not $signPublicArtifacts) { "unsigned_release_acknowledged" } elseif ($InternalEvaluation) { "not_applicable" } else { "passed" }
    }
    authorization_id = if ($InternalEvaluation) { $null } else { $DistributionAuthorizationId }
    artifacts = $artifactManifest
}
$releaseManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $releaseRoot "release-manifest.json") -Encoding UTF8
$hashes = $artifactManifest | ForEach-Object { "$($_.sha256) *$($_.path)" }
Set-Content -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") -Value $hashes -Encoding UTF8

Write-Host "构建完成: $releaseRoot"
Get-ChildItem -LiteralPath $releaseRoot | Select-Object Name, Length, LastWriteTime
