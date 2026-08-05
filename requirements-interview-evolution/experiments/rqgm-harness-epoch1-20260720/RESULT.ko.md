# RQGM 기반 하니스 자기진화 1세대 결과

## 결론

하니스에 자동 evaluator-anchor, evaluator challenger, epoch 단위 고정, 엄격 승격, evaluator identity 검증, 선택적 무효화 경계를 추가했다. Evaluator challenger는 별도 validation anchor에서 incumbent의 3/4보다 높은 4/4를 기록해 epoch 1로 승격됐다.

승격된 evaluator로 인터뷰 v0 스킬 한 세대를 실행했지만, skill candidate 3개는 모두 development 사례별 비회귀 gate에서 탈락했다. validation과 holdout은 열리지 않았고 deployed skill은 v0 그대로다.

## 자동 evaluator anchor

- training source: `django__django-15268`, `matplotlib__matplotlib-26466`
- training anchors: 18
- validation source: `psf__requests-5414`
- validation anchors: 4
- skill 실험의 holdout source 사용: 0
- A/B 위치: source와 item ID의 digest로 결정적 무작위화
- 라벨 생성 모델 호출: 0
- confidence: 현재 로컬의 별도 source에는 material decision이 없어 모두 B

## Evaluator 진화

| evaluator | validation anchor |
|---|---:|
| incumbent | 3/4 |
| challenger | 4/4 |

- promotion rule: `challenger_correct > incumbent_correct`
- promoted: true
- epoch: 1
- selected evaluator SHA-256: `092d710631296b3eafbae335cbc557f498ae9c8664fe16bc31b5e66112958c40`
- generation run manifests: 32
- generation 내 evaluator identity 수: 1
- 독립 재계산: verified

## Skill development 결과

| 지표 | baseline | candidate 1 | candidate 2 | candidate 3 |
|---|---:|---:|---:|---:|
| implementation ready | 8 | 7 | 8 | 8 |
| invented requirements | 20 | 34 | 21 | 2 |
| compatibility regressions | 0 | 1 | 0 | 0 |
| implementation decisions | 1 | 2 | 1 | 4 |
| owner recall | 1.0 | 0.88625 | 1.0 | 1.0 |
| repository fidelity | 0.93625 | 0.88125 | 0.93875 | 0.9875 |

Candidate 3은 invented requirements를 20에서 2로 줄이고 repository fidelity를 높여 합계상 가장 강했다. 하지만 `astropy__astropy-7671`과 `sympy__sympy-17318`에서 회귀했고 implementation decision도 1에서 4로 늘어 사례별 비회귀 조건을 만족하지 못했다.

- candidate 1: 1개 사례 개선, 5개 회귀
- candidate 2: 4개 사례 개선, 4개 회귀
- candidate 3: 6개 사례 개선, 2개 회귀
- eligible candidates: 0
- validation opened: false
- holdout opened: false
- promoted skill: false

## 평가

이번 결과는 evaluator와 skill을 함께 진화시키는 메커니즘이 실제로 작동하고 한 epoch 동안 평가 기준이 고정됐음을 보여준다. 또한 개선 폭이 큰 candidate 3을 유망 부모로 보존할 가치가 있다는 신호를 다시 확인했다.

그러나 evaluator 성능 향상이 일반화됐다고 결론내릴 수는 없다. validation anchor가 한 source의 B급 4쌍뿐이고, anchor repository family가 skill corpus의 일부 family와 겹친다. 새 evaluator를 사용한 실행은 인터뷰·구현도 새로 생성했으므로 이전 evaluator와의 지표 차이를 evaluator 효과만으로 인과 귀속할 수도 없다. 다음 evaluator epoch 전에는 repository-family가 완전히 분리된 A/B anchor source를 더 확보해야 한다.

## 검증

- evaluator epoch verifier: `verified: true`
- skill development rejection verifier: `verified: true`
- 전체 테스트: `103 passed`
- compileall: 통과
- diff check: 통과

참고한 설계 원칙: [The Red Queen Gödel Machine](https://arxiv.org/abs/2606.26294)
