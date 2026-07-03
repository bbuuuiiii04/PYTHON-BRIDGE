---
name: template-lab
description: Use when Brandon asks for a new LED cue/template or wants to tune one — the AI-assisted flow for creating draft Govee renders in Template Lab, playing them live with placeholder colors, iterating on Brandon's feedback, and promoting accepted drafts into govee_frame_renderer.py via tests + contracts. Not for laser or SoundSwitch work.
---

# Template Lab — agent workflow

## 0. Ground rules (live safety first)
- Never start Govee playback yourself without confirming output ownership: bridge status file fresh (<5s) → ask Brandon before takeover; the pad UI's takeover button is his call.
- Never edit `govee_frame_renderer.py`, `led_config.py`, or any bridge module during lab iteration. Lab code lives ONLY in `config/led_lab/effects_lab.py`.
- Never touch `GOVEE_API_KEY`, device IDs, or live config. Never commit `config/led_lab/`.
- Respect strobe limits: if the draft strobes, say so, keep duty/rate within the patterns already in the renderer, and flag that promotion will need allow_strobe gating.
- Label claims: rendered-in-lab ≠ validated-on-hardware ≠ show-ready. Use §10 status words.

## 1. Interview Brandon (short, concrete)
Ask at most: (1) which moment (groove/buildup/drop/post-drop/breakdown/ambient)?
(2) what does it look like in one sentence (object + motion + energy)? (3) nearest existing
render (play 1-2 references from the pad if unsure)? (4) beat relationship (per-beat hits,
N-beat cycle, continuous)? (5) white accents or palette-only?
Translate to: Comet(s) = visual objects; Motion Pattern = how they move; Motion Beats /
Breath Beats = timing. Confirm the sentence back before writing code.

## 2. Start from existing patterns
Read the closest existing effect in govee_frame_renderer.py and copy its skeleton
(slot-based unless Brandon explicitly wants fixed colors). Reuse the house primitives:
center-out comets, `_drop_chase_spawn_times`, sub-pixel slot mapping (slots 0-4, slot 5
white-reserved), strobe gates, `_rng` stable seeding. Deterministic by construction:
no wall-clock, no global random.

## 3. Smallest runnable draft
One function, production signature (SlotEffectFn preferred), hardcode everything except what
Brandon will obviously tune. Register it in config/led_lab/effects_lab.py, add a drafts.json
entry, set cue_beats to the natural cycle.

## 4. Play + tune loop
Play through /lab with Test Palette placeholder colors at Brandon's BPM. One change per
iteration; describe what changed in plain language ("comets now die at the ends instead of
wrapping"). Prefer param-izing a constant over rewriting the shape. Keep a running list of
which constants Brandon actually adjusted — those become the promoted render's exposed
controls; everything he never touched stays hardcoded.

## 5. Accept / reject
Accepted = Brandon says so while watching it. Then hand promotion to the normal pipeline
(codex-spec skill): move code, allowlist params (value-validate every new numeric key),
strobe-set membership, tests in tests/test_govee_frame_renderer.py, example-config look,
led_govee card cue-table row, contract checks, unittest run. Rejected = status flip in
drafts.json, one line on why (so the next agent doesn't re-pitch it).

## 6. Forbidden
Editing bridge modules mid-lab; running/restarting the bridge without the single-process
check; sending Govee cloud commands; inventing palette systems or scene names; upgrading
status language; leaving playback running when Brandon steps away (Stop is free).
