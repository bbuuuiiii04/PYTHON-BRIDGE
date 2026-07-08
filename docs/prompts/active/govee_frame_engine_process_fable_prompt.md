---
doc_status: current
truth_level: prompt-artifact
last_verified_commit: d2ed39c
last_verified_date: 2026-07-08
validation_scope: Fable 5 prompt text only; commissions design validation + spec authoring + orchestrated implementation of the Govee frame-engine process; no hardware action authorized by the prompt itself
---

# Fable 5 Prompt — Govee Frame-Engine Process: Validate, Spec, Orchestrate

**Target model:** Claude Fable 5 · **Effort:** `xhigh`

Paste everything below the rule into Fable. It is self-contained.

---

This is benign local software work on Brandon's DJ lighting bridge (`rb_ss_bridge_v2`, this repo): moving an LED frame-rendering loop into its own OS process for smoother timing. "Frames" are UDP color packets to a consumer Govee LED strip on the LAN; "process scheduling" here means ordinary macOS task priority, nothing adversarial.

## Mission

Brandon wants the bridge's Govee realtime frame engine lifted into its own small process so LED animation can never again be starved by the rest of the bridge. You own this workstream end to end: first judge whether the design is actually right, then write the implementation spec, then orchestrate the implementation through a separate Opus session and adversarially review what comes back. Brandon is the operator, not an engineer — your final summary must read in plain English. This platform work is preparation for the LIGHTING ENGINE v2 choreography work that will draw on it.

## What is already established (do not rediscover; verify only where marked)

Measured on this machine, 2026-07-08, with the production classes (a fresh audit session ran these; treat as trustworthy inputs, spot-check cheaply if you wish):

- `GoveeRealtimeRunner` + `GoveeFrameRenderer` + `GoveeRealtimeTransport` at 60 segments in a clean foreground process deliver **60.0 fps** (dry-run and localhost UDP). The renderer costs 0.03–0.54 ms/frame; packet build 0.03 ms.
- Under `taskpolicy -b` (macOS background band) the same code drops to **20.5 fps** because `time.sleep(1/60)` overshoots to ~88–95 ms. Per-thread QoS (`pthread_set_qos_class_self_np`) and an `NSProcessInfo` NSActivity latency-critical assertion do **not** rescue a darwin-bg process.
- The live bridge and the standalone LED Pad — both long-running faceless processes — each deliver only ~28–29 fps, decaying to ~16.5 fps when the bridge is busy (two decks + laser/SoundSwitch pipeline) with dips to 1–7 fps during reader memory scans. Which exact macOS mechanism demotes them is **[unknown]** — the design must not depend on knowing; it must control the band explicitly and self-measure.
- The standalone LED Pad (`tools/led_pad_playback.py`) already runs this exact trio in its own process — it is the working precedent, including its ownership handshake with the bridge via the status/command files.

Repo context you must read before judging the design: `govee_realtime_runner.py`, `govee_realtime_transport.py`, `govee_frame_renderer.py` (large — delegate reads to cheaper subagents), `beat_sync_engine.py`, `led_dispatch_coordinator.py`, `govee_owner_state.py`, the LED wiring in `__main__.py` (~lines 520–600 and the `set_beat_provider` bind near line 1155), `get_active_beat_anchor` in `led_dispatch_policy.py:286`, and `docs/subsystems/led_govee.md`. Source-of-truth order: code → tests → config → docs.

**Coordination constraint (hard):** AWR-145 (`docs/plans/active/govee_led_phase1_blackout_keepalive_spec.md`) is being implemented RIGHT NOW by an Opus session in tmux session `claude`, editing the same files (runner, coordinator, policy, state_manager, pad playback). Your validation and spec authoring are read-only and can proceed in parallel, but the spec must be written against the post-AWR-145 surface (razer keepalive, `request_activate_assert`, `request_brightness`, pad auto-stop), and **implementation must not start until AWR-145's commits have landed and its tests are green** — watch `git log` and the `claude` session. Never revert or fight its changes; the worktree is shared and dirty-worktree discipline applies (no destructive git, ever; work directly on `main`; no branches or extra worktrees).

## The design to validate (Brandon's accepted direction, shape open to you)

One child process ("frame engine") owned by the bridge, containing runner + renderer + transport, being the bridge's only realtime writer to the strip. The bridge keeps the decision layer and feeds the process a beat-anchor stream plus look/blackout/brightness commands over a local channel you choose (unix socket, loopback UDP, or pipe — justify the pick; the anchor is a ~5-field snapshot at tens of Hz, commands are occasional). Requirements the design must satisfy: explicit scheduling-band control at launch plus an achieved-fps self-report in its status so a regression is a number, not a feeling; crash/orphan safety (bridge death → frames stop and strip goes dark, never a zombie writer; process death → bridge respawns it and the room recovers); clean shutdown ordering; the AWR-145 blackout guarantees survive the move (keepalive, activate-assert, brightness backstop now execute inside the frame process); the Pad mutual-exclusion behavior still holds; and the 200 Hz push loop gains no blocking I/O talking to the child. Cloud dispatch stays in-bridge as today. If validation finds the design wrong or a simpler variant strictly better (e.g. band-fixing alone, or a subinterpreter), say so with evidence and a verdict — Brandon prefers an honest NOT READY over a polite yes.

## Deliverables, in order

1. **Validation verdict** — `READY` / `READY WITH GAPS` / `NOT READY`, with evidence-tied findings (file:line), each claim labeled confirmed / assumed / unknown. Gaps must name exactly what closes them.
2. **Implementation spec** at `docs/plans/active/govee_frame_engine_process_spec.md`, registry row AWR-146 in `docs/status/active_work_registry.md`, following the repo spec format in `.claude/skills/codex-spec/SKILL.md` (Part A–E, absolute rules, invariants, pure-seam tests, acceptance incl. the `led_govee` contract's docs_update and the three hard checks in `tools/`). Extend `docs/agents/change_contracts.yml` first if new files fall outside existing contracts.
3. **Orchestrated implementation.** Dispatch the spec to an idle Opus session — use tmux session `claude3` (or another idle `claude*`; `claude` is busy with AWR-145, `claude2` is you). Convention: send `/clear`, wait, send a short kickstart pointing at the spec file, then verify it actually submitted — typed prompts sometimes sit in the input box needing one extra Enter; confirm with `tmux capture-pane`. The Opus session may use its own subagents. You monitor, you do not implement in your own session.
4. **Adversarial review** of the full diff against the spec's invariants — strict about evidence: live-safety first (blackout paths, single-writer, no push-loop blocking I/O, fail-dark), then correctness, then tests. Findings severity-first with file:line; require fixes and re-review until clean or genuinely blocked.
5. **Final report in chat, for Brandon:** outcome first, plain English, what changed, what was verified (including the measured fps of the new process from the test suite's simulated run — live fps needs his next mix), what stays unproven until hardware, and rollback (git revert + menubar restart). Status language: implemented / software-tested / hardware-unvalidated only.

## Boundaries

Read-only toward the rig: no bridge restart or launch, no frames or commands to the strip or its cloud, no config edits to the live gitignored config, never `git clean`. Tools allowed: full repo read, `git log/show/diff`, running the test suite, tmux orchestration of `claude*` sessions as described, file writes limited to the spec, registry, contract, and docs the contract names. Subagents: cheaper-tier only, never Fable-tier; announce spawns. Do not ask any model to reveal its private reasoning. If SoundSwitch or laser behavior would be touched, stop — out of scope.

## Success criteria

The spec is executable without guessing (exact names, exact call sequences, exact test seams); the implemented result keeps every AWR-145 test green plus its own; the frame process proves 60 fps in a foreground band on this machine via its self-report in tests; blackout/fail-dark behavior is demonstrably not weakened (tests, not assertions); and Brandon can read the final summary cold. Rejection conditions: implementing in your own session; starting implementation before AWR-145 lands; a design that silently drops the blackout guarantees or adds push-loop blocking I/O; upgrading status language beyond software-tested.
