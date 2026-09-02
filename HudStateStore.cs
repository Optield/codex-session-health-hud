using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace CodexSessionHealthHUD
{
    public sealed class HudThreadState
    {
        public string lastObservedCompactionId { get; set; }
        public int compactionCount { get; set; }
        public string snapshotCompactionId { get; set; }
        public string postCompactionStatus { get; set; }
        public long? postCompactionTokens { get; set; }
        public long? postCompactionWindow { get; set; }
        public string captureRunId { get; set; }
        public string capturedAt { get; set; }

        public HudThreadState()
        {
            compactionCount = -1;
            postCompactionStatus = "syncing";
        }
    }

    public sealed class HudPersistentState
    {
        public int schemaVersion { get; set; }
        public Dictionary<string, HudThreadState> threads { get; set; }

        public HudPersistentState()
        {
            schemaVersion = 1;
            threads = new Dictionary<string, HudThreadState>(StringComparer.Ordinal);
        }
    }

    internal sealed class HudStateStore
    {
        private const int SchemaVersion = 1;
        private const long MaximumStateFileBytes = 4L * 1024L * 1024L;
        private const int MaximumThreadEntries = 10000;
        private const string StateMutexName = "Local\\CodexSessionHealthHUD.State";

        private readonly object gate = new object();
        private readonly string statePath;
        private readonly string runId;
        private readonly JavaScriptSerializer serializer;
        private HudPersistentState state;

        internal HudStateStore(string runId)
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

        internal string GetBootstrapJson()
        {
            lock (gate)
            {
                Dictionary<string, object> bootstrap = new Dictionary<string, object>();
                bootstrap["runId"] = runId;
                bootstrap["schemaVersion"] = SchemaVersion;
                bootstrap["threads"] = state.threads;
                return serializer.Serialize(bootstrap);
            }
        }

        internal void ApplyRendererPayload(string payload)
        {
            if (string.IsNullOrWhiteSpace(payload) || payload.Length > 32768)
                return;

            IDictionary<string, object> root;
            try
            {
                root = serializer.DeserializeObject(payload) as IDictionary<string, object>;
            }
            catch
            {
                return;
            }
            if (root == null)
                return;

            string action = ReadString(root, "action", 64);
            if (!string.Equals(action, "upsertThreadState", StringComparison.Ordinal))
                return;

            string threadId = ReadString(root, "threadId", 256);
            if (!IsSafeIdentifier(threadId))
                return;

            object rawState;
            IDictionary<string, object> stateMap;
            if (!root.TryGetValue("state", out rawState) ||
                (stateMap = rawState as IDictionary<string, object>) == null)
                return;

            HudThreadState next = ParseThreadState(stateMap);
            if (next == null)
                return;

            lock (gate)
            {
                if (state.threads.Count >= MaximumThreadEntries && !state.threads.ContainsKey(threadId))
                    return;
                state.threads[threadId] = next;
                SaveLocked();
            }
        }

        private HudPersistentState Load()
        {
            try
            {
                FileInfo file = new FileInfo(statePath);
                if (!file.Exists)
                    return new HudPersistentState();
                if (file.Length <= 0 || file.Length > MaximumStateFileBytes)
                {
                    Quarantine("oversized");
                    return new HudPersistentState();
                }

                string json = File.ReadAllText(statePath, Encoding.UTF8);
                HudPersistentState loaded = serializer.Deserialize<HudPersistentState>(json);
                if (loaded == null || loaded.schemaVersion != SchemaVersion || loaded.threads == null)
                {
                    Quarantine("unsupported");
                    return new HudPersistentState();
                }

                Dictionary<string, HudThreadState> sanitized =
                    new Dictionary<string, HudThreadState>(StringComparer.Ordinal);
                foreach (KeyValuePair<string, HudThreadState> pair in loaded.threads)
                {
                    if (sanitized.Count >= MaximumThreadEntries)
                        break;
                    if (!IsSafeIdentifier(pair.Key) || pair.Value == null)
                        continue;
                    HudThreadState item = SanitizeThreadState(pair.Value);
                    sanitized[pair.Key] = item;
                }
                loaded.threads = sanitized;
                return loaded;
            }
            catch
            {
                Quarantine("corrupt");
                return new HudPersistentState();
            }
        }

        private bool InvalidateForeignPendingMeasurements()
        {
            bool changed = false;
            foreach (HudThreadState item in state.threads.Values)
            {
                if (item == null || !string.Equals(item.postCompactionStatus, "measuring", StringComparison.Ordinal))
                    continue;
                if (string.Equals(item.captureRunId, runId, StringComparison.Ordinal))
                    continue;

                item.postCompactionStatus = "notCaptured";
                item.postCompactionTokens = null;
                item.postCompactionWindow = null;
                item.captureRunId = null;
                item.capturedAt = null;
                changed = true;
            }
            return changed;
        }

        private HudThreadState ParseThreadState(IDictionary<string, object> map)
        {
            HudThreadState item = new HudThreadState();
            item.lastObservedCompactionId = ReadString(map, "lastObservedCompactionId", 256);
            item.compactionCount = ReadInt(map, "compactionCount", -1, 1000000, -1);
            item.snapshotCompactionId = ReadString(map, "snapshotCompactionId", 256);
            item.postCompactionStatus = ReadString(map, "postCompactionStatus", 32);
            item.postCompactionTokens = ReadNullableLong(map, "postCompactionTokens", 0, 2000000000L);
            item.postCompactionWindow = ReadNullableLong(map, "postCompactionWindow", 1, 2000000000L);
            item.captureRunId = ReadString(map, "captureRunId", 128);
            item.capturedAt = ReadString(map, "capturedAt", 64);
            return SanitizeThreadState(item);
        }

        private static HudThreadState SanitizeThreadState(HudThreadState item)
        {
            if (!IsAllowedStatus(item.postCompactionStatus))
                item.postCompactionStatus = "syncing";
            if (!IsSafeOptionalIdentifier(item.lastObservedCompactionId))
                item.lastObservedCompactionId = null;
            if (!IsSafeOptionalIdentifier(item.snapshotCompactionId))
                item.snapshotCompactionId = null;
            if (item.compactionCount < -1)
                item.compactionCount = -1;
            if (item.compactionCount > 1000000)
                item.compactionCount = 1000000;
            if (item.postCompactionTokens.HasValue && item.postCompactionTokens.Value < 0)
                item.postCompactionTokens = null;
            if (item.postCompactionWindow.HasValue && item.postCompactionWindow.Value <= 0)
                item.postCompactionWindow = null;

            if (!string.Equals(item.postCompactionStatus, "ready", StringComparison.Ordinal))
            {
                item.postCompactionTokens = null;
                item.postCompactionWindow = null;
                item.capturedAt = null;
            }
            if (!string.Equals(item.postCompactionStatus, "measuring", StringComparison.Ordinal))
                item.captureRunId = null;
            return item;
        }

        private void SaveLocked()
        {
            string directory = Path.GetDirectoryName(statePath);
            if (string.IsNullOrWhiteSpace(directory))
                return;
            Directory.CreateDirectory(directory);

            string json = serializer.Serialize(state);
            if (Encoding.UTF8.GetByteCount(json) > MaximumStateFileBytes)
                return;

            using (Mutex mutex = new Mutex(false, StateMutexName))
            {
                bool entered = false;
                try
                {
                    try { entered = mutex.WaitOne(TimeSpan.FromSeconds(2)); }
                    catch (AbandonedMutexException) { entered = true; }
                    if (!entered)
                        return;

                    string temp = statePath + ".tmp-" + Process.GetCurrentProcess().Id.ToString(CultureInfo.InvariantCulture) +
                        "-" + Guid.NewGuid().ToString("N");
                    try
                    {
                        using (FileStream stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                        using (StreamWriter writer = new StreamWriter(stream, new UTF8Encoding(false)))
                        {
                            writer.Write(json);
                            writer.Flush();
                            stream.Flush(true);
                        }

                        if (File.Exists(statePath))
                        {
                            try { File.Replace(temp, statePath, null); }
                            catch { try { File.Delete(temp); } catch { } }
                        }
                        else
                        {
                            File.Move(temp, statePath);
                        }
                    }
                    finally
                    {
                        try
                        {
                            string[] leftovers = Directory.GetFiles(directory, Path.GetFileName(statePath) + ".tmp-*");
                            for (int i = 0; i < leftovers.Length; i++)
                            {
                                try { File.Delete(leftovers[i]); } catch { }
                            }
                        }
                        catch { }
                    }
                }
                catch { }
                finally
                {
                    if (entered)
                    {
                        try { mutex.ReleaseMutex(); } catch { }
                    }
                }
            }
        }

        private void Quarantine(string reason)
        {
            try
            {
                if (!File.Exists(statePath))
                    return;
                string directory = Path.GetDirectoryName(statePath);
                string fileName = "state." + reason + "." + DateTime.UtcNow.ToString("yyyyMMddHHmmss", CultureInfo.InvariantCulture) + ".json";
                string target = Path.Combine(directory, fileName);
                File.Move(statePath, target);
            }
            catch { }
        }

        private static string DefaultStatePath()
        {
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "state.json");
        }

        private static bool IsAllowedStatus(string value)
        {
            return value == "syncing" || value == "noCompaction" || value == "measuring" ||
                value == "notCaptured" || value == "ready" || value == "unavailable";
        }

        private static bool IsSafeIdentifier(string value)
        {
            return !string.IsNullOrWhiteSpace(value) && value.Length <= 256 && value.IndexOf('\0') < 0;
        }

        private static bool IsSafeOptionalIdentifier(string value)
        {
            return string.IsNullOrEmpty(value) || IsSafeIdentifier(value);
        }

        private static string ReadString(IDictionary<string, object> map, string key, int maximumLength)
        {
            object raw;
            if (!map.TryGetValue(key, out raw) || raw == null)
                return null;
            string value = Convert.ToString(raw, CultureInfo.InvariantCulture);
            if (string.IsNullOrWhiteSpace(value) || value.Length > maximumLength || value.IndexOf('\0') >= 0)
                return null;
            return value;
        }

        private static int ReadInt(IDictionary<string, object> map, string key, int minimum, int maximum, int fallback)
        {
            object raw;
            int value;
            if (!map.TryGetValue(key, out raw) || raw == null ||
                !int.TryParse(Convert.ToString(raw, CultureInfo.InvariantCulture), NumberStyles.Integer,
                    CultureInfo.InvariantCulture, out value))
                return fallback;
            if (value < minimum || value > maximum)
                return fallback;
            return value;
        }

        private static long? ReadNullableLong(IDictionary<string, object> map, string key, long minimum, long maximum)
        {
            object raw;
            long value;
            if (!map.TryGetValue(key, out raw) || raw == null)
                return null;
            if (!long.TryParse(Convert.ToString(raw, CultureInfo.InvariantCulture), NumberStyles.Integer,
                CultureInfo.InvariantCulture, out value))
                return null;
            if (value < minimum || value > maximum)
                return null;
            return value;
        }
    }
}
