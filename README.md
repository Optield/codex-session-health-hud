# Codex Session Health HUD

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)](#requirements)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![Korean README](https://img.shields.io/badge/README-한국어-4c8bf5)](README.ko.md)

Long-running Codex sessions accumulate active context. As the working set grows and repeated compactions retain more of it, a thread can become progressively less efficient to continue and may eventually benefit from a clean session boundary. **Codex Session Health HUD** was built to make that transition easier to judge from observable context behavior instead of elapsed time, task count, or intuition.

It is a lightweight Windows companion for Codex Desktop centered on one practical decision:

> **Is this session still healthy enough to keep using, or is post-compaction pressure high enough that starting a fresh session is worth considering?**

Instead of opening a separate monitoring window, the HUD is inserted cleanly into the Codex composer toolbar, immediately to the **left of the native context ring**:

```text
[ Weekly usage ] [ Post-compaction risk ] [ Native Codex context ring ]
```

The native ring is left untouched. The HUD adds only the information Codex does not currently surface together: post-compaction pressure, compaction count, cumulative session tokens, and both account quota windows.

## Post-compaction risk

The three vertical bars represent the **residual context pressure immediately after the most recent compaction that the HUD successfully measured**.

| Post-compaction context | Display | Guidance |
| --- | --- | --- |
| No compaction | Gray | `No compaction yet.` |
| Measuring | Gray | `Waiting for measured context usage.` |
| Not captured / unavailable | Gray | No risk is guessed |
| `<45%` | Green | `This session is in good shape.` |
| `45–65%` | Yellow | `You can keep using this session.` |
| `65–80%` | Red | `Consider starting a new session soon.` |
| `>=80%` | Purple | `Starting a new session is recommended.` |

Hovering the risk indicator shows the session data used to interpret that signal:

```text
Post-compaction context
103K / 258K   39.9%
This session is in good shape.

Current context
187K / 258K   72.4%

Compactions
3

Session tokens
12.84M
```

The risk bar is intentionally based on **post-compaction context**, not current context. If a compaction leaves the session at 39.9% and the current context later grows to 85%, the bar remains tied to the 39.9% compaction result until another compaction occurs. This makes it a measure of how much context pressure survived the last compaction rather than a second copy of the native context ring.

## Why 65%?

The 65% boundary is an **evidence-informed operational threshold**, not an official OpenAI session policy. It combines two related signals: how much runway remains before the next normal compaction region, and how much of the context window is already occupied by information that survived the previous compaction.

Codex currently exposes an effective model context window that is approximately 95% of the model's raw window, while automatic compaction is normally triggered near 90% of the raw window. Expressed against the effective window reported to the client, that default compaction region is roughly **94.7%**.

That makes post-compaction occupancy directly useful as a headroom signal:

- At **45%**, roughly **49.7 percentage points** of the effective window remain before the default compaction region — close to half a fresh working window.
- At **65%**, that runway falls to roughly **29.7 percentage points**. A compaction intended to reclaim working space has left almost two thirds of the effective window occupied, so the next compaction cycle is materially closer.
- At **80%**, only about **14.7 percentage points** remain, which is why the HUD treats this as a separate critical tier.

There is a second reason this matters. Compaction is not simply deletion: it has to preserve enough instructions, decisions, code state, tool results, constraints, and summarized history for the thread to remain coherent. If the context is still heavily occupied immediately after compaction, a large fraction of the effective window is already committed before much new work begins.

That leaves less room for subsequent observations and decisions before another compaction is required. As the cycle repeats, newly accumulated information has to compete with an increasingly dense retained state, and the next compaction has less freedom to discard material without losing something useful. This does not guarantee quality loss, but it raises the risk of user-visible degradation such as missed constraints, weaker recall of earlier details, repeated work, or less stable reasoning — the kind of behavior that can make a long-running session feel progressively less sharp.

The 65% transition is therefore not based on session age or an arbitrary token count. It marks a point where both signals become meaningful at the same time: the previous compaction has restored **less than about one third of effective-window runway**, while almost two thirds of the usable context is already occupied by retained state. For long-running work, that is a practical boundary between “continue normally” and “start considering a clean session boundary.”

Custom context-window or auto-compaction settings can shift the exact runway, so the colors remain guidance rather than a quality guarantee. **Compaction count and cumulative session tokens are shown separately and do not affect the risk color.**

## Measurement model

The HUD deliberately avoids estimating context from transcript length.

Current Codex exposes thread usage as `last`, `total`, and `modelContextWindow`. Codex itself defines the latest `last.totalTokens` as the active context size and `total.totalTokens` as cumulative session usage. The HUD therefore uses:

```text
Current context  = tokenUsage.last.totalTokens
Session tokens   = tokenUsage.total.totalTokens
Context window   = tokenUsage.modelContextWindow
```

`modelContextWindow` is used exactly as reported by Codex. It already represents the effective model window exposed to the client, so the HUD does **not** apply a second 95% reduction.

### Measuring after compaction

For current Codex versions, the authoritative compaction lifecycle is the `contextCompaction` item. The HUD arms a new measurement only after:

```text
item/completed
└─ item.type == contextCompaction
```

It then waits for a later `thread/tokenUsage/updated` event with a real token breakdown before accepting the new post-compaction snapshot.

This distinction matters. Immediately after compaction, Codex can recompute context locally. A public Codex issue documents how that local estimate can temporarily overwrite measured usage and can be inaccurate for CJK-heavy histories because of byte-based token approximation: [openai/codex#37135](https://github.com/openai/codex/issues/37135).

Codex's local recomputation currently produces an all-zero usage breakdown apart from `totalTokens`. The HUD rejects that shape and waits for measured activity before committing the snapshot. This is especially useful for Korean, Chinese, Japanese, emoji-heavy, or otherwise non-ASCII sessions.

If the latest compaction happened while the HUD was not running, the HUD displays **Not captured** instead of reconstructing a number from private rollout files and presenting an estimate as fact.

## Additional session information

The risk indicator is the main signal, but its hover card also keeps a small set of supporting values available without turning the composer into a monitoring dashboard:

- **Current context** — the latest active context size and effective context window reported by Codex.
- **Compactions** — the reconciled compaction count for the current thread.
- **Session tokens** — cumulative token usage for the thread; informative only and not part of the risk calculation.
- **Usage limits** — account-level 5-hour and weekly quota information reported by Codex.

### Weekly usage bar

The horizontal usage bar is based on **weekly quota remaining** so the always-visible graphic stays stable and easy to read. Hovering it expands the account view to show both quota windows:

```text
Usage limits

5-hour
63% remaining

Weekly
78% remaining
```

The HUD identifies 5-hour and weekly windows from the durations reported by Codex, using the same approximate-window approach used in current Codex code. Rate-limit snapshots are isolated by `limitId`, so unrelated limits such as model-specific reserve windows cannot overwrite the main Codex allowance.

## Lightweight by design

The resident path is intentionally small and event-driven. In normal use the HUD does not:

- scan Codex session JSONL files;
- read `state_5.sqlite`;
- launch a second `codex app-server` process;
- poll token usage on a timer;
- continuously animate the toolbar;
- rebuild the entire HUD on every Codex DOM mutation.

The host spends most of its lifetime waiting on the local DevTools WebSocket. Token, quota, and compaction work runs only when Codex emits a relevant event. DOM observation is limited to keeping the small composer surface attached, and rendering is dirty-field based so unchanged indicators are not rewritten.

The HUD also tracks runtime state by thread ID, so a background Codex task can compact and report its post-compaction usage even while another thread is visible.

### Persistent state

The HUD persists only **one mutable runtime data file**:

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\state.json
```

It stores bounded metadata only: thread IDs, compaction IDs/counts, post-compaction token/window snapshots, and capture status. A typical thread entry is only a few hundred bytes. Even around **1,000 tracked sessions**, the state file should normally remain in the **low hundreds of kilobytes**, not hundreds of megabytes. The implementation also hard-limits the state store to 10,000 thread entries and 4 MiB.

Program binaries, scripts, documentation, and the icon are static install files; `state.json` is the only mutable session-state file maintained by the HUD.

## Installation and everyday use

### Requirements

- Windows 10 or Windows 11 x64
- Microsoft Store Codex Desktop (`OpenAI.Codex` package)
- Windows .NET Framework compiler for source builds; `Build.ps1` uses the framework compiler included with standard Windows installations

### Install from source

Open PowerShell in the repository directory:

```powershell
.\Install.ps1
```

The installer builds and installs the HUD to:

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\
```

and creates a Start menu shortcut named:

```text
Codex with Session Health HUD
```

### Important: launch Codex through the HUD shortcut

For the in-composer HUD to attach, Codex must start with a loopback-only Chromium DevTools port enabled. Therefore, when you want the HUD, launch:

```text
Codex with Session Health HUD
```

—not the native Codex shortcut.

The launcher activates the official Microsoft Store package and passes only:

```text
--remote-debugging-address=127.0.0.1
--remote-debugging-port=9231
```

The HUD then attaches locally after the port is ready. It does **not** patch or replace the Codex installation.

If Codex is already running from its native shortcut without the debug port, save your work, exit Codex, and relaunch it through **Codex with Session Health HUD**. The launcher intentionally does not force-close or restart Codex on your behalf.

To use a different loopback port:

```powershell
.\Install.ps1 -Port 9331
```

### Build only

```powershell
.\Build.ps1
```

The build runs the state-store and renderer regression self-tests before replacing `CodexSessionHealthHUD.exe`.

### Uninstall

Run:

```powershell
& "$env:LOCALAPPDATA\CodexSessionHealthHUD\Uninstall.ps1"
```

The uninstaller verifies the installation marker, removes the HUD shortcuts, and deletes the entire:

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\
```

directory, including `state.json`. Codex conversations, rollout data, settings, and credentials are never modified.

## Compatibility strategy

Codex Desktop can move slightly ahead of or behind the public `openai/codex` repository. The HUD therefore favors **runtime feature detection** over hard-coded Codex version checks.

Current paths are preferred, with narrowly scoped legacy fallbacks where useful:

- `contextCompaction` item lifecycle first; deprecated `thread/compacted` only as compatibility fallback;
- current camelCase token/rate-limit fields with legacy snake_case parsing where required;
- official `thread/items/list` pagination for compaction-history reconciliation when supported;
- native loaded-history fallback for older clients.

The parser is allow-listed and bounded rather than recursively scanning arbitrary Codex payloads.

## Privacy and security

Persistent HUD state contains only bounded operational metadata. The HUD does **not** persist:

- prompt text;
- assistant replies;
- tool output;
- file contents;
- workspace paths;
- credentials or auth tokens;
- account identity.

The HUD makes no external network requests of its own. The DevTools endpoint is explicitly bound to `127.0.0.1`.

## Engineering lineage

This project draws substantial inspiration and implementation ideas from two MIT-licensed Windows projects:

- [`wtf12345789/codex-context-hud`](https://github.com/wtf12345789/codex-context-hud) — packaged-app launching, local DevTools attachment, and the concept of a compact composer-integrated HUD.
- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring ideas and the value of exposing cumulative token/session information.

Codex Session Health HUD is not a mechanical merge of those repositories. During implementation, the relevant assumptions were revalidated against current `openai/codex`: deprecated compaction notifications were moved to fallback status, active-context accounting was aligned with `last.totalTokens`, quota merging was updated for sparse rate-limit notifications, JSONL/SQLite monitoring was removed from the resident path, and the renderer/CDP architecture was narrowed to reduce polling, parsing, and DOM work.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution and license notices.

## Development invariants

A few implementation rules are treated as architectural constraints:

- one CDP WebSocket reader owns all incoming messages;
- renderer-to-host persistence uses a fixed, one-way binding with a small payload limit;
- event parsing is method allow-listed and depth/node bounded;
- thread state is maintained independently from the currently visible thread;
- `state.json` is written atomically under a named mutex;
- Codex session/rollout files remain untouched.

## License

MIT licensed. See [LICENSE](LICENSE).

Codex Session Health HUD is an independent community project and is **not an official OpenAI product**.
