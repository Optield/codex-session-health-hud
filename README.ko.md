# Codex Session Health HUD

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)](#요구-환경)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![English README](https://img.shields.io/badge/README-English-4c8bf5)](README.md)

**Codex Session Health HUD**는 장시간 이어지는 Codex Desktop 세션의 상태를 판단하는 데 필요한 핵심 정보를, 별도 모니터 창이 아니라 **Codex 자체 UI 안에 자연스럽게 통합**해 보여주는 경량 Windows HUD입니다.

특히 다음 질문에 답하도록 설계했습니다.

> **마지막 컴팩션 이후 컨텍스트가 실제로 얼마나 남았고, 컴팩션이 세션에 어느 정도의 여유 공간을 되돌려 주었는가?**

HUD는 Codex의 composer toolbar에 삽입되며 **기존 native context ring 바로 왼쪽**에 배치됩니다.

```text
[ 주간 사용량 ] [ Post-compaction 위험도 ] [ Codex native context ring ]
```

Native context ring은 수정하지 않습니다. 대신 Codex가 한 화면에서 제공하지 않는 post-compaction pressure, 컴팩션 횟수, 세션 누적 토큰, 5시간/주간 quota를 작고 정돈된 형태로 추가합니다.

## 표시 정보

### 주간 Usage bar

가로 Usage bar의 그래픽은 **주간 quota 잔여량**을 기준으로 표시됩니다. 마우스를 올리면 Codex가 로컬에서 보고한 두 사용량 window를 함께 보여줍니다.

```text
Usage limits

5-hour
63% remaining

Weekly
78% remaining
```

5시간/주간 window는 Codex가 보고하는 duration을 기반으로 식별하며, 현재 Codex 자체 구현과 같은 approximate-window 방식으로 판별합니다. 또한 `limitId`별로 rate-limit 상태를 분리하므로 model-specific reserve와 같은 다른 limit이 Codex 계정 quota를 덮어쓰지 못합니다.

### Post-compaction Risk bar

세 개의 세로 bar는 **컴팩션 횟수**를 뜻하지 않습니다. HUD가 마지막으로 정상 측정한 컴팩션 직후의 잔여 컨텍스트 압력을 나타냅니다.

| Post-compaction context | 표시 | 안내 문구 |
| --- | --- | --- |
| 컴팩션 없음 | 회색 | `No compaction yet.` |
| 측정 중 | 회색 | `Waiting for measured context usage.` |
| 측정하지 못함 / unavailable | 회색 | 위험도를 추정하지 않음 |
| `<45%` | 초록 | `This session is in good shape.` |
| `45–65%` | 노랑 | `You can keep using this session.` |
| `65–80%` | 빨강 | `Consider starting a new session soon.` |
| `>=80%` | 보라 | `Starting a new session is recommended.` |

Risk bar에 마우스를 올리면 다음처럼 세션 핵심 정보를 함께 확인할 수 있습니다.

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

Risk bar는 **현재 context가 아니라 마지막 post-compaction context**를 기준으로 합니다. 예를 들어 컴팩션 직후 39.9%였고 이후 current context가 85%까지 다시 증가했더라도, 다음 컴팩션이 발생하기 전까지 Risk bar는 39.9% 결과를 나타냅니다.

즉 native context ring의 복제품이 아니라, **“이번 컴팩션이 실제로 얼마나 많은 여유 공간을 회복했는가”**를 별도로 보여주는 지표입니다.

## 왜 65%인가?

65%는 OpenAI가 공식적으로 정한 세션 교체 기준이 아닙니다. 이 HUD에서는 공개된 Codex 자료와 post-compaction headroom 관점이 같은 방향을 가리키는 지점을 바탕으로 **근거 기반의 운영 임계값(evidence-informed operational threshold)**으로 사용합니다.

- 최근 Codex adaptive-context 제안에서는 컴팩션 후 잔여 컨텍스트를 **45% 미만**, **45–65%**, **65% 이상**으로 구분해 context budget 확대 여부를 결정하는 방식을 제안합니다: [openai/codex#41538](https://github.com/openai/codex/issues/41538).
- 별도의 Codex App 버그 리포트에서는 **컴팩션 직후 65%를 초과하는 컨텍스트가 남는 현상**을, 이후 유의미한 작업을 이어갈 여유를 크게 줄이는 문제로 보고하고 있습니다: [openai/codex#40856](https://github.com/openai/codex/issues/40856).
- 실무적인 관점에서도 컴팩션 직후 이미 유효 context window의 약 2/3가 차 있다면, 컴팩션이 되돌려 준 working headroom이 상대적으로 작다는 뜻입니다. 세션을 자동으로 종료할 근거는 아니지만, 시각적 경고 단계를 바꾸기에는 유용한 지점입니다.

따라서 65%부터 빨강으로 전환합니다. `>=80%`의 보라색은 컴팩션 이후에도 매우 많은 컨텍스트가 남은 경우를 구분하기 위해 추가한 local critical tier입니다.

이 위험도는 어디까지나 안내 지표입니다. **컴팩션 횟수와 세션 누적 토큰은 별도로 표시되며 Risk bar의 색상 계산에는 관여하지 않습니다.**

## 컨텍스트를 어떻게 측정하는가

이 HUD는 transcript 길이나 문자 수로 context를 추정하지 않습니다.

현재 Codex는 thread usage를 `last`, `total`, `modelContextWindow`로 제공합니다. Codex 본체에서 `last.totalTokens`는 최신 active context 크기, `total.totalTokens`는 세션 누적 사용량으로 취급되므로 HUD도 동일한 의미를 사용합니다.

```text
Current context  = tokenUsage.last.totalTokens
Session tokens   = tokenUsage.total.totalTokens
Context window   = tokenUsage.modelContextWindow
```

`modelContextWindow`는 Codex가 이미 effective window로 계산해 내려준 값을 그대로 사용합니다. 따라서 HUD가 별도로 95%를 다시 곱하지 않습니다.

### 컴팩션 직후 측정

현재 Codex에서 컴팩션의 정식 lifecycle은 `contextCompaction` item입니다. HUD는 다음 이벤트가 완료된 뒤에만 새 측정을 시작합니다.

```text
item/completed
└─ item.type == contextCompaction
```

그 후 들어오는 `thread/tokenUsage/updated` 중 실제 token breakdown이 확인되는 이벤트를 기다린 뒤 post-compaction snapshot을 확정합니다.

이 구분은 중요합니다. Codex는 컴팩션 직후 컨텍스트 크기를 로컬에서 다시 추정할 수 있는데, 공개 Codex 이슈에서는 이 값이 실제 measured usage를 일시적으로 덮어쓰며 CJK 중심 히스토리에서 byte 기반 근사 때문에 오차가 커질 수 있다는 문제가 설명되어 있습니다: [openai/codex#37135](https://github.com/openai/codex/issues/37135).

현재 로컬 recomputation은 `totalTokens`를 제외한 token breakdown을 0으로 만드는 특성이 있습니다. HUD는 이 형태를 snapshot으로 받아들이지 않고 실제 사용량 activity가 관찰될 때까지 기다립니다. 따라서 한국어·중국어·일본어·이모지 등 비ASCII 비중이 높은 세션에서도 컴팩션 직후의 단순 로컬 근사를 위험도 값으로 확정하는 것을 피합니다.

HUD가 실행되지 않은 상태에서 마지막 컴팩션이 일어났다면 private rollout 파일을 역추적해 그럴듯한 값을 만들어내지 않습니다. 대신 **Not captured**를 표시합니다. 측정하지 못한 값을 추정치로 가장하지 않는 것이 이 HUD의 정확성 원칙입니다.

## 매우 가볍게 설계한 이유

상주 경로는 가능한 한 작고 event-driven으로 구성했습니다. 일반적인 사용 중 HUD는 다음 작업을 하지 않습니다.

- Codex session JSONL 스캔
- `state_5.sqlite` 읽기
- 별도의 `codex app-server` 프로세스 실행
- timer 기반 token polling
- 지속 애니메이션
- Codex DOM이 변할 때마다 전체 HUD/history 재계산

Host 프로세스는 대부분의 시간 동안 로컬 DevTools WebSocket 이벤트를 기다립니다. Token, quota, compaction 관련 처리는 Codex가 해당 이벤트를 보낼 때만 수행됩니다. DOM observer는 composer 안의 작은 HUD가 제 위치에 있는지를 유지하는 역할만 하고, 실제 render도 변경된 필드만 갱신합니다.

또한 runtime state는 현재 화면에 보이는 thread 하나가 아니라 thread ID별로 관리합니다. 따라서 Thread A에서 작업을 돌려 놓고 Thread B를 보고 있는 동안 A에서 컴팩션이 완료되더라도 post-compaction snapshot을 놓치지 않도록 설계했습니다.

### 추가로 생성되는 데이터 파일

HUD가 지속적으로 변경하며 저장하는 runtime 데이터 파일은 **단 하나**입니다.

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\state.json
```

여기에는 thread ID, compaction ID/횟수, post-compaction token/window snapshot, capture 상태처럼 작은 메타데이터만 저장됩니다.

세션 하나의 레코드는 보통 수백 바이트 수준입니다. 따라서 **1,000개 정도의 세션을 추적해도 일반적으로 수백 KB 이하의 작은 파일**에 머무르는 규모입니다. 구현 자체에서도 10,000 thread entry와 4 MiB의 hard limit을 두고 있습니다.

실행 파일, launcher, 문서, 아이콘 등은 설치 시 한 번 배치되는 static 파일이며, 세션 상태 때문에 계속 증가하는 mutable 파일은 `state.json` 하나뿐입니다.

## 추가 세션 정보

Risk hover에는 장시간 Codex 세션을 판단할 때 유용한 정보만 최소한으로 추가했습니다.

- 현재 thread의 정확한 컴팩션 횟수
- 현 세션 누적 토큰 사용량
- 현재 active context / effective context window
- 마지막 post-compaction context snapshot과 비율

Usage bar의 그래픽은 주간 사용량에 집중하지만 hover 시에는 **5시간 quota와 주간 quota를 모두** 확인할 수 있습니다.

## 설치 및 사용 방법

### 요구 환경

- Windows 10 또는 Windows 11 x64
- Microsoft Store 버전 Codex Desktop (`OpenAI.Codex` package)
- 소스 빌드 시 Windows .NET Framework compiler; `Build.ps1`는 일반적인 Windows 설치에 포함된 framework compiler를 사용합니다

### 소스에서 설치

저장소 폴더에서 PowerShell을 열고 실행합니다.

```powershell
.\Install.ps1
```

기본 설치 경로:

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\
```

설치 후 시작 메뉴에 다음 바로가기가 생성됩니다.

```text
Codex with Session Health HUD
```

### 중요: 일반 Codex가 아니라 HUD 바로가기로 실행해야 합니다

Composer 내부에 HUD를 붙이려면 Codex가 시작될 때 loopback-only Chromium DevTools port가 활성화되어 있어야 합니다.

따라서 HUD를 사용할 때는 기본 Codex 바로가기가 아니라:

```text
Codex with Session Health HUD
```

를 실행해야 합니다.

Launcher는 Microsoft Store에 설치된 공식 Codex package를 Windows package activation API로 실행하면서 다음 두 인자만 전달합니다.

```text
--remote-debugging-address=127.0.0.1
--remote-debugging-port=9231
```

포트가 준비되면 HUD가 로컬에서 연결됩니다. Codex 설치 파일을 수정하거나 교체하지 않습니다.

이미 기본 Codex 바로가기로 앱이 실행 중이라면 그 프로세스에는 나중에 debug port를 추가할 수 없습니다. 작업을 저장하고 Codex를 종료한 뒤 **Codex with Session Health HUD**로 다시 실행하면 됩니다. Launcher가 사용자 대신 Codex를 강제로 종료하거나 재시작하지는 않습니다.

다른 로컬 포트를 사용하려면:

```powershell
.\Install.ps1 -Port 9331
```

### 빌드만 수행

```powershell
.\Build.ps1
```

실행 파일을 교체하기 전에 state-store와 renderer regression self-test가 실행됩니다.

### 삭제

```powershell
& "$env:LOCALAPPDATA\CodexSessionHealthHUD\Uninstall.ps1"
```

Uninstaller는 install marker를 검증한 뒤 관련 shortcut을 제거하고 다음 폴더 자체를 삭제합니다.

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\
```

따라서 `state.json`을 포함한 HUD 파일이 모두 제거됩니다. Codex conversation, rollout, 설정, credential에는 손대지 않습니다.

## 최신 Codex와의 호환성

Codex Desktop은 공개 `openai/codex` main보다 약간 앞서거나 뒤질 수 있습니다. 그래서 특정 Codex 버전 번호에 의존하기보다 **runtime feature detection**을 우선합니다.

- 현재 `contextCompaction` item lifecycle을 우선 사용하고 deprecated `thread/compacted`는 호환 fallback으로만 처리
- 최신 camelCase token/rate-limit field를 우선 사용하고 필요한 경우 legacy snake_case 지원
- 지원되는 환경에서는 공식 `thread/items/list` pagination으로 compaction history reconciliation 수행
- 오래된 client에서는 이미 로딩된 native history를 fallback으로 사용

이벤트 parser도 임의의 Codex payload를 재귀적으로 전부 탐색하지 않고, 필요한 method만 allow-list 방식으로 제한적으로 처리합니다.

## Privacy / Security

영구 저장되는 정보는 작은 운영 메타데이터뿐입니다. HUD는 다음 정보를 저장하지 않습니다.

- 사용자 prompt
- assistant 답변
- tool output
- 파일 내용
- workspace 경로
- credential / auth token
- account identity

HUD 자체가 외부 네트워크 요청을 만들지 않으며 DevTools endpoint는 명시적으로 `127.0.0.1`에만 bind합니다.

## 기반 프로젝트와 구현 방향

Codex Session Health HUD는 다음 두 MIT 프로젝트의 아이디어와 구현에서 많은 도움을 받았습니다.

- [`wtf12345789/codex-context-hud`](https://github.com/wtf12345789/codex-context-hud) — Windows packaged-app launcher, local DevTools attach, composer-integrated HUD 구조
- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring 아이디어, session 누적 token과 운영 정보를 노출하는 방식

다만 두 프로젝트의 코드를 단순히 합친 것은 아닙니다. 구현 과정에서 최신 `openai/codex`를 다시 기준으로 삼아 여러 가정을 교정했습니다. Deprecated compaction notification은 fallback으로 내렸고, active context 계산은 `last.totalTokens` 기준으로 정렬했으며, sparse rate-limit update를 올바르게 merge하도록 변경했습니다. 또한 상시 JSONL/SQLite monitoring을 제거하고 event parser, DOM observer, renderer, CDP receive path를 더 좁게 만들어 resident resource cost와 유지보수 표면을 줄였습니다.

자세한 attribution과 license notice는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하세요.

## 구현 원칙

이 프로젝트는 몇 가지 규칙을 architecture invariant로 유지합니다.

- CDP WebSocket의 incoming message reader는 하나만 유지
- Renderer → Host persistence는 작은 payload만 허용하는 고정 one-way binding 사용
- 이벤트 parser는 method allow-list와 depth/node bound 적용
- 현재 보이는 thread와 무관하게 thread별 runtime state 유지
- `state.json`은 named mutex 아래에서 atomic write
- Codex session/rollout 원본 파일은 읽거나 수정하지 않음

## 라이선스

MIT License. [LICENSE](LICENSE)를 참고하세요.

Codex Session Health HUD는 독립적인 community project이며 **OpenAI의 공식 제품이 아닙니다.**
