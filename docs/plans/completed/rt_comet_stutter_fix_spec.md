# Codex Implementation Spec — Realtime Comet Chase Stutter Fix

**Implementer: Codex.** Live Rekordbox → SoundSwitch → Govee LED bridge. Wrong behavior is
visible to an audience. Implement exactly Part B. Do not redesign, do not edit
`config/led_look_director.json`, do not restart/deploy the bridge.

---

## Part A — Context & root cause (verified)

**Symptom (operator):** realtime "comet chase" cues launch on the beat but the comet does **not
travel smoothly** — it jerks across ~5 of 20 LEDs and snaps back every beat ("sends on beat but
stuttery"). It was smooth before the beat-sync engine landed.

**Root cause — the comet renderer is never reached for the groove-chase looks.** The smooth
full-strip comet (`GoveeFrameRenderer.render_comet`) is only invoked in the `_compose_frame`
**`overlap`** branch. But nothing resolves the groove-chase looks to `overlap`:

- `govee_frame_renderer.py:default_sync_mode()` only special-cases `_RETRIGGER_EFFECTS`, then
  returns `"continuous"`. It **never consults `_OVERLAP_EFFECTS`**, even though the
  `groove_chase_*` family is defined there. Verified:
  ```
  default_sync_mode("groove_chase_blue") == "continuous"   # in_OVERLAP=True  ← bug
  ```
- So `rt_groove_chase_blue` (no `sync_mode` in config) resolves to `continuous`, and
  `_compose_frame`'s **else** branch renders the legacy `_dual_chase` (a 4-beat ring), ignoring
  `travel_beats` and never launching on the beat.
- The test look `rt_blue_chase_overlap_every_beat` sets `sync_mode:"retrigger"`. Retrigger also
  falls to the else branch → legacy `_dual_chase` fed `beat_pos = ir.local_beat`, which **resets to
  0 every beat**. With `_dual_chase(loop_beats=4)` the head only sweeps segments `0 → ~4.9 of 20`,
  then snaps back. **That is the stutter.** Verified by simulating the real engine (126 BPM, 60 fps,
  `travel_beats=1`):
  ```
  frame  local_beat  head_seg(of 20)
    28     0.9800       4.900
    29     0.0000       0.000   <== RESET every beat  (only ~5/20 LEDs traversed)
  ```

**The fix idea:** comet effects (`_OVERLAP_EFFECTS`) must always render via `render_comet`
(progress-based, full-strip), and default to `overlap` mode. `render_comet` uses
`progress = local_beat / travel_beats`, which travels the full strip smoothly in **all** modes
because `local_beat` is monotonic wall-time × bpm. Verified for both looks after the fix:
```
retrigger, travel=1:  one comet sweeps 0→17.5→reset 0 each beat (clean single comet/beat)
overlap,   travel=2:  comets launch each beat, travel full strip over 2 beats, overlap 1→2→3 heads
```
This fixes **both** looks with **zero config edits** (`rt_blue_chase_overlap_every_beat` stays
`retrigger` and now yields a clean single comet; `rt_groove_chase_blue` now defaults to `overlap`).

---

## Part B — Tasks (implement exactly)

### Task 1 — `default_sync_mode` maps overlap effects (`govee_frame_renderer.py`)

**Current (~line 674):**
```python
def default_sync_mode(name: str) -> str:
    name = str(name)
    if name in _RETRIGGER_EFFECTS:
        return "retrigger"
    return "continuous"
```
**Replacement:**
```python
def default_sync_mode(name: str) -> str:
    name = str(name)
    if name in _OVERLAP_EFFECTS:
        return "overlap"
    if name in _RETRIGGER_EFFECTS:
        return "retrigger"
    return "continuous"
```

### Task 2 — `is_comet_effect` helper (`govee_frame_renderer.py`)

Add right after `_OVERLAP_EFFECTS` / `_RETRIGGER_EFFECTS` are defined (before `default_sync_mode`):
```python
def is_comet_effect(name: str) -> bool:
    """True for effects whose realtime render is the traveling comet primitive
    (render_comet), as opposed to a legacy _EFFECTS function."""
    return str(name) in _OVERLAP_EFFECTS
```

### Task 3 — route comet effects through `render_comet` in every mode (`govee_realtime_runner.py`)

Import the helper. **Current (line 10):**
```python
from .govee_frame_renderer import GoveeFrameRenderer, default_sync_mode, default_beat_division
```
**Replacement:**
```python
from .govee_frame_renderer import (
    GoveeFrameRenderer, default_sync_mode, default_beat_division, is_comet_effect,
)
```

Change the render branch. **Current `_compose_frame` (~line 248):**
```python
    def _compose_frame(self, spec: EffectSpec, instances: list) -> list[RGB]:
        # Runs on the runner thread; reading self._engine here is safe.
        segments = self._segments
        if not instances:
            return self._renderer.blank(segments)
        if self._engine.mode == "overlap":
            width = float(spec.params.get("width", 0.8))
            direction = self._engine.direction
            frames = [
                self._renderer.render_comet(
                    spec.effect_name,
                    progress=ir.progress,
                    segments=segments,
                    width=width,
                    direction=direction,
                    params=spec.params,
                )
                for ir in instances
            ]
            return self._renderer.fold_additive(frames, segments)
        ir = instances[0]
        return self._renderer.render(
```
**Replacement (only the branch condition changes — `overlap` → `is_comet_effect(...)`):**
```python
    def _compose_frame(self, spec: EffectSpec, instances: list) -> list[RGB]:
        # Runs on the runner thread; reading self._engine here is safe.
        segments = self._segments
        if not instances:
            return self._renderer.blank(segments)
        if is_comet_effect(spec.effect_name):
            # Comet effects always render via the traveling-head primitive, in
            # every sync mode: overlap folds several concurrent comets; retrigger /
            # continuous have a single instance, so this folds exactly one comet.
            width = float(spec.params.get("width", 0.8))
            direction = self._engine.direction
            frames = [
                self._renderer.render_comet(
                    spec.effect_name,
                    progress=ir.progress,
                    segments=segments,
                    width=width,
                    direction=direction,
                    params=spec.params,
                )
                for ir in instances
            ]
            return self._renderer.fold_additive(frames, segments)
        ir = instances[0]
        return self._renderer.render(
```
Leave the rest of `_compose_frame` (the legacy `render(...)` call) unchanged.

> Why both conditions: Task 1 makes `rt_groove_chase_blue` default to `overlap`. Task 3 additionally
> guarantees a comet effect can never fall back to the legacy `_dual_chase` even when configured as
> `retrigger`/`continuous` (e.g. `rt_blue_chase_overlap_every_beat`). The two are complementary;
> implement **both**.

---

## Part C — Tests

1. **`tests/test_govee_frame_renderer.py`** — the existing
   `test_groove_chase_defaults_to_continuous_named_scene` (~line 208) encodes the bug. Update it:
   ```python
   def test_groove_chase_defaults_to_overlap_named_scene(self) -> None:
       self.assertEqual(default_sync_mode("groove_chase_blue"), "overlap")
   ```
   Add an `is_comet_effect` assertion: true for every `groove_chase_*`, false for `beat_chase`,
   `breathe`, `twinkle_blue`, `groove_freestyle_nebula`.

2. **`tests/test_govee_realtime_runner.py`** — add a render-path test (reuse `_FakeTransport`,
   `_anchor`, `_tick_once` idioms):
   - **retrigger comet travels full strip & relaunches:** configure `groove_chase_blue`,
     `sync_mode="retrigger"`, `beat_division=1.0`, `travel_beats=1.0`. Drive a steady forward
     `abs_beat` at a fixed bpm for ~1 beat of ticks and capture frames. Assert the lit-segment index
     (argmax luminance) increases monotonically across the beat and reaches the **far half** of the
     strip (≥ `segments*0.6`) before the next beat reset — proving the comet crosses the strip, not
     the old ~5/20 stutter. Assert that on the beat crossing it resets toward segment 0.
   - **overlap comet count:** `sync_mode="overlap"`, `travel_beats=2`, `beat_division=1` →
     after 2+ beats, `engine.instance_count >= 2` and the folded frame has lit pixels in two strip
     regions.
   - **non-comet unaffected:** a `breathe`/`beat_chase` look still routes through the legacy
     `render(...)` path (e.g. assert it does not raise and produces a full-length frame).

3. Run `python -m unittest discover tests` (or the repo's standard command) — all existing tests
   stay green; the renamed/added assertions pass.

---

## Part D — Acceptance

- `default_sync_mode("groove_chase_blue") == "overlap"`; `is_comet_effect` true only for the 5
  `groove_chase_*`.
- In retrigger and overlap modes, `_compose_frame` for a `groove_chase_*` effect calls
  `render_comet` (never `render(...)`), and the comet head traverses the full strip.
- `rt_groove_chase_blue` and `rt_blue_chase_overlap_every_beat` both render smooth full-strip comets
  with **no `led_look_director.json` edits**.
- No change to non-comet effects, the trigger clock, manual-fire, wrap re-anchor, leak/teardown,
  or owner-lock paths.

---

## When you finish

Output a final fenced block titled `PASTE BACK TO CLAUDE` with: (a) files changed + one-line
rationale each; (b) any deviation from this spec and why; (c) exact test command + pass/fail
summary; (d) confirmation that non-comet effects and the engine/trigger/leak paths are untouched;
(e) request for Claude to review: comet routing in all three sync modes, the retrigger
single-comet full-strip traversal test, and that the `default_sync_mode` change didn't disturb
config validation or signature/reconfigure behavior.
