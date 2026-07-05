---
doc_status: current
truth_level: operator-authoritative target behavior
last_verified_commit: 18689e9
last_verified_date: 2026-07-05
validation_scope: intent contract, re-verified against as-built W1-W7 code; implemented/software-tested; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Logging Authority (event stream + `bridge-view`)

Status: AUTHORITATIVE TARGET BEHAVIOR; **implemented/software-tested** — the AWR-125 logging
overhaul (`docs/plans/active/logging_overhaul_spec.md`, Tasks W1-W7) is built and this document has
been re-verified against the as-built `bridge_log.py`/`bridge_view.py`/`scripts/ss_bridge_watcher.sh`
(see the two amendments below); a bridge restart, `bridge-verify`, and operator sign-off remain
outstanding. Behavior that differs from this document is a regression unless this document is
intentionally updated. Code-grounded design detail, evidence, teardown ledger, and the build
decomposition live in the design doc; this document is the intent contract that survives
implementation drift.

Sibling authorities: `runtime_invariants.md` (push-loop and event rules this system must never
violate), `palette_control_authority.md`, `drop_presentation_authority.md`,
`laser_color_authority.md` (surfaces whose decisions this system reports).

## Meaning

The bridge keeps exactly **one authoritative record of what it decided and what it knows about
its own health**: a per-run JSONL event stream, written by the bridge process itself. Everything a
human or agent reads is a **view over that one stream** — rendered by a separate viewer process
(`bridge-view`), never by the bridge. There are no parallel hand-maintained logs that can drift
from what the bridge actually decided.

Audiences, in priority order: **Brandon mid-set** (glance, verify the rig by eye, notice breakage);
**Brandon post-set** (reconstruct what happened); **AI agents** (root-cause from the raw stream).

## Non-negotiables

1. **The 200 Hz push loop never blocks for logging.** On the hot path the bridge does exactly:
   level check → merge message → read two contextvars + two clocks → build one dict →
   non-blocking put into a bounded in-memory queue (drop + count when full). It never opens,
   writes, flushes, serializes, or waits for anything on the hot path. All slow work (JSON, disk,
   redaction, mirroring) belongs to one writer thread.
2. **One source of truth.** Decisions emit their record at the decision point, by the deciding
   code. Lenses are read-side filters; a record carries no lens field. `/tmp/bridge.log` is a
   console crash-catcher (banner, WARNING+ mirror, tracebacks), never a second event log.
3. **The viewer is disposable and read-only.** It cannot write to the stream, cannot touch the
   bridge, and its crash or closure has zero effect on the show. Closing the viewer window does
   **not** stop the bridge in either launch mode: in auto mode the menubar owns bridge lifecycle;
   in manual mode (`RBSS_BRIDGE_MANUAL=1`) the watcher's own loop owns it and exits only when the
   bridge process itself exits (no crash-restart backoff), never on the viewer closing. The watcher
   reopens a missing viewer.
4. **Secrets never reach the stream.** Key-name redaction (`token`/`secret`/`password`/`key`)
   applies to all structured payloads; sanitized surfaces (e.g. pack error categories) stay
   sanitized.
5. **No fake reconciliation.** No output path (laser MIDI, Enttec DMX, Govee cloud, Govee LAN,
   OS2L) has an acknowledgement channel, so the system never claims a fixture did something —
   PERFORMANCE states intent, the operator's eyes are the check, and OPERATOR reports only
   failures the code genuinely detects. Building hardware read-back is out of scope.

## The four lenses (fixed vocabulary)

One stream; a lens is a predicate over `(cat, lvl)`. Records may match several lenses.

| Lens | Predicate | Answers | Audience |
|---|---|---|---|
| **PERFORMANCE** | `cat` starts with `perf.` | "What *should* the rig be doing right now?" — authoritative intent; never discusses health | Brandon, eyes on the rig |
| **OPERATOR** | level ≥ WARNING, or `cat` starts with `health.` | "Is it working? What broke, what recovered?" — quiet when healthy | Brandon, mid-set |
| **SYSTEM** | `cat` starts with `sys.` or `health.`, or (legacy infra module AND level ≥ INFO)¹ | Threads, attach, queues, timing, connections | Brandon + agents |
| **MAX DEBUG** | everything captured | Forensic firehose | AI agents |

Intent (`perf.*`) covers at minimum: active-deck switches, drop detection + type, laser scene
decisions **and** executed selections, LED look + palette selections, autoloop arm/lock/clear,
scripted-track outcomes, SoundSwitch selection sends, manual overrides/blackouts, and a ≤2 s
heartbeat snapshot (deck, bpm, phrase, laser, led, palette, health summary).

Health (`health.*`) records are **edge-triggered transitions only** (fail → one record,
recover → one record), never per-failure spam.

**Structural noise protection:** only the `perf()` helper can reach PERFORMANCE and only
WARNING+/health can reach OPERATOR — a chatty or badly-logged subsystem can pollute MAX DEBUG
only. The old 50-INFO-lines-per-resolution failure mode is impossible by construction, not by
discipline.

¹ **Approved deviation, recorded during the W6 build (2026-07-04):** taken literally, the spine's
SYSTEM predicate had no level qualifier on the legacy-infra clause, which would let a DEBUG-level
record from a legacy module (e.g. `rb_memory`'s per-candidate spam, whose `src` is literally
`rb_memory`) also match SYSTEM — contradicting the noise guarantee above and W6's own required test
(a DEBUG record with `cat="rb_memory"` must route to DEBUG only). `bridge_view.lens_of()` gates the
legacy-infra branch on `levelno >= INFO`; every named SYSTEM-relevant legacy event (attach, RB gone,
drift, queue drops) is already INFO/WARNING/ERROR, or has migrated to an explicit `health.*` cat
that matches the first clause directly regardless of level. This is an implementation-side
clarification of an ambiguity in this contract, not a policy change: the intent ("legacy infra story
without DEBUG firehose noise") is unchanged.

## The record (schema intent)

One JSON object per line: `ts` (epoch), `mono`, `lvl`, `cat`, `msg`, `src` required; `deck`,
`beat`, `trace`, `data`, `exc` optional. A run opens with a schema-versioned header record and
closes (cleanly) with a footer carrying drop counts. Unknown fields and categories must be
tolerated by every reader.

**Trace-id propagation, verified against as-built code** (`state_manager.py:1820-1850`,
`filepath_resolver.py:367-396,556-573`): one event's chain (`TRACK_LOADED` → `FILEPATH_RESOLVED` →
`SCRIPTED_ARM`) does share one `trace` id, but not through one uniform mechanism — this contract
originally implied automatic propagation, which overstates it. Within the single-threaded event
drain, `bridge_log.event_scope()`'s contextvar carries the id automatically to any event enqueued
while handling another (e.g. `SCRIPTED_ARM`'s payload never sets `__trace_id` itself; it inherits
the ambient trace via `stamp_trace()`'s contextvar fallback). Across the filepath-resolver's
worker-thread hop, propagation is **explicit, by construction, not automatic**: `_on_track_loaded`
reads `ev.payload["__trace_id"]` off the dequeued `TRACK_LOADED` event and passes it as a
`trace_id=` keyword through `resolve_by_anlz`/`resolve_by_title`/`resolve_async`; each resolver
worker thread re-stamps `payload["__trace_id"]` before enqueuing `FILEPATH_RESOLVED`. Python
contextvars do not cross thread boundaries on their own, so this only holds because every call site
on that path explicitly threads `trace_id=` through — a future cross-thread hop that omits this
would silently start a new trace id for that leg, not an error, just a broken chain.

## Operator experience contract (`bridge-view`)

- Default screen shows, with **zero keys pressed**: a sticky current-state header (from the
  heartbeat), the PERFORMANCE feed, and an OPERATOR strip that is green/"all quiet" when healthy.
  The heartbeat record itself feeds the header only — it does not scroll through the feed
  (rule 1: a steady show is a still screen); it remains in MAX DEBUG.
- **Alerts latch.** A WARNING/ERROR rings the bell once and stays visibly latched (with the
  problem text) until the condition clears or the operator acknowledges. Nothing important is
  ever conveyed by a transient effect alone; nothing important can scroll away.
- **ADHD-first readability rules are acceptance criteria, not style:** the screen is still when
  the show is steady (motion = meaning); current state lives in fixed screen positions; one fact
  per line in aligned columns, no wrapping; plumbing dim, payload bright; a fixed color vocabulary
  where **red only ever means broken**; plain words (`laser`, `led`), never codes (`[LX]`,
  `[RBMEM]`); problem ages shown relative ("2m ago"); newest line statically marked.
- Header shows stream staleness (heartbeat guarantees a fresh record ≤2 s from a healthy bridge);
  a stalled stream is visibly flagged.
- One monitor window total, in both auto and manual launch modes.

## Files

Per-run file `bridge-YYYYMMDD-HHMMSS.jsonl` + `current.jsonl` symlink; newest 20 runs kept. Log
dir resolves as `$RBSS_RUNTIME_DIR/logs/` when that env var is set (the parked USB launcher's
relocation knob — dormant until that project resumes), else `~/Library/Logs/rb_ss_bridge/`. The
`/tmp/bridge-events.jsonl` convenience symlink exists only in the default case.

## Extension rule (per new feature)

No lens, viewer, schema, or config work — categories route themselves. Three questions: decides
what the rig does → one `perf(...)` at the commit point; can fail/recover → one `health(...)`
transition pair; everything else → ordinary stdlib `log.*` (which remains the normal API for all
code). Every new emit site inherits the hot-path rule (no blocking I/O, no per-frame INFO).

## What this system does not promise

Hardware/fixture state confirmation (no read-back exists); always-on DEBUG capture (DEBUG is
opt-in via `BRIDGE_DEBUG` / `BRIDGE_LOG_LEVELS`, the only two logging env vars); event streams
for non-bridge processes (Stream Deck script, pad tools, menubar — their actions appear only at
the bridge boundary as commands/overrides); durability of guest-Mac diaries past the USB "End
Set" wipe (deliberate no-trace; export-to-stick is the parked AWR-122's flow).
