---
doc_status: current
truth_level: measured
last_verified_commit: 67b7d66
last_verified_date: 2026-07-09
validation_scope: read-only triage of the 2026-07-08 evening mix logs (~/Library/Logs/rb_ss_bridge/, sessions 18:22 / 19:40 / 20:31 / 21:50) cross-checked against current code (state_manager.py, filepath_resolver.py, led_identity_v2.py). Every count was computed from the JSONL logs, commands cited inline. No runtime/hardware action; the LED v2 identity store is EXONERATED; the defect is upstream in the Rekordbox reader's load-emission path. Fix direction named here; implemented and software-tested as AWR-160 (see Status below) — this doc remains the historical triage evidence, not the implementation record.
---

# Phantom-load palette flicker — read-only triage (2026-07-08 mix)

**Operator symptom.** "Color palettes are slightly bugged, not sure if they
correctly remember tracks."

**One-line answer.** The palettes *do* remember tracks — the v2 identity store is
deterministic. The flicker is a **Rekordbox-reader bug**: the reader announces a
rapid stream of *fake* track loads onto an empty/being-browsed deck, and the LED
engine faithfully repaints with each fake track's palette. The color/identity code
is downstream and innocent.

Claim labels: **confirmed** = computed from the log / read in code, command or
file:line cited; **assumed** = inferred from a documented mechanism; **unknown** =
not determined, reason given.

- **HEAD at triage:** `46fd9fb` (confirmed — `git rev-parse --short HEAD`).
- **Primary log:** `~/Library/Logs/rb_ss_bridge/bridge-20260708-215046.jsonl` (10,283 lines; `current.jsonl` symlink target).

---

## 1. The identity store is deterministic (confirmed — store EXONERATED)

Parsing every `[LED] identity deck=N zone=Z slot=S depth=D corrected=C key=K` line
(emitted at `state_manager.py:1749`):

- **160** identity assignments over **122** distinct track-keys.
- **28** keys were replayed during the set. **Zero** of them drifted — every replay
  produced the identical `(zone, hue_slot, depth)`. (confirmed)
- **Zero** NEUTRAL / provisional fallbacks all night; the spectral cache was hitting
  (`[SM] spectral-path source=v4-extract/…-cache` lines present). (confirmed)

Mechanism this matches: the key is `content_key(content_id, filepath)`
(`led_identity_v2.py:133`); `content_hash` is plain blake2b (deterministic,
`led_identity_v2.py:139`); the store freezes the first *measured* reading and won't
overwrite it (`IdentityStore.freeze`, `led_identity_v2.py:301-315`). Given a stable
key, the palette is fixed. So the store is not the bug.

## 2. The reader emits phantom track-loads (confirmed — root cause)

A deck holds exactly one track at a time. Tonight the reader disagreed, hard.
Counting `[SM] load deck=N title=… gen=G src=rb_state` (emitted from the
FILEPATH_RESOLVED handler; `meta.content_id` is set at `state_manager.py:2388`):

- **168** track-loads in one mix (deck1 = 90, deck2 = 78); `load_gen` climbed to
  90 / 78. The operator did not load 168 tracks. (confirmed)
- **81** distinct titles on deck 1, **62** on deck 2. (confirmed)
- **13** rapid-reload storms (≥4 loads with <1.5 s gaps), holding **100** of the 168
  loads. (confirmed)
- **125 of 160** palette assignments (78%) landed inside these storms. Worst single
  burst: deck 1 cycled through **19 distinct tracks spanning all six color zones in
  ~28 s**; a deck-2 burst hit 18–21 keys. (confirmed)

Verbatim slice — deck 2, ~2 seconds, `gen=44…52`, nine different tracks (confirmed,
raw from `current.jsonl` around ts `1783564697–1783564703`):

```
gen=44  Dark Horse Remix EXTENDED MIX
gen=45  Britney Spears … Baby One More Time
gen=46  Wocka Flocka Flame … No Hands
gen=47  Sexy Follow (Sotschi Mashup)
gen=48  COBRA STARSHIP - YOU MAKE ME FEEL
gen=49  CALVIN HARRIS - SWEET NOTHING
gen=50  COBRA STARSHIP  (again)
gen=51  Lana Del Rey - Summertime Sadness
gen=52  Come alive …
```

Each fake load ran the full pipeline — `[ANLZ][DIRECT]` (new USBANLZ UUID each time)
→ `[FRES] resolve` (`content_id = str(c.ID)`, `filepath_resolver.py:289`) → anlz
worker → identity emit (`state_manager.py:2207`) → new palette. The engine has no way
to know the "track" is fake, so it paints it. **That is the flicker.**

## 3. Load path vs position path disagree at the same instant (confirmed — the lever)

During the deck-2 storm above, the *position* reader reported deck 2 as empty:

```
[SM] pos deck=2  0:00.109  bpm=0.0  live_bpm=114.9  mode=autoloop  file=<none>
[SM] pos deck=1  0:50.440  bpm=130.0  live_bpm=130.0  mode=scripted  file=Demi Lovato - Cool For The Summer …
```

So at the very moment the *load* path shouted "Dark Horse loaded on deck 2," the
*pos* path correctly said `file=<none> bpm=0.0` at position `0:00`. Deck 2 was idle /
at zero while deck 1 played; the phantom loads are the operator **browsing his library
for the next track**, with the highlighted/preview rows leaking through as loads
(browse-cursor bleed). The two read paths hold contradictory truth — the load-emission
path is missing the readiness gate the pos path already applies. That gap is the
root-cause lever. (confirmed the disagreement; browse-as-source is **assumed** from
the empty-deck + rotating-title pattern.)

## 4. Escalation timeline (confirmed)

Storms were not constant — they built through the evening:

| Session log | Loads | Storms (≥4 loads) | Loads in storms |
|---|---|---|---|
| `bridge-20260708-182236.jsonl` (18:22) | 3 | 0 | 0 |
| `bridge-20260708-194051.jsonl` (19:40) | 2 | 0 | 0 |
| `bridge-20260708-203103.jsonl` (20:31) | 38 | 4 | 19 |
| `bridge-20260708-215046.jsonl` (21:50) | 168 | 13 | 100 |

Early sessions were clean; the 21:50 session was ~4× worse than 20:31 and ~50× the
load count of the early sessions. Why it escalated is **unknown** (see §6) — could be
heavier browsing late in the night, or a Rekordbox/reader state that degrades over a
long session.

## 5. The four triage questions, answered

- **(a) Same track, different zones across plays?** No churn at the key level —
  deterministic (§1). What *looks* like churn is the reader swapping in different
  phantom tracks, not the store forgetting. (confirmed)
- **(b) Cache misses falling back to NEUTRAL?** No. Zero NEUTRAL/provisional palettes
  tonight; spectral cache hitting. Ruled out. (confirmed)
- **(c) content-id / key_hash instability?** The hash is fine (deterministic blake2b).
  The instability is that the reader assigns *different tracks* — hence different
  `content_id`s — to an idle deck. Upstream, not in the identity math. (confirmed)
- **(d) AWR-152 round-1 interplay?** None. The defect lives entirely in the Rekordbox
  reader / load-emission path, upstream of every LED color/identity file AWR-152
  touched. AWR-152 is not implicated. (confirmed)

## 6. Named unknown (next step)

**Which memory read leaks the browse cursor is UNKNOWN.** The symptom traces cleanly
to the load-emission boundary (`load_gen` advancing + `FILEPATH_RESOLVED` firing for a
deck that pos-reads as `file=<none> bpm=0.0`), but I did not open `rb_memory.py`,
`rb_offsets.py`, or `active_deck_resolver.py` to pin the exact offset/pointer that
picks up Rekordbox's library-browse / preview highlight. That is the next step to get
the true source fix rather than a downstream gate.

Fix directions (named, not specced): gate `load_gen` advance / `FILEPATH_RESOLVED`
emission on real deck readiness — position > 0 or bpm > 0 or actually-playing, or
require the same track across N consecutive reads before treating it as a load. This
belongs at the reader / load boundary, **not** in the color engine. Sibling context:
`deck2_reader_diagnosis_2026_07_08.md` (the deck-2 reader was exonerated for a
*different* 07-08 defect; the readiness-gate weakness noted there is consistent with
this finding).

---

**Status.** AWR-160 (2026-07-09 overnight) closed the "stability gate, not a
readiness requirement" fix direction from this triage: `rb_state_reader.py:_tick_deck`
now requires a candidate track title to read identically for 3 consecutive
ticks before `TRACK_LOADED`/`ANLZ_PATH` fire, software-tested including the
FEIN load-never-played case this triage flagged as a risk of a readiness-based
gate. The named unknown above (which memory read leaks the browse cursor) is
still open — it was not pinned, only fingerprinted: every discarded
pre-stability candidate now logs a throttled DEBUG line and an edge-triggered
INFO storm summary carrying the leaking read's fields, for a future pass to
pin the exact offset/pointer without another live triage. See
`docs/status/active_work_registry.md` (AWR-160) for implementation status;
operator's next mix is the live-verification gate.
