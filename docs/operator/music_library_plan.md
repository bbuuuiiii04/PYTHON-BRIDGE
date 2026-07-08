---
doc_status: current
truth_level: operator-working-file
last_verified_date: 2026-07-08
validation_scope: Brandon's music-library organization system, designed conversationally in the 1-1 lane. No repo code changes; no rekordbox DB writes — all library changes happen by Brandon's hands in the rekordbox UI.
---

# Brandon's Music Library Organization Plan

Working file for the 1-1 lane. Resume from here; don't make Brandon re-explain.

## The problem (agreed)
- ~800+ tracks, rekordbox 7.x, macOS.
- Adds ~40 at a time, only mixes the newest batch; the older hundreds get forgotten (recency bleed).
- Genre folders fail — tracks span many genres, so the folder never decides the next track.
- Inattentive ADHD: needs low-decision, checklist-shaped external structure, not willpower.
- More problems underneath, to be elicited a couple at a time.

## Agreed direction
Attack the **recency bleed first** (loudest problem), before any big reorg. Build a self-maintaining
"forgotten tracks" rekordbox intelligent playlist that resurfaces old/unplayed tracks on its own.
Then design the "what track goes where in a set" system on top.

## Verified rekordbox facts (2026-07-08, web-confirmed)
- Intelligent (smart) playlists exist. Path: right-click the **Playlists** section (lower-left) →
  **Create new Intelligent Playlist** → name → add conditions (criteria / operator / value) with +/− → OK.
- Available criteria include **DJ play count** and **Date Added**. There is **no "last played" date** field.
- Uncertain / to confirm on his screen: exact Date Added operators (does it support a rolling
  "older than N months", or only a fixed calendar date?), and whether the dialog has a match ALL/ANY toggle.

## Forgotten list — DONE (step 1)
Built "Forgotten" intelligent playlist, rule: **DJ play count = 0**. Result: **131 tracks** of ~800.
→ Confirmed: DJ play count IS populated in his library, so it's a usable signal. List self-maintains
(a track leaves it once he plays it out). Refinements (older-than-N-months, loosen to ≤1) deferred.

## The REAL problem (surfaced 2026-07-08, his words)
Finding the next track mid-mix eats ~**80% of his live time**. Genre organization actively hurts:
the tracks that mix well together cross genres. He named dubstep, trap, bass house, "in-between",
jersey club, ISOXO/Juelz-type trap, tech house — and good transitions jump between these (bass house →
jersey → ISOXO trap → tech house). Genre folders never answer the only live question: "what goes next?"

## Proposed direction (PENDING his veto)
Stop sorting by genre. Make **energy level the primary axis** — one label per track for how hard it hits
(e.g. 1–5, chill→peak). Rationale: mid-mix the real question is hold / lift / drop the energy, and energy
is the one axis that crosses all his genres (a bass house, jersey, and trap track can all be "a 4", any
works next). He filters to "show me my 4s" → every fitting track across genres, one glance.
- Mechanism (default, not yet his choice): rekordbox **MyTag** (multi-tag, native, nothing to install;
  scales to a second "feel" axis later).
- Anti-mountain: he does NOT hand-rate 800 tracks. Bridge already measures per-track energy → auto-fill
  is a real option → write up for the executive-manager chat (`docs/plans/active/music_library_automation_ideas.md`),
  don't build here. Today only: agree the energy labels.
- Next tiny step if he says yes: propose what the energy levels mean, he vetoes/adjusts.

## Trust gate: verify bridge energy on a labeled sample BEFORE auto-tagging (in progress)
Agreed principle: don't auto-tag 800 on faith. Test the bridge's energy read against Brandon's own
ear-labels on ~17 tracks he grouped himself, THEN decide whether to trust it. His labeled sample:

- **Bangers (expect high):** YTIGAF_2347457927 – Allenora; SPACE LACES – FORCE MAJEURE (Jackknife rec);
  smoke [4ura]; ISOXO – Fuck The Speakerz Up (Rayvolpe remix); Control Live Intro
- **Chill (expect low):** Utopia; Stay With Me (Extended); Prospa – Don't Stop (Script remix)
- **Euphoric hard hitters (expect high, euphoric feel):** TITANIUM (Twinsick remix);
  Rock Ur World x Lights (Dabin / Aura / Park); We Could Be Love (Odd Mob Extended remix)
- **Mainstage crowd rippers (expect high):** Tremor (Sensational 2014 Anthem); Animals (Botnek edit)
- **Tech House slappers (expect mid-high groove):** Shinyy Disco Balls (Extended); Turn Up The Bass
  (Extended remix); Lose Control (original mix); Walker & Royce / Odd Mob / Benni / Ola – Can't Say Nah

Pass = chill trio reads clearly lower than the bangers/rippers. If scrambled, don't use the auto-tagger.

### RESULT (2026-07-08): TEST FAILED — do NOT auto-tag energy off the spectral cache
- The bridge has **no stored field called "energy."** The v4 spectral cache (`~/Library/Application Support/
  RBSS Bridge/spectral_cache/v4/`, populated, ~660/801 = 82% coverage, actively growing) stores 8 acoustic
  TEXTURE scalars: grit, punch, drama (dynamic-range contrast), brightness_med, loudness_ref_db, + derived
  bass_duty. `drama` is the doc's "closest to energy" but is explicitly a LED-color axis, not an energy tier
  (`audio_spectral_features.py:118-121`, `spectral_cache.py:284-296`, `docs/research/spectral_audio_analysis_redesign.md:180`).
- A real per-track energy/"vibe" labeler exists (`energy_model.py`, `tools/analyze_anlz_energy_corpus.py`,
  groove/drive/contrast/peak) but has **NEVER been run** — zero output on disk; report is a template only.
- **None of the cached scalars match Brandon's ear.** Money proof: his CHILL pick **Utopia** = punch 1.48
  (highest of all 17), drama 19.3 (top). His BANGER **Force Majeure** = drama 8.0 (lowest), punch 0.67.
  The computer ranks them backwards from Brandon. Texture ≠ felt energy. Test caught it before 800 mislabels.

### PIVOT (pending his veto): capture HIS labels, don't trust the computer's
Brandon sorted 17 cross-genre tracks into bangers/chill/euphoric/mainstage/tech-house in ~10s and his labels
are correct exactly where the cache is wrong → HE is the accurate sensor. Direction: cheap capture of his own
vibe-family calls (tag-as-you-play, one tap, no 800-track marathon), not a computer-guessed 1–5 energy dial.
Note his mental model is ~5 vibe FAMILIES, not a single energy ladder — may reshape the tag scheme.
- Parked experiment for the executive-manager chat (NOT blocking): can the never-run energy labeler be made
  to match his ear? Run it, validate against these 17 labels, report. If it works, it backfills the rest.
  → goes in `docs/plans/active/music_library_automation_ideas.md`.

## Step 2 setup — MyTag vibe families (in progress, he said yes 2026-07-08)
Chosen mechanism: rekordbox **MyTag**, NOT color codes. Why not color: rekordbox 7 can't rename colors,
so color→family would be memorized = willpower (rejected). MyTag values are named text = external structure.
Verified rekordbox 7 facts: MyTag panel via tag icon (right of browser) or View→Show My Tag; 4 category
slots (Genre/Components/Situation/blank), renameable, up to 50 tags each, no 5th category; add tag via RIGHT-CLICK in the My Tag area → "Create My Tag" (the "+" instruction was wrong, corrected live);
tag = select track + click tag; filter = click a tag in the panel → library narrows to it; multi-tags in a
row = OR. Tags save to rekordbox DB (NOT the audio file) and travel to USB/CDJ on export.
Starter tag set proposed (his words shortened, editable): **Banger, Chill, Euphoric, Mainstage, Tech House**.
First tiny step handed to him: open panel → make a "Vibe" category → add the 5 tags → tag 3–4 known tracks →
click a tag to watch the list filter. Stopping point: confirm the filter works + flag any weird step.

## Boundaries
- No rekordbox DB writes; Brandon clicks in the UI, guided step by tiny step.
- Automation ideas (auto-tagging from spectral profiles, forgotten-gems surfacing tool) → write to
  `docs/plans/active/music_library_automation_ideas.md` and hand to his executive-manager chat; don't build here.
