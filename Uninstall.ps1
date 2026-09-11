[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'CodexSessionHealthHUD'),
    [switch]$NoShortcuts
)

$ErrorActionPreference = 'Stop'
$fullInstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\\')
$marker = Join-Path $fullInstallDir '.install-marker'
$targetExe = Join-Path $fullInstallDir 'CodexSessionHealthHUD.exe'
$programsDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Codex Session Health HUD'
$launcherShortcut = Join-Path $programsDir 'Codex with Session Health HUD.lnk'
$taskbarShortcut = Join-Path $env:APPDATA `
    'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Codex with Session Health HUD.lnk'

if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw "Install marker not found: $marker" }
$markerValue = (Get-Content -LiteralPath $marker -Raw).Trim()
if ($markerValue -ne 'CodexSessionHealthHUD|v1') { throw 'Install marker did not match this application.' }

$driveRoot = [IO.Path]::GetPathRoot($fullInstallDir).TrimEnd('\\')
$userProfile = [IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\\')
$localAppData = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\\')
if ($fullInstallDir -eq $driveRoot -or $fullInstallDir -eq $userProfile -or $fullInstallDir -eq $localAppData) {
    throw "Refusing to modify unsafe path: $fullInstallDir"
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

if (-not $NoShortcuts) {
    foreach ($shortcutPath in @($launcherShortcut, $taskbarShortcut)) {
        if (Test-Path -LiteralPath $shortcutPath) {
            try { Remove-Item -LiteralPath $shortcutPath -Force } catch { }
        }
    }
    if (Test-Path -LiteralPath $programsDir -PathType Container) {
        try {
            if (@(Get-ChildItem -LiteralPath $programsDir -Force).Count -eq 0) {
                Remove-Item -LiteralPath $programsDir -Force
            }
        } catch { }
    }
}

$ownedFiles = @(
    'CodexSessionHealthHUD.exe',
    'Launch-CodexWithSessionHealthHUD.ps1',
    'Uninstall.ps1',
    'README.md',
    'README.ko.md',
    'CHANGELOG.md',
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'Codex.ico',
    'state.json'
)
foreach ($relativePath in $ownedFiles) {
    $path = Join-Path $fullInstallDir $relativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        try { Remove-Item -LiteralPath $path -Force } catch { }
    }
}

foreach ($pattern in @('state.corrupt.*.json', 'state.oversized.*.json', 'state.unsupported.*.json', 'state.json.tmp-*')) {
    Get-ChildItem -LiteralPath $fullInstallDir -File -Filter $pattern -ErrorAction SilentlyContinue |
        ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Force } catch { } }
}

$assetPath = Join-Path $fullInstallDir 'assets\\hud-composer.svg'
if (Test-Path -LiteralPath $assetPath -PathType Leaf) {
    try { Remove-Item -LiteralPath $assetPath -Force } catch { }
}
$assetsDir = Join-Path $fullInstallDir 'assets'
if (Test-Path -LiteralPath $assetsDir -PathType Container) {
    try {
        if (@(Get-ChildItem -LiteralPath $assetsDir -Force).Count -eq 0) {
            Remove-Item -LiteralPath $assetsDir -Force
        }
    } catch { }
}

# Remove the ownership marker last, and only after known HUD files are gone.
# If cleanup was incomplete, keep the marker so uninstall can be retried safely.
$remainingOwned = @()
foreach ($relativePath in $ownedFiles) {
    if (Test-Path -LiteralPath (Join-Path $fullInstallDir $relativePath) -PathType Leaf) {
        $remainingOwned += $relativePath
    }
}
if (Test-Path -LiteralPath $assetPath -PathType Leaf) { $remainingOwned += 'assets\hud-composer.svg' }
if ($remainingOwned.Count -gt 0) {
    throw ('Could not remove all HUD-owned files: ' + ($remainingOwned -join ', '))
}
if (Test-Path -LiteralPath $marker -PathType Leaf) {
    Remove-Item -LiteralPath $marker -Force
}

try {
    $currentDirectory = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\\')
    if ($currentDirectory.StartsWith($fullInstallDir + '\\', [StringComparison]::OrdinalIgnoreCase) -or
        $currentDirectory -eq $fullInstallDir) {
        Set-Location -LiteralPath ([IO.Path]::GetTempPath())
    }
} catch { }

if (Test-Path -LiteralPath $fullInstallDir -PathType Container) {
    try {
        if (@(Get-ChildItem -LiteralPath $fullInstallDir -Force).Count -eq 0) {
            Remove-Item -LiteralPath $fullInstallDir -Force
        }
    } catch { }
}

Write-Host 'Codex Session Health HUD files and state were removed. Codex data and unrelated files were not modified.'
