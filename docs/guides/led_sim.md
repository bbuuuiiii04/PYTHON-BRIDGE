---
doc_status: current
truth_level: software-tested
last_verified_commit: 6eb441d
last_verified_date: 2026-07-15
validation_scope: >
  H612D LED Studio (AWR-196 + AWR-244 room-view + AWR-246 layout library):
  offline production-runner frame composition, room polyline layout with
  arc-length LED placement, named layouts library (schema v2) with Home/Venue
  style isolation, picker Use/Delete targeting selected (refuse active/last
  via error banner; in-page confirm dialog — not window.confirm), Pad|Lab|Sim
  cross-nav + stage room-size label (AWR-248), mid-width shell hardening
  (AWR-249: topbar/nav, ≥900 desktop grid, HUD below canvas, label clamp),
  Use persists active_layout immediately without leaking unsaved knobs
  (AWR-250), perimeter/snake/custom presets, layout and
  calibration lockers, timestamp-held playback, calibration sequence v2,
  profile evidence guards, the local web service, and AWR-258 data-integrity
  (stale-write 409 via base_mtime, rotating .bak-* keep-5, refuse save while
  profile_error, beforeunload when dirty) are software-tested.
  Optics (glow/bleed/gamma) remain uncalibrated assumptions. Generated timing
  uses an ideal grid. Device color, PWM, latency, physical response, packet
  delivery, and hardware cadence remain unmeasured; SOFTWARE-VALIDATED ONLY /
  HARDWARE-UNVALIDATED.
---

# H612D LED Studio

This local tool shows what the bridge asks the Govee H612D to do. It models the
known fixture shape: **60 controllable RGB segments, six physical LEDs per
segment, 360 LEDs total, 49.2 ft / 14,996.16 mm**. Two 7.5 m halves meet at a
**center junction / control box** (arc-length midpoint = 7498.08 mm, segment
29|30). Addressing stays one linear 60-segment strip through that junction.

**AWR-244** adds a default **room view**: the strip is a polyline in true room
millimetres. LED pitch is fixed (**41.656 mm/LED**, ~250 mm/segment). Distances
along the path are absolute — the drawing is never stretched to fit the strip.
Path longer than 49.2 ft → strip ends there; leftover path is a dashed guide.
Path shorter → live shortfall warning (`Path … / Strip … — … unplaced`).
Junction is always at absolute **24.6 ft / 7498.08 mm**. A **Strip** toggle keeps
the old 6×10 bench grid for command inspection.

Round 3 rebuilds the page as a **lighting-console shell**: stage-first room
canvas, collapsible right sidecar (Play / Layout / Calibrate tabs), bottom
transport, layout and calibration lockers, and Archivo + mono numeric chrome.
Round 4 polishes the lockers (persist + stage padlock chip), the phone bottom
sheet (zero page scroll), tablist semantics, and contrast.

**AWR-248** adds the shared **Pad | Lab | Sim** route tabs in the top bar
(plain links: pad `:8766`, lab `:8766/lab`, sim `:8767` — canonical defaults)
and a stage **room-size** label near the bottom wall of the room drawing
(e.g. `17.1 × 7.5 ft`, lowest label priority). Clicking it opens the Layout
tab and focuses Room width.

**AWR-249** hardens mid-width shell layout (≈900–1280): topbar owns brand+nav
without clipping; desktop stage+sidecar holds from ≥900px (sidecar ≥300px);
HUD text lives in a strip **below** the canvas (never over the room); short
stages hide provenance chips into the `?` help; tick/room labels clamp inside
the canvas. Layout sweep: `node tools/led_sim_layout_sweep.mjs`
(playwright-core + system Chrome).

Each group of six dots receives one RGB command because the H612D exposes 60
groups, not 360 separately controllable pixels. Screen optics (gamma, gains,
glow, bleed) are still uncalibrated assumptions.

## What is exact today

The studio is fixed to the supplied H612D control shape: 60 RGB command
segments, each displayed as six matching emitters. It rejects replay files with
any other segment count instead of stretching or guessing.

For a **Production effect**, the server drives the real
`GoveeRealtimeRunner` offline with a deterministic beat clock and replaces its
network transport with an in-memory collector. Production effect rendering,
runner fades, strobe shaping, and frame composition are therefore executed by
the Python production classes, not copied into JavaScript. The result is labeled
`production_runner_offline`.

For a **Saved look**, the same path starts with the effect and parameters
read from the current look config. Those parameters are labeled
`pre_runtime_injection`: a running bridge can still inject per-frame color or
other live state before it reaches the runner. This source is useful for
authoring the configured base, but it is not a recording of a final live
`EffectSpec`.

Generated frames use an explicit ideal clock and are labeled `ideal_grid`.
That makes repeatable offline comparison possible; it does **not** reproduce
macOS scheduling jitter, network timing, or controller timing.

Recorded frames keep their original `t_ms` timestamps. Playback uses
sample-and-hold: a frame remains visible until the next timestamp. The browser
does not invent in-between frames. A header `duration_ms` preserves the final
hold exactly. Legacy files without it receive a clearly labeled one-frame
duration estimate. The browser's **DRAW**, **RAF**, and **MISSED** readouts report
browser drawing health, not Govee hardware health.

The two badges over the fixture state the frame source and timing source. The
calibration badge describes only the saved evidence state. With the committed
profile it reads `Colors not calibrated yet`, so the identity transfer is visibly an assumption.

## Room layout (AWR-244 + AWR-246 library)

**AWR-246** stores multiple named room layouts in one profile (Home vs Venue
rooms differ). Schema **v2** fields:

| Field | Meaning |
| --- | --- |
| `layouts` | Object of 1–24 named entries. Each name is 1–40 characters, unique. |
| `active_layout` | Name of the layout currently on the stage. |
| `layouts[name].preset` | `perimeter`, `snake`, or `custom` |
| `layouts[name].points_mm` | Ordered polyline corners in that layout's room coordinates (≥2) |
| `layouts[name].flip_chain` | When true, segment 0 is the other end of the path |
| `layouts[name].room_mm` | `[width, height]` for that layout (default `[5216, 2284]`) |
| `layouts[name].layout_locked` | Disables vertex drag / room-size / presets for that layout only |

Top-level `calibration_locked` stays global (Calibrate tab). Layout lock lives
**inside** each layout entry so Home and Venue can lock independently.

`layout_led_positions` / the JS mirror always resolve the **active** layout.
`validate_profile` accepts both schema v1 (single top-level `layout` +
`room_mm` + `layout_locked`) and schema v2; garbage libraries (empty, missing
active, dangling active, bad names, >24) are rejected. Loading a v1 profile
auto-wraps it as `layouts={"Home": …}` + `active_layout="Home"`. The next
**Save** writes schema v2 and drops the old top-level keys.

Legacy keys (`corner_segments`, `start_corner`, `direction`, wash fields) are
accepted and ignored. Points beyond the room (±2 mm tolerance) emit a soft
**warning** via `profile_warnings()` — saves still succeed so edge dragging
stays fluid.

Presets:

- **Perimeter** — rectangle loop whose path length equals the strip when the
  room perimeter is ≥ 49.2 ft. For the operator room (2×(5216+2284)=15000 mm)
  the bottom gap is the real **3.84 mm** shortfall; junction at top-center.
  When the gap is wider than the bottom wall (very large rooms), the path
  clamps to a corner-to-corner U so coordinates never leave `[0, room]`.
- **Snake** — classic S: exactly 3 horizontal runs + 2 vertical connectors,
  lengths solved so total = 14996.16 mm. The absolute junction (24.6 ft) falls
  on the middle run for the operator room; the card does not claim a corner.
- **Custom** — current points, freely editable on the canvas.

**Chain direction.** On the real room hang (∩ / perimeter, junction top-center),
the post-drop comet chase always starts on the **left** wall (operator-observed
2026-07-15). That matches `flip_chain: false` with the default perimeter point
order (start bottom-center → bottom-left → up the left wall → junction → right
wall → bottom-right). Reverse direction only when the physical hang is the opposite
way; geometry itself does not change.

The Python engine function `layout_led_positions(profile)` is the tested
reference (fixed pitch, absolute junction, truncation/shortfall). `ledsim-view.js`
mirrors it. LED screen positions are cached per layout/resize, not recomputed
every frame. UI lengths are **feet primary** with metric secondary
(e.g. `49.2 ft · 15.0 m`); segment ticks every 10 show true distance (8.2 ft),
except the junction arc (segment 30) where the tick is suppressed under the
control-box label.

The Layout tab opens with a **layout slot picker** (select + Use / Save as… /
Rename / Delete). Selecting a slot **previews** that layout on the stage immediately
(read-only ghost: corners visible, drag/presets/room fields/Reverse/Reset disabled,
hint “previewing — press Use to activate & edit”). Editing tools bind only to the
**active** layout — Use activates and persists. **Use** writes `active_layout` to
disk immediately (GET the saved profile → set the pointer → POST). Unsaved local
geometry or calibration knob edits stay local and are not committed by Use —
**Save changes** still owns geometry/calibration. If the selected name exists only
in the browser, Use asks you to Save changes first. **Save as / Rename / Delete**
also persist to disk in the same action (library-structure ops are immediate;
geometry edits remain explicit-Save). Save as duplicates the active entry (prompt
prefilled `Copy of <name>`). Delete targets the **selected** slot: it refuses the
last layout and refuses the active layout, both via the error banner — select a
non-active slot, then Delete. Confirm uses the same in-page dialog pattern as
Save as (not `window.confirm`, which automation silently dismisses). On confirm,
the slot leaves the picker and is removed from disk immediately. Room W/H,
presets, and the editor operate on the active layout only. The dimension bar is
unchanged. Preset cards, drag handles (≥32 px), double-click / long-press vertex
edit, flip chain, reset, bounded undo (up to 20, Cmd/Ctrl-Z on the Layout tab),
and the per-layout locker still apply.
**Save changes** (formerly “Save layout”) persists geometry/calibration via the
existing validated profile POST. Unsaved badges are scoped: layout edits do not
light the calibration badge, and vice versa. After Use, Lab’s Room preview picks
up the new active layout on the next Preview click or Room toggle (AWR-250) — no
manual reload. AWR-251 journey: `tools/awr251_save_story_journey.mjs`.

**Data integrity (AWR-258).** Full-profile Save carries the `base_mtime` from the
load this tab edited; a mismatch returns HTTP 409 `stale_profile` so a stale tab
cannot delete another layout. Every successful overwrite writes a rotating
`.bak-*` snapshot (keep 5). While `profile_error` is set (broken on-disk file →
fallback example), Save is refused so the example can never overwrite the real
file. Closing/reloading a dirty Sim tab prompts via `beforeunload`.

## What is not exact yet

The capture boundary is before the network and physical controller. The studio
does not yet know or prove:

- whether every packet reaches the controller, or when it arrives;
- controller buffering, dropped/late-frame behavior, PWM, or refresh scanning;
- the H612D's measured RGB transfer, low-level cutoff, peak brightness, or
  mixed-color behavior;
- measured latency, color transition time, or phone/camera/display color error;
- scheduling jitter from a running bridge under real system load;
- that the room polyline matches the operator's real hang (spatial calibration
  remains unmeasured until he signs it off).

The current screen model is intentionally small: one gamma value, three channel
gains, one brightness value, a three-tap neighbor bleed, one latency offset, and
an optional single slew constant. Real evidence may require a per-channel lookup
table, load-dependent brightness, a cutoff/dead-zone model, asymmetric color
mixing, or a multi-stage temporal model. The committed profile is an identity
starting point, not a hardware measurement. A convincing-looking screen is not
validation, and 100% physical parity cannot honestly be claimed yet.

## Start it

```bash
python3 -m tools.led_sim_web
python3 -m tools.led_sim_web --port 8767 --profile config/led_sim_profile.json
```

Open `http://127.0.0.1:8767`. The server listens on loopback only. The default
saved profile is `config/led_sim_profile.json`, which is gitignored. If it does
not exist, the committed example is loaded without writing anything.

## Author mode

Choose a source and press its render button:

- **Saved look** reads the current look config,
  including its stable seed, base effect parameters, sync mode, and beat
  division, then uses the real runner offline.
- **Production effect** runs an effect through the same offline runner capture.
- **Lab draft** uses the Template Lab preview path and is labeled as a lab
  pipeline, not a production-runner result.
- **Recorded frames** loads frames-JSONL from this repo or the system temp
  directory.

The transport supports play/pause, loop, exact-frame scrubbing, left/right
frame stepping, Space to play or pause, **L** for labels, arrow nudge of a
selected vertex (10 mm, Shift = 100 mm) when layout is unlocked, and a **?**
shortcuts popover. On phones the sidecar becomes a bottom sheet; the stage
stays first.

## Calibrate mode

These deterministic sequences are generated offline. Selecting one does not
send it to the strip. Sequence results include the version
`h612d-cal-v2` and a SHA-256 hash of the exact generated payload.

| Sequence | Measurement purpose |
| --- | --- |
| Segment map | Walks segments 00 through 59 at command levels 16, 64, and 255 with black gaps. Intended to measure order, direction, group boundaries, low-level cutoff, and whether all six emitters in a group behave together. |
| Color response | Exercises dense near-black through full-scale RGB and white ramps plus cyan, magenta, yellow, orange, and violet. Every patch runs at isolated, alternating-segment, and full-strip loads to reveal transfer and load-dependent dimming. |
| Timing response | Runs three color-coded passes of 256 uniquely identifiable counter frames. Every counter frame keeps exactly 28 segments lit, then short holds and one-/two-frame chases follow. This lets a later sender log be matched to captured video while minimizing brightness changes between codes. |

Static white, red, green, blue, gray-50, and segment-0 frames are also
available.

### Capture protocol for the first real measurement

No color checker is required for a first **relative** profile. For useful phone
evidence:

1. Put the phone on a tripod and keep one lens, distance, angle, framing, and
   room-light state for the entire run.
2. Lock exposure, shutter, ISO, white balance, focus, resolution, and frame rate
   wherever the phone allows it. Disable HDR, Night mode, automatic frame-rate
   changes, stabilization, and automatic lens switching where possible. The
   exact controls depend on the phone model, so the model must be recorded.
3. Keep every original camera file. Do not send it through social media, chat,
   or any service that recompresses or changes frame timing.
4. Run the timing sequence at requested rates 10, 20, 30, 40, and 60 FPS, three
   times each. Record once in a locked normal-video mode and again at the
   phone's highest trustworthy slow-motion mode.
5. Run the segment and color sequences without changing the locked camera or
   room setup. The color sequence holds each patch long enough for steady-frame
   sampling.
6. The future live sender must log, for every uniquely coded frame, its sequence
   version/hash, code, monotonic attempt time, and transport success/failure.
7. Record H612D firmware, phone model, camera settings, capture date, and any
   remaining unknowns. SHA-256 hash the untouched capture and the exact sequence.

A phone can establish repeatability, relative channel response, visible cutoff,
relative timing, and many dropped/held-frame patterns. It cannot establish
absolute colorimetry, luminance, or camera-independent perception. Those need a
colorimeter or spectrometer, a characterized laptop display, and ideally a
photodiode plus a shared command clock for timing/PWM proof.

Actual strip capture is a separate, explicit live operation. Before any future
sender contacts the H612D, the operator must approve the exact phrase:
`LIVE H612D CALIBRATION APPROVED`. Stopping or restarting the bridge requires a
separate approval. The current studio contains no hardware sender.

## Device profile

| Field | Meaning |
| --- | --- |
| `layouts` / `active_layout` | Named room-layout library (schema v2; see Room layout). |
| `calibration_locked` | Global Calibrate-tab edit lock. |
| `gamma` | Fitted command-value to visible-level curve. |
| `white_point` | Fitted red, green, and blue channel gains. |
| `brightness` | Fitted overall display level. |
| `glow_radius`, `glow_gain` | Screen-only visualization of one physical emitter's halo. |
| `bleed` | Fitted light spill into adjacent segments; endpoints never wrap into each other. |
| `fps` | Requested offline runner and playback cadence. Default 60; not a measured H612D refresh claim. |
| `latency_ms` | Fitted display offset. Default zero is an assumption. |
| `hold_mode` | `zoh` holds exact frames; `slew` applies a fitted transition response. |
| `slew_ms` | Fitted transition constant. Slew is ignored while `calibration_status` is `unmeasured`. |
| `calibration_domains` | Separate `color`, `timing`, and `spatial` evidence states. |
| `calibration_status` | Derived whole-profile state: all unmeasured → `unmeasured`; all measured → `measured`; every mixed/relative case → `relative`. |
| `calibration_evidence` | Sequence/capture hashes, firmware, phone and camera settings, date, measured fields, fit residuals, and remaining unknowns. Absolute `measured` status also requires a named reference instrument. |

The server refuses to save `relative` or `measured` status without its required
evidence. Editing any transfer or timing control in the UI resets all domains to
`unmeasured` and clears old evidence so stale measurements cannot be carried
forward silently. Slew is used only when both the whole profile and timing
domain are relative or measured.

Old schema-v1 profiles (top-level `layout` / `room_mm` / `layout_locked`) load
as a single `Home` library entry in memory. They are rewritten to schema v2 on
the next **Save**.

## Frames-JSONL

Line 1 is a header. Every later line carries one 60-segment frame and its
nondecreasing timestamp:

```json
{"v":1,"kind":"header","fps":60,"segments":60,"duration_ms":8000,"meta":{"name":"beat_chase","frame_source":"production_runner_offline","timing_source":"ideal_grid"}}
{"v":1,"t_ms":0,"frame":[[255,0,0],[0,0,0]]}
```

The shortened frame above is illustrative; a valid H612D line contains exactly
60 RGB triples. Generate an offline production-runner composition without
starting the web server:

```bash
python3 -m tools.led_sim_engine render-jsonl --name beat_chase \
  --out /tmp/chase.jsonl --fps 60 --duration-s 8 --bpm 128
```

## View seam

`tools/led_sim_assets/ledsim-view.js` is a drawing-only ES module:

```js
createLedSimView(canvas, profile, options?) -> {
  renderFrame(frame), setProfile(profile),
  setViewMode("room"|"strip"), setLabelsVisible(bool), setEditing(bool),
  hitTestVertex, hitTestEdge, canvasToMm, mmToCanvas, destroy()
}
layoutLedPositions(profile)  // pure; mirrors led_sim_engine.layout_led_positions
```

`options` defaults to `{}` (the sim page passes nothing, so its view is unchanged).
`{presentation: true}` (AWR-253, used by the Lab room preview) draws only walls, path,
LEDs, the junction marker + label, and start/end markers — it skips the editor chrome
(segment ticks, boundary/room-size labels, vertex handles, unplaced/excess warnings).

It does not fetch, save, or send frames. The Python engine contains the tested
reference transfer, linear-bleed, and layout calculations mirrored by the view.

## Hard lines and checks

- No Govee UDP, discovery, cloud, bridge-runtime, subprocess, or non-loopback
  network contact.
- POST requests require a local Host header and JSON content type.
- Reads the LED look config; writes only the chosen simulator profile, and only
  when **Save** is pressed after validation.
- Matching command frames do not prove device receipt or visible parity.
- `production_runner_offline` does not mean a live bridge capture, and
  `ideal_grid` does not mean measured FPS parity.
- Configured-look parameters are read before live runtime injection.
- Six displayed LEDs per segment are a control-group model, not six individual
  commands.
- No new pad-lane imports (AWR-193 fence). Pad/lab integration is round 2.

Focused checks:

```bash
python3 -m unittest discover tests -p "test_led_sim*"
```

That command is the software proof for the offline studio; no H612D hardware
was exercised. Optics remain uncalibrated.
