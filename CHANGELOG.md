# Changelog

## 0.1.1 - 2026-09-03

- Fix Start menu launch failures caused by resolving the install directory from `$PSScriptRoot` inside a parameter default; the launcher now resolves its own path at runtime and the shortcut passes `-InstallDir` explicitly.
- Surface launcher startup exceptions in a Windows message box instead of silently closing the PowerShell window.
- Mount the HUD against the native Codex context ring instead of guessing the smallest composer flex group.
- Recognize localized native context-ring labels, including Korean `컨텍스트`, with regression coverage.
- Add a local-only `Install-Easy.bat` and a prebuilt Windows CI artifact for non-developer installation; the easy installer does not download code or use `-EncodedCommand`.
- Add package-layout regression checks for the launcher path fix, safe easy-installer invariants, required files, and README assets.
- Include README assets in source installs and prebuilt packages.
- Replace the textual toolbar mockup in both READMEs with a screenshot of the actual composer integration.

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
