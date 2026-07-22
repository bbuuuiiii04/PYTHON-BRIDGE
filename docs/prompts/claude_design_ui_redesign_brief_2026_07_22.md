# Claude Design handoff — lighting console UI redesign (2026-07-22)

Status: prompt handoff for claude.ai/design. Not documentation of current truth — the inventory
below was verified against source on 2026-07-22 and goes stale from there. The prototype this
produces is a design direction only; landing it in the bridge is a separate implementation step.

Everything below the line is the prompt to paste into a new claude.ai/design project.

---

# Redesign brief: DJ lighting console (three-screen web app)

## What this is

You are redesigning an existing, working web console that one DJ uses to control LED strip
lighting during live mixes. It runs locally on their Mac (Python servers) and is used from both
the Mac and a phone. It works today — the problem is that it grew screen by screen, so layout,
hierarchy, and interaction patterns drift between screens. Your job is to redesign it as **one
coherent design system** and rebuild the screens as a working React prototype with mock data.

This is a **redesign, not a reinvention**: the workflows, safety rules, and plain-language
wording rules below are settled and must survive. What you own is visual design, layout,
hierarchy, component consistency, and polish.

**User context that should drive the design:** one person, often mid-mix in a dark room,
glancing at this on a phone while doing something else with their hands. Cold screens must be
simple and calm; power tools live behind disclosure. Anything live/dangerous must be impossible
to miss. Dark theme only.

## The three screens (one shared shell)

A shared top bar with route tabs `Pad` / `Lab` / `Sim` plus a session cluster and an always
visible red `■ STOP` (emergency stop). Pad↔Lab switch in place; Sim is currently a separate
server the phone can't reach (today a toast says "Sim runs on the Mac for now" — design a more
graceful treatment of that limitation).

### 1. Pad — the play surface (used mid-mix)

A grid of saved lighting "looks" (cues), grouped into phrase banks matching song structure:
tabs `Untagged, Ambient, Groove, Buildup, Drop, Post-Drop, Breakdown, Utility, Legacy…, Other`,
each with a count and a role color. Each look card shows: human title + machine id (mono),
color mode ("Uses show colors" with gradient dot, or "Set colors" with fixed dot), badges
(`<N> beats`, timing, `⚡ strobe`, `Lab cue`, `LIVE`), a primary `▶ Play`, and icon actions
(Edit ✎, Duplicate ⧉, Rename Aa, Move ⇄, Delete 🗑). The playing card pulses green with a
`LIVE` chip.

Top bar session cluster: `Preview tempo` (60–200 with −/+ steppers), `Test Palette` select,
`Loop` toggle. When the real show is running, a status chip reads "Following your music ·
<bpm> · tempo set by the live mix" and the tempo controls disable.

Ownership model (important): the lights are owned by `free` / the show (`bridge_owned`) / this
pad (`pad_owned`). A pill states it in plain words — "Lights are free" / "The show is running
the lights" / "This pad is running the lights" — with a `Take control` / `Release` button.
Taking control from the show always confirms first: "The show is running the lights right now.
Take control?" / "The show side goes dark until you release."

An editor drawer (right side, always below the STOP button in z-order) opens per look:
transport (`▶ Play`, `■ Stop`, cue length 4/8/16/32/custom beats), Effect select, Color section
(segmented "Match the track" / "Use set colors", palette select, Brightness %, "Strobe allowed"
switch with warning copy), Color spread (Even / Random / Random with solid chance), Motion
Pattern (dynamic per-effect controls with reset ↺ and an "Advanced motion" collapse), and a
footer `Save` / `Undo` / `Cancel` with dirty state ("Unsaved changes" / "Draft saved").

Pad edits are a local draft: a disclosure ("Pad look edits", with count) holds `Push pad edits`
(confirm: "This writes N Pad look edit(s) into your lighting file. Your lights will use them at
the next bridge start. Lab drafts are not touched.") and `Undo all changes` (confirm).

### 2. Lab — the cue editor (used at the desk)

Where new cues are authored, tuned, previewed, and — only via `Accept` — promoted into the show.
Two-panel layout: a drafts list (search, status filter chips `Work in progress` / `Accepted` /
`Rejected`, phrase filter, grouped list with phrase chips + status dots + relative dates) and a
detail panel with, today, six stacked zones:

1. Header: draft title, kind chip, status pill (`Work in progress`/`Accepted`/`Rejected`/
   `Promoted`), `LIVE` chip, Phrase select, read-only Timing note ("Locks to the beat" /
   "Beat + clock" / "Runs on a clock" / "Still").
2. Preview hero: `Strip` / `Room` / `Watch live playback` modes, canvas, transport
   (`◉ Preview`, preview length `2 bars`/`4 bars`/`Full cue`, `▶ Play once on lights`,
   `■ Stop`), beat meter with metronome, honest captions ("Room view · simulator layout ·
   preview only", "Play once sends to the real lights · one cue · no loop").
3. Tuning card: dynamic sliders/toggles/selects/color pickers, cue length, `Save draft` +
   dirty chip.
4. Verdict bar: `Accept — adds it to your show` (green) / `Reject — keep out of show` (danger).
5. Text: Brief textarea, Notes, advanced Params JSON.
6. Footer utils: `⟳ Reload effect code`, `Archive draft`, `Delete`.

This detail panel is dense — improving its hierarchy is a core ask. There's also a collapsed
`Diagnostics` disclosure in the top bar (server health dot, effect-code health dot, playback
dot, `Check this draft` self-test) and a `?` help popover.

When another lab cue is already live, `▶ Play once on lights` morphs into `⇄ Switch live
lights` (amber).

### 3. Sim — room preview + setup ("H612D Studio")

An offline room preview of the LED strip (canvas, Room/Strip view modes, Labels toggle, Play/
scrub/Loop transport, collapsed Diagnostics corner with device facts and FPS). Persistent
honesty chips: "Preview only — never touches the lights" (green) and "Colors not calibrated
yet" (amber, until calibration). A sidecar has two tabs:

- **Play:** source picker (Saved look / Built-in effect / Lab draft / Recording), BPM +
  duration, `Render`, plus a shelf of named demo look-groups.
- **Setup** (deliberately one extra step so everyday Play stays simple), two subtabs:
  **Layout** — layout library (Use / Save as… / Rename / Delete), lock toggle, corner-drag room
  editing ("Drag corners on the room. Double-click or long-press an edge to add a point, a
  corner to remove one. LED spacing is fixed — the path is never stretched."), presets
  (Perimeter / Snake / Custom), room dimensions, `Reverse direction`, `Reset to Perimeter`,
  Undo, `Save changes`. **Calibrate** — lock toggle, measurement sequences and static reference
  frames, screen-matching knobs (color curve, RGB balance, brightness, glow, "Color spill",
  FPS, latency, response model), `Save values` / `Revert` + dirty chip.

Keyboard: Space play/pause, L labels, ←→ step frame, arrows nudge corner 10mm (⇧ = 100mm),
⌘Z undo layout.

## Hard rules that must survive the redesign

**Safety and flow semantics (do not weaken):**
- `Accept` in the Lab is the ONLY way a cue enters the show. `Save draft` never touches it.
- "Play once on lights" is exactly one cue, no loop, and always saves the draft first.
- Taking the lights from the running show always gets a confirm.
- `■ STOP` is always visible and clickable — nothing may cover it, ever.
- Sim never touches real lights, and the UI keeps saying so.
- Concurrent-edit conflicts surface as a modal ("Look changed elsewhere" / "Draft changed
  elsewhere") with Reload as the safe default.
- Config staleness is stated honestly in a banner with three states: bridge not running /
  changes not live yet, restart to load them / "Live config matches the running bridge."

**Language (a CI gate enforces this — banned phrases in parentheses):**
Musician words are fine: BPM, beat, bar, drop, groove, buildup, breakdown. Engineer jargon is
banned. Never write: "Strobe Hz" (→ Flashes per second), "Strobe Duty" (→ Flash length %),
"Strobe Rate" (→ Flashes per beat), "Beat Division" (→ Trigger every … beats), "Dim Floor"
(→ Minimum brightness), "Fade Decay" (→ Fade-out), "Follow Show Color" (→ Match the track),
"Locked Palette" (→ Use set colors), "time driven" (→ Runs on a clock), "beat sync" (→ Locks
to the beat), "Bridge owns LEDs" (→ The show is running the lights), "UNMEASURED" (→ Colors
not calibrated yet), "Flip chain" (→ Reverse direction), "Neighbor bleed" (→ Color spill),
"Renderer" as a heading (→ Effect), "vertex/vertices" (→ corner/corners), "(px)" (→ "(LEDs)").
Button labels are verbs/outcomes, often with a plain tail: "Accept — adds it to your show",
"Play once on lights", "Push pad edits". Honesty copy is always spelled out: "no loop",
"never touches the lights". You may write new copy, but in this voice.

**Platform:** dark theme only; phone + desktop; touch targets ≥44px on touch; visible focus
rings; AA contrast on all text.

## Current visual system (baseline — evolve it, don't discard its logic)

Tokens shared across screens: bg `#0b0d10`, surfaces `#14171c` / `#1b2027` / `#232a33`,
borders `#2b333d` / `#3a4450`; text `#edf1f5`, dim `#98a4b1`, faint `#6b7683`; ok `#3fd68f`,
warn `#e8b13f`, danger `#f25f5c`. Phrase-role colors (a real vocabulary users learn — keep the
concept): ambient `#4cc9c0`, groove `#4da3ff`, buildup `#e8b13f`, drop `#f25f5c`, post-drop
`#b48cff`, breakdown `#6f9bd1`, utility `#8b98a5`. Per-screen identity: Pad accent blue
`#4da3ff`, Lab recolors primary to violet `#b48cff`, Sim uses cyan `#4dd8e6` for dimension
truth + violet for interaction. Font: Archivo variable (100–900) for UI; system mono for
data/ids. Radius 10px (6px small), spacing scale 4/8/12/16/24, soft shadows.

State color conventions: live/playing = green pulse; draft/lab = violet; dirty/stale = amber;
danger/stop = red. Keep these mappings.

## Known problems — your redesign mandate

1. STOP is styled differently on Pad (filled red) vs Sim (outline). One treatment everywhere.
2. Two dialog/modal systems with different focus behavior. One modal component.
3. The Pad's editor drawer and the Lab's tuning card are the same job (tune an effect's
   controls) with different layouts. One shared editor component, used by both.
4. The Lab detail panel is six stacked zones — dense and scroll-heavy. Restructure the
   hierarchy so Preview + tune + verdict feel like one workflow.
5. Sim feels like a different app (different title style, slightly different chrome). Same
   shell, same components.
6. The phone can't reach the Sim at all today (separate localhost server) — the current
   answer is a toast. Design the honest version of that state.
7. Card badge rows, chips, pills, and banners each have local variants. One badge/chip/banner
   system with the state colors above.
8. Empty states exist ("No looks yet", "Select a draft", "No drafts yet — press New to make
   one.") but are plain text. Keep them honest and calm, make them designed.

## Backend reality (mock this; don't redesign it)

The prototype should run on mock data shaped like the real API. The states that matter:
- `runtime_status`: ownership `free|bridge_owned|pad_owned`; playback (which look, beat);
  `config_stale` `not_running|stale|fresh`; bridge heartbeat freshness (drives the
  "Following your music" tempo lock).
- Looks: id, human title, bank/phrase role, beats, timing kind, strobe flag, color mode
  (show colors vs set colors + palette), playable vs cloud-scene (not previewable), dirty flag.
- Lab drafts: name, kind, status (`work in progress|accepted|rejected|promoted`), phrase,
  brief/notes, param specs (slider/toggle/select/color), preview frames, live/not.
- Conflict model: saves can fail stale (someone else edited) → Reload / Overwrite modal.
- A live mirror stream (what the pad is sending right now) that the Lab can watch read-only.

Build mock fixtures for: free vs show-owned vs pad-owned; fresh vs stale config; a look
playing live; a stale-save conflict; empty states; a strobe look with strobe disallowed.

## How to work

Build in this order, showing me each stage: (1) the shared shell + design tokens + core
components (buttons, cards, chips, banners, modal, editor controls), (2) the Pad screen with
all its states, (3) the Lab, (4) the Sim + Setup. Keep a components reference page so the
system stays consistent. Every screen should demo its live/stale/empty/conflict states, not
just the happy path.

One future note (design the system to allow it, don't build it): a fourth surface exists — a
laser controller pad, currently a separate app with its own patterns. The design system you
create should be able to absorb it later (same shell, same components, one more route tab).
