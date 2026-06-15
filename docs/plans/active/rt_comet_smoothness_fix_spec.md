# Codex Implementation Spec — Realtime Comet Visual Smoothness (segment stepping)

**Implementer: Codex.** Live Rekordbox → Govee LED bridge; visible to an audience. Implement Part B
exactly. Do NOT edit `config/led_look_director.json`, do NOT restart/deploy the bridge. This is a
**pure renderer change** in `govee_frame_renderer.py` — no engine/runner/transport edits.

---

## Part A — Context & root cause (verified live + in sim)

Operator report: the realtime comet chase (`rt_groove_chase_blue`, overlap) launches on the beat but
the motion is **broken into segment-by-segment increments** — "clear jumps from one segment to the
next, moves forward after a slight pause," not a smooth glide.

This is **not temporal**, verified:
- Bridge renders + sends a steady **~60 fps for 95 s** with no decay, `active=True`, `send_err=0`,
  and the permission gate never dropped (no anchor freeze).
- Changing config `fps` 30↔60 changed nothing.
- Engine `progress` advances smoothly (~0.35 LED/frame at 120 BPM) — confirmed by unit sim.

The defect is **spatial, in the renderer**. `_comet_frame` (govee_frame_renderer.py:70) draws a
**symmetric triangular blob with `width` clamped to ≥1.0** (config default `width=0.8` → 1.0), i.e. a
**1–2 LED dot**, and renders **no trailing tail** (`trail_beats` is used only for engine TTL, never
drawn). Worse, its `/ideal_sum` normalization makes the **peak brightness throb** full→half→full as
the head crosses each LED. Rendered output (brightness 0–9 per LED) as the head sweeps:

```
width=0.8 (clamped 1.0):              proposed head+trail comet:
 pos=0.0 |9...................|        pos=0.0 |93..................|
 pos=0.5 |44..................|        pos=0.5 |860.................|
 pos=1.0 |.9..................|        pos=1.0 |793.................|
 pos=1.5 |.44.................|        pos=1.5 |6860................|
 pos=2.0 |..9.................|        pos=2.0 |5793................|
   (1-LED dot, throbbing 9→4)            (stable head 9 + fading tail, glides)
```

A single narrow dot hopping across 20 LEDs reads as stepping no matter the frame rate. The fix: draw
a **bright head with an exponential fade trail** behind it (≥~5-LED footprint, stable head
brightness). This keeps several LEDs lit with overlapping gradients so center-of-mass motion is
perceived as a smooth glide. Validated in sim (the right column above).

---

## Part B — Tasks (implement exactly, `govee_frame_renderer.py`)

### Task 1 — module constants

Add near the other comet/effect constants (e.g. just above `_comet_frame`):
```python
COMET_MIN_HEAD_SOFT = 1.6   # leading-edge fade length, in LED segments
COMET_MIN_TRAIL_LEDS = 4.0  # minimum trailing-tail length, in LED segments
```

### Task 2 — rewrite `_comet_frame` as a head + trailing comet

**Current (govee_frame_renderer.py:70–100)** — symmetric triangular blob, normalized, no trail.
**Replacement:**
```python
def _comet_frame(progress: float, segments: int, color: RGB, head_soft: float,
                 trail_len: float, direction: int) -> Frame:
    """A comet: a bright head at `progress` with an exponential fade trail behind it
    (opposite the travel direction) and a short soft leading edge. Non-wrapping: the
    comet enters, sweeps, and exits the strip as progress goes 0 -> 1+. `head_soft`
    and `trail_len` are in LED segments."""
    if segments <= 0:
        return []
    pos = progress * segments if direction >= 0 else (1.0 - progress) * segments
    head_soft = max(0.5, float(head_soft))
    trail_len = max(0.5, float(trail_len))
    frame = [(0, 0, 0) for _ in range(segments)]
    for idx in range(segments):
        # d > 0 => this LED is behind the head (the trail side, along travel dir).
        d = (pos - idx) if direction >= 0 else (idx - pos)
        if d >= 0.0:
            intensity = math.exp(-d / trail_len)        # bright head -> fading tail
        else:
            intensity = max(0.0, 1.0 + d / head_soft)   # short soft leading edge
        if intensity > 0.0:
            frame[idx] = _scale(color, intensity)
    return frame
```
Remove the old normalization (`ideal_sum`) entirely; the exponential head is already brightness-stable.

### Task 3 — derive head/trail in `render_comet`

**Current (govee_frame_renderer.py:690–699)** calls `_comet_frame(progress, seg, color, width, dir)`.
**Replacement body of `render_comet`:**
```python
    def render_comet(self, name: str, *, progress: float, segments: int,
                     width: float, direction: int, params: Mapping[str, Any] | None) -> Frame:
        seg = max(0, int(segments))
        safe = params if isinstance(params, Mapping) else {}
        color = _color(safe.get("color"), _edm_color_for_look(str(name), 0.0)[0])
        travel = max(1e-3, float(safe.get("travel_beats", 1.0)))
        trail_beats = max(0.0, float(safe.get("trail_beats", 0.25)))
        head_soft = max(COMET_MIN_HEAD_SOFT, float(width))
        trail_len = max(COMET_MIN_TRAIL_LEDS, (trail_beats / travel) * seg)
        frame = _comet_frame(float(progress), seg, color, head_soft, trail_len, int(direction))
        clamped = [(_clamp_channel(r), _clamp_channel(g), _clamp_channel(b)) for r, g, b in frame[:seg]]
        if len(clamped) < seg:
            clamped.extend([(0, 0, 0)] * (seg - len(clamped)))
        return clamped
```
Keep the public signature unchanged (`width` still accepted; it now sets head softness). With the
live config (`travel_beats=2`, no `width`/`trail_beats`): `head_soft=1.6`, `trail_len=max(4.0, 2.5)=4.0`
— the validated smooth comet.

> Note (acceptable, no engine change required): the engine culls an overlap instance at
> `travel_beats + trail_beats`. With the floored 4-LED visual trail, the very tip of the tail
> (intensity < ~0.1) may be culled a fraction early. It is imperceptible; do **not** change the
> engine TTL for this fix.

---

## Part C — Tests (`tests/test_govee_frame_renderer.py`)

Two existing tests call `render_comet` (public signature unchanged) and assert the **old** blob
behavior — update their assertions, do not delete coverage:

1. `test_comet_frame_exits_strip` (~line 145): with a trailing comet, `progress=1.5` leaves a faint
   tail. Change the "fully dark" probe to a progress where the tail has fully exited (e.g.
   `progress=2.0`, head 2× strip length away) and assert ~all dark there; keep the `progress=0.0`
   lit-at-segment-0 assertion.
2. `test_comet_keeps_steady_brightness_between_segments` (~line 166): assert the **head** peak
   brightness is stable between on-segment (`progress=1/20`) and between-segment (`progress=1.5/20`)
   positions — the new exponential head should keep the max channel within a tight tolerance
   (e.g. within ~15%), proving the throb is gone.

Add:
3. `test_comet_has_trailing_tail`: at a mid-strip `progress`, assert multiple consecutive LEDs behind
   the head are lit with **monotonically decreasing** brightness toward the tail, and that LEDs ahead
   of the head are dark — proving a real head+trail shape (≥4 lit LEDs, not a 1–2 LED dot).
4. `test_comet_glides_smoothly`: sweep `progress` in fine steps; assert the brightness-weighted
   centroid advances monotonically and the **per-step centroid delta is bounded** (no large jumps),
   i.e. continuous motion.

Run `python -m unittest discover -s tests -p 'test*.py'` — all green (the comet-routing/runner tests
from the prior fix must stay green; only the renderer assertions above change).

---

## Part D — Acceptance

- `rt_groove_chase_blue` (overlap, `travel_beats=2`, no width/trail in config) renders a comet with a
  stable bright head and a ≥4-LED fading tail that glides smoothly — no single-LED hop, no peak throb.
- `width`/`trail_beats`/`travel_beats` overrides still respected; reverse direction still works.
- No change to the engine, runner, transport, trigger clock, overlap folding, or any non-comet effect.

## When you finish

Output a final `PASTE BACK TO CLAUDE` block: (a) files changed + one-line rationale; (b) any
deviation + why; (c) exact test command + pass/fail; (d) confirmation engine/runner/transport and
non-comet effects are untouched; (e) request Claude review the head+trail math, the throb-removal
test tolerance, the trailing-tail vs engine-TTL note, and reverse-direction correctness.
