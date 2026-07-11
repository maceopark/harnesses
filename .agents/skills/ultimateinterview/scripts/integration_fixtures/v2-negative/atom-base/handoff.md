# Part 1 - Build Contract

## Behavior Contract

| ID | Requirement | Acceptance criterion (EARS or Given/When/Then) | Source | Assurance class | Atom IDs |
| --- | --- | --- | --- | --- | --- |
| REQ-101 | structured boundaries remain explicit | When invoked, each declared boundary shall remain observable. | REQ-101 | high | ATOM-101, ATOM-102, ATOM-103, ATOM-104, ATOM-105 |

Behavior atom catalog:

| Source | Assurance class | Atom ID | Condition | Polarity | Observable response | Boundary context | Temporal context | Coercion context |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-101 | high | ATOM-101 | The request declares corrupt, permission, and write modes. | must | The request is rejected before any effect. | No effect occurs. |  |  |
| REQ-101 | high | ATOM-102 | A protected action is invoked. | must | An authorization result is recorded. |  |  |  |
| REQ-101 | high | ATOM-103 | Three failed attempts have been recorded. | must | The retry lock is active. |  | Applies at version >= 3. |  |
| REQ-101 | high | ATOM-104 | An identifier is supplied. | must | Only canonical integer identifiers are accepted. |  |  | Numeric strings are rejected without coercion. |
| REQ-101 | high | ATOM-105 | The first validation boundary passes. | must | The request remains guarded. | The later write boundary repeats authorization. |  |  |

# Part 2 - Audit Trail

The atom base is a redacted mutation fixture for structured coverage only.
