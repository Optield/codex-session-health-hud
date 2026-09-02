using System;
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
                if (args != null && args.Length >= 2 &&
                    string.Equals(args[0], "--renderer-attach", StringComparison.OrdinalIgnoreCase))
                {
                    int port;
                    if (!int.TryParse(args[1], out port) || port < 1024 || port > 65535)
                        return 2;
                    return RendererHudHost.Run(port);
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
