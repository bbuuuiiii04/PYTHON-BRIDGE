# Codex Diagnosis Prompt — Realtime Comet Chase Stutter / Missed Beats

## Context

Repo: `/Users/bbui/rb_ss_bridge_v2/`
Live Rekordbox → Govee H612D realtime LED bridge (Razer DreamView UDP, 20 segments).
Operator reports `rt_groove_chase_blue` looks **laggy and robotic**: motion **stops and starts on
the beat**, sometimes **misses a downbeat**, especially on a **short looped track** (~9–15 s).

Beat-sync overlap runtime was implemented (`beat_sync_engine.py`, runner wiring). Bridge has been
restarted multiple times. Config currently has:
- `room_perimeter.realtime.fps: 60`
- `rt_groove_chase_blue.params: {"travel_beats": 2}` (overlap defaults: `beat_division=1`,
  `sync_mode=overlap`, `trail_beats=0.25`, `width=0.8`)

**This is a diagnosis task only.** Do not implement fixes, do not edit live config, do not restart
the bridge, do not commit. Produce evidence-backed root-cause analysis and a ranked fix plan.

---

## Reported symptoms (operator language)

1. Chase is **on beat** (good) but not smooth — **start / continue / stop / continue** per beat.
2. Sometimes **misses a beat** entirely (no comet launch on that downbeat).
3. Feels **laggy** even after raising fps from 30 → 60.
4. Worse or more noticeable on a **looped short track** (I Kissed Girl edit, ~126 BPM, ~9–15 s loop).

---

## Already ruled out / corrected

| Claim | Verdict |
|-------|---------|
| "Bridge wasn't restarted, still on old dual-chase code" | **Wrong signal.** `sync_mode` / `instance_count` are stripped by `state_manager._sanitize_led_adapter_status` before status.json — their absence does NOT prove old code. On-disk code has `BeatSyncEngine`. |
| "It's a strobe effect" | **No.** `groove_chase_blue` overlap uses `render_comet`; `allow_strobe: false`. |
| "60 fps didn't apply" | **Applied when bridge live.** Measured ~60.5 fps via `frame_index` delta while active. |

---

## Leading hypotheses (verify each with evidence)

### H1 — Overlap spawn design causes beat-synced pulsing (architectural)
- `beat_division=1` spawns a **new comet every downbeat**.
- Each comet is **dark after `progress > 1`** (`_comet_frame` exits strip).
- Additive composite peaks brightness at **segment 0 on every spawn** → rhythmic pulse, not glide.

**Check:** Log or script `InstanceRender.progress` and per-instance pixel sum across frames; confirm
brightness peaks align with `floor(abs_beat)` crossings.

### H2 — Loop wrap drops spawn (`spawn_on_wrap=false`)
- Bridge log shows loop wraps: `drift deck=1: backward jump 15281→66 ms (-15215 ms)`.
- `TriggerClock.advance()` sets `wrapped=True` on backward `abs_beat`; default `spawn_on_wrap=False`
  → **no comet at wrap**.
- Comet **motion** uses wall-clock (immune to wrap); **spawn clock** uses `abs_beat_pos` (not).

**Check:** Instrument `BeatSyncEngine.on_tick` across a scripted backward `abs_beat` jump; count
spawns before/after wrap. Correlate with operator "missed beat" on loop boundary.

### H3 — `MAX_CATCHUP=1` drops spawns after anchor jumps
- If `abs_beat_pos` advances >1 beat index between runner frames (beatgrid snap, loop, correction),
  `TriggerClock` caps spawns at 1 per tick.

**Check:** Log `(prev_idx, idx, spawn)` on every `advance()` during live play or replay session.

### H4 — Beat anchor discontinuity / permission gaps freeze frames
- Runner only animates when `get_active_beat_anchor()` returns non-None AND `permitted`.
- `_dispatch_led_automation`: `position_stale` is checked **before** `manual_override` — stale memory
  can set `_led_rt_permitted=False` even during manual realtime look.
- When anchor missing: `_idle_tick` **re-sends `_last_frame` without incrementing `frame_index`** →
  visible full stop.

**Check:** Sample `_led_rt_permitted`, `automation_gate_reason`, anchor presence, and
`frame_index` delta at 60 Hz for 10 s during manual `rt_groove_chase_blue`. Flag stretches where
`frame_index` stalls while `active=True`.

### H5 — Discrete strip + narrow head (rendering quantization)
- 20 segments, `width=0.8`, head position `progress * segments` → ~1 LED step per frame at 60 fps.
- Inherent stepping; may amplify H1 pulse perception but does not explain **missed beats**.

**Check:** Compute max segment-index delta per frame; compare 30 vs 60 fps.

### H6 — Transport / runner thread stall (infra)
- Non-blocking UDP; `send_error_count` was 0 in samples.
- Status file updates every ~0.5 s — do not confuse frozen status snapshot with frozen runner.

**Check:** Measure `transport.frames_sent` delta directly from in-process runner status or a short
live probe, not only status.json cadence.

---

## Files to read first

| File | Why |
|------|-----|
| `beat_sync_engine.py` | `TriggerClock.advance`, `MAX_CATCHUP`, `spawn_on_wrap`, overlap spawn/expire |
| `govee_realtime_runner.py` | `_tick_once`, `_idle_tick`, `abs_pos` interpolation, permitted gate |
| `govee_frame_renderer.py` | `_comet_frame`, `render_comet` — progress>1 behavior |
| `state_manager.py` | `_led_rt_beat`, `_led_rt_permitted`, `get_active_beat_anchor`, `_dispatch_led_automation` order (stale vs manual), `_sanitize_led_adapter_status` |
| `beat_math.py` | `_compute_beatgrid_position` — `abs_beat_pos` on loop |
| `diagnostics.py` | `DriftDetector` backward-jump warnings |
| `config/led_look_director.json` | live fps, `rt_groove_chase_blue` params |
| `/tmp/bridge.log` | `drift deck=1: backward jump` correlation with missed beats |

---

## Diagnostic tasks (do all that apply without live bridge changes)

### Task 1 — Reproduce in unit tests (no hardware)
Add **temporary diagnostic tests** (or a standalone script under `tests/`) that simulate:

1. **Steady forward `abs_beat`** at 126 BPM, 60 runner ticks/s, `travel_beats=2`, `beat_division=1`:
   - Assert spawn every beat index crossing.
   - Plot/progress series: any frame where all instances have `progress > 1` (all-dark gap)?

2. **Loop wrap**: `abs_beat` sequence `… 7.8, 7.9, 0.1, 0.2 …` with monotonic `now`:
   - Count spawns across wrap with `spawn_on_wrap=False` (current default).
   - Repeat with `spawn_on_wrap=True` for comparison.

3. **Forward seek**: single-tick jump `abs_beat` 0 → 3.5:
   - Assert `spawn_count` obeys `MAX_CATCHUP=1` (drops beats).

4. **Anchor snap**: alternate provider pattern mimicking SM updates every 50 ms with intermittent
   backward `abs_beat_pos` corrections — measure missed `floor(abs_beat)` crossings.

Delete or gate experimental tests before handoff unless operator wants them kept.

### Task 2 — Trace manual-look permission path
Confirm whether `position_stale` or other gates can clear `_led_rt_permitted` while
`manual_override=rt_groove_chase_blue` and deck is playing. Quote the exact branch order in
`_dispatch_led_automation` and `_dispatch_led_idle_ambient`.

### Task 3 — Quantify "pulse per beat" vs "missed beat"
Define measurable criteria:
- **Pulse:** max segment luminance peaks N times per M beats (Fourier or peak count on segment-0
  brightness).
- **Missed beat:** beat index crossing where `spawn_count==0` and no instance has `progress < 0.2`.

Run against simulated tick stream; report numbers.

### Task 4 — Status observability gap
Document that `sync_mode`, `beat_division`, `instance_count`, `spawn_count`, `pending_manual` are
**dropped** by `_sanitize_led_adapter_status` (realtime key whitelist ~line 680). Recommend which
keys to add for live diagnosis (report only — do not implement unless asked).

---

## Absolute rules

1. **Diagnose only** — no fixes, no config edits, no bridge restarts, no commits.
2. **Evidence over intuition** — every root cause must cite code path + test/log/replay proof.
3. Separate **by-design behavior** (overlap spawn pulse) from **bugs** (permission freeze, wrap
   spawn drop, MAX_CATCHUP loss).
4. Do not modify `config/led_look_director.json`.
5. If adding tests, they must not break `python -m unittest discover tests` (gate or skip
   hardware-only probes).

---

## Deliverable format

### 1. Executive summary (≤5 sentences)
What is causing stop/start on beat? What causes missed beats? What is inherent vs fixable?

### 2. Root-cause table
| ID | Cause | Type (design / bug / infra) | Evidence | Confidence |
|----|-------|----------------------------|----------|------------|

### 3. Timeline diagram (mermaid)
One beat cycle + one loop wrap showing: spawn events, instance progress, composite brightness.

### 4. Ranked fix options
For each: config-only vs code change, risk, expected visual impact. **Do not implement.**

Suggested options to evaluate:
- `spawn_on_wrap: true`
- `beat_division: 2`
- `travel_beats: 3–4`, `width: 1.2`
- Raise `MAX_CATCHUP`
- Wall-clock spawn clock decoupled from `abs_beat_pos`
- Sub-segment comet interpolation
- Fix `position_stale` vs `manual_override` ordering
- Expose engine fields in status sanitizer

### 5. Recommended next step
Single smallest change most likely to improve operator perception, with a concrete A/B test protocol
(what to send via `/tmp/rb_ss_bridge_v2_commands.jsonl`, what to measure, pass/fail bar).

---

## When you finish

Output a fenced code block titled `PASTE BACK TO CLAUDE` containing:
(a) root-cause table condensed;
(b) top 3 evidence artifacts (test names, log lines, code citations);
(c) recommended fix ranking;
(d) any assumptions or unresolved questions;
(e) explicit request for Claude to review: design-vs-bug split, loop-wrap spawn gap, permission
freeze path, and whether sub-segment interpolation is needed for acceptable smoothness on 20 LEDs.
