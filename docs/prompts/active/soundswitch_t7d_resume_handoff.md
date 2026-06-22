---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: ed96b41
last_verified_date: 2026-06-22
validation_scope: next-agent T7d resume handoff prompt; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Next-agent handoff — finish T7d capture pass → derive contract → implement native autoloop DMX

You are taking over the **T7d** workstream in `/Users/bbui/rb_ss_bridge_v2` (branch
`soundswitch/impl`, PR #116). **Scope (operator-chosen): (a)** finish the live capture pass,
derive the proven phase contract, and — only if the evidence passes — implement the native
autoloop→DMX runtime. (The separate "chorus drop-look cycling" laser spec at
`docs/plans/active/chorus_drop_cycling_spec.md` is NOT your job here; it goes to Codex
separately. It does not change T7d.)

---

## 0. READ THIS FIRST — corrected architecture model (the prior agent got this wrong)
Do not re-derive this from scratch or quiz the operator on it; it is verified against code.

**The bridge drives SoundSwitch over two independent channels:**
1. **OS2L over TCP** (`osl_output.py`) — transport/loop/position state as `{"evt":"subscribed",...}`
   triggers + `{"evt":"beat",...}` events. Outbound only; the bridge reads Rekordbox directly,
   not via SS.
2. **IAC MIDI notes** (`laser_executor.py` → `laser_output_backend.py` → `midi_output.py`) —
   selects *which* look/autoloop SoundSwitch plays.

**How an autoloop actually works (this is what T7d must reproduce):**
- **Arm** (unscripted track, no `SOUNDSWITCH_ID`): OS2L `deck N loop on` + `get_loop = AUTOLOOP_BEATS` +
  `play on` (`osl_output.py:312-317`, `send_deck_load`). `AUTOLOOP_BEATS=8` is **8 bars** in SS
  loop units (misnamed; it is bars, not beats) = **32 beats** = the look length.
- **Scripted track** (has `SOUNDSWITCH_ID`): OS2L `loop off`; SS runs that track's scripted show.
  *Scripted = scripted tracks; autoloop = non-scripted tracks.* No notes select scripted shows.
- **Look selection**: the **IAC MIDI note** the SS project maps to an autoloop — but it only does
  anything **while autoloop is armed**.
- **The bridge advances the autoloop itself**: it streams `get_beatpos` (= `abs_beat_pos`) **every
  push-loop tick** (`send_elapsed`, `state_manager.py:3862`) + beat events (`send_beat`, `:3729`).
  SS just renders the selected look **at that beat position** — scrubbing the track scrubs the look.
- **Static looks** are MIDI-note-mapped held DMX. (There are **no** "StaticOverride slots" — ignore
  any doc that says so.)
- The **SoundSwitch exporter / RE pipeline captures it all** (autoloop catalogs/looks, scripted
  `.ssfile`s, static looks + their DMX) = the pack; the **pack player = native DMX**.

**Therefore native DMX (T7d) = render the selected autoloop's frames at the tick derived from
`abs_beat_pos`** (within the 8-bar/32-beat loop, at the proven TICKS_PER_BEAT + phase origin). It
mirrors SoundSwitch *by construction* because the bridge already controls position via `beatpos` —
SS does nothing independent. In a fully-native world, **OS2L, the autoloop arm, and the scripted
arm become unnecessary *as SoundSwitch-facing outputs*** — but the internal state they encode
(`abs_beat_pos`, the autoloop/scripted/idle mode, the selected look identity, the scripted track
identity) stays essential; the bridge already computes all of it. Until native DMX is
hardware-validated and fully replaces SS, OS2L stays live (SS is still the renderer).

**Phase origin is role-agnostic.** The arm/refire timing that sets the phase origin is computed
purely from beat/marker/interval with **zero** references to lighting role/scene/note
(`autoloop_controller.py`; refire at `state_manager.py:3747-3768`; arm sync =
`next_arm_phrase` `:571`). So the origin depends on **transition TYPE** (arm / refire /
drop-crossing / master-switch / …), **not** on which look fires. This is why the capture pass
enumerates transition types as separate scenarios, and why the `refire` contract will also cover
future drop/post_drop cycling.

---

## 1. State as of this session
- **Captures ACCEPTED so far (overlap-valid):** `arm` **2/2** (`t7d_arm_20260622_145840`,
  `..._150103`), `refire` **2/2** (`t7d_refire_20260622_151420`, `..._151812`). Raw captures live
  under `tools/ssfmt/captures/t7d/` (gitignored). Coverage so far: BPMs **130 / 138 / 141**.
- **Remaining scenarios (2 ACCEPTED reps each):** `master-switch`, `drop-hold`, `buildup`,
  `correction`. (`correction` is provisional — keep it; if its `arm-grace-late`/`arm-correction-*`
  markers never appear across accepted runs, it doesn't fire in this rig and can be dropped.)
  `phrase-anchor` was **dropped** (dead in the live rig — `RBSS_PHRASE_ANCHOR` off).
- **Corpus coverage still needed** (plan §A4/§B6): ≥3 verified IAC identities, ≥2 BPM/pitch values
  (have 3 BPMs), ≥1 full holdout identity.
- **B1 phase-trace wiring is live in the running bridge** (verified this session via a smoke test:
  start recorder while playing → `autoloop_phase` rows + clean `phase_trace_footer`). If the bridge
  is restarted, re-verify (see the smoke test in the capture-gate handoff §6).
- **Conductor (`tools/t7d_capture_conductor.py`) was hardened this session** — these fixes are why
  the captures are trustworthy:
  - counts the single **python** core, not the menubar `| tee` shell wrapper (`f66b69f`);
  - **requires real playback** before ACCEPTED (clean footer + playing rows spanning
    min_window_beats) — no empty-trace rubber-stamp (`5b0b1a9`);
  - **requires pcap/playback temporal overlap** — playback must happen *while tcpdump is capturing*,
    else the oracle can't align arms→Art-Net (`f66117c`);
  - `T7D_CONDUCTOR_QUIET=1` silences the conductor's `say`/notification spam (`fa2addc`).

## 2. Binding protocols (do not violate)
- **Capture gates are active-wait, never stopping points** (capture-gate handoff §0): when you need
  a physical action, ping + poll + resume; never end your turn at a gate.
- **Operator-facing pings:** print the **exact copy-pasteable command in chat** AND fire **one short**
  `say` alert (no reading the whole command aloud). Always launch run-scenario with
  `T7D_CONDUCTOR_QUIET=1`. Tell the operator to **Ctrl-C the previous tcpdump before each scenario**.
- **Operator workflow that makes captures valid:** (1) start `sudo tcpdump` FIRST, (2) **then** play
  and keep playing through the whole window, (3) **keep the bridge's Terminal window open** — closing
  it kills the bridge (`[watcher] manual terminal closed; stopping bridge`) and fails the run.
- **Fail-closed:** every timeout/empty/non-overlapping run is INCOMPLETE — re-run, never reinterpret.
- **Live-safety:** no bridge restart / device output / MIDI-serial-Enttec-DMX open / SoundSwitch
  project mutation by you — operator actions; ping + poll. After any restart verify exactly one core.
- **Roles:** Codex implements bridge code; you do evidence/analysis/planning + (task-scoped operator
  override) the T7d runtime once evidence passes. Live-critical runtime work is **plan-first**.

## 3. Read (smallest path)
1. `AGENTS.md` (§1 source-of-truth order, §7 change contracts, §8 hard checks, §10 status language);
   `CLAUDE.md`.
2. `docs/plans/active/soundswitch_t7d_capture_gate_handoff.md` — capture protocol + §6 session log
   (restart gate, B1 smoke test, resume command, six-scenario table).
3. `docs/plans/active/soundswitch_t7d_capture_evidence_plan.md` — scenarios, coverage, B5 derivation,
   B3 markers (scope banner: six scenarios, phrase-anchor dropped).
4. `docs/validation/soundswitch_t7d_phase_contract_evidence.md` — the evidence ledger you will fill.
5. `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` — exporter/pack
   authority (what the pack/player captures).
Tools: `tools/t7d_capture_conductor.py` (prepare / run-scenario / validate-scenario /
summarize-corpus), `tools/ssfmt/re/validate_autoloop_capture.py` (oracle, `--t7d`),
`tools/ssfmt/re/t7d_phase_contract.py` (pure contract).

## 4. Mission, in order
### Phase 1 — finish captures (live, operator present)
`python3 tools/t7d_capture_conductor.py prepare` (expect green: 1 core, pack disabled). Then, per
remaining scenario, `T7D_CONDUCTOR_QUIET=1 python3 tools/t7d_capture_conductor.py run-scenario
<name> --run-stamp <YYYYmmdd_HHMMSS>`, driving the active-wait and the operator workflow above until
**2 ACCEPTED reps each** for `master-switch`, `drop-hold`, `buildup`, `correction`, plus the §A4/§B6
identity/BPM/holdout coverage. Track with `summarize-corpus`. Confirm each scenario's required
markers against real `bridge_fmt` output; refine `SCENARIOS[...]["required_markers"]` if a real run
shows a different exact string (tooling fix, not evidence reinterpretation).

### Phase 2 — derive the contract (offline, falsifiable)
Run the oracle per accepted segment: `cd tools/ssfmt/re && python3 validate_autoloop_capture.py
<run>/artnet.pcap --venue <verified-venue> --t7d --phase-trace <run>/session.jsonl --t7d-ssfile
<one immutable pack ssfile> --owner-deck <deck> --clock-offset <measured dual-timestamp residual>`.
Derive `TICKS_PER_BEAT` and the per-transition phase origin on a **holdout** (fit on some
identities/BPMs, confirm on held-out ones). **600 must be *earned* by the data** (= 19200/32 over the
8-bar/32-beat loop), never assumed; `validate_autoloop_capture.py` `rate=bpm*10.0` is circular and is
NOT proof. Because the origin is role-agnostic (§0), the per-transition-TYPE origins are what matter;
expect the `refire` origin to also cover future drop/post_drop cycling (verify, don't assume).

### Phase 3 — write evidence + decide the gate
Fill `docs/validation/soundswitch_t7d_phase_contract_evidence.md` (accepted/rejected/incomplete set,
hashes, ticks/beat tested, 600 pass/fail, winning quantizer, per-transition origin/reset/continue/snap,
tolerances, identity ownership, Universe-0 verification, project-hash, recorder drops, rejected
hypotheses, final verdict). If FAIL/INCOMPLETE: update
`docs/validation/soundswitch_t7d_phase_contract_blocked.md` and STOP — do not write a runtime spec
without passing evidence.

### Phase 4 — implement native autoloop DMX (ONLY if verdict == PASS)
Write `docs/plans/active/soundswitch_t7d_runtime_autoloop_dmx_implementation_spec.md` grounded
strictly in the evidence (proven TICKS_PER_BEAT, quantizer, per-transition origin, StateManager
integration, **safe-zero/precedence**, tests, rollback, sanitization). Then implement in
`state_manager.py` / pack driver so `_drive_pack_output` (`state_manager.py:~3209`) selects the
autoloop frame **only on the proven contract** — render the selected look's frames at the tick from
`abs_beat_pos` within the 8-bar loop. Preserve **safe-zero on every non-happy path**; never seed a
production constant from a capture/log/pcap. Pure-function seam for the phase math. Live-critical →
**plan-first** (review the spec before/with implementation). Run focused gates → full suite → doc
hard checks.

## 5. Hard constraints
- Active-wait gates; ping + poll; never stop at a gate.
- No bridge restart / device output / DMX-MIDI-serial open / SoundSwitch mutation by you.
- Do not choose `600`; do not seed production code from captures/logs/pcaps.
- No blocking I/O (network/socket/MIDI/serial/subprocess/sleep/contended-lock) in `_push_tick`.
- Repo status stays **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED** until a real operator
  hardware-validation gate says otherwise. A software/wire pass never upgrades it.
- AGENTS.md §7 change contracts + §8 hard checks for every code/doc edit.

## 6. Definition of done
Either: a complete evidence doc with verdict **PASS** plus a reviewed+implemented+tested native
autoloop→DMX behind safe-zero precedence; OR a precise `_blocked.md` stating exactly what
capture/derivation is still missing. State explicitly at the end whether native autoloop DMX is
implemented and that hardware remains unvalidated. Do not end with "ready for Codex" / "awaiting
implementation" for the capture+derivation work — you own that (operator override; live-critical stays
plan-first).
