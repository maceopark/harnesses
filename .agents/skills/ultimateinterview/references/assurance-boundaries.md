# Assurance boundaries

Read during ENDGAME when a v2 assurance result is requested or reported.

- `abi` does not imply property observation, adequacy, stakeholder acceptance, independent verification, authentic provenance, or external freshness.
- `trace` does not imply a property observation or semantic completeness.
- `property` does not imply authenticated execution, authentic provenance, adequacy, or stakeholder acceptance.
- `adequacy` does not imply property observation, stakeholder acceptance, semantic completeness, or factual truth.
- `stakeholder` does not imply factual truth, property observation, or adequate coverage.

Treat every verdict as a bounded result for the exact artifacts, policy, and observation described by its record. A v0/v1 structural result does not become a v2 verdict. A v2 property result is bounded evidence, not a general assurance claim.

## Release-audit operator invocation

Run F1 against the candidate branch diff from the skill directory. `ROOT` is the
workspace root, and `PATHS` is the file populated from the candidate's
`BASE...HEAD` changed-path list.

```bash
BASE="$(git -C "$ROOT" merge-base HEAD origin/master)"
git -C "$ROOT" diff --name-only "$BASE"...HEAD > "$PATHS"
cd "$ROOT/.agents/skills/ultimateinterview"
uv run --python 3.13 --with pydantic --with pytest --with rich --with typer scripts/release_audit.py \
  --workspace-root "$ROOT" \
  --changed-paths "$PATHS" \
  --evidence-dir "$ROOT/.omo/evidence" \
  --plan "$ROOT/.omo/plans/ultimateinterview-v2-assurance-plane.md"
```

`--evidence-dir` is an explicit generated workspace input, not an assumption
that `.omo/evidence` is Git-tracked. The release owner must provide the required
Task 1--13 receipts at that path before F1 can approve the mapped diff.

The [release-audit map](../scripts/release_audit_map.json) intentionally assigns
`references/orientation.md` to C2 because that reference routes lifecycle
initialization; it is not an assurance-boundary (C1) document merely because it
mentions v2.
