'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');

global.window = global;
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
    total: { totalTokens: 12840000 },
    modelContextWindow: 258400
  }
});
assert.equal(measuredUsage.lastTotal, 103184, 'active context uses last.totalTokens');
assert.equal(measuredUsage.sessionTotal, 12840000, 'session total uses total.totalTokens');
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
    total: { totalTokens: 12840000 },
    modelContextWindow: 258400
  }
});
assert.equal(localEstimate.measured, false, 'all-zero local re-estimate is rejected for post-compaction capture');

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
