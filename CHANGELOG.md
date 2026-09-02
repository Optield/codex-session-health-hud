# Changelog

## 0.1.0 - 2026-09-03

- Initial Codex Session Health HUD implementation.
- Keep the Codex Desktop composer-integrated HUD and loopback package launcher architecture.
- Show weekly quota as the visible usage bar and both 5-hour/weekly remaining values on hover.
- Replace compaction-count severity bars with post-compaction context pressure tiers: gray, green, yellow, red, and violet.
- Capture post-compaction context only after completed `contextCompaction` items and a later measured token-usage update.
- Use `last.totalTokens` for active context, `total.totalTokens` for cumulative session usage, and the effective `modelContextWindow` supplied by Codex.
- Track live background-thread events independently from the currently visible thread.
- Synchronize compaction count through `thread/items/list` with rollback-aware anchor reconciliation and legacy loaded-history fallback.
- Add `Syncing`, `Measuring`, `Not captured`, `Unavailable`, and context-window-stale states instead of guessing risk.
- Merge sparse rate-limit notifications by `limitId` and clear account quota state on account changes.
- Remove session JSONL, SQLite, and secondary app-server monitoring dependencies.
- Add an atomic, bounded `%LOCALAPPDATA%\CodexSessionHealthHUD\state.json` store.
- Make uninstall remove the complete marked application directory while leaving all Codex data untouched.
