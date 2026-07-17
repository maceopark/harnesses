# Owner World Model: Configuration Merge

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- `config.json` is the active base configuration.
- A named overlay is expected to be resolved from repository-local configuration data.
- Configuration can contain nested objects; unrelated keys must survive a merge.

## Vocabulary and decision posture

- “Merge” means recursive object merge; overlay scalar values replace base values at the same path.
- Arrays, when encountered, are replaced as values rather than concatenated without an explicit product rule.
- A missing or malformed named overlay fails atomically.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"config-merge","items":[{"item_id":"recursive-object-merge","owner_statement":"Merge nested objects recursively while preserving base keys absent from the named overlay; overlay scalar or array values replace values at the same path.","materiality":"critical","forbidden_outcomes":["Replacing the entire base object","Silently concatenating arrays"]},{"item_id":"missing-overlay-no-write","owner_statement":"A missing named overlay fails without changing config.json.","materiality":"critical","forbidden_outcomes":["Treating a missing overlay as empty success"]},{"item_id":"malformed-overlay-atomic","owner_statement":"A malformed or non-object overlay fails atomically and leaves the active configuration unchanged.","materiality":"material","forbidden_outcomes":["Partially persisted merge"]}],"probes":[]}
```
