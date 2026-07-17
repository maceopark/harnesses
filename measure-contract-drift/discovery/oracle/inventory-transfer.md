# Owner World Model: Inventory Transfer

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Inventory is tracked per item and location in integer units.
- Both `east` and `west` are known locations.
- Item metadata is descriptive and must not change during transfer.

## Vocabulary and decision posture

- Quantity must be a positive integer.
- A transfer is one atomic conservation operation: subtract from source and add to destination.
- Transfers to the same location are rejected because they indicate a caller mistake.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"inventory-transfer","items":[{"item_id":"atomic-conservation","owner_statement":"A valid transfer atomically subtracts QUANTITY from FROM and adds the same QUANTITY to TO without changing total stock or item metadata.","materiality":"critical","forbidden_outcomes":["Stock creation or loss","Partial source-only update"]},{"item_id":"sufficient-stock","owner_statement":"Unknown items or locations, non-positive or non-integer quantities, and insufficient source stock fail without changing inventory.json.","materiality":"critical","forbidden_outcomes":["Negative stock","Implicit item or location creation"]},{"item_id":"distinct-locations","owner_statement":"FROM and TO must be different locations; a same-location transfer is rejected without mutation.","materiality":"material","forbidden_outcomes":["Reporting a meaningless transfer as changed"]}],"probes":[]}
```
