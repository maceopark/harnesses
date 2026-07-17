# Owner World Model: Todo Completion

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Todos have stable IDs, text, and a boolean `done` field.
- Completion is a state transition on one existing item.
- Completed items remain in the collection.

## Vocabulary and decision posture

- “Complete” sets `done` to true; it does not toggle or delete.
- Completing an already-complete item is a successful no-op.
- An unknown ID is an error and must not create a todo.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"todo","items":[{"item_id":"set-not-toggle","owner_statement":"Completing a todo sets only the identified item's done field to true and never toggles it back or deletes the item.","materiality":"critical","forbidden_outcomes":["Toggling true to false","Deleting the todo"]},{"item_id":"preserve-records","owner_statement":"Completion preserves the todo's ID and text and every unrelated todo record.","materiality":"critical","forbidden_outcomes":["Changing todo text","Mutating another item"]},{"item_id":"idempotent-and-unknown","owner_statement":"Completing an already-complete todo succeeds as a no-op, while an unknown ID fails without changing todos.json.","materiality":"material","forbidden_outcomes":["Implicit todo creation"]}],"probes":[]}
```
