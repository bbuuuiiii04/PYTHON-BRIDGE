# Career Advisor production-hardening report — 2026-08-10

## 1. Final verdict

**production-ready with explicitly bounded limitations**

Brandon can use Career Advisor as the user for Fall 2026 start: Morning Briefing + ChatGPT coaching against live Drive owners, with corrected attention (including the Aug 11–12 GRE diagnostic), syllabus-derived academic obligations, hardened coach constitution, interview/CTL prep tracking, letter-runway early warning, and automation silent-death visibility improvements.

This is **not** a claim that every automation has been production-verified unattended, that Drive↔Val sync is healthy, or that secrets storage is remediated.

## 2. What materially changed

Architecture / behavior repairs written to live Google Drive (readback-verified), not cosmetic doc polish:

1. **Attention truth (`STATE.md`)** — GRE diagnostic Aug 11–12 now in NEXT DATES; Physics wait-state no longer reserves idle hours; unfinished HCA PCT is the One Thing (DPC preference over scribe); email cadence corrected to 07:00/11:00/20:00; BCPM shows both ~3.34 and ~3.32.
2. **Academic schedule intelligence (`REFERENCE.md`)** — Fall 2026 syllabus obligation baseline seeded (PHY2053 exam nights Sep 24 / Nov 3 / Dec 8, HW/Perusall cadence, ASL APA, ENY deadline penalties, risk modes). Full hour-by-hour week grid still correctly blocked on Physics section + ENY4210 confirmation.
3. **Coach constitution (`AGENTS.md`)** — Morning Briefing silent-death peek at session-open; Canvas-empty ≠ quiet week; 07:00 email morning-slot freshness rule for 08:00 briefing; slow-burn runway monitors (Physics letter, CTL prep debt, shadowing, offer→first shift); interview rung map + optional `assistance_max`.
4. **Morning Briefing procedure** — morning email-slot SLA; interview digs not default fronts; delivery-unverified language for missing `last_run`.
5. **Interview product** — rung 0–4 map; relevant-session digs (not always-on); CTL REQUIRED hardest-conversation card placeholder in `ESSAY_BANK.md` + fence; one-home fix for Rooms-and-tubes content.
6. **Relationships** — `CONTACTS.md` letter-runway monitor with dated Physics/CTL/#3 triggers.
7. **Study** — `risk_mode` seeding for Fall courses; Canvas-empty rule in `STUDY_ENGINE.md`.
8. **Automation visibility** — Weekly Plan Recalc **COMPACT STATE** fence inside existing contract (service account cannot create contentful new files); ENGINES register cleaned and updated honestly.
9. **Certification harness** — `scenarios.md` S19–S24; Morning Briefing suite expanded **50 → 54** and passing.

## 3. Lifecycle matrix

| Capability | Highest stage reached | Limitation |
|---|---|---|
| Owner-precedence coaching constitution | **implemented** (+ partial **tested** via MB suite / spot checks) | Full model certification (`scenarios.md` S1–S24) **not run** as fresh coaching sessions |
| STATE attention rewrite (GRE/Physics/HCA) | **implemented** + live readback **verified** | Needs real Morning Briefing consumption evidence |
| Fall academic obligation baseline | **implemented** | Hour-by-hour grid waiting on Physics section + ENY4210 confirmation |
| Targeted schedule recalc / STALE law | **specified** + contract-**tested** | No genuine midweek production recalc observed yet |
| Morning Briefing procedure/state | **implemented** + mechanic-**tested** (54/54) | Unattended 08:00 production run + notification delivery **awaiting evidence** |
| Smart Email Sweep | **implemented** (prior) | Unattended 07:00×3 not verified; notifications disabled |
| GPA calculator | **implemented** + baseline-**tested** this run | Course-row fixture not shipped; no auto ingestion |
| Interview engine + CTL required card | **implemented** | First real calibrated rep **not observed**; 2/8 cards |
| Letter runway monitor | **implemented** | No production trigger fired yet (classes start Aug 20) |
| Weekly Plan Recalc silent-death state | **implemented** (fence) | Unattended Sunday run **not verified** |
| CAA deadline watcher | **specified**/dormant | Starts Jan 2027; no Drive state yet |
| Application object | **not implemented** | Defer to PIPELINE CAA section when cycle opens |
| Drive↔Val sync / ledger migration / KEYS remediation | **blocked** | See remaining blockers |

## 4. Remaining blockers

**Unbuilt**
- Per-program CAA application object (deferred until cycle usefulness)
- Course-row GPA fixture / auto transcript ingestion
- Automatic fresh-shift → essay dig capture

**Built but untested / awaiting production evidence**
- Unattended Morning Briefing 08:00 delivery + state write
- Unattended Smart Email Sweep 07:00 pre-brief slot chain
- Unattended Weekly Plan Recalc / Job Sweep / Audit scheduler proof
- First live interview rep under calibration; letter-runway triggers after Aug 20
- Midweek material schedule change → targeted recalc in production

**Future external facts that cannot yet exist**
- Final Physics lecture/lab section registration
- ENY4210 ONE.UF confirmation
- Published 2027–28 CASAA / program deadlines
- First qualifying clinical shift / CTL live hours

**Blocked infrastructure (do not pretend repaired)**
- Drive↔Val divergence (`RUNTIME.md`) — blocks ledger migration and aggressive pruning
- `KEYS.md` still stores live secrets in ordinary Drive with `anyoneWithLink` writer on the folder — remediation needs consumer inventory + rotation (Brandon/platform), not a silent rewrite this run
- ChatGPT automation notification delivery observed disabled / not writable via current API

## 5. Evidence

- Drive write receipts (readback-verified): `16` primary file updates this run, plus ENGINES rewrite, Plan Recalc contract fence, MB test-results update.
- Morning Briefing adversarial suite: **54/54 pass** (post-hardening).
- GPA calculator this run: official 3.47; computed 3.4776; BCPM 3.3390; Physics A projection 3.4308.
- Live spot-checks: STATE contains GRE Aug 11–12, Physics wait-state carve-out, HCA One Thing, 07:00 cadence, dual BCPM; REFERENCE contains Sep 24 8:20 exam; AGENTS contains silent-death / Canvas-empty / 05:30 rules.

## 6. Brandon-required actions

Ideally none for machinery. Only these are truly his:

1. **Career / irreversible user actions already in flight:** finish HCA application fields; attend Rula if still scheduled; take GRE POWERPREP on Aug 11 or 12; send Luisa reply when ready (system drafts at current autonomy level — he sends).
2. **Platform permission / security (optional but recommended, not required to use the advisor tomorrow):** decide whether to rotate exposed Drive/API credentials and remove `anyoneWithLink` writer once consumers are mapped — do **not** rotate blindly mid-semester without a rollback path.
3. **No** ask to reconcile Drive files, edit AGENTS, or maintain automation state.

## Security note (no secret values)

`KEYS.md` remains a known defect: secrets live in the ordinary Drive tree, and the Career Advisor folder is shared as `anyoneWithLink` **writer**. This mission did not rotate credentials (destructive without full consumer graph + Brandon approval). Coaches must not quote KEYS values.
