---
doc_status: current
truth_level: code-verified
last_verified_commit: abe60dac
last_verified_date: 2026-07-24
validation_scope: implementation spec only — nothing here is implemented; every file:line claim re-verified at abe60dac this session; live config is READ-ONLY for the implementer (mirror + restart are operator-gated); default-OFF behind `realtime.gamma` with a flag-off byte-identity kill test
---

# Codex Implementation Spec - LED perceptual dimming (gamma LUT at the Govee realtime wire) — AWR-289

Operator-approved polish item #1 (2026-07-22 polish pack). LED brightness ramps
should FEEL linear to human eyes instead of being numerically linear. The fix is
a single per-channel lookup table (LUT) applied exactly once, at the last
possible point before the bytes leave for the strip, behind a config knob that
ships OFF.

Plain-language mechanism (why this works): the strip turns a channel value into
light roughly proportionally, but human eyes compress bright light — going from
200 to 255 barely registers, while going from 5 to 20 looks like a huge jump.
So a fade that is numerically smooth spends most of its numbers on
indistinguishable bright steps and then falls off a cliff at the dim end. The
standard cure is to bend the numbers with a power curve (`out = 255·(in/255)^γ`,
γ ≈ 2.2 to start) right before they hit the wire, so the *authored* ramp — which
every effect computes in easy linear terms — lands on the eye as an even ramp.
Everything upstream (envelopes, fades, the CFX overlay) keeps working in the
simple linear space it was written in; only the final wire bytes are bent, and
only once.

## Part A - Context & Root Cause (verified; read, do not implement)

All claims re-verified at HEAD `abe60dac` (2026-07-24) unless labeled otherwise.

- **Wire format is linear per-channel RGB 0-255.** [confirmed]
  `GoveeRealtimeTransport.build_packet` (`govee_realtime_transport.py:67-76`)
  emits header + segment count + raw R,G,B bytes + XOR checksum; `_clamp_byte`
  (`govee_realtime_transport.py:17-22`) is a plain clamp, no curve.
  `send_frame` (`govee_realtime_transport.py:93-105`) is `build_packet`'s ONLY
  production caller [confirmed by repo grep — the other callers are tests and
  `experiments/`]. `blackout()` routes through `send_frame`
  (`govee_realtime_transport.py:107-108`).
- **All dimming today is linear RGB scaling.** [confirmed]
  Renderer helpers `_clamp_channel` (`govee_frame_renderer.py:25-30`), `_lerp`
  (`:66-72`), `_scale` (`:101-106`); the CFX filter-knob overlay
  `_apply_cfx_overlay` (`govee_realtime_runner.py:36-53`) applied on the
  composed playback frame at `govee_realtime_runner.py:440`, before the
  transport send at `:446`. The device 0-100 brightness command is pinned to
  100 on activate (`govee_realtime_runner.py:423`) and 0 as the fail-dark
  backstop — it is a separate device-domain command, not part of the frame
  path.
- **No display gamma exists anywhere on the bridge output path.** [confirmed by
  grep at `abe60dac`] The only gamma in the repo is the LED room simulator's
  screen-calibration profile (`tools/led_sim_engine.py:851-856`, validated
  `:394`) — that curve models how the PHYSICAL strip looks on a MONITOR for
  preview purposes; it never touches wire bytes and is out of scope here (see
  the watchpoint in Part C).
- **Root cause of the perceptual problem:** strip light output is roughly
  proportional to the commanded value, but perceived brightness follows a
  compressive power law. A numerically linear ramp therefore looks front-loaded:
  coarse, jumpy steps at the dim end and near-invisible steps at the bright end.
  Authored fades, ember decays, and dim overlays all inherit this distortion at
  their dim tails.
- **Whether the Govee strip applies its own internal gamma: [unknown]** — this
  is hardware behavior with no repo evidence. It decides the best exponent
  (if the strip already bends the curve, the right setting is simply leaving
  this feature OFF). That is exactly why the knob ships OFF, the exponent is
  config, and activation is an operator bench look at a restart he chooses.
- **Insertion point.** The LUT goes in `send_frame` immediately after the
  existing clamp of the frame triples and before `build_packet`
  (`govee_realtime_transport.py:99-100`). This catches every frame path —
  playback frames, idle/blank frames, `blackout()` — and the XOR checksum is
  computed over the mapped bytes automatically because `build_packet` runs
  after the mapping. (Deviation from the 2026-07-22 audit, recorded: the audit
  suggested "inside `build_packet`"; applying in `send_frame` has identical
  coverage since `send_frame` is `build_packet`'s only production caller, and
  it keeps the pure static packet builder — and its probe-vector test
  `tests/test_govee_realtime_transport.py:35-45` — byte-untouched.)
- **Construction sites that must receive the knob** (both read the same
  per-target `realtime` config block, so ONE config key covers both
  processes):
  - Bridge: `__main__.py:760-772` builds the `engine_init` dict from `rt`
    (`LEDRealtimeConfig`); the frame-engine child builds the transport in
    `_make_transport` (`govee_frame_engine.py:454-461`).
  - LED pad process: `tools/led_pad_playback.py:268-279` builds
    `GoveeRealtimeTransport` directly from `target.realtime`.
  - Config model: `LEDRealtimeConfig` (`led_models.py:15-28`), built by
    `_build_realtime_config` (`led_config.py:1903-1922`), validated inside
    `_validate_target` (`led_config.py:396-430`; note `:402` returns early for
    disabled targets). Example block: `config/led_look_director.example.json`
    target `room_perimeter` → `realtime`.
- **Double-curve inventory — every place that already shapes brightness.**
  These are all INTENT-space artistic curves and must stay upstream and
  untouched; the LUT is the single display transfer, applied exactly once at
  wire-out:
  - `resolve_fade` color lerp (`govee_frame_renderer.py:75-98`) — color-only
    linear fade.
  - Effect envelopes: `_ember_env` fast-in/exp-out, sine buildup ramps,
    `_head_weights` triangle falloff, sparkle density curves — all inside
    `govee_frame_renderer.py`.
  - CFX overlay mix/dim (`govee_realtime_runner.py:36-53`).
  - `_scale`-based per-look dims (e.g. palate-reset dim in the color engine).
  - Device brightness command 0-100 (`set_brightness`,
    `govee_realtime_transport.py:84-91`) — NOT gamma'd; different unit domain,
    pinned 100/0.
  - Cloud DIY scenes (`govee_scene_adapter.py` / `govee_runtime_sender.py`) —
    rendered by Govee's cloud, no RGB frame path in the bridge; out of scope.
  Nothing in this list applies a display gamma today, so adding the LUT at the
  wire creates exactly one application point. [confirmed]
- **Frame-mirror note.** The pad's `TeeTransport`
  (`tools/led_pad_playback.py`, AWR-269) mirrors the frame handed to it — the
  inner real transport applies the LUT internally afterward. So the Lab Watch
  mirror (and the bridge runner's `_last_frame`) show INTENT-space frames while
  the wire carries gamma-mapped bytes. This is correct (the sim/watch show what
  was authored) and is documented, not changed.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Out-of-scope files/subsystems — do not touch: `state_manager.py`,
  `led_dispatch_policy.py`, `led_color_engine.py`, `govee_frame_renderer.py`,
  `govee_realtime_runner.py`, `govee_scene_adapter.py`,
  `govee_runtime_sender.py`, `tools/led_sim_engine.py`, every laser / reader /
  SoundSwitch file, and the live gitignored `config/led_look_director.json`
  (READ-ONLY; the operator mirrors and restarts).
- Behavior that must not change: with `gamma` absent or `1.0`, every wire byte,
  packet, and command is byte-identical to today (kill test). `blackout()`
  emits all-zero segment bytes at ANY gamma. The activate brightness-100 pin
  and the brightness-0 fail-dark backstop are untouched. No new I/O anywhere;
  no new threads; no new state fields.
- Expected error handling: config validation fails closed by appending to the
  `errors` list exactly like the sibling `realtime.*` checks — never clamp bad
  input and continue. The IPC init field is `.get`-defaulted on the child side
  so version skew (old frozen child, new bridge — or the reverse) degrades to
  gamma-off, never to a crash. No broad try/except, no silent fallbacks.

### Task 1 - `govee_realtime_transport.py`: LUT builder + single application point

Add a module-level pure function after `_clamp_byte`:

```python
def build_gamma_lut(gamma: float) -> tuple[int, ...] | None:
    """256-entry perceptual-dimming LUT, or None when gamma is identity.

    out = round(255 * (in/255) ** gamma), with both endpoints forced exact so
    black stays black and full brightness stays full brightness (peak/drop
    looks are never dimmed). Monotonic and <= identity for gamma > 1.
    """
    g = float(gamma)
    if g == 1.0:
        return None
    lut = [int(round(255.0 * (i / 255.0) ** g)) for i in range(256)]
    lut[0] = 0
    lut[255] = 255
    return tuple(lut)
```

`GoveeRealtimeTransport.__init__` gains a keyword parameter `gamma: float = 1.0`
(after `deactivate_pt`, before `sock`) and stores
`self._gamma_lut = build_gamma_lut(gamma)`.

In `send_frame`, immediately after the existing
`clean = [(_clamp_byte(r), _clamp_byte(g), _clamp_byte(b)) for r, g, b in rgb_list]`
line and before the `build_packet` call, insert:

```python
        lut = self._gamma_lut
        if lut is not None:
            clean = [(lut[r], lut[g], lut[b]) for r, g, b in clean]
```

Do NOT modify `build_packet`, `_clamp_byte`, `set_brightness`, or
`GoveeRealtimeDryRunTransport` (the dry-run transport sends nothing; it does
not take the kwarg). No status/observability field is added (deliberate
simplification: verification is config + tests; the runtime status surface and
its sanitizer whitelist stay untouched).

### Task 2 - `led_models.py`: config field

`LEDRealtimeConfig` (`led_models.py:15-28`) gains `gamma: float = 1.0` (place
after `fps`). Docstring/comment one-liner: absent key ⇒ 1.0 ⇒ wire bytes
byte-identical (kill test; same precedent as `F2Config.enabled`,
`led_models.py:115-121`).

### Task 3 - `led_config.py`: parse + validation

In `_build_realtime_config` (`led_config.py:1903-1922`) add
`gamma=float(data.get("gamma", 1.0)),` beside `fps` (mirror the sibling
direct-cast style).

In `_validate_target`'s realtime section, after the `fps` check
(`led_config.py:416-418`), add:

```python
    gamma = realtime.get("gamma", 1.0)
    if isinstance(gamma, bool) or not isinstance(gamma, (int, float)) or not (
        1.0 <= float(gamma) <= 4.0
    ):
        errors.append(f"{prefix} realtime.gamma must be a number between 1.0 and 4.0")
```

Range rationale (pinned; move only by spec amendment): γ < 1.0 would BRIGHTEN
mid-tones (the opposite correction — if the strip turns out to already bend the
curve internally, the remedy is leaving the knob at 1.0/absent, never γ < 1);
γ > 4.0 is far beyond any plausible display transfer.

### Task 4 - `__main__.py`: one init key

In the `engine_init` dict (`__main__.py:760-772`) add `"gamma": rt.gamma,`
beside the other `rt.*` fields. Nothing else in `__main__.py` changes. (This
one-line edit crosses into the `core_bridge` contract's `code_globs`; see
Part E for the contract handling.)

### Task 5 - `govee_frame_engine.py`: child-side plumb

In `_make_transport` (`govee_frame_engine.py:454-461`), the real-transport
branch gains `gamma=float(init.get("gamma", 1.0))`. `.get` with a default is
REQUIRED (version-skew safety — same law as the CFX wire fields in the
playbook); the dry-run branch is untouched.

### Task 6 - `tools/led_pad_playback.py`: pad-side plumb

In the real-transport constructor call (`tools/led_pad_playback.py:270-278`)
add `gamma=rt.gamma,`. The dry-run branch is untouched. This gives the pad's
live preview the same wire transfer as the bridge from the same config key —
no separate pad knob.

### Task 7 - `config/led_look_director.example.json`: example key

Add `"gamma": 1.0` to the `room_perimeter` target's `realtime` block (beside
`fps`). The example ships OFF; 2.2 is the documented starting point the
operator can try in the live copy. Do not add the key to the disabled
`strip_light_mirror` target.

### Task 8 - Tests

Implement Part D exactly.

## Part C - Invariants That MUST Still Hold (live safety)

- **Default-off is absolute.** An un-mirrored live config has no `gamma` key ⇒
  `LEDRealtimeConfig.gamma == 1.0` ⇒ `build_gamma_lut` returns `None` ⇒
  `send_frame` takes the `lut is None` fast path ⇒ every datagram is
  byte-identical to today. Activation belongs to the operator: mirror
  `"gamma": 2.2` into the live config's realtime block and restart via the
  menubar at a moment he chooses. Rollback is deleting the key (or setting
  1.0) + restart — no code change, no git action.
- **STANDING OPERATOR LAW — no drop look is ever dim; peak/drop brightness is
  never reduced.** This feature corrects the CURVE's fidelity at already-dim
  levels; it must never dim a peak. Enforced structurally and by test:
  `lut[255] == 255` and `lut[0] == 0` are FORCED exact in the builder, so
  full-intensity pixels (drop hits, strobes at peak, full-white flashes) are
  byte-unchanged at ANY allowed gamma; the LUT is monotonic and `lut[i] <= i`
  everywhere (it only ever dims mid-tones, never brightens, never clips a
  peak). Test-pinned across the whole allowed exponent range (Part D test 3).
  Stated plainly: mid-intensity values DO get numerically dimmer — that is the
  correction itself, redistributing steps so dim ramps read evenly — but the
  top of every look is untouched. If a drop look nevertheless READS dimmer in
  the room (because its body lives in mid-tones), that is the operator's veto:
  turn the knob off; the law's hard guarantee (peaks exact) still held.
- **Live-mixing walk-through.** Config is read at process start only — nothing
  changes mid-mix, ever. Every blackout path (emergency, manual, tactical
  pre-drop, idle) emits zero frames → `lut[0] == 0` → blackout is
  byte-identical even with gamma on; the brightness-0 fail-dark backstop and
  the activate brightness-100 pin bypass the LUT entirely (different command).
  The AWR-145 keepalive, AWR-150 cloud staging/yield, and AWR-146 respawn
  replay paths carry commands and frames through the same `send_frame` — no
  path bypasses the single application point, and none gains new failure
  modes (the LUT cannot raise: it is a tuple index on already-clamped 0-255
  ints).
- **Hot-path cost.** Zero when off (one `is None` check per frame). When on:
  three tuple-index lookups per pixel on the frame-engine child's own frame
  thread (60 fps × 60 segments × 3 ≈ 11k lookups/s — negligible, and in the
  child process, not the bridge). The StateManager 200 Hz push loop gains
  nothing — the only bridge-process edit is one static key in a startup dict
  (`__main__.py`). No blocking I/O is added anywhere.
- **No pending state, no mode transitions.** The LUT is a stateless pure
  per-frame mapping constructed once at transport init. There are no new
  fields to clean up on idle/scripted/autoloop/blackout transitions and no
  interaction with any pending-state machinery (checked against: CFX overlay
  tuple, keepalive yield, cloud stage pending, dispatch retry slots — all
  upstream and orthogonal).
- **Version skew fails safe both directions.** Old frame-engine child (e.g. a
  frozen USB bundle) + new bridge: the extra `gamma` init key is ignored by
  key-reads; frames stay intent-space (feature silently off — safe). New child
  + old init: `.get` default 1.0 (off). Never a crash, never an unexpected
  transfer.
- **Sim watchpoint (docs-only, no code).** The room simulator's
  screen-matching profile has its own gamma (`tools/led_sim_engine.py:851-856`)
  calibrated against the strip's CURRENT (linear-wire) behavior. When the
  operator enables wire gamma, the physical room changes while the sim's
  calibration still models the old response — the sim may need an operator
  re-calibration pass. Named here and in the card so nobody "fixes" the sim by
  adding a second wire curve.

## Part D - Tests

All pure / fake-socket; no on-disk config, no subprocess, no network.

In `tests/test_govee_realtime_transport.py` (reuse the existing `_FakeSocket`
harness, `tests/test_govee_realtime_transport.py:17-31`):

1. **Identity:** `build_gamma_lut(1.0) is None`; constructing the transport
   with no `gamma` kwarg leaves `_gamma_lut is None`.
2. **LUT shape at 2.2:** length 256; `lut[0] == 0`; `lut[255] == 255`;
   monotonic non-decreasing; `lut[i] <= i` for all i; and the pinned
   perceptual midpoint `lut[128] == 56` (formula-derived:
   `round(255·(128/255)^2.2)`; exact, no tolerance — the formula is specified,
   so the value is deterministic; NO-TUNING: this pin moves only by spec
   amendment).
3. **Operator-law sweep:** for gamma in (1.5, 2.2, 3.0, 4.0): endpoints exact,
   monotonic, `lut[i] <= i` — peaks never reduced, mids never brightened, at
   every allowed exponent.
4. **Flag-off byte-identity kill test:** two transports on fake sockets — one
   default-constructed, one with explicit `gamma=1.0` — sending the same frame
   produce byte-identical datagrams, and that payload equals the pre-change
   expectation (decode the razer `pt` base64 and compare against the existing
   probe-vector packet bytes for the same input).
5. **Wire application:** transport with `gamma=2.2`, send a frame with known
   mixed values (include 0, 128, 255); decode the sent JSON → base64 `pt` →
   packet; assert packet equals
   `build_packet(header, [(lut[r], lut[g], lut[b]) …])` — proving mapped bytes
   AND a checksum computed over the mapped bytes. Assert the 0-valued and
   255-valued channels are unchanged. `blackout()` on the same transport still
   emits all-zero segment bytes.

In `tests/test_led_config.py`:

6. `gamma` absent → parsed `LEDRealtimeConfig.gamma == 1.0`; explicit `2.2`
   parses; each of `"x"`, `true`, `0.9`, `4.5` produces the
   `realtime.gamma must be a number between 1.0 and 4.0` validation error; the
   shipped example config still loads clean.

In `tests/test_govee_frame_engine.py`:

7. `_make_transport` with an init dict LACKING `gamma` → real transport with
   `_gamma_lut is None` (version-skew default); with `"gamma": 2.2` → LUT
   present. Dry-run branch unaffected.

In `tests/test_led_pad_playback.py`:

8. A pad playback built from a config whose realtime block carries
   `gamma: 2.2` constructs its inner real transport with the LUT present (or,
   matching that file's existing style, assert the constructor receives
   `gamma=2.2`).

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-8 implemented exactly; no out-of-scope file touched; live config
      untouched.
- [ ] New tests green plus targeted suites:
      `python3 -m unittest tests.test_govee_realtime_transport tests.test_led_config tests.test_govee_frame_engine tests.test_led_pad_playback`
      and the contract-listed
      `python3 -m unittest tests.test_led_state_manager tests.test_led_identity_v2`;
      `python3 -m unittest discover tests` when practical (compare any reds
      against the documented pre-existing baseline before attributing).
- [ ] Single-application-point audit: `grep -rn "gamma" *.py` at the finish
      shows wire-path gamma ONLY in `govee_realtime_transport.py` (config/
      plumb references excepted; `tools/led_sim_engine.py` is the sim's screen
      profile, not wire).
- [ ] NO-TUNING clause (restated in three places by design — here, Part C's
      operator law, Part D test 2): the [1.0, 4.0] validation range, the 2.2
      documented starting exponent, and the `lut[128] == 56` midpoint pin move
      only by amendment to this spec.
- [ ] Contract compliance (`led_govee` in `docs/agents/change_contracts.yml`) —
      apply these doc updates as text:
      - `docs/subsystems/led_govee.md`: new AWR-289 section (perceptual
        dimming gamma LUT: default-off `realtime.gamma`, single wire-out
        application in `send_frame`, endpoints-exact operator-law guarantee,
        the double-curve rule "the LUT is the only display transfer; renderer/
        runner curves are intent-space", the sim-recalibration watchpoint, and
        the mirror-shows-intent note) + append the round to the frontmatter
        `validation_scope`.
      - `docs/status/feature_status_matrix.md`: add row — LED perceptual
        dimming (gamma LUT), `implemented` + `software-tested`, default-off,
        `hardware-unvalidated`.
      - `docs/status/support_matrix.md` and `docs/status/validation_matrix.md`:
        extend the LED/Govee realtime rows' notes with the default-off gamma
        knob (software-only proof; room-visible correctness = operator bench
        look).
      - `docs/validation/hardware_validation_log.md`: add the pending-
        validation entry (perceptual dimming curve — needs operator eyes at a
        chosen restart; exponent choice is the bench outcome).
      - `docs/validation/software_test_inventory.md`: append an AWR-289
        sentence to the LED/Govee row naming the new test cases (LUT shape/
        sweep, kill test, wire application, config validation, child + pad
        plumb).
      - `docs/status/active_work_registry.md`: flip the AWR-289 row from
        spec-authored to implemented/software-tested with the verification
        anchor.
      - `docs/agents/task_playbooks/change_led_govee_behavior.md`: add one
        implementation note — display gamma is applied exactly once, in
        `GoveeRealtimeTransport.send_frame`; never add a second curve in the
        renderer, runner, or sim (workflow guidance change, so this file is in
        scope per the contract).
      - `docs/architecture/palette_control_authority.md`,
        `docs/plans/active/streamdeck_palette_control_design_spec.md`,
        `docs/plans/active/true_drop_section_cycling_spec_2026_07_15.md`: no
        content impact (this change touches no palette, Stream Deck, or
        section behavior) — re-verify that statement against the diff and
        leave them unchanged; record the no-change finding in the completion
        report.
      - `core_bridge` contract (crossed by the one-key `__main__.py` edit):
        `docs/subsystems/core_bridge.md`, `current_architecture.md`, and
        `runtime_invariants.md` do not describe `engine_init` fields
        [confirmed by grep at `abe60dac`] — no content change; run that
        contract's checks and record the no-change finding.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`,
      `python3 tools/check_agent_contracts.py`,
      `python3 tools/check_docs_drift.py`, `python3 tools/check_ui_jargon.py`.
- [ ] Status language stays `implemented` / `software-tested` /
      `hardware-unvalidated` — SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## When You Finish

Report: changed files, tests/checks run with results, the two no-change
contract findings, and any deviation from this spec with its reason.

Plain-language operator summary (include verbatim-adapted):
- Expected live behavior: NOTHING changes at the next restart — the feature
  ships off. When you want to try it, add `"gamma": 2.2` inside
  `"realtime": {...}` in your live `config/led_look_director.json` and restart
  from the menubar. Dim tails (ember fades, breakdown dims, the filter-knob
  darkening) should then ramp smoothly instead of stair-stepping; full-blast
  moments (drops, strobes at peak) are mathematically untouched.
- Watchpoints: the overall room may read a touch dimmer in mid-intensity looks
  — that is the curve redistributing steps, and if a drop look's body feels
  dimmer, veto by removing the key and restarting. The on-screen room
  simulator was calibrated against the old behavior; if you keep gamma on and
  the sim stops matching the room, its screen-matching profile needs a
  recalibration pass (say so — do not let anyone add a second curve to the
  sim wire path).
- Unverified hardware assumption: whether the strip itself already bends the
  curve internally is unknown — if it does, the honest setting is leaving this
  off. Your eyes at the bench decide the exponent; 2.2 is the starting point,
  valid range 1.0-4.0.
- Rollback: delete the key (or set 1.0) + menubar restart. After any restart:
  `pgrep -f rb_ss_bridge_v2 | wc -l` must be 1.
