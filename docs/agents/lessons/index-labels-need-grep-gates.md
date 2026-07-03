---
doc_status: current
truth_level: evidence-cited
last_verified_commit: 9705363
last_verified_date: 2026-07-03
---

# Index Labels Need Grep Gates

No checker fully compares `doc_index` labels and file locations to reality.
Rows marked active pointed at completed files, and 13 archived specs carried
active-looking headers.
Docs-truth specs must include explicit `rg` acceptance gates for labels,
locations, and stale active wording.
Evidence: 2026-07-03 phase-4 audit.
