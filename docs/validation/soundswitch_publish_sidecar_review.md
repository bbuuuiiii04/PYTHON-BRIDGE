---
doc_status: active-validation
truth_level: code-and-test-grounded
last_verified_commit: e9b7a36
last_verified_date: 2026-06-25
validation_scope: publish_pack binding-sidecar atomicity review; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch publish_pack sidecar atomicity review

Review head: `e9b7a36`.

## Status

This is a software-only review of the `publish_pack` required MIDI binding sidecar
change. It does not validate hardware, DMX output, live reload behavior, or SoundSwitch
physical behavior.

## Reproduced gates

- `python3 -m unittest tests.test_soundswitch_pack`: PASS, 66 tests.
- `python3 -m unittest discover tests`: PASS, 2399 tests, 3 skipped, 1 expected failure.
- `python3 tools/check_docs_metadata.py`: PASS.
- `python3 tools/check_agent_contracts.py`: PASS.
- `python3 tools/check_docs_drift.py`: PASS.
- `git diff --check`: PASS.

## Property review

| ID | Result | Evidence |
| --- | --- | --- |
| B-1 pre-swap failure is clean | PASS | `publish_pack` stages the binding sidecar before either first-export `os.replace` or replacement swap (`tools/export_soundswitch_pack.py:448-458`). Sidecar production/write failures are wrapped as `BindingSidecarWriteError` before the swap (`tools/export_soundswitch_pack.py:172-200`). The regression test proves an existing pack and prior sibling sidecar remain byte-identical and no `.tmp`/`.bak` leftovers remain (`tests/test_soundswitch_pack.py:864-883`). For first export, the same line order means no destination is published before sidecar staging succeeds. |
| B-2 swap failure is clean | PASS | The fallback swap restores the prior pack on the second rename failure (`tools/export_soundswitch_pack.py:377-389`), and `publish_pack` unlinks the staged sidecar before surfacing `PackSwapError` (`tools/export_soundswitch_pack.py:459-464`). `PackSwapError` is an `OSError` subclass (`tools/export_soundswitch_pack.py:52-53`), so the verdict maps to `swap_failed` (`tools/export_soundswitch_pack.py:498-508`). The regression test still passes and checks no staging or backup leftovers (`tests/test_soundswitch_pack.py:836-862`). |
| B-3 success is correct | PASS | Required binding sidecars are sibling files, not pack contents (`tools/export_soundswitch_pack.py:126-127`, `tests/test_soundswitch_pack.py:1017-1064`). `export_pack` writes the same `_binding_sidecar_rows` payload through `_write_required_binding_sidecar` (`tools/export_soundswitch_pack.py:161-169`, `tools/export_soundswitch_pack.py:415-420`), while `publish_pack` stages and promotes the same sorted JSON payload (`tools/export_soundswitch_pack.py:180-190`, `tools/export_soundswitch_pack.py:465-468`). |
| B-4 promote residual | PASS with low residual | There is no single atomic operation for both the canonical pack directory and sibling sidecar file. Current code minimizes the practical risk by durably writing the sidecar before the swap, then using one same-directory `os.replace` to promote it (`tools/export_soundswitch_pack.py:180-190`, `tools/export_soundswitch_pack.py:465-468`). If that final rename fails, the command returns `sidecar_failed` (`tools/export_soundswitch_pack.py:507-508`) and canonical publish does not write the source sidecar (`tools/export_soundswitch_pack.py:512-532`, `tests/test_soundswitch_pack.py:1210-1237`). A stricter rollback would need to keep and swap back the old pack after a successful pack swap, adding new two-object recovery logic for a same-directory rename failure. No blocker/high revision is justified by current evidence. |
| B-5 orphan reclamation | PASS | Sidecar temp names use the same `.{destination}.tmp-*` prefix as pack staging (`tools/export_soundswitch_pack.py:172-183`). `_gc_orphan_staging` removes both real directories and non-directory/symlink temp entries, so a crashed sidecar temp is unlinked rather than promoted into a pack (`tools/export_soundswitch_pack.py:301-307`). The publish path runs this before decoding or staging (`tools/export_soundswitch_pack.py:437-445`), and the existing orphan test exercises the shared glob (`tests/test_soundswitch_pack.py:989-996`). |
| B-6 export_pack unchanged | PASS | `export_pack` still requires a new destination, stages artifacts, verifies, renames into place, then writes the required binding sidecar and removes the new output if sidecar writing fails (`tools/export_soundswitch_pack.py:399-423`). The sidecar-failure test still proves the new output and sibling sidecar are absent after failure (`tests/test_soundswitch_pack.py:658-678`). |
| B-7 no leak | PASS | `_binding_sidecar_rows` emits only `channel`, `note`, `target_kind`, `interaction`, and `name` for enabled static-look note press/toggle bindings (`tools/export_soundswitch_pack.py:142-158`). The sibling-sidecar tests include private `device_name` values and assert that field is absent from the output (`tests/test_soundswitch_pack.py:1017-1064`, `tests/test_soundswitch_pack.py:1125-1168`). |

## Findings

- blocker: none.
- high: none.
- medium: none.
- low: Post-swap sidecar promote failure can still leave the new pack on disk with an old
  or absent sibling binding sidecar while returning `sidecar_failed`. This is the minimal
  practical residual for the current two-object publish shape; fix only if observed in real
  logs or if the exporter grows a general multi-object transaction helper.

## Task 2 disposition

No revisions are required for blocker/high findings. The reproduced software evidence above
shows the requested properties hold, and the only remaining issue is recorded as low severity.
