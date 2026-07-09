---
doc_status: current
truth_level: code-verified + log-corpus-grounded (read-only diagnosis, no code changed)
last_verified_commit: f627853
last_verified_date: 2026-07-08
validation_scope: read-only diagnosis of the 2026-07-08 evening "last-song LED blackout" across 20 session logs in ~/Library/Logs/rb_ss_bridge/ plus source verification of state_manager.py / led_look_director.py / rb_memory.py / rb_state_reader.py / active_deck_resolver.py / scripts/ss_bridge_watcher.sh at commit f627853; the bridge was DOWN during analysis. No runtime behavior changed, no code written. THREE operator corrections (2026-07-08) reversed the original thesis — see §0. Conclusion: the deck-2 reader was HEALTHY during the faulty darkness; the darkness was a scripted-mode blank-role room_blackout during the crossover into the Knock2 mashup. The deck-2 reader single-source/dead-fallback findings are preserved as a LATENT risk, not tonight's cause. §7 fix shapes are direction, not an implementation authorization.
---

# Last-song LED blackout diagnosis — the reader was healthy; the role went blank (2026-07-08)

**What this is.** A read-only diagnosis of why the LEDs went dark during the last
song of the 2026-07-08 evening mix. It began as a deck-2 rekordbox-reader
investigation and, after three operator corrections plus log re-verification,
**exonerates the reader**: the deck-2 position and active-deck reads were healthy
throughout the faulty darkness. The real cause is a **blank-role `room_blackout`
default during the crossover into a scripted-mode mashup**. The deck-2 reader
weaknesses found along the way are real but latent — they did not fire tonight.

**Claim labels:** **confirmed** = verified against source at `f627853` or counted
from the logs; **assumed** = inferred from a documented mechanism; **unknown** =
could not be settled from available evidence; **operator-testimony** = the
operator's first-hand account (evidence, but instrument before trusting).

---

## 0. Correction trail (read this first)

This doc's original thesis was wrong. It was corrected in three steps:

1. **"Turned it off" meant the fallback, not the deck.** `RBSS_POS_CHAIN_SKIP_OBJC=1`
   is set deliberately (`scripts/ss_bridge_watcher.sh:152`); the ObjC scan is
   operator-disabled, not bug-dead.
2. **FEIN was never played.** The operator loaded FEIN and ended the night without
   playing it. So FEIN reading "paused at 0:02" is *correct*, not a freeze bug.
3. **The faulty blackout happened BEFORE FEIN.** It occurred during the Knock2
   mashup that was playing before FEIN; the FEIN load was the operator's
   **reaction** to the already-dark room, not its cause.

Net effect: the "deck-2 chain froze on a fresh load and caused the darkness"
thesis is **falsified**. The reader was healthy during the darkness (§3). The
cause is in the LED role path (§4).

---

## 1. The corrected one-line finding

**The faulty darkness was a blank-role `room_blackout` burst during the crossover
into the scripted Knock2 mashup — the LED role kept arriving empty while a track
played audibly, so the look director fell back to its `utility` blackout.** The
deck-2 position reader and the active-deck reader were both healthy the whole
time. No track load and no reader freeze triggered it.

Two separate things, kept distinct in this doc:

- **(A) Tonight's cause — §4:** scripted-mode / blank-role → `room_blackout`,
  firing repeatedly during a normal DJ crossover. An LED look-director /
  drop-presentation issue. Readers healthy.
- **(B) A latent reader risk — §5:** deck 2 runs on one position source with its
  ObjC fallback configured off and a freeze-blind health check. This did **not**
  cause tonight's darkness, but it is a real gap worth closing.

---

## 2. Corrected timeline (`bridge-20260708-203103.jsonl`)

The darkness window is **20:52:37 → 20:53:23, during the Knock2 mashup on deck 2**.
FEIN comes *after*.

| Time | Line | Event |
|---|---|---|
| 20:51:31–20:52:03 | 3929–4100 | Operator browses deck 2 — ~11 rapid loads (gen 11–21), a preview storm |
| 20:52:03 | 4115 | Knock2 mashup settles on **deck 2** (`mode=scripted`); plays 0:01 → 1:19 |
| 20:52:30 | 4182 | `switch 1->2 (fader_top)` — crossover: deck 2 becomes active |
| 20:52:36 | — | master 1→2; deck 2 `only_audible` |
| **20:52:37** | 4209/4211 | deck 1 (POP LOCK) pauses; **`look room_blackout role=utility`** — darkness onset |
| 20:52:37 → 20:53:23 | — | `room_blackout (utility)` burst, oscillating with brief buildup/drop/ambient looks; deck 2 stays `only_audible` and its position keeps advancing |
| 20:53:23 | 4307 | FEIN loads on deck 2 — the operator's **reaction** to the dark room |
| 20:53:26 | 4339/4343 | FEIN `[RBMEM][INVALID]` + `pause deck=2` + `switch 2->0 idle_no_audible` → idle-freewheel `rt_twinkle` |
| 20:53:27 → 20:56:11 | — | idle ambient (FEIN never played = correctly idle); clean shutdown |

**Onset is independent of the FEIN load:** darkness began at 20:52:37, 46s before
FEIN loaded.

---

## 3. Why the reader is exonerated **[confirmed]**

During the entire faulty-darkness window (20:52:37–20:53:19), with deck 2 playing
the Knock2 mashup:

- **Deck-2 position advanced smoothly and monotonically** — 16 consecutive `[SM]
  pos deck=2` samples: 0:01 → 0:04 → 0:10 → 0:16 → 0:21 → 0:27 → 0:33 → 0:39 →
  0:44 → 0:49 → 0:54 → 0:59 → 1:04 → 1:09 → 1:14 → 1:19. No wobble, no freeze.
- **Zero `[RBMEM]`/chain-INVALID events** during Knock2 play. The only tonight
  INVALID is at 20:53:26 (FEIN, after the darkness and after the reaction load).
- **The active-deck read was healthy** — every heartbeat in the window reads
  `deck=2 auth=only_audible` (one 1-tick `deck=0` flicker at 20:53:13 is the only
  exception). The deck was correctly resolved as the audible one.

So the operator's "a load on either deck invalidates the deck-2 chain mid-play"
lead is **not supported by tonight's log**: there was no load during Knock2's
play, and the deck-2 chain never degraded. And the "position wobble / INVALID
churn degraded role resolution" sub-lead is also **not supported** — neither
happened during Knock2. The role went blank while every reader was healthy.

---

## 4. The actual mechanism — scripted-mode blank-role blackout **[confirmed origin; persistence partly unknown]**

The `room_blackout` look is the look director's **default when the LED context
role is empty**: `role = "utility"` when `context.role` is blank
(`led_look_director.py:145-150`), and `utility` maps to `room_blackout`.

The blank role has a code-confirmed source. When the active deck's lighting mode
is scripted, the drop-presentation is ticked with **`drop_role="none"`** by design
(`state_manager.py:2555-2567` — "Required Behavior Test 9: zero policy activity
end-to-end on a scripted track"). The Knock2 mashup was `mode=scripted` on every
`[SM] pos` line, so while it was the audible active deck the drop-presentation
contributed a blank/`none` role each tick.

Corroborating the role-path (not reader-path) cause, the RGB events across the
window are all look-director/drop-lifecycle churn, never reader errors:

- 20:52:31 `[RGB] hold-engaged deck=2` → 20:52:37 `[RGB] hold-released
  reason=beat_backstop held_s=6.5` — the LED hold that was covering the crossover
  expires exactly at the darkness onset.
- 20:52:44 / 20:53:13 `[RGB] gate-reason-change reason=adapter_rejected` — looks
  rejected by the adapter, back to `clear` a beat later.
- 20:52:57 `[RGB] tactical-blackout-accepted phase=pre_drop` — a pre-drop
  blackout arming on the mashup.
- 20:53:23 `[SM] smart-drop-energy-shadow deck=2 anlz_elapsed=0:22 … 1:26` — the
  ANLZ/energy model disagreeing with itself by ~64s on the mashup's position.

**Confirmed:** the darkness is the blank-role/`utility` `room_blackout` default
(`led_look_director.py:145-150`), and scripted lighting mode feeds `drop_role=
"none"` (`state_manager.py:2555-2567`). **Unknown / needs instrumentation:** why
the blank role *persisted and oscillated for ~46s* rather than the scripted-mode
fail-open (comment at `state_manager.py:2559-2561`) restoring a lit look — the
interaction between the crossover, the prior autoloop track's leftover window
state, and the scripted fail-open is not resolved from logs alone (§6, Q-A).

---

## 5. The latent deck-2 reader risk (real, but NOT tonight's cause)

Preserved because it is a genuine gap the investigation surfaced — it simply did
not fire tonight (deck 2 was healthy in §3; FEIN's "freeze" was a real pause).

- **Deck 1 vs deck 2 asymmetry [confirmed].** Deck 1 is a deterministic pointer
  walk (`rb_memory.py:732-733, 774-789`), always resolvable. Deck 2 has no known
  fixed offset — its ObjC field is found by scanning for a counter moving at
  ~44,100/sec *while playing* (`rb_memory.py:677-724`; `probe_deck2.py:8-12`).
  Corpus: `[RBMEM][INVALID]` references deck 1 zero times, deck 2 24 times, across
  20 sessions.
- **The ObjC fallback is operator-disabled [confirmed].** `RBSS_POS_CHAIN_SKIP_OBJC=1`
  (`scripts/ss_bridge_watcher.sh:152`, with `RBSS_POS_CHAIN_DIRECT=1` at `:151`)
  gates `_skip_objc_when_chain` (`rb_memory.py:1201-1205`); the scan then engages
  only on ticks where the chain itself misses (`skip2 = _skip_objc_when_chain AND
  _chain_ok_last[2]`, `rb_memory.py:1307`). It was turned off to avoid the
  pre-AWR-148 multi-second GIL freezes.
- **The chain health check is freeze-blind [confirmed].** `chain_ok =
  (chain_snap is not None)` (`rb_memory.py:1404`); `read_live_pos_chain` returns a
  valid snapshot even when the value is frozen (`rb_memory.py:871-895`), inferring
  `playing = raw != prev_raw` (`:899`). So a *frozen* chain reads as "healthy,"
  never misses, and never lets the fallback back in. **This is the one to fix**
  even though it was not tonight's trigger: it is exactly the failure mode that
  would turn a real future freeze-while-playing into an unrecoverable dark room,
  with no working fallback behind it.

---

## 6. Open questions and rejected leads

**Rejected [confirmed against log]:**
- **"A load on either deck freezes the deck-2 chain mid-play"** — no load during
  Knock2 play; deck-2 position advanced smoothly (§3).
- **H1 "FEIN was paused, and that pause caused the darkness"** — FEIN was never
  played (correct pause) and loaded 46s *after* the darkness began; it is the
  reaction, not the cause.

**Primary open — Q-A: why did the blank role persist ~46s on a scripted, audibly
playing deck?** The look director should not sit on `room_blackout` while a deck
is `only_audible`. Candidates: the scripted-mode fail-open
(`state_manager.py:2559-2561`) not restoring a prior autoloop track's dark window
state; the phrase→role path emitting `none` on the mashup's irregular structure;
the adapter repeatedly rejecting the intended look. This is an LED look-director /
drop-presentation investigation, **separate from the reader** — likely its own doc.

**Latent — Q-B: does the deck-2 chain ever freeze while a track truly plays?**
Not demonstrated tonight (Knock2 advanced fine; FEIN was a real pause). Still
worth ruling out because the freeze-blind health check (§5) has no safety net.

---

## 7. Fix shapes (direction, not an implementation authorization)

**Priority (a) — tonight's actual cause.** A blank/`none` role must not produce a
room blackout while a deck is audibly playing. When `active_deck` is
`only_audible` and the role is empty, **hold the last real look** (or a safe
groove default) instead of falling through to `utility`/`room_blackout`
(`led_look_director.py:145-150`). This addresses the crossover-into-scripted burst
directly. Pair with Q-A instrumentation: log, each tick the look would go
`utility` while a deck is `only_audible`, the source of the blank role
(scripted-mode `none` vs phrase `none` vs adapter reject) so the exact persistence
path is named.

**Priority (b) — the latent reader risk (hardening).** Two coupled changes:
1. **Freshness-aware chain health.** `chain_ok` should require the value to be
   *advancing* while the playing-hint says playing, not merely non-null
   (`rb_memory.py:1404`, `read_live_pos_chain` at `:859-912`). A frozen chain on a
   playing deck must count as a miss so the fallback can engage.
2. **Conditional skip.** Skip the ObjC scan while the chain is healthy-and-advancing;
   engage the now-vectorized (AWR-148, `rb_memory.py:264-458`) scan when the chain
   goes stale. The original reason for disabling it (multi-second GIL freezes) no
   longer holds post-AWR-148, so the fallback can be re-enabled behind the
   freshness gate rather than left globally off.

**(c) — instrumentation to settle Q-B.** In `read_live_pos_chain`
(`rb_memory.py:~899`), when deck-2 `playing` flips False within N seconds of a
load, log `raw`, `prev_raw`, and (if a rekordbox play-flag byte exists at a known
offset) that flag — distinguishing a real pause from a frozen-while-playing field
in one session.

---

## 8. What this diagnosis did NOT do

No code changed, no tests changed, the (down) bridge was not touched, and nothing
in `~/Library/Logs/rb_ss_bridge` was modified. Tonight's darkness is attributed to
the LED role path, not the reader; the reader findings are preserved as latent
risk. The 15:13 session cross-check earlier in this investigation still holds
(the active deck flipped `1->2` at 15:13:13.497 and the scripted laser armed 2ms
later — no non-flip miss). The fix is a separate spec once Q-A instrumentation
names the exact blank-role persistence path.
