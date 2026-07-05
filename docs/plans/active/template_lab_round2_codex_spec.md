---
doc_status: current
truth_level: implementation-spec
last_verified_commit: 89736bb
last_verified_date: 2026-07-04
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED repo status unchanged
---

# Implementation Spec - Template Lab Round 2 (touch-first sliders + swatches + JSON demotion)

Parent: `docs/plans/active/template_lab_direction_2026_07_04.md` §3/§6. Depends on Round 1
(`template_lab_round1_codex_spec.md`) being landed — it reuses Round 1's auto-apply path and
endpoints. Round 1's **Absolute Rules and Part C invariants apply verbatim** (same file
allowlist, no bridge modules, no strobe rail, error handling propagates — no broad try/except).

## Part A - Context (verified at 89736bb)

- **[confirmed]** `LabRegistry.save()` (`tools/led_pad_lab.py:77-103`) copies the existing entry
  then `update()`s a **fixed key set** — unknown payload keys are dropped, so `param_specs`
  must be explicitly persisted and validated there.
- **[confirmed]** The params textarea is the single tuning surface (`lab.html:47`); Round 1 adds
  a debounced auto-apply on its `input` event. Round 2 must route slider input through the same
  apply path — programmatic `.value` writes do not fire `input`, so the debounced apply must be
  a named function both surfaces call.
- **[confirmed]** Slot colors are injected into play/switch specs server-side
  (`tools/led_pad_web.py:518-549,622`); `lab_play` returns the full spec, so the UI can read
  `res.spec.params.slot_colors`.
- Operator decisions (direction doc §6): iPad/phone are first-class — every new control ≥40px;
  raw JSON must never be the primary surface again.

## Part B - Tasks (in order)

### Task 1 - `tools/led_pad_lab.py`: persist + validate `param_specs`

In `LabRegistry.save()`, add to the `current.update({...})` dict:
`"param_specs": self._validate_param_specs(payload.get("param_specs", current.get("param_specs", {}))),`
and add:

```python
@staticmethod
def _validate_param_specs(value: Any) -> dict[str, dict[str, Any]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("param_specs must be a dict of param -> spec")
    out: dict[str, dict[str, Any]] = {}
    for key, spec in value.items():
        if not str(key) or not isinstance(spec, dict):
            raise ValueError(f"param_specs[{key!r}] must be a dict")
        kind = str(spec.get("kind", "slider"))
        if kind not in ("slider", "toggle"):
            raise ValueError(f"param_specs[{key!r}].kind must be slider or toggle")
        clean: dict[str, Any] = {"kind": kind, "label": str(spec.get("label", key))}
        if kind == "slider":
            if "min" not in spec or "max" not in spec:
                raise ValueError(f"param_specs[{key!r}] slider needs min and max")
            lo = float(spec["min"]); hi = float(spec["max"]); step = float(spec.get("step", 1))
            if not (hi > lo) or step <= 0:
                raise ValueError(f"param_specs[{key!r}] needs max > min and step > 0")
            clean.update({"min": lo, "max": hi, "step": step})
        out[str(key)] = clean
    return out
```

Every malformed shape raises `ValueError` (never `KeyError`) — Part D-2 asserts this.

### Task 2 - `tools/led_pad_web.py`: expose slot colors in preview

In `lab_preview`'s return dict add `"slot_colors": params.get("slot_colors") or []`.
(`lab_play`/`lab_switch` already return them inside `spec.params`.)

### Task 3 - `tools/led_pad_assets/lab.html`: controls above, JSON demoted

Replace the bare `Params JSON` label/textarea block with:

```html
<div id="paramControls" class="param-controls"></div>
<div id="slotSwatches" class="slot-swatches" aria-label="Test palette slot colors"></div>
<details class="advanced-panel">
  <summary>Advanced (raw JSON)</summary>
  <label>Params JSON <textarea id="paramsInput" class="mono" rows="8"></textarea></label>
</details>
```

`paramsInput` keeps its id — all Round 1 wiring (auto-apply, validation, save payload) keeps
working unchanged.

### Task 4 - `tools/led_pad_assets/lab.js` + `pad.css`: render controls, wire to auto-apply

1. Factor Round 1's debounced auto-apply body into a named `queueAutoApply()`; the textarea
   `oninput` calls it; sliders/toggles call it too.
2. Add `renderParamControls()` called from `renderDetail()`:
   - For each `[key, spec]` of `state.current.param_specs || {}`: slider → a row with
     `spec.label`, `<input type="range" min max step>` and a live numeric readout; toggle → a
     labeled checkbox. Current value comes from the parsed params JSON (fall back to `min` /
     `false` when unset).
   - On input: parse `$("paramsInput").value` (on parse failure, show the error banner and skip),
     set `params[key]` (`parseFloat` for sliders, boolean for toggles), write
     `JSON.stringify(params, null, 2)` back to the textarea, update the readout, call
     `queueAutoApply()`.
3. Add `renderSwatches(slotColors)`: six fixed-size color chips (≥40px) painted from
   `slot_colors`; slot 5 annotated "white". Call it with `res.spec.params.slot_colors` after
   play/switch, `res.slot_colors` after preview; clear it on draft switch. **Guard falsy/empty
   input by clearing the row and returning** — frame-kind drafts get `color_a`/`color_b`
   injected instead of `slot_colors` (`tools/led_pad_web.py:532-549` only writes `slot_colors`
   when `force_slot` or the scene is in `SLOT_EFFECTS`), so `undefined` here is normal, not an
   error.
4. `pad.css`: minimal rules — `.param-controls` rows and range inputs ≥40px touch height,
   `.slot-swatches` chip row, `.advanced-panel` matching existing panel styling. Follow the
   file's existing conventions; no redesign.

### Task 5 - `.claude/skills/template-lab/SKILL.md`: one addition

In §5's knob-mode bullet, append: "author `param_specs` for those params when you save the
draft — the UI turns them into sliders (`{key: {label, min, max, step}}`, `kind: "toggle"` for
booleans). 2-5 knobs, never the whole param dict."

### Task 6 - Docs (led_pad contract)

`docs/guides/led_pad.md`: extend the Template Lab section (param sliders, swatches, JSON now
under Advanced). Registry/doc-index entries only if Round 1's are missing. Status language §10.

## Part C - Invariants

Round 1 Part C verbatim, plus: `param_specs` is UI metadata only — it must never gate or filter
what `lab_play`/`lab_update` accept (lab params stay unvalidated by design; the allowlist
fail-safe is a production-promotion concern, not a lab concern).

## Part D - Tests (extend `tests/test_led_pad_lab.py`)

1. `param_specs` round-trip through `LabRegistry.save` (slider + toggle survive reload).
2. Validation rejects: non-dict, missing min/max on slider, `max <= min`, `step <= 0`, unknown
   kind — each raises `ValueError`.
3. Saving a payload **without** `param_specs` preserves the existing entry's specs (fixed-key-set
   regression guard).
4. `lab_preview` response contains `slot_colors` (list) for a slot-kind draft.

## Part E - Acceptance

- [ ] Tasks 1-6 done; suite + the three hard docs checks pass (CI is Python 3.11 — no 3.12+
      syntax).
- [ ] Manual smoke (dry-run server, temp config): a draft with `param_specs` shows sliders;
      dragging one updates the JSON textarea and (while playing) live-applies; JSON editing
      under Advanced still works; swatches appear after play and preview.
- [ ] Report: changed files, test results, plain-language operator summary.
