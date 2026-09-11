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


path = Path('RendererHudScript.js')
text = path.read_text(encoding='utf-8')

text = replace_once(
    text,
    "  const HISTORY_PAGE_SIZE = 200;\n  const MAX_ENVELOPE_DEPTH = 4;\n",
    "  const HISTORY_PAGE_SIZE = 200;\n  const HISTORY_RETRY_DELAYS = [300, 1000, 3000, 8000, 15000];\n  const LEGACY_HISTORY_MAX_NODES = 100000;\n  const LEGACY_HISTORY_MAX_DEPTH = 12;\n  const MAX_COMPACTION_PAIR_KEYS = 512;\n  const MAX_ENVELOPE_DEPTH = 4;\n",
    'renderer constants',
)
text = replace_once(
    text,
    "  const completedCompactionTurns = new Map();\n",
    "  const compactionTurnPairs = new Map();\n",
    'compaction pairing map',
)
text = replace_once(
    text,
    "      syncInFlight: false,\n      syncGeneration: 0,\n      validatedThisRun: false,\n",
    "      syncInFlight: false,\n      syncTimer: 0,\n      syncGeneration: 0,\n      historyRetryAttempts: 0,\n      validatedThisRun: false,\n",
    'runtime sync fields',
)
text = replace_once(
    text,
    "        capturedAt: runtime.postStatus === 'ready' ? runtime.capturedAt || new Date().toISOString() : null\n",
    "        capturedAt: runtime.postStatus === 'ready' ? runtime.capturedAt || null : null\n",
    'capturedAt persistence',
)
text = replace_once(
    text,
    "      const runtime = threadRuntime(activeThreadId);\n      if (!runtime.validatedThisRun || runtime.historyDirty) {\n",
    "      const runtime = threadRuntime(activeThreadId);\n      runtime.historyRetryAttempts = 0;\n      if (!runtime.validatedThisRun || runtime.historyDirty) {\n",
    'active thread resets bounded retry',
)
old_send = '''  async function sendRequest(method, params) {
    const manager = conversationManager();
    if (!manager || typeof manager.sendRequest !== 'function') throw new Error('conversation manager unavailable');
    return await Promise.resolve(manager.sendRequest(method, params || {}));
  }
'''
new_send = '''  async function sendRequest(method, params) {
    const manager = conversationManager();
    if (!manager || typeof manager.sendRequest !== 'function') throw new Error('conversation manager unavailable');
    try {
      return await Promise.resolve(manager.sendRequest(method, params || {}));
    } catch (error) {
      if (cachedConversationManager === manager) cachedConversationManager = null;
      throw error;
    }
  }
'''
text = replace_once(text, old_send, new_send, 'sendRequest stale manager reset')

history_block = r'''  function isUnsupportedMethodError(error) {
    if (!error) return false;
    const code = number(error.code ?? (error.error && error.error.code));
    if (code === -32601) return true;
    const message = String(error.message || error);
    return /(?:method\s+not\s+found|unknown\s+method|unsupported\s+method|method\s+is\s+not\s+supported)/i.test(message);
  }

  function historyRetryDelay(attempt) {
    const index = Math.max(0, Math.min(HISTORY_RETRY_DELAYS.length - 1, Number(attempt || 1) - 1));
    return HISTORY_RETRY_DELAYS[index];
  }

  function failTransientHistorySync(runtime, generation) {
    if (!runtime || generation !== runtime.syncGeneration) return;
    runtime.syncInFlight = false;
    runtime.historyDirty = true;
    runtime.validatedThisRun = false;
    runtime.historyRetryAttempts += 1;
    if (runtime.historyRetryAttempts < HISTORY_RETRY_DELAYS.length) {
      if (runtime.threadId === activeThreadId) runtime.postStatus = 'syncing';
      scheduleCompactionSync(runtime.threadId, historyRetryDelay(runtime.historyRetryAttempts));
    } else if (runtime.threadId === activeThreadId) {
      runtime.postStatus = 'unavailable';
    }
    if (runtime.threadId === activeThreadId) renderActive();
  }

  function scheduleCompactionSync(threadId, delay = 120) {
    const runtime = threadRuntime(threadId);
    if (!runtime || runtime.syncInFlight || runtime.syncTimer) return;
    const generation = ++runtime.syncGeneration;
    runtime.syncTimer = window.setTimeout(() => {
      runtime.syncTimer = 0;
      if (disposed || runtime.syncInFlight || generation !== runtime.syncGeneration) return;
      syncCompactions(runtime).catch(() => {
        if (generation !== runtime.syncGeneration) return;
        runtime.syncInFlight = false;
        runtime.historyDirty = true;
        runtime.validatedThisRun = false;
        runtime.postStatus = 'unavailable';
        if (runtime.threadId === activeThreadId) renderActive();
      });
    }, delay);
  }

  async function syncCompactions(runtime) {
    runtime.syncInFlight = true;
    const generation = runtime.syncGeneration;
    const cachedAnchor = runtime.lastObservedCompactionId;
    const cachedCount = runtime.compactionCount;
    let latestId = '';
    let countNewer = 0;
    let fullCount = 0;
    let anchorFound = false;
    let cursor = null;
    let pages = 0;
    let listResultComplete = false;

    if (historyListCapability !== 'unsupported') {
      try {
        do {
          const params = { threadId: runtime.threadId, limit: HISTORY_PAGE_SIZE, sortDirection: 'desc' };
          if (cursor) params.cursor = cursor;
          const response = await sendRequest('thread/items/list', params);
          historyListCapability = 'supported';
          const data = response && Array.isArray(response.data) ? response.data : [];
          for (const entry of data) {
            const item = entry && entry.item;
            if (!isCompactionItem(item)) continue;
            const id = compactionId(item);
            if (!id) continue;
            if (!latestId) latestId = id;
            if (cachedAnchor && cachedCount >= 0 && id === cachedAnchor) {
              anchorFound = true;
              break;
            }
            countNewer += 1;
            fullCount += 1;
          }
          if (anchorFound) break;
          cursor = response && typeof response.nextCursor === 'string' ? response.nextCursor : null;
          pages += 1;
          if (pages % 5 === 0) await new Promise(resolve => window.setTimeout(resolve, 0));
        } while (cursor && pages < 10000);
        listResultComplete = anchorFound || !cursor;
      } catch (error) {
        if (isUnsupportedMethodError(error)) {
          historyListCapability = 'unsupported';
        } else {
          failTransientHistorySync(runtime, generation);
          return;
        }
      }
    }

    if (historyListCapability === 'unsupported') {
      const legacy = await legacyCompactionSnapshot(runtime.threadId);
      latestId = legacy.latestId;
      fullCount = legacy.count;
      anchorFound = false;
      listResultComplete = true;
    } else if (!listResultComplete) {
      failTransientHistorySync(runtime, generation);
      return;
    }

    if (generation !== runtime.syncGeneration) return;
    runtime.syncInFlight = false;
    runtime.historyDirty = false;
    runtime.validatedThisRun = true;
    runtime.historyRetryAttempts = 0;

    if (anchorFound && cachedCount >= 0) runtime.compactionCount = cachedCount + countNewer;
    else runtime.compactionCount = fullCount;
    runtime.lastObservedCompactionId = latestId;
    if (latestId) runtime.seenCompactionIds.add(latestId);

    reconcileSnapshotToHistory(runtime, latestId);
    persistThread(runtime);
    if (runtime.threadId === activeThreadId) renderRisk();
  }

  function countCompactionsInLoadedHistory(result) {
    let count = 0;
    let latestId = '';
    const seenObjects = new WeakSet();
    const seenIds = new Set();
    const stack = [{ value: result, depth: 0 }];
    let visited = 0;

    while (stack.length) {
      if (visited >= LEGACY_HISTORY_MAX_NODES) throw new Error('loaded thread history exceeded safety limit');
      const node = stack.pop();
      const value = node.value;
      if (!value || typeof value !== 'object' || seenObjects.has(value)) continue;
      seenObjects.add(value);
      visited += 1;

      if (isCompactionItem(value)) {
        const id = compactionId(value);
        if (!id || !seenIds.has(id)) {
          count += 1;
          if (id) {
            seenIds.add(id);
            latestId = id;
          }
        }
      }
      if (node.depth >= LEGACY_HISTORY_MAX_DEPTH) continue;

      const children = Array.isArray(value) ? value : Object.values(value);
      for (let i = children.length - 1; i >= 0; i--) {
        const child = children[i];
        if (child && typeof child === 'object') stack.push({ value: child, depth: node.depth + 1 });
      }
    }
    return { count, latestId };
  }

  async function legacyCompactionSnapshot(threadId) {
    const manager = conversationManager();
    if (!manager || typeof manager.getConversation !== 'function') throw new Error('thread history unavailable');
    let conversation = null;
    try { conversation = manager.getConversation(threadId); } catch (_) { }
    const entities = conversation && conversation.turnHistory && conversation.turnHistory.history &&
      conversation.turnHistory.history.entitiesByKey;
    const hasCompleteHistory = conversation && conversation.turnsPagination &&
      conversation.turnsPagination.hasLoadedOldest === true;
    if (!hasCompleteHistory) throw new Error('loaded thread history is incomplete');
    return countCompactionsInLoadedHistory({
      turns: Array.isArray(conversation.turns) ? conversation.turns : [],
      history: entities && typeof entities === 'object' ? entities : {}
    });
  }
'''
text = sub_once(
    text,
    r"  function scheduleCompactionSync\(threadId, delay = 120\) \{.*?\n  async function legacyCompactionSnapshot\(threadId\) \{.*?\n  \}\n\n(?=  function reconcileSnapshotToHistory)",
    history_block,
    'history synchronization block',
)

pairing_block = r'''  function trimCompactionPairMap() {
    while (compactionTurnPairs.size > MAX_COMPACTION_PAIR_KEYS) {
      const oldest = compactionTurnPairs.keys().next().value;
      if (oldest === undefined) break;
      compactionTurnPairs.delete(oldest);
    }
  }

  function compactionPairState(threadId, turnId) {
    const key = `${threadId}:${turnId}`;
    let state = compactionTurnPairs.get(key);
    if (!state) {
      state = { legacySeen: 0, primarySeen: 0, legacyKeys: [] };
      compactionTurnPairs.set(key, state);
      trimCompactionPairMap();
    }
    return { key, state };
  }

  function maybeFinishCompactionPair(pairKey, state) {
    if (state && state.legacySeen > 0 && state.legacySeen === state.primarySeen) {
      compactionTurnPairs.delete(pairKey);
    }
  }

  function upgradeCompactionIdentity(threadId, oldKey, newId) {
    if (!threadId || !oldKey || !newId || oldKey === newId) return false;
    const runtime = threadRuntime(threadId);
    if (!runtime || runtime.seenCompactionIds.has(newId)) return false;
    runtime.seenCompactionIds.delete(oldKey);
    runtime.seenCompactionIds.add(newId);
    if (runtime.lastObservedCompactionId === oldKey) runtime.lastObservedCompactionId = newId;
    if (runtime.snapshotCompactionId === oldKey) runtime.snapshotCompactionId = newId;
    persistThread(runtime);
    if (threadId === activeThreadId) renderRisk();
    return true;
  }

  function registerCompletedCompaction(threadId, turnId, id, source) {
    if (!threadId) return;
    const runtime = threadRuntime(threadId);
    const key = id || `${source}:${turnId || 'unknown'}:${eventSequence}`;
    if (runtime.seenCompactionIds.has(key)) return;
    runtime.seenCompactionIds.add(key);

    runtime.syncGeneration += 1;
    runtime.syncInFlight = false;
    if (runtime.syncTimer) window.clearTimeout(runtime.syncTimer);
    runtime.syncTimer = 0;
    runtime.historyRetryAttempts = 0;

    if (runtime.compactionCount >= 0) runtime.compactionCount += 1;
    runtime.lastObservedCompactionId = key;
    runtime.snapshotCompactionId = key;
    runtime.postStatus = 'measuring';
    runtime.postTokens = -1;
    runtime.postWindow = -1;
    runtime.currentContextTokens = -1;
    runtime.currentContextPercent = -1;
    runtime.captureRunId = runId;
    runtime.capturedAt = '';
    runtime.measurementArmedSeq = eventSequence;
    runtime.measuringAnimationPending = true;
    runtime.validatedThisRun = runtime.compactionCount >= 0;
    runtime.historyDirty = false;
    persistThread(runtime);
    if (!runtime.validatedThisRun) scheduleCompactionSync(threadId, 240);
    if (threadId === activeThreadId) renderRisk();
  }

  function handleCompletedCompaction(params) {
    const item = first(params, ['item']);
    if (!isCompactionItem(item)) return;
    const threadId = stringValue(first(params, ['threadId', 'thread_id']));
    const turnId = stringValue(first(params, ['turnId', 'turn_id']));
    if (!threadId) return;
    const runtime = threadRuntime(threadId);
    const realId = compactionId(item);
    if (realId && runtime.seenCompactionIds.has(realId)) return;

    if (!turnId) {
      registerCompletedCompaction(threadId, '', realId || `primary:unknown:${eventSequence}`, 'item/completed');
      return;
    }

    const pair = compactionPairState(threadId, turnId);
    pair.state.primarySeen += 1;
    const ordinal = pair.state.primarySeen;
    const legacyKey = pair.state.legacyKeys[ordinal - 1] || '';
    if (legacyKey) {
      if (realId) upgradeCompactionIdentity(threadId, legacyKey, realId);
      maybeFinishCompactionPair(pair.key, pair.state);
      return;
    }

    registerCompletedCompaction(threadId, turnId,
      realId || `primary:${turnId}:${ordinal}`, 'item/completed');
    maybeFinishCompactionPair(pair.key, pair.state);
  }

  function handleLegacyCompacted(params) {
    const threadId = stringValue(first(params, ['threadId', 'thread_id']));
    const turnId = stringValue(first(params, ['turnId', 'turn_id']));
    if (!threadId) return;
    if (!turnId) {
      const runtime = threadRuntime(threadId);
      runtime.historyDirty = true;
      runtime.validatedThisRun = false;
      runtime.historyRetryAttempts = 0;
      scheduleCompactionSync(threadId, 120);
      return;
    }

    const pair = compactionPairState(threadId, turnId);
    pair.state.legacySeen += 1;
    const ordinal = pair.state.legacySeen;
    if (pair.state.primarySeen >= ordinal) {
      maybeFinishCompactionPair(pair.key, pair.state);
      return;
    }

    const legacyKey = `legacy:${turnId}:${ordinal}`;
    pair.state.legacyKeys[ordinal - 1] = legacyKey;
    registerCompletedCompaction(threadId, turnId, legacyKey, 'thread/compacted');
    maybeFinishCompactionPair(pair.key, pair.state);
  }
'''
text = sub_once(
    text,
    r"  function registerCompletedCompaction\(threadId, turnId, id, source\) \{.*?\n  function handleLegacyCompacted\(params\) \{.*?\n  \}\n\n(?=  function usageBreakdownMeasured)",
    pairing_block,
    'compaction pairing block',
)

quota_old = '''  async function requestRateLimits() {
    quotaRequestTimer = 0;
    quotaRequestAttempts += 1;
    try {
      const result = await sendRequest('account/rateLimits/read', {});
      const snapshot = normalizeRateLimitSnapshot(result);
      if (snapshot) {
        mergeRateLimitSnapshot(snapshot, true);
        hasFullQuotaSnapshot = true;
        quotaRequestAttempts = 0;
        renderUsage();
        return;
      }
    } catch (_) { cachedConversationManager = null; }
    if (!hasFullQuotaSnapshot && quotaRequestAttempts < 8 && !quotaRequestTimer) {
      quotaRequestTimer = window.setTimeout(requestRateLimits, 700);
    }
  }
'''
quota_new = '''  function quotaRetryDelay(attempt) {
    const value = Math.max(1, Number(attempt || 1));
    if (value <= 8) return 700;
    const exponent = Math.min(4, value - 9);
    return Math.min(30000, 2000 * (2 ** exponent));
  }

  async function requestRateLimits() {
    quotaRequestTimer = 0;
    quotaRequestAttempts += 1;
    try {
      const result = await sendRequest('account/rateLimits/read', {});
      const snapshot = normalizeRateLimitSnapshot(result);
      if (snapshot) {
        mergeRateLimitSnapshot(snapshot, true);
        hasFullQuotaSnapshot = true;
        quotaRequestAttempts = 0;
        renderUsage();
        return;
      }
    } catch (_) { }
    if (!hasFullQuotaSnapshot && !quotaRequestTimer && !disposed) {
      quotaRequestTimer = window.setTimeout(requestRateLimits, quotaRetryDelay(quotaRequestAttempts));
    }
  }
'''
text = replace_once(text, quota_old, quota_new, 'quota bounded backoff')

text = replace_once(
    text,
    "    runtime.syncGeneration += 1;\n    runtime.syncInFlight = false;\n    runtime.historyDirty = true;\n",
    "    runtime.syncGeneration += 1;\n    runtime.syncInFlight = false;\n    if (runtime.syncTimer) window.clearTimeout(runtime.syncTimer);\n    runtime.syncTimer = 0;\n    runtime.historyRetryAttempts = 0;\n    runtime.historyDirty = true;\n",
    'rollback sync timer reset',
)
text = replace_once(
    text,
    '''    if (method === 'item/completed') {
      const item = first(params, ['item']);
      if (!isCompactionItem(item)) return;
      const threadId = stringValue(first(params, ['threadId', 'thread_id']));
      const turnId = stringValue(first(params, ['turnId', 'turn_id']));
      registerCompletedCompaction(threadId, turnId, compactionId(item), 'item/completed');
      return;
    }
''',
    '''    if (method === 'item/completed') {
      handleCompletedCompaction(params);
      return;
    }
''',
    'primary compaction dispatch',
)
text = replace_once(
    text,
    '''  const onVisibility = () => {
    if (!document.hidden) {
      scheduleMount(0);
      scheduleActiveThreadRefresh(0);
    }
  };
''',
    '''  const onVisibility = () => {
    if (!document.hidden) {
      scheduleMount(0);
      scheduleActiveThreadRefresh(0);
      if (!hasFullQuotaSnapshot && !quotaRequestTimer) {
        quotaRequestTimer = window.setTimeout(requestRateLimits, 120);
      }
    }
  };
''',
    'quota retry on visibility',
)
text = replace_once(
    text,
    '''    if (tooltipTimer) window.clearTimeout(tooltipTimer);
    mountTimer = activeThreadTimer = quotaRequestTimer = tooltipTimer = 0;
    if (host) host.remove();
''',
    '''    if (tooltipTimer) window.clearTimeout(tooltipTimer);
    for (const runtime of runtimeThreads.values()) {
      if (runtime.syncTimer) window.clearTimeout(runtime.syncTimer);
      runtime.syncTimer = 0;
    }
    compactionTurnPairs.clear();
    mountTimer = activeThreadTimer = quotaRequestTimer = tooltipTimer = 0;
    if (host) host.remove();
''',
    'dispose per-thread timers',
)
text = replace_once(
    text,
    '''      hydrateCurrentUsageFromSnapshot,
      usageBreakdownMeasured,
      normalizeRateLimitSnapshot,
''',
    '''      hydrateCurrentUsageFromSnapshot,
      usageBreakdownMeasured,
      isUnsupportedMethodError,
      historyRetryDelay,
      countCompactionsInLoadedHistory,
      handleCompletedCompaction,
      handleLegacyCompacted,
      compactionPairCount: () => compactionTurnPairs.size,
      clearCompactionPairing: () => compactionTurnPairs.clear(),
      threadRuntimeForTest: threadRuntime,
      persistThreadForTest: persistThread,
      normalizeRateLimitSnapshot,
''',
    'renderer test hooks 1',
)
text = replace_once(
    text,
    '''      remainingPercent,
      effectiveRisk,
''',
    '''      remainingPercent,
      quotaRetryDelay,
      effectiveRisk,
''',
    'renderer test hooks quota',
)

path.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Regression tests for the renderer hardening.
# ---------------------------------------------------------------------------
path = Path('tests/renderer-logic.test.js')
test = path.read_text(encoding='utf-8')
insert_after_capture = '''assert.equal(t.formatCapturedAt('not-a-date'), '', 'invalid capture time is hidden');
'''
new_tests = r'''

assert.equal(t.isUnsupportedMethodError({ code: -32601, message: 'Method not found' }), true,
  'JSON-RPC Method Not Found enables legacy compatibility mode');
assert.equal(t.isUnsupportedMethodError(new Error('Method not found')), true,
  'explicit Method Not Found text enables legacy compatibility mode');
assert.equal(t.isUnsupportedMethodError(new Error('request timed out while calling method')), false,
  'transient errors that merely mention method do not disable the list API');
assert.equal(t.historyRetryDelay(1), 300);
assert.equal(t.historyRetryDelay(5), 15000);
assert.equal(t.historyRetryDelay(99), 15000, 'history retry delay is capped');

const loadedHistory = {
  turns: [
    { item: { type: 'contextCompaction', id: 'history-1' } },
    { nested: [{ type: 'contextCompaction', id: 'history-2' }] }
  ],
  duplicate: { type: 'contextCompaction', id: 'history-1' }
};
const countedHistory = t.countCompactionsInLoadedHistory(loadedHistory);
assert.equal(countedHistory.count, 2, 'bounded loaded-history scan deduplicates compaction IDs');
assert.equal(countedHistory.latestId, 'history-2');

let persistedPayload = null;
window.__codexSessionHealthHudPersist = payload => { persistedPayload = JSON.parse(payload); };
t.persistThreadForTest({
  threadId: 'capture-without-time',
  compactionCount: 1,
  lastObservedCompactionId: 'capture-1',
  snapshotCompactionId: 'capture-1',
  postStatus: 'ready',
  postTokens: 1000,
  postWindow: 10000,
  captureRunId: '',
  capturedAt: ''
});
assert.equal(persistedPayload.state.capturedAt, null,
  'ready snapshots without a measured capture time do not invent the current time');
delete window.__codexSessionHealthHudPersist;

t.clearCompactionPairing();
const legacyFirst = t.threadRuntimeForTest('pair-legacy-first');
legacyFirst.compactionCount = 0;
t.handleLegacyCompacted({ threadId: 'pair-legacy-first', turnId: 'turn-1' });
assert.equal(legacyFirst.compactionCount, 1);
const legacyIdentity = legacyFirst.snapshotCompactionId;
legacyFirst.postStatus = 'ready';
legacyFirst.postTokens = 34002;
legacyFirst.postWindow = 258400;
legacyFirst.capturedAt = capturedIso;
t.handleCompletedCompaction({
  threadId: 'pair-legacy-first', turnId: 'turn-1',
  item: { type: 'contextCompaction', id: 'real-1' }
});
assert.equal(legacyFirst.compactionCount, 1, 'late primary event does not double-count a legacy compaction');
assert.notEqual(legacyIdentity, 'real-1');
assert.equal(legacyFirst.snapshotCompactionId, 'real-1', 'late primary event upgrades the provisional identity');
assert.equal(legacyFirst.postStatus, 'ready', 'identity upgrade preserves captured status');
assert.equal(legacyFirst.postTokens, 34002, 'identity upgrade preserves captured tokens');
assert.equal(legacyFirst.capturedAt, capturedIso, 'identity upgrade preserves capture time');

const primaryFirst = t.threadRuntimeForTest('pair-primary-first');
primaryFirst.compactionCount = 0;
t.handleCompletedCompaction({
  threadId: 'pair-primary-first', turnId: 'turn-2',
  item: { type: 'contextCompaction', id: 'real-2' }
});
t.handleLegacyCompacted({ threadId: 'pair-primary-first', turnId: 'turn-2' });
assert.equal(primaryFirst.compactionCount, 1, 'legacy fallback after primary does not double-count');

const multipleSameTurn = t.threadRuntimeForTest('pair-multiple');
multipleSameTurn.compactionCount = 0;
t.handleLegacyCompacted({ threadId: 'pair-multiple', turnId: 'turn-multi' });
t.handleLegacyCompacted({ threadId: 'pair-multiple', turnId: 'turn-multi' });
assert.equal(multipleSameTurn.compactionCount, 2, 'multiple legitimate compactions in one turn remain distinct');
t.handleCompletedCompaction({
  threadId: 'pair-multiple', turnId: 'turn-multi',
  item: { type: 'contextCompaction', id: 'multi-1' }
});
t.handleCompletedCompaction({
  threadId: 'pair-multiple', turnId: 'turn-multi',
  item: { type: 'contextCompaction', id: 'multi-2' }
});
assert.equal(multipleSameTurn.compactionCount, 2, 'paired primary events do not add duplicate counts');
assert.equal(multipleSameTurn.snapshotCompactionId, 'multi-2');

for (let i = 0; i < 600; i++) {
  t.handleCompletedCompaction({
    threadId: 'pair-bound', turnId: `turn-bound-${i}`,
    item: { type: 'contextCompaction', id: `bound-${i}` }
  });
}
assert.ok(t.compactionPairCount() <= 512, 'unmatched compaction pairing state is bounded');
t.clearCompactionPairing();

assert.equal(t.quotaRetryDelay(1), 700);
assert.equal(t.quotaRetryDelay(8), 700);
assert.equal(t.quotaRetryDelay(9), 2000);
assert.equal(t.quotaRetryDelay(13), 30000);
assert.equal(t.quotaRetryDelay(100), 30000, 'quota failure backoff is capped');

const rendererSource = require('node:fs').readFileSync(path.join(__dirname, '..', 'RendererHudScript.js'), 'utf8');
assert.equal(rendererSource.includes("readThread(threadId, { includeTurns: true })"), false,
  'legacy history fallback never hydrates the full thread');
assert.equal(rendererSource.includes("runtime.capturedAt || new Date().toISOString()"), false,
  'persistence never fabricates a capture timestamp');
'''
test = replace_once(test, insert_after_capture, insert_after_capture + new_tests, 'renderer hardening tests')
path.write_text(test, encoding='utf-8')

print('renderer hardening patch applied')
