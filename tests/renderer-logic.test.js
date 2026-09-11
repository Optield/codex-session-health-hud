'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');

global.window = global;
window.addEventListener = () => {};
window.removeEventListener = () => {};
window.__codexSessionHealthHudTestMode = true;
window.__codexSessionHealthHudBootstrap = { runId: 'test-run', threads: {} };
global.document = {
  hidden: true,
  documentElement: {},
  querySelectorAll: () => [],
  addEventListener: () => {},
  removeEventListener: () => {}
};
global.MutationObserver = class { observe() {} disconnect() {} };

require(path.join(__dirname, '..', 'RendererHudScript.js'));
const instance = window[Symbol.for('codex-session-health-hud.renderer.v1')];
assert.ok(instance && instance.test, 'renderer test hooks are available');
const t = instance.test;

const measuredUsage = t.normalizeTokenUsage({
  threadId: 'thread-1',
  tokenUsage: {
    last: {
      totalTokens: 103184,
      inputTokens: 98000,
      cachedInputTokens: 88000,
      cacheWriteInputTokens: 0,
      outputTokens: 5184,
      reasoningOutputTokens: 900
    },
    modelContextWindow: 258400
  }
});
assert.equal(measuredUsage.lastTotal, 103184, 'active context uses last.totalTokens');
assert.equal(measuredUsage.windowSize, 258400, 'effective context window is used as reported');
assert.equal(measuredUsage.measured, true, 'non-zero breakdown is measured usage');

const localEstimate = t.normalizeTokenUsage({
  tokenUsage: {
    last: {
      totalTokens: 103184,
      inputTokens: 0,
      cachedInputTokens: 0,
      cacheWriteInputTokens: 0,
      outputTokens: 0,
      reasoningOutputTokens: 0
    },
    modelContextWindow: 258400
  }
});
assert.equal(localEstimate.measured, false, 'all-zero local re-estimate is rejected for post-compaction capture');

const rendererSnapshot = {
  last: {
    totalTokens: 132304,
    inputTokens: 131989,
    cachedInputTokens: 130944,
    cacheWriteInputTokens: 0,
    outputTokens: 315,
    reasoningOutputTokens: 173
  },
  modelContextWindow: 258400
};
const missingLiveUsage = {
  currentContextTokens: -1,
  currentContextWindow: -1,
  currentContextPercent: -1,
  postStatus: 'ready',
  postTokens: 34002,
  postWindow: 258400
};
assert.equal(t.hydrateCurrentUsageFromSnapshot(missingLiveUsage, rendererSnapshot), true,
  'renderer snapshot hydrates usage missed during startup replay');
assert.equal(missingLiveUsage.currentContextTokens, 132304);
assert.equal(missingLiveUsage.currentContextWindow, 258400);
assert.equal(missingLiveUsage.currentContextPercent, 132304 * 100 / 258400);
assert.equal(missingLiveUsage.postStatus, 'ready', 'usage hydration does not change post-compaction state');
assert.equal(missingLiveUsage.postTokens, 34002, 'usage hydration does not replace post-compaction tokens');

const newerLiveUsage = {
  currentContextTokens: 150000,
  currentContextWindow: 258400,
  currentContextPercent: 150000 * 100 / 258400,
};
assert.equal(t.hydrateCurrentUsageFromSnapshot(newerLiveUsage, rendererSnapshot), false,
  'renderer fallback never overwrites already observed live telemetry');
assert.equal(newerLiveUsage.currentContextTokens, 150000);

const liveUpdate = t.normalizeTokenUsage({ tokenUsage: {
  last: { totalTokens: 160000, inputTokens: 159000, cachedInputTokens: 120000, outputTokens: 1000 },
  modelContextWindow: 258400
}});
assert.equal(t.applyUsageTelemetry(missingLiveUsage, liveUpdate, false), true,
  'live telemetry remains authoritative after renderer hydration');
assert.equal(missingLiveUsage.currentContextTokens, 160000);

function readyRisk(percent, currentWindow = 100) {
  return t.effectiveRisk({
    postStatus: 'ready',
    postTokens: percent,
    postWindow: 100,
    currentContextWindow: currentWindow
  });
}
assert.equal(readyRisk(44.999).tier, 'green');
assert.equal(readyRisk(45).tier, 'yellow');
assert.equal(readyRisk(64.999).tier, 'yellow');
assert.equal(readyRisk(65).tier, 'red');
assert.equal(readyRisk(79.999).tier, 'red');
assert.equal(readyRisk(80).tier, 'purple');
assert.equal(readyRisk(40, 200).status, 'staleWindow');

const capturedIso = '2026-09-07T07:40:22.000Z';
const capturedDate = new Date(capturedIso);
const padCaptured = value => String(value).padStart(2, '0');
const expectedCaptured = `${capturedDate.getFullYear()}-${padCaptured(capturedDate.getMonth() + 1)}-${padCaptured(capturedDate.getDate())} ${padCaptured(capturedDate.getHours())}:${padCaptured(capturedDate.getMinutes())}`;
assert.equal(t.formatCapturedAt(capturedIso), expectedCaptured, 'capture time is formatted in local YYYY-MM-DD HH:mm');
assert.equal(t.formatCapturedAt('not-a-date'), '', 'invalid capture time is hidden');


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

const persistedReadyDuringSync = {
  postStatus: 'syncing',
  snapshotCompactionId: 'compact-1',
  postTokens: 34002,
  postWindow: 258400,
  captureRunId: '',
  capturedAt: capturedIso
};
t.reconcileSnapshotToHistory(persistedReadyDuringSync, 'compact-1');
assert.equal(persistedReadyDuringSync.postStatus, 'ready', 'matching persisted snapshot survives transient syncing state');
assert.equal(persistedReadyDuringSync.postTokens, 34002, 'matching persisted snapshot keeps captured tokens');
assert.equal(persistedReadyDuringSync.postWindow, 258400, 'matching persisted snapshot keeps captured window');
assert.equal(persistedReadyDuringSync.capturedAt, capturedIso, 'matching persisted snapshot keeps capture time');

const mismatchedPersistedSnapshot = {
  postStatus: 'syncing',
  snapshotCompactionId: 'compact-1',
  postTokens: 34002,
  postWindow: 258400,
  captureRunId: '',
  capturedAt: capturedIso
};
t.reconcileSnapshotToHistory(mismatchedPersistedSnapshot, 'compact-2');
assert.equal(mismatchedPersistedSnapshot.postStatus, 'notCaptured', 'different latest compaction invalidates an old snapshot');
assert.equal(mismatchedPersistedSnapshot.snapshotCompactionId, 'compact-2');
assert.equal(mismatchedPersistedSnapshot.postTokens, -1);
assert.equal(mismatchedPersistedSnapshot.postWindow, -1);
assert.equal(mismatchedPersistedSnapshot.capturedAt, '');

const activeMeasurement = {
  postStatus: 'measuring',
  snapshotCompactionId: 'compact-3',
  postTokens: -1,
  postWindow: -1,
  captureRunId: 'test-run',
  capturedAt: ''
};
t.reconcileSnapshotToHistory(activeMeasurement, 'compact-3');
assert.equal(activeMeasurement.postStatus, 'measuring', 'current-run measurement remains armed during reconciliation');

t.clearRateLimits();
t.mergeRateLimitSnapshot(t.normalizeRateLimitSnapshot({
  rateLimits: {
    limitId: 'codex',
    primary: { usedPercent: 20, windowDurationMins: 300 },
    secondary: { usedPercent: 30, windowDurationMins: 10080 }
  }
}), true);
let windows = t.codexQuotaWindows();
assert.equal(t.remainingPercent(windows.fiveHour), 80);
assert.equal(t.remainingPercent(windows.weekly), 70);

t.mergeRateLimitSnapshot(t.normalizeRateLimitSnapshot({
  rateLimits: {
    limitId: 'gpt-reserve',
    primary: { usedPercent: 99, windowDurationMins: 300 }
  }
}), false);
windows = t.codexQuotaWindows();
assert.equal(t.remainingPercent(windows.fiveHour), 80, 'non-Codex limits do not overwrite Codex quota');

assert.equal(t.isApproximateWindow(285, 300), true);
assert.equal(t.isApproximateWindow(315, 300), true);
assert.equal(t.isApproximateWindow(284, 300), false);
assert.equal(t.isApproximateWindow(9576, 10080), true);
assert.equal(t.isApproximateWindow(10584, 10080), true);

assert.equal(t.isContextAriaLabel('Context usage: 92%'), true);
assert.equal(t.isContextAriaLabel('컨텍스트 사용량: 92%'), true);
assert.equal(t.isContextAriaLabel('上下文使用量：92%'), true);
assert.equal(t.isContextAriaLabel('Usage limits'), false);

console.log('renderer logic: ok');
