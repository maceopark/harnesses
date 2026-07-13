# 두 개의 주문을 만들어 낸 재시도

## 엔지니어를 위한 `ultimateinterview` 가이드

[함께 보는 컨퍼런스 발표 자료(HTML)를 열어 보세요.](./ultimateinterview-conference-talk.ko.html)

한 팀이 겉보기에는 작은 안정성 개선 요청을 받습니다.

> `POST /orders`의 일시적 실패를 지수 백오프로 재시도하세요.

플래너는 HTTP 클라이언트를 찾아 지터를 적용한 최대 3회 시도를 추가하고, 벤더가 요청을 처리하기 전에 목(mock)이 실패하도록 테스트를 작성합니다. 두 번째 시도는 성공합니다. 테스트 스위트는 모두 통과합니다.

하지만 프로덕션에서는 다른 타임라인이 발생합니다.

```text
10:00:00.000  checkout이 client_order_id=checkout-734로 POST /orders를 전송
10:00:00.041  벤더가 주문 O-481을 삽입하고 트랜잭션을 커밋
10:00:00.044  벤더가 고객에게 한 번 청구
10:00:00.600  시도별 600 ms 관찰 타임아웃이 만료됨. checkout은 쓰기가 커밋되었는지 여전히 판단할 수 없음
10:00:00.800  재시도 스케줄링/백오프 후, 첫 번째 재시도가 안정적인 멱등성 키 없이 또 다른 POST를 전송
10:00:00.843  벤더가 주문 O-482를 삽입하고 고객에게 다시 청구
10:00:02.000  별도로 설정된 2 s 엔드투엔드 checkout 데드라인이 만료될 시점이지만, 중복은 이미 생성됨
```

`600 ms` 제한은 “이 시도가 관찰 가능한 응답을 얼마나 오래 기다릴 수 있는가?”에 답합니다. `2 s` 제한은 “전체 checkout 호출이 얼마나 오래 실행될 수 있는가?”에 답합니다. 둘은 서로 바꿔 쓸 수 없습니다. 약 `800 ms` 시점의 첫 번째 재시도는 전체 예산 안에 있으므로, 이 장애는 데드라인 이후에 부당하게 재시도했기 때문에 발생한 것이 아닙니다.

재시도 알고리즘은 설계한 대로 정확히 동작합니다. 그런데도 계획은 잘못되었습니다. 부수 효과는 성공했지만 응답이 유실된 경우, 재시도가 무엇을 의미하는지 전혀 정의하지 않았기 때문입니다.

이 가이드는 하나의 요청이 `ultimateinterview` 세션을 통과하는 과정을 따라갑니다. 기록된 가설, 증거, 점수, 질문, 게이트 등 프로토콜 상태와 의사결정 로직을 보여 줍니다. 이는 LLM의 비공개 사고 과정을 공개한다고 **주장하지 않습니다**.

## 1. 사례 연구를 위해 설정한 가상의 저장소 사실

이 표의 모든 내용은 **가상이지만 현실적인 사례**입니다. `harnesses` 저장소나 실제 벤더에 관한 주장이 아닙니다.

| 조사한 표면 | 저장소 또는 계약상의 사실 |
| --- | --- |
| 주문 클라이언트 | `OrderGateway.submit()`은 벤더의 `POST /orders`를 동기 방식으로 한 번 호출합니다. |
| 요청 모델 | 모든 checkout 요청에는 안정적인 `client_order_id`가 포함됩니다. |
| 로컬 스키마 | `orders`에는 `(merchant_id, client_order_id)`에 대한 고유 키가 있습니다. |
| 현재 헤더 | 게이트웨이는 HTTP 시도마다 바뀌는 `X-Request-Id`를 전달하지만, 벤더의 `Idempotency-Key`는 보내지 않습니다. |
| 벤더 OpenAPI | 연결 재설정, 타임아웃, `502`, `503`, `504`는 재시도할 수 있습니다. `429`는 `Retry-After`를 사용해 재시도할 수 있습니다. |
| 벤더 멱등성 | 24시간 안에 같은 키와 페이로드를 다시 사용하면 원래 주문이 반환됩니다. 같은 키를 다른 페이로드와 함께 다시 사용하면 `409`가 반환됩니다. |
| 기존 정책 | 멱등적인 `GET`은 총 3회 시도, 100 ms 기본 지연, 지수 2, 풀 지터, 1 s 상한을 사용합니다. |
| 요청 예산 | 벤더에 대한 각 시도에는 600 ms 관찰 타임아웃이 있고, 이를 포함하는 checkout 호출에는 별도의 2 s 엔드투엔드 데드라인이 있습니다. |
| 공유 유틸리티 | 기존 코드에는 판매자 범위 식별자를 위한 버전 관리된 정규 튜플 직렬화와, 시도·결과·실패 분류·해시된 상관관계 식별자를 기록하는 의존성 텔레메트리가 있습니다. |
| 테스트 기능 | 픽스처를 사용해 벤더가 주문을 커밋한 다음, 응답이 checkout에 도달하기 전에 연결을 닫게 할 수 있습니다. |

원래 요청은 아직 구현 가능한 상태가 아닙니다. “일시적”이나 “지수” 같은 단어는 재시도 라이브러리, 시도 횟수, 타이밍으로 주의를 끕니다. 위험한 분기는 그보다 앞에 있습니다.

```text
벤더가 요청을 거부했는가,
아니면 주문을 커밋했고 응답만 실패했는가?
```

호출자에게는 두 상태가 똑같아 보이지만, 각각 필요한 동작은 다릅니다. 따라서 실제로 원하는 결과를 다음과 같이 다시 서술합니다.

> 하나의 논리적 주문, 한 번의 결제, 기존 동기식 데드라인을 유지하면서 선택된 전송 실패로부터 복구한다.

이것은 제품 계약입니다. “지수 백오프 추가”는 가능한 메커니즘 중 하나일 뿐입니다.

## 2. LLM이 이미 알고 있는 실패 모드를 놓칠 수 있는 이유

성능이 뛰어난 언어 모델은 멱등성, 모호한 네트워크 결과, 재시도 폭주, 데드라인을 알고 있습니다. 문제는 저장된 지식의 부족이 아닙니다. 어떤 지식이 현재 상황에 적용되는지 판단하고, 그럴듯한 일반 패턴을 로컬 사실로 취급하지 않는 것이 문제입니다.

LLM 워크플로의 몇 가지 특성 때문에 피상적인 계획이 매력적으로 보입니다.

1. **요청이 주의의 방향을 정합니다.** “재시도 추가”라는 표현은 트랜잭션 상태나 중복 결제보다 타이밍과 재시도 라이브러리를 더 쉽게 떠올리게 합니다.
2. **익숙한 구현이 빠르게 떠오릅니다.** 지수 백오프는 합리적인 일반 패턴이므로, 모델은 커밋 경계를 조사하기 전에 일관성 있어 보이는 계획에 도달할 수 있습니다.
3. **하나의 컨텍스트가 자신의 전제를 반복합니다.** 플래너가 설계를 선택하고, 커밋 전 실패를 가정하는 테스트를 작성한 다음, 통과한 테스트를 확인 근거로 인용할 수 있습니다. 산출물들이 일치하는 이유는 모두 하나의 가정을 물려받았기 때문입니다.
4. **복사된 증거가 복수의 증거처럼 보입니다.** OpenAPI 문단, 생성된 SDK 주석, 내부 위키가 모두 하나의 출처를 반복할 수 있습니다. 이를 세 명의 증인으로 세면, 하나의 인과적 뿌리가 외관상 삼각 검증된 것처럼 세탁됩니다.
5. **유창한 표현이 누락된 판단 조건을 가립니다.** 누군가 무엇이 일시적인지, “안전하게”가 무엇을 의미하는지, 어떤 관찰 가능한 결과가 이를 증명하는지 묻기 전까지는 “일시적 실패를 안전하게 재시도”라는 말이 정밀하게 들립니다.

`ultimateinterview`는 LLM의 지식을 활용하지만 그 역할을 제한합니다.

> 모델의 지식은 가설, 적용 가능성 질문, 반증 조건, 증거 경로를 제안합니다. 그 자체로는 어떤 결론을 확정하는 근거 점수도 받지 못합니다.

**반증 조건(falsifier)**은 현재 모델이 틀렸음을 보여 주는 증거입니다. “실패한 시도는 커밋되지 않았다”라는 주장에는 커밋 후 연결 종료 추적이 반증 조건입니다. 이를 명시하면 일반 지식이 조사 계획으로 바뀝니다.

## 3. 사용자에게 질문하기 전에 ORIENT 수행

인터뷰는 설문지로 시작하지 않습니다. 먼저 저장소, 과거 교훈, 완료되지 않은 인터뷰 상태를 확인합니다. 핵심 규칙은 간단합니다. 저장소가 답할 수 있는 사실을 사람에게 묻지 마세요.

### 3.1 저장소 우선 조사

이 사례에서 첫 번째로 범위를 제한해 조사하면 다음을 찾습니다.

- 동기식 `OrderGateway.submit()` 호출
- 안정적인 `client_order_id`와 판매자 범위의 고유성
- 매번 바뀌는 `X-Request-Id`와 존재하지 않는 벤더 멱등성 헤더
- 시도별 600 ms 관찰 타임아웃, 이와 별개인 2 s 엔드투엔드 데드라인, 기존 `GET` 재시도 정책
- 벤더 문서에 정의된 재시도 분류, 키 동작, 24시간 보존 기간
- 커밋 후 연결 종료 픽스처

이것만으로도 가치가 낮은 사용자 질문 여러 개를 피할 수 있습니다. 인터뷰는 벤더 문서에 어떤 상태 코드가 적혀 있는지, 로컬 고유 인덱스가 어떻게 구성되어 있는지, 현재 타임아웃이 얼마인지 사용자에게 묻지 않습니다. 증거만으로 결정할 수 없는 중요한 제품 또는 정책 선택이 남아 있는 경우에만 질문합니다.

### 3.2 비용 없는 열린 세계 가설

분석 렌즈를 선택하기 전에 모델은 최대 세 가지 누락 가능성을 기록합니다. 각 가설은 `origin: open-world`, `model-prior`, `assumption`, `hypothesis-only` 상태로 시작합니다.

| 가설 | 적용 가능성 질문 | 반증 조건 | 증거 경로 | 초기 상태 |
| --- | --- | --- | --- | --- |
| 호출자가 실패를 관찰하기 전에 업스트림이 커밋할 수 있다. | 타임아웃이나 연결 재설정이 클라이언트에 도달하기 전에 `POST /orders`가 커밋될 수 있는가? | 작업과 응답 전달이 원자적이거나, 안정적인 키를 사용하는 멱등성이 이미 연결되어 있다. | 벤더 계약, 호출 지점, 커밋 후 연결 종료 픽스처, 여전히 필요하다면 승인된 프로덕션 추적. | 가설일 뿐이며, 근거 점수 없음. |
| 재시도가 일시적인 서비스 저하를 증폭하고 checkout 데드라인을 소진할 수 있다. | 벤더 성능이 저하된 동안 많은 요청이 동시에 재시도할 수 있는가? | 트래픽이 다른 곳에서 직렬화되거나, 이 호출이 대화형 데드라인 밖에 있다. | 데드라인 설정, 메트릭, 재시도 라이브러리 동작, 범위를 제한한 부하 시나리오. | 가설일 뿐이며, 근거 점수 없음. |
| 자동 재시도가 호출 범위를 벗어나 벤더의 보존 기간보다 오래 지속될 수 있다. | 이 변경으로 도입되는 재시도 중 다른 호출에서 실행되거나 24시간 이후에 실행될 수 있는 것이 있는가? | 모든 자동 재시도가 원래 2 s 호출 안으로 제한되며, 호출 간 재실행에는 별도의 영속적 설계가 필요하다. | 호출 그래프, 재시도 생명주기, 벤더 TTL 계약, 지원 워크플로. | 가설일 뿐이며, 근거 점수 없음. |

이 변경은 도메인 상태, 목표와 장애물, 안정성 품질, 통제 언어, 이해관계자 관점, 오용 등 여러 분석 렌즈를 활성화합니다. 이름 자체보다 각 렌즈가 요구하는 의무가 중요합니다. 상태를 열거하고, 서로 경쟁하는 결과를 드러내며, 모호한 품질을 수치화하고, 결정을 내리는 판단 조건을 정의하고, 영향을 받는 주체를 확인하며, 호출자가 제어하는 키를 집중적으로 검증해야 합니다.

이는 안정성에 영향을 주는 외부 금융 쓰기 작업이므로, 이 사례에서는 `full` 깊이와 최대 20회의 사용자 의사결정 상호작용 한도를 선택합니다.

### 3.3 브레인 덤프

조사가 끝난 뒤에야 사용자에게 보이는 인터뷰가 시작됩니다.

> 원하는 결과, 망가질까 우려하는 부분, 이미 알고 있는 제약 조건, 지금까지 본 엣지 케이스를 알려 주세요. 이 변경은 외부 금융 쓰기와 안정성 동작을 바꾸므로, 최대 20회의 의사결정 상호작용이 가능한 전체 인터뷰로 진행하겠습니다.

사용자는 다음과 같이 답합니다.

- checkout은 동기식으로 유지되어야 한다.
- 중복 주문이나 결제는 허용할 수 없다.
- 반복적으로 발생하는 장애는 벤더의 `503`이다.
- 이 변경으로 큐를 도입해서는 안 된다.

각 항목은 별도의 주장으로 기록됩니다. “큐 없음”은 비목표로 기록됩니다. “중복 결제 없음”은 코드에서 추론한 사실이 아니라 사용자가 소유한 제품 의사결정입니다.

### 3.4 프레이밍 검증

프로토콜은 요청된 메커니즘을 원하는 결과와 비교해 검증합니다.

1. 재시도 루프를 추가한다.
2. 모호한 전송 결과에서도 하나의 논리적 주문을 유지한다.
3. 재시도를 피하고 조정 절차를 도입한다.

사용자에게 보이는 재서술은 다음과 같습니다.

> 요청된 루프는 실제 계약이 아니라 메커니즘이라고 생각합니다. 이 변경은 두 번째 논리적 주문을 만들거나 현재 동기식 데드라인을 초과하지 않으면서, 선택된 전송 실패로부터 복구해야 합니다. 큐나 백그라운드 조정 흐름은 범위 밖입니다. 이 내용이 의도를 바꾼다면 바로잡아 주세요.

사용자가 확인합니다. 산출물은 여전히 동기식 동작 변경이지만, 성공 조건은 “결국 응답을 받는다”에서 “영속적인 비즈니스 효과를 중복 생성하지 않고 복구한다”로 바뀌었습니다.

## 4. 첫 번째 원장에 기록된 활성 잔여 모호성은 99

원장은 무엇을 알고 있는지, 무엇이 여전히 구현을 분기시킬 수 있는지, 무엇이 안전한 인계를 가로막는지에 관한 단일 진실 공급원입니다.

| ID | 초기 주장 또는 공백 | 모호성 점수 | 영향 가중치 | 상태 | 초기 근거 |
| --- | --- | ---: | ---: | --- | --- |
| `F-CURRENT` | 현재 `POST /orders`는 한 번 시도합니다. | 0 | 2 | 삼각 검증됨 | 호출 지점과 테스트. |
| `G-TRANSIENT` | 정확한 재시도 가능 실패 집합이 불명확합니다. | 2 | 3 | 초안 | 벤더 계약과 기존 `GET` 정책은 `429` 처리 방식이 다릅니다. |
| `G-POST-COMMIT` | 커밋 후 응답이 유실된 경우의 동작이 정의되지 않았습니다. | 3 | 5 | 차단됨 | 픽스처는 이 상태가 가능함을 보여 줍니다. |
| `G-IDEMPOTENCY` | 시도 간에 유지되는 안정적인 식별자가 정의되지 않았습니다. | 3 | 5 | 차단됨 | `client_order_id`는 존재하지만 벤더 키로 전송되지 않습니다. |
| `G-DUPLICATE` | “주문과 결제가 각각 최대 하나”라는 조건이 아직 명시적 불변 조건이 아닙니다. | 2 | 5 | 초안 | 금융 영향은 추론된 것이므로 사용자 권한자의 결정이 필요합니다. |
| `G-ATTEMPTS` | 시도 횟수가 명시되지 않았습니다. | 2 | 3 | 초안 | `GET` 기본값은 있지만 `POST`에 적용된다고 볼 수 없습니다. |
| `G-TTL` | 벤더의 24시간 키 유효 기간이 지난 뒤 호출 간 재실행 동작이 결정되지 않았습니다. | 3 | 3 | 초안 | 벤더 문서에는 TTL이 정의되어 있습니다. 현재 코드는 하나의 2 s 호출 안에서만 재시도하며, 영속적 재실행 저장소나 제어 가능한 시계 연결부가 없습니다. |
| `G-KEY-PAYLOAD` | 동일한 키를 다른 페이로드와 함께 사용할 때의 로컬 동작이 정의되지 않았습니다. | 3 | 3 | 초안 | 벤더 계약은 `409`를 규정하지만 로컬 API에는 정의가 없습니다. |
| `G-CONCURRENCY` | 동일한 논리적 식별자를 사용하는 동시 요청의 동작이 정의되지 않았습니다. | 3 | 5 | 차단됨 | 로컬 고유성만으로는 업스트림 동작을 입증할 수 없습니다. |
| `G-DEADLINE` | 2 s 데드라인 안에서의 재시도 동작이 명시되지 않았습니다. | 2 | 3 | 초안 | 요청 설정. |
| `G-OBSERVE` | 운영자가 최초 호출과 재시도를 구분할 수 없습니다. | 2 | 2 | 초안 | 현재 로그와 메트릭. |
| `G-SCOPE` | 이 변경이 비동기 큐 또는 조정 기능으로 확대되는지가 불명확합니다. | 2 | 2 | 초안 | 사용자 의도가 아니라 모델이 생성한 대안입니다. |

잔여 모호성은 활성 상태이고 연기되지 않은 공백의 가중 합입니다. 현재 `G-TTL`은 여전히 활성 상태이므로 `3 * 3 = 9`가 합계에 남습니다.

```text
6 + 15 + 15 + 10 + 6 + 9 + 9 + 15 + 6 + 4 + 4 = 99
```

이 수치는 “99%를 모른다”는 뜻이 아닙니다. 활성 위험 요인과 그 변화를 가시화합니다. 나중에 저장소 증거를 통해 연기를 권고할 수는 있지만, 증거만으로 범위 결정을 내리거나 `G-TTL`을 활성 잔여 모호성에서 제거할 수는 없습니다.

## 5. 프로토콜은 금융 상태에 관한 질문을 먼저 요구하며, 헬퍼는 산술을 결정적으로 만듭니다

필수적인 범위 또는 상태 관련 의무가 명확해지면 `question_score.py`는 영향, 구현 분기 정도, 불확실성 감소, 범위 포괄도, 사용자 비용, 중복도를 기준으로 후보의 순위를 정합니다.

공식은 다음과 같습니다.

```text
impact * branch_split * uncertainty_reduction * coverage
----------------------------------------------------------------
1 + user_cost + redundancy
```

이 사례에서 사용한 요소들은 최종 수치로부터 역산한 것이 아니라 명시적으로 정의되어 있습니다.

| 순위 | 후보 | 영향 | 분기 정도 | 불확실성 감소 | 범위 포괄도 | 사용자 비용 | 중복도 | 정확한 점수 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 커밋 후 응답 유실 | 5 | 5 | 5 | 5 | 3 | 0 | `625 / 4 = 156.25` |
| 2 | 논리적 주문 키 | 5 | 4 | 5 | 4 | 3 | 0 | `400 / 4 = 100` |
| 3 | 전체 시도 횟수 상한 | 3 | 3 | 3 | 3 | 1 | 0 | `81 / 2 = 40.5` |
| 4 | 재시도 가능 실패 분류 | 3 | 4 | 3 | 4 | 3 | 0 | `144 / 4 = 36` |

대표적인 스코어러 입력과 실행 명령은 다음과 같습니다.

```json
{
  "questions": [
    {"id":"q-post-commit","question":"커밋 후 응답 유실?","impact":5,"branch_split":5,"uncertainty_reduction":5,"coverage":5,"user_cost":3,"redundancy":0,"target_ids":["G-POST-COMMIT"]},
    {"id":"q-key","question":"논리적 주문 키?","impact":5,"branch_split":4,"uncertainty_reduction":5,"coverage":4,"user_cost":3,"redundancy":0,"target_ids":["G-IDEMPOTENCY"]},
    {"id":"q-attempts","question":"전체 시도 횟수 상한?","impact":3,"branch_split":3,"uncertainty_reduction":3,"coverage":3,"user_cost":1,"redundancy":0,"target_ids":["G-ATTEMPTS"]},
    {"id":"q-retryable","question":"재시도 가능 실패 분류?","impact":3,"branch_split":4,"uncertainty_reduction":3,"coverage":4,"user_cost":3,"redundancy":0,"target_ids":["G-TRANSIENT"]}
  ]
}
```

```bash
uv run .agents/skills/ultimateinterview/scripts/question_score.py --format markdown questions.json
```

```text
## 질문 점수

| 순위 | ID | 점수 | 대상 ID | 질문 |
| --- | --- | --- | --- | --- |
| 1 | q-post-commit | 156.25 | G-POST-COMMIT | 커밋 후 응답 유실? |
| 2 | q-key | 100.00 | G-IDEMPOTENCY | 논리적 주문 키? |
| 3 | q-attempts | 40.50 | G-ATTEMPTS | 전체 시도 횟수 상한? |
| 4 | q-retryable | 36.00 | G-TRANSIENT | 재시도 가능 실패 분류? |
```

커밋 후 의미론은 금융 불변 조건에 영향을 주고, 점수 3인 공백을 해소하며, 아직 검토하지 않은 상태 전이를 포괄하고, 여러 설계로 분기되게 하므로 여전히 가장 중요합니다. 논리적 식별자는 `G-IDEMPOTENCY` 역시 점수 3인 공백이므로 그다음 순위입니다. 선언된 판단에 따르면 시도 횟수 상한은 실패 분류보다 근소하게 높은 점수를 받습니다(`40.5` 대 `36`). 두 항목 모두 동작과 테스트를 바꾸므로 영향은 `3`이지만, 시도 횟수 질문은 답변 비용이 더 낮습니다. 어느 쪽도 기능이 두 개의 주문을 생성할 수 있는지를 결정하지 않으므로, 둘 다 커밋 후 질문보다 훨씬 낮은 순위에 머뭅니다.

백오프 매개변수는 이를 뒷받침하는 원장 공백이 없으므로 의도적으로 이 점수화된 큐에서 제외됩니다. 중요한 상태, 식별자, 데드라인, 시도 횟수 공백이 확정된 뒤에야 기존 `GET` 정책에 근거하여 해당 수치를 증거 기반의 저위험 기본값으로 스마트 기본값 묶음에 포함할 수 있습니다.

유능한 Claude 또는 Codex 플래너도 **동일한 질문에 도달할 수 있습니다**. 구조적인 주장은 그보다 범위가 좁습니다. 이 위험이 원장에 기록되면, 세션 런타임 규칙은 인터뷰어가 더 쉬운 메커니즘 설정 질문보다 우선하여 가장 높은 순위의 질문 가능한 핵심 경로 질문을 선택하도록 요구합니다. `question_score.py`는 입력된 판단과 산술을 결정적으로 만들지만, 누락된 후보를 감지하거나 잘못된 차원 판단을 교정하거나 인터뷰어가 실제로 최상위 순위를 따랐는지 독립적으로 강제할 수는 없습니다. 런타임 규칙과 영속화된 세션 검토가 나머지 통제 역할을 담당합니다.

## 6. 첫 번째 구조화된 질문

인터뷰는 증거를 보여 주고, 구체적인 실패 시퀀스를 제시하고, 여러 분기를 열어 두며, 증거가 뒷받침하는 분기만 추천하고, 현재 모델을 반증할 조건을 명시합니다.

> 호출자에게 안정적인 `client_order_id`가 있지만, 현재 게이트웨이는 벤더의 `Idempotency-Key`를 전송하지 않는다는 사실을 확인했습니다. 다음 시퀀스를 생각해 보세요. 벤더가 주문 `O-481`을 생성하고 고객에게 청구한 다음, 서비스가 응답을 받기 전에 연결이 닫힙니다. 동일한 논리적 요청이 재시도될 때 반드시 어떤 일이 일어나야 합니까? 중복 생성을 허용하거나 다른 시스템이 이미 조정을 보장한다면, 이는 현재 모델을 반증합니다.

선택지:

1. **원래 주문을 반환하고, 두 번째 주문 생성이나 결제는 절대 하지 않는다 — 권장.** 벤더 계약은 안정적인 키를 사용한 재실행을 지원하고, 로컬 모델에도 이미 고유한 `client_order_id`가 있습니다.
2. **알 수 없음 또는 대기 중 결과를 반환하고 재시도하지 않는다.** 이후에 조정을 담당할 주체가 필요하므로 범위가 추가됩니다.
3. **새 주문으로 재시도하고 중복을 허용한다.** 제안일 뿐이며, 명시된 장애 우려와 충돌합니다.
4. **기타.** 구조화된 인터페이스에는 항상 자유 형식의 예외 선택지가 있습니다.

사용자는 선택지 1을 선택합니다. 이 답변 하나만으로 영향 가중치 5인 공백이 즉시 사라지는 것은 아닙니다. 압박 질문을 견뎌야 하고, 인과적으로 독립적인 출처를 통해 뒷받침되어야 하며, 그렇지 않다면 해당 결정을 소유한 권한자가 명시적으로 수용해야 합니다.

### 무료 압박 후속 질문

다음 프롬프트는 또 다른 추상적 선택 대신 하나의 구체적인 이야기를 요청합니다.

> 구체적인 결과 하나를 순서대로 설명해 주세요. 벤더가 `O-481`을 저장하고 고객에게 한 번 청구했지만 응답은 유실되었습니다. 200밀리초 뒤에 서비스가 재시도합니다. 호출자가 받아야 하는 정확한 결과는 무엇이고, 어떤 레코드가 존재할 수 있으며, 절대 일어나서는 안 되는 일은 무엇입니까?

사용자는 다음과 같이 답합니다.

> 호출자는 `O-481`을 받아야 합니다. 로컬 주문 하나, 벤더 주문 하나, 결제 한 건만 존재해야 합니다. 재시도는 동일한 논리적 키를 사용해야 합니다. 페이로드가 변경되었다면 첫 번째 결과를 재사용하지 말고 실패해야 합니다.

프로토콜은 이 풍부한 답변을 단순히 “멱등적”이라는 한 단어로 압축하지 않고 다음과 같이 분해합니다.

1. 재시도는 성공했던 동일한 `order_id`를 반환한다.
2. 로컬 주문은 최대 하나만 존재한다.
3. 벤더 주문과 결제는 각각 최대 하나만 존재한다.
4. 동일한 키를 다른 페이로드와 함께 사용하면 거부된다.

이처럼 이야기를 이끌어 내는 압박 후속 질문은 스레드별 무료 후속 질문 2회 규칙에 따라 비용 없이 사용할 수 있습니다. 더 중요한 점은 이후 인수 조건에 관찰 가능한 명사와 개수를 제공한다는 것입니다.

## 7. 증거는 인과적 독립성과 권한을 기준으로 집계한다

인터뷰는 파일 이름이나 채널 라벨의 개수를 투표수처럼 세지 않는다.

| 증거 | 채널 | 독립성 그룹 | 권한 및 인정 범위 |
| --- | --- | --- | --- |
| `OrderGateway.submit()` 호출 지점 | `from-code` | `repo:order-call-site` | 현재 동작을 확정한다. 한 번만 시도하며 벤더 키는 사용하지 않는다. |
| `(merchant_id, client_order_id)`의 고유 인덱스 | `from-code` | `repo:order-schema` | 로컬 고유성 경계를 확정한다. |
| 벤더 OpenAPI의 멱등성 섹션 | `from-docs` | `vendor:idempotency-contract` | 벤더가 문서화한 키 동작과 24시간 TTL을 확정한다. |
| OpenAPI에서 복사되어 생성된 SDK 주석 | `from-code` | 여전히 `vendor:idempotency-contract` | 동일한 근원에서 파생되었으므로 독립성 점수를 추가하지 않는다. |
| 사용자 결정: 주문 하나와 결제 하나 | `from-user` | `user-dependency:G-DUPLICATE` | 제품 결정 권한을 가진다. 현재 코드 동작을 확정하지는 않는다. |
| 커밋 후 연결 종료 픽스처 관찰 결과 | `from-scenario` | `scenario:commit-close` | 이 대리 환경에서 모호한 시퀀스가 발생함을 확정한다. |
| 모델의 사전 지식: POST 재시도는 중복 쓰기를 만들 수 있음 | `assumption` | `model-prior:post-retry` | 탐색 경로만 생성하며, 합의 점수는 받지 않는다. |

이러한 구분은 흔한 범주 오류를 방지한다.

- 코드는 시스템이 현재 무엇을 하는지는 확정하지만, 비즈니스가 무엇을 원해야 하는지는 결정할 수 없다.
- 사용자는 원하는 동작의 소유자가 될 수 있지만, 그렇다고 현재 구현 세부사항에 관한 권위 있는 출처로 취급되지는 않는다.
- 복사된 문서와 생성된 코드는 동일한 하나의 인과적 출처로 남는다.
- 소유자는 단일 출처에 기반한 결정을 명시적으로 수용할 수 있지만, 그렇다고 두 번째 증인이 새로 생기는 것은 아니다.
- 시나리오는 해당 픽스처가 입증한 내용만 증명하며, 벤더가 프로덕션에서 항상 그렇게 동작한다는 사실까지 증명하지는 않는다.

서로 모순되는 출처는 `Contested` 상태로 남는다. 인터뷰어는 현재 계획을 더 쉽게 만들어 주는 출처를 조용히 선택해서는 안 된다.

## 8. 인터뷰의 나머지 과정은 구현 분기를 따른다

다음 질문들은 일반적인 체크리스트가 아니다. 각 질문은 현재 원장, 저장소에서 확인된 사실, 그리고 직전 답변에서 이어진다.

### 8.1 하나의 논리적 주문이란 무엇인가?

저장소에는 판매자 범위의 고유 키가 있지만, `X-Request-Id`는 전송을 시도할 때마다 바뀐다. 사용자에게 표시되는 질문은 다음과 같다.

> 저장소에는 고유한 `(merchant_id, client_order_id)`가 있지만, HTTP 요청이 반복되면 `X-Request-Id`는 바뀝니다. 재시도 전반에 걸쳐 하나의 논리적 주문을 정의하는 값은 무엇입니까?

선택지:

1. **`(merchant_id, client_order_id)` — 권장.** 시도 전반에 걸쳐 안정적이며 로컬 고유성과 일치한다.
2. `X-Request-Id`.
3. 매번 시도할 때마다 생성하는 임의의 키.
4. 기타.

이 결정은 외부에서 관찰 가능한 식별자를 확정하되, 직렬화와 해싱 방식은 빌더가 결정하도록 남겨 둔다.

### 8.2 `429`를 포함해 어떤 실패가 데드라인을 소모할 수 있는가?

벤더 계약에는 이미 대부분의 상태 코드 관련 사실이 정의되어 있다. 사용자에게는 아직 해결되지 않은 정책 분기만 질문한다.

> 벤더는 연결 타임아웃/리셋과 `502`, `503`, `504`를 일시적 오류로 분류합니다. 또한 `Retry-After`와 함께 `429`를 반환합니다. 해당 지연 시간에 다음 시도의 전체 600ms 관찰 예산을 더한 값이 남은 2초 체크아웃 데드라인 안에 들어온다면 재시도해야 합니까?

결정:

- 연결 타임아웃/리셋, `502`, `503`, `504`는 재시도한다.
- `429`는 `Retry-After`와 다음 시도의 전체 600ms 관찰 예산을 합친 값이 데드라인 안에 들어올 때만 재시도한다.
- 그 밖의 `4xx` 응답은 재시도하지 않는다.
- 남은 데드라인 안에 끝낼 수 없는 sleep이나 시도는 절대로 시작하지 않는다.

문서에 명시된 오류 분류와 데드라인 값은 저장소가 답했다. 서버가 지시한 대기 시간이 제품 데드라인과 어떻게 상호작용하는지는 사용자가 결정했다.

### 8.3 데드라인과 시도 횟수는 중요하고 서로 영향을 주므로 별도로 유지한다

`G-DEADLINE`과 `G-ATTEMPTS`는 둘 다 모호성 점수 `2`, 영향 가중치 `3`에서 시작한다. 어느 결정이든 런타임 동작과 테스트를 바꾸며, 두 결정의 답은 서로를 제약한다. 따라서 둘 다 크리티컬 패스 갭으로 유지된다. 어느 쪽도 저위험 스마트 기본값 묶음에 포함될 수 없고, 서로 독립적이지 않으므로 선택적 다중 질문 크리티컬 왕복에도 함께 넣을 수 없다.

먼저 데드라인 질문을 별도의 구조화된 질문으로 제시한다.

> 저장소에는 두 개의 시계가 있습니다. 각 벤더 시도에 적용되는 600ms 관찰 타임아웃과 체크아웃 호출 전체에 적용되는 엄격한 2초 엔드투엔드 데드라인입니다. 재시도 시작 여부는 어느 경계를 기준으로 결정해야 합니까?

선택지:

1. **2초 데드라인이 우선합니다. 필요한 지연 시간과 다음 시도의 전체 600ms 관찰 예산이 모두 들어올 때만 다음 시도를 시작합니다 — 권장.** 기존 호출자 계약을 보존하고 두 시계를 명시적으로 구분한다.
2. 시도 횟수가 허용하는 한 시작하며, 해당 시도가 2초 후에 끝나더라도 허용한다. 이는 호출자에게 노출되는 데드라인을 변경한다.
3. 다음 시도의 타임아웃을 600ms 미만으로 동적으로 줄인다. 제안일 뿐이며, 더 짧은 관찰 구간이 유용하다는 저장소 증거는 없다.
4. 기타.

사용자는 1번을 선택한다. 이 답변으로 가중치 3인 갭을 해결하기 때문에, 프로토콜은 점수를 `2` 아래로 낮추기 전에 압박 질문을 적용한다.

> `t=1.55 s`에 그 밖의 조건으로는 재시도가 가능하고 지연 시간이 `100 ms`이지만, 엔드투엔드 데드라인까지는 `350 ms`만 남아 있습니다. 설정된 시도별 관찰 예산이 `600 ms`인데도 이 시도를 시작합니까?

사용자는 아니라고 답한다. sleep하거나 해당 시도를 시작하지 않고, 매핑된 dependency-unavailable 결과를 반환한다. 이로써 “들어온다”는 표현은 모호하게 “타임아웃을 준수하라”는 지시가 아니라 판정 가능한 조건이 된다.

그런 다음에야 인터뷰는 `G-ATTEMPTS`를 별도의 구조화된 질문으로 묻는다.

> 이 엄격한 데드라인 규칙을 전제로 할 때, 한 번의 호출에서 허용되는 벤더 시도의 최대 총횟수는 몇 번입니까?

선택지:

1. **총 세 번의 시도 — 권장.** 기존 `GET` 정책과 일치하며, 데드라인에 따라 실제 시도 횟수는 줄어들 수 있다.
2. 총 두 번의 시도.
3. 횟수 상한 없이 2초 데드라인까지 계속한다. 제안일 뿐이며, 장애 확산 시 요청을 증폭할 수 있다.
4. 기타.

사용자는 세 번을 선택한다. 압박 시나리오는 단순히 숫자를 반복해서 묻는 대신 상호작용을 확인한다.

> 첫 번째 시도는 600ms 관찰 타임아웃에 도달하고, 첫 번째 재시도는 대략 `800 ms`에 시작하며, 이후 지연 때문에 세 번째 전체 600ms 시도를 더 이상 넣을 수 없습니다. “세 번”은 목표입니까, 아니면 상한입니까?

사용자는 상한이라고 확인한다. 엔드투엔드 조건이 다음 시도를 거부하면 더 적게 시도한다. 이 순서는 중요하다. 시도 횟수 질문을 먼저 묶음에서 수용했다면, 마지막 시도가 2초 계약을 위반하더라도 “세 번 시도”를 반드시 수행해야 하는 것으로 쉽게 오해할 수 있었다.

### 8.4 저위험 메커니즘 기본값만 묶어서 질문한다

중요한 상태, 데드라인, 시도 횟수 결정이 확정된 뒤에는 더 이상 해당 분기를 제약하지 않는 기본값을 묶어서 질문할 수 있다. 각 권장 사항은 근거가 되는 저장소 증거를 명시한다.

> 제안하는 저위험 기본값:
>
> 1. **백오프:** 기존 `GET` 재시도 정책을 근거로, 기본값 100ms, 지수 2, 상한 1초인 full-jitter 지수 백오프를 사용합니다.
> 2. **키 직렬화:** 기존 버전 관리형 정규 튜플 직렬화기를 근거로, 벤더에서 안전하게 사용할 키를 만들기 전에 해당 유틸리티로 `(merchant_id, client_order_id)`를 직렬화합니다. 구분자 문자열 연결 방식을 새로 만들지 않습니다.
> 3. **관측 가능성:** 기존 의존성 텔레메트리를 근거로, 시도 횟수, 최종 결과, 실패 분류, 멱등성 키 해시를 내보냅니다. 원본 키는 절대로 내보내지 않습니다.
>
> 모두 수락하거나, 개별 항목을 수정해 주세요.

사용자는 모두 수락한다. 시도 횟수와 데드라인 동작은 의도적으로 이 묶음에서 제외한다. 이러한 기본값이 권장되는 이유는 로컬 증거가 이를 뒷받침하고, 중요한 계약을 확정한 뒤 남은 선택의 위험이 낮기 때문이다. LLM이 익숙한 재시도 레시피를 임의로 만들어 냈기 때문이 아니다.

### 8.5 같은 키와 다른 payload

벤더는 `409`를 반환하지만, 로컬 계약에는 응답 형태와 동등성의 정의가 필요하다.

> 같은 논리 키가 다른 payload와 함께 재사용되면 API는 결정적인 conflict를 반환해야 합니까, 첫 주문을 반환해야 합니까, 아니면 새 주문을 만들어야 합니까?

사용자는 추가 벤더 호출 없이 로컬 `409 IDEMPOTENCY_KEY_REUSED`를 반환하고, payload 본문은 남기지 않은 채 키 해시와 payload fingerprint만 기록하기로 한다. 이어지는 질문은 “같은 payload”가 동일한 JSON byte를 뜻하는가이다. 최종 판정 기준은 정규화한 business field의 동등성이다. 필드 순서나 의미 없는 표현 차이는 identity를 바꾸지 않는다.

### 8.6 호출 간 재실행은 현재 요구사항이 아니라 명시적으로 연기된 위험이다

현재 자동 재시도는 2초 호출 안에서만 실행된다. 반면 호출을 넘나드는 재실행이나 벤더의 24시간 보존 기간 이후를 탐지하려면 새 vendor-key 저장소와 제어 가능한 clock seam이 필요하다. 안정적인 키만으로 “24시간 이후”를 탐지할 수 있는 척해서도 안 되고, 현재 코드에 기능이 없다는 이유로 활성 `G-TTL`을 조용히 연기해서도 안 된다.

> 현재 코드는 원래 2초 호출 안에서만 재시도합니다. 호출 간 또는 24시간 이후 재실행을 탐지하려면 이 변경에 없는 영속적인 원주문 저장소와 제어 가능한 clock seam이 필요합니다. `G-TTL`을 어떻게 처리할까요?

선택지:

1. **Payments Platform 검토로 연기하고 날짜를 2026-08-15로 기록 — 권장.** 영속 상태와 시간 제어를 추가하면 호출 내부 재시도 변경의 범위를 넘어선다. 소유자, 날짜, 빠진 증거를 명시한다.
2. **현재 범위를 확장.** handoff 전에 영속 저장소, 보존 정책, 호출 간 동작, clock-controlled 검증을 설계하고 구현한다.
3. **기타.** 다른 소유자, 날짜 또는 경계를 제시한다.

사용자가 1번을 선택해야만 `G-TTL`이 `Draft`에서 `Deferred`로 바뀌고 활성 잔여 모호성에서 9점이 빠진다. 현재 구현 경계는 **원래 호출을 벗어나는 자동 재제출 없음**이다.

| 연기된 위험 | 소유자 | 검토 날짜 | 이유 |
| --- | --- | --- | --- |
| 호출 간 재실행 동작, 영속적인 원주문 증명, 보존 의미론, 테스트 가능한 store/clock seam 정의 | Payments Platform | 2026-08-15 | 검증 가능한 24시간 재실행 정책에는 현재 호출 내부 재시도 범위를 벗어난 새 영속 상태와 시간 제어가 필요하다. |

별도 계약이 생길 때까지 retry 코드는 호출 간 자동 재제출을 하지 않으며, 신뢰성 있게 탐지할 수 없는 특별한 24시간 conflict를 반환한다고 주장하지도 않는다.

### 8.7 동시 호출자

> 두 worker가 거의 동시에 같은 `(merchant_id, client_order_id)`를 받으면 무엇이 관찰되어야 합니까?

합의된 동작은 다음과 같다.

- 동일한 payload는 하나의 `order_id`로 수렴한다.
- 벤더 주문과 charge는 각각 최대 하나다.
- 서로 다른 payload가 모두 성공해서는 안 된다. 하나가 이기고 다른 하나는 결정적인 conflict를 반환한다.

구현은 로컬 constraint, distributed lock, 벤더 idempotency 중 무엇이든 선택할 수 있다. 인터뷰는 내부 기법이 아니라 관찰 가능한 동작을 고정한다.

## 9. 모호한 한 줄 요구사항이 다섯 개의 통제된 요구사항으로 바뀐다

각 요구사항에는 trigger, condition, response, 관찰 가능한 실패 경계가 있다.

```text
REQ-001
Given merchant_id M과 client_order_id C를 가진 POST /orders 요청
When 시도가 connect timeout, connection reset, 502, 503, 504로 끝남
Then gateway는 최대 두 번 더 시도할 수 있음
And 모든 시도는 (M, C)에서 파생한 같은 vendor Idempotency-Key를 사용함
And 모든 자동 재시도는 원래 호출 안에 머묾.

REQ-002
Given 벤더가 (M, C)에 대해 주문 O를 커밋함
And gateway가 응답을 관찰하기 전에 응답이 유실됨
When gateway가 같은 호출 안에서 재시도함
Then 호출자는 O를 받음
And 로컬 주문, 벤더 주문, charge가 각각 정확히 하나만 존재함.

REQ-003
Given canonical payload fingerprint P1과 함께 사용된 idempotency key
When 같은 키가 P1 != P2인 fingerprint P2와 함께 제시됨
Then 서비스는 409 IDEMPOTENCY_KEY_REUSED를 반환함
And 추가 vendor POST를 수행하지 않음.

REQ-004
Given 같은 (M, C)와 동일한 canonical payload를 가진 두 동시 요청
When 둘 다 order gateway에 도달함
Then 모든 성공 응답은 같은 order_id를 포함함
And 해당 논리 주문의 vendor order count와 charge count는 각각 하나임.

REQ-005
Given Retry-After D를 가진 429 응답
And 시도별 600 ms 관찰 예산
When D + 600 ms가 남은 2초 end-to-end deadline 안에 들어감
Then gateway는 D 이후 재시도할 수 있음
Otherwise sleep하거나 새 vendor 시도를 시작하지 않고 중단함
And 매핑된 dependency-unavailable 결과를 반환함.
```

호출 간 재실행은 의도적으로 현재 구현 요구사항에서 빠진다. 그 위험의 소유자, 검토 날짜, 선행 증거, 이유는 Deferred Risks에 남아 있으며, 구현은 미래 계약 없이 탐지 가능한 24시간 정책을 만들어 내서는 안 된다.

가장 중요한 검증은 “HTTP client가 두 번 호출되었다”가 아니다. 모호했던 business outcome 자체를 재현한다.

```text
VER-ORDER-COMMIT-DROP
1. 생성한 주문과 charge를 기록하는 stateful fake vendor를 시작한다.
2. canonical payload P와 안정적인 outbound key K로 (M, C)를 보낸다.
3. 첫 호출에서 vendor order O와 charge 하나를 커밋한 뒤 응답을 유실시킨다.
4. gateway가 재시도하게 한다.
5. 모든 시도의 outbound key와 payload, 최종 response order_id R을 수집한다.
6. 모든 시도가 K를 사용했고, R == O이며, vendor_order_count(K) == 1,
   vendor_charge_count(K) == 1, (M, C)의 local order count == 1일 때만 통과한다.
```

실제 client가 시도마다 새 키를 보내더라도 mock이 늘 같은 ID만 돌려주면 통과하는 식으로 이 oracle을 속일 수 없다. outbound 요청과 영속 효과를 함께 관찰하기 때문이다.

## 10. 새로운 구현자는 여전히 구멍을 찾는다

첫 draft를 인터뷰 대화는 보지 못한 새로운 구현자에게 저장소와 함께 제공한다. L0—정적 조사와 독립적인 읽기—에서 네 가지 blocking 질문이 나온다.

1. `client_order_id`는 전역인가, merchant scope인가?
2. 같은 payload란 raw JSON, normalized JSON, 선택된 business field 중 무엇인가?
3. `Retry-After`가 남은 deadline보다 길면 어떻게 되는가?
4. 실제 client가 시도마다 다른 key를 보내도 mock이 하나의 주문만 반환하도록 만들어 테스트가 통과할 수 있는가?

첫 번째는 저장소가 답한다. uniqueness는 `(merchant_id, client_order_id)`이다. 이는 사용자 질문이 아니라 draft의 synthesis loss다. 2번과 3번은 명시적 계약 결정이 필요하고, 4번은 검증을 mock call count에서 실제 outbound 요청과 stateful vendor fake로 다시 묶는다.

프로토콜은 L0부터 L3까지 중 이 사례를 판정할 수 있는 최소 수준을 명시적으로 선택해야 한다. L0만으로 race를 관찰할 수 없으므로 이 사례는 L1, 즉 서로 독립적으로 작성한 두 behavioral stub을 선택한다.

- **Producer A:** database-backed fake가 커밋한 뒤 socket을 닫는다. 시도마다 새 키를 쓰면 영속 row가 두 개 생김을 보여 준다.
- **Producer B:** barrier-based concurrent fake가 두 호출을 교차 실행한다. 다른 payload를 쓴 경우의 conflict가 명시되지 않으면 “같은 키 사용”만으로 충분하지 않음을 보여 준다.

두 producer는 다른 failure mechanism과 causal root를 사용하지만, 여전히 production vendor 자체의 증명은 아닌 surrogate다. 중대한 차이가 발견되면 `origin: probe` gap이 생기고, dry-sweep streak와 checkpoint, 검토된 Build Contract의 readiness가 무효화되어 인터뷰로 돌아간다. 수정 후 제한된 probe가 새 차이를 찾지 못해도 completeness credit은 0이다. “이 범위에서 더 찾지 못했다”는 “다른 실패가 없다”는 뜻이 아니다.

## 11. 대표 인터뷰 trace

중요한 것은 phase 이름이 아니라 매 turn에서 증거가 다음 질문으로 바뀌는 과정이다.

| 단계 | 새 증거 또는 사용자 결정 | LLM의 가설·후보 생성 | 프로토콜 라우팅 | 다음에 보이는 상호작용 |
| ---: | --- | --- | --- | --- |
| 1 | 코드에 변하는 `X-Request-Id`가 있고 fixture는 commit 후 close 가능 | “실패 응답 뒤에 성공한 write가 숨을 수 있다”를 사실이 아니라 applicability question과 falsifier로 만든다. | `G-POST-COMMIT`: score 3, weight 5, question score `156.25`. | retry 설정보다 먼저 post-commit 결과를 묻는다. |
| 2 | 사용자가 주문·charge 하나를 선택 | “같은 HTTP 응답”, “같은 영속 주문”, “나중 reconciliation” 해석이 아직 남는다. | critical answer는 score를 2 아래로 내리기 전에 pressure가 필요하다. | 결과 ID, local/vendor row count, charge count, 금지 결과를 구체적으로 묻는다. |
| 3 | pressure story가 원주문 ID와 각 count 1, changed-payload 거부를 요구 | “같은 논리 요청”에 identity predicate가 필요하다. | repo 근거는 `(merchant_id, client_order_id)`를 권장하고 per-attempt ID를 반증한다. | 논리 키를 구조화된 질문으로 묻는다. |
| 4 | vendor docs와 코드가 retry class, 600 ms와 2 s의 다른 clock을 보여 줌 | `429`와 `Retry-After`가 remaining-budget branch를 만든다. | `G-DEADLINE`은 due critical obligation. 후보 점수는 attempt `40.5`, class `36`. | deadline boundary를 묻고 `t=1.55 s`에서 pressure한다. |
| 5 | hard deadline이 우선이고 full 600 ms budget이 들어가야 함 | attempt count가 이제 timing predicate의 제약을 받는다. | `G-ATTEMPTS`를 별도 score-2/weight-3 질문으로 유지한다. | 최대 횟수를 묻고 3이 목표인지 상한인지 pressure한다. |
| 6 | 3은 상한이며 실제 count는 더 적을 수 있음 | backoff, tuple encoding, telemetry는 critical semantics를 더 바꾸지 않는다. | 이 저위험·독립·evidence-backed default만 batch한다. | 근거와 함께 세 default를 제안한다. |
| 7 | 호출 간 replay에는 현재 없는 store/clock이 필요 | 모델은 24시간 conflict를 상상할 수 있지만 현재 system은 predicate를 증명 못 함 | 사용자가 scope 추가와 명시적 연기 중 선택할 때까지 `G-TTL`을 Draft로 유지한다. | 사용자가 Payments Platform, 2026-08-15 연기를 선택하면 Deferred로 이동한다. |
| 8 | fresh implementer가 scope, payload equality, 큰 `Retry-After`, gameable mock을 발견 | 완전해 보였던 계약에 synthesis loss가 있음을 드러낸다. | 이 사례의 최소 적정 단계로 L1을 선택하고 divergence가 readiness를 무효화한다. | 관련 질문과 verification oracle을 다시 연다. |

이 구조가 persisted state 없는 planner 대화보다 강한 이유는 LLM이 가설과 점수 요인을 제안하더라도, session state가 다음에 처리할 branch, pressure가 필요한 answer, batch할 수 없는 question, readiness를 무효화하는 새 evidence를 결정하기 때문이다.

## 12. 정적 소유권 경계

| 소유자 또는 표면 | 소유하는 책임 | 주장해서는 안 되는 것 |
| --- | --- | --- |
| 인터뷰 runtime | repository-first evidence, ambiguity ledger, due obligation, 질문 routing, pressure, sweep, 최소 역량 L0–L3 probe 결정 | model prior가 사실이라는 주장, scorer가 모든 후보를 찾았다는 주장, neutral probe가 completeness를 증명한다는 주장 |
| `question_score.py` | 제공된 후보 JSON의 결정적 validation, 산술, ordering. 여기서는 `156.25`, `100`, `40.5`, `36` | 후보 completeness, 사람의 factor 판단 정확성, top-ranked 질문을 실제로 물었다는 독립 보장 |
| 검토된 계약 | 안정적인 `REQ`/`VER` ID와 사람이 검토한 behavior digest | 구현 기법이나 검토·연기 범위 밖 behavior |
| 외부 Claude, Codex, CI, 인간 builder | product edit, runtime tool, worktree, permission, 계약이 허용한 구현 선택 | 계약 재작성 권한이나 스스로 specification completeness를 부여할 권한 |
| 반환 evidence와 fresh postmortem | 약속, 실제 change, decision, observable proof 비교와 escaped requirement 등록 | interview history를 고쳐 이전 miss를 지울 권한 |

인터뷰어는 빠진 결정을 조용히 구현할 수 없고, builder는 자신이 평가받을 계약을 조용히 재정의할 수 없다.

## 13. Claude와 Codex: 강한 모델이 할 수 있는 일과 프로토콜이 반드시 하게 만드는 일

비교는 공정해야 한다. Codex CLI는 저장소 조사, 계획, 편집, 도구 실행과 skill/plan surface를 제공한다. [공식 Codex CLI 가이드](https://learn.chatgpt.com/docs/codex/cli)와 [현재 Codex 기능 문서](https://learn.chatgpt.com/docs/features)를 참고하라. Claude Code도 읽기 전용 planning과 Explore → Plan → Implement → Commit 흐름을 지원한다. [Claude Code 권한 모드](https://code.claude.com/docs/en/permission-modes)와 [Claude Code 모범 사례](https://code.claude.com/docs/en/best-practices)를 참고하라.

강한 모델은 어느 환경에서도 이 사례의 모든 질문을 **할 수 있다**. `ultimateinterview`의 장점은 모델 지능이 아니라 **할 수 있다**와 **반드시 해야 한다**의 차이다.

| 강한 Claude/Codex planner가 할 수 있는 일 | `ultimateinterview`가 반드시 해야 하는 일 |
| --- | --- |
| POST retry의 idempotency risk를 기억 | applicability question, falsifier, evidence route가 있는 hypothesis로 기록하고 prior에는 fact credit 0 |
| 질문 전 repo 조사 | repo-answerable 질문을 제거하고 evidence source와 user authority를 분리 보존 |
| duplicate order 질문 | ledger에 들어온 post-commit state를 쉬운 retry/backoff 설정보다 먼저 routing |
| 중요한 답에 follow-up | high-impact gap을 낮추기 전에 pressure, independent evidence, 또는 owner authority 요구 |
| identity, replay, concurrency, observability 언급 | active/deferred sibling track을 persisted state에 유지하고 sweep/locality correction으로 망각 방지 |
| 상세 acceptance criterion 작성 | stable `REQ`/`VER`를 reviewed digest에 묶고 stale/substituted contract 거부 |
| 다른 agent에게 review 요청 | fresh implementer에게 contract만 주고 material divergence를 새 gap으로 취급, readiness 무효화 |
| test 실행과 성공 요약 | exact contract에 bound된 typed executor return/evidence만 수용; executor는 자신에게 completeness를 부여 못 함 |
| failure에서 비공식 학습 | escaped requirement를 stable identity로 분류해 다음 orientation에 반영 |

네이티브 planner도 prompt를 받으면 이런 일을 할 수 있다. 프로토콜은 이를 context compaction, handoff, 서로 다른 runtime 사이에서도 지속적이고 순서가 보장되며 fail-closed가 되게 한다.

## 14. 인터뷰가 제품 실행을 의도적으로 소유하지 않는 이유

한 context가 인터뷰하고, 구현하고, 스펙이 충분했는지까지 판단하면 세 신호가 결합된다.

1. 빠진 요구사항을 코딩 중 조용히 채울 수 있다.
2. 구현 선택을 나중에 스펙의 요구였다고 설명할 수 있다.
3. 실제 behavior를 피하면서 문구만 만족하는 test를 작성할 수 있다.

이 사례에서 실행하는 인터뷰어는 process-local lock을 선택해 unit test를 통과시키면서 두 service replica의 race를 숨길 수 있다. 별도 builder는 작성된 cross-replica behavior를 구현하거나 deviation을 반환해야 한다. 그래야 다음 반사실을 측정할 수 있다.

> 새로운 구현자가 검토된 계약만으로 같은 관찰 가능한 동작을 만들 수 있는가?

Claude, Codex, CI, 인간 팀은 이미 도구, 권한, worktree, sandbox, deployment, runtime recovery를 소유한다. 각 환경을 다시 구현하면 요구사항을 더 찾지 못하면서 adapter treadmill만 만든다.

인터뷰가 소유하는 실행 표면은 두 개뿐이다.

- 한 unresolved semantic question을 측정하는 bounded L0–L3 probe
- 미리 선언되고 allowlist에 든 repo-local verification command를 위한 `safe-auto` evidence capture

`safe-auto`는 product code를 edit하거나 deploy하거나 implementation mechanism을 고르거나 임의 shell command를 실행할 수 없다. 그 밖의 작업은 외부 executor 또는 execution-owning control plane이 맡는다. 규제 attestation, rollback, persistent experiment, production telemetry custody, hard sandbox guarantee에는 그런 control plane이 필요하다. artifact schema만으로 임의 executor를 신뢰할 수 있게 만들 수는 없다.

## 15. 닫힌 순환이 여전히 필요한 이유

빌드 전 discovery는 불확실성이 0임을 증명할 수 없다. 외부 builder는 `execution-return.json`, changed surface, `decisions.jsonl`, REQ/VER outcome, hash-bound evidence를 반환한다. fresh postmortem은 약속, 구현, 증명을 비교한다.

안정적인 키가 중복 주문 row는 막지만 fulfillment event가 두 번 발행된다고 하자. 원계약이 다른 영속 side effect를 놓친 것이다. 기존 category가 없어도 postmortem은 escape를 기록하고 다음 interview의 open-world orientation을 “order row 하나”에서 “외부에서 관찰 가능한 모든 side effect”로 바꾼다.

루프가 중요한 이유는 artifact가 원을 그리기 때문이 아니다. 실행이 interview history를 다시 쓰지 못하게 하면서도 interview의 model을 반증할 수 있기 때문이다.

## 16. 중단과 handoff는 blocker 기준이다

세션은 다음을 모두 만족할 때만 멈춘다.

- score 2 또는 3의 모든 gap이 해결되거나 owner/date와 함께 명시적으로 deferred
- fresh breadth sweep 두 번에서 implementation-changing gap이 없음
- mandatory falsification checkpoint가 현재 model을 확인
- 최소 역량 L0–L3 수준의 probe decision이 해결됨. 이 사례는 L1을 최소 적정 수준으로 선택
- fresh implementer에게 blocking ask가 없음
- gameable criterion이 실제 observable surface에 다시 bind됨
- deterministic implementation gate 통과

handoff 경계는 작다.

- `handoff.md`: 사람이 읽는 합의
- `build-contract.json`: strict digest-bound `BuildContract v1`
- builder는 강제되지 않은 선택을 `decisions.jsonl`에 추가하고 evidence와 `execution-return.json` 반환

이 사례의 `handoff.md`는 `G-TTL` Deferred Risks도 포함한다. 소유자는 Payments Platform, review date는 2026-08-15, prerequisite는 durable store + controllable clock proof다. 이 owner/date 결정이 없으면 `G-TTL`은 active score-3 gap으로 남아 stop을 막는다.

builder는 retry library, lock mechanism, module decomposition, hashing implementation을 고를 수 있다. retry condition, identity scope, duplicate behavior, invocation-only boundary, deferred cross-invocation risk, deadline, verification oracle를 조용히 바꿀 수는 없다.

## 17. 언제 이 overhead를 감수할 가치가 있는가

- 잘못된 가정이 금전, data, permission, compatibility를 훼손할 수 있다.
- 변경이 network, transaction, lifecycle, concurrency, ownership boundary를 가로지른다.
- 저장소가 오래됐거나 분산됐거나 낯설다.
- 구현이 다른 사람, session, model, runtime으로 넘어간다.
- 얕은 mock이나 self-authored test로 acceptance를 속일 수 있다.
- context compaction과 handoff 뒤에도 evidence와 decision이 살아남아야 한다.

오타, reversible local refactor, 기계적 dependency bump, authoritative test suite가 완전히 제약한 변경에는 일반 planner나 minimal interview가 낫다. 이 방법은 잘못된 전제를 그대로 둘 비용이 그 전제를 드러낼 비용보다 클 때 가치가 있다.

핵심 교훈은 “항상 idempotency를 물어라”가 아니다. 그러면 또 하나의 고정 checklist가 된다.

> LLM으로 위험한 가능성을 생성하고, 중요한 가능성을 local evidence와 decision authority에 통과시키며, 결과가 가장 큰 질문을 먼저 묻고, fresh builder나 runtime result가 인터뷰가 틀렸음을 증명할 수 있도록 충분히 분리하라.
