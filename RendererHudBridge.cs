using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

namespace CodexSessionHealthHUD
{
    internal static class RendererHudScript
    {
        internal const string ResourceName = "CodexSessionHealthHUD.RendererHudScript.js";

        internal static string Load()
        {
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream stream = assembly.GetManifestResourceStream(ResourceName))
            {
                if (stream == null)
                    throw new InvalidOperationException("Renderer HUD script resource is missing.");
                using (StreamReader reader = new StreamReader(stream, Encoding.UTF8, true))
                    return reader.ReadToEnd();
            }
        }
    }

    internal sealed class CdpTarget
    {
        internal string Title;
        internal string Url;
        internal string WebSocketDebuggerUrl;
    }

    internal static class CdpTargetDiscovery
    {
        internal static CdpTarget Find(int port)
        {
            string endpoint = "http://127.0.0.1:" + port + "/json/list";
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(endpoint);
            request.Timeout = 2000;
            request.ReadWriteTimeout = 2000;
            request.Proxy = null;
            string json;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            using (StreamReader reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                json = reader.ReadToEnd();

            object[] targets = new JavaScriptSerializer().DeserializeObject(json) as object[];
            if (targets == null)
                return null;

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
                    return target;
                if (fallback == null)
                    fallback = target;
            }
            return fallback;
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

    internal sealed class CdpConnection : IDisposable
    {
        private const string PersistBindingName = "__codexSessionHealthHudPersist";
        private readonly ClientWebSocket socket = new ClientWebSocket();
        private readonly JavaScriptSerializer serializer = new JavaScriptSerializer();
        private readonly ConcurrentDictionary<int, TaskCompletionSource<IDictionary<string, object>>> pending =
            new ConcurrentDictionary<int, TaskCompletionSource<IDictionary<string, object>>>();
        private readonly SemaphoreSlim sendGate = new SemaphoreSlim(1, 1);
        private readonly SemaphoreSlim injectGate = new SemaphoreSlim(1, 1);
        private readonly CancellationTokenSource cancellation = new CancellationTokenSource();
        private readonly HudStateStore stateStore;
        private readonly string rendererScript;
        private int nextId;
        private Task readerTask;
        private int reinjectScheduled;
        private volatile bool canReinject;

        internal CdpConnection(HudStateStore stateStore, string rendererScript)
        {
            this.stateStore = stateStore;
            this.rendererScript = rendererScript;
            serializer.MaxJsonLength = 16 * 1024 * 1024;
            serializer.RecursionLimit = 128;
        }

        internal void ConnectAndInject(CdpTarget target)
        {
            socket.ConnectAsync(new Uri(target.WebSocketDebuggerUrl), CancellationToken.None)
                .GetAwaiter().GetResult();
            readerTask = Task.Run((Func<Task>)ReceiveLoopAsync);

            SendCommandAsync("Runtime.enable", null).GetAwaiter().GetResult();
            try { SendCommandAsync("Page.enable", null).GetAwaiter().GetResult(); } catch { }
            Dictionary<string, object> bindingParams = new Dictionary<string, object>();
            bindingParams["name"] = PersistBindingName;
            SendCommandAsync("Runtime.addBinding", bindingParams).GetAwaiter().GetResult();
            InjectAsync().GetAwaiter().GetResult();
            canReinject = true;
        }

        internal void WaitUntilClosed()
        {
            if (readerTask == null)
                return;
            try { readerTask.GetAwaiter().GetResult(); } catch { }
        }

        private async Task InjectAsync()
        {
            await injectGate.WaitAsync().ConfigureAwait(false);
            try
            {
                if (socket.State != WebSocketState.Open)
                    return;
                string bootstrap = stateStore.GetBootstrapJson();
                string bootstrapExpression = "window.__codexSessionHealthHudBootstrap=" + bootstrap + ";";
                await EvaluateAsync(bootstrapExpression).ConfigureAwait(false);
                await EvaluateAsync(rendererScript).ConfigureAwait(false);
            }
            finally
            {
                injectGate.Release();
            }
        }

        private Task EvaluateAsync(string expression)
        {
            Dictionary<string, object> parameters = new Dictionary<string, object>();
            parameters["expression"] = expression;
            parameters["awaitPromise"] = false;
            parameters["returnByValue"] = true;
            return SendCommandAsync("Runtime.evaluate", parameters);
        }

        private async Task<IDictionary<string, object>> SendCommandAsync(string method, object parameters)
        {
            if (socket.State != WebSocketState.Open)
                throw new InvalidOperationException("CDP socket is not open.");

            int id = Interlocked.Increment(ref nextId);
            TaskCompletionSource<IDictionary<string, object>> completion =
                new TaskCompletionSource<IDictionary<string, object>>();
            if (!pending.TryAdd(id, completion))
                throw new InvalidOperationException("Could not register a CDP request.");

            try
            {
                Dictionary<string, object> command = new Dictionary<string, object>();
                command["id"] = id;
                command["method"] = method;
                if (parameters != null)
                    command["params"] = parameters;
                byte[] data = Encoding.UTF8.GetBytes(serializer.Serialize(command));

                await sendGate.WaitAsync().ConfigureAwait(false);
                try
                {
                    await socket.SendAsync(new ArraySegment<byte>(data), WebSocketMessageType.Text, true,
                        cancellation.Token).ConfigureAwait(false);
                }
                finally
                {
                    sendGate.Release();
                }

                Task timeout = Task.Delay(5000);
                Task winner = await Task.WhenAny(completion.Task, timeout).ConfigureAwait(false);
                if (winner != completion.Task)
                    throw new TimeoutException("CDP command timed out: " + method);
                return await completion.Task.ConfigureAwait(false);
            }
            finally
            {
                TaskCompletionSource<IDictionary<string, object>> ignored;
                pending.TryRemove(id, out ignored);
            }
        }

        private async Task ReceiveLoopAsync()
        {
            Exception terminalError = null;
            try
            {
                while (!cancellation.IsCancellationRequested && socket.State == WebSocketState.Open)
                {
                    string text = await ReceiveTextAsync().ConfigureAwait(false);
                    if (text == null)
                        break;
                    IDictionary<string, object> message;
                    try { message = serializer.DeserializeObject(text) as IDictionary<string, object>; }
                    catch { continue; }
                    if (message == null)
                        continue;

                    object rawId;
                    if (message.TryGetValue("id", out rawId) && rawId != null)
                    {
                        int id;
                        if (int.TryParse(Convert.ToString(rawId), out id))
                        {
                            TaskCompletionSource<IDictionary<string, object>> completion;
                            if (pending.TryGetValue(id, out completion))
                            {
                                object error;
                                if (message.TryGetValue("error", out error) && error != null)
                                    completion.TrySetException(new InvalidOperationException(serializer.Serialize(error)));
                                else
                                    completion.TrySetResult(message);
                            }
                        }
                        continue;
                    }

                    object rawMethod;
                    if (!message.TryGetValue("method", out rawMethod) || rawMethod == null)
                        continue;
                    string method = Convert.ToString(rawMethod);
                    if (string.Equals(method, "Runtime.bindingCalled", StringComparison.Ordinal))
                    {
                        HandleBindingCalled(message);
                    }
                    else if (string.Equals(method, "Page.frameNavigated", StringComparison.Ordinal) ||
                        string.Equals(method, "Runtime.executionContextsCleared", StringComparison.Ordinal))
                    {
                        if (canReinject) ScheduleReinject();
                    }
                }
            }
            catch (Exception ex)
            {
                terminalError = ex;
            }
            finally
            {
                Exception error = terminalError ?? new InvalidOperationException("CDP connection closed.");
                foreach (KeyValuePair<int, TaskCompletionSource<IDictionary<string, object>>> pair in pending)
                    pair.Value.TrySetException(error);
            }
        }

        private void HandleBindingCalled(IDictionary<string, object> message)
        {
            object rawParams;
            IDictionary<string, object> parameters;
            if (!message.TryGetValue("params", out rawParams) ||
                (parameters = rawParams as IDictionary<string, object>) == null)
                return;
            object rawName;
            if (!parameters.TryGetValue("name", out rawName) ||
                !string.Equals(Convert.ToString(rawName), PersistBindingName, StringComparison.Ordinal))
                return;
            object rawPayload;
            if (!parameters.TryGetValue("payload", out rawPayload) || rawPayload == null)
                return;
            string payload = Convert.ToString(rawPayload);
            if (payload == null || payload.Length > 32768)
                return;
            // Persistence messages are rare (compaction/synchronization state only).
            // Apply them on the single CDP reader so measuring -> ready writes cannot
            // be reordered by the thread pool.
            stateStore.ApplyRendererPayload(payload);
        }

        private void ScheduleReinject()
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

        private async Task<string> ReceiveTextAsync()
        {
            byte[] buffer = new byte[32 * 1024];
            using (MemoryStream stream = new MemoryStream())
            {
                WebSocketReceiveResult result;
                do
                {
                    result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellation.Token)
                        .ConfigureAwait(false);
                    if (result.MessageType == WebSocketMessageType.Close)
                        return null;
                    stream.Write(buffer, 0, result.Count);
                    if (stream.Length > 16L * 1024L * 1024L)
                        throw new InvalidOperationException("CDP message exceeded the safety limit.");
                } while (!result.EndOfMessage);
                return Encoding.UTF8.GetString(stream.ToArray());
            }
        }

        public void Dispose()
        {
            try { cancellation.Cancel(); } catch { }
            try { socket.Abort(); } catch { }
            socket.Dispose();
            cancellation.Dispose();
            sendGate.Dispose();
            injectGate.Dispose();
        }
    }

    internal static class RendererHudHost
    {
        private const int RetryDelayMilliseconds = 750;

        internal static int Run(int port)
        {
            bool created;
            using (Mutex mutex = new Mutex(true, "Local\\CodexSessionHealthHUD.Renderer." + port, out created))
            {
                if (!created)
                    return 0;

                string runId = Guid.NewGuid().ToString("N");
                HudStateStore stateStore = new HudStateStore(runId);
                string script = RendererHudScript.Load();

                while (true)
                {
                    try
                    {
                        CdpTarget target = CdpTargetDiscovery.Find(port);
                        if (target != null)
                        {
                            using (CdpConnection connection = new CdpConnection(stateStore, script))
                            {
                                connection.ConnectAndInject(target);
                                connection.WaitUntilClosed();
                            }
                        }
                    }
                    catch { }
                    Thread.Sleep(RetryDelayMilliseconds);
                }
            }
        }
    }
}
