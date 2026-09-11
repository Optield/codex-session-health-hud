# Changelog

## 0.1.6 - 2026-09-12

- Bind each HUD host run to the Codex browser process that owns the local DevTools listener, so `CodexSessionHealthHUD.exe` exits instead of surviving into a later Codex run. Missing endpoints, permanently missing main renderer targets, and repeated attach failures now have bounded grace periods while normal connected operation remains event-driven.
- Validate the DevTools listener owner against the installed `OpenAI.Codex` package and distinguish the Electron browser process from renderer/utility helpers before attaching or deciding that Codex is already running.
- Treat JavaScript exceptions returned through CDP `Runtime.evaluate` as failed injection, restrict navigation reinjection to top-level frames, and keep low-frequency reinjection retries only while the renderer is actually unavailable.
- Retry transient `thread/items/list` failures with bounded backoff without disabling the current API or hydrating the entire thread; legacy reconciliation now uses only already-loaded complete history with bounded traversal.
- Replace the timing-based legacy compaction dedupe with bounded per-turn ordinal pairing, so primary and legacy compaction events can arrive in either order, including multiple compactions in one turn, without double-counting or discarding an already-captured snapshot.
- Never synthesize a `Captured` timestamp for a snapshot whose measurement time is unknown; invalid persisted timestamps are sanitized instead.
- Recover the initial account-rate-limit snapshot with capped backoff only while it is unavailable, pause that recovery while the renderer is hidden, and stop retrying immediately after a full quota snapshot is obtained.
- Keep the bounded state store writable at its 10,000-thread / 4 MiB limits by evicting lower-value entries only when a hard limit is actually exceeded; ordinary persistence keeps the previous single-serialization event-driven path.
- Reject non-empty unmarked custom install directories, and make uninstall remove only known HUD-owned files while preserving unrelated files, non-empty Start-menu folders, and the install marker when cleanup is incomplete.
- Add permanent Windows regression coverage for host lifetime, endpoint/renderer transitions, state eviction, injection exceptions, install/uninstall safety, renderer recovery, history fallback, compaction dedupe, and package layout.

## 0.1.5 - 2026-09-10

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
