[CmdletBinding()]
param(
    [string]$InstallDir,
    [ValidateRange(1024, 65535)]
    [int]$Port = 9231
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = [IO.Path]::GetDirectoryName($PSCommandPath)
}
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    throw 'Could not resolve the Codex Session Health HUD installation directory.'
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir)

function Show-HudMessage {
    param(
        [Parameter(Mandatory)] [string]$Message,
        [ValidateSet('Information', 'Warning', 'Error')] [string]$Icon = 'Information'
    )
    Add-Type -AssemblyName System.Windows.Forms
    $iconValue = [Enum]::Parse([Windows.Forms.MessageBoxIcon], $Icon)
    [void][Windows.Forms.MessageBox]::Show(
        $Message, 'Codex Session Health HUD',
        [Windows.Forms.MessageBoxButtons]::OK, $iconValue)
}

function Get-CodexPackage {
    $package = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending | Select-Object -First 1
    if (-not $package) { throw 'Microsoft Store Codex Desktop was not found.' }
    if ([string]::IsNullOrWhiteSpace($package.InstallLocation)) {
        throw 'Codex Desktop is installed, but Windows did not expose its package install location.'
    }
    return $package
}

function Get-CodexAppUserModelId {
    param([Parameter(Mandatory)] $Package)
    $manifestPath = Join-Path $Package.InstallLocation 'AppxManifest.xml'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Codex AppxManifest.xml is unavailable.' }
    [xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw
    $application = $manifest.SelectSingleNode("/*[local-name()='Package']/*[local-name()='Applications']/*[local-name()='Application'][1]")
    if (-not $application -or -not $application.Id) { throw 'Could not read the Codex application identifier.' }
    return "$($Package.PackageFamilyName)!$($application.Id)"
}

function Get-CodexPackageRoot {
    param([Parameter(Mandatory)] $Package)
    return [IO.Path]::GetFullPath($Package.InstallLocation).TrimEnd(
        [IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
}

function Test-IsCodexProcess {
    param([Parameter(Mandatory)] $Process, [Parameter(Mandatory)] [string]$PackageRoot)
    if (-not $Process -or [string]::IsNullOrWhiteSpace([string]$Process.ExecutablePath)) { return $false }
    try {
        $path = [IO.Path]::GetFullPath([string]$Process.ExecutablePath)
        $prefix = $PackageRoot.TrimEnd(
            [IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) +
            [IO.Path]::DirectorySeparatorChar
        return $path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}

function Get-ProcessByIdCim {
    param([uint32]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue |
        Select-Object -First 1
}

function Start-PackagedCodex {
    param([Parameter(Mandatory)] [string]$AppUserModelId, [Parameter(Mandatory)] [string]$Arguments)
    if (-not ('CodexSessionHealthHUD.PackageActivator' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace CodexSessionHealthHUD
{
    [Flags] internal enum ActivateOptions : uint { None = 0 }
    [ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IApplicationActivationManager
    {
        [PreserveSig] int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
            [MarshalAs(UnmanagedType.LPWStr)] string arguments, ActivateOptions options, out uint processId);
        [PreserveSig] int ActivateForFile([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
            IntPtr itemArray, [MarshalAs(UnmanagedType.LPWStr)] string verb, ActivateOptions options, out uint processId);
        [PreserveSig] int ActivateForProtocol([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId,
            IntPtr itemArray, ActivateOptions options, out uint processId);
    }
    [ComImport, Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")]
    internal class ApplicationActivationManager { }
    public static class PackageActivator
    {
        public static uint Activate(string appUserModelId, string arguments)
        {
            var manager = (IApplicationActivationManager)new ApplicationActivationManager();
            uint processId;
            int result = manager.ActivateApplication(appUserModelId, arguments, ActivateOptions.None, out processId);
            if (result < 0) Marshal.ThrowExceptionForHR(result);
            return processId;
        }
    }
}
'@
    }
    return [CodexSessionHealthHUD.PackageActivator]::Activate($AppUserModelId, $Arguments)
}

function Get-DebugListener {
    param([int]$LocalPort)
    return Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $LocalPort `
        -ErrorAction SilentlyContinue | Select-Object -First 1
}

try {
    $hudExe = Join-Path $InstallDir 'CodexSessionHealthHUD.exe'
    if (-not (Test-Path -LiteralPath $hudExe)) {
        throw 'CodexSessionHealthHUD.exe was not found. Reinstall the HUD.'
    }

    $package = Get-CodexPackage
    $packageRoot = Get-CodexPackageRoot -Package $package
    $listener = Get-DebugListener -LocalPort $Port
    if ($listener) {
        $owner = Get-ProcessByIdCim -ProcessId ([uint32]$listener.OwningProcess)
        if (-not (Test-IsCodexProcess -Process $owner -PackageRoot $packageRoot)) {
            throw "Local port $Port is already in use by a non-Codex process. Codex and the HUD were not started."
        }
        Start-Process -FilePath $hudExe -ArgumentList @('--renderer-attach', $Port, [int]$listener.OwningProcess) `
            -WorkingDirectory $InstallDir -WindowStyle Hidden
        exit 0
    }

    $running = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe'" -ErrorAction SilentlyContinue |
        Where-Object { Test-IsCodexProcess -Process $_ -PackageRoot $packageRoot })
    if ($running.Count -gt 0) {
        Show-HudMessage -Message (
            'Codex is already running without the local HUD debugging port.' + [Environment]::NewLine +
            [Environment]::NewLine + 'Save your work, exit Codex, then open "Codex with Session Health HUD" again.') `
            -Icon Warning
        exit 3
    }

    $appUserModelId = Get-CodexAppUserModelId -Package $package
    $activationArguments = @(
        '--remote-debugging-address=127.0.0.1',
        "--remote-debugging-port=$Port"
    ) -join ' '
    [void](Start-PackagedCodex -AppUserModelId $appUserModelId -Arguments $activationArguments)

    $listener = $null
    for ($attempt = 0; $attempt -lt 60 -and -not $listener; $attempt++) {
        $listener = Get-DebugListener -LocalPort $Port
        if (-not $listener) { Start-Sleep -Milliseconds 250 }
    }

    if (-not $listener) {
        Show-HudMessage -Message "Codex started, but the local HUD port $Port did not become ready." -Icon Warning
        exit 4
    }

    $owner = Get-ProcessByIdCim -ProcessId ([uint32]$listener.OwningProcess)
    if (-not (Test-IsCodexProcess -Process $owner -PackageRoot $packageRoot)) {
        throw "Local port $Port became owned by a non-Codex process. The HUD was not attached."
    }

    Start-Process -FilePath $hudExe -ArgumentList @('--renderer-attach', $Port, [int]$listener.OwningProcess) `
        -WorkingDirectory $InstallDir -WindowStyle Hidden
} catch {
    $message = 'Codex Session Health HUD could not start.' + [Environment]::NewLine +
        [Environment]::NewLine + $_.Exception.Message
    try {
        Show-HudMessage -Message $message -Icon Error
    } catch {
        Write-Error $message
    }
    exit 1
}
