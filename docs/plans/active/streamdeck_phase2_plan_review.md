# Phase 2 (Part F) — Plan / Spec Review: generic layered static-look compositor

Status: **planning + spec review — SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.** Do not implement
from this doc alone; it gates the Codex spec. Baseline: `main` @ `2eff33e` (clean tree), suite
**2382 OK** (skipped 3, xfail 1). All anchors below were re-resolved against this HEAD.

Source spec: `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` Part F.

---

## 1. Verdict

**REVISE.**

Task 5 (the live-critical compositor) and Task 7 (controller LEDs) are well-grounded and implementable
with the plan in §3 — that part is READY-quality. The blocker is **Task 6**: its stated hook site,
"the exporter writes `<pack_path>/midi_bindings.json`" (spec lines 359, 362), **contradicts current
code** and cannot be implemented as written. One spec edit fixes it (exact replacement wording in §3,
Task 6). Because a spec line contradicts code, the whole-Part-F verdict is REVISE, not READY.

Why Task 6 as written is impossible:
- The pack verifier enforces **strict file-set equality** against the manifest:
  `if files != sorted(["manifest.json", *declared]): _fail("missing or extra artifact")`
  (`soundswitch_pack_verifier.py:394`). Any file living **inside** the pack dir that the manifest
  doesn't declare fails verification.
- `verify_pack` runs over the **staging** dir on every export/publish, and `publish_pack` re-stages
  from a fresh `mkdtemp` and atomically swaps (`tools/export_soundswitch_pack.py:369,377`). A file
  written into the published pack dir *after* the swap is **wiped on the next re-export** and is never
  covered by verification — so an in-pack sidecar is both illegal (set-equality) and non-durable.
- The repo already has the right pattern and is explicit about it: `_write_source_sidecar` writes a
  **sibling of the pack dir, "NEVER inside it"** (`tools/export_soundswitch_pack.py:37,117-118`).
- Adding `midi_bindings.json` as a real manifest artifact via `compile_pack_artifacts`
  (`soundswitch_pack.py:265,382-383`) is technically valid (the verifier accepts extra declared+hashed
  artifacts beyond the `required` set, `soundswitch_pack_verifier.py:406-409`) **but changes
  `manifest_sha256`**, which is **pinned** in two hard gates:
  `tools/prove_soundswitch_pack_generation.py:85` and
  `tests/test_prove_soundswitch_pack_generation.py:112` (`88a2e948…`). That breaks CI until re-pinned.

Recommendation (defaulted, low-risk): write the sidecar as a **sibling** of the pack dir, exactly like
`_write_source_sidecar`. It touches nothing the live render path reads, leaves the manifest and the
pinned proof-gate hash alone, and the controller (Task 7) reads it from a known sibling path. Task 6 is
build-time only and not live-critical, so this does not gate Task 5.

---

## 2. Current Code Confirmation

All **[confirmed]** unless noted. Anchors re-resolved at `2eff33e`.

- **Single-slot player state — [confirmed].** `LaserPackPlayer._active_static_slot: int|None`
  (`soundswitch_laser_player.py:186`); `hold_static`/`release_static` (`:234-245`);
  `active_static_slot` property (`:192`).
- **Opaque static render path — [confirmed].** `render_static_look_frame` seeds
  `frame = [0] * CHANNEL_COUNT` (`:147`) → unset channels render **black, not transparent**.
  `resolve_frame` returns `static_override if static_override is not None else base` (`:163`) — a
  **whole-frame replace**, never an overlay. Precedence emergency/blackout > static > base (`:161-163`).
- **Scalar MIDI held slot — [confirmed].** `_held_static_slot: int|None` (`soundswitch_midi_input.py:83`),
  with `_static_held_at` (`:84`); processed in `_process_note_on` (`:222-251`, toggle branch `:228-237`)
  and `_process_note_off` (`:253-277`, toggle-ignore `:259-261`). Snapshot field
  `MidiInputSnapshot.held_static_slot: int|None` (`:47`).
- **Snapshot stale-clear WRITES on the read path — [confirmed]** (this is the anti-pattern Task 5B
  fixes). `snapshot()` (`:104-126`) mutates `_held_static_slot`, `_static_held_at`, `_blackout_held`,
  `_blackout_held_at`, `_error` at `:110-119`, and is called **on the 200 Hz push loop** from
  `state_manager._drive_pack_output` (`state_manager.py:3406`). So today the hot path mutates engine
  state — the spec is correct that `snapshot()` must become a pure read.
- **Group snapshot conflict collapse — [confirmed].** `SoundSwitchMidiInputGroup.snapshot()`
  (`:508-525`) collapses adapters to a single slot and raises `conflicting_static_holds` when >1 held
  slot exists (`:515` builds `held_slots`, `:518,522`). Structurally incompatible with a stack.
- **StateManager degradation latch — [confirmed; anchor moved to `:3405-3435`** (spec said 3418-3428,
  correct in substance).] `_drive_pack_output` (`:3362`) reads `midi_input.snapshot()` on the push loop
  (`:3406`); latches `_pack_input_degraded_latched` on `(not worker_alive) or (err is not None) or
  new_drop` (`:3418`); clears it only on a clean/quiet/healthy tick (`:3420-3425`); drops the overlay
  with `slot = held_slot if input_healthy else None` (`:3428`) and calls `hold_static`/`release_static`
  on the push loop (`:3430-3435`).
- **Pack reload behavior — [confirmed].** `LaserPackPlayer.reload()` resets `_active_static_slot=None`
  + `_waiting_after_reload=True` (`:203-211`). `SoundSwitchMidiInputAdapter.on_pack_reload()` clears
  held (`:201-203`); group fans out (`:504-506`). `set_pack_runtime` resets `_pack_last_static_slot=None`
  (`state_manager.py:3302`). **Slot indices are positional and unstable across reload**: built as
  `looks[slot] = LoadedStaticLook(slot_index=slot, …)` (`soundswitch_pack_loader.py:582`).
- **Interaction decoding + `PackMidiBinding.interaction` — [confirmed].** Decoded from the `.ssproj`
  (`soundswitch_project_decoder.py:885-888`, `"toggle" if mode_raw == 1 else "press"`), carried to
  `PackMidiBinding.interaction` (field `soundswitch_pack_loader.py:53`, set `:296`). The engine already
  branches on `binding.interaction == "toggle"` (`soundswitch_midi_input.py:228,259`).
- **Sparse `generic_attributes` + `fixture_group` filter — [confirmed].**
  `LoadedStaticLook.generic_attributes: tuple[LoadedAttribute, ...]` (`soundswitch_pack_loader.py:138`),
  built **sparsely** at `:586`. `LoadedAttribute.fixture_group` (`:58`). `_apply_attribute` **skips rows
  where `fixture_group != PRIMARY_FIXTURE_GROUP`** (`soundswitch_laser_player.py:78`) then writes
  `frame[row.dmx_channel-1] = row.value` (`:82`). Transparency needs **no exporter change** — the
  renderer just discards the sparseness today.
- **`controller_hold_timeout_ms` wiring — [confirmed].** Config field
  (`soundswitch_pack_player_config.py:53`, default 2000 `:117-119`) flows to the adapter as
  `stale_timeout_ms=cfg.controller_hold_timeout_ms` (`__main__.py:498`), used as `_stale_timeout_ms`
  in the snapshot stale logic.
- **Task 6 exporter hook site — [contradicted]** (see §1). Pack-build path is `compile_pack_artifacts`
  (`soundswitch_pack.py:265`) → `_stage_artifacts`/`verify_pack`/swap
  (`tools/export_soundswitch_pack.py:339,341,369,377`); strict file-set equality
  (`soundswitch_pack_verifier.py:394`); pinned manifest hash
  (`tools/prove_soundswitch_pack_generation.py:85`, `tests/test_prove_soundswitch_pack_generation.py:112`).

---

## 3. Implementation Plan

Ordering: **5A → 5B → 5C → 5D → 5E → 5F → 5G** (all bridge-side, commit after each), then **Task 6**
(build-time, independent), then **Task 7** (controller, independent). Task 5 must not start until
Phase 1 has landed and the operator confirms the live build (spec gate, lines 433-434).

**Global constraints (apply to every task; verbatim from the spec / AGENTS):**
- No Stream-Deck/HID/device string, code, or file emit in any `rb_ss_bridge_v2/*.py` runtime module.
- The 200 Hz push loop gains **no** blocking I/O, MIDI/socket/file/subprocess calls, or locks
  (AGENTS §6); stack mutation is worker-thread only, read via an **immutable** snapshot.
- Laser MIDI channels 1-2 untouched; controller stays channel 3, outside bridge runtime.
- `pgrep -f rb_ss_bridge_v2 | wc -l` stays `1`.
- Status language stays SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

### Task 5A — data model: layer entries + immutable snapshot
- **Files owned:** `soundswitch_midi_input.py` (model only).
- **Symbols add/change:** add `@dataclass(frozen=True, slots=True) LayerEntry { slot: int, kind:
  Literal["toggle","press"], seq: int }` (`seq` = monotonic push counter, used only by 5D's merge —
  cheap to add now, avoids a model migration later). Change `MidiInputSnapshot` (`:40-51`): **replace**
  `held_static_slot: int | None` with `held_layers: tuple[LayerEntry, ...]` ordered **bottom→top**.
  Export `LayerEntry` in `__all__` (`:537-542`).
- **Forbidden:** no behavior yet; no render code; no device strings.
- **Preserve:** keep `blackout_held`, `worker_alive`, `error`, `mail_drop_count` fields unchanged.
- **Tests:** update every `snapshot().held_static_slot` assertion in
  `tests/test_soundswitch_midi_input.py` to `held_layers` (mechanical here; semantics land in 5B). Add
  `test_snapshot_is_frozen` coverage for the tuple type.
- **Risk/gate:** the field rename ripples to ~25 call sites in `tests/` and to `state_manager.py:3410`.
  Gate: full suite compiles and the renamed assertions are coherent before 5B.

### Task 5B — MIDI adapter: layer-stack lifecycle + pure snapshot
- **Files owned:** `soundswitch_midi_input.py` (`SoundSwitchMidiInputAdapter`).
- **Symbols add/change:**
  - Replace scalar `_held_static_slot`/`_static_held_at` (`:83-84`) with `_layers: list[LayerEntry]`
    and a `_seq: int` counter (both under `_lock`).
  - `_process_note_on` (`:222-251`) `static_look`: **toggle** → if a `(slot)` entry is present **remove
    it** (do **not** move to top), else append `LayerEntry(slot, "toggle", next_seq)`. **press** →
    append `LayerEntry(slot, "press", next_seq)` on top (allow duplicates; each press is its own layer).
  - `_process_note_off` (`:253-277`) `static_look`: **press** → remove the **topmost** matching
    `(slot, "press")` entry; **toggle** → ignore (`:259-261` behavior preserved).
  - `snapshot()` (`:104-126`) becomes a **pure read**: build `held_layers` by copying `_layers` into a
    tuple **under `_lock`**; perform **no writes**. **Move the stale-clear writes off the read path**:
    delete the static stale logic entirely (static layers no longer auto-expire — spec lines 311-312),
    and move the **blackout** stale-release (`:114-117`) into the worker loop (5C) so blackout-hold
    auto-release survives but never runs on the push loop.
  - `_clear_held` (`:209-220`) → clear `_layers` (and blackout) on stop/panic/reload/worker-death;
    keep the existing reasons and the `changed`-logging.
- **Forbidden:** no `get_ports`/port logic here (that is 5C); no group changes (5D); no render (5F).
- **Preserve:** velocity-0 → note-off normalization (`_feed_raw_message:289-290`); device-name dispatch
  filter (`:310-314`); stale-error recovery on a fresh matched message (`:315-317`) — but keyed off the
  worker/blackout path now, not static; `panic`/`on_pack_reload`/`stop` still clear all held state.
- **Tests:** rewrite the single-slot tests in `tests/test_soundswitch_midi_input.py` to stack semantics:
  `:309-322` (toggle latch/unlatch → push/remove), `:331-343` (two toggles **compose**, not replace;
  press **stacks over** toggle and reverts to the toggle on release — this **inverts** the current
  `test_press_replaces_toggle_and_press_release_clears` and `test_different_toggle_slot_replaces_current`
  assertions). Add: recency order (newest last); re-press removes without reordering; remove-then-re-press
  lands on top. Drop/rewrite `test_toggle_is_exempt_from_stale_timeout` (`:324`) — nothing auto-expires
  now. Split `test_stale_holds_clear_independently…` (`:394-404`) into a **blackout-only** stale test
  driven by the worker tick (5C); static no longer stale-clears.
- **Risk/gate:** this is the behavior inversion (single-slot → stack). Gate: the rewritten lifecycle
  tests pass and a press-over-toggle revert test is green before 5C.

### Task 5C — input-port-gone detection (injectable, worker thread only)
- **Files owned:** `soundswitch_midi_input.py` (`SoundSwitchMidiInputAdapter`, `_make_real_source`,
  `_worker`).
- **Symbols add/change:**
  - Add an injectable `_port_present_source: Callable[[], Sequence] | None` param to `start()` (mirrors
    `_message_source`, `:137`), defaulting to a real reader built from `rtmidi.MidiIn().get_ports`.
  - In `_worker` (`:380-415`), on a throttled cadence (~1 s; reuse the existing poll loop — the source
    already yields `None` every `_INPUT_POLL_INTERVAL_S`), call the port-present source and decide
    presence by **exact string equality** to the bound `port_name`. **Treat any non-string entry as
    absent** (CoreMIDI returned a `None` entry after an abandoned source — spec lines 263-266). Do **not**
    reuse the substring `_match_port_index` scan (`:328-336`) for this check.
  - On port-gone → `_clear_held("input_port_gone")` (clears the whole stack) and set `worker_alive=False`
    so the push loop's fail-closed latch (5G) also sees it. Move the **blackout** stale-release here too.
- **Forbidden:** no `get_ports` call on the push loop; no device strings; no render.
- **Preserve:** the existing real-source open path (`:349-378`) and its `finally: close_port()`; the
  `# ponytail:` immediate-clear ceiling and no-press-watchdog ceiling (spec lines 268-274).
- **Tests:** feed a port-absent signal via the injected source and assert the stack clears; include a
  case where the source returns a **non-string** entry and assert the worker clears (does not raise);
  assert blackout-hold auto-release still fires on the worker tick after the static timeout removal.
- **Risk/gate:** load-bearing on the Phase 1 controller closing its virtual port on deck loss. Gate:
  port-gone clear + non-string-entry safety + blackout auto-release tests green.

### Task 5D — group merge into global recency order
- **Files owned:** `soundswitch_midi_input.py` (`SoundSwitchMidiInputGroup.snapshot()` `:508-525`).
- **Symbols change:** replace the single-slot collapse + `conflicting_static_holds` flag with a
  concatenation of each adapter's `held_layers`. For the **live single-controller** rig this is just
  that one adapter's tuple. For >1 adapter, merge all entries **sorted by `LayerEntry.seq`** (global
  newest-on-top). Keep `blackout_held = any(...)`, `worker_alive = all(...)`, `mail_drop_count = sum`.
  Drop `error="conflicting_static_holds"`; keep `error="input_error"` on any adapter error.
- **Forbidden:** no per-device strings; no push-loop logic.
- **Preserve:** the empty-group healthy default (`worker_alive=True`, `error=None`,
  `held_layers=()`) — `state_manager:3393-3394` relies on it; `status()` (`:527-534`) stays
  path/port/device-free.
- **Tests:** two adapters each holding disjoint slots → merged tuple in `seq` order; single adapter →
  identity passthrough; conflict flag is gone.
- **Risk/gate:** `# ponytail:` the multi-adapter merge is exercised only by tests today (one controller
  live); the `seq` field keeps it a 2-line sort. Gate: single-adapter passthrough preserves 5B order.

### Task 5E — player API: `set_static_layers` + reload clearing
- **Files owned:** `soundswitch_laser_player.py` (`LaserPackPlayer`).
- **Symbols add/change:** replace `_active_static_slot` (`:186`) with `_static_layers:
  tuple[LayerEntry-like, ...]` (store the `(slot, kind)` ordered bottom→top; the player ignores `seq`).
  Add `set_static_layers(layers)` storing the tuple. `reload()` (`:203-211`) must reset it to **empty**.
  Replace `hold_static`/`release_static` (`:234-245`) usage from `state_manager` (5G) with
  `set_static_layers`; keep `active_static_slot` only if a status surface still reads it (else remove and
  fix readers). Update `__all__`.
- **Forbidden:** no I/O, no threads (module is pure by contract, `:1-6`); no device strings.
- **Preserve:** `reload()` still returns `reload_waiting_authority` and sets `_waiting_after_reload`;
  `clear_selection`/`set_masks`/`select_*` semantics unchanged.
- **Tests:** `tests/test_soundswitch_laser_player.py` — replace `hold_static(8)`/`release_static(8)`
  flows (`:175-250,528-529`) with `set_static_layers([...])`; assert reload empties the stack.
- **Risk/gate:** slot indices unstable across reload (`soundswitch_pack_loader.py:582`) — a carried layer
  would render the wrong look. Gate: reload-clears-stack test green.

### Task 5F — pure `apply_layers` compositor
- **Files owned:** `soundswitch_laser_player.py` (replace `render_static_look_frame` `:143-150` +
  `resolve_frame` `:153-163`; rewrite the static branch of `render()` `:363-372`).
- **Symbols add:** `apply_layers(base, layers, static_looks, blackout, emergency) -> tuple[int,...]`:
  1. if `emergency or blackout` → `ZERO_FRAME` (precedence emergency/blackout > stack > base).
  2. start from a **copy of `base`** (validated 19-int frame) — **never `[0]*19`**.
  3. for each layer **bottom→top**, look up its `LoadedStaticLook`, and for each `generic_attributes`
     row apply `_apply_attribute`'s filter: **skip rows where `fixture_group != PRIMARY_FIXTURE_GROUP`**
     (`:78`), else `frame[dmx_channel-1] = value` (explicit 0 overrides; absent channel falls through).
     Topmost layer wins each channel it sets.
  - **Per-layer error isolation:** wrap each layer's application in `try/except (TypeError, ValueError)`;
    on a malformed layer **skip it and log**, continue rendering the rest. One bad look must never ZERO
    the whole frame.
  - `render()` (`:345-373`) calls `apply_layers(base.frame, self._static_layers, self._pack.static_looks,
    False, False)` when `base.diagnostic` is `None` or `missing_selection` (preserve the `:361` gate so
    layers never bypass a stop/stale/error base); empty stack → returns `base` unchanged.
- **Forbidden:** no I/O, no locks; keep it a pure function (testable standalone).
- **Preserve:** identical output to today when the stack is empty (autoloop/scripted/blackout unchanged);
  `CHANNEL_COUNT=19`, `ZERO_FRAME`, `PRIMARY_FIXTURE_GROUP` constants.
- **Tests:** see §4 — the full pure-compositor matrix lives here.
- **Risk/gate:** the transparency seed is the highest-stakes line. Gate: transparency + explicit-0 +
  topmost-wins + two-disjoint-compose + skip-bad-layer tests all green.

### Task 5G — StateManager: pack-input read + degradation latch update
- **Files owned:** `state_manager.py` (`_drive_pack_output` `:3405-3435`).
- **Symbols change:** read `s.held_layers` instead of `s.held_static_slot` (`:3410`). Replace the
  `hold_static`/`release_static` slot-diff block (`:3430-3435`) with one `player.set_static_layers(
  s.held_layers if input_healthy else ())` call; drop `_pack_last_static_slot` diffing (or keep it as a
  cheap change-detect to avoid redundant calls — optional). **Restrict the drop-all latch** (`:3418`)
  to **true worker-death / port-gone only**: trip on `not worker_alive`; **remove `err is not None` and
  `new_drop` from the trip condition** so a transient error string no longer blinks the whole stack.
  Keep the clear condition (`:3420-3425`) and keep fail-closed: a malformed snapshot still raises → the
  outer `except` (`:3523-3542`) submits ZERO.
- **Forbidden:** no MIDI/port I/O on the push loop (the port-gone detection lives in 5C, surfaced via
  the snapshot); no device strings; do not reset the latch on `set_pack_runtime` (H10, `:3298-3299`).
- **Preserve:** blackout handling (`blackout = blackout_held if input_healthy else False`, `:3427`);
  `set_masks`/`clear_selection`/transport derivation (`:3437-3506`) unchanged; status publish fields
  (`:3511-3521`) — `static_held = bool(s.held_layers)` now.
- **Tests:** in `state_manager` pack-driver tests, assert: a transient `error` string does **not** clear
  held layers; worker-death/port-gone (`worker_alive=False`) **does** drop to base; `set_static_layers`
  receives the snapshot's tuple.
- **Risk/gate:** this is the only Task-5 file on the 200 Hz loop. Gate: the no-flicker-on-transient-error
  and worker-death-drops tests green; manual reasoning that the loop still does no I/O.

### Task 6 — exporter: device-agnostic binding sidecar (build-time) — **REVISE wording first**
- **Required spec edit (replace lines 359-362).** Old:
  > "have the **exporter** write `<pack_path>/midi_bindings.json`"

  New (verbatim replacement):
  > "have the **exporter** write the binding sidecar **as a sibling of the pack directory**, at
  > `_sidecar_path`-style `<pack_dir.parent>/.<pack_dir.name>.midi_bindings.json` — **never inside the
  > pack dir** (the verifier enforces strict file-set equality at
  > `soundswitch_pack_verifier.py:394`, and `publish_pack` re-stages + atomically swaps, so an in-pack
  > file is rejected by verification and wiped on the next export). Write it with the existing durable
  > `_atomic_write_result` helper (`tools/export_soundswitch_pack.py:386`) in `_canonical_publish_result`
  > (`:419-447`), right after `_write_source_sidecar`, sourced from the decoded project's learned
  > controls. The pack manifest and its pinned `manifest_sha256`
  > (`tools/prove_soundswitch_pack_generation.py:85`) are **not** touched."
- **Files owned (impl):** `tools/export_soundswitch_pack.py` only.
- **Symbols add:** a `_write_binding_sidecar(destination, decoded)` mirroring `_write_source_sidecar`
  (`:121-130`), emitting a list of `{channel, note, target_kind, interaction, name}` from the project's
  learned static-look bindings (data already present — `interaction` at
  `soundswitch_project_decoder.py:885-888`; `selection_map` control rows at `soundswitch_pack.py:211-219`).
- **Forbidden:** **no** edit to `compile_pack_artifacts` / `soundswitch_pack.py` / the manifest / the
  verifier; **no** new file inside the pack dir; no device name in the payload.
- **Preserve:** export atomicity, lock, and fsync ordering; the canonical proof gate stays green
  (manifest unchanged).
- **Tests:** a small `tools/`-level test: export to a temp dir, assert the sibling sidecar exists with
  the expected `{channel,note,target_kind,interaction,name}` rows and **no** new file inside the pack
  dir; assert `verify_pack` still passes and `manifest_sha256` is unchanged.
- **Risk/gate:** build-time only, not live-critical. Gate: proof gate
  `tools/prove_soundswitch_pack_generation.py` still PASS (29/0/0) after the change.

### Task 7 — controller: local LED state from the sidecar (cosmetic; may diverge)
- **Files owned:** `streamdeck/streamdeck_midi.py` only (controller, **outside** `rb_ss_bridge_v2/*.py`).
- **Symbols add:** read the sibling sidecar at startup (fallback to fixed notes 36-50 if absent); key
  each pad by `(CHANNEL, note)`; toggle pad → track **local** on/off and flip per press; press pad →
  momentary flash (today's behavior). Blank all LEDs on (re)start. A pure
  `led_state(sidecar, pressed_set) -> per-pad-on` mapping for the test seam.
- **Forbidden:** **no** compositor logic in the controller; the LED must **never** drive lighting; never
  emit on MIDI channels 1-2 (keep `CHANNEL = 2`).
- **Preserve:** Phase 1 supervisor/flock/SIGTERM behavior; channel-3 isolation selftest.
- **Tests:** the `led_state` pure mapping (sidecar + pressed-set → lit pads).
- **Risk/gate:** LED is cosmetic and **can diverge** from the bridge stack (spec lines 370-376 — the
  "correct by construction" claim is retracted). Recovery = double-press. Gate: selftest stays green incl.
  the `CHANNEL not in (0,1)` channel-safety assertion.

---

## 4. Test Plan

New/updated tests, by file. **Bold** = the spec's required cases.

**`tests/test_soundswitch_laser_player.py` — pure `apply_layers` matrix (the core, Task 5F):**
- **Transparency over base:** base has CH3=200; a layer setting only CH1 → CH3 still 200, CH1 from layer.
- **Explicit 0 override:** a layer with `value=0` on a channel the base lit → that channel becomes 0.
- **Topmost wins overlap:** two layers both set CH5 → the upper (later, bottom→top) value wins; the
  lower layer's *other* channels still show.
- **Two disjoint toggles compose (Lego):** layer A sets CH1, layer B sets CH2 → both present.
- **Press over toggle reverts on release:** stack [toggle@CH1=v1, press@CH1=v2] renders v2; removing the
  press renders v1 (the toggle), not base.
- **Blackout/emergency → `ZERO_FRAME`:** with any layers, `blackout=True` or `emergency=True` → ZERO.
- **Malformed layer skipped, not whole-frame ZERO:** a layer whose look raises in apply is skipped+logged;
  the remaining layers + base still render.
- Rewrite `test_resolve_precedence_and_frame_validation` (`:146-153`) and
  `test_static_generic_attributes…` (`:133-150`) to the new function; replace `hold_static`/
  `release_static` flows (`:175-250,528-529`) with `set_static_layers`.

**`tests/test_soundswitch_midi_input.py` — stack lifecycle (Tasks 5B/5C/5D):**
- **Toggle add/remove:** note-on adds; re-press removes (does not reorder); remove-then-re-press → top.
- **Press add-on-`note_on` / remove-on-`note_off`:** transient layer; topmost matching press removed.
- **Recency order:** newest entry is last in `held_layers`.
- **Clear on port-gone:** injected port-absent source → `held_layers == ()`.
- **`get_ports` returns a non-string entry:** worker treats it as absent and clears, does not raise.
- **Blackout-hold auto-release after timeout removal:** worker tick releases blackout after its timeout,
  while static layers persist (no static timeout).
- Two disjoint toggles compose at the group level; single-adapter passthrough; conflict flag removed.
- Inversions to land: rewrite `test_press_replaces_toggle_and_press_release_clears` (`:337-343`) and
  `test_different_toggle_slot_replaces_current` (`:331-335`) to **stack** semantics; remove
  `test_toggle_is_exempt_from_stale_timeout` (`:324`).

**`state_manager` pack-driver tests (Task 5G):**
- A transient `error` string does **not** clear held layers (no flicker).
- `worker_alive=False` (worker-death / port-gone) **does** drop the overlay to base.
- `set_static_layers` receives the snapshot's `held_layers` tuple.

**`tools/` exporter test (Task 6):**
- Sibling sidecar written with the expected rows; **no** new file inside the pack dir; `verify_pack`
  passes; `manifest_sha256` unchanged (proof gate stays green).

**Controller test (Task 7):** `led_state(sidecar, pressed_set)` pure mapping.

**Acceptance grep (Task 5 invariant):** assert **no** `streamdeck`/`Stream Deck` token under
`rb_ss_bridge_v2/*.py` runtime code; `pgrep -f rb_ss_bridge_v2 | wc -l` == 1.

---

## 5. Live Safety / Operator Watchpoints

**What changes live (after Task 5 lands + you restart):**
- A held look now **overlays transparently** instead of replacing the whole frame — channels a look
  doesn't set keep showing the autoloop underneath.
- Multiple looks **stack** (newest on top); a **press** look temporarily sits over a **toggle** and
  reverts to the toggle when released; two disjoint toggles show **at the same time**.
- A held look **no longer auto-drops after 2 s** — it stays until you release it (press) or the
  controller's MIDI port disappears.

**What stays unchanged:**
- With **no** look held, autoloop / scripted / blackout output is byte-identical to today.
- Lasers on MIDI channels **1-2** are untouched; the controller stays on channel **3** and remains a
  separate process outside the bridge — the 200 Hz loop gains no new I/O.
- Blackout still blacks the **whole** stack; emergency still wins everything.

**Logs / status that prove health:**
- `pgrep -f rb_ss_bridge_v2 | wc -l` == `1` after any restart (run `/bridge-verify`).
- `/tmp/bridge.log` `[SS-MIDI]` lines: worker started, held-state-cleared reasons (now incl.
  `input_port_gone`), no `worker died`.
- Pack status fields: `static_held` true while a look is held, `input_degraded` flips only on real
  worker-death / port-gone (not on transient glitches anymore).

**What remains HARDWARE-UNVALIDATED:**
- The actual DMX overlay on real fixtures; port-gone detection timing on real CoreMIDI/rtmidi;
  deck-yank → port-gone → stack-clear latency; the residual "lost `note_off` with the port still up"
  tail (accepted, no press watchdog).

**Approval gates before any runtime restart / hardware smoke:**
1. All Task 5 software tests green + full suite still ~2382 OK.
2. Operator sign-off on the press-over-toggle and two-toggle-compose behavior (it's a deliberate change
   from today's single-slot replace).
3. Only then restart the bridge; immediately verify `pgrep == 1`; watch `/tmp/bridge.log` for clean
   `[SS-MIDI] worker started` and no degradation flaps before touching the controller.

---

## 6. Adversarial Review — how Phase 2 could break live, and the guard

1. **Transparency regression blacks the autoloop.** If `apply_layers` seeds a per-layer `[0]*19` (the
   current `render_static_look_frame` pattern, `:147`) instead of copying base, every channel the
   topmost look doesn't set goes black and the autoloop vanishes under any held look. **Guard:** 5F step
   2 starts from a copy of `base`; the **transparency-over-base** test fails if anyone reintroduces the
   `[0]*19` seed.
2. **Push-loop mutation / frame tearing.** Today `snapshot()` *writes* engine state on the 200 Hz loop
   (`:110-119`) and could hand the loop a live list. **Guard:** 5B makes `snapshot()` a pure read that
   returns an **immutable tuple** built under `_lock`; stale/port-gone writes move to the worker (5C).
   Violates AGENTS §6 otherwise.
3. **Degradation latch blinks the whole stack on a transient glitch.** The latch drops **all** overlay on
   any `err` (incl. `stale_hold`) or `new_drop` (`:3418`) — with a multi-layer stack that is a visible
   mid-set stutter. **Guard:** 5G restricts the drop-all to true worker-death / port-gone; the
   **transient-error-does-not-clear** test locks it in.
4. **One corrupt look blacks the stage.** Today a malformed look raises and `render()` fail-closes the
   **whole** frame to ZERO (`:371-372`). In a stack that would kill the autoloop and every other layer.
   **Guard:** 5F isolates each layer in try/except — skip+log the bad one, render the rest; the
   **skip-bad-layer** test asserts the rest still render.
5. **Pack reload points a carried layer at the wrong look.** Slot indices are positional and unstable
   across reload (`soundswitch_pack_loader.py:582`). **Guard:** 5E `reload()` empties the stack and 5G
   pushes `set_static_layers(())` from a fresh group; `set_pack_runtime` already resets the tracker
   (`:3302`). The **reload-clears-stack** test asserts it.
6. **A stuck press (lost `note_off`) overrides the show forever.** **Guard (partial):** the port-gone
   backstop (5C) clears the whole stack when the controller drops its virtual port — load-bearing on the
   Phase 1 `finally: port.close()`. The narrow residual (port stays up, `note_off` lost in the rtmidi
   buffer) is **accepted** with a documented ceiling; recovery is an operator re-press. Flagged, not
   fully eliminated.
7. **Blackout auto-release lost in the timeout removal.** Removing the 2 s static cutoff shares the gate
   that also auto-releases blackout (`:114-117`). **Guard:** 5B/5C keep blackout's `_blackout_held_at`
   timeout, evaluated on the **worker** tick; the **blackout-auto-release-after-timeout-removal** test
   asserts it still fires.
8. **A Stream-Deck token leaks into bridge runtime.** Any device string in `rb_ss_bridge_v2/*.py` couples
   the generic compositor to one surface. **Guard:** layers keyed by generic `(device_name, channel,
   note)`; the acceptance grep fails CI on any `streamdeck`/`Stream Deck` token in runtime code.

---

### Open decision for the operator (the single REVISE item)
Task 6 sidecar location — **recommend sibling-of-pack** (`_write_source_sidecar` pattern; manifest +
pinned proof-gate hash untouched; build-time only, doesn't gate Task 5). The alternative (in-pack
manifest artifact) is also valid but forces re-pinning `88a2e948…` in two hard gates and adds a verifier
surface for zero live benefit. Confirm sibling, and I'll fold the exact wording into the Codex spec.
