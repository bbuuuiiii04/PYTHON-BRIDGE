# TimecodeLink Retirement Process Log

Purpose: continuously track the current evidence, decisions, and next steps for
phased TimecodeLink reduction in `rb_ss_bridge_v2`.

This is a repo-local continuity file for future agents. It does not change
runtime behavior and does not promote any authority source.

## Current Ground Rules

- TL retirement is signal-by-signal, not a single switch.
- Evidence gathering must stay separate from retirement.
- `StateManager` does not currently arbitrate by event source.
- TL remains authoritative unless a later explicit, narrow migration changes
  one signal with fail-closed behavior.
- No direct master authority has been promoted.
- No play/pause, track-load, timing, scripted-routing, ANLZ, or TL TC authority
  has been promoted.

## Current Repo State

- `TLLogTailer` remains authoritative for TL log and ENGINE STATE events.
- `LiveBPMService` is the strongest direct-first subsystem and already uses
  offset-table BPM when valid.
- Direct master support exists as:
  - one-shot startup probe
  - startup settle/retry observation
  - bounded runtime observer
  - TL-only `TLMasterSnapshot` comparison source
- Direct master logs remain observational and use `authority=tl_log`.
- Direct master runtime comparison uses `comparison_source=tl_master_snapshot`.
- `rb_memory.py` remains unchanged in this process.
- Lighting/output behavior remains unchanged.

## Direct BPM Status

Direct BPM is already the most mature TL-reduction path in the repo.

Current behavior:

- `LiveBPMService` reads Rekordbox displayed BPM directly from process memory.
- On supported Rekordbox versions, it uses the per-version offset-table BPM
  chains from `rb_offsets.py`.
- If the offset-table chain is unsupported, unreadable, stale, or invalid, it
  falls back to discovery/validation and ultimately to metadata/ENGINE STATE
  fallback.
- It is used for autoloop arm snapshots and default-on active autoloop BPM
  follow when fresh and valid.
- It does not change master deck, play/pause, track load, or timing authority.

Evidence and handoff docs:

- `docs/live_bpm_findings.md`
- `docs/live_bpm_handoff.md`
- `docs/bridge_design.md` Live BPM section

Current TL-retirement interpretation:

- TL/ENGINE BPM is no longer the primary live BPM source when direct BPM is
  valid.
- TL/metadata BPM remains the fail-closed fallback.
- Direct BPM readiness must not be generalized to direct master, direct
  play/pause, direct track load, scripted routing, ANLZ, or TL TC retirement.

Remaining Direct BPM risks:

- unsupported Rekordbox versions
- stale reads after Rekordbox restart or session/base change
- same/near-same BPM deck separation
- discovery latency when offset-table reads are unavailable
- validation windows where the wrong deck moves or no pitch movement occurs

No current action is needed for Direct BPM in the TL-retirement sequence except
to preserve its direct-first, fail-closed behavior and keep validation logs
visible.

## Direct Master Live Evidence So Far

### Clean Deck 1 Stable Startup / No-Touch Runs

Observed:

- `outcome=became_valid_and_matched_tl`
- `first_valid_master=deck1`
- `final_direct_master=deck1`
- `final_tl_master=deck1`
- `tl_master_at_first_valid=deck1`
- `first_valid_elapsed_s=0.00`
- `transition_count=1`
- `mismatches=0`
- `comparison_source=tl_master_snapshot`
- `authority=tl_log`

Judgment: encouraging. Direct master is immediate, readable, stable, and aligned
with TL in clean deck1 windows.

### Dirty Deck 2 Stable-Window Runs

Observed pattern:

- direct reads `deck2`
- TL snapshot initially says `deck1`
- TL/ENGINE later updates to `deck2`
- final direct and TL match `deck2`
- `transition_count=1`
- `mismatches` observed during startup freshness gap

Representative fields:

- `outcome=became_valid_but_mismatched_tl`
- `first_valid_master=deck2`
- `final_direct_master=deck2`
- `final_tl_master=deck2`
- `tl_master_at_first_valid=deck1`
- `first_valid_elapsed_s=0.00`
- `transition_count=1`
- `mismatches=1` or more

Judgment: encouraging for direct readability and stability, but not a clean
deck2 no-mismatch proof. The narrow interpretation is that direct Rekordbox
master may surface current master state earlier than the TL-only snapshot
becomes fresh at startup.

### Intentional Single Master Switch

Observed:

- `first_valid_master=deck1`
- `final_direct_master=deck2`
- `final_tl_master=deck2`
- `tl_master_at_first_valid=deck1`
- `first_valid_elapsed_s=0.00`
- `transition_count=2`
- `mismatches=1`
- outcome did not become `flapped`

Judgment: encouraging for single-switch behavior. Direct moved once, ended
aligned with TL, and did not flap. The mismatch appears consistent with a
switch-time TL/direct timing race.

## Current Conclusions

Convincingly proven:

- direct master is live-readable on the tested Rekordbox `7.2.11` setup
- raw `0` maps to bridge `deck1`
- raw `1` maps to bridge `deck2`
- first valid direct master appears immediately in observed runs
- clean deck1 stable windows match TL with `mismatches=0`
- a single direct transition during an intentional switch gives
  `transition_count=2`, not `flapped`
- final direct/TL state has matched in reviewed useful runs

Not yet proven:

- direct master should become runtime authority
- a clean deck2 stable-window run where TL is fresh at first valid and
  `mismatches=0`
- direct play/pause readiness
- direct track-load authority readiness
- direct startup metadata replacement
- ANLZ path replacement
- scripted OSC / scripted ID replacement
- TL TC fallback removal

## TL Dependency Retirement Position

Already plausible / partly migrated:

- Live BPM via `LiveBPMService` direct offset-table path, with fallback.

Needs targeted validation:

- direct master startup seed
- master runtime parity expansion
- direct track-load/title parity
- startup loaded-deck metadata replacement

High risk / not ready:

- play/pause authority
- scripted routing and scripted IDs
- ANLZ path correlation
- TL TC fallback removal
- full TL runtime removal

## Near-Term Execution Plan

### Phase N+1: Hold Position And Consolidate Evidence

No runtime changes. Preserve current evidence and decisions in this process log.

Success:

- future agents can see direct master is promising but still shadow-only
- next candidate is master startup seed design, not runtime authority

### Phase N+2: Master Startup-Seed Experiment Design

No implementation until explicitly authorized.

Candidate rule to design later:

- startup only
- direct must be supported, readable, valid `deck1`/`deck2`, and stable
- fail closed to TL on unsupported, unreadable, `none`, or unstable
- runtime TL/ENGINE remains authority after startup

No-go:

- direct final master disagrees with TL final master after settle
- direct flaps or returns to `none`
- rule requires broad arbitration

### Optional Phase N+3: Master Parity Expansion

Continue evidence gathering only.

Useful next validation:

- clean deck2 stable no-touch run where TL is already deck2 at first valid
- repeated intentional single switches
- longer no-touch windows after switch

## Current Smallest Justified Next Step

If more live validation is desired, run one clean deck2 stable-window symmetry
test:

- set Rekordbox master to deck2
- wait for TL/ENGINE to settle
- start bridge
- do not touch master during the bounded runtime window

Target:

- `outcome=became_valid_and_matched_tl`
- `first_valid_master=deck2`
- `final_direct_master=deck2`
- `final_tl_master=deck2`
- `tl_master_at_first_valid=deck2`
- `transition_count=1`
- `mismatches=0`

Even if this passes, do not promote runtime master authority from this evidence
alone.

## Update Rule For Future Agents

After each new live run, decision, or user correction, append or revise this
file with:

- exact observed summary fields
- scenario conditions
- judgment: encouraging, inconclusive, or concerning
- what the evidence proves
- what remains open
- smallest justified next step
