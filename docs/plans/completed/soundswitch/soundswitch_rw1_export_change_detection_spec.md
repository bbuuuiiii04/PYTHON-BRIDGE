---
doc_status: completed-spec
truth_level: historical-implementation-spec
last_verified_commit: 9095cef
last_verified_date: 2026-06-23
validation_scope: implemented RW-1 export change-detection spec; historical evidence only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — `Export from Soundswitch` change-detection button

> **Goal (operator words):** "If there are changes detected on SoundSwitch, the
> button should say **Export from Soundswitch** (clickable). If we're up to date
> with SoundSwitch, the button should be greyed out and say **Exported**."
>
> **Scope:** add cheap, honest change-detection that drives the menubar export
> button's label + enabled-state, and repurpose the currently-duplicate greyed
> menu row into the live-reload result line. Nothing here opens a device, enables
> output, changes the backend, restarts the bridge, adds a runtime command, or
> changes the status schema. Accepted status stays SOFTWARE-VALIDATED ONLY /
> HARDWARE-UNVALIDATED.
>
> **Ordering:** land `soundswitch_rw1_export_fixes_spec.md` first (it rewrites
> `_run_export`'s reload-ack and `_recover_orphan_backup`). This spec is additive
> on top of that and does not re-touch `_run_export`'s body.

## Design in one paragraph

At export time the tool writes a tiny **sidecar** next to the canonical pack
recording (a) a content fingerprint of the SoundSwitch source bundle and (b) the
generator commit it built from. The menubar, on its existing refresh timer,
cheaply checks whether the source bundle changed (a stat-signature gate) and — only
when it changed — recomputes the content fingerprint on a **background thread** and
compares it to the sidecar. The button is greyed **"Exported"** only when it has
**positive, exact proof** that re-exporting now would produce the same pack
(source fingerprint matches **and** generator commit matches **and** the pack is
present). In every other case — any uncertainty whatsoever — the button is the
clickable **"Export from Soundswitch"**. This makes the greyed state safe: the
operator is never wrongly told they're up to date, and is never left without a way
to export.

---

## Part A — Context & root cause (verified; read, do not implement)

### A1. There is no change-detection today  [confirmed]
The button is static. `scripts/bridge_menubar.py:504-509` creates two items both
titled "Export from SS": a disabled status row (`export_status_item`) and a
clickable action (`export_item`). `_render_export_state` (`scripts/bridge_menubar.py:664-668`)
writes the **same** `export_display` string (`scripts/bridge_menubar.py:259-273`,
which returns `text, text`) into both, so at rest they are duplicates and the
button never reflects whether SoundSwitch has unexported changes. This spec makes
`export_item` reflect detection and frees `export_status_item` for the reload
result.

### A2. The source is a directory bundle  [confirmed — inspected]
`~/Music/SoundSwitch/default.ssproj` is a **directory** with 97 top-level entries:
the `.ssproj` file, the `SSAutoLoopN.ssfile` lighting files, catalogs/midi, and one
large media file (`In App Demo.mp4`). Change-detection must walk the bundle, not
stat a single file.

### A3. A sidecar must live OUTSIDE the pack directory  [confirmed]
`verify_pack` rejects any extra file in the pack (`soundswitch_pack_verifier.py:395`
"missing or extra artifact"; exercised by `tests/test_soundswitch_pack.py`'s
"extra.json" case). So the fingerprint sidecar must be a **sibling** of the pack
dir, never inside it. Its name must also not collide with the existing
`.{name}.bak-*` / `.{name}.tmp-*` / `.{name}.export.lock` globs used by
`_recover_orphan_backup` / `_gc_orphan_staging` / `_export_lock`
(`tools/export_soundswitch_pack.py:140-231`). `.rbss_canonical_pack.source.json`
satisfies both.  [confirmed: the bak/tmp/lock globs do not match `.source.json`]

### A4. The menubar must not import the bridge package  [confirmed]
`tools/export_soundswitch_pack.py:24-30` imports the decoder/compiler/verifier at
module top (heavy). The menubar (AppKit + stdlib only) therefore cannot import the
tool module to share code. The fingerprint/stat helpers are **duplicated** in both
files and kept in lock-step by a parity test (Part D). (A pure stdlib
`rb_ss_bridge_v2/source_fingerprint.py` imported by both is a viable alternative if
the operator chooses to relax the no-package-import rule; default here is duplicate
+ parity-test, which changes no invariant.)

### A5. The export tool already has the seams  [confirmed]
`_canonical_publish_result` (`tools/export_soundswitch_pack.py:345-364`) wraps
`publish_pack` and is the canonical-only path. `_generator_commit`
(`tools/export_soundswitch_pack.py:52-63`) returns the validated 40-hex HEAD.
`_atomic_write_result` (`tools/export_soundswitch_pack.py:312-330`) shows the
tmp+fsync+`os.replace` atomic-write pattern to reuse for the sidecar. The published
pack's manifest already records per-file `source_sha256` and the generator commit,
so the sidecar duplicates only a small, menubar-reproducible summary.  [confirmed]

### A6. Detection scope = export freshness (disk), not bridge liveness  [assumed — see decision]
"Up to date with SoundSwitch" is interpreted as **"the saved SoundSwitch project
matches the last successful export."** This is independent of whether the bridge is
running or has hot-reloaded; the live-reload result stays on the separate status
row (`export_status_item`). So "Exported" can show with the bridge off (nothing to
export). If the operator instead wants "Exported" to require the **live** bridge to
be running this pack, say so — it is a one-line change to the verdict.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Do **not** add a runtime command, change `parse_command`, or change the status
  schema. Detection is read-only filesystem work in the menubar process.
- The menubar still imports AppKit + stdlib only; it never imports the bridge
  package, opens a device, or blocks the AppKit main thread on hashing/subprocess.
- Do **not** change `export_pack`, `publish_pack`, the swap/lock/recover primitives,
  `_run_export`'s reload flow (owned by the fixes spec), `runtime_status.py`,
  `soundswitch_pack_controller.py`, `__main__.py`, or the 200 Hz push loop.
- The sidecar holds only hashes + a commit hash. No path/UUID/port/device/raw
  text in the sidecar, any UI string, or any committed file.

### Task 1 — `tools/export_soundswitch_pack.py`: fingerprint helpers + sidecar write

Add two pure helpers (stdlib only) and a sidecar writer; call the writer from the
canonical publish path **after** a successful publish.

```python
_SIDECAR_SUFFIX = ".source.json"  # sibling of the pack dir; NEVER inside it


def _source_stat_signature(project: str | os.PathLike[str]) -> str | None:
    """Cheap change gate: sha256 over sorted (relpath, size, mtime_ns) of every
    regular file in the bundle. Returns None if the bundle is absent."""
    base = Path(project).expanduser()
    if not base.is_dir():
        return None
    entries = []
    for root, dirs, files in os.walk(base, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            path = Path(root) / name
            try:
                st = path.lstat()
            except OSError:
                continue
            rel = path.relative_to(base).as_posix()
            entries.append((rel, st.st_size, st.st_mtime_ns))
    digest = hashlib.sha256()
    for rel, size, mtime in sorted(entries):
        digest.update(f"{rel}\x00{size}\x00{mtime}\n".encode("utf-8"))
    return digest.hexdigest()


def _source_content_fingerprint(project: str | os.PathLike[str]) -> str | None:
    """Exact change signal: sha256 over sorted (relpath, sha256(file bytes)) of
    every regular file in the bundle. Returns None if the bundle is absent."""
    base = Path(project).expanduser()
    if not base.is_dir():
        return None
    rows = []
    for root, dirs, files in os.walk(base, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            path = Path(root) / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                return None  # unreadable source -> treat as "cannot prove up-to-date"
            rel = path.relative_to(base).as_posix()
            rows.append((rel, hashlib.sha256(data).hexdigest()))
    digest = hashlib.sha256()
    for rel, file_hash in sorted(rows):
        digest.update(f"{rel}\x00{file_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def _sidecar_path(destination: Path) -> Path:
    return destination.parent / f".{destination.name}{_SIDECAR_SUFFIX}"


def _write_source_sidecar(destination: Path, source: Path, manifest_sha256: str) -> None:
    fingerprint = _source_content_fingerprint(source)
    if fingerprint is None:
        return  # cannot fingerprint -> leave no sidecar; detection stays "changes"
    payload = {
        "source_fingerprint": fingerprint,
        "generator_commit": _generator_commit(),
        "pack_manifest_sha256": manifest_sha256,
    }
    _atomic_write_result(_sidecar_path(destination), payload)
```

Add `import hashlib` at the top (alongside the existing imports). Then, in
`_canonical_publish_result` (`tools/export_soundswitch_pack.py:345-364`), after a
successful `publish_pack`, write the sidecar — failure to write the sidecar must
**not** fail the export (the pack is already published; a missing sidecar simply
makes detection report "changes"):

```python
    return {
        "ok": True,
        ...
    }
```
becomes (after computing `result`):
```python
    try:
        _write_source_sidecar(CANONICAL_PACK_DIR, CANONICAL_SOURCE_PROJECT,
                              str(result["manifest_sha256"]))
    except Exception:
        pass  # pack is published; sidecar is best-effort, detection self-heals
    return {
        "ok": True,
        ...
    }
```

> Do not touch `export_pack`, `publish_pack`, or the proof-tool path — the sidecar
> is written only by the canonical (`--publish-canonical`) flow.

### Task 2 — `scripts/bridge_menubar.py`: duplicate helpers + background detection

Add **byte-identical** copies of `_source_stat_signature`, `_source_content_fingerprint`,
`_sidecar_path` (parity-tested in Part D), plus constants and a detector. Use the
canonical paths as plain strings (the one intentional path constant, per RW-1
kickoff revision #3):

```python
CANONICAL_SOURCE_PROJECT = str(Path("~/Music/SoundSwitch/default.ssproj").expanduser())
CANONICAL_PACK_DIR = Path("~/Music/SoundSwitch/rbss_canonical_pack").expanduser()
DETECT_MAX_AGE_SECONDS = 30.0  # bound staleness if a save somehow preserves stat


def current_generator_commit() -> str | None:
    repo = Path(__file__).resolve().parents[1]
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip().lower()
    if out.returncode != 0 or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        return None
    return commit


def read_source_sidecar() -> dict | None:
    try:
        with open(_sidecar_path(CANONICAL_PACK_DIR), "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def detect_export_state() -> str:
    """Returns "up_to_date" only with exact positive proof; else "changes"."""
    pack = CANONICAL_PACK_DIR
    if pack.is_symlink() or not pack.is_dir():
        return "changes"
    sidecar = read_source_sidecar()
    if not sidecar:
        return "changes"
    current = _source_content_fingerprint(CANONICAL_SOURCE_PROJECT)
    if current is None or current != sidecar.get("source_fingerprint"):
        return "changes"
    expected_commit = sidecar.get("generator_commit")
    now_commit = current_generator_commit()
    # Only enforce the commit guard when we can actually determine HEAD; an
    # unavailable git must not permanently un-grey the button.
    if now_commit is not None and isinstance(expected_commit, str) and now_commit != expected_commit:
        return "changes"
    return "up_to_date"
```

Wire it into the existing refresh cycle with a stat-signature gate + a background
worker (mirror the export marshaling pattern). Add to `init` (near the other
`_export_*` fields at `scripts/bridge_menubar.py:492-494`):

```python
        self._export_up_to_date = False     # detection verdict (False until proven)
        self._detect_in_progress = False
        self._detect_sig = None             # stat-signature the verdict was computed for
        self._detect_at = 0.0
```

In `refresh_` (after `self._render_export_state()` at `scripts/bridge_menubar.py:612`),
add a cheap gate that spawns the worker only when needed:

```python
        self._maybe_detect_export_state()
```

```python
    def _maybe_detect_export_state(self):
        if self._export_in_progress or self._detect_in_progress:
            return
        sig = _source_stat_signature(CANONICAL_SOURCE_PROJECT)
        fresh_enough = (time.monotonic() - self._detect_at) < DETECT_MAX_AGE_SECONDS
        if sig == self._detect_sig and fresh_enough:
            return
        self._detect_in_progress = True
        self._pending_sig = sig
        threading.Thread(target=self._run_detect, daemon=True).start()

    def _run_detect(self):
        try:
            verdict = detect_export_state()
        except Exception:
            verdict = "changes"
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "finishDetect:", {"verdict": verdict, "sig": self._pending_sig}, False)

    def finishDetect_(self, payload):
        verdict = payload.get("verdict") if isinstance(payload, dict) else "changes"
        self._export_up_to_date = (verdict == "up_to_date")
        self._detect_sig = payload.get("sig") if isinstance(payload, dict) else None
        self._detect_at = time.monotonic()
        self._detect_in_progress = False
        self._render_export_state()
```

In `finishExport_` (`scripts/bridge_menubar.py:729-738`), after clearing
`_export_in_progress`, set the verdict immediately so the button flips without
waiting for a detection cycle (a successful publish means the disk now matches the
current source):

```python
        self._export_up_to_date = state != "export_failed"
        self._detect_sig = None   # force a real re-detect on the next tick
```

### Task 3 — `scripts/bridge_menubar.py`: button states + free the duplicate row

Change the action label to the operator's wording and drive enabled-state from
detection; repurpose `export_status_item` as the **reload-result** line (fixing the
duplicate). Replace `export_display` (`scripts/bridge_menubar.py:259-273`) and
`_render_export_state` (`scripts/bridge_menubar.py:664-668`):

```python
def export_button_text(in_progress: bool, up_to_date: bool) -> str:
    if in_progress:
        return "Exporting…"
    if up_to_date:
        return "Exported"
    return "Export from Soundswitch"


def export_result_line(state: str, result: dict | None = None) -> str:
    result = result or {}
    return {
        "published_not_live": "  saved (loads when pack enabled)",
        "reload_succeeded": "  live now",
        "reload_failed": "  saved — live reload not confirmed",
        "export_failed": f"  export failed ({_safe_error_category(result.get('error_category'))})",
    }.get(state, "")   # idle/exporting -> blank, no duplicate
```

```python
    def _render_export_state(self):
        self.export_item.setTitle_(
            export_button_text(self._export_in_progress, self._export_up_to_date))
        self.export_item.setEnabled_(
            not self._export_in_progress and not self._export_up_to_date)
        self.export_status_item.setTitle_(
            export_result_line(self._export_state, self._export_result))
```

Set `export_status_item`'s initial title to "" in `init`
(`scripts/bridge_menubar.py:504-506`) instead of "Export from SS".

> The button is enabled **only** when not exporting and not up-to-date. Greyed
> "Exported" is reached only via an exact `detect_export_state()=="up_to_date"`
> verdict (or immediately after a successful export). All uncertainty → clickable.

### Task 4 — tests wiring, docs, change-contract

- Add `tests/test_source_fingerprint_parity.py` (Part D1).
- Extend `tests/test_soundswitch_pack.py` (Part D2) and `tests/test_bridge_menubar.py`
  (Part D3).
- `docs/subsystems/soundswitch_output.md`: document the smart Export button
  (Export from Soundswitch / Exported / Exporting…), the sidecar (sibling of the
  pack, never inside), the exact source-fingerprint + generator-commit verdict, and
  that any uncertainty shows clickable. Keep it path/identifier-free.
- `docs/agents/change_contracts.yml`: the `soundswitch_pack_player` contract already
  lists both code files and both test files; add `tests/test_source_fingerprint_parity.py`.
  Bump `last_verified_commit` on touched contract docs.
- Run the §D hard checks + staleness.

---

## Part C — Invariants that MUST still hold (live safety)

1. Push loop / `StateManager` / OS2L / lasers / LEDs / readers / scripted / T7d /
   static / blackout untouched. Detection is read-only filesystem work in the
   menubar process; nothing is added to `_push_tick`.
2. The menubar still imports AppKit + stdlib only; no bridge-package import, no
   device opened, no runtime command added, no status-schema change. Detection's
   only runtime effect is the button's title/enabled-state.
3. **No heavy work on the AppKit main thread:** only the cheap stat-signature gate
   and marshaled verdict touch the main thread; content hashing + `git rev-parse`
   run on the daemon worker.
4. The sidecar lives **outside** the pack dir and never changes `verify_pack`'s file
   set; a missing/corrupt sidecar is safe (→ "changes"). The export's pack-publish
   contract (byte-identical prior pack on any failure) is unchanged — the sidecar is
   best-effort and never gates the publish.
5. **Greyed "Exported" requires exact positive proof** (source fingerprint match +
   generator-commit match when determinable + pack present). Any uncertainty
   (source missing/unreadable, sidecar missing/corrupt, pack missing, hash error,
   detection not yet run) → clickable "Export from Soundswitch". The operator is
   never wrongly told they are up to date, and never loses the ability to export.
6. Default-off neutrality: detection changes only the button; with no click every
   existing behavior is unchanged.

---

## Part D — Tests (pure seams; no device, no live menu bar)

### D1. `tests/test_source_fingerprint_parity.py` (new)
Build a temp bundle (subdirs, a symlink, a couple files). Assert the tool's and the
menubar's `_source_content_fingerprint` and `_source_stat_signature` return
**identical** values on it; assert both return `None` for an absent bundle; assert a
one-byte content change flips the content fingerprint but a pure `os.utime` (mtime)
change does **not**. Skip the menubar import if PyObjC is unavailable (mirror
`tests/test_bridge_menubar.py:16-21`).

### D2. `tests/test_soundswitch_pack.py` — add to `PublishPackCliTests`
- After a mocked successful `_canonical_publish_result`, a sidecar exists at the
  **sibling** path, parses as JSON with `source_fingerprint` / `generator_commit` /
  `pack_manifest_sha256`, and is **not** inside `CANONICAL_PACK_DIR` (so `verify_pack`'s
  file set is unaffected — assert no `.source.json` under the pack dir).
- A sidecar-write failure (patch `_write_source_sidecar` to raise) still returns
  `ok=True` (publish is not failed by the sidecar).
- The sidecar contains no path/home string (reuse the `Path.home()` assertion shape).

### D3. `tests/test_bridge_menubar.py` — add cases
- `export_button_text`: `(in_progress=True,*) -> "Exporting…"`;
  `(False, up_to_date=True) -> "Exported"`; `(False, False) -> "Export from Soundswitch"`.
- `export_result_line`: each post-publish state maps to its line; `idle`/`exporting`
  → `""`; `export_failed` carries only the sanitized category (no `/`, no raw text).
- `detect_export_state` truth table with a temp HOME (patch the module's
  `CANONICAL_*`): pack+matching sidecar+matching commit → `up_to_date`; changed
  source bytes → `changes`; missing sidecar → `changes`; missing pack → `changes`;
  differing generator commit (patch `current_generator_commit`) → `changes`;
  `current_generator_commit() is None` → still `up_to_date` on a source match.
- `finishExport_` sets `_export_up_to_date=True` for `reload_succeeded` /
  `published_not_live` / `reload_failed`, and `False` for `export_failed`.
- `_maybe_detect_export_state` does not spawn a worker while `_export_in_progress`
  or when the stat-signature is unchanged and the verdict is fresh.

### D4. Gates (record outputs; all hardware-unvalidated)
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 -m unittest tests.test_soundswitch_pack tests.test_bridge_menubar tests.test_source_fingerprint_parity
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check

cd /Users/bbui
python3 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
  --project ~/Music/SoundSwitch/default.ssproj --output-dir /tmp/rbss-detect-proof   # expect 29/0/0
```
Run the two changed modules under Python 3.11 too (CI is 3.11; local is 3.14).

---

## Part E — Acceptance (definition of done)

- [ ] After an export, the button reads greyed **"Exported"**; after a real edit +
      save in SoundSwitch it returns to clickable **"Export from Soundswitch"** (D3 +
      a manual dry-run click).
- [ ] Greyed "Exported" never shows without exact proof: missing/corrupt sidecar,
      missing pack, unreadable/missing source, or a changed generator commit all show
      clickable (D3).
- [ ] A no-op SoundSwitch re-save (mtime bump, identical bytes) does **not** flip the
      button to "changes" (content fingerprint, not mtime, decides) (D1).
- [ ] The sidecar is a sibling of the pack, never inside it; `verify_pack` still
      passes and the proof gate is `29/0/0` (D2 + D4).
- [ ] No content hashing or `git` runs on the AppKit main thread; a slow/failed
      detection never blocks the UI and defaults to "changes".
- [ ] The formerly-duplicate greyed row now shows only the live-reload result
      (blank at idle); no two identical "Export…" items.
- [ ] Full suite + the three named test modules green; the three hard doc checks
      pass; staleness re-verified; `git diff --check` clean; no path/identifier leak
      in UI, sidecar, logs, or committed files (besides the intentional canonical path).

## Edge cases this design handles (and how)

- Source missing/unreadable → `_source_content_fingerprint` returns None → `changes`. [confirmed by code path]
- Sidecar missing/corrupt → `read_source_sidecar` None → `changes`. [confirmed]
- Pack dir missing/symlink → `changes`. [confirmed]
- Mid-save torn read while hashing → transient `changes` that self-heals next tick;
  the export re-decodes and the verifier still guards integrity. [assumed; safe direction]
- No-op re-save (mtime change only) → stat gate fires, content matches → stays
  "Exported" (no false "changes"). [confirmed via D1]
- Media-only change (the bundled `.mp4`) → counts as a change → clickable; clicking
  re-exports idempotently (pack stays byte-identical). Harmless; whole-bundle hashing
  keeps the safe direction. [intended]
- Edit that preserves every file's size **and** mtime_ns → stat gate misses it; the
  `DETECT_MAX_AGE_SECONDS` periodic re-detect bounds staleness, and SoundSwitch
  saves update mtimes in practice. [assumed: SS bumps mtime on save; residual ≤30 s]
- Bridge code update (same source) → generator commit differs → `changes` (a
  re-export would differ), when HEAD is determinable. [confirmed if git available]
- git unavailable → commit guard skipped, source fingerprint still governs. [confirmed]
- Bridge off → button reflects export freshness only; live state stays on the result
  row. [by design A6]
- Export in progress / just finished → "Exporting…" then immediate "Exported" via
  `finishExport_`. [confirmed]
- Concurrency: detection only reads; the export holds the cross-process lock and
  writes the sidecar atomically; detection is skipped while exporting. [confirmed]
- Two menubars → blocked by `already_running()`. [existing]

## When you finish
Commit per task (1→4). Report: tests run + counts, proof verdict, the three hard
doc checks, the staleness line, and explicit confirmation that (a) detection runs
off the AppKit main thread, (b) greyed "Exported" requires exact proof, and (c) the
sidecar never lands inside the pack dir. Do not claim complete until an independent
review of the detection verdict honesty, AppKit-thread safety, and sidecar placement
passes.
