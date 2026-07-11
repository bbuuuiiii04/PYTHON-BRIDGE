---
doc_status: current
truth_level: spec
last_verified_commit: 85cb8ea
last_verified_date: 2026-07-11
validation_scope: >
  Implementation spec for AWR-212 — pre-resolve mounted export sticks at
  bridge startup so USB track identity (incl. scripted) is warm before the
  first load. Operator choice "B" 2026-07-11, eliminating the ~3.4s worst-case
  autoloop->scripted window the AWR-207 ultracode review flagged (finding F2).
  Sequenced in the SAME lane as AWR-209 (shared files). STAGED.
---

# Implementation Spec — AWR-212 Startup pre-resolution of mounted export sticks

## Part A — Context (verified)
- [confirmed] AWR-207 resolves USB loads asynchronously; the ultracode review
  bounded the worst case at ~3.4 s from TRACK_LOADED to scripted-mode entry
  for an instant-played scripted USB track (review doc F2, operator chose
  mitigation over acceptance). A session memo already makes REPEAT loads
  instant — the gap is only each track's FIRST load.
- [confirmed] The operator's ritual: stick plugged in before the menubar
  start. So a startup scan warms the memo before any load.

## Part B — Tasks
### Absolute Rules
- Same boundaries as AWR-207/209 (bridge running = untouched; read-only
  sources; fail closed). Out of scope: sidecar (AWR-210/211), mount-event
  watching (startup-time scan only — a stick mounted AFTER startup simply
  uses the existing lazy path; state that in docs).
- The push loop gains nothing; the scan runs in ONE background daemon thread
  started from bridge startup (after the resolver exists), throttled
  (small sleep between tracks) so startup I/O never contends with the
  reader/push threads.

### Task 1 — startup scan
At bridge startup: enumerate mounted device exports (`/Volumes/*/PIONEER/
USBANLZ`), walk each ANLZ entry, and run the EXISTING resolution path
(AWR-207 twin match incl. AWR-209 levers) for each, storing results in the
existing session memo — identical code path, just eager. Per-stick summary
log at INFO: resolved / unresolved+reasons / elapsed. Scan failure of any
entry logs and continues (lazy path remains for it). A load arriving MID-scan
for an unmemoized track uses today's lazy path unchanged (no locking games —
memo writes are already thread-safe or become a single lock; verify at HEAD).

### Task 2 — tests
Pure seams: scan enumerates only device-export roots; memo warm → load
resolves synchronously (scripted ssid present at TRACK_LOADED handling);
mid-scan load falls back lazily; scan errors don't propagate; throttle
present. Regression: no-stick startup = zero behavior change.

### Task 3 — contract/docs/checks
`rekordbox_readers` docs_update; AWR-212 registry row (re-check max); note in
the runbook: plug stick before menubar start for instant scripted; 3 hard
checks; scoped suites + discover BY NAME.

## Part C — Invariants
Push loop untouched; reader event order untouched; startup must not block —
the bridge is fully live while the scan proceeds; STAGED.

## Part E — Acceptance
Warm-memo scripted load test proves the window is gone (0 async wait when
memoized); real-stick spot run if /Volumes/MINK mounted (report counts +
scan time); suites/checks green; explicit-path commits.
Report + signals: /tmp/rbss_lane_signals/sol205.AWR212.{done,blocked,report.md}.
