---
doc_status: active-session-handoff
truth_level: byte-and-capture-grounded
last_verified_commit: c6d1a50
last_verified_date: 2026-06-20
validation_scope: read-only SoundSwitch research tooling, passive wire captures, and docs; no bridge runtime implementation; hardware-unvalidated
---

# Codex Implementation Spec - Close Scripted-Track Renderer Verification

Paste this entire file into a fresh Codex session opened at
`/Users/bbui/rb_ss_bridge_v2`.

This handoff supersedes older task ordering for the scripted-renderer closure
thread. Older SoundSwitch plans remain useful evidence, but this file defines the
next session's objective, safety boundary, current measurements, and completion
gate.

## Mission

Close the foundational scripted-track renderer gap completely. Do not stop at
another diagnosis, another partial match count, or another list of unknowns.
Continue offline analysis, pure research-tool changes, focused tests, and
operator-orchestrated captures until every declared supported scripted target is
byte-exact at events and arbitrary positions, including transport edges.

An uncertainty may leave the task only when it is either:

1. resolved by bytes/code/tests/wire evidence; or
2. proven to be an already-declared excluded class with deterministic fail-closed
   behavior, such as the In-App Demo layout or controlled MIXED/edited files.

Do not turn an unexplained residual in a normal project track into a new
"unsupported" class merely to finish. Code and captured bytes win over this or
any other document.

## Part A - Context and Root Cause (verified; read, do not implement)

### A1. Absolute live-safety boundary

- [confirmed] Do not start, stop, restart, toggle, or kill the bridge. The
  operator owns those actions.
- [confirmed] Do not send MIDI, OS2L, Art-Net, DMX, serial output, or Laser Pad
  commands.
- [confirmed] Do not run `tcpdump`; the operator runs it in their terminal.
- [confirmed] Do not modify `~/Music/SoundSwitch/default.ssproj` or any other
  SoundSwitch project. Read-only parsing of copies is allowed.
- [confirmed] Do not change bridge runtime modules, the Enttec daemon, or the
  VLN adapter in this research task.
- [confirmed] Before any laser playback, establish the monitored pcap/project/
  AppLog/bridge-log baseline first. Then post exactly one operator action both
  visibly and with macOS `say`. Require fixture-safe confirmation in that action.
- [confirmed] Never wait for a chat reply after an operator action. Monitor the
  named files and current logs for the requested change.
- [confirmed] Every later operator action, including seek, pause, resume, loop,
  stop, unload, and log copy, is separately visible and separately spoken. Take
  a new file/hash baseline before each `say` ping.
- [confirmed] Passive Art-Net evidence is software/wire evidence only. It does
  not prove physical laser behavior.

### A2. Worktree boundary

- [confirmed] Repo: `/Users/bbui/rb_ss_bridge_v2`; verified HEAD at handoff:
  `c6d1a50`.
- [confirmed] The worktree is intentionally dirty. It contains the current
  SoundSwitch research-tool/doc work, staged capture-untracking deletions,
  untracked active specs/tests, and unrelated user changes.
- [confirmed] Do not reset, checkout, restore, clean, re-stage, or delete any
  existing change. Do not commit unless the operator explicitly requests it.
- [confirmed] Read `AGENTS.md`, then `docs/agents/change_contracts.yml` key
  `soundswitch_research`, then this file. Use
  `$codex-context-delegation` before implementation work, but do not delegate
  live-safety decisions.
- [confirmed] Source authority is executable research code/tests/current bytes,
  then current docs. Prompts, plans, memory, and prior summaries are secondary.

### A3. Product boundary

- [confirmed] The bridge's foundational purpose is to own scripted-track deck
  state, play/seek/pause/loop, elapsed/BPM/beat, while SoundSwitch holds the
  scripted timeline and renders laser DMX.
- [confirmed] The end goal is to export project timelines and reproduce
  SoundSwitch's Universe-0 CH1-19 bytes without SoundSwitch running.
- [confirmed] The bridge does not need channel meaning if it can reproduce the
  bytes.
- [confirmed] Two Venue fixture groups, `0x493` and `0x496`, are mirrored in the
  current project and produced identical comparisons in all new captures.
- [confirmed] Runtime integration is out of scope until this spec's byte-exact
  gates pass. Do not implement the bridge renderer or Enttec output path here.

### A4. Already-proven facts that must not be re-litigated without contrary bytes

- [confirmed] A5/SANFRANDISCO legacy scripted capture is 16/16 full-frame exact:
  14 positive cues plus two clears, using one-based references.
- [confirmed] Cue-reference convention is provenance-dependent: controlled
  legacy records are one-based, controlled newly created records are direct,
  and edited legacy files can be MIXED with no per-record byte discriminator.
- [confirmed] Ambiguous and MIXED files must fail closed.
- [confirmed] Captured legacy autoloops are one-based. The current autoloop
  layered model reproduces 29/30 distinct wire frames; this result does not prove
  representative scripted-track parity.
- [confirmed] Raw reference zero clears the main layer in the validated A5/
  autoloop scope. CH8/CH9/CH11 persistence is not a universal scripted rule.
- [confirmed] In-App Demo has an unsupported layout and remains excluded.

### A5. Canonical current evidence

Start with `/tmp/ss_scripted_validation_summary_20260620.json`, size 19,072,
SHA-256
`9ec44192a6bfaab5b62f336b0b86e6d0e51cb970c99b5381e05d6a54dfe716ff`.
If an artifact is missing, do not reconstruct its result from memory; either
find its identical hashed copy or schedule a fresh operator capture under the
safety protocol.

| Run | Pcap / SHA-256 / size | Copied bridge log | Final reports |
| --- | --- | --- | --- |
| TITANIUM uninterrupted | `/tmp/ss_scripted_probe_FC10FC02-93C2-418F-8815-16088884DA42_retry1.pcap`; `1e98137f2f236e8c1020a964c76d9063244f59afd374db89a0629c38b50351f5`; 12,587,610 | `/tmp/ss_scripted_probe_FC10FC02_retry1_bridge.log` | `/tmp/ss_scripted_final_titanium_{493,496}.json`; direct hypothesis beside them |
| Opalite uninterrupted | `/tmp/ss_scripted_probe_74044FA4-45A5-4FE6-85ED-F8D8698A346A.pcap`; `15a3acc859a0736df8106f937edd69cff54d283c1d2ab4c04153881b615d4521`; 12,525,404 | `/tmp/ss_scripted_probe_74044FA4-45A5-4FE6-85ED-F8D8698A346A_bridge.log` | `/tmp/ss_scripted_final_opalite_{493,496}.json`; direct hypothesis beside them |
| New Sky uninterrupted | `/tmp/ss_scripted_probe_AE9E3C61-AF40-4392-80B4-380D39C631B9.pcap`; `70731ea37cb4e421d56420b2cab22e1a0c3b691401a9abe7aea585a4320841d0`; 15,453,860 | `/tmp/ss_scripted_probe_AE9E3C61-AF40-4392-80B4-380D39C631B9_bridge.log` | `/tmp/ss_scripted_final_newsky_{493,496}.json`; direct hypothesis beside them |
| Opalite transport | `/tmp/ss_scripted_transport_74044FA4-45A5-4FE6-85ED-F8D8698A346A.pcap`; `ac6c8d99c13b55adcf66fc3063027ad8769102a918b108091fba16ed1d5782d6`; 19,372,398 | `/tmp/ss_scripted_transport_74044FA4-45A5-4FE6-85ED-F8D8698A346A_bridge.log` | `/tmp/ss_scripted_final_transport_{493,496}.json`; direct hypothesis beside them |

The corresponding copied AppLogs are in same-prefix `_logs/` directories.
SoundSwitch AppLogs explicitly prove that the default-project SSID file was used
for each uninterrupted capture.

Live read-only source paths and handoff hashes:

- TITANIUM
  `/Users/bbui/Music/SoundSwitch/default.ssproj/{FC10FC02-93C2-418F-8815-16088884DA42}.ssfile`,
  SHA `4c365b8084098b2488944d0aaf3389b0d8fa694da1a3ca406d84647efb027953`.
- Opalite
  `/Users/bbui/Music/SoundSwitch/default.ssproj/{74044FA4-45A5-4FE6-85ED-F8D8698A346A}.ssfile`,
  SHA `53e7b70656eb622d67be9b5d528612baa30cb261f510be62f0f50adee19de897`.
- New Sky
  `/Users/bbui/Music/SoundSwitch/default.ssproj/{AE9E3C61-AF40-4392-80B4-380D39C631B9}.ssfile`,
  SHA `b136912ef09111b265c596cf0833b794aa521b5fb2af7ed9c5a58ada9a2b2b9c`.
- Venue SHA
  `f34bfc796e9e589c7eb4707ee4f223c6ea6fd2f597d08622d30370f16a2a3398`.
- `SSAutoLoop1.ssfile` SHA
  `13e085b2e7c47f471af0fda5d605d7c873374e9a2c3b25d96667689fc7b7cf48`.
- Controlled MIXED negative:
  `/tmp/soundswitch_finish_IiVlD1/WHYB-AFTER.ssproj/{528E8B22-BD17-41B9-A111-275D3E8B3031}.ssfile`,
  SHA `63302346d324315fccc0759df5931935214fef701d58840cc5d117ce025ad3ee`.

### A6. Current measured result: completion is falsified

| Track | Distinct Universe-0 states | One-based event samples | Direct hypothesis | One-based bridge-position samples | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| TITANIUM | 16 | 16/64 | 0/64 | 21/57 | blocked |
| Opalite | 21 | 23/39 | 0/39 | 48/57 | blocked |
| New Sky | 34 | 304/367 | 45/367 | 53/71 | blocked |

- [confirmed] Both mirrored group reports are identical for all three tracks.
- [confirmed] One-based is strongly preferred on wire for all three captured
  default-project files.
- [confirmed] Opalite's prior label "controlled newly-created direct" is
  contradicted by current default-project wire: one-based is 23/39 while direct
  is 0/39. Do not resolve convention from that label, title, SSID, file size, or
  best-fit alignment alone. Establish its actual lineage or replace it with a
  controlled existing direct candidate.
- [confirmed] Unconstrained time fitting previously manufactured false direct
  matches. Evidence reports must use `--bridge-log` or explicit `--start-epoch`.
- [confirmed] Event comparison must render expected state at
  `event_elapsed + sample_delay`; compound cues may be only 1-2 ms apart.

### A7. Decoupled-color scripted failure

- [confirmed] New Sky sequence 342, `WHITE` at 214,807 ms, emits CH8/CH9
  `172/255` byte-exact.
- [confirmed] Sequence 343, decoded `BUILDUP SPEEDUP` at 215,483 ms, has the
  current parsed Venue patch `{15: 207}`. The current model expects
  CH8/CH9/CH15 `172/255/207`; wire emits `0/255/0`.
- [confirmed] The same behavior repeats at sequence 344/345,
  217,137/217,387 ms.
- [confirmed] Therefore "channel omitted from decoded patch" does not yet mean
  "persist it" for representative scripted records. The likely missing concept
  is cue type/mask/layer/reset semantics, not another global control-channel
  tuple.

### A8. Transport result

- [confirmed] Dedicated Opalite report is 60/89 exact position samples overall;
  stopped/unloaded samples intentionally expose the difference between timeline
  render and all-zero transport policy.
- [confirmed] Backward seek at 16:38:24.985 to 83,157 ms is full-frame exact.
- [confirmed] Forward seek at 16:38:50.011 to 180,203 ms is full-frame exact.
- [confirmed] The first forward seek/pause at 123,643-128,880 ms fails on the
  same channels as uninterrupted Opalite's 116-133 s base-render residual. Wire
  holds byte-for-byte steady across pause and returns to an exact frame at
  133,887 ms after resume. This is not transport drift.
- [confirmed] The short loop oscillates between 210,601 and 212,311 ms; all
  22 logged loop-window position samples are exact.
- [confirmed] Re-fire is exact on all seven actually-playing samples starting
  at 1,978 ms. A prior zero-position arm observation occurred before actual play
  and must not be mislabeled a render failure.
- [confirmed] Both confirmed `stop` markers are all-zero exact. A
  `scripted->idle` log marker may precede the wire clear by more than the current
  30 ms sample delay.
- [confirmed] Unload after stop yields nine all-zero wire samples and no new DMX
  transition, but bridge status retains stale Opalite filename/mode while
  position resets to zero. A direct unload-from-active-frame capture remains
  required.

### A9. Current research seams

- [confirmed] `tools/ssfmt/re/layered_renderer.py:153`
  `render_at_elapsed(...)` rebuilds from explicit initial state in
  `(elapsed, source_sequence)` order and fails closed on unresolved provenance.
- [confirmed] `tools/ssfmt/re/layered_renderer.py:225`
  `render_playback_state(...)` models playing/paused by elapsed and
  ended/unloaded as all-zero.
- [confirmed] `tools/ssfmt/re/validate_scripted_capture.py:207` anchors track
  zero to the nearest copied bridge `arm-scripted` observation.
- [confirmed] `validate_scripted_capture.py:250` parses bridge position samples;
  line 309 parses idle/stop zero-output observations; line 430 renders at the
  sampled compound-cue time.
- [confirmed] `tests/test_ssfile_reference_convention.py` currently has 21
  focused passing tests. Full suite at handoff: 1,836 tests OK, three skipped,
  one expected failure.

### A10. Root-cause hypotheses that are not yet facts

- [assumed] Venue cue records contain or imply an enable/reset/type mask that
  `parse_venue_cues.py` does not yet expose correctly for cues such as
  `BUILDUP SPEEDUP`.
- [assumed] Different cue classes may have different layer ownership or reset
  behavior. A single global `{8,9,11}` control set is probably insufficient.
- [unknown] Whether the TITANIUM and Opalite residual clusters share the same
  missing cue mask/type field as New Sky.
- [unknown] The trustworthy provenance lineage of the current Opalite bytes.
- [unknown] Which existing unmodified project/corpus track is the best
  discriminating DIRECT wire target.

These hypotheses guide experiments; they are not documentation conclusions.

## Part B - Tasks (implement exactly in order)

### Absolute rules for all tasks

- Do all useful offline work before requesting any operator playback.
- Research helpers may read project bytes and captures but may never become a
  bridge runtime dependency.
- Captured frames are verification oracles, never renderer inputs or hidden
  state seeds.
- Do not overfit a rule to one track. Every candidate model must be evaluated
  against A5, TITANIUM, Opalite, New Sky, both mirrored groups, and relevant
  autoloop regressions.
- Preserve the global direct/one-based fail-closed gate. Do not add a heuristic
  "choose whichever matches more wire frames" production resolver.
- Do not edit tests to bless current residuals. A residual remains a failure.
- Do not ask the operator to choose implementation mechanics. Ask only for
  fixture safety/live-operation approval or genuinely required behavior scope.

### Task 0 - Re-establish evidence integrity

1. Read the minimum authority path: `AGENTS.md` -> `soundswitch_research`
   contract -> this spec -> exact research tools/tests -> current evidence JSON.
2. Run `git status --short` and record HEAD. Preserve every existing change.
3. Verify the summary, four pcap hashes/sizes, bridge logs, AppLog directories,
   three live `.ssfile` hashes, Venue hash, and MIXED negative hash.
4. Re-run all final reports from the pcaps with explicit `--bridge-log`,
   `--reference-rule one_based`, `--owner-deck 1`, control channels `8,9,11`,
   and both `0x493`/`0x496` groups. Re-run direct as a labeled hypothesis only.
5. Confirm the regenerated counts match A6. If not, stop documentation work and
   explain the exact byte/tool drift first.
6. Verify current bridge health read-only with `$rbss-bridge-verify` before
   relying on live logs. Do not change its state.

### Task 1 - Build a deterministic scripted residual corpus

Add or extend a read-only tool under `tools/ssfmt/re/` that consumes final
validator JSON and emits, for every non-exact event/position:

- track/SSID, pcap and source hashes, group, event/source sequence, elapsed;
- raw reference, direct and one-based candidates, GUID, cue name/type if known;
- full raw Venue cue-record bytes and offsets;
- parsed patch plus exact expected/actual/delta bytes;
- previous and next timeline records, compound-cue spacing, active control
  state, and whether the same residual occurs in uninterrupted and transport
  runs;
- a stable residual-signature key based on changed channels and cue identity,
  not wall time.

The output must cluster cross-track residuals and explicitly show exact uses of
the same cue/GUID. Add focused synthetic tests for deterministic ordering,
duplicate states, adjacent compound cues, missing GUIDs, and both fixture groups.
Do not infer semantics in this task.

### Task 2 - Recover Venue cue enable/reset/type semantics

1. Trace `parse_venue_cues.py` from raw record boundaries. For each exact and
   failing cue cluster, expose all currently skipped bytes/bitfields with offsets
   and stable names such as `unknown_u8_0xNN`; do not name a field semantically
   until evidence supports it.
2. Correlate raw fields against:
   - New Sky sequence 342-345 (`WHITE` / `BUILDUP SPEEDUP`);
   - Opalite 116-133 s residuals and exact neighbors;
   - TITANIUM 147-152 s residual clusters;
   - exact A5 and autoloop cue uses;
   - controlled mutation evidence already under
     `/tmp/soundswitch_finish_IiVlD1` and
     `/tmp/soundswitch_baseline_current_SCS2oe`.
3. Determine whether zero means explicit write, disabled/unchecked, layer
   clear, or cue-type reset on each channel. Prove the result from at least two
   independent cues or one controlled before/after corpus plus wire.
4. If existing bytes cannot distinguish the behaviors, identify the smallest
   existing unmodified project/corpus playback that discriminates them. Do not
   request a live capture until the prediction is written down byte-for-byte.

### Task 3 - Implement candidate cue-layer semantics as pure research code

1. Extend `layered_renderer.py` through explicit cue metadata/layer operations;
   do not scatter track-name or GUID exceptions.
2. Keep `render_at_elapsed` history-independent and `render_playback_state`
   explicit about transport.
3. Model enabled writes, explicit zero writes, persistence, layer clears, and
   cue-type resets separately if the recovered bytes require them.
4. Emit a trace for every applied operation so a mismatch can be attributed to
   a source record and rule.
5. Run the candidate model across all evidence. A model is rejected if it
   improves one target by regressing any previously exact A5/autoloop frame or
   requires capture bytes as input.
6. Iterate Tasks 1-3 until all existing normal scripted captures are full-frame
   exact or a single falsifiable missing-byte prediction requires a capture.

### Task 4 - Close reference provenance without heuristics

1. Reconstruct current Opalite lineage from project copies, hashes, controlled
   scratch evidence, logs, and snapshot manifests. Explain why the current bytes
   render one-based despite the older "new direct" label.
2. Inventory existing unmodified DIRECT candidates from the controlled corpus.
   Prefer a track with two cues whose direct and one-based rendered frames differ
   on multiple stable channels.
3. Record its source hash, project path, AppLog-resolvable SSID, predicted direct
   frame, predicted one-based frame, and exact discriminating channels before
   playback.
4. If no trustworthy existing candidate exists, report that specific authority
   blocker. Do not modify a SoundSwitch project to create one under this spec.
5. Keep controlled MIXED/edited files non-exportable. Re-run the validator gate
   and focused test proving exit-before-render.

### Task 5 - Request only evidence-driven operator captures

Do not perform this task until Tasks 0-4 have produced byte-level predictions.
For every run:

1. Choose a fresh `/tmp/<descriptive>.pcap`; prove it absent or hash the prior
   file. Hash project inputs, current AppLogs, and `/tmp/bridge.log` before `say`.
2. Post one visible action beginning `OPERATOR ACTION: confirm fixtures are
   safe.` Include the exact operator `sudo tcpdump` command and one playback or
   transport operation only.
3. Speak the same action with macOS `say` after the baseline.
4. Monitor pcap size, AppLog mtime, bridge mode/position, and project hashes.
   Never wait for a chat response.
5. After the requested event, establish a new baseline before speaking the next
   operator action.
6. At close, separately request Ctrl-C and copied AppLogs/bridge log, then hash
   every artifact.

Minimum remaining discriminating captures, unless offline bytes make one
unnecessary:

- New Sky: the 214.807-217.387 s WHITE -> BUILDUP SPEEDUP sequence after a
  byte-level cue-mask prediction exists.
- TITANIUM: the 147-152 s residual cluster after its candidate cue operations
  are predicted.
- Opalite: 116-134 s after its residual rule is predicted.
- Transport: pause/resume at the already-exact Opalite 180.203 s state, then
  unload directly from an active exact frame in a separate action.
- Reference convention: one existing controlled DIRECT candidate with
  discriminating stable frames.

Do not capture BLACKPINK/JUMP or clean Where Have You Been merely to increase
track count. Capture them only as holdout validation after the candidate model
is already exact on the three current tracks.

### Task 6 - Holdout validation and no-overfit proof

After the model fits all existing evidence:

1. Freeze the rule and tests before opening the holdout result.
2. Capture or use a previously untouched real scripted holdout from
   BLACKPINK/JUMP (`1FD042ED`) or clean Where Have You Been (`528E8B22`, SHA
   `1f740632...`).
3. Require full-frame event and position parity for both mirrored groups with no
   rule changes.
4. If the holdout fails, return to Tasks 1-3; do not patch in a track exception.

### Task 7 - Update every contract doc and close honestly

Update every `soundswitch_research.docs_update` file, especially:

- `docs/research/soundswitch_ssfile_format.md`;
- `docs/plans/active/soundswitch_validation_matrix.md`;
- `docs/plans/active/soundswitch_standalone_laser_exporter_spec.md`;
- this handoff;
- `docs/status/active_work_registry.md`;
- `docs/agents/change_contracts.yml` if tool/docs routing changes.

Remove superseded match counts and hypotheses. Preserve artifact hashes and
explicit scope. Do not mark the runtime exporter implemented; this task closes
research verification only.

## Part C - Invariants That Must Still Hold

- The bridge remains exactly one worker process; menubar, Laser Pad, shell
  wrapper, and current command processes are not extra workers.
- No bridge runtime module imports `tools/ssfmt/re`.
- No blocking I/O is added to the 200 Hz push loop.
- No SoundSwitch project, live config, serial device, MIDI map, or Enttec daemon
  is changed.
- Universe 1 remains zero in the declared evidence; Universe-0 CH1-19 is the
  compared surface.
- Fixture groups `0x493` and `0x496` are evaluated independently even when their
  expected/output bytes mirror.
- Source convention resolution fails closed before rendering on ambiguous or
  MIXED provenance.
- Ended/unloaded output is all-zero; a delayed wire clear is measured rather
  than hidden by an arbitrary sample delay.
- Status remains **SOFTWARE/WIRE-VALIDATED ONLY - PHYSICAL HARDWARE-UNVALIDATED**.

## Part D - Tests and Checks

Add focused tests for every recovered field/rule and adversarial case. At
minimum retain and extend:

```bash
python3 -m py_compile tools/ssfmt/re/*.py
python3 -m unittest tests.test_ssfile_reference_convention
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Also regenerate all final validator reports and an updated canonical summary.
Record report, source, pcap, Venue, AppLog, and bridge-log hashes. Staleness is
advisory; unrelated LED/config warnings must be reported but not fixed in this
scope.

## Part E - Acceptance: Do Not Call This Done Until Every Box Passes

- [ ] At least TITANIUM, Opalite, New Sky, A5, and one untouched holdout are
      full-frame byte-exact for all in-window scripted event samples on groups
      `0x493` and `0x496`.
- [ ] No captured normal scripted residual remains unexplained or hidden by a
      wider sample tolerance.
- [ ] The New Sky WHITE -> BUILDUP SPEEDUP decoupled-color sequence is
      byte-exact under a byte-derived cue mask/layer rule.
- [ ] Forward seek, backward seek, pause, resume, loop, re-fire, natural end,
      stop, and unload-from-active-frame are demonstrated at exact base-render
      positions with no drift or history dependence.
- [ ] Confirmed stop/end/unload clear timing is measured and all-zero policy is
      byte-exact.
- [ ] Current Opalite provenance is explained; one trustworthy existing DIRECT
      track is wire-discriminated; legacy one-based remains proven.
- [ ] MIXED/edited and ambiguous files fail closed before rendering.
- [ ] A5 and autoloop previously exact frames do not regress.
- [ ] Captured frames are never renderer input.
- [ ] All required docs/checks/tests pass.
- [ ] No bridge runtime, SoundSwitch project, live config, MIDI/DMX path, or
      output adapter was modified.

If any checkbox fails, the renderer is not done. Continue the task. If progress
requires authority forbidden by this spec, present the exact byte-level blocker
and request only that authority; do not substitute an assumption.

## Adversarial Self-Review

Before closeout, actively try to falsify the model with these cases:

- the same GUID exact in one track but residual in another;
- a zero byte that means disabled in one cue and explicit clear in another;
- two cues 1 ms apart sampled as one settled frame;
- a repeated wire state that creates a false time anchor;
- a transport jump into a known base-render residual interval;
- an arm-at-zero before actual play;
- a loop shorter than the five-second bridge position log cadence;
- idle marker preceding actual zero wire clear;
- an unload that resets position while retaining stale metadata;
- a direct/one-based hypothesis that matches by coincidence rather than
  provenance.

The spec prevents these failures by requiring bridge/log anchors, settled-time
rendering, explicit transport state, raw cue metadata, cross-track clustering,
holdout validation, and provenance fail-closed behavior.

## When You Finish

Report:

1. the recovered byte fields and renderer rules with file:line references;
2. per-track and per-transport byte-exact counts for both mirrored groups;
3. all artifact/source/report hashes and paths;
4. convention/provenance result for every supported track and all rejected
   MIXED/ambiguous files;
5. exact tests and docs checks;
6. a plain-language operator summary: what would change live in a future
   renderer, what remained unchanged in this research task, healthy log/wire
   behavior, physical-hardware limits, and the exact approval/restart gates for
   any later runtime integration.

Do not restart or toggle the bridge as part of closeout. Do not claim physical
hardware validation from passive Art-Net evidence.

## Session Progress and Blockers — 2026-06-20 (HEAD c6d1a50, no code changed)

Status against Part E: **NOT closed.** Static color/dimmer cues are byte-exact;
effect/strobe cues are not. Repo healthy: full suite **1842 OK** (3 skipped, 1
expected failure); `py_compile`, both focused tests, `check_docs_metadata`,
`check_agent_contracts`, `check_docs_drift`, `git diff --check` all pass.

Verified this session (byte + wire grounded; captured frames used only as oracle):

- **Task 0 done.** Evidence re-verified: Venue SHA `f34bfc79…`, SSAutoLoop1 SHA
  `13e085b2…`, three live `.ssfile` hashes, summary
  `/tmp/ss_scripted_validation_summary_20260620.json`. Counts reproduce A6.
- **Task 1 done.** `tools/ssfmt/re/build_scripted_residual_corpus.py` +
  `tests/test_scripted_residual_corpus.py` cluster residuals across tracks/groups
  (oracle-only, no renderer feedback). 190 residual observations, 55 clusters on
  group 0x493.
- **Fixture profile decoded** (group 0x493/0x496, profile `b8ad2201…`), 19
  channels: CH1 On/Off, CH2 Auto Mode, CH3 Static Pattern, CH4 Static Pattern
  Selection, CH5 Pattern Size, CH6 Horizontal Adjustment, CH7 Vertical
  Adjustment, CH8 Color, CH9 Color Speed, CH10 Pattern Line, CH11 Strobe,
  CH12 Rotation Z, CH13 Rotation X, CH14 Rotation Y, CH15 Horizontal Movement,
  CH16 Vertical Movement, CH17 Zoom, CH18 Gradient, CH19 X/Y Wave.
- **Operator-confirmed model (authoritative):** the laser is controlled **only by
  attribute cues**, rendered as a **layered persistent buffer**; there is **no**
  effect engine and **no** attribute→DMX transform (DMX = attribute value,
  identity). **CH11 is the only strobe.** This *invalidates* the earlier
  "fixture-profile transform / cue-class transform" hypothesis.
- **Task 2 root cause (corrected):** residuals are NOT a value transform and NOT
  a validator sampling artifact (settled-midpoint render = same 304/367 as the
  event sampler). They concentrate in **rapid compound-cue regions** (e.g. New
  Sky strobe triplets MASTER STROBE→INTENSIFY→STROBE ~476 ms apart at 38–60 s,
  and the 214–217 s WHITE↔BUILDUP SPEEDUP pair). There, the timeline
  raw-references do **not** map to the wire-observed cue under any single
  consistent rule yet found: at 38.5 s, raw_ref 3 renders MASTER STROBE (idx2)
  but the wire shows STROBE (idx1); raw_ref 4 → INTENSIFY 1 (idx3) matches; raw_ref
  2 → STROBE (idx1) but wire shows WHITE DOT STROBE. The per-event offset is
  non-uniform (−1, −2, …), so this is a **reference-resolution / timeline-parse
  discrepancy in dense regions**, not a render-layer bug. Static/isolated cues
  (the large majority) render byte-exact.
- **Falsified** (data, not blessed): a global "value-0 = skip/disabled" rule
  breaks **290/367** New Sky events. Zeros are normally written.

Remaining blockers preventing Part E closure here:

- **B1 — investigated to exhaustion (offline closed):** the per-track `.ssfile`
  dictionary + `one_based` renderer is byte-exact for the vast majority
  (New Sky 304/367; every `raw_ref ≥ 4` tested resolves `raw−1` ✓; clear-control
  `raw_ref 0` is 109/111). The misses are a **small per-file set of anomalous
  references to the effect-cue family**: New Sky `raw ∈ {1,2,3,13}` (STROBE,
  MASTER STROBE, INTENSIFY, BUILDUP SPEEDUP); TITANIUM `raw ∈ {24,196,211–215}`;
  Opalite `raw ∈ {1,3,4,18,50,52}`. These resist **every** rule tested against
  the wire oracle — one_based, direct, dictionary-position (0/367), venue
  catalog-ordinal direct/one_based/+1 (16/0/40 of 247), zero-skip (breaks
  290/367), and the (operator-refuted) fixture-profile transform. Offsets are
  non-uniform per file (raw3→idx1, raw1→idx2), and at least one reference
  (New Sky raw2 → stable CH11=227) resolves to a cue **not present in the file's
  own 104-cue dictionary**. CH11 is stable across the window, so it is not a
  dynamic strobe. This is the byte-signature of **MIXED/edited-provenance
  records** (A4: "edited legacy files can be MIXED with no per-record byte
  discriminator" → fail closed). It cannot be reduced to a renderer rule or
  proven per-record from bytes alone; resolving whether these are MIXED-edited
  records or a missing reference indirection needs a **controlled mutation
  capture** (operator-gated → B2).
- **B2 (authority):** the transport unload-from-active-frame box, the Opalite
  provenance / one DIRECT-discriminating reference box, and the holdout box all
  require fresh operator-orchestrated live captures. The live-safety boundary
  (A1) makes these operator-owned; the agent may not run tcpdump or playback.

Per Part E's escalation clause, these are presented as exact blockers; no
assumption was substituted and no residual was blessed into "supported."
