# Owner World Model: Order Cancellation

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Orders have stable IDs, items, and a lifecycle status.
- `pending` orders are cancellable; `completed` orders are not.
- The supplied reason is audit information and must be retained for a successful cancellation.

## Vocabulary and decision posture

- “Cancel” is a lifecycle transition, not deletion.
- Repeating cancellation of an already-cancelled order is a successful no-op and preserves the first reason.
- Refund behavior is outside this local command and must not be invented.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"order-cancel","items":[{"item_id":"lifecycle-boundary","owner_statement":"Only a pending order may transition to cancelled; a completed order cannot be cancelled and the file remains unchanged.","materiality":"critical","forbidden_outcomes":["Cancelling a completed order","Deleting an order"]},{"item_id":"reason-audit","owner_statement":"A successful first cancellation stores the non-blank REASON while preserving the order ID and items.","materiality":"critical","forbidden_outcomes":["Losing order items","Cancelling without an audit reason"]},{"item_id":"idempotent-cancel","owner_statement":"Cancelling an already-cancelled order succeeds as a no-op and preserves the original cancellation reason.","materiality":"material","forbidden_outcomes":["Overwriting the original reason"]}],"probes":[]}
```
