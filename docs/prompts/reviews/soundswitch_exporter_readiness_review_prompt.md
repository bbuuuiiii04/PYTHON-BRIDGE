# SoundSwitch Exporter / Importer Readiness Review

## rb_ss_bridge_v2 — ChatGPT/Codex Review Prompt → emits an Opus next-steps prompt

> **Status:** review prompt / non-authoritative artifact (per AGENTS.md §9). Repo status stays
> **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**. Target of review: branch
> `soundswitch/impl`, PR #116, commit `d1d952a` (the readiness review was authored against this
> head; `97f2553` is its parent and has no CI runs). The branch head advances as finisher work
> lands (CI-green fix, T7c, T7e, Task 8/9); the live current commit is recorded in
> `docs/plans/active/soundswitch_impl_progress.md`. Authoring model: Opus 4.8.

---

## ROLE

You are a senior reviewer auditing the SoundSwitch exporter/importer + bridge runtime
integration for "operator-success readiness" — i.e., is this safe for Brandon to run a
real export and (later) a controlled live DMX validation. Trust CODE, TESTS, and LIVE
ARTIFACTS over any prose or doc. Every claim below is a CLAIM TO VERIFY, not a fact.
Cite `file:line` for everything. If you cannot verify something from the repo, say
"UNVERIFIED" — do not guess.

## REPO / WHERE THE WORK IS

- Repo: `github.com/bbuuuiiii04/PYTHON-BRIDGE` (local: `/Users/bbui/rb_ss_bridge_v2`)
- Branch/PR under review: `soundswitch/impl` → PR #116 (base `main`), review head `d1d952a`
  (`97f2553` is its parent; current head advances with finisher commits — see the progress ledger).
- Pinned identity to confirm everywhere: project UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`,
  active-cue union SHA-256 `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`.

## ORIENT FIRST (read before judging)

- Exporter: `tools/export_soundswitch_pack.py` (`export_pack`)
- Compiler/guards: `soundswitch_pack.py` (`compile_pack_artifacts`; F10 guard; pinned-totals tuple; venue/identity boundary)
- Verifier: `soundswitch_pack_verifier.py` ; Loader/importer: `soundswitch_pack_loader.py` (`load_pack`, runtime metadata)
- Startup wiring: `__main__.py` (`_build_soundswitch_pack_startup`, `_start_soundswitch_pack_workers`, `main()`'s signal/atexit block, `_shutdown`, `_build_laser_startup_wiring`'s `backend` param)
- Output: `soundswitch_frame_sender.py`, `soundswitch_midi_input.py`, `laser_output_backend.py`
- Proof gate: `python3 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation`
- Tests: `tests/test_soundswitch_pack.py`, `test_soundswitch_pack_startup.py`, `test_soundswitch_frame_sender.py`, `test_soundswitch_midi_input.py`, `test_soundswitch_laser_player.py`
- Plans/ledger: `docs/plans/active/soundswitch_t7_t8_t9_implementation_spec.md`, `soundswitch_impl_progress.md`
- Run: `cd /Users/bbui/rb_ss_bridge_v2 && python3 -m unittest discover tests` and the proof gate, and report what you actually saw.

## PART 1 — HOW EXPORT ACTUALLY WORKS (trace it, don't assume)

1. Walk the full pipeline end to end: source `.ssproj` → `decode_project` → `compile_pack_artifacts` → staging write → `verify_pack` → atomic publish. What is the exact order, and what runs BEFORE any bytes hit disk?
2. Is the publish truly atomic and crash-safe? Examine the staging dir + `os.replace` + `fsync` + exclusive (`"xb"`) writes. Can a crash/kill at any step leave a partial or corrupt pack at the destination? What about directory-entry durability (is the parent dir fsynced)?
3. Rollback: on verify failure, write failure, or publish failure, is the destination guaranteed absent and the staging guaranteed cleaned? Are there leak paths (e.g., SIGKILL between `mkdtemp` and `replace`)? Is that acceptable?
4. Determinism: is output byte-identical across runs? What makes it canonical (JSON ordering, separators, no timestamps)? Where could nondeterminism sneak in (dict ordering, set iteration, locale, float formatting, git commit embedding)?
5. Identity/version pinning: where are project UUID, venue GUID, soundswitch_version, container_version, fixture profile, universe, channel span enforced? Can a wrong-but-plausible project (e.g., same venue GUID, different project UUID) pass? Confirm the drift checks.
6. Totals fail-closed: confirm compile enforces the pinned totals tuple BY DEFAULT on the real export path (`enforce_pinned_totals` default). What totals are pinned, and would any drift (empty bank, extra/missing cue, wrong DDJ/IAC count, drifted union SHA) hard-fail before publish?
7. F9 (one-byte mutation rejected) and F10 (active CC/pitch-bend render control fails export): confirm both are enforced in the current tree and tested. Is F10's "note-only for render-affecting controls" correct and complete?
8. Does any exported artifact leak sensitive data (absolute paths, audio file paths, device names, serial details)? Verify.

## PART 2 — IMPORTER / LOADER READINESS

9. `load_pack`: does it run the verifier FIRST and fail closed? Can a corrupt/mutated pack ever load into the running bridge? Is the verification error preserved as the cause?
10. Runtime metadata (`bridge_scene_crosswalk`, `learned_midi_bindings`, project/boundary/totals/union): is parsing strict and fail-closed? Any field that is trusted without validation? Any way malformed-but-verified data slips through?
11. Crosswalk/bindings cross-checks: are scene→identity and controller→target references validated against the actual loaded looks/autoloops? What happens on a dangling reference?

## PART 3 — THE NEUTRALITY QUESTION (most important for operator success)

12. PROVE OR DISPROVE: with NO SoundSwitch pack configured (config absent or `enabled=false`), does the bridge behave EXACTLY as it did before this branch? Trace `__main__`: is `MidiOutput` constructed/started identically, the IAC port opened the same, the same backend injected into `LaserSceneExecutor`, `StateManager` untouched?
13. The new signal/atexit block (`_early_shutdown`, `_cleanup_pack_outputs`, `atexit.register`) and the rebound SIGTERM/SIGINT handlers: when no pack is active, do these change ANY existing shutdown behavior, ordering, or timing vs. the prior code? Could they double-stop, swallow signals, or alter exit semantics?
14. Are any new threads, ports, file handles, or background work created when pack mode is OFF? There should be none — confirm.
15. Default backend selection: confirm an ABSENT/disabled pack does NOT silently replace the laser backend with `NoneBackend` (that would kill existing MIDI-laser output). Where exactly is `laser_backend=None` vs `NoneBackend` decided?
16. Is DMX-vs-MIDI-laser mutual exclusivity actually enforced at the PORT level (pack mode must NOT open IAC)? Show the code path.

## PART 4 — EDGE CASES (enumerate and check each)

17. Export-side: missing project file, malformed/truncated project, stale/mismatched identity, duplicate cue names/GUIDs, missing cue bindings, empty banks, unexpected slot counts, invalid DDJ override mappings, partial write failure, pre-existing output (dir AND dangling symlink), symlinked/file/missing parent, generator-commit (git) failure. For each: does it fail loud with a clear error and zero corrupt output? Which are tested, which only inspected?
18. Runtime-side (even though T7c isn't wired yet): startup rollback when controller input or DMX port fails to open async; readiness-handshake timeouts; stop-before-start; idempotent panic/cleanup; stale-hold clearing. Are these correct and tested?
19. What edge case is NOT covered anywhere that could bite a first real run?

## PART 5 — IMPLEMENTATION CLEANLINESS

20. Is the T7b implementation clean or are there smells: dead/placeholder code, duplicated logic (e.g., between `_build_soundswitch_pack_startup` and `_start_soundswitch_pack_workers`), the two-phase owner-registration into the mutable dict, the `PackMidiBinding` relocation, redundant try/except swallowing?
21. Are the tests meaningful (assert real behavior, have teeth) or do any just exercise mocks / assert source-text? Call out any weak or tautological tests.
22. Naming/structure/typing consistency with the rest of the module. Anything that would make future T7c/T7d/T7e work harder?
23. Any correctness bug, race, or TOCTOU you can find in the readiness handshakes or the atomic publish.

## PART 6 — LIVE-SAFETY

24. 200 Hz dispatch path and 40 fps Govee realtime path: does anything here add blocking/slow work or per-frame allocation/IO to those paths? (`load_pack`/config parse must be startup-only.)
25. `kill -9` Enttec last-frame hazard: is it acknowledged and NOT falsely claimed as fail-safe? Is zero-on-stop correct?
26. Status language: any forbidden claims (stable/production-ready/hardware-validated) where only software-validated is justified?

## PART 7 — GAPS / NOT DONE

27. Confirm what is genuinely incomplete: T7c (StateManager per-tick scripted driver — the thing that actually emits DMX frames), T7d (autoloop `phase_tick` — evidence-blocked), T7e (status+commands), Task 8 shadow proof, Task 9 hardware handoff. Is the pushed state a SAFE checkpoint to merge as default-off, or not? Justify.
28. For T7d specifically: is keeping autoloop at safe-zero (until the phase origin is proven from capture evidence) the right call? What evidence would actually unblock it?

## YOUR OUTPUT (required format)

**A.** A concise findings section: for each part, VERDICT (PASS / CONCERN / FAIL / UNVERIFIED) with `file:line` evidence and the single most important risk.

**B.** A blocking-issues list (anything that must change before Brandon exports or before merge), separated from non-blocking nits.

**C.** THEN, as your primary deliverable, EMIT A READY-TO-PASTE PROMPT FOR CLAUDE OPUS that tells Opus exactly how to drive the remaining work to operator success. That Opus prompt MUST:
- State the current verified state and the exact blocking issues you found (with `file:line`).
- Order the next steps: fix any blockers → T7c (scripted-mode per-tick driver, all transition→ZERO edge cases) → T7e (status+commands) → Task 8 shadow proof (physical backend `none`, frame-hash vs expected; autoloop deferred if T7d unproven) → Task 9 operator runbook → operator-executed controlled Enttec/bridge validation.
- Encode hard constraints: bridge code changes must be TDD with the full suite + proof gate + doc gates green; preserve default-off neutrality; preserve the 200 Hz and 40 fps paths; never claim hardware validation; the live run is operator-executed, not autonomous.
- Define explicit acceptance criteria and a verification command list for each step.
- Flag the T7d evidence dependency and what proof unblocks it.

Make the Opus prompt self-contained (paths, commands, pinned IDs) so it works in a fresh session.
