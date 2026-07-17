# Fixed Owner World Models

This directory contains one `<case-id>.md` dossier for every discovery case. Each dossier is fixed
before candidate evaluation and serves two purposes:

- its prose gives the automated owner responder a stable mental model: known reality, vocabulary,
  priorities, explicit unknowns, and decision posture;
- its fenced `owner-card` JSON block identifies the material policies that can grant compiler
  authority and be scored for discovery coverage.

The responder receives the complete Markdown file but never receives the candidate ID, candidate
skill, ranking, or sibling results. A fact mentioned in prose may support an answer, but only a
unique match to an item in the authority block grants authority. The world models are intentionally
synthetic and plausible; they are benchmark fixtures, not claims about a real product owner.

Do not encode preferred question wording or an interview algorithm in these files. Change a dossier
only as a benchmark version change, because its byte digest is bound into every cell and resume.
