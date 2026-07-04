---
doc_status: current
truth_level: prompt-only
last_verified_date: 2026-07-04
validation_scope: Fable 5 research/planning prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Fable 5 prompt — cross-platform / cross-version portability research + plan

Paste the block below to Claude Fable 5. Deliverable is a research report + Codex-executable plan, not implementation.

---

**Model:** Claude Fable 5 · **Effort:** xhigh

This is benign local software work for Brandon's own DJ lighting hobby project. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Everything here happens on hardware and software Brandon owns and is licensed for — his own laptops (and friends' laptops with their permission), his own paid Rekordbox and TimecodeLink licenses, for personal event lighting. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

I'm planning how to make Brandon's existing lighting bridge run on *any host laptop* he plugs a USB stick into, instead of only his one Mac. He wants to walk up to a friend's Windows laptop or his next MacBook, plug in, and have the same physical rig (Pioneer DDJ-800 controller, SoundSwitch, lasers, LEDs, Govee) driven correctly. The bridge works today by reading Rekordbox's live playback state — master deck, per-deck BPM, playback position, current track — directly from the running Rekordbox app, exactly the way the commercial TimecodeLink tool does. It currently only runs on Brandon's current machine. **You are researching and planning this port — Codex implements it later. Do not write, patch, run, or analyze any binary; produce the report and the plan.**

## Deliverable

One document with three parts:
1. **Feasibility findings**, with a per-platform verdict (`FEASIBLE` / `FEASIBLE WITH CAVEATS` / `NOT FEASIBLE`) for macOS-arm64 and Windows-x64, each with its evidence and its single biggest risk.
2. **A phased, Codex-executable plan**: ordered phases, each with a concrete deliverable, the files/areas it touches, how to verify it, and its live-performance-safety note. Phase 1 must be the cheapest thing that proves or kills the riskiest assumption.
3. **Unknowns and an overall readiness verdict** (`READY` / `READY WITH GAPS` / `NOT READY` for Codex), blocking gaps first, naming which unknowns can only be settled with a Windows machine, a second Mac, or the actual TimecodeLink app.

Lead with the outcome. When you have enough to recommend, recommend — don't survey options you won't pursue.

## Evidence packet (confirmed — do not re-derive these)

- **How the bridge reads state.** It follows per-version pointer paths into the running Rekordbox app to read master-deck index, per-deck BPM, playback position, track info, and ANLZ file path, using the standard macOS APIs `task_for_pid` + `mach_vm_read_overwrite`. It is a read-only integration: no code injection, no driver, no elevated privileges; the bridge and Rekordbox simply run as the same user. Source: `rb_memory.py`, `rb_state_reader.py`, `rb_offsets.py`.
- **What grants read access on macOS.** The reads work because the locally installed Rekordbox carries Apple's standard debugging entitlement `com.apple.security.get-task-allow` (the same entitlement Xcode applies to let a developer inspect an app). Confirmed on Brandon's machine: `/Applications/rekordbox 7/rekordbox.app` carries `get-task-allow` plus `cs.disable-library-validation` and `cs.allow-unsigned-executable-memory`, applied via an ad-hoc signature. That entitlement was applied by the TimecodeLink setup tool, **not** by the bridge. `rb_memory.py` documents the dependency ("rekordbox must have com.apple.security.get-task-allow = true … no root needed").
- **Current version coverage.** `rb_offsets.py` embeds an arm64 macOS field-offset table for exactly five Rekordbox builds: 7.2.8, 7.2.10, 7.2.11, 7.2.13, 7.2.14. Each entry is a pointer path plus a final offset. An unsupported version returns no offsets.
- **Where the offsets came from, and the reference oracle.** They were originally derived by studying **TimecodeLink**, a maintained, licensed tool that locates these same Rekordbox playback fields in order to emit MIDI timecode. TimecodeLink remains Brandon's reference for *which field holds which playback value* — a comparison oracle to check any new mapping against. Brandon owns a TimecodeLink license.
- **TimecodeLink facts** (timecodelink.com, verified July 2026): it reads Rekordbox playback state after applying the `get-task-allow` entitlement to Rekordbox (admin password required; re-applied on every Rekordbox update). It supports Rekordbox 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14 on **both** macOS (Apple Silicon and Intel) and Windows 10/11 (64-bit). It is actively maintained (~weekly; v0.0.31, June 2026). Paid, with a 30-day trial.
- **Stability reports (unverified).** Brandon reports three posts on r/LiveShowSystems describing Rekordbox becoming unstable in connection with TimecodeLink. The thread could not be fetched (login wall) — treat as unverified. Leading hypothesis: applying the entitlement relaxes Rekordbox's own memory-integrity flags (`disable-library-validation` / `allow-unsigned-executable-memory`), and that relaxation is the destabilizer — **not** the read-only integration itself, since Brandon's bridge reads Rekordbox playback state live during sets without destabilizing it. Confirm or reject if you can find the source.

## Locked constraints (Brandon's decisions — do not re-litigate)

1. **The data source stays Rekordbox's in-app playback state.** Do not propose swapping to a network or clock protocol: the DDJ-800 controller does not emit PRO DJ LINK, and Ableton Link carries no track / deck / position.
2. **TimecodeLink stays a reference oracle on Brandon's dev Mac only.** It is never installed on a performance host and never a runtime data source for the bridge.
3. **Targets are macOS Apple Silicon (arm64) and Windows 11 x64.** Intel Mac is out of scope.
4. **On macOS the USB deployment applies the `get-task-allow` debugging entitlement to the local Rekordbox itself** (admin-gated, re-applied whenever Rekordbox updates), without depending on TimecodeLink being installed. Windows does not use this entitlement model at all.
5. **Best-effort runtime accuracy is acceptable** — occasional wrong lighting on an unfamiliar machine is fine. One hard floor: bad values must never produce a dangerous strobe; clamp anything derived from BPM/beat so a garbage read can't drive an unsafe flash rate.
6. **Raspberry-Pi / standalone (no-Rekordbox) operation is out of scope.** Note it once so the design doesn't foreclose it; do not design for it.

## Research questions (weigh the trade-offs, then recommend one path each)

- **Version resilience.** Brandon prefers moving off the hardcoded per-build offset table toward runtime field-location that survives Rekordbox builds nobody has pre-analyzed — for example, locating the structures by stable byte-pattern signatures rather than fixed addresses. Assess reliability and effort of that versus keeping a hardcoded table refreshed against the TimecodeLink reference, and recommend a path plus a concrete version-support policy.
- **Windows port.** What it takes to read the same fields on Windows x64: the standard Windows process-inspection permission model (the platform equivalent of the macOS mach read APIs), how to identify the x64 field locations (comparison against the Windows TimecodeLink reference, plus any publicly documented Rekordbox memory-layout references if they exist), and what the clean packaging story is.
- **macOS entitlement step.** How the USB deployment applies the `get-task-allow` debugging entitlement to the local Rekordbox on its own, its admin/first-run experience, its per-update repetition, and its SIP / Gatekeeper implications — and whether this step (not the read integration) is what explains the stability reports.
- **Portable runtime + smooth first run.** Packaging the Python bridge to launch from a USB stick on a foreign host with no developer tools installed, on both operating systems, including standard code-signing / notarization so the operator gets a clean first launch. (Goal is a smooth trusted first-run on Brandon's own machines; not evasion of any protection.)

## Working rules

- **Source-of-truth order:** executable code > tests > this packet > TimecodeLink docs / web. Where code and this packet disagree, code wins — flag it.
- **Allowed tools — read-only.** You may read the named repo files, search the repo read-only, and do web research (TimecodeLink docs, Rekordbox memory-layout community work, macOS code-signing / entitlements, Windows process-inspection APIs). You may fan out independent research threads to parallel subagents and use a fresh-context pass to check your plan against these constraints before the verdict. Do **not** edit code, run or restart the bridge, apply entitlements to or modify any binary, run binary-analysis tools, touch hardware, or use git.
- **Claim discipline.** Label every load-bearing claim `confirmed` / `assumed` / `unknown` / `rejected`, tied to the file, command, or URL behind it. Mark clearly what can only be settled with a real Windows machine or a live foreign Mac.

---

### Brandon-facing note (not part of the Fable prompt)

If Fable still blocks on safeguards, the topic itself (process memory + code-signing entitlements) is borderline for Fable regardless of wording — don't add jailbreak phrasing. Two clean fallbacks: (1) narrow the evidence further and keep terms neutral, or (2) move this to Opus 4.8, which handles this research/planning shape without the same false-positive risk (author it with `opus-prompt-writer`). Save the accepted output to `docs/plans/active/` — that's where the Codex handoff lives.
