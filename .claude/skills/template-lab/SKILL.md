---
name: template-lab
description: Use when Brandon asks for a new LED cue/template or wants to tune one — the AI-assisted flow for creating draft Govee renders in Template Lab, playing them live with placeholder colors, iterating on Brandon's feedback, and promoting accepted drafts into govee_frame_renderer.py via tests + contracts. Not for laser or SoundSwitch work.
---

# Template Lab — agent workflow

## 0. Ground rules (live safety first)
- Ownership first: check `GET /api/runtime_status` before any playback. If the bridge owns the
  LEDs (bridge status fresh <5s), ask Brandon before takeover — the pad UI takeover button is
  his call, not yours.
- STROBE — you are the only gate. Production strobe validation never fires for lab scenes
  (`lab_*` names cannot be in `REALTIME_STROBE_EFFECTS`; the check short-circuits). If a draft
  flashes: say so before the first play, stay at or under the house ceiling (the renderer's
  16th-note gate, ≤50% duty), and never leave it playing unattended.
- Never edit `govee_frame_renderer.py`, `led_config.py`, or any bridge module during lab
  iteration. Lab code lives ONLY in `config/led_lab/effects_lab.py`. Never touch
  `GOVEE_API_KEY`, device IDs, or live config. Never commit `config/led_lab/`.
- Label claims: rendered-in-lab ≠ validated-on-hardware ≠ show-ready. Use §10 status words.

## 1. Interview Brandon (short, concrete)
Ask at most: (1) which moment (groove/buildup/drop/post-drop/breakdown/ambient)? (2) what does
it look like in one sentence (object + motion + energy)? (3) nearest existing render (play 1-2
references from the pad if unsure)? (4) beat relationship (per-beat hits, N-beat cycle,
continuous)? (5) white accents (slot 5) or palette-only?
Translate to renderer knobs before coding: cycle length → `cue_beats`/`duration_beats`; speed →
`travel_beats`; object size → `width`/`trail_beats`; re-hit feel → `sync_mode` + `beat_division`.
Confirm the sentence back before writing code.

## 2. How the lab works (mechanics)
- Server: LED Pad web on `:8766`, lab UI at `/lab`. Agent API: `GET /api/lab/list`,
  `/api/runtime_status`; `POST /api/lab/save` (draft fields), `/api/lab/reload` (syntax +
  registration check — never touches lights; use after every edit), `/api/lab/play`
  `{"name", "params", "cue_beats", "takeover"}`, `/api/lab/update` `{"name", "params"}`,
  `/api/lab/switch` `{"name"}` (seamless swap to another lab draft while one plays — the beat
  keeps running), `/api/lab/preview` `{"name", "params"?, "beats"?, "bpm"?}`, `/api/stop`.
- Code: define the function in `config/led_lab/effects_lab.py`, register it in
  `LAB_EFFECTS = {"myname": ("slot", fn)}` — kind `"slot"` or `"frame"`. Create/update the
  draft entry via `/api/lab/save`, not by hand-editing `drafts.json` while the server runs.
- The module is fully re-imported on every Play, Update, and Reload; edits are live
  immediately, and a broken module fails the call with the traceback surfaced in the UI (a
  break during live play goes dark until fixed — fail-dark is intended).
- Signature (both kinds, 6 args): `fn(beat_pos, local_t, frame_index, params, segments, seed)`.
  Kind `slot` returns a MotionField (per-pixel slot intensities; slots 0-4 palette, slot 5
  white-reserved, `MAX_SLOTS` 6) and is colorized with Test Palette colors. Kind `frame`
  returns `[(r, g, b), ...]` directly — the full-RGB escape hatch.
- Lab-only constraints: drafts run `continuous` by default (`retrigger` via
  `params["sync_mode"]`); the engine's overlap/multi-comet folding is production-only — drive
  all motion inside your function from `beat_pos`. Play params = saved entry params overlaid by
  the play payload. `slot_colors` is runtime-injected — never invent it as a draft param.
- Live tuning: while a draft is playing, param edits in the `/lab` UI auto-apply (and the agent
  can `POST /api/lab/update`). Color-only keys (`slot_colors`, `color*`, `fade_beats`,
  `gradient_stops`) apply in place; any other key reconfigures motion from the current beat.
  `cue_beats` changes take effect on the next Play; Play always restarts the cue window.

## 3. Start from house patterns
Read the closest existing effect in `govee_frame_renderer.py` and copy its skeleton (slot-based
unless Brandon explicitly wants fixed colors). Reuse the house primitives: `_comet_frame` /
`render_comet`, `_dual_chase`, `_sparkle_frame`, the `slot_coord = intensity * 4.0` gradient
idiom, `_rng(...)` stable seeding. Deterministic by construction: no wall clock, no global
`random` (local `random.Random(...)` only — never reseed the module RNG), survive
`segments == 0`, channels clamp 0-255.

## 4. Self-check before hardware (mandatory)
Before the first Play: `POST /api/lab/reload` and fix any traceback. Then
`POST /api/lab/preview` (or dry-render by calling your function directly) for ~2 cycles at
Brandon's BPM and check: not all-dark, channels in range, motion actually moves, and count
full-strip on/off flips — faster than the house 16th-note gate means stop and rethink before it
reaches the strip.

## 5. Variants first, then tune
For a new idea, author 2-3 variants that each differ on ONE meaningful axis (motion pattern,
density, white usage — not three random takes). Register each as its own draft (`idea_a`,
`idea_b`, `idea_c`), self-check all of them (§4), then play one with Test Palette at Brandon's
BPM and switch live (`/api/lab/switch`) while he watches — switching is seamless, the beat
keeps running. He picks a winner; reject the losers with one line each. Then tune the winner in
whichever mode Brandon wants that day:
- Talk-mode: he describes, you change ONE thing per iteration (`/api/lab/update` while live)
  and describe it back in plain language ("comets now die at the ends instead of wrapping").
- Knob-mode: point him at the few params worth feeling out; his edits in the UI apply live.
  author `param_specs` for those params when you save the draft — the UI turns them into
  sliders (`{key: {label, min, max, step}}`, `kind: "toggle"` for booleans). 2-5 knobs, never
  the whole param dict.
Prefer param-izing a constant over rewriting the shape. Keep a running list of constants
Brandon actually adjusted — those become the promoted render's exposed controls; everything he
never touched stays hardcoded. Stop playback whenever Brandon steps away (Stop is free).

## 6. Accept / reject
Accepted = Brandon says so while watching it. Hand promotion to the codex-spec pipeline: move
the function into `govee_frame_renderer.py`; register in `SLOT_EFFECTS`/`_EFFECTS`; add its
`REALTIME_EFFECT_PARAM_KEYS` allowlist entry (an un-allowlisted static param on a live look
disables ALL LEDs — the C5 fail-safe); add to `REALTIME_STROBE_EFFECTS` if it strobes; tests in
`tests/test_govee_frame_renderer.py` (determinism, frame length/clamping, slot-5 white if
slot-based, param defaults); example-config look; `led_govee` card cue-table row; contract
checks + unittest run. Rejected = status flip in `drafts.json` plus one line on why (so the
next agent doesn't re-pitch it).

## 7. Forbidden
Editing bridge modules mid-lab; running/restarting the bridge without the single-process check;
sending Govee cloud commands; inventing palette systems, scene names, or `slot_colors` params;
upgrading status language; leaving playback running — especially a strobing draft — when
Brandon steps away.
