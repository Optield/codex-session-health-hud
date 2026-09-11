from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    return text.replace(old, new, 1)

# Launcher: distinguish the Electron browser/main process from package-owned
# renderer/utility helpers, and require the DevTools listener owner to be main.
path = Path('Launch-CodexWithSessionHealthHUD.ps1')
text = path.read_text(encoding='utf-8')
needle = '''function Get-ProcessByIdCim {
    param([uint32]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue |
        Select-Object -First 1
}
'''
replacement = '''function Test-IsCodexBrowserProcess {
    param([Parameter(Mandatory)] $Process, [Parameter(Mandatory)] [string]$PackageRoot)
    if (-not (Test-IsCodexProcess -Process $Process -PackageRoot $PackageRoot)) { return $false }
    $commandLine = [string]$Process.CommandLine
    return $commandLine -notmatch '(?:^|\\s)--type(?:=|\\s)'
}

function Get-ProcessByIdCim {
    param([uint32]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue |
        Select-Object -First 1
}
'''
text = replace_once(text, needle, replacement, 'browser process helper')
text = text.replace('Test-IsCodexProcess -Process $owner -PackageRoot $packageRoot',
                    'Test-IsCodexBrowserProcess -Process $owner -PackageRoot $packageRoot')
text = replace_once(
    text,
    '''    $running = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe'" -ErrorAction SilentlyContinue |
        Where-Object { Test-IsCodexProcess -Process $_ -PackageRoot $packageRoot })
''',
    '''    $running = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe'" -ErrorAction SilentlyContinue |
        Where-Object { Test-IsCodexBrowserProcess -Process $_ -PackageRoot $packageRoot })
''',
    'running Codex main-process filter',
)
path.write_text(text, encoding='utf-8')

# Renderer: use all configured history retries, give exhausted/incomplete history
# a one-shot retry when the user returns to the window, and pause quota recovery
# while the document is hidden. Normal successful state still has no retry timer.
path = Path('RendererHudScript.js')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    '''    if (runtime.historyRetryAttempts < HISTORY_RETRY_DELAYS.length) {
''',
    '''    if (runtime.historyRetryAttempts <= HISTORY_RETRY_DELAYS.length) {
''',
    'history retry off-by-one',
)
text = replace_once(
    text,
    '''    if (!hasFullQuotaSnapshot && !quotaRequestTimer && !disposed) {
      quotaRequestTimer = window.setTimeout(requestRateLimits, quotaRetryDelay(quotaRequestAttempts));
    }
''',
    '''    if (!hasFullQuotaSnapshot && !quotaRequestTimer && !disposed && !document.hidden) {
      quotaRequestTimer = window.setTimeout(requestRateLimits, quotaRetryDelay(quotaRequestAttempts));
    }
''',
    'pause quota recovery while hidden',
)
old_visibility = '''  const onVisibility = () => {
    if (!document.hidden) {
      scheduleMount(0);
      scheduleActiveThreadRefresh(0);
      if (!hasFullQuotaSnapshot && !quotaRequestTimer) {
        quotaRequestTimer = window.setTimeout(requestRateLimits, 120);
      }
    }
  };
'''
new_visibility = '''  const onVisibility = () => {
    if (!document.hidden) {
      scheduleMount(0);
      scheduleActiveThreadRefresh(0);
      const runtime = threadRuntime(activeThreadId);
      if (runtime && runtime.historyDirty && !runtime.syncInFlight && !runtime.syncTimer) {
        runtime.historyRetryAttempts = 0;
        runtime.postStatus = 'syncing';
        scheduleCompactionSync(activeThreadId, 120);
      }
      if (!hasFullQuotaSnapshot && !quotaRequestTimer) {
        quotaRequestTimer = window.setTimeout(requestRateLimits, 120);
      }
    }
  };
'''
text = replace_once(text, old_visibility, new_visibility, 'visibility one-shot recovery')
path.write_text(text, encoding='utf-8')

# Uninstaller: delete only the owned shortcut and remove its folder only if empty.
# Keep the marker if owned cleanup failed, so the user can retry uninstall safely.
path = Path('Uninstall.ps1')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    '''    if (Test-Path -LiteralPath $programsDir) {
        try { Remove-Item -LiteralPath $programsDir -Recurse -Force } catch { }
    }
''',
    '''    if (Test-Path -LiteralPath $programsDir -PathType Container) {
        try {
            if (@(Get-ChildItem -LiteralPath $programsDir -Force).Count -eq 0) {
                Remove-Item -LiteralPath $programsDir -Force
            }
        } catch { }
    }
''',
    'nonrecursive Start-menu cleanup',
)
needle = '''# Remove the ownership marker last. Never recursively delete InstallDir: a custom
# install directory may contain unrelated user files from before this safeguard.
if (Test-Path -LiteralPath $marker -PathType Leaf) {
    Remove-Item -LiteralPath $marker -Force
}
'''
replacement = '''# Remove the ownership marker last, and only after known HUD files are gone.
# If cleanup was incomplete, keep the marker so uninstall can be retried safely.
$remainingOwned = @()
foreach ($relativePath in $ownedFiles) {
    if (Test-Path -LiteralPath (Join-Path $fullInstallDir $relativePath) -PathType Leaf) {
        $remainingOwned += $relativePath
    }
}
if (Test-Path -LiteralPath $assetPath -PathType Leaf) { $remainingOwned += 'assets\\hud-composer.svg' }
if ($remainingOwned.Count -gt 0) {
    throw ('Could not remove all HUD-owned files: ' + ($remainingOwned -join ', '))
}
if (Test-Path -LiteralPath $marker -PathType Leaf) {
    Remove-Item -LiteralPath $marker -Force
}
'''
text = replace_once(text, needle, replacement, 'retryable uninstall marker')
path.write_text(text, encoding='utf-8')

# Tests: cover history final delay and static launcher/uninstaller safeguards.
path = Path('tests/renderer-logic.test.js')
test = path.read_text(encoding='utf-8')
test = replace_once(
    test,
    '''assert.equal(t.historyRetryDelay(5), 15000);
assert.equal(t.historyRetryDelay(99), 15000, 'history retry delay is capped');
''',
    '''assert.equal(t.historyRetryDelay(5), 15000);
assert.equal(t.historyRetryDelay(6), 15000, 'history retry delay stays capped after the configured sequence');
assert.equal(t.historyRetryDelay(99), 15000, 'history retry delay is capped');
''',
    'history retry test',
)
path.write_text(test, encoding='utf-8')

path = Path('tests/package-layout.test.ps1')
text = path.read_text(encoding='utf-8')
needle = '''    if ($launcher.IndexOf('DirectorySeparatorChar', [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer uses a path-boundary-safe Codex package containment check.'
    }
'''
replacement = needle + '''    if ($launcher.IndexOf('Test-IsCodexBrowserProcess', [StringComparison]::Ordinal) -lt 0 -or
        $launcher.IndexOf("--type", [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer distinguishes the Codex browser process from helper processes.'
    }
'''
text = replace_once(text, needle, replacement, 'launcher browser role static test')
needle2 = '''    if ($uninstaller -match 'Remove-Item\\s+-LiteralPath\\s+\\$fullInstallDir\\s+-Recurse') {
        throw 'Uninstaller regressed to recursively deleting the entire install directory.'
    }
'''
replacement2 = needle2 + '''    if ($uninstaller -match 'Remove-Item\\s+-LiteralPath\\s+\\$programsDir\\s+-Recurse') {
        throw 'Uninstaller regressed to recursively deleting the Start-menu folder.'
    }
    if ($uninstaller.IndexOf('remainingOwned', [StringComparison]::Ordinal) -lt 0) {
        throw 'Uninstaller no longer preserves the marker when owned-file cleanup is incomplete.'
    }
'''
text = replace_once(text, needle2, replacement2, 'uninstaller static safety test')
path.write_text(text, encoding='utf-8')

# Dynamic install safety: unrelated Start-menu contents are tested indirectly by
# NoShortcuts; owned-file preservation remains the critical custom-dir behavior.
print('final audit patch applied')
