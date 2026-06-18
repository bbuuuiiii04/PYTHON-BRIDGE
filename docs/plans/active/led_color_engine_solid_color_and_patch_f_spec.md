# Codex Implementation Spec — M2.5 Solid-Color (`random_with_mono_chance`) + Patch F Bank Cleanup

**Status:** SPEC — code-grounded, verified against current HEAD `c9db322` on `main` (read 2026-06-18). **Implementation: NOT STARTED.**
**Validation gate:** `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED`. Do **not** claim live-ready / hardware-validated.
**Roles:** Claude authored this spec; **Codex implements** (one patch per session). Standing M2.5 exception (Claude-implemented) does not change the per-patch accept-list discipline.

> Two patches, **in order**: **Patch S** (solid-color strategy + plumbing — pure software, inert by default) then **Patch F** (bank cleanup — **GATED**, see §6/§9-D). Do **not** start F until (1) operator hardware dry-run validates C–E on a real rig, **and** (2) Patch S has landed. Implement exactly one patch per session.

---

## 0. Executive summary

The slot engine (`LedColorEngine.resolve_slot_colors`, `led_color_engine.py:588`) today supports exactly two fill strategies — `gradient_even` and `random_with_replacement`. The operator wants a third, **`random_with_mono_chance`**: with probability `p`, one hue fills palette slots 0–4 (a true solid look); otherwise it behaves byte-for-byte like `random_with_replacement`. Slot 5 stays pure white in every case; the 6-slot model and the seam are unchanged.

Separately, the default look bank still mixes legacy per-color realtime looks (`rt_*_chase_{blue,cyan,red,green,cyan_white}`, the `*_blue_cyan` center cues, `rt_twinkle_blue`) with the new generic engine-colored slot looks. **Patch F** moves (never deletes) the legacy color-suffix looks into a new `legacy_color_suffix` bank and collapses the default bank onto the generic slotized looks, without making solid outcomes unreachable.

- **Patch S** = `led_models.py` + `led_config.py` + `led_color_engine.py` + tracked example config + tests. Default mono probability is **0.0** (opt-in by look), so landing S changes **no observable behavior** until the operator configures a probability. **Not hardware-gated.**
- **Patch F** = config-only (tracked `config/led_look_director.example.json`; live config mirror is operator-gated). **No code changes.** **Hardware-gated.**

---

## Part A — Context & root cause (verified; read, do NOT implement)

### A.1 Current slot engine (CONFIRMED — `led_color_engine.py`)

`resolve_slot_colors(self, *, role, section_id, cycle, look_name, color_source, slot_count=6)` (`:588`). Verbatim current control flow:

- Early returns `{}` (inject nothing) on: engine disabled, `color_source != "engine"`, `look_name in exempt_looks` (`:612-617`). **[confirmed]**
- `palette = self._config.palettes.get(self._current_palette)`; `{}` if `None` (`:619-621`). **[confirmed]**
- `focus_lo, focus_hi = self._focus_window(role)` (`:623`). **[confirmed]**
- `n = 6` — the caller's `slot_count` is intentionally ignored (`:625`). **[confirmed]**
- Strategy resolution (`:627-631`): `slot_fill_strategy_by_look.get(look_name)` → `slot_fill_strategy_by_role.get(role)` → `"gradient_even"`. **[confirmed]**
- **Defensive guard (`:637-638`):** `if strategy not in ("gradient_even", "random_with_replacement"): strategy = "gradient_even"`. **This is the root blocker — a new strategy string here is silently downgraded to gradient.** **[confirmed]**
- `gradient_even` branch (`:641-655`): RNG-free; 5 even gradient draws over `[focus_lo, focus_hi]` + `slots.append((255,255,255))`. **[confirmed]**
- `random_with_replacement` branch (`:656-667`):
  ```python
  use_step = self._config.step_within_section.get(role, False)
  step_index = cycle if use_step else 0
  fill_seed = _blake2b_int(f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1")
  fill_rng = _rng_from_seed(fill_seed)
  for _ in range(5):
      p = fill_rng.uniform(focus_lo, focus_hi)
      p = max(0.0, min(1.0, p))
      rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
      rgb = _blend_white(rgb, palette.white)
      slots.append(rgb)
  slots.append((255, 255, 255))
  ```
  **[confirmed]** Fresh **local** RNG; never touches `self._journey_rng`. Salt `:slotfill:v1` isolates it from `resolve_color`'s un-salted seed (`:545`).
- Shared memo/fade tail (`:669-681`): builds `result = {"slot_colors": slots}`, memo-keys on `(track_key, role, section_id, look_name, "slot_colors")`, sets `slot_colors_from`/`_to` and `fade_beats` (from `fade_beats_by_role[role]`) when a previous fill exists. **Strategy-agnostic — any branch that produces `slots` inherits it unchanged.** **[confirmed]**

Helpers reused verbatim (do not re-derive): `_blake2b_int` (`:118`), `_rng_from_seed` (`:125`), `_p_to_rgb` (`:64`), `_blend_white` (`:105`, second arg is a float in `[0,1]`), `self._stop_positions`, `self._current_track_seed`, `self._focus_window`. **[confirmed]**

### A.2 Config plumbing (CONFIRMED)

- `led_models.py:80-116` `ColorEngineConfig` (frozen dataclass) already carries `slot_fill_strategy_by_look` / `slot_fill_strategy_by_role` (`:111-112`, `Dict[str,str] = field(default_factory=dict)`). **No `slot_mono_chance_by_look` field exists.** **[confirmed]**
- `led_config.py:955-971` validates both strategy dicts: each value must be `"gradient_even"` or `"random_with_replacement"` else an error is appended (this disables only the engine, never LED — `_parse_color_engine` returns `None` on any error, `:1099-1105`). **[confirmed]**
- `led_config.py:1147-1153` parses the two strategy dicts; `:1166-1183` constructs `ColorEngineConfig`. **[confirmed]**
- Number-dict validators to mirror: `role_spread` (`:938-944`), `fade_beats_by_role` (`:974-980`) reject non-number / bool. **[confirmed]**

### A.3 Renderer / slot effects (CONFIRMED — `govee_frame_renderer.py`)

- `SLOT_EFFECTS` (`:1796-1811`) — generic engine slot looks present: `rt_groove_chase`, `rt_groove_nebula`, `rt_post_drop_chase`, `rt_post_drop_nebula`, `rt_drop_chase`, `rt_drop_nebula`, `rt_drop_center_burst`, `rt_post_drop_center_comet`, `rt_twinkle`, plus Phase-2a `groove_center_chase`, `groove_center_burst_retract`, `post_drop_firework_chase`, `breakdown_full_breathing`, `breakdown_star_twinkle`. **[confirmed]** → **Patches A–E are implemented in code.**
- `_M2_PHASE2A_PARAM_KEYS` (`:1842-1864`) registers every slot effect with `{"duration_beats"} | _SYNC_PARAM_KEYS`; **`slot_colors` is deliberately NOT allowlisted** (runtime-injected). **[confirmed]**
- `render()` (`:1902-1952`): for `name in SLOT_EFFECTS`, runs the slot fn → `universal_colorizer(field, slot_colors)`; missing `slot_colors` falls back to `_DEFAULT_SLOT_COLORS = [(255,255,255)]` (fails bright, never crashes). **[confirmed]**
- Baked `breakdown_star_twinkle_sand` is in `_EFFECTS` (returns a `Frame`), NOT `SLOT_EFFECTS`. **[confirmed]**

### A.4 Seam (CONFIRMED — `state_manager.py:1724-1761`)

`slot_based = scene_ref_for_multi in SLOT_EFFECTS` (`:1727`) → `engine.resolve_slot_colors(role, section_id, cycle, look_name=decision.look, color_source=..., slot_count=MAX_SLOTS)` (`:1730-1737`) → merges `computed` into `decision.params` (`:1758-1761`). Any exception sets `_led_last_error` and leaves the decision unmodified. **No `fill_strategy` kwarg.** **[confirmed]** **Neither patch changes this seam.**

### A.5 Director bank selection (CONFIRMED — `led_look_director.py`)

The director reads **only `self._config.banks.get("default")`** (`:59, :190, :200, :265`). **[confirmed]** ⇒ any non-`default` bank (e.g. `legacy_color_suffix`) is **never selected at runtime** — it is pure storage that preserves definitions while removing them from rotation. Bank schema supports arbitrary bank names (`banks: Dict[str, LEDBank]`, `led_models.py:180`; `_validate_bank` `led_config.py:420-447`).

### A.6 LIVE vs EXAMPLE config divergence (CONFIRMED — read both 2026-06-18)

| Axis | `config/led_look_director.json` (LIVE; `enabled:true,dry_run:false`) | `config/led_look_director.example.json` (tracked; `enabled:false,dry_run:true`) |
|---|---|---|
| `color_engine.slot_fill_strategy_by_look` | `{"rt_groove_chase":"random_with_replacement"}` | same |
| `slot_fill_strategy_by_role` | absent | absent |
| Generic looks `rt_twinkle`, `rt_post_drop_center_comet` | **MISSING (look defs + bank entries)** | present |
| `default.ambient` | `[ambient_pb_halves, rt_twinkle_blue]` | `[ambient_pb_halves, rt_twinkle_blue, rt_twinkle]` |
| `default.post_drop` | …`rt_post_drop_center_comet_blue_cyan`, `rt_post_drop_firework_chase`] (no generic comet) | …`rt_post_drop_center_comet_blue_cyan`, `rt_post_drop_center_comet`, `rt_post_drop_firework_chase`] |

**Consequence [confirmed]:** E2/E3 generics are *coded + in example* but **not yet live-reachable**. Patch F's live-config mirror must therefore *add* `rt_twinkle` and `rt_post_drop_center_comet` to the live config before collapsing rotation. The example config (which CI tests load) is already complete.
**[assumed]** the live config is gitignored and operator-owned; CI cannot read it. Treat live edits as operator-gated.

### A.7 Root cause

The strategy was capped at two by the M2.5 master spec (Rule 3) on purpose. Adding a third is a small, additive engine branch + a single new config field + two validator/guard allowlist extensions. The only non-obvious correctness requirement is the **RNG-stream choice** (§B.2): the mono decision must not perturb the existing fill stream, so chance `0.0` is provably identical to `random_with_replacement`.

---

## 1. Confirmed current code state (audit answers)

| Question | Answer |
|---|---|
| Which M2.5 pieces are implemented? | A (engine strategy + 6-slot invariant + plumbing), B (`_slot_groove_chase`), C (`_slot_post_drop_chase`), D (`_slot_drop_chase`, `_slot_drop_center_burst`), E1 (nebula family: `_slot_groove_nebula` + `rt_drop_nebula`/`rt_post_drop_nebula`), E2 (`_slot_post_drop_center_comet`), E3 (`_slot_twinkle`). **[confirmed via `SLOT_EFFECTS` + test files]** |
| C/D/E looks in `SLOT_EFFECTS`? | `rt_post_drop_chase`, `rt_drop_chase`, `rt_drop_nebula`, `rt_drop_center_burst`, `rt_post_drop_center_comet`, `rt_groove_nebula`, `rt_post_drop_nebula`, `rt_twinkle` (+ B's `rt_groove_chase`). **[confirmed]** |
| New generic looks in config (example)? | `rt_groove_chase`, `rt_drop_chase`, `rt_post_drop_chase`, `rt_drop_center_burst`, `rt_post_drop_center_comet`, `rt_groove_nebula`, `rt_drop_nebula`, `rt_post_drop_nebula`, `rt_twinkle`, `rt_post_drop_firework_chase`, `rt_groove_center_chase`, `rt_groove_center_burst_retract`, `rt_breakdown_full_breathing`, `rt_breakdown_star_twinkle`. **[confirmed]** |
| Legacy looks still in default rotation? | `rt_{groove,drop,post_drop}_chase_{blue,cyan,red,green,cyan_white}`, `rt_drop_center_burst_blue_cyan`, `rt_post_drop_center_comet_blue_cyan`, `rt_twinkle_blue`, plus the three `*_freestyle_nebula`. **[confirmed]** |
| Legacy looks exempt/baked? | All `*_freestyle_nebula`, `rt_twinkle_blue`, `rt_drop_center_burst_blue_cyan`, `rt_post_drop_center_comet_blue_cyan`, white utility/strobe looks, and all DIY/cloud looks are in `exempt_looks` (engine injects nothing). `rt_breakdown_star_twinkle_sand` is `color_source:"baked"`. **[confirmed]** |
| Tests for A–E? | `test_color_engine_config.py`, `test_led_color_engine.py`, `test_led_color_engine_m2_phase2b.py`, `test_led_color_engine_m2_patch_{b,c,d,e1,e2,e3}.py`, `test_govee_frame_renderer.py`. **[confirmed present]** |
| Can the code import/run (static read)? | Yes — imports + registries are internally consistent; `random_with_mono_chance` is simply absent. **[confirmed by reading]** **[unknown]** — not executed; Codex must run the suite. |
| Is current "solid" only degenerate-focus? | **Yes.** A true solid only happens today when `focus_lo == focus_hi` (point palette like `["red","red"]` or `mono` focus collapsing the window) — `uniform(x,x)=x`. No live palette is a point range, so true probabilistic mono does **not** exist. `random_with_mono_chance` adds it. **[confirmed]** |

---

## Part B — Patch S tasks (implement exactly, in order; commit once at the end after all tests pass)

### Absolute rules (Patch S)

- **Do NOT touch:** the seam (`state_manager.py:1724-1761`); the `resolve_slot_colors` 6-kwarg signature; the fade memo key; `self._journey_rng`; the palette/focus/dwell/drop-snap logic; `resolve_color`; any `_slot_*` fn or `SLOT_EFFECTS`/`_M2_PHASE2A_PARAM_KEYS`/`_EFFECTS` entry; `exempt_looks`; lasers / Rekordbox / SoundSwitch.
- **The `gradient_even` and `random_with_replacement` branches must stay byte-for-byte unchanged.** A `git diff` of those two branches must be empty. The new strategy is a **third, additive `elif`** placed *after* the `random_with_replacement` branch.
- **Slot model stays exactly 6 slots; slot 5 is always `(255,255,255)` in every output.**
- **Static config param allowlists must never include `slot_colors`** (it is runtime-injected) — this patch does not touch param allowlists at all.
- Verify file:line anchors against current code before editing (they were correct at HEAD `c9db322`; re-confirm).

### Task S-1 — `led_models.py`: add the mono-chance config field

In `ColorEngineConfig` (`:80-116`), immediately **after** `slot_fill_strategy_by_role` (`:112`), add:

```python
    slot_mono_chance_by_look: Dict[str, float] = field(default_factory=dict)
```

Do not add `slot_mono_chance_by_role` (out of scope — see §8). `Dict` is already imported (`:9`).

### Task S-2 — `led_config.py`: accept the new strategy + validate the new field

**(a)** In `_validate_color_engine`, extend **both** strategy allowlists to add `"random_with_mono_chance"`:

- `:961` — change the membership test to `if strategy_val not in ("gradient_even", "random_with_replacement", "random_with_mono_chance"):` and update the error message accordingly.
- `:970` — same change for `slot_fill_strategy_by_role`.

**(b)** Add a validator for the new number-in-`[0,1]` dict. Place it directly after the `slot_fill_strategy_by_role` block (after `:971`), mirroring the structure of the `fade_beats_by_role` validator (`:974-980`) but with a closed `[0,1]` range and an explicit `bool` rejection:

```python
    # slot_mono_chance_by_look: dict of str -> number in [0, 1]
    slot_mono_chance_by_look = data.get("slot_mono_chance_by_look", {})
    if not isinstance(slot_mono_chance_by_look, dict):
        errors.append("color_engine.slot_mono_chance_by_look must be an object")
    else:
        for look_name, chance_val in slot_mono_chance_by_look.items():
            if not isinstance(chance_val, (int, float)) or isinstance(chance_val, bool):
                errors.append(f"color_engine.slot_mono_chance_by_look.{look_name} must be a number")
            elif not (0.0 <= float(chance_val) <= 1.0):
                errors.append(f"color_engine.slot_mono_chance_by_look.{look_name} must be in [0, 1]")
```

**(c)** In `_parse_color_engine`, parse the field (after the strategy dicts, `:1153`):

```python
    # Build slot_mono_chance_by_look
    mono_chance_raw = raw.get("slot_mono_chance_by_look", {})
    slot_mono_chance_by_look: dict[str, float] = {k: float(v) for k, v in mono_chance_raw.items()}
```

and pass `slot_mono_chance_by_look=slot_mono_chance_by_look,` into the `ColorEngineConfig(...)` constructor (`:1166-1183`), beside `slot_fill_strategy_by_role=...`.

After S-2, the existing live config (which has no `slot_mono_chance_by_look`) must still validate and load with the field defaulting to `{}`. Run the config tests + load both configs before continuing.

### Task S-3 — `led_color_engine.py`: add the `random_with_mono_chance` branch

**(a)** Extend the defensive guard (`:637-638`) to include the new strategy so it is not downgraded to gradient:

```python
        if strategy not in ("gradient_even", "random_with_replacement", "random_with_mono_chance"):
            strategy = "gradient_even"
```

**(b)** Add a **new** `elif` branch immediately **after** the `random_with_replacement` branch (after `:667`, before the shared `result = {"slot_colors": slots}` tail at `:669`). Do not modify the two existing branches:

```python
        elif strategy == "random_with_mono_chance":
            use_step = self._config.step_within_section.get(role, False)
            step_index = cycle if use_step else 0
            mono_chance = self._config.slot_mono_chance_by_look.get(look_name, 0.0)
            # Dedicated, clearly-named mono stream — keeps the `:slotfill:v1` fill
            # stream byte-identical on a miss (so chance==0.0 == random_with_replacement)
            # and never touches self._journey_rng.
            mono_seed = _blake2b_int(
                f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:mono:v1"
            )
            mono_rng = _rng_from_seed(mono_seed)
            if mono_rng.random() < mono_chance:
                # MONO HIT: one hue fills palette slots 0-4.
                p = mono_rng.uniform(focus_lo, focus_hi)
                p = max(0.0, min(1.0, p))
                rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
                rgb = _blend_white(rgb, palette.white)
                for _ in range(5):
                    slots.append(rgb)
                slots.append((255, 255, 255))
            else:
                # MONO MISS: identical to random_with_replacement (same fill stream).
                fill_seed = _blake2b_int(
                    f"{self._current_track_seed}:{section_id}:{step_index}:slotfill:v1"
                )
                fill_rng = _rng_from_seed(fill_seed)
                for _ in range(5):
                    p = fill_rng.uniform(focus_lo, focus_hi)
                    p = max(0.0, min(1.0, p))
                    rgb = _p_to_rgb(p, self._config.scale_stops, self._stop_positions)
                    rgb = _blend_white(rgb, palette.white)
                    slots.append(rgb)
                slots.append((255, 255, 255))
```

The shared memo/fade tail (`:669-681`) then runs unchanged for all three strategies.

> **Why a separate `:slotfill:mono:v1` stream (DECISION, justified):** if the mono roll were drawn from the existing `:slotfill:v1` stream, consuming `random()` would shift the 5 subsequent `uniform()` draws, so the miss path would **not** equal `random_with_replacement`. A dedicated stream that owns *both* the probability roll *and* (on a hit) the single hue keeps the miss path byte-identical and isolates the decision. `random()` returns `[0.0, 1.0)`, so `< 0.0` is never true ⇒ `chance==0.0` always misses ⇒ provably identical to `random_with_replacement`; `< 1.0` is always true ⇒ `chance==1.0` always mono.

> **Rejected alternative:** merging the two random branches into one shared loop (parameterized by a `mono` bool). It is more elegant but edits the frozen `random_with_replacement` branch; the additive `elif` keeps that branch's diff empty, which is the lower-risk choice the operator asked for ("preserve the existing two strategies").

### Task S-4 — tracked example config: document the knob (behavior-neutral)

In `config/led_look_director.example.json`, inside the `color_engine` object, add an **empty** key so the field is documented and validated with zero behavior change:

```json
    "slot_mono_chance_by_look": {},
```

Do **not** flip any look to `random_with_mono_chance` in the shipped example. **Reachability is proven by tests using in-test configs (§D), not by shipping a nonzero default.** The operator's actual opt-in (recommended values below) is applied at the hardware gate, by look, to the live config.

**Recommended initial opt-in (operator-gated; NOT part of the committed example):**
- `rt_groove_chase` → strategy `random_with_mono_chance`, chance `0.15` (already the random testbed look).
- `rt_post_drop_chase` → strategy `random_with_mono_chance`, chance `0.15`.
- Leave `rt_drop_chase` on `gradient_even` initially (drop snaps; higher visual impact — defer).
- **Not** nebula / twinkle / center cues initially (atmospheric/ambient — a forced solid reads worse there).
- Do **not** promote via `slot_fill_strategy_by_role` (blast-radius: a role strategy flips *every* slot cue in that role). By-look only.

---

## Part B (cont.) — Patch F tasks (config-only; GATED — see §6/§9-D; commit once after all tests pass)

### Absolute rules (Patch F)

- **No code changes.** Config only (`config/led_look_director.example.json` is the authoritative, CI-tested edit; the live config mirror is an operator-gated checklist, §F-5).
- **Delete nothing:** no look definition, no `_EFFECTS`/`SLOT_EFFECTS` entry, no `exempt_looks` entry, no legacy `drop_pairs` entry is removed.
- **Do not make solid unreachable:** the default bank must retain generic engine slot looks that can carry `random_with_mono_chance` (see §F-4).
- `safe_default`, `blackout`, `safety`, `targets` untouched.
- Every default-bank look name must resolve to a look definition; every default-bank realtime `scene_ref` must be in `_EFFECTS` or `SLOT_EFFECTS`.

### Task F-1 — add the `legacy_color_suffix` bank (storage only)

Add a second bank under `banks` (sibling of `default`). It must contain **all 8 role keys** (`_validate_bank` errors on any missing role). `utility` must stay `[]` (only `cloud_diy` looks may appear in `utility`; these are `realtime_razer`). Populate with the looks moved out of `default` in F-2:

```json
    "legacy_color_suffix": {
      "ambient": ["rt_twinkle_blue"],
      "groove": ["rt_groove_chase_blue", "rt_groove_chase_cyan", "rt_groove_chase_red", "rt_groove_chase_green", "rt_groove_chase_cyan_white"],
      "buildup": [],
      "pre_drop": [],
      "drop": ["rt_drop_chase_blue", "rt_drop_chase_cyan", "rt_drop_chase_red", "rt_drop_chase_green", "rt_drop_chase_cyan_white", "rt_drop_center_burst_blue_cyan"],
      "post_drop": ["rt_post_drop_chase_blue", "rt_post_drop_chase_cyan", "rt_post_drop_chase_red", "rt_post_drop_chase_green", "rt_post_drop_chase_cyan_white", "rt_post_drop_center_comet_blue_cyan"],
      "breakdown": [],
      "utility": []
    }
```

### Task F-2 — collapse the `default` bank onto generics (move legacy out)

Edit `banks.default` so each role becomes exactly (order preserved otherwise):

- **ambient:** `["ambient_pb_halves", "rt_twinkle"]` — remove `rt_twinkle_blue`.
- **groove:** keep the 7 `groove_diy_*`, `rt_groove_chase`, `rt_groove_nebula`, `rt_groove_freestyle_nebula`, `rt_groove_center_chase`, `rt_groove_center_burst_retract`; remove the five `rt_groove_chase_{blue,cyan,red,green,cyan_white}`.
- **buildup:** unchanged (no legacy color-suffix looks here).
- **drop:** keep the 8 `drop_diy_*`, `rt_drop_chase`, `rt_drop_nebula`, `rt_drop_chase_freestyle_nebula`, `rt_drop_white_aggressive`, `rt_drop_center_burst`; remove the five `rt_drop_chase_{…}` and `rt_drop_center_burst_blue_cyan`.
- **post_drop:** keep `rt_post_drop_chase`, `rt_post_drop_nebula`, `rt_post_drop_freestyle_nebula`, `rt_post_drop_center_comet`, `rt_post_drop_firework_chase`; remove the five `rt_post_drop_chase_{…}` and `rt_post_drop_center_comet_blue_cyan`.
- **breakdown:** unchanged.
- **utility:** unchanged (`["room_blackout"]`).

**Retention decisions (DECIDED; the freestyle-nebula one requires operator visual sign-off at the F gate):**
- `rt_twinkle_blue` → **legacy** (generic `rt_twinkle` replaces it). DECIDED.
- `rt_drop_center_burst_blue_cyan`, `rt_post_drop_center_comet_blue_cyan` → **legacy** (generic `rt_drop_center_burst` / `rt_post_drop_center_comet` replace them). DECIDED.
- All `rt_*_chase_{color}` → **legacy** (generic `rt_*_chase` replace them). DECIDED.
- The three `*_freestyle_nebula` → **KEEP in default** as signature baked/exempt variants. Rationale: they are `exempt_looks` (engine injects nothing, so they don't interact with the slot/solid pipeline) and the generic `rt_*_nebula` slot looks dropped the breathing-bg layer, so they are *not* visually redundant. **Operator must confirm this visual call before F runs**; the alternative (move all three to a `legacy_baked` bank) is a one-line follow-up.
- Cloud/DIY scenes (`groove_diy_*`, `drop_diy_*`, `breakdown_*`, `buildup_diy_*`, `ambient_pb_halves`) → **stay as-is** in default. They are cloud-baked, cannot be per-slot runtime-colored, ride the `diy_color_tags` cohesion path, and are out of scope for realtime slot cleanup. DECIDED.

### Task F-3 — drop_pairs: generic drop → generic post-drop

Add to `drop_pairs` (do not remove the legacy pairs — they stay valid and inert because the legacy bank is never selected):

```json
    "rt_drop_chase": { "post_drop": "rt_post_drop_chase", "duration_beats": 8.0 },
```

`rt_drop_nebula → rt_post_drop_nebula`, `rt_drop_center_burst → rt_post_drop_center_comet`, and `rt_drop_chase_freestyle_nebula → rt_post_drop_freestyle_nebula` already exist (`led_look_director.example.json:204-220`) — leave them. **[confirmed]**

### Task F-4 — keep solid reachable (guardrail)

After F-2, the default bank still contains `rt_groove_chase` (groove) plus the other generic slot looks. Solid remains reachable iff at least one default-bank engine slot look is opted into `random_with_mono_chance` with chance `> 0`. The committed example stays at chance `0.0` (§S-4); reachability is enforced by the F test that a default-bank generic slot look configured with `random_with_mono_chance @ 1.0` yields a mono vector (§D). Operator applies real probabilities to the live config at the hardware gate.

### Task F-5 — live-config mirror (operator-gated checklist; NOT a Codex edit unless instructed)

The live `config/led_look_director.json` is operator-owned and behind the example (§A.6). Before F is considered done **for the live rig**, the operator (or Codex, only if explicitly told to edit the live file) must, in this order:
1. Add the `rt_twinkle` and `rt_post_drop_center_comet` **look definitions** (copy verbatim from the example) — they are absent live.
2. Add `rt_twinkle` to `default.ambient` and `rt_post_drop_center_comet` to `default.post_drop`.
3. Apply F-1/F-2/F-3 to the live config.
4. Run the loader against the live path (§E) and confirm zero errors; the config is live-ready (`dry_run:false`), so any placeholder/unmapped ref will hard-fail.

---

## Part C — Invariants that MUST still hold (live safety)

- **6-slot model; slot 5 == `(255,255,255)`** in every `slot_colors` output, every strategy. (`runtime_invariants` / M2.5 Rule 2.)
- **`self._journey_rng` is never read or advanced** by `resolve_slot_colors` — palette journey, dwell, and drop-snap streams are untouched. Patch S uses only fresh local RNGs.
- **`resolve_color` determinism is unperturbed** — Patch S adds no statements on its path; existing `resolve_color` asserts must stay byte-identical.
- **Engine-off / `color_source!="engine"` / exempt → `{}`** (inject nothing) is unchanged for all strategies.
- **No new engine instance state.** Mono is a pure per-call computation; the only mutable state touched is the existing `_prev_color` memo (already cleared on new track `:367` and via `reset_fade_memory()` `:325`). No new field to clean up on any mode transition (idle / scripted / autoloop / drop-snap). [adversarial check: confirmed there is no per-strategy state that could leak across tracks or modes.]
- **Seam unchanged**; the merge-not-replace `{**decision.params, **computed}` (`:1760`) preserves `sync_mode`/`beat_division`/etc.
- **Static param allowlists never gain `slot_colors`.**
- **Patch F:** the `default` bank never references an undefined look or an unregistered `scene_ref` (would disable ALL LED). `safe_default`/`blackout`/`safety` untouched. The push loop gains no I/O (config-only).
- **One bridge process** after any restart: `pgrep -f rb_ss_bridge_v2 | wc -l == 1`.

---

## Part D — Tests

Run after **every** file edit where practical; the full LED suite + config load must pass before declaring a patch done. Do **not** edit existing tests to make new behavior pass.

### Patch S — config tests → extend `tests/test_color_engine_config.py`
Mirror the existing `slot_fill_strategy_*` tests (`:321-398`):
- `slot_mono_chance_by_look` defaults to `{}` when absent (parsed config).
- Valid values carried: `{"rt_groove_chase": 0.0, "rt_x": 1.0, "rt_y": 0.15}` → engine available, values float-equal.
- Validator: `slot_fill_strategy_by_look`/`_by_role` now **accept** `"random_with_mono_chance"` (engine available).
- Validator rejects (engine `None`, LED still available): mono chance `< 0`; `> 1`; non-number string (`"high"`); **bool** `True` (must be rejected as non-number); `slot_mono_chance_by_look` not an object.
- Regression: the tracked example config still loads with zero errors and `slot_mono_chance_by_look == {}`.

### Patch S — engine tests → new `tests/test_led_color_engine_m2_patch_s.py`
Use the `_engine(*, enabled=True, **overrides)` idiom from `tests/test_led_color_engine_m2_phase2b.py:49-61` (a wide `blue_cyan` palette, `set_seed_mode="fixed:12345"`), call `engine.begin_dispatch(...)` once to seed a track, then `engine.resolve_slot_colors(...)`:
- **Mono @ 1.0:** `slot_mono_chance_by_look={"L":1.0}`, strategy `random_with_mono_chance` → `slot_colors[0..4]` all equal; `slot_colors[5] == (255,255,255)`; length 6.
- **Mono @ 0.0 == random_with_replacement:** for identical engine/inputs, the output of strategy `random_with_mono_chance` (chance `0.0`) equals the output of strategy `random_with_replacement` **exactly** (byte-identical list). (Build two engines with the same `set_seed`/palette/`begin_dispatch`, differing only in strategy/chance.)
- **Mono produces varied (non-degenerate) output at intermediate chance** under a wide palette across many `(section_id, cycle)` inputs: some cycles mono (all-equal 0–4), some not — both occur. (Sweep cycles/sections; assert both a mono and a non-mono vector appear.)
- **Determinism:** identical `(set_seed, deck/load_gen/content, role, section_id, cycle, look_name)` → identical `slot_colors` across two engine instances.
- **Stepping:** with `step_within_section[role]=True`, different `cycle` may change the vector; with `=False`, the vector is identical across cycles. (Same contract as `random_with_replacement`.)
- **White blend parity:** mono hue uses `_blend_white(rgb, palette.white)` — set `palette.white=0.5` and assert the mono RGB is shifted toward white identically to a gradient draw at the same `p` is not required, but assert the mono RGB != the un-blended `_p_to_rgb` value when `white>0`.
- **Degenerate focus still solid:** a point palette (`range=("red","red")`) under `random_with_replacement` and under `random_with_mono_chance@0.0` both yield all-equal 0–4 (existing behavior preserved).
- **Drop snap/fade unchanged:** with `fade_beats_by_role["drop"]=0` no `fade_beats` key appears; with a role whose `fade_beats>0` and a changed fill across cycles, `slot_colors_from`/`_to`/`fade_beats` appear (memo tail is strategy-agnostic — assert it fires for the mono strategy too).
- **`_journey_rng` untouched:** snapshot `engine._journey_rng.getstate()` before/after a `resolve_slot_colors(random_with_mono_chance)` call → unchanged.
- **Defensive guard:** a `ColorEngineConfig` built directly (bypassing the loader) with an unknown `slot_fill_strategy_by_look` value still produces a valid 6-slot gradient vector (fail-safe).
- **Allowlist regression:** `"slot_colors"` is in **no** value of `_M2_PHASE2A_PARAM_KEYS` nor `REALTIME_EFFECT_PARAM_KEYS`.
- **`gradient_even` unchanged:** golden equality of a `gradient_even` vector vs the pre-patch expected values (lock the existing output).
- Existing suites (`test_led_color_engine.py`, `…_m2_phase2b`, `…_m2_patch_{b,c,d,e1,e2,e3}`) still pass.

### Patch F — new `tests/test_led_color_engine_m2_patch_f.py`
Load the tracked example via `load_led_look_director_config(example_path)`:
- Example config validates (zero errors).
- `default.groove` / `default.drop` / `default.post_drop` / `default.ambient` contain **none** of the legacy color-suffix looks (`rt_*_chase_{color}`, `*_blue_cyan`, `rt_twinkle_blue`).
- Bank `legacy_color_suffix` exists and contains exactly the moved looks (per F-1).
- Every look name in `default` **and** in `legacy_color_suffix` resolves to a look definition.
- Every realtime `scene_ref` referenced by default-bank looks is in `_EFFECTS` ∪ `SLOT_EFFECTS`.
- Generic looks are in their expected default roles (`rt_groove_chase`∈groove, `rt_drop_chase`∈drop, `rt_post_drop_chase`∈post_drop, `rt_twinkle`∈ambient, `rt_post_drop_center_comet`∈post_drop).
- Legacy baked/exempt looks remain in `exempt_looks`; new generics are **not** in `exempt_looks` and have `color_source=="engine"`.
- `drop_pairs["rt_drop_chase"].post_drop == "rt_post_drop_chase"`; all `drop_pairs` keys/targets resolve to defined looks.
- Legacy look definitions still resolve (regression).
- No static `params.slot_colors` anywhere in the config (scan all looks).
- Reachability guardrail: a default-bank generic slot look (e.g. `rt_groove_chase`) configured with `random_with_mono_chance @ 1.0` yields a mono `slot_colors` vector (proves F did not foreclose solid).
- Full LED suite (`python3 -m unittest discover tests`) passes.

### Docs / status (both patches)
Per the `led_govee` + `config_schema` contracts (`docs/agents/change_contracts.yml`), update the docs in `docs_update` and the status matrices to state: **`random_with_mono_chance` software-validated only; Patch F software-validated only; HARDWARE-UNVALIDATED until the operator tests the rig.** Run the four `tools/check_docs_*.py` checks; bump `last_verified_commit` on the touched contracts.

---

## Part E — Acceptance (definition of done)

**Patch S:**
- [ ] `git diff led_color_engine.py` shows the `gradient_even` and `random_with_replacement` branches **unchanged**; only the guard line + the new `elif` are added.
- [ ] New config field validates; `[0,1]` enforced; bool/non-number/`<0`/`>1` rejected (engine off, LED stays available).
- [ ] Both strategy allowlists accept exactly `{gradient_even, random_with_replacement, random_with_mono_chance}`.
- [ ] Mono@1.0 → slots 0–4 equal, slot 5 white; mono@0.0 == `random_with_replacement` byte-identical; determinism + stepping proven.
- [ ] `_journey_rng` and `resolve_color` determinism unperturbed.
- [ ] Example config gains empty `slot_mono_chance_by_look`; loads clean; live config still loads.
- [ ] Full LED suite + four doc checks green. Status docs say software-validated-only / hardware-unvalidated.

**Patch F (only after the gate):**
- [ ] Default bank free of legacy color-suffix looks; `legacy_color_suffix` bank holds them; nothing deleted.
- [ ] All default + legacy bank look names resolve; all default scene_refs registered; generics in expected roles; exempt/baked unchanged; generics non-exempt + engine.
- [ ] `drop_pairs` generic drop → generic post-drop; legacy pairs intact.
- [ ] Solid reachable (guardrail test passes). No static `slot_colors`.
- [ ] Example config validates; full LED suite + doc checks green; status docs updated; live-config mirror checklist (§F-5) recorded for the operator.

---

## §D Sequencing decision (justified)

**Option 1 — two patches, Patch S then Patch F.** CHOSEN.
- **S must precede F** so solid exists before rotation collapses; otherwise F would leave a window where the default bank is all generics that can only do gradient/random and the operator's "solid possible" intent is unmet.
- The surfaces are disjoint (S = engine + config plumbing/validation; F = config banks), so separate accept-lists give cleaner review and rollback.
- **F is hardware-gated; S is not** (S is inert by default). Bundling would needlessly drag S behind F's hardware gate.
- Both remain `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED`. A combined patch is **rejected**: it conflates a testable code change with a hardware-gated config reorg.

---

## §8 Out of scope (do NOT do)

- `slot_mono_chance_by_role` or any role-wide mono default (by-look opt-in only; role flips every slot cue in the role).
- Changing the seam, the `resolve_slot_colors` signature, the fade memo key, `self._journey_rng`, `resolve_color`, palette/focus/dwell/drop-snap, or any `_slot_*`/`SLOT_EFFECTS`/`_EFFECTS`/`_M2_PHASE2A_PARAM_KEYS` entry.
- Deleting/renaming any legacy look, effect, renderer fn, `exempt_looks` entry, or legacy `drop_pairs` entry.
- Adding `slot_colors` to any static param allowlist.
- Flipping the shipped example config to a nonzero mono chance, or editing the live config in Patch S.
- Touching laser / Rekordbox / SoundSwitch / DIY-cloud behavior.
- Claiming hardware-validated / live-ready / show-ready.
- A second `mono` strategy variant, weighting knobs, `slot_repeat_bias`, etc. (nothing consumes them).

---

## §9 Risks / adversarial review

1. **RNG perturbation breaks existing cues.** Mitigated: separate `:slotfill:mono:v1` stream; the miss path reuses the exact `:slotfill:v1` fill stream ⇒ byte-identical at chance 0. *Test directly asserts equality with `random_with_replacement`.* Attack tried: "does constructing `mono_rng` on every call cost a `_blake2b_int` even when strategy is `random_with_replacement`?" — No: the mono block is inside the `random_with_mono_chance` elif only; the other branches are untouched.
2. **Defensive guard silently downgrades the new strategy** (would make mono a no-op that's hard to spot). Mitigated: guard explicitly extended; a test constructs the strategy and asserts mono behavior, not gradient.
3. **Validation lets a bool through** (`True == 1`, `0 <= True <= 1`). Mitigated: explicit `isinstance(chance_val, bool)` rejection + a test for `True`.
4. **Patch F disables ALL LED** by leaving a default-bank look referencing a missing definition or unregistered scene_ref. Mitigated: F test resolves every default + legacy bank look and every scene_ref; F is config-only and CI loads the example.
5. **Patch F makes solid unreachable** by removing the only mono-capable look. Mitigated: §F-4 guardrail + reachability test; `rt_groove_chase` stays in default.
6. **LIVE config drift** (§A.6): generics missing live means F's collapse would orphan post_drop/ambient if applied naively to live. Mitigated: §F-5 ordered checklist adds the missing generics *before* collapsing; CI tests run on the complete example, not live.
7. **`legacy_color_suffix` bank fails validation** for a missing role or a non-cloud_diy look in `utility`. Mitigated: all 8 roles present; `utility:[]`.
8. **Operator visual call on freestyle nebula** is the one non-mechanical F decision. Surfaced explicitly; reversible; gated behind hardware sign-off anyway.
9. **Stale line anchors.** Codex must re-verify each file:line before editing (HEAD may have advanced past `c9db322`).

---

## §10 Paste-ready Codex prompts

### Codex Prompt 1 — implement solid-color slot fill (`random_with_mono_chance`) ONLY

```
Implement Patch S from docs/plans/active/led_color_engine_solid_color_and_patch_f_spec.md (Part B, Tasks S-1..S-4). Do NOT implement Patch F.

Rules:
- Verify every file:line anchor in the spec against current code BEFORE editing (HEAD may have moved past c9db322). If reality differs from the spec, STOP and report — do not guess.
- Edit only: led_models.py, led_config.py, led_color_engine.py, config/led_look_director.example.json, and the named test files. Do NOT touch the state_manager seam, the resolve_slot_colors signature, the fade memo key, self._journey_rng, resolve_color, palette/focus/dwell/drop-snap, any _slot_*/SLOT_EFFECTS/_EFFECTS/_M2_PHASE2A_PARAM_KEYS entry, exempt_looks, or laser/RB/SS code.
- The gradient_even and random_with_replacement branches must remain byte-for-byte unchanged: add a THIRD additive elif after random_with_replacement, and only extend the defensive guard allowlist. `git diff led_color_engine.py` must show no edits inside the two existing branches.
- Slot model stays 6 slots; slot 5 is always (255,255,255). Never add slot_colors to any param allowlist. Default mono chance is 0.0 (chance==0.0 must be byte-identical to random_with_replacement — prove it with a test). Use a dedicated :slotfill:mono:v1 RNG stream; never use self._journey_rng or global random.
- Do NOT flip the shipped example to a nonzero chance; add only the empty "slot_mono_chance_by_look": {}.

After EACH file edit, run: python3 -m unittest discover tests, and load BOTH config/led_look_director.example.json and config/led_look_director.json through load_led_look_director_config — all must pass with zero errors before moving on.

Add tests exactly as in the spec's Part D "Patch S" sections (extend tests/test_color_engine_config.py; new tests/test_led_color_engine_m2_patch_s.py). Then update the docs in the led_govee + config_schema contracts' docs_update lists and the status matrices to say: random_with_mono_chance is SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. Run tools/check_docs_metadata.py, check_agent_contracts.py, check_docs_drift.py.

Do NOT claim hardware-validated or live-ready. Commit once at the end with all tests green; report the diff summary, the byte-identical-at-chance-0 proof, and any anchors that had drifted.
```

### Codex Prompt 2 — implement Patch F bank cleanup ONLY (assumes Prompt 1 landed)

```
GATED — do NOT run until BOTH are true: (1) the operator confirms a hardware dry-run validated C–E on a real rig, AND (2) Patch S (random_with_mono_chance) has landed. If either is unconfirmed, STOP and ask.

Implement Patch F from docs/plans/active/led_color_engine_solid_color_and_patch_f_spec.md (Part B "Patch F tasks", F-1..F-4). Config-only — NO code changes.

Rules:
- Edit config/led_look_director.example.json (tracked, CI-tested) only. Do NOT edit the live config/led_look_director.json unless the operator explicitly tells you to (it is operator-owned and live-ready); instead record the §F-5 live-mirror checklist for the operator.
- Move (never delete) the legacy color-suffix looks from banks.default into a new banks.legacy_color_suffix bank exactly as in F-1/F-2. Delete no look definition, no _EFFECTS/SLOT_EFFECTS entry, no exempt_looks entry, no legacy drop_pairs entry.
- legacy_color_suffix must include all 8 role keys; utility must be []. Keep the three *_freestyle_nebula looks in default (operator must confirm this visual call — flag it).
- Add drop_pairs["rt_drop_chase"] -> rt_post_drop_chase (8.0 beats); leave existing pairs.
- Do not make solid unreachable: rt_groove_chase and the other generic slot looks stay in default (F-4 guardrail).
- safe_default/blackout/safety/targets untouched. Every default-bank look must resolve and every default scene_ref must be in _EFFECTS or SLOT_EFFECTS.

After editing, run python3 -m unittest discover tests and load config/led_look_director.example.json through load_led_look_director_config (zero errors). Add tests/test_led_color_engine_m2_patch_f.py exactly as in Part D "Patch F". Update the led_govee + config_schema docs/status matrices to say Patch F is SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED, and run the four tools/check_docs_*.py checks.

Do NOT claim hardware-validated / live-ready / show-ready. Commit once at the end with all tests green; report the before/after default-bank role lists and the live-mirror checklist.
```

---

## When you finish (each patch)

- Commit message: `Implement M2.5 Patch S: random_with_mono_chance solid-color slot fill` / `Implement M2.5 Patch F: legacy color-suffix bank cleanup`.
- Report back: the exact diff summary, test counts (before/after), the byte-identical-at-chance-0 proof (Patch S), the before/after default-bank role lists (Patch F), any drifted anchors, and the explicit reminder that this is `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED`.
