# Claude Design handoff — full lighting console UI/UX redesign (2026-07-22)

Status: prompt handoff for claude.ai/design. Not documentation of current truth — the inventory
below was verified against source on 2026-07-22 and goes stale from there. The prototype this
produces is a design direction only; landing it in the bridge is a separate implementation step.
Operator intent: the design agent gets full creative authority ("think of everything itself");
this file supplies only facts it cannot know and constraints that are real product requirements.

Everything below the line is the prompt to paste into a new claude.ai/design project.

---

# Redesign my DJ lighting console — full UI/UX, from first principles

## Your role

You have **full creative authority**. Redesign the entire UI/UX of this console from first
principles: information architecture, navigation, how features group into screens, layout,
visual language, interaction patterns, copy structure — question all of it. The current design
is described at the end **as reference only**, so you know what exists; you are free to keep,
evolve, or discard any of it. Nothing binds you except the Non-negotiables section — those are
real product requirements (live-show safety, an enforced plain-language rule, platform
reality), not taste.

Two honesty rules for your redesign: nothing in the functional inventory may be **silently**
dropped — if you think something shouldn't exist, cut it in the design but flag it as a
proposal; and every screen must demonstrate its real states (live, stale, conflict, empty,
error), not just the happy path.

## The product and its user

A local web console one DJ uses to control lighting during live mixes — LED strips and lasers
driven by a Python "bridge" that follows the music. Runs on their Mac; used from the Mac and a
phone. The critical usage moment: **mid-mix, in a dark room, glancing at a phone with one free
hand.** Cold screens need to be calm and instantly readable; deep tools can live behind
disclosure. There is also a desk mode: sitting at the Mac authoring and tuning cues between
shows. Dark environment always.

Today the console is four surfaces (three servers). This division is itself up for redesign —
re-divide however serves the user, as long as every capability survives:

## Functional inventory (what the console must be able to do)

### A. Play surface ("Pad") — used mid-mix
- Grid of saved lighting "looks" (cues), grouped by song-structure phrase banks: Ambient,
  Groove, Buildup, Drop, Post-Drop, Breakdown, Utility (+ Untagged/Legacy/Other overflow).
  Phrase roles have a learned color vocabulary.
- Each look: human title + machine id, color mode ("Uses show colors" vs "Set colors"), length
  in beats, timing kind, strobe flag, origin (Lab cue / cloud scene — cloud scenes aren't
  previewable), live indicator. Actions: Play, Edit, Duplicate, Rename, Move, Delete.
- Session controls: preview tempo (60–200 BPM, steppers), test palette, loop toggle. When the
  live show is running, tempo follows the music and manual tempo locks ("Following your music ·
  128 · tempo set by the live mix").
- Ownership model: the lights are owned by nobody / the show / this pad. Stated in plain words
  ("Lights are free" / "The show is running the lights" / "This pad is running the lights"),
  with Take control / Release. Taking control from the show always confirms first ("The show
  side goes dark until you release.").
- Per-look editor: transport (play/stop, cue length 4/8/16/32/custom beats), effect picker,
  color section (Match the track / Use set colors, palette, brightness %, "Strobe allowed"
  switch with warning copy), color spread (even/random/random-with-solid-chance), per-effect
  motion controls with reset + advanced collapse, save/undo/cancel with dirty state.
- Pad edits are a local draft layer: "Push pad edits" writes them to the lighting file (with a
  confirm explaining the show picks them up at next bridge start); "Undo all changes" reverts.
- Emergency `■ STOP` — always visible, nothing may ever cover it.
- Connect-another-device flow (QR code + LAN URL, with a "anyone on this Wi-Fi can edit"
  warning).

### B. Cue editor ("Lab") — used at the desk
- Drafts list: search, status filters (Work in progress / Accepted / Rejected), phrase filter,
  grouped list with status dots and relative dates.
- Per-draft: title, status pill (Work in progress / Accepted / Rejected / Promoted), phrase
  assignment, read-only timing note ("Locks to the beat" / "Runs on a clock" / "Still").
- Preview: strip view and room view (uses the simulator's room layout), plus "Watch live
  playback" — a read-only mirror of what the pad is sending right now. Preview length 2 bars /
  4 bars / full cue. Beat meter with optional metronome click, honest about click accuracy.
- Tuning: dynamic controls (sliders/toggles/selects/color pickers) generated per effect; cue
  length; live-apply while tuning; "Save draft" with dirty chip.
- The verdict: **"Accept — adds it to your show"** vs **"Reject — keep out of show"**. Accept
  is the ONLY way any cue enters the show, and it promotes what you actually heard (last
  live-tuned values).
- "Play once on lights": fires the draft on the real lights exactly once — one cue, no loop,
  always saves first. When another lab cue is already live it becomes "Switch live lights".
- New draft from a starter (clone a working cue, or an empty shell that needs code before it
  previews). Also: brief/notes text, advanced params JSON, reload effect code, archive
  (refused while live), delete, a collapsed diagnostics corner (server health, effect-code
  health with traceback access, playback state, one-click self-test), help popover.

### C. Room simulator ("Sim") — preview + setup, never touches lights
- Offline room preview of the strip on a canvas: Room/Strip views, labels toggle,
  play/scrub/loop, collapsed diagnostics (device facts: 60 segments, 360 LEDs, 49.2 ft; FPS;
  draw health "Browser draw health, not hardware").
- Two persistent honesty signals: "Preview only — never touches the lights" and "Colors not
  calibrated yet" (until calibration exists).
- Play: render any saved look / built-in effect / lab draft / recorded session at a chosen
  BPM and duration; demo shelf of named look groups.
- Setup (deliberately one step removed so everyday play stays simple):
  - **Layout:** room-shape editing by dragging corners (add/remove points on edges; LED
    spacing is fixed — the path never stretches), presets (Perimeter / Snake / Custom), room
    dimensions in feet with mm hints, a layout library (use/save-as/rename/delete), reverse
    direction, reset, undo, lock toggle that gates all edit gestures.
  - **Calibrate:** measurement sequences + static reference frames for a later capture against
    the real strip ("Nothing is sent now."), screen-matching knobs (color curve, RGB balance,
    brightness, glow size/amount, color spill, target FPS, latency, response model), save/
    revert with dirty chip, its own lock.
- Keyboard: space play/pause, L labels, ←→ step frame, arrows nudge a corner 10mm (⇧ 100mm),
  ⌘Z undo layout.
- Today this is a separate local server the phone cannot reach at all — the current answer is
  a toast ("Sim runs on the Mac for now"). Design the honest version of this reality however
  you see fit.

### D. Laser controller ("Laser Pad") — currently a separate app
- Master "Lasers enabled" toggle (immediate, danger-tinted when on). Runtime pill showing the
  live personality/scene/reason, with emergency and offline states.
- MIDI output port picker (with manual-name fallback), and a test mode ("Practice mode — pads
  light up in the UI but don't send real MIDI") + test BPM.
- A grid of MIDI-note pads in banks (per-bank MIDI channel): each mapped pad shows its label,
  role, personality membership chips, and a safety dot on a safe→strobe→blackout scale.
  Click = send test note; modifier-click = toggle personality membership; long-press/right-
  click = editor drawer; drag-drop = reassign with overwrite confirm and a 10-second undo.
- Per-pad editor: display name, move to bank/pad, primary mapping (role, trigger style
  tap/hold, trigger length, intensity, cooldown beats, fire instantly, motion level, backup
  scene), bank rotation pool (scene list with a primary star), send test / set primary /
  remove.
- Settings: global (drop transition style, lifecycle scenes for startup/stop/stale/emergency/
  fallback, manual MIDI test), personalities (create/rename/duplicate/delete, chip color,
  aliases, BPM band, timing, per-bank primaries, a resolver test), blackout on/off signals,
  bank management.
- Config checks: validate ("✓ check config") and verify mappings ("▶ … no lasers fired"),
  with errors/warnings surfaced in a banner and failing pads ringed red.
- Save model: every edit is a draft (staged + immediately live), "Apply" writes to disk and
  reloads the bridge, "Discard" reverts; save badge (Draft saved / Applied / Saving… / error).
  Backup history with restore + diff.

## Non-negotiables

**Live-show safety semantics** (redesign their presentation freely; never weaken them):
1. Accept is the only path into the show; saving a draft never touches it.
2. "Play once" fires exactly one cue, no loop, and never fires unsaved params.
3. Taking the lights away from the running show always confirms first.
4. An emergency stop is always visible and reachable on the LED surfaces; nothing covers it.
5. The simulator can never touch real lights, and the UI keeps saying so, honestly.
6. Concurrent-edit conflicts (someone/something else changed the file) surface explicitly,
   with reload-the-latest as the safe default.
7. Staleness is honest: the UI distinguishes "bridge not running", "your applied changes
   aren't live yet — restart the bridge to load them", and "live config matches the running
   bridge".
8. Laser: test mode really sends nothing; "verify" fires no lasers; enabled/emergency state
   is unmissable.

**Language** (a CI gate enforces this; musician-plain always): allowed vocabulary includes
BPM, beat, bar, drop, groove, buildup, breakdown. Banned → required: "Strobe Hz" → "Flashes
per second"; "Strobe Duty" → "Flash length (%)"; "Strobe Rate" → "Flashes per beat"; "Beat
Division" → "Trigger every … beats"; "Dim Floor" → "Minimum brightness"; "Fade Decay" →
"Fade-out"; "Follow Show Color" → "Match the track"; "Locked Palette" → "Use set colors";
"time driven" → "Runs on a clock"; "beat sync" → "Locks to the beat"; "Bridge owns LEDs" →
"The show is running the lights"; "UNMEASURED" → "Colors not calibrated yet"; "Flip chain" →
"Reverse direction"; "Neighbor bleed" → "Color spill"; "Renderer" as a heading → "Effect";
"vertex/vertices" → "corner/corners"; "(px)" → "(LEDs)". The voice: buttons are verbs/
outcomes, often with a plain tail ("Accept — adds it to your show"); safety copy is always
explicit ("one cue · no loop", "never touches the lights", "no lasers fired"). Write new copy
freely, in this voice.

**Platform reality:** dark environment (design for dark; a light theme is not needed); phone
and desktop both first-class; touch targets ≥44px on touch devices; visible focus rings; AA
contrast.

**Backend contract:** the prototype runs on mock data, but shaped by the real state model —
ownership (free / show / pad), playback (which look, current beat), config staleness
(not running / stale / fresh), heartbeat-driven tempo lock, look and draft fields as in the
inventory, stale-save conflicts, a live mirror stream, and the laser draft/apply/discard
cycle. Include fixtures that exercise: show-owned vs pad-owned vs free; stale config; a look
live; a stale-save conflict; empty states; a strobe look with strobe disallowed; laser test
mode; laser emergency.

## Known pain points (evidence from the current app — diagnoses, not instructions)

- The three LED surfaces share tokens but drifted: the emergency STOP is styled two different
  ways, there are two modal systems with different behavior, and the Sim feels like a
  different app.
- The Pad's look editor and the Lab's tuning card are the same job (tune an effect's controls)
  built twice with different layouts.
- The Lab's detail panel is six stacked zones — dense and scroll-heavy.
- The Laser Pad is a whole separate application with its own interaction patterns, its own
  dirty-state philosophy, and copy that never went through the plain-language pass.
- Badges, chips, pills, and banners each have local variants per screen.
- Empty states are honest but undesigned plain text.

## Current design (reference only — yours to keep or discard)

Dark UI. Tokens: bg #0b0d10; surfaces #14171c / #1b2027 / #232a33; borders #2b333d /
#3a4450; text #edf1f5 / dim #98a4b1 / faint #6b7683; ok #3fd68f; warn #e8b13f; danger
#f25f5c. Phrase-role colors (the one visual vocabulary the user has actually learned — if you
replace it, replace it deliberately and consistently): ambient #4cc9c0, groove #4da3ff,
buildup #e8b13f, drop #f25f5c, post-drop #b48cff, breakdown #6f9bd1, utility #8b98a5.
Per-screen identity accents: Pad blue, Lab violet, Sim cyan+violet, Laser green. Type:
Archivo variable font for UI, system mono for data/ids. Radius 10px, spacing 4/8/12/16/24,
soft shadows. State conventions: live = green pulse, draft = violet, dirty/stale = amber,
danger = red.

## Deliverable

A working React prototype of the full redesigned console — every surface, every major flow,
real state coverage, on mock data — plus whatever design-system reference you need to keep it
coherent. How you structure the work, what you show first, and every design decision along
the way: your call. Surprise me.
