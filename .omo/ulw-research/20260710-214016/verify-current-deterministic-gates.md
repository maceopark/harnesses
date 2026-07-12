# Verification — Current deterministic gates

Observer: `/root/deterministic_gates` · Valid at: live working tree, 2026-07-10

## Environment and baseline

- Python 3.14.6; uv 0.10.6; pytest 9.1.1; pydantic 2.13.4; typer 0.26.8.
- `uv run --python 3.14 --with pydantic>=2.7 --with pytest>=8.0 --with rich>=13.7 --with typer>=0.12 pytest -q scripts/test_*.py` → `666 passed in 20.51s`.
- Unpinned uv selected Python 3.11.14 and failed collection on PEP 695 aliases; runtime pinning is required.

## Executed adversarial verdicts

- REFUTED actual independence: same actor/warrant can self-declare groups `a` and `b`; year-2000 observations declared `current` can settle weight-5.
- REFUTED actor/channel provenance binding: `channel=from-code`, `source_actor=user` is accepted and eligible.
- REFUTED global/time freshness: direct coherent ledger mutation with unchanged revision can leave orientation/review fresh and implementation ready.
- PARTIAL handoff semantics: unrelated citation of an entry ID satisfies coverage while enumerated behavior is absent.
- REFUTED verification execution: a command targeting a nonexistent test file passes syntax/head policy because the gate does not run it.
- PARTIAL predicate lint: global/row regexes miss cross-field/category bindings and can false-positive incidental words; standalone mode is advisory.
- REFUTED blanket fail-closed claim: a fixture lacking `questions.json`, `transcript.md`, and decisions log passed the composite gate.

## Verdict

Current helpers provide a strong structural floor but not authenticated provenance, causal independence, trusted freshness, semantic fidelity, or executed-verification proof.

## Exact adversarial reproduction

Working directory: `/Users/jpark/IdeaProjects/harnesses/.agents/skills/ultimateinterview`.

Cases 1-5:

```bash
uv run --python 3.14 --with 'pydantic>=2.7' --with 'typer>=0.12' --with 'rich>=13.7' python - <<'PY'
import json
from datetime import datetime, timezone
from scripts.claim_evidence import ClaimEvidence, eligible_independence_groups
from scripts.handoff_coverage import id_is_cited
from scripts.verification_lint import command_head_status

def rec(i, group, *, year=2026, channel='from-user', actor='user'):
    return ClaimEvidence.model_validate_json(json.dumps({
      'id': i, 'channel': channel, 'claim_kind':'observed-fact',
      'source_actor':actor, 'provenance_mode':'firsthand',
      'independence_group':group,
      'observed_at':datetime(year,1,1,tzinfo=timezone.utc).isoformat(),
      'freshness':'current', 'warrant':'self-declared',
      'epistemic_authority':'establishes'
    }))

print('CASE1_same_actor_two_groups=', sorted(eligible_independence_groups((rec('a','g1'), rec('b','g2')))))
print('CASE2_year_2000_current_eligible=', sorted(eligible_independence_groups((rec('old','old',year=2000),))))
mismatch = rec('m','m',channel='from-code',actor='user')
print('CASE3_channel_actor_mismatch_accepted=', mismatch.channel.value, mismatch.source_actor.value)
part1 = '| Verification |\n|---|\n| `uv run pytest does-not-exist.py` |\n'
print('CASE4_nonexistent_target_head_only=', command_head_status(part1))
print('CASE5_id_only_semantic_narrowing_passes=', id_is_cited('g14','REQ g14: corrupt only'))
PY
```

Verbatim output, exit 0:

```text
CASE1_same_actor_two_groups= ['g1', 'g2']
CASE2_year_2000_current_eligible= ['old']
CASE3_channel_actor_mismatch_accepted= from-code user
CASE4_nonexistent_target_head_only= {'uv': True}
CASE5_id_only_semantic_narrowing_passes= True
```

Case 6:

```bash
tmp=$(mktemp -d)
cp scripts/regression_fixtures/ready-minimal/{ledger.json,protocol.json,handoff.md} "$tmp"/
printf 'CASE6_fixture_files_before_gate=\n'
find "$tmp" -maxdepth 1 -type f -exec basename {} \; | sort
uv run --python 3.14 --with 'pydantic>=2.7' --with 'rich>=13.7' --with 'typer>=0.12' scripts/session_status.py "$tmp" --gate --format json
rc=$?
rm -rf "$tmp"
exit $rc
```

Verbatim output, exit 0 (the temporary directory was removed):

```text
CASE6_fixture_files_before_gate=
handoff.md
ledger.json
protocol.json
{
  "implementation_gate": {
    "failures": [],
    "implementation_ready": true
  },
  "interview_converged": true,
  "ledger": {
    "active_count": 1,
    "ambiguity_percent": 0.0,
    "blockers": [],
    "contested": [],
    "deferred_count": 0,
    "denominator": 6,
    "display_percent": "0%",
    "handoff_ready": true,
    "residual": 0,
    "top_drivers": [],
    "triangulation_violations": []
  },
  "protocol": {
    "depth": "minimal",
    "handoff_blockers": [],
    "interactions_used": 3,
    "interview_obligations": [
      "question budget exhausted: stop ordinary questioning; ask the user to defer remaining gaps or explicitly extend the budget"
    ],
    "protocol_ready": true,
    "question_budget": 3
  }
}
```
