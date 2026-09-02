[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$PackagePath
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
    throw "Package was not found: $PackagePath"
}

$stage = Join-Path ([IO.Path]::GetTempPath()) ("CodexSessionHealthHUD-package-test-{0}" -f [Guid]::NewGuid())
New-Item -ItemType Directory -Path $stage -Force | Out-Null

try {
    Expand-Archive -LiteralPath $PackagePath -DestinationPath $stage -Force

    $required = @(
        'CodexSessionHealthHUD.exe',
        'Install-Easy.bat',
        'Install.ps1',
        'Launch-CodexWithSessionHealthHUD.ps1',
        'Uninstall.ps1',
        'README.md',
        'README.ko.md',
        'assets\hud-composer.svg'
    )

    foreach ($relativePath in $required) {
        $path = Join-Path $stage $relativePath
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Package is missing required file: $relativePath"
        }
    }

    $easyInstaller = Get-Content -LiteralPath (Join-Path $stage 'Install-Easy.bat') -Raw
    foreach ($forbidden in @(
        '-EncodedCommand',
        'Invoke-WebRequest',
        'Start-BitsTransfer',
        'bitsadmin',
        'curl.exe',
        'Add-MpPreference',
        'Set-MpPreference'
    )) {
        if ($easyInstaller.IndexOf($forbidden, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "Install-Easy.bat contains forbidden pattern: $forbidden"
        }
    }
    if ($easyInstaller.IndexOf('Install.ps1', [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw 'Install-Easy.bat does not invoke the bundled Install.ps1.'
    }

    $launcher = Get-Content -LiteralPath (Join-Path $stage 'Launch-CodexWithSessionHealthHUD.ps1') -Raw
    if ($launcher.IndexOf('GetDirectoryName($PSCommandPath)', [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer contains the safe InstallDir fallback.'
    }
    if ($launcher -match '\[string\]\$InstallDir\s*=\s*\(\s*Join-Path\s+\$PSScriptRoot') {
        throw 'Launcher regressed to evaluating $PSScriptRoot in a parameter default.'
    }

    $installer = Get-Content -LiteralPath (Join-Path $stage 'Install.ps1') -Raw
    if ($installer -notmatch '\$shortcut\.Arguments\s*=.*-InstallDir') {
        throw 'Start menu shortcut does not pass InstallDir explicitly.'
    }

    $readmeAsset = Get-Content -LiteralPath (Join-Path $stage 'assets\hud-composer.svg') -Raw
    if ($readmeAsset.IndexOf('data:image/png;base64,', [StringComparison]::Ordinal) -lt 0) {
        throw 'README HUD screenshot asset is not the expected embedded PNG SVG.'
    }

    Write-Host 'package layout: ok'
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
