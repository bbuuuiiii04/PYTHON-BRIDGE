---
doc_status: current
truth_level: prompt-only
last_verified_date: 2026-07-04
validation_scope: Fable 5 plan-review prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Fable 5 prompt — cross-platform portability plan: review, challenge, expand

Paste the block below to Claude Fable 5. Deliverable is a plan review + creative expansion, not implementation.

---

**Model:** Claude Fable 5 · **Effort:** xhigh

This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. The bridge legitimately reads Rekordbox's playback state on Brandon's own machine via a macOS-sanctioned, admin-granted mechanism; treat every mention of that as quoted benign context, out of scope to design or alter. Review only normal software correctness, design quality, maintainability, runtime safety, and operator behavior inside the named scope.

I'm stress-testing the feasibility report + phased plan for making Brandon's DJ lighting bridge portable across host laptops (macOS-arm64 now, Windows-x64 deferred but planned-for) and across Rekordbox versions. Brandon is the operator — a project owner, not a software engineer; same physical rig everywhere, only the host varies. The plan was produced by Opus from code analysis plus cited packaging/signing research; before any phase becomes a Codex spec, I want it challenged and improved by someone acting as **executive creative engineer, lead designer, and senior engineering architect in one**: attack the weak reasoning, find what the plan missed, and make it better — not just longer.

## Deliverable

One document, three parts, in this order:

1. **Adversarial plan review.** Severity-first findings: location (doc § or file:line), the flaw, why it matters in Brandon's actual use (live DJ sets, foreign machines, non-engineer operator), evidence, and the required change. Scrutinize especially: the claimed seam (is the "five primitives" surface really complete — e.g. `live_bpm.py` and `filepath_resolver.py` also touch OS specifics?), the strobe-floor design (§4 — is the two-clamp scheme actually sufficient as the one hard safety floor?), the phase ordering (§5 — is Phase 1 still the right first move now that notarization is declined?), and the external research claims the plan leans on (packaging, virtual-MIDI-on-Windows, SmartScreen). End with a verdict: `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL`.
2. **Creative expansion.** Ranked ideas that raise the plan's value for its real user — cheaper de-risking, better failure/degradation behavior on unknown Rekordbox builds, smarter use of the existing replay tooling, anything the plan under-uses. For each: what it is, why it earns its complexity, what it costs; mark `adopt now` / `adopt later` / `explored and rejected` with the reason. Ethos is solo-hobby minimalism — no enterprise ceremony; "cut this phase/section" is a first-class idea.
3. **Relationship ruling.** This plan and the USB launcher design are meant to compose (launcher = the Mac slice executing this plan's Mac path; this plan = the superset holding the seam, version resilience, and the deferred Windows work). Confirm or refute with specifics: contradictions, duplicated work, or a decision in either that quietly forecloses the other — especially whether the launcher's packaging/launch-profile choices remain the base a future Windows target extends rather than a Mac-only fork.

Lead with the outcome: verdict and top findings first. Label every load-bearing claim confirmed / assumed / unknown, tied to the file or evidence behind it.

## Evidence packet (verified against HEAD 2026-07-04)

- `docs/plans/active/cross_platform_portability_plan.md` — the plan under review (already updated for the declined-notarization decision).
- `docs/plans/active/usb_bridge_launcher_design.md` — the Mac-slice design it must compose with.
- Code the plan's claims rest on: `rb_state_reader.py:48-56,658-790` (reader orchestration; the five imported primitives; chain walker), `rb_memory.py:54-98,126-139,1255-1260` (mach/ctypes primitives, pgrep, vmmap), `rb_offsets.py` (5-build macOS-arm64 table; fail-closed lookup), `models.py` (platform-agnostic currency), `state_manager.py:3304,2363,3623-3717` (BPM write points and fan-out — the proposed clamp sites), `rb_state_reader.py:690` (the 0<bpm<1000 filter), `led_models.py:170-173`, `beat_sync_engine.py`, `live_bpm.py:799-823` (Info.plist version detection), `filepath_resolver.py:85-87` (lsof + DB fallback), `session_recorder.py` / `session_replayer.py` (the replay seam), `pyproject.toml`, `scripts/ss_bridge_watcher.sh`.
- Repo ground rules: `AGENTS.md` (§6 invariants — 200 Hz push loop, no blocking I/O in it, exactly one bridge process; §10 status language).

## Locked decisions — challenge the plan, not these

Brandon has ruled: data source stays Rekordbox's in-app playback state (no network/clock protocols); targets are macOS-arm64 + Windows-11-x64 with Intel Mac out of scope; **Windows is deferred** (a timing decision — keep the plan Windows-ready, don't delete the Windows half); **no notarization / no $99** (ad-hoc signing only); best-effort runtime accuracy is acceptable with the strobe floor as the only hard requirement; reader mechanics (per-host authorization, Windows field data, adaptive lookup) belong to a separate spec — named dependencies, do not design them; Pi/standalone out of scope.

## Boundaries

Read-only repo access (read/search the named files and anything they reference); web research allowed on cross-platform Python packaging, PyInstaller, launchd, Windows virtual MIDI, and photosensitive-flash safety thresholds; parallel subagents fine for independent verification threads. Do not edit code or docs, run or restart the bridge, touch git, hardware, or the live rig. Do not implement anything — accepted findings get folded into the plan, then Codex specs, separately. Write your report to `docs/plans/active/cross_platform_portability_fable_review.md` and nothing else.

## Success criteria

- Every `assumed`/`unknown` label in the plan is either confirmed with evidence, upgraded to a concrete finding, or explicitly left standing with the reason it cannot be settled from a desk.
- The seam-completeness question is answered file-by-file: every OS-specific touchpoint in the runtime bridge is either inside the plan's claimed surface or named as a missed one.
- The strobe-floor section gets an explicit sufficient / insufficient ruling with evidence.
- At least one external-research claim per area (packaging, signing, Windows MIDI) is spot-verified rather than trusted.
- Creative ideas are ranked and costed; rejections state why. The relationship ruling cites specific sections of both docs.
- Stop when the report is written; do not continue into implementation planning.

---

### Brandon-facing note (not part of the Fable prompt)

Fable writes its report to `docs/plans/active/cross_platform_portability_fable_review.md`. Read it alongside the launcher review — part 3 of each is the same composition question examined from opposite ends, so disagreements between the two reports are themselves findings. If the run gets blocked, retry with narrower evidence and more neutral wording (the memory-read mention is the likely trigger; it's already framed as quoted benign context) — never jailbreak language.
