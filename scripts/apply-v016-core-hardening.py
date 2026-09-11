from pathlib import Path
import re


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def sub_once(text, pattern, repl, label, flags=re.S):
    text, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text


# ---------------------------------------------------------------------------
# Program/self-tests: bind one HUD host to one Codex browser PID and add
# regression coverage for host lifetime, Runtime.evaluate exceptions, and
# bounded state eviction.
# ---------------------------------------------------------------------------
path = Path('CodexSessionHealthHUD.cs')
text = path.read_text(encoding='utf-8')
text = replace_once(text, 'using System;\nusing System.IO;\n',
                    'using System;\nusing System.Collections.Generic;\nusing System.IO;\n',
                    'program usings')
old_attach = '''                if (args != null && args.Length >= 2 &&
                    string.Equals(args[0], "--renderer-attach", StringComparison.OrdinalIgnoreCase))
                {
                    int port;
                    if (!int.TryParse(args[1], out port) || port < 1024 || port > 65535)
                        return 2;
                    return RendererHudHost.Run(port);
                }
'''
new_attach = '''                if (args != null && args.Length >= 3 &&
                    string.Equals(args[0], "--renderer-attach", StringComparison.OrdinalIgnoreCase))
                {
                    int port;
                    int browserProcessId;
                    if (!int.TryParse(args[1], out port) || port < 1024 || port > 65535 ||
                        !int.TryParse(args[2], out browserProcessId) || browserProcessId <= 0)
                        return 2;
                    return RendererHudHost.Run(port, browserProcessId);
                }
'''
text = replace_once(text, old_attach, new_attach, 'renderer attach arguments')
needle = '''                bootstrap = storeB.GetBootstrapJson();
                if (bootstrap.IndexOf("103184", StringComparison.Ordinal) < 0 ||
                    bootstrap.IndexOf("258400", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("Ready snapshot did not persist.");

                File.WriteAllText(outputPath, "state-store: ok" + Environment.NewLine);
'''
replacement = '''                bootstrap = storeB.GetBootstrapJson();
                if (bootstrap.IndexOf("103184", StringComparison.Ordinal) < 0 ||
                    bootstrap.IndexOf("258400", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("Ready snapshot did not persist.");

                if (!RendererHudHost.ShouldExitForLifetime(true, 0) ||
                    RendererHudHost.ShouldExitForLifetime(false, RendererHudHost.EndpointFailureExitThreshold - 1) ||
                    !RendererHudHost.ShouldExitForLifetime(false, RendererHudHost.EndpointFailureExitThreshold))
                    throw new InvalidOperationException("Host lifetime policy regression.");

                Dictionary<string, object> evaluationBody = new Dictionary<string, object>();
                evaluationBody["exceptionDetails"] = new Dictionary<string, object>();
                Dictionary<string, object> evaluationResponse = new Dictionary<string, object>();
                evaluationResponse["result"] = evaluationBody;
                if (!CdpConnection.HasEvaluationException(evaluationResponse))
                    throw new InvalidOperationException("Runtime.evaluate exception detection regression.");
                evaluationResponse["result"] = new Dictionary<string, object>();
                if (CdpConnection.HasEvaluationException(evaluationResponse))
                    throw new InvalidOperationException("Runtime.evaluate false-positive exception regression.");

                string boundedPath = Path.Combine(root, "bounded-state.json");
                HudStateStore bounded = new HudStateStore(boundedPath, "run-bounded", 2, 4096);
                bounded.ApplyRendererPayload(
                    "{\\\"action\\\":\\\"upsertThreadState\\\",\\\"threadId\\\":\\\"thread-low\\\",\\\"state\\\":{\\\"compactionCount\\\":0,\\\"postCompactionStatus\\\":\\\"noCompaction\\\"}}"
                );
                bounded.ApplyRendererPayload(
                    "{\\\"action\\\":\\\"upsertThreadState\\\",\\\"threadId\\\":\\\"thread-old\\\",\\\"state\\\":{\\\"lastObservedCompactionId\\\":\\\"old\\\",\\\"compactionCount\\\":1,\\\"snapshotCompactionId\\\":\\\"old\\\",\\\"postCompactionStatus\\\":\\\"ready\\\",\\\"postCompactionTokens\\\":1000,\\\"postCompactionWindow\\\":10000,\\\"capturedAt\\\":\\\"2026-01-01T00:00:00Z\\\"}}"
                );
                bounded.ApplyRendererPayload(
                    "{\\\"action\\\":\\\"upsertThreadState\\\",\\\"threadId\\\":\\\"thread-new\\\",\\\"state\\\":{\\\"lastObservedCompactionId\\\":\\\"new\\\",\\\"compactionCount\\\":2,\\\"snapshotCompactionId\\\":\\\"new\\\",\\\"postCompactionStatus\\\":\\\"ready\\\",\\\"postCompactionTokens\\\":2000,\\\"postCompactionWindow\\\":10000,\\\"capturedAt\\\":\\\"2026-09-01T00:00:00Z\\\"}}"
                );
                string boundedBootstrap = bounded.GetBootstrapJson();
                if (boundedBootstrap.IndexOf("thread-low", StringComparison.Ordinal) >= 0 ||
                    boundedBootstrap.IndexOf("thread-old", StringComparison.Ordinal) < 0 ||
                    boundedBootstrap.IndexOf("thread-new", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("State entry eviction did not preserve the most useful snapshots.");

                string bytesPath = Path.Combine(root, "byte-bounded-state.json");
                HudStateStore byteBounded = new HudStateStore(bytesPath, "run-bytes", 100, 900);
                for (int i = 0; i < 8; i++)
                {
                    byteBounded.ApplyRendererPayload(
                        "{\\\"action\\\":\\\"upsertThreadState\\\",\\\"threadId\\\":\\\"thread-byte-" + i.ToString() +
                        "\\\",\\\"state\\\":{\\\"compactionCount\\\":0,\\\"postCompactionStatus\\\":\\\"noCompaction\\\"}}"
                    );
                }
                if (!File.Exists(bytesPath) || new FileInfo(bytesPath).Length > 900)
                    throw new InvalidOperationException("State byte limit was not enforced.");
                if (byteBounded.GetBootstrapJson().IndexOf("thread-byte-7", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("Newest protected state was evicted while enforcing byte limit.");

                HudStateStore timestampStore = new HudStateStore(Path.Combine(root, "timestamp-state.json"), "run-time");
                timestampStore.ApplyRendererPayload(
                    "{\\\"action\\\":\\\"upsertThreadState\\\",\\\"threadId\\\":\\\"thread-time\\\",\\\"state\\\":{\\\"lastObservedCompactionId\\\":\\\"time\\\",\\\"compactionCount\\\":1,\\\"snapshotCompactionId\\\":\\\"time\\\",\\\"postCompactionStatus\\\":\\\"ready\\\",\\\"postCompactionTokens\\\":1000,\\\"postCompactionWindow\\\":10000,\\\"capturedAt\\\":\\\"not-a-date\\\"}}"
                );
                if (timestampStore.GetBootstrapJson().IndexOf("not-a-date", StringComparison.Ordinal) >= 0)
                    throw new InvalidOperationException("Invalid capture timestamps were not sanitized.");

                File.WriteAllText(outputPath, "state-store: ok" + Environment.NewLine);
'''
text = replace_once(text, needle, replacement, 'core self-tests')
path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Host/CDP lifecycle.
# ---------------------------------------------------------------------------
path = Path('RendererHudBridge.cs')
text = path.read_text(encoding='utf-8')
text = replace_once(text, 'using System.Collections.Generic;\nusing System.IO;\n',
                    'using System.Collections.Generic;\nusing System.Diagnostics;\nusing System.IO;\n',
                    'bridge diagnostics using')
new_discovery = r'''    internal sealed class CdpProbeResult
    {
        internal bool EndpointReachable;
        internal CdpTarget Target;
    }

    internal static class CdpTargetDiscovery
    {
        internal static CdpProbeResult Probe(int port)
        {
            CdpProbeResult result = new CdpProbeResult();
            string endpoint = "http://127.0.0.1:" + port + "/json/list";
            string json;
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(endpoint);
                request.Timeout = 2000;
                request.ReadWriteTimeout = 2000;
                request.Proxy = null;
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                using (StreamReader reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                    json = reader.ReadToEnd();
                result.EndpointReachable = true;
            }
            catch
            {
                return result;
            }

            object[] targets;
            try { targets = new JavaScriptSerializer().DeserializeObject(json) as object[]; }
            catch { return result; }
            if (targets == null)
                return result;

            CdpTarget fallback = null;
            for (int i = 0; i < targets.Length; i++)
            {
                IDictionary<string, object> map = targets[i] as IDictionary<string, object>;
                if (map == null || Get(map, "type") != "page")
                    continue;
                CdpTarget target = new CdpTarget();
                target.Title = Get(map, "title");
                target.Url = Get(map, "url");
                target.WebSocketDebuggerUrl = Get(map, "webSocketDebuggerUrl");
                if (!IsAllowedTarget(target) || !IsLoopbackWebSocket(target.WebSocketDebuggerUrl))
                    continue;
                if (string.Equals(target.Url, "app://-/index.html", StringComparison.OrdinalIgnoreCase))
                {
                    result.Target = target;
                    return result;
                }
                if (fallback == null)
                    fallback = target;
            }
            result.Target = fallback;
            return result;
        }

        internal static CdpTarget Find(int port)
        {
            return Probe(port).Target;
        }

        private static bool IsAllowedTarget(CdpTarget target)
        {
            if (target == null || string.IsNullOrWhiteSpace(target.Url) ||
                string.IsNullOrWhiteSpace(target.WebSocketDebuggerUrl))
                return false;
            Uri uri;
            if (!Uri.TryCreate(target.Url, UriKind.Absolute, out uri))
                return false;
            if (uri.Scheme == "app")
            {
                return string.Equals(uri.AbsolutePath, "/index.html", StringComparison.OrdinalIgnoreCase) &&
                    uri.Query.IndexOf("avatar-overlay", StringComparison.OrdinalIgnoreCase) < 0;
            }
            if (uri.Scheme != "file")
                return false;
            string path = uri.AbsolutePath.Replace('\\', '/');
            return path.IndexOf("/OpenAI.Codex_", StringComparison.OrdinalIgnoreCase) >= 0 &&
                (path.EndsWith("/webview/index.html", StringComparison.OrdinalIgnoreCase) ||
                 path.EndsWith("/app/index.html", StringComparison.OrdinalIgnoreCase));
        }

        private static bool IsLoopbackWebSocket(string address)
        {
            Uri uri;
            return Uri.TryCreate(address, UriKind.Absolute, out uri) &&
                (uri.Scheme == "ws" || uri.Scheme == "wss") && uri.IsLoopback;
        }

        private static string Get(IDictionary<string, object> map, string key)
        {
            object value;
            return map.TryGetValue(key, out value) && value != null ? Convert.ToString(value) : null;
        }
    }

'''
text = sub_once(text,
                r'    internal static class CdpTargetDiscovery\n    \{.*?\n    \}\n\n(?=    internal sealed class CdpConnection)',
                new_discovery,
                'CDP discovery class')
text = replace_once(text,
                    '        private volatile bool canReinject;\n',
                    '        private volatile bool canReinject;\n        private volatile bool disposed;\n',
                    'connection disposed field')
old_eval = '''        private Task EvaluateAsync(string expression)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>();
            parameters["expression"] = expression;
            parameters["awaitPromise"] = false;
            parameters["returnByValue"] = true;
            return SendCommandAsync("Runtime.evaluate", parameters);
        }
'''
new_eval = '''        private async Task EvaluateAsync(string expression)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>();
            parameters["expression"] = expression;
            parameters["awaitPromise"] = false;
            parameters["returnByValue"] = true;
            IDictionary<string, object> response = await SendCommandAsync("Runtime.evaluate", parameters)
                .ConfigureAwait(false);
            if (HasEvaluationException(response))
                throw new InvalidOperationException("Runtime.evaluate reported a JavaScript exception.");
        }

        internal static bool HasEvaluationException(IDictionary<string, object> response)
        {
            if (response == null)
                return false;
            object rawResult;
            IDictionary<string, object> result;
            if (!response.TryGetValue("result", out rawResult) ||
                (result = rawResult as IDictionary<string, object>) == null)
                return false;
            object exceptionDetails;
            return result.TryGetValue("exceptionDetails", out exceptionDetails) && exceptionDetails != null;
        }
'''
text = replace_once(text, old_eval, new_eval, 'Runtime.evaluate validation')
old_nav = '''                    else if (string.Equals(method, "Page.frameNavigated", StringComparison.Ordinal) ||
                        string.Equals(method, "Runtime.executionContextsCleared", StringComparison.Ordinal))
                    {
                        if (canReinject) ScheduleReinject();
                    }
'''
new_nav = '''                    else if (string.Equals(method, "Runtime.executionContextsCleared", StringComparison.Ordinal) ||
                        (string.Equals(method, "Page.frameNavigated", StringComparison.Ordinal) &&
                         IsTopLevelFrameNavigation(message)))
                    {
                        if (canReinject) ScheduleReinject();
                    }
'''
text = replace_once(text, old_nav, new_nav, 'top-level reinjection events')
old_schedule = r'''        private void ScheduleReinject()
        {
            if (Interlocked.Exchange(ref reinjectScheduled, 1) != 0)
                return;
            Task.Run(async () =>
            {
                try
                {
                    for (int attempt = 0; attempt < 5; attempt++)
                    {
                        try
                        {
                            await Task.Delay(180 + attempt * 160).ConfigureAwait(false);
                            await InjectAsync().ConfigureAwait(false);
                            break;
                        }
                        catch
                        {
                            if (attempt == 4) throw;
                        }
                    }
                }
                catch { }
                finally
                {
                    Interlocked.Exchange(ref reinjectScheduled, 0);
                }
            });
        }
'''
new_schedule = r'''        private static bool IsTopLevelFrameNavigation(IDictionary<string, object> message)
        {
            object rawParams;
            IDictionary<string, object> parameters;
            object rawFrame;
            IDictionary<string, object> frame;
            if (message == null || !message.TryGetValue("params", out rawParams) ||
                (parameters = rawParams as IDictionary<string, object>) == null ||
                !parameters.TryGetValue("frame", out rawFrame) ||
                (frame = rawFrame as IDictionary<string, object>) == null)
                return false;
            object parentId;
            return !frame.TryGetValue("parentId", out parentId) || parentId == null ||
                string.IsNullOrWhiteSpace(Convert.ToString(parentId));
        }

        private void ScheduleReinject()
        {
            if (!canReinject || disposed || Interlocked.Exchange(ref reinjectScheduled, 1) != 0)
                return;
            Task.Run(async () =>
            {
                int delay = 180;
                try
                {
                    while (!disposed && !cancellation.IsCancellationRequested && socket.State == WebSocketState.Open)
                    {
                        try
                        {
                            await Task.Delay(delay, cancellation.Token).ConfigureAwait(false);
                            await InjectAsync().ConfigureAwait(false);
                            return;
                        }
                        catch (OperationCanceledException)
                        {
                            return;
                        }
                        catch
                        {
                            delay = Math.Min(5000, Math.Max(360, delay * 2));
                        }
                    }
                }
                finally
                {
                    Interlocked.Exchange(ref reinjectScheduled, 0);
                }
            });
        }
'''
text = replace_once(text, old_schedule, new_schedule, 'persistent reinjection retry')
text = replace_once(text,
                    '''        public void Dispose()\n        {\n            try { cancellation.Cancel(); } catch { }\n''',
                    '''        public void Dispose()\n        {\n            disposed = true;\n            try { cancellation.Cancel(); } catch { }\n''',
                    'connection dispose flag')
new_host = r'''    internal static class RendererHudHost
    {
        private const int RetryDelayMilliseconds = 750;
        internal const int EndpointFailureExitThreshold = 12;

        internal static bool ShouldExitForLifetime(bool ownerExited, int consecutiveEndpointFailures)
        {
            return ownerExited || consecutiveEndpointFailures >= EndpointFailureExitThreshold;
        }

        private static bool OwnerExited(Process owner)
        {
            if (owner == null)
                return true;
            try { return owner.HasExited; }
            catch { return true; }
        }

        internal static int Run(int port, int browserProcessId)
        {
            if (browserProcessId <= 0)
                return 2;

            Process owner;
            try { owner = Process.GetProcessById(browserProcessId); }
            catch { return 0; }

            using (owner)
            {
                bool created;
                using (Mutex mutex = new Mutex(true, "Local\\CodexSessionHealthHUD.Renderer." + port, out created))
                {
                    if (!created)
                        return 0;

                    string runId = Guid.NewGuid().ToString("N");
                    HudStateStore stateStore = new HudStateStore(runId);
                    string script = RendererHudScript.Load();
                    int consecutiveEndpointFailures = 0;

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
                }
            }
        }
    }
'''
text = sub_once(text,
                r'    internal static class RendererHudHost\n    \{.*?\n    \}\n(?=\})',
                new_host,
                'renderer host lifetime')
path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# State store: keep normal writes event-driven, but make hard caps evict old /
# low-value entries instead of silently stopping persistence. Invalid capture
# times are not invented or retained.
# ---------------------------------------------------------------------------
path = Path('HudStateStore.cs')
text = path.read_text(encoding='utf-8')
old_constants = '''        private const int SchemaVersion = 1;
        private const long MaximumStateFileBytes = 4L * 1024L * 1024L;
        private const int MaximumThreadEntries = 10000;
        private const string StateMutexName = "Local\\\\CodexSessionHealthHUD.State";

        private readonly object gate = new object();
        private readonly string statePath;
        private readonly string runId;
        private readonly JavaScriptSerializer serializer;
        private HudPersistentState state;
'''
new_constants = '''        private const int SchemaVersion = 1;
        private const long MaximumStateFileBytes = 4L * 1024L * 1024L;
        private const long MaximumReadStateFileBytes = 8L * 1024L * 1024L;
        private const int MaximumThreadEntries = 10000;
        private const string StateMutexName = "Local\\\\CodexSessionHealthHUD.State";

        private readonly object gate = new object();
        private readonly string statePath;
        private readonly string runId;
        private readonly int maximumThreadEntries;
        private readonly long maximumStateFileBytes;
        private readonly long maximumReadStateFileBytes;
        private readonly JavaScriptSerializer serializer;
        private HudPersistentState state;
'''
text = replace_once(text, old_constants, new_constants, 'state limits fields')
old_ctors = '''        internal HudStateStore(string runId)
            : this(DefaultStatePath(), runId)
        {
        }

        internal HudStateStore(string statePath, string runId)
        {
            this.statePath = statePath;
            this.runId = string.IsNullOrWhiteSpace(runId) ? Guid.NewGuid().ToString("N") : runId;
            serializer = new JavaScriptSerializer();
            serializer.MaxJsonLength = 8 * 1024 * 1024;
            serializer.RecursionLimit = 64;
            state = Load();
            if (InvalidateForeignPendingMeasurements())
                SaveLocked();
        }
'''
new_ctors = '''        internal HudStateStore(string runId)
            : this(DefaultStatePath(), runId)
        {
        }

        internal HudStateStore(string statePath, string runId)
            : this(statePath, runId, MaximumThreadEntries, MaximumStateFileBytes, MaximumReadStateFileBytes)
        {
        }

        internal HudStateStore(string statePath, string runId, int maximumThreadEntries, long maximumStateFileBytes)
            : this(statePath, runId, maximumThreadEntries, maximumStateFileBytes,
                Math.Max(maximumStateFileBytes * 2L, maximumStateFileBytes + 65536L))
        {
        }

        private HudStateStore(string statePath, string runId, int maximumThreadEntries,
            long maximumStateFileBytes, long maximumReadStateFileBytes)
        {
            this.statePath = statePath;
            this.runId = string.IsNullOrWhiteSpace(runId) ? Guid.NewGuid().ToString("N") : runId;
            this.maximumThreadEntries = Math.Max(1, maximumThreadEntries);
            this.maximumStateFileBytes = Math.Max(512L, maximumStateFileBytes);
            this.maximumReadStateFileBytes = Math.Max(this.maximumStateFileBytes, maximumReadStateFileBytes);
            serializer = new JavaScriptSerializer();
            serializer.MaxJsonLength = 8 * 1024 * 1024;
            serializer.RecursionLimit = 64;
            state = Load();
            bool changed = TrimToLimits(null);
            if (InvalidateForeignPendingMeasurements())
                changed = true;
            if (changed)
                SaveLocked();
        }
'''
text = replace_once(text, old_ctors, new_ctors, 'state constructors')
old_apply = '''            lock (gate)
            {
                if (state.threads.Count >= MaximumThreadEntries && !state.threads.ContainsKey(threadId))
                    return;
                state.threads[threadId] = next;
                SaveLocked();
            }
'''
new_apply = '''            lock (gate)
            {
                state.threads[threadId] = next;
                TrimToLimits(threadId);
                SaveLocked();
            }
'''
text = replace_once(text, old_apply, new_apply, 'state apply eviction')
text = replace_once(text,
                    '''                if (file.Length <= 0 || file.Length > MaximumStateFileBytes)\n                {\n                    Quarantine("oversized");\n                    return new HudPersistentState();\n                }\n''',
                    '''                if (file.Length <= 0 || file.Length > maximumReadStateFileBytes)\n                {\n                    Quarantine("oversized");\n                    return new HudPersistentState();\n                }\n''',
                    'state read safety limit')
text = replace_once(text,
                    '''                foreach (KeyValuePair<string, HudThreadState> pair in loaded.threads)\n                {\n                    if (sanitized.Count >= MaximumThreadEntries)\n                        break;\n                    if (!IsSafeIdentifier(pair.Key) || pair.Value == null)\n''',
                    '''                foreach (KeyValuePair<string, HudThreadState> pair in loaded.threads)\n                {\n                    if (!IsSafeIdentifier(pair.Key) || pair.Value == null)\n''',
                    'load all bounded input before eviction')
text = replace_once(text,
                    '''            if (!string.Equals(item.postCompactionStatus, "measuring", StringComparison.Ordinal))\n                item.captureRunId = null;\n            return item;\n''',
                    '''            if (!string.Equals(item.postCompactionStatus, "measuring", StringComparison.Ordinal))\n                item.captureRunId = null;\n            DateTimeOffset captured;\n            if (!string.IsNullOrWhiteSpace(item.capturedAt) && !TryCapturedAt(item, out captured))\n                item.capturedAt = null;\n            return item;\n''',
                    'capture timestamp sanitization')
insert_before_save = '''        private static bool TryCapturedAt(HudThreadState item, out DateTimeOffset value)
        {
            value = default(DateTimeOffset);
            return item != null && !string.IsNullOrWhiteSpace(item.capturedAt) &&
                DateTimeOffset.TryParse(item.capturedAt, CultureInfo.InvariantCulture,
                    DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out value);
        }

        private static int RetentionRank(HudThreadState item)
        {
            if (item == null)
                return 0;
            if (string.Equals(item.postCompactionStatus, "ready", StringComparison.Ordinal))
            {
                DateTimeOffset captured;
                return TryCapturedAt(item, out captured) ? 3 : 2;
            }
            if (string.Equals(item.postCompactionStatus, "measuring", StringComparison.Ordinal))
                return 1;
            return 0;
        }

        private List<KeyValuePair<string, HudThreadState>> EvictionCandidates(string protectedThreadId)
        {
            List<KeyValuePair<string, HudThreadState>> candidates =
                new List<KeyValuePair<string, HudThreadState>>();
            foreach (KeyValuePair<string, HudThreadState> pair in state.threads)
            {
                if (!string.IsNullOrEmpty(protectedThreadId) &&
                    string.Equals(pair.Key, protectedThreadId, StringComparison.Ordinal))
                    continue;
                candidates.Add(pair);
            }
            candidates.Sort(delegate(KeyValuePair<string, HudThreadState> left,
                KeyValuePair<string, HudThreadState> right)
            {
                int rank = RetentionRank(left.Value).CompareTo(RetentionRank(right.Value));
                if (rank != 0)
                    return rank;
                DateTimeOffset leftTime;
                DateTimeOffset rightTime;
                bool leftHas = TryCapturedAt(left.Value, out leftTime);
                bool rightHas = TryCapturedAt(right.Value, out rightTime);
                if (leftHas && rightHas)
                {
                    int time = leftTime.CompareTo(rightTime);
                    if (time != 0)
                        return time;
                }
                else if (leftHas != rightHas)
                {
                    return leftHas ? 1 : -1;
                }
                return string.CompareOrdinal(left.Key, right.Key);
            });
            return candidates;
        }

        private bool TrimToLimits(string protectedThreadId)
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
text = replace_once(text, '        private void SaveLocked()\n', insert_before_save + '        private void SaveLocked()\n', 'state eviction helpers')
text = replace_once(text,
                    '            if (Encoding.UTF8.GetByteCount(json) > MaximumStateFileBytes)\n',
                    '            if (Encoding.UTF8.GetByteCount(json) > maximumStateFileBytes)\n',
                    'state save byte limit')
path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Launcher: identify Codex from the Store package path, validate the owner of
# the DevTools listener, and pass that owner PID to the HUD host.
# ---------------------------------------------------------------------------
path = Path('Launch-CodexWithSessionHealthHUD.ps1')
text = path.read_text(encoding='utf-8')
old_package_fn = r'''function Get-CodexAppUserModelId {
    $package = Get-AppxPackage -Name 'OpenAI.Codex' -ErrorAction SilentlyContinue |
        Sort-Object Version -Descending | Select-Object -First 1
    if (-not $package) { throw 'Microsoft Store Codex Desktop was not found.' }
    if ([string]::IsNullOrWhiteSpace($package.InstallLocation)) {
        throw 'Codex Desktop is installed, but Windows did not expose its package install location.'
    }
    $manifestPath = Join-Path $package.InstallLocation 'AppxManifest.xml'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Codex AppxManifest.xml is unavailable.' }
    [xml]$manifest = Get-Content -LiteralPath $manifestPath -Raw
    $application = $manifest.SelectSingleNode("/*[local-name()='Package']/*[local-name()='Applications']/*[local-name()='Application'][1]")
    if (-not $application -or -not $application.Id) { throw 'Could not read the Codex application identifier.' }
    return "$($package.PackageFamilyName)!$($application.Id)"
}
'''
new_package_fn = r'''function Get-CodexPackage {
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
    return ([IO.Path]::GetFullPath($Package.InstallLocation).TrimEnd('\\') + '\\')
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

function Get-ProcessByIdCim {
    param([uint32]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue |
        Select-Object -First 1
}
'''
text = replace_once(text, old_package_fn, new_package_fn, 'launcher package identity helpers')
new_try = r'''try {
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
'''
text = sub_once(text, r'try \{\n    \$hudExe = Join-Path \$InstallDir.*\Z', new_try, 'launcher main flow')
path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Install/uninstall safety. Avoid a manifest: reject non-empty unowned custom
# directories up front, and uninstall only known HUD-owned files.
# ---------------------------------------------------------------------------
path = Path('Install.ps1')
text = path.read_text(encoding='utf-8')
safety = r'''
$marker = Join-Path $InstallDir '.install-marker'
if (Test-Path -LiteralPath $InstallDir -PathType Container) {
    $existingEntries = @(Get-ChildItem -LiteralPath $InstallDir -Force -ErrorAction Stop)
    if ($existingEntries.Count -gt 0) {
        if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) {
            throw "InstallDir is not empty and is not a marked Codex Session Health HUD installation: $InstallDir"
        }
        $markerValue = (Get-Content -LiteralPath $marker -Raw).Trim()
        if ($markerValue -ne 'CodexSessionHealthHUD|v1') {
            throw 'InstallDir contains an unrecognized installation marker.'
        }
    }
}

'''
text = replace_once(text, "$InstallDir = [IO.Path]::GetFullPath($InstallDir)\n\n", "$InstallDir = [IO.Path]::GetFullPath($InstallDir)\n" + safety, 'installer directory ownership check')
text = replace_once(text, "$marker = Join-Path $InstallDir '.install-marker'\n", '', 'remove duplicate installer marker')
# The previous replacement removes the first occurrence if the injected marker also matches;
# restore exactly one marker declaration immediately after InstallDir normalization if needed.
if "$marker = Join-Path $InstallDir '.install-marker'" not in text:
    text = text.replace("$InstallDir = [IO.Path]::GetFullPath($InstallDir)\n", "$InstallDir = [IO.Path]::GetFullPath($InstallDir)\n$marker = Join-Path $InstallDir '.install-marker'\n", 1)
path.write_text(text, encoding='utf-8')

path = Path('Uninstall.ps1')
path.write_text(r'''[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'CodexSessionHealthHUD'),
    [switch]$NoShortcuts
)

$ErrorActionPreference = 'Stop'
$fullInstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\\')
$marker = Join-Path $fullInstallDir '.install-marker'
$targetExe = Join-Path $fullInstallDir 'CodexSessionHealthHUD.exe'
$programsDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Codex Session Health HUD'
$launcherShortcut = Join-Path $programsDir 'Codex with Session Health HUD.lnk'
$taskbarShortcut = Join-Path $env:APPDATA `
    'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Codex with Session Health HUD.lnk'

if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw "Install marker not found: $marker" }
$markerValue = (Get-Content -LiteralPath $marker -Raw).Trim()
if ($markerValue -ne 'CodexSessionHealthHUD|v1') { throw 'Install marker did not match this application.' }

$driveRoot = [IO.Path]::GetPathRoot($fullInstallDir).TrimEnd('\\')
$userProfile = [IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\\')
$localAppData = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\\')
if ($fullInstallDir -eq $driveRoot -or $fullInstallDir -eq $userProfile -or $fullInstallDir -eq $localAppData) {
    throw "Refusing to modify unsafe path: $fullInstallDir"
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

if (-not $NoShortcuts) {
    foreach ($shortcutPath in @($launcherShortcut, $taskbarShortcut)) {
        if (Test-Path -LiteralPath $shortcutPath) {
            try { Remove-Item -LiteralPath $shortcutPath -Force } catch { }
        }
    }
    if (Test-Path -LiteralPath $programsDir) {
        try { Remove-Item -LiteralPath $programsDir -Recurse -Force } catch { }
    }
}

$ownedFiles = @(
    'CodexSessionHealthHUD.exe',
    'Launch-CodexWithSessionHealthHUD.ps1',
    'Uninstall.ps1',
    'README.md',
    'README.ko.md',
    'CHANGELOG.md',
    'LICENSE',
    'THIRD_PARTY_NOTICES.md',
    'Codex.ico',
    'state.json'
)
foreach ($relativePath in $ownedFiles) {
    $path = Join-Path $fullInstallDir $relativePath
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        try { Remove-Item -LiteralPath $path -Force } catch { }
    }
}

foreach ($pattern in @('state.corrupt.*.json', 'state.oversized.*.json', 'state.unsupported.*.json', 'state.json.tmp-*')) {
    Get-ChildItem -LiteralPath $fullInstallDir -File -Filter $pattern -ErrorAction SilentlyContinue |
        ForEach-Object { try { Remove-Item -LiteralPath $_.FullName -Force } catch { } }
}

$assetPath = Join-Path $fullInstallDir 'assets\\hud-composer.svg'
if (Test-Path -LiteralPath $assetPath -PathType Leaf) {
    try { Remove-Item -LiteralPath $assetPath -Force } catch { }
}
$assetsDir = Join-Path $fullInstallDir 'assets'
if (Test-Path -LiteralPath $assetsDir -PathType Container) {
    try {
        if (@(Get-ChildItem -LiteralPath $assetsDir -Force).Count -eq 0) {
            Remove-Item -LiteralPath $assetsDir -Force
        }
    } catch { }
}

# Remove the ownership marker last. Never recursively delete InstallDir: a custom
# install directory may contain unrelated user files from before this safeguard.
if (Test-Path -LiteralPath $marker -PathType Leaf) {
    Remove-Item -LiteralPath $marker -Force
}

try {
    $currentDirectory = [IO.Path]::GetFullPath((Get-Location).Path).TrimEnd('\\')
    if ($currentDirectory.StartsWith($fullInstallDir + '\\', [StringComparison]::OrdinalIgnoreCase) -or
        $currentDirectory -eq $fullInstallDir) {
        Set-Location -LiteralPath ([IO.Path]::GetTempPath())
    }
} catch { }

if (Test-Path -LiteralPath $fullInstallDir -PathType Container) {
    try {
        if (@(Get-ChildItem -LiteralPath $fullInstallDir -Force).Count -eq 0) {
            Remove-Item -LiteralPath $fullInstallDir -Force
        }
    } catch { }
}

Write-Host 'Codex Session Health HUD files and state were removed. Codex data and unrelated files were not modified.'
''', encoding='utf-8')


# ---------------------------------------------------------------------------
# Process-level Windows lifecycle and install-safety regression tests.
# ---------------------------------------------------------------------------
Path('tests/host-lifecycle.test.ps1').write_text(r'''[CmdletBinding()]
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
    if (-not $hud.WaitForExit(14000)) { throw 'HUD did not exit after sustained endpoint loss.' }
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
''', encoding='utf-8')

Path('tests/install-safety.test.ps1').write_text(r'''[CmdletBinding()]
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
''', encoding='utf-8')


# Static package-layout safeguards for the new launcher/uninstaller behavior.
path = Path('tests/package-layout.test.ps1')
text = path.read_text(encoding='utf-8')
needle = '''    if ($launcher -match '\\[string\\]\\$InstallDir\\s*=\\s*\\(\\s*Join-Path\\s+\\$PSScriptRoot') {
        throw 'Launcher regressed to evaluating $PSScriptRoot in a parameter default.'
    }

    $installer = Get-Content -LiteralPath (Join-Path $stage 'Install.ps1') -Raw
'''
replacement = '''    if ($launcher -match '\\[string\\]\\$InstallDir\\s*=\\s*\\(\\s*Join-Path\\s+\\$PSScriptRoot') {
        throw 'Launcher regressed to evaluating $PSScriptRoot in a parameter default.'
    }
    if ($launcher.IndexOf('OwningProcess', [StringComparison]::Ordinal) -lt 0 -or
        $launcher.IndexOf('Test-IsCodexProcess', [StringComparison]::Ordinal) -lt 0) {
        throw 'Launcher no longer validates the Codex-owned DevTools listener process.'
    }

    $installer = Get-Content -LiteralPath (Join-Path $stage 'Install.ps1') -Raw
'''
text = replace_once(text, needle, replacement, 'package launcher identity checks')
needle2 = '''    if ($installer -notmatch '\\$shortcut\\.Arguments\\s*=.*-InstallDir') {
        throw 'Start menu shortcut does not pass InstallDir explicitly.'
    }

    $readmeAsset = Get-Content -LiteralPath (Join-Path $stage 'assets\\hud-composer.svg') -Raw
'''
replacement2 = '''    if ($installer -notmatch '\\$shortcut\\.Arguments\\s*=.*-InstallDir') {
        throw 'Start menu shortcut does not pass InstallDir explicitly.'
    }
    if ($installer.IndexOf('InstallDir is not empty and is not a marked', [StringComparison]::Ordinal) -lt 0) {
        throw 'Installer no longer rejects non-empty unowned custom install directories.'
    }

    $uninstaller = Get-Content -LiteralPath (Join-Path $stage 'Uninstall.ps1') -Raw
    if ($uninstaller -match 'Remove-Item\\s+-LiteralPath\\s+\\$fullInstallDir\\s+-Recurse') {
        throw 'Uninstaller regressed to recursively deleting the entire install directory.'
    }
    if ($uninstaller.IndexOf('unrelated files were not modified', [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw 'Uninstaller no longer documents preservation of unrelated files.'
    }

    $readmeAsset = Get-Content -LiteralPath (Join-Path $stage 'assets\\hud-composer.svg') -Raw
'''
text = replace_once(text, needle2, replacement2, 'package install/uninstall checks')
path.write_text(text, encoding='utf-8')


# Permanent CI gates for the new process-level tests.
path = Path('.github/workflows/ci.yml')
text = path.read_text(encoding='utf-8')
needle = '''      - name: Build and run self-tests
        shell: pwsh
        run: .\\Build.ps1

      - name: Create Windows package
'''
replacement = '''      - name: Build and run self-tests
        shell: pwsh
        run: .\\Build.ps1

      - name: Test host lifecycle
        shell: pwsh
        run: .\\tests\\host-lifecycle.test.ps1

      - name: Test install safety
        shell: pwsh
        run: .\\tests\\install-safety.test.ps1

      - name: Create Windows package
'''
text = replace_once(text, needle, replacement, 'CI lifecycle safety tests')
path.write_text(text, encoding='utf-8')

print('core hardening patch applied')
