# Implementation Spec: Configurable Scripted-Mode LED Role Policy

**For: Codex.** Source-of-truth order per AGENTS.md §1 (code wins). Status language per §10.

---

## Part A — Context & Goal

When a SoundSwitch **scripted** track is the active/master deck and is playing, LED automation currently freezes: after the `scripted_mode` enable check, the dispatcher gates on `lighting_mode != "autoloop"` and returns (`state_manager.py:1636–1642`). 

**Goal:** When (and only when) the operator enables scripted-mode LED automation, let dispatch proceed during `lighting_mode == "scripted"`, and remap the smart-phrasing role through a **JSON-configurable, conservative-by-default** policy so scripted tracks emit only restrained looks unless the operator opts in.

**Two-part control surface (unchanged split):**
- `safety.scripted_mode_automation` (bool, exists: `led_models.py:170`, validated `led_config.py:765–767`) = **master enable switch**.
- new top-level `scripted_mode` block = **role-remap policy**.

---

## Part B — Grounded Current-State Facts (verified at HEAD)

- **LEDConfig structure:** `LEDConfig` (`led_models.py:173–189`) carries structured sub-objects (`safety`, `rate_limits`, `automation`, `color_engine`, `drop_pairs`). A new `scripted_mode` field fits this pattern.

- **Role vocabulary:** `_BANK_ROLES` (`led_config.py:64–73`) = `(ambient, groove, buildup, pre_drop, drop, post_drop, breakdown, utility)` — the single role vocabulary; reuse it.

- **Config build:** `_build_config` (`led_config.py:1283–1358`) builds `LEDSafety(...)` etc.; add the policy build here.

- **LEDLookDirector storage:** Director stores `self._config` (`led_look_director.py:44`); `status()` (`:160–185`) is the existing channel StateManager reads.

- **StateManager latches:** StateManager caches `status()` into latches in `__init__` (`state_manager.py:390–422`); **StateManager does NOT store an `LEDConfig` object**. All config comes via the latches.

- **Latch refresh:** Only `_led_enabled_latch` is refreshed at runtime (`:1285`, `LED_SET_ENABLED`). `_led_scripted_mode_automation_latch` is written only at init (`:350/398/421`). A policy latch can be init-only without behaving differently from the existing master switch.

- **Dispatch path:** Single caller to `_dispatch_led_automation` at `:3422`. The path (`:3420–3427`) is mode-agnostic for any playing deck, so scripted decks currently hit the `not_autoloop` gate (`:1640`).

- **Remap seam:** `_led_effective_role_for_dispatch` (`:2131–2132`, body `return role`), single call site `:1671`. Takes a raw role and must return a remapped role.

- **Roles at the seam:** `_led_role_from_smart_phrasing` (`:2143–2180`) returns only `{drop, post_drop, breakdown, pre_drop, buildup, groove}`. **`ambient` and `utility` never appear here.** (Ambient comes from the separate idle path `_dispatch_led_idle_ambient` at `:3429`.)

- **Scripted entry reset:** `_apply_lighting` scripted branch (`:3071–3077`). Existing 4-line LED reset pattern appears at `:2507–2510`, `:3931–3934`, `:3962–3965`.

- **Test seams:**
  - `tests/test_led_config.py`: `_live_ready_base_config()` (`:27`), `_example_config()` (`:23`), `test_example_file_loads` (`:132`).
  - `tests/test_led_state_manager.py`: `_AutomationLEDLookDirector` (`:167`), `status()` (`:190–203`), `_make_sm` (`:290`), scripted test (`:1534`).

- **Contracts:** 
  - `led_govee` owns: `led_config.py`, `led_models.py`, `led_look_director.py`, `config/led_look_director.example.json`.
  - `core_bridge` owns: `state_manager.py`.
  - Both `docs_update` lists apply (AGENTS.md §7).

- **Backward-compat semantic flip:** With the master switch on, scripted decks are today still blocked by `not_autoloop` (`:1636–1642`). This change makes that switch newly active during `lighting_mode == "scripted"`. The master default is `false` (`led_models.py:170`), so out-of-box behavior remains unchanged.

---

## Part C — Exact Edits

### C1. `led_models.py` — Add model

**After `LEDSafety` (`:170`), add:**

```python
@dataclass(frozen=True)
class LEDScriptedModePolicy:
    """Scripted-track LED role remap policy (deck/mode policy, not safety limits)."""
    default_role: str = "breakdown"
    role_map: Mapping[str, str] = field(default_factory=dict, compare=False)
```

**In the `LEDConfig` dataclass (after `color_engine: Optional[ColorEngineConfig] = None`, `:189`), add:**

```python
    scripted_mode: LEDScriptedModePolicy = field(default_factory=LEDScriptedModePolicy)
```

---

### C2. `led_config.py` — Constants, validation, build

#### Import the new model

**In the imports block (`:20–34`), add `LEDScriptedModePolicy` to the from-block:**

```python
from .led_models import (
    ColorEngineConfig,
    LEDAutomation,
    LEDBank,
    LEDConfig,
    LEDConfigResult,
    LEDDropPair,
    LEDLook,
    LEDRateLimits,
    LEDRealtimeConfig,
    LEDSafety,
    LEDScriptedModePolicy,  # ADD THIS
    LEDTarget,
    Palette,
    _DEFAULT_SCALE_STOPS,
)
```

#### Add constants

**After `_BANK_ROLES` (`:73`), add. DO NOT reuse the name `_AUTOMATION_ROLES`** (it is taken in `led_look_director.py:31`):

```python
# Scripted remap source/destination roles = all bank roles except 'utility'
# (utility is a cloud_diy-only safety bank, never a scripted look bucket).
_SCRIPTED_REMAP_ROLES = tuple(role for role in _BANK_ROLES if role != "utility")
_SCRIPTED_MODE_DEFAULT_ROLE = "breakdown"
_SCRIPTED_MODE_DEFAULT_ROLE_MAP = MappingProxyType({
    "ambient": "breakdown",
    "groove": "breakdown",
    "buildup": "buildup",
    "pre_drop": "buildup",
    "drop": "breakdown",
    "post_drop": "breakdown",
    "breakdown": "breakdown",
})
```

#### Add validator

**After the `_validate_safety` call in `_validate` (after `:262`), add:**

```python
    _validate_scripted_mode(data.get("scripted_mode"), errors)
```

**Add the validator function (anywhere after `_validate_safety`, before `_build_config`):**

```python
def _validate_scripted_mode(raw: Any, errors: list[str]) -> None:
    """Validate the optional scripted_mode block."""
    if raw is None:
        return  # optional; defaults applied in _build_config
    if not isinstance(raw, dict):
        errors.append("'scripted_mode' must be an object")
        return
    default_role = raw.get("default_role", _SCRIPTED_MODE_DEFAULT_ROLE)
    if not isinstance(default_role, str) or default_role not in _SCRIPTED_REMAP_ROLES:
        errors.append(
            f"'scripted_mode.default_role' must be one of {list(_SCRIPTED_REMAP_ROLES)}"
        )
    role_map = raw.get("role_map", {})
    if not isinstance(role_map, dict):
        errors.append("'scripted_mode.role_map' must be an object")
        return
    for src, dst in role_map.items():
        if not isinstance(src, str) or src not in _SCRIPTED_REMAP_ROLES:
            errors.append(
                f"'scripted_mode.role_map' has invalid source role '{src}'"
            )
        if not isinstance(dst, str) or dst not in _SCRIPTED_REMAP_ROLES:
            errors.append(
                f"'scripted_mode.role_map.{src}' has invalid destination role '{dst}'"
            )
```

#### Build config in _build_config

**In the `return LEDConfig(...)` statement (`:1283–1358`), after the `color_engine=_parse_color_engine(data),` line (`:1357`), add:**

```python
        scripted_mode=_build_scripted_mode(data.get("scripted_mode")),
```

**Add the builder function (before `_build_config`):**

```python
def _build_scripted_mode(raw: Any) -> LEDScriptedModePolicy:
    """Build LEDScriptedModePolicy from raw JSON.
    
    When absent: conservative default (NOT identity). Scripted tracks only
    emit buildup/breakdown until the operator opts roles in via JSON.
    """
    if not isinstance(raw, dict):
        # Absent or non-dict → full conservative default map.
        return LEDScriptedModePolicy(
            default_role=_SCRIPTED_MODE_DEFAULT_ROLE,
            role_map=MappingProxyType(dict(_SCRIPTED_MODE_DEFAULT_ROLE_MAP)),
        )
    default_role = str(raw.get("default_role", _SCRIPTED_MODE_DEFAULT_ROLE))
    role_map_raw = raw.get("role_map", {})
    role_map = {str(k): str(v) for k, v in role_map_raw.items()} if isinstance(role_map_raw, dict) else {}
    return LEDScriptedModePolicy(
        default_role=default_role,
        role_map=MappingProxyType(role_map),
    )
```

> **Note:** When the block is **present** but `role_map` is omitted, `role_map` is empty and every reachable role falls back to `default_role` (`"breakdown"`). This is intentional and conservative. The full conservative map is only auto-applied when the whole block is absent.

---

### C3. `led_look_director.py` — Surface policy via `status()`

**In the `status()` method (`:160–185`), after line `:184` (before the final `return status`), add:**

```python
        status["scripted_mode"] = {
            "default_role": self._config.scripted_mode.default_role,
            "role_map": dict(self._config.scripted_mode.role_map),
        }
```

---

### C4. `state_manager.py` — Latch, gate, remap, reset

#### (a) Init defaults

**Next to `self._led_scripted_mode_automation_latch = False` (`:350`), add:**

```python
        self._led_scripted_default_role = "breakdown"
        self._led_scripted_role_map: dict[str, str] = {}
```

#### (b) Latch from status — init

**In the `try` block after `:400` (inside the director.status() read), after the line that reads `_led_scripted_mode_automation_latch`, add:**

```python
                sm_policy = status_payload.get("scripted_mode", {}) or {}
                self._led_scripted_default_role = str(sm_policy.get("default_role", "breakdown"))
                self._led_scripted_role_map = dict(sm_policy.get("role_map", {}))
```

**In the `except` fallback (after `:421`), add:**

```python
                self._led_scripted_default_role = "breakdown"
                self._led_scripted_role_map = {}
```

#### (c) Gate rewrite

**Replace `state_manager.py:1636–1642` exactly with:**

```python
        scripted_led_mode = bool(
            d.scripted_id
            and self._os.lighting_mode == "scripted"
            and self._led_scripted_mode_automation_latch
        )
        if d.scripted_id and not self._led_scripted_mode_automation_latch:
            self._gate_led_automation("scripted_mode", active_deck=active, rt_permitted=True)
            return
        if self._os.lighting_mode != "autoloop" and not scripted_led_mode:
            self._gate_led_automation("not_autoloop", active_deck=active)
            return
```

#### (d) Pass the flag to the seam

**At `:1671`, change from:**

```python
        role = self._led_effective_role_for_dispatch(role)
```

**to:**

```python
        role = self._led_effective_role_for_dispatch(role, scripted=scripted_led_mode)
```

#### (e) Helper rewrite

**Replace `_led_effective_role_for_dispatch` (`:2131–2132`) with:**

```python
    def _led_effective_role_for_dispatch(self, role: str, *, scripted: bool = False) -> str:
        if not scripted:
            return role
        return self._led_scripted_role_map.get(role, self._led_scripted_default_role)
```

#### (f) Scripted-entry reset

**In `_apply_lighting` (`:3063–3102`), inside the existing `if mode == "scripted":` branch (which starts at `:3071`), add the 4-line LED reset BEFORE the existing `self._clear_smart_rearm_state()` call:**

Current code around `:3071–3078`:

```python
        if mode == "scripted":
            self._clear_smart_rearm_state()
            self._os.autoloop_arm_after_master_change = False
            ...
```

**Change to:**

```python
        if mode == "scripted":
            self._led_last_auto_role_key = ""
            self._led_last_idle_role_key = ""
            self._led_smart_drop_blackout_key = ""
            self._clear_led_drop_lifecycle()
            self._clear_smart_rearm_state()
            self._os.autoloop_arm_after_master_change = False
            ...
```

(Do not duplicate `_clear_smart_rearm_state`; it already exists in the branch.)

---

### C5. `config/led_look_director.example.json`

**Insert a top-level block between `safety` (ends ~`:1174`) and `metadata` (at end):**

```json
  "scripted_mode": {
    "default_role": "breakdown",
    "role_map": {
      "ambient": "breakdown",
      "groove": "breakdown",
      "buildup": "buildup",
      "pre_drop": "buildup",
      "drop": "breakdown",
      "post_drop": "breakdown",
      "breakdown": "breakdown"
    }
  },
```

Leave `safety.scripted_mode_automation: false` unchanged.

---

## Part D — Tests

### D1. `tests/test_led_config.py` (reuse `_live_ready_base_config()`)

Add the following test cases:

1. **Absent block → conservative default.**
   - No `scripted_mode` key in config.
   - Assert: `result.available == True`; `result.config.scripted_mode.default_role == "breakdown"`; `result.config.scripted_mode.role_map["groove"] == "breakdown"`; `result.config.scripted_mode.role_map["buildup"] == "buildup"`.

2. **Non-object block fails.**
   - `"scripted_mode": 5` (or any non-dict).
   - Assert: error contains `"scripted_mode' must be an object"`.

3. **`default_role = "utility"` fails.**
   - `"scripted_mode": {"default_role": "utility"}`.
   - Assert: error contains `"invalid"` or `"must be one of"`.

4. **`role_map` not an object fails.**
   - `"scripted_mode": {"role_map": []}`.
   - Assert: error contains `"role_map' must be an object"`.

5. **Invalid source role fails.**
   - `"scripted_mode": {"role_map": {"chorus": "breakdown"}}`.
   - Assert: error contains `"invalid source role"`.

6. **Invalid destination role fails.**
   - `"scripted_mode": {"role_map": {"groove": "utility"}}`.
   - Assert: error contains `"invalid destination role"` or `"groove"`.

7. **`utility` rejected as source.**
   - `"scripted_mode": {"role_map": {"utility": "breakdown"}}`.
   - Assert: error contains `"invalid source role"` or `"utility"`.

8. **Partial map allowed; missing roles fall back.**
   - `"scripted_mode": {"role_map": {"groove": "groove"}}`.
   - Assert: `result.available == True`; `result.config.scripted_mode.role_map == {"groove": "groove"}`; `result.config.scripted_mode.default_role == "breakdown"`.

9. **`test_example_file_loads` still green.**
   - The existing test (`:132`) loads the example file, which now carries the `scripted_mode` block.
   - Assert: `result.available == True`.

---

### D2. `tests/test_led_state_manager.py`

#### Extend `_AutomationLEDLookDirector` (`:167–203`) to accept and surface policy:

**Modify `__init__` to accept:**

```python
    def __init__(
        self,
        *,
        enabled: bool = True,
        dry_run: bool = True,
        automation_enabled: bool = True,
        scripted_mode_automation: bool = False,
        scripted_default_role: str = "breakdown",
        scripted_role_map: dict[str, str] | None = None,
    ) -> None:
        self._enabled = enabled
        self._dry_run = dry_run
        self._automation_enabled = automation_enabled
        self._scripted_mode_automation = scripted_mode_automation
        self._scripted_default_role = scripted_default_role
        self._scripted_role_map = dict(scripted_role_map or {})
        self.preview_decision: LEDLookDecision | None = None
        self.preview_decisions: dict[str, LEDLookDecision] = {}
        self.role_decisions: dict[str, LEDLookDecision] = {}
        self.commit_calls: list[str] = []
        self._manual_override = ""
        self._emergency_blackout = False
        self.status_calls = 0
        self.tick_calls: list[LEDContext] = []
        self.mapped_roles = {"ambient", "groove", "buildup", "drop", "breakdown", "utility", "pre_drop", "post_drop"}
```

**Modify `status()` to include the policy:**

```python
    def status(self) -> dict:
        self.status_calls += 1
        return {
            "available": True,
            "enabled": self._enabled,
            "dry_run": self._dry_run,
            "automation_enabled": self._automation_enabled,
            "scripted_mode_automation": self._scripted_mode_automation,
            "scripted_mode": {
                "default_role": self._scripted_default_role,
                "role_map": dict(self._scripted_role_map),
            },
            "current_look": "",
            "last_reason": "",
            "last_source": "",
            "manual_override": self._manual_override,
            "emergency_blackout": self._emergency_blackout,
        }
```

#### Add new test cases:

1. **Conservative default preserved (extends existing `:1534`).**
   - Setup: `director = _AutomationLEDLookDirector(scripted_mode_automation=False)`.
   - Deck: `d.scripted_id = 1`, `d.playing = True`.
   - State: `lighting_mode = "scripted"`.
   - Call: `sm._dispatch_led_automation(active=1, d=d, sp_state=led_sp)`.
   - Assert: `sm.led_status_provider()["automation_gate_reason"] == "scripted_mode"`; no adapter trigger.

2. **Enabled bypasses `not_autoloop`.**
   - Setup: `director = _AutomationLEDLookDirector(scripted_mode_automation=True)`.
   - Deck: `d.scripted_id = 1`, `d.playing = True`.
   - State: `lighting_mode = "scripted"`.
   - Call: `sm._dispatch_led_automation(active=1, d=d, sp_state=led_sp)`.
   - Assert: Gate reason is **not** `"not_autoloop"`; director/adapter receive a decision.

3. **Default scripted mapping at the dispatch seam.**
   - For each role in `{buildup, pre_drop, drop, post_drop, groove}` (the roles reachable from `_led_role_from_smart_phrasing`):
     - Setup: `director = _AutomationLEDLookDirector(scripted_mode_automation=True)` (use default policy).
     - Drive `sp_state` so the raw role resolves to that value (e.g., `sp_state.transition_window_active = True` → `pre_drop`).
     - Set `lighting_mode = "scripted"`.
     - Call dispatch.
     - Assert expected remapped role: `buildup→buildup`, `pre_drop→buildup`, `drop→breakdown`, `post_drop→breakdown`, `groove→breakdown`.
   - **Do not test `ambient` here** (unreachable at this seam; test it in D2.7 instead).

4. **Override allows groove.**
   - Setup: `director = _AutomationLEDLookDirector(scripted_mode_automation=True, scripted_role_map={"groove": "groove"})`.
   - Drive `sp_state` so raw role = `groove`.
   - Set `lighting_mode = "scripted"`.
   - Assert: Director receives `LEDContext(role="groove")`.

5. **Override allows post_drop.**
   - Setup: `director = _AutomationLEDLookDirector(scripted_mode_automation=True, scripted_role_map={"post_drop": "post_drop"})`.
   - Drive `sp_state` so raw role = `post_drop`.
   - Assert: Director receives `LEDContext(role="post_drop")`.

6. **Remap does NOT apply outside scripted.**
   - Setup: `director = _AutomationLEDLookDirector(scripted_mode_automation=True, scripted_role_map={"groove": "breakdown"})`.
   - Deck: `d.scripted_id = 1`, `d.playing = True`.
   - State: `lighting_mode = "autoloop"` (NOT scripted).
   - Drive `sp_state` so raw role = `groove`.
   - Call dispatch.
   - Assert: Director receives `LEDContext(role="groove")` **unremapped**.

7. **Helper direct unit test.**
   - Call `sm._led_effective_role_for_dispatch("ambient", scripted=True)`.
   - Assert: returns `"breakdown"` (uses default).
   - Call `sm._led_effective_role_for_dispatch("buildup", scripted=True)`.
   - Assert: returns `"buildup"` (pass-through with default map).
   - Call `sm._led_effective_role_for_dispatch("groove", scripted=False)`.
   - Assert: returns `"groove"` (identity when not scripted).

8. **Downstream smoke test.**
   - Setup: Full StateManager with scripted automation enabled.
   - Deck: `d.scripted_id = 1`, `d.playing = True`.
   - State: `lighting_mode = "scripted"`.
   - Drive `sp_state` to a mix of states (transition window, post-drop, etc.).
   - Call dispatch multiple times.
   - Assert: **No exception** during `:1649–1695` (smart-drop, phrase, color-engine paths). (This bounds the unknowns about smart-phrasing aptness for scripted tracks.)

---

## Part E — Acceptance, Checks, Contracts, Non-Goals

### Acceptance Criteria

1. ✓ `python3 -m unittest discover tests` passes (existing + new).
2. ✓ With `scripted_mode_automation=false`, scripted playing decks stay LED-inert (gate `scripted_mode`).
3. ✓ With `scripted_mode_automation=true`, scripted decks dispatch during `lighting_mode=="scripted"`.
4. ✓ Default scripted policy emits only `buildup`/`breakdown` at the dispatch seam.
5. ✓ JSON edits enable `groove`/`post_drop` with no Python change.
6. ✓ Remap applies only when `scripted_led_mode` is true.
7. ✓ No Govee transport / color-engine / bank-schema / LEDLookDirector policy changes.
8. ✓ No forbidden status language (AGENTS.md §10); no hardware/live-readiness claims added.

### Mandatory Checks Before Commit (AGENTS.md §8)

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
```

All must **pass** before commit.

### Contracts & Docs (AGENTS.md §7 — This change crosses two contracts)

**Before editing code:**

1. Extend **both** contracts in `docs/agents/change_contracts.yml`:
   - Under `contracts.led_govee`: add `LEDScriptedModePolicy` to `key_symbols`; note the new config shape.
   - Under `contracts.core_bridge`: add state_manager gate/helper changes.

2. Update each contract's `docs_update` docs:
   - **`led_govey`** → update `docs/subsystems/led_govey.md` (new config block, conservative default), and feature/support/validation matrices, registry, playbook.
   - **`core_bridge`** → update `docs/subsystems/core_bridge.md`, `docs/architecture/current_architecture.md` (dispatch gate logic), `docs/architecture/runtime_invariants.md` (scripted mode path).

3. **Status language:** Mark the scripted-LED automation path as:
   - `implemented` (code written).
   - `software-tested` (D1–D2 tests pass).
   - `hardware-unvalidated` (no SoundSwitch scripted track hardware testing yet).

### Backward-Compatibility Note (must appear in PR description / docs)

**Semantic Flip:**
- Before: `safety.scripted_mode_automation = true` was a **no-op** for LED automation. Scripted decks were still blocked by the `not_autoloop` gate (line 1640).
- After: This switch becomes **active** during `lighting_mode == "scripted"`.
- Safety: Master default remains `false` (`led_models.py:170`), so out-of-box behavior is **unchanged**. Operators who have manually set the flag to `true` will see LED automation start during scripted tracks.

---

### Non-Goals (Explicit, Grounded)

- **No remap in backend-offset preview:** `_led_sp_state_for_next_backend` (`state_manager.py:3760–3813`) uses the raw role only to pick the cloud-vs-realtime *offset*, never changing the dispatched look. Remapping there is **out of scope**.
- **No change to idle-ambient path:** `_dispatch_led_idle_ambient` (`:3429`) is untouched. `ambient` is unreachable at the scripted dispatch seam and is kept valid in the config schema for forward-compatibility only.
- **No separate scripted banks, per-look allowlists, per-track policy, SoundSwitch cue parsing, drop-pair scripted overrides.**

---

## Part F — 9-Point Pre-Handoff Checklist

1. ✓ **Verified claims:** Every fact tied to code location (file:line).
2. ✓ **Knowns vs. unknowns separated:** Unknown boundary is musical aptness of smart-phrasing for scripted tracks, bounded by conservative default + smoke test D2.8.
3. ✓ **Pending state / mode transition guards:** Reset block (C4f) clears latches when entering `mode == "scripted"`.
4. ✓ **Third-party API completeness:** N/A (internal seam).
5. ✓ **Pure-function test seam:** `_led_effective_role_for_dispatch` is deterministic; testable in isolation (D2.7).
6. ✓ **Live-safety invariants preserved:** Master switch default is `false`; push loop untouched; no new blocking I/O.
7. ✓ **Adversarial self-review:** Name collision (C2), ambient unreachability (B), dual-contract (E), offset-preview boundary (E), semantic flip (E) all identified and addressed.
8. ✓ **No forbidden assumptions:** No "hardware-validated", "production-ready", "stable" claims in code/docs.
9. ✓ **Drift prevention:** Change contracts extended; docs updated before code; checks mandated.

---

## Summary

This change is **minimal, scoped, and bounded**:

| Component | Change |
|-----------|--------|
| **Models** | Add `LEDScriptedModePolicy`, add field to `LEDConfig`. |
| **Config** | Add constants, validator, builder; example JSON block. |
| **Director** | Surface policy via `status()` dict key. |
| **StateManager** | Latch policy at init; rewrite gate; pass flag to seam; rewrite helper; reset on entry. |
| **Tests** | 9 config cases; 8 state-manager cases. |

**No changes to:** Govee transport, color engine, banks, director policy, laser, autoloop, smart-phrasing, idle path.

**Backward-compat risk:** Low (master default off; semantic flip documented).

**Hardware readiness:** Unvalidated (marked `software-tested`).
