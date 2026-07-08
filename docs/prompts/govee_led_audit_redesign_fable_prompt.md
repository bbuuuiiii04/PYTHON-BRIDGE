---
doc_status: current
truth_level: prompt-artifact
last_verified_commit: f754853
last_verified_date: 2026-07-08
validation_scope: Fable 5 prompt text only; commissions a read-only audit + diagnosis + redesign proposal for the Govee LED subsystem; no bridge behavior change, no implementation, no hardware action
---

# Fable 5 Prompt — Govee LED Subsystem: Full Audit, Live-Bug Diagnosis, and Redesign Proposal

**Target model:** Claude Fable 5 · **Effort:** `xhigh`

Paste everything between the rules below into Fable. It is self-contained.

---

This is benign local software work for Brandon's DJ lighting bridge. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning-extraction task. You are reviewing normal software correctness, real-time media timing, maintainability, runtime safety, and operator-visible lighting behavior inside one named subsystem. "Realtime frames" here are UDP color packets sent to a consumer Govee LED strip on the local network; "reverse-engineering" here means understanding an already-integrated home-lighting protocol, nothing adversarial.

## Why this matters and who it's for

Brandon runs `rb_ss_bridge_v2`, a Python bridge that reads his Rekordbox/DJ runtime state and drives room lighting. One output is a Govee LED strip. The Govee subsystem was built incrementally by an earlier Opus model, and Brandon suspects the architecture can be meaningfully better. He is asking **you** — as the strongest reasoner available — to take a deep, honest look and tell him both what is wrong today and what a genuinely better design would be. The output is for Brandon (a skilled operator, not a software engineer) to read cold and then hand the concrete change work to a separate implementer (Codex). **You audit, diagnose, and design. You do not implement, and you do not touch his live rig.**

## What Brandon told me, in his words (operator observations — verify against code, do not treat as ground truth)

- The bridge drives the Govee strip using **two paths at once as a system: Govee "realtime" and Govee "cloud."**
- **Cloud** gives *far smoother, better-looking* animations but *less control*: only certain API commands, plus switching to "looks"/scenes he built in the Govee app via DIY. He cannot freely paint arbitrary frames through it.
- **Realtime (RT)** gives *far more customization* (arbitrary per-segment color frames) but *can lag, go unresponsive, drop framerate, look less smooth,* and is *limited to about 60 controllable sections* on his hardware.
- **The bug he wants diagnosed:** during Rekordbox track playback, the Govee strip sometimes **gets stuck on a cloud look, fails to black out when it should, and stutters/flickers.**
- **The critical clue:** in his separate **LED Pad** tool, playing the *same* realtime looks *independently of the bridge* is **much smoother** than when the bridge drives them. Same strip, same renderer family, smoother when not driven by the bridge.

Reconcile these operator statements with the code. Where the code disagrees with his mental model (for example: the realtime transport's configured segment count vs. the "60 sections" ceiling; whether cloud and realtime truly run simultaneously vs. being arbitrated by an owner/handoff so only one drives the strip at a time; whether cloud "mirror" means cloud→realtime or cloud→multiple-cloud-targets), say so plainly and explain the real mechanism. His framing being imprecise is expected and useful — it tells you where the design is confusing.

## What the redesign must achieve (the north star — no assumed compromises)

Brandon's instruction is explicit: **do not treat these as competing tradeoffs to balance. Find the architecture that delivers all of them at once.** The standalone LED Pad already plays the same realtime looks smoothly on the same hardware and network — so smoothness over realtime is *proven possible*, not a limit to accept. Treat today's lag, stutter, and flicker as defects to engineer out, not as a hardware ceiling.

The recommended design must hit all four of these together:

1. **As smooth as the LED Pad.** The Pad is the proof-of-possible and the bar. Bridge-driven realtime should look identical to the Pad driving the same look — no stutter or flicker the eye can catch during a normal mix.
2. **Full custom control without losing cloud's smooth looks.** Keep both paths for what each does best — cloud for its smooth app-made scenes, realtime for arbitrary custom frames — and rebuild the switching between them so the strip is always cleanly owned by exactly one path and never latches on the wrong one.
3. **Blackout is absolutely reliable.** Going dark/off when it should must never fail. On any failure — network stall, unresponsive device, cloud rate-limit — the strip goes dark, never frozen on a stale cloud scene.
4. **Tight to the beat and smooth at the same time.** Lighting tracks the music closely, crisp on drops and hits where timing matters, and may relax slightly on ambient/breakdown sections where it doesn't — while staying buttery throughout. Do not buy smoothness with latency the operator can feel on a drop.

**On tradeoffs:** do not silently accept one. If — and only if — you can *prove with evidence* that two of these genuinely cannot coexist on this hardware (a real, demonstrated physical or protocol limit, not an assumption or a convenience), surface it to Brandon as an explicit decision with the evidence attached, and default to this priority order: **reliable blackout is never sacrificed; then beauty; then timing.** But your starting assumption — backed by the Pad already doing it — is that no such compromise is necessary and the current problems are fixable design defects. A redesign that quietly picks one of these to give up, without proving it had to, fails this task.

## Deliverable

A single written report, structured exactly as the five parts below. Lead with a plain-language TL;DR (a few sentences: what the subsystem actually does, the most likely cause of the stuck/stutter bug, and your headline redesign recommendation) before Part A. Write the whole thing so Brandon can understand *how* things work and *why* they behave as they do — plain English, real mechanism, no engineering jargon (avoid "blast radius", "load-bearing", "seams"; if you must use a term, define it once in ordinary words).

**Part A — How it actually works today (the map).** How the bridge connects to the Govee strip and how it produces and sends frames and cloud scenes. Cover: the two backends and how ownership/handoff between cloud and realtime is decided; where realtime frames are rendered vs. sent; how beat/BPM and phrase state drive the realtime motion; how blackout is supposed to happen on each path; and — importantly — the relationship between the bridge's 200 Hz `StateManager` push loop and the realtime send loop (which thread renders, which thread sends, what is shared, where timing can be injected or starved). Draw the contrast with how the standalone LED Pad drives the *same* renderer, since that is the smoothness reference.

**Part B — Bug diagnosis.** Root-cause hypotheses for the two reported failures, ranked by likelihood, each tied to specific `file:line` evidence:
1. *Stuck on a cloud look / fails to black out during playback.*
2. *Stutter / flicker during Rekordbox playback, and why the bridge-driven path is worse than the standalone LED-Pad-driven path.*
Treat the second one as your sharpest lever: the same renderer being smooth under the Pad and rough under the bridge is strong evidence the problem is in *how the bridge feeds and paces the realtime path*, not in the device or the frame math — confirm or refute that with code. For each hypothesis give a **falsifiable confirmation step Brandon can run himself** (a specific log line to grep in `~/Library/Logs/rb_ss_bridge/current.jsonl`, a config toggle, a one-off capture, an A/B against the Pad). Do not run live-repro steps yourself — propose them for him.

**Part C — Redesign proposal (the ambitious part).** Propose the better architecture for driving this strip. Be genuinely willing to say the current cloud+realtime split should be restructured. Give **two or three concrete design options with honest tradeoffs, then one clear recommendation.** Address at least: whether the realtime path should be decoupled from the 200 Hz push loop / `StateManager` the way the Pad already is (its own render/send loop with a clean state feed); the cloud-vs-realtime ownership model and when each should own the strip (cloud for the smooth scenes it does best, realtime for custom control); how to guarantee blackout actually reaches the strip on both paths; frame pacing / target framerate / jitter handling; the ~60-section hardware ceiling and configured segment count; and the main failure modes (network stalls, device unresponsiveness, cloud rate limits) and how the design degrades safely instead of latching a stale scene. State what stays the same and what is torn out.

**Part D — Migration path.** A phased, low-risk sequence to get from today's code to your recommended design, each phase independently shippable and testable, ordered so the highest-value / lowest-risk fixes (likely the stuck-cloud/blackout bug) land first and the deeper architectural change comes later. Describe each phase at the level of *what changes and why*, so Brandon can later have Codex author an implementation spec from it. **Do not write the Codex spec and do not write implementation code** — that is Codex's job, not yours.

**Part E — Verdict + unknowns.** Two verdicts: (1) current subsystem health — `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL`; (2) redesign readiness — `READY` / `READY WITH GAPS` / `NOT READY`. Then an explicit list of what you could not determine from code and logs alone and exactly what live evidence from Brandon would settle each open question.

## Evidence packet (start here; code wins over docs, docs win over your priors)

Source-of-truth order: executable `*.py` → `tests/` → config examples → the subsystem card → everything else. If a doc and the code disagree, the code is right and the doc is drifted; note the drift.

Realtime path:
- `govee_realtime_runner.py` (~453 lines) — the realtime render+send thread: beat anchor, idle "freewheel", idle-grace teardown, frame cadence, foreign-thread `force_deactivate`.
- `govee_realtime_transport.py` (~200) — the UDP frame sender; **note it defaults to `segments=20`, not 60** — reconcile with the hardware "60 sections" ceiling and the configured value.
- `govee_frame_renderer.py` (~1952) — the actual per-segment frame math, shared by the bridge *and* the LED Pad. This is large; consider delegating a read of it to a cheaper-tier subagent (see below).
- `beat_sync_engine.py` (~213) — beat-synced motion timing for realtime looks.

Cloud path:
- `govee_scene_adapter.py` (~531) — cloud DIY scene commands.
- `govee_runtime_sender.py` (~510) — cloud send + circuit-breaker + cloud→cloud "mirror" targets and their health logging.

Ownership / dispatch / arbitration:
- `govee_owner_state.py` (~41) — who currently owns the strip (cloud vs realtime).
- `led_dispatch_coordinator.py` (~255) — routes decisions to the cloud-DIY vs realtime backend.
- `led_dispatch_policy.py` (~1955, `LEDDispatchPolicyMixin`, mixed into `StateManager`) — when and what to dispatch, blackout owners (including the `drop_spotlight` dark-hold), hold-gating, smart-drop blackout.
- `led_look_director.py` (~421) and `led_color_engine.py` (~1453) — look selection and color resolution feeding both paths.
- `state_manager.py` — the runtime owner and the **200 Hz push loop** (`_TICK_INTERVAL = 1.0/200`); LED automation call sites live here. Runtime invariant: this push loop must **not** gain blocking network / socket / MIDI / filesystem / subprocess I/O. Check whether realtime sending honors that or leaks I/O into the hot path.

The smoothness reference (why the Pad is smoother):
- `tools/led_pad_playback.py` and `tools/led_pad_web.py` — the standalone LED Pad that plays the *same* realtime renderers on its *own* clock/loop, independent of the bridge. Compare how it feeds and paces frames vs. how `govee_realtime_runner.py` does under `StateManager`.

Config and logs:
- `config/led_look_director.example.json` (tracked) and the local, gitignored `config/led_look_director.json` (the live values — the realtime enable flag, segment count, target device IPs, cloud API config live here; read it if present).
- `~/Library/Logs/rb_ss_bridge/current.jsonl` — event log; `ts` is epoch and persists across restarts. Relevant markers already exist: `[RGB] hold-engaged` / `hold-released`, `[RGB] deactivate reason=idle_grace blackout_sent=...`, `[RGB] idle-freewheel-start`, `[RGB] mirror-send-degraded` / `mirror-send-recovered`, `[RGB] smart-drop-blackout-accepted transport=...`. Use these to check whether the documented fixes actually fire in a real session.

Context and known-stale caution:
- `docs/subsystems/led_govee.md` — the subsystem card. Useful map, but it is a **doc**: it records many recent fixes (idle-grace teardown now sends a blackout frame before deactivating; the `AWR-141` realtime wrap-flicker guard; smart-drop blackout transport tagging; mirror-send health) all marked **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**. Do **not** assume these resolved the live symptom — several target exactly the behaviors Brandon still reports, which means either they don't fully cover it, they regressed, or the real cause is elsewhere. Verify against code and logs; the card is a lead, not proof.

Do not re-derive the file map above from scratch, and do not re-litigate Brandon's operator taste calls (cloud is for smooth scenes, realtime is for custom control — that split is his, keep it as a design input).

## How to work

- **Diagnose and design; do not fix.** Brandon is describing problems and asking for an assessment and a plan. Report findings and stop at the design; do not apply any change. Before you would recommend a state-changing action, confirm the evidence supports that *specific* action — a symptom that pattern-matches a known fix may have a different cause.
- **Read-only, and never touch the live rig.** You may read any repo file, read the log file, read the config, and run the test suite read-only (`python3 -m unittest discover tests`) and offline analysis of the renderer. You may **not** modify any file, commit, restart or launch the bridge, or send any frame/command to the Govee hardware or cloud. SoundSwitch won't autorotate without the bridge running, so leave the running process alone entirely.
- **Delegate the heavy reads.** `govee_frame_renderer.py`, `led_dispatch_policy.py`, and `led_color_engine.py` are large. Send independent read-only subtasks to **cheaper-tier** subagents and keep working; you are the only Fable-tier agent and must not spawn another Fable-tier agent. Use a fresh-context subagent to re-verify your load-bearing claims against the actual lines before you rely on them. Announce any nested spawn rather than running it silently.
- **Label every important claim** `confirmed` / `assumed` / `unknown` / `rejected`, each tied to `file:line` or a log line or a test result. "The renderer is fine" is not a finding; "the renderer output is identical under Pad and bridge, so the difference is in send pacing at `govee_realtime_runner.py:NNN`" is.
- **Do not reproduce or narrate your private reasoning.** Give evidence-tied findings, the claim labels, and the verdicts — not a transcript of your thinking.
- **Write the final report for a cold reader.** Outcome first, plain sentences, each file/flag/log-line in its own clear clause. Being readable matters more than being short.

## Success criteria (this is what "good" means here)

- The map in Part A is specific enough that Brandon finally understands *why* the same look is smooth under the Pad and rough under the bridge.
- Each bug hypothesis in Part B names concrete `file:line` evidence and a confirmation step Brandon can run himself without you touching hardware.
- Part C commits to a recommendation with honest tradeoffs, not a menu — and it directly addresses decoupling realtime from the push loop, the cloud/realtime ownership model, and guaranteed blackout.
- Part D is phased so the stuck-cloud/blackout fix can ship before any big rewrite.
- Every load-bearing claim is verified against current code, not the subsystem card, and drift between them is flagged.
- Nothing in the running bridge, the hardware, or the repo files is modified.

Rejection conditions (do not do these): implementing or writing patch code; authoring the Codex spec; asserting the card's "fixed" claims resolve the live bug without code/log verification; proposing a redesign that quietly drops the blackout guarantee or the "push loop stays non-blocking" invariant; treating "60 sections" or "cloud + RT simultaneously" as settled fact without checking the code.
