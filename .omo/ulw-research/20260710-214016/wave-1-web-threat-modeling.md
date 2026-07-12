# Wave 1 — Threat Modeling

Worker: `/root/threat_modeling`  
Observed: 2026-07-10

## Digest

- Threat modeling generates bounded, falsifiable obligations; no method proves threat completeness.
- Severe threats should use two structurally different generators plus independent challenge, but this is a design proposition whose false-positive cost must be calibrated.
- Every high-impact threat must end in a falsifiable requirement, evidence demand, authorized risk decision, or stop condition.
- Control nouns are not evidence; closure requires a scenario oracle and suitable proof.
- Red-team execution requires explicit authorization/safety gates and scenario-specific evidence.

## Sources

- https://doi.org/10.6028/NIST.SP.800-30r1
- https://doi.org/10.6028/NIST.SP.800-115
- https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html
- https://www.sei.cmu.edu/blog/cyber-threat-modeling-an-evaluation-of-three-methods/
- https://www.se.rit.edu/~se555/Reading%20Materials/Capturing%20Security%20Requirements%20through%20Misuse%20Cases.pdf

## EXPAND

- Map proposed threat records and gates to the live schema/helpers.
- Test a severe-threat coverage gate on prior handoffs to measure false blocks.
- Define domain-neutral trust-crossing and irreversible-action trigger questions.

