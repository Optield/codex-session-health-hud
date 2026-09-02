[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$sources = @(
    (Join-Path $projectDir 'CodexSessionHealthHUD.cs'),
    (Join-Path $projectDir 'HudStateStore.cs'),
    (Join-Path $projectDir 'RendererHudBridge.cs')
)
$rendererScript = Join-Path $projectDir 'RendererHudScript.js'
$output = Join-Path $projectDir 'CodexSessionHealthHUD.exe'
$buildOutput = Join-Path ([IO.Path]::GetTempPath()) ("CodexSessionHealthHUD-build-{0}.exe" -f [Guid]::NewGuid())

if (-not (Test-Path -LiteralPath $compiler)) {
    throw 'Windows .NET Framework C# compiler was not found.'
}

foreach ($path in $sources + @($rendererScript)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing source file: $path" }
}

foreach ($scriptPath in @(
    (Join-Path $projectDir 'Launch-CodexWithSessionHealthHUD.ps1'),
    (Join-Path $projectDir 'Install.ps1'),
    (Join-Path $projectDir 'Uninstall.ps1'),
    (Join-Path $projectDir 'Package.ps1')
)) {
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $scriptPath, [ref]$null, [ref]$parseErrors)
    if ($parseErrors.Count -gt 0) {
        throw "PowerShell syntax check failed for $scriptPath`: $($parseErrors[0].Message)"
    }
}

$arguments = @(
    '/nologo', '/target:winexe', '/optimize+', "/out:$buildOutput",
    '/reference:System.Web.Extensions.dll',
    "/resource:$rendererScript,CodexSessionHealthHUD.RendererHudScript.js"
) + $sources

$selfTest = Join-Path ([IO.Path]::GetTempPath()) ("CodexSessionHealthHUD-selftest-{0}.txt" -f [Guid]::NewGuid())
$rendererTest = Join-Path ([IO.Path]::GetTempPath()) ("CodexSessionHealthHUD-renderer-test-{0}.txt" -f [Guid]::NewGuid())
try {
    & $compiler @arguments
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed with exit code $LASTEXITCODE." }

    $test = Start-Process -FilePath $buildOutput -ArgumentList @('--self-test', $selfTest) -Wait -PassThru
    if ($test.ExitCode -ne 0) { throw (Get-Content -LiteralPath $selfTest -Raw) }
    Write-Host (Get-Content -LiteralPath $selfTest -Raw)

    $renderer = Start-Process -FilePath $buildOutput -ArgumentList @('--renderer-self-test', $rendererTest) -Wait -PassThru
    if ($renderer.ExitCode -ne 0) { throw (Get-Content -LiteralPath $rendererTest -Raw) }
    Write-Host (Get-Content -LiteralPath $rendererTest -Raw)

    Get-CimInstance Win32_Process -Filter "Name='CodexSessionHealthHUD.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            try {
                if ($_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($output)) {
                    Stop-Process -Id $_.ProcessId -Force
                    Wait-Process -Id $_.ProcessId -Timeout 3 -ErrorAction SilentlyContinue
                }
            } catch { }
        }

    Copy-Item -LiteralPath $buildOutput -Destination $output -Force
}
finally {
    Remove-Item -LiteralPath $selfTest -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $rendererTest -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $buildOutput -Force -ErrorAction SilentlyContinue
}

Write-Host "Build completed: $output"
