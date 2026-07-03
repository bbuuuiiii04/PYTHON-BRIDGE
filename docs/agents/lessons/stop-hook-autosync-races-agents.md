---
doc_status: current
truth_level: evidence-cited
last_verified_commit: 9705363
last_verified_date: 2026-07-03
---
# Stop Hook Autosync Races Agents

The operator's global Claude Stop hook auto-commits and pushes this repo's
dirty tree on every Claude turn-end.
Long-running implementer work left dirty mid-flight can be swept into a
junk-labeled pushed commit.
Evidence: `1f180c9` took phase-3 staged deletions on 2026-07-03.
Before multi-minute mutating work, check hook state or use the agreed lockfile
guard if one is adopted; never rely on unpushed history existing.
