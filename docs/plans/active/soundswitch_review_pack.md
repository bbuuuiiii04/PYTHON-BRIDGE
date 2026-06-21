# SoundSwitch implementation — Opus review pack

> **Operator:** open a fresh **Opus / Claude Code** session in the `rb_ss_bridge_v2` repo,
> attach this doc, and say e.g. *"review Codex's implementation of T3."*
> Valid targets: **T3**, **T6**, **before‑T7**, **T8**, **T9**. Opus reads §0–§2 (shared)
> plus the one gate section that matches.

---

You are an **adversarial, Opus‑tier implementation reviewer**. A coding agent ("Codex") has
implemented part of the SoundSwitch importer/exporter/player system. Your job is to decide,
with evidence, whether that work is correct, complete, live‑safe, and faithful to the spec —
or to send it back with specific findings. **Do not rubber‑stamp.** Assume Codex's prose
summary is optimistic; trust only code, tests, and gate output you verify yourself.

## 0. Review protocol (every gate)

- **Authority:** the spec is `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md`
  (the only active implementation authority). `AGENTS.md` governs (code wins over docs).
  Hold Codex to the spec's **Part B** (the task), **Part C** (invariants), **Part D** (tests),
  **Part E** (acceptance), **Part F** (hardening), and the **Adversarial self‑review targets**.
- **Read‑only and live‑safe.** You **review**, you do not implement fixes. During the review:
  do **not** edit code, restart the bridge, open any MIDI/serial/Art‑Net/Enttec/DMX device,
  or mutate the SoundSwitch project. Running tests, the proof gate, and `git`/`gh` read
  commands is allowed (they open no devices). If a step would, stop.
- **Method (in order):**
  1. Find the work: `gh pr view`/`gh pr diff` for the running PR (branch `soundswitch/impl`)
     or `git log`/`git diff` for the task's commits; read `docs/plans/active/soundswitch_impl_progress.md`.
  2. Read the matching spec task section(s) + Part C/D/E and the adversarial targets it cites.
  3. **Try to break it.** Walk each acceptance item and each adversarial scenario for the
     gate and actively look for the failure — don't just confirm the happy path.
  4. **Verify claims against artifacts** — run the gate/tests yourself (§1); read the code at
     the cited `file:line`; diff "what Codex says" vs "what the code does."
  5. Check the **universal invariants** (§2) still hold.
- **Honest test reporting.** Report exact output. Two failures are **pre‑existing and
  unrelated**: `test_led_color_engine_m2_patch_c/d` + `..._phase3` (5 errors — need the
  gitignored live `config/led_look_director.json`, absent in CI) and the order‑dependent
  `test_runtime_status` flake. Do **not** credit Codex for "fixing" them and do **not** let
  them mask a **new** failure in a module Codex touched (that is a regression — flag it).
- **No scope creep / no hardware claims.** Anything beyond SoundSwitch 2.10.3 / canonical
  project UUID / RAVE Venue / Universe 0 CH1‑CH19 / 19‑channel no‑intensity profile is a
  finding. Implementation completion is **not** hardware validation; status stays
  SOFTWARE/WIRE‑VALIDATED ONLY / HARDWARE‑UNVALIDATED.

## 1. Verification commands (run the ones the gate names; paste real output)

```bash
# Proof gate — gate on the final_verdict STRING (PASS_IMPLEMENTATION_MAY_BEGIN); nonzero exit also = blocked
python3 tools/prove_soundswitch_pack_generation.py \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir artifacts/soundswitch_pack_generation_proof

# Hard checks
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
git diff --check

# Tests — run the task's modules; run discover before a phase sign-off
python3 -m unittest tests.<module_codex_added>
python3 -m unittest discover tests

# Determinism spot-check where a pack exists (Task 2+): export twice, diff the trees
```

## 2. Universal invariants — confirm at every gate (spec Part C)

- `StateManager` is the only `DeckState` writer; reader threads publish events, never mutate.
- `_push_tick` (200 Hz) gains **no** blocking filesystem / MIDI / serial / network /
  subprocess / lock / sleep work. Pack I/O is worker‑owned + nonblocking mailbox.
- Laser **policy** and **execution** stay separate; existing MIDI‑laser behavior is byte/
  order‑equivalent under the MIDI backend; LED/Govee + OS2L unchanged when pack mode is off.
- Pack mode is **default‑off / dry‑run**; no implicit hot enable; DMX and MIDI‑laser output
  are mutually exclusive.
- Production modules do **not** import `tools/ssfmt/re/` (algorithms are ported + tested);
  captures are oracles only, never pack input or seeded state.
- No secrets / absolute paths / device IDs / live config / captures / project bytes / the
  gitignored proof reports are committed.
- Every stop / stale / error / reload / disconnect / shutdown path resolves **zero**, never a
  retained nonzero frame.

## 3. Verdict + finding format (end every review with this)

```
VERDICT: APPROVE | CHANGES-REQUIRED | BLOCKED (could not verify — say why)
GATES RUN: <commands + their real verdict/output lines>
VERIFIED: <acceptance items you confirmed against code/tests>
FINDINGS (most severe first):
  [blocker|major|minor|nit] <file:line> — <what is wrong> — <why it matters> — <fix>
INVARIANTS: <Part C items checked; any at risk>
ADVERSARIAL: <each scenario tried → held / broke (with evidence)>
SAFETY: confirm no device opened, no bridge restart, no project mutation during review.
```

APPROVE only when: every acceptance item is verified against code/tests (not prose), the
gate the phase requires passes, all adversarial scenarios held, no invariant is at risk, and
there are no `blocker`/`major` findings.

---

## Gate — **T3** (offline foundation: decode → export+verifier → renderer)

**Scope:** Tasks 1–3. Files to expect: `soundswitch_pack_models.py`,
`soundswitch_project_decoder.py`, `tools/export_soundswitch_pack.py`, `soundswitch_pack.py`,
`soundswitch_pack_verifier.py`, `soundswitch_pack_loader.py`, `soundswitch_laser_player.py`
and their tests. **Spec:** Part B T1/T2/T3, Part D, Part E, Part F‑1/F‑4/F‑5/F‑9/F‑10,
adversarial targets #1,#2,#3,#4,#9,#10. **Gate to run:** proof gate (must PASS) + hard checks
+ the new tests + a twice‑export byte‑diff.

**Try hardest to break these:**
- **Identity gate (T1.0):** a project with the **RAVE GUID but a different UUID** (the scratch
  corpus) is **rejected on UUID** — not authorized on Venue GUID [#9]. Verify in code + via the
  gate's `F1`.
- **232 + 1 = 233 split:** the catalog‑tail record is classified distinctly, **never rendered
  as a cue**, never counted among the 232, never crashes decode [#10]. Reject any "bare 232."
- **Verifier rejects a one‑byte pack mutation (F9):** actually implemented and passing — not
  a stub/TODO. Also rejects missing/extra artifact, count mismatch, noncanonical order,
  wrong UUID (even with RAVE GUID), drifted union SHA, source/profile mismatch.
- **Determinism:** two exports from identical bytes are **byte‑identical**; no timestamps in
  hashed content; canonical JSON + stable ordering. Run it twice and diff.
- **Pack retains raw truth:** raw fields, source offsets, raw/stored refs, resolved GUIDs,
  negative/clear classification, intensity nodes, unused static maps — **not only
  pre‑rendered frames.**
- **Reference rule:** `raw==0` → clear/control; `raw>0` → `raw-1` under the 2.10.3 one_based
  rule **after** the version gate; ambiguous/unversioned **fails closed**.
- **Renderer (T3):** outputs exactly **19 ints in 0..255**; precedence **emergency/blackout >
  held static override > base > zero**; releasing blackout/override **recomputes current base
  (no cached frame)** [#2,#3]; a new held override replaces the prior, releasing an old
  non‑current note doesn't clear the new slot [#1]; pack reload clears held + outputs zero
  [#4]; stop/end/unload/missing/stale → zero.
- **Sparse + history‑independent:** present channels update, omitted persist, raw‑zero clears
  main; intensity nodes retained but **not** output (no‑intensity profile); seek/backward/
  pause/refire recompute from immutable events (no order dependence).

## Gate — **T6** (learned‑MIDI input + backend MIDI‑parity + Enttec packet, software only)

**Scope:** Tasks 4–6. Files: `soundswitch_midi_input.py`, `laser_output_backend.py`
(+ refactor of `LaserSceneExecutor`), `enttec_dmx_pro.py`, `soundswitch_frame_sender.py`
and tests. **Spec:** Part B T4/T5/T6, Part D, Part E, Part F‑7/F‑8, adversarial #1,#6,#7,#8.
**Gate to run:** targeted tests + hard checks; **confirm no serial/MIDI device is opened in
any test.**

**Try hardest to break these:**
- **F10:** an **active** Static Override/Autoloop learned to **CC or pitch‑bend fails export**
  with a relearn instruction — implemented, not deferred. Note‑based current controls still
  work.
- **MIDI input safety:** note‑on velocity 0 → note‑off; exact device identity + message type +
  zero‑based channel + data byte match; override note‑on selects direct slot, **note‑off
  releases only if still current**, repeated note‑on idempotent [#1]; `CueBeat`/non‑render
  controls inventoried but never mutate the player.
- **Hot‑path purity:** no MIDI/serial API call anywhere reachable from `_push_tick`; events
  cross a **bounded non‑blocking mailbox**; exactly one worker owns the input.
- **Fail to zero:** device disconnect, worker failure, stale held input, shutdown, pack
  reload, panic → held state cleared and output forced **zero** before base resumes [#7].
- **MIDI‑parity (T5):** the existing MIDI adapter is the default and preserves **exact calls,
  pulse/hold ordering, cooldown gates, random role‑bank rotation, blackout owner refcounts,
  and existing tests**. A gated/cooldown‑skipped/rejected scene must **not** advance pack
  selection [#6]; an unlearned scene is a no‑op; default/none backend produces **no new
  output**.
- **Enttec packet (T6):** `build_dmx_packet` byte‑equivalent to the VLN reference
  `~/virtuallasernode/calib/dmx_pro.py` — `0x7e | label 6 | len_lsb | len_msb |
  start_code(0x00)+512 | 0xe7`, 513 LE payload; blackout 518 bytes; **byte‑equivalence test
  present** (or divergence justified). Zero packet pushed on idle/stale/error/stop/SIGINT/
  SIGTERM/shutdown. The `kill -9` last‑frame hazard is **documented**, not claimed fixed [#8].
  CH1‑CH19 → 512‑frame expansion comes from the reviewed fixture map (**no name inference**).
  No serial opened in unit tests.

## Gate — **before‑T7** (StateManager / startup / status / commands integration — LIVE‑SAFETY)

**Scope:** Task 7 — the integration into the runtime owner. This gate is **pre‑/at‑
integration**: review the design + the diff for live‑safety **before trusting it in the 200 Hz
runtime.** Files: `config/soundswitch_pack_player.example.json` + loader, `__main__.py`,
`state_manager.py`, `runtime_status.py`, command surface. **Spec:** Part B T7, Part C (all),
F‑8. **Gate:** hard checks + tests; confirm default‑off startup is behavior‑neutral.

**Try hardest to break these:**
- **`StateManager` discipline:** it calls **only pure player/controller methods + nonblocking
  frame submission**; it does **not** become a second deck/transport authority; it reuses
  `active_deck`, `DeckState.scripted_id`, `TrackMetadata.soundswitch_id`, elapsed/playing,
  lighting mode, beat/phrase, executor‑accepted selection.
- **Hot path:** absolutely no pack/config/file parsing, reload, or device I/O in `_push_tick`;
  pack/config are **loaded + verified before worker threads start** in `__main__.py`.
- **Transitions all resolve safe frames:** scripted/autoloop/idle, deck change, track load,
  stop/stale, config disable, pack reload, worker error, shutdown — each clears incompatible
  pending/held state and resolves zero or the correct base.
- **Default‑off neutrality:** with pack mode disabled, OS2L, MIDI‑laser, Rekordbox, LED/Govee,
  command, and status behavior are **unchanged** (diff the relevant paths; run existing tests).
- **No implicit hot enable:** any enable/reload/backend command follows the runtime‑command
  change contract, **validates first**, and requires an **explicit operator action**; an
  invalid reload keeps the old verified pack disabled or forces zero — **never a partial swap.**
- **Sanitized status:** never exposes audio paths, device names, or serial details.
- **Reversibility:** the change is rollback‑safe and does not alter the single‑bridge‑process
  requirement. (Do not restart the bridge to test — review the code path.)

## Gate — **T8** (offline + shadow verification gates — pre‑hardware go/no‑go)

**Scope:** Task 8. **Spec:** Part B T8, Part D, Part E, F‑5/F‑6, adversarial #5,#9,#10.
**Gate:** **rerun the proof gate (must PASS)**; run the full offline/shadow suite.

**Try hardest to break these:**
- **F9 and F10 are now COMPLETE and passing** (not deferred). Verify both directly — this is
  the gate where they convert from INCOMPLETE to mandatory PASS.
- Proof gate `PASS_IMPLEMENTATION_MAY_BEGIN`; pinned project UUID and the active‑cue union
  SHA‑256 `88a2e948…1d1b4f4a2` confirmed; wrong UUID rejected even when the RAVE GUID matches.
- **Two exports byte‑identical;** the independent verifier **rejects every adversarial
  mutation** you throw at it (one‑byte flip, missing/extra artifact, count off, reordered).
- **Totals all hold:** 42/42 Autoloops; 44/45 scripted (inactive demo visible/unsupported);
  19/19 IAC; 32/32 existing‑path scripted; **232 render + 1 catalog‑tail = 233**; 166 active
  cues, zero missing; 32 Static Looks; 4 DDJ overrides; **0 learned‑event collisions** [#5].
- **Oracles without contamination:** A5 16/16, cold new‑track 3/3 one‑based vs 0 direct,
  legacy Autoloop discriminator, file‑5/file‑18 exact cases replay **without capture‑seeded
  production state** (captures are oracles only).
- **Shadow mode:** backend `none`, logs only frame hashes, compared to independent expected
  output. Single‑process verification + rollback plan exist; code/config/adversarial reviews
  obtained. **No hardware claim anywhere.**

## Gate — **T9** (hardware handoff document — REVIEW ONLY, NEVER EXECUTE)

**Scope:** Task 9 is **not** an implementation — it is an operator hardware‑gate handoff.
**You review the document; you do not run anything, open any device, restart the bridge, or
send any output.** **Spec:** Part B T9, Part C, F‑6/F‑7, adversarial #7,#8.

**The handoff must, to APPROVE:**
- Name whether fixtures are **connected or disconnected**, the selected output backend +
  sanitized port alias, the **zero‑frame preflight** and the **physical kill method**.
- Give the exact bridge **stop/start + rollback** commands and **single‑process verification**
  (`rbss-bridge-verify` / `pgrep -f rb_ss_bridge_v2 | wc -l` == 1) **after** any restart.
- Specify the test order: safe **OFF/static** → one controlled **Autoloop** → **scripted
  track** → **DDJ press/release** → **blackout press/release** → **disconnect** → **shutdown**,
  with explicit logs/status/physical **pass/fail criteria** for each.
- State **DMX and MIDI‑laser output are mutually exclusive**; require exactly one bridge process.
- **Surface the `kill -9` Enttec last‑frame hazard** (firmware repeats the last frame; a
  physical kill/power path is the true failsafe) [#8] — software must not claim fail‑safe
  `kill -9`.
- **Require explicit operator approval** and state plainly that **implementation completion is
  NOT approval and NOT hardware validation**; status remains HARDWARE‑UNVALIDATED.

Flag as a **blocker** any handoff that auto‑enables output, infers approval from completion,
omits the kill path, or claims hardware/show readiness.
