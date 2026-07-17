# Owner World Model: Contacts CSV Import

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Contacts minimally contain `name` and `email`.
- Email is the practical identity key for import reconciliation.
- A CSV import may contain malformed rows or duplicates.

## Vocabulary and decision posture

- Header names are required; column order is not significant.
- Email matching is case-insensitive, while the imported display spelling may be preserved.
- The owner prefers atomic rejection over a partially imported file when any row is invalid.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"contacts-csv","items":[{"item_id":"required-columns","owner_statement":"The CSV must have named name and email columns; missing columns or malformed rows fail the entire import without changing contacts.json.","materiality":"critical","forbidden_outcomes":["Partial import","Positional interpretation without headers"]},{"item_id":"email-identity","owner_statement":"Contacts are reconciled by case-insensitive email identity; an existing email is updated rather than duplicated.","materiality":"critical","forbidden_outcomes":["Duplicate contacts differing only by email case"]},{"item_id":"in-file-duplicates","owner_statement":"If the same email occurs more than once in one file, the last valid row wins deterministically before the atomic write.","materiality":"material","forbidden_outcomes":["Order-dependent duplicate records"]}],"probes":[]}
```
