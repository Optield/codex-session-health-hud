[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $projectDir 'Install.ps1'
$uninstaller = Join-Path $projectDir 'Uninstall.ps1'
$exe = Join-Path $projectDir 'CodexSessionHealthHUD.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw 'Build CodexSessionHealthHUD.exe before running install safety tests.'
}

$root = Join-Path ([IO.Path]::GetTempPath()) ('CodexSessionHealthHUD-install-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
try {
    # Non-empty, unmarked custom directories must be rejected before any copy.
    $unsafe = Join-Path $root 'unowned'
    New-Item -ItemType Directory -Path $unsafe -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $unsafe 'sentinel.txt') -Value 'keep' -Encoding ASCII
    $rejected = $false
    try {
        & $installer -InstallDir $unsafe -NoStartMenu
    } catch {
        $rejected = $true
    }
    if (-not $rejected) { throw 'Installer accepted a non-empty unmarked custom InstallDir.' }
    if (-not (Test-Path -LiteralPath (Join-Path $unsafe 'sentinel.txt'))) {
        throw 'Installer modified unrelated content in a rejected custom InstallDir.'
    }

    # Legacy/custom marked installs remove only known HUD files, preserving unrelated files.
    $legacy = Join-Path $root 'legacy-custom'
    New-Item -ItemType Directory -Path (Join-Path $legacy 'assets') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $legacy '.install-marker') -Value 'CodexSessionHealthHUD|v1' -Encoding ASCII
    foreach ($name in @('CodexSessionHealthHUD.exe', 'README.md', 'state.json')) {
        Set-Content -LiteralPath (Join-Path $legacy $name) -Value 'owned' -Encoding ASCII
    }
    Set-Content -LiteralPath (Join-Path $legacy 'assets\hud-composer.svg') -Value 'owned' -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $legacy 'sentinel.txt') -Value 'keep' -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $legacy 'assets\sentinel.bin') -Value 'keep' -Encoding ASCII

    & $uninstaller -InstallDir $legacy -NoShortcuts
    if (-not (Test-Path -LiteralPath (Join-Path $legacy 'sentinel.txt'))) {
        throw 'Uninstaller deleted an unrelated root file.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $legacy 'assets\sentinel.bin'))) {
        throw 'Uninstaller deleted an unrelated asset file.'
    }
    foreach ($owned in @('.install-marker', 'CodexSessionHealthHUD.exe', 'README.md', 'state.json', 'assets\hud-composer.svg')) {
        if (Test-Path -LiteralPath (Join-Path $legacy $owned)) {
            throw "Uninstaller left an owned file behind: $owned"
        }
    }
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'install safety: ok'
