# Owner World Model: Reminder Creation

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Reminders contain text and a due value.
- The current store does not define IDs, recurrence, completion, or timezone metadata.
- The CLI adds one reminder; it does not edit existing reminders.

## Vocabulary and decision posture

- TEXT and DUE are stored literally after rejecting blank values.
- Natural-language date parsing is not authorized by this model.
- Identical reminders are allowed because repeated text and due values may represent separate intentions.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"reminder","items":[{"item_id":"literal-fields","owner_statement":"A valid reminder stores TEXT and DUE literally without inventing date parsing, recurrence, IDs, or timezone conversion.","materiality":"critical","forbidden_outcomes":["Silent date normalization","Invented reminder fields"]},{"item_id":"blank-no-write","owner_statement":"Blank or whitespace-only TEXT or DUE fails without changing reminders.json.","materiality":"critical","forbidden_outcomes":["Persisting unusable reminders"]},{"item_id":"append-duplicates-allowed","owner_statement":"A valid reminder is appended once while preserving all existing reminders; an identical text and due pair is still a distinct reminder.","materiality":"material","forbidden_outcomes":["Implicit duplicate suppression","Replacing reminder history"]}],"probes":[]}
```
