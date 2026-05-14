## Codex Prompt — Reformat Laser Pad UI to Match Approved Mockups

You are working in the repo `rb_ss_bridge_v2` on branch `Laser-Pad-UX`. The Laser Pad is a browser-based MIDI mapping editor that renders a Vue/Alpine SPA from `tools/laser_pad_assets/`. Your task is to **restyle and reorganize the existing Laser Pad UI** to match the mockups below, **without removing functionality** and **without breaking any existing test in `tests/test_laser_pad_web.py`**.

### Files in scope
- `tools/laser_pad_assets/index.html` — primary template (Alpine.js).
- `tools/laser_pad_assets/pad.js` — application data + methods.
- `tools/laser_pad_assets/pad.css` — styles.
- (Bump cache-busting from `?v=ux-3` to `?v=ux-4` on the `<script>` and `<link>` tags.)

### Files to leave alone
- `tools/laser_pad_web.py` (HTTP backend — APIs already exist for everything you need).
- `tools/laser_config_ops.py` (pure data ops).
- All tests under `tests/`.

### Existing routes available (do not invent new ones)
`GET /api/config`, `POST /api/draft`, `POST /api/commit`, `POST /api/discard`, `POST /api/test_note`, `POST /api/validate`, `POST /api/verify`, `GET /api/midi_ports`, `GET /api/history*`, `POST /api/role_cooldown`, `POST /api/banks/reset`, `POST /api/personality/{create,rename,duplicate,delete}`.

### Target layout (must match)

**Header strip (single compact row, then a quick-test row):**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ▓▓ LASER PAD ▓▓                                                        │
│  Output: [IAC Driver Bus 1 ▾]  Personality: [house ▾ + ✎ ⓘ]             │
│  [☐ enabled]  [☑ dry_run]  BPM (test): [128]  [💾 Commit]  [✓] [▶] ⚙   │
│  Quick test: Ch [1] Note [__] Vel [127] Beats [4] [Fire]                │
├─────────────────────────────────────────────────────────────────────────┤
│ ⚠ duplicate (ch1,37) across 2 scenes · 1 high_impact w/o allow flag     │
├─────────────────────────────────────────────────────────────────────────┤
│ [Groove Ch1][Buildup Ch1][Drop Ch1][Breakdown Ch1][Drop Impacts Ch2] +  │
└─────────────────────────────────────────────────────────────────────────┘
```

Header rules:
- Title `▓▓ LASER PAD ▓▓` is a small monospace title chip top-left.
- **Output** is a MIDI-port dropdown (move out of Settings into the header). Keep Settings copy as a fallback.
- **Personality** dropdown sits next to a tiny `+` (new), `✎` (rename), and `ⓘ` (open Settings → Personalities) trio of icon buttons.
- `☐ enabled` and `☑ dry_run` are inline checkboxes.
- `BPM (test)` is a small numeric input that writes to `_pad_meta.ui.bpm_for_test_fire` via `/api/draft`.
- Action buttons: `💾 Commit`, `✓ Validate`, `▶ Verify`, `⚙ Settings`. Keep Discard accessible from the Settings cog menu (move it out of the header).
- Quick test row is a single line (`Ch / Note / Vel / Beats / Fire`). Vel and Beats persist in `_pad_meta.ui.last_test_*` so they survive reload.
- **Banner row** appears immediately under the header when there are duplicates, errors, or warnings. Use existing data sources (`hardDuplicates`, `liveErrors`, `liveWarnings`). Show only the most severe single line; clicking it opens the Diagnostics panel.

**Bank tab row:**

```
[ Groove · Ch1 ][ Buildup · Ch1 ][ Drop · Ch1 ][ Breakdown · Ch1 ][ Drop Impacts · Ch2 ] [ + ]
```

- Render bank name + `· Ch{n}` pill in a single tab.
- A `+` button at the end opens an "Add bank" dialog (name + channel) and POSTs a `_pad_meta.banks` patch via `/api/draft`.
- Long-press / right-click a tab opens an inline edit popover for name + channel (already partially supported in Settings → Banks; keep that as the canonical edit surface and just expose rename/move-channel inline too).

**Note grid cell (single tile):**

```
┌─────────────────┐
│  big-room       │  ← label (largest, 18 px) — falls back to note name if empty
│  pulse          │
│                 │
│  37             │  ← note number (14 px, top-right corner)
│  ⭐ groove      │  ← role chip (12 px) + primary star
│  •              │  ← safety dot (color-coded, 10 px corner)
└─────────────────┘
```

Tile rules:
- The **primary content is the user-defined label**. If empty, show the role + note (e.g., `groove 37`).
- Note number is **top-right corner**, small, monospace.
- Role chip + primary `⭐` is a **bottom-left** chip; show `⭐` only when the scene equals the role's `*_scene`.
- Safety dot is **bottom-right**, 10px, color from `safety_class` (already mapped via `safetyDotClass`).
- Unmapped tiles render with a dotted border and only show the note number centered.
- Mapped tiles use the existing `role-*` background color but de-saturated; the firing flash (`.firing`) overlays a bright yellow pulse — keep current `flashNoteElement` behavior.
- Drag/drop cursor + overwrite modal stay as-is.
- Tooltip on hover should show: `scene_name · ch{n} · note{n} · {behavior} {duration}` for fast inspection.

**Drawer (right-click / long-press) layout:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Note 37 · C#2                                              [×] close   │
├─────────────────────────────────────────────────────────────────────────┤
│  Label:       [ big-room pulse                                      ]   │
│  Bank:        ( Groove ▾ )       Move to bank: …                        │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─ PRIMARY MAPPING ───────────────────────────────────────────────┐    │
│  │  Personality: [ house ▾ ]   Role: [ groove ▾ ]                  │    │
│  │  Scene name:  [ house_groove_1                              ]   │    │
│  │  Message:     ◉ Note   ○ CC                                     │    │
│  │  Behavior:    [ Tap ▾ / Hold ▾ ]    Duration ms: [ 80 ]         │    │
│  │  Channel: [1]  Velocity: [127]                                  │    │
│  │  Cooldown beats: [ 16 ]   ☑ immediate                           │    │
│  │  Safety class:   [ movement_low ▾ ]                             │    │
│  │  Fallback scene: [ safe_static ▾ ]                              │    │
│  │  [ Fire test ]  [ Set as primary ]  [ Remove mapping ]          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─ BANK ROTATION POOL (3 scenes) ─────────────────────────────────┐    │
│  │  • house_groove_1  note 37  pulse 80ms       ⭐ primary         │    │
│  │  • house_groove_2  note 39  pulse 80ms       [make primary] [×] │    │
│  │  • house_groove_3  note 41  pulse 80ms       [make primary] [×] │    │
│  │  [ + add another scene to this bank ]                           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ▸ Advanced (CC fields, hold_ms/hold_beats, raw JSON view)              │
└─────────────────────────────────────────────────────────────────────────┘
```

Drawer rules:
- Behavior must remain a **two-tier dropdown**: `Tap` (= `pulse`) or `Hold` (= `hold_beats`/`hold_ms` chosen via the Advanced disclosure). The current Tap/Hold UI is correct — keep it but lay it out as in the mockup.
- "Move to bank" rewrites the note's owning bank in `_pad_meta.banks` (note-set mutation) — confirm-on-channel-change if the new bank's channel differs.
- The **Bank Rotation Pool** section reads from the active personality's `*_bank` array for the selected role. For each entry list scene name, mapped note (from `scenes[scene].midi.note`), and current behavior. Buttons: `make primary` (PATCH primary scene), `×` (remove from bank). `+ add another scene to this bank` opens a quick "pick an unmapped note → assign" picker.
- **Advanced disclosure** at the bottom collapses by default and contains: CC fields (number, value), `hold_ms` numeric, `hold_beats` numeric, raw JSON view (read-only).
- For **system mappings** (`manual_commands.blackout_on/off`) keep the read-only banner currently shown and do not render the bank pool — instead show a "Managed via Settings → Blackout" CTA that opens the Settings tab.

### Non-negotiable invariants
1. **Do not touch backend Python or test files** unless adding *new* tests under `tests/test_laser_pad_web.py` or `tests/`.
2. **Do not regress any existing operator action.** All current pad capabilities (commit/discard, validate/verify, history drawer, drag/drop reassign, overwrite confirm, personality CRUD, blackout settings, dry-run firing, mapped-channel firing, firing flash) must still work after the refactor.
3. **All Alpine state mutations** must continue to flow through `/api/draft` for config edits — never write to disk directly.
4. **No new external dependencies** (no Vue, no React, no Tailwind). Stay on Alpine 3.x + plain CSS.
5. Preserve `pad.js`'s existing function names where possible (`sendTest`, `flashNoteElement`, `apply_mapping_payload`, etc.) so future diffs stay readable. Refactor by extraction, not by rewriting from scratch.
6. Bump `?v=ux-3` → `?v=ux-4` in `index.html`.
7. Run `python3 -m pytest tests/test_laser_pad_web.py tests/test_laser_config_ops.py tests/test_laser_map_wizard.py -q` and `node --check tools/laser_pad_assets/pad.js`. All must pass.

### Suggested implementation order
1. **Header refactor** (`index.html` + supporting `pad.js` getters/setters): collapse the multi-card header into a single banner strip. Add inline Personality `+/✎/ⓘ` icon trio that opens the same modals already wired in Settings → Personalities.
2. **Banner row**: extract a small `headerBanner()` Alpine getter that returns the most severe single line from duplicates/errors/warnings; click → open Diagnostics panel.
3. **Bank tab row**: replace existing `.bank-tabs` with the wider tab style (name + `·` + `Chn` pill). Add `+` button bound to a new `addBankPrompt()` method that mutates `_pad_meta.banks` via `/api/draft`.
4. **Note grid tile redesign** in `pad.css`: re-layout to label-dominant, top-right note number, bottom-left role chip, bottom-right safety dot. Ensure `.firing` still produces the visible flash.
5. **Drawer redesign**: split into Header / Primary Mapping card / Bank Rotation Pool card / Advanced disclosure, matching the mockup exactly.
6. **Bank Rotation Pool**: render from `personalities[active][role + '_bank']`; wire `make primary` to existing `apply_mapping` call with `replace_primary: true`; wire `×` to a new `removeFromBank(scene)` helper that patches the bank list and the `*_scene` primary if necessary.
7. Cache-bust + manual smoke test.

### Acceptance / verification checklist
- [ ] Backend tests still pass (`pytest tests/ -q`).
- [ ] `node --check tools/laser_pad_assets/pad.js` returns 0.
- [ ] Hard-refresh of `http://127.0.0.1:8765` shows the new header strip with title chip, output dropdown, personality+icons trio, enabled/dry_run inline, BPM input, and Quick Test row.
- [ ] Banner row appears only when duplicates/errors/warnings exist; clicking opens Diagnostics.
- [ ] Bank tabs render `Name · Chn`; `+` opens "Add bank" dialog; new bank persists via `_pad_meta.banks`.
- [ ] Note tiles show label-dominant content, note in top-right corner, role+star chip bottom-left, safety dot bottom-right.
- [ ] Tap fires on the mapped channel; `.firing` flash still visible for ≥600 ms.
- [ ] Right-click / long-press opens the new drawer with Header / Primary Mapping / Bank Rotation Pool / Advanced sections.
- [ ] Bank Rotation Pool lists every scene in the role bank with `make primary` and `×`, and `+ add another scene to this bank` opens the picker.
- [ ] Advanced disclosure exposes CC, hold_ms, hold_beats, and raw JSON view (read-only) and is collapsed by default.
- [ ] System mappings (`manual_commands.blackout_on/off`) still appear as system tiles and the drawer shows the "Managed via Settings → Blackout" CTA.
- [ ] No existing operator action regresses (commit, discard, validate, verify, history, drag/drop, overwrite, personality CRUD, blackout settings, hot reload).

### Output expected
- Edits to `index.html`, `pad.js`, `pad.css` only (plus the `?v=ux-4` bump).
- A short `git diff --stat` summary in your final response.
- The exact verification commands you ran and their results.

If you encounter ambiguity in the mockup, **prefer the layout shown over the existing UI**, and add a one-line note in your final response so the maintainer can review.
