---
doc_status: current
truth_level: code-verified
last_verified_commit: HEAD-2026-07-08-night
last_verified_date: 2026-07-08
validation_scope: implementation spec for the overnight darkness-fix round (executive-released); grounded in docs/research/deck2_reader_diagnosis_2026_07_08.md with every cited site re-verified at current HEAD this session; bridge is DOWN — no bridge starts, live config read-only
---

# Codex Implementation Spec - Darkness fix round: blank-role hold + reader freshness (AWR-157)

Executive-released round 1 of the 2026-07-08 overnight queue, from the
diagnosis `docs/research/deck2_reader_diagnosis_2026_07_08.md`: (a) tonight's
actual cause — a blank/none LED role while a deck played audibly fell through
to `utility`/`room_blackout` for ~46s during a scripted-mashup crossover;
(b) the latent deck-2 reader risk — a frozen position chain reads as healthy
forever, with the ObjC fallback globally disabled.

## Part A - Context & Root Cause (verified; read, do not implement)

All sites re-verified at current HEAD this session:

1. **Blank role → utility default:** `led_look_director.py:145-150`
   (`default_role = role or "utility"`; `utility` bank maps to
   `room_blackout`). The log proves the outcome (`look room_blackout
   role=utility` bursts 20:52:37→20:53:23 while deck 2 was `only_audible`
   and advancing). [confirmed]
2. **Scripted mode contributes `drop_role="none"` by design**
   (`state_manager.py:2555-2570`, Required Behavior Test 9). [confirmed]
3. **The exact blank-role persistence path is the diagnosis's OPEN Q-A** —
   role derivation (`led_dispatch_policy.py:1748-1790`
   `_led_role_from_smart_phrasing` can yield "", and
   `_led_effective_role_for_dispatch` `:1729-1737` maps scripted roles) has
   several candidate blank sources (phrase none, scripted map, adapter
   reject). **Therefore the fix intercepts at the DISPATCH layer, where every
   path converges, and the instrumentation names the origin** — do NOT try to
   fix one origin path. [confirmed design decision]
4. **Reader latent risk:** `chain_ok = chain_snap is not None`
   (`rb_memory.py:1404`) is freeze-blind; `read_live_pos_chain`
   (`:859-912`) returns valid snapshots for a frozen value and infers
   `playing` from `raw != prev_raw` (`:898-899`); the ObjC scan is skipped
   whenever the chain was ok last tick (`skip2 = self._skip_objc_when_chain
   and self._chain_ok_last.get(2, False)`, `:1307`) with
   `RBSS_POS_CHAIN_SKIP_OBJC=1` set by the watcher
   (`scripts/ss_bridge_watcher.sh:152`). Post-AWR-148 the scan is vectorized
   (28-40×), so the original freeze reason for disabling it no longer holds.
   [confirmed]
5. **Executive default, operator veto-able:** hold-last-look on
   blank-role-while-audible ships DEFAULT ON. [locked]

[assumed, verify while implementing]: an external playing hint (direct play
flags, not the chain's own raw-delta inference) is reachable at the chain
health-decision site — the readers publish play hints alongside position.
If no hint is plumbed into `rb_memory`'s chain path, wire the existing
deck-2 play hint through the existing call chain (name the exact functions
in your report); do NOT use the chain's self-inferred `playing` for the
freshness gate (circular).

## Part B - Tasks (implement exactly, in order; one commit per task)

### Absolute Rules

- NO bridge starts (bridge is down and stays down; the operator's next
  menubar start is his). `config/led_look_director.json` LIVE = read-only.
  `config/led_lab/**` out of scope. No laser/SoundSwitch behavior changes.
- Behavior that must not change: emergency/manual blackout paths (AWR-154/
  155 semantics), the TACTICAL pre-drop blackout
  (`_dispatch_led_smart_drop_blackout` — an intentional dark moment, never
  suppressed by the new hold), scripted-mode Required Behavior Test 9 (zero
  drop-presentation policy activity on scripted tracks), idle behavior when
  nothing is audible (utility blackout while NOT playing stays exactly
  today's), AWR-149 rotation, the 200 Hz push loop (no new blocking I/O),
  deck-1 reader behavior.
- Error handling: fail toward LIGHT on the LED side (a broken hold guard
  must degrade to today's behavior, not to a new dark state); fail toward
  MISS on the reader side (an uncertain chain counts as a miss so the
  fallback engages). No broad try/except.

### Task 1 - `led_dispatch_policy.py` + `led_models.py` + `led_config.py`: blank-role hold guard

New config knob `blank_role_hold: bool = True` (top-level in the LED config,
parsed + validated like the other booleans; DEFAULT TRUE — an absent key in
the un-mirrored live config gets the executive-approved behavior; FLAG in
the operator summary: setting it `false` restores today's blackout-on-blank).

In the automation dispatch path (where the director's decision is accepted
for dispatch), intercept: when ALL of —
- the decision's look equals the configured blackout look
  (`config.blackout`) AND decision source is automation/policy (NOT
  `emergency`, NOT `manual`, NOT the tactical smart-drop blackout path),
- the active deck is audibly playing (the same playing/audible state the
  dispatch tick already has in scope — `d.playing` + active-deck auth),
- `blank_role_hold` is true, and
- a previously-accepted automation decision exists this session —

then SUPPRESS the blackout dispatch and keep the current look (re-dispatch
the last accepted automation decision only if the strip needs a refresh;
otherwise emit nothing — the room simply stays on the current look). Gate
the event with the existing gate-bookkeeping pattern (reason
`blank_role_hold`) so counters/status stay truthful. The hold lapses the
moment playing stops or a non-blackout decision arrives.

### Task 2 - Q-A instrumentation (same files)

Every time the guard fires (or WOULD fire with the knob off), log
edge-triggered INFO `[RGB] blank-role-hold` with: `original_role`,
`effective_role`, `scripted` flag, active-deck auth, and a source
classification field — `phrase_none` (role derivation returned blank) vs
`scripted_map` (scripted mapping produced the blank/utility) vs
`adapter_reject` (a real look was rejected upstream this tick) vs `other`.
Per-tick repeats at DEBUG only (log-style rule: INFO for outcomes,
edge-triggered). This names Q-A's persistence path from one live session.

### Task 3 - `rb_memory.py`: freshness-aware chain health

At the chain health decision (`:1404` area): a chain snapshot only counts as
healthy when it is FRESH — `raw` advanced within the last
`_CHAIN_FRESH_TICKS = 5` consecutive reads while the EXTERNAL playing hint
says playing (see Part A [assumed]). A frozen-while-playing chain becomes a
miss: `chain_ok = False` for gating purposes (position value handling
otherwise unchanged — do not zero the position, just mark the miss). While
the hint says paused/stopped, an unchanging raw is NOT stale (a real pause
reads frozen legitimately — tonight's FEIN case). Track per-deck consecutive
identical-raw counts on the reader thread; module constant, no new env knob.

### Task 4 - `rb_memory.py`: conditional ObjC fallback re-engage

`skip2` (`:1307`) gates on freshness, not mere presence: the ObjC scan is
skipped only while the chain is healthy-AND-fresh; when Task 3 marks the
chain stale, the (AWR-148-vectorized) scan engages on the next tick even
with `RBSS_POS_CHAIN_SKIP_OBJC=1`. The watcher env line is NOT touched —
its meaning refines from "never scan while chain exists" to "never scan
while the chain is actually working." Log edge-triggered INFO when the
fallback engages/disengages (`[RBMEM] chain-stale fallback-engaged deck=2`
/ `fallback-idle`).

### Task 5 - `rb_memory.py`: Q-B pause-vs-freeze instrumentation

In `read_live_pos_chain` (`:898-899` area): when deck-2 `playing` flips
False within 10 s of a track load, log one DEBUG line with `raw`,
`prev_raw`, and the direct play-flag value if reachable — distinguishing a
real pause from a frozen-while-playing field in one session. Edge-triggered,
never per-tick.

### Task 6 - Tests

Pure seams:
1. Hold guard (`tests/test_led_state_manager.py`): blank role + audible
   playing → blackout suppressed, gate reason `blank_role_hold`, current
   look retained; NOT playing → blackout dispatches exactly as today;
   emergency blackout → still wins immediately; tactical pre-drop blackout
   path → unaffected; knob false → today's behavior byte-identical; the
   would-fire log still emitted with knob off.
2. Config (`tests/test_led_config.py`): `blank_role_hold` parse
   (absent→True, false→False, malformed→error); example config loads.
3. Chain freshness (`tests/test_rb_memory_scans.py` or a new focused file):
   frozen raw + playing hint → miss after 5 identical reads; advancing raw →
   healthy; frozen + paused hint → healthy (the FEIN case); fallback skip2
   flips accordingly; deck-1 path untouched.
4. Instrumentation smoke: log lines emitted edge-triggered (no per-tick
   spam) — assert via the existing log-capture test idioms.

### Task 7 - Contract docs (final commit)

Contracts: `led_govee`, `rekordbox_readers`, `config_schema` — update every
`docs_update` doc for all three (subsystem cards, matrices, configuration
docs, playbooks per the yml), example config gains `blank_role_hold: true`,
and an AWR-157 registry row (implemented / software-tested; operator veto
flag on the hold default; the diagnosis doc's §7 becomes "implemented, Q-A/
Q-B instrumentation live"). Run both contract test lists +
`python3 -m unittest discover tests` (known reds: the six environmental
ones) + the three hard doc checks.

## Part C - Invariants That MUST Still Hold (live safety)

- Emergency and manual blackouts ALWAYS dark the room instantly — the hold
  guard never intercepts them (source check is load-bearing; test-pinned).
- The tactical pre-drop blackout stays exactly as designed (drop impact
  choreography depends on it).
- Idle/no-audible behavior unchanged: blank role while NOTHING plays still
  blackouts/idles exactly as today.
- Scripted-mode Required Behavior Test 9 unchanged (the window machine tick
  with `drop_role="none"` stays; only the downstream blackout-while-audible
  outcome changes).
- Reader: deck-1 path byte-identical; a REAL pause never counts as stale
  (paused hint exempts freshness); the ObjC scan still never runs
  concurrently with itself and engages only via the existing per-tick
  gating; the push loop gains nothing.
- Fail direction: LED guard failure → today's behavior (dark), never a
  stuck-lit emergency-defeating state; reader uncertainty → miss →
  fallback, never a silent frozen "healthy."

## Part D - Test seams

Named in Task 6 — the dispatch guard is testable through the existing
`test_led_state_manager` harness fixtures; the chain freshness logic must be
a pure function or method testable with synthetic (raw, hint) sequences, no
process memory required.

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-7 in order, one commit each, explicit paths (auto-sync may
  fragment — check git log before treating a commit as failed, note it,
  never rewrite).
- [ ] All three contracts' docs_update lists fully updated; suite at the
  known-six-reds baseline; three hard checks green.
- [ ] The Part A [assumed] playing-hint plumbing verified and named in the
  report.
- [ ] Operator summary: plain-language — after his next menubar start, a
  song that is audibly playing can no longer go pitch-black just because the
  phrase/role data went blank (the room holds its current look; one config
  line restores the old behavior if he ever wants it); the deck-2 position
  fallback now wakes up automatically if the main reader ever freezes
  mid-song instead of staying silently broken; two new log lines will tell
  us exactly why any future blank-role or freeze happens.
- [ ] LIVE config untouched; no bridge start.

## When You Finish

Report per task: files, tests, checks, the playing-hint verification, any
deviation. Print exactly AWR157-DONE on its own line with real suite numbers
above it; if blocked, AWR157-BLOCKED plus the reason.
