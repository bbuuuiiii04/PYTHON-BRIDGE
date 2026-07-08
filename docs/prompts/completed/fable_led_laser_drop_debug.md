# Fable 5 prompt — dissect and root-cause the LED + laser misbehavior from the 2026-07-07 session

**Target model:** Claude Fable 5. **Effort:** xhigh. (Multi-source, ambiguous, long-horizon, live-lighting safety — worth the quota.)

---

## Benign scope

This is benign local software work for Brandon's DJ lighting bridge. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning-extraction task. "Laser," "strobe," and "blackout" are stage-lighting looks driven over MIDI/DMX. Review only normal software correctness, tests, maintainability, runtime safety, and operator-visible lighting behavior inside the named scope.

## Mission

Brandon ran a real mixing session and the LED and laser lighting misbehaved in a repeatable set of ways. Two headline problems: (1) the RT LED effects **flicker and strobe during live bridge runtime** — the same effects play clean and stable in the LED Pad with the bridge and Rekordbox not running; (2) the LED "drop" looks **freeze on the first look and never cycle** through a drop section. I need you to dissect the whole session, tie every reported symptom to a **confirmed root cause in the code**, and hand me a fix plan Codex can execute. This feeds Codex; **do not implement anything** — the deliverable is diagnosis plus proposed fixes, and I approve fixes before any code changes.

Why it matters: this bridge drives lighting live in front of people. A wrong "confident" root cause that gets implemented can make the next set worse. I would rather you reach fewer causes that are each proven than a full list of guesses.

## What behaves correctly (do not chase these)

Idle fallback on track **end** works. RT/DIY look cycling in **up-phrase** sections works *most* of the time. The pre-drop blackout arms correctly on true drops much of the time. Palette *switching* on deck change generally works. Treat these as the baseline the broken cases deviate from.

## Deliverable and format

A root-cause debug report, written to be read cold:

1. **Outcome first** — one paragraph: how many distinct root causes you found, and which one explains the dominant "drop won't cycle" symptom.
2. **Root causes**, most-impactful first. For each: the operator-visible symptom in plain words, the confirmed mechanism in code (`file:line`), the intended behavior it violates (cite the authority doc section), the log evidence (`ts` epoch + what the events show), a claim label (confirmed / assumed / unknown / rejected), and a proposed fix as **direction for Codex** (which function, what change, what stays untouched) — not a diff, not implemented.
3. **Symptom → cause map** — every cluster in the observational log below mapped to a root cause, to "same cause as #N" (dedupe shared causes), to "observation artifact / log-vs-eye mismatch," or to "unknown — needs a specific live capture," naming the capture I'd run.
4. **Verdict on the pending spec** (see below): is `drop_two_hit_rule_restore_spec.md` the correct and *complete* fix for the drop-cycling cluster, or does the code/log evidence show it needs changes? `CORRECT & COMPLETE` / `CORRECT BUT INCOMPLETE` / `NEEDS CHANGE`, with reasons.
5. **Open decisions for Brandon** — only real taste/behavior calls (e.g. what the breakdown look *should* look like), not routine mechanics.

## The pending fix you must fold in — do not re-litigate

`docs/plans/active/drop_two_hit_rule_restore_spec.md` already exists and **should be restored** — that is a settled operator decision (Brandon, 2026-07-07): a drop section gets a drop look on the true drop and on the 2nd chorus marker; any further chorus marker in the section demotes to post-drop. The ×64 smart-drop marker collapse from AWR-131 stays. **Do not argue whether to restore it.** Your job is to (a) confirm this deleted capped re-arm is in fact the mechanism behind the dominant "drop won't cycle / 2nd chorus doesn't fire" symptom, and (b) check the spec is complete and still matches current code before I hand it to Codex.

One drift lead to reconcile first: the spec's Part A claims `impact_allowed` in `drop_lifecycle.py` has *no* chorus label re-arm branch, but the current file already contains `current_phrase_is_chorus` / `phrase_start_crossing` checks near lines 50 and 70. Confirm what is actually present at HEAD before trusting Part A — the spec may be partly stale, or the branch may be present-but-inert. Code wins over the spec's prose.

## Evidence packet

**Source-of-truth order (this repo, non-negotiable):** executable code `*.py` → `tests/` → config examples → `runtime_status.py` → file tree → docs → old prompts/plans. If a doc conflicts with code, code wins. If you cannot verify a claim, mark it unknown — never guess.

**Intended behavior (what SHOULD happen — the correctness oracle). Ground every "this is wrong" claim in one of these; a behavior is only a bug if it violates *implemented* intent, not Brandon's in-the-moment surprise and not unbuilt future design.**

Critical framing — what is actually running this session: **the v1 lighting foundation plus the landed packages below, plus Feature 1 (track-identity color) of Lighting Engine v2.** The rest of Lighting Engine v2 is **PLANNED and NOT built** — both v2 docs' headers say so. So a behavior that merely fails to match unimplemented v2 is "not built yet," NOT a bug; do not report it as one. Read all relevant authority docs, but weight them by what is implemented:

- **The live system:** `docs/architecture/current_architecture.md`, `docs/architecture/runtime_invariants.md`, `docs/architecture/bridge_design.md` (threading + the 200 Hz push loop), and the code-verified subsystem cards `docs/subsystems/led_govee.md` + `docs/subsystems/laser.md`.
- **Landed behavior contracts (implemented/software-tested — these govern this session):** `docs/architecture/drop_presentation_authority.md` (per-drop presentation, AWR-119), `docs/architecture/palette_control_authority.md` (palette / manual override / rainbow, AWR-121), `docs/architecture/laser_blackout_authority.md` (blackout ownership + survival matrix, AWR-111), `docs/architecture/laser_color_authority.md` (laser color follow, AWR-111 plumbing), `docs/architecture/laser_director_design.md` (laser policy), and `docs/plans/active/lighting_v1_foundation_fix_spec.md` (v1 baseline stabilization, implemented).
- **The rendering + LED Pad path (central to the flicker cluster):** `docs/architecture/led_pad_template_lab_design.md` (the LED Pad — the clean-reference path), `docs/govee_realtime_design.md` (realtime frame rendering), `docs/led_look_director_design.md` (LED look director).
- **Feature 1 (implemented) + the v2 target (mostly planned):** `docs/architecture/lighting_engine_v2_authority.md` — §3 "The color story (Feature 1)" IS live (AWR-128, enabled in operator config); the rest of this doc and all of `docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` are the PLANNED target, correctness-authoritative only for F1 color, not for section/drop/breakdown mechanics.

**The session log (ground truth for what the code actually did):**
- `~/Library/Logs/rb_ss_bridge/current.jsonl` → resolves to `bridge-20260707-161941.jsonl`, which covers this whole session (started 16:19, Brandon's notes run 16:20–17:03 local; his "4:20"–"5:03" are PM). Each event has `ts` = epoch seconds and persists across restarts. Correlate each timestamped observation below to the `ts` window around it; the status file is snapshot-only, so use the JSONL.

**Code likely in scope (verify, don't assume ownership):**
- LED policy + drop cycling: `led_dispatch_policy.py` (`_led_drop_impact_allowed` ~1569, `LED_MAX_DROP_IMPACTS` =2 ~45), `led_dispatch_coordinator.py`, `led_look_director.py`, `led_color_engine.py`.
- Drop lifecycle (laser+LED shared): `drop_lifecycle.py` (`impact_allowed` ~59, `_impact_count`, `max_drops_in_a_row`), `drop_presentation.py`.
- Phrasing / section detection: `smart_phrasing.py` (`select_smart_drops` ~603, phrase-segment builder, pre-drop blackout arming ~396-429), `smart_rearm.py`.
- Flicker/render path (cluster #1): `led_dispatch_coordinator.py`, `govee_realtime_runner.py`, `govee_frame_renderer.py`, `govee_runtime_sender.py`, `govee_realtime_transport.py`, `beat_sync_engine.py` (breathing modulation + its beat/phase source), `led_pad_controls.py` and the `tools/` LED Pad server (:8766) for how the clean standalone path drives the same renderer. Compare the two.
- Laser: `laser_director.py` (policy), `laser_executor.py` (MIDI execution) — for "lasers randomly kick in during drop" and the laser-solo↔LED interaction.
- Palette / manual override application: trace from `led_color_engine.py` / `led_look_director.py`.

**Known-stale, evidence-only:** project memories and any doc without a current status header. AWR-131 (`docs/plans/active/smart_drop_marker_collapse_spec.md`) is the change that deleted the capped re-arm — useful history, but confirm against code.

## The observational session log (Brandon's own notes — treat as leads, not truth)

These are Brandon's best-effort real-time notes. Some descriptions may be imprecise or mislabel a look. Use them to know *where in the timeline to look in the JSONL*, then let the code + events tell you what actually happened. Where a note and the log disagree, say so.

The distinct clusters I see in his notes (dedupe against code — several may share one cause):

1. **RT effect flicker / glitch at runtime — clean in the LED Pad (headline).** During live bridge runtime with Rekordbox running, the RT LED effects flicker and glitch; the ambient/idle/breakdown effects are worst, and the **breathing** effect is the sharpest case — it visibly strobes and flickers live. Playing the *same* effects in the LED Pad standalone (no Rekordbox, no bridge) produces a calm, stable, smooth result. The clean-Pad reference is the key clue: the effect definition is fine, so something in the **live runtime path corrupts the frame stream** — candidate mechanisms to test, not assume: the beat/phase source the effect is driven from differs live (Rekordbox-derived, jittery) vs the LED Pad's synthetic clock (smooth) so the breathing phase keeps resetting; two systems writing Govee frames out of phase (`led_dispatch_coordinator.py` vs `govee_realtime_runner.py` / `govee_frame_renderer.py` / `govee_runtime_sender.py` / `govee_realtime_transport.py`); per-tick re-selection / re-dispatch restarting the effect (edge-trigger churn); or CPU starvation on the 200 Hz push loop under Rekordbox load (a known dominant cause on 2026-07-06) jittering send timing. Compare the live frame/dispatch path against how the LED Pad drives the identical renderer — the delta is the bug.
2. **Drop section won't cycle (dominant, every run).** LED freezes on the first drop look; the 2nd-chorus marker inside the drop section does not fire a new look; post-drop white-shatter sometimes claimed in logs but not seen. This is the one the pending spec targets.
3. **Up-phrase 32-beat cycling is intermittent.** Sometimes cycles correctly entering the next up marker, sometimes stuck on the DIY groove look for the whole phrase. First playback was worse than the second — look at what differs between a cold track load and a re-cue.
4. **Section-entry misses.** Breakdown or buildup sometimes not entered — LED stays on the previous look. Correlate to phrase-start crossings in the log.
5. **Breakdown look "strobes" — likely a facet of #1, confirm.** "RT breakdown full breathing" strobes / pulsates too hard live. Given it is calm in the LED Pad, first test whether this IS the #1 flicker instability rather than a wrong look or too-fast modulation; only if the Pad also pulses hard is it a look/speed choice. Do not assume.
6. **Blackout inconsistency.** Pre-drop blackout fires on some drops, not others; a full 4-bar blackout appeared once at a 2nd-chorus marker that had never blacked out before.
7. **Lasers randomly kick in during the drop section.**
8. **Laser-solo ↔ LED coupling.** On a learned laser-solo, LEDs were sometimes late to react (played a drop look for a second or two), sometimes did not blackout at all, sometimes kept playing through the solo.
9. **Manual palette / override not fully applying, or delayed.** Manual "red" override produced a blue drop then a cyan/white post-drop, not red; "green" override left it stuck cyan; a queued crimson palette applied late.
10. **Deck-switch LED latency.** Switching deck 2 → deck 1, LEDs did not change on time.
11. **Idle fallback fails on PAUSE (works on END).** Paused + jumped back — LEDs did not fall to idle ambient despite the track being paused.

## Boundaries

- **Read-only on the bridge.** Read code, logs, docs. You may run the test suite read-only (`python3 -m unittest discover tests`; some suites need optional deps and there is a known ~3-red baseline — do not "fix" tests). Do **not** edit bridge code, do **not** change config, do **not** restart or touch the running bridge, do **not** touch hardware.
- **No implementation.** Fable reasons, plans, audits, reviews; Codex implements bridge code. Your fixes are direction for a Codex spec, not code.
- **Delegate the grind, keep the safety reasoning.** Hand log-parsing, corpus sweeps, and multi-file symbol tracing to cheaper-tier Claude subagents — the read-only `bridge-triage` agent is built for exactly this (it returns conclusions + exact `file:line`, never transcripts), or hand a task to the Claude session at `tmux a -t claude`. You are the only Fable-tier agent: never spawn another Fable-tier subagent, and announce nested spawns rather than running them silently. Keep the live-safety and root-cause judgment on yourself; verify a subagent's load-bearing claims before relying on them.
- **Adversarial verification is expected.** For each root cause you're about to call "confirmed," have a fresh-context subagent try to refute it against the code and the log. A cause survives only if the refutation fails. Distinguish a real bug from a log-line that merely *claims* a look fired (Brandon flagged at least one "logs said X, eye saw Y").

## Claim discipline and success criteria

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, each tied to evidence: a `ts` in the JSONL, a `file:line`, or an authority-doc section. "The log says so" is not confirmation that the *pixels were right* — separate "the code took branch X" from "the look on the wall was correct."

You are done when: every one of the 11 clusters above maps to a labeled root cause, a shared cause, an observation artifact, or a named unknown-needing-capture; both headline clusters (RT flicker, drop-cycling) have a confirmed mechanism in code; the pending spec has a `CORRECT & COMPLETE` / `CORRECT BUT INCOMPLETE` / `NEEDS CHANGE` verdict; and no cluster is left as a bare restated symptom. If a cause genuinely needs a live capture only Brandon can run, stop and name the exact capture rather than guessing.

**Verdict line to end on:** `ROOT-CAUSED: N of 11 clusters` + the spec verdict.
