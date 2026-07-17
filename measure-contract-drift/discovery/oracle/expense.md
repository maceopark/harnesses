# Owner World Model: Expense Recording

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Existing expenses contain an amount and note.
- Financial values must not acquire binary floating-point artifacts.
- The CLI records a new expense; it does not edit an existing one.

## Vocabulary and decision posture

- Amount must be a finite positive decimal with at most two fractional digits.
- The stored JSON number represents the normalized decimal amount.
- The note is required and preserved as supplied; whitespace-only notes are invalid.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"expense","items":[{"item_id":"decimal-money","owner_statement":"AMOUNT must be a finite positive decimal with at most two fractional digits and must be persisted without binary floating-point artifacts.","materiality":"critical","forbidden_outcomes":["Accepting NaN or infinity","Floating-point rounding artifacts"]},{"item_id":"validate-before-append","owner_statement":"An invalid amount or blank note fails without appending an expense or changing expenses.json.","materiality":"critical","forbidden_outcomes":["Partial or placeholder expense"]},{"item_id":"append-preserve","owner_statement":"A valid expense is appended once while preserving all existing expense records and the supplied note text.","materiality":"material","forbidden_outcomes":["Replacing the expense history"]}],"probes":[]}
```
