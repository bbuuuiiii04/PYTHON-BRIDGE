---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: a3de9dd
last_verified_date: 2026-07-06
validation_scope: spec only until tasks land; all cited seams re-verified read-only at HEAD a3de9dd; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; nothing here authorizes a bridge restart, live process, device, or hardware action
---

# Codex Implementation Spec — LIGHTING ENGINE v2, Feature 1: per-track color identity + Stream Deck correction surface

**Effort: `xhigh`.** Design authority (locked — implement, do not re-litigate):
`docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md` §2, §2.3, §2.4, §6, §7 (F1 rows), §8, §15.6;
operator contract `docs/architecture/lighting_engine_v2_authority.md` §3, §11, §12.
Where this spec pins a constant the design marked TUNE-LIVE, the constant is a starting value
behind config, never a fact.

> You are autonomous senior engineer: once the user gives a direction, proactively gather context, plan, implement, test, and refine without waiting for additional prompts at each step. Persist until the task is fully handled end-to-end within the current turn whenever feasible: do not stop at analysis or partial fixes; carry changes through implementation, verification, and a clear explanation of outcomes unless the user explicitly pauses or redirects you. Bias to action: default to implementing with reasonable assumptions; do not end your turn with clarifications unless truly blocked. Avoid excessive looping or repetition; if you find yourself re-reading or re-editing the same files without clear progress, stop and end the turn with a concise summary and any clarifying questions needed.

> Act as a discerning engineer: optimize for correctness, clarity, and reliability over speed; avoid risky shortcuts, speculative changes, and messy hacks; cover the root cause or core ask, not just a symptom. Conform to the codebase conventions: follow existing patterns, helpers, naming, formatting; if you must diverge, state why. Investigate and wire between all relevant surfaces so behavior stays consistent. Preserve intended behavior and UX; gate or flag intentional changes and add tests when behavior shifts. Tight error handling: no broad try/catch and no success-shaped fallbacks; propagate or surface errors explicitly rather than swallowing them; no silent early-returns on invalid input. Avoid repeated micro-edits: read enough context before changing a file and batch logical edits. Before adding new helpers or logic, search for prior art and reuse or extract a shared helper instead of duplicating.

> Think first. Before any tool call, decide ALL files/resources you will need. Batch everything: if you need multiple files (even from different places), read them together. Only make sequential calls if you truly cannot know the next file without seeing a result first. Workflow: (a) plan all needed reads → (b) issue one parallel batch → (c) analyze results → (d) repeat if new, unpredictable reads arise. Always maximize parallelism; never read files one-by-one unless logically unavoidable.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make unless explicitly requested. If asked to make edits and there are unrelated changes in those files, do not revert them. If you notice unexpected changes you didn't make, STOP and ask how to proceed. NEVER use destructive commands like `git reset --hard` or `git checkout --` unless specifically requested.

> Skip the planning tool for straightforward tasks (roughly the easiest 25%). Do not make single-step plans. After performing a sub-task on the plan, update it. Unless asked for a plan, never end with only a plan — the deliverable is working code. Before finishing, reconcile every stated intention/TODO: mark each Done, Blocked (one-sentence reason + targeted question), or Cancelled (with reason). Do not end with in_progress/pending items. Avoid committing to tests/broad refactors unless you will do them now; otherwise label them explicitly as optional next steps.

---

## Part A — Context & Root Cause (verified; read, do not implement)

Every file:line below was re-verified read-only at HEAD `a3de9dd` (2026-07-06). Labels:
**[confirmed]** = read in current code or ran; **[assumed]**; **[unknown]**.

### What exists today (v1)

- **[confirmed]** `LedColorEngine` (`led_color_engine.py:254`) is a pure, I/O-free module (docstring
  `:1-6`). Per-track color is a **salted, session-random seed**: `identifier = content_id or
  filepath or str(load_gen)`; `_current_track_seed = _blake2b_int(f"{self._set_seed}:{active_deck}:
  {identifier}")` (`led_color_engine.py:373-376`). `set_seed_mode` defaults `"random"`
  (`led_models.py:121`), so the same track wears different colors every session — the exact thing
  F1 replaces with a permanent, content-keyed identity.
- **[confirmed]** All engine calls run **on the 200 Hz push loop**: `begin_dispatch`
  (`led_dispatch_policy.py:796-804`), `resolve_slot_colors` (`:869-876`), `resolve_color`
  (`:905-912`) inside `_dispatch_led_automation`; `advance_fade` (`:674`) inside
  `_advance_palette_fade_and_publish`; both invoked from the tick path at
  `state_manager.py:3882-3883`. **Nothing new on these paths may block or touch a file.**
- **[confirmed]** Slot plumbing already exists: `resolve_slot_colors` returns a fixed 6-slot vector
  with slot 5 reserved pure white (`led_color_engine.py:635-776`); the renderer consumes it via
  `universal_colorizer` (`govee_frame_renderer.py:1026`), `_slots` (`:42`), and per-frame fade
  interpolation `resolve_fade`/`slot_colors_from|to` (`:74,92-94`). Comet-family looks bypass
  `renderer.render()` — `_compose_frame` routes them to `render_comet`
  (`govee_realtime_runner.py:351,364`); comets take engine `color`/`color_a/b` params, with a
  name-based fallback at `govee_frame_renderer.py:1882` that engine-supplied colors make dead weight.
- **[confirmed]** Pad surface: Stream Deck is a **separate OS process** (`streamdeck/
  streamdeck_midi.py`, launched by `scripts/ss_bridge_watcher.sh:63-74`) speaking to the bridge only
  via (a) MIDI notes on zero-based channel 2 (`streamdeck_midi.py:35`) mapped by config
  `color_engine.palette_control` (`config/led_look_director.example.json:113-130`; binding builder
  `led_config.py:1347-1399`) into `BridgeEvent`s (`soundswitch_midi_input.py:260,315,348` →
  `Ev.LED_PALETTE_PAD` etc.), and (b) a one-way feedback JSON file the bridge writes
  (`led_palette_control.py:42`, writer `:66-136`) and the deck polls every 0.5 s
  (`streamdeck_midi.py:832-835`), stale after 10 s (`:45`). Deck layout is hardcoded in
  `compose_layout` (`:202-256`): keys 0-4 first five journey palettes, 5 white_sand, 7/8/9/14
  controls, 10-13 static-look sidecar. Unknown feedback fields pass through by design (`:153-167`,
  2026-07-04 incident note). No shift/layer mechanism exists.
- **[confirmed]** Gestures (`led_palette_control.py`): tap = queue for **next track**
  (`_handle_palette_tap:290-299` → `queue_palette`, committed at track change,
  `led_color_engine.py:390-395`); hold ≥ 0.5 s = override-now fading to the phrase grid + lock
  (`_handle_palette_hold:301-306`, `_override_palette_now:308-329`, FADE_GRID contract `:21-30`).
  v1 `_lock` freezes dwell rotation + drop-snap (`led_color_engine.py:396,416`) and survives track
  changes (the new-track reset block `:367-403` never clears it).
- **[confirmed]** Per-track measurements: the v4 spectral layer stores everything F1 needs —
  `identity_axes(v4)` → grit/punch/bass/drama (`spectral_profile.py:111-118`; `bass` = `bass_duty`,
  a 0..1 beat fraction, `:91-101`), scalars `brightness_med`/`attack_low_p90`/`onset_mh_p90`/
  `growl_timbre_p90` in `v4.scalars` (`audio_spectral_features.py:118-121,410-414`), and per-beat
  `sustained_synth_flags(v4)` (`spectral_profile.py:245-255`; **no rate helper exists** — the
  consumer computes `mean(flags)`). Cache: `spectral_cache.get_cached_v4/put_cached_v4`
  (`spectral_cache.py:214-223`), keyed on file content+beatgrid, threshold-retune-safe.
- **[confirmed] Root cause of the runtime gap:** the at-load spectral path is **dark in the live
  launch**. `_spectral_enable` requires BOTH `RBSS_SMART_REARM_EXPERIMENT=1` AND
  `RBSS_SPECTRAL_ENABLE=1` (`state_manager.py:594-597`); the watcher sets only the former
  (`scripts/ss_bridge_watcher.sh:150-170`). The spectral ANLZ worker call site
  (`state_manager.py:2116-2127`, inside the FILEPATH_RESOLVED handler where `content_id` lands at
  `:2089`) therefore never fires live, and even when it does, the worker **discards the v4 object**
  — only `energy_shadow` survives onto `TrackMetadata` (`state_manager.py:227-241`). No in-memory
  per-deck axes handle exists anywhere. F1 must add its own worker-side identity hook, gated on its
  own config, NOT on the smart-rearm experiment flags (rejected alternative: adding
  `RBSS_SPECTRAL_ENABLE=1` to the watcher — that would also flip today's gated smart-rearm spectral
  consumers, a behavior change outside F1's scope).
- **[confirmed]** `content_id` = Rekordbox `DjmdContent.ID` as string (`filepath_resolver.py:337`),
  arrives via FILEPATH_RESOLVED (`state_manager.py:2089`), empty string on DB failure
  (`filepath_resolver.py:349`).
- **[confirmed]** Persistent-store precedent: `LearnedStore` (`drop_presentation.py:483-537`) —
  JSON under `local/state/` (`LEARNED_STORE_PATH`, `:51`), content_id-keyed, `load()`/`to_dict()`
  as the only I/O surface, written by a dedicated debounced `PaletteFeedbackWriter(path,
  debounce_s=0.5)` owned by StateManager (`state_manager.py:517-519`). Copy this pattern exactly.
- **[confirmed]** Live-toggle precedent: `Ev.LED_SET_ENABLED` → `_led_enabled_latch`
  (`led_dispatch_policy.py:395-396`), a StateManager-owned bool flipped by a runtime command —
  the v1↔v2 master switch copies this, not config reload (no LED config hot-reload exists; the
  only `ConfigReloader` is laser-scoped, `__main__.py:1704-1710`).
- **[confirmed]** Engine construction: `LedColorEngine(cfg.color_engine)` at `__main__.py:499`,
  startup-only; `ColorEngineConfig` parsed by `_parse_color_engine` (`led_config.py:1232-1344`)
  from the `color_engine` key of `config/led_look_director.json`; unknown keys silently ignored.
- **[confirmed]** Look selection: role banks with cursors/shuffle-bags in `led_look_director.py`;
  the `diy_eligible` predicate filter (`:298-301`) with the never-empty-bank fallback is the
  pattern F1's motion-style/travel preference filter mirrors.
- **[confirmed]** Drop-marker seam for the max-energy arm: `_led_role_from_smart_phrasing` arms the
  drop lifecycle at `led_dispatch_policy.py:1343-1348` (`_led_drop_marker_anchor` →
  `_led_arm_drop_lifecycle(drop_anchor)`).
- **[confirmed]** `color_state()` feeds the laser color mapper (`state_manager.py:2801`) — v2
  identity colors flow to lasers through this existing seam for free once `color_state` is v2-aware.
- **[assumed]** Fresh v4 extraction for an uncached track costs ~12 s (project memory; not
  re-timed). 666/686 on-disk tracks are already cached (design §13, measured 2026-07-05).

### What F1 builds (locked design, condensed)

Per the §7 kill matrix, the **F1 identity switch** owns exactly: (1) zone map + hash spread +
depth/dynamics axes (§2); (2) identity permanence store + palette-pad correction path (§2.3/§2.4);
(3) first-play bloom; (4) identity handover soft flip on active-deck flip; (5) motion-style +
dynamics-budget look selection; (6) palate reset on hard genre pivots. Plus: the §8 color-slot
contract carried through v2 resolution, the v1↔v2 master switch (live, v2-off ⇒ v1
byte-identical), the max-energy drop-queue **pad + arming only** (rendering is F2), and the
Stream Deck zone/manual surface. Operator ground truth (do not re-open): zone pads = per-track
correction, hold/lock stores permanently, unlock-while-playing clears; manual pads (white/sand,
R/G/B) = live-only rank-0 override, never stored; queue = current track at next phrase boundary;
v2 "lock" = store-the-correction (v1 freeze meaning dropped); lasers do not coordinate with LED
blackout (out of F1).

### Spec-author decisions (gaps closed here; veto-marked ones listed again in "When You Finish")

- **D1 — Correction granularity: zone-only.** A zone pad re-zones the track; the content hash
  still picks hue slot + depth variant inside the new zone. Rationale: preserves OLC-3
  neighbor-distinctness and permanence with zero extra UI; "this track lives HERE" is exactly a
  zone statement; zone+variant would need selection UI that doesn't fit 15 keys.
- **D2 — v2 lock is an act, not a mode.** "Lock" = write the active zone override to the store for
  the current track. No persistent freeze state exists in v2 (nothing rotates to freeze; identity
  is already deterministic). The residual v1 freeze behavior is dropped entirely in v2 mode. Lock
  feedback on a zone pad = "current track has a stored correction".
- **D3 — Warm stops do NOT enter the shared `scale_stops`.** Design §2.2 phrased warm accents as
  "added to scale_stops", but stop positions are evenly spaced by insertion order
  (`led_color_engine.py:60-66`), so adding a 7th stop moves all six v1 stops and breaks v2-off
  byte-identity — a hard requirement. v2 zones carry their own explicit RGB ramps (amber/gold live
  inside zone accent ramps); v1's six stops are untouched. Deviation is deliberate and
  intent-preserving.
- **D4 — Identity derivation runs whenever F1 is configured on, even while the v1 latch renders.**
  Derivation is worker-thread work; having identities warm makes the mid-show v1→v2 flip instant.
  The latch gates *rendering* only.
- **D5 — New-purchase first play:** NEUTRAL until the one-time analysis lands, then the real
  identity applies **at the next phrase boundary of that same first play**; the store freezes from
  the real derivation. (No-repaint protects across-plays permanence; a one-time upgrade at a phrase
  boundary during the very first play reads as a normal look change, not a repaint.) *Operator-veto.*
- **D6 — Palate-reset trigger = aggression-side flip** between outgoing and incoming identities on
  an active-deck/track flip (smooth half {GLACIER, DEEP_POOL, TWILIGHT, NEUTRAL} ↔ aggressive half
  {ION, VOLT, EMBERCORE}). Window: `palate_reset_beats` = 4.0 beats of NEUTRAL ramp dimmed by
  `palate_reset_dim` = 0.35 — dim, never black. Both config, TUNE-LIVE.
- **D7 — Bloom mechanics:** first time a `content_key` is the active dispatched track tonight
  (in-memory session set; re-bloom after restart accepted), after ≥ `bloom_hold_beats` = 8 audible
  beats **on that track's own timeline** (per-track counter, reset by new-track detection; beat
  deltas from the active deck's `abs_beat`), the next color resolution fades in from the identity
  dimmed by `bloom_dim` = 0.3 over `bloom_beats` = 8 (2 bars). Skip-not-queue is literal: if a
  rank-0 hold or rank-5 reset claim overlaps, the bloom is marked done and never retried; and a
  pending bloom **expires unfired** if no resolution consumes it within `bloom_beats` of arming
  (this is what keeps a blackout/predark from deferring a bloom into a late fire — automation is
  gated during blackout, so the pending window simply lapses).
- **D8 — Soft flip default `soft_flip_beats` = 8.0** (authority allows 4-8; config, TUNE-LIVE).
- **D9 — Master flip applies at the next color resolution** (≤ one cue step). Fade memory is
  cleared on every flip, so no frame ever interpolates across engines. This satisfies the design's
  "next look boundary" rule without pending-flag machinery.
- **D15 — Rainbow in v2 is a manual-tier override.** v1 Rainbow works through
  `set_mode_override` (`led_palette_control.py:354-363`) — a v1 field v2 resolution never reads,
  so without this decision the rainbow pad would silently do nothing in v2. In v2, the rainbow
  pad/command routes to `set_manual("rainbow")` (tap again clears), and v2 manual resolution
  reproduces the v1 rainbow-palette-type output verbatim (`led_color_engine.py:574-581` for
  single-color, `:677-683` for slots). Unlike v1 (`_rainbow` gates other pads,
  `led_palette_control.py:262,280-281`), v2 zone gestures stay live while rainbow manual is
  active — corrections are store ops and simply don't repaint until the manual clears.
- **D10 — Max-energy arm lifecycle (F1):** toggle to arm/disarm; armed state clears on (a) firing
  at the next drop marker (one-shot), (b) new audible track, (c) master flip to v1. In F1 firing
  changes **nothing visible** — it logs `[LED] max_energy consumed (render unchanged until F2)` and
  clears; the F2 spec attaches the max-energy template. *Operator-visible no-op; veto-marked.*
- **D11 — bass norm anchors are not in the design's frozen table.** Ship
  `bass_lo=0.15, bass_hi=0.90` **[assumed]** as config defaults, and pin the real p5/p95 with the
  one-off read-only calibration tool (Task 10) against the local 666-track cache at implementation
  time. All other anchors are frozen from design §2.1/§2.3 verbatim.
- **D12 — Key layout (operator-veto, feedback-file-driven so cheap to change):**
  - v2 config absent → deck byte-identical to today (no code path change).
  - Config on + **v1 latched**: today's exact layout, plus key 6 (dark today when `lock_note` is
    absent — [confirmed] AWR-121) becomes the `→ v2` engine-toggle pad.
  - Config on + **v2 latched**: keys 0-5 = GLACIER, DEEP_POOL, TWILIGHT, ION, VOLT, EMBERCORE;
    key 6 = white/sand (manual); keys 7/8/9 mutes/solo unchanged; 10-13 static looks unchanged;
    key 14 = **shift layer toggle** (deck-local). Shift layer: 0=RED, 1=GREEN, 2=BLUE,
    3=MAX-ENERGY arm, 4=RAINBOW, 5=`→ v1` engine toggle; 6 dark; 7-13 unchanged; 14 exits.
- **D13 — Runtime commands:** reuse `led_palette_queue/override/lock/unlock` with v2 semantics when
  v2 is latched (zone names accepted; lock/unlock = store/clear correction); add `led_engine
  <v1|v2>`, `led_manual_override <white_sand|red|green|blue>`, `led_manual_clear`,
  `led_max_energy_toggle`.
- **D14 — The moment arbiter ships now as a small pure function** with the full §6 rank table
  (0-9) as constants; F1 registers only ranks 0 (manual), 5 (palate reset), 6 (bloom). F2/F3 add
  their rows without reshaping it.

### Knowns / unknowns

- **[unknown]** Live `config/led_look_director.json` note values and whether `lock_note` is bound
  live — the live config is gitignored. All new note bindings are config; collisions are validated
  fatal (Task 3). The operator confirms final note numbers at the live gate.
- **[unknown]** Govee/Stream Deck device latency; DB-rebuild content_id stability (filepath
  fallback pinned by design). Neither blocks software work.
- **[unknown]** Whether the live deck script instance restarts with the bridge (watcher manages
  both — `scripts/ss_bridge_watcher.sh:63-74`); feedback-schema changes are pass-through-safe on
  the deck side regardless.

---

## Part B — Tasks (implement exactly, in order)

### Absolute Rules

- **Out of scope — do not touch:** laser modules (`laser_*.py`, `soundswitch_laser_player.py`,
  `midi_output.py`, `enttec_dmx_pro.py`), SoundSwitch output/pack modules (`osl_output.py`,
  `soundswitch_*.py` except reading `soundswitch_midi_input.py` binding plumbing you extend),
  Rekordbox readers (`rb_*.py`, `mtc_reader.py`, `live_bpm.py`), `drop_presentation.py` behavior
  (you may read `LearnedStore` as the pattern; do not modify the file), `smart_phrasing.py`,
  `autoloop_controller.py`, the Template Lab / LED Pad web tools (`tools/led_pad_web.py` may keep
  calling v1 paths; do not extend it), `streamdeck` static-look/DMX-compositor paths, tests you
  didn't write except where a task names them.
- **Behavior that must not change:** every byte of v1 LED behavior when the v2 config block is
  absent OR `v2.enabled=false` and the latch is v1 — including RNG draw sequences (no new draws on
  any v1 path), fade memory semantics, dwell/queue/lock semantics, feedback payload fields consumed
  today, deck layout with config absent, scripted-track LED behavior (v2 stands down on scripted
  tracks in ALL modes), blackout/mute/static-override authority, and the 200 Hz push-loop I/O
  profile (no file/socket/subprocess/MIDI added to it — identity lookups at dispatch are in-memory
  dict reads only).
- **Error handling:** config errors fail closed at parse (reject the v2 block with a reason;
  bridge runs v1-only). A corrupt/unreadable identity store loads as empty with one WARNING and a
  status flag (`identity_store=degraded`) — never crash, never silently truncate an existing store
  file on the next write (write only after a successful load, else write to the path only when the
  first real record freezes and the load failure was file-not-found). Derivation errors on the
  worker thread log once per track and fall back NEUTRAL — never propagate into the load path.
  No broad try/except anywhere else; no success-shaped fallbacks.
- **Threading:** engine mutations only on the StateManager thread (BridgeEvents), matching
  AGENTS.md §6. Worker threads publish events; the debounced writer thread does all store file I/O.

### Task 0 — `docs/agents/change_contracts.yml`: extend contracts FIRST (anti-drift §7)

Add to `led_govee.code_globs`: `led_identity_v2.py`, `tools/calibrate_identity_v2.py`. Add to
`led_govee.key_symbols`: `LedIdentityV2`, `IdentityStore`. Add to `streamdeck_palette.code_globs`:
`led_identity_v2.py`. Add `python3 -m unittest tests.test_led_identity_v2` to both contracts'
`tests` lists. Do not remove anything.

### Task 1 — `led_identity_v2.py` (NEW, pure — no imports from bridge modules except `led_models`; no I/O beyond `IdentityStore.load`)

Mirror `led_color_engine.py`'s pure-module conventions. Contents:

**1a. Frozen constants** (design §2.1/§2.3 verbatim; module-level, not config):

```python
NORM_ANCHORS = {
    "punch": (0.4298, 1.2), "attack_low_p90": (6.7, 38.875), "grit": (0.0137, 0.0776),
    "onset_mh_p90": (2.0, 4.0), "brightness_med": (341.8, 1456.5),
    "synth_rate": (0.053, 0.725), "growl_timbre_p90": (0.1528, 0.377),
    "drama": (7.0, 23.375),
}
AGGRESSION_SPLIT = 0.418; EMBERCORE_DISTORTION = 0.75
ION_LUMINANCE = 0.52; GLACIER_LUMINANCE = 0.40; DEEP_POOL_LUMINANCE = 0.28
ZONES = ("GLACIER", "DEEP_POOL", "TWILIGHT", "ION", "VOLT", "EMBERCORE")  # + "NEUTRAL"
SMOOTH_ZONES = frozenset({"GLACIER", "DEEP_POOL", "TWILIGHT", "NEUTRAL"})
HUE_SLOTS = 16; DEPTH_VARIANTS = 3
```

`bass` anchors come from config (D11), not this table.

**1b. Scoring + zone assignment** (pure):

```python
def norm(v, lo, hi): return clip((v - lo) / (hi - lo), 0.0, 1.0)

def identity_scores(axes, scalars, synth_rate) -> dict:
    aggression = 0.35*norm(axes["punch"],*A["punch"]) + 0.25*norm(scalars["attack_low_p90"],*A["attack_low_p90"]) \
               + 0.25*norm(axes["grit"],*A["grit"]) + 0.15*norm(scalars["onset_mh_p90"],*A["onset_mh_p90"])
    luminance  = 0.60*norm(scalars["brightness_med"],*A["brightness_med"]) + 0.40*norm(synth_rate,*A["synth_rate"])
    distortion = norm(scalars["growl_timbre_p90"],*A["growl_timbre_p90"])
    return {"aggression":…, "luminance":…, "distortion":…}

def assign_zone(scores) -> str:
    # exact frozen splits, design §2.2:
    # aggression >= 0.418: distortion >= 0.75 -> EMBERCORE; luminance >= 0.52 -> ION; else VOLT
    # else: luminance >= 0.40 -> GLACIER; < 0.28 -> DEEP_POOL; else TWILIGHT
```

Unmeasurable (no v4 entry, empty inputs) never reaches `assign_zone` — callers use `"NEUTRAL"`.

**1c. Content key + hash spread**:

```python
def content_key(content_id: str, filepath: str) -> str:
    return content_id or ("path:" + os.path.realpath(filepath))   # realpath computed OFF hot path (worker/load only)
def content_hash(key: str) -> int:   # blake2b 64-bit, same recipe as led_color_engine._blake2b_int
```

**1d. Dressing derivation** (pure; the per-track identity):

```python
def derive_dressing(zone: str, zone_cfg, key_hash: int, norm_bass: float,
                    norm_drama: float, norm_punch: float) -> Dressing
```

- `hue_slot = key_hash % 16`; `depth_variant = (key_hash // 16) % 3`.
- `sat_floor = clip(lerp(0.55, 0.85, norm_bass) + (-0.05, 0.0, +0.05)[depth_variant], 0.40, 0.95)`.
- `span = lerp(0.8, 0.35, norm_bass)`.
- `hue_offset = (hue_slot / 15 - 0.5) * zone_cfg.hue_span` (config default `hue_span = 0.06`,
  TUNE-LIVE).
- Base slots: with `R(t)` = piecewise-linear over the zone's 3 base-ramp anchors (t∈[0,1],
  dark→core): `slot[i] = adjust(R(1 - span*(2-i)/2))` for i=0,1,2 (slot 2 always the core).
- Accent slots 3-4: `adjust(accent_ramp[j])`.
- `adjust(rgb)` = HSV: rotate hue by `hue_offset`, raise saturation to ≥ `sat_floor` (never lower
  it), value unchanged. Use `colorsys`; round/clamp like `_p_to_rgb` does.
- Slot 5 = `(255, 255, 255)` always (§8 white slot; white-share scaling is F2).
- `budget = lerp(0.3, 1.0, norm_drama)`; `style = "sharp" if norm_punch >= 0.6 else "flowing"`.
- Returns frozen `Dressing(zone, hue_slot, depth_variant, sat_floor, span, budget, style,
  slot_rgbs: tuple[6 rgb])`.
- NEUTRAL uses the same function with the NEUTRAL zone_cfg (same hash spread — design §2.3).

**1e. Hard pivot** (D6): `def is_hard_pivot(zone_a, zone_b) -> bool` — True iff exactly one side is
in `SMOOTH_ZONES`.

**1f. Moment arbiter** (D14, design §6; pure):

```python
RANKS = {"manual":0, "drop":1, "landing":2, "dip":3, "blend_resolve":4,
         "palate_reset":5, "bloom":6, "stinger":7, "texture":8, "simmer":9}
def claim_allowed(new: Claim, active: Iterable[Claim]) -> bool:
    # a claim [start,end) is allowed iff no active overlapping claim has a lower rank number
```

`Claim = NamedTuple(rank:int, start_beat:float, end_beat:float, tag:str)`. F1 registers manual /
palate_reset / bloom only.

**1g. `IdentityStore`** — mirror `LearnedStore` (`drop_presentation.py:483-537`) exactly in shape:
`load(path) -> IdentityStore` (classmethod; missing file → empty; corrupt → empty + `degraded=True`
+ one WARNING), `to_dict()`, `get(key) -> record|None`,
`freeze(key, record) -> bool` (first-write-wins: returns False and changes nothing if the key
exists — **analysis upgrades can never repaint**), `set_correction(key, zone)`,
`clear_correction(key)`. Record schema (JSON):

```json
{"zone": "GLACIER", "hue_slot": 7, "depth_variant": 1, "sat_floor": 0.62, "span": 0.55,
 "budget": 0.41, "style": "flowing",
 "scores": {"aggression": 0.268, "luminance": 0.436, "distortion": 0.12},
 "analysis_rev": "v4", "correction": null}
```

`correction` is `{"zone": "<ZONE>"}` or `null`. Store version key `{"version": 1, "tracks": {…}}`.
No file writes in this class beyond nothing — writing is the owner's job via the debounced writer
(Task 5). Corrected identity = re-run `derive_dressing` with the corrected zone and the SAME
frozen hash/axis inputs recorded at freeze time (store the three norm inputs in the record:
`"norm_inputs": {"bass": …, "drama": …, "punch": …}` — add this field to the schema above).

### Task 2 — `led_models.py`: v2 config models (additive only)

- `ZoneRampConfig` (frozen): `base_ramp: tuple[RGB, RGB, RGB]`, `accent_ramp: tuple[RGB, RGB]`,
  `white: float = 0.0`, `hue_span: float = 0.06`.
- `IdentityV2Config` (frozen): `enabled: bool = False`, `zones: Dict[str, ZoneRampConfig]` (keys:
  the 6 zones + `NEUTRAL`), `bass_norm: tuple[float, float] = (0.15, 0.90)`,
  `store_path: str = "local/state/led_identity_v2.json"`, `soft_flip_beats: float = 8.0`,
  `palate_reset_enabled: bool = True`, `palate_reset_beats: float = 4.0`,
  `palate_reset_dim: float = 0.35`, `bloom_enabled: bool = True`, `bloom_hold_beats: float = 8.0`,
  `bloom_beats: float = 8.0`, `bloom_dim: float = 0.3`, `punch_sharp_threshold: float = 0.6`,
  `budget_wide_threshold: float = 0.5`.
- `ColorEngineConfig` gains `v2: Optional[IdentityV2Config] = None`.
- `LEDLook` gains `motion_style: str = ""` (allowed `""|"sharp"|"flowing"`) and `travel: str = ""`
  (allowed `""|"calm"|"wide"`).
- `LEDContext` gains `look_preference: Optional[Callable[[str], bool]] = field(default=None,
  compare=False)` (mirrors `diy_eligible`).

### Task 3 — `led_config.py`: parse + validate

- Parse `color_engine.v2` in `_parse_color_engine` (`:1232-1344` area). Validation (extend
  `_validate_color_engine`): all 7 zone keys present when the block is enabled (absent zones =
  config error), each RGB a valid 0-255 triple, **every base/accent anchor non-(0,0,0)** (no
  dark-room ramps), thresholds in range, `motion_style`/`travel` look values in their allowed sets, and — when v2 is
  enabled — a `white_sand` palette of type `fixed_rgb` present (v2 manual white depends on it).
  Fail closed: any v2 validation error rejects the v2 block with an error string surfaced through
  the existing `LEDConfigResult.errors` path; the rest of the LED config still loads (bridge runs
  v1-only) — do not take the whole LED subsystem down for a v2 typo.
- Extend `_build_palette_control_bindings` (`:1347-1399`) with new optional keys inside
  `palette_control`: `zone_notes` (dict zone→note; validate zone names), `manual_notes` (dict over
  `red/green/blue`; `white_sand_note` stays the manual white in v2), `max_energy_note`,
  `engine_toggle_note`. **Any note collision across ALL bound notes (old + new) is a fatal config
  error** (fail closed at parse). Each binding carries a distinct `target_kind`: `"zone_pad"`,
  `"manual_pad"`, `"max_energy_pad"`, `"engine_toggle_pad"` (follow the existing binding tuple
  shape the builder emits for palette/control pads).

### Task 4 — `models.py`: new event kinds

Add to `Ev`: `LED_ZONE_PAD` (payload `{"name", "phase": "down"|"up"}`), `LED_MANUAL_PAD`
(`{"name"}`), `LED_MAX_ENERGY_PAD` (`{}`), `LED_ENGINE_MODE` (`{"mode": "v1"|"v2"}`),
`LED_TRACK_IDENTITY` (`{"deck", "load_gen", "key", "record"}` — record = the store-schema dict).
Events stay immutable after creation (AGENTS.md §6).

### Task 5 — `led_color_engine.py` + `state_manager.py`/`led_dispatch_policy.py`: the v2 brain and its wiring

**Engine (`led_color_engine.py`)** — every v2 branch is a FIRST-LINE guard so v1 code below is
textually untouched:

- Constructor: accept the parsed `config.v2`; hold `self._v2_cfg`, `self._v2_active =
  bool(v2.enabled)` (boot default), `self._v2_dressing: dict[int, Dressing]` per deck,
  `self._v2_track_key_by_deck`, `self._v2_manual: str = ""`, `self._v2_staged: tuple[str, float]
  | None` (zone, commit_beat), `self._v2_flip_fade: tuple[slots, until_beat] | None`,
  `self._v2_reset_until: float | None`, `self._v2_bloomed: set[str]`, `self._v2_bloom_pending /
  _v2_bloom_until`, `self._v2_claims: list[Claim]`, `self._v2_first_seen_beat: float | None`.
- `set_v2_active(active: bool)` — on ANY change: `reset_fade_memory()`, clear every `_v2_*`
  transient (manual, staged, flip fade, reset window, claims, bloom-pending; NOT `_v2_bloomed`,
  NOT dressings). Never reads or writes `_journey_rng`, `_current_palette`, `_dwell_remaining`,
  `_lock`, `_queued_palette`, `_hold_track`, `_mode_override` — v1 journey state is frozen in
  place while v2 renders and resumes untouched on flip-back.
- `set_track_identity(deck, load_gen, key, record)` — store-schema dict → `Dressing` (pure
  reconstruction; corrected zone wins via re-derivation from `norm_inputs`); in-memory only.
- `begin_dispatch(...)`: `if self._v2_active: return self._v2_begin_dispatch(...)`. The v2 path
  does its own `(active_deck, load_gen)` new-track detection against `_v2_track_key_by_deck` (do
  NOT touch `_recent_keys` — that deque is v1 journey state). On new audible track: clear manual +
  staged + bloom-pending; set `_v2_flip_fade` from the **previously active dressing's** slot vector — whichever deck it
  lived on, covering both deck flips and same-deck track swaps — over
  `soft_flip_beats` (identity handover soft flip, F-10); if `palate_reset_enabled` and
  `is_hard_pivot(outgoing.zone, incoming.zone)` and `claim_allowed(reset_claim, active)`:
  set `_v2_reset_until = now + palate_reset_beats` and register the rank-5 claim; bloom
  bookkeeping per D7 (needs `content_key` — pass it through: v2 uses the same `content_id`/
  `filepath` args begin_dispatch already receives; realpath fallback allowed here **only if**
  content_id is empty AND the value was precomputed by the worker — at dispatch time use
  `content_id or filepath` verbatim as the session-bloom key, no realpath call on the hot path).
- `resolve_color` / `resolve_slot_colors`: first-line v2 guard. v2 resolution order:
  1. same early returns as v1 (engine disabled / `color_source != "engine"` / exempt look) —
     byte-for-byte the same guard set;
  2. manual override active → fixed output: `white_sand` uses the configured white_sand palette
     rgb ([confirmed] live ships `fixed_rgb` 255,235,200; Task 3 validates a fixed_rgb
     `white_sand` palette exists whenever v2 is enabled); `red/green/blue` use literals
     (255,0,0)/(0,255,0)/(0,0,255); `rainbow` reproduces the v1 rainbow-type output verbatim
     (D15); slots = 5×rgb + white, mirroring the v1 fixed_rgb slot shape
     (`led_color_engine.py:675-676`);
  3. palate-reset window active (`abs_beat < _v2_reset_until`) → NEUTRAL dressing slots scaled by
     `palate_reset_dim` (HSV value-scale; floor so no channel triple goes full black);
  4. otherwise the active deck's dressing (staged zone applies only once committed): single-color
     cues get a deterministic per-cue pick inside the base ramp — `cue_seed =
     blake2b(f"{key_hash}:{section_id}:{step_index}:v2")`, `p = rng.uniform(0,1)` mapped through
     `R(1 - span*p)` with the dressing's adjust — same `step_within_section` rule as v1; `multi`
     → `color_a/b` = base slots 0 and 2; slot cues → the dressing's 6-slot vector;
  5. fade fields: while `_v2_flip_fade` is live, inject `*_from` = the outgoing slots/color and
     `fade_beats` = remaining flip beats; while bloom is live, inject `*_from` = dressing dimmed
     by `bloom_dim` and `fade_beats` = remaining bloom beats; else use the v1 `_prev_color`
     mechanics verbatim (same mem_key shape, same `fade_beats_by_role`).
- `advance_fade(abs_beat)`: first-line v2 guard → `_v2_advance(abs_beat)`: commit staged zone at
  its phrase-anchor beat; expire flip/reset/bloom windows; track `_v2_first_seen_beat` for the
  bloom 8-beat hold; then return (v1 fade path untouched in v2 — `_fade_*` fields are v1 state).
- Control methods, all v2-aware with first-line guards: `stage_zone(zone, commit_beat)`,
  `apply_zone_override(zone, start_beat, end_beat)` (immediate, fades on the FADE_GRID contract
  like v1 override), `clear_zone_override()`, `set_manual(name)` / `clear_manual()`,
  `snapshot()` gains `{"engine": "v1"|"v2", "zone", "corrected": bool, "staged_zone", "manual",
  "store_degraded": bool}` (v1 fields unchanged), `color_state()` in v2 returns the SAME key set as v1
  (`rgb`, `palette`, `white_sand_active`, `rainbow_active` — `led_color_engine.py:838-845`):
  `rgb` = the dressing core slot (or the manual rgb), `palette` = `"v2:"+zone` (or the manual
  name), `white_sand_active`/`rainbow_active` true while those manuals hold — the laser mapper at
  `state_manager.py:2801` consumes it unchanged.
- v2 lock/unlock plumbing: `lock()`/`unlock()` keep their v1 bodies untouched; the v2 store
  semantics live in `LedPaletteControl`/StateManager (Task 7) which, when v2 is latched, do NOT
  call engine `lock()`/`unlock()` at all — they call the store correction path. (Keeps v1 lock
  state pristine for flip-back.)

**Wiring (`state_manager.py` / `led_dispatch_policy.py` / `__main__.py`):**

- `__main__.py:499` area: build `IdentityStore.load(cfg.color_engine.v2.store_path)` when the v2
  block is enabled (startup, before threads — off hot path); pass the store into StateManager
  alongside the engine; construct a second `PaletteFeedbackWriter(store_path, debounce_s=0.5)`
  exactly like the learned-store writer (`state_manager.py:517-519`); verify the store path is
  gitignored (`local/` — extend `.gitignore` if the existing patterns don't already cover it).
- Identity worker hook: in the FILEPATH_RESOLVED handler (`state_manager.py:2116-2127`), change
  the gate to `if self._spectral_enable or self._v2_identity_enabled:` and pass a new
  `identity_enabled` flag into `_start_anlz_worker`. Inside the worker (`:1880-1927` +
  `_read_runtime_anlz_data`): obtain v4 ONCE (existing `get_cached_v4` → `extract…v4` under the
  existing `_V4_AT_LOAD_MAX_S` guard → `put_cached_v4`); run today's spectral consumers ONLY when
  `spectral_enabled` (exactly today's behavior — `energy_shadow` etc. must NOT start populating
  because of v2); when `identity_enabled`: store hit? → publish `Ev.LED_TRACK_IDENTITY` with the
  stored record; miss → `identity_axes(v4)` + `v4.scalars` + `mean(sustained_synth_flags(v4))` →
  scores → zone → `derive_dressing` → publish the event with the fresh record. No v4 (uncached +
  span guard fails, or extraction error) → publish a NEUTRAL record (hash spread still applies;
  do NOT freeze NEUTRAL-for-missing-analysis into the store — freezing happens only for records
  derived from real measurements OR for explicit operator corrections; D5 depends on the store
  staying empty for not-yet-analyzed tracks).
- Event consumption (StateManager thread, near `:1431-1439`): `LED_TRACK_IDENTITY` →
  `engine.set_track_identity(...)`; if the record is fresh (not from store) and derived from real
  measurements → `store.freeze(key, record)`; if freeze returned True → `writer.submit(
  store.to_dict())`. `LED_ENGINE_MODE` → flip a StateManager-owned `_led_v2_latch` (mirror
  `led_dispatch_policy.py:395-396`) + `engine.set_v2_active(...)` + one INFO log. `LED_ZONE_PAD` /
  `LED_MANUAL_PAD` / `LED_MAX_ENERGY_PAD` → route to `LedPaletteControl.handle_event` (extend the
  routing table).
- Correction writes (from Task 7 handlers): `store.set_correction(key, zone)` /
  `clear_correction(key)` where `key` is the **active deck's** content key at press time
  ([ground truth] a stored correction always stamps the active deck) → `writer.submit(...)` →
  `engine.set_track_identity` refresh. If the track has no frozen record yet (correction before
  first derivation lands), freeze the current record first (NEUTRAL-with-correction is valid: the
  operator's call beats a missing analysis — and D5's no-freeze rule yields to an explicit
  operator act).
- Max-energy arm: `_led_max_energy_armed` flag on the dispatch-policy mixin; toggled by
  `LED_MAX_ENERGY_PAD`/command; consumed one-shot inside `_led_arm_drop_lifecycle`'s caller at
  `led_dispatch_policy.py:1345-1348` (log + clear, D10); cleared on new audible track and on
  latch flip to v1; surfaced in feedback + status.
- Identity INFO log at load (authority §14): one line per track load when v2 configured:
  `[LED] identity deck=N zone=GLACIER slot=7 depth=1 corrected=no key=…` (INFO = outcome; no
  per-tick logging).
- Status: extend the LED status payload (same provider that carries `led_status_provider` fields
  today) with `engine`, `zone`, `corrected`, `staged_zone`, `manual`, `max_energy_armed`,
  `identity_store` (`ok|degraded`).

### Task 6 — `led_look_director.py`: motion-style / travel preference filter

In `_automation_decision_for_role`, immediately after the `diy_eligible` filter (`:298-301`),
apply `context.look_preference` the same way — via the plumbing that supplies `diy_eligible`
today (the callable arrives through `LEDContext`; follow how `_dispatch_led_automation` builds
the context). Same never-empty rule: empty filtered subset ⇒ keep the previous set. StateManager
builds the predicate ONLY when v2 is latched and a dressing is active:
look passes iff (`look.motion_style` is `""` or equals `dressing.style`) AND (`look.travel` is
`""` or (`"wide"` and `budget >= budget_wide_threshold`) or (`"calm"` and
`budget < budget_wide_threshold`)). v1 latched ⇒ predicate `None` ⇒ selection byte-identical.
Tagging looks in live config is operator work at the live gate; the example config tags a
handful (Task 9) so the path is testable.

### Task 7 — `led_palette_control.py` + `soundswitch_midi_input.py`: v2 gestures

- `soundswitch_midi_input.py`: emit the new event kinds for the new binding target kinds —
  `zone_pad` gets down/up phases exactly like `palette_pad` (`:260-346` note-on/off paths);
  `manual_pad`, `max_energy_pad`, `engine_toggle_pad` are press-only (`phase` omitted).
  `engine_toggle_pad` emits `Ev.LED_ENGINE_MODE` with the OPPOSITE of the current latch — the
  adapter doesn't know the latch, so emit a dedicated payload `{"mode": "toggle"}` and let the
  StateManager consumer resolve it.
- `LedPaletteControl` gains the latch view via a `get_engine_mode: Callable[[], str]` constructor
  callable (pull pattern, like `get_laser_blackout`). New handlers:
  - `LED_ZONE_PAD` (v2 latched): tap on inactive zone = stage (engine.stage_zone at the next
    phrase anchor via the existing `_get_phrase_anchor` beat math — reuse `_override_palette_now`'s
    grid logic for the commit beat, but WITHOUT starting a fade: staging commits as a snap at the
    boundary); tap on the staged zone = unstage; tap on the active zone when a stored correction
    exists = **clear correction** (store + engine refresh); hold = `apply_zone_override` now
    (FADE_GRID fade) + `set_correction` (store, permanent — "hold/lock stores it"). v1 latched:
    one DEBUG log, no-op (stale-layout presses inside the ≤10 s feedback window are expected and
    harmless).
  - `LED_PALETTE_LOCK_PAD` (v2 latched): `lock` intent = store the currently active zone override
    as the correction (no-op if no override active); `unlock` = clear the current track's stored
    correction. (v1 latched: existing behavior untouched.)
  - `LED_MANUAL_PAD` (v2): tap = `engine.set_manual(name)`; tap the active manual pad again =
    `clear_manual`. Rank-0: while a manual is set, engine resolution short-circuits (Task 5) and
    bloom/reset claims are disallowed (`claim_allowed` vs an open-ended rank-0 claim).
  - `LED_RAINBOW_PAD` (v2 latched): route to `set_manual("rainbow")` / `clear_manual` toggle
    (D15) instead of `set_mode_override`; v1 latched keeps today's `_set_rainbow` path untouched.
  - `LED_MAX_ENERGY_PAD` (v2): forward to the sink (StateManager owns the flag).
  - In v2, `white_sand` arriving via the existing v1 palette binding (note 56) reroutes to
    `set_manual("white_sand")` — same physical pad, mode-correct meaning.
- Feedback payload (extend `_publish_feedback` body — pass-through-safe on the deck): add
  `"engine": "v1"|"v2"`, `"zones": [{name, note, rgb, ramp, state ∈ active|staged|inactive,
  corrected: bool}]` (rgb/ramp from the ACTIVE TRACK's dressing for the active zone, zone-core
  ramps otherwise), `"manual": [{name, note, rgb, state}]`, `"max_energy": {note, state ∈
  armed|inactive}`, `"engine_toggle": {note, state}`. Keep every existing field exactly as
  today in both modes (the deck's v1 branch must keep working against a v2-mode payload).

### Task 8 — `streamdeck/streamdeck_midi.py`: v2 layout + shift layer (D12)

- `compose_layout` v2 branch keyed on `feedback.get("engine") == "v2"` and presence of `zones`:
  primary layer per D12; deck-local `shift` boolean flipped by key 14 (`interaction: "press"` row
  rendered with a distinct glyph; shift state resets when feedback goes stale or engine flips).
  Shift layer rows per D12 (manual pads, max-energy with `armed` pulse, rainbow control row,
  engine-toggle row). With `engine == "v1"` AND an `engine_toggle` row present in feedback: key 6
  = engine-toggle; everything else exactly today's layout. No feedback / no engine field ⇒
  today's layout code path, untouched.
- Zone pad rendering: reuse the palette-pad renderer (ramp gradient + state grammar per
  `palette_control_authority.md` rules 21-24: bright=engaged, dim=available); `corrected: true`
  reuses the `locked_current` padlock glyph; `staged` renders like `queued` today. All row
  projections stay pass-through-by-default (`_palette_row` convention).
- MIDI emission needs no change — `note_for(key)` already reads the composed row's note.

### Task 9 — commands, example config, docs

- `runtime_status.py` (parser `:449-465`, validation `:622-634`) + `__main__.py`
  (`_led_palette_command` `:1345-1370` area): add `led_engine <v1|v2>`,
  `led_manual_override <white_sand|red|green|blue>`, `led_manual_clear`, `led_max_energy_toggle`.
  Make `led_palette_queue/override/lock/unlock` v2-aware per D13 (when latched v2: zone names
  valid; palette names rejected with the existing invalid-command surface; lock/unlock = correction
  store/clear).
- `config/led_look_director.example.json`: full `v2` block — all 7 zone ramps with these starting
  values (TUNE-LIVE; RGB triples):
  GLACIER base (10,40,120)/(0,120,255)/(0,220,255), accent (120,240,255)/(210,250,255);
  DEEP_POOL base (5,10,60)/(0,40,140)/(0,90,140), accent (40,0,160)/(0,60,200);
  TWILIGHT base (40,0,90)/(90,0,180)/(140,0,220), accent (180,0,220)/(230,0,180);
  ION base (0,60,255)/(0,180,255)/(60,255,220), accent (140,255,60)/(240,255,220);
  VOLT base (180,0,120)/(255,0,160)/(200,0,255), accent (0,220,255)/(120,255,240);
  EMBERCORE base (120,0,10)/(200,0,30)/(120,0,120), accent (255,30,30)/(255,200,180);
  NEUTRAL base (0,80,200)/(0,160,230)/(0,220,255), accent (0,255,255)/(140,220,255).
  `palette_control` additions: `zone_notes` {GLACIER:62, DEEP_POOL:63, TWILIGHT:64, ION:65,
  VOLT:66, EMBERCORE:67}, `manual_notes` {red:68, green:69, blue:70}, `max_energy_note`: 71,
  `engine_toggle_note`: 72. Tag 2-3 example looks with `motion_style`/`travel`.
- Docs (the union of both contracts' `docs_update`, all mandatory): `docs/subsystems/led_govee.md`,
  `docs/subsystems/runtime_commands.md` (new commands — check_docs_drift enforces this),
  `docs/architecture/palette_control_authority.md` (add a "v2 engine mode" rules section covering
  D1/D2/D12 gestures; do not renumber existing rules), `docs/plans/active/
  streamdeck_palette_control_design_spec.md` (append a v2-surface addendum note),
  `docs/agents/task_playbooks/change_led_govee_behavior.md`, `docs/status/feature_status_matrix.md`,
  `docs/status/support_matrix.md`, `docs/status/validation_matrix.md`,
  `docs/validation/hardware_validation_log.md` (row: v2 F1 = hardware-unvalidated),
  `docs/validation/software_test_inventory.md`, `docs/status/active_work_registry.md` (update the
  AWR-128 row this spec registers). Status language: `implemented`/`software-tested` at most.

### Task 10 — `tools/calibrate_identity_v2.py` (NEW, offline, read-only)

Iterates the local v4 cache via `spectral_cache` public API; per track computes the identity
inputs, scores, zone; prints: zone distribution, `bass_duty` p5/p95 (D11 — then pin those two
numbers into the example config and module docstring), and the anchor checks (STARsound (pt3) →
GLACIER, Can't Say Nah → DEEP_POOL) when present in the cache. No runtime imports of this tool;
no writes. Run it once during implementation and paste its summary into the completion report.

### Task 11 — housekeeping

`.gitignore`: confirm `local/state/led_identity_v2.json` is covered (it must never be committed —
same class as the learned store). Never touch `config/led_look_director.json` (live config,
operator-owned; example only).

---

## Part C — Invariants that MUST still hold (live safety)

1. **200 Hz push loop gains zero blocking I/O** (AGENTS.md §6): dispatch-time identity access is a
   dict read; `os.path.realpath` only on worker/load paths; store writes only via the debounced
   writer thread; derivation/extraction only on the ANLZ worker thread.
2. **v2 config absent ⇒ nothing anywhere changes** — code paths, RNG draws, payloads, deck layout,
   test outcomes. **v2 off/latched-v1 ⇒ v1 light output byte-identical**, including RNG sequences
   (no v2 draw touches `_journey_rng`; no v1 field is written by any v2 path).
3. **Manual always wins:** emergency blackout, LED mute, static overrides, and the layered
   blackout ownership rules are untouched; v2 manual pads are rank 0 *within* v2 but sit BELOW
   blackout/mute exactly like v1 palettes (they recolor looks; they never override a blackout).
4. **No new dark-room failure mode:** every resolution path returns defined colors (NEUTRAL
   fallback); zone ramps validated non-black; palate reset dims, never blacks; bloom fades IN;
   realtime transport loss keeps today's fallback exactly (v2 changes colors/selection only).
5. **Scripted tracks: v2 stands down completely** — the scripted LED path
   (`LEDScriptedModePolicy` remap) renders as v1 in every mode; no identity repaint, no bloom, no
   reset, no zone-pad effect on scripted playback (pads still store corrections for the track, but
   nothing repaints until a non-scripted play).
6. **Mode/engine flips act within one cue step, tear down through `reset_fade_memory` + cleared
   v2 transients — no frame blends across engines** (`beat_sync_engine.py:128-131` reset seam
   untouched and unhooked by v2).
7. **Events are immutable; engine state mutates only on the StateManager thread.** Reader/worker
   threads publish `LED_TRACK_IDENTITY`, never call engine setters.
8. **`ANLZ_PATH` before `TRACK_LOADED` ordering and all reader behavior unchanged** — F1 hooks the
   FILEPATH_RESOLVED handler only.
9. **The store never silently repaints:** `freeze` is first-write-wins; analysis upgrades and
   schema bumps cannot alter a frozen record; only operator corrections (and D5's
   first-play-real-derivation for tracks with NO frozen record) change what a track wears.
10. **Secrets/live config:** live JSON, store files, and `local/` state never committed.

---

## Part D — Tests (new file `tests/test_led_identity_v2.py` + extensions; every algorithm has a pure seam — no file/subprocess dependencies except explicit tmp-path store tests)

1. **Scoring/zones (pure):** `norm` clamps; exact-formula fixtures; frozen-split table tests; the
   five design anchors as fixtures at the score level — STARsound (pt3) (aggression 0.268,
   luminance 0.436) → GLACIER; Can't Say Nah (0.233, 0.267) → DEEP_POOL; LUNCH (aggressive,
   luminance 0.19) → VOLT; distortion 1.0 → EMBERCORE; boundary values land per the exact `>=`
   splits (0.418/0.75/0.52/0.40/0.28).
2. **Dressing (pure):** hash → slot/variant determinism (same key ⇒ same dressing, different keys
   spread); sat_floor/span lerps + clamps; slot 5 always pure white; slot 2 = adjusted core;
   NEUTRAL uses hash spread; non-black guarantee over all 7 example ramps × 16 slots × 3 variants.
3. **Arbiter (pure):** table of overlapping claims → survivor per §6 ranks; rank-0 open claim
   blocks bloom and reset; disjoint windows don't interact.
4. **Store:** load missing → empty; corrupt JSON → empty + degraded, original file not clobbered
   before first legitimate freeze; `freeze` first-write-wins (re-freeze with different record
   returns False, record unchanged); correction set/clear round-trip via `to_dict`; version key.
5. **Engine v2:** byte-identity golden — with v2 config PRESENT but latched v1, a scripted
   sequence of `begin_dispatch`/`resolve_color`/`resolve_slot_colors`/`advance_fade` calls (fixed
   `set_seed`) produces output equal to an engine built WITHOUT the v2 block, and `_journey_rng`
   state (`getstate()`) is identical afterward; flip v2→v1 mid-sequence resumes the same
   downstream v1 outputs as never-flipped (same seed, same calls); v2 resolution: manual override
   short-circuit + evaporation on track change; staged zone commits at the anchor beat, unstage
   works; correction re-derives in the corrected zone with unchanged slot/variant; soft-flip
   `*_from`/`fade_beats` injection on deck flip; palate reset fires on side-flip pairs only, dims
   and expires; bloom: fires once per key per session after the 8-beat hold, skip-not-queue under
   a rank-0 claim, never during blackout (simulate via the reset/blackout path the policy uses);
   exempt looks / `color_source: baked` return `{}` in v2 exactly as v1.
6. **Wiring:** `LED_TRACK_IDENTITY` consumption sets identity + freezes + submits store payload
   exactly once (fresh) / zero times (store-hit); NEUTRAL-for-missing-analysis does NOT freeze;
   `LED_ENGINE_MODE` toggle resolves "toggle" correctly and flips the latch + engine; max-energy
   arm → consumed exactly once at the drop-marker seam with the log line, cleared on track change
   and on flip-to-v1; identity worker hook: with `identity_enabled` and spectral disabled,
   `energy_shadow` stays unpopulated (guard against the smart-rearm leak) — extend
   `tests/test_led_state_manager.py` / the pack-driver harness as the existing integration tests do.
7. **Pads/commands:** zone tap stage/unstage/clear-correction branches; hold = override + stored
   correction (stamps the ACTIVE deck's key); lock/unlock v2 semantics; manual pads set/clear;
   white_sand + rainbow reroutes in v2 (D15) with v1 rainbow-type output equality; v1-latched
   zone-pad no-op; command surface round-trips
   (`led_engine`, `led_manual_override`, `led_max_energy_toggle`, v2-aware `led_palette_*`) —
   extend `tests/test_led_palette_control.py`, `tests/test_soundswitch_midi_input.py`,
   `tests/test_runtime_status.py`.
8. **Deck script:** v2 layout composition (primary + shift layers, D12 exactly); v1 payload ⇒
   today's layout unchanged (regression); engine-toggle-at-key-6 when v1+toggle-row; corrected
   padlock + staged/armed states; stale/absent feedback resets shift — extend
   `tests/test_streamdeck_midi.py`.
9. **Config:** v2 block parse round-trip; each validation failure fails closed with LED config
   still loading v1; note-collision fatal; look tag validation — extend
   `tests/test_led_config.py` / `tests/test_color_engine_config.py`.

---

## Part E — Acceptance (definition of done)

- [ ] Task 0 contract extension landed BEFORE code.
- [ ] `python3 -m unittest discover tests` fully green.
- [ ] Contract test lists green: `python3 -m unittest tests.test_led_state_manager` and
  `python3 -m unittest tests.test_led_palette_control tests.test_led_color_engine
  tests.test_color_engine_config tests.test_led_config tests.test_runtime_status
  tests.test_soundswitch_midi_input tests.test_streamdeck_midi tests.test_state_manager_pack_driver
  tests.test_led_identity_v2`.
- [ ] Hard doc checks green: `python3 tools/check_docs_metadata.py`,
  `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Byte-identity demonstrated, not asserted: the golden test (D-5) plus the full existing LED
  test suite passing unmodified (except files a task explicitly extends).
- [ ] Every doc in Task 9's union list updated; AWR-128 row updated with what actually landed;
  no status word beyond `implemented`/`software-tested`; hardware rows say `hardware-unvalidated`.
- [ ] `tools/calibrate_identity_v2.py` run once locally; its zone distribution + bass p5/p95 +
  anchor checks pasted into the completion report; bass anchors pinned in the example config.
- [ ] No commit contains live config, store files, secrets, or anything under `local/`.
- [ ] Commit per task or logical group; conventional repo style.

## When You Finish

Report: changed files; tests/checks run with real output; the calibration summary; any Blocked/
Cancelled plan items with reasons. Then a plain-language operator summary covering exactly:

- What changes in the room when v2 is latched on (per-track permanent colors, zone pads correct
  them, hold stores forever, white/sand+R/G/B instant manual, first-play bloom, soft handover,
  neutral dip on hard vibe pivots) — and what does NOT change (drops still v1 cues, blackout/mutes/
  static overrides identical, scripted tracks identical, lasers only follow color as before).
- What changes when v2 is OFF: nothing — and where that's proven (golden test + suite).
- The Stream Deck layout (D12) with the note that it's feedback-driven and cheap to re-map at the
  live gate; the max-energy pad arms but renders nothing new until F2 (D10).
- Watchpoints for the first live pass: zone ramp taste (all TUNE-LIVE), bass-anchor calibration
  numbers, soft-flip length, palate-reset feel, bloom visibility, correction store surviving a
  restart.
- Unverified hardware assumptions (Govee latency, deck feedback latency) and rollback: flip
  `led_engine v1` live, or set `v2.enabled=false` / remove the block and restart via the menubar
  watcher (never a raw launch).
