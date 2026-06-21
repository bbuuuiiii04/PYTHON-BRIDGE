# Orchestration prompt — SoundSwitch T7 + T8 (+ T9 handoff) implementation

> Paste everything below the line into a fresh **GPT‑5.5 (medium) Codex CLI** session
> (or a Claude failover session) opened in the `rb_ss_bridge_v2` repo. It is written to be
> **model‑portable and resumable from repo state** — if you rate‑limit and switch account/
> vendor, re‑paste the same prompt; the protocol resumes from commits/PR/ledger, not chat
> memory.
>
> Status: planned. Repo status stays **SOFTWARE/WIRE‑VALIDATED ONLY / HARDWARE‑UNVALIDATED**.
> The **before‑T7 live‑safety design review is already complete** (Opus, this is its output);
> the two preconditions it surfaced are encoded as **T7.0** and **T7.1** below.

---

You are the **Orchestrator** resuming the SoundSwitch importer/exporter/player implementation.
Tasks 0–6 are merged/approved (`PR #115`, HEAD `601d8db`, proof gate
`PASS_IMPLEMENTATION_MAY_BEGIN`). Your job: drive **T7 → T8 → T9‑handoff** to completion
through disciplined **implement → self‑gate → adversarial review → revise → checkpoint**
cycles, one task at a time, **resumably** and **cost‑efficiently**. You coordinate; you
delegate the heavy lifting to fresh‑context subagents (§ effort table) and keep your own
context small. You never implement large changes inline.

## 0. Authority — obey in this order
1. Executable code (`*.py`) and tests (`tests/`).
2. **Implementation spec (the only active implementation authority):**
   `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` —
   Part B **Task 7** (`:534`), **Task 8** (`:574`), **Task 9** (`:605`); Part C/D/E/F.
3. **Generic orchestration protocol (follow verbatim):**
   `docs/plans/active/soundswitch_orchestration_prompt.md` §0–§12 — operating reality,
   guardrails, bootstrap, ledger, per‑task loop, gates, subagent brief template, reporting.
4. **Review gates:** `docs/plans/active/soundswitch_review_pack.md` — shared §0–§3 plus
   "Gate — before‑T7" (`:168`), "Gate — T8" (`:195`), "Gate — T9" (`:217`).
5. `AGENTS.md` + `CLAUDE.md`. **If a doc conflicts with code, code wins.** If anything is
   ambiguous or unverifiable, **stop and ask the operator — do not guess.**

Resume anchor / ledger: `docs/plans/active/soundswitch_impl_progress.md`.

## 1. Bootstrap (run every session, including after a failover switch)
1. `git status` / `git log --oneline -8` / `gh pr list --state all --limit 10`.
2. Read only what the current task needs: spec task section → the ledger.
3. Run the proof gate + hard checks (§5). Treat the printed `final_verdict` **string** as
   authoritative; nonzero exit also = blocked.
4. From ledger + git/PR state, determine the single **next action** and resume the loop (§3).
5. Confirm gate inputs exist read‑only (`~/Music/SoundSwitch/default.ssproj` + scratch corpus).

## 2. Hard guardrails — never violate
- **No hardware until the Task 9 operator gate.** Open or write **no** MIDI/serial/Art‑Net/
  Enttec/DMX device — not in code you run, not in tests. **Never restart the bridge.** Never
  mutate the SoundSwitch project (decode/export is read‑only).
- `StateManager` stays the only `DeckState` writer; the **200 Hz `_push_tick` loop gains no
  blocking fs/MIDI/serial/network/subprocess/lock/sleep work**; pack/config are **loaded +
  verified before worker threads start** in `__main__.py`.
- **Pack mode is default‑off / dry‑run. No implicit hot enable.** With pack disabled, OS2L /
  MIDI‑laser / Rekordbox / LED‑Govee / command / status behavior must be **byte‑ and
  order‑unchanged** (diff the paths; run existing tests).
- **Physical MIDI‑laser and direct‑DMX output are mutually exclusive** — enforced at the
  executor object **and** at the port (T7.1).
- Do not import `tools/ssfmt/re/` into production modules. Captures are verifier oracles only.
- Sanitized status only (no audio paths / device names / serial details). Commit no secrets /
  local paths / device IDs / live config / captures / project bytes / proof reports.
- Use repo status language only; **implementation completion is not hardware validation.**

## 3. Per‑task loop (for each task, strict order — never skip ahead)
For the current task: **(1) scope** (read only that task's spec section + Part C/D/E + the
adversarial rows that apply); **(2) contract‑first** (confirm/extend
`docs/agents/change_contracts.yml` — `soundswitch_pack_player` — before any code);
**(3) implement** via a delegated subagent at the §4 tier with a tight §8‑template brief,
TDD preferred (tests from Part D/E first); **(4) self‑gate** (targeted tests + hard checks +
`git diff --check`; rerun the proof gate for any SoundSwitch‑semantics change);
**(5) adversarial review** via a **fresh‑context subagent that did not implement the task**,
cross‑model preferred, using the matching review‑pack gate as its brief; it returns
`APPROVE | CHANGES‑REQUIRED | BLOCKED` with file:line findings per review‑pack §3;
**(6) revise loop** (delegate or inline fixes per §4, re‑gate, re‑review until APPROVE — use
`receiving-code-review` discipline; verify each finding, don't perform agreement);
**(7) checkpoint** (commit on `soundswitch/impl`, push the running PR, record exact gate/test
output in the commit/PR + ledger; `verification-before-completion` — no "done/green" without
the command output in front of you).

## 4. Task → effort → reviewer map (the right subagent for each)
> **Effort‑tier vocabulary (pick the cheapest that is safe; higher = more rate‑limit burn):**
> `sonnet medium` — boilerplate / docs / mechanical scaffolding · `sonnet high` — ordinary
> modules + tests, config loaders · `opus medium` — correctness‑sensitive logic + careful
> safety‑doc authoring · `opus high` — live‑safety‑critical implementation (StateManager /
> 200 Hz / startup / mutual exclusivity) · `opus xhigh` — deepest correctness/live‑safety
> review of the runtime‑owner integration · `opus max` — the pre‑hardware go/no‑go review.
> **Every adversarial review is opus‑tier, fresh context, NOT the implementer, cross‑model
> preferred,** and uses the named review‑pack gate as its brief.

| Step | Implementer | Reviewer + gate brief |
| --- | --- | --- |
| **T7.0** signal‑handler removal + `_shutdown` wiring | **sonnet high** (mechanical edit + docstrings + one wiring line; exact code given) | **opus high** — review‑pack "Gate — before‑T7" live‑safety rows (shutdown / fail‑to‑zero) |
| **T7.1** executor backend injection + port gating + `scene_name` | **opus high** (correctness + mutual‑exclusivity, live‑safety) | **opus high** — "Gate — before‑T7" (mutual exclusivity, default‑off neutrality) |
| **T7** config + loader (scaffold: **sonnet high**) + `StateManager` / status / commands (**opus high**) | **opus high** (StateManager / 200 Hz / startup) | **opus xhigh** — full "Gate — before‑T7" (`:168‑193`) against the actual diff |
| **T8** offline + shadow gates; F9 + F10; totals; shadow `none` | **opus high** (gate completeness) | **opus max** — "Gate — T8" (`:195‑215`) ← the **after‑T8 adversarial review** |
| **T9** operator hardware‑gate **handoff document** | **opus medium** (careful safety‑doc authoring; **never execute**) | **opus high** — "Gate — T9" (`:217‑239`), **REVIEW ONLY, never execute** |

Spawn a subagent when the work is substantial (real reading / multi‑file editing) so your
conductor context stays lean; do trivial one‑liners / ledger edits inline. Brief every
subagent with the §8 template of `soundswitch_orchestration_prompt.md` (ROLE / EFFORT /
READ ONLY THESE / DO / INVARIANTS / GATES TO RUN+PASTE / FORBIDDEN / RETURN summary+diff
stat+exact output, no transcript).

## 5. Gates and verification commands
```bash
# Proof gate — rerun after any SoundSwitch-semantics change; gate on the final_verdict STRING.
python3 tools/prove_soundswitch_pack_generation.py \
  --project ~/Music/SoundSwitch/default.ssproj \
  --output-dir artifacts/soundswitch_pack_generation_proof   # want: PASS_IMPLEMENTATION_MAY_BEGIN

# Hard checks (CI-failing; must pass)
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report   # advisory; re-verify+restamp flagged docs
git diff --check

# Tests: targeted during dev; discover before a PR
python3 -m unittest tests.<the_module_you_touched>
python3 -m unittest discover tests
```
**Honest test reporting (required).** Report exact output. Two failures are **pre‑existing and
unrelated** — do NOT "fix" them, do NOT let them block SoundSwitch PRs, but DO confirm you
added no new ones: `test_led_color_engine_m2_patch_c/d` + `..._phase3` (need the gitignored
live `config/led_look_director.json`) and the order‑dependent `test_runtime_status` flake.
Any **new** failure in a module you touched is a regression you must fix.

---

## 6. Preconditions surfaced by the before‑T7 review (verified at HEAD `601d8db`) — do FIRST, inside T7

### T7.0 — Remove the module‑owned signal handlers (live‑safety blocker; commit alone)
Root cause [confirmed]: `enttec_dmx_pro.py:149` `start()` → `_install_signal_handlers()`
(`:243‑261`) installs **process‑global** `signal.signal(SIGTERM/SIGINT, _handle)` where
`_handle` only calls the worker's `stop()`. This clobbers the bridge's master handler
`__main__.py:1288 _shutdown` (installed `:1311‑1312`): whichever installs last wins, so SIGTERM
either runs only the DMX worker stop (the 200 Hz loop + OS2L never cleanly exit; `sys.exit(0)`
never runs) or clobbers the worker's blackout. The bridge owner must be the single signal
authority.
- `enttec_dmx_pro.py`: delete `_install_signal_handlers()` (`:243‑261`) and its call in
  `start()` (`:149`); drop now‑unused `import signal` (`:29`) — keep `import threading`.
  Update the module docstring (`:13‑14`), class docstring (`:99‑101`), and `start()` docstring
  (`:139`): the worker still pushes a zero packet **on `stop()`** before close (its `_run`
  `finally` → `_push_zero_and_close`), but the **bridge owner drives stop on signals**.
- `soundswitch_frame_sender.py`: reword docstrings (`:7‑10`, `:159‑163`) from "SIGINT/SIGTERM
  … sends a zero packet" to "on owner‑driven `stop()` / `zero_and_stop()`." Behavior is
  preserved: `stop()` → `zero_and_stop()` enqueues `_ZERO_PACKET` then `worker.stop()`.
- `__main__.py _shutdown` (`:1288‑1309`): after `midi_output.stop()` (`:1301‑1302`) and before
  `sys.exit(0)`, add the T7‑constructed sender:
  ```python
  if soundswitch_frame_sender is not None:
      soundswitch_frame_sender.stop()   # zero_and_stop(): zero packet, then worker stop()
  ```
- Tests: `enttec_dmx_pro` installs **no** signal handler (`signal.getsignal(SIGTERM)`
  untouched by `worker.start()`); `_shutdown` calls `sender.stop()`; a stop still emits a zero
  packet via the worker `finally`.

### T7.1 — Enforce backend mutual exclusivity at construction AND at the port
[confirmed] The executor still hardcodes its backend: `laser_executor.py:39` param
`midi_output: MidiOutput`, `:45` `self._backend = MidiOutputBackend(midi_output)` — a
`PackOutputBackend`/`NoneBackend` cannot be injected. And `__main__.py:374‑378` builds **and
`start()`s** `MidiOutput` unconditionally, opening the IAC port regardless of backend, so
`output_backend=pack` would leave a live MIDI‑laser surface concurrent with live DMX
(violates Part C mutual exclusivity).
- Refactor `LaserSceneExecutor.__init__` to accept exactly **one** pre‑built
  `backend: LaserOutputBackend` (drop the internal `MidiOutputBackend(...)`). Keep the single
  `self._backend` slot; no path may hold both a MIDI and a pack backend.
- `__main__.py` selects **one** backend from the validated `output_backend` config:
  - `midi` / default pack‑disabled path: build + `start()` `MidiOutput` **exactly as today**
    → `MidiOutputBackend`. **Behavior‑neutral.**
  - `pack`: do **not** build/start `MidiOutput` (do not open the IAC port); build
    `SoundSwitchFrameSender(enttec_port)` (default‑off/dry‑run keeps serial closed) →
    `PackOutputBackend(frame_sender=…)`.
  - `none` / dry‑run / disabled: `NoneBackend`; open neither MIDI nor serial.
- Add `scene_name` to `LaserMidiMessage` (or carry it in the trigger signature) so
  `PackOutputBackend.trigger` (`laser_output_backend.py:163‑169`) can resolve identities;
  today it always misses → no‑op.
- Tests (currently absent in `test_laser_executor.py`): `trigger()` + `submit_frame()` route
  through the single backend; `output_backend=pack` opens **no** MIDI port; default/disabled
  config opens MIDI exactly as today and emits **identical** MIDI; gated/cooldown/rejected
  scenes never advance pack selection.

## 7. Complete Task 7 (per spec `:534`)
Tracked `config/soundswitch_pack_player.example.json`
(`enabled:false, dry_run:true, output_backend:"none"`, plus `pack_path`, `fixture_map_path`,
`midi_input_aliases`, `enttec_port`, `frame_stale_timeout_ms`, `controller_hold_timeout_ms`)
+ validated loader. Load/verify pack+config **before** worker threads start. `StateManager`
calls **only** pure player/controller methods + nonblocking frame submission and creates **no
second deck/transport authority** (reuse `active_deck`, `DeckState.scripted_id`,
`TrackMetadata.soundswitch_id`, elapsed/playing, lighting mode, beat/phrase, executor‑accepted
selection). Every transition (scripted/autoloop/idle, deck change, track load, stop/stale,
config disable, pack reload, worker error, shutdown) clears incompatible pending/held state
and resolves a safe frame. Sanitized status. **No implicit hot enable** — enable/reload/backend
follows the runtime‑command change contract, validates first, requires explicit operator
action, never partially swaps state.

**T7 stop:** after T7.0 + T7.1 + Task 7 are review‑approved (**opus xhigh** reviewer against
the full "Gate — before‑T7" criteria) and gates green, checkpoint and **proceed to T8** (do not
ask the operator merely to "continue"; the design‑level before‑T7 gate is already satisfied by
this prompt's existence). Stop only on a §10 condition.

## 8. Complete Task 8 (per spec `:574`) + the after‑T8 adversarial review
Implement (**opus high** subagent): rerun the proof gate (`PASS_IMPLEMENTATION_MAY_BEGIN`),
confirm pinned UUID `{3CCBCD6F‑7C1B‑44D8‑882C‑A52A74CC1827}` + active‑cue union SHA‑256
`88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`; **complete F9**
(one‑byte pack mutation rejected) and **F10** (active CC/pitch‑bend override export‑fail);
twice‑export byte‑identical; assert all totals (42/42 Autoloops; 44/45 scripted; 19/19 IAC;
32/32 existing‑path; **232 render + 1 catalog‑tail = 233**; 166 active cues, 0 missing; 32
Static Looks; 4 DDJ overrides; **0 learned collisions**); replay oracles without
capture‑seeded state; shadow mode backend `none`, frame‑hash only.

**After‑T8 adversarial review (mandatory milestone gate).** When T8 is fully implemented,
self‑gated green, and committed, the Orchestrator **deploys a dedicated review subagent**:
- ROLE: adversarial, **opus max** implementation reviewer of Task 8 (pre‑hardware go/no‑go);
  **did NOT implement T8**; cross‑model preferred.
- BRIEF: read `docs/plans/active/soundswitch_review_pack.md` shared **§0–§3** plus
  **"Gate — T8"** (`:195‑215`) and execute it exactly — rerun the proof gate, run the full
  offline/shadow suite, verify F9 + F10 are COMPLETE (not deferred), prove twice‑export
  byte‑identical, throw adversarial mutations at the independent verifier, confirm every total
  + the union SHA, confirm oracles run without contamination, confirm shadow mode is backend
  `none` with no hardware claim. Check the §2 universal invariants. Return a verdict in the
  review‑pack §3 format (`APPROVE | CHANGES‑REQUIRED | BLOCKED`) with file:line findings and a
  SAFETY line confirming no device opened / no bridge restart / no project mutation.
- REVISE LOOP: on `CHANGES‑REQUIRED`/`BLOCKED`, delegate fixes (**opus high**), re‑gate, and
  **re‑run the after‑T8 review with a fresh reviewer** until `APPROVE`. Only `APPROVE` with the
  proof gate `PASS_IMPLEMENTATION_MAY_BEGIN`, F9+F10 complete, and no blocker/major findings
  advances to T9.

## 9. Task 9 — operator hardware‑gate handoff DOCUMENT (author only; NEVER execute)
Once the after‑T8 review is `APPROVE` and revised, produce the Task 9 handoff **document**
(spec `:605`). This is **not** an implementation and **not** an execution — author a doc, open
no device, send no output, do not restart the bridge. The doc must (to be approvable against
review‑pack "Gate — T9", `:217‑239`):
- name whether fixtures are connected/disconnected, the selected output backend + **sanitized**
  port alias, the zero‑frame preflight, and the physical kill method;
- give exact bridge stop/start + rollback commands and single‑process verification
  (`rbss-bridge-verify` / `pgrep -f rb_ss_bridge_v2 | wc -l` == 1) after any restart;
- specify the test order: safe OFF/static → one controlled Autoloop → scripted track → DDJ
  press/release → blackout press/release → disconnect → shutdown, each with explicit
  logs/status/physical pass/fail criteria;
- state plainly that **DMX and MIDI‑laser output are mutually exclusive** and exactly one
  bridge process is required;
- **surface the `kill -9` Enttec last‑frame hazard** (firmware repeats the last frame; physical
  kill/power is the true failsafe) — software must not claim fail‑safe `kill -9`;
- **require explicit operator approval** and state that implementation completion is NOT
  approval and NOT hardware validation; status stays HARDWARE‑UNVALIDATED.

Then run the **T9 doc review** (**opus high**, fresh, REVIEW ONLY, review‑pack "Gate — T9"):
flag as a blocker any handoff that auto‑enables output, infers approval from completion, omits
the kill path, or claims hardware/show readiness. Revise until approved.

**T9 hard stop:** deliver the approved handoff document, set the ledger "Next action" to
`AWAITING OPERATOR: T9 hardware gate (handoff ready, PR #NN) — do not execute`, report, and
**stop. Never execute the hardware steps — that is operator‑only.**

## 10. STOP and ask the operator when
- the proof gate is not `PASS_IMPLEMENTATION_MAY_BEGIN`, or a gate input is missing;
- a change would touch a live‑safety invariant (§2) without an explicit spec mandate;
- the spec is ambiguous or conflicts with code (surface it; don't guess);
- anything would broaden scope beyond SoundSwitch 2.10.3 / canonical UUID / RAVE Venue /
  Universe 0 CH1‑CH19 / the 19‑channel no‑intensity profile;
- you reach any restart / device‑open / Task‑9 **execution** step — operator‑gated; deliver the
  handoff, never execute.

## 11. Reporting + ledger (every cycle)
Update `docs/plans/active/soundswitch_impl_progress.md` after every impl checkpoint, review
verdict, and before any likely failover. Per cycle report to the operator: files changed, the
gate/test output **verbatim**, the review verdict + PR link, and the ledger's updated next
action. Label claims confirmed / assumed / unknown. Never assert "done/green/passing" without
the command output in front of you.

---

### Your first move
Run **Bootstrap (§1)**. Confirm HEAD / proof‑gate / ledger. Then start with **T7.0**
(signal‑handler removal, committed alone), then **T7.1**, then the rest of **Task 7**;
auto‑advance to **T8**; run the **after‑T8 review** (§8); then author + review the **T9
handoff** (§9). Report findings + next step at each checkpoint, and stop only at the §10
conditions and the T9 hardware‑execution gate.
