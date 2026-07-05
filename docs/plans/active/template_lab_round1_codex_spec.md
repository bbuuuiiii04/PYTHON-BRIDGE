---
doc_status: current
truth_level: implementation-spec
last_verified_commit: 89736bb
last_verified_date: 2026-07-04
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED repo status unchanged
---

# Codex Implementation Spec - Template Lab Round 1 (live-apply + variant switch + preview + skill adoption)

Parent direction doc: `docs/plans/active/template_lab_direction_2026_07_04.md` (operator approved
all three rounds 2026-07-04; §6 records the operator workflow decisions this spec implements;
this spec is Round 1 only). Recommended Codex effort: `medium`.

Operator workflow decisions shaping this round (direction doc §6): sessions are **variants-first**
(agent authors 2-3 takes, Brandon flips between them live on the strip and picks, then tunes),
**both driving modes** are first-class (talk-and-react via the agent API; hands-on via the UI),
devices include **iPad/phone** (touch-first for any new control), beat source stays the
**synthetic clock** (no Rekordbox-follow, no tap tempo — do not build either).

## Part A - Context & Root Cause (verified; read, do not implement)

All claims **[confirmed]** — read in current code at `89736bb` this session — unless labeled.

- Template Lab is live: `/lab` on the LED Pad server (`tools/led_pad_web.py:845-847`, port
  default 8766 at `:902`). Drafts live in gitignored `config/led_lab/` (`effects_lab.py` +
  `drafts.json`), managed by `LabRegistry` / `LabRenderer` (`tools/led_pad_lab.py`).
- Playback path: `LedPadService` constructs `LabRenderer(self._lab.module_path)` and hands it to
  `PadPlayback` (`tools/led_pad_web.py:213-220`), which drives the production
  `GoveeRealtimeRunner` (`tools/led_pad_playback.py:212-231`).
- **Root cause of friction 1 (every tweak restarts the cue):** the lab UI only calls
  `/api/lab/play` (`tools/led_pad_assets/lab.js:90-102`). The existing live-apply endpoint
  `/api/update` → `LedPadService.update()` (`tools/led_pad_web.py:667-681`) resolves names through
  the production look table (`_look_state`, `:500-516`) and therefore cannot address `lab_*`
  scenes. The runner underneath already supports live apply: params are split into a motion
  signature and a color signature (`govee_realtime_runner.py:433-438`, `_COLOR_SIG_KEYS`
  `:22-29`); a color-only change re-anchors without reconfiguring, a motion change calls
  `engine.configure(...)` at the **current** abs beat (`:282-303`). `PadPlayback.update()`
  (`tools/led_pad_playback.py:296-302`) sets the desired spec without restarting the `CueTimer`
  or the `SyntheticClock`.
- **Root cause of friction 2 (no preview):** the only render surface is the physical strip.
  `LabRenderer.render` is pure (`tools/led_pad_lab.py:175-189`) — offline frame rendering needs
  no transport, no ownership, no hardware.
- Reload semantics today: `lab_reload` (`tools/led_pad_web.py:590-598`) calls the standalone
  `load_lab_effects` — a syntax/registration check that does **not** swap the live renderer's
  effects. Only `_lab_play_spec` (`:609-629`) calls `self._lab_renderer.reload()`, which swaps
  `LabRenderer.effects` in place; on a failed reload it swaps to `{}` and the live render goes
  dark (fail-dark, the house failure direction). This spec's `lab_update` reuses `_lab_play_spec`
  and inherits exactly that behavior — intended.
- Param merge order for lab play: saved entry params overlaid by request payload params
  (`tools/led_pad_web.py:618-620`). Seed at play time: `stable_seed(look_name)`
  (`tools/led_pad_playback.py:24-26,251`) where `look_name` is the lab scene ref
  (`tools/led_pad_web.py:624`).
- Strobe: production strobe validation (`tools/led_pad_playback.py:257-265`) checks membership in
  `REALTIME_STROBE_EFFECTS` (`govee_frame_renderer.py:947,1828`); `lab_*` names can never be in
  that set (`tools/led_pad_lab.py:117-121`). **Operator decision 2026-07-04: discipline-only —
  do NOT add a code-level strobe rail in this round.** The rewritten skill text (Task 5) is the
  rail.
- API client: `window.LedPadApi` methods are thin `request()` wrappers
  (`tools/led_pad_assets/pad-core.js:123-144`).
- Existing test harnesses: `tests/test_led_pad_lab.py` (`_FakePlayback` at `:35`, registry/reload/
  renderer/preempt tests at `:71-115`) and `tests/test_led_pad_service.py` (pad-look `update()`
  coverage around `:236-251`). Follow their construction patterns.

## Part B - Tasks (implement exactly, in order; commit after each on `main`)

### Absolute Rules
- Touch ONLY: `tools/led_pad_web.py`, `tools/led_pad_lab.py`, `tools/led_pad_assets/lab.js`,
  `tools/led_pad_assets/lab.html`, `tools/led_pad_assets/pad-core.js`,
  `.claude/skills/template-lab/SKILL.md`, `tests/test_led_pad_lab.py`,
  `tests/test_led_pad_service.py`, and the docs listed in Task 6. **No bridge runtime modules**:
  do not edit `govee_frame_renderer.py`, `govee_realtime_runner.py`, `led_config.py`,
  `led_color_engine.py`, `state_manager.py`, or anything else at repo root.
- Behavior that must not change: pad-look `/api/play` and `/api/update` semantics; `/api/lab/play`
  request/response shape; ownership/takeover protocol; `lab_reload` staying a no-side-effect
  check; the `allow_strobe: False` field in the lab play spec (dead weight but harmless — leave).
- Error handling: propagate `ValueError`/`RuntimeError` to the HTTP handler's existing
  except-path (`tools/led_pad_web.py:869-870`, and the POST equivalent) — no new broad
  try/except, no success-shaped fallbacks. `lab_preview` returns
  `{"ok": False, "error", "traceback"}` for a broken sandbox module (mirror `lab_reload`'s
  shape), raises `ValueError` for unknown draft / unregistered fn / invalid LED config.
- Never run the bridge, never construct a real `GoveeRealtimeTransport` in tests (use the
  existing fake/dry-run patterns), never touch `config/led_lab/` outside temp dirs in tests,
  never commit anything under `config/`.
- Dirty worktree: other uncommitted changes may exist; never revert, checkout, or clean files you
  did not change; no `git clean`, no force-push, no branches.

### Task 1 - `tools/led_pad_lab.py`: pure preview-frame helper

Add a module-level function (after `load_lab_effects`):

```python
def render_preview_frames(
    renderer: "LabRenderer",
    scene_ref: str,
    *,
    params: Mapping[str, Any],
    segments: int,
    seed: int,
    fps: int,
    bpm: float,
    beats: float,
    max_frames: int = 2000,
) -> list[Frame]:
    total = min(int(max_frames), max(1, int(round(beats * 60.0 / bpm * fps))))
    frames: list[Frame] = []
    for index in range(total):
        t = index / float(fps)
        frames.append(renderer.render(
            scene_ref,
            beat_pos=t * bpm / 60.0,
            local_t=t,
            frame_index=index,
            params=params,
            segments=segments,
            seed=seed,
        ))
    return frames
```

Pure: no I/O, no clock, deterministic for fixed args. Callers are responsible for clamping
`fps`/`bpm`/`beats` (Task 2 does).

### Task 2 - `tools/led_pad_web.py`: `lab_update` + `lab_switch` + `lab_preview` + routes

1. Extend the import at `:27` to `from .led_pad_playback import PadPlayback, stable_seed`, and
   the import at `:26` to also bring `render_preview_frames`.

2. Add to `LedPadService`, next to `lab_play` (`:631`):

```python
def lab_update(self, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    entry = self._lab.get(name)
    scene = LabRegistry.scene_ref(name)
    if not self._playback.status().get("playing"):
        self._playing_name = ""
        self._last_play_editor = None
    if not self._playing_name or self._playing_name != scene:
        return {"ok": True, "applied": False}
    with self._lock:
        config = copy.deepcopy(self._draft)
    spec, _cue_beats = self._lab_play_spec(config, entry, payload)
    self._playback.update(spec)
    return {"ok": True, "applied": True, "spec": spec, "playback": self._playback.status()}
```

   Mirrors `update()` (`:667-681`): no cue-timer restart, no clock restart, no takeover.
   `cue_beats` changes deliberately do not apply until the next Play. `_lab_play_spec` reloads the
   sandbox module, so live code edits apply too; a broken module raises (surfacing the traceback
   string) after the live renderer has swapped to `{}` — the strip goes dark until fixed
   (intended fail-dark).

   Then the variant switch — seamless swap to a different lab draft while one is playing:

```python
def lab_switch(self, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    entry = self._lab.get(name)
    scene = LabRegistry.scene_ref(name)
    if not self._playback.status().get("playing") or not str(self._playing_name).startswith("lab_"):
        return {"ok": False, "error": "no_lab_scene_playing"}
    with self._lock:
        config = copy.deepcopy(self._draft)
    spec, _cue_beats = self._lab_play_spec(config, entry, payload)
    self._playback.update(spec)
    self._playing_name = scene
    self._last_play_editor = None
    return {"ok": True, "applied": True, "spec": spec, "playback": self._playback.status()}
```

   Same `update()` path as tuning, so the `SyntheticClock` and `CueTimer` are untouched: the
   beat keeps running and the runner reconfigures the engine to the new effect from the current
   beat — that is the point (A/B/C comparison without the lights stuttering). Deliberate limits:
   refuses when nothing is playing or when a **pad** look is playing (the UI falls back to
   `lab_play`, which carries the existing preempt + ownership semantics); with Loop off, the
   previous draft's remaining cue window still governs auto-stop (accepted; switching is a
   Loop-on workflow). Switching to a broken module fails dark exactly like `lab_update`.

```python
def lab_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    entry = self._lab.get(name)
    with self._lock:
        config = copy.deepcopy(self._draft)
        session = copy.deepcopy(self._session(config))
    renderer = LabRenderer(self._lab.module_path)
    result = renderer.reload()
    if not result["ok"]:
        return {"ok": False, "error": result["error"], "traceback": result["traceback"]}
    if name not in renderer.effects:
        raise ValueError(f"lab effect not registered: {name}")
    params = copy.deepcopy(entry.get("params") or {})
    if isinstance(payload.get("params"), dict):
        params.update(copy.deepcopy(payload["params"]))
    scene = LabRegistry.scene_ref(name)
    look = {"scene_ref": scene, "color_source": "engine"}
    self._inject_engine_colors(config, scene, look, params, force_slot=(str(entry["kind"]) == "slot"))
    led_config = self._load_config_result(config).config
    target = next((item for item in led_config.targets.values() if item.realtime.enabled), None) if led_config else None
    if target is None:
        raise ValueError("no realtime-enabled LED target in config")
    fps = max(1, min(40, int(payload.get("fps") or target.realtime.fps)))
    bpm = max(40.0, min(220.0, float(payload.get("bpm") or session.get("bpm") or 128)))
    default_beats = min(float(entry.get("cue_beats", 16) or 16), 8.0)
    beats = max(1.0, min(32.0, float(payload.get("beats") or default_beats)))
    frames = render_preview_frames(
        renderer, scene,
        params=params, segments=int(target.realtime.segments),
        seed=stable_seed(scene), fps=fps, bpm=bpm, beats=beats,
    )
    return {"ok": True, "frames": frames, "fps": fps, "bpm": bpm, "beats": beats,
            "segments": int(target.realtime.segments)}
```

   Uses a **fresh local `LabRenderer`** so preview never swaps the live renderer's effects
   mid-play, and never touches `self._playback` — no transport, no ownership, no UDP. The seed
   matches play (`stable_seed(scene_ref)` — same value `PadPlayback.build_spec` derives at
   `tools/led_pad_playback.py:251` since the lab spec's `look_name` is the scene ref).

3. Register all three in `_POST_ROUTES` (`:785-804`): `"/api/lab/update": service.lab_update,`
   `"/api/lab/switch": service.lab_switch,` and `"/api/lab/preview": service.lab_preview,`.

### Task 3 - `tools/led_pad_assets/pad-core.js`: API client methods

Next to the existing lab methods (`:141-144`):

```js
labUpdate: (body) => request("/api/lab/update", {method: "POST", body}),
labSwitch: (body) => request("/api/lab/switch", {method: "POST", body}),
labPreview: (body) => request("/api/lab/preview", {method: "POST", body}),
```

### Task 4 - `tools/led_pad_assets/lab.html` + `lab.js`: auto-apply + preview strip

`lab.html`: inside the detail panel, directly above the `tracePanel` details element
(`lab.html:57`), add:

```html
<div class="preview-row">
  <button id="previewBtn" type="button" class="ghost">◉ Preview</button>
  <canvas id="previewStrip" height="24" aria-label="Draft preview strip"></canvas>
</div>
```

(If `pad.css` lacks styling for `.preview-row`, add a minimal rule there — flex row, canvas
`flex:1; width:100%` — matching existing panel spacing. `pad.css` is in the allowed file set via
`tools/led_pad_assets/**`; keep the rule small.)

`lab.js`:

1. **Auto-apply while live.** Add after the existing `paramsInput.onblur` handler
   (`lab.js:140`) — programmatic `.value` writes do not fire `input`, so this cannot self-loop:

```js
let applyTimer = 0;
$("paramsInput").oninput = () => {
  clearTimeout(applyTimer);
  applyTimer = setTimeout(async () => {
    if (!state.current || state.playingLook !== labScene(state.current.name)) return;
    let params;
    try { params = JSON.parse($("paramsInput").value || "{}"); } catch { return; }
    try {
      const res = await api.labSave(currentPayload());
      state.current = res.entry;
      await api.labUpdate({name: state.current.name, params});
      clearError();
    } catch (err) { showError(err); }
  }, 400);
};
```

   Deliberately does **not** call `refresh()`/`renderDetail()` — rewriting the textarea mid-typing
   would steal the cursor. Sidebar "updated" dates staying stale until the next refresh is
   accepted. Invalid JSON mid-typing is silently skipped here; the existing `onblur` validator
   still reports it.

2. **Preview.** Add:

```js
const preview = {frames: [], fps: 40, raf: 0};
function stopPreview() {
  cancelAnimationFrame(preview.raf);
  preview.frames = [];
  const canvas = $("previewStrip");
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}
async function previewDraft() {
  if (!state.current) return;
  stopPreview();
  await save();
  const res = await api.labPreview({name: state.current.name});
  if (!res.ok) {
    $("traceText").textContent = res.traceback || res.error || "preview failed";
    $("tracePanel").open = true;
    throw new Error(res.error || "preview failed");
  }
  const canvas = $("previewStrip");
  canvas.width = canvas.clientWidth || 600;
  const ctx = canvas.getContext("2d");
  preview.frames = res.frames;
  preview.fps = res.fps;
  let start;
  const step = (ts) => {
    if (!preview.frames.length) return;
    if (start === undefined) start = ts;
    const frame = preview.frames[Math.floor((ts - start) / 1000 * preview.fps) % preview.frames.length];
    const w = canvas.width / frame.length;
    frame.forEach((rgb, i) => {
      ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      ctx.fillRect(i * w, 0, Math.ceil(w), canvas.height);
    });
    preview.raf = requestAnimationFrame(step);
  };
  preview.raf = requestAnimationFrame(step);
}
$("previewBtn").onclick = async () => {
  $("previewBtn").disabled = true;
  try { await previewDraft(); } catch (err) { showError(err); } finally { $("previewBtn").disabled = false; }
};
```

   The disable-while-in-flight guard matters: without it, two rapid clicks spawn two concurrent
   `previewDraft()` calls and `preview.raf` only tracks the latest animation loop — the orphaned
   loop keeps drawing until its frames drain.

   Call `stopPreview()` at the top of `selectDraft(...)` so switching drafts kills the animation.
   Note `previewDraft` reuses the existing `save()` (which calls `refresh()`) — acceptable here
   because Preview is an explicit click, not mid-typing. Disable/enable `previewBtn` with the
   other buttons in `renderDetail()` (add it to the disabled-ids list at `lab.js:57`). All new
   controls keep ≥40px touch targets (iPad is a first-class seat — match the existing pad.css
   sizing conventions).

3. **Variant switch.** In `play(takeover)` (`lab.js:90-102`), after the `save()` call and before
   the `labPlay` request: if a *different* lab draft is currently live, switch instead of
   replaying —

```js
const mine = labScene(state.current.name);
if (state.playingLook && state.playingLook.startsWith("lab_") && state.playingLook !== mine) {
  const sw = await api.labSwitch({name: state.current.name, params: JSON.parse($("paramsInput").value || "{}")});
  if (sw.ok) { await updateRuntime(); return; }
}
```

   (On `sw.ok === false` fall through to the existing `labPlay` path, which handles ownership
   and pad-look preemption.) And make the button say what it will do — in `renderLive()`:

```js
$("playDraftBtn").textContent =
  state.current && state.playingLook && state.playingLook.startsWith("lab_") &&
  state.playingLook !== labScene(state.current.name) ? "⇄ Switch" : "▶ Play";
```

### Task 5 - `.claude/skills/template-lab/SKILL.md`: replace entire file with this text

```markdown
---
name: template-lab
description: Use when Brandon asks for a new LED cue/template or wants to tune one — the AI-assisted flow for creating draft Govee renders in Template Lab, playing them live with placeholder colors, iterating on Brandon's feedback, and promoting accepted drafts into govee_frame_renderer.py via tests + contracts. Not for laser or SoundSwitch work.
---

# Template Lab — agent workflow

## 0. Ground rules (live safety first)
- Ownership first: check `GET /api/runtime_status` before any playback. If the bridge owns the
  LEDs (bridge status fresh <5s), ask Brandon before takeover — the pad UI takeover button is
  his call, not yours.
- STROBE — you are the only gate. Production strobe validation never fires for lab scenes
  (`lab_*` names cannot be in `REALTIME_STROBE_EFFECTS`; the check short-circuits). If a draft
  flashes: say so before the first play, stay at or under the house ceiling (the renderer's
  16th-note gate, ≤50% duty), and never leave it playing unattended.
- Never edit `govee_frame_renderer.py`, `led_config.py`, or any bridge module during lab
  iteration. Lab code lives ONLY in `config/led_lab/effects_lab.py`. Never touch
  `GOVEE_API_KEY`, device IDs, or live config. Never commit `config/led_lab/`.
- Label claims: rendered-in-lab ≠ validated-on-hardware ≠ show-ready. Use §10 status words.

## 1. Interview Brandon (short, concrete)
Ask at most: (1) which moment (groove/buildup/drop/post-drop/breakdown/ambient)? (2) what does
it look like in one sentence (object + motion + energy)? (3) nearest existing render (play 1-2
references from the pad if unsure)? (4) beat relationship (per-beat hits, N-beat cycle,
continuous)? (5) white accents (slot 5) or palette-only?
Translate to renderer knobs before coding: cycle length → `cue_beats`/`duration_beats`; speed →
`travel_beats`; object size → `width`/`trail_beats`; re-hit feel → `sync_mode` + `beat_division`.
Confirm the sentence back before writing code.

## 2. How the lab works (mechanics)
- Server: LED Pad web on `:8766`, lab UI at `/lab`. Agent API: `GET /api/lab/list`,
  `/api/runtime_status`; `POST /api/lab/save` (draft fields), `/api/lab/reload` (syntax +
  registration check — never touches lights; use after every edit), `/api/lab/play`
  `{"name", "params", "cue_beats", "takeover"}`, `/api/lab/update` `{"name", "params"}`,
  `/api/lab/switch` `{"name"}` (seamless swap to another lab draft while one plays — the beat
  keeps running), `/api/lab/preview` `{"name", "params"?, "beats"?, "bpm"?}`, `/api/stop`.
- Code: define the function in `config/led_lab/effects_lab.py`, register it in
  `LAB_EFFECTS = {"myname": ("slot", fn)}` — kind `"slot"` or `"frame"`. Create/update the
  draft entry via `/api/lab/save`, not by hand-editing `drafts.json` while the server runs.
- The module is fully re-imported on every Play, Update, and Reload; edits are live
  immediately, and a broken module fails the call with the traceback surfaced in the UI (a
  break during live play goes dark until fixed — fail-dark is intended).
- Signature (both kinds, 6 args): `fn(beat_pos, local_t, frame_index, params, segments, seed)`.
  Kind `slot` returns a MotionField (per-pixel slot intensities; slots 0-4 palette, slot 5
  white-reserved, `MAX_SLOTS` 6) and is colorized with Test Palette colors. Kind `frame`
  returns `[(r, g, b), ...]` directly — the full-RGB escape hatch.
- Lab-only constraints: drafts run `continuous` by default (`retrigger` via
  `params["sync_mode"]`); the engine's overlap/multi-comet folding is production-only — drive
  all motion inside your function from `beat_pos`. Play params = saved entry params overlaid by
  the play payload. `slot_colors` is runtime-injected — never invent it as a draft param.
- Live tuning: while a draft is playing, param edits in the `/lab` UI auto-apply (and the agent
  can `POST /api/lab/update`). Color-only keys (`slot_colors`, `color*`, `fade_beats`,
  `gradient_stops`) apply in place; any other key reconfigures motion from the current beat.
  `cue_beats` changes take effect on the next Play; Play always restarts the cue window.

## 3. Start from house patterns
Read the closest existing effect in `govee_frame_renderer.py` and copy its skeleton (slot-based
unless Brandon explicitly wants fixed colors). Reuse the house primitives: `_comet_frame` /
`render_comet`, `_dual_chase`, `_sparkle_frame`, the `slot_coord = intensity * 4.0` gradient
idiom, `_rng(...)` stable seeding. Deterministic by construction: no wall clock, no global
`random` (local `random.Random(...)` only — never reseed the module RNG), survive
`segments == 0`, channels clamp 0-255.

## 4. Self-check before hardware (mandatory)
Before the first Play: `POST /api/lab/reload` and fix any traceback. Then
`POST /api/lab/preview` (or dry-render by calling your function directly) for ~2 cycles at
Brandon's BPM and check: not all-dark, channels in range, motion actually moves, and count
full-strip on/off flips — faster than the house 16th-note gate means stop and rethink before it
reaches the strip.

## 5. Variants first, then tune
For a new idea, author 2-3 variants that each differ on ONE meaningful axis (motion pattern,
density, white usage — not three random takes). Register each as its own draft (`idea_a`,
`idea_b`, `idea_c`), self-check all of them (§4), then play one with Test Palette at Brandon's
BPM and switch live (`/api/lab/switch`) while he watches — switching is seamless, the beat
keeps running. He picks a winner; reject the losers with one line each. Then tune the winner in
whichever mode Brandon wants that day:
- Talk-mode: he describes, you change ONE thing per iteration (`/api/lab/update` while live)
  and describe it back in plain language ("comets now die at the ends instead of wrapping").
- Knob-mode: point him at the few params worth feeling out; his edits in the UI apply live.
Prefer param-izing a constant over rewriting the shape. Keep a running list of constants
Brandon actually adjusted — those become the promoted render's exposed controls; everything he
never touched stays hardcoded. Stop playback whenever Brandon steps away (Stop is free).

## 6. Accept / reject
Accepted = Brandon says so while watching it. Hand promotion to the codex-spec pipeline: move
the function into `govee_frame_renderer.py`; register in `SLOT_EFFECTS`/`_EFFECTS`; add its
`REALTIME_EFFECT_PARAM_KEYS` allowlist entry (an un-allowlisted static param on a live look
disables ALL LEDs — the C5 fail-safe); add to `REALTIME_STROBE_EFFECTS` if it strobes; tests in
`tests/test_govee_frame_renderer.py` (determinism, frame length/clamping, slot-5 white if
slot-based, param defaults); example-config look; `led_govee` card cue-table row; contract
checks + unittest run. Rejected = status flip in `drafts.json` plus one line on why (so the
next agent doesn't re-pitch it).

## 7. Forbidden
Editing bridge modules mid-lab; running/restarting the bridge without the single-process check;
sending Govee cloud commands; inventing palette systems, scene names, or `slot_colors` params;
upgrading status language; leaving playback running — especially a strobing draft — when
Brandon steps away.
```

### Task 6 - Docs (led_pad contract `docs_update` + drift fixes)

Per `docs/agents/change_contracts.yml` `led_pad` (`:205-228`):
1. `docs/guides/led_pad.md`: extend the Template Lab section with `/api/lab/update` and
   `/api/lab/preview`, the auto-apply-while-live behavior, and the Preview strip. Verify the
   section's current structure before editing.
2. `docs/subsystems/led_govee.md`: if it describes the lab loop, reflect live-apply + preview;
   otherwise no change (verify, don't assume).
3. `docs/architecture/doc_index.md`: classify `docs/plans/active/template_lab_direction_2026_07_04.md`
   and this spec.
4. `docs/status/active_work_registry.md`: register both docs as active (Template Lab Round 1).
5. Drift fix (docs-only, no behavior change): `docs/architecture/led_pad_template_lab_design.md`
   lines 5 and 11-13 still say "planned — nothing implemented"; update to reflect
   implemented/software-tested status, pointing at `docs/plans/active/led_pad_template_lab_spec.md`
   for the phase table. Use §10 status words only.
6. `docs/plans/active/led_pad_template_lab_spec.md`: add a Round 1 row (this spec, its commits,
   `implemented/software-tested`) to the post-Phase-3 additions table when done.

## Part C - Invariants That MUST Still Hold (live safety)

- Pad-look play/update behavior byte-identical; the single shared playback slot stays (a lab
  update never spawns a second playback path).
- `lab_update` applies ONLY when the pad already owns playback and that exact draft is playing;
  it never calls `request_takeover()`, never activates the transport, never restarts the
  `CueTimer`/`SyntheticClock`.
- `lab_switch` applies ONLY when a lab scene is already playing; it never takes over from the
  bridge, never preempts a pad look, and never restarts the `CueTimer`/`SyntheticClock` — the
  seamless-beat property is the feature.
- `lab_preview` never constructs a transport, never sends UDP, never reads/writes ownership or
  the bridge status/commands files, never swaps the live `LabRenderer`'s effects.
- Failure direction stays dark: broken sandbox module during live apply → blank frames, never a
  stuck bright/strobing frame.
- No code-level strobe rail added (operator decision); no changes to strobe validation.
- No bridge module edits; the 200 Hz push loop and bridge runtime are untouched by definition of
  the file allowlist.
- Emergency stop (`■ STOP`) and Stop behavior unchanged.

## Part D - Tests

Extend `tests/test_led_pad_lab.py` (reuse its temp-dir + `_FakePlayback` harness) and/or
`tests/test_led_pad_service.py` (whichever already builds a full `LedPadService`; follow its
constructor pattern). **First, augment the lab `_FakePlayback`** (`tests/test_led_pad_lab.py:35-68`):
its `update()` is currently a no-op that records nothing — add
`self.update_calls: list[dict] = []` in `__init__` and make `update(spec)` append the spec and
set `self.playing = spec["look_name"]`, so the update/switch assertions below are actually
checkable. (The service-test fake at `tests/test_led_pad_service.py:47-49` already records
`update_calls`, but its `_service()` helper builds no lab dir — if you use it for lab tests,
give it a temp `lab_dir` + `effects_lab.py`.)

1. `render_preview_frames` (pure, no service): fixed args → deterministic (two calls equal);
   frame count = `round(beats*60/bpm*fps)` capped at `max_frames` and floored at 1; every frame
   exactly `segments` long with 0-255 int channels.
2. `lab_preview` endpoint: returns `ok` with `frames`/`fps`/`bpm`/`beats`/`segments`; unknown
   draft raises `ValueError`; broken `effects_lab.py` returns `ok: False` with non-empty
   `traceback`; the fake playback records **zero** calls (no play/update/takeover/status side
   effects beyond none — assert its call log is empty).
3. `lab_update`: (a) when the fake playback reports playing and `_playing_name` is the draft's
   scene ref → `applied: True`, fake's `update()` called once with a spec whose `scene_ref` is
   `lab_<name>`, and `play()` NOT called; (b) not playing → `applied: False` and internal
   playing-name cleared; (c) a different look playing → `applied: False`; (d) payload params
   overlay saved entry params in the spec passed to `update()`.
4. Live code swap: write `effects_lab.py` v1, play; rewrite with changed function, `lab_update`
   → the service's live `LabRenderer.effects` now contains the new function (assert via a
   rendered frame difference or fn identity), consistent with `_lab_play_spec`'s reload.
5. `lab_switch`: (a) lab draft A playing → switch to B: fake's `update()` called once with a
   spec whose `scene_ref` is `lab_b...`, `play()` NOT called, and the service now reports B as
   the playing name (subsequent `lab_update` for B applies); (b) nothing playing →
   `{"ok": False, "error": "no_lab_scene_playing"}`; (c) a **pad** look playing (non-`lab_`
   playing name) → same refusal, fake's `update()` NOT called; (d) unknown draft raises
   `ValueError`.
6. Regression guard: pad-look `update()` for a production look still behaves as in the existing
   tests (run the full suite).

No JS test harness exists in this repo — frontend changes are covered by the manual checklist in
Part E only. Do not add a JS test framework.

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-6 implemented exactly; each committed on `main` (no branches) with a clear message.
- [ ] `python3 -m unittest discover tests` passes from the repo's parent directory convention
      used by CI (and note: CI is Python 3.11 — no 3.12+ syntax).
- [ ] `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
      `python3 tools/check_docs_drift.py` all pass.
- [ ] All six Task-6 doc updates done; status language stays within §10 (nothing above
      `implemented`/`software-tested`).
- [ ] SKILL.md replaced verbatim with the Task 5 text.
- [ ] Manual smoke (dry-run only, no hardware): start the pad server with `--dry-run`, open
      `/lab`, create two trivial drafts, Reload, Preview renders an animating strip, Play +
      param-edit auto-applies without the cue restarting, selecting the other draft shows
      "⇄ Switch" and switching swaps the playing scene without a stop/start, Stop works. Do NOT
      take over from a live bridge; if the bridge owns the LEDs, skip the Play steps and say so.

## When You Finish

Report: changed files; tests/checks run with results; the dry-run smoke outcome; anything
skipped and why. Then a plain-language operator summary: what tuning feels like now (edit a
number while it plays → lights follow; tap another draft while one runs → the look morphs
without the beat stopping; Preview shows a draft in the browser before it ever touches the
strip), what did not change (pad looks, ownership, emergency stop, strobe policy stays
discipline-only), watchpoints (a syntax error while live-editing goes dark until fixed — that
is intended), and that everything remains SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED until
Brandon runs it on the strip.

## Adversarial self-review (spec author, pre-handoff)

Attack considered: **auto-apply feedback loop** — save → refresh → textarea rewritten → `input`
fires → infinite loop. Prevented: the handler never calls `refresh()`, and programmatic `.value`
writes don't fire `input` events. Attack: **cursor theft while typing** — same prevention (no
DOM rewrite on the auto-apply path). Attack: **preview swaps live effects mid-play** — prevented
by the fresh local `LabRenderer` in `lab_preview`. Attack: **lab_update steals ownership or
restarts the cue** — it has no takeover branch and `PadPlayback.update()` touches neither
`CueTimer` nor `SyntheticClock` (`tools/led_pad_playback.py:296-302`). Attack: **switch stomps a
pad look or steals ownership** — `lab_switch` refuses unless a `lab_*` scene is already playing;
the UI's fallback path is the existing `lab_play`, which already carries preempt + ownership
semantics. Attack: **switch desyncs tuning** — it updates `_playing_name`, so auto-apply and
`lab_update` immediately track the new draft. Attack: **fps=0 / bpm=0 division** — clamps floor
fps at 1, bpm at 40. Attack: **huge JSON response** — frames capped at 2000. Attack: **pad
update path regression** — `lab_update`/`lab_switch` are additive; `update()` untouched;
regression test in Part D-6.
