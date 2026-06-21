---
doc_status: active-session-handoff
truth_level: capture-protocol-only
last_verified_commit: c6d1a50
last_verified_date: 2026-06-20
validation_scope: read-only research + operator-orchestrated passive captures; no bridge runtime, no SoundSwitch project mutation by the agent; hardware-unvalidated
---

# Codex/Agent Handoff — B2: Operator-Ping Capture Campaign for Scripted-Renderer Closure

Paste this whole file into a fresh session opened at `/Users/bbui/rb_ss_bridge_v2`.
This is the **B2** follow-on to
`docs/plans/active/soundswitch_scripted_renderer_closure_handoff_spec.md`
(read that spec's Part A–E and its "Session Progress and Blockers" section first).
B1 (offline analysis) is exhausted; the remaining work needs live evidence that
**only the operator can produce**.

## Mission

Run a small set of **operator-orchestrated passive Art-Net captures**, each with a
**written byte-level prediction beforehand**, to resolve the four open items B1
could not close offline. Do all prediction/analysis yourself; the operator only
performs physical/playback actions you request and runs `tcpdump`.

## Absolute live-safety boundary (do not violate — these are hard rules)

- Do **not** start, stop, restart, toggle, or kill the bridge. The operator owns
  that. Verify health read-only only: `pgrep -f rb_ss_bridge_v2 | wc -l`
  (menubar/Laser Pad/wrapper/command processes are not extra workers).
- Do **not** send MIDI, OS2L, Art-Net, DMX, serial, or Laser Pad output.
- Do **not** run `tcpdump` yourself — give the operator the exact command; they
  run it in their terminal.
- Do **not** modify `~/Music/SoundSwitch/default.ssproj` or any live project.
  Mutation captures use an explicit **scratch copy** the operator opens; you only
  read copies.
- Do **not** change bridge runtime modules, the Enttec daemon, or the VLN adapter.
- Passive Art-Net is **software/wire evidence only** — never claim physical-laser
  or hardware validation.

## Operator-ping protocol (repeat for every capture)

1. Pick a fresh `/tmp/<descriptive>.pcap`; prove it absent (or hash any prior
   file). Hash the project inputs, current AppLogs, and `/tmp/bridge.log` to
   establish a baseline **before** pinging.
2. Post one visible message beginning exactly:
   `OPERATOR ACTION: confirm fixtures are safe.` then the exact
   `sudo tcpdump` command and **one** playback/transport/edit action only.
3. Speak the same action with macOS `say` **after** the baseline is taken.
4. Monitor pcap size, AppLog mtime, bridge mode/position, and project hashes —
   **never wait for a chat reply**.
5. Take a fresh baseline before each subsequent `say` ping.
6. At close, separately request Ctrl-C and copied AppLogs/bridge log; hash every
   artifact. Re-verify bridge health read-only.

Write each prediction to disk (`/tmp/<name>_prediction.json`) **before** the ping;
after the capture, diff prediction vs wire and record the result with hashes.

## Captures to run (in order; each needs its prediction written first)

### Capture 1 — Effect-cue reference mutation (resolves B1's open item)

**Why:** B1 proved the renderer (`one_based` + per-track dictionary, layered
identity buffer) is byte-exact for all non-effect cues, but a small per-file set
of **effect-cue references** (New Sky `raw∈{1,2,3,13}` = STROBE/MASTER STROBE/
INTENSIFY/BUILDUP SPEEDUP; TITANIUM `raw∈{24,196,211–215}`; Opalite
`raw∈{1,3,4,18,50,52}`) resolve to the wrong/absent cue under every offline rule
(one_based, direct, position, catalog-ordinal, transform — all falsified with
data). At least one (New Sky raw2 → stable CH11=227) points to a cue **not in the
file's own dictionary**. The byte-signature matches MIXED/edited provenance.

**Goal:** determine whether these are MIXED-edited records or a missing reference
indirection. On a **scratch copy** of `default.ssproj`, have the operator open
SoundSwitch, then in a scripted track re-place / re-save one known effect cue
(e.g. MASTER STROBE) at a known timeline position and save.

**Prediction to write first:** the exact `{SSID}.ssfile` byte offset(s) of the
edited timeline record and what its `raw_cue_reference` byte (high byte of the
LE u32 at record+12) is **now**, and whether a pure one_based read would place
MASTER STROBE there. Predict whether, post-edit, the reference byte becomes the
**direct** cue_index (MIXED hypothesis) or stays one_based (indirection
hypothesis).

**Operator actions (separate pings):** (a) snapshot/hash the scratch `.ssproj`
before; (b) open SS + re-place the one effect cue + save; (c) copy + hash the
edited `.ssfile`. Then you diff the timeline record bytes against the prediction.
A short passive playback capture of just that cue confirms the wire.

### Capture 2 — Transport: pause/resume + unload-from-active-frame

Pause/resume at the already-exact Opalite **180.203 s** base-render state, then in
a separate action **unload directly from an active exact frame** (not after a
stop). Predict the exact 19-byte Universe-0 frame at 180.203 s (from the
validated render) and the all-zero clear on unload; measure the clear latency.

### Capture 3 — DIRECT-discriminating reference track

One existing **unmodified** controlled DIRECT candidate whose direct vs one_based
rendered frames differ on multiple stable channels. Write its source hash,
project path, AppLog-resolvable SSID, predicted direct frame, predicted one_based
frame, and the discriminating channels **before** playback. (If no trustworthy
existing DIRECT candidate exists, report that specific authority blocker — do not
modify a live project to create one.)

### Capture 4 — Holdout (only after 1–3 pass)

A previously untouched real scripted holdout: BLACKPINK/JUMP (`1FD042ED`) or clean
Where Have You Been (`528E8B22`). Freeze the renderer + tests first; require
full-frame event+position parity on both mirrored groups (`0x493`/`0x496`) with
**no** rule changes. If it fails, return to offline analysis — do not patch a
track exception.

## Invariants (must hold)

- Exactly one bridge worker process; no runtime/project/config/MIDI/DMX/Enttec
  change by the agent.
- Universe 1 stays zero; Universe-0 CH1–19 is the compared surface; groups
  `0x493`/`0x496` evaluated independently.
- Captured frames are oracles, never renderer input. MIXED/ambiguous files fail
  closed before rendering.
- Status remains **SOFTWARE/WIRE-VALIDATED ONLY — PHYSICAL HARDWARE-UNVALIDATED**.

## Reference artifacts (verify hashes before relying on any)

- Venue SHA `f34bfc796e9e589c7eb4707ee4f223c6ea6fd2f597d08622d30370f16a2a3398`.
- SSAutoLoop1 SHA `13e085b2e7c47f471af0fda5d605d7c873374e9a2c3b25d96667689fc7b7cf48`.
- New Sky `{AE9E3C61-…}.ssfile` SHA `b136912ef09111b265c596cf0833b794aa521b5fb2af7ed9c5a58ada9a2b2b9c`.
- Opalite `{74044FA4-…}.ssfile` SHA `53e7b70656eb622d67be9b5d528612baa30cb261f510be62f0f50adee19de897`.
- TITANIUM `{FC10FC02-…}.ssfile` SHA `4c365b8084098b2488944d0aaf3389b0d8fa694da1a3ca406d84647efb027953`.
- Fixture channel map (group 0x493, profile `b8ad2201…`): 1 On/Off, 2 Auto Mode,
  3 Static Pattern, 4 Static Pattern Selection, 5 Pattern Size, 6 Horizontal
  Adjustment, 7 Vertical Adjustment, 8 Color, 9 Color Speed, 10 Pattern Line,
  11 Strobe, 12 Rotation Z, 13 Rotation X, 14 Rotation Y, 15 Horizontal
  Movement, 16 Vertical Movement, 17 Zoom, 18 Gradient, 19 X/Y Wave.

## When you finish

Report per-capture: prediction vs wire result, all artifact/source hashes, the
MIXED-vs-indirection verdict for the effect-cue references, transport edge
results with clear-latency, the DIRECT-track discrimination, and the holdout
parity. Update every `soundswitch_research.docs_update` file. Do not mark the
runtime exporter implemented; do not claim hardware validation.

## Session progress — 2026-06-20 (HEAD c6d1a50, no repo code changed; analysis only)

Operator steer this session: **"use existing projects, don't make a new one."**
Honored. All work below is read-only byte analysis of existing artifacts; no new
scratch project, no bridge/SoundSwitch/MIDI/DMX/tcpdump action by the agent.
Bridge verified healthy read-only: exactly ONE worker (PID 60279), idle
`autoloop`. Live `.ssfile` hashes re-verified (New Sky `b136912e…`, Opalite
`53e7b706…`, TITANIUM `4c365b80…`).

### Capture 1 — RESOLVED from existing controlled-mutation corpus (no new capture)

Verdict: **MIXED-edited confirmed; missing-indirection hypothesis REFUTED.** The
prediction (a placed/edited effect cue carries a DIRECT `cue_index` byte ⇒ MIXED)
is **confirmed** by the WHYB before→after pair under `/tmp/soundswitch_finish_IiVlD1`:

- WHYB-BEFORE `{528E8B22…}.ssfile` sha `1f740632…` (dict 196, timeline 136) →
  WHYB-AFTER sha `63302346…` (dict **233 full bank**, timeline 137).
- Editing **renumbered `cue_index` bytes** (STROBE 2→3, MASTER STROBE 3→2) and
  **rewrote the references to track the renumbering**: the three MASTER STROBE
  records changed `raw 3→2` to keep pointing at MASTER STROBE by DIRECT
  `cue_index`. One added record `raw=21` = DIRECT `cue_index 21` = RED.
- Therefore `cue_index` is **not a stable identity** (GUID is); edited files mix
  numbering bases with **no per-record byte discriminator**. No indirection table
  appears anywhere in the controlled corpus.
- New Sky's anomalous effect refs `{1,2,3,13}` (e.g. `raw2` wire=WHITE DOT STROBE,
  whose GUID is absent from New Sky's own 104-cue dict) are this MIXED signature.
  Note: dict size is NOT a discriminator — A5 has the full 233 bank yet is
  wire-proven one_based; convention is structurally ambiguous (every live scripted
  file fits one_based AND direct), so fail-closed is correct and now
  mechanism-grounded.
- Artifacts: prediction `/tmp/b2_capture1_effectcue_mutation_prediction.json`;
  result `/tmp/b2_capture1_RESULT.json`; tools `/tmp/b2_whyb_diff.py`,
  `/tmp/b2_whyb_diff2.py`, `/tmp/b2_classify_scripted.py`.

### Captures 2–4 — predictions staged; genuinely need operator wire (next session)

- **Capture 2 (transport unload-from-active-frame):** predicted Opalite frame at
  180.203 s = `[17,0,17,0,0,138,131,165,255,0,0,0,0,0,179,0,0,72,24]` (CYAN AND
  BLUE, raw_ref 18 @176974 ms; both groups mirror; A8 already proved this seek
  exact); unload ⇒ all-zero. Confirmed the existing transport pcap ends in a
  `stop` at elapsed 35.9 s — it has **no** direct unload-from-active-frame, so the
  clear-latency measurement needs a new live capture. Prediction:
  `/tmp/b2_capture2_transport_prediction.json`.
- **Capture 3 (DIRECT-discriminating track):** **authority blocker (evidence-backed).**
  No structurally direct-discriminating *unmodified* candidate exists — every live
  scripted file classifies `ambiguous_both_fit` (`/tmp/b2_classify_scripted.py`),
  and the only pure-direct files are freshly *created* ones (ST-ADD/SCRIPT-CREATE),
  not existing-unmodified. Per Task 4.4, report the blocker; do not modify a live
  project to manufacture one.
- **Capture 4 (holdout BLACKPINK/JUMP `{1FD042ED…}` sha `cc59b3d1…`):** prediction
  **COMPUTED** (`/tmp/b2_capture4_blackpink_prediction.json`, via
  `/tmp/b2_capture4_blackpink.py`): dict 119, timeline 112, **structurally clean
  one_based — all 91 cue-refs resolve, 0 unresolved** (contrast New Sky), both
  groups `0x493`/`0x496` mirror, 112 event frames oracled. Only the live
  full-track passive playback remains (operator-gated) to confirm wire parity.

### Exact next operator actions (all use the LIVE project; no scratch)

1. Re-run `/tmp/b2_capture4_blackpink.py` to emit the BLACKPINK prediction.
2. Capture 4 ping: `sudo tcpdump -i lo0 -w /tmp/ss_holdout_blackpink.pcap udp port 6454`,
   then play BLACKPINK/JUMP start→finish, then Ctrl-C + copy AppLogs/bridge.log.
3. Capture 2 ping: same tcpdump to a fresh pcap; play Opalite to a steady frame,
   then **unload while actively playing** (not after stop); measure clear latency.
4. Then validate with `validate_scripted_capture.py --reference-rule one_based
   --control-channels 8,9,11` on both `0x493`/`0x496`, diff vs the staged
   predictions, and update `soundswitch_research.docs_update` docs.

Note: `/tmp/b2_*` analysis artifacts are local-only (not in git).
