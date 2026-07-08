# Deep web research: how top EDM productions design lighting COLOR

You are doing internet research for a DJ lighting project. Work end-to-end autonomously.
Your only outputs: extensive web research and ONE report file (path in "Deliverable" below).

**Who reads the report:** Brandon (a DJ/operator, not an engineer — write in plain language)
and Claude (the design lead of his automated lighting engine, who will turn your findings into
design rules). Cite sources with URLs throughout. Clearly label sourced fact vs your inference.

## Mission

Find out how the world's best EDM light shows decide **color** — who decides it, what rules
they follow, how color relates to the type/sound/energy of a song — and extract what a small,
fully-automated home rig can actually learn from them.

## Research questions (in priority order)

1. **The profession.** Who designs light shows for top DJs and festivals? Job titles and how
   the roles differ: lighting designer (LD), show designer, production designer, lighting
   director/operator, VJ. Find NAMED people with real sources — designers behind acts like
   deadmau5, Eric Prydz, Excision, Anyma, Swedish House Mafia, and festival stages like
   Tomorrowland / EDC / Ultra. Prioritize interviews, podcasts, talks, and trade-press articles
   (PLSN, Live Design, etc.) where they explain their COLOR decisions in their own words.
2. **Color philosophy.** How is color chosen relative to the music?
   - Genre conventions: techno vs trance vs bass/dubstep vs house — do pros follow color
     conventions per genre, and what are they?
   - Song identity: do famous tracks get signature looks/colors that repeat every show?
   - Song sections: what happens to color in intros, build-ups, drops, breakdowns?
   - Energy: is there an accepted mapping from musical intensity to color choices?
   - White vs color: when do pros use saturated color for mood vs white/blinders for impact?
   - The pre-drop blackout/dip: how established is it, how is it executed?
   - How do pros avoid the amateur "RGB rainbow vomit" look? What restraint rules do they state?
3. **Workflow reality.** Timecoded pre-programmed shows vs live improvised operating
   ("busking") on consoles like grandMA3/Avolites: what fraction of top shows is per-song
   authored vs improvised from palettes? Most important for us: **festival house LDs who busk
   for guest DJs whose tracks they've never heard — how do they choose color in real time?**
   That improvised-but-professional workflow is the closest analog to an automated engine.
4. **Structure moves.** The canonical lighting moves for build-ups, drops, and breakdowns that
   pros keep reusing, described concretely enough to imitate.
5. **Anti-patterns.** What do professional LDs say looks amateur or ruins a show (e.g., color
   changing every beat, constant strobing, no restraint)? Direct quotes preferred.

## Our system and limitations — judge every lesson against these

- Rig: consumer Govee RGB LED strips (whole-strip color, ~30 updates/sec) plus MIDI-controlled
  lasers. NO moving heads, NO blinders, NO CO2/pyro, NO video walls, NO haze, small room.
- Fully automated: no human touches the lights during a set — the DJ is busy mixing. No
  timecode, no per-song pre-programming, no cue calling. Everything must come from rules.
- Signals the engine already has per song: measured audio character (distortion/grit, drum
  punchiness, sub-bass presence, dynamic range), Rekordbox musical key, marked drop/build/
  breakdown positions, live beat/BPM/playhead, and the DJ's deck fader positions.
- Design decisions already locked (do not relitigate; build on them): every song owns a
  permanent identity color; energy controls brightness, not color; drops always hit full
  power; white is the "wattage" layered over the song's color at peaks; blends follow the
  fader.

## Deliverable

Write the report to `docs/research/edm_lighting_color_research.md` (repo-relative). Structure:

1. **The people** — named designers/roles with one-line color philosophies, each sourced.
2. **Color conventions found** — genre, energy, section, white-vs-color, with citations.
3. **Workflow reality** — timecode vs busking, and specifically how festival LDs busk color
   for unknown tracks.
4. **Transferable rules** — 15–25 concrete rules ranked by fit to OUR constraints above; one
   line each: the rule, why it works, source. This section is the point of the whole task.
5. **Do NOT copy** — practices that depend on hardware/humans we don't have.
6. **Sources** — full URL list.

## Boundaries

- Web research + writing that ONE report file. Do not modify any other file in this repo.
- No git commands, no installs, no code changes, no reading unrelated repo files.
- If a claim matters and you can't source it, say so explicitly rather than asserting it.
