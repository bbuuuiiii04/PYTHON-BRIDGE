---
doc_status: current
truth_level: prompt-only
last_verified_date: 2026-07-04
validation_scope: Fable 5 design-review prompt text only; no bridge behavior, runtime action, or hardware validation
---

# Fable 5 prompt — USB bridge launcher design: review, challenge, expand

Paste the block below to Claude Fable 5. Deliverable is a design review + creative expansion, not implementation.

---

**Model:** Claude Fable 5 · **Effort:** xhigh

This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. The bridge legitimately reads Rekordbox's playback state on Brandon's own machine via a macOS-sanctioned, admin-granted mechanism; treat every mention of that as quoted benign context, out of scope to design or alter. Review only normal software correctness, design quality, maintainability, runtime safety, and operator behavior inside the named scope.

I'm planning a macOS-only USB launcher for Brandon's existing DJ lighting bridge: a self-contained PyInstaller app on a USB stick that spawns the bridge's menubar on any Mac, with **Run temporarily** (wipe-on-eject scratch state) and **Install permanently** (copy to `~/Applications` + launchd `StartOnMount` auto-spawn + uninstall) modes. Brandon is the operator — a project owner, not a software engineer; the rig is his own, used for himself and friends. The design was drafted quickly and approved in outline; before it becomes a Codex implementation plan, I want it stress-tested and improved by someone acting as **executive creative engineer, lead designer, and senior engineering architect in one**: kill weak decisions, find what the design missed, and make it *better* — not just safer.

## Deliverable

One document, three parts, in this order:

1. **Adversarial design review.** Severity-first findings: location (doc § or file:line), the flaw, why it matters in Brandon's actual use (live DJ sets, foreign Macs, non-engineer operator), evidence, and the required change. End with a verdict: `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL`.
2. **Creative expansion.** Ranked ideas that make the product meaningfully better for its real user — operator experience, show-day workflow, failure recovery, first-run flow on a stranger's Mac, the temporary/permanent model itself. For each: what it is, why it earns its complexity, and what it costs. Mark each `adopt now` / `adopt later` / `explored and rejected` with the reason. This project's ethos is solo-hobby minimalism — no enterprise ceremony, no safety theater; an idea must pay rent in operator value, and "delete this part of the design" is a first-class idea.
3. **Relationship ruling.** The launcher spec and the portability plan are meant to compose (launcher = the Mac slice; portability plan = the superset incl. deferred Windows). Confirm or refute that with specifics: any contradiction, duplicated work, or decision in one that quietly forecloses the other — especially whether the launcher's packaging and launch-profile choices remain the base a future Windows target extends rather than a Mac-only fork.

Lead with the outcome: verdict and the top findings first. Label every load-bearing claim confirmed / assumed / unknown, tied to the file or evidence behind it.

## Evidence packet (verified against HEAD 2026-07-04)

- `docs/plans/active/usb_bridge_launcher_design.md` — the design under review.
- `docs/plans/active/cross_platform_portability_plan.md` — the parent plan (verdict, seam, packaging research, strobe floor, §7 memory-access risk).
- Code the design's claims rest on: `scripts/bridge_menubar.py` (raw AppKit/NSStatusBar menubar), `scripts/ss_bridge_watcher.sh` (launch profile env flags; one-process watch logic; hardcoded `/opt/homebrew/bin/python3`; parent-dir import workaround), `__main__.py:417,429,1737` (MIDI port opened by name, IAC Bus 1), `streamdeck/streamdeck_midi.py:431` (existing self-created virtual MIDI port), `pyproject.toml` (deps; numpy optional).
- Repo ground rules: `AGENTS.md` (§0 communication, §6 invariants — esp. exactly one bridge process; §10 status language).

## Locked decisions — challenge the design, not these

Brandon has ruled: **no notarization / no $99** (ad-hoc signing only); **bundle everything** (no host Python/dependency installs); **Windows deferred**; **the one-time admin memory-grant on foreign Macs is accepted** as the residual trace; the memory-reader's authorization mechanics belong to a separate spec — treat as a named dependency, do not design them. Everything else in the design — including its component split, the two modes, `StartOnMount`, the shared launch profile, the build order — is challengeable and should be challenged where weak.

## Boundaries

Read-only repo access (read/search the named files and anything they reference); web research allowed on macOS packaging, launchd, PyInstaller, and menubar-app behavior; parallel subagents fine for independent research threads. Do not edit code or docs, run or restart the bridge, touch git, hardware, or the live rig. Do not implement anything — the output feeds a Codex implementation plan that will be written separately. Write your report to `docs/plans/active/usb_bridge_launcher_fable_review.md` and nothing else.

## Success criteria

- Every §6 "risky bit" in the design is either confirmed with evidence, upgraded to a concrete finding, or explicitly cleared.
- At least the four surfaces are examined: bundling/runtime (PyInstaller + PyObjC + in-bundle bridge), lifecycle (eject/wipe/StartOnMount/one-process invariant), foreign-Mac first-run UX, and live-show failure modes (stick yanked mid-set, Rekordbox restart, second plug-in).
- Creative ideas are ranked and costed, not listed; rejections state why.
- The relationship ruling cites specific sections of both docs, not vibes.
- Stop when the report is written; do not continue into implementation planning.

---

### Brandon-facing note (not part of the Fable prompt)

Fable writes its report to `docs/plans/active/usb_bridge_launcher_fable_review.md`; the next step after you read it is folding accepted findings into the design spec, then the Codex plan. If the run gets blocked, retry with narrower evidence and more neutral wording (the memory-read mention is the likely trigger; it's already framed as quoted benign context) — never jailbreak language.
