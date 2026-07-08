---
doc_status: current
truth_level: code-verified
last_verified_commit: 1b51c66
last_verified_date: 2026-07-08
validation_scope: read-only code trace plus an offline deterministic sampling simulation of the strobe gate; no runtime, bridge, or hardware action; the live post-ProcessType frame rate is unmeasured — labeled unknown throughout
---

# AWR-153 — Full-strip white strobe (`rt_drop_white_aggressive`): hold-then-stutter mechanism diagnosis

**Operator symptom (design input, his words):** the full-strip white strobe
"turns the LEDs full white, kinda holds for a bit, strobes kinda, very
inconsistent."

**Verdict: code defect.** The strobe gate is frame-rate- and stall-fragile by
construction. The executive's aliasing hypothesis is **confirmed — and
extended**: frame-gap jitter is the bigger term than mean fps, so the AWR-151
ProcessType fix improves the clean case but does NOT make this gate robust.
The durable fix is a frame-rate/stall-aware gate.

## 1. The mechanism, in three parts — [confirmed]

1. **The gate is a 29 ms window sampled statelessly.**
   `_drop_white_aggressive` renders `strobe_on = (beat % 0.25) < 0.0625`
   (`govee_frame_renderer.py:511`): a 0.25-beat strobe cycle with a 25% duty
   ON window. At 128 BPM that is a 117.2 ms cycle with a 29.3 ms ON window.
   Each rendered frame independently asks "is the beat inside the window right
   now?" — there is no memory, no guarantee any frame lands inside it. The
   in-code comment (`:505-510`) says the constants were designed for 40 fps
   ("~1 frame ON").
2. **The transport holds the last frame through any stall.** The runner
   renders one frame per tick and sleeps to the next slot with no catch-up
   (`govee_realtime_runner.py:251-265`); razer-mode frames REPLACE strip state
   and nothing decays between packets. A stall that begins on an ON frame
   freezes the strip **full white** for the whole gap; a stall on an OFF frame
   freezes it dark.
3. **The render loop was throttled and jittery when the operator formed the
   impression.** AWR-151 established the launchd ProcessType throttle
   (28-33 fps self-reported in production, flip-proven 28.1→60.0). The 82 ms
   p90 frame-gap figure comes from that perf lane [assumed — executive-supplied,
   not re-measured here]. Post-fix live fps is **[unknown]**: today's
   15:32 bridge log contains no fps fields yet (checked read-only).

## 2. Simulation — the math reproduces his exact words [confirmed, modeled]

Deterministic offline sampling of the real gate expression (per-frame
independent sampling; jitter modeled as a heavy tail — 10% of frames gain
~p90 extra delay; seed fixed). Designed flash = 29-30 ms.

| BPM | fps | jitter p90 | ON frames/cycle | cycles with NO flash | longest miss run | max white hold |
| --- | --- | --- | --- | --- | --- | --- |
| 128 | 28 | — | 0.82 | 18.0% | 1 | 36 ms |
| 128 | 28 | 82 ms | 0.67 | **32.6%** | **5 in a row** | **164 ms** |
| 128 | 33 | 82 ms | 0.75 | 25.0% | 5 | 160 ms |
| 128 | 40 | — | 1.14 | 0% | 0 | 25 ms |
| 128 | 60 | — | 1.76 | 0% | 0 | 17 ms |
| 128 | 60 | 82 ms | 1.09 | **30.9%** | 5 | **147 ms** |

Reading it back against his words:

- "turns full white, kinda holds for a bit" → a stall landing on an ON frame
  holds full white up to ~165 ms — **5.6× the designed 29 ms flash**.
- "strobes kinda" → at throttled fps, one flash per cycle degrades to 0.67-0.85.
- "very inconsistent" → up to 5 consecutive strobe cycles (0.6 s) with **no
  flash at all**, then runs of hits — the aliasing walks in and out of phase.
- The 60 fps + jitter row is the important one: **even with the ProcessType
  fix delivering 60 fps mean, stall-driven misses (~31%) and long white holds
  (~147 ms) persist whenever jitter recurs.** The fix helps the clean case
  (0% missed at steady 60) but the gate remains fragile against every future
  source of frame-gap jitter.

Model honesty: the jitter shape is modeled, not measured; the qualitative
match to the symptom is the claim, not the exact percentages. The zero-jitter
rows are pure sampling math.

## 3. Fix direction (for the follow-up spec — NOT implemented, NOT specced this round)

Frame-rate/stall-aware gate, two composable parts:

1. **Runner injects frame timing:** the runner knows its real cadence; inject
   `render_fps` (or beats-per-frame) into effect params per frame — the same
   runtime-injection pattern as `slot_colors` (never a static config key).
2. **Gate widens to guarantee coverage:** ON window =
   `max(0.0625 beats, ~1.5 frames worth of beats)` so at least one rendered
   frame lands ON in every strobe cycle at any achievable fps; optionally cap
   consecutive held-ON time by keying off frame_index so a stall cannot hold
   white longer than one designed flash.

The same fixed gate should carry the operator-requested **full-strip color
strobe family** (blue, cyan, green, red, red+white, blue+cyan, cyan+white) —
the colorways are being taste-tested as Template Lab drafts first; production
promotion rides this fix so the family is born robust.

## 4. Scope and status

Diagnosis only — no code changed, no bridge touched. Registered as **AWR-153**
in `docs/status/active_work_registry.md`. Next steps, in order: operator
visual session on the Template Lab colorway/subdivision drafts → executive
release → Codex implementation spec for the gate fix + colorway family under
the `led_govee` contract. SOFTWARE/ANALYSIS ONLY / HARDWARE-UNVALIDATED.
