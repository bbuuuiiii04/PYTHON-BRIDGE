---
doc_status: current
truth_level: code-verified + log-corpus-grounded (read-only diagnosis, no code changed)
last_verified_commit: a98927a
last_verified_date: 2026-07-08
validation_scope: read-only forensic diagnosis of the deck-2 rekordbox reader across 20 session logs in ~/Library/Logs/rb_ss_bridge/ plus source verification of rb_memory.py / rb_state_reader.py / active_deck_resolver.py / led_dispatch_policy.py at commit a98927a; the bridge was DOWN during analysis. No runtime behavior changed, no code written. Names the mechanism and three instrumented-testable hypotheses; H2 is priority per operator testimony (both decks played the whole session incl. FEIN). Not implementation-authorizing.
---

# Deck-2 reader diagnosis — the "last-song LED blackout" root cause (2026-07-08)

**What this is.** A read-only diagnosis of why the LEDs went dark during the last
song of the 2026-07-08 evening mix and never returned, traced past the LED
subsystem into the rekordbox deck-2 position reader. The LED darkness was a
*correct* downstream reaction; the real fault is that the bridge stopped seeing
deck 2 as playing. This doc names the mechanism with `file:line` evidence and
leaves three instrumented hypotheses for the fix owner (Codex).

**Claim labels:** **confirmed** = verified against source at commit `a98927a` or
counted from the log corpus; **assumed** = inferred from a documented mechanism;
**unknown** = could not be settled from available evidence; **operator-testimony**
= the operator's first-hand account of the live session (evidence, but memory can
be wrong — instrument anyway).

---

## 1. The one-line reframe

**Deck 2 has a single working position source with a dead backup, and that
source's "healthy" test passes on a frozen value.** When the one source froze on
the FEIN load, both readers reported deck 2 paused, the active-deck resolver went
idle, and the LEDs parked on the dim ambient idle look. This is **not** an LED
bug and **not** a blackout latch — it is a rekordbox-reader fault.

---

## 2. Why deck 2 and not deck 1 — the structural asymmetry **[confirmed]**

Two completely different resolution strategies:

- **Deck 1 — deterministic pointer walk.** `base → container → DPU1 → inner1 → +0x0C`
  (`rb_memory.py:732-733`, `rb_memory.py:774-789`). Resolves the same way every
  tick, cached, independent of play state. Always available.
- **Deck 2 — no known fixed offset for its ObjC position field.** It is *found by
  scanning* memory near `inner1` for an int counting up at ~44,100/sec — i.e. by
  recognising a **moving** counter (`_strict_eval_candidate`, `rb_memory.py:677-724`;
  `probe_deck2.py:8-12` exists precisely because this field had to be discovered
  by scan). A counter can only be recognised **while the deck is playing and
  advancing**. A stopped or just-loaded deck 2 is, by design, unfindable this way.

Corpus proof: across all 20 sessions, `[RBMEM][INVALID]` references deck 1 **zero
times** and deck 2 **24 times**. There is no `_d1_pending`/`_deck2_inner`
machinery for deck 1 — the failure is deck-2-exclusive by construction.

---

## 3. The two deck-2 sources, and how the fallback died

Deck 2 actually has two position sources; the fault is that only one works and it
suppresses the other.

### 3a. The offset-table live_pos chain (the only working source) **[confirmed]**

`read_live_pos_chain` (`rb_memory.py:859-912`) walks a versioned offset chain
(`live_pos_per_deck[2]`) fresh every tick — `_follow_chain_addr` re-walks from
`base` with **no cached intermediate pointers** (`rb_memory.py:839-848`), so a
frozen reading means the field at that offset genuinely was not changing (not a
stale pointer). Play state is inferred from movement: `playing = raw != prev_raw`
(`rb_memory.py:899`). During the mix this chain carried deck 2 correctly (e.g.
Knock2 – 2HEARTS advanced 0:33 → 1:19).

### 3b. The `chain_ok`-suppresses-fallback mechanism (the core defect) **[confirmed]**

`read_live_pos_chain` returns a **valid snapshot even when the value is frozen** —
it returns `None` only on unreadable / negative / out-of-range / rewind
(`rb_memory.py:871-895`). So the health test is:

```
chain_ok = (chain_snap is not None)      # rb_memory.py:1404
skip2    = self._skip_objc_when_chain and self._chain_ok_last.get(2, False)  # :1307
```

A **frozen-but-readable** chain therefore counts as "healthy" → `skip2 = True` →
the entire ObjC heap-scan resolution pipeline is skipped (`rb_memory.py:1310`,
`_read_decks_chain_first` at `rb_memory.py:1392-1410`). **A frozen chain reads as
healthy and turns off the very fallback meant to catch it.**

### 3c. The ObjC fallback has been dead since Jul-8 afternoon **[confirmed]**

Even when it *does* run, the ObjC deck-2 scan has not resolved deck 2 in recent
sessions:

- Tonight (`bridge-20260708-203103.jsonl`): **11 resolution attempts, 0
  validated, 0 committed.**
- Zero `[RBMEM][D2COMMIT]` in every July-8 afternoon/evening session
  (`145239`, `153227`, `203103`). Only 2 commits exist across all 20 sessions.

Why it fails even mid-track: stage **B** always finds a decoy pointer
`ptr_b = (container − 0x270)[+0x78]` (`rb_memory.py:960-969`) that never
validates; stage **C** is the zone scan (`rb_memory.py:972-984`); and the stage
**D** heap scan that could find the *real* moving field is gated on
`target_ms is not None and not zone_hits and attempt >= min and deck2_playing`
(`rb_memory.py:1004-1011`). Whenever B/C surface any zone hit, `not zone_hits`
is false and **stage D never runs** — no `heap moving` scan line appears in
tonight's log at all. The decoy starves the scan that would succeed.

### 3d. The circular dependency that makes fresh loads worst **[confirmed]**

Stage D also needs `deck2_playing` and `target_ms`, and both come from the
StateManager, which is fed by the readers:

- `deck2_playing = self._deck_playing_hint(2)` (`rb_memory.py:1291`)
- `target_ms = self._deck_elapsed_hint(2)` (`rb_memory.py:1330-1332`)
- wired to `sm.get_deck_playing` / `sm.get_deck_elapsed_ms`
  (`__main__.py:1621-1622`).

On a fresh load the direct reader hasn't established the new track's play/elapsed
yet, so `target_ms=none` and `deck2_playing=False` gate the scan off. Corpus:
`target_ms=none` appears **26 times at attempt 2–30 with `playing=True`** — the
scanner repeatedly unable to get a reference position mid-playing.

---

## 4. `[INVALID]` vs `[INCONCLUSIVE]` — and why the label is only partly trustworthy **[confirmed]**

- **INCONCLUSIVE** (`rb_memory.py:1104-1105`, **DEBUG**): every candidate returned
  `None` — movement < 500 samples → "deck likely paused."
- **INVALID** (`rb_memory.py:1106-1107`, **INFO**): at least one candidate returned
  `False` (negative jump / bad rate / out-of-range) and none validated.

Two trust problems:

1. **It conflates a transient load-reset with a hard failure.** On a fresh load
   the old candidate resets → negative jump → `False` (`rb_memory.py:704-711`) →
   forces the "INVALID" label even though the true state is just "track changed a
   moment ago." `[INVALID]` does **not** mean "deck is unreadable."
2. **The paused case is invisible.** The entire 77k-line corpus has **zero DEBUG
   lines**, so `[INCONCLUSIVE]` ("deck likely paused") and the per-candidate
   `[RBMEM][REJECT]` reasons (`rb_memory.py:709/714/719`) never appear. You only
   ever see the INFO-level `[INVALID]` — the most alarming and least diagnostic
   variant.

---

## 5. Self-heal vs wedge **[confirmed]**

Retry loop retries indefinitely on intervals (`rb_memory.py:1317-1348`). Across
23 `[INVALID]` events:

| outcome | count |
|---|---|
| RECOVERED (deck-2 pos advanced past the frozen value, same track) | 12 (10–80s, median ~26s) |
| TRACK CHANGED before recovery could be observed | 10 |
| PERMANENT WEDGE to session end | **1 (tonight, 20:53:26)** |

Permanent wedge is rare (1 in 23). `read_deck(2)` returns `None` while
`_deck2_inner is None` (`rb_memory.py:1129-1130`), so during a wedge the ObjC path
contributes nothing and the (frozen) chain is authoritative.

---

## 6. Tonight's exact sequence — the wedge (`bridge-20260708-203103.jsonl`)

| Time | Line | Event |
|---|---|---|
| 20:47:23 | 3294 | `[RBMEM][INVALID]` #1 — recovered in ~16s (unremarkable) |
| 20:53:23 | 4307 | FEIN loads on deck 2; `health.reader drift: backward jump 83234→0 ms` |
| 20:53:26.8 | 4339 | `[RBMEM][INVALID] deck=2 all candidates failed strict validation` (the load reset) |
| 20:53:26.87 | 4342 | `[SM] pause deck=2 src=rb_state` (+71ms) — direct reader reports the field frozen |
| 20:53:26 | 4343 | `switch 2->0 (idle_no_audible)` → LEDs `[RGB] idle-freewheel-start look=rt_twinkle` |
| 20:53:27 → 20:56:11 | — | frozen; zero deck-2 activity; clean shutdown |

**Downstream chain (all correct given the frozen input):**
`active_deck_resolver.py:103-112` returns `idle_no_audible` / `no_eligible_deck`
→ `led_dispatch_policy.py:1313` dispatches the idle-ambient look and starts the
freewheel (`led_dispatch_policy.py:384-385`). `rt_twinkle` on the `deep_ocean`
palette renders as a sparse dim twinkle — "dead" during a loud last song.

**Independence caveat (correction to the first triage note).** The `src=rb_state`
pause is a *separate thread* but **not a separate signal**: both the direct reader
(`rb_state_reader.py:397, 437` — `is_playing = pos != prev`) and the chain reader
(`rb_memory.py:871, 899` — `playing = raw != prev_raw`) infer "playing" from
movement of the **same** `live_pos_per_deck[2]` field. Their agreement confirms
**the field froze** — it does not independently prove FEIN was paused.

---

## 7. The 15:13 "laser miss" premise — corrected **[confirmed from logs]**

The 15:13 session (`bridge-20260708-145239.jsonl`) had the *same* deck-2 INVALID
churn, but the specific "scripted-laser miss via active-deck non-flip" **did not
happen**:

- 15:13:01.041 (`:3148`) — `[RBMEM][INVALID] deck=2 all candidates failed…`
- 15:13:13.497 (`:3167`) — `switch 1->2 (bass_dominance)` — **active deck DID flip**
- 15:13:13.499 (`:3170`) — `arm deck=2 id=1284885839 elapsed=0:30.202` — **scripted laser DID arm** (2ms later)
- 15:13:13.612 (`:3172`) — `arm-phase2 deck=2 id=1284885839 elapsed=0:30.202`

The real symptom at 15:13 was **INVALID churn plus a position wobble**
(`pos deck=2` bounced 30.4 → 20.5 → 25.6 → 30.8 across 15:13:01–15:13:14), which
could cause subtle mistiming (armed at 30.2s while the live value was moving), but
**not** a missed trigger or a non-flip. The deck-2 fault family is real and
shared; the specific "non-flip laser miss" framing is not supported by that
session's logs.

---

## 8. The one thing logs cannot settle, and the operator testimony that resolves priority

Was the FEIN field frozen because **(a)** FEIN was genuinely paused, or **(b)**
the offset chain read the *wrong field* for a freshly-loaded deck-2 track while
audio actually played?

- **Operator-testimony (2026-07-08):** both decks were playing the whole session,
  **including FEIN**. This is first-hand evidence **against (a)** and tilts
  priority to **(b) — wrong field on fresh load**. (Evidence beats memory, so H1
  instrumentation still lands as the cheap confirm.)
- Log support for (b): the 15:13 position wobble proves the chain/scan *can*
  misreport deck-2 position during instability, and the dead ObjC fallback means
  nothing would catch a wrong chain.

---

## 9. Three instrumented-testable hypotheses (for the fix owner)

Priority order reflects §8: **H2 first**, then H3 (the missing safety net), with
H1 as the cheap confirm that runs regardless.

### H2 — the live_pos offset reads the wrong/stale field for a freshly-loaded deck-2 track **[unknown — priority per operator testimony]**
- *Instrument:* for ~10s after each deck-2 load, log (INFO) the chain-resolved
  address from `_follow_chain_addr` (`rb_memory.py:848`) and its raw value,
  alongside the best moving candidate the `inner1±window` scan finds and its rate.
- *Decisive test:* `probe_deck2.py` already performs this scan standalone — run it
  live against a freshly-loaded **and playing** deck-2 track and compare its
  `STRICT PASS` address to the chain's resolved address. **Same** address → the
  offset is correct (the freeze was real). **Different** → the offset points at the
  wrong field on fresh loads (the software bug), and the fix is an offset/anchor
  correction for the post-load deck-2 live_pos field.

### H3 — the ObjC deck-2 fallback is effectively dead in rekordbox 7.2.11 **[confirmed dead; mechanism to pin down]**
- *Evidence:* 0 commits across all July-8 sessions; stage D never ran tonight; the
  stage-B decoy `ptr_b` plus any zone hit gate stage D off (`not zone_hits`,
  `rb_memory.py:1004`).
- *Instrument:* promote the stage-B/C candidate addresses and per-sample deltas
  from DEBUG to INFO (`rb_memory.py:709/714`), and log which of
  `target_ms / zone_hits / deck2_playing / min_attempt` blocked stage D each
  attempt (`rb_memory.py:1004-1011`).
- *Test / fix direction:* one session shows whether B/C perpetually surface a
  static decoy that starves the heap scan. If so, validate B/C before trusting them
  enough to skip D, or run stage D regardless of zone hits. Note: if the fix makes
  stage D run, the **AWR-148 vectorized filter** (`rb_memory.py:264-458`) becomes
  load-bearing — verify its `target_ms` tolerance does not exclude the true moving
  field (`rb_memory.py:315-316`).

### H1 — FEIN was genuinely paused/previewed **[assumed low, per §8; run as the cheap confirm]**
- *Instrument:* in `read_live_pos_chain` (`rb_memory.py:~899`), emit one INFO line
  whenever deck-2 `playing` flips to False within N seconds of a load, carrying
  `raw`, `prev_raw`, and — if rekordbox exposes a play-state byte at a known offset
  — that flag too.
- *Test:* load a track on deck 2 and don't play it → expect frozen chain + this
  log; then play it → expect the chain advances. Distinguishes a real pause from a
  frozen-while-playing field in one session. Runs regardless of H2's outcome
  because operator memory, however confident, is still testimony.

---

## 10. What this diagnosis did NOT do

No code changed, no tests changed, the (down) bridge was not touched, and nothing
in `~/Library/Logs/rb_ss_bridge` was modified. AWR-148 was **not** implicated as
the cause of the wedge (stage D never ran); it is only relevant on the H3 repair
path. This doc is analysis, not an implementation authorization — the fix is a
separate Codex spec once H2/H3 instrumentation names the exact offset or gate.
