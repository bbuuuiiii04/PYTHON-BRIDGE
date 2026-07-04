---
doc_status: current
truth_level: design-direction, code-grounded
last_verified_commit: 89736bb
last_verified_date: 2026-07-04
validation_scope: review + proposals only — no code changed; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED repo status unchanged
---

# Template Lab — creative + engineering direction (2026-07-04)

Author: Claude Fable 5, acting as Template Lab creative/engineering lead per
`docs/prompts/active/template_lab_creative_lead_fable.md`. Everything cited below was read in
code this session at commit `89736bb` unless labeled otherwise.

## 1. What Template Lab is today (confirmed)

A second route (`/lab`) on the LED Pad web server (`:8766`, `tools/led_pad_web.py:902`) where an
agent writes a draft effect function into the gitignored sandbox `config/led_lab/effects_lab.py`,
registers it in a `LAB_EFFECTS` dict, and plays it on the real strip through the **production**
playback stack: `LabRenderer` wraps `GoveeFrameRenderer` and is handed to `PadPlayback` at
construction (`tools/led_pad_web.py:213-220`), which drives the production
`GoveeRealtimeRunner`/transport (`tools/led_pad_playback.py:212-231`). The sandbox module is fully
re-imported on every Play (`tools/led_pad_web.py:610`), so edits are live immediately and a broken
module fails the play with a traceback surfaced to the UI. Draft metadata (brief/notes/params/
cue_beats/status) lives in `config/led_lab/drafts.json` via `LabRegistry`
(`tools/led_pad_lab.py:45-130`). Test-palette placeholder colors are injected at play time through
the real `LedColorEngine` (`tools/led_pad_web.py:518-549,622`). No drafts have been authored yet
(assumed — file is runtime-created and gitignored; stated in the mission prompt).

The design doc `docs/architecture/led_pad_template_lab_design.md` still says "planned — nothing
implemented" (its lines 5, 11-13). That is stale; the spec's phase table
(`docs/plans/active/led_pad_template_lab_spec.md:17-40`) and the code above are the truth. Code
wins.

## 2. Friction and ceilings (each confirmed in code this session)

**Tool:**
- **T1 — every tweak restarts the cue.** The lab UI only ever calls play
  (`tools/led_pad_assets/lab.js:90-102`); `/api/update`'s live-apply path resolves names through
  the production look table and so rejects lab scenes (`tools/led_pad_web.py:667-681` →
  `_look_state` `:500-516`). Meanwhile the runner already supports seamless color-only updates and
  motion-only reconfigures (`govee_realtime_runner.py:282-303,433-438`) and
  `PadPlayback.update()` exists (`tools/led_pad_playback.py:296-302`). The capability is built;
  the lab just doesn't reach it.
- **T2 — tuning means editing raw JSON.** Params are a bare textarea (`lab.html:47`); no
  min/max/step, no indication of which keys the draft even reads.
- **T3 — no preview; the only render surface is the physical strip.** The agent authors blind and
  Brandon can't see a draft without playing it. `LabRenderer.render` is pure
  (`tools/led_pad_lab.py:175-189`), so offline frame rendering is nearly free — the tool just
  doesn't offer it.
- **T4 — no code-level strobe gate for lab drafts.** Strobe validation only fires for names in
  `REALTIME_STROBE_EFFECTS` (`tools/led_pad_playback.py:257-265`), a fixed set of production
  names (`govee_frame_renderer.py:947,1828`); `lab_*` names can never be in it (collision guard at
  `tools/led_pad_lab.py:117-121`). The `allow_strobe: False` in the lab spec
  (`tools/led_pad_web.py:627`) is dead weight — validation short-circuits before reading it. The
  only rail today is agent discipline in the skill.
- **T5 — housekeeping ceilings.** No draft delete/archive endpoint (`tools/led_pad_web.py:783-803`)
  and no status filter in the sidebar (`lab.js:38-46`) — rejected drafts accumulate forever.

**Cue-authoring skill (`.claude/skills/template-lab/SKILL.md`):**
- **S1 — mechanics are missing.** The skill never mentions the HTTP API
  (`/api/lab/save|play|reload`, `tools/led_pad_web.py:783-803`), the reload-per-play semantics, or
  the param merge order (saved entry overlaid by play payload, `tools/led_pad_web.py:618-620`).
  Each session's agent rediscovers the tool from scratch.
- **S2 — vocabulary doesn't map to real knobs.** "Comet / Motion Pattern / Motion Beats / Breath
  Beats" (skill §1) vs the actual param surface (`travel_beats`, `width`, `trail_beats`,
  `sync_mode`, `beat_division` — `govee_frame_renderer.py:987`).
- **S3 — the strobe rule implies a gate that doesn't exist** (see T4). The skill must own this
  honestly: the agent IS the gate.
- **S4 — no self-check before hardware.** Nothing tells the agent to dry-render frames and sanity-
  check before the first Play lands on Brandon's strip.
- **S5 — lab-only constraints unstated.** Lab drafts run `continuous` by default
  (`govee_frame_renderer.py:1010-1016`; `lab_*` is never comet-classified `:1006-1008`), so the
  engine's overlap/multi-comet instance folding (`govee_realtime_runner.py:343-361`) is
  production-only. An agent copying a comet skeleton needs to know motion must be driven inside
  the function from `beat_pos`.

**Expressiveness ceilings (renderer, confirmed):** 6-arg `EffectFn`/`SlotEffectFn` signature
(`govee_frame_renderer.py:11,19`); `MAX_SLOTS = 6`, slots 0-4 palette + slot 5 white-reserved
(`:15,1026-1046`); determinism required (no wall clock; `_rng` stable seeding `:108-115`); frames
exact-length, fail-dark (`:1943-1952`). The `frame` draft kind bypasses the colorizer entirely
(`tools/led_pad_lab.py:184-188`) — the full-RGB escape hatch already exists.

## 3. Direction (committed)

North star: **the agent writes the shape once; Brandon tunes it by feel, live, without touching
JSON.** Three build rounds, each one Codex spec, in this order:

**Round 1 — close the tune loop (intuitive + practical).**
1. `/api/lab/update`: mirror `_lab_play_spec` but call `PadPlayback.update()` instead of
   `play()`. The lab UI auto-applies param edits while its draft is playing: color-only edits
   apply in place, motion edits reconfigure from the current beat — exactly the semantics the
   runner already implements for pad looks.
2. `/api/lab/preview`: server-side offline render of N beats × 40 fps through the pure
   `LabRenderer` (no transport, no ownership needed), returning frames; `lab.js` animates them on
   a canvas strip. Doubles as the agent's self-check surface — and as the input to the strobe
   metric below.
3. Strobe rail (operator decision, see §5): compute a flash metric from the preview frames
   (full-strip luma flips/sec); warn in the UI and optionally refuse `lab/play` above the house
   ceiling (16th-note gate) without an explicit override.

**Round 2 — sliders over JSON (intuitive + customizable).**
Draft entries gain an optional `param_specs` map (`{key: {label, min, max, step, kind}}`) written
by the agent at authoring time; the UI renders sliders/toggles above the JSON textarea (which
stays, as the advanced fallback). `LabRegistry` is schema-free dicts already — passthrough is
trivial. `param_specs` is also the concrete record of "controls Brandon actually tuned" that the
skill's promotion step wants: what he moved gets exposed in production, what he never touched
stays hardcoded. Plus: swatches showing the injected slot colors for the current test palette, so
"slot 3" means something visible.

**Round 3 — housekeeping (practical).**
Status filter in the drafts sidebar (default: hide rejected) and a `/api/lab/delete` endpoint.
Small, no design risk.

**Deliberately not doing:** in-browser Python editing (the agent owns the code file; a textarea
IDE is scope creep), multi-draft layering/compositing (that's the Stream Deck compositor
workstream), cloud-scene preview, versioning beyond `drafts.json` (agent snapshots in notes when
needed).

## 4. Proposed replacement for `.claude/skills/template-lab/SKILL.md`

Ready to adopt against today's code (no Round 1-3 features assumed). Apply via Codex or by
operator; per my boundaries I have not edited the skill file.

```markdown
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
  `{"name", "params", "cue_beats", "takeover"}`, `/api/stop`.
- Code: define the function in `config/led_lab/effects_lab.py`, register it in
  `LAB_EFFECTS = {"myname": ("slot", fn)}` — kind `"slot"` or `"frame"`. Create/update the
  draft entry via `/api/lab/save`, not by hand-editing `drafts.json` while the server runs.
- The module is fully re-imported on every Play and Reload; edits are live immediately, and a
  broken module fails the play with the traceback surfaced in the UI.
- Signature (both kinds, 6 args): `fn(beat_pos, local_t, frame_index, params, segments, seed)`.
  Kind `slot` returns a MotionField (per-pixel slot intensities; slots 0-4 palette, slot 5
  white-reserved, `MAX_SLOTS` 6) and is colorized with Test Palette colors. Kind `frame`
  returns `[(r, g, b), ...]` directly — the full-RGB escape hatch.
- Lab-only constraints: drafts run `continuous` by default (`retrigger` via
  `params["sync_mode"]`); the engine's overlap/multi-comet folding is production-only — drive
  all motion inside your function from `beat_pos`. Play params = saved entry params overlaid by
  the play payload. `slot_colors` is runtime-injected — never invent it as a draft param.
- Every Play restarts the cue from the top; there is no live param apply in the lab today.

## 3. Start from house patterns
Read the closest existing effect in `govee_frame_renderer.py` and copy its skeleton (slot-based
unless Brandon explicitly wants fixed colors). Reuse the house primitives: `_comet_frame` /
`render_comet`, `_dual_chase`, `_sparkle_frame`, the `slot_coord = intensity * 4.0` gradient
idiom, `_rng(...)` stable seeding. Deterministic by construction: no wall clock, no global
`random` (local `random.Random(...)` only — never reseed the module RNG), survive
`segments == 0`, channels clamp 0-255.

## 4. Self-check before hardware (mandatory)
Before the first Play: `POST /api/lab/reload` and fix any traceback. Then dry-render ~2 cycles
by calling your function directly at Brandon's BPM (several `beat_pos`/`local_t`/`frame_index`
points) and check: not all-dark, channels in range, motion actually moves, and count full-strip
on/off flips — faster than the house 16th-note gate means stop and rethink before it reaches
the strip.

## 5. Play + tune loop
Play through `/lab` with Test Palette at Brandon's BPM. ONE change per iteration; describe it in
plain language ("comets now die at the ends instead of wrapping"). Prefer param-izing a constant
over rewriting the shape. Keep a running list of constants Brandon actually adjusted — those
become the promoted render's exposed controls; everything he never touched stays hardcoded.
Stop playback whenever Brandon steps away (Stop is free).

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
```

## 5. Open decisions (Brandon)

1. **Build scope for round one** — skill-rewrite-only vs Round 1 (live-apply + preview) vs
   Rounds 1+2 vs all three. My recommendation: Round 1 now; it kills T1/T3 with one Codex spec.
2. **Lab strobe rail** — code rail (preview-derived flash metric, warn/block with override) vs
   discipline-only (skill §0). My recommendation: the code rail, since it rides on Round 1's
   preview for ~free; but this is a live-safety/taste call.
3. **First template target** (aesthetic): groove-time variety, breakdown/ambient moods, or more
   drop/post-drop variants. Catalog is drop/post-drop-heavy today; most set-time is groove.

Once decided: I author the Codex spec(s) per `.claude/skills/codex-spec/SKILL.md`; Codex
implements; the skill rewrite is applied verbatim from §4.
