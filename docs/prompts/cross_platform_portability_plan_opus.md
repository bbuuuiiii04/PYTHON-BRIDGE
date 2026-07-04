---
doc_status: current
truth_level: prompt-only
last_verified_date: 2026-07-04
validation_scope: Opus 4.8 research/planning prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Opus 4.8 prompt — cross-platform / cross-version portability plan (planning half)

Paste the block below to Claude Opus 4.8. Deliverable is a feasibility report + Codex-executable plan, not implementation.

This is the **planning half** of the portability work. The **reader mechanics** — how each host authorizes the reader, and how per-version field data is produced for each platform — are deliberately out of scope here and become a separate Codex/RE implementation spec (see the handoff note at the end).

---

**Model:** Claude Opus 4.8 · **Effort:** xhigh · Set a large max-output budget (~64k tokens).

I'm planning how to make Brandon's existing DJ lighting bridge run on *any host laptop* he plugs a USB stick into, instead of only his one Mac. He wants to walk up to a friend's Windows laptop or his next MacBook, plug in, and have the same physical rig (Pioneer DDJ-800 controller, SoundSwitch, lasers, LEDs, Govee) driven correctly. Today the bridge runs only on his current Mac. The output is a feasibility report and a phased plan that Codex will implement later. **Do not implement anything — produce the report and the plan only.**

## The reader is a given, not your job

The bridge already obtains Rekordbox's live playback state — master-deck index, per-deck BPM, playback position, current track — on Brandon's Mac today, through a platform-specific **reader component**. Treat that reader as an **existing capability** that a *separate* implementation spec will provide for each platform and each Rekordbox version. This plan does **not** design the reader's internals. It plans everything the rest of the bridge needs *around* the reader so the whole system runs portably, and it names the reader-side items it depends on as explicit blocking dependencies (see the handoff section).

## Deliverable

One document with these parts. **The plan must cover both macOS-arm64 and Windows-x64** — every phase states which platform(s) it applies to; do not plan the Mac in detail and leave Windows implied.

1. **Portability architecture — the seam.** Read the code and identify where OS-specific reading is (or should be) isolated behind an interface, and where the rest of the bridge consumes deck state. Specify the seam: the interface the reader must satisfy, what the platform-agnostic bridge depends on, and what has to change so the same bridge runs on Windows and macOS behind that seam.
2. **Version-resilience policy.** The bridge today carries a fixed table for five Rekordbox builds and produces nothing on an unsupported version. Weigh keeping a per-version data table (refreshed as new builds appear) against a version-adaptive lookup that tolerates builds nobody has pre-analyzed. Recommend one, state a concrete version-support policy, and show how the seam makes either approach swappable without touching the rest of the bridge.
3. **Deployment & packaging.** How to launch the Python bridge from a USB stick on a foreign host with no developer tools installed, on both operating systems, including standard code-signing / notarization so the operator gets a clean, trusted first launch.
4. **Live-performance safety.** One hard floor regardless of data quality: a bad reading must never drive a dangerous strobe. Specify where to clamp anything derived from BPM/beat so a garbage value can't produce an unsafe flash rate.
5. **Phased, Codex-executable plan.** Ordered phases, each with a concrete deliverable, the files/areas it touches, how to verify it, and its live-safety note. Phase 1 must be the cheapest thing that proves or kills the riskiest assumption.
6. **Unknowns + readiness verdict** (`READY` / `READY WITH GAPS` / `NOT READY` for Codex), blocking gaps first, naming which unknowns can only be settled with a real Windows machine or a live foreign Mac.

Lead with the outcome. When you have enough to recommend, recommend — don't survey options you won't pursue.

## Evidence packet (confirmed — do not re-derive)

- **Where deck state is read and consumed.** The reader and its consumers live in `rb_memory.py`, `rb_state_reader.py`, and the deck-state model; the per-version field table is in `rb_offsets.py` (five builds: 7.2.8, 7.2.10, 7.2.11, 7.2.13, 7.2.14; an unsupported version yields no data). `state_manager.py` owns runtime state and the push loop. Use these to locate the seam and the platform-agnostic boundary; confirm the exact call flow against the code rather than assuming.
- **The bridge is macOS-only today.** All existing platform-specific reading and the offset table target macOS Apple Silicon. Windows has no equivalent yet.
- **The rig is fixed.** Same DDJ-800 / SoundSwitch / lasers / LEDs / Govee on every host; only the host computer varies.

## Locked constraints (Brandon's decisions — do not re-litigate)

1. **The data source stays Rekordbox's in-app playback state.** Do not propose swapping to a network or clock protocol: the DDJ-800 does not emit PRO DJ LINK, and Ableton Link carries no track / deck / position.
2. **Targets are macOS Apple Silicon (arm64) and Windows 11 x64.** Intel Mac is out of scope.
3. **Best-effort runtime accuracy is acceptable** — occasional wrong lighting on an unfamiliar machine is fine. The only hard floor is the strobe clamp above.
4. **Raspberry-Pi / standalone (no-Rekordbox) operation is out of scope.** Note it once so the seam doesn't foreclose it; do not design for it.

## Reader-side dependencies to flag (out of scope to solve — name them, don't design them)

These belong to the separate reader spec. In this plan, treat each as a named dependency and a blocking unknown, and route them to the handoff — do not attempt to design or describe their mechanics:

- **Per-host authorization.** Each host must authorize the reader before it can see Rekordbox's state; on macOS this is a per-install, admin-gated setup step, re-applied when Rekordbox updates. Its reliability and operator experience on a machine Brandon doesn't own (a friend's Mac) is a top risk and a top blocking unknown. The mechanism is specified separately.
- **Per-version field data.** Windows x64 field data does not exist yet and must be produced by the reader spec. Treat "a working Windows reader exists" as an assumption this plan depends on, and mark it the top blocking unknown for the Windows target.
- **Version-adaptive lookup mechanism.** If part 2 recommends tolerating unseen builds, the mechanism that finds fields on those builds is the reader spec's job — this plan only defines the interface it must satisfy.

## Working rules

- **Source-of-truth order:** executable code > tests > this packet. Where code and this packet disagree, code wins — flag it.
- **Allowed tools — read-only.** Read the named repo files and search the repo read-only; do web research on cross-platform Python packaging, code-signing, and notarization. You may delegate independent research threads (for example packaging vs. code-signing) to subagents. Do **not** edit code, run or restart the bridge, modify any binary, touch hardware, or use git.
- **Claim discipline.** Label every load-bearing claim `confirmed` / `assumed` / `unknown`, tied to the file, command, or URL behind it. Mark clearly what can only be settled with a real Windows machine or a live foreign Mac.
- **Do not implement.** The output is a plan for Codex, plus the named handoff to a separate reader spec. Write the plan and the report only.

---

### Brandon-facing note (not part of the Opus prompt)

This is the clean planning half — no reader mechanics, so no safeguard-flag risk; runs fine on Opus 4.8 (your current model). The deferred half — Windows field-data derivation, the macOS authorization step, and any version-adaptive lookup — becomes a separate Codex implementation/RE spec, authored *after* this plan defines what that spec must deliver (don't write it speculatively). Save the accepted output to `docs/plans/active/`; that's where the Codex handoff lives.
