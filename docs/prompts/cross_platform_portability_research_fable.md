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

This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

I'm planning how to make Brandon's existing Rekordbox-reading lighting bridge run on *any host laptop* he plugs a USB stick into, instead of only his one Mac. He wants to walk up to a friend's Windows laptop or his next MacBook, plug in, and have the same physical rig (Pioneer DDJ-800 controller, SoundSwitch, lasers, LEDs, Govee) driven correctly. Today the bridge reads Rekordbox's live playback state from that app's own process memory, and it only works on his current machine. **You are researching and planning this port — Codex will implement it later. Do not write, patch, run, or reverse-engineer anything; produce the report and the plan.**

## Deliverable

One document with three parts:
1. **Feasibility findings**, with a per-platform verdict (`FEASIBLE` / `FEASIBLE WITH CAVEATS` / `NOT FEASIBLE`) for macOS-arm64 and Windows-x64, each with its evidence and its single biggest risk.
2. **A phased, Codex-executable plan**: ordered phases, each with a concrete deliverable, the files/areas it touches, how to verify it, and its live-performance-safety note. Phase 1 must be the cheapest thing that proves or kills the riskiest assumption.
3. **Unknowns and an overall readiness verdict** (`READY` / `READY WITH GAPS` / `NOT READY` for Codex), blocking gaps first, naming which unknowns can only be settled with a Windows machine, a second Mac, or the actual TimecodeLink binaries.

Lead with the outcome. When you have enough to recommend, recommend — don't survey options you won't pursue.

## Evidence packet (confirmed — do not re-derive these)

- **How the bridge reads state.** It follows per-version pointer chains into Rekordbox's process memory to read master-deck index, per-deck BPM, playback position, track info, and ANLZ file path, using the macOS mach APIs `task_for_pid` + `mach_vm_read_overwrite`. It is a pure external reader: no code injection, no driver, no root; the bridge and Rekordbox just run as the same user. Source: `rb_memory.py`, `rb_state_reader.py`, `rb_offsets.py`.
- **What grants read access on macOS.** The reads only work because Rekordbox is code-signed with the `com.apple.security.get-task-allow` entitlement. Confirmed on Brandon's machine: `/Applications/rekordbox 7/rekordbox.app` is ad-hoc re-signed with `get-task-allow` plus `cs.disable-library-validation` and `cs.allow-unsigned-executable-memory`; the original Pioneer signature is gone. This re-sign was performed by TimecodeLink's patcher, **not** by the bridge. `rb_memory.py` documents the dependency ("rekordbox must have com.apple.security.get-task-allow = true … no root needed").
- **Current offset coverage.** `rb_offsets.py` embeds an arm64 macOS table for exactly five Rekordbox builds: 7.2.8, 7.2.10, 7.2.11, 7.2.13, 7.2.14. Each entry is a chain of pointer hops plus a final offset. An unsupported version returns no offsets.
- **Where the offsets came from.** They were derived by reverse-engineering **TimecodeLink** — a maintained commercial app that locates these same Rekordbox fields in memory in order to emit MIDI timecode. TimecodeLink is Brandon's reference oracle for the field locations.
- **TimecodeLink facts** (timecodelink.com, verified July 2026): it reads Rekordbox memory externally *after* re-signing Rekordbox with `get-task-allow` (admin password required; must re-patch on every Rekordbox update). It supports Rekordbox 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14 on **both** macOS (Apple Silicon and Intel) and Windows 10/11 (64-bit). It is actively maintained (~weekly; v0.0.31, June 2026). It is paid, with a 30-day trial.
- **Crash reports (unverified).** Brandon reports three posts on r/LiveShowSystems describing Rekordbox crashing in connection with TimecodeLink. The thread could not be fetched (login wall) — treat as unverified. Leading hypothesis: the re-sign weakening Rekordbox's own memory protections (`disable-library-validation` / `allow-unsigned-executable-memory`) is the destabilizer, **not** the external reads — Brandon's bridge reads Rekordbox memory live during sets without crashing it. Confirm or reject if you can find the source.

## Locked constraints (Brandon's decisions — do not re-litigate)

1. **The data source stays Rekordbox memory offsets.** Do not propose swapping to a network or clock protocol: the DDJ-800 controller does not emit PRO DJ LINK, and Ableton Link carries no track / deck / position.
2. **TimecodeLink stays an offline reverse-engineering reference on Brandon's dev Mac only.** It is never installed on a performance host and never a runtime data feed.
3. **Targets are macOS Apple Silicon (arm64) and Windows 11 x64.** Intel Mac is out of scope.
4. **On macOS the USB deployment carries its own independent re-sign step** that reproduces the `get-task-allow` ad-hoc signature itself (admin-gated, repeated whenever Rekordbox updates). It must not depend on TimecodeLink being present. Windows requires no binary re-sign.
5. **Best-effort runtime accuracy is acceptable** — occasional wrong lighting on an unfamiliar machine is fine. One hard floor: bad values must never produce a dangerous strobe; clamp anything derived from BPM/beat so a garbage read can't drive an unsafe flash rate.
6. **Raspberry-Pi / standalone (no-Rekordbox) operation is out of scope.** Note it once so the design doesn't foreclose it; do not design for it.

## Research questions (weigh the trade-offs, then recommend one path each)

- **Version resilience.** Brandon prefers moving off the hardcoded per-build offset table toward runtime discovery that survives Rekordbox builds nobody has pre-analyzed — e.g. locating the structures by stable byte-pattern signatures rather than fixed addresses. Assess reliability and effort of that versus keeping a hardcoded table refreshed from the TimecodeLink reference, and recommend a path plus a concrete version-support policy.
- **Windows port.** What it takes to read the same fields on Windows x64: the `OpenProcess` / `ReadProcessMemory` permission model, deriving the x64 field locations (reverse-engineering the Windows TimecodeLink build vs. any community-published offset sources), and whether antivirus / Defender false-positives against a program that reads another process's memory are a real deployment blocker on a foreign machine — and how to reduce those false positives legitimately (signing, allow-listing, packaging), never evade detection.
- **macOS independent re-sign step.** How to reproduce the `get-task-allow` ad-hoc signature without TimecodeLink, its admin UX, its per-update repetition, and its SIP / Gatekeeper implications — and whether this step (not the reads) is what explains the crash reports.
- **Portable runtime.** Packaging the Python bridge to launch from a USB stick on a foreign host with no developer tools installed, on both operating systems.

## Working rules

- **Source-of-truth order:** executable code > tests > this packet > TimecodeLink docs / web. Where code and this packet disagree, code wins — flag it.
- **Allowed tools — read-only.** You may read the named repo files, search the repo read-only, and do web research (TimecodeLink, Rekordbox memory-layout community work, macOS code-signing, Windows process-memory APIs). You may fan out independent research threads to parallel subagents and use a fresh-context pass to check your plan against these constraints before the verdict. Do **not** edit code, run or restart the bridge, re-sign or patch any binary, run reverse-engineering tools, touch hardware, or use git.
- **Claim discipline.** Label every load-bearing claim `confirmed` / `assumed` / `unknown` / `rejected`, tied to the file, command, or URL behind it. Mark clearly what can only be settled with a real binary or a live foreign machine.

---

### Brandon-facing note (not part of the Fable prompt)

If Fable blocks on safeguards despite the benign-scope line, retry with narrower evidence and more neutral wording — never jailbreak phrasing. Save Fable's output to `docs/plans/active/` once you're happy with it; that's where the Codex handoff lives.
