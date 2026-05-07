# Direct Master Runtime Validation

This guide is for live validation of the bounded runtime direct-master observer.
The observer is a shadow-only readiness check for Rekordbox's direct
`master_deck` byte path. It does not promote direct master authority.

As of B6, live direct master authority can also be enabled separately with
`RBSS_MASTER_DIRECT=1`. That authority path runs through the main
`RBStateReader._tick()` instance, routes `MASTER_CHANGED source='rb_state'` to
the authoritative queue, and bypasses TL OSC `/bridge/active_deck` plus TL log
and ENGINE STATE `MASTER_CHANGED` only while the direct master byte is readable
and valid. ENGINE STATE BPM and TC fallback events still flow. The bounded
runtime observer described here remains shadow-only and is still only a
comparison tool.

## Scope

The runtime observer:

- starts after bridge startup wiring has had a short settle period
- reads the version-specific direct `master_deck` chain at low rate
- compares direct master against the TL-only `TLMasterSnapshot`
- logs start, initial, first-valid, first-mismatch, and summary phases
- stops after the bounded runtime window

The runtime observer does not:

- enqueue bridge events
- mutate `StateManager`
- change master authority
- change play, pause, track, timing, autoloop, or lighting behavior
- poll indefinitely
- justify authority promotion by itself

## Comparison And Authority Wording

Runtime comparison uses `comparison_source=tl_master_snapshot`.
`TLMasterSnapshot` tracks only TL-derived master sources:

- `tl_log`
- `engine_state`
- `initial_engine_state`

It deliberately ignores bridge-local or fallback sources such as `osc`,
`auto-detect`, and pause auto-switch paths.

Runtime log lines keep `authority=tl_log` as the fail-closed authority label.
For validation purposes, read this as: TL/ENGINE-derived state remains
authoritative, and direct master is observational only.

## Key Log Phases

Use only `[RBMASTER][RUNTIME]` lines for this validation.

- `phase=start`: observer configuration, including delay, window, interval,
  version, comparison source, and authority label.
- `phase=initial`: first direct read after attach.
- `phase=first_valid`: first readable direct value that maps to `deck1` or
  `deck2`, including elapsed seconds and TL snapshot value at that moment.
- `phase=mismatch`: first direct-vs-TL mismatch only. Repeated mismatches are
  counted in the summary, not logged every poll.
- `phase=summary`: final decision-quality result for the bounded window.

## Summary Fields

The summary line is the primary live-validation artifact.

- `attempts`: number of direct reads attempted inside this observer run.
- `outcome`: final bounded-window classification.
- `supported_version`: `1` when the current Rekordbox version has offsets.
- `readable`: `1` when the direct path was readable at the summary point.
- `version`: Rekordbox offset version used by the observer.
- `first_valid_master`: first direct master that mapped to `deck1` or `deck2`,
  or `none` if direct master never became valid.
- `final_direct_master`: final direct master label at window end.
- `final_raw`: final raw direct byte, or `-` when unavailable.
- `final_tl_master`: final TL-only snapshot value at summary time.
- `tl_master_at_first_valid`: TL-only snapshot value when direct first became
  valid, or `none` if TL had no deck then.
- `first_valid_elapsed_s`: seconds from observer attach to first valid direct
  master, or `-` if direct never became valid.
- `transition_count`: count of valid direct-master deck states observed as
  transitions. It is `0` if direct never became valid, `1` at first valid
  direct deck, `2` after one legitimate direct deck change, and `3+` indicates
  repeated valid direct instability.
- `mismatches`: number of valid direct polls where TL snapshot was also valid
  and direct master did not equal TL master. Only the first mismatch gets a
  dedicated `phase=mismatch` log line.
- `comparison_source`: should be `tl_master_snapshot`.
- `authority`: should remain `tl_log`.

## Outcomes

- `read_failed`: offsets were unsupported, attach failed, or the direct chain
  became unreadable. This is a direct-read status, not a master authority
  decision.
- `never_became_valid`: direct path was readable, but stayed at no-master
  sentinel for the whole bounded window.
- `became_valid_and_matched_tl`: direct became valid and no valid direct-vs-TL
  mismatches were observed.
- `became_valid_but_mismatched_tl`: direct became valid, TL was available at
  first valid, and at least one valid direct-vs-TL mismatch was observed.
- `became_valid_without_tl_available`: direct became valid before the TL-only
  snapshot had `deck1` or `deck2` at first-valid time. The summary still reports
  `final_tl_master` for interpretation.
- `flapped`: direct master was unstable. This means direct returned to
  `none` after first valid, or more than one valid direct deck transition was
  observed inside the bounded window. A single intentional master switch should
  produce `transition_count=2` and should not be classified as `flapped`.

Outcome priority is exact: `flapped` wins over mismatch outcomes, and
`became_valid_without_tl_available` is based on TL availability at first-valid
time.

## Live Test Scenarios

### 1. Startup Into Playback

1. Load and start normal playback in Rekordbox.
2. Start the bridge.
3. Watch `/tmp/bridge.log` for `[RBMASTER][RUNTIME]` lines.
4. Confirm `phase=start` appears after startup and shows
   `comparison_source=tl_master_snapshot`.
5. Use `phase=summary` as the final result.

Expected healthy direct-path result:

- `outcome=became_valid_and_matched_tl`
- `final_direct_master` matches `final_tl_master`
- `mismatches=0`
- `authority=tl_log`

If direct stays sentinel, expect `outcome=never_became_valid`; this remains
fail-closed and does not change bridge behavior.

### 2. No Master Change During Window

1. Start the bridge with a known master deck.
2. Do not change Rekordbox master for at least the runtime window.
3. Read the summary line.

Expected stable result when direct master is readable:

- `transition_count=1`
- `mismatches=0`
- `final_direct_master` equals `final_tl_master`
- `outcome=became_valid_and_matched_tl`

If `transition_count` is greater than `1` without an intentional master switch,
that is evidence of direct-master instability.

### 3. Intentional Master Switch During Window

1. Start the bridge.
2. During the bounded runtime window, intentionally switch master once between
   deck 1 and deck 2.
3. Read the summary line.

Expected result for a clean single switch:

- `transition_count=2`
- `final_direct_master` equals the new direct master
- `final_tl_master` equals the new TL-only snapshot, if TL caught up
- `mismatches=0` if direct and TL agreed at each valid sampled point
- outcome should not be `flapped` for one legitimate switch

If the summary shows `mismatches>0`, inspect whether the mismatch was a real
disagreement or a timing race between the direct byte and TL/ENGINE snapshot.
If the summary shows `flapped`, direct master changed too many times or returned
to `none` after first becoming valid.

## Stop Rule

This validation can show whether the direct master path is readable, stable, and
corroborated against TL-only master state during a bounded window. It is not, by
itself, approval to promote direct master authority or change bridge behavior.
