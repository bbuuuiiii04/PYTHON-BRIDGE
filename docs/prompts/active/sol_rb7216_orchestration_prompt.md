---
doc_status: current
truth_level: orchestration-handoff
last_verified_commit: 5be388a
last_verified_date: 2026-07-13
validation_scope: >
  SOL manager/orchestrator handoff to add Rekordbox 7.2.16 direct-reader support at
  parity. Ground truth = Fable/Opus static RE against the official 7.2.16.0342 arm64
  binary (hash-verified) plus GhidraMCP confirmation of all four chain roots. Interior
  offsets carried from the 7.2.14 table (operator-live-validated there) — software
  landing only; operator live validation on 7.2.16 is still the final gate.
---

# SOL orchestration prompt — Rekordbox 7.2.16 support (parity)

You are **SOL**, the manager/orchestrator for this one workstream. Pin your seat at
**model = <SOL model>, effort = HIGH**, verify the pin on screen before you start.

Read `AGENTS.md`, then `docs/agents/multi_agent_org_workflow.md` and
`docs/agents/opus_seat_harness.md` in full before dispatching anything. This prompt
assumes their rules (seat ladder, review chain, suite-baseline-by-name, dispatch/watch
tooling + its four field bugs, live-safety spine). Communicate with the operator in
AGENTS.md §0 mode: plain language, mechanism kept, evidence class stated, no status
blocks.

## 0. Your job in one paragraph

Get the bridge to support Rekordbox **7.2.16** at **parity** with the versions it
already supports — nothing more. You do this by (1) dispatching the implementation to
the **grok4.5** implementer lane over tmux, (2) **adversarially reviewing** its output
at your own desk (nobody certifies their own work), and (3) handing a clean,
evidence-backed result back. **You do not edit bridge code yourself, you do not run or
restart the bridge, and you do not touch any hardware/output path.** grok4.5
implements; you review. If you are ever forced to touch code, a separate reviewer must
check it — self-certification is banned.

## 1. The mission and its exact scope

**Goal:** on Rekordbox 7.2.16 the bridge must deliver the SAME direct-read signal set
it already delivers on 7.2.11, and every already-supported version (7.2.8 / 7.2.10 /
7.2.11 / 7.2.13 / 7.2.14) must keep working byte-for-byte.

Parity signal set (this is the whole scope):
- master deck, live BPM, live position, play/pause inference, track title, ANLZ path
  (decks 1–4 as today);
- mixer active-deck authority = **deck 1/2 upfader + LOW/BASS EQ only** (exactly what
  7.2.11 carries today);
- CFX FILTER tracking (deck 1/2 filter param0 + selected-id + unit-channel), tracking-
  only, never feeding active-deck authority.

**Explicitly OUT of scope — do NOT let it fold in** (no evidence exists; adding it is
scope creep, harness failure mode #5): trim, HIGH/MID EQ, crossfader, crossfader
assign, CFX on/off, CFX PARAM1, any Beat FX, decks 3/4 mixer/CFX. A reviewer or
implementer who "notices" these = a NOTE in the report, never an edit.

**Urgency context:** the operator is already ON 7.2.16.0342, and 7.2.16 is absent from
the offset table, so the direct reader is currently a **no-op — the bridge is running
dark on direct reads right now.** Landing this row is what restores it. This does not
license shortcuts; it means the round matters.

## 2. Ground truth, pinned (verified — do not re-derive, but re-verify cites at HEAD)

Commit at handoff: **5be388a**. Reader gates version support by exact string match in
`_OFFSETS_MACOS_ARM64` inside `rb_offsets.py`; a missing version → reader is a clean
no-op (`RBStateReader.run()` exits, all availability callbacks go False). So adding a
7.2.16 block is **purely additive** — it changes nothing for the other five versions.

Static RE result (Fable/Opus against the official 7.2.16 arm64 binary; installer zip
SHA-256 `b1007870…4613a99`, universal binary SHA-256 `b6fc70c0…5dfa05e` — both
verified; GhidraMCP project *Rekordbox Mixer RE*):

**All four chain roots CONFIRMED two independent ways (nm symbol math + decompiled
instance-pointer globals):**
- master root `04EE71D8` = `ApplicationMode` singleton instance;
- ANLZ root `04EE7C08` = `browse::LoadedContentsManager` singleton instance;
- mixer root `04EE5758` = `djengine::DjEngineIF` singleton instance (0xD8 object;
  `DAT_104ee5758`); first mixer hop `+0xA8` confirmed = the `RekordboxDjSystem` audio
  graph in the DjEngineIF constructor;
- deck root `04EA17A0` = `rbxfrm::DjPlayerRepository` member +8 = the players-array
  pointer (`*(root)+deck*8` = each DjPlayer, proven in `doGetSyncMasterUnit`). This is
  the one root with no public symbol; it is now positively identified. The previously
  rejected `04E9B670` stays rejected.

**Interior offsets: CANDIDATE (carried from the 7.2.14 table, which is operator-live-
validated for BPM/position/track).** They were not traced field-by-field; they hang
off confirmed roots/entry objects and are byte-identical to 7.2.14's deck layout and
7.2.11's mixer/CFX layout. The reader range-validates and fails closed on every one, so
a wrong interior offset degrades to "no signal," never to garbage authority — but
**operator one-control-at-a-time live validation on 7.2.16 is still the final gate
before this row is trusted for a live show.**

## 3. Live-safety spine (state the relevant lines in every dispatch)

- Reason the live-mixing scenario before any change. The bridge is started ONLY by the
  operator (menubar); no lane runs `python3 -m rb_ss_bridge_v2` or restarts it.
- Memory reads stay on the reader thread; **add zero blocking work to the StateManager
  200 Hz push loop.**
- Fail-closed is preserved: unsupported version → no-op; per-read finite/range/CFX-
  identity checks reject bad reads; a bad CFX or mixer sample must NEVER invalidate the
  other group (independent optional groups) and CFX must never feed active-deck
  authority.
- The 7.2.16 row lands as **software-tested only**. It is NOT cleared for live use until
  the operator runs the live checklist. Say this in the ship report; do not imply
  live-ready.

## 4. The implementation spec to dispatch to grok4.5 (verify at HEAD, then send)

This is a ready Part A–E spec; re-verify the file fence and the 7.2.11 block at HEAD
before dispatch (the tree moves under you — auto-sync + parallel lanes).

**A. Task:** append one `7.2.16` block to the `_OFFSETS_MACOS_ARM64` string literal in
`rb_offsets.py`, mirroring the existing `7.2.11` block's structure (17 positional core
lines + labeled MIXER_*/CFX_* lines). Change NOTHING else in that literal — the other
five version blocks stay byte-for-byte identical.

**Exact block to add (bare chains, no inline comments — the parser splits on
whitespace and a `#` would break it):**

```
7.2.16
04EE71D8 20 278 124
04EA17A0 0 2C8 188
04EA17A0 0 2C8 120
04EA17A0 0 270 38 88 28 F0 0
04EE7C08 8 3F0
04EA17A0 8 2C8 188
04EA17A0 8 2C8 120
04EA17A0 8 270 38 70 28 F0 0
04EE7C08 10 3F0
04EA17A0 10 2C8 188
04EA17A0 10 2C8 120
04EA17A0 10 270 38 48 28 F0 0
04EE7C08 18 3F0
04EA17A0 18 2C8 188
04EA17A0 18 2C8 120
04EA17A0 18 270 38 48 28 F0 0
04EE7C08 20 3F0
MIXER_D1_UPFADER_RAW 04EE5758 A8 458 0 2C8 0 470 30
MIXER_D2_UPFADER_RAW 04EE5758 A8 458 0 2C8 8 470 30
MIXER_D1_LOW_RAW     04EE5758 A8 458 0 2C8 0 460 30 38
MIXER_D2_LOW_RAW     04EE5758 A8 458 0 2C8 8 460 30 38
CFX_D1_FILTER_PARAM0 04EE5758 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8
CFX_D2_FILTER_PARAM0 04EE5758 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8
CFX_D1_SELECTED_ID   04EE5758 A8 458 0 2C8 0 480 0 1E0 0 88 0 70
CFX_D2_SELECTED_ID   04EE5758 A8 458 0 2C8 8 480 0 1E0 0 88 0 70
CFX_D1_UNIT_CHANNEL  04EE5758 A8 458 0 2C8 0 480 0 1E0 0 D0
CFX_D2_UNIT_CHANNEL  04EE5758 A8 458 0 2C8 8 480 0 1E0 0 D0
```

**B. File fence (touch ONLY these):**
- `rb_offsets.py` (the block above)
- `tests/test_rb_offsets.py` and/or `tests/test_rb_state_reader.py` (new tests, task D)
- `tests/test_rekordbox_reader_safety.py` (update ONE existing per-version invariant, task D2 — added to the fence after a verified round-1 block; see note)
- the contract docs in task E. Nothing else. Commit by EXPLICIT PATHS, never `-a`.

> **Fence-widen note (verified at commit 5be388a):** round 1 correctly BLOCKED because
> `test_mixer_cfx_only_on_7_2_11` lives outside the original fence. That test encodes
> the OLD invariant "mixer/CFX chains exist only on 7.2.11." Adding 7.2.16 with
> mixer/CFX legitimately changes that invariant, so the test must be extended (task D2).
> This is why the safety test is now in-fence. It is a real invariant update from a new
> supported version — NOT weakening a safety check, and NOT the forbidden "edit tests to
> pass." No other assert in that file breaks (the unsupported-version and derive-tool
> asserts still hold).

**C. Tasks, one commit each:**
1. Add the 7.2.16 block to `rb_offsets.py`.
2. Add tests (task D).
3. Update docs/contracts (task E).

**D. Tests to add (assert-level, no new frameworks):**
- 7.2.16 parses: `load_offsets_for_version("7.2.16")` returns a populated
  `RBOffsetVersion` with the exact roots/hops above (master, 4×deck bpm/pos/track/anlz,
  the 4 mixer chains, the 6 CFX chains).
- 7.2.11 regression: the 7.2.11 record is unchanged (roots + mixer + CFX identical to
  pre-change) — a literal-value assertion, so a stray edit to the shared literal fails
  loudly.
- Unsupported-version no-op: an unknown version → `load_offsets_for_version` returns
  None and the reader is a no-op (existing behavior still holds).
- Group independence: a 7.2.16 record with a malformed mixer line disables ONLY mixer
  (CFX stays), and vice versa (reuse the existing labeled-group tests' pattern).
- Endpoint/range: mixer upfader 0 and 1023, LOW 0 and 255, CFX param 0.0 and 1.0 accept;
  out-of-range/non-finite reject (reader `_follow_finite_f32_result`).
- CFX channel ownership: selected_id≠0 → wrong_effect; unit_channel≠deck-1 → mismatch.
- No output side effects / no push-loop work: the new row exercises only the reader
  path; assert no import of any output backend and no StateManager push-loop change.

**E. Docs/contracts to update (change contract `rekordbox_readers`):**
`docs/subsystems/rekordbox_readers.md`, `docs/status/support_matrix.md`,
`docs/status/feature_status_matrix.md`, `docs/status/validation_matrix.md`,
`docs/validation/software_test_inventory.md`,
`docs/agents/task_playbooks/change_rekordbox_reader.md`. Record 7.2.16 as
**software-tested, roots STATIC-CONFIRMED, interiors CANDIDATE, live-unvalidated**;
bump `last_verified_commit`.

**Acceptance (state as the completion contract in the dispatch):**
- `python3 -m unittest discover tests` — full suite green, reconciled BY NAME against
  the named baseline (not a count).
- `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
  `python3 tools/check_docs_drift.py` — all pass.
- Commit stat matches the file fence exactly.

**The four verbatim clauses (inline in the grok4.5 dispatch):**
- *Report, don't certify:* "You report evidence; SOL reviews; the operator gates. You
  never declare the round shipped or the baseline moved."
- *Run straight through:* "Do not pause at checkpoints for acknowledgment; run straight
  through unless genuinely blocked."
- *Block, don't invent:* "If reality diverges from this spec (a version block that
  doesn't match, a moved file, an unexpected test red): STOP, write the `.blocked`
  signal with one line of evidence, and wait. Blocking is a success mode."
- *Spec files only:* "Touch ONLY the fenced files. An improvement you notice is a NOTE
  in your report, never an edit."

## 5. Dispatch + watch mechanics

- Write the section-4 spec to a message file, then dispatch:
  `tools/agents/dispatch_lane.sh grok4.5 <grok model> <effort> <msgfile> RB7216 <agent>`
  (the script does the ritual: hands-off check, model/effort pin, paste-trap clearing,
  run-straight-through clause, signal-file instruction; it creates/boots the grok4.5
  session if missing). Pin model AND effort explicitly — never rely on saved defaults.
- Completion contract in the dispatch: print the sentinel on its own line AND write
  `/tmp/rbss_lane_signals/grok4.5.RB7216.done` (or `.blocked`).
- Watch with ONE watcher, signal-file first:
  `tools/agents/watch_lane.sh grok4.5 '' 900 0 RB7216`.
- After EVERY paste: capture the pane and nudge Enter until any `[Pasted text #N]` chip
  clears (field bug #1). Don't put the literal sentinel string in relay text (field bug
  #3). If you block-and-resume, watch by signal file only (field bug #4).
- `tmux list-sessions` before creating/routing. Never send keys to a pane showing real
  typed text (operator mid-thought) — abort instead.

## 6. Adversarial review — do this at YOUR desk, don't re-read grok4.5's word

When RB7216.done fires:
1. **Re-derive the suite, by name.** Run `python3 -m unittest discover tests` yourself;
   reconcile reds against the named baseline. "N reds, pre-existing" without names is an
   INVALID report — demand names or derive them. Isolate known flappers (pack byte-
   identity tests that embed HEAD flap on any mid-run commit) — green in isolation =
   baseline, never gate on it.
2. **Verify the row bytes.** Diff the landed 7.2.16 block against the exact block in
   §4 — every root and hop. Verify the 7.2.11 block is unchanged (byte-for-byte).
3. **Diff the commit stat against the file fence.** Anything outside `rb_offsets.py` +
   the named tests + the named docs = scope creep; route it back.
4. **Run the hard checks** yourself (metadata, agent-contracts, docs-drift).
5. **Refute before escalating.** Any finding you raise passes an independent default-to-
   refuted check (severity + file:line + reproduction + refuter verdict) before it
   reaches the operator. Praise a correct block if grok4.5 blocks — it reinforces the
   behavior.
Verdict: PASS / PASS-with-required-fixes / redo. If redo, dispatch a fix round with the
same fence and re-review; do not fix it yourself.

## 7. Done / handback

The round is **software-complete** when: the 7.2.16 block matches §4 exactly, the other
five versions are unchanged, the full suite is green by name, the three hard checks
pass, the contract docs are updated, and your adversarial review is PASS. Report to the
operator in plain language with the evidence class stated explicitly:
**software-tested; roots statically confirmed; interior offsets carried from 7.2.14 and
NOT yet live-validated on 7.2.16.** Then hand off the operator live-validation checklist
(deck load/unload, title, ANLZ, BPM, play/pause/seek/restart, master change, deck 1/2
faders, LOW EQ, CFX select + FILTER sweep + on/off, app quit/relaunch reacquire) and
state clearly that the row is **not cleared for a live show until that pass is clean.**
Do NOT declare it shipped — the operator's live gate is the final word.

## 8. Escalation

Ship-blocker (would break a live session): `.blocked` immediately with severity, exact
file:line, reproduction, refuter verdict, proposed fix shape. Anything ambiguous about
scope or a diverging version block: block, don't invent. The operator is your only
upward surface — lanes never report to the operator directly.
