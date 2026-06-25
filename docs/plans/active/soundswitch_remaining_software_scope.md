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
changes no behavior. Code and tests win where any doc drifts.

**Labels.** This doc uses the roadmap's own plain item names
(`soundswitch_exporter_remaining_work.md`, items 1-5 + T7d). It deliberately
does **not** invent its own letter/number scheme — there were already two
overlapping ones (`RW-N` and the format-spec's `Task 7/8/9` → `T7c/d/e`) and a
third would only add confusion. The roadmap stays the single status authority;
this file is the do-next breakdown under it.

**Verified at HEAD `f822f4c`** (roadmap/README/AWR were last stamped `f6910f9`,
review prompt at `67c9b7a` — HEAD has moved past both; see Item 1 and the drift
note).

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

## Numbering crosswalk (the labels, reconciled)

Three labeling schemes touch this project. They are not separate work — they name
the same items:

| Scheme | Origin | What it covers |
| --- | --- | --- |
| Roadmap items 1-5 + T7d | current `soundswitch_exporter_remaining_work.md` | the live naming this doc uses |
| `RW-1 … RW-10` | original workstream phase order | survives only in completed RW-1…RW-4 specs + the `rw7` prompt filename |
| `Task 7/8/9` → `T7c/T7d/T7e` | format/product spec (`soundswitch_importer_exporter_player_codex_spec.md`) | the autoloop / pack-player lineage |

Old `RW-N` → current item:

| Old | Means | Current item |
| --- | --- | --- |
| RW-1…RW-5 | export/publish/reload, shutdown, transport, mode, input health, status/menubar | **done / software-tested** (phantom-work list) |
| RW-6 | create the *live* local config (hardware prereq) | operator, part of **Item 2** (hardware run) |
| RW-7 = T7d | live autoloop-phase capture | **Item 3** — tooling done; captures pending |
| RW-8 | native-DMX Autoloop implementation | **Item 4** (`select_autoloop` still uncalled) |
| RW-9 / RW-10 | hardware run(s) / final validation | **Item 2** + hardware slice of **Item 5** |

No `RW-6`/`RW-8`/`RW-9` spec file exists (`find docs -iname '*rw6*'…` → none); the
divergence between `RW-N` and `T7*` is a known, *deliberately shelved* debt — see
the `soundswitch_roadmap_registry_reconciliation_spec.md` marked UNROUTED /
EXCLUDED in `doc_index.md`. Reconciling it is out of scope here.

---

## Software, doable now

### Item 1 — Independent implementation review

1. **Plain meaning.** An outside adversarial reviewer (ChatGPT) re-checks the
   already-landed status/menubar/shutdown work and the hardware procedure before
   you trust any of it live. Last software sign-off on work that's already written
   and passing.
2. **Current state — `confirmed`.** The review handoff exists
   (`docs/prompts/reviews/soundswitch_rw5_hardware_validation_implementation_review_prompt.md`),
   pinned to range `4138c61..67c9b7a`. The surfaces it names are real and current:
   `soundswitch_pack_runtime.py:35` (`sanitized_status`, provider-free — reads
   frozen dataclass fields only, calls no `backend`/`player` method),
   `state_manager.py:3318/3322/3362` (`get_pack_status`, `_publish_pack_status`,
   `_drive_pack_output`); `select_autoloop` is never called in `state_manager.py`
   (grep: 0 hits).
   **`confirmed` drift:** HEAD `f822f4c` is past the review head `67c9b7a`. The
   menubar freshness simplification landed at `3758d40` (after `67c9b7a`) — it
   removed the git-commit guard in `detect_export_state` and updated
   `tests/test_bridge_menubar.py`. The pinned review range does **not** cover that
   change, so running the review as-pinned reviews stale code.
3. **Doable now or blocked.** Doable now. No gate.
4. **Dependencies / ordering.** Do before the doc-drift stamp bump and before any
   final closeout (Item 5), so review covers everything landed.
5. **Smallest next deliverable.** Edit only the `Base/Head/Range` block of the
   review prompt to `…67c9b7a → f822f4c` and re-resolve its file:line anchors.
6. **Effort S. Risk low.** No runtime, no live-safety exposure.
7. **Invariants.** Must not weaken roadmap invariants 1, 2, 6, 8, 11.
8. **Owner.** Claude (range refresh) → operator/ChatGPT (the review run). Any
   BLOCKER/HIGH finding → a separate reviewed change (bridge code → Codex).

### Code/doc drift — menubar freshness (the one cleanup this pass found)

Not a numbered roadmap item; it's the "code/doc drift you can prove" bucket.

1. **Plain meaning.** The Export button's "is my pack up to date?" logic changed
   (it now keys purely on SoundSwitch source content, ignoring bridge git commits,
   because auto-sync moved HEAD every turn and kept un-greying the button). The
   docs describing the menubar still carry their pre-change verified stamp.
2. **Current state — `confirmed`.** Staleness flags `soundswitch_pack_player`
   STALE: `scripts/bridge_menubar.py` + `tests/test_bridge_menubar.py` changed
   since the docs were verified at `87b900a`. `detect_export_state` now returns
   `up_to_date` on a matching source fingerprint regardless of HEAD (the removed
   guard is a `ponytail:` comment in `bridge_menubar.py`). The button label also
   changed to `"Export"` (was `"Export from Soundswitch"` / `"Export from SS"`);
   README line 75 still says "Menubar `Export from SS`" — minor label drift.
3. **Doable now or blocked.** Doable now. No gate.
4. **Dependencies / ordering.** Pairs with Item 1; do in the same docs pass. The
   behavior is *more* source-only than the roadmap's "source-fingerprint freshness
   drives the menubar state" (roadmap line 36) — text not contradicted, only the
   stamp and the README label are stale.
5. **Smallest next deliverable.** Re-verify the staleness-listed docs against
   `bridge_menubar.py`, fix the README label, bump `last_verified_commit` to
   `f822f4c`.
6. **Effort S. Risk low.** Docs-only; no behavior change.
7. **Invariants.** Docs-only rule (AGENTS.md §6): no runtime change.
8. **Owner.** Claude / docs.

### Static-override interaction model — momentary only (open question, was missed)

1. **Plain meaning.** Static looks work, but the bridge-native player only does
   *momentary/hold* — a static is on while the controller note is held, and
   releases on note-off. It does **not** do *toggle* (tap-on, walk away, tap-off).
2. **Current state — `confirmed`.** `soundswitch_midi_input.py:214-256`: note-on
   holds the slot, **repeated note-on is idempotent** (no toggle-off), note-off
   releases, velocity-0 note-on → note-off, 2 s stale-hold auto-clear. The export
   binding (`PackMidiBinding`, `soundswitch_pack_loader.py:40-51`) carries only
   `target_kind` + `target_slot` — **no toggle/momentary field**; the exporter does
   not record a pad's toggle setting. Tested:
   `tests/test_soundswitch_midi_input.py` (`test_repeated_note_on_idempotent`,
   `test_note_off_releases_current`), `tests/test_static_looks.py`. Consistent with
   the RE finding that SoundSwitch's own `EnableStaticLookOverride` is momentary at
   the engine level (`soundswitch_ghidra_addendum.md:85`) — a different layer from
   the controller pad's toggle/momentary setting.
3. **Scope impact.** Only bites in the bridge-native direct-DMX path (default-off,
   gated behind T7d + hardware). In the current live OS2L path SoundSwitch handles
   the pad mode, so toggle works today. **Not listed in the roadmap** as remaining
   work or as a stated limitation — a genuine gap in prior scoping, surfaced
   2026-06-24.
4. **Doable now or blocked.** The *decision* is doable now (operator input). The
   implementation, if needed, is doable now too (no hardware/T7d dependency).
5. **Decision needed (operator).** Do any live static-look pads use **toggle**
   mode? **If yes** → the bridge-native path needs a toggle latch in the input
   adapter + a toggle flag carried through the export binding/spec (Effort S-M,
   software). **If no** → momentary-only is correct; just record it as an accepted
   boundary in `soundswitch_output.md` / the roadmap (Effort S, docs).
6. **Effort S (decision/docs) → S-M (if toggle latch needed). Risk low** until the
   direct-DMX path is enabled.
7. **Invariants.** Any toggle latch must keep safe-zero on stale/degraded/swap
   (roadmap invariants 8, 11) — a latched toggle must still release on input
   degradation, pack reload, panic, and shutdown like the momentary hold does.
8. **Owner.** Operator decision → Claude (doc the boundary) or Codex (toggle latch).

### Item 5 (software slice) — rerun the closeout gates

1. **Plain meaning.** Re-prove the suite/proof/docs gates are green — done this
   pass, all green (table above).
2. **Current state — `confirmed` green at HEAD.** The *full* closeout stays
   blocked (see below); only this gate-rerun slice is doable now.
3. **Doable now.** Yes — a checkpoint to repeat, not build work.
4. **Owner.** Claude.

---

## Software, BLOCKED (gate named)

### Item 3 — T7d capture evidence (software half: derivation + oracle PASS)

1. **Plain meaning.** Prove, from real captures, exactly how SoundSwitch's autoloop
   animation phase behaves on each transition, so the bridge could one day drive
   the same animation natively without guessing.
2. **Current state — `confirmed`: the software tooling is built and tested.** The
   phase-trace seam (`session_phase_trace.py`; schema-2 in `session_recorder.py`/
   `session_replayer.py`; `tests/replay/test_phase_trace.py`) and the falsifiable
   oracle (`tools/ssfmt/re/t7d_phase_contract.py`, wired via
   `validate_autoloop_capture.py --t7d`; `tests/test_t7d_phase_contract.py`) exist
   and pass in the 2355-test discovery. The conductor
   (`tools/t7d_capture_conductor.py`) exists. Corpus: 2 accepted `arm` + 2 accepted
   `refire`; `master-switch`, `drop-hold`, `buildup`, `correction` at zero.
3. **Blocked — exact gate.** Operator capture collection of the four remaining
   scenarios (2 accepted reps each, ≥3 verified bank-4 identities, 2 BPM/pitch
   values, ≥1 full holdout), then the oracle returning `PASS_T7D_PHASE_CONTRACT`
   over the corpus (capture plan §B6). The derivation analysis (§B5) is software
   but cannot start until those captures exist.
4. **Dependencies.** Unblocks Item 4.
5. **Smallest deliverable (when unblocked).** Run the conductor for one scenario
   with the operator present per capture plan §B4/§B4.5; do not start
   tcpdump/playback/restart yourself.
6. **Effort L. Risk: live-safety adjacent** — captures run with fixtures
   disconnected and pack output disabled; fail-closed on any unsafe baseline.
7. **Invariants.** Capture plan Part C; roadmap invariants 2, 8, 13.
8. **Owner.** Operator (captures, via conductor) → Claude (derivation + oracle run
   + sanitized verdict).

### Item 4 — Native Autoloop DMX (spec authoring)

1. **Plain meaning.** Write the implementation spec for the bridge driving autoloop
   animations on CH1-CH19 itself, instead of letting SoundSwitch do it.
2. **Current state — `confirmed` not implemented, by design.** `StateManager` never
   calls `select_autoloop`; the automatic base resolves software-zero in Autoloop
   mode (roadmap line 45; invariant 8). Even spec authoring is gated.
3. **Blocked — exact gate.** `PASS_T7D_PHASE_CONTRACT` from Item 3. No phase
   mapping may be selected from incomplete evidence. The scoping boundary forbids
   designing this now.
4. **Dependencies.** Strictly downstream of Item 3.
5. **Smallest deliverable (when unblocked).** A Codex spec mapping *only* the proven
   transition contract into pure code/tests, then adversarial review.
6. **Effort L. Risk: HIGH live-safety** (new per-tick DMX authority). Unknown
   transition classes must stay software-zero.
7. **Invariants.** Roadmap invariants 1, 2, 7, 8, 9, 10, 12.
8. **Owner.** Claude (analyze proven contract) → Codex (implementation spec).

### Item 5 — Full project closeout

1. **Plain meaning.** Declare the bounded local project done — only after every
   gate, including a real hardware run, is recorded.
2. **Current state.** Software gate-rerun slice green now; the rest is blocked.
3. **Blocked — exact gates.** T7d PASS (Item 3) → native Autoloop (Item 4) → final
   proof rerun + full gates + adversarial review → a recorded operator hardware run
   (Item 2). The hardware-evidence record is not a software artifact.
4. **Owner.** Operator + Claude at the final checkpoint.

---

## Out of software scope (operator / hardware — listed, not doable now)

### Item 2 — Non-Autoloop operator hardware run

- **Gate:** `docs/validation/soundswitch_hardware_validation_procedure.md`. Needs
  DMX connected, a reachable physical kill path, exactly one bridge process after
  an operator-approved start, and a recorded sanitized evidence file from
  `soundswitch_hardware_runs/TEMPLATE.md`.
- **State — `confirmed`:** the software/wire preflight already ran and PASSED at
  `3b7469a`
  (`docs/validation/soundswitch_hardware_runs/2026-06-24_3b7469a_rw5-software-preflight.md`);
  every physical row is `PENDING` (DMX lasers not connected); verdict `INCOMPLETE`.
  No software work unblocks it — purely operator + rig.
- **Owner.** Operator action.

### Item 3 (operator half) — T7d capture collection

- The operator-conducted half of Item 3: `master-switch`, `drop-hold`, `buildup`,
  `correction`, two accepted reps each, via the conductor. Needs the rig +
  operator. **Owner.** Operator action.

---

## Prioritized sequence

**Do-first software (no gate):**
1. **Item 1** — refresh the review handoff range to `f822f4c`, then run the review.
2. **Menubar doc-drift** — re-verify staleness-flagged docs, fix the README label,
   bump stamps. Bundle with #1.
3. Resolve any BLOCKER/HIGH review finding via a separate reviewed change.
4. **Item 5 (software slice)** — re-run the gate block (green now).

**Blocked-software (gate named):**
5. **Item 3** — T7d derivation/oracle PASS. *Gate:* operator captures of the four
   scenarios → `PASS_T7D_PHASE_CONTRACT`.
6. **Item 4** — native Autoloop DMX spec authoring. *Gate:* `PASS_T7D_PHASE_CONTRACT`.
7. **Item 5** — full closeout. *Gate:* Items 3 + 4 + final gates + Item 2.

**Operator / hardware (not software):**
8. **Item 2** hardware run; **Item 3** capture collection.

## Phantom-work list (roadmap implies build work the code already did)

- **T7d tooling.** Item 3 reads like build work ("reconcile identity/holdout",
  "obtain one unique contract"). The phase-trace seam and the falsifiable oracle
  are already built and tested. What remains is *operator data + running the tool*,
  not building it.
- **RW-1 … RW-5 + graceful shutdown + copied menubar status.** All implemented and
  software-tested; verified at HEAD (symbols present, 210 focused + 2355 full OK).
  No remaining software *build* here — the latest menubar change net-*removed* code.
- **Current-project proof rerun.** Closeout lists "rerun the proof" — it passes
  right now (29/0/0). A checkpoint to repeat at the final snapshot, not build work.

## Recommended first move

Refresh the independent-review handoff's commit range from `67c9b7a` to HEAD
`f822f4c` (re-resolving the named file:line anchors so the post-`67c9b7a` menubar
freshness change and its test are inside the reviewed range), bundle the one-line
doc-staleness re-verify into the same docs pass, then hand the prompt to the
external reviewer. It's the only do-first software item with no gate, it's an S,
and it closes the single real drift this pass surfaced — the menubar change
currently sits *outside* the pinned review range and is the lone staleness flag.
Everything past that is gated on operator captures (Item 3) or the T7d PASS
(Items 4/5), and the hardware run (Item 2) is operator-only.
