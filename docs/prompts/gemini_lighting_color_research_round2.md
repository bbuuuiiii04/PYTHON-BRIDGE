# Deep web research ROUND 2: EDM lighting color — genre deep-dives, numbers, and transitions

Round 1 produced `docs/research/edm_lighting_color_research.md` (read it first; do not repeat
it). This round goes DEEPER. Same readers as before: Brandon (DJ, plain language) and Claude
(design lead turning findings into rules for a fully-automated Govee-strip + laser home rig,
no operator mid-set, no per-song programming). Same citation discipline: URLs throughout,
label sourced fact vs inference, and if you can't source something important, say so. If any
round-1 claim looks wrong or weakly sourced on closer inspection, flag it in a corrections
section rather than silently repeating it.

## The five deep-dives (priority order)

1. **Bass music color language, in detail.** Our library is heavy on Crankdat, Knock2, ISOxo,
   Ray Volpe, Kai Wachi, Subtronics, Excision-adjacent sounds. Research the actual shows:
   Lost Lands, Bass Canyon, Excision tours, ISOKNOCK, the Sable Valley / trap wave aesthetic.
   What colors do these shows actually run per moment (build, drop, headbang section,
   melodic interlude)? Is the "electric neon (magenta/cyan/lime) + white violence" reading
   correct, or more nuanced? How do dubstep/riddim moments differ from trap/festival-trap
   moments in color?
2. **House / tech house color language, in detail.** The other half of our library: FISHER,
   John Summit, Odd Mob, Dom Dolla, club residencies (Hï Ibiza, Club Space Miami) and events
   (CRSSD, ARC). How do those rooms use color: monochrome washes? blue/teal/purple depth?
   warm amber moments? How does color behave during a 10-minute rolling groove with no big
   drops?
3. **Numbers — the micro-execution constants.** Anywhere professionals state actual values,
   collect them: how long is a pre-drop blackout (in beats or milliseconds)? What strobe
   rates (Hz) do pros use early-build vs late-build vs drop? How fast are color fades between
   looks (snap vs 1-beat vs 4-beat)? Attack/decay of a drop flash? Dimmer curves? Any
   numeric lore from console programming guides (grandMA3 busking layouts, cue timing
   fractions) counts. This section feeds engine constants directly — numbers with sources
   are worth more than adjectives.
4. **Transitions between songs — what an LD does during a DJ blend.** Round 1 covered drops;
   this round: the 1–3 minute crossfade between two tracks with different vibes. Does the LD
   pre-empt the incoming track's mood? Morph gradually? Hold neutral? Snap at the drop of the
   incoming track? How do festival LDs visually handle a genre switch mid-set (bass → house)?
   Any stated practice about color during EQ swaps / bassline swaps?
5. **Set-arc color pacing.** How do designers pace color across a full night — opening hour vs
   peak time vs closer? Do they deliberately save certain colors (or white ceilings, or
   strobe budgets) for later? Any "journey" philosophies (e.g., Eric Prydz sets, Anyma
   narrative arcs) that describe WHICH colors belong to WHICH chapter of a night?

## Also collect (secondary)

- **Two-color pairings pros actually use** (base + accent): blue+amber, magenta+cyan, etc. —
  with when/why. Our engine renders one base color per song plus accents; proven pairings
  feed the accent chooser and the blend grammar.
- **Vocal/emotional moments:** what happens to color when a big vocal or emotional breakdown
  hits, vs instrumental grooves?
- **Consumer-strip translations:** anyone credible documenting pro-style design on LED strips
  / small DIY rigs — what reads well and what fails on a strip compared to a fixture rig.

## Our constraints (unchanged — judge everything against these)

Govee RGB strips (~30 fps, whole-strip or few segments) + MIDI lasers; no moving heads,
blinders, CO2, video, haze; fully automated (no human on lights); per-song signals: measured
grit/punch/bass/drama, Rekordbox key + drop/build/breakdown markers, live beat/BPM, deck
faders. Locked design (build on, don't relitigate): each song owns a permanent color;
smooth songs → blues/teals/purples; aggressive songs → electric neons (magenta/pink/acid
cyan) with white-hot peaks; true red rare; energy owns brightness; drops always full power;
blends follow the fader.

## Deliverable

Write `docs/research/edm_lighting_color_research_round2.md`:

1. Bass music color language (the deep dive, cited)
2. House/tech-house color language (cited)
3. **The numbers table** — every timing/rate/duration found, with source and how confident
4. Transition/blend practice (cited)
5. Set-arc pacing (cited)
6. Secondary findings (pairings, vocal moments, strip translations)
7. Corrections to round 1, if any
8. **New transferable rules** — up to 15 NEW rules (don't repeat round 1's), ranked by fit to
   our constraints, one line each: rule, why, source
9. Sources — full URL list

## Boundaries

Web research + writing that ONE report file only. Read the round-1 report and prompt for
context. Do not modify any other file, no git commands, no installs, no code changes.
