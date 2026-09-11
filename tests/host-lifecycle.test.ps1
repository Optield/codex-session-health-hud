[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $projectDir 'CodexSessionHealthHUD.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw 'Build CodexSessionHealthHUD.exe before running host lifecycle tests.'
}

function Get-FreePort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return ([Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function Start-OwnerProcess {
    return Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoLogo', '-NoProfile', '-Command', 'Start-Sleep -Seconds 40'
    ) -WindowStyle Hidden -PassThru
}

function Stop-Quietly($process) {
    if (-not $process) { return }
    try { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force } } catch { }
    try { $process.Dispose() } catch { }
}

# 1. A live owner with a missing endpoint gets a grace period, then the HUD exits.
$owner = $null
$hud = $null
try {
    $owner = Start-OwnerProcess
    $port = Get-FreePort
    $hud = Start-Process -FilePath $exe -ArgumentList @('--renderer-attach', $port, $owner.Id) `
        -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    if ($hud.HasExited) { throw 'HUD exited before the endpoint-loss grace period elapsed.' }
    if (-not $hud.WaitForExit(18000)) { throw 'HUD did not exit after sustained endpoint loss.' }
} finally {
    Stop-Quietly $hud
    Stop-Quietly $owner
}

# 2. Endpoint reachable but no page target is treated like a renderer transition:
#    the HUD stays alive. Killing the bound owner process then ends the HUD.
$temp = Join-Path ([IO.Path]::GetTempPath()) ('CodexSessionHealthHUD-host-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
$serverScript = Join-Path $temp 'server.py'
@'
import http.server, sys
port = int(sys.argv[1])
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'[]'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
'@ | Set-Content -LiteralPath $serverScript -Encoding utf8

$server = $null
$owner = $null
$hud = $null
try {
    $port = Get-FreePort
    $server = Start-Process -FilePath 'python.exe' -ArgumentList @($serverScript, $port) -WindowStyle Hidden -PassThru
    $ready = $false
    for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
        try {
            $client = [Net.Sockets.TcpClient]::new()
            $client.Connect('127.0.0.1', $port)
            $client.Dispose()
            $ready = $true
        } catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $ready) { throw 'Test CDP endpoint did not start.' }

    $owner = Start-OwnerProcess
    $hud = Start-Process -FilePath $exe -ArgumentList @('--renderer-attach', $port, $owner.Id) `
        -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
    if ($hud.HasExited) { throw 'HUD exited while its owner and CDP endpoint were still alive.' }

    Stop-Process -Id $owner.Id -Force
    if (-not $hud.WaitForExit(5000)) { throw 'HUD did not exit after its bound browser owner exited.' }
} finally {
    Stop-Quietly $hud
    Stop-Quietly $owner
    Stop-Quietly $server
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host 'host lifecycle: ok'
