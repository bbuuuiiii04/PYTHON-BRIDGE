---
doc_status: current
truth_level: implementation-spec
last_verified_commit: 89736bb
last_verified_date: 2026-07-04
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED repo status unchanged
---

# Implementation Spec - Template Lab Round 3 (housekeeping: rejected filter + draft delete)

Parent: `docs/plans/active/template_lab_direction_2026_07_04.md` §3/§6. Depends on Rounds 1-2
landed. Round 1's **Absolute Rules and Part C invariants apply verbatim**. Variant grouping is
explicitly OUT (direction doc: decide after real use).

## Part A - Context (verified at 89736bb)

- **[confirmed]** No delete anywhere: `LabRegistry` (`tools/led_pad_lab.py:45-130`) has
  save/get/list/set_status only; `_POST_ROUTES` (`tools/led_pad_web.py:785-804`) has no
  `lab/delete`.
- **[confirmed]** The sidebar renders every entry regardless of status
  (`tools/led_pad_assets/lab.js:38-46`) — rejected drafts accumulate forever.
- **[confirmed]** `PadModal.confirm` exists and is already used by the lab page
  (`tools/led_pad_assets/pad-core.js:18`, `lab.js:96`).

## Part B - Tasks (in order)

### Task 1 - `tools/led_pad_lab.py`: `LabRegistry.delete`

```python
def delete(self, name: str) -> dict[str, Any]:
    data = self._load()
    entries = data["entries"]
    existing = next((item for item in entries if item.get("name") == name), None)
    if existing is None:
        raise ValueError(f"unknown lab draft: {name}")
    entries.remove(existing)
    self._save(data)
    return {"ok": True, "deleted": name}
```

Deletes the registry entry only — the function in `effects_lab.py` is the agent's cleanup, not
this endpoint's.

### Task 2 - `tools/led_pad_web.py`: `lab_delete` + route

```python
def lab_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if self._playing_name == LabRegistry.scene_ref(name):
        return {"ok": False, "error": "stop_playback_first"}
    return self._lab.delete(name)
```

Route: `"/api/lab/delete": service.lab_delete,` in `_POST_ROUTES`.

### Task 3 - `tools/led_pad_assets/pad-core.js`

`labDelete: (body) => request("/api/lab/delete", {method: "POST", body}),` next to the other
lab methods.

### Task 4 - `tools/led_pad_assets/lab.html` + `lab.js`: filter + delete button

1. Filter: add a toggle chip next to the "New" button in the drafts panel head —
   `<button id="rejectedToggle" type="button" class="ghost"></button>`. State
   `state.showRejected = false` (default). `renderList()` filters
   `state.entries.filter(e => state.showRejected || e.status !== "rejected")` and the chip label
   shows `Rejected (n)` with `n` = rejected count; clicking toggles and re-renders. If the
   current draft becomes hidden by the filter, keep it selected (detail panel unaffected) —
   only the list hides it.
2. Delete: add `<button id="deleteBtn" type="button" class="danger ghost">Delete</button>` at
   the END of the lab-actions row (after Reject; it must not sit next to ▶ Play). Handler:
   `PadModal.confirm("Delete draft <name>?", "Removes the drafts.json entry. Its function in
   effects_lab.py stays — clean that up separately.", "Delete", ...)` → `api.labDelete({name})`
   → on `ok: false` with `stop_playback_first`, show the error banner "Stop playback first.";
   on success clear `state.current`, `refresh()`. Include `deleteBtn` in `renderDetail()`'s
   disabled-ids list. Touch target ≥40px.

### Task 5 - Docs (led_pad contract)

`docs/guides/led_pad.md`: Template Lab section gains delete + rejected-filter lines.
`docs/status/active_work_registry.md` / spec-table row updates for Round 3 landing. §10 status
language.

## Part C - Invariants

Round 1 Part C verbatim, plus: delete never touches `effects_lab.py`, never stops or alters
playback (it refuses instead), and the filter is pure UI — `/api/lab/list` keeps returning
every entry so agents always see rejected drafts (the "don't re-pitch" record).

## Part D - Tests (extend `tests/test_led_pad_lab.py`)

1. `LabRegistry.delete`: entry gone after delete + reload; unknown name raises `ValueError`.
2. `lab_delete` while that draft is playing (fake playback playing, `_playing_name` set) →
   `{"ok": False, "error": "stop_playback_first"}` and the entry still exists.
3. `lab_delete` of a non-playing draft succeeds; `lab_list` no longer contains it.

## Part E - Acceptance

- [ ] Tasks 1-5 done; suite + the three hard docs checks pass (CI is Python 3.11).
- [ ] Manual smoke (dry-run server, temp config): rejected drafts hidden by default, chip shows
      count and toggles them; Delete confirms, refuses while playing, removes the entry.
- [ ] Report: changed files, test results, plain-language operator summary.
