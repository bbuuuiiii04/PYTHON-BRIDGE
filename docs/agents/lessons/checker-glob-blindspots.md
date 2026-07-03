---
doc_status: current
truth_level: evidence-cited
last_verified_commit: 9705363
last_verified_date: 2026-07-03
---
# Checker Glob Blindspots

Advisory checkers can under-resolve silently.
The staleness checker excluded `tools/` and dropped `/**` while pad contracts
lived in `tools/`; `laser_pad` reported only 1 impl file and `fresh` through 6
landed commits.
When adding a contract, run `python3 tools/check_docs_staleness.py --report`
and sanity-check the implementation file count.
Evidence: `c5906dc`.
