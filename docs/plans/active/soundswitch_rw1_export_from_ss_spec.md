---
doc_status: active-spec
truth_level: code-grounded
last_verified_commit: 683af8d
last_verified_date: 2026-06-23
validation_scope: RW-1 implementation spec only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no implementation performed
---

# Codex Implementation Spec — RW-1 one-click `Export from SS`

> **Scope:** RW-1 only — a single menubar action that re-exports the canonical
> saved SoundSwitch project, atomically replaces the one canonical pack, and
> (when the bridge is live and pack output is enabled) confirms a reload took
> effect. This spec does NOT implement RW-1A, RW-2..RW-11, T7d, native autoloop
> DMX, local live config creation, or any hardware/output enablement.
>
> **Accepted status stays:** SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
> Nothing here opens MIDI/serial/Enttec/DMX, enables output, changes the backend,
> or starts/restarts the bridge.

## Operator decisions locked for this spec (2026-06-23)

These three were resolved with the operator before authoring; the design depends
on them.

1. **Execution seam = subprocess.** The menubar spawns a Python subprocess to do
   the heavy decode/compile/verify/publish; it never imports the bridge package
   into the AppKit process.
2. **Pack location = fixed canonical path baked into code.** Export always
   publishes to one constant location; no per-click directories, and no config is
   required for the *disk* export to succeed. (Live reload still requires the
   running bridge's local pack config `pack_path` to point at that location — see
   §B2/§B6.)
3. **Reload confirmation = pack-fingerprint poll.** After publishing, the menubar
   appends the existing `set_soundswitch_pack reload` command and waits for the
   bridge's already-published `soundswitch_pack.pack_sha12` to flip to the new
   pack's hash. No new runtime command, no command/status contract change.

---

## Part A — Context & verified current state (read; do not implement)

### A1. Objective and non-goals

**Objective.** Brandon edits and *saves* lighting in SoundSwitch, clicks one
menubar item **Export from SS**, and the bridge republishes the single canonical
pack and (if live + enabled) confirms the new pack is running — with honest,
sanitized feedback distinguishing "saved" from "live now."

**Non-goals (out of scope, must not change):** RW-1A runtime-swap shutdown
ownership, scripted pause/stop semantics (RW-2), mode-authority gate (RW-3),
MIDI-input health (RW-4), status-schema expansion beyond what RW-1 needs (RW-5),
T7d/native autoloop, creating the *live* local config (RW-6), and hardware (RW-9/10).

### A2. Authority files/symbols (verified at `683af8d`)

| Symbol | Location | Verified fact | Label |
| --- | --- | --- | --- |
| `export_pack(project, output)` | `tools/export_soundswitch_pack.py:58` | Decodes → compiles → sibling `mkdtemp` staging → write `xb`+`os.fsync` each artifact → fsync dirs → `verify_pack(staging, source_project=source)` → `os.replace(staging, destination)` → fsync parent; `rmtree(staging)` on any `BaseException`. | [confirmed] |
| reject-existing guard | `tools/export_soundswitch_pack.py:61` | `if destination.exists() or destination.is_symlink(): raise FileExistsError`. So `export_pack` **cannot** replace; it is new-path only. | [confirmed] |
| parent guard | `:64` | parent must be a real existing dir, not a symlink. | [confirmed] |
| `verify_pack(pack, *, source_project=None)` | `soundswitch_pack_verifier.py:368` | independent verifier; keyword `source_project`. | [confirmed] |
| `SoundSwitchPackPlayerConfig.pack_path` | `soundswitch_pack_player_config.py:48` | config holds the pack **destination** (`pack_path`); there is **no** source-project key in `_ALLOWED_KEYS` (`:25`). Loader is fail-closed and never raises. Default config path `config/soundswitch_pack_player.json`; env override `RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG`. | [confirmed] |
| example config | `config/soundswitch_pack_player.example.json` | `enabled=false, dry_run=true, output_backend="none", pack_path=""`. | [confirmed] |
| `SoundSwitchPackController._reload` | `soundswitch_pack_controller.py:139` | if runtime not enabled → `prepare()` validate-only → `(True,"reloaded_disabled")` on success else `(False, <ClassName>)`; if enabled → `_swap_to_started()`. **No implicit enable.** | [confirmed] |
| `_prepare_pack_runtime` | `__main__.py:1234` | reloads config + builds bundle; raises `RuntimeError("pack_prepare_failed")` unless `player`+`frame_sender`+`laser_backend` all built — which only happens for a fully pack-capable config (`enabled=true, dry_run=false, output_backend=pack, enttec_port` set). So `reloaded_disabled` only returns success when the on-disk config is fully pack-capable. | [confirmed] |
| `set_soundswitch_pack` parse | `runtime_status.py:431,457,461` | actions `{reload,backend,enable}`; rejects extra keys; backend ∈ `{pack,none,midi}`. | [confirmed] |
| pack command dispatch | `runtime_status.py:402` | calls `self._pack_command_callback(action, **{backend,enabled})`; result `(ok, detail)`; on failure sets the **single shared** `self._last_error` (sanitized class name only). | [confirmed] |
| status snapshot | `runtime_status.py:101,125,134` | `atomic_write_json(STATUS_PATH)`; includes `written_at`, `soundswitch_pack` (= `PackRuntime.sanitized_status()` → `enabled/backend/pack_loaded/pack_sha12/reason/...`), and a single `last_error`. | [confirmed] |
| `PackRuntime.sanitized_status` | `soundswitch_pack_runtime.py:35` | exposes `pack_sha12` (first 12 of manifest sha), `enabled`, `reason`, `backend`; no paths/ports/UUIDs/raw errors. | [confirmed] |
| menubar helpers | `scripts/bridge_menubar.py:36,97,153,166` | `STATUS_PATH`/`COMMANDS_PATH` constants; `bridge_pids()` (pgrep); `read_status()` (marks `stale` when `written_at` age > 3 s); `append_command()` (O_APPEND JSON line). Module imports only AppKit + stdlib — **nothing from the bridge package.** | [confirmed] |
| menubar UI thread | `scripts/bridge_menubar.py:463,474,576` | a 1–3 s `NSTimer` drives `refresh_` on the AppKit main thread; `toggleBridge_` already does a blocking `while…time.sleep(0.2)` loop up to 1.5 s on that thread. No background-work helper exists for long tasks. | [confirmed] |
| canonical SOURCE path | `tools/prove_soundswitch_pack_generation.py:115` | the only place pinning `~/Music/SoundSwitch/default.ssproj` is the proof tool's `DEFAULT_PROJECT`. **No production constant exists.** Identity is enforced by UUID inside the decoder regardless of path. | [confirmed] |
| owner cleanup (RW-1A) | `__main__.py:872,874` | `pack_output_owners` + `_cleanup_pack_outputs` cover startup senders only; runtime-swapped senders aren't re-registered. **RW-1A — explicitly out of scope here.** | [confirmed] |

### A3. Root gap

The compiler/verifier/loader and durable new-path publish are all done and
tested (`ExportPackLaunchSafetyTests`, `test_two_exports_are_byte_identical`,
`test_atomic_publish_requires_new_destination`). What is missing:

1. **No in-place replacement.** `export_pack` refuses an existing destination, and
   `os.replace(src, dst)` cannot replace a **non-empty** directory on macOS
   (`rename(2)` → `ENOTEMPTY`). A real replace needs a directory *swap* primitive.
2. **No menubar action / worker / progress / result.**
3. **No reload acknowledgement.** Appending a command proves nothing: `last_error`
   is a single shared field, written only on failure, with no success echo and no
   command id. The fingerprint (`pack_sha12`) in status is the usable correlation.

### A4. Control flow to deliver

```
[click Export from SS]
   menubar(main thread): guard concurrency, set state=exporting, disable item
   menubar(worker thread): spawn  python3 -m rb_ss_bridge_v2.tools.export_soundswitch_pack
                                  --publish-canonical --result-json <tmp>
        tool: lock → recover orphan backup → decode(CANONICAL_SOURCE)
              → compile → stage+fsync → verify_pack(staging)
              → swap into CANONICAL_PACK_DIR (renamex_np RENAME_SWAP, fallback move-aside)
              → write sanitized result JSON {ok, verdict, manifest_sha256, artifact_count}
   menubar(worker): parse result.
        if bridge off OR pack not enabled  -> state=published_not_live   (no reload sent)
        else: append {"cmd":"set_soundswitch_pack","action":"reload"}
              poll fresh read_status() until soundswitch_pack.pack_sha12 == new_sha[:12]
                 match within timeout -> state=reload_succeeded
                 timeout              -> state=reload_failed   (disk publish still stands)
   menubar(main thread): render sanitized state into a status row + item title; re-enable item
```

---

## Part B — Implementation design (implement exactly, in order; commit per task)

### Absolute rules

- Do **not** modify `export_pack` (keep the launch-path / proof-tool contract and
  its `test_atomic_publish_requires_new_destination`). Add new symbols beside it.
- Do **not** add any runtime command, change `parse_command`, or change the status
  schema. The reload uses the existing `set_soundswitch_pack reload`.
- The menubar must **not** import the bridge package, open any device, or send
  `enable`/`backend`. Its only runtime command is `reload`.
- No change to `StateManager`, the 200 Hz push loop, OS2L, lasers, LEDs/Govee,
  Rekordbox readers, scripted/autoloop/T7d, static/blackout, or RW-1A ownership.
- Never write into the SoundSwitch source project; never automate Command-S.
- No path/UUID/port/device/raw-exception text in any UI string, status, log line,
  result file, or committed file.

### Task 1 — `tools/export_soundswitch_pack.py`: replace-capable `publish_pack`

Add constants and a replace transaction. Keep `export_pack` untouched.

```python
CANONICAL_SOURCE_PROJECT = Path("~/Music/SoundSwitch/default.ssproj").expanduser()
# [assumed] Operator may relocate; must equal the live pack config pack_path (see B2/B6).
CANONICAL_PACK_DIR = Path("~/Music/SoundSwitch/rbss_canonical_pack").expanduser()

_RENAME_SWAP = 0x00000002  # macOS sys/stdio.h renamex_np flag
```

`publish_pack(project, destination) -> dict`:

```
source = Path(project).expanduser(); dest = Path(destination).expanduser(); parent = dest.parent
if dest.is_symlink(): raise ValueError("destination must not be a symlink")
if not parent.is_dir() or parent.is_symlink(): raise ValueError("parent must be a real dir")
with _export_lock(parent, dest.name):           # cross-process O_EXCL lock; stale recovery
    _recover_orphan_backup(parent, dest.name)   # finish/rollback any prior crashed swap
    decoded   = decode_project(source)
    artifacts = compile_pack_artifacts(decoded, generator_commit=_generator_commit())
    staging   = Path(tempfile.mkdtemp(prefix=f".{dest.name}.tmp-", dir=parent))
    try:
        # identical write/fsync loop as export_pack (xb + os.fsync per file, fsync dirs)
        result = verify_pack(staging, source_project=source)   # publish gate
        if not dest.exists():
            os.replace(staging, dest); _fsync_dir(parent)      # first publish (atomic create)
        else:
            _atomic_swap_dir(staging, dest, parent)            # replace existing
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True); raise
```

`_atomic_swap_dir(staging, dest, parent)`:

```
try:
    _renamex_np_swap(dest, staging)        # atomic: dest <-> staging
    _fsync_dir(parent)
    shutil.rmtree(staging, ignore_errors=True)   # remove the swapped-out OLD pack
except (OSError, AttributeError, NotImplementedError):
    # Fallback: NOT atomic. The crash window (dest renamed away, new not yet in place)
    # is recovered by _recover_orphan_backup on the next publish.
    backup = parent / f".{dest.name}.bak-{secrets.token_hex(8)}"
    os.replace(dest, backup)
    try:
        os.replace(staging, dest)
    except BaseException:
        os.replace(backup, dest); raise      # rollback to old pack
    _fsync_dir(parent); shutil.rmtree(backup, ignore_errors=True)
```

`_renamex_np_swap(a, b)`: `ctypes.CDLL("libc.dylib", use_errno=True).renamex_np(bytes(a), bytes(b), _RENAME_SWAP)`; on non-zero raise `OSError(errno, ...)`. Make the libc handle injectable (module-level `_libc` or a parameter) so tests can force the fallback.

`_recover_orphan_backup(parent, name)`: scan `parent` for `.{name}.bak-*`:
- backup present **and** `dest` missing → `os.replace(backup, dest)` (finish rollback);
- backup present **and** `dest` present → `rmtree(backup)` (new already published);
- multiple backups → keep none once dest is valid; never delete the only valid pack.

`_export_lock(parent, name)` (contextmanager): `os.open(parent/f".{name}.export.lock", O_CREAT|O_EXCL|O_WRONLY)` with `pid\n<mono>`; if it exists, read it — if the pid is dead or the file is older than a bounded TTL (e.g. 10 min) steal it, else raise a typed "export already running". Always remove on exit.

> **Refactor note:** factor the shared write+fsync loop out of `export_pack` into a
> private `_stage_artifacts(artifacts, parent, dest_name) -> staging` and call it
> from both `export_pack` and `publish_pack` so the durable-write behavior cannot
> drift between them.

### Task 2 — `tools/export_soundswitch_pack.py`: canonical CLI + sanitized result

Extend `main()` (keep `--project/--output` working for the proof tool):

- Add `--publish-canonical` (publish `CANONICAL_SOURCE_PROJECT` → `CANONICAL_PACK_DIR`
  via `publish_pack`, creating `CANONICAL_PACK_DIR.parent` only if it is a real dir).
- Add `--result-json PATH`: write a sanitized result atomically (tmp + `os.replace`):

```json
{"ok": true, "verdict": "published", "manifest_sha256": "<hex>",
 "artifact_count": 95, "first_export": false, "error_category": ""}
```

`verdict ∈ {published, source_error, verify_failed, locked, swap_failed, unknown_error}`;
`error_category` = exception class name only. **Never** emit a path, UUID, port, or
raw message. Exit code 0 on `ok`, non-zero otherwise (menubar uses the JSON, not
stdout text).

### Task 3 — `scripts/bridge_menubar.py`: `Export from SS` action, worker, reload handshake

Add pure, importable seams (testable without AppKit):

```python
def build_export_argv(result_path: str) -> list[str]:
    return [sys.executable, "-m", "rb_ss_bridge_v2.tools.export_soundswitch_pack",
            "--publish-canonical", "--result-json", result_path]

def parse_export_result(text: str) -> dict:   # tolerant; malformed -> {"ok": False, "verdict": "unknown_error"}

def evaluate_reload_ack(status: dict, expected_sha12: str) -> str:
    # "succeeded"  : fresh (not stale) status, soundswitch_pack.pack_sha12 == expected_sha12
    # "not_live"   : bridge has no pack enabled (soundswitch_pack.enabled is False/absent)
    # "pending"    : fresh but sha not yet matching
    # "stale"      : no fresh snapshot to judge
```

Wire the UI:

- One status row reused for export state (extend the existing `status_rows` block or
  add one menu item); plus a clickable `self.export_item = self._add_action("Export from SS", "exportFromSS:")`.
- `exportFromSS_(sender)` (main thread): if `self._export_in_progress` → return
  (concurrency guard); else set it, set `self._export_state="exporting"`, disable the
  item, and start a `threading.Thread(daemon=True, target=self._run_export)`.
- `_run_export` (worker thread; only file I/O + subprocess, never AppKit):
  1. `result_path = NamedTemporaryFile path`; `subprocess.run(build_export_argv(result_path), timeout=…)`.
  2. `res = parse_export_result(Path(result_path).read_text())`.
  3. if not `res["ok"]` → marshal `_finish_export("export_failed", res)` to main thread; return.
  4. determine liveness: `status = read_status()`; if `not bridge_pids()` or
     `evaluate_reload_ack(status, …)=="not_live"` → marshal `_finish_export("published_not_live", res)`.
  5. else `append_command({"cmd":"set_soundswitch_pack","action":"reload"})`; poll
     `read_status()` every ~0.25 s up to a bounded timeout (e.g. 8 s) calling
     `evaluate_reload_ack(read_status(), res["manifest_sha256"][:12])`:
     `"succeeded"`→`reload_succeeded`; on timeout→`reload_failed`.
  6. marshal `_finish_export(state, res)`.
- Marshal results to the main thread with
  `self.performSelectorOnMainThread_withObject_waitUntilDone_("finishExport:", payload, False)`;
  `finishExport_` clears `_export_in_progress`, stores `_export_state`, re-enables
  the item, and lets `refresh_` render it.
- `refresh_` renders sanitized text only:

| state | item / row text |
| --- | --- |
| idle | `Export from SS` |
| exporting | `Export from SS…  (working)` (disabled) |
| published_not_live | `Exported ✓  saved (loads when pack enabled)` |
| reload_succeeded | `Exported ✓  live now` |
| reload_failed | `Exported ✓  saved — live reload not confirmed` |
| export_failed | `Export failed  (<error_category>)` |

> `<error_category>` is the sanitized class name from the result JSON only.

### Task 4 — config + docs + change-contract

- `config/soundswitch_pack_player.example.json`: set `pack_path` to the canonical
  pack path string (`~/Music/SoundSwitch/rbss_canonical_pack`) so a copied config
  loads the exported pack. Keep `enabled=false, dry_run=true, output_backend="none"`.
- `docs/agents/change_contracts.yml` (`soundswitch_pack_player`): add
  `tools/export_soundswitch_pack.py` and `scripts/bridge_menubar.py` to `code`, and
  the new test files to `tests`; confirm `docs_update` lists the docs below.
- `docs/subsystems/soundswitch_output.md`: document Export from SS, the canonical
  location, the swap/rollback contract, and the fingerprint reload-ack (saved vs live).
- `docs/subsystems/runtime_commands.md` + `docs/setup/runtime_commands.md`: note the
  menubar reuses `set_soundswitch_pack reload`; **no new command**.
- `docs/plans/active/soundswitch_exporter_remaining_work.md`: flip RW-1 status when
  landed (implementer updates, with evidence).
- Run the §D hard checks + staleness; bump verified commit on touched contract docs.

---

## Part C — Invariants that MUST still hold (live safety)

1. The 200 Hz push loop and `StateManager` are untouched; the menubar and tool are
   separate processes. No filesystem/subprocess/MIDI/serial/socket/sleep/blocking
   lock is added to `_push_tick`.
2. Reload **never** enables output, changes backend, restarts/starts the bridge, or
   opens MIDI/serial/Enttec/DMX. The controller already enforces no-implicit-enable
   (`soundswitch_pack_controller.py:139`); the menubar must only ever send `reload`.
3. The SoundSwitch source project is read-only; no Command-S, no project mutation.
4. Only a fully `verify_pack`-passed staged pack may become canonical. A failed
   decode/compile/verify/swap leaves the prior canonical pack **byte-identical and
   loadable**; staging/backup never replace the only valid pack.
5. Disk publish success and live reload success are **distinct** states and reported
   separately; a disabled runtime / stopped bridge stays exactly that.
6. Default-off neutrality: the feature is additive and only runs on an explicit
   click. With no click, every existing OS2L / MIDI-laser / LED-Govee / Rekordbox /
   command / log behavior is unchanged.
7. RW-1A (runtime-swap shutdown ownership) is **not** addressed and **not**
   regressed; this spec does not enable pack output, so the latent RW-1A gap stays
   latent.
8. No path, UUID, port, device name, project byte, or raw exception text appears in
   UI strings, the result JSON, logs, or any committed file. The pack sha (a content
   hash) is the only identifier surfaced.
9. The AppKit main thread is never blocked by decode/compile/verify/poll; all of it
   runs on the subprocess + the daemon worker thread, with results marshaled back.

---

## Part D — Tests (pure seams; no device, no live menu bar, no SoundSwitch)

### D1. `tests/test_soundswitch_pack.py` — new `PublishPackReplaceTests`

- first publish to an absent dest creates a pack byte-identical to `export_pack`'s.
- replace an existing non-empty pack → new pack present and byte-identical to a fresh
  export of the same source; old artifacts gone.
- publish the same source twice → byte-identical (idempotent).
- staged-verify failure (patch `verify_pack` to raise) → existing canonical pack left
  byte-identical + `load_pack`-able; no leftover staging; no orphan backup.
- swap failure (force both primitive and the fallback second rename to raise) →
  canonical pack restored byte-identical (rollback); staging removed.
- symlink destination rejected; symlink/file/missing parent rejected (mirror the
  existing `ExportPackLaunchSafetyTests`).
- `renamex_np` unavailable (inject a libc whose `renamex_np` raises) → move-aside
  fallback used and result still correct.
- orphan-backup recovery: (backup present, dest missing) → restored; (backup present,
  dest present) → backup discarded, dest untouched.
- lockfile: a held lock makes a second `publish_pack` raise the typed "already
  running"; a stale lock (dead pid / past TTL) is stolen and publish proceeds.
- reuse `test_pack_contains_no_absolute_source_or_audio_path` shape against
  `publish_pack` output.

### D2. `tests/test_bridge_menubar.py` — new cases (importlib + patch seam)

- `build_export_argv()` returns the exact `[sys.executable, "-m", …, "--publish-canonical", "--result-json", p]` (no shell).
- `parse_export_result()` parses ok/verdict/sha/artifact_count; malformed/empty →
  `{"ok": False, "verdict": "unknown_error"}`.
- `evaluate_reload_ack()` truth table: fresh+match→`succeeded`; fresh+no-pack-enabled→
  `not_live`; fresh+mismatch→`pending`; stale→`stale`.
- export handler with bridge **off** (patch `bridge_pids` → []) after an ok result:
  state `published_not_live`, `append_command` **not** called.
- export handler with bridge **on** + pack enabled: appends exactly
  `{"cmd":"set_soundswitch_pack","action":"reload"}`; on a subsequent fresh status
  with matching `pack_sha12` → `reload_succeeded`.
- concurrency: a second `exportFromSS_` while `_export_in_progress` spawns no second
  subprocess.
- sanitization: rendered item/row text for each state contains no `/` path segment
  and no raw exception message.

### D3. Gates (record outputs; all hardware-unvalidated)

```bash
cd /Users/bbui
python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
  --project ~/Music/SoundSwitch/default.ssproj --output-dir /tmp/rbss-rw1-proof   # expect 29/0/0

cd /Users/bbui/rb_ss_bridge_v2
python3 -m unittest tests.test_soundswitch_pack tests.test_bridge_menubar
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Also run the new/affected modules under Python 3.11 (CI is 3.11; local is 3.14) for
any dataclass/import/`ctypes` additions.

---

## Part E — Acceptance, sequencing, rollback

### E1. Commit slicing (each leaves the tree safe; the menubar item lands last)

1. `publish_pack` + `_atomic_swap_dir` + `_renamex_np_swap` + `_export_lock` +
   `_recover_orphan_backup` + the `_stage_artifacts` refactor + D1 tests.
   (`export_pack` untouched; proof gate unaffected.)
2. CLI `--publish-canonical` + `--result-json` sanitized result + tests.
3. Menubar `Export from SS` item + worker + state machine + reload handshake + D2 tests.
4. Config `pack_path` + docs + change-contract + RW-1 status; run all D3 gates.

### E2. Definition of done

- [ ] one click runs exactly one full rescan and publishes to the one canonical location.
- [ ] replacing an existing non-empty pack succeeds; a failed export leaves the prior
      pack byte-identical and `load_pack`-able (proven by D1).
- [ ] disk publish and live reload are distinct, sanitized states (D2); the menubar
      can show: export failed / saved-not-live / saved-live-not-confirmed / live now.
- [ ] no test opens a device; no UI/result/log string leaks a path/UUID/port/raw error.
- [ ] reload never enables, changes backend, restarts the bridge, or opens hardware;
      a disabled runtime stays disabled and a stopped bridge stays stopped.
- [ ] full suite + proof gate (29/0/0) + the three hard docs checks pass; staleness
      re-verified; `git diff --check` clean.

### E3. Rollback / disable

The feature is additive and triggered only by the menu click. Reverting the Task 3
commit removes the menu item; `publish_pack` is never called by the runtime; the
bridge's pack output stays default-off. No live state is touched by reverting.

### E4. Stop point

Spec + independent review only. **No implementation in this task.** Reviewer prompt:
`docs/prompts/reviews/soundswitch_rw1_export_from_ss_review_prompt.md`.

---

## Pre-handoff checklist + adversarial self-review

1. **Claims labeled.** §A2 labels every fact confirmed/assumed; the two `[assumed]`
   items are the exact canonical paths (operator-relocatable constants).
2. **Verified at current code.** All anchors re-read at `683af8d`; `os.replace`
   non-empty-dir failure and the single-shared `last_error` are the load-bearing
   facts driving the swap primitive and the fingerprint ack.
3. **Pending-state guard.** The only shared output surface touched is the pack
   runtime; reload goes through the existing validate-first controller, which already
   guards enable/backend/swap. The menubar never sends enable/backend.
4. **Mode-transition cleanup.** Export state is menubar-local and reset on completion
   (`finishExport_` clears `_export_in_progress`); a crashed swap is cleaned by
   `_recover_orphan_backup` on the next publish; the lockfile is released on every exit.
5. **Third-party API completeness.** `renamex_np(from, to, RENAME_SWAP=0x2)` via
   `libc.dylib` with `use_errno`; both-must-exist semantics handled (first publish uses
   `os.replace`); fallback + recovery + support boundary stated.
6. **Cross-checked existing code.** `publish_pack` reuses `decode_project`,
   `compile_pack_artifacts`, `verify_pack(…, source_project=)`, `_generator_commit`,
   `_fsync_dir`, and the `xb`+fsync write loop exactly as `export_pack`; the menubar
   reuses `read_status`/`append_command`/`bridge_pids` and the existing reload command.
7. **Pure-function seam.** `_atomic_swap_dir`, `_renamex_np_swap`, `_recover_orphan_backup`,
   `_export_lock`, `build_export_argv`, `parse_export_result`, `evaluate_reload_ack` are
   all testable without AppKit/SoundSwitch/devices.
8. **Live safety explicit.** Part C: push loop untouched; no enable/backend/restart/
   hardware; failed publish preserves the prior pack; saved≠live; default-off neutral.
9. **Adversarial attacks considered:**
   - *Non-empty `os.replace`* → the bug if "atomically replace" were taken literally;
     fixed by `renamex_np` swap + move-aside fallback + orphan recovery.
   - *Reload "succeeds" with no proof* → fingerprint poll requires the bridge's
     `pack_sha12` to actually flip; never asserts live on a stale snapshot.
   - *Identical re-export* → same bytes → same sha → ack can't distinguish; benign,
     because the live pack is already that content (reported as live/no-op, never
     false-failed).
   - *Concurrent clicks / second process* → in-process guard + cross-process O_EXCL
     lock with stale recovery.
   - *Crash mid-swap* → fallback leaves a recoverable backup; next publish restores or
     discards it; the only-valid-pack is never deleted.
   - *AppKit freeze* → all heavy work on subprocess + daemon thread; only marshaled
     UI-state updates touch the main thread.
   - *Info leak* → result JSON and UI carry only verdict/category/sha/count.

## When you finish (Codex)

Commit per Task (E1). Report: tests run + counts, proof-gate verdict, the three hard
docs checks, the staleness line, and confirmation that no device was opened and no
path/identifier is surfaced. Do not claim RW-1 complete until an independent review of
the swap safety, UI concurrency, reload ack, sanitization, and no-implicit-enable
passes.
