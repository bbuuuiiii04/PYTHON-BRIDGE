---
doc_status: active-plan
truth_level: code-and-test-grounded
last_verified_commit: f822f4c
last_verified_date: 2026-06-24
validation_scope: read-only Opus scoping of remaining SOFTWARE SoundSwitch exporter / bridge-native CH1-CH19 work; scoping only, no behavior change; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Remaining SOFTWARE scope — SoundSwitch exporter / bridge-native DMX

This separates *software that can move now* from *software blocked on an operator
capture or hardware run*, and kills roadmap items the code already satisfies. It
changes no behavior. Code and tests win where any doc drifts. The single status
authority remains `soundswitch_exporter_remaining_work.md`; this file is the
do-next breakdown under it.

**Verified at HEAD `f822f4c`** (roadmap/README/AWR were last stamped `f6910f9`,
review prompt at `67c9b7a` — HEAD has moved past both; see Item 1 and Drift).

## Gate results I reran (read-only, this pass)

| Gate | Result |
| --- | --- |
| 7 focused suites (`test_state_manager_pack_driver` … `test_soundswitch_pack_startup`) | 210 OK |
| `python3 -m unittest discover tests` | 2355 OK (skipped=3, expected failures=1) |
| `check_docs_metadata` / `check_agent_contracts` / `check_docs_drift` | all PASS (hard checks) |
| `check_docs_staleness --report` | **1 advisory:** `soundswitch_pack_player` STALE (menubar change since `87b900a`) |
| `prove_soundswitch_pack_generation.py` (default canonical project) | `PASS_IMPLEMENTATION_MAY_BEGIN`, 29 PASS / 0 FAIL / 0 INCOMPLETE |
| `git diff --check` | clean |

These are software/wire gates only. `software_zero_frame` and `frame_count`
prove no serial send, no Enttec acceptance, and no physical darkness.

## Numbering crosswalk (old RW-6…RW-10 → current items)

The current roadmap names items 1-5 + T7d and dropped the old `RW-N` numbers.
Those numbers survive only as forward-references inside the completed RW-1…RW-4
specs and the `soundswitch_rw7_capture_agent_prompt.md` filename — **no RW-6/RW-8/
RW-9 spec file exists** (`find docs -iname '*rw6*'…` → none). So they are not
unscoped work; they map onto the items below:

| Old label | Means | Here |
| --- | --- | --- |
| RW-5 | operational status (copied status + menubar) | landed/software-tested (phantom-work list) |
| RW-6 | create the *live* local config (hardware prereq) | operator, folded into **H1** |
| RW-7 | T7d live autoloop-phase capture | tooling **B1** (done) + capture **H2** (operator) |
| RW-8 | native-DMX Autoloop implementation | **B2** (`select_autoloop` still uncalled) |
| RW-9 / RW-10 | hardware run(s) / final hardware validation | **H1** + hardware slice of **B3** |

---

## Software items, doable now

### S1. Refresh + run the independent implementation review (roadmap item 1)

1. **Plain meaning.** An outside adversarial reviewer (ChatGPT) re-checks the
   already-landed RW-5 status/menubar/shutdown work and the non-Autoloop hardware
   procedure before the operator trusts any of it live. It's the last software
   sign-off gate on work that is already written and passing.
2. **Current state — `confirmed`.** The review handoff exists:
   `docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md`,
   pinned to range `4138c61..67c9b7a` (prompt lines 14-19). The RW-5 surfaces it
   names are real and current: `soundswitch_pack_runtime.py:35` (`sanitized_status`,
   provider-free — reads frozen dataclass fields only, calls no `backend`/`player`
   method), `state_manager.py:3318` (`get_pack_status`), `:3322`
   (`_publish_pack_status`), `:3362` (`_drive_pack_output`); `select_autoloop` is
   never called in `state_manager.py` (grep: 0 hits) — confirming invariant 8 /
   `autoloop_phase_blocked` never selects Autoloop.
   **`confirmed` drift:** HEAD `f822f4c` is past the review head `67c9b7a`. The
   menubar freshness simplification landed at `3758d40` (after `67c9b7a`) — it
   removed the git-commit guard in `detect_export_state` and updated
   `tests/test_bridge_menubar.py`. So the pinned review range does **not** cover
   the latest menubar change; running the review as-pinned reviews stale code.
3. **Doable now or blocked.** Doable now (software). No gate.
4. **Dependencies / ordering.** Do before S2's commit-stamp bump and before any
   final closeout (Item 5), so review covers everything landed.
5. **Smallest bounded next deliverable.** Edit only the `Base/Head/Range` block
   (lines 14-19) of the review prompt to `…67c9b7a → f822f4c` (and re-resolve the
   file:line anchors in its "Inspect the implementation surfaces" list). One doc,
   ~6 lines.
6. **Effort S. Risk low.** No runtime, no live-safety exposure (prompt edit).
7. **Invariants.** Must not weaken roadmap invariants 1, 2, 6, 8, 11; the review
   itself is read-only and asserts them.
8. **Owner type.** Claude analysis (range refresh) → operator/ChatGPT (the review
   run). Any BLOCKER/HIGH finding → a *separate reviewed change* (bridge code →
   Codex; see CLAUDE.md role split).

### S2. Clear the menubar-freshness doc drift (roadmap "code/doc drift" bucket)

1. **Plain meaning.** The Export button's "is my pack up to date?" logic changed
   (it now keys purely on SoundSwitch source content, ignoring bridge git commits,
   because auto-sync moved HEAD every turn and kept un-greying the button). The
   docs that describe the menubar still carry their pre-change verified stamp.
2. **Current state — `confirmed`.** Staleness flags `soundswitch_pack_player`
   STALE: `scripts/bridge_menubar.py` + `tests/test_bridge_menubar.py` changed
   since the contract's docs were verified at `87b900a`. The new behavior:
   `detect_export_state` returns `up_to_date` on a matching source fingerprint
   regardless of HEAD (the removed git guard is documented in-code as a
   `ponytail:` comment in `bridge_menubar.py`). The button label also changed:
   `export_button_text(False, False)` now returns `"Export"` (was
   `"Export from Soundswitch"`), and the menu item is `"Export"` (was
   `"Export from SS"`). README line 75 still says "Menubar `Export from SS`" —
   minor label drift.
3. **Doable now or blocked.** Doable now. No gate.
4. **Dependencies / ordering.** Pairs with S1; do in the same docs pass. The
   behavior is *more* source-only than the roadmap's "source-fingerprint freshness
   drives the menubar state" claim (roadmap line 36) — so the roadmap text is not
   contradicted, only its verified stamp and the README label are stale.
5. **Smallest bounded next deliverable.** Re-verify the docs the staleness report
   lists against `bridge_menubar.py`, fix the README `Export from SS` label
   reference, bump `last_verified_commit` to `f822f4c` on the re-verified docs.
6. **Effort S. Risk low.** Docs-only; must not change runtime behavior.
7. **Invariants.** Docs-only rule (AGENTS.md §6 last bullet): no behavior change.
8. **Owner type.** Claude analysis / docs.

### S3. Rerun the software closeout gates (software slice of roadmap item 5)

1. **Plain meaning.** Re-prove the suite/proof/docs gates are green at the
   software checkpoint — already done this pass and all green (see table above).
2. **Current state — `confirmed` green at HEAD.** This is the *software slice* of
   the closeout. The **full** closeout (Item 5 below) stays blocked because it
   also requires T7d PASS, native Autoloop, and a recorded hardware run.
3. **Doable now.** Yes (re-run on demand). It is a checkpoint, not build work.
4. **Dependencies.** Run after S1/S2 land and again at the true final checkpoint.
5. **Smallest deliverable.** Re-run the gate block; record verdicts. (No code.)
6. **Effort S. Risk low.**
7. **Invariants.** Tests must use fake/injected interfaces; no live/hardware.
8. **Owner type.** Claude analysis.

---

## Software items, BLOCKED (gate named)

### B1. T7d derivation / reconciliation + oracle PASS (roadmap item 3)

1. **Plain meaning.** Prove, from real captures, exactly how SoundSwitch's
   autoloop animation phase behaves on each transition, so the bridge could one
   day drive the same animation natively without guessing.
2. **Current state — `confirmed`: the software tooling is built and tested.** B1
   phase-trace seam (`session_phase_trace.py`, schema-2 in `session_recorder.py`/
   `session_replayer.py`, `tests/replay/test_phase_trace.py`) and B2 falsifiable
   oracle (`tools/ssfmt/re/t7d_phase_contract.py`, wired via
   `validate_autoloop_capture.py --t7d`, `tests/test_t7d_phase_contract.py`) exist
   and pass in the 2355-test discovery. The conductor
   (`tools/t7d_capture_conductor.py`) exists. Corpus: 2 accepted `arm` + 2 accepted
   `refire` integrity captures; `master-switch`, `drop-hold`, `buildup`,
   `correction` at zero (capture-evidence plan, corpus update 2026-06-23).
3. **Blocked — exact gate.** Operator capture collection of the four remaining
   scenarios (2 accepted repetitions each, ≥3 verified bank-4 identities, 2
   BPM/pitch values, ≥1 full holdout), then the oracle returning
   `PASS_T7D_PHASE_CONTRACT` over the corpus (capture plan §B6). The derivation
   analysis (§B5) is software but cannot start until those captures exist.
4. **Dependencies.** Unblocks B2 (native Autoloop spec). Independent of S1-S3.
5. **Smallest deliverable (when unblocked).** Run the conductor for one scenario
   (`run-scenario master-switch`) with the operator present per the capture plan
   §B4/§B4.5; do not start tcpdump/playback/restart yourself.
6. **Effort L. Risk: live-safety adjacent** — captures run with fixtures
   disconnected and pack output disabled; fail-closed on any unsafe baseline.
7. **Invariants.** Capture plan Part C (StateManager sole writer; no 200 Hz I/O;
   OS2L unchanged; pack default-off; safe-zero on any ambiguity); roadmap
   invariants 2, 8, 13.
8. **Owner type.** Operator action (captures, via conductor) → Claude analysis
   (derivation + oracle run + sanitized verdict).

### B2. Native Autoloop DMX spec authoring (roadmap item 4)

1. **Plain meaning.** Write the implementation spec for the bridge driving
   autoloop animations on CH1-CH19 itself (instead of letting SoundSwitch do it).
2. **Current state — `confirmed` not implemented, by design.** `StateManager`
   never calls `select_autoloop`; the automatic base resolves software-zero in
   Autoloop mode (roadmap line 45; invariant 8). Even **spec authoring** is gated.
3. **Blocked — exact gate.** `PASS_T7D_PHASE_CONTRACT` from B1. No phase mapping
   may be selected from incomplete evidence (capture plan §B6, roadmap item 4).
   The scoping boundary forbids designing this now.
4. **Dependencies.** Strictly downstream of B1.
5. **Smallest deliverable (when unblocked).** A Codex spec mapping *only* the
   proven transition contract into pure code/tests, then adversarial review.
6. **Effort L. Risk: HIGH live-safety** (new per-tick DMX authority). Unknown
   transition classes must stay software-zero.
7. **Invariants.** Roadmap invariants 1, 2, 7, 8, 9, 10, 12.
8. **Owner type.** Claude analysis of the proven contract → Codex implementation
   spec.

### B3. Full project closeout (roadmap item 5, non-software remainder)

1. **Plain meaning.** Declare the bounded local project done — only after every
   gate, including a real hardware run, is recorded.
2. **Current state.** Software slice green now (S3). The rest is blocked.
3. **Blocked — exact gates.** T7d PASS (B1) → native Autoloop (B2) → final proof
   rerun + full gates + adversarial review → a recorded operator hardware run
   (Item H1). The hardware-evidence record is not a software artifact.
4. **Owner type.** Operator action + Claude analysis at the final checkpoint.

---

## Out of software scope (operator / hardware — listed, not doable now)

### H1. Non-Autoloop operator hardware run (roadmap item 2)

- **Gate:** `docs/validation/soundswitch_hardware_validation_procedure.md`. Needs
  DMX connected, a reachable physical kill path, exactly one bridge process after
  an operator-approved start, and a recorded sanitized evidence file from
  `soundswitch_hardware_runs/TEMPLATE.md`.
- **State — `confirmed`:** the software/wire preflight already ran and PASSED at
  `3b7469a` (`docs/validation/soundswitch_hardware_runs/2026-06-24_3b7469a_rw5-software-preflight.md`);
  every physical row is `PENDING` (DMX lasers not connected); verdict `INCOMPLETE`.
  No software work unblocks it — it is purely operator + rig.
- **Owner type.** Operator action.

### H2. T7d capture collection

- The operator-conducted half of B1: `master-switch`, `drop-hold`, `buildup`,
  `correction`, two accepted reps each, via the conductor. Needs the rig +
  operator. **Owner type.** Operator action.

---

## Prioritized sequence

**Do-first software (no gate):**
1. **S1** — refresh the RW-5 review handoff range to `f822f4c`, then run the
   independent review.
2. **S2** — clear the menubar-freshness doc drift (re-verify staleness-flagged
   docs, fix the README `Export from SS` label, bump verified stamps). Bundle with S1.
3. Resolve any BLOCKER/HIGH review finding via a separate reviewed change.
4. **S3** — re-run the software gate block at the checkpoint (green now).

**Blocked-software (gate named):**
5. **B1** — T7d derivation/oracle PASS. *Gate:* operator captures of the four
   scenarios → `PASS_T7D_PHASE_CONTRACT`.
6. **B2** — native Autoloop DMX spec authoring. *Gate:* `PASS_T7D_PHASE_CONTRACT`.
7. **B3** — full closeout. *Gate:* B1 + B2 + final gates + H1.

**Operator / hardware (not software):**
8. **H1** non-Autoloop hardware run; **H2** T7d capture collection.

## Phantom-work list (roadmap implies build work the code already did)

- **T7d B1/B2 tooling.** Roadmap item 3 reads like build work ("reconcile
  identity/holdout", "obtain one unique contract"). The phase-trace seam and the
  falsifiable oracle are already built and tested (`t7d_phase_contract.py`,
  `session_phase_trace.py`, `validate_autoloop_capture.py --t7d`, plus tests in
  the 2355-test pass). What remains is *operator data + running the tool*, not
  building it.
- **RW-1 … RW-5 + graceful shutdown + copied menubar status.** All implemented and
  software-tested; verified at HEAD (symbols present, 210 focused + 2355 full OK).
  No remaining software *build* here. The latest menubar change net-*removed* code.
- **Current-project proof rerun.** Roadmap closeout lists "rerun the proof" — it
  passes right now (29/0/0). Not build work; just a checkpoint to repeat at the
  final snapshot.

## Recommended first move

Refresh the RW-5 independent-review handoff's commit range from `67c9b7a` to HEAD
`f822f4c` (re-resolving the named file:line anchors so the post-`67c9b7a` menubar
freshness change and its test are inside the reviewed range), bundle the one-line
doc-staleness re-verify (S2) into the same docs pass, then hand the prompt to the
external reviewer. It's the only do-first software item with no gate, it's an S,
and it closes the single real drift this pass surfaced — the menubar change
currently sits *outside* the pinned review range and is the lone staleness flag.
Everything past that is gated on operator captures (B1) or the T7d PASS (B2/B3),
and the hardware run (H1) is operator-only.
