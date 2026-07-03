---
doc_status: active-analysis-prompt
truth_level: capture-grounded
last_verified_commit: 3312c40
last_verified_date: 2026-06-29
validation_scope: read-only offline analysis prompt for two sealed T7d scout captures; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no bridge restart, no pack enable, no SoundSwitch project mutation, no hardware/DMX/MIDI/Enttec operation
---

# Deep analysis prompt - T7d normal-mix scout captures

You are an offline analysis agent in `/Users/bbui/rb_ss_bridge_v2`. Analyze the two
sealed T7d normal-mix scout captures and decide what evidence can be promoted into
RW7/T7d autoloop coverage, what remains scout-only, and what targeted captures are
still required.

This is **analysis only**. Do not restart the bridge, do not toggle pack output, do not
open MIDI/serial/Art-Net/Enttec/DMX devices, do not mutate the SoundSwitch project,
and do not ask the operator to perform live actions. Use local files, local parsers,
`editcap`/`tshark` if useful, code inspection, tests, and GhidraMCP only when it
answers a concrete static question that changes interpretation of captured evidence.

## Inputs

Primary capture runs:

1. `tools/ssfmt/captures/t7d/t7d_scout_mix_20260629_161931`
   - Clean scout run.
   - `scout_analysis.md` exists.
   - `summary.json` verdict: `SCOUT_CAPTURED`.
   - Project before/after hashes matched.
   - `session.jsonl` has a clean `phase_trace_footer`.
   - `artnet_classic.pcap` exists for the local parser.

2. `tools/ssfmt/captures/t7d/t7d_scout_mix_cont_20260629_163143`
   - Continuation scout run.
   - `continuation_analysis.md` exists.
   - `summary.json` verdict: `SEALED_SHUTDOWN_CLOSED_SCOUT_CAPTURE`.
   - `session.jsonl` has no `phase_trace_footer`; the bridge log has `[REC] session-capture`
     closeout followed by shutdown.
   - Project before/after hashes do not match: SoundSwitch added one
     `automation_presets/PRESET 1.sspreset` and four `recordable/*.dat` files.
   - `artnet_classic.pcap` exists for the local parser.

Required reference files:

- `docs/prompts/active/soundswitch_rw7_capture_agent_prompt.md`
- `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md`
- `tools/t7d_capture_conductor.py`
- `docs/architecture/active_deck_authority.md`
- `active_deck_resolver.py`
- `state_manager.py`
- `autoloop_controller.py`
- `tools/ssfmt/re/parse_artnet_pcap.py`
- `tools/ssfmt/re/validate_autoloop_capture.py`
- `tools/ssfmt/captures/t7d/coverage_sidecar_20260629.md`

## Current contract caveat

Use the current active-deck contract, not stale master-switch wording. The bridge now
uses mixer authority for active deck selection:

- Rekordbox master is retained as `rb_master_deck`.
- `active_deck` follows the audible/dominant mixer state.
- Rekordbox master only resolves ties/fallbacks when mixer authority cannot pick a
  dominant deck.

Therefore, an old RW7 `master-switch` requirement that expects
`trigger=master_changed` is probably stale. Reframe it as **active-deck handoff under
mixer authority** if code and docs confirm that interpretation. Cite exact code/doc
anchors for this decision.

## Known scout facts to verify, not blindly trust

First run, `t7d_scout_mix_20260629_161931`:

- pcap packets: `37760`; Universe-0 frames: `17906`.
- session rows: `header=1`, `event=15574`, `position=79254`,
  `live_bpm=79241`, `autoloop_phase=79045`, `phase_trace_footer=1`.
- marker counts inside active session:
  `[SM] switch=3`, `active_deck_changed=3`, `arm-autoloop=3`,
  `arm-immediate=3`, `midi-refire=34`, `AUTOLOOP-TICK=34`,
  `buildup_to_drop_window=12`, `drop_crossing=16`, `post_drop=433`,
  `[LX] fired=36`, `same-scene-refire=5`, correction markers `0`,
  push-loop errors `0`.

Continuation run, `t7d_scout_mix_cont_20260629_163143`:

- pcap packets: `70556`; Universe-0 frames: `33460`.
- session rows: `header=1`, `event=30532`, `position=129861`,
  `live_bpm=114705`, `autoloop_phase=129186`.
- phase rows by active deck: Deck 1 `72697`, Deck 2 `56489`.
- marker counts inside active session:
  `[SM] switch=12`, `active_deck_changed=9`, `arm-autoloop=9`,
  `arm-immediate=9`, `midi-refire=56`, `AUTOLOOP-TICK=56`,
  `buildup_to_drop_window=29`, `drop_crossing=25`, `post_drop=592`,
  `[LX] fired=63`, `same-scene-refire=14`, correction markers `0`,
  push-loop errors `0`.

Treat these as starting facts. Recompute anything that affects the verdict.

## Analysis tasks

1. Verify run integrity.
   - Confirm all required files exist and are nonempty.
   - Confirm `artifacts.sha256` matches current run files, or report the mismatch.
   - Confirm `project.before.sha256`/`project.after.sha256` match for the first run.
   - For the continuation run, preserve the project-change and missing-footer warnings.
   - Confirm AppLogs were copied and identify their time coverage.
   - Confirm `artnet.pcap` is pcapng/raw and `artnet_classic.pcap` is parser-readable.
   - Confirm no `push loop error`, traceback loop, or recorder write failure occurs inside
     the active capture windows.

2. Build a timeline.
   - Segment each run by recorder start/stop or shutdown close.
   - Align `bridge.log`, `session.jsonl`, pcap timestamps, and AppLog windows.
   - Produce exact anchors: file path, line number or timestamp, and what happened.
   - Separate Deck 1, Deck 2, and idle/zero-active-deck periods.

3. Reclassify RW7 scenario coverage.
   - `arm`: look for active-deck entry, `arm-autoloop`, `arm-immediate`, stable BPM/beat,
     and subsequent `[LX] fired` / `AUTOLOOP-TICK`.
   - `refire`: look for repeated same-scene or 32-beat/marker-relative MIDI refire evidence
     plus corresponding Art-Net frame changes.
   - `master-switch`: decide whether to rename to mixer-authority active-deck handoff.
     Validate both directions and tie/fader/bass-dominance cases if present.
   - `buildup`: require `buildup_to_drop_window`, role `buildup`, scene/note identity,
     and enough pre-drop phase context.
   - `drop-hold`: require buildup window, `drop_crossing`, post-drop/hold evidence, same
     active deck/track identity, and Art-Net/AppLog corroboration.
   - `correction`: do not force acceptance. If no `arm-grace-late`,
     `arm-correction-pending`, or `arm-correction-clear` markers exist, determine from code
     and docs whether this scenario is stale/unreachable under current immediate-arm behavior
     or simply not captured.

4. Verify identity and BPM coverage.
   - Extract track identities, content ids, file names, BPMs, deck, and active-deck-change
     reasons from `bridge.log` and session rows.
   - Map fired scenes/notes to SoundSwitch autoloop identities where possible.
   - Determine whether at least three identities are represented.
   - Determine whether the same identity appears across two BPM/pitch contexts.
   - Check whether the previous holdout identity (`SSAutoLoop18.ssfile`, if still the
     documented holdout) was accidentally used; if yes, mark holdout contamination and propose
     a new holdout.

5. Use GhidraMCP only for concrete static questions.
   - Good uses: identify SoundSwitch runtime constants, beat-window behavior, callsite bounds,
     or binary behavior that helps interpret a captured artifact.
   - Bad uses: replacing passive Art-Net/AppLog/phase evidence, claiming
     `PASS_T7D_PHASE_CONTRACT` from binary evidence alone, or broad x86_64 parity work.
   - If GhidraMCP is unavailable or not useful, state that and continue with local evidence.

6. Produce verdicts and next actions.
   - Use one of:
     `PROMOTABLE_TO_RW7_ACCEPTED`, `ACCEPTED_FOR_SCOUT_ONLY`, `INCOMPLETE`, `FAIL`.
   - Explain each verdict with exact evidence and exact missing pieces.
   - Do not count conductor `ACCEPTED` alone as final proof.
   - For any remaining capture, specify the smallest targeted live run needed and the exact
     semantic markers it must produce.

## Deliverable

Write one report, preferably under `docs/reports/` or a clearly named capture-sidecar file,
with:

- integrity table for both runs;
- timeline and active-deck-handoff table;
- scenario coverage matrix;
- identity/BPM/holdout coverage;
- GhidraMCP/static-analysis notes, if used;
- prompt/spec/code-contract drift findings;
- exact remaining targeted captures, if any;
- clear separation of verified evidence, scout-only evidence, and hardware-unvalidated claims.

End with an operator summary:

- what the bridge behavior evidence currently supports;
- what remains unchanged and hardware-unvalidated;
- how healthy behavior should look in bridge logs, Rekordbox reader state, SoundSwitch,
  lasers, and LEDs/Govee;
- what not to do live until a new operator-approved capture run is requested.
