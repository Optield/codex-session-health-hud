from pathlib import Path
import re


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


renderer = Path("RendererHudScript.js")
text = renderer.read_text(encoding="utf-8")
text = replace_once(text, "      sessionTotalTokens: -1,\n", "", "runtime sessionTotalTokens")
text = replace_once(
    text,
    "    const total = first(usage, ['total', 'totalTokenUsage', 'total_token_usage']);\n",
    "",
    "normalize total object",
)
text = replace_once(
    text,
    "    const sessionTotal = total && typeof total === 'object' ? number(first(total, ['totalTokens', 'total_tokens'])) : null;\n",
    "",
    "normalize session total",
)
text = replace_once(
    text,
    "    return { last, lastTotal, sessionTotal, windowSize, measured: usageBreakdownMeasured(last) };\n",
    "    return { last, lastTotal, windowSize, measured: usageBreakdownMeasured(last) };\n",
    "normalized usage return",
)
session_apply = (
    "    if (parsed.sessionTotal !== null && parsed.sessionTotal >= 0 &&\n"
    "      (!onlyMissing || runtime.sessionTotalTokens < 0)) {\n"
    "      changed = changed || runtime.sessionTotalTokens !== parsed.sessionTotal;\n"
    "      runtime.sessionTotalTokens = parsed.sessionTotal;\n"
    "    }\n"
)
text = replace_once(text, session_apply, "", "session total telemetry application")
needs_block = (
    "    const needsCurrent = runtime.currentContextTokens < 0 || runtime.currentContextWindow <= 0;\n"
    "    const needsSessionTotal = runtime.sessionTotalTokens < 0;\n"
    "    if (!needsCurrent && !needsSessionTotal) return false;\n"
)
text = replace_once(
    text,
    needs_block,
    "    const needsCurrent = runtime.currentContextTokens < 0 || runtime.currentContextWindow <= 0;\n"
    "    if (!needsCurrent) return false;\n",
    "renderer hydration need check",
)
text = replace_once(
    text,
    '          <span style="opacity:.72">Session tokens</span><span data-r-total style="font-variant-numeric:tabular-nums">—</span>\n',
    "",
    "session tokens tooltip row",
)
text = replace_once(
    text,
    "    const total = tooltip.querySelector('[data-r-total]');\n",
    "",
    "session total tooltip ref",
)
text = replace_once(
    text,
    "    total.textContent = runtime && runtime.sessionTotalTokens >= 0 ? formatTokens(runtime.sessionTotalTokens) : '—';\n",
    "",
    "session total tooltip render",
)
renderer.write_text(text, encoding="utf-8")


tests = Path("tests/renderer-logic.test.js")
test = tests.read_text(encoding="utf-8")
fixture_total = "    total: { totalTokens: 12840000 },\n"
if test.count(fixture_total) != 2:
    raise SystemExit(
        f"token usage fixture totals: expected 2 occurrences, found {test.count(fixture_total)}"
    )
test = test.replace(fixture_total, "", 2)
for old, label in [
    (
        "assert.equal(measuredUsage.sessionTotal, 12840000, 'session total uses total.totalTokens');\n",
        "session total assertion",
    ),
    ("  total: { totalTokens: 32145397 },\n", "renderer snapshot total"),
    ("  sessionTotalTokens: -1,\n", "missing live usage total"),
    (
        "assert.equal(missingLiveUsage.sessionTotalTokens, 32145397);\n",
        "hydrated session total assertion",
    ),
    ("  sessionTotalTokens: 33000000\n", "newer live usage total"),
    (
        "assert.equal(newerLiveUsage.sessionTotalTokens, 33000000);\n",
        "preserved session total assertion",
    ),
    ("  total: { totalTokens: 34000000 },\n", "live update total"),
    (
        "assert.equal(partialLiveUsage.sessionTotalTokens, 34000000);\n",
        "live update session total assertion",
    ),
]:
    test = replace_once(test, old, "", label)

partial_pattern = re.compile(
    r"\nconst partialLiveUsage = \{.*?assert\.equal\(partialLiveUsage\.sessionTotalTokens, 32145397\);\n",
    re.S,
)
test, count = partial_pattern.subn("", test, count=1)
if count != 1:
    raise SystemExit(
        f"partial session-total hydration test: expected 1 block, found {count}"
    )
test = replace_once(
    test,
    "assert.equal(t.applyUsageTelemetry(partialLiveUsage, liveUpdate, false), true,\n",
    "assert.equal(t.applyUsageTelemetry(missingLiveUsage, liveUpdate, false), true,\n",
    "live update target",
)
test = replace_once(
    test,
    "assert.equal(partialLiveUsage.currentContextTokens, 160000);\n",
    "assert.equal(missingLiveUsage.currentContextTokens, 160000);\n",
    "live current context assertion",
)
tests.write_text(test, encoding="utf-8")


readme = Path("README.md")
en = readme.read_text(encoding="utf-8")
replacements_en = [
    (
        "The native ring is left untouched. The HUD adds only the information Codex does not currently surface together: post-compaction pressure, compaction count, cumulative session tokens, and both account quota windows.",
        "The native ring is left untouched. The HUD adds only the information Codex does not currently surface together: post-compaction pressure, compaction count, and both account quota windows.",
        "English intro capability list",
    ),
    (
        "\nCompactions\n3\n\nSession tokens\n12.84M\n",
        "\nCompactions\n3\n",
        "English tooltip example",
    ),
    (
        "Custom context-window or auto-compaction settings can shift the exact runway, so the colors remain guidance rather than a quality guarantee. **Compaction count and cumulative session tokens are shown separately and do not affect the risk color.**",
        "Custom context-window or auto-compaction settings can shift the exact runway, so the colors remain guidance rather than a quality guarantee. **Compaction count is shown separately and does not affect the risk color.**",
        "English risk-color note",
    ),
    (
        "Current Codex exposes thread usage as `last`, `total`, and `modelContextWindow`. Codex itself defines the latest `last.totalTokens` as the active context size and `total.totalTokens` as cumulative session usage. The HUD therefore uses:\n\n```text\nCurrent context  = tokenUsage.last.totalTokens\nSession tokens   = tokenUsage.total.totalTokens\nContext window   = tokenUsage.modelContextWindow\n```",
        "Current Codex exposes the active context through `last.totalTokens` together with `modelContextWindow`. The HUD therefore uses:\n\n```text\nCurrent context  = tokenUsage.last.totalTokens\nContext window   = tokenUsage.modelContextWindow\n```",
        "English measurement model",
    ),
    (
        "- **Session tokens** — cumulative token usage for the thread; informative only and not part of the risk calculation.\n",
        "",
        "English supporting-info bullet",
    ),
    (
        "- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring ideas and the value of exposing cumulative token/session information.",
        "- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring ideas and compact status presentation.",
        "English lineage",
    ),
]
for old, new, label in replacements_en:
    en = replace_once(en, old, new, label)
readme.write_text(en, encoding="utf-8")


readme_ko = Path("README.ko.md")
ko = readme_ko.read_text(encoding="utf-8")
replacements_ko = [
    (
        "Native context ring은 수정하지 않습니다. 대신 Codex가 한 화면에서 제공하지 않는 post-compaction pressure, 컴팩션 횟수, 세션 누적 토큰, 5시간/주간 quota를 작고 정돈된 형태로 추가합니다.",
        "Native context ring은 수정하지 않습니다. 대신 Codex가 한 화면에서 제공하지 않는 post-compaction pressure, 컴팩션 횟수, 5시간/주간 quota를 작고 정돈된 형태로 추가합니다.",
        "Korean intro capability list",
    ),
    (
        "\nCompactions\n3\n\nSession tokens\n12.84M\n",
        "\nCompactions\n3\n",
        "Korean tooltip example",
    ),
    (
        "즉 65%는 세션 사용 시간이나 임의의 누적 토큰 수로 정한 숫자가 아닙니다.",
        "즉 65%는 세션 사용 시간 같은 간접 지표로 정한 숫자가 아닙니다.",
        "Korean threshold wording",
    ),
    (
        "사용자가 context window나 auto-compaction 설정을 직접 변경하면 정확한 runway는 달라질 수 있으므로 색상은 어디까지나 판단을 돕는 지표입니다. **컴팩션 횟수와 세션 누적 토큰은 별도로 표시되며 Risk bar의 색상 계산에는 관여하지 않습니다.**",
        "사용자가 context window나 auto-compaction 설정을 직접 변경하면 정확한 runway는 달라질 수 있으므로 색상은 어디까지나 판단을 돕는 지표입니다. **컴팩션 횟수는 별도로 표시되며 Risk bar의 색상 계산에는 관여하지 않습니다.**",
        "Korean risk-color note",
    ),
    (
        "현재 Codex는 thread usage를 `last`, `total`, `modelContextWindow`로 제공합니다. Codex 본체에서 `last.totalTokens`는 최신 active context 크기, `total.totalTokens`는 세션 누적 사용량으로 취급되므로 HUD도 동일한 의미를 사용합니다.\n\n```text\nCurrent context  = tokenUsage.last.totalTokens\nSession tokens   = tokenUsage.total.totalTokens\nContext window   = tokenUsage.modelContextWindow\n```",
        "현재 Codex가 제공하는 `last.totalTokens`와 `modelContextWindow`를 사용해 active context를 표시합니다.\n\n```text\nCurrent context  = tokenUsage.last.totalTokens\nContext window   = tokenUsage.modelContextWindow\n```",
        "Korean measurement model",
    ),
    (
        "- **Session tokens** — 해당 thread의 누적 token 사용량. 참고 정보일 뿐 Risk 계산에는 사용하지 않음\n",
        "",
        "Korean supporting-info bullet",
    ),
    (
        "- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring 아이디어와 cumulative token/session 정보 표시",
        "- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring 아이디어와 compact status 표시",
        "Korean lineage",
    ),
]
for old, new, label in replacements_ko:
    ko = replace_once(ko, old, new, label)
readme_ko.write_text(ko, encoding="utf-8")


changelog = Path("CHANGELOG.md")
change = changelog.read_text(encoding="utf-8")
heading = "# Changelog\n\n"
entry = (
    "# Changelog\n\n## Unreleased\n\n"
    "- Remove the `Session tokens` field and its cumulative-session telemetry path; the Risk tooltip now focuses on post-compaction context, current context, and compaction count.\n"
    "- Keep renderer-state hydration only for missing current-context telemetry.\n\n"
)
if not change.startswith(heading):
    raise SystemExit("unexpected changelog header")
if "## Unreleased" in change:
    raise SystemExit("unexpected pre-existing Unreleased section")
change = entry + change[len(heading):]
changelog.write_text(change, encoding="utf-8")
