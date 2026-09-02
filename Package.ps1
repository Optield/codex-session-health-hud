[CmdletBinding()]
param([string]$OutputDir = (Join-Path $PSScriptRoot 'dist'))

$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Build.ps1')
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$stage = Join-Path ([IO.Path]::GetTempPath()) ("CodexSessionHealthHUD-package-{0}" -f [Guid]::NewGuid())
New-Item -ItemType Directory -Path $stage -Force | Out-Null
try {
    foreach ($name in @(
        'CodexSessionHealthHUD.exe', 'Install-Easy.bat', 'Launch-CodexWithSessionHealthHUD.ps1', 'Install.ps1', 'Uninstall.ps1',
        'README.md', 'README.ko.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'
    )) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $stage $name) -Force
    }
    $zip = Join-Path $OutputDir 'CodexSessionHealthHUD-win-x64.zip'
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "Package created: $zip"
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
