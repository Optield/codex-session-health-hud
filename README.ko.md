# Codex Session Health HUD

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)](#요구-환경)
[![License: MIT](https://img.shields.io/badge/License-MIT-2ea44f.svg)](LICENSE)
[![English README](https://img.shields.io/badge/README-English-4c8bf5)](README.md)

Codex에서 같은 세션을 오래 사용할수록 active context가 누적되고, 반복되는 컴팩션 뒤에도 큰 working set이 남기 시작하면 세션을 계속 유지하는 효율과 안정성이 점차 떨어질 수 있습니다. **Codex Session Health HUD**는 단순히 세션이 얼마나 오래됐는지가 아니라 실제 컨텍스트 상태를 바탕으로, **현재 세션을 계속 사용할지 새 세션으로 넘어갈지를 판단하는 데 도움을 주기 위해** 만들었습니다.

별도 모니터 창을 띄우는 프로그램이 아니라 Codex Desktop 안에 자연스럽게 통합되는 경량 Windows HUD이며, 핵심적으로 다음 질문에 답합니다.

> **이 세션은 아직 계속 사용하기에 건강한가, 아니면 컴팩션 후에도 컨텍스트 압력이 너무 많이 남아 새 세션을 고려할 시점인가?**

HUD는 Codex의 composer toolbar에 삽입되며 **기존 native context ring 바로 왼쪽**에 배치됩니다.

```text
[ 주간 사용량 ] [ Post-compaction 위험도 ] [ Codex native context ring ]
```

Native context ring은 수정하지 않습니다. 대신 Codex가 한 화면에서 제공하지 않는 post-compaction pressure, 컴팩션 횟수, 세션 누적 토큰, 5시간/주간 quota를 작고 정돈된 형태로 추가합니다.

## 표시 정보

### Post-compaction Risk bar

세 개의 세로 bar는 **HUD가 마지막으로 정상 측정한 컴팩션 직후의 잔여 컨텍스트 압력**을 나타냅니다.

| Post-compaction context | 표시 | 안내 문구 |
| --- | --- | --- |
| 컴팩션 없음 | 회색 | `No compaction yet.` |
| 측정 중 | 회색 | `Waiting for measured context usage.` |
| 측정하지 못함 / unavailable | 회색 | 위험도를 추정하지 않음 |
| `<45%` | 초록 | `This session is in good shape.` |
| `45–65%` | 노랑 | `You can keep using this session.` |
| `65–80%` | 빨강 | `Consider starting a new session soon.` |
| `>=80%` | 보라 | `Starting a new session is recommended.` |

Risk bar에 마우스를 올리면 위험도를 해석하는 데 필요한 세션 정보를 함께 확인할 수 있습니다.

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

Risk bar는 **현재 context가 아니라 마지막 post-compaction context**를 기준으로 합니다. 예를 들어 컴팩션 직후 39.9%였고 이후 current context가 85%까지 다시 증가했더라도, 다음 컴팩션이 발생하기 전까지 Risk bar는 39.9% 결과를 유지합니다.

즉 native context ring의 복제품이 아니라, **마지막 컴팩션 이후에도 얼마나 많은 컨텍스트 압력이 남았는지**를 별도로 보여주는 지표입니다.

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

## 왜 65%인가?

65%는 OpenAI가 공식적으로 정한 세션 교체 기준이 아니라, **현재 Codex의 컨텍스트 예산 구조에서 컴팩션 이후 남는 실질적인 작업 여유를 기준으로 정한 운영 임계값**입니다.

현재 기본 Codex 설정에서는 모델의 raw context window 중 약 95%가 실제 client에 노출되는 effective context window로 사용되고, 자동 컴팩션은 raw window의 약 90% 부근에서 시작됩니다. 이를 HUD가 사용하는 effective window 기준으로 환산하면, 다음 기본 컴팩션 영역은 대략 **94.7%** 지점입니다.

따라서 컴팩션 직후의 점유율은 다음 컴팩션까지 남은 실질적인 runway를 직접 보여줍니다.

- **45%**에서는 다음 기본 컴팩션 영역까지 약 **49.7%p**가 남습니다. 사실상 effective window의 절반 가까이를 다시 사용할 수 있는 상태입니다.
- **65%**에서는 남은 runway가 약 **29.7%p**로 줄어듭니다. 컨텍스트를 비우기 위한 컴팩션이 끝났는데도 effective window의 거의 2/3가 이미 차 있다는 뜻이며, 다음 컴팩션 사이클까지의 여유가 눈에 띄게 짧아집니다.
- **80%**에서는 약 **14.7%p**만 남기 때문에 별도의 critical 단계로 구분합니다.

즉 65%는 세션 사용 시간이나 임의의 누적 토큰 수로 정한 숫자가 아닙니다. **컴팩션이 완료된 직후에도 다음 기본 컴팩션 영역까지 effective-window runway를 약 1/3도 회복하지 못한 시점**을 경계로 삼은 것입니다. 장시간 이어지는 작업에서는 이 지점부터 “그대로 계속 사용”보다 “새 세션으로 경계를 정리할지 고려”하는 것이 합리적인 운영 판단이 됩니다.

사용자가 context window나 auto-compaction 설정을 직접 변경하면 정확한 runway는 달라질 수 있으므로 색상은 어디까지나 판단을 돕는 지표입니다. **컴팩션 횟수와 세션 누적 토큰은 별도로 표시되며 Risk bar의 색상 계산에는 관여하지 않습니다.**

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

Uninstaller는 install marker를 검증한 뒤 관련 shortcut을 제거하고:

```text
%LOCALAPPDATA%\CodexSessionHealthHUD\
```

폴더 자체를 재귀적으로 삭제합니다. `state.json`을 포함한 HUD 전용 파일은 모두 제거되며 Codex의 conversation, rollout, 설정, credential에는 손대지 않습니다.

## 최신 Codex와의 호환성

Codex Desktop은 공개 `openai/codex` main보다 약간 앞서거나 뒤질 수 있습니다. 그래서 특정 Codex 버전 번호를 하드코딩하지 않고 **runtime feature detection**을 우선합니다.

현재 경로를 우선 사용하고 필요한 범위에서만 legacy fallback을 둡니다.

- `contextCompaction` item lifecycle 우선, deprecated `thread/compacted`는 구버전 fallback
- 현재 camelCase token/rate-limit field 우선, 필요한 경우 legacy snake_case 파싱
- 지원되는 경우 공식 `thread/items/list` pagination으로 compaction history 동기화
- 오래된 client에서는 native loaded-history fallback

이벤트 parser도 임의의 Codex payload 전체를 재귀 탐색하지 않고 method allow-list와 depth/node limit을 둔 bounded dispatcher로 구성했습니다.

## Privacy / Security

HUD가 영구 저장하는 것은 작은 운영 메타데이터뿐입니다. 다음 데이터는 저장하지 않습니다.

- prompt text
- assistant reply
- tool output
- file content
- workspace path
- credential / auth token
- account identity

HUD 자체가 외부 네트워크 요청을 만들지 않으며 DevTools endpoint는 `127.0.0.1`에만 bind됩니다.

## 기반 프로젝트와 구현 방향

이 프로젝트는 다음 두 MIT 라이선스 Windows 프로젝트의 아이디어와 구현을 상당 부분 참고했습니다.

- [`wtf12345789/codex-context-hud`](https://github.com/wtf12345789/codex-context-hud) — Windows packaged-app launcher, local DevTools attach, Codex composer 내부의 작은 HUD라는 구조
- [`LH-03/codex-monitor-hud`](https://github.com/LH-03/codex-monitor-hud) — context/quota monitoring 아이디어와 cumulative token/session 정보의 활용

다만 두 프로젝트를 그대로 합친 코드는 아닙니다. 구현 과정에서 현재 `openai/codex`를 기준으로 가정을 다시 검증했습니다. Deprecated compaction notification은 fallback으로 내리고, active context accounting은 `last.totalTokens`에 맞추고, sparse rate-limit update에 맞게 quota merge 방식을 바꾸고, resident path에서는 JSONL/SQLite monitoring을 제거했습니다. Renderer와 CDP 구조 역시 polling, object traversal, DOM work를 줄이는 방향으로 다시 구성했습니다.

라이선스 및 attribution은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하십시오.

## 구현 원칙

몇 가지는 단순 구현 세부사항이 아니라 architectural invariant로 두었습니다.

- 모든 incoming CDP message는 하나의 WebSocket reader만 처리
- renderer → host persistence는 payload size가 제한된 고정 one-way binding 사용
- event parser는 method allow-list + depth/node bound 적용
- thread state는 현재 visible thread와 독립적으로 유지
- `state.json`은 named mutex 아래에서 atomic write
- Codex session/rollout 파일은 읽거나 수정하지 않음

## 라이선스

MIT License. [LICENSE](LICENSE)를 참고하십시오.

Codex Session Health HUD는 독립적인 community project이며 **OpenAI 공식 제품이 아닙니다.**
