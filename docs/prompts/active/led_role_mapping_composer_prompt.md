# Codex Implementation Prompt — LED Role Mapping v2

## Context

Repo: `/Users/bbui/rb_ss_bridge_v2/`
Real-time Rekordbox → SoundSwitch → Govee/laser show bridge. Runs live at EDM shows; wrong role
behavior is visible to an audience. Implement exactly what the spec says. Do not add features, do not
refactor beyond the spec.

## Spec

Read and implement the full spec at:
```
/Users/bbui/rb_ss_bridge_v2/docs/plans/active/led_role_mapping_v2_spec.md
```
Part A is context. Part B (Tasks 1–4) is what you implement. Part C is the tests. Part D is the
acceptance bar. **Part E is operator curation — NOT yours; do not touch the config.**

## What it does (summary)

The LED role selector (`state_manager.py:_led_role_from_smart_phrasing`) currently dumps every
playing phrase that isn't a special moment into `ambient` (a static, idle-style bank), so verses /
long ups / full tracks look dead. And a chorus flashes `drop` for one beat, then deflates. This spec:
1. Playing catch-all `ambient` → `groove` (beat-driven baseline). The stopped path keeps ambient.
2. During a chorus: **hold + cycle** the drop for `LED_DROP_HOLD_BEATS`, then **sustain `post_drop`**
   for the rest of the chorus when `post_drop` is mapped.
   If `post_drop` is empty, dispatch falls back to `drop` and continues cycling the drop bank every
   `LED_DROP_CYCLE_BEATS` counts.
3. Cycling is achieved by bucketing the `drop` role_key by beats-into-the-chorus (the director already
   advances a bank cursor each time the role_key changes).
4. `low` phrases map to the calm `breakdown` bank.

It needs a new `beats_into_phrase` value, derived in `smart_phrasing.py` from the current phrase's
`start_beat` and exposed on `SmartPhrasingState`.

## Absolute Rules

1. **Follow the spec exactly** — use the shown current→replacement code blocks verbatim.
2. **Do NOT edit `config/led_look_director.json`** (Part E is the operator's job). All code must keep
   loading the existing config unchanged.
3. **Do NOT change** `smart_post_drop_active` / `active_drop_beat` computation, or any laser /
   smart_rearm code. This spec only changes how the LED **role** is chosen and keyed.
4. **Do NOT add a `lift` bank/role** — it's explicitly deferred (it would force config edits to every
   bank). Ups outside a buildup window fall to `groove`; that's intended.
5. Files in scope: `state_manager.py`, `smart_phrasing.py`, and the test files in Part C
   (`tests/test_smart_phrasing.py`, `tests/test_led_state_manager.py`, golden-trace fixtures).
6. Run the golden-trace tests. Regenerate/update recorded fixtures only if a failure proves they are
   affected, and read the diff to confirm it contains only the intended role changes.
7. Work on a branch. Commit after each task only if commits are explicitly authorized and the
   worktree can be staged narrowly without unrelated hunks. Do not deploy or restart the bridge.

## Task order

1. Task 1 — module constants `LED_DROP_HOLD_BEATS`, `LED_DROP_CYCLE_BEATS` (`state_manager.py`).
2. Task 2 — `beats_into_phrase` field + computation (`smart_phrasing.py`).
3. Task 3 — new `_led_role_from_smart_phrasing` (`state_manager.py`).
4. Task 4 — drop-cycling role_key in `_led_automation_role_key` (`state_manager.py`).
5. Empty `post_drop` fallback — dispatch `drop` when `post_drop` has no mapped preview but `drop`
   does.
6. Part C — tests (new + updated role assertions; run golden traces and update fixtures only if
   failures prove they are affected).
7. Part D — verify acceptance.

## When you finish

Output, as the final section, a single fenced code block titled `PASTE BACK TO CLAUDE` containing a
concise review-request for Claude with:
(a) files changed, one-line rationale each;
(b) any deviation from the spec and why;
(c) which existing tests / golden fixtures changed and a one-line confirmation the diffs are only the
intended role changes;
(d) the exact test command run and pass/fail summary;
(e) an explicit request for Claude to review: chorus drop-hold→post_drop timing,
empty-post_drop fallback to 16-count drop cycling,
`ambient`→`groove` only on the playing path (stopped path still ambient), `post_drop` reachable only
inside a chorus after the hold, role_key cycling correctness, and that no laser/rearm behavior changed.
