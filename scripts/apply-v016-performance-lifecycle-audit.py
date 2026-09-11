from pathlib import Path
import re


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    return text.replace(old, new, 1)


def sub_once(text, pattern, replacement, label):
    text, count = re.subn(pattern, lambda _m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    return text

# Host: bounded target/attach failure states and a local WebSocket connect timeout.
path = Path('RendererHudBridge.cs')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    '''            socket.ConnectAsync(new Uri(target.WebSocketDebuggerUrl), CancellationToken.None)
                .GetAwaiter().GetResult();
''',
    '''            using (CancellationTokenSource connectTimeout = new CancellationTokenSource())
            {
                connectTimeout.CancelAfter(3000);
                socket.ConnectAsync(new Uri(target.WebSocketDebuggerUrl), connectTimeout.Token)
                    .GetAwaiter().GetResult();
            }
''',
    'WebSocket connect timeout',
)
text = replace_once(
    text,
    '''        internal const int EndpointFailureExitThreshold = 8;

        internal static bool ShouldExitForLifetime(bool ownerExited, int consecutiveEndpointFailures)
        {
            return ownerExited || consecutiveEndpointFailures >= EndpointFailureExitThreshold;
        }
''',
    '''        internal const int EndpointFailureExitThreshold = 8;
        internal const int TargetMissingExitThreshold = 80;
        internal const int AttachFailureExitThreshold = 20;

        internal static bool ShouldExitForLifetime(bool ownerExited, int consecutiveEndpointFailures)
        {
            return ownerExited || consecutiveEndpointFailures >= EndpointFailureExitThreshold;
        }

        internal static bool ShouldExitForTargetState(int consecutiveTargetMisses, int consecutiveAttachFailures)
        {
            return consecutiveTargetMisses >= TargetMissingExitThreshold ||
                consecutiveAttachFailures >= AttachFailureExitThreshold;
        }
''',
    'host target/attach policy',
)
old_loop = '''                    int consecutiveEndpointFailures = 0;

                    while (true)
                    {
                        bool ownerExited = OwnerExited(owner);
                        if (ShouldExitForLifetime(ownerExited, consecutiveEndpointFailures))
                            return 0;

                        CdpProbeResult probe = CdpTargetDiscovery.Probe(port);
                        if (!probe.EndpointReachable)
                        {
                            consecutiveEndpointFailures += 1;
                            if (ShouldExitForLifetime(OwnerExited(owner), consecutiveEndpointFailures))
                                return 0;
                            Thread.Sleep(RetryDelayMilliseconds);
                            continue;
                        }

                        consecutiveEndpointFailures = 0;
                        if (probe.Target != null)
                        {
                            try
                            {
                                using (CdpConnection connection = new CdpConnection(stateStore, script))
                                {
                                    connection.ConnectAndInject(probe.Target);
                                    connection.WaitUntilClosed();
                                }
                            }
                            catch { }
                        }
                        Thread.Sleep(RetryDelayMilliseconds);
                    }
'''
new_loop = '''                    int consecutiveEndpointFailures = 0;
                    int consecutiveTargetMisses = 0;
                    int consecutiveAttachFailures = 0;

                    while (true)
                    {
                        bool ownerExited = OwnerExited(owner);
                        if (ShouldExitForLifetime(ownerExited, consecutiveEndpointFailures) ||
                            ShouldExitForTargetState(consecutiveTargetMisses, consecutiveAttachFailures))
                            return 0;

                        CdpProbeResult probe = CdpTargetDiscovery.Probe(port);
                        if (!probe.EndpointReachable)
                        {
                            consecutiveEndpointFailures += 1;
                            consecutiveTargetMisses = 0;
                            consecutiveAttachFailures = 0;
                            if (ShouldExitForLifetime(OwnerExited(owner), consecutiveEndpointFailures))
                                return 0;
                            Thread.Sleep(RetryDelayMilliseconds);
                            continue;
                        }

                        consecutiveEndpointFailures = 0;
                        if (probe.Target == null)
                        {
                            consecutiveTargetMisses += 1;
                            consecutiveAttachFailures = 0;
                            if (ShouldExitForTargetState(consecutiveTargetMisses, consecutiveAttachFailures))
                                return 0;
                            Thread.Sleep(RetryDelayMilliseconds);
                            continue;
                        }

                        consecutiveTargetMisses = 0;
                        try
                        {
                            using (CdpConnection connection = new CdpConnection(stateStore, script))
                            {
                                connection.ConnectAndInject(probe.Target);
                                consecutiveAttachFailures = 0;
                                connection.WaitUntilClosed();
                            }
                        }
                        catch
                        {
                            consecutiveAttachFailures += 1;
                            if (ShouldExitForTargetState(consecutiveTargetMisses, consecutiveAttachFailures))
                                return 0;
                        }
                        Thread.Sleep(RetryDelayMilliseconds);
                    }
'''
text = replace_once(text, old_loop, new_loop, 'host retry loop')
path.write_text(text, encoding='utf-8')

# Self-test the additional lifecycle policy without adding long wall-clock CI waits.
path = Path('CodexSessionHealthHUD.cs')
text = path.read_text(encoding='utf-8')
needle = '''                if (!RendererHudHost.ShouldExitForLifetime(true, 0) ||
                    RendererHudHost.ShouldExitForLifetime(false, RendererHudHost.EndpointFailureExitThreshold - 1) ||
                    !RendererHudHost.ShouldExitForLifetime(false, RendererHudHost.EndpointFailureExitThreshold))
                    throw new InvalidOperationException("Host lifetime policy regression.");
'''
replacement = needle + '''                if (RendererHudHost.ShouldExitForTargetState(RendererHudHost.TargetMissingExitThreshold - 1, 0) ||
                    !RendererHudHost.ShouldExitForTargetState(RendererHudHost.TargetMissingExitThreshold, 0) ||
                    RendererHudHost.ShouldExitForTargetState(0, RendererHudHost.AttachFailureExitThreshold - 1) ||
                    !RendererHudHost.ShouldExitForTargetState(0, RendererHudHost.AttachFailureExitThreshold))
                    throw new InvalidOperationException("Host target/attach lifetime policy regression.");
'''
text = replace_once(text, needle, replacement, 'host target policy self-test')
path.write_text(text, encoding='utf-8')

# State store: normal persistence serializes once. Entry eviction occurs before
# save only when count exceeds the cap; byte eviction occurs only after the
# one normal serialization discovers an actual overflow.
path = Path('HudStateStore.cs')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    '''            bool changed = TrimToLimits(null);
            if (InvalidateForeignPendingMeasurements())
                changed = true;
            if (changed)
                SaveLocked();
''',
    '''            bool changed = TrimEntryLimit(null);
            long startupBytes = Encoding.UTF8.GetByteCount(serializer.Serialize(state));
            if (startupBytes > maximumStateFileBytes && TrimBytesToLimit(null, startupBytes))
                changed = true;
            if (InvalidateForeignPendingMeasurements())
                changed = true;
            if (changed)
                SaveLocked(null);
''',
    'startup limit handling',
)
text = replace_once(
    text,
    '''                state.threads[threadId] = next;
                TrimToLimits(threadId);
                SaveLocked();
''',
    '''                state.threads[threadId] = next;
                TrimEntryLimit(threadId);
                SaveLocked(threadId);
''',
    'normal persistence single serialization path',
)
new_limits = '''        private bool TrimEntryLimit(string protectedThreadId)
        {
            int excessEntries = Math.Max(0, state.threads.Count - maximumThreadEntries);
            if (excessEntries <= 0)
                return false;
            bool changed = false;
            List<KeyValuePair<string, HudThreadState>> candidates = EvictionCandidates(protectedThreadId);
            int index = 0;
            while (excessEntries > 0 && index < candidates.Count)
            {
                if (state.threads.Remove(candidates[index++].Key))
                {
                    excessEntries -= 1;
                    changed = true;
                }
            }
            return changed;
        }

        private bool TrimBytesToLimit(string protectedThreadId, long currentBytes)
        {
            if (currentBytes <= maximumStateFileBytes)
                return false;
            bool changed = false;
            long bytes = currentBytes;
            List<KeyValuePair<string, HudThreadState>> candidates = EvictionCandidates(protectedThreadId);
            int index = 0;
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

        private void SaveLocked(string protectedThreadId)
        {
            string directory = Path.GetDirectoryName(statePath);
            if (string.IsNullOrWhiteSpace(directory))
                return;
            Directory.CreateDirectory(directory);

            string json = serializer.Serialize(state);
            long bytes = Encoding.UTF8.GetByteCount(json);
            if (bytes > maximumStateFileBytes)
            {
                TrimBytesToLimit(protectedThreadId, bytes);
                json = serializer.Serialize(state);
                if (Encoding.UTF8.GetByteCount(json) > maximumStateFileBytes)
                    return;
            }
'''
text = sub_once(
    text,
    r'        private bool TrimToLimits\(string protectedThreadId\)\n        \{.*?\n        private void SaveLocked\(\)\n        \{\n            string directory = Path.GetDirectoryName\(statePath\);\n            if \(string.IsNullOrWhiteSpace\(directory\)\)\n                return;\n            Directory.CreateDirectory\(directory\);\n\n            string json = serializer.Serialize\(state\);\n            if \(Encoding.UTF8.GetByteCount\(json\) > maximumStateFileBytes\)\n                return;\n',
    new_limits,
    'state limit/save methods',
)
# All non-Apply call sites must use the new optional protected-thread parameter explicitly.
text = text.replace('SaveLocked();', 'SaveLocked(null);')
path.write_text(text, encoding='utf-8')

# Launcher: fail closed if CIM cannot provide the command line needed to
# distinguish browser/main from helpers.
path = Path('Launch-CodexWithSessionHealthHUD.ps1')
text = path.read_text(encoding='utf-8')
text = replace_once(
    text,
    '''    $commandLine = [string]$Process.CommandLine
    return $commandLine -notmatch '(?:^|\\s)--type(?:=|\\s)'
''',
    '''    $commandLine = [string]$Process.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) { return $false }
    return $commandLine -notmatch '(?:^|\\s)--type(?:=|\\s)'
''',
    'browser process command-line fail closed',
)
path.write_text(text, encoding='utf-8')

# Static regression gates.
path = Path('tests/package-layout.test.ps1')
text = path.read_text(encoding='utf-8')
needle = '''    if ($launcher.IndexOf('Test-IsCodexBrowserProcess', [StringComparison]::Ordinal) -lt 0 -or
        $launcher.IndexOf("--type", [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer distinguishes the Codex browser process from helper processes.'
    }
'''
replacement = needle + '''    if ($launcher.IndexOf('IsNullOrWhiteSpace($commandLine)', [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer fails closed when browser-process command-line identity is unavailable.'
    }
'''
text = replace_once(text, needle, replacement, 'launcher fail-closed static gate')
path.write_text(text, encoding='utf-8')

print('performance/lifecycle audit patch applied')
