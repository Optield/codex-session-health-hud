[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'CodexSessionHealthHUD'),
    [ValidateRange(1024, 65535)] [int]$Port = 9231,
    [switch]$NoStartMenu
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    throw 'InstallDir cannot be empty.'
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)

$sourceExe = Join-Path $PSScriptRoot 'CodexSessionHealthHUD.exe'
if (-not (Test-Path -LiteralPath $sourceExe)) {
    & (Join-Path $PSScriptRoot 'Build.ps1')
}
if (-not (Test-Path -LiteralPath $sourceExe)) { throw 'Build did not produce CodexSessionHealthHUD.exe.' }

$targetExe = Join-Path $InstallDir 'CodexSessionHealthHUD.exe'
$targetLauncher = Join-Path $InstallDir 'Launch-CodexWithSessionHealthHUD.ps1'
$targetIcon = Join-Path $InstallDir 'Codex.ico'
$sourceAssets = Join-Path $PSScriptRoot 'assets'
$targetAssets = Join-Path $InstallDir 'assets'
$marker = Join-Path $InstallDir '.install-marker'
$programsDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Codex Session Health HUD'
$launcherShortcut = Join-Path $programsDir 'Codex with Session Health HUD.lnk'
$taskbarShortcut = Join-Path $env:APPDATA `
    'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Codex with Session Health HUD.lnk'
$payload = @(
    'CodexSessionHealthHUD.exe', 'Launch-CodexWithSessionHealthHUD.ps1', 'Uninstall.ps1',
    'README.md', 'README.ko.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'
)

foreach ($name in $payload) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $name))) { throw "Missing install payload: $name" }
}
if (-not (Test-Path -LiteralPath $sourceAssets -PathType Container)) {
    throw 'Missing install payload directory: assets'
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

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
foreach ($name in $payload) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $InstallDir $name) -Force
}
New-Item -ItemType Directory -Path $targetAssets -Force | Out-Null
Copy-Item -Path (Join-Path $sourceAssets '*') -Destination $targetAssets -Recurse -Force
Set-Content -LiteralPath $marker -Value 'CodexSessionHealthHUD|v1' -Encoding ASCII

if (-not $NoStartMenu) {
    $package = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending | Select-Object -First 1
    $packageInstallLocation = if ($package -and -not [string]::IsNullOrWhiteSpace($package.InstallLocation)) {
        $package.InstallLocation
    } else {
        $null
    }
    $codexExe = if ($packageInstallLocation) {
        Join-Path $packageInstallLocation 'app\ChatGPT.exe'
    } else {
        $null
    }
    $codexIconPng = if ($packageInstallLocation) {
        Join-Path $packageInstallLocation 'assets\Square44x44Logo.targetsize-256_altform-unplated.png'
    } else {
        $null
    }

    if ($codexIconPng -and (Test-Path -LiteralPath $codexIconPng)) {
        $pngBytes = [IO.File]::ReadAllBytes($codexIconPng)
        $stream = [IO.File]::Create($targetIcon)
        try {
            $writer = New-Object IO.BinaryWriter($stream)
            try {
                $writer.Write([UInt16]0); $writer.Write([UInt16]1); $writer.Write([UInt16]1)
                $writer.Write([Byte]0); $writer.Write([Byte]0); $writer.Write([Byte]0); $writer.Write([Byte]0)
                $writer.Write([UInt16]1); $writer.Write([UInt16]32)
                $writer.Write([UInt32]$pngBytes.Length); $writer.Write([UInt32]22); $writer.Write($pngBytes)
            } finally { $writer.Dispose() }
        } finally { $stream.Dispose() }
    } elseif ($codexExe -and (Test-Path -LiteralPath $codexExe)) {
        Add-Type -AssemblyName System.Drawing
        $icon = [Drawing.Icon]::ExtractAssociatedIcon($codexExe)
        if ($icon) {
            try {
                $stream = [IO.File]::Create($targetIcon)
                try { $icon.Save($stream) } finally { $stream.Dispose() }
            } finally { $icon.Dispose() }
        }
    }

    New-Item -ItemType Directory -Path $programsDir -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $powershell = (Get-Process -Id $PID).Path
    $shortcut = $shell.CreateShortcut($launcherShortcut)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$targetLauncher`" -InstallDir `"$InstallDir`" -Port $Port"
    $shortcut.WorkingDirectory = $InstallDir
    if (Test-Path -LiteralPath $targetIcon) { $shortcut.IconLocation = "$targetIcon,0" }
    $shortcut.Description = 'Start Codex with the Session Health HUD'
    $shortcut.Save()

    if ((Test-Path -LiteralPath $taskbarShortcut) -and (Test-Path -LiteralPath $targetIcon)) {
        try {
            $pinned = $shell.CreateShortcut($taskbarShortcut)
            if ($pinned.Arguments.IndexOf($targetLauncher, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $pinned.IconLocation = "$targetIcon,0"
                $pinned.Save()
            }
        } catch { }
    }
}

Write-Host "Installed: $targetExe"
if ($NoStartMenu) { Write-Host "Run $targetLauncher to start Codex with the HUD." }
else { Write-Host 'Open "Codex with Session Health HUD" from the Start menu.' }
