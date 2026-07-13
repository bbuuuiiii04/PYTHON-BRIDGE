---
doc_status: current
truth_level: spec
last_verified_commit: f5d8aaf
last_verified_date: 2026-07-12
validation_scope: >
  Menubar-only change to make the "Rebuild USB Bridge…" item state-aware,
  mirroring the SoundSwitch export item (greyed/relabelled when idle, live
  "Rebuilding…" indicator mid-run). Software-tested via tests/test_bridge_menubar.py;
  the frozen/guest bundle hides the item entirely, so this affects the maintainer
  (source) run only. No runtime/bridge behavior changes.
work_status: spec — implementation authorized to Claude this task (operator exception 2026-07-12)
relates_to: usb_bridge_launcher_design.md, usb_launcher_runbook.md
---

# Codex/Claude Implementation Spec — Rebuild USB Bridge button: state-aware label + busy indicator

> **Who implements:** Claude, this task only (operator granted the exception on 2026-07-12).
> The menubar is otherwise Codex's lane. Scope is exactly the three items below and their tests/docs.

## Part A — Context & Root Cause (verified; read, do not implement)

**What Brandon wants.** The "Rebuild USB Bridge…" menu item should behave like the "SoundSwitch Export…" item:
show a live "Rebuilding…" state while it runs, and otherwise tell him whether the stick needs a rebuild —
`No USB Found` / `USB Bridge Rebuilt` (up to date, greyed) / `Rebuild USB Bridge…` (outdated, active).

**Why it doesn't today.**
- [confirmed] The item is registered at `scripts/bridge_menubar.py:1101` and its only enable gate is
  `"update_usb_item": not frozen` (`_menu_visibility`, line ~1112). It has **no** up-to-date detection, so it is
  always clickable on a source run — that is why Brandon can "rebuild again right after rebuilding."
- [confirmed] `updateUsbBridge_` (line 2134) checks for exactly one PIONEER USB **only after** the click
  (`pioneer_usb_mounts()`, line 703), then confirms and spawns `make_stick.sh` via `_spawn_watched`
  (line 2165) with `busy_item_attr="update_usb_item"`, `busy_title="Rebuilding USB Bridge…"`.
- [confirmed] The busy title today is set once by `_spawn_watched` (line 1601-1607: saves `saved_title`,
  disables the item, sets `busy_title`) and restored once by `finishWatchedChild_` (line 1702-1710:
  restores `saved_title`, re-enables). Nothing repaints the item between spawn and finish, so the single
  set/restore is enough **today**.

**The exporter is the template (mirror it).**
- [confirmed] Pure render functions: `export_button_text(in_progress, up_to_date)` (line 486) and
  `export_button_enabled(in_progress, up_to_date, frozen)` (line 494). These are the test seams.
- [confirmed] `_render_export_state()` (line 1320) runs on **every** status render and sets the item's
  title + enabled purely from `self._export_in_progress` and `self._export_up_to_date`. Because it checks
  `in_progress` first, the periodic repaint keeps showing "Exporting…" for the whole run — that is the
  pattern the rebuild item needs so a periodic repaint does not erase "Rebuilding…".
- [confirmed] `_maybe_detect_export_state()` (line 1360) runs detection **off the AppKit main thread**
  (daemon thread → `_run_detect` → `performSelectorOnMainThread_("finishDetect:")`), throttled by a cheap
  stat signature (`_source_stat_signature`) + a max-age, and **returns early when frozen or already in
  progress** (line 1361-1364). `detect_export_state()` (line 179) returns `"up_to_date"` only with positive
  proof (content fingerprint of the source), else `"changes"`.
- [confirmed] State fields are initialised in `__init__` around line 1129-1136 (`_export_in_progress`,
  `_export_up_to_date`, `_detect_in_progress`, `_detect_sig`, `_detect_at`, `_detect_generation`).

**Root-cause summary.** The rebuild item needs (1) a periodic, in-progress-aware render function like
`_render_export_state`, (2) an off-main-thread detector like `_maybe_detect_export_state`, and (3) a busy
flag reset on completion — because once (1) repaints every tick, the current one-shot set/restore of the
title is no longer sufficient (a repaint mid-build would erase "Rebuilding…").

**The measured cost that justifies the detection design.** Full SHA-256 of the analysis cache
(`~/Library/Application Support/RBSS Bridge/spectral_cache`, 3,641 files / 563 MB) is ~1.26 s; a stat-only
signature (path+size+mtime) over the same tree is ~9 ms. [confirmed by measurement 2026-07-12] The detector
therefore keys "did anything change" on a **stat signature**, never content-hashes 563 MB, and runs
off-thread anyway — the menu never blocks.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- **Out of scope — do not touch:** `packaging/make_stick.sh` (the live-critical transactional build; this
  feature is deliberately menubar-only), any bridge/runtime module, the 200 Hz loop, laser/LED/SoundSwitch
  code, the export item's behavior, `pioneer_usb_mounts` semantics.
- **Behavior that must not change:** the click flow of `updateUsbBridge_` (mount checks, confirm dialog,
  the actual `make_stick.sh` invocation), the export item, and the frozen/guest menu inventory
  (`update_usb_item` stays `not frozen`).
- **Error handling:** the detector must **fail toward "outdated"** — any unreadable source, missing stamp,
  missing/!= generation, or exception → `"outdated"` (never silently claim "up to date"). No broad
  try/except that swallows a real error into "up_to_date". Detection runs off the main thread; a detector
  exception resolves to `"outdated"`, mirroring `_run_detect`'s `except → "changes"`.

### Task 1 — `scripts/bridge_menubar.py`: pure helpers (module scope, near `export_button_text`, ~line 486)

Add three module-level pure functions (test seams — no I/O):

```python
def usb_button_text(in_progress: bool, state: str) -> str:
    if in_progress:
        return "Rebuilding USB Bridge…"
    if state == "no_usb":
        return "No USB Found"
    if state == "up_to_date":
        return "USB Bridge Rebuilt"
    return "Rebuild USB Bridge…"          # "outdated" or any unknown → actionable label


def usb_button_enabled(in_progress: bool, state: str, frozen: bool) -> bool:
    # Actionable only on a source run with a mounted, out-of-date stick.
    return (not in_progress) and (not frozen) and state == "outdated"


def classify_usb_state(
    mount_count: int,
    stick_generation: "str | None",
    stamp: "dict | None",
    current_fingerprint: "str | None",
) -> str:
    """Pure decision. Returns 'no_usb' | 'up_to_date' | 'outdated'. Fails toward 'outdated'."""
    if mount_count == 0:
        return "no_usb"
    if mount_count > 1:
        return "outdated"                 # ambiguous; the click handler guides "leave only one"
    if not stick_generation:
        return "outdated"                 # no complete bridge on the stick
    if not isinstance(stamp, dict) or stamp.get("generation") != stick_generation:
        return "outdated"                 # we did not build this stick (or cold start)
    if not current_fingerprint:
        return "outdated"                 # could not read the sources → cannot prove up to date
    return "up_to_date" if stamp.get("source_fingerprint") == current_fingerprint else "outdated"
```

### Task 2 — `scripts/bridge_menubar.py`: source stat-signature + stamp I/O (module scope)

Add near the other module helpers (reuse existing constants: `pioneer_usb_mounts`, and the App Support path
already used for `spectral_cache`; the four `config/*.json` names and `govee.env` mirror `make_stick.sh`'s
`HOME_PARITY_FILES`; the canonical bindings path is the same `CANONICAL_*` region the file already defines).

Define the input roots ONE place, as a module function, so drift from `make_stick.sh` is visible:

```python
# ponytail: stat-signature (path+size+mtime_ns), NOT a content hash. Re-analysis and Codex
# edits always rewrite mtimes, so this catches every real change in Brandon's workflow and
# fails toward "rebuild"; the only miss is an identical-content, identical-mtime rewrite, which
# does not happen naturally. Upgrade to a content hash only if that ever matters.
# ponytail: this list mirrors make_stick.sh's staged inputs by hand. If that script's inputs
# change, update this list (test_bridge_menubar pins the key entries so drift shows up).
def _usb_source_roots() -> list[Path]:
    repo = Path(__file__).resolve().parents[1]
    support = Path.home() / "Library" / "Application Support" / "RBSS Bridge"
    roots: list[Path] = []
    roots += sorted(repo.glob("*.py"))                       # flat bridge modules
    roots += [repo / "streamdeck", repo / "scripts"]         # bundled packages
    roots += [repo / "tools" / "lighting_sidecar_export.py"] # runs at build time
    roots += [repo / "pyproject.toml",
              repo / "packaging" / "rbss_launcher.spec",
              repo / "packaging" / "sign.sh",
              repo / "packaging" / "make_stick.sh"]
    roots += sorted((repo / "packaging").glob("*.lock"))
    roots += [repo / "config" / name for name in (
        "laser_director.json", "led_look_director.json",
        "soundswitch_pack_player.json", "laser_color_map.json")]
    roots.append(support / "govee.env")
    roots.append(support / "spectral_cache")                 # the 563 MB tree — stat only
    # the exported pack (pack_path from the live config) + the canonical Stream Deck
    # bindings — actually appended (adversarial fix A4: the earlier draft only said so).
    try:
        value = json.loads((repo / "config" / "soundswitch_pack_player.json")
                           .read_text(encoding="utf-8"))
        pack = value.get("pack_path", "") if isinstance(value, dict) else ""
        if pack:
            roots.append(Path(pack))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass  # config itself is already a root; its unreadability surfaces there
    roots.append(repo / "local" / "soundswitch" / ".rbss_canonical_pack.midi_bindings.json")
    return roots


def usb_source_signature(roots: "list[Path] | None" = None) -> str:
    """Cheap stat signature over every build input. Never reads file contents.
    Adversarial fix A1: stat() on a chmod-000 FILE succeeds (proven 2026-07-12), so
    there is no None-on-unreadable path; mirror _source_stat_signature instead —
    per-file lstat, skip on OSError. A vanished/changed file changes the signature,
    which already resolves toward "outdated"."""
    if roots is None:
        roots = _usb_source_roots()
    entries: list[tuple[str, int, int]] = []
    for root in roots:
        if root.is_dir():
            for dirpath, dirs, files in os.walk(root, followlinks=False):
                dirs.sort()
                for name in sorted(files):
                    p = Path(dirpath) / name
                    try:
                        st = p.lstat()
                    except OSError:
                        continue
                    entries.append((str(p), st.st_size, st.st_mtime_ns))
        else:
            try:
                st = root.lstat()
            except OSError:
                continue  # absent root contributes nothing; absence is stable
            entries.append((str(root), st.st_size, st.st_mtime_ns))
    digest = hashlib.sha256()
    for name, size, mtime in sorted(entries):
        digest.update(f"{name}\x00{size}\x00{mtime}\n".encode("utf-8"))
    return digest.hexdigest()
```

Stamp file at `~/Library/Application Support/RBSS Bridge/.usb_rebuild_state.json`, shape
`{"generation": <str>, "source_fingerprint": <str>}`. Add `_usb_stamp_path()`, `read_usb_stamp() -> dict|None`
(tolerate missing/corrupt → None), and `write_usb_stamp(generation, fingerprint)` (atomic temp+replace,
`OSError` swallowed only here — a stamp we could not write just means the next detection reads None → outdated,
which is safe).

Add `read_stick_generation(mount: Path) -> str|None`: read
`mount / "RBSS BRIDGE USB" / "lighting_sidecar" / ".rbss_build_manifest.json"`, return its `generation`
string, or None on any error. [confirmed the manifest carries `generation`; observed value on MINK
`39a2ffa5c770-20260712T225252Z`.]

### Task 3 — `scripts/bridge_menubar.py`: wire the item like the exporter

**3a. `__init__` (~line 1136), add fields:**
```python
self._usb_rebuild_in_progress = False
self._usb_state = "outdated"          # safe active default until the first detection resolves
self._usb_pending_fingerprint = None  # click-time fingerprint (fix A3)
self._usb_detect_in_progress = False
self._usb_detect_sig = None
self._usb_detect_at = 0.0
self._usb_detect_generation = 0
```

**3b. New `_render_usb_state(self)` (beside `_render_export_state`, ~line 1320):** the single owner of the
item's title + enabled, in-progress-aware so the periodic repaint keeps "Rebuilding…":
```python
def _render_usb_state(self):
    if getattr(self, "update_usb_item", None) is None:
        return
    frozen = bool(getattr(sys, "frozen", False))
    self.update_usb_item.setTitle_(usb_button_text(self._usb_rebuild_in_progress, self._usb_state))
    self.update_usb_item.setEnabled_(
        usb_button_enabled(self._usb_rebuild_in_progress, self._usb_state, frozen))
```
Call `self._render_usb_state()` and `self._maybe_detect_usb_state()` in the render tick, right next to the
existing `self._render_export_state()` / `self._maybe_detect_export_state()` calls (line 1308-1310).

**3c. `_maybe_detect_usb_state(self)` — mirror `_maybe_detect_export_state` (line 1360):**
```python
def _maybe_detect_usb_state(self):
    if getattr(sys, "frozen", False):
        return                         # item hidden on frozen/guest runs — nothing to detect
    if self._usb_rebuild_in_progress or self._usb_detect_in_progress:
        return
    # Adversarial fix A2: fold mount names into the throttle key, else plugging or
    # unplugging the stick would not repaint for up to DETECT_MAX_AGE_SECONDS (30 s).
    mounts = pioneer_usb_mounts()
    sig = (usb_source_signature(), tuple(p.name for p in mounts))
    fresh = (time.monotonic() - self._usb_detect_at) < DETECT_MAX_AGE_SECONDS
    if sig == self._usb_detect_sig and fresh:
        return
    self._usb_detect_in_progress = True
    self._usb_detect_generation += 1
    generation = self._usb_detect_generation
    threading.Thread(target=self._run_usb_detect, args=(generation, sig), daemon=True).start()
```
`_run_usb_detect(self, generation, sig)` computes, OFF the main thread:
`mounts = pioneer_usb_mounts()`; `gen = read_stick_generation(mounts[0])` iff exactly one mount;
`fp = usb_source_signature()`; `verdict = classify_usb_state(len(mounts), gen, read_usb_stamp(), fp)` —
all wrapped so any exception → `verdict = "outdated"`; then
`performSelectorOnMainThread_("finishUsbDetect:", {...})`.
`finishUsbDetect_` mirrors `finishDetect_` (line 1383): drop stale generations, set `self._usb_state`,
`self._usb_detect_sig`, `self._usb_detect_at`, clear `_usb_detect_in_progress`, call `self._render_usb_state()`.

**3d. `updateUsbBridge_` (line 2134): set the flag + capture the fingerprint, keep the existing spawn.**
After the confirm passes and immediately before `_spawn_watched`:
```python
self._usb_rebuild_in_progress = True
# Adversarial fix A3: capture the source fingerprint NOW, before the multi-minute
# build. Stamping a post-build fingerprint would fold in any edit made DURING the
# build, falsely marking a stick built from older sources as up to date.
self._usb_pending_fingerprint = usb_source_signature()
self._render_usb_state()
```
Keep the `_spawn_watched(..., busy_item_attr="update_usb_item", busy_title="Rebuilding USB Bridge…")` call
unchanged: the periodic `_render_usb_state()` is now the real owner of the label; `_spawn_watched` still
disables the item and marshals completion. (`_usb_pending_fingerprint` is initialised to `None` in 3a.)

**3e. `finishWatchedChild_` (line 1702): reset the flag + re-detect for this item only.** After the existing
`saved_title`/enable restore and BEFORE the early `return`s (adversarial fix A5 — read the code from the
payload, and place the branch where every completion path hits it):
```python
if attr == "update_usb_item":
    self._usb_rebuild_in_progress = False
    if payload.get("returncode", 0) == 0:
        self._record_usb_rebuild_stamp()     # read new stick generation + write the stamp
    self._usb_pending_fingerprint = None
    self._usb_detect_at = 0.0                # force a fresh detection next tick (stick changed)
    self._usb_detect_sig = None
    self._render_usb_state()
```
`_record_usb_rebuild_stamp(self)`: `mounts = pioneer_usb_mounts()`; if exactly one, its
`read_stick_generation` is non-None, and `self._usb_pending_fingerprint` is non-None, then
`write_usb_stamp(generation, self._usb_pending_fingerprint)` (the CLICK-TIME fingerprint — fix A3). Any
failure is swallowed here (→ next detection sees no matching stamp → "outdated", safe). This runs on the
main thread inside the completion selector; it is a handful of small stats + one small JSON write (the 9 ms
class), acceptable there.

## Part C — Invariants That MUST Still Hold (live safety)

- **No bridge/runtime impact.** This touches only the menubar UI process. The 200 Hz push loop, readers,
  SoundSwitch/laser/LED output, and `pioneer_usb_mounts` semantics are untouched (AGENTS.md §6).
- **No main-thread stall.** All source-signature + USB reads happen on a daemon thread
  (`_run_usb_detect`), exactly like `_run_detect`. The only main-thread work added is the render
  (title/enabled set) and the small stamp write on completion — no content hashing, no 563 MB read, no
  subprocess, ever on the main thread.
- **Menubar UI state is not process truth** (contract `forbidden_assumptions`): the label describes the
  *stick*, never whether the bridge or watcher is running. Keep the two concerns separate.
- **Frozen/guest bundle unchanged:** `update_usb_item` stays `not frozen`; detection early-returns when
  frozen; the item is hidden on guest runs as today.
- **Fail toward action, never toward false safety:** every uncertain path resolves to "outdated"
  (actionable), never "up_to_date".

## Part D — Tests (`tests/test_bridge_menubar.py`, extend)

Pure-function seams (no files, no AppKit):
1. `usb_button_text`: in_progress → "Rebuilding USB Bridge…" (wins over every state);
   no_usb/up_to_date/outdated/unknown → the four labels.
2. `usb_button_enabled`: True only for `(in_progress=False, state="outdated", frozen=False)`; False for
   in_progress, for up_to_date, for no_usb, and for frozen.
3. `classify_usb_state`: table — 0 mounts → no_usb; 2 mounts → outdated; None generation → outdated;
   stamp None → outdated; stamp.generation != stick → outdated; fingerprint None → outdated;
   matching generation + matching fingerprint → up_to_date; matching generation + differing fingerprint
   → outdated.
4. `usb_source_signature(roots=[...])` on a `tmp_path`: stable across calls when nothing changes; **changes**
   when a listed file's content changes (bump mtime explicitly via `os.utime` — same-second writes may not
   move mtime_ns enough on coarse filesystems); **changes** when a file is added or removed. Feed explicit
   `roots` so the test is hermetic. (No unreadable-file → None case: stat on a chmod-000 file succeeds —
   adversarial fix A1.)
5. Drift pin: assert `_usb_source_roots()` includes the spectral_cache dir, the four `config/*.json`, and
   `make_stick.sh` — so a silent divergence from the build's inputs fails a test.
6. Stamp round-trip: `write_usb_stamp` then `read_usb_stamp` (point `$HOME` at tmp) returns the dict;
   `read_usb_stamp` on missing/corrupt file → None.

Run: `python3 -m unittest tests.test_bridge_menubar` and `python3 tools/check_agent_contracts.py`.

## Part E — Acceptance (definition of done)

- [ ] Three items behave: **No USB Found** (unplug MINK → greyed), **USB Bridge Rebuilt** (right after a
      successful rebuild → greyed), **Rebuild USB Bridge…** (after any bridge-code/config/cache change →
      active). **Rebuilding USB Bridge…** shows for the whole build and survives the periodic repaint.
- [ ] Clicking still runs the exact same confirm + `make_stick.sh` flow; export item unchanged.
- [ ] New pure functions covered by tests; `python3 -m unittest tests.test_bridge_menubar` green.
- [ ] Contract `bridge_menubar` `docs_update` satisfied: note the state-aware item in
      `docs/subsystems/runtime_commands.md` and `docs/validation/software_test_inventory.md`; run
      `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_metadata.py`,
      `python3 tools/check_docs_drift.py`.
- [ ] `make_stick.sh` untouched; no runtime module touched.

## When You Finish — operator summary to write
- What changes on screen: the Rebuild item now greys out and renames itself the way the SoundSwitch export
  item does, and shows a live "Rebuilding…" while it works. Nothing about the bridge, the show, or the
  stick's contents changes.
- Watchpoints: right after a rebuild it should read "USB Bridge Rebuilt"; edit a live LED/laser config and
  it should flip back to "Rebuild USB Bridge…"; unplug MINK and it should read "No USB Found".
- Known ceiling: "up to date" is judged by file size+timestamp, not by re-hashing 563 MB every time; every
  real edit in normal use bumps a timestamp, and anything uncertain shows "Rebuild" (never a false
  "Rebuilt"). If the stick is ever rebuilt from the terminal instead of this button, it will read "Rebuild"
  until the next button rebuild — safe, just conservative.
- Rollback: menubar-only; restart the menubar to revert if needed. No bridge restart involved.

## Adversarial spec review — round 1 (2026-07-12, pre-implementation; all amended above)
- **A1 [CONFIRMED, empirically]** stat() on a chmod-000 file succeeds → the None-on-unreadable path and its
  test were wrong. Replaced with the exporter's lstat/skip pattern; signature is now always a hex string.
- **A2 [CONFIRMED]** `DETECT_MAX_AGE_SECONDS = 30.0` (line 69) → mount plug/unplug repainted only after 30 s.
  Mount names folded into the throttle key.
- **A3 [CONFIRMED]** post-build fingerprint could fold in mid-build edits → false "up to date". Fingerprint
  now captured at click time (`_usb_pending_fingerprint`).
- **A4 [CONFIRMED]** roots comment promised the pack + bindings without appending them. Now appended, plus
  `tools/lighting_sidecar_export.py` (build-time code that shapes stick output).
- **A5 [CONFIRMED]** `finishWatchedChild_` branch must read `payload.get("returncode", 0)` and sit before
  the early returns so every completion path resets the flag.

## Post-implementation review + adversarial review — round 2 (2026-07-12; code as landed)
- **R1 [CONFIRMED by measurement, FIXED].** The spec's throttle computed `usb_source_signature()` on the
  AppKit main thread every render tick. Measured cost over the REAL root set is ~44 ms (not the 9 ms
  cache-only figure), and the render timer fires every 1 s while the bridge is on — a 4% main-thread duty
  cycle. As landed, the main-thread throttle is mount-names + age only (sub-ms); the full signature runs
  ONLY on the detect daemon thread. Consequence: source edits repaint within DETECT_MAX_AGE_SECONDS (30 s)
  instead of the next tick; mount plug/unplug still repaints on the next tick.
- **AV1 [FIXED].** Stale "~9 ms" claim in the signature docstring corrected to the measured 44 ms.
- **AV12 [ACCEPTED CEILING, documented in code].** `pioneer_usb_mounts()` now runs on the main thread each
  tick; a hung network volume under /Volumes would stall its is_dir probe. Local-USB workflow today;
  the upgrade path (NSWorkspace volume-mount notifications) is named at the call site.
- **Post-build flicker [ACCEPTED].** After a successful rebuild there is a ≤1-tick window showing
  "Rebuild USB Bridge…" before the forced re-detect flips it to "USB Bridge Rebuilt" — transient, in the
  fail-toward-action direction, self-corrects in ~1 s.
- **End-to-end evidence (real MINK, real manifest, throwaway HOME for the stamp):** cold/no-stamp →
  outdated; button-stamp simulation → up_to_date; one-module mtime bump → outdated; exact restore →
  up_to_date; zero mounts → no_usb. 9 unit tests green; the module's only reds are the 4 instances of the
  PRE-EXISTING AWR-192 blueprint test (red at HEAD, out of scope). Three hard doc checks green.

## Adversarial self-review (pre-implementation)
- **Periodic repaint erases "Rebuilding…"** → prevented: `usb_button_text` checks `in_progress` first and
  `_render_usb_state` runs every tick from the flag, exactly like the exporter; the flag is reset only in
  `finishWatchedChild_`.
- **Flag never resets if the build never completes** → `_spawn_watched`'s full-lifetime watcher
  (`busy_item_attr` set → `_watch_child_full`) always marshals `finishWatchedChild_`, including on spawn
  failure (line 1622-1633) and signal death (returncode < 0); the reset branch runs in all of them.
- **False "up to date" hiding a needed rebuild** → the fingerprint includes bridge code + the live configs
  + the cache; the stamp is tied to the stick's exact `generation`. Any mismatch → "outdated". Docs/memory
  files are NOT in the root list, so auto-sync commits do not nag.
- **Main-thread stall from USB or 563 MB** → detection is off-thread; the signature is stat-only (~9 ms
  class); no content hashing anywhere.
- **Two features writing the same tick** — N/A: this is UI-only; it does not touch DeckState, the push
  loop, or any pending-transition state.
