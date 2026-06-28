---
doc_status: current
truth_level: code-and-re-evidence-grounded implementation spec
last_verified_commit: 2c5758a
last_verified_date: 2026-06-28
validation_scope: current-code inspection plus committed static/passive-live RE evidence for local Rekordbox 7.2.11 Deck 1/2 upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 mid fader, relaunch reacquire, and mixer-chain readability after operator-labeled master-button actions; runtime implementation, software behavior, and hardware behavior unvalidated
---

# Codex Implementation Spec - Rekordbox Mixer Active-Deck Authority

Status: ACTIVE SPEC. This is an implementation handoff, not proof that runtime
mixer authority exists.

The feature target is `docs/architecture/active_deck_authority.md`: the
show-driving `active_deck` must be selected from Deck 1/2 playing state,
upfader position, LOW/BASS EQ, and Rekordbox-master tie/fallback rules.
Rekordbox master must remain visible separately as `rb_master_deck`.

This project is separate from the SoundSwitch exporter / bridge-native DMX
runtime work. Keep downstream SoundSwitch, laser, LED/Govee, scripted, and
autoloop behavior unchanged after the resolved show deck is chosen.

## Part A - Current Truth And Root Cause

- [confirmed] `DeckState` has no mixer fields today; it stores metadata,
  playing, elapsed, scripted id, load generation, and track title hint
  (`models.py:75-89`).
- [confirmed] `OutputState.active_deck` is the current show-deck field and
  defaults to Deck 1 (`models.py:125-128`).
- [confirmed] `BridgeEvent` is the existing event shape used by reader threads
  to publish state into `StateManager` (`models.py:115-122`). It is treated as
  immutable by convention today, but the dataclass and its `payload` are mutable.
- [confirmed] `Ev.MASTER_CHANGED` currently means "deck = new master (1 or 2)"
  (`models.py:196-198`).
- [confirmed] `rb_offsets.py` has only the legacy fixed layout: one
  `master_deck` chain plus BPM, live position, track-info, and ANLZ chains per
  deck (`rb_offsets.py:29-38`, `rb_offsets.py:167-175`).
- [confirmed] `parse_offsets()` currently reads exactly `1 + 4 * deck_count`
  chain lines and slices away any extra anonymous lines after that legacy layout
  (`rb_offsets.py:188-234`).
- [confirmed] `_parse_chain()` currently parses all tokens with base 16
  (`rb_offsets.py:180-185`). The module comment says "hex (or decimal)",
  but current code does not auto-detect decimal.
- [confirmed] `RBStateReader._tick()` reads `offs.master_deck` and emits
  `Ev.MASTER_CHANGED` when the valid direct master byte changes
  (`rb_state_reader.py:242-252`).
- [confirmed] `RBStateReader._tick_deck()` emits `ANLZ_PATH` before
  `TRACK_LOADED`; this ordering must remain intact (`rb_state_reader.py:266-300`).
- [confirmed] `RBStateReader` already derives play/pause from live-position
  movement after warmup/evidence polls (`rb_state_reader.py:317-386`). Basic
  play/stop is not unresolved RE.
- [confirmed] `RBStateReader._enqueue()` already routes enabled authoritative
  event kinds to the authoritative queue without blocking the reader thread
  (`rb_state_reader.py:494-505`).
- [confirmed] `RBStateReader._follow_float()` rejects `0.0` and `1023.0`
  (`rb_state_reader.py:530-542`). That helper must not be reused for mixer
  fader/EQ reads because those are valid mixer endpoints.
- [confirmed] `__main__.py` can make direct master authoritative by adding
  `Ev.MASTER_CHANGED` to `authoritative_kinds` when `RBSS_MASTER_DIRECT=1`
  (`__main__.py:1396-1410`).
- [confirmed] OSC `/bridge/active_deck` and `/bridge/bridge_deck` enqueue
  `Ev.MASTER_CHANGED` unless direct master readiness bypasses the OSC input
  (`__main__.py:717-733`).
- [confirmed] `StateManager._handle_event()` sends every `Ev.MASTER_CHANGED`
  directly to `_on_master_changed()` (`state_manager.py:1168-1175`).
- [confirmed] `_on_master_changed()` currently writes
  `self._os.active_deck = new_deck` and resets lighting/autoloop/LED/laser
  state (`state_manager.py:2610-2671`).
- [confirmed] `set_initial_state()` also writes startup `active_deck`
  (`state_manager.py:644-648`).
- [confirmed] Current playing-only mirror auto-switch paths still enqueue
  `Ev.MASTER_CHANGED` in stale/idle, stop-confirmed, and active-idle cases
  (`state_manager.py:3624-3633`, `state_manager.py:3772-3784`,
  `state_manager.py:3797-3810`).
- [confirmed] `_do_resume()` has a direct empty-deck correction that writes
  `self._os.active_deck = mirror` without going through `_on_master_changed()`
  (`state_manager.py:4429-4440`).
- [confirmed] `_push_tick_inner()` reads `active = os.active_deck` and indexes
  `self._deck[active]` before downstream output work (`state_manager.py:3561-3569`).
- [confirmed] `_drive_pack_output()` uses `self._os.active_deck` to render the
  active pack deck (`state_manager.py:3389-3408`).
- [confirmed] `SoundSwitchEngine.deck_route(active)` assumes `active` is a real
  bridge deck and returns `(active, 3 - active, 3, 4)`; `active=0` would create
  invalid routing (`sound_switch_engine.py:20-23`).
- [confirmed] `_update_lighting()` derives scripted/autoloop/idle from the active
  deck's playing/scripted state (`state_manager.py:3187-3218`).
- [confirmed] Per-tick OS2L sends fan out through `SoundSwitchEngine.deck_route`
  for the current active deck (`state_manager.py:3875-3888`,
  `state_manager.py:4103-4107`).
- [confirmed] `StateManager.snapshot()` currently publishes `active_deck` but no
  `rb_master_deck`, mixer validity, or authority reason (`state_manager.py:1013-1045`).
- [confirmed] `runtime_status._heartbeat_payload()` currently returns
  `"master": active_deck`, so heartbeat conflates Rekordbox master with show deck
  (`runtime_status.py:637-677`).
- [confirmed] Current tests expect that heartbeat conflation
  (`tests/test_runtime_status.py:479-521`).
- [confirmed] `__main__.py` currently builds `RBStateReader` only when at least
  one existing direct flag is enabled (`__main__.py:1021-1024`,
  `__main__.py:1396-1411`).
- [confirmed] The active-work/status docs say mixer active-deck authority is
  planned, local Rekordbox 7.2.11 only, runtime-unimplemented, and
  hardware-unvalidated (`docs/status/active_work_registry.md:28`,
  `docs/status/feature_status_matrix.md:37`,
  `docs/status/validation_matrix.md:38`).

RE facts the implementation must preserve:

- [confirmed] The committed evidence is for installed Rekordbox `7.2.11.0342`
  only, using thin arm64 artifact `/tmp/rbss_re/rekordbox_7_2_11_arm64`, MD5
  `f87084a7261547c0fe0c725291fa8c3e`, and SHA-256
  `bfd71965fb23fb6dc88461de9bd39e371b34a6455faea89fd1e353ba1d03efbd`
  (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:20-27`).
- [confirmed] The bridge-readable mixer root is holder `base + 0x4e16ea8`,
  engine `*(holder + 0x40)`, audio graph `*(engine + 0xa8)`, mixer vector
  `*(graph + 0x458)`, mixer base `*(mixer_vector + 0)`, channel vector
  `*(mixer_base + 0x2c8)`, and `channel_graph[n] = *(channel_vector + n * 8)`
  (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:53-77`).
- [confirmed] Deck 1 maps to mixer channel index `0`, Deck 2 maps to channel
  index `1`, upfader raw is `0..1023` normalized by `raw / 1023.0`, LOW/BASS
  raw is `0..255` normalized by `raw / 255.0`, and EQ band index `2` is
  physical LOW/BASS (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:79-123`).
- [confirmed] Passive one-control-at-a-time proof mapped Deck 1/2 upfader and
  LOW/BASS changes without swapping channel ownership
  (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:136-152`).
- [confirmed] CFX FILTER param0/param1 chains are RE-proven as tracking/status
  data only; filter must not decide active-deck authority
  (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:154-204`,
  `docs/architecture/active_deck_authority.md:67-82`).
- [confirmed] Relaunch reacquire and mixer-chain readability after
  operator-labeled master-button actions are proven for local 7.2.11; the JSONL
  mixer artifacts do not prove raw direct-master bytes
  (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:230-259`).
- [unknown] Other Rekordbox versions are unvalidated.
- [unknown] Actual loaded-track play/stop survival was not proven by the mixer RE
  evidence; current bridge play/pause still comes from existing live-position
  movement (`docs/research/rekordbox_mixer_active_deck_re_evidence.md:324-334`).
- [unknown] Runtime validity/freshness thresholds, resolver hysteresis/stability
  timing, status integration, and hardware-visible output remain implementation
  or validation work.

Root cause: current runtime treats Rekordbox master changes and playing-only
mirror heuristics as the show-driving deck. The target behavior keeps
`rb_master_deck` as a separate Rekordbox signal and selects `active_deck` from
the audible Deck 1/2 mixer state when that state is valid.

## Part B - Tasks

### Absolute Rules

- Do not restart the bridge without explicit live-operation approval in that
  implementation turn.
- Do not run process-memory sampling, live capture, Ghidra, GhidraMCP, or
  hardware-adjacent checks unless explicitly approved in that implementation
  turn.
- Do not open MIDI, serial, DMX, Enttec, Govee, SoundSwitch, laser, or LED output
  paths for this feature.
- Do not add a runtime feature flag. Mixer dominance is the default once it is
  implemented, with visible fallback while mixer authority is invalid.
- Do not add a config/calibration file unless live evidence proves code constants
  are not enough.
- Do not use real audio loudness, crossfader, trim/gain, channel mute, mid/high
  EQ, unrelated FX, CFX FILTER, or Decks 3/4 as authority inputs.
- Do not redesign SoundSwitch exporter, direct-DMX, laser, LED/Govee,
  scripted-track, or autoloop behavior. Only change how the show deck is chosen.
- The 200 Hz `StateManager` push loop must not gain blocking I/O, process-memory
  scanning, Ghidra calls, filesystem scans, network calls, MIDI/serial/DMX calls,
  sleeps, subprocess calls, or status-provider calls.

### Task 1 - `rb_offsets.py`: named optional mixer fields

Implement the offset model extension before reader code.

Exact model changes:

- Add these optional fields to `RBOffsetVersion`, all defaulting to `None` for
  old records:
  - `mixer_deck1_upfader_raw: Optional[ChainEntry]`
  - `mixer_deck2_upfader_raw: Optional[ChainEntry]`
  - `mixer_deck1_low_raw: Optional[ChainEntry]`
  - `mixer_deck2_low_raw: Optional[ChainEntry]`
- If CFX FILTER is exposed for tracking/status in the same implementation, add
  these optional non-authority fields:
  - `filter_deck1_param0: Optional[ChainEntry]`
  - `filter_deck2_param0: Optional[ChainEntry]`
  - `filter_deck1_param1: Optional[ChainEntry]`
  - `filter_deck2_param1: Optional[ChainEntry]`
- Do not represent Decks 3/4 mixer fields for authority in this feature.

Exact parser behavior:

- Keep old blocks with only the legacy `1 + 4 * deck_count` chain lines valid.
  They must set every mixer/filter field to `None`, which makes mixer authority
  fail closed.
- Do not append anonymous mixer chains after the legacy layout. Current
  `parse_offsets()` slices extra lines away; the implementation must stop that
  from becoming silent authority.
- Accept optional labeled lines after the legacy layout. Use these exact labels:
  `MIXER_D1_UPFADER_RAW`, `MIXER_D2_UPFADER_RAW`, `MIXER_D1_LOW_RAW`,
  `MIXER_D2_LOW_RAW`, and, if filter tracking is included,
  `FILTER_D1_PARAM0`, `FILTER_D2_PARAM0`, `FILTER_D1_PARAM1`,
  `FILTER_D2_PARAM1`.
- Unknown labeled lines after the legacy layout must be ignored with a warning,
  not treated as authority.
- Anonymous trailing chain lines after the legacy layout must be ignored with a
  warning, not treated as authority.
- If any of the four required mixer labels is malformed or only partially
  present for a version, keep the legacy record valid but set all four required
  mixer fields to `None`. That makes mixer authority invalid for that version
  while preserving current direct master/play/load behavior.
- If filter labels are partially present or malformed, set all filter fields to
  `None`; do not affect mixer authority.

Exact local 7.2.11 mixer chains:

```text
MIXER_D1_UPFADER_RAW 04E16EE8 A8 458 0 2C8 0 470 30
MIXER_D2_UPFADER_RAW 04E16EE8 A8 458 0 2C8 8 470 30
MIXER_D1_LOW_RAW     04E16EE8 A8 458 0 2C8 0 460 30 38
MIXER_D2_LOW_RAW     04E16EE8 A8 458 0 2C8 8 460 30 38
```

Optional local 7.2.11 filter tracking chains:

```text
FILTER_D1_PARAM0 04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8
FILTER_D2_PARAM0 04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8
FILTER_D1_PARAM1 04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 EC
FILTER_D2_PARAM1 04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 EC
```

Tests:

- Extend `tests/test_rb_offsets.py`.
- Prove old mini records and embedded older records still parse with mixer fields
  set to `None`.
- Prove local `7.2.11` exposes the four mixer fields by name.
- Prove malformed/partial mixer labels leave mixer fields `None`.
- Prove anonymous trailing chain lines are not silently accepted as authority.
- If filter fields are included, prove they are named optional fields and cannot
  affect active-deck authority.

### Task 2 - `models.py`: mixer snapshot and event shape

Keep `DeckState` as deck/track/transport state. Do not store reader-owned mixer
fields in `DeckState`.

Add small data models in `models.py`:

- `MixerDeckReading`
  - `deck: int`
  - `upfader_raw: float`
  - `upfader_norm: float`
  - `upfader_label: str`
  - `low_raw: float`
  - `low_norm: float`
  - `low_label: str`
- `MixerAuthoritySnapshot`
  - `valid: bool`
  - `deck: read-only Mapping[int, MixerDeckReading]`
  - `updated_at: float`
  - `reason: str`
  - optional non-authority `filter` data only if filter tracking is implemented

Add `Ev.MIXER_STATE = "mixer_state"`.

Snapshot rules:

- A valid snapshot requires both Deck 1 and Deck 2 to have readable upfader and
  LOW/BASS data in range during the same reader tick.
- Missing either deck, missing either field, a null chain, an unreadable chain,
  NaN, infinity, or out-of-range raw value must produce `valid=False`.
- `reason` must be short and status-safe, for example
  `ok`, `missing_offsets`, `unreadable`, `out_of_range`, `non_finite`,
  `partial_deck_state`, or `stale`.
- The reader publishes
  `BridgeEvent(kind=Ev.MIXER_STATE, deck=0, payload={"snapshot": snapshot},
  source="rb_state")`; `StateManager` owns the latest copy.
- Because current `BridgeEvent.payload` is mutable, make mixer snapshots frozen or
  copy-on-receive. Do not let reader-owned mutable dicts/lists be shared with
  `StateManager` after enqueue.
- Add a mutation-after-enqueue regression test proving a reader-side mutation
  cannot alter the StateManager-owned mixer snapshot.

### Task 3 - `rb_state_reader.py`: finite mixer reader

Add mixer reads to `RBStateReader`; do not add a second process-memory reader.

Exact helper:

- Add a mixer-specific helper near `_follow_float()`:
  `_follow_finite_f32(task, base, ch, *, minimum, maximum) -> Optional[float]`.
- Implement it through existing `_follow_addr()`.
- Use `struct.unpack_from("<f", data)[0]`.
- Accept inclusive endpoints: `minimum <= value <= maximum`.
- Use `math.isfinite(value)` to reject NaN and infinity.
- Return `None` on null chain, unreadable chain, non-finite value, or
  out-of-range value.
- Do not change `_follow_float()` for BPM unless the implementation also updates
  every current BPM test and caller.

Exact read behavior:

- Decode only Deck 1 and Deck 2 for this feature.
- Read Deck 1/2 upfader raw with range `0.0..1023.0`.
- Read Deck 1/2 LOW/BASS raw with range `0.0..255.0`.
- Normalize after range validation: upfader `raw / 1023.0`, LOW/BASS
  `raw / 255.0`.
- Label upfader and LOW/BASS separately. Label thresholds are implementation
  policy, not RE fact; define the constants in code and cover boundary cases in
  tests.
- A reader tick with all four required values valid publishes
  `MixerAuthoritySnapshot(valid=True, reason="ok")`.
- A reader tick with any required value missing/invalid publishes one invalid
  snapshot for both decks. Do not guess from one valid deck.
- Unchanged values must still refresh `updated_at` so freshness is not tied only
  to physical knob movement.
- Preserve `RBStateReader._tick_deck()` ordering: `ANLZ_PATH` before
  `TRACK_LOADED`.
- Keep reader threads publishing events/snapshots only; do not mutate
  `DeckState`, `OutputState`, or lighting state from the reader.

Freshness:

- The exact stale threshold is implementation policy, not RE evidence.
- Put the threshold in one named constant near the resolver/StateManager wiring.
- StateManager must treat missing first snapshot or stale latest snapshot as
  invalid mixer authority and use visible fallback.

Filter tracking, if included:

- Validate finite `0.0..1.0` param0/param1 for both decks.
- Validate selected effect id `0`, `unit_channel`, vector bounds, and both-deck
  readability before reporting filter status.
- Missing/invalid filter tracking must invalidate filter status only. It must not
  invalidate active-deck mixer authority and must never affect authority.

Tests:

- Extend `tests/test_rb_state_reader.py`.
- Cover valid f32 edges `0.0`, `255.0`, and `1023.0`.
- Cover NaN, infinity, null chain, unreadable chain, and out-of-range values.
- Cover both-deck validity and partial-deck invalidation.
- Cover unchanged valid values refreshing snapshot time.

### Task 4 - `active_deck_resolver.py`: pure resolver

Add one pure module for the authority algorithm. It must have no Rekordbox reads,
queues, `StateManager`, OS2L, MIDI, serial, DMX, network, filesystem, logging
side effects, or hardware imports.

Required input model:

- current `active_deck` (`0`, `1`, or `2`; `0` means idle/no audible show deck)
- current `rb_master_deck` (`1` or `2`)
- Deck 1 playing state
- Deck 2 playing state
- Deck 1 decoded upfader raw/norm/label
- Deck 2 decoded upfader raw/norm/label
- Deck 1 decoded LOW/BASS raw/norm/label
- Deck 2 decoded LOW/BASS raw/norm/label
- mixer validity/freshness
- pending/stability state

Required output model:

- selected `active_deck` (`0`, `1`, or `2`)
- `authority_reason`
- `fallback_reason`
- pending candidate deck
- pending/stable switch state
- updated stability state for the next call

Resolver behavior:

- Implement `docs/architecture/active_deck_authority.md` exactly.
- If mixer authority is invalid or stale, return the old-RB-master fallback
  decision with `authority_reason="mixer_invalid_fallback"` and a concrete
  `fallback_reason`.
- Eligible means playing and upfader not down.
- Fader-down decks are not eligible even if bass is high.
- Paused/not-playing decks are not eligible even if fader is top.
- Exactly one eligible deck wins.
- Both eligible and exactly one top fader: top-fader deck wins.
- Both eligible, both faders top, unequal LOW/BASS: higher LOW/BASS wins.
- Both eligible, both faders top, equal/neutral LOW/BASS: hold current eligible
  active deck; otherwise use eligible `rb_master_deck`.
- Both eligible, neither fader top: hold current eligible active deck; otherwise
  use eligible `rb_master_deck`.
- No eligible deck returns `active_deck=0` with `authority_reason="idle_no_audible"`.
- Any active-deck change must pass stability. During stability wait, hold current
  active deck only while it remains playing and audible; otherwise return idle.
- Numeric thresholds, equality tolerance, and stability duration are
  implementation policy. Define them as code constants and cover them in tests.

Tests:

- Add `tests/test_active_deck_resolver.py`.
- Cover every scenario listed in `docs/architecture/active_deck_authority.md`.
- Cover invalid fallback, invalid-to-valid recovery, no-audible idle, bass-swap
  stability, and fader-down playing deck rejection.

### Task 5 - `state_manager.py`: integrate resolver without output redesign

State ownership:

- Add `OutputState.rb_master_deck: int = 1`.
- Change `OutputState.active_deck` semantics to the resolved show deck:
  `0` means idle/no audible active deck, `1` or `2` means that deck drives the
  show.
- Store latest `MixerAuthoritySnapshot` on `StateManager`, not in `DeckState`.
- Store status-facing authority fields on `OutputState` and copy them through
  `StateManager.snapshot()`:
  `active_deck_authority_reason`, `mixer_authority_valid`,
  `mixer_authority_updated_at`, and `mixer_fallback_reason`.

Deck-switch side effects:

- Extract the side-effect body of `_on_master_changed()` that currently resets
  lighting/autoloop/LED/laser/personality state (`state_manager.py:2614-2671`)
  into one helper, for example `_apply_active_deck_change(new_deck, source,
  reason)`.
- That helper must only run when the resolved show deck changes from one
  nonzero deck to another nonzero deck.
- Do not run the full deck-switch side effects when `MASTER_CHANGED` only updates
  `rb_master_deck` and the resolver holds the current show deck.
- Add an explicit idle transition path for `active_deck=0` before
  `_push_tick_inner()`, `_drive_pack_output()`, or any `deck_route(active)` call
  indexes/routes a real deck. Idle must not drive the previous deck just because
  it was previously active.
- Define all three active-deck transition classes:
  - `1/2 -> 1/2`: run the extracted deck-switch side effects once.
  - `1/2 -> 0`: clear/idle output state without routing Deck 0; reset or clear
    pack selection, lighting/autoloop pending state, laser/LED runtime intent,
    and MTC-active-deck fallback as needed so stale deck timing does not keep
    driving outputs.
  - `0 -> 1/2`: resume normal resolved-deck operation and run only the setup
    needed for a fresh show deck; do not replay stale previous-deck timing.

Event handling:

- `Ev.MIXER_STATE` updates the latest mixer snapshot and reruns the resolver.
- `Ev.MASTER_CHANGED` updates `rb_master_deck`.
- While mixer authority is valid/fresh, `Ev.MASTER_CHANGED` must not directly
  write `active_deck`; it only influences resolver tie/fallback cases.
- While mixer authority is invalid/stale, preserve old direct RB-master
  behavior as the named fallback so current bridge operation does not go dark
  just because mixer authority is missing. Legacy playing-only mirror
  auto-switches must stay gated off; invalid fallback authority may change
  `active_deck` only through the RB-master fallback path.
- OSC `/bridge/active_deck` and `/bridge/bridge_deck` remain legacy/debug
  fallback inputs only. They must not bypass valid mixer authority, must not
  independently select the show deck, and should not rewrite `rb_master_deck`
  when mixer authority is valid.

Current bypasses to remove or gate:

- Gate the stale/idle mirror auto-switch at `state_manager.py:3624-3633`.
- Gate the stop-confirmed mirror auto-switch at `state_manager.py:3772-3784`.
- Gate the active-idle mirror auto-switch at `state_manager.py:3797-3810`.
- Gate `_do_resume()` empty-deck direct write at `state_manager.py:4436-4440`.
- Each gate must say: if mixer authority is valid/fresh, do not enqueue or write
  an authority switch here; rerun the resolver instead.

Downstream behavior:

- Existing SoundSwitch, laser, LED/Govee, scripted, autoloop, BPM, beat, and
  elapsed paths keep using the resolved nonzero `active_deck`.
- When resolved `active_deck=0`, downstream output must idle/clear through
  existing idle/zero-safe paths; it must not keep sending the previous active
  deck's timing.
- Do not add per-tick INFO logs. Log only meaningful changes:
  valid-to-invalid, invalid-to-valid, active deck changed, authority reason
  changed, fallback reason changed.

Tests:

- Add `tests/test_state_manager_active_deck_authority.py` or extend the smallest
  existing StateManager test file if it already owns these helpers.
- Prove `MASTER_CHANGED` updates `rb_master_deck` without bypassing the resolver
  while mixer authority is valid.
- Prove old RB-master behavior still works while mixer authority is invalid.
- Prove valid mixer recovery returns to fader dominance.
- Prove each mirror auto-switch path cannot promote a fader-down deck while mixer
  authority is valid.
- Prove `_do_resume()` empty-deck correction cannot bypass valid mixer authority.
- Prove idle/no-audible `1/2 -> 0` does not drive the previous active deck, call
  `deck_route(0)`, or leave pack/lighting/autoloop/laser/LED state armed from
  the old show deck.
- Prove `0 -> 1/2` recovery starts the new show deck without replaying stale
  previous-deck timing.

### Task 6 - `__main__.py`: wire reader and fallback inputs

- Mixer authority must not depend on an existing direct flag being enabled. Add a
  default-on mixer authority startup decision that loads offsets for the current
  Rekordbox version and constructs `RBStateReader` when all four named mixer
  fields exist, even if `RBSS_ANLZ_DIRECT`, `RBSS_PLAY_DIRECT`,
  `RBSS_TRACK_LOAD_DIRECT`, and `RBSS_MASTER_DIRECT` are all unset/false.
- Reuse the existing `RBStateReader` instance when any current direct path is also
  enabled; do not add a second process-memory reader.
- When `RBStateReader` is constructed, enable mixer-state publication only when
  the loaded `RBOffsetVersion` has all four named mixer fields.
- Route `Ev.MIXER_STATE` through the existing event queue. Do not add a separate
  live thread or polling loop.
- Keep existing direct master readiness behavior for the old fallback path.
- Keep startup seeding conservative: direct master may seed `rb_master_deck` and
  old fallback active deck, but it is not proof of mixer authority.
- OSC `/bridge/active_deck` remains ignored while current direct master is ready
  today; after mixer authority lands, it must also be unable to bypass valid
  mixer authority.
- Add a startup wiring test proving mixer authority constructs/wires
  `RBStateReader` when the version has named mixer offsets and all existing
  direct flags are disabled.

### Task 7 - `runtime_status.py` and `StateManager.snapshot()`: separate show deck and master

Expose these fields from `StateManager.snapshot()`:

- `active_deck`: resolved show deck, `0`, `1`, or `2`
- `rb_master_deck`: current Rekordbox master deck, `1` or `2`
- `active_deck_authority_reason`
- `mixer_authority_valid`
- `mixer_authority_age_s` or `mixer_authority_updated_at`
- `mixer_fallback_reason`
- Deck 1/2 decoded upfader raw/norm/label
- Deck 1/2 decoded LOW/BASS raw/norm/label
- Optional CFX FILTER tracking/status fields only if filter tracking was implemented

Heartbeat rules:

- Heartbeat must stop reporting `master = active_deck`.
- Prefer explicit fields: `active_deck` or `show_deck`, plus `rb_master_deck`.
- If the legacy `master` field remains, it must mean `rb_master_deck` only and
  tests must prove that `master` no longer follows `active_deck`.
- The `[BEAT]` log should name both concepts clearly, for example
  `deck=<active_deck> rb_master=<rb_master_deck>`.
- Include mixer validity/fallback reason in status JSON. Keep heartbeat concise
  and throttled; do not add per-tick status spam.

Tests:

- Extend `tests/test_runtime_status.py`.
- Prove status contains separate `active_deck` and `rb_master_deck`.
- Prove heartbeat no longer conflates master/show deck.
- Prove decoded mixer labels/reasons are present when provided and safely absent
  or degraded when not provided.

### Task 8 - Docs/contracts after code implementation

Before code changes, identify the matching contracts in
`docs/agents/change_contracts.yml`:

- `rekordbox_readers` for `rb_offsets.py` and `rb_state_reader.py`.
- `core_bridge` for `models.py`, `state_manager.py`, and resolver integration.
- `runtime_commands` for `runtime_status.py` / heartbeat/status surface.
- If `active_deck_resolver.py` is added, extend `core_bridge.code_globs` and
  `key_symbols` so agent routing and drift checks own the new authority module.

After code changes, update every listed doc whose current statement would drift.
At minimum re-check:

- `docs/architecture/active_deck_authority.md`
- `docs/architecture/current_architecture.md`
- `docs/architecture/runtime_invariants.md`
- `docs/subsystems/rekordbox_readers.md`
- `docs/status/active_work_registry.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/status/support_matrix.md`
- `docs/validation/software_test_inventory.md`

Do not upgrade hardware validation status without a completed hardware validation
record.

## Part C - Invariants That MUST Still Hold

- `StateManager` remains the only writer of `DeckState`.
- Reader threads publish events/snapshots; they do not mutate deck, output, or
  lighting state directly.
- `BridgeEvent`s remain immutable once enqueued.
- `RBStateReader._tick_deck()` still enqueues `ANLZ_PATH` before `TRACK_LOADED`.
- Memory play bits do not override `DeckState.playing`.
- Direct readiness must be currently true; a flag alone is not authority.
- The 200 Hz push loop must not gain blocking I/O, process-memory scanning,
  Ghidra calls, filesystem scans, network calls, MIDI/serial/DMX calls, sleeps,
  subprocess calls, or status-provider calls.
- SoundSwitch Decks 3/4 remain routing/internal fanout details, not active-deck
  authority candidates.
- CFX FILTER remains tracking/status only and never affects active-deck authority.
- Invalid or stale mixer authority is visible and recoverable.
- Software tests do not prove SoundSwitch, laser, LED/Govee, DMX, MIDI, serial,
  Enttec, or hardware-visible behavior.

## Part D - Required Tests

Run the smallest targeted tests while developing, then run the broad software
suite before calling the implementation complete.

Required new/extended tests:

- `tests/test_rb_offsets.py`
  - named 7.2.11 mixer fields
  - old records without mixer fields still valid
  - malformed/partial mixer labels fail closed
  - anonymous trailing chain lines do not become authority
  - optional filter fields, if implemented, are non-authority
- `tests/test_rb_state_reader.py`
  - finite f32 inclusive edges `0.0`, `255.0`, `1023.0`
  - NaN, infinity, null/unreadable, and out-of-range failure
  - both-deck validity requirement
  - unchanged mixer values refreshing freshness
- `tests/test_active_deck_resolver.py`
  - every scenario in `docs/architecture/active_deck_authority.md`
  - invalid fallback
  - invalid-to-valid recovery
  - no-audible idle
  - bass-swap stability
  - fader-down playing deck rejection
- StateManager integration tests
  - `MASTER_CHANGED` updates `rb_master_deck` without bypassing resolver when
    mixer authority is valid
  - old RB-master fallback works while mixer authority is invalid
  - legacy mirror fallback has a distinct fallback reason if retained while
    mixer authority is invalid
  - mirror auto-switch paths cannot promote fader-down decks while mixer authority
    is valid
  - `_do_resume()` empty-deck correction cannot bypass resolver
  - idle/no-audible state does not drive previous active deck, route Deck 0, or
    leave stale pack/lighting/autoloop/laser/LED intent armed
  - `0 -> 1/2` recovery starts a fresh show deck without stale previous-deck timing
- `tests/test_runtime_status.py`
  - heartbeat separates show deck and `rb_master_deck`
  - status exposes mixer validity, decoded Deck 1/2 fader/BASS, authority reason,
    and fallback reason
- Filter tests, if filter tracking lands
  - filter values validate only with selected effect id `0`, correct
    `unit_channel`, vector bounds, both-deck readability, and finite values
  - filter state cannot affect authority output

Suggested implementation checks:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

## Part E - Acceptance

The runtime implementation is not complete until:

- `docs/architecture/active_deck_authority.md` remains accurate.
- `rb_offsets.py` exposes named optional mixer fields; legacy records fail
  closed for mixer authority.
- `RBStateReader` publishes valid/invalid both-deck mixer snapshots without
  reusing `_follow_float()` for mixer raw values.
- `active_deck_resolver.py` is pure and test-covered.
- `rb_master_deck` is separate from `active_deck`.
- `MASTER_CHANGED` cannot directly change `active_deck` while mixer authority is
  valid/fresh.
- Playing-only mirror auto-switch cannot bypass valid mixer authority.
- `_do_resume()` empty-deck correction cannot bypass valid mixer authority.
- Idle/no-audible `active_deck=0` is explicitly handled before any deck-index,
  pack, MTC, or `deck_route()` path can use it as a real deck.
- Mixer authority is default-on for versions with named mixer offsets, even when
  existing direct-reader flags are disabled.
- Invalid/stale mixer authority visibly falls back to old RB-master behavior.
- Recovery from invalid/stale mixer authority returns to fader dominance.
- Status/heartbeat expose separate show deck and Rekordbox master plus mixer
  validity/reasons.
- CFX FILTER, if implemented, is tracking/status only.
- Required tests and docs checks pass.
- No live restart, live sampling, bridge toggle, or hardware action was performed
  without explicit approval.

## Adversarial Self-Review Checklist

Before marking the implementation ready, try to disprove these:

- A fader-down playing deck can still steal authority through a leftover
  auto-switch path.
- `MASTER_CHANGED` still writes `active_deck` directly during valid mixer
  authority.
- `_do_resume()` still writes `active_deck` directly during valid mixer authority.
- Idle/no-audible state keeps driving the previous deck.
- `active_deck` and `rb_master_deck` are still conflated in status or heartbeat.
- One deck's missing mixer state is treated as a valid comparison.
- Raw memory thresholds are described as RE facts instead of implementation
  policy.
- Filter state affects active-deck authority.
- Decks 3/4, crossfader, trim/gain, mute, mid/high EQ, or real audio loudness
  become authority inputs.
- The push loop gained blocking process-memory, Ghidra, filesystem, network,
  MIDI, serial, DMX, sleep, subprocess, or provider work.
- The passive-verified mixer vector chain was replaced by the static
  `getMixerControl()` return adjustment without a new passive proof.
- Mixer chain lines were appended anonymously and ignored by the fixed parser
  layout.
- `_follow_float()` still rejects valid mixer endpoints.
- Mixer JSONL artifact labels are used as raw direct-master byte proof.
- Hardware validation is claimed without a completed hardware validation log.

## When You Finish Implementation

Report:

- changed files
- tests/checks run and results
- exact remaining unknowns
- whether any live/hardware validation was performed
- whether a bridge restart is needed for the running process to use the change
- operator summary: expected live behavior, unchanged behavior, status/log
  watchpoints, unvalidated hardware assumptions, and any restart/toggle gates
