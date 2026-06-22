---
doc_status: active-plan
truth_level: code-grounded
last_verified_commit: 37fffa4
last_verified_date: 2026-06-22
validation_scope: capture-gate handoff only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# T7d capture-gate handoff (for the next agent)

> **Why this handoff exists.** All software prerequisites for the T7d
> phase-contract evidence pass are built, tested, and green. The remaining work
> is the **live capture gate**, which needs an actively running bridge and the
> operator physically at the decks for an extended session. At handoff time the
> bridge core process was **not running** and the status file was stale, so no
> capture could be taken in that session. This document hands the capture gate to
> the next agent so it runs when the operator is actually present.

## 0. THE ONE RULE THAT MATTERS MOST

**An "OPERATOR ACTION" is an active-wait gate, NOT a stopping point. You MUST NOT
end your turn at a gate.**

When you need a physical action from the operator (Brandon), you:

1. **Ping** him — audibly (`say`) **and** visibly (desktop notification) **and**
   print the exact action. The conductor's `ping()` does all three; use it.
2. **Keep your turn alive and poll** for the artifact/marker/state that proves
   the action happened (the conductor's `poll_until` / `run-scenario` does this).
3. **Resume automatically** the instant the polled condition appears.
4. Ping again **only** when *another* physical action is required.

You MUST NOT:

- ❌ end your turn and write "awaiting operator action";
- ❌ ask Brandon to paste anything back into you to continue;
- ❌ mark the task complete because an operator action is pending;
- ❌ hand off a checklist and quit;
- ❌ reinterpret a missing artifact as evidence.

This rule exists to stop the constant operator/agent back-and-forth. **Stay in
the loop and poll. Only physical actions Brandon must do himself should ever
leave your control, and even then you keep polling for their result.**

If you genuinely must wait a long time between physical actions, use the
runtime's scheduled-wakeup / active-poll mechanism so your turn continues — do
not terminate.

## 1. What Brandon must do physically (everything else is automated)

Only these cannot be safely automated; ping for each and poll for the result:

- confirm fixtures/Enttec disconnected and safe, SoundSwitch open on the saved
  bounded project, no live audience;
- start/stop a physical playback/transport action (load + play a deck, switch
  master, etc.) per the scenario;
- start `sudo tcpdump` (needs sudo) and stop it with Ctrl-C (you cannot stop a
  sudo process you did not own);
- approve + perform an exact bridge restart **only** if a scenario needs startup
  flags (phrase-anchor; possibly correction).

Automated by the conductor: run dir + manifest, one-bridge-process check,
status/pack-disabled check, project before/after hashing, session-recorder
start/stop (via the runtime command file), Universe-0 frame parsing, marker
validation, classification, sanitized summaries.

## 2. Preconditions to verify FIRST (fail-closed)

```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 tools/t7d_capture_conductor.py prepare
```

`prepare` reports the core bridge process count and whether the pack backend is
disabled, and pings Brandon for the safety confirmation. **Do not start any
scenario** unless: exactly one core bridge process, pack backend disabled
(`soundswitch_pack` null or `enabled=false`/`backend in {none,midi}`), fixtures
safe.

At handoff: `pgrep`-core was **0** (bridge not running) and
`/tmp/rb_ss_bridge_v2_status.json` was stale. The bridge must be started by
Brandon (menubar toggle) before captures. Starting/restarting the bridge is an
operator action — ping, state the exact reason, and **poll** `prepare` until it
is green. Per the live-safety rule, after any restart verify exactly one
process (`pgrep -f rb_ss_bridge_v2 | wc -l` core == 1).

## 3. Run the scenarios (active-wait, two accepted reps each)

```bash
python3 tools/t7d_capture_conductor.py run-scenario <name> --run-stamp <YYYYmmdd_HHMMSS>
```

`run-scenario` already implements the §B4.5 protocol: baseline → recorder start
→ ping for tcpdump + the scenario action → **active-wait** for pcap+session
growth → **active-wait** for the scenario markers → ping to stop → settle →
classify → sanitized `summary.json`. It pings at each physical gate and polls in
between. Do not replace this with manual steps.

Seven scenarios (each needs **two ACCEPTED repetitions**, plus the identity/BPM
coverage of plan §A4/§B6 — ≥3 verified IAC/bank-4 identities, ≥2 BPM/pitch
values, ≥1 full holdout identity):

| name | what Brandon does | required markers (presence) |
| --- | --- | --- |
| `arm` | load+play a known unscripted track through ≥2 phrases | `[LX] fired` |
| `refire` | hold one identity across a marker refire + a 32-beat interval refire | `[SM] midi-refire` |
| `master-switch` | two decks similar BPM; switch master >1s before a 32-beat boundary | `[LX] fired` |
| `drop-hold` | reviewed drop_mode, nonzero post_drop_hold_beats; capture the whole hold | `[LX] fired` |
| `buildup` | curated Smart Drop + UP phrase; start before the lookahead | `[LX] fired role=buildup`, `buildup_to_drop_window` |
| `phrase-anchor` | **needs restart** with `RBSS_SMART_REARM_EXPERIMENT=1 RBSS_PHRASE_ANCHOR=1` | `phrase-anchor-clear`, `phrase-anchor`, `autoloop-rearm reason=phrase-anchor` |
| `correction` | master phrase-arm on; switch master 0.25–0.5 beat after a 32-beat boundary | `arm-grace-late`, `arm-correction-pending`, `arm-correction-clear` |

> Marker strings are presence checks sourced from plan §B3; confirm them against
> `bridge_fmt` log output and refine `SCENARIOS[...]["required_markers"]` in the
> conductor if a real run shows a different exact string. Refining a marker is a
> tooling change, not evidence reinterpretation.

**Restart gate.** For `phrase-anchor` (and `correction` if it needs flags), the
conductor pings for an operator-approved restart with the exact flags and does
**not** restart. Ping Brandon, state the exact command and why, then **poll**
`prepare` until green and re-run. A missing-flag run is `INCOMPLETE`; never
substitute a synthetic event.

**Fail-closed.** Every active wait times out into an `INCOMPLETE` record. Do not
reinterpret. Re-ping and re-run if an operator action can fix it; otherwise
record the precise hard blocker.

Track progress:

```bash
python3 tools/t7d_capture_conductor.py summarize-corpus
```

## 4. After enough ACCEPTED captures: run the oracle

For each accepted segment (one identity per run), run the falsifiable oracle:

```bash
cd tools/ssfmt/re
python3 validate_autoloop_capture.py <run_dir>/artnet.pcap \
  --venue <verified-venue> --t7d \
  --phase-trace <run_dir>/session.jsonl \
  --t7d-ssfile <one immutable pack ssfile for this segment> \
  --owner-deck <deck> --clock-offset <measured dual-timestamp residual>
```

It emits a JSON verdict: `PASS_T7D_PHASE_CONTRACT`, `FAIL_T7D_PHASE_CONTRACT`,
or `INCOMPLETE_T7D_EVIDENCE`, plus whether 600 passed, the winning quantizer,
and the origin. The contract math is unit-tested
(`tests/test_t7d_phase_contract.py`); the pcap/trace alignment glue is exercised
only on real data — confirm the clock offset and segment windows against the
capture (plan §B5) and do not seed any production value from a capture.

The schema-2 phase trace requires the **B1 `_push_tick` call-site** to be wired
first — that is a live-critical hot-path edit deferred for plan-first review (see
plan §B1 implementation-status note). Get that reviewed and merged before live
captures, or the `session.jsonl` will lack `autoloop_phase` rows.

## 5. Then, and only then, write the final artifacts

- Update `docs/validation/soundswitch_t7d_phase_contract_evidence.md` with the
  real accepted/rejected/incomplete set, hashes, ticks/beat tested, 600
  pass/fail, quantizer, per-scenario origin/reset/continue/snap, tolerances,
  identity ownership, Universe-0 verification, project hash result, recorder
  drops, rejected hypotheses, and the final verdict.
- **If and only if** the corpus verdict is `PASS_T7D_PHASE_CONTRACT`, write
  `docs/plans/active/soundswitch_t7d_runtime_autoloop_dmx_implementation_spec.md`
  grounded in that evidence (proven TICKS_PER_BEAT, quantizer, per-transition
  origin contract, StateManager integration, safe-zero/precedence, tests,
  rollback, sanitization, and an explicit hardware-unvalidated statement).
- If FAIL/INCOMPLETE, update
  `docs/validation/soundswitch_t7d_phase_contract_blocked.md` with exactly what
  is still missing. **Do not write a runtime spec without passing evidence.**

Repo status stays **SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED**
throughout the capture pass; a software/wire pass never upgrades it.

## 6. Session log — 2026-06-22 (prep done, capture not yet run)

Operator was **not yet set up** for the live pass, so no scenarios ran. All
automatable prep is done; resume goes straight to §3 scenario captures.

- **Restart gate CLEARED.** The core bridge was restarted onto the B1 wiring
  (core start `14:14:57` > `state_manager.py` mtime `14:00:04`). Phase-trace
  rows emit only during an active recording while *playing*. **Re-verify B1 is
  live before trusting any capture** — preferred smoke test (definitive, beats
  the start-time heuristic): with the operator playing a deck, append
  `{"cmd":"toggle_record_session","path":"/tmp/t7d_smoke.jsonl","dedup":false}`
  to `/tmp/rb_ss_bridge_v2_commands.jsonl`, wait a few playing seconds, toggle
  again to stop, and confirm `/tmp/t7d_smoke.jsonl` contains `autoloop_phase`
  rows + a `phase_trace_footer`. If it does not, the running core predates the
  wiring — operator must restart (menubar toggle) and re-verify `prepare`.
- **Conductor blocker FIXED (commit `f66b69f`).** `core_bridge_process_count()`
  counted the menubar's `python -m rb_ss_bridge_v2 ... | tee /tmp/bridge.log`
  shell wrapper as a second core, so `prepare`/run-scenario baselines
  permanently failed `count==1` under the real launch method. Now a pure
  `is_core_bridge_line()` requires an exact `-m rb_ss_bridge_v2` module and
  drops shell-wrapper lines; a genuine second python core still reports 2
  (safety preserved). `prepare` is now green (1 core, pack disabled).
  `tests/test_t7d_capture_conductor.py::CoreProcessLineTests` covers it.
- **Resume command (operator says "go"):** `python3
  tools/t7d_capture_conductor.py prepare` (expect green) → run the smoke test
  above → `python3 tools/t7d_capture_conductor.py run-scenario arm --run-stamp
  <YYYYmmdd_HHMMSS>`. `phrase-anchor` still needs an operator restart with
  `RBSS_SMART_REARM_EXPERIMENT=1 RBSS_PHRASE_ANCHOR=1` (current launch has
  REARM but not PHRASE_ANCHOR).
