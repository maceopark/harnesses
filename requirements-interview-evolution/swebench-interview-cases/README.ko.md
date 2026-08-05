# SWE-bench 인터뷰 스킬 진화 파일럿

이 프로젝트는 고정된 SWE-bench Verified 사례를 이용해 `clarify-requirements` v5의 인터뷰 품질을 측정하고, 개발 사례에서 반복된 실패만으로 후보 스킬을 만든 뒤 검증·홀드아웃 게이트를 통과한 경우에만 v6로 승격한다.

구현 기준은 `../artifacts/swebench-interview-cases/build-contract.json`이다. 데이터셋 revision, parquet SHA-256, 공식 harness revision, 역할 모델은 코드에 고정돼 있으며 이동하는 revision이나 모델 fallback은 허용하지 않는다.

## Co-evolving evaluator epoch

하니스는 인터뷰 스킬과 별도로 버전된 evaluator rubric을 진화시킬 수 있다. 자동 anchor의 라벨은 모델이 만들지 않고 승인된 sealed source의 material decision, hindsight observation, implementation incidental provenance에서 결정적으로 만든다. 한 source case의 파생 anchor는 분리하지 않으며 validation/holdout source는 anchor 생성에서 제외한다.

`build-evaluator-anchors`로 development source의 전체 anchor corpus를 만들고 `split-evaluator-anchors`가 repository-family 단위로 training/validation을 결정론적으로 분할해 split digest를 봉인한다. `evolve-evaluator --split-manifest`와 `verify-evaluator-epoch --training-anchors --split-manifest`를 함께 사용하면 실행과 검증 모두에서 이 결합을 확인한다. Challenger는 training anchor만 보고 rubric을 수정하며, incumbent와 challenger는 별도 validation anchor의 무작위화된 A/B 쌍을 블라인드 평가한다. Challenger의 오류 anchor 집합이 incumbent 오류의 엄격한 부분집합이고 confidence-A 및 family별 회귀가 없을 때만 다음 epoch로 승격한다. 동률이면 incumbent를 유지한다.

`execute-study --evaluator-spec <selected.json>`은 evaluator를 세대 시작 시 동결하고 모든 run manifest에 같은 SHA-256을 기록한다. `verify-evaluator-epoch`은 저장된 블라인드 예측에서 승격 결정을 다시 계산하고 한 세대에 evaluator identity가 하나뿐인지 확인한다.

Evaluator 교체 시 contract, transcript, repository evidence, blind review, adjudication, implementation은 원본 증거로 보존한다. `selective_invalidation_paths`는 현재 evaluator rubric에 직접 의존하는 judge와 그에 의존하는 mutation·selection·decision artifact만 무효화 대상으로 식별한다. `replay-evaluator-2x2`는 기록된 동일 judge payload를 incumbent와 challenger로 다시 평가해 evaluator 효과와 skill 효과를 분리한다. 기록 payload의 public·sealed 필드를 원래 run manifest digest에 다시 결합하며, 완료 replay 재사용 때도 raw artifact와 judge call digest를 재검증한다. `snapshot-recorded-corpus`는 corpus rotation 이후에도 기록된 public-case digest를 재현한다. 데이터 분리, provenance, holdout 봉인과 독립 verifier는 진화 대상이 아니다.

실패한 skill candidate를 배포본으로 취급하지 않으면서 후속 수정을 만들려면 `execute-study`에 `--mutation-parent-skill`과 정확히 8개의 `--mutation-signal-run`을 함께 전달한다. Mutation은 해당 lineage의 실패만 사용하지만 새 후보의 승격 gate는 계속 배포된 baseline과 사례별로 비교한다.

모든 구현자 자율 선택은 `decision.jsonl`에 기록한다. 구현 후 독립 materiality review가 사용자 초기 결정을 바꾸거나, 계약의 권한 경계를 넘거나, 보안·안전·데이터 손실·비가역 마이그레이션·상당한 비용·광범위 호환성 위험을 만드는 결정만 material로 분류한다. Raw `implementation_decisions`는 진단 지표이며 gate나 mutation signal이 아니다. `material_implementation_decisions`만 결함으로 취급한다.

`recompute-strategy-outcomes`는 이전 세대의 후보별 개선·회귀를 `material_implementation_decisions`, `approved_finding__invention`, `approved_finding__omission` 같은 failure class 변화량으로 다시 봉인한다. 다음 strategist에는 raw alias나 case별 delta를 노출하지 않고 class별 개선·회귀 횟수만 전달한다. 따라서 invented requirement 감소가 material decision이나 승인된 finding 증가로 이동하는 상충을 직접 피할 수 있다.

`build-evaluator-anchors --include-material-omission-confidence-a`는 owner answer가 빠진 불완전 clause와, 승인된 issue-time material decision이 전혀 없는 사례에서 issue-time evidence 원문과 implementation incidental 원문을 직접 비교하는 confidence-A boundary anchor를 추가한다. Blind pair에는 `required`, `incidental`, `no additional clause` 같은 정답 암시 wrapper를 넣지 않는다.

`run-coevolution-epoch --config <config.json> --output-root <epoch-dir>`는 anchor 생성·분리, evaluator 진화, 2×2 replay, 선택 evaluator의 rejudged run view, skill 세대, generation verifier, evaluator verifier, promotion commit을 하나로 묶는다. 입력은 `epoch-input.json`에 digest로 봉인되고 각 단계는 immutable `attempt-NNN/receipt.json`을 남긴다. 중단되거나 변조된 attempt는 삭제하지 않고 새 attempt로 재개한다. 두 verifier가 모두 읽기 전용으로 통과한 뒤 별도 promotion-commit stage가 epoch-local shadow를 변경할 수 있으며, 마지막에만 `epoch-manifest.json`을 원자적으로 기록한다. 실제 배포 파일의 교체는 이 manifest 검증 이후 별도 작업이다.

## 실행 순서

1. `download`로 고정 parquet를 내려받고 SHA-256을 검증한다.
2. `prepare-pilot`으로 개발 8개, 검증 3개, 홀드아웃 4개와 동-stratum 대체열을 동결한다.
3. `checkout-repositories`로 각 사례의 base commit을 sealed cache에 준비한다.
4. `build-corpus`가 모든 사례의 baseline-empty/gold Docker 무결성을 확인한다. 각 실행 후 environment와 instance 이미지는 제거하고 공통 base 이미지만 유지한다. 실패한 사례는 같은 stratum에서만 교체한다.
5. 독립된 두 `gpt-5.6-sol` 프로세스가 파생된 material decision을 모두 승인한 사례만 corpus에 등록한다.
6. `native-evolution/run_evolution.py --imported-case`로 개발 8개를 frozen v5에 실행한다. 사례별 Mutator는 호출하지 않는다.
7. `batch-mutate`의 meta-strategist가 오직 개발 실행의 decision·invented requirement·compatibility regression과 이전 세대의 development-only 전략 성적을 검토한다. 원시 사례 식별자는 이전 성적에서 제거하고 개선 사례 수·회귀 사례 수·변경량만 전달한다. 이어서 `REPLACE`, `DELETE`, `ADD` 전략을 하나씩 만들고 각 전략이 baseline의 정확히 한 위치만 제한 편집해 candidate 3개를 생성한다. validation과 holdout 결과는 전략 또는 candidate 생성 입력에 넣지 않는다.
8. 후보들을 개발 8개에 최대 병렬도로 실행한다. 모든 사례에서 v5 대비 결함이 늘지 않고 적어도 하나가 엄격히 개선된 후보만 남긴 뒤, 고정 순위와 생성 순서로 후보 하나를 선택한다. 각 전략의 개선 사례, 회귀 사례, 변경량, gate 통과 여부는 `strategy-outcomes.json`에 기록해 다음 세대의 전략 선택 입력으로 사용할 수 있다.
9. 선택된 후보 하나만 검증 사례 3개의 absolute-zero gate에 넣는다. 세 사례가 모두 implementation-ready이고 contamination, leakage, invented requirement, compatibility regression, implementation decision, 승인된 material blocker가 전부 0일 때만 홀드아웃을 연다. 탈락하면 해당 세대를 종료한다.
10. 검증을 통과한 후보만 홀드아웃 4개에 실행한다. `finalize-study`는 승격 전 결정을 봉인하고 파일을 변경하지 않는다.
11. `verify-completion`이 corpus, 독립 review, 공식 harness, 모든 run digest와 지표를 다시 계산해 통과한 뒤에만 v6와 배포본을 byte-identical하게 만든다.

원문 issue, patch, test patch, 저장소 checkout, 역할 prompt와 transcript, holdout 내부 식별자는 `SWEBENCH_INTERVIEW_CACHE` 아래에만 둔다. 공개 selection의 홀드아웃 SHA-256 alias는 단순 가명화이며 알려진 500개 ID에 대한 열거 공격을 막지 못한다.

## 현재 실행 제약

Docker 용량은 고정된 사전 상한으로 차단하지 않는다. 공식 harness는 `cache_level=base`로 실행해 baseline과 gold를 포함한 매 호출 뒤 environment와 instance 이미지를 정리한다. 이미지 다운로드와 재빌드는 허용하며, 실제 Docker 또는 파일시스템 용량 부족은 해당 실행 실패로 기록한다. Docker 실행·인터뷰·validation·holdout 결과가 생성되기 전에는 v6 승격을 주장하지 않는다.
