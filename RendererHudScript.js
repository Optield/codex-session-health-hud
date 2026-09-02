(() => {
  'use strict';

  const INSTANCE = Symbol.for('codex-session-health-hud.renderer.v1');
  const previous = window[INSTANCE];
  if (previous && typeof previous.dispose === 'function') previous.dispose();
  for (const element of document.querySelectorAll('[data-codex-session-health-hud]')) element.remove();
  for (const element of document.querySelectorAll('[data-codex-session-health-tooltip]')) element.remove();

  const PRODUCT_NAME = 'Codex Session Health HUD';
  const TEST_MODE = window.__codexSessionHealthHudTestMode === true;
  const PERSIST_BINDING = '__codexSessionHealthHudPersist';
  const GOOD_LIMIT = 0.45;
  const CAUTION_LIMIT = 0.65;
  const HIGH_LIMIT = 0.80;
  const FIVE_HOUR_MINUTES = 300;
  const WEEKLY_MINUTES = 10080;
  const HISTORY_PAGE_SIZE = 200;
  const MAX_ENVELOPE_DEPTH = 4;
  const MAX_ENVELOPE_NODES = 48;

  const COLORS = {
    muted: '#AEB2B7',
    track: '#62666C',
    green: '#86A58E',
    yellow: '#D4BB6F',
    red: '#C96B6B',
    purple: '#AF8CE0'
  };

  const bootstrap = window.__codexSessionHealthHudBootstrap || { runId: '', threads: {} };
  const runId = typeof bootstrap.runId === 'string' ? bootstrap.runId : '';
  const persistedThreads = bootstrap.threads && typeof bootstrap.threads === 'object' ? bootstrap.threads : {};

  const runtimeThreads = new Map();
  const rateLimitsById = new Map();
  const completedCompactionTurns = new Map();
  let eventSequence = 0;
  let activeThreadId = '';
  let cachedConversationManager = null;
  let cachedComposer = null;
  let host = null;
  let ui = null;
  let nativeContext = null;
  let toolbar = null;
  let mountTimer = 0;
  let activeThreadTimer = 0;
  let quotaRequestTimer = 0;
  let quotaRequestAttempts = 0;
  let hasFullQuotaSnapshot = false;
  let historyListCapability = 'unknown';
  let riskTooltip = null;
  let usageTooltip = null;
  let lastRiskVisualKey = '';
  let tooltipTimer = 0;
  let tooltipKind = '';
  let disposed = false;

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function integer(value) {
    const parsed = number(value);
    return parsed !== null && Number.isSafeInteger(parsed) ? parsed : null;
  }

  function clamp(value, minimum = 0, maximum = 100) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function own(object, name) {
    return !!object && typeof object === 'object' && Object.prototype.hasOwnProperty.call(object, name);
  }

  function first(object, names) {
    if (!object || typeof object !== 'object') return undefined;
    for (const name of names) if (own(object, name)) return object[name];
    return undefined;
  }

  function stringValue(value) {
    return typeof value === 'string' && value ? value : '';
  }

  function formatTokens(value) {
    if (!Number.isFinite(value) || value < 0) return '—';
    if (value < 1000) return String(Math.round(value));
    if (value < 1_000_000) {
      const k = value / 1000;
      const text = k >= 100 ? k.toFixed(0) : k >= 10 ? k.toFixed(1) : k.toFixed(2);
      return `${Number(text)}K`;
    }
    const m = value / 1_000_000;
    const text = m >= 100 ? m.toFixed(1) : m.toFixed(2);
    return `${Number(text)}M`;
  }

  function formatPercent(value) {
    return Number.isFinite(value) ? `${value.toFixed(1)}%` : '—';
  }

  function ratioPercent(tokens, windowSize) {
    if (!Number.isFinite(tokens) || tokens < 0 || !Number.isFinite(windowSize) || windowSize <= 0) return null;
    return clamp(tokens * 100 / windowSize);
  }

  function isApproximateWindow(minutes, expected) {
    return Number.isFinite(minutes) && minutes >= expected * 0.95 && minutes <= expected * 1.05;
  }

  function persistedFor(threadId) {
    const raw = persistedThreads[threadId];
    return raw && typeof raw === 'object' ? raw : null;
  }

  function createThreadRuntime(threadId) {
    const saved = persistedFor(threadId);
    return {
      threadId,
      currentContextTokens: -1,
      currentContextWindow: -1,
      currentContextPercent: -1,
      sessionTotalTokens: -1,
      compactionCount: saved && Number.isInteger(saved.compactionCount) ? saved.compactionCount : -1,
      lastObservedCompactionId: saved ? stringValue(saved.lastObservedCompactionId) : '',
      snapshotCompactionId: saved ? stringValue(saved.snapshotCompactionId) : '',
      postStatus: saved ? stringValue(saved.postCompactionStatus) || 'syncing' : 'syncing',
      postTokens: saved && Number.isFinite(Number(saved.postCompactionTokens)) ? Number(saved.postCompactionTokens) : -1,
      postWindow: saved && Number.isFinite(Number(saved.postCompactionWindow)) ? Number(saved.postCompactionWindow) : -1,
      captureRunId: saved ? stringValue(saved.captureRunId) : '',
      capturedAt: saved ? stringValue(saved.capturedAt) : '',
      measurementArmedSeq: 0,
      syncInFlight: false,
      syncGeneration: 0,
      validatedThisRun: false,
      historyDirty: false,
      seenCompactionIds: new Set(),
      measuringAnimationPending: false
    };
  }

  function threadRuntime(threadId) {
    if (!threadId) return null;
    let runtime = runtimeThreads.get(threadId);
    if (!runtime) {
      runtime = createThreadRuntime(threadId);
      runtimeThreads.set(threadId, runtime);
    }
    return runtime;
  }

  function persistThread(runtime) {
    if (!runtime || typeof window[PERSIST_BINDING] !== 'function') return;
    const payload = {
      action: 'upsertThreadState',
      threadId: runtime.threadId,
      state: {
        lastObservedCompactionId: runtime.lastObservedCompactionId || null,
        compactionCount: Number.isInteger(runtime.compactionCount) ? runtime.compactionCount : -1,
        snapshotCompactionId: runtime.snapshotCompactionId || null,
        postCompactionStatus: runtime.postStatus || 'syncing',
        postCompactionTokens: runtime.postStatus === 'ready' && runtime.postTokens >= 0 ? Math.round(runtime.postTokens) : null,
        postCompactionWindow: runtime.postStatus === 'ready' && runtime.postWindow > 0 ? Math.round(runtime.postWindow) : null,
        captureRunId: runtime.postStatus === 'measuring' ? runId || null : null,
        capturedAt: runtime.postStatus === 'ready' ? runtime.capturedAt || new Date().toISOString() : null
      }
    };
    try { window[PERSIST_BINDING](JSON.stringify(payload)); } catch (_) { }
  }

  function motionAllowed() {
    return typeof Element.prototype.animate === 'function' &&
      !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function visible(element) {
    if (!element || !element.isConnected) return false;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 10 && rect.height > 10 && rect.bottom > innerHeight * 0.4 &&
      style.display !== 'none' && style.visibility !== 'hidden';
  }

  function editableCandidates() {
    return Array.from(document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"]'))
      .filter(visible)
      .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom);
  }

  function currentComposer() {
    if (cachedComposer && visible(cachedComposer)) return cachedComposer;
    cachedComposer = editableCandidates()[0] || null;
    return cachedComposer;
  }

  function composerFiber() {
    let anchor = currentComposer();
    if (!anchor) return null;
    let fiberKey = null;
    let fiberAnchor = anchor;
    while (fiberAnchor && fiberAnchor !== document.body && !fiberKey) {
      fiberKey = Object.getOwnPropertyNames(fiberAnchor).find(key => key.startsWith('__reactFiber')) || null;
      if (!fiberKey) fiberAnchor = fiberAnchor.parentElement;
    }
    return fiberAnchor && fiberKey ? fiberAnchor[fiberKey] : null;
  }

  function composerConversationId() {
    let fiber = composerFiber();
    for (let depth = 0; fiber && depth < 40; depth += 1, fiber = fiber.return) {
      for (const props of [fiber.memoizedProps, fiber.pendingProps]) {
        if (props && typeof props.conversationId === 'string' && props.conversationId) return props.conversationId;
      }
    }
    return '';
  }

  function conversationManager() {
    if (cachedConversationManager && typeof cachedConversationManager.sendRequest === 'function') return cachedConversationManager;
    let fiber = composerFiber();
    for (let depth = 0; fiber && depth < 40; depth += 1, fiber = fiber.return) {
      let hook = fiber.memoizedState;
      for (let index = 0; hook && index < 200; index += 1, hook = hook.next) {
        const candidate = hook.memoizedState;
        if (candidate && typeof candidate.getConversation === 'function' &&
          typeof candidate.getHostId === 'function') {
          cachedConversationManager = candidate;
          return candidate;
        }
      }
    }
    return null;
  }

  function stableSidebarThreadId() {
    const active = document.querySelector(
      '[data-app-action-sidebar-thread-id][aria-current="page"], [aria-current="page"] [data-app-action-sidebar-thread-id]'
    );
    if (!active) return { id: '', provisional: false };
    const raw = active.getAttribute('data-app-action-sidebar-thread-id') || '';
    const separator = raw.indexOf(':');
    const id = separator >= 0 ? raw.slice(separator + 1) : raw;
    return { id, provisional: id.startsWith('client-new-thread:') };
  }

  function resolveActiveThread() {
    const sidebar = stableSidebarThreadId();
    if (sidebar.id && !sidebar.provisional) return sidebar.id;
    const composerId = composerConversationId();
    if (composerId) return composerId;
    return sidebar.provisional ? '' : sidebar.id;
  }

  function setActiveThread(threadId) {
    if (threadId === activeThreadId) return;
    activeThreadId = threadId || '';
    if (activeThreadId) {
      const runtime = threadRuntime(activeThreadId);
      if (!runtime.validatedThisRun || runtime.historyDirty) {
        runtime.postStatus = 'syncing';
        scheduleCompactionSync(activeThreadId, 0);
      }
    }
    renderActive();
  }

  function refreshActiveThread() {
    if (disposed || document.hidden) return;
    setActiveThread(resolveActiveThread());
  }

  function scheduleActiveThreadRefresh(delay = 120) {
    if (activeThreadTimer || disposed) return;
    activeThreadTimer = window.setTimeout(() => {
      activeThreadTimer = 0;
      refreshActiveThread();
    }, delay);
  }

  async function sendRequest(method, params) {
    const manager = conversationManager();
    if (!manager || typeof manager.sendRequest !== 'function') throw new Error('conversation manager unavailable');
    return await Promise.resolve(manager.sendRequest(method, params || {}));
  }

  function itemType(item) {
    return item && typeof item === 'object' ? stringValue(item.type) : '';
  }

  function isCompactionItem(item) {
    const type = itemType(item);
    return type === 'contextCompaction' || type === 'context-compaction';
  }

  function compactionId(item) {
    return stringValue(first(item, ['id', 'itemId', 'item_id']));
  }

  function scheduleCompactionSync(threadId, delay = 120) {
    const runtime = threadRuntime(threadId);
    if (!runtime || runtime.syncInFlight) return;
    const generation = ++runtime.syncGeneration;
    window.setTimeout(() => {
      if (disposed || runtime.syncInFlight || generation !== runtime.syncGeneration) return;
      syncCompactions(runtime).catch(() => {
        if (generation !== runtime.syncGeneration) return;
        runtime.syncInFlight = false;
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
    let usedListApi = false;
    let listResultComplete = false;

    if (historyListCapability !== 'unsupported') {
      try {
        do {
          const params = { threadId: runtime.threadId, limit: HISTORY_PAGE_SIZE, sortDirection: 'desc' };
          if (cursor) params.cursor = cursor;
          const response = await sendRequest('thread/items/list', params);
          usedListApi = true;
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
        const text = String(error && (error.message || error));
        if (/method|not found|unknown|not supported|unsupported/i.test(text)) historyListCapability = 'unsupported';
        else if (historyListCapability === 'unknown') historyListCapability = 'unknown';
      }
    }

    if (!usedListApi || !listResultComplete) {
      const legacy = await legacyCompactionSnapshot(runtime.threadId);
      latestId = legacy.latestId;
      fullCount = legacy.count;
      anchorFound = false;
    }

    if (generation !== runtime.syncGeneration) return;
    runtime.syncInFlight = false;
    runtime.historyDirty = false;
    runtime.validatedThisRun = true;

    if (anchorFound && cachedCount >= 0) runtime.compactionCount = cachedCount + countNewer;
    else runtime.compactionCount = fullCount;
    runtime.lastObservedCompactionId = latestId;
    if (latestId) runtime.seenCompactionIds.add(latestId);

    reconcileSnapshotToHistory(runtime, latestId);
    persistThread(runtime);
    if (runtime.threadId === activeThreadId) renderRisk();
  }

  async function legacyCompactionSnapshot(threadId) {
    const manager = conversationManager();
    if (!manager) throw new Error('thread history unavailable');
    let result = null;
    try {
      const conversation = typeof manager.getConversation === 'function' ? manager.getConversation(threadId) : null;
      const entities = conversation && conversation.turnHistory && conversation.turnHistory.history &&
        conversation.turnHistory.history.entitiesByKey;
      const hasCompleteHistory = conversation && conversation.turnsPagination &&
        conversation.turnsPagination.hasLoadedOldest === true;
      if (hasCompleteHistory) {
        result = {
          turns: Array.isArray(conversation.turns) ? conversation.turns : [],
          history: entities && typeof entities === 'object' ? Object.values(entities) : []
        };
      }
    } catch (_) { }
    if (!result) {
      if (typeof manager.readThread !== 'function') throw new Error('thread history unavailable');
      result = await Promise.resolve(manager.readThread(threadId, { includeTurns: true }));
    }
    let count = 0;
    let latestId = '';
    const seenObjects = new WeakSet();
    const seenIds = new Set();
    const walk = value => {
      if (!value || typeof value !== 'object' || seenObjects.has(value)) return;
      seenObjects.add(value);
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
      if (Array.isArray(value)) {
        for (const child of value) walk(child);
      } else {
        for (const child of Object.values(value)) walk(child);
      }
    };
    walk(result);
    return { count, latestId };
  }

  function reconcileSnapshotToHistory(runtime, latestId) {
    if (!latestId) {
      runtime.postStatus = 'noCompaction';
      runtime.snapshotCompactionId = '';
      runtime.postTokens = -1;
      runtime.postWindow = -1;
      runtime.captureRunId = '';
      runtime.capturedAt = '';
      return;
    }

    if (runtime.postStatus === 'measuring' && runtime.snapshotCompactionId === latestId &&
      runtime.captureRunId === runId) return;
    if (runtime.postStatus === 'ready' && runtime.snapshotCompactionId === latestId &&
      runtime.postTokens >= 0 && runtime.postWindow > 0) return;
    if (runtime.postStatus === 'notCaptured' && runtime.snapshotCompactionId === latestId) return;

    runtime.postStatus = 'notCaptured';
    runtime.snapshotCompactionId = latestId;
    runtime.postTokens = -1;
    runtime.postWindow = -1;
    runtime.captureRunId = '';
    runtime.capturedAt = '';
  }

  function registerCompletedCompaction(threadId, turnId, id, source) {
    if (!threadId) return;
    const runtime = threadRuntime(threadId);
    const key = id || `${source}:${turnId || 'unknown'}`;
    if (runtime.seenCompactionIds.has(key)) return;
    runtime.seenCompactionIds.add(key);
    if (turnId) completedCompactionTurns.set(`${threadId}:${turnId}`, true);

    runtime.syncGeneration += 1;
    runtime.syncInFlight = false;

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

  function handleLegacyCompacted(params) {
    const threadId = stringValue(first(params, ['threadId', 'thread_id']));
    const turnId = stringValue(first(params, ['turnId', 'turn_id']));
    if (!threadId) return;
    window.setTimeout(() => {
      if (turnId && completedCompactionTurns.has(`${threadId}:${turnId}`)) return;
      registerCompletedCompaction(threadId, turnId, `legacy:${turnId || ++eventSequence}`, 'thread/compacted');
    }, 80);
  }

  function usageBreakdownMeasured(last) {
    if (!last || typeof last !== 'object') return false;
    const values = [
      first(last, ['inputTokens', 'input_tokens']),
      first(last, ['cachedInputTokens', 'cached_input_tokens']),
      first(last, ['cacheWriteInputTokens', 'cache_write_input_tokens']),
      first(last, ['outputTokens', 'output_tokens']),
      first(last, ['reasoningOutputTokens', 'reasoning_output_tokens'])
    ];
    return values.some(value => {
      const parsed = number(value);
      return parsed !== null && parsed > 0;
    });
  }

  function normalizeTokenUsage(params) {
    const usage = first(params, ['tokenUsage', 'token_usage']) || params;
    if (!usage || typeof usage !== 'object') return null;
    const last = first(usage, ['last', 'lastTokenUsage', 'last_token_usage']);
    const total = first(usage, ['total', 'totalTokenUsage', 'total_token_usage']);
    const windowSize = number(first(usage, ['modelContextWindow', 'model_context_window', 'contextWindow', 'context_window']));
    if (!last || typeof last !== 'object') return null;
    const lastTotal = number(first(last, ['totalTokens', 'total_tokens']));
    const sessionTotal = total && typeof total === 'object' ? number(first(total, ['totalTokens', 'total_tokens'])) : null;
    return { last, lastTotal, sessionTotal, windowSize, measured: usageBreakdownMeasured(last) };
  }

  function handleTokenUsage(params) {
    const threadId = stringValue(first(params, ['threadId', 'thread_id']));
    if (!threadId) return;
    const parsed = normalizeTokenUsage(params);
    if (!parsed) return;
    const runtime = threadRuntime(threadId);
    if (parsed.lastTotal !== null && parsed.lastTotal >= 0) runtime.currentContextTokens = parsed.lastTotal;
    if (parsed.windowSize !== null && parsed.windowSize > 0) runtime.currentContextWindow = parsed.windowSize;
    runtime.currentContextPercent = ratioPercent(runtime.currentContextTokens, runtime.currentContextWindow) ?? -1;
    if (parsed.sessionTotal !== null && parsed.sessionTotal >= 0) runtime.sessionTotalTokens = parsed.sessionTotal;

    if (runtime.postStatus === 'measuring' && eventSequence > runtime.measurementArmedSeq &&
      parsed.measured && parsed.lastTotal !== null && parsed.lastTotal > 0 && parsed.windowSize !== null && parsed.windowSize > 0) {
      runtime.postStatus = 'ready';
      runtime.postTokens = parsed.lastTotal;
      runtime.postWindow = parsed.windowSize;
      runtime.captureRunId = '';
      runtime.capturedAt = new Date().toISOString();
      persistThread(runtime);
    }

    if (runtime.historyDirty) scheduleCompactionSync(threadId, 180);
    if (threadId === activeThreadId) renderRisk();
  }

  function normalizeRateLimitSnapshot(value) {
    if (!value || typeof value !== 'object') return null;
    const nested = first(value, ['rateLimits', 'rate_limits']);
    if (nested && nested !== value) return normalizeRateLimitSnapshot(nested);
    const limitId = stringValue(first(value, ['limitId', 'limit_id'])) || 'codex';
    const primary = first(value, ['primary', 'primaryLimit', 'primary_limit']);
    const secondary = first(value, ['secondary', 'secondaryLimit', 'secondary_limit']);
    return { limitId, primary: normalizeRateWindow(primary), secondary: normalizeRateWindow(secondary) };
  }

  function normalizeRateWindow(value) {
    if (!value || typeof value !== 'object') return null;
    const usedPercent = number(first(value, ['usedPercent', 'used_percent']));
    const windowDurationMins = number(first(value, ['windowDurationMins', 'window_minutes', 'windowMinutes']));
    if (usedPercent === null && windowDurationMins === null) return null;
    return { usedPercent, windowDurationMins };
  }

  function mergeRateLimitSnapshot(snapshot, fullSnapshot) {
    if (!snapshot) return;
    const id = snapshot.limitId || 'codex';
    if (fullSnapshot) {
      rateLimitsById.set(id, snapshot);
      return;
    }
    const previous = rateLimitsById.get(id) || { limitId: id, primary: null, secondary: null };
    rateLimitsById.set(id, {
      limitId: id,
      primary: snapshot.primary || previous.primary,
      secondary: snapshot.secondary || previous.secondary
    });
  }

  function codexQuotaWindows() {
    const snapshot = rateLimitsById.get('codex');
    if (!snapshot) return { fiveHour: null, weekly: null };
    const candidates = [snapshot.primary, snapshot.secondary].filter(Boolean);
    const choose = expected => candidates
      .filter(window => isApproximateWindow(window.windowDurationMins, expected))
      .sort((a, b) => Math.abs(a.windowDurationMins - expected) - Math.abs(b.windowDurationMins - expected))[0] || null;
    return { fiveHour: choose(FIVE_HOUR_MINUTES), weekly: choose(WEEKLY_MINUTES) };
  }

  function remainingPercent(window) {
    return window && Number.isFinite(window.usedPercent) ? clamp(100 - window.usedPercent) : null;
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
    } catch (_) { cachedConversationManager = null; }
    if (!hasFullQuotaSnapshot && quotaRequestAttempts < 8 && !quotaRequestTimer) {
      quotaRequestTimer = window.setTimeout(requestRateLimits, 700);
    }
  }

  function resetQuotaForAccountChange() {
    rateLimitsById.clear();
    hasFullQuotaSnapshot = false;
    quotaRequestAttempts = 0;
    if (quotaRequestTimer) window.clearTimeout(quotaRequestTimer);
    quotaRequestTimer = window.setTimeout(requestRateLimits, 120);
    renderUsage();
  }

  function markHistoryDirty(params) {
    const threadId = stringValue(first(params, ['threadId', 'thread_id']));
    if (!threadId) return;
    const runtime = threadRuntime(threadId);
    runtime.syncGeneration += 1;
    runtime.syncInFlight = false;
    runtime.historyDirty = true;
    runtime.validatedThisRun = false;
    if (threadId === activeThreadId) {
      runtime.postStatus = 'syncing';
      renderRisk();
      window.setTimeout(() => scheduleCompactionSync(threadId, 0), 900);
    }
  }

  function dispatchEnvelope(method, params) {
    if (!method || !params || typeof params !== 'object') return;
    eventSequence += 1;
    if (method === 'thread/tokenUsage/updated') {
      handleTokenUsage(params);
      return;
    }
    if (method === 'account/rateLimits/updated') {
      const snapshot = normalizeRateLimitSnapshot(params);
      if (snapshot) mergeRateLimitSnapshot(snapshot, false);
      renderUsage();
      return;
    }
    if (method === 'account/updated') {
      resetQuotaForAccountChange();
      return;
    }
    if (method === 'item/completed') {
      const item = first(params, ['item']);
      if (!isCompactionItem(item)) return;
      const threadId = stringValue(first(params, ['threadId', 'thread_id']));
      const turnId = stringValue(first(params, ['turnId', 'turn_id']));
      registerCompletedCompaction(threadId, turnId, compactionId(item), 'item/completed');
      return;
    }
    if (method === 'thread/compacted') {
      handleLegacyCompacted(params);
      return;
    }
    if (method === 'thread/rollback' || method === 'thread/revert') {
      markHistoryDirty(params);
    }
  }

  const INTERESTING_METHODS = [
    'thread/tokenUsage/updated', 'account/rateLimits/updated', 'account/updated',
    'item/completed', 'thread/compacted', 'thread/rollback', 'thread/revert'
  ];

  const WRAPPER_KEYS = ['data', 'payload', 'message', 'body', 'result', 'response', 'notification', 'event'];

  function consume(raw) {
    let value = raw;
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return;
      if (!INTERESTING_METHODS.some(method => trimmed.includes(method))) return;
      try { value = JSON.parse(trimmed); } catch (_) { return; }
    }
    if (!value || typeof value !== 'object') return;

    const queue = [{ value, depth: 0 }];
    const seen = new WeakSet();
    let visited = 0;
    while (queue.length && visited < MAX_ENVELOPE_NODES) {
      const node = queue.shift();
      const object = node.value;
      if (!object || typeof object !== 'object' || seen.has(object)) continue;
      seen.add(object);
      visited += 1;
      if (!Array.isArray(object) && typeof object.method === 'string' &&
        INTERESTING_METHODS.includes(object.method) && object.params && typeof object.params === 'object') {
        dispatchEnvelope(object.method, object.params);
      }
      if (node.depth >= MAX_ENVELOPE_DEPTH) continue;
      if (Array.isArray(object)) {
        for (let i = 0; i < Math.min(object.length, 8); i++) queue.push({ value: object[i], depth: node.depth + 1 });
      } else {
        for (const key of WRAPPER_KEYS) if (own(object, key)) queue.push({ value: object[key], depth: node.depth + 1 });
      }
    }
  }

  function effectiveRisk(runtime) {
    if (!runtime) return { status: 'syncing', percent: null, tier: 'muted', bars: 0, message: 'Checking session state…' };
    if (runtime.postStatus === 'syncing') return { status: 'syncing', percent: null, tier: 'muted', bars: 0, message: 'Checking session state…' };
    if (runtime.postStatus === 'unavailable') return { status: 'unavailable', percent: null, tier: 'muted', bars: 3, message: 'Session state is unavailable.' };
    if (runtime.postStatus === 'noCompaction') return { status: 'noCompaction', percent: null, tier: 'muted', bars: 0, message: 'No compaction yet.' };
    if (runtime.postStatus === 'measuring') return { status: 'measuring', percent: null, tier: 'muted', bars: 3, message: 'Waiting for measured context usage.' };
    if (runtime.postStatus === 'notCaptured') return { status: 'notCaptured', percent: null, tier: 'muted', bars: 3, message: 'Post-compaction context was not captured.' };

    const percent = ratioPercent(runtime.postTokens, runtime.postWindow);
    if (percent === null) return { status: 'unavailable', percent: null, tier: 'muted', bars: 3, message: 'Session state is unavailable.' };
    if (runtime.currentContextWindow > 0 && Math.round(runtime.currentContextWindow) !== Math.round(runtime.postWindow)) {
      return { status: 'staleWindow', percent, tier: 'muted', bars: 3, message: 'Context window has changed since this compaction.' };
    }
    const ratio = percent / 100;
    if (ratio < GOOD_LIMIT) return { status: 'ready', percent, tier: 'green', bars: 1, message: 'This session is in good shape.' };
    if (ratio < CAUTION_LIMIT) return { status: 'ready', percent, tier: 'yellow', bars: 2, message: 'You can keep using this session.' };
    if (ratio < HIGH_LIMIT) return { status: 'ready', percent, tier: 'red', bars: 3, message: 'Consider starting a new session soon.' };
    return { status: 'ready', percent, tier: 'purple', bars: 3, message: 'Starting a new session is recommended.' };
  }

  function riskColor(tier) {
    return tier === 'green' ? COLORS.green : tier === 'yellow' ? COLORS.yellow :
      tier === 'red' ? COLORS.red : tier === 'purple' ? COLORS.purple : COLORS.muted;
  }

  function createHost() {
    const element = document.createElement('span');
    element.dataset.codexSessionHealthHud = 'renderer-v1';
    element.style.cssText = 'display:inline-flex;align-items:center;flex:0 0 auto;min-width:0;height:28px;';
    const root = element.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        :host{display:inline-flex;align-items:center;flex:0 0 auto;font:inherit}
        .hud{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 2px;white-space:nowrap}
        .stat{display:inline-flex;align-items:center;height:22px;border-radius:6px;outline:none}
        .stat:focus-visible{box-shadow:0 0 0 2px rgba(128,128,128,.35)}
        .usage-icon{width:24px;height:12px;display:block}
        .risk-icon{width:15px;height:12px;display:block}
        .usage-track,.risk-track{fill:${COLORS.track};opacity:.50}
        .usage-fill{fill:${COLORS.green};transform-box:fill-box;transform-origin:left center}
        .risk-bar{opacity:0;stroke-width:.5;shape-rendering:geometricPrecision;transform-box:fill-box;transform-origin:center bottom}
        @media(max-width:760px){.hud{gap:5px;padding:0 1px}}
      </style>
      <span class="hud" aria-label="${PRODUCT_NAME}">
        <span class="stat" data-stat="usage" tabindex="0" aria-label="Codex usage limits">
          <svg class="usage-icon" viewBox="0 0 24 12" aria-hidden="true">
            <rect class="usage-track" x="1" y="4.5" width="22" height="3" rx="1.5"/>
            <rect class="usage-fill" data-usage-fill x="1" y="4.5" width="0" height="3" rx="1.5"/>
          </svg>
        </span>
        <span class="stat" data-stat="risk" tabindex="0" aria-label="Post-compaction context pressure">
          <svg class="risk-icon" viewBox="0 0 15 12" aria-hidden="true">
            <rect class="risk-track" x="1" y="1" width="2.6" height="10" rx="1.3"/>
            <rect class="risk-track" x="6.2" y="1" width="2.6" height="10" rx="1.3"/>
            <rect class="risk-track" x="11.4" y="1" width="2.6" height="10" rx="1.3"/>
            <rect class="risk-bar" data-risk-bar x="1" y="1" width="2.6" height="10" rx="1.3"/>
            <rect class="risk-bar" data-risk-bar x="6.2" y="1" width="2.6" height="10" rx="1.3"/>
            <rect class="risk-bar" data-risk-bar x="11.4" y="1" width="2.6" height="10" rx="1.3"/>
          </svg>
        </span>
      </span>`;
    const usageStat = root.querySelector('[data-stat="usage"]');
    const riskStat = root.querySelector('[data-stat="risk"]');
    const refs = {
      usageStat,
      riskStat,
      usageFill: root.querySelector('[data-usage-fill]'),
      riskBars: Array.from(root.querySelectorAll('[data-risk-bar]'))
    };
    usageStat.addEventListener('mouseenter', () => showTooltipSoon('usage', usageStat));
    usageStat.addEventListener('mouseleave', hideTooltips);
    usageStat.addEventListener('focus', () => showTooltipNow('usage', usageStat));
    usageStat.addEventListener('blur', hideTooltips);
    riskStat.addEventListener('mouseenter', () => showTooltipSoon('risk', riskStat));
    riskStat.addEventListener('mouseleave', hideTooltips);
    riskStat.addEventListener('focus', () => showTooltipNow('risk', riskStat));
    riskStat.addEventListener('blur', hideTooltips);
    return { element, refs };
  }

  function renderUsage() {
    if (!ui) return;
    const { weekly } = codexQuotaWindows();
    const remaining = remainingPercent(weekly);
    const width = remaining === null || remaining <= 0 ? 0 : Math.max(1.5, remaining * 22 / 100);
    const fill = ui.usageFill;
    const previousWidth = Number(fill.getAttribute('width')) || 0;
    if (Math.abs(previousWidth - width) > 0.01) {
      fill.setAttribute('width', width.toFixed(2));
      if (motionAllowed() && width > 0) {
        for (const animation of fill.getAnimations()) animation.cancel();
        fill.animate([{ opacity: .72 }, { opacity: 1 }], { duration: 260, easing: 'ease-out' });
      }
    }
    fill.style.fill = remaining === null ? COLORS.muted : remaining <= 15 ? COLORS.red : remaining <= 35 ? COLORS.yellow : COLORS.green;
    ui.usageStat.style.opacity = remaining === null ? '.55' : '1';
    ui.usageStat.setAttribute('aria-label', remaining === null ? 'Codex weekly usage unavailable' : `Codex weekly quota: ${Math.round(remaining)} percent remaining`);
    if (usageTooltip && usageTooltip.style.display !== 'none') updateUsageTooltip();
  }

  function renderRisk() {
    if (!ui) return;
    const runtime = threadRuntime(activeThreadId);
    const risk = effectiveRisk(runtime);
    const color = riskColor(risk.tier);
    const visualKey = `${activeThreadId}|${risk.status}|${risk.tier}|${risk.bars}`;
    if (visualKey !== lastRiskVisualKey) {
      lastRiskVisualKey = visualKey;
      ui.riskBars.forEach((bar, index) => {
        bar.style.fill = color;
        bar.style.stroke = risk.tier === 'purple' ? 'rgba(236,224,255,.58)' : 'none';
        bar.style.opacity = index < risk.bars ? (risk.status === 'unavailable' || risk.status === 'notCaptured' || risk.status === 'staleWindow' ? '.72' : '1') : '0';
      });
      ui.riskStat.style.opacity = risk.status === 'syncing' || risk.status === 'noCompaction' ? '.72' : '1';
      ui.riskStat.setAttribute('aria-label', `Post-compaction context: ${risk.message}`);
    }
    if (runtime && runtime.measuringAnimationPending && risk.status === 'measuring') {
      runtime.measuringAnimationPending = false;
      animateMeasuring(ui.riskBars);
    }
    if (riskTooltip && riskTooltip.style.display !== 'none') updateRiskTooltip();
  }

  function renderActive() {
    renderUsage();
    renderRisk();
  }

  function animateMeasuring(bars) {
    if (!motionAllowed()) return;
    bars.forEach((bar, index) => {
      for (const animation of bar.getAnimations()) animation.cancel();
      bar.animate([
        { transform: 'scaleY(.42)', opacity: .35 },
        { transform: 'scaleY(1.08)', opacity: 1, offset: .72 },
        { transform: 'scaleY(1)', opacity: 1 }
      ], { duration: 620, delay: index * 90, easing: 'cubic-bezier(.2,.75,.25,1)' });
    });
  }

  function tooltipBase(kind, width) {
    const element = document.createElement('div');
    element.dataset.codexSessionHealthTooltip = kind;
    element.setAttribute('role', 'tooltip');
    element.style.cssText = `position:fixed;z-index:2147483647;display:none;width:${width}px;box-sizing:border-box;padding:11px 12px;border:1px solid rgba(255,255,255,.14);border:1px solid color-mix(in srgb, CanvasText 14%, transparent);border-radius:12px;background:#303030;background:color-mix(in srgb, Canvas 96%, transparent);box-shadow:0 12px 28px rgba(0,0,0,.28);color:#eeeeee;color:CanvasText;font:500 12px/1.38 system-ui,sans-serif;letter-spacing:0;pointer-events:none;color-scheme:light dark;`;
    document.body.appendChild(element);
    return element;
  }

  function ensureUsageTooltip() {
    if (usageTooltip) return usageTooltip;
    usageTooltip = tooltipBase('usage', 205);
    usageTooltip.innerHTML = `
      <div style="display:grid;gap:7px">
        <div style="font-weight:650;opacity:.72">Usage limits</div>
        <div style="display:flex;justify-content:space-between;gap:18px"><span style="opacity:.72">5-hour</span><span data-u-5h style="font-variant-numeric:tabular-nums">—</span></div>
        <div style="display:flex;justify-content:space-between;gap:18px"><span style="opacity:.72">Weekly</span><span data-u-week style="font-variant-numeric:tabular-nums">—</span></div>
      </div>`;
    return usageTooltip;
  }

  function ensureRiskTooltip() {
    if (riskTooltip) return riskTooltip;
    riskTooltip = tooltipBase('risk', 282);
    riskTooltip.innerHTML = `
      <div style="display:grid;gap:10px">
        <div>
          <div style="font-weight:650;opacity:.72">Post-compaction context</div>
          <div data-r-post style="margin-top:2px;font-variant-numeric:tabular-nums">—</div>
          <div data-r-message style="margin-top:3px;opacity:.78"></div>
        </div>
        <div style="height:1px;background:currentColor;opacity:.10"></div>
        <div style="display:grid;grid-template-columns:1fr auto;gap:5px 18px">
          <span style="opacity:.72">Current context</span><span data-r-current style="font-variant-numeric:tabular-nums">—</span>
          <span style="opacity:.72">Compactions</span><span data-r-count style="font-variant-numeric:tabular-nums">—</span>
          <span style="opacity:.72">Session tokens</span><span data-r-total style="font-variant-numeric:tabular-nums">—</span>
        </div>
      </div>`;
    return riskTooltip;
  }

  function updateUsageTooltip() {
    const tooltip = ensureUsageTooltip();
    const { fiveHour, weekly } = codexQuotaWindows();
    const five = remainingPercent(fiveHour);
    const week = remainingPercent(weekly);
    tooltip.querySelector('[data-u-5h]').textContent = five === null ? '—' : `${Math.round(five)}% remaining`;
    tooltip.querySelector('[data-u-week]').textContent = week === null ? '—' : `${Math.round(week)}% remaining`;
  }

  function updateRiskTooltip() {
    const tooltip = ensureRiskTooltip();
    const runtime = threadRuntime(activeThreadId);
    const risk = effectiveRisk(runtime);
    const post = tooltip.querySelector('[data-r-post]');
    const message = tooltip.querySelector('[data-r-message]');
    const current = tooltip.querySelector('[data-r-current]');
    const count = tooltip.querySelector('[data-r-count]');
    const total = tooltip.querySelector('[data-r-total]');
    if (risk.status === 'ready' || risk.status === 'staleWindow') {
      post.textContent = `${formatTokens(runtime.postTokens)} / ${formatTokens(runtime.postWindow)}   ${formatPercent(risk.percent)}`;
    } else if (risk.status === 'measuring') {
      post.textContent = 'Measuring…';
    } else if (risk.status === 'syncing') {
      post.textContent = 'Checking…';
    } else {
      post.textContent = '—';
    }
    message.textContent = risk.message;
    if (runtime && runtime.currentContextTokens >= 0 && runtime.currentContextWindow > 0) {
      current.textContent = `${formatTokens(runtime.currentContextTokens)} / ${formatTokens(runtime.currentContextWindow)}   ${formatPercent(runtime.currentContextPercent)}`;
    } else {
      current.textContent = '—';
    }
    count.textContent = runtime && Number.isInteger(runtime.compactionCount) && runtime.compactionCount >= 0 ? String(runtime.compactionCount) : '…';
    total.textContent = runtime && runtime.sessionTotalTokens >= 0 ? formatTokens(runtime.sessionTotalTokens) : '—';
  }

  function positionTooltip(tooltip, anchor) {
    if (!tooltip || !anchor || tooltip.style.display === 'none') return;
    const rect = anchor.getBoundingClientRect();
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    const left = Math.max(8, Math.min(innerWidth - width - 8, rect.left + rect.width / 2 - width / 2));
    const above = rect.top - height - 9;
    const top = above >= 8 ? above : Math.min(innerHeight - height - 8, rect.bottom + 9);
    tooltip.style.left = `${Math.round(left)}px`;
    tooltip.style.top = `${Math.round(top)}px`;
  }

  function showTooltipSoon(kind, anchor) {
    if (tooltipTimer) window.clearTimeout(tooltipTimer);
    tooltipTimer = window.setTimeout(() => {
      tooltipTimer = 0;
      showTooltipNow(kind, anchor);
    }, 420);
  }

  function showTooltipNow(kind, anchor) {
    hideTooltips(false);
    tooltipKind = kind;
    const tooltip = kind === 'usage' ? ensureUsageTooltip() : ensureRiskTooltip();
    if (kind === 'usage') updateUsageTooltip(); else updateRiskTooltip();
    tooltip.style.display = 'block';
    positionTooltip(tooltip, anchor);
  }

  function hideTooltips(clearTimer = true) {
    if (clearTimer && tooltipTimer) window.clearTimeout(tooltipTimer);
    tooltipTimer = 0;
    tooltipKind = '';
    if (usageTooltip) usageTooltip.style.display = 'none';
    if (riskTooltip) riskTooltip.style.display = 'none';
  }

  function findComposerFooter() {
    if (toolbar && toolbar.isConnected && visible(toolbar)) return toolbar;
    const editor = currentComposer();
    if (!editor) return null;
    let footer = editor;
    while (footer && footer !== document.body && !String(footer.className).includes('ComposerLayoutFooter')) {
      footer = footer.parentElement;
    }
    toolbar = footer && footer !== document.body ? footer : null;
    return toolbar;
  }

  function isContextAriaLabel(label) {
    return /context|컨텍스트|上下文/i.test(label || '');
  }

  function findNativeContext(container) {
    if (nativeContext && nativeContext.isConnected && isContextAriaLabel(nativeContext.getAttribute('aria-label'))) {
      return nativeContext;
    }
    const scope = container || document;
    nativeContext = Array.from(scope.querySelectorAll('[role="img"][aria-label]'))
      .find(element => visible(element) && isContextAriaLabel(element.getAttribute('aria-label'))) || null;
    return nativeContext;
  }

  function directChildUnder(ancestor, element) {
    if (!ancestor || !element || !ancestor.contains(element)) return null;
    let current = element;
    while (current && current.parentElement !== ancestor) current = current.parentElement;
    return current && current.parentElement === ancestor ? current : null;
  }

  function mount() {
    if (disposed || document.hidden) return;
    refreshActiveThread();

    const footer = findComposerFooter();
    if (!footer) {
      if (host) host.remove();
      host = null;
      ui = null;
      return;
    }

    const contextElement = findNativeContext(footer);
    let anchorSlot = contextElement && contextElement.parentElement;
    let anchorGroup = anchorSlot && anchorSlot.parentElement;

    if (anchorSlot && anchorGroup && !footer.contains(anchorGroup)) {
      anchorSlot = null;
      anchorGroup = null;
    }

    if (!anchorSlot || !anchorGroup) {
      const modelButton = Array.from(footer.querySelectorAll('button[aria-haspopup="menu"]'))
        .find(button => button.hasAttribute('data-codex-intelligence-trigger')) ||
        Array.from(footer.querySelectorAll('button[aria-haspopup="menu"]')).filter(visible).at(-1);
      if (modelButton) {
        anchorGroup = modelButton.parentElement;
        while (anchorGroup && anchorGroup !== footer && getComputedStyle(anchorGroup).display !== 'flex') {
          anchorGroup = anchorGroup.parentElement;
        }
        if (anchorGroup) anchorSlot = directChildUnder(anchorGroup, modelButton);
      }
    }

    if (!anchorSlot || !anchorGroup) return;
    if (host && host.isConnected && host.parentElement === anchorGroup && host.nextElementSibling === anchorSlot) {
      renderActive();
      return;
    }

    if (host) host.remove();
    const created = createHost();
    host = created.element;
    ui = created.refs;
    lastRiskVisualKey = '';
    anchorGroup.insertBefore(host, anchorSlot);
    renderActive();
    if (!hasFullQuotaSnapshot && !quotaRequestTimer) quotaRequestTimer = window.setTimeout(requestRateLimits, 100);
  }

  function scheduleMount(delay = 180) {
    if (mountTimer || disposed || document.hidden) return;
    mountTimer = window.setTimeout(() => {
      mountTimer = 0;
      if (host && host.isConnected && toolbar && toolbar.isConnected && nativeContext && nativeContext.isConnected) {
        scheduleActiveThreadRefresh(0);
        return;
      }
      cachedComposer = null;
      toolbar = null;
      nativeContext = null;
      try { mount(); } catch (_) { scheduleMount(220); }
    }, delay);
  }

  const onMessage = event => consume(event.data);
  const onViewport = () => {
    if (usageTooltip && usageTooltip.style.display !== 'none' && ui) positionTooltip(usageTooltip, ui.usageStat);
    if (riskTooltip && riskTooltip.style.display !== 'none' && ui) positionTooltip(riskTooltip, ui.riskStat);
  };
  window.addEventListener('message', onMessage, true);
  window.addEventListener('resize', onViewport, true);
  window.addEventListener('scroll', onViewport, true);
  const observer = new MutationObserver(() => {
    if (disposed || document.hidden) return;
    if (!host || !host.isConnected || !toolbar || !toolbar.isConnected || !nativeContext || !nativeContext.isConnected) scheduleMount(80);
    scheduleActiveThreadRefresh(100);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  const onVisibility = () => {
    if (!document.hidden) {
      scheduleMount(0);
      scheduleActiveThreadRefresh(0);
    }
  };
  document.addEventListener('visibilitychange', onVisibility, true);

  const dispose = () => {
    disposed = true;
    observer.disconnect();
    document.removeEventListener('visibilitychange', onVisibility, true);
    window.removeEventListener('message', onMessage, true);
    window.removeEventListener('resize', onViewport, true);
    window.removeEventListener('scroll', onViewport, true);
    if (mountTimer) window.clearTimeout(mountTimer);
    if (activeThreadTimer) window.clearTimeout(activeThreadTimer);
    if (quotaRequestTimer) window.clearTimeout(quotaRequestTimer);
    if (tooltipTimer) window.clearTimeout(tooltipTimer);
    mountTimer = activeThreadTimer = quotaRequestTimer = tooltipTimer = 0;
    if (host) host.remove();
    host = null;
    ui = null;
    if (usageTooltip) usageTooltip.remove();
    if (riskTooltip) riskTooltip.remove();
    usageTooltip = riskTooltip = null;
    if (window[INSTANCE] && window[INSTANCE].dispose === dispose) delete window[INSTANCE];
  };

  window[INSTANCE] = {
    version: 1,
    remount: () => scheduleMount(0),
    dispose,
    snapshot: () => ({
      activeThreadId,
      runId,
      threadCount: runtimeThreads.size,
      historyListCapability,
      quotaWindows: codexQuotaWindows()
    }),
    test: TEST_MODE ? {
      normalizeTokenUsage,
      usageBreakdownMeasured,
      normalizeRateLimitSnapshot,
      mergeRateLimitSnapshot,
      codexQuotaWindows,
      remainingPercent,
      effectiveRisk,
      isApproximateWindow,
      isContextAriaLabel,
      clearRateLimits: () => rateLimitsById.clear()
    } : undefined
  };

  if (!TEST_MODE) {
    scheduleMount(0);
    quotaRequestTimer = window.setTimeout(requestRateLimits, 180);
  }
})();