아래는 확장판입니다. 핵심은 **브라운필드 프로젝트에서 요구사항 분석은 “무엇을 새로 만들 것인가”가 아니라 “기존 시스템의 어떤 실제 동작을 바꾸고, 무엇은 그대로 보존해야 하는가”를 밝히는 활동**이라는 점입니다. unknown unknowns는 대개 “아무도 상상할 수 없는 미지의 것”이라기보다, **문서·코드·데이터·운영 절차·사용자 습관 사이의 불일치에 숨어 있는 암묵지**입니다.

요구사항 공학 연구에서도 unknown unknown 요구사항을 다루기 위해 tacit knowledge, ambiguity, stakeholder 간 common ground 문제를 중요하게 봅니다. 즉, 요구사항이 빠지는 이유는 단순히 질문을 덜 해서가 아니라, 말하는 사람과 듣는 사람이 서로 “당연하다”고 가정하는 배경지식이 다르기 때문입니다.  PMI의 unknown unknowns 연구도 많은 unknown unknowns가 완전히 식별 불가능한 것이 아니라, 적절한 탐색을 통해 **known unknowns**, 즉 “아직 모르지만 추적 가능한 리스크”로 전환될 수 있다고 설명합니다. 

---

# 1. 먼저 사고방식을 바꾼다: 요구사항이 아니라 “변경 가설”로 본다

브라운필드에서 요구사항을 받았을 때 가장 위험한 출발점은 다음과 같습니다.

> “새 기능은 A입니다. 그러니 A를 구현하면 됩니다.”

이 방식은 그린필드에서는 어느 정도 통하지만, 브라운필드에서는 위험합니다. 이미 시스템에는 기존 사용자, 배치, 데이터, 리포트, 외부 연동, 운영 절차, 과거 장애 대응 코드가 있습니다. 그래서 요구사항은 항상 다음처럼 바꿔 읽어야 합니다.

> “현재 시스템은 특정 조건에서 이렇게 동작한다. 이번 요구사항은 그 동작 중 일부를 이렇게 바꾸려는 것이다. 단, 기존에 의존되고 있는 동작 중 무엇은 유지되어야 한다.”

ISO/IEC/IEEE 29148은 요구사항 공학을 단순 문서 작성이 아니라 시스템·소프트웨어 생명주기 전반의 요구사항 관련 프로세스와 산출물로 다룹니다. 브라운필드에서는 이 관점이 특히 중요합니다. 요구사항 하나가 코드, 테스트, 운영, 데이터, 사용자 매뉴얼, 외부 계약과 연결되어 있기 때문입니다. 

## 왜 이렇게 해야 하는가

브라운필드의 unknown unknowns는 보통 “요구사항 자체” 안에 있지 않습니다. 요구사항과 기존 시스템 사이의 **delta**, 즉 차이에서 나옵니다.

예를 들어 요구사항이 “주문 취소 정책을 변경한다”라면 표면적으로는 간단해 보입니다. 하지만 실제 위험은 이런 곳에 있습니다.

| 숨은 질문 | 놓치면 생기는 문제 |
|---|---|
| 기존 주문 상태값은 어떤 의미로 쓰이고 있는가? | 상태값 하나 바꿨는데 정산/배송/CS 리포트가 깨짐 |
| 취소 가능 여부를 누가 판단하는가? | UI, API, 배치, 운영자 화면의 판단 기준이 서로 달라짐 |
| 이미 취소된 주문을 다시 취소 요청하면? | 멱등성 문제, 중복 환불 |
| 야간 정산 배치와 충돌하지 않는가? | 장부 불일치 |
| 특정 고객사만 쓰는 예외 정책이 있는가? | VIP/파트너 고객 장애 |
| 과거 버그를 우회하기 위한 코드가 있는가? | “이상한 코드” 제거 후 장애 발생 |

따라서 1단계 산출물은 user story가 아니라 **변경 가설서**가 되어야 합니다.

```text
Change hypothesis

1. 현재 동작:
2. 바꿀 동작:
3. 절대 유지해야 하는 기존 동작:
4. 영향을 받을 actor:
5. 영향을 받을 데이터:
6. 영향을 받을 API / batch / report / UI:
7. 외부 시스템 연동:
8. 성능 / 보안 / 감사 / 운영 영향:
9. rollback 가능성:
10. 현재 모르는 것:
```

여기서 중요한 칸은 `현재 모르는 것`입니다. 이것을 부끄러워하지 말고 명시적으로 드러내야 합니다. unknown unknowns 발견의 첫 단계는 “우리가 무엇을 모르는지 모른다”를 “이 부분은 확인이 필요하다”로 바꾸는 것입니다.

---

# 2. Interaction perimeter를 먼저 잡는다

다음으로 해야 할 일은 “이 요구사항이 어떤 시스템 경계에 닿는가?”를 찾는 것입니다. 브라운필드에서 큰 사고는 보통 내부 코드보다 **외부 연동과 숨은 소비자**에서 납니다.

Agile Modeling의 legacy system analysis 자료는 대부분의 개발이 완전한 그린필드가 아니라 기존 시스템을 개선하는 브라운필드 성격이며, 시스템은 다른 시스템과 상호작용한다고 설명합니다. 그래서 legacy 분석에서는 외부 데이터 소스, 외부 인터페이스, 우리 시스템을 호출하거나 우리 데이터를 읽는 외부 시스템을 파악해야 합니다. 

## 왜 이 단계가 코드 분석보다 먼저인가

많은 팀이 요구사항을 받으면 바로 관련 코드부터 찾습니다. 하지만 브라운필드에서는 “우리 코드에서만 쓰이는 줄 알았던 것”이 실제로는 외부 시스템, 엑셀 다운로드, BI 리포트, 운영자 SQL, 파트너 API에서 쓰이고 있을 수 있습니다.

코드 내부만 보면 다음을 놓칩니다.

| 외부 접점 | 숨어 있을 수 있는 unknown unknown |
|---|---|
| 외부 API consumer | API 응답 필드 하나를 제거했는데 파트너 앱 장애 |
| 메시지 큐 consumer | 이벤트 payload 변경 후 비동기 소비자 장애 |
| DB 직접 조회 | API는 안정적이지만 DB 컬럼 변경으로 리포트 장애 |
| 파일 export/import | CSV 컬럼 순서 변경으로 정산 실패 |
| 배치/cron | 실시간 정책 변경이 야간 배치 로직과 충돌 |
| 운영자 수동 작업 | 화면은 바뀌었지만 운영 runbook은 예전 기준 유지 |
| 고객별 특례 | 특정 tenant만 쓰는 예외 정책 누락 |

즉, interaction perimeter는 “어디를 봐야 하는가”를 정하는 지도입니다. 이 지도가 없으면 코드 분석이 깊어져도 엉뚱한 곳만 볼 수 있습니다.

## 어떻게 실행하는가

요구사항이 건드리는 핵심 entity를 하나 고릅니다. 예를 들어 `Order`, `Payment`, `User`, `Subscription`, `Inventory` 같은 것입니다. 그다음 아래 질문을 던집니다.

```text
이 entity를 생성하는 시스템은 무엇인가?
수정하는 시스템은 무엇인가?
조회하는 시스템은 무엇인가?
이벤트로 발행하는가?
파일로 내보내는가?
리포트나 BI에서 쓰는가?
운영자가 직접 DB나 admin 화면으로 바꾸는가?
외부 고객/파트너가 의존하는 API가 있는가?
```

산출물은 복잡한 아키텍처 다이어그램일 필요 없습니다. 처음에는 이런 표면 충분합니다.

| 접점 | 방향 | 대상 | 근거 | 신뢰도 | 확인 액션 |
|---|---|---|---|---:|---|
| 주문 API | inbound | 모바일 앱 | API gateway 로그 | 높음 | contract 확인 |
| 주문 이벤트 | outbound | 배송 시스템 | Kafka topic | 중간 | consumer 목록 확인 |
| `orders` table | read | BI 리포트 | DB query log | 낮음 | 리포트 owner 확인 |
| 취소 배치 | internal | 정산 job | scheduler 설정 | 중간 | batch code 확인 |
| 운영자 SQL | manual | CS팀 | 구두 증언 | 낮음 | runbook/실제 작업 확인 |

이 표에서 신뢰도가 낮은 항목들이 바로 unknown unknowns의 입구입니다.

---

# 3. As-built architecture를 복원한다

interaction perimeter가 “경계”를 잡는 단계라면, as-built architecture reconstruction은 “실제 내부 구조”를 복원하는 단계입니다.

CMU SEI는 architecture reconstruction을 기존 legacy system에서 구현된 실제 구조, 즉 **as-built architecture**를 얻는 과정으로 설명합니다. 도구를 사용해 시스템 정보를 추출하고, 점진적으로 추상화 수준을 높여 아키텍처 표현을 만든다는 점이 핵심입니다. 

## 왜 문서가 아니라 as-built인가

브라운필드 시스템의 문서는 자주 낡아 있습니다. 더 위험한 것은 문서가 완전히 없을 때가 아니라, **그럴듯하지만 틀린 문서가 있을 때**입니다.

예를 들어 문서에는 “결제 취소는 PaymentService에서만 처리한다”고 되어 있지만, 실제로는 다음이 있을 수 있습니다.

```text
PaymentService.cancel()
AdminController.forceCancel()
NightlySettlementJob.reversePayment()
LegacyRefundBatch.process()
PartnerCallbackHandler.handleCancel()
```

이 상황에서 PaymentService만 수정하면 일부 경로는 새 정책을 따르고, 일부 경로는 옛 정책을 따르게 됩니다. 이것이 브라운필드 장애의 전형적인 패턴입니다.

## 어떻게 실행하는가

요구사항과 관련된 핵심 기능을 기준으로 2-hop 정도만 복원합니다. 처음부터 전체 시스템을 완벽히 그리려 하면 실패합니다.

분석 대상은 다음입니다.

| 분석 대상 | 확인할 것 |
|---|---|
| package/module dependency | 변경 대상 모듈이 누구를 호출하고 누구에게 호출되는가 |
| API endpoint | 같은 업무 규칙이 여러 endpoint에 중복되어 있는가 |
| service method/call graph | 실제 정책 판단 로직이 어디에 있는가 |
| DB table/column usage | 같은 컬럼을 어디서 읽고 쓰는가 |
| message topic/queue | 이벤트 발행/소비자가 누구인가 |
| scheduler/batch | 시간차 처리 로직이 있는가 |
| config/feature flag | 고객별, 환경별 분기가 있는가 |
| deployment topology | 실제 장애 전파 범위가 어디까지인가 |

산출물은 다음 수준이면 됩니다.

```text
Requirement: 주문 취소 정책 변경

관련 entrypoint:
- POST /orders/{id}/cancel
- POST /admin/orders/{id}/force-cancel
- Kafka: order.cancel.requested
- Batch: nightly-refund-reconciliation

핵심 domain logic 후보:
- OrderCancellationPolicy
- PaymentRefundService
- SettlementAdjustmentService

주요 데이터:
- orders.status
- orders.cancel_reason
- payments.refund_status
- settlement.adjustment_type

불명:
- LegacyRefundBatch가 현재도 실행되는지
- PartnerCallbackHandler가 취소 상태를 직접 바꾸는지
- BI 리포트가 orders.status를 어떤 의미로 해석하는지
```

## 이 단계에서 찾는 unknown unknowns

이 단계에서 특히 많이 나오는 것은 다음입니다.

| 발견 패턴 | 의미 |
|---|---|
| 같은 업무 규칙이 여러 곳에 중복 | 한 곳만 고치면 정책 불일치 |
| 문서에 없는 batch/job 존재 | 시간차 장애 가능성 |
| 오래된 fallback 코드 존재 | 과거 장애 대응 로직일 수 있음 |
| DB trigger/stored procedure 존재 | 애플리케이션 코드만 봐서는 동작 설명 불가 |
| feature flag/customer-specific branch | 특정 고객만 다른 흐름 |
| circular dependency | 작은 변경이 넓게 전파될 가능성 |
| dead code처럼 보이는 코드 | 실제로는 rare path일 수 있음 |

---

# 4. 데이터와 상태 전이를 별도로 분석한다

많은 팀이 기능 흐름은 분석하지만 데이터 의미는 가볍게 봅니다. 브라운필드에서는 이것이 매우 위험합니다. 오래된 시스템일수록 데이터는 “정규화된 진실”이 아니라 **역사적 타협의 누적물**인 경우가 많습니다.

특히 다음은 반드시 별도로 분석해야 합니다.

| 대상 | 질문 |
|---|---|
| 상태값 | 상태 전이가 명시적인가, 아니면 코드 곳곳에서 암묵적으로 바꾸는가 |
| nullable column | null이 “없음”, “미처리”, “레거시 데이터”, “오류” 중 무엇인가 |
| enum/code value | 코드값이 화면/정산/외부 시스템에서 같은 의미인가 |
| 날짜/시간 | timezone, 영업일, 정산일, 생성일/승인일/처리일 의미가 구분되는가 |
| soft delete | 삭제된 데이터가 리포트나 배치에서 제외되는가 |
| historical data | 과거 데이터가 현재 validation rule을 만족하는가 |
| migration | 새 정책 적용 시 기존 데이터 변환이 필요한가 |

## 왜 데이터 분석이 별도 단계여야 하는가

기능 요구사항은 보통 현재와 미래만 말합니다. 하지만 데이터는 과거를 포함합니다.

예를 들어 “앞으로 사용자는 구독 플랜을 하나만 가질 수 있다”는 요구사항이 있다고 합시다. 신규 생성 로직만 바꾸면 되는 것처럼 보이지만, 이미 과거 데이터에는 한 사용자가 여러 플랜을 가진 경우가 있을 수 있습니다. 그러면 다음 문제가 생깁니다.

```text
기존 데이터는 migration할 것인가?
migration하지 않는다면 화면은 어떻게 보여줄 것인가?
API는 배열을 계속 반환할 것인가, 단일 객체로 바꿀 것인가?
정산 배치는 과거 다중 플랜을 어떻게 처리할 것인가?
고객센터는 과거 계약을 어떻게 조회할 것인가?
```

이런 질문들은 요구사항 인터뷰만으로는 잘 나오지 않습니다. 실제 데이터 profiling을 해야 나옵니다.

## 실무 액션

가능하면 production snapshot 또는 anonymized dataset으로 다음을 확인합니다.

```sql
-- 상태값 분포
select status, count(*)
from orders
group by status;

-- 문서에 없는 상태값
select distinct status
from orders
where status not in ('CREATED', 'PAID', 'CANCELLED', 'SHIPPED');

-- 불가능해 보이는 조합
select count(*)
from orders
where status = 'CANCELLED'
  and shipped_at is not null;

-- 오래된 데이터와 신규 validation 충돌
select count(*)
from subscriptions
where plan_id is null
   or user_id in (
      select user_id
      from subscriptions
      group by user_id
      having count(*) > 1
   );
```

여기서 발견되는 “이상한 데이터”를 바로 정리 대상으로 보면 안 됩니다. 먼저 물어야 합니다.

> “이 데이터는 버그인가, 과거 정책의 흔적인가, 특정 고객이 의존하는 정상 데이터인가?”

unknown unknowns는 이 질문에서 많이 드러납니다.

---

# 5. 런타임 증거를 본다: 로그, 트레이스, 메트릭, 실제 사용 흐름

코드는 “가능한 경로”를 보여주지만, 로그와 트레이스는 “실제로 일어난 경로”를 보여줍니다. 브라운필드에서는 이 둘이 다를 때가 많습니다.

Google SRE는 black-box monitoring을 사용자 관점의 외부 동작 확인, white-box monitoring을 로그나 내부 endpoint 등 시스템 내부 정보를 기반으로 한 모니터링으로 구분합니다. 특히 white-box monitoring은 retry로 가려진 실패나 임박한 문제를 포착하는 데 유리합니다.  OpenTelemetry는 traces, metrics, logs 같은 telemetry 데이터를 생성·수집·내보내는 vendor-neutral observability framework로, 분산 시스템에서 실제 호출 경로를 보는 데 유용합니다. 

## 왜 런타임 증거가 필요한가

요구사항 회의에서 사람들은 보통 “정상 흐름”을 설명합니다. 하지만 장애는 다음에서 납니다.

```text
가끔만 쓰는 고객별 흐름
운영자만 쓰는 admin 흐름
retry가 여러 번 발생하는 흐름
외부 시스템 timeout 후 보상 처리 흐름
오래된 앱 버전에서 호출하는 API
batch window에만 실행되는 흐름
데이터가 많은 특정 tenant의 흐름
```

이 흐름들은 문서나 일반 인터뷰에 잘 안 나옵니다. 그러나 로그, trace, metrics에는 흔적이 남습니다.

## 어떻게 실행하는가

요구사항과 관련된 transaction을 정하고, 다음을 봅니다.

| 관찰 대상 | 확인할 질문 |
|---|---|
| API access log | 누가 호출하는가, 오래된 client version이 있는가 |
| trace | 실제로 어떤 service/db/external API를 타는가 |
| error log | 이미 실패하고 있지만 retry로 가려진 경로가 있는가 |
| metrics | peak traffic, latency, saturation은 어느 정도인가 |
| audit log | 운영자가 어떤 수동 변경을 하는가 |
| support ticket | 사용자가 반복적으로 겪는 예외 상황은 무엇인가 |
| incident report | 과거 장애에서 어떤 우회 코드/운영 절차가 생겼는가 |
| batch log | 야간/월말/정산일에만 실행되는 경로가 있는가 |

예를 들어 주문 취소 정책 변경이라면 다음을 확인합니다.

```text
최근 90일간 취소 요청 빈도
취소 요청 중 실패율
취소 후 환불까지 걸리는 시간
취소 요청이 가장 많은 client/app version
취소 관련 admin action 비율
취소 후 정산 보정이 발생한 건수
취소 API timeout/retry 발생 횟수
```

## process mining을 적용할 수 있는 경우

업무 흐름이 복잡하고 event log가 충분하다면 process mining도 유용합니다. Process mining은 event log를 기반으로 process discovery, conformance checking, performance analysis를 수행하는 접근입니다.  legacy system은 process mining에 적합한 event log가 없을 수 있는데, 관련 연구는 source code와 database operation 정보를 결합해 legacy system에서 process mining용 event log를 도출하는 방법을 제안합니다. 

간단히 말하면, process mining은 다음 질문에 답하는 데 좋습니다.

```text
사람들이 말한 프로세스와 실제 프로세스가 같은가?
예외 흐름은 얼마나 자주 발생하는가?
어떤 단계에서 병목이 생기는가?
특정 고객/지역/상품군만 다른 흐름을 타는가?
정책상 금지된 순서가 실제로 발생하는가?
```

---

# 6. 도메인 워크숍으로 암묵지를 끌어낸다

브라운필드에서는 코드와 로그만 봐도 부족합니다. 어떤 동작은 “왜 그렇게 되어 있는지”를 코드만으로 알 수 없습니다. 그 이유는 운영자, CS, 정산 담당자, DBA, 보안 담당자, 특정 현업 사용자가 알고 있을 수 있습니다.

EventStorming은 복잡한 비즈니스 도메인을 협업적으로 탐색하는 워크숍 포맷이며, 기존 business line의 건강 상태를 평가하고 개선 영역을 찾는 데도 쓰일 수 있습니다.  Domain Storytelling은 도메인 전문가와 개발팀이 함께 사람, 활동, 작업 산출물을 시각화하여 비즈니스 프로세스와 도메인 지식을 tangible하게 만드는 방법입니다. 

## 왜 워크숍이 필요한가

일반 인터뷰는 이런 식으로 흐르기 쉽습니다.

> 분석가: “주문 취소는 어떻게 하나요?”  
> 현업: “사용자가 취소 버튼을 누르면 취소됩니다.”

이 답변은 틀린 것은 아니지만, unknown unknowns를 찾기에는 부족합니다. 우리가 알고 싶은 것은 정상 흐름보다 예외 흐름입니다.

더 좋은 질문은 다음과 같습니다.

```text
취소 버튼이 안 보이는 경우는 언제인가요?
사용자가 취소했는데 환불이 안 되는 경우는 있나요?
운영자가 대신 취소하는 경우는 언제인가요?
이미 배송 시작된 주문을 취소하려면 어떻게 하나요?
정산 후 취소는 어떻게 처리하나요?
고객사별로 다른 규칙이 있나요?
장애가 나면 수동으로 어떤 작업을 하나요?
이상하지만 절대 건드리면 안 되는 규칙이 있나요?
```

## EventStorming 방식

EventStorming에서는 먼저 도메인 이벤트를 시간순으로 나열합니다.

```text
주문 생성됨
결제 승인됨
재고 할당됨
배송 준비 시작됨
사용자가 취소 요청함
취소 가능 여부 판단됨
환불 요청됨
정산 보정 생성됨
고객에게 알림 발송됨
```

그다음 각 이벤트 옆에 command, actor, policy, external system, read model, hotspot을 붙입니다.

| 요소 | 예시 |
|---|---|
| Command | 주문 취소 요청 |
| Actor | 고객, CS 상담원, 파트너 시스템 |
| Policy | 배송 시작 전까지만 취소 가능 |
| External system | 결제사, 배송사, 정산 시스템 |
| Read model | 주문 상세 화면, CS admin 화면 |
| Hotspot | “배송 시작”의 기준이 시스템마다 다름 |

여기서 `hotspot`이 중요합니다. 사람들 사이에 의견이 갈리는 지점, “그건 상황마다 달라요”라고 말하는 지점, “운영팀이 알아요”라고 넘어가는 지점이 unknown unknowns 후보입니다.

## Domain Storytelling 방식

Domain Storytelling은 사람과 작업 산출물 중심으로 흐름을 그리기 때문에, 수동 업무나 운영 절차를 드러내는 데 특히 좋습니다.

예를 들어 다음 같은 이야기를 시각화합니다.

```text
고객이 CS에 취소 요청을 한다.
CS 상담원이 주문 상태를 확인한다.
배송이 이미 시작되었으면 물류팀에 중단 가능 여부를 묻는다.
물류팀이 중단 가능 여부를 회신한다.
CS 상담원이 admin에서 강제 취소한다.
정산 담당자가 다음날 보정 내역을 확인한다.
```

이 흐름은 코드에는 `forceCancel()` 한 줄로 보일 수 있지만, 실제로는 여러 부서와 수동 판단이 얽혀 있습니다. 이런 수동 절차가 빠지면 기능은 구현됐는데 운영이 실패합니다.

---

# 7. Change Impact Analysis로 흩어진 단서를 합친다

이제 요구사항, 외부 접점, as-built architecture, 데이터, 로그, 도메인 워크숍에서 나온 정보를 하나로 모아야 합니다. 이 단계가 Change Impact Analysis입니다.

Change Impact Analysis는 변경이 시스템의 다른 부분에 미칠 잠정적 효과를 탐색하는 활동이며, 유지보수 비용과 소프트웨어 개발 실패 위험을 줄이는 데 실무적 이점이 있다고 연구에서 정리합니다. 

## 왜 이 단계가 필요한가

각 분석은 서로 다른 종류의 사실을 줍니다.

| 분석 | 알려주는 것 | 한계 |
|---|---|---|
| 요구사항 분석 | 의도 | 실제 시스템과 다를 수 있음 |
| 코드 분석 | 가능한 경로 | 실제 사용 빈도는 모름 |
| 로그 분석 | 실제 사용 | 왜 그런지는 모름 |
| 도메인 워크숍 | 업무 이유 | 기술 의존성은 모를 수 있음 |
| 데이터 분석 | 과거와 예외 | 정책 의도는 모를 수 있음 |
| 테스트 분석 | 보호되는 동작 | 테스트 없는 영역은 안 보임 |

따라서 unknown unknowns는 한 분석 안에서보다 **분석 결과를 서로 대조할 때** 더 잘 나옵니다.

예를 들어 다음은 강한 위험 신호입니다.

```text
현업은 “취소는 배송 전까지만 가능”하다고 말한다.
하지만 로그에는 배송 시작 후 admin 강제 취소가 있다.
코드에는 forceCancel 경로가 별도 정책을 탄다.
정산 배치는 forceCancel을 다른 취소 유형으로 처리한다.
테스트에는 forceCancel 케이스가 없다.
```

이런 경우 요구사항 자체는 단순해 보여도 실제로는 정책, 운영, 정산, 테스트 리스크가 큽니다.

## Impact matrix 예시

| 영역 | 영향 여부 | 근거 | 신뢰도 | unknown | 다음 액션 |
|---|---|---|---:|---|---|
| UI | 있음 | 취소 버튼 노출 조건 변경 | 중간 | 모바일 구버전 처리 | app version 로그 확인 |
| API | 있음 | 취소 가능 여부 응답 변경 | 높음 | 외부 partner consumer | API gateway key별 호출 확인 |
| Domain logic | 있음 | 취소 정책 변경 | 높음 | 강제 취소와 일반 취소 정책 차이 | 코드/현업 확인 |
| DB | 있음 | `cancel_reason`, `status` 사용 | 중간 | status 의미를 BI가 어떻게 쓰는지 | BI query 확인 |
| Batch | 불명 | 정산 보정 job 존재 | 낮음 | 취소 후 정산 보정 기준 | batch owner 인터뷰 |
| Event | 있음 | `OrderCancelled` 발행 | 중간 | consumer 전체 목록 불명 | broker consumer group 확인 |
| Monitoring | 있음 | 취소 실패율 알림 없음 | 낮음 | 장애 감지 가능 여부 | metric 추가 |
| Security/Audit | 불명 | admin 강제 취소 | 낮음 | 감사 로그 충분성 | audit log 샘플 확인 |
| Test | 있음 | 관련 회귀 테스트 부족 | 낮음 | 현재 동작 보호 안 됨 | characterization test 작성 |

이 표에서 `불명`, `낮음`, `근거 없음`, `owner 불명`이 unknown unknowns를 known unknowns로 바꾸는 지점입니다.

---

# 8. Characterization test로 현재 동작을 고정한다

브라운필드에서 테스트는 “정답을 검증하는 도구”이기 전에 “현재 시스템이 실제로 어떻게 동작하는지 기록하는 도구”가 되어야 합니다.

Michael Feathers는 characterization testing의 목적이 우리가 원하는 동작을 검증하는 것이 아니라, 시스템의 **actual behavior**를 문서화하는 것이라고 설명합니다. 특히 사용자가 기존 버그처럼 보이는 동작에 의존하고 있을 수 있다는 점을 강조합니다. 

## 왜 이 단계가 필요한가

브라운필드에서 자주 나오는 사고는 다음입니다.

```text
개발자가 이상한 로직을 발견한다.
“이건 버그겠지”라고 생각하고 정리한다.
배포 후 고객이 항의한다.
알고 보니 그 동작은 특정 업무에서 의존하던 기능이었다.
```

이 문제를 피하려면 변경 전 현재 동작을 고정해야 합니다. 그 동작이 좋은지 나쁜지는 나중 문제입니다. 먼저 “무엇을 바꾸는지”를 알아야 합니다.

## 어떤 테스트를 작성하는가

| 상황 | 추천 테스트 |
|---|---|
| 복잡한 계산 로직 | golden master / snapshot test |
| legacy service method | characterization unit/integration test |
| API 변경 | contract test |
| 외부 시스템 연동 | consumer-driven contract test |
| DB migration | before/after data comparison |
| batch 로직 | representative dataset 기반 회귀 테스트 |
| UI 리포트 | snapshot / approval test |
| 상태 전이 | state transition test |

Pact 문서는 contract test를 애플리케이션 간 메시지가 공유된 계약에 부합하는지 검증하는 테스트로 설명하며, contract testing이 없으면 애플리케이션 간 동작 보장을 위해 비싸고 취약한 통합 테스트에 의존하게 된다고 설명합니다. 

## 좋은 characterization test 예시

```text
Given: 이미 결제 승인되고 배송 준비 전인 주문
When: 사용자가 취소 요청
Then: 주문 상태는 CANCELLED
And: 환불 요청이 생성됨
And: OrderCancelled 이벤트가 발행됨
And: 정산 보정 대상이 됨
```

하지만 더 중요한 것은 예외 케이스입니다.

```text
Given: 배송 시작 후 주문
When: 일반 사용자가 취소 요청
Then: 취소 실패

Given: 배송 시작 후 주문
When: CS 상담원이 force cancel
Then: 취소 성공
And: cancel_reason = ADMIN_FORCE
And: audit log 기록
And: 정산 보정 생성
```

여기서 테스트 결과가 예상과 다르면 둘 중 하나입니다.

```text
1. 시스템이 잘못되어 있다.
2. 우리가 업무 규칙을 잘못 이해했다.
```

둘 다 중요한 발견입니다.

---

# 9. 품질속성 리스크를 따로 본다: ATAM-lite

기능 요구사항만 보면 “정상적으로 동작하는가”에는 답할 수 있지만, 다음 질문은 놓치기 쉽습니다.

```text
트래픽이 10배면 버티는가?
외부 시스템이 장애면 어떻게 되는가?
개인정보 노출 가능성이 생기는가?
운영자가 장애를 감지할 수 있는가?
감사 로그가 충분한가?
이 변경이 다음 변경을 더 어렵게 만드는가?
```

CMU SEI의 ATAM은 소프트웨어 아키텍처를 quality attribute goal 기준으로 평가하고, architecture risk와 quality attribute 간 tradeoff를 드러내는 방법입니다. ATAM은 성능, 보안, 가용성, 변경 용이성 같은 품질속성이 서로 영향을 주고받는다는 점을 다룹니다. 

## 왜 기능 분석과 분리해야 하는가

기능 요구사항 회의에서는 보통 다음처럼 말합니다.

> “사용자가 취소 요청을 하면 취소 처리한다.”

하지만 품질속성 관점에서는 질문이 달라집니다.

| 품질속성 | 질문 |
|---|---|
| 성능 | 월말 정산일에 취소 요청이 몰리면 latency가 어떻게 되는가 |
| 가용성 | 결제사가 장애면 취소 요청을 실패시킬 것인가, pending 처리할 것인가 |
| 보안 | 누가 강제 취소할 수 있는가 |
| 감사 | 강제 취소 사유와 수행자를 추적할 수 있는가 |
| 운영성 | 취소 실패율이 증가하면 알림이 오는가 |
| 변경 용이성 | 취소 정책이 여러 코드 경로에 중복되어 있지 않은가 |
| 데이터 정합성 | 주문 취소와 환불, 정산이 eventually consistent해도 되는가 |
| 복구성 | 배포 후 정책 오류가 발견되면 데이터까지 rollback 가능한가 |

이 질문들은 기능 명세서에 자연스럽게 나오지 않습니다. 그래서 별도 세션으로 다뤄야 합니다.

## ATAM-lite 실행 방식

정식 ATAM은 며칠이 걸릴 수 있지만, 브라운필드 요구사항 분석에서는 60~120분짜리 ATAM-lite로 충분한 효과를 볼 수 있습니다.

```text
1. 변경 요구사항 설명
2. 현재 아키텍처/흐름 간단히 설명
3. 중요한 품질속성 3~5개 선정
4. 각 품질속성별 시나리오 작성
5. 시나리오별 현재 구조의 약점 식별
6. risk / non-risk / sensitivity point / tradeoff 정리
7. 구현 전 확인해야 할 spike 도출
```

예시 시나리오:

```text
성능 시나리오:
월말 18:00~20:00 사이 취소 요청이 평소의 5배로 증가한다.
95 percentile latency는 500ms 이하이어야 한다.

가용성 시나리오:
결제사 환불 API가 30분 동안 timeout된다.
사용자에게 중복 환불 없이 일관된 상태를 보여줘야 한다.

보안 시나리오:
CS 상담원이 강제 취소를 수행한다.
권한 없는 상담원은 수행할 수 없어야 하며, 모든 수행 이력이 감사 가능해야 한다.
```

이렇게 하면 기능 구현 중간에 뒤늦게 발견되는 NFR 리스크를 초기에 끌어낼 수 있습니다.

---

# 10. Premortem으로 사람들이 말하지 않는 우려를 끌어낸다

unknown unknowns는 기술 분석만으로는 다 나오지 않습니다. 팀원들이 이미 걱정하고 있지만 말하지 않은 것이 있을 수 있습니다. Gary Klein의 premortem은 팀이 “이 프로젝트가 이미 실패했다”고 가정한 뒤 실패 이유를 생성하는 방식입니다. HBR 설명에 따르면 이 방식은 사람들이 계획 단계에서 우려를 더 자유롭게 말하게 하여, 사후 부검이 아니라 사전 개선을 가능하게 합니다. 

## 왜 premortem이 효과적인가

일반 회의에서는 사람들이 이런 말을 꺼리기 쉽습니다.

```text
“이 일정은 위험합니다.”
“저 모듈은 아무도 모릅니다.”
“운영팀이 수동으로 처리하는 부분을 우리가 모르는 것 같습니다.”
“정산 쪽은 건드리면 위험합니다.”
“테스트가 없어서 영향 범위를 확신할 수 없습니다.”
```

하지만 premortem에서는 “실패했다고 가정”하기 때문에 이런 우려가 더 자연스럽게 나옵니다.

## 실행 질문

```text
배포 일주일 후 큰 장애가 났다고 가정하자. 왜 났을까?
고객이 항의했다고 가정하자. 어떤 기존 동작을 깨뜨렸을까?
정산 금액이 틀렸다고 가정하자. 어디에서 불일치가 생겼을까?
운영팀이 rollback을 못 했다고 가정하자. 왜 못 했을까?
성능 장애가 났다고 가정하자. 어떤 query/job/API가 병목이었을까?
보안 이슈가 났다고 가정하자. 어떤 권한/감사 구멍 때문이었을까?
```

산출물은 “걱정 목록”이 아니라, 검증 가능한 task여야 합니다.

| 실패 가정 | 위험 신호 | 검증 액션 |
|---|---|---|
| 외부 파트너 장애 | consumer 목록 불명 | API key별 호출 로그 분석 |
| 정산 불일치 | 취소 상태값 의미 불명 | batch owner와 정산 샘플 확인 |
| rollback 실패 | 데이터 migration 포함 | rollback rehearsal |
| 성능 장애 | 월말 batch와 충돌 | peak traffic 기준 load test |
| 운영 혼선 | runbook 미갱신 | 운영팀 walkthrough |

---

# 11. AI/LLM은 탐색 보조로 쓰되, 증거로 취급하지 않는다

요즘은 LLM으로 legacy code를 요약하거나 관련 파일 후보를 찾는 것이 상당히 유용합니다. Martin Fowler/Thoughtworks의 legacy modernization 글도 GenAI의 가치가 코드 생성보다 **long-lived, large, complex legacy system 이해**에 있을 수 있다고 설명합니다. Thoughtworks Technology Radar 역시 GenAI가 legacy codebase 이해에서 business rule, logic summary, dependency 식별을 돕는 실용적 default가 되고 있다고 평가합니다. 

## 왜 조심해야 하는가

LLM은 다음에는 유용합니다.

```text
관련 파일 후보 찾기
복잡한 메서드 요약
도메인 용어 후보 추출
중복 정책 로직 후보 찾기
테스트 케이스 후보 생성
영향 범위 초안 만들기
```

하지만 LLM 답변 자체는 증거가 아닙니다. 특히 브라운필드 unknown unknowns는 **실제 운영 데이터, 과거 장애, 특정 고객 예외, 비공식 운영 절차**에 숨어 있는데, LLM은 이런 것을 모를 수 있습니다.

따라서 AI 출력은 반드시 다음 중 하나로 검증해야 합니다.

```text
코드 검색
테스트 실행
로그/trace 확인
DB 데이터 샘플 확인
도메인 전문가 확인
운영 runbook 확인
contract/API consumer 확인
```

좋은 사용 방식은 다음입니다.

```text
LLM에게 “이 요구사항의 영향 범위를 말해줘”라고 묻는다.
→ 후보 목록을 받는다.
→ 각 후보에 대해 실제 근거를 붙인다.
→ 근거 없는 후보는 unknown register에 넣는다.
```

---

# 전체 프로세스: 요구사항 수신 후 discovery flow

아래 순서가 논리적으로 가장 안정적입니다.

```text
1. 변경 가설로 재정의
2. interaction perimeter 파악
3. as-built architecture 복원
4. 데이터/상태 전이 분석
5. 런타임 증거 수집
6. 도메인 워크숍
7. change impact matrix 작성
8. characterization/contract test 작성
9. ATAM-lite로 품질속성 분석
10. premortem으로 잔여 리스크 도출
11. unknown register와 구현 전 spike로 전환
```

## 왜 이 순서인가

각 단계는 앞 단계의 blind spot을 보완합니다.

| 단계 | 주로 드러내는 것 | 다음 단계가 필요한 이유 |
|---|---|---|
| 변경 가설 | 요구사항의 모호함 | 시스템 경계를 아직 모름 |
| interaction perimeter | 외부 소비자/연동 | 내부 구조를 아직 모름 |
| as-built architecture | 실제 코드 구조 | 실제 사용 빈도를 아직 모름 |
| 데이터 분석 | 과거 데이터/상태 의미 | 업무적 이유를 아직 모름 |
| 런타임 증거 | 실제 사용 흐름 | 왜 그런 흐름인지 아직 모름 |
| 도메인 워크숍 | 업무 암묵지 | 기술 영향으로 정리 필요 |
| impact analysis | 영향 범위 | 검증 장치 필요 |
| characterization test | 현재 동작 보호 | NFR 리스크는 별도 |
| ATAM-lite | 성능/보안/운영성 | 말 못 한 우려는 남음 |
| premortem | 잠재 실패 이유 | 실행 가능한 task로 바꿔야 함 |

이 구조의 핵심은 **한 가지 방법에 의존하지 않는 것**입니다. unknown unknowns는 대개 한 소스에서는 보이지 않고, 여러 소스를 대조할 때 보입니다.

---

# 실무 템플릿 1: Unknown register

요구사항 분석 중 발견한 불확실성은 별도 register로 관리하는 것이 좋습니다.

| ID | Unknown | 유형 | 근거 | 위험도 | 확인 방법 | Owner | Due |
|---|---|---|---|---:|---|---|---|
| U-01 | 외부 파트너가 취소 API 응답 필드에 의존하는지 불명 | Interface | API gateway consumer 있음 | 높음 | key별 호출 로그 + 파트너 확인 | Backend | D+2 |
| U-02 | `CANCELLED` 상태가 정산에서 어떤 의미인지 불명 | Data | batch code 미확인 | 높음 | batch owner 인터뷰 + 샘플 검증 | Data | D+3 |
| U-03 | admin force cancel이 새 정책을 따라야 하는지 불명 | Domain | CS 수동 처리 존재 | 중간 | CS 워크숍 | PO | D+2 |
| U-04 | 결제사 timeout 시 재시도 멱등성 보장 여부 불명 | Reliability | retry 코드 존재 | 높음 | idempotency test | Backend | D+4 |
| U-05 | rollback 시 이미 생성된 환불 요청 처리 불명 | Release | 데이터 변경 포함 | 높음 | rollback rehearsal | DevOps | D+5 |

중요한 점은 unknown을 “회의록에 적어두는 것”이 아니라 **검증 가능한 액션과 owner를 붙이는 것**입니다.

---

# 실무 템플릿 2: 요구사항 분석 질문 세트

## 비즈니스/도메인 질문

```text
이 요구사항이 바꾸는 업무 규칙은 정확히 무엇인가?
기존 규칙 중 절대 유지해야 하는 것은 무엇인가?
예외 케이스는 무엇인가?
수동 처리 절차가 있는가?
고객/상품/지역/권한별로 다른 규칙이 있는가?
과거 장애나 고객 요구 때문에 생긴 특례가 있는가?
현업이 “당연하다”고 생각하지만 문서화하지 않은 규칙은 무엇인가?
```

## 기술 영향 질문

```text
어떤 API, batch, event, DB table, report가 영향을 받는가?
외부 consumer가 있는가?
같은 규칙이 여러 코드 경로에 중복되어 있는가?
feature flag나 tenant별 분기가 있는가?
데이터 migration이 필요한가?
구버전 client는 어떻게 동작하는가?
```

## 데이터 질문

```text
기존 데이터가 신규 규칙을 만족하는가?
상태값/코드값의 의미가 모든 시스템에서 같은가?
null, default, legacy value의 의미는 무엇인가?
과거 데이터는 어떻게 보여줄 것인가?
감사 로그와 변경 이력은 충분한가?
```

## 운영/릴리즈 질문

```text
배포 후 문제를 어떻게 감지할 것인가?
rollback은 코드만 하면 되는가, 데이터도 되돌려야 하는가?
feature flag로 점진 배포 가능한가?
운영 runbook은 바뀌어야 하는가?
CS/운영팀 교육이 필요한가?
장애 시 수동 보정 절차가 있는가?
```

## 테스트 질문

```text
현재 동작을 보호하는 테스트가 있는가?
없다면 characterization test를 어디에 둘 것인가?
외부 API contract test가 필요한가?
batch와 정산 테스트 데이터가 있는가?
성능/부하 테스트가 필요한가?
```

---

# 실무 예시: “회원 등급 정책 변경” 요구사항

요구사항:

```text
회원의 최근 6개월 구매금액을 기준으로 등급을 산정한다.
```

겉으로 보면 단순한 정책 변경입니다. 하지만 브라운필드에서는 다음 unknown unknowns가 나올 수 있습니다.

## 1단계: 변경 가설

```text
현재: 누적 구매금액 기준으로 등급 산정
변경: 최근 6개월 구매금액 기준
유지: 기존 VIP 혜택 일부 유지 가능성
불명: 과거 등급 이력, 수동 승급, 제휴 고객 예외
```

## 2단계: interaction perimeter

```text
등급을 쓰는 곳:
- 쇼핑몰 할인
- 쿠폰 발급 batch
- CS admin
- CRM campaign
- 외부 제휴 API
- BI 리포트
```

## 3단계: as-built

```text
등급 계산 로직:
- UserGradeService.calculate()
- CouponBatch.selectTargetUsers()
- CRMExportJob.mapGrade()
- AdminUserController.forceUpgrade()
```

unknown:

```text
CouponBatch가 UserGradeService를 쓰지 않고 자체 SQL로 등급 판단
CRMExportJob이 grade_code를 다른 의미로 변환
Admin 강제 승급은 만료일이 없음
```

## 4단계: 데이터

```text
grade_code = VIP, GOLD, SILVER 외에 VVIP, MANUAL, LEGACY 존재
manual_upgrade_until이 null인 데이터 다수
최근 6개월 구매금액 계산 시 환불/취소 주문 포함 여부 불명
```

## 5단계: 런타임

```text
등급 조회 API는 모바일 구버전에서 매우 자주 호출
쿠폰 batch는 매월 1일 새벽에 실행
CRM export는 매주 월요일 실행
CS admin force upgrade는 특정 시즌에 급증
```

## 6단계: 도메인 워크숍

현업이 말합니다.

```text
일부 VIP는 계약상 1년 유지해야 한다.
제휴 고객은 구매금액과 무관하게 GOLD 이상이어야 한다.
환불된 주문은 구매금액에서 제외하지만, 부분 환불은 예외가 있다.
```

이제 원래 요구사항은 다음처럼 바뀝니다.

```text
회원 등급은 기본적으로 최근 6개월 순구매금액 기준으로 산정한다.
단, 계약 VIP, 제휴 고객, 수동 승급 고객은 별도 policy를 따른다.
등급 변경은 쿠폰 batch, CRM export, CS admin, 외부 제휴 API와 정합성을 유지해야 한다.
```

이것이 unknown unknowns를 요구사항으로 전환한 결과입니다.

---

# 최종 산출물은 무엇이어야 하는가

브라운필드 요구사항 discovery의 최종 산출물은 긴 문서가 아니라, 의사결정 가능한 패키지여야 합니다.

```text
1. 변경 가설서
2. interaction perimeter map
3. as-built 영향 범위 지도
4. 데이터/상태 분석 결과
5. runtime evidence 요약
6. domain workshop hotspot 목록
7. change impact matrix
8. characterization/contract test 계획
9. NFR risk 목록
10. unknown register
11. 구현 전 spike / PoC / 검증 task 목록
```

특히 중요한 것은 10번과 11번입니다. unknown unknowns를 발견했다면 반드시 다음 중 하나로 전환해야 합니다.

```text
요구사항 수정
설계 제약
테스트 케이스
관측 지표
운영 runbook
migration task
spike task
release/rollback 조건
```

그렇지 않으면 “좋은 분석을 했다”로 끝나고 실제 구현 중 같은 리스크가 다시 터집니다.

---

# 요약: 가장 효과적인 조합

브라운필드 프로젝트에서 unknown unknowns를 발견하는 가장 좋은 방법은 하나의 기법이 아니라 다음 조합입니다.

```text
요구사항을 변경 가설로 재정의
+ 외부 interaction perimeter 확인
+ as-built architecture 복원
+ 데이터/상태 의미 분석
+ 로그/trace 기반 runtime evidence 확인
+ EventStorming/Domain Storytelling으로 암묵지 도출
+ Change Impact Analysis로 통합
+ Characterization/Contract Test로 현재 동작 보호
+ ATAM-lite와 Premortem으로 품질속성/실패 리스크 탐색
```

이 접근의 논리는 단순합니다.

**요구사항은 의도를 말해주고, 코드는 가능한 동작을 말해주고, 데이터는 과거의 흔적을 말해주고, 로그는 실제 사용을 말해주고, 현업은 이유를 말해줍니다. unknown unknowns는 이 다섯 가지가 서로 어긋나는 지점에서 가장 많이 발견됩니다.**