---
doc_status: active-plan
truth_level: code-and-capture-corpus-grounded
last_verified_commit: 3131aa7
last_verified_date: 2026-07-01
validation_scope: Codex-orchestrated live all-surface U0/U1 parity capture WITH the operator; SoundSwitch 2.10.3 canonical project / RAVE / 2 mirrored lasers / Universe 0 / CH1-CH19; SOFTWARE/WIRE capture only, HARDWARE-UNVALIDATED
---

# Codex Spec — SoundSwitch Parity Capture Orchestration

You (Codex) run a **live all-surface U0/U1 capture WITH the operator** and produce one aligned capture
directory. This capture is the empirical ground truth used later to derive and prove perfect parity
(scripted, autoloops, static looks). You are an **observer + orchestrator + recorder**, not an
implementer. Do not change bridge behavior, run hardware, or run the live-port tools yourself.

## Part A — Context & rig (verified; read, do not change)

**Goal.** Capture SoundSwitch's own DMX output (**U0 = Art-Net universe 0**) and the bridge's shadow
render (**U1 = Art-Net universe 1**) across all three surfaces, *aligned* so every captured frame maps
to a known look / cue / phase. The reduction of this corpus derives the composition + phase algorithms
and proves them; it feeds a downstream Fable spec.

**Rig (all live binds are OPERATOR-owned — you must NOT start them):**
- `[confirmed]` SoundSwitch emits Art-Net on **universe 0** to loopback (U0). Operator configures/starts this.
- `[confirmed]` Bridge runs with `RBSS_ARTNET_TRUTH_CHECK=1` + `RBSS_ARTNET_UNIVERSE=1` → emits U1 on **universe 1** and writes the truth sidecar `/tmp/rbss_artnet_truth_frames.jsonl` (`artnet_truth.py:25,26,30`). Bridge launch is operator-only (menubar). Production pack output stays software-ZERO while SoundSwitch is connected; U1 is the shadow render.
- `[confirmed]` `tools/ssfmt/re/artnet_sniff.py` binds live UDP `:6454` and its own docstring says **agents must not run it** — the **operator** runs it, redirecting stdout to the capture dir's `artdmx_packets.jsonl`. It passively receives BOTH universes.
- `[confirmed]` Universe split is fixed: `ss_universe=0`, `bridge_universe=1` (`tools/artnet_compare.py:167-185`). U0 vs U1 is by universe number.
- `[confirmed]` Bridge status file `/tmp/rb_ss_bridge_v2_status.json` (deck elapsed_ms, lighting_mode, `native_autoloop` block with target/phase_tick/anchor, static_held); bridge log `/tmp/bridge.log`. Poll these for alignment + markers.
- `[confirmed]` Precedent to replicate: `tools/ssfmt/captures/all_surface/all_surface_20260701_024858/` (files: `capture_meta.json`, `actions.jsonl`, `artdmx_packets.jsonl`, `rbss_artnet_truth_frames.slice.jsonl`, `status_samples.jsonl`, `capture_end.json`, `artifacts.sha256`, `bridge.tail.log`). Match this layout; ADD an `alignment_index.jsonl` (below).

**Locked capture scope (operator-confirmed):** default project, RAVE, **2 mirrored lasers, CH1-19**.
Static-look targets are exactly the **4 mapped slots**: `0` (FULL STRAIGHT LINES WHITE), `24` (STROBE
BUILDUP #1), `16` (OFF), `31` (BLACK OUT). Autoloops: **all 19**, selected by the bridge's phrase logic.
Scripted: the operator's **real tracks** (start with `528E8B22` = "Rihanna – Where Have You Been
(Hardwell Club Mix)"). `[confirmed]` **DD42028C is EXCLUDED** — a metadata-less orphan the operator
never plays; do not prompt for it.

**Alignment facts you must exploit:**
- `[confirmed]` Autoloop selection is **phrase-driven by the bridge**: it picks the loop at a phrase
  marker and advances at the next phrase or after ~32 beats. `[assumed, to confirm in capture]` a loop's
  phase origin (phase 0) is the phrase marker where it was selected; cycle is 32 beats / 19,200 ticks at
  600 ticks/beat. So U0 must be aligned by **beats-since-the-loop's-phrase-marker**, read from status.
- `[confirmed]` Static looks overlay on the base; captured on a **dark/idle base** (no track playing)
  each look's U0 is that look's composed CH1-19 frame standing alone.
- `[assumed]` The 2 lasers are mirrored on CH1-19, so U0 is one 19-channel frame; confirm nothing
  nonzero beyond CH19.

## Part B — Capture procedure (do in order; one surface at a time; fail-closed)

### Absolute rules
- **Do NOT** run `artnet_sniff.py`, start/stop/restart the bridge, enable or change the pack backend,
  open Enttec/serial/DMX, mutate the SoundSwitch project, or append any runtime command that changes
  output. You only observe status/log/sidecar/packets and prompt the operator.
- Use the **operator-ping + active-wait** pattern (like `tools/t7d_capture_conductor.py`): print a clear
  instruction, notify (`say` + terminal), then POLL `/tmp/rb_ss_bridge_v2_status.json` / `/tmp/bridge.log`
  / the packet + sidecar files until the expected marker appears or a hard timeout hits. On timeout,
  record **INCOMPLETE** for that step and continue — never rubber-stamp missing evidence.
- Append every operator instruction + observed transition to `actions.jsonl` with a wall + monotonic
  timestamp and a `surface`/`label` (match the precedent's schema).
- Sample `/tmp/rb_ss_bridge_v2_status.json` at ≥5 Hz into `status_samples.jsonl` for the whole session
  (this is the alignment backbone: elapsed_ms, lighting_mode, native_autoloop target/phase_tick/anchor,
  static_held, active_deck, beat/phrase fields).

### Task 0 — Pre-flight (gate; abort if any fails)
1. Operator confirms physical laser/DMX/Enttec outputs are safe/disconnected/powered-off, no live audience.
2. Confirm **exactly one** bridge process (`pgrep -f rb_ss_bridge_v2 | wc -l == 1`).
3. Confirm truth-check is live: status has a `truth_check.run_id`; sidecar `/tmp/rbss_artnet_truth_frames.jsonl` is growing.
4. Confirm the operator has started the sniffer into `<capture_dir>/artdmx_packets.jsonl` and that BOTH
   universe 0 (U0) and universe 1 (U1) packets are arriving. If no U0 packets: STOP and tell the operator
   SoundSwitch is not emitting Art-Net U0 — do not proceed.
5. Create `<capture_dir>` under `tools/ssfmt/captures/parity/parity_<UTC>/` (gitignored) and write
   `capture_meta.json` (type `parity_capture_meta`, repo, sidecar path + start byte, status path,
   started_iso/wall, the safety confirmation string).

### Task 1 — Static looks (fastest; likely solves the surface)
For each mapped slot in order `[0, 24, 16, 31]`, with **no track playing** (idle/dark base):
- Prompt: "Trigger and HOLD static look slot N ("<name>") for ~20 s; nothing else active."
- Active-wait until status shows the look held (`static_held` / held layer for that slot), then hold the
  window; log start/end timestamps to `actions.jsonl` and keep sampling status.
- Slot 24 is the **time-invariance probe**: while it is held, note whether U0 packets are a *constant*
  frame or a *changing stream* — record the observation explicitly.

### Task 2 — Autoloops (all 19, phrase-driven; do NOT manually hold)
- Prompt: "Play unscripted tracks and let the bridge drive autoloop selection normally; keep playing
  through many phrases so different loops fire. Aim to exercise all 19."
- Continuously record, from status/log, the fired-loop identity, phrase markers, beat position, and
  `native_autoloop` phase_tick/anchor over time (this IS the phase ground truth). Maintain a running set
  of loop identities seen.
- Continue until all 19 distinct active autoloop targets have fired for ≥1 full 32-beat window each, or a
  hard time cap. Record which loops were covered and which were **not** (INCOMPLETE list) — do not claim
  full coverage if a loop never fired.

### Task 3 — Scripted (real tracks; Rihanna first; DD42028C excluded)
- Prompt the operator to play each real scripted track **fully and clean** (no static/autoloop overlap),
  starting with `528E8B22` (Rihanna). For each: active-wait for real playback (deck playing, elapsed_ms
  advancing from near 0), then let it run through; log track SSID + play window; keep sampling status so
  U0 aligns to elapsed_ms/boundaries.
- Cover the operator's real tracks. Record which SSIDs were captured and which were skipped.

### Task 4 — Mirror + time-invariance confirmation
- From the static (slot 0/24) and a scripted window, record: (a) is U0 constant within a held state
  (time-invariance)? (b) is anything nonzero beyond CH19? (c) if the sniffer sees the second fixture
  group/universe separately, do its CH1-19 match the primary? Note findings; do not block on this.

### Task 5 — Finalize
- Write `alignment_index.jsonl`: one row per captured state window = `{surface, label, look_slot|ssid|loop_identity, t_start_wall, t_end_wall, t_start_mono, t_end_mono, notes}`. This is what lets the reducer map U0 frames → look/cue/phase without re-guessing.
- Slice the truth sidecar for the session window into `rbss_artnet_truth_frames.slice.jsonl`; tail
  `bridge.log` into `bridge.tail.log`; write `capture_end.json` (end timestamps, per-surface
  ACCEPTED/INCOMPLETE, coverage lists) and `artifacts.sha256`.
- Keep everything **sanitized**: no absolute local paths beyond the repo root, no device serials, no
  project UUIDs in any committed summary (the capture dir itself is gitignored; keep it that way).

## Part C — Invariants that MUST hold (live safety)
1. Observer/read-only. StateManager stays the only DeckState writer; you add no runtime command that
   changes output, backend, or enable state.
2. You never start the sniffer, start/stop/restart the bridge, open hardware, or mutate the SoundSwitch
   project. Those are operator actions.
3. Exactly one bridge process throughout; if it dies or a second appears, STOP and report.
4. The capture directory stays under the gitignored `tools/ssfmt/captures/` tree; nothing sanitized-out
   leaks into a committed file.
5. Missing evidence is INCOMPLETE, never ACCEPTED. No surface is "covered" unless its frames + alignment
   rows exist.

## Part D — Verification (you validate BEFORE declaring done)
- U0 and U1 both present across the whole session (universe 0 and 1 packet counts > 0 per surface window).
- Static: all 4 slots have a held window with ≥N U0 frames each and an alignment row.
- Autoloops: the covered-loop set + phase samples exist; the uncovered set is recorded.
- Scripted: each captured track has a play window with advancing elapsed_ms and an alignment row.
- `alignment_index.jsonl` rows are internally consistent with `actions.jsonl` + `status_samples.jsonl`
  timestamps.
- `tools/artnet_compare.py --self-check` still passes (sanity of the comparator you'll hand off).

## Part E — Acceptance (definition of done)
- One `tools/ssfmt/captures/parity/parity_<UTC>/` directory with: `capture_meta.json`, `actions.jsonl`,
  `artdmx_packets.jsonl`, `rbss_artnet_truth_frames.slice.jsonl`, `status_samples.jsonl`,
  `alignment_index.jsonl`, `capture_end.json`, `artifacts.sha256`, `bridge.tail.log`.
- Per-surface ACCEPTED/INCOMPLETE recorded honestly with coverage lists.
- The time-invariance (slot 24) and mirror observations recorded.

## When you finish
- Do not commit the capture dir (gitignored). Print the capture directory path and a short
  ACCEPTED/INCOMPLETE-per-surface summary + coverage lists so the operator can paste it back into the
  Claude chat. Report exact totals (U0/U1 frame counts, loops covered, tracks covered); do not round
  "INCOMPLETE" up to "done."
