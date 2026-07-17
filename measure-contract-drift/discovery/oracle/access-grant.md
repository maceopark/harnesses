# Owner World Model: Access Grant

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Users and their current roles are stored in `access.json`.
- Only `reader`, `editor`, and `admin` are supported roles.
- Granting access is security-sensitive; an invalid user or role must not mutate state.

## Vocabulary and decision posture

- “Grant” adds a role; it does not replace existing roles.
- Repeating an already-effective grant is a successful no-op.
- The owner prioritizes preventing unauthorized privilege over convenience.
- Who is allowed to grant `admin` is not specified by this local dataset; the command must not invent an authorization model.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"access-grant","items":[{"item_id":"add-not-replace","owner_statement":"Granting a role preserves every existing role and adds only the requested supported role.","materiality":"critical","forbidden_outcomes":["Replacing or dropping an existing role"]},{"item_id":"validate-before-write","owner_statement":"An unknown user or unsupported role fails without changing access.json.","materiality":"critical","forbidden_outcomes":["Creating an implicit user","Persisting an unsupported role"]},{"item_id":"idempotent-grant","owner_statement":"Granting a role the user already has succeeds without duplicating it or changing state.","materiality":"material","forbidden_outcomes":["Duplicate role entries"]}],"probes":[]}
```
