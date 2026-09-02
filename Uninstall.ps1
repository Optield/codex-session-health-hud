[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'CodexSessionHealthHUD')
)

$ErrorActionPreference = 'Stop'
$fullInstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$marker = Join-Path $fullInstallDir '.install-marker'
$targetExe = Join-Path $fullInstallDir 'CodexSessionHealthHUD.exe'
$programsDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Codex Session Health HUD'
$launcherShortcut = Join-Path $programsDir 'Codex with Session Health HUD.lnk'
$taskbarShortcut = Join-Path $env:APPDATA `
    'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Codex with Session Health HUD.lnk'

if (-not (Test-Path -LiteralPath $marker)) { throw "Install marker not found: $marker" }
$markerValue = (Get-Content -LiteralPath $marker -Raw).Trim()
if ($markerValue -ne 'CodexSessionHealthHUD|v1') { throw 'Install marker did not match this application.' }

$driveRoot = [IO.Path]::GetPathRoot($fullInstallDir).TrimEnd('\')
$userProfile = [IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\')
$localAppData = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')
if ($fullInstallDir -eq $driveRoot -or $fullInstallDir -eq $userProfile -or $fullInstallDir -eq $localAppData) {
    throw "Refusing to recursively remove unsafe path: $fullInstallDir"
}

Get-CimInstance Win32_Process -Filter "Name='CodexSessionHealthHUD.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object {
        try {
            if ($_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($targetExe)) {
                Stop-Process -Id $_.ProcessId -Force
                Wait-Process -Id $_.ProcessId -Timeout 3 -ErrorAction SilentlyContinue
            }
        } catch { }
    }

foreach ($shortcutPath in @($launcherShortcut, $taskbarShortcut)) {
    if (Test-Path -LiteralPath $shortcutPath) {
        try { Remove-Item -LiteralPath $shortcutPath -Force } catch { }
    }
}
if (Test-Path -LiteralPath $programsDir) {
    try { Remove-Item -LiteralPath $programsDir -Recurse -Force } catch { }
}

try {
    $currentDirectory = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\')
    if ($currentDirectory.StartsWith($fullInstallDir, [StringComparison]::OrdinalIgnoreCase)) {
        Set-Location -LiteralPath ([IO.Path]::GetTempPath())
    }
} catch { }

Remove-Item -LiteralPath $fullInstallDir -Recurse -Force
Write-Host 'Codex Session Health HUD was removed, including its state directory. Codex data was not modified.'
