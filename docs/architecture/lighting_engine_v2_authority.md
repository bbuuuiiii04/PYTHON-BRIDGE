---
doc_status: current
truth_level: operator-authoritative intended behavior (design)
last_verified_commit: f30f1e6
last_verified_date: 2026-07-05
validation_scope: authoritative intended-features contract for LIGHTING ENGINE v2 — design intent, not yet implemented except where a section explicitly says a v1 behavior carries forward (those carryovers are implemented/software-tested and verified in code at the commit above); no hardware validation anywhere
---

# LIGHTING ENGINE v2 — The Authoritative Intended Experience

**Status: AUTHORITATIVE TARGET BEHAVIOR; PLANNED (not yet implemented).** Once v2 is built,
behavior that differs from this document is a regression unless this document is
intentionally updated. Until then, this is the single design authority the expansion
one-shot and the Feature 1–4 Codex specs build from — and the one document the operator
reads to know what his light show is supposed to do.

This document consolidates every decision made across the v2 design record, the two design
reviews, the operator's locked agreement and corrections, his two beat-by-beat lighting
walkthroughs, and the built spectral-v4 analysis layer. Where it summarizes today's (v1)
behavior, that behavior was verified in code and is marked as a carryover. Where numbers
came from outside research, they are starting values to tune live, never verified facts.

Sibling authorities that keep governing alongside this one:
`drop_presentation_authority.md` (which fixtures fire per drop),
`laser_color_authority.md` (laser color follows the LED engine),
`laser_blackout_authority.md` (blackout beats everything),
`palette_control_authority.md` (the Stream Deck surface),
`active_deck_authority.md` (which deck leads).

---

## 1. The show, in one page

The promise: **every track wears its own light and wears it every time; the room knows
what's coming; the big moments land on the beat, not after it; and your hands always win.**

A night with v2 on looks like this. A track loads and the bridge already knows its
character from a one-time audio analysis of your whole library — how gritty, how punchy,
how bass-heavy, how dramatic it is. That character picks the track's color identity: its
own corner of the palette, permanent across nights, so recurring anthems become
recognizable. The room follows the music's shape — sparse and dim in atmospheric stretches,
grooving in color through the body, climbing with the builds — and when a drop approaches,
the lights *move toward it*: build moves that squeeze, cascade, or swell and arrive exactly
on the downbeat; a blackout sized to the track's own pre-drop silence; then the drop
explodes at full scale, every track, every time. Lasers join on the track's biggest moments
only, in colors chosen to cut against the LED wash, now as visible beams in haze. When you
mix, the lights mirror your fader; when you slam, they slam. And through all of it, your
pads and Stream Deck outrank everything the automation wants.

**The seven laws** (each one is operator-locked or a settled review ruling; nothing below
may violate them):

1. **One engine at a time.** One master switch selects v1 or v2. v2 off ⇒ today's behavior,
   byte-identical. Every v2 feature also has its own kill switch.
2. **Manual always wins.** Emergency blackout > manual holds/mutes/static overrides > any
   automation, v1 or v2. Blackout ownership rules are untouched.
3. **Markers are authoritative.** Rekordbox phrase/drop markers are your owned truth. The
   analysis describes sound; it never times or triggers a structural moment.
4. **Decorate, never decide.** Texture and analysis flavor what plays; they never create,
   cancel, or move a moment.
5. **Drops always render full-scale.** Color identity picks colors, never power.
6. **Total darkness is fine.** True black is a designed tool in this room (your call,
   confirmed twice).
7. **No double drops.** One song owns the room, no exceptions.

**Every track, guaranteed.** v2 must hold for the whole library, not a demo set. Three
mechanisms make that structural rather than hopeful: (a) every track that can be analyzed
already is (666 of 686 on-disk files; the remainder are beatgrid-less FX one-shots and one
corrupt file), and a new purchase analyzes itself at first load; (b) every selector has a
safe default — an unmeasurable track gets a neutral zone, an ambiguous drop gets the
neutral family, a track without a texture shows none of it — so no track can ever fall off
the map; worst case is tasteful-generic, never broken; (c) before anything is built, the
**library-wide dry-run audit** runs the complete decision pipeline over every cached track
and reports the distributions and the strangest outliers — the ear-check list is targeted
at the weirdest tracks in the library instead of trusting a handful of anchors. Coverage is
demonstrated on all ~700 tracks, then taste is tuned live.

## 2. The room and the hardware (what is physically true)

- **The Govee strips are the room's only light** — wall-strung around the living-room
  perimeter, 60 segments, driven over LAN at 30 frames per second. Full blackout means a
  pitch-black room with people in it; that is accepted and used deliberately (law 6).
- **The 30 fps pipeline caps strobes at 15 flashes per second**, and odd rates shimmer
  instead of strobing. Cue design therefore uses beat-division rates (every beat, half-beat,
  quarter-beat) plus rising intensity/width to sell acceleration — the eye reads the
  combination as continuous. This is physics, not a policy cap; your no-rate-cap lock
  stands untouched.
- **Whole-strip looks read professional; busy multi-color segment chases are banned.**
  Simple single-head motion (comets, sweeps — already validated live) stays. (Carryover
  idiom, verified in the renderer.)
- **White is wattage.** Saturated color is physically dimmer than white on these strips, so
  color carries identity and white carries power: peaks are white-hot cores with the
  track's color at the edges. Sustained white is banned outside manual looks — white is a
  burst that decays back into the track's color.
- **Two DMX lasers, in haze.** Haze is confirmed IN, so beams are visible in the air —
  beam-based looks are first-class design material. One authoring guideline (not an engine
  rule): beams aim above heads or at surfaces in this room.
- **The mixer signal** (for Feature 3) exists for decks 1/2 only and is pinned to
  Rekordbox 7.2.11 — a Rekordbox upgrade silently drops it until offsets are re-derived,
  and the blend degrades invisibly to a time-based stand-in. Accepted constraint.
- **Hardware tip on record** (not engine work): diffuse the strips (milky channel) or
  bounce them off walls; exposed LED dots read amateur at close range.

## 3. The color story (Feature 1 — track identity)

**What you see:** each track owns a slice of color and keeps it forever. STARsound wears
bright blue/cyan/white; Can't Say Nah wears darker blue/cyan. Those two calls are the
anchors — the measured character axes already separate them exactly that way (STARsound
reads twice as bright, far punchier, and more dramatic than Can't Say Nah), and the zone
map must reproduce both from measurements alone.

**How identity is chosen:**
- Four measured character axes — grit (distortion), punch (kick spikiness), bass (sub
  weight), drama (dynamic range) — pick the track's **color zone**. Corpus-proven stable:
  the same track measures the same every time.
- Zones follow the **neon direction** you locked: smooth/melodic → deep blues, teals,
  purples; aggressive bass/trap → electric neons (hot magenta, acid cyan, lime) with white
  violence at peaks; the dubstep/riddim extreme also earns deep reds/purples; true red
  stays rare and earned. Musical key is out of the color story entirely — no key owns a
  color.
- A **deterministic per-track hash spreads tracks within their zone** so same-zone
  neighbors don't twin; the depth and dynamics axes (saturation floor, gradient span,
  excursion budget) must differ visibly between neighbors so recognition comes from the
  combination, not hue alone.
- **Permanent across nights**: identity is a pure function of the track and its
  measurements — no randomness, no session seed, no deck salt. Identity freezes at first
  derivation and is stored per track, so later analysis upgrades can never silently repaint
  the library.
- Warm color stops (orange/amber/gold) get added to the engine's color scale — today's
  scale is six cool-only stops — because earned warm accents need to exist; they are
  accents, not key-owned families.

**Correction path (launch requirement):** if a track lands in a color you hate, the
existing palette pads override it live for that play; pressing **palette lock** while the
override is active writes it as the permanent per-track correction; unlock while that track
plays clears the stored correction. The correction store survives restarts.

**Identity in motion:** character also drives motion style — punchy tracks get sharp
attacks and hard onsets; smooth tracks get flowing sweeps. The track's dynamics budget
decides how far its looks travel between breakdown and drop; the identity holds while the
energy arc decides how loudly it speaks. Long single-zone stretches are a feature — the
room follows the set's shape.

**First play of the night:** a single 2-bar bloom the first time a track becomes audible
tonight (held ~8 beats before it can fire). After a bridge restart, tracks may bloom again
— accepted (rare and pretty).

**Handover:** until Feature 3 exists, switching decks soft-flips the identity over 4–8
beats, keyed off the active-deck flip (so cutting to deck B and back repaints A correctly).

**Fallbacks are corner cases now:** the whole decodable library is analyzed (666 of 686
on-disk tracks; the rest have no beatgrid or a corrupt file). A brand-new purchase pays a
one-time ~12-second analysis at first load and has its identity from that load onward.
Anything unmeasurable lands in a neutral-safe zone with the same hash spread.

## 4. Moments that land (Feature 2 — Land on the One)

**What you see:** effects stop reacting and start *anticipating*. A comet doesn't fire on
the beat — it arrives on the one. Builds are physical: light squeezes toward the center and
explodes outward exactly on the drop; a fuse burns segment by segment and the last segment
ignites on the downbeat; an 8-bar swell completes precisely at the phrase turn.

- **Landing as infrastructure:** the existing comet/sweep library upgrades from
  "starts on the beat" to "lands on the one." Arrival math retargets every frame from the
  live beat clock, so riding the pitch fader bends the flight and the landing stays pinned.
  Backward jumps (spinback, scratch, seek) never glitch: the move finishes gracefully or
  melts away; deck switches mid-flight degrade safely (an arrival never retargets onto
  another deck's timeline).
- **The build family:** squeeze-explode, fuse (cascade), swell (phrase-scale). The track's
  character picks its build move and its body language, per-track consistent — the build
  becomes part of the track's identity.
- **Landing restore — the marquee moment:** in a breakdown the room eases down within the
  track's dynamics budget; then light flies back in and *lands on the drop's first beat*
  (the drop beat is known from markers ahead of time). This is the single v2 moment guests
  will describe out loud.
- **Strobe acceleration lives inside specific buildup cues** (as your v1 cues already do);
  the role system schedules those cues; acceleration is the cue's own behavior.
- **White share scales with build intensity:** a modest build gets white+color mixes; a
  monster build earns full white at the top. The measured build energy (rising roll flux
  and level over the buildup) sets the white fraction — formula pinned in the spec, tuned
  on your walkthrough tracks.
- **Phrase pacing:** look changes snap to the 16/32-bar phrase grid; step rate is
  character-driven (techno-like tracks hold long arcs; punchy trap/bass tracks pivot every
  8–16). Phrase-end turnaround stingers — a brief accelerating accent landing on the next
  downbeat — are texture/energy-gated and get their own short cooldown class so they don't
  eat each other (drop-scale impacts keep the long 12 s cooldown).
- **Fires at every true drop, never on a bare bar count.** A missing marker means no build
  move — safe absence.
- **New animation vocabulary is a v2 deliverable in its own right** (operator ask,
  2026-07-05): beyond the build family, landing restore, stingers, bloom, and the blend
  painter — which are all new shapes — every role family (groove, buildup, drop, post-drop,
  breakdown/atmospheric) gains at least 2–3 genuinely new shapes, designed in the expansion
  phase, authored through Template Lab against the color-slot contract, and selected by
  measured character and energy. v2 is not v1 repainted: the old library's dozen shapes
  carry forward *and* the vocabulary grows in every role.

### 4.1 The pre-drop blackout (the rules, settled)

Per drop, the engine reads the track's own pre-drop emptiness from the cached analysis and
sizes the blackout to it — capped at 16 beats (~7 s at 140 BPM). These rules replace the
idealized "scan backwards from the drop" prose everywhere else; they were derived by
running the shipped analysis against your walkthrough tracks:

1. **The floor test is sub-only.** "Lows out" to your ear = the sub band gone, even while
   build percussion keeps the 60–150 Hz band busy. (Measured: every gap you described
   matches sub-only; the stricter two-band test missed all of them.)
2. **Pickup tolerance.** The gap may end up to ~3 beats before the marker (real drops carry
   a 1–2 beat pickup/riser hit). The blackout still runs **through the pickup into the
   hit**: dark from (marker − gap length) until the marker, light explodes at the hit —
   exactly your Can't Say Nah "room blackout → drop" and the 1-beat "percussive cut →
   1-beat blackout".
3. **Floor-returned abort.** If the sub comes back and stays back (2+ consecutive beats)
   while the room is dark, the blackout aborts early and the previous look returns — the
   room is never black over a landed drop (STARsound's drop audio arrives 3 beats before
   its marker; the marker still fires the drop cue). Confirmed by you, no veto.
4. **Relative dips are their own trigger.** Some of your "lights cut" moments are not
   bottom-gone at all — the whole mix ducks several dB while the floor stays (STARsound
   2:12.4; Can't Say Nah beat 127). A relative-dip rule (full-band level falling well below
   its local context inside build/breakdown sections, capped at 4 beats) drives those short
   cuts. Constants tune live.
5. **No gap found → snap flick.** Music that slams straight in gets the short
   snap-to-black flick (~125–250 ms starting value).
6. **Breakdowns ride "sparse and dim," not black.** True black is reserved for the blackout
   window itself; the long empty-floor stretch before it keeps a low simmer (your words,
   your confirmation, no veto).

Everything above is arithmetic over data already cached for the whole library — no
re-analysis, ever. Acceptance is falsifiable: the rules must produce the right gaps on
ILL (12 beats at drop 109, 2 at 261), Can't Say Nah (26 → capped 16 at drop 352), and
STARsound (2 beats at 131 with the abort) straight from the shipped cache.

### 4.2 Drop-type selection (which drop cue fires)

Each drop's own measured character (its window of band levels, attack, onsets, timbre,
pre-gap) selects the drop cue family: **dubstep/trap wall-stutter** (dense bursts with
darkness between — trap and dubstep share one expression, your ruling), **techno comet**
(fast red beat-locked chase), **house families** (tech-house sparkle-burst→groove-chase;
bass-house looping pulse-expand), with a **neutral default** whenever the window is thin or
ambiguous — a wrongly-neutral drop is invisible; a wrongly-loud one is the worst seasoning,
so ties always land neutral. Selection chooses *which* cue, never *whether or when* (marker
fires it). Held-out measurement already proves these families are separable well above
chance. The classification and its reason are visible in status per drop.

**Drop energy, within the family.** Every drop renders full-scale (law 5) — so a drop's
energy level never scales its brightness down; it shapes its **aggression profile**. Each
drop gets a measured intensity tier (corpus-absolute, from its window: absolute level, lift
over the track's own loudness reference, low-end attack, onset density, pre-drop vacuum),
and the tier sets the violence knobs *within* the chosen family: strobe density and burst
structure (continuous wall vs stutter bursts vs no strobe at all), animation-rate rung
(every beat / half-beat / quarter-beat), white share (white-hot core vs white accents
riding the track's color), motion violence, and micro-darkness between hits. Concretely: a
pounding hard-techno drop reads **relentless** — driving beat-locked red comet, white
slamming on the one, no gaps, the room pounding as one light. An ISOxo-grade trap/dubstep
monster reads **maximal** — full-strip white stutter-strobe at half/quarter-beat rates with
darkness between the hits so each one lands harder. A groovy house drop is *just as
bright* but reads **bounce** — color-forward pulse and sparkle, white as accents, no wall.
The tier is per-drop, not per-track — a track's four drops measurably differ (Ray Volpe —
DROP EM spans clean-to-growliest across its four) — and SET mode's "true ceiling reserved
for peak-time" reads this same tier.

## 5. Which fixtures fire (drop presentation — v1 authority, carried forward)

This is already implemented and software-tested, and v2 keeps it exactly (it is the
standing answer to "some drops LEDs, some LEDs+lasers, some lasers only"):

- **LEDs carry most drops alone.** Lasers are drop-only punctuation.
- **The track's biggest moments get LEDs + lasers**: each track's true drops are ranked by
  its own dramaturgy (last drop first, then longest runway) and the top ~40% earn lasers —
  a pure function of the track, so the same track presents identically every play.
- **Laser Solo (Govees black, lasers alone) is rare and never a dice roll**: only a pad
  press, a `LASER` hot-cue tag, a remembered manual solo, a big BPM gear-shift, or the
  night's record-breaking buildup earns one — always operator-traceable, with a darkness
  guard that falls back to LEDs+lasers if the lasers wouldn't actually be visible.
- The session's first tracks are damped (LEDs only), a track's final drop is guaranteed at
  least LEDs+lasers, scripted tracks are sovereign (no policy activity), and everything
  fails open — the policy can never latch a fixture dark.

v2's only change of substance here: v2 supplies *what* the fixtures show (identity colors,
build moves, drop families); this policy keeps deciding *who* fires. The two compose.

## 6. Lasers in the haze era

- **Personality by measured character.** Today lasers pick a personality (role→scene map)
  by playlist name or BPM with only {dubstep, house} defined. v2 replaces just the picker:
  the same character zones that pick LED colors pick the laser personality. Scenes, safety
  classes, cooldowns, fallbacks, and the MIDI executor all keep.
- **Color: lasers contrast the strips, never mud.** The bridge already owns the laser
  frame and follows the LED color engine on non-scripted tracks (scripted shows stay
  sovereign). v2 rides that plumbing: each color zone carries a fixed complementary accent
  pair (neon zones → cyan+magenta; smooth/deep zones → deep blue+amber; extreme zone →
  red+white), so beams cut against the wash by construction.
- **Rest vs fire.** Lasers rest in verses and fire on drops — scarcity is what makes them
  read as an event (and the drop-presentation ladder already enforces scarcity).
- **Beams are in scope now** (haze confirmed): aerial fans, sky/liquid effects, beam
  chases — not just wall patterns. What blocks beam-look design is one working session:
  **cataloging the lasers' real MIDI-reachable vocabulary** (patterns, size, motion,
  rotation speed, color, strobe — the CH8 color/effects, CH9 speed, CH11 strobe controls).
  That is the planned operator+Claude session; after it, personality packages are drafted
  per zone and auditioned live, Template-Lab style, then locked.

## 7. Mixing two songs (Feature 3 — the blend)

**What you see:** the incoming track's colors enter the room the way your hands bring in
the music. Accents first — offbeat hits and comet spawns start drawing from the incoming
palette, gaining beats of presence bar by bar as your fader rises — then past the midpoint
the base wash itself morphs. When the blend commits, a single one-bar resolve bloom marks
"we're in the new track now."

- **The fader is the boss.** Takeover speed mirrors your actual fader ride; the lights
  never take longer than your hands did. Slam = instant snap. Chops = the room chops along.
- **Near colors glide; opposite colors trade.** Neighboring identities morph smoothly
  through the palette space between them; distant identities never smear through grey —
  they alternate accent ownership with rising incoming share, then snap-commit. No frame
  ever shows a muddy in-between.
- **Dipless and single-axis:** total room brightness never dips mid-blend, and any moment
  morphs color or moves intensity — never both at once.
- **An abandoned blend breathes back out** — presence steps release bar by bar; no
  flapping, no resolve fired unless the blend crosses and holds.
- **No double drops** (law 7). If both decks happen to sit in drops with both faders up,
  the active-deck authority picks the leader and the other deck stays accent-only; no
  special moment fires.
- Deck 1/2 only; blend constants get tuned from one recorded practice session
  (`RBSS_RECORD_SESSION`) riding a few long blends — the one hardware input v2 still wants
  from you.

## 8. Texture (Feature 4 — the seasoning layer)

**What you see:** within an already-playing look, the room reacts to what the beat *is* —
percussion-locked hits where drums dominate, sparkle where the sound is thick and
aggressive, smooth flow in melodic passages, darkness where the floor is empty, a low
simmer in percussion-free atmospheric stretches.

**The containment law and its mechanism (settled this review):** texture may never trigger,
suppress, retime, or replace a moment — but **within the moment the schedule already chose,
texture picks the variant and the flavor.** Your walkthrough is the defining example: at a
Can't Say Nah drop, the growl-bass beats get the strobing sparkle and the driving beats get
the post-drop comet chase — both are drop-family cues; texture only chooses between them,
beat by beat, while the drop itself was fired by the marker and stays full-scale. The
scheduler never sees texture; texture is read only at cue selection/parameterization.
Worst-case wrong texture = wrong seasoning for a beat, never a missed or phantom cue.

**The classes** (all from the cached analysis; all corpus-absolute — tracks without a
texture show none of it):
- Kick-prominence, thick-vs-thin, bright/dark tilt, stab-vs-sustain, empty-floor darkness,
  atmospheric simmer (percussion-free stretches).
- **Bass-forward beats (the tech-house "growl" answer, settled this review):** the
  distortion-based growl class correctly catches dubstep/riddim screams but measures *zero*
  at your tech-house growls — those basslines are clean-toned. So the walkthrough behavior
  is driven by a new rule reading the bass's *level and shape*: a beat is bass-forward when
  its low-mid bass rides near the drop's own bass ceiling with a sustained (not kick-spiked)
  shape. Calibrated on Can't Say Nah's drops as the anchor, scrub-gated like every class.
  The distortion class stays for what it really measures (named honestly: distorted growl).
- **Busy-pulse** (the experimental fast low-mid pulse): wobble basses, dense rolls, chugs,
  and sirens all fire it — used only as busy/aggressive seasoning, never as "wobble"
  semantics.

**Two recorded limitations** (deliberately not retuned on single tracks; the live/scrub
pass decides): sidechained four-on-floor kicks under thick walls under-read as
kick-prominent (a slot-pattern alternative is already derivable), and very thick layered
walls miss the sustained-synth class by a hair of its cleanliness gate.

## 9. The night's modes

- **WILD OUT (default):** every drop hits 100%, all night. Your lock.
- **SET mode (selectable):** pro pacing by **layer withholding**, not dimming — held drops
  lose the white burst, the strobe ceiling, and full-strip span but keep 100%-intensity
  color hits; the true ceiling (white + max strobe + full span) is reserved for peak-time.
  A flat brightness multiply is invisible on strips; withholding is what actually reads.
- Mode flips (and the v1/v2 engine switch) take effect at the next look boundary, never
  mid-move.
- **The animation-rate ladder** (your general principle): atmospheric moments animate every
  4/2/1 beats by character; regular grooves every beat; drops every 1 / 0.5 / 0.25 beats.
  Which rung a moment gets is selected from its section energy, texture, and BPM (a
  quarter-beat rung at high BPM only where the 30 fps clock can actually render it).
- Fast color changes *within the track's palette* are also an energy signal.
- Fade grammar starting values: snap 0.0 s (drops/blackouts), snappy 0.1–0.3 s
  (high-energy), smooth 1–3 s BPM-scaled (look-to-look). A 1–2 s neutral dip may reset the
  palate on hard genre pivots.

## 10. Priority — the moment arbiter

When designed moments collide on the same bars, one list decides; lower-priority moments in
a claimed window are **skipped, not queued** (they are moments, not tasks):

1. Emergency / manual (absolute, unchanged authority)
2. Pre-drop blackout + drop cue (the floor-returned abort acts inside this window)
3. Landing build move
4. Blend resolve
5. Palate reset
6. First-play bloom
7. Phrase step / turnaround stinger
8. Texture seasoning (including drop-variant selection, which rides *inside* slot 2's cue
   rather than claiming its own window)

## 11. Switches, kills, and what remains when something is off

- **Master switch:** v1 or v2, live-switchable; switching tears down v2 instances through
  the existing reset/idle machinery and the newly-active brain takes over at the next
  dispatch. v2 off ⇒ v1 byte-identical.
- **Feature 1 off:** colors fall back to today's journey palettes; Feature 3 auto-collapses
  to the soft flip (no identities to blend); texture keeps its shapes with v1 colors.
- **Feature 2 off:** builds/landings/audio-matched blackout off; the blackout reverts to
  the fixed 4-beat predark that exists in live config today; cues trigger on the beat as
  they do now.
- **Feature 3 off:** handover = soft flip only.
- **Feature 4 off:** role cues untouched by construction — the containment law guarantees
  coherent remaining behavior.
- The expansion phase delivers the full kill matrix: every behavior in this document mapped
  to exactly one owning switch, plus these dependency rules, before any spec is written.

## 12. Your hands (manual controls)

All existing surfaces carry forward unchanged in authority: layered static-override pads
(note-on stacks, recency-ordered), palette pads + palette lock/unlock (now also the
per-track color correction path), LED mute, rainbow, Laser Solo (arm/veto), and the Stream
Deck layered DMX compositor (orthogonal manual overlay). v2 adds pads via the same pattern:
engine v1/v2 switch, WILD/SET toggle, per-feature kills, and identity controls (lock
identity / queue color — the reserved color-engine live controls finally get their
surface). A held manual look survives every v2 moment, including `leds_only` drops and
blackouts, exactly per the standing authority rules.

## 13. What the analysis hears — and honestly can't

The analysis layer (schema v4) stores, per beat of every track: absolute loudness in six
bands, quarter-beat shape, harmonic vs percussive balance, sustained-tone levels,
distortion timbre, brightness, attack, onset density, and a frame-rate low-mid envelope —
plus per-track character scalars. It is proven deterministic, bit-compatible with the old
smart-drop path, and covers the whole decodable library. Every v2 behavior in this document
is driven by that data plus your markers.

What it **cannot** do (verified, and the design must never promise):
- Hear that a third chorus is "softer" when its energy measures equal to the first drop.
- Rank one growl as angrier than another when their levels measure the same (your ear
  wins; drop growls are treated uniformly).
- See formant/filter "wow-wow" wobble that moves timbre without moving level (a named,
  deferred extension exists if lights ever need it).
- Judge whether an energetic section is *musically* a drop — markers stay authoritative.

## 14. What the status screen tells you

Per track: engine (v1/v2), identity zone + color (logged at load so misfires are precisely
reportable), corrected-by-you flag. Per drop: presentation (LEDs/both/solo) with its reason,
drop-type classification with its reason, blackout decision (gap found, length, which rule
fired). Live: mode (WILD/SET), per-feature kill states, blend scalar, active texture class
and why. The LED Pad gains a "now playing identity" chip.

## 15. Acceptance and the road from here

Software tests are build gates; **your eyes on the room are the only acceptance gate** —
no feature is "done" until you sign off on the live look. The staged road:

1. **Expansion one-shot** (next): designs the full experience from this document + the
   strict-review charter — the zone map, the arbiter, the kill matrix, the color-slot
   contract, the consumer-rule pack (blackout rules, bass-forward beats, build-intensity,
   rate-ladder selection, simmer), the build-move details, the new-template roadmap (2–3
   new shapes per role family), and observability. Its work is falsifiable: the blackout
   rules must reproduce your walkthrough gaps from the shipped cache; the zone map must
   reproduce the STARsound/Can't Say Nah palette calls; and the **library-wide dry-run
   audit** must show every cached track with a defined outcome at every decision point,
   plus a ranked outlier list that becomes the targeted scrub-check set.
2. **The laser session** (you + Claude, separate conversation): catalog the two lasers'
   real MIDI vocabulary in haze; then beam personality packages per zone; then live
   audition and lock.
3. **Codex specs, Feature 1 → 2 → 3** (texture rides 1/2), each with tests, contracts, and
   kill switches; Codex implements; you gate live.

## 16. Provenance (agent-facing)

- Decision sources: `docs/research/spectral_palettes_arrival_crossfade_exploration.md`
  (locked agreement, addenda 1–21, corrections, v1→v2 mapping — superseded passages are
  marked in place), `docs/research/lighting_engine_v2_design_review.md` (rulings F-1..F-17,
  OLC-1..4, P-1..P-6, post-review decisions), `docs/research/lighting_engine_v2_strict_review.md`
  (S-1..S-7, T2-1..T2-11, OLC-A..C, the expansion charter §6),
  `docs/research/spectral_audio_analysis_redesign.md` (the v4 layer: design, proofs,
  Appendices A–G including the operator walkthroughs; S-4 corrections applied in place).
- v1 carryover claims (renderer physics, seams, pads, drop presentation, laser color/
  blackout authorities, live-config values) were verified in code at `f30f1e6`; per
  AGENTS.md §1, code wins over this document for *current* behavior — this document is
  authoritative for *intended v2* behavior.
- Research-derived numbers are tune-live starting values; two safety-flavored citations in
  the research rounds are known-fabricated and must never be imported as standards.
- Change contracts: v2 implementation work lands under the existing `led_govee`, `laser`,
  `config_schema`, and `spectral_analysis` contracts (extended per feature spec); this
  document joins the docs those contracts update.
