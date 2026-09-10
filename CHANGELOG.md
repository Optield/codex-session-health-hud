# Changelog

## Unreleased

- Remove the `Session tokens` field and its cumulative-session telemetry path; the Risk tooltip now focuses on post-compaction context, current context, and compaction count.
- Keep renderer-state hydration only for missing current-context telemetry.

## 0.1.4 - 2026-09-10

- Hydrate missing `Current context` and `Session tokens` from Codex Desktop's already-loaded `latestTokenUsageInfo` when the injected HUD misses the startup/thread-reentry token-usage replay.
- Fill only telemetry fields that are still missing, so an already-observed live `thread/tokenUsage/updated` value is never replaced by the renderer-state fallback.
- Keep post-compaction snapshot state and the persistent state schema unchanged; the fallback performs no extra app-server resume/read request and does not read Codex JSONL or SQLite data.
- Add regression coverage for full hydration, partial hydration, preservation of existing live telemetry, and live-event updates after fallback hydration.

## 0.1.3 - 2026-09-10

- Preserve valid post-compaction snapshots while thread history is revalidated after thread switches, renderer reloads, or Codex restarts; transient `Syncing` state no longer causes a matching captured snapshot to be discarded as `Not captured`.
- Keep the existing snapshot only when its compaction ID still matches the latest compaction and its captured token/window payload is valid; a genuinely newer compaction still invalidates the old snapshot as intended.
- Add regression coverage for matching persisted snapshots, mismatched compaction IDs, and active in-run measurements.

## 0.1.2 - 2026-09-07

- Show the local capture date and time directly under the post-compaction value in the Risk tooltip, making repeated identical percentages verifiably fresh without adding history UI or new persistent state.

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
