# `ui-native-77b0327-r4`

This directory vendors the frozen native Ultimateinterview closure approved at workspace commit `77b0327fe2549baebbe6ca4d287d98bc1c56296e`. The copy lives under `frozen/`; it contains the native scripts, skill instructions, reference documents, postmortem ABI, and v1 structural fixture seed required by this snapshot.

`protocol-source-manifest.json` binds every copied file by its original workspace-relative `source_path` and raw-byte SHA-256. `frozen_source_root` selects the immutable copy. Records are sorted by `source_path`; the tree digest is SHA-256 over sorted UTF-8 lines `<source_path>\t<sha256>\n`.

Before any native invocation, call `driftbench.native_snapshot.validate_native_snapshot` on this directory. It rejects substituted paths, symlinks, missing or extra source files, byte-digest mismatch, tree-digest mismatch, and a direct local-import closure that differs from the recorded closure. Validation is standalone: it reads only this directory and does not consult `.agents` or another workspace project.

A source change requires a new snapshot ID and manifest digest. It must not be silently accepted under this snapshot ID.

## Fixtures

- `fixtures/native-v1-structural-valid.json` points to the native v1-ready fixture and expects the applicable v1 structural/readiness gate to pass. It makes no assurance-v2, creditable-receipt, property-observation, or completeness claim.
- `fixtures/v2-noncreditable-expected-fail.json` requires a valid current simulated receipt import and records the native final-gate failure: `creditable imported execution receipts are required`. It is non-scored and not scorecard eligible; observing that failure is not assurance success.
- `fixtures/binding-failures.json` enumerates coordinate, return, receipt, and decision-log mismatch cases. Every case must be rejected before receipt import or the final v2 gate is invoked.
