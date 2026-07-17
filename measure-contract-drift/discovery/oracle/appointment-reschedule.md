# Owner World Model: Appointment Reschedule

This is a synthetic but plausible product-owner model, fixed before candidate evaluation.

## Known reality

- Appointments have stable IDs, a due value, and notes that must be preserved.
- The schedule is interpreted in `America/Los_Angeles`.
- The CLI accepts one `DUE` argument, so supported due text remains a single token unless explicitly quoted by the caller.

## Vocabulary and decision posture

- “Reschedule” changes the due value of one existing appointment, not its identity or notes.
- An unknown appointment is an error and must not create a new appointment.
- Calendar collision policy and natural-language normalization are genuinely unspecified; the command must preserve the supplied due text rather than invent them.

```owner-card
{"schema":"DiscoveryOwnerCard.v1","case_id":"appointment-reschedule","items":[{"item_id":"targeted-update","owner_statement":"Rescheduling changes only the due value of the identified appointment and preserves its ID, notes, and every other appointment.","materiality":"critical","forbidden_outcomes":["Replacing the appointment object","Changing unrelated appointments"]},{"item_id":"unknown-id-no-write","owner_statement":"An unknown appointment ID fails without changing appointments.json.","materiality":"critical","forbidden_outcomes":["Creating an appointment during reschedule"]},{"item_id":"timezone-and-literal-due","owner_statement":"The supplied due value is stored literally and interpreted in the existing America/Los_Angeles schedule context; no unstated collision or normalization policy is invented.","materiality":"material","forbidden_outcomes":["Silently converting to another timezone"]}],"probes":[]}
```
