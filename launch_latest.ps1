$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseRoot = Join-Path $projectRoot "build\authorized-public"
$latestExe = $null

if (Test-Path -LiteralPath $releaseRoot) {
    $latestExe = Get-ChildItem -LiteralPath $releaseRoot -Directory -Filter "v*" |
        Sort-Object {
            try { [version]$_.Name.Substring(1) } catch { [version]"0.0" }
        } -Descending |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "山东定额助手-完整版\山东定额助手.exe"
            if (Test-Path -LiteralPath $candidate) {
                Get-Item -LiteralPath $candidate
                break
            }
        }
}

if ($latestExe) {
    Start-Process -FilePath $latestExe.FullName -WorkingDirectory $latestExe.DirectoryName
    exit 0
}

$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$entry = Join-Path $projectRoot "run.py"
$database = Join-Path $projectRoot "data\shandong_quota.sqlite"
if ((Test-Path -LiteralPath $pythonw) -and (Test-Path -LiteralPath $entry) -and (Test-Path -LiteralPath $database)) {
    Start-Process -FilePath $pythonw -ArgumentList @($entry) -WorkingDirectory $projectRoot
    exit 0
}

Add-Type -AssemblyName PresentationFramework
[System.Windows.MessageBox]::Show(
    "未找到可启动的山东定额助手。请先完成一次授权公共版构建。",
    "山东定额助手",
    "OK",
    "Error"
) | Out-Null
exit 1
