using System;
using System.Collections.Generic;
using System.IO;

namespace CodexSessionHealthHUD
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            try
            {
                if (args != null && args.Length >= 3 &&
                    string.Equals(args[0], "--renderer-attach", StringComparison.OrdinalIgnoreCase))
                {
                    int port;
                    int browserProcessId;
                    if (!int.TryParse(args[1], out port) || port < 1024 || port > 65535 ||
                        !int.TryParse(args[2], out browserProcessId) || browserProcessId <= 0)
                        return 2;
                    return RendererHudHost.Run(port, browserProcessId);
                }

                if (args != null && args.Length >= 2 &&
                    string.Equals(args[0], "--self-test", StringComparison.OrdinalIgnoreCase))
                {
                    return SelfTest.Run(args[1]);
                }

                if (args != null && args.Length >= 2 &&
                    string.Equals(args[0], "--renderer-self-test", StringComparison.OrdinalIgnoreCase))
                {
                    return RendererSelfTest.Run(args[1]);
                }

                return 2;
            }
            catch (Exception)
            {
                return 1;
            }
        }
    }

    internal static class SelfTest
    {
        internal static int Run(string outputPath)
        {
            string root = Path.Combine(Path.GetTempPath(), "CodexSessionHealthHUD-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            try
            {
                string statePath = Path.Combine(root, "state.json");
                string runA = "run-a";
                HudStateStore storeA = new HudStateStore(statePath, runA);
                storeA.ApplyRendererPayload(
                    "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-1\",\"state\":{\"lastObservedCompactionId\":\"cmp-1\",\"compactionCount\":1,\"snapshotCompactionId\":\"cmp-1\",\"postCompactionStatus\":\"measuring\",\"postCompactionTokens\":null,\"postCompactionWindow\":null,\"captureRunId\":\"run-a\",\"capturedAt\":null}}"
                );

                HudStateStore storeB = new HudStateStore(statePath, "run-b");
                string bootstrap = storeB.GetBootstrapJson();
                if (bootstrap.IndexOf("notCaptured", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("Pending measurements were not invalidated across runs.");

                storeB.ApplyRendererPayload(
                    "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-1\",\"state\":{\"lastObservedCompactionId\":\"cmp-1\",\"compactionCount\":1,\"snapshotCompactionId\":\"cmp-1\",\"postCompactionStatus\":\"ready\",\"postCompactionTokens\":103184,\"postCompactionWindow\":258400,\"captureRunId\":null,\"capturedAt\":\"2026-09-03T00:00:00Z\"}}"
                );
                bootstrap = storeB.GetBootstrapJson();
                if (bootstrap.IndexOf("103184", StringComparison.Ordinal) < 0 ||
                    bootstrap.IndexOf("258400", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("Ready snapshot did not persist.");

                if (!RendererHudHost.ShouldExitForLifetime(true, 0) ||
                    RendererHudHost.ShouldExitForLifetime(false, RendererHudHost.EndpointFailureExitThreshold - 1) ||
                    !RendererHudHost.ShouldExitForLifetime(false, RendererHudHost.EndpointFailureExitThreshold))
                    throw new InvalidOperationException("Host lifetime policy regression.");
                if (RendererHudHost.ShouldExitForTargetState(RendererHudHost.TargetMissingExitThreshold - 1, 0) ||
                    !RendererHudHost.ShouldExitForTargetState(RendererHudHost.TargetMissingExitThreshold, 0) ||
                    RendererHudHost.ShouldExitForTargetState(0, RendererHudHost.AttachFailureExitThreshold - 1) ||
                    !RendererHudHost.ShouldExitForTargetState(0, RendererHudHost.AttachFailureExitThreshold))
                    throw new InvalidOperationException("Host target/attach lifetime policy regression.");

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
                    "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-low\",\"state\":{\"compactionCount\":0,\"postCompactionStatus\":\"noCompaction\"}}"
                );
                bounded.ApplyRendererPayload(
                    "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-old\",\"state\":{\"lastObservedCompactionId\":\"old\",\"compactionCount\":1,\"snapshotCompactionId\":\"old\",\"postCompactionStatus\":\"ready\",\"postCompactionTokens\":1000,\"postCompactionWindow\":10000,\"capturedAt\":\"2026-01-01T00:00:00Z\"}}"
                );
                bounded.ApplyRendererPayload(
                    "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-new\",\"state\":{\"lastObservedCompactionId\":\"new\",\"compactionCount\":2,\"snapshotCompactionId\":\"new\",\"postCompactionStatus\":\"ready\",\"postCompactionTokens\":2000,\"postCompactionWindow\":10000,\"capturedAt\":\"2026-09-01T00:00:00Z\"}}"
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
                        "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-byte-" + i.ToString() +
                        "\",\"state\":{\"compactionCount\":0,\"postCompactionStatus\":\"noCompaction\"}}"
                    );
                }
                if (!File.Exists(bytesPath) || new FileInfo(bytesPath).Length > 900)
                    throw new InvalidOperationException("State byte limit was not enforced.");
                if (byteBounded.GetBootstrapJson().IndexOf("thread-byte-7", StringComparison.Ordinal) < 0)
                    throw new InvalidOperationException("Newest protected state was evicted while enforcing byte limit.");

                HudStateStore timestampStore = new HudStateStore(Path.Combine(root, "timestamp-state.json"), "run-time");
                timestampStore.ApplyRendererPayload(
                    "{\"action\":\"upsertThreadState\",\"threadId\":\"thread-time\",\"state\":{\"lastObservedCompactionId\":\"time\",\"compactionCount\":1,\"snapshotCompactionId\":\"time\",\"postCompactionStatus\":\"ready\",\"postCompactionTokens\":1000,\"postCompactionWindow\":10000,\"capturedAt\":\"not-a-date\"}}"
                );
                if (timestampStore.GetBootstrapJson().IndexOf("not-a-date", StringComparison.Ordinal) >= 0)
                    throw new InvalidOperationException("Invalid capture timestamps were not sanitized.");

                File.WriteAllText(outputPath, "state-store: ok" + Environment.NewLine);
                return 0;
            }
            catch (Exception ex)
            {
                File.WriteAllText(outputPath, "state-store: failed" + Environment.NewLine + ex.ToString());
                return 1;
            }
            finally
            {
                try { Directory.Delete(root, true); } catch { }
            }
        }
    }

    internal static class RendererSelfTest
    {
        internal static int Run(string outputPath)
        {
            try
            {
                string script = RendererHudScript.Load();
                string[] required = new string[] {
                    "thread/tokenUsage/updated",
                    "account/rateLimits/updated",
                    "contextCompaction",
                    "Post-compaction context",
                    "Codex Session Health HUD",
                    "__codexSessionHealthHudPersist",
                    "thread/items/list"
                };
                for (int i = 0; i < required.Length; i++)
                {
                    if (script.IndexOf(required[i], StringComparison.Ordinal) < 0)
                        throw new InvalidOperationException("Renderer script is missing: " + required[i]);
                }
                File.WriteAllText(outputPath, "renderer-script: ok" + Environment.NewLine);
                return 0;
            }
            catch (Exception ex)
            {
                File.WriteAllText(outputPath, "renderer-script: failed" + Environment.NewLine + ex.ToString());
                return 1;
            }
        }
    }
}
