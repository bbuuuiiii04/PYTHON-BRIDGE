---
doc_status: current
truth_level: handoff-report
last_verified_commit: HEAD-2026-07-09-overnight
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the MASTER VISUAL REFERENCE lane (operator mandate 2026-07-09 pre-dawn):
  one self-contained HTML page — master look library, zone/energy maps, tonight's
  changelog, 10 real example tracks with mm:ss timestamps computed from the REAL F2 plan
  code over cached v4 data, stems status, USB tutorial. ADHD-friendly visual design.
  Read-only on everything except the new deliverable files.
---

# Master visual reference — kickoff (2026-07-09)

Operator mandate (verbatim): "i also expect everything new cue look and every track
energy family mapping etc. i have adhd so i need some sort of visual reference and a
master library and changelog of things. and then 10 example tracks with timestamps of
what should happen... this includes stems and usb (a usb tutorial too and everything for
me to be informed abt it)."

## Deliverable
ONE self-contained HTML file: `docs/operator/master_light_library_2026_07_09.html`
(inline CSS, real color swatches rendered as actual colors, no external resources, works
opened straight from Finder). ADHD-friendly: short chunks, big headers, checklists,
visual over prose. Plus a 5-line `docs/operator/master_light_library_2026_07_09.md`
pointer with a doc header so the docs checks stay green.

## Sections (accuracy rules below are binding)
1. **Tonight's changelog** — plain English, from the registry rows: every fix and
   feature shipped (AWR-157/159/160/161+fix/laser config/163 F2/164 F4/170 if landed),
   one line each: what changed in the ROOM's behavior.
2. **Master look library** — parse `config/led_look_director.example.json` (the mirrored
   truth): every look by bank (drop / groove / buildup / post-drop), with its colors as
   REAL swatches, width/rate/params, which round shipped it, strobe vs sparkle vs chase
   class. Include the laser side: zone chase values (laser_color_map.json), the Energy
   Ladder behavior, solo tiers in one line each.
3. **Zones & palettes** — the 6 zones (GLACIER/DEEP_POOL/TWILIGHT/ION/VOLT/EMBERCORE +
   NEUTRAL) as color-swatch cards: what kind of sound lands there, example known tracks.
4. **The energy system, visually** — families (WALL/COMET/HOUSE/NEUTRAL), tiers 1-3,
   the darkness ladder (1/2/4/8/16/balloon) as a diagram, white-share rule, what the
   lasers do per tier (energy gate).
5. **10 example tracks with timestamps** — THE centerpiece. Use the calibration anchors
   (ILL, Can't Say Nah, STARsound pt3, DROP EM, Satisfaction, Cruel Summer,
   kidstopbreathing, Hide and Seek, FE!N, Caramelle — substitute only if cache-missing).
   For each: RUN the real plan code (`lighting_moments_v2` pure functions over the
   cached v4 + markers, exactly as `state_manager` plan-time does) and convert beats →
   mm:ss via the track's beatgrid/BPM. Timeline per track: load (zone/palette), each
   build (move + balloon-or-black + window mm:ss), each drop (family, tier, look class,
   laser behavior), post-drop. Plain words per moment ("2:41 — room goes black for 4
   beats; 2:43 — drop hits as a WALL tier-2: colorway strobes, lasers fire the divided
   chase").
6. **Stems** — what it is in 2 sentences, tonight's outcome (read the pilot/sweep state
   from the stems lane docs/registry at build time — report honestly whatever it is),
   what it unlocks next, what it costs him (listening rounds gate any consumer).
7. **USB stick tutorial** — plain steps: what the stick is, current build state (read
   the AWR-122 registry row), how he'll build/refresh the DMG, first run on a foreign
   Mac (right-click-open, one-time admin grant), the test-the-lights button, what the
   host needs (Rekordbox 7.2.11 pinned — same version as home), known limits (RX3
   standalone impossible; performance mode = the way), signing state (unsigned until
   Xcode; 30-second re-sign later).

## Accuracy rules (binding — this is an operator-facing truth surface)
- Parse the REAL configs and RUN the REAL pure functions; never invent values. Every
  number on the page traces to config, registry, or computed plan output.
- Timestamps: verify beats→seconds conversion against the beatgrid for at least 2 tracks
  by hand before templating the rest.
- Label anything uncertain plainly ("not yet live-validated"). The whole page carries
  one banner: "software-tested tonight — your next mix is the live gate."
- Read-only on everything except your two deliverable files. No bridge, no pads, no live
  config. Commit explicit-path, hard checks green.

## Sentinels
Signal file per dispatch convention (TAG MASTERREF) + print MASTERREF-DONE / -BLOCKED.
The executive (superman3) reviews accuracy (2-3 track timelines re-derived) before it
reaches the operator.
