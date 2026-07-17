# Owner World Model: Feature Flag Setting

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Flags are scoped by environment; `dev` and `prod` currently exist.
- Existing flag values are booleans.
- Top-level metadata, including owner information, is not part of the mutation target.

## Vocabulary and decision posture

- Accepted VALUE spellings are exactly `true` and `false`.
- A known environment may receive a new flag name.
- Creating an environment implicitly is not authorized.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"feature-flags","items":[{"item_id":"strict-boolean","owner_statement":"VALUE accepts exactly true or false and is persisted as a JSON boolean, not a string.","materiality":"critical","forbidden_outcomes":["Truthy string coercion","Persisting a string value"]},{"item_id":"environment-boundary","owner_statement":"An unknown environment fails without changing flags.json; a known environment may add or update the named flag.","materiality":"critical","forbidden_outcomes":["Implicit environment creation"]},{"item_id":"preserve-other-state","owner_statement":"Setting one flag preserves every other environment, flag, and top-level metadata field.","materiality":"material","forbidden_outcomes":["Dropping metadata","Cross-environment mutation"]}],"probes":[]}
```
