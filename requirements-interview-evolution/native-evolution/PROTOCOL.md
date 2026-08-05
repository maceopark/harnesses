# 네이티브 서브에이전트 진화 프로토콜

이 프로토콜은 Orca 없이 동작한다. 각 역할은 격리된 새 임시 디렉터리에서 별도의 `codex exec --ephemeral` 프로세스로 실행된다. 스킬 본문과 역할 프롬프트, JSON 필드 같은 기계 인터페이스는 영어를 유지하고, 운영 문서는 한국어를 기본으로 한다.

## 정보 경계

| 역할 | 허용 입력 | 금지 입력 |
|---|---|---|
| Failure-Lens Proposer | 일반 seed 범주, 동결된 인계 목적 | candidate skill, 다른 도구, 이전 점수, mutation, 원하는 결과 |
| Lens Auditor / Deduplicator | 제안된 lens, 닫힌 승인 규칙 | candidate skill, 사례, 점수, mutation |
| Lens-Conditioned Case Designer | 동결된 lens, context mode, repository mode의 감사된 evidence | candidate skill, Judge 출력, mutation, 다른 partition의 사례 |
| Repository Discovery | 공개 repository 요청, repository 파일 | candidate skill, private owner oracle, lens 평가 결과 |
| Evidence Auditor | 봉인된 discovery, repository 파일 | candidate skill, private owner oracle, 원하는 결과 |
| Owner Oracle Designer | 공개 요청, 감사된 evidence, 객관적 실패 신호 | candidate skill, transcript, Judge 출력 |
| Interviewer | candidate skill, 공개 요청, transcript, 감사된 evidence | private oracle, Judge 출력 |
| Owner | private oracle, 현재 질문, transcript | candidate skill, Judge 출력 |
| Adversarial Reviewer | 공개 요청, 감사된 evidence, transcript, contract, 동결된 lens | private oracle, candidate 계보, 원하는 finding |
| Judge | private oracle, 완료된 transcript와 contract, 감사된 evidence | candidate 계보, 원하는 승자 |
| Adjudicator | blind finding, 정확히 인용된 산출물, 동결된 lens, private oracle | candidate skill, mutation, 선호하는 수정안 |
| Mutator | candidate skill, transcript, Judge 실패 요약, 승인된 finding | private oracle, raw blind finding, 거부된 finding, holdout 사례 |

coordinator는 위 allowlist에 해당하는 입력만 역할별 JSON payload로 전달한다. 어떤 프로세스에도 다른 역할의 private 작업 디렉터리 경로를 주지 않는다.

이 구조는 논리적 context 격리이며 적대적 프로세스를 막는 OS 수준 read-deny 경계가 아니다. `codex exec --sandbox read-only`는 쓰기를 차단하지만 로컬 Codex sandbox 구현에 따라 더 넓은 host 읽기를 허용할 수 있다. 평가 무결성은 새 임시 디렉터리, 최소 prompt, 경로 비공개, 산출물 검사, 비적대적 역할 지시에 의존한다. 의도적으로 경계를 탐색하는 역할까지 막아야 한다면 container 등 별도의 OS 격리를 사용한다.

## 한 번의 development 실행

1. Failure-Lens Proposer가 일반 seed에서 해결책 중립적이고 외부에서 관찰 가능한 실패 lens 3~5개를 제안한다.
2. Lens Auditor가 모든 lens의 관찰 가능성, 중요성, 해결책 중립성, 중복 여부를 명시적으로 평가한다. 모든 제안을 승인 또는 거부하고 중복은 대표 ID에 연결한다. coordinator는 승인된 lens를 `lens-set.json`으로 동결하고 digest를 기록한 뒤에만 사례 생성을 시작한다.
3. Repository mode는 공개 요청을 대상으로 Discovery와 Evidence Auditor를 실행한다. Greenfield mode에는 repository evidence 단계가 없다.
4. Lens-Conditioned Case Designer는 candidate를 보지 않고 객관적으로 판정 가능한 사례를 만든다. Repository mode에서는 공개 요청을 byte-for-byte로 보존하고 oracle을 만들지 않는다. 이후 Owner Oracle Designer가 repository에서 알 수 없는 잠재 owner 결정만 만든다. Greenfield mode에서는 Case Designer가 oracle을 함께 만든다.
5. 새 Interviewer 프로세스가 질문 하나를 만들거나 contract로 종료한다.
6. 새 Owner 프로세스가 oracle에 따라 현재 질문에만 답한다. material decision이 남고 진전이 있는 동안 5~6을 반복한다.
7. Blind Adversarial Reviewer가 공개 인계 자료만 보고 blocker 후보를 제시한다. 모든 finding은 contract, transcript 또는 evidence의 정확한 JSON pointer와 정확한 전체 값을 인용해야 한다.
8. 새 Judge가 transcript와 contract를 평가하고, 별도의 oracle-aware Adjudicator가 모든 blind finding을 독립 판정한다. 단순 선호, 근거 부족, lens 불일치, oracle 충돌은 거부한다.
9. Development mode에서만 새 Mutator가 skill, transcript, Judge 실패 요약과 승인된 finding만 받아 가장 작은 일반화 수정을 작성한다.

각 역할은 별도의 ephemeral 프로세스다. 일반 지식은 `가능한 실패 → 관찰 가능한 검사 → 실제 finding → 독립 판정 → 최소 mutation` 순서로만 skill 개선에 도달한다. 관찰되지 않은 좋은 관행을 곧바로 skill에 복사하지 않는다.

## 닫힌 schema와 fail-closed 검사

모든 역할 출력은 `additionalProperties: false`인 닫힌 JSON schema를 사용한다. Codex transport의 schema 강제에 더해 coordinator가 같은 schema를 재검증한다. 따라서 custom backend, malformed JSON, 누락 필드, 추가 필드, 잘못된 enum·범위도 run을 무효화한다.

Lens Auditor는 모든 제안에 다음 평가를 남긴다.

- `observable`
- `material`
- `solution_neutral`
- `duplicate_of`

승인된 lens는 앞의 세 값이 모두 `true`이고 `duplicate_of`가 `null`이어야 한다. 거부된 lens에는 적어도 하나의 명시적인 거부 근거가 있어야 한다.

Adversarial finding은 알려진 lens를 가리켜야 하고, 인용 pointer가 실제 산출물에 존재하며 `quoted_text`가 그 위치의 전체 값과 정확히 같아야 한다. Adjudicator는 모든 finding을 정확히 한 번 판정해야 한다. 승인 여부가 evidence support, lens match, materiality, oracle conflict 필드와 모순되면 run을 중단한다.

## 증거와 완료 무결성

각 run directory는 실제 역할 prompt와 digest, 입력, raw structured 출력, 동결된 lens set, lens-conditioned case, transcript, blind review, adjudication, evaluation, candidate와 manifest를 보존한다. `calls/NNN-role.json`에는 `prompt`, `prompt_sha256`, `input`, `output`이 들어간다.

registry를 `completed`로 바꾸기 전에 coordinator가 다음을 다시 계산한다.

- lens set의 self digest와 manifest/case identity의 lens digest 일치
- lens case, public case, evidence pack, owner oracle, transcript, evaluation, adversarial review, adjudication digest
- 모든 call prompt의 digest와 call count
- development candidate digest
- holdout에서 candidate와 mutation이 존재하지 않음

어느 하나라도 다르면 registry는 완료 처리되지 않는다. 역할 timeout, malformed output, 정보 경계 위반, 미처리 lens/finding/conflict, 잘못된 인용, forced close의 거짓 ready 주장도 run을 무효화한다. CLI 실행 실패는 `failure.json`으로 보존한다.

Development 결과만 mutation에 사용할 수 있다. Holdout mode는 구조적으로 Mutator를 호출하지 않는다. 공유 study registry는 seed, public request, frozen lens set, lens-conditioned case, full case digest를 기록하며, development와 holdout 사이에서 어느 identity 하나라도 겹치면 양방향으로 fail-closed한다. 예약과 완료는 POSIX file lock 아래 수행한다. 실패한 예약은 남겨 명시적인 검토 없이는 재사용하지 않는다. 운영자가 registry를 삭제하거나 산출물을 수동 복사할 수 있으므로 이것 역시 filesystem 보안 경계는 아니다.

## Repository ground truth

Repository mode에서는 인터뷰 전에 두 read-only 역할을 실행한다.

1. Discovery가 모든 사실에 repository-relative 경로와 정확한 line bounds를 인용한다.
2. Evidence Auditor가 해당 파일을 다시 열어 직접 지지되는 사실만 승인하고 모든 fact와 conflict를 처리한다.

coordinator는 인용된 전체 text, text digest, 파일 digest, Git HEAD/status digest를 봉인한다. 감사된 evidence pack만 Interviewer에 전달한다. repository에서 발견할 수 없는 제품 선택은 별도 private Owner oracle에 둔다.

## 적응형 종료

Interviewer는 매 turn 현재 open material decisions를 보고한다. 정상 완료는 contract를 반환했을 때만 가능하며, implementation-ready contract에는 open material decision이 없어야 한다. 같은 open-decision 집합과 같은 질문이 반복되면 stagnation으로 종료한다. 기본 실행에는 turn ceiling이 없다. `--safety-max-turns N`을 명시한 경우에만 프로세스 장애 대응용 비상 runaway guard가 생기며, 이를 인터뷰 예산이나 정상 종료 목표로 사용하지 않는다. Stagnation 또는 명시된 safety ceiling에 도달하면 확인된 evidence를 보존하는 non-ready contract로 강제 종료한다.

## 실행

이 프로젝트의 Python 명령은 `uv run`을 사용한다.

Development:

```bash
uv run python native-evolution/run_evolution.py \
  --mode development \
  --seed "a compact ambiguous software task" \
  --skill clarify-requirements/SKILL.md \
  --run-dir native-evolution/runs/dev-001 \
  --study-registry native-evolution/runs/study-registry.json
```

Holdout:

```bash
uv run python native-evolution/run_evolution.py \
  --mode holdout \
  --seed "a distinct task not used during development" \
  --skill native-evolution/runs/dev-001/candidate-SKILL.md \
  --run-dir native-evolution/runs/holdout-001 \
  --study-registry native-evolution/runs/study-registry.json
```

Repository mode:

```bash
uv run python native-evolution/run_evolution.py \
  --context repository \
  --repo /absolute/path/to/repository \
  --mode development \
  --seed "the requested brownfield change" \
  --skill clarify-requirements/SKILL.md \
  --run-dir native-evolution/runs/repo-dev-001 \
  --study-registry native-evolution/runs/study-registry.json
```

각 호출은 ephemeral, read-only, fresh temporary directory에서 실행되고 user configuration을 무시한다. Discovery와 Evidence Auditor만 `--add-dir`로 repository 경로를 받는다. 인증은 로컬 Codex 설치를 사용한다. `--model`로 모델을 고정하고 `--timeout`으로 역할별 제한 시간을 바꿀 수 있다.

## 승격 규칙

`candidate-SKILL.md`는 자동으로 `clarify-requirements/SKILL.md`나 v5로 승격하지 않는다. 관찰된 development 실패를 실제로 일반화한 candidate만 별개의 holdout에 투입한다. Holdout의 Judge와 Adjudicator 결과로 일반화 여부를 판정하고, 실패한 holdout도 `failure.json` 또는 non-ready contract와 manifest로 그대로 보존한다.
