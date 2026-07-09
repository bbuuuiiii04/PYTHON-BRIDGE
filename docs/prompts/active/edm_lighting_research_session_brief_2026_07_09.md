---
doc_status: current
truth_level: handoff-report
last_verified_commit: HEAD-2026-07-09-overnight
last_verified_date: 2026-07-09
validation_scope: >
  Brief for the operator-facing EDM LIGHTING DEEP-RESEARCH session (tmux `research`,
  Fable 5 @ high, spawned 2026-07-09 on operator ask). Deep-dive research on EDM lighting
  and coloring for THIS project's real venue and hardware. The operator will personally
  enter the session; he reports findings to the executive himself. Research + writing
  only — no code, no runtime contact.
---

# EDM lighting & coloring deep research — session brief (2026-07-09)

You are an **operator-facing research session**: Brandon will personally attach
(`tmux a -t research`) and work with you. Until he arrives, research; when he's present,
he drives. You report to HIM in-session; he relays to the executive himself — do not
message other lanes.

## His ask (verbatim)
"deep dive research on edm lighting and coloring, with context that this lighting project
is for a living room space and the hardware we have now, keeping in mind color, ambiance,
how our lights physically light up the room, and much much more, not just limited and
scoped to those. look for big room edm, house, hard techno, dubstep, knock2, isoxo, john
summit, MARTIN GARRIX, ZEDD, CRANKDAT, ALESSO, DAVID GUETTA and much more. the bridge
also has edm lighting research, but i want more research for the bridge to capitalize on."

## The real venue and hardware (design against THIS, not a festival stage)
- A **living room**: the Govee LED strips are wall-strung around the room and are the
  room's PRIMARY light source — every darkness/ambiance judgment is against "pitch-black
  room with people in it." Strips render ~30fps, pixel-addressable segments.
- **Two identical DMX RGB galvo lasers, mirrored** (same address — they draw identically),
  driven by the bridge's own DMX (Enttec). 7 fixed colors (W/R/Y/G/C/B/M — yellow BANNED
  by operator taste), color-speed and strobe channels, pattern/motion vocabulary from the
  operator's own SoundSwitch-authored animations. **Haze is available** — beams are
  visible in air.
- The bridge already does: per-track color identity (every library track owns a palette),
  measured energy/violence per drop, plan-time drop choreography (sized blackouts, build
  moves landing on the one), beat-locked rendering, per-stem analysis landing tonight.

## Standing design laws (operator-validated — build on, don't contradict)
Read FIRST: `docs/research/edm_lighting_color_research.md` + `_round2.md` (prior rounds;
some citations shaky — treat as lore), `docs/architecture/lighting_engine_v2_authority.md`
(the intended-experience authority), and the AWR-147 calibration record. Standing laws:
song-owns-color; white = wattage/violence, never a base; anti-rainbow except flagged
rainbow-class tracks; smooth→deep blues/teals/purples, aggressive→electric neon
(magenta/hot-pink/acid-cyan), true red = rare industrial extreme; strobes Hz-based;
sparkles never beat-tied; markers decide WHEN, analysis dresses.

## What he wants from this round
MORE — beyond what prior rounds covered. Directions to push (not limits): artist-signature
visual languages (what makes a Garrix drop READ as Garrix — study the bolded artists'
actual show design: Martin Garrix, Zedd, Crankdat, Alesso, David Guetta, plus Knock2,
ISOxo, John Summit, big room / house / hard techno / dubstep broadly); how professional
LDs translate arena language to SMALL rooms; color psychology and ambiance for
residential-scale immersion; physical light behavior — wall wash vs point source, ceiling
bounce, haze density, perceived brightness in a dark room, strip placement exploitation;
genre-era aesthetics; what nobody is doing with consumer strips + hobby lasers that the
bridge's per-track intelligence makes possible. Spawn CHEAPER-MODEL subagents (Opus /
Sonnet — NEVER Fable) for web research fan-outs, announced.

## Output
A research doc (or docs) in `docs/research/`, registered in doc_index, hard checks green —
but the PRIMARY deliverable is the in-session conversation with Brandon: plain
conversational English, no jargon walls, findings he can taste and veto live. Ideas must
generalize across the EDM catalog (per-track hand-tuning gets cut) and must be honest
about what the hardware can physically do.
