# SoundSwitch Tasks 4–6 — Sonnet 4.6 orchestration handoff

> Open a fresh **Claude Sonnet 4.6 (high)** session in the `rb_ss_bridge_v2` repo and paste the
> block below. **High** is recommended over medium: Task 5 carries MIDI-parity regression risk
> and Task 6 requires byte-equivalence to the VLN reference.
>
> Produced after a code-verified adversarial review of Tasks 0–2 (all APPROVE; minor cleanup
> items carried forward below) and the Opus review of Task 3 (APPROVE). At handoff time:
> branch `soundswitch/impl`, PR #115, proof gate `PASS_IMPLEMENTATION_MAY_BEGIN` (28/0/1, the
> lone INCOMPLETE is `F10`, which Task 4 closes).

---

```text
You are the Orchestrator continuing the SoundSwitch importer/exporter/player effort.
Drive Tasks 4 → 5 → 6 to completion via implement → review → gate cycles, then STOP at
the after-T6 milestone gate. Do NOT touch StateManager/startup/200 Hz (that is T7).

AUTHORITY (in order; code wins over docs):
1. Code (*.py) + tests/.
2. Spec (the only implementation authority):
   docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md
   — read Task 4 (L414), Task 5 (L442), Task 6 (L470), Part C (L699), D (L718),
     E (L752), F-7/F-8/F-10, and adversarial targets #1,#6,#7,#8.
3. The full orchestration protocol you must follow:
   docs/plans/active/soundswitch_orchestration_prompt.md  (bootstrap §3, per-task loop §5,
   milestone gates §5a, gates §6, delegation/effort §7, STOP conditions §10).
4. AGENTS.md + CLAUDE.md.

CURRENT STATE (verify, don't trust):
- Branch soundswitch/impl, running PR #115. Tasks 0–3 are done, reviewed (T3 by Opus),
  committed and pushed (HEAD ~168ce70). Ledger: docs/plans/active/soundswitch_impl_progress.md.
- Proof gate at HEAD = PASS_IMPLEMENTATION_MAY_BEGIN, 28 PASS / 0 FAIL / 1 INCOMPLETE.
  The lone INCOMPLETE is F10-active-cc-override — your Task 4 converts it to a mandatory PASS.

BOOTSTRAP (run first, every session): git status / git log -8 / gh pr view 115;
re-run the proof gate + hard checks; read the ledger's "Next action"; confirm gate inputs
exist (~/Music/SoundSwitch/default.ssproj). Then resume at Task 4.

SCOPE & EFFORT:
- T4 soundswitch_midi_input.py (+tests) — HIGH. Note-on vel 0 → note-off; exact device/
  type/zero-based-channel/data-byte match; bounded NONBLOCKING mailbox; NO MIDI API in
  _push_tick; override note-on selects slot, note-off releases only if still current,
  repeated note-on idempotent; disconnect/worker-death/stale/shutdown/reload/panic → clear
  held + force zero. F10: an active Static Override/Autoloop learned to CC/pitch must FAIL
  EXPORT with a relearn instruction (implement, don't defer). Rerun the proof gate; F10 PASS.
- T5 laser_output_backend.py + refactor LaserSceneExecutor onto the protocol — HIGH
  (regression risk). Existing MIDI adapter stays DEFAULT and byte/order-identical: exact
  calls, pulse/hold ordering, cooldown gates, random role-bank rotation, blackout owner
  refcounts, and ALL existing laser tests must still pass. A gated/cooldown-skipped/rejected
  scene must NOT advance pack selection; unlearned scene = no-op; none/dry-run backend emits
  no new output.
- T6 enttec_dmx_pro.py + soundswitch_frame_sender.py (+tests) — HIGH, SOFTWARE/LOOPBACK ONLY.
  VLN reference IS PRESENT: ~/virtuallasernode/calib/dmx_pro.py (+ test_dmx_pro.py). Port/adapt
  it; do NOT import VLN as a runtime dep, do NOT modify VLN, do NOT re-derive from scratch.
  build_dmx_packet byte-equivalent: 0x7E|label6|len_lsb|len_msb|start_code(0x00)+512|0xE7,
  513 LE payload; blackout 518 bytes; add a byte-equivalence test (or justify divergence).
  Zero packet on idle/stale/error/stop/SIGINT/SIGTERM/shutdown. DOCUMENT the kill -9 Enttec
  last-frame hazard (firmware repeats last frame; physical kill is the true failsafe) — do
  NOT claim software fail-safe kill -9. CH1-CH19→512 expansion comes from the reviewed fixture
  map, never name inference. NO serial/Enttec/MIDI device opened in any test.

HARD RULES (§2/§10): open NO hardware (MIDI/serial/Art-Net/Enttec/DMX) in code you run or
tests; never restart the bridge; never mutate the SoundSwitch project; production code must
not import tools/ssfmt/re/; pack mode stays default-off/dry-run; DMX and MIDI-laser output
mutually exclusive. STOP and ask on ambiguity, scope creep beyond 2.10.3/canonical UUID/RAVE/
Universe 0 CH1-CH19, or any device-open/restart step. If VLN ever becomes unavailable, T6 blocks.

PER TASK: contract is already in change_contracts.yml (soundswitch_pack_player) — confirm it
covers your files. TDD from spec Part D/E. Self-gate: targeted tests + hard checks
(check_docs_metadata / check_agent_contracts / check_docs_drift) + git diff --check; rerun the
proof gate after any SoundSwitch-semantics change; run `unittest discover tests` before pushing.
Then a fresh-context adversarial review (cross-model preferred) per the review pack
docs/plans/active/soundswitch_review_pack.md (gate T6) before you mark a task done. Commit each
task on soundswitch/impl, push to PR #115, update the ledger. Honest reporting: paste real
gate output; two suite failures (test_led_color_engine_m2_patch_c/d/phase3, test_runtime_status)
are pre-existing/CI-only — confirm you added no NEW failures.

MILESTONE: after T6, finish the in-flight task, push, set the ledger "Next action" to
"AWAITING OPERATOR: review I/O surfaces + MIDI parity (PR #115); before-T7 is a live-safety
gate", report crisply, and STOP. Do not start T7.

CARRY-FORWARD from the T0–T3 review (NOT T4–6 blockers; address at/by T8):
- Pre-rendered pack boundaries are stored-order; the player renders time-filtered. They
  coincide on the canonical project, but T8 shadow mode must compare against the PLAYER's
  output (or re-derive expected frames in time order), not assume boundary[i]==player(time[i])
  for the 4 out-of-time-order docs (SSAutoLoop47 active, SSAutoLoop9, two inactive scripts).
- Render logic is triplicated (soundswitch_pack.py / soundswitch_pack_verifier.py /
  soundswitch_laser_player.py); keep any cue-rule change in sync across all three.
```
