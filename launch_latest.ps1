$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$releaseRoot = Join-Path $projectRoot "build\authorized-public"
$latestExe = $null

if (Test-Path -LiteralPath $releaseRoot) {
    $releaseDirectories = Get-ChildItem -LiteralPath $releaseRoot -Directory -Filter "v*" |
        Sort-Object {
            try { [version]$_.Name.Substring(1) } catch { [version]"0.0" }
        } -Descending
    foreach ($releaseDirectory in $releaseDirectories) {
        $candidate = Get-ChildItem -LiteralPath $releaseDirectory.FullName -Recurse -File -Filter "*.exe" |
            Where-Object {
                $_.Name -notlike "*Setup*" -and
                $_.DirectoryName -notmatch "\\_internal(?:\\|$)"
            } |
            Select-Object -First 1
        if ($candidate) {
            $latestExe = $candidate
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
    "No runnable Shandong Quota Assistant release was found.",
    "Shandong Quota Assistant",
    "OK",
    "Error"
) | Out-Null
exit 1
