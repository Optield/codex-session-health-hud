from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    return text.replace(old, new, 1)

# Avoid sorting the entire persistent state during ordinary writes. Candidate
# ranking is only needed when a hard entry/byte limit is actually exceeded.
path = Path('HudStateStore.cs')
text = path.read_text(encoding='utf-8')
old = '''        private bool TrimToLimits(string protectedThreadId)
        {
            bool changed = false;
            List<KeyValuePair<string, HudThreadState>> candidates = EvictionCandidates(protectedThreadId);
            int index = 0;

            int excessEntries = Math.Max(0, state.threads.Count - maximumThreadEntries);
            while (excessEntries > 0 && index < candidates.Count)
            {
                if (state.threads.Remove(candidates[index++].Key))
                {
                    excessEntries -= 1;
                    changed = true;
                }
            }

            long bytes = Encoding.UTF8.GetByteCount(serializer.Serialize(state));
            while (bytes > maximumStateFileBytes && index < candidates.Count)
            {
                long average = Math.Max(1L, bytes / Math.Max(1, state.threads.Count));
                int removeCount = (int)Math.Max(1L,
                    (bytes - maximumStateFileBytes + average - 1L) / average);
                for (int i = 0; i < removeCount && index < candidates.Count; i++)
                {
                    if (state.threads.Remove(candidates[index++].Key))
                        changed = true;
                }
                bytes = Encoding.UTF8.GetByteCount(serializer.Serialize(state));
            }
            return changed;
        }
'''
new = '''        private bool TrimToLimits(string protectedThreadId)
        {
            bool changed = false;
            List<KeyValuePair<string, HudThreadState>> candidates = null;
            int index = 0;

            int excessEntries = Math.Max(0, state.threads.Count - maximumThreadEntries);
            if (excessEntries > 0)
            {
                candidates = EvictionCandidates(protectedThreadId);
                while (excessEntries > 0 && index < candidates.Count)
                {
                    if (state.threads.Remove(candidates[index++].Key))
                    {
                        excessEntries -= 1;
                        changed = true;
                    }
                }
            }

            long bytes = Encoding.UTF8.GetByteCount(serializer.Serialize(state));
            if (bytes > maximumStateFileBytes && candidates == null)
                candidates = EvictionCandidates(protectedThreadId);
            while (bytes > maximumStateFileBytes && candidates != null && index < candidates.Count)
            {
                long average = Math.Max(1L, bytes / Math.Max(1, state.threads.Count));
                int removeCount = (int)Math.Max(1L,
                    (bytes - maximumStateFileBytes + average - 1L) / average);
                for (int i = 0; i < removeCount && index < candidates.Count; i++)
                {
                    if (state.threads.Remove(candidates[index++].Key))
                        changed = true;
                }
                bytes = Encoding.UTF8.GetByteCount(serializer.Serialize(state));
            }
            return changed;
        }
'''
text = replace_once(text, old, new, 'lazy state eviction ranking')
path.write_text(text, encoding='utf-8')

# Use platform separator characters for package-root containment instead of
# manually building a string ending in backslashes.
path = Path('Launch-CodexWithSessionHealthHUD.ps1')
text = path.read_text(encoding='utf-8')
old = '''function Get-CodexPackageRoot {
    param([Parameter(Mandatory)] $Package)
    return ([IO.Path]::GetFullPath($Package.InstallLocation).TrimEnd('\\\\') + '\\\\')
}

function Test-IsCodexProcess {
    param([Parameter(Mandatory)] $Process, [Parameter(Mandatory)] [string]$PackageRoot)
    if (-not $Process -or [string]::IsNullOrWhiteSpace([string]$Process.ExecutablePath)) { return $false }
    try {
        $path = [IO.Path]::GetFullPath([string]$Process.ExecutablePath)
        return $path.StartsWith($PackageRoot, [StringComparison]::OrdinalIgnoreCase)
    } catch {
        return $false
    }
}
'''
new = '''function Get-CodexPackageRoot {
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
'''
text = replace_once(text, old, new, 'package root containment')
path.write_text(text, encoding='utf-8')

# Static package gate so the safer boundary check does not regress later.
path = Path('tests/package-layout.test.ps1')
text = path.read_text(encoding='utf-8')
needle = '''    if ($launcher.IndexOf('OwningProcess', [StringComparison]::Ordinal) -lt 0 -or
        $launcher.IndexOf('Test-IsCodexProcess', [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer validates the Codex-owned DevTools listener process.'
    }
'''
replacement = needle + '''    if ($launcher.IndexOf('DirectorySeparatorChar', [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer uses a path-boundary-safe Codex package containment check.'
    }
'''
text = replace_once(text, needle, replacement, 'package root static test')
path.write_text(text, encoding='utf-8')

print('follow-up audit patch applied')
