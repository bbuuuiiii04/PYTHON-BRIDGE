---
doc_status: historical-evidence
truth_level: read-only-memory-research-notebook
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: historical read-only process-memory investigation; not required by static exporter/player; hardware-unvalidated
---

# SoundSwitch Memory Discovery — Notebook

> **Historical notebook.** The final bounded exporter/player does not depend on
> SoundSwitch process memory: `.ssfile`, Venue, catalog, TrackMap, Static Look,
> and learned MIDI-map bytes are sufficient after save. Do not revive memory
> probing as an exporter dependency. Current authority is
> `soundswitch_re_closure_report.md`.

Running notebook for the PR-F memory-read investigation (see
`/Users/bbui/.claude/plans/ss-memory-discovery.md`). Read-only,
`mach_vm_read_overwrite` only. Probe tool: `tools/ss_memory_probe.py`.

---

## Session 1 — 2026-05-21

### Environment snapshot

| item | value |
|---|---|
| host | macOS 15.3.1 (Darwin 24.3.0), arm64 |
| SIP | enabled |
| passwordless sudo | no |
| SS version | 2.10.3 (2.10.3.0) |
| SS PID at probe time | 71767 |
| SS Load Address | `0x1007c8000` |
| SS arch in use | arm64 (host matches) |
| Qt | 6.5.3 |
| RB version | 7 (PID 14381 during probe) |
| bridge state during probe | stopped (manual session killed, watcher LaunchAgent unloaded) |

### Phase 0 — Tooling setup

**0.1 — SS code signature** (`codesign -dvvv --entitlements -`):

- Universal binary (x86_64 + arm64), PIE, hardened runtime (`flags=0x10000(runtime)`)
- TeamIdentifier: `SKE5HH5VKW` (ArKaos SA, Developer ID)
- Entitlements observed:
  - `com.apple.security.cs.allow-unsigned-executable-memory = true`
  - `com.apple.security.device.audio-input = true`
- Entitlements **not** present (relevant ones grepped):
  - `com.apple.security.get-task-allow` — **MISSING**
  - `com.apple.security.cs.debugger`
  - `com.apple.security.cs.disable-library-validation`

**Comparison — Rekordbox** (`/Applications/rekordbox 7/rekordbox.app`):

- `com.apple.security.cs.disable-library-validation = true`
- `com.apple.security.get-task-allow = true` ✅

This is the documented basis on which `rb_memory.py` reads RB without root
(see its module docstring lines 6–8). SS has no equivalent entitlement.

**0.2 — SS linked libraries** (`otool -L`, abbreviated):

- Qt 6.5.3: `QtCore`, `QtNetwork`, `QtSql`, `QtXml`, `QtMultimedia`,
  `QtMultimediaWidgets`, `QtOpenGL`, `QtOpenGLWidgets`, `QtQuick`,
  `QtQuickControls2`, `QtQuickWidgets`, `QtQml`, `QtQmlModels`,
  `QtSvgWidgets`
- SS-specific: `librtmidi.5`, `libdfu`, `libftd2xx` (FTDI DMX),
  `libtag.1` (TagLib for ID3), `libhuestream.2` (Philips Hue), `libQtZeroConf`,
  `libavcodec/avdevice/avfilter/avformat/avutil/swresample/swscale.58–7`
  (FFmpeg)
- Crypto: `libssl.1.1`, `libcrypto.1.1`

Implications:

- Qt 6 → autoloop state likely lives in QObject hierarchies under MALLOC heap.
  `Q_GLOBAL_STATIC` singletons would sit in the main `__DATA` segment at
  static-but-PIE-relocated offsets.
- TagLib presence explains how SS reads track metadata; not relevant to
  current-look state.

**0.3 — SS layout via `vmmap 71767`**:

Critical segments:

| segment | range | size | perms | notes |
|---|---|---|---|---|
| `__TEXT` (main) | `0x1007c8000–0x101520000` | 13.3 MB | r-x/r-x | mach-o magic expected at start |
| `__DATA_CONST` (main) | `0x101520000–0x1015bc000` | 624K | r--/rw- | const data, GOT |
| `__DATA` (main) | `0x1015bc000–0x1015d0000` | 80K | rw-/rw- | `Q_GLOBAL_STATIC` slot candidates |
| `__DATA` (main, PRV) | `0x1015d0000–0x101610000` | 256K | rw- | private/dirty data |
| `__LINKEDIT` | `0x101610000–0x101da4000` | 7760K | r--/r-- | symtab/strings |

Heap landscape (from `vmmap --summary`):

- `MALLOC_MEDIUM`: 768 MB virtual, ~1.4 MB resident — likely main Qt heap
- `MALLOC_LARGE`: 32 MB virtual, mostly swapped
- 20 MALLOC zones, 18 guard pages
- Physical footprint: 501 MB

PIE means `0x1007c8000` (the load address) is the ASLR-relocated base of
`__TEXT`. The static link-time base is some lower value; the slide is
`current_load - static_base`. A discovery offset table needs to be expressed
as `(__DATA + N)` rather than absolute addresses, mirroring `rb_offsets.py`.

**0.4 — `ss_memory_probe.py` skeleton**: created at
`tools/ss_memory_probe.py`. Subcommands: `regions`, `smoketest`, `find-string`,
`read`, `walk`, `watch`. Uses `mach_vm_read_overwrite` via ctypes against
`libSystem.B.dylib`. No `vm_write`, no `task_*` calls beyond `task_for_pid`.

**0.5 — `vm_read` smoke test**:

```
$ python3 tools/ss_memory_probe.py smoketest 71767
[smoketest] pid=71767
[smoketest] FAIL: task_for_pid(71767) failed: KERN_FAILURE.
  On macOS, this typically requires the target to have
  com.apple.security.get-task-allow=true, or the caller to run as root,
  or the caller to be signed with com.apple.security.cs.debugger.
exit=2
```

`task_for_pid` returned `KERN_FAILURE` (kr=5). This is the plan's named
Phase 0 stop-condition: "if vm_read returns ... for all SS regions, we cannot
read SS memory at all." It triggered at the `task_for_pid` step before any
`vm_read` call, but the practical effect is the same.

### Phase 0 — Decision point

**Confirmed (verified)**:

- SS lacks `get-task-allow`; bridge's user-space `task_for_pid` cannot acquire
  its task port (kr=5).
- SS layout itself is observable via `vmmap` (Apple-privileged tool) — we
  have the segment table even without read access.
- The probe tool is functional; it will work the moment a privileged caller
  obtains the task port.

**Assumed (not yet tested)**:

- Running the probe under `sudo` would succeed. `task_for_pid` from a root
  process bypasses the `get-task-allow` check. Not tested because no
  passwordless sudo is configured and I haven't asked the user for the
  interactive password.
- An `lldb` script could attach (lldb is Apple-signed with debugger
  entitlement) and run `memory read` / `expression` commands without
  per-session sudo. Not tested.
- A Python wrapper signed ad-hoc with `com.apple.security.cs.debugger` may
  work, but that entitlement is restricted to Apple-distributed binaries on
  hardened-runtime; ad-hoc signing usually won't grant it.

**Unknown**:

- Whether SS's hardened runtime would refuse a task port even to a root
  caller in some edge configuration (unlikely on stock macOS 15.3).
- Whether `lldb`'s ScriptingBridge can deliver per-deck reads at the
  sustained rates Phase 4 requires (200 Hz target).

### Open options

A. **`sudo python3 tools/ss_memory_probe.py …`** — simplest. Probe sessions
   need interactive password each time. Acceptable for discovery; production
   PR-F would still need a non-sudo answer.

B. **lldb-script probe** — Apple-signed binary, no sudo. Wrap the same
   subcommands in an lldb python script. Higher engineering cost, but
   sustainable.

C. **Sign a wrapper executable with `com.apple.security.cs.debugger`** —
   requires Developer ID and Apple-blessed entitlement. Almost certainly
   not workable for this project.

D. **Pivot to PR D+E (Art-Net acknowledgment path)** — abandon SS memory
   reading entirely. Plan section "Decision + (if go) PR-F seed" names this
   as the alternative. Cost is well-known; lands faster.

E. **Hybrid: investigate via sudo, deploy via Art-Net** — use sudo-driven
   discovery to **prove or disprove** that SS has a stable "current
   autoloop" field. If yes, build production around lldb or a signed helper;
   if no, the discovery itself is the green light for D+E.

### Recommendation (for user)

Option **E** (hybrid). The high-risk question in PR-F isn't the
authentication mechanism — it's whether SS exposes "current autoloop" in a
single readable field at all. That question is best answered by Phases 1–2,
which only need a few short probe sessions. Each session needs sudo once.
After Phase 2, we know whether to invest in a production access path
(option B) or pivot (option D) — with evidence, not speculation.

### Phase 0 — Option B test (lldb-driven probe)

Hypothesis: `/usr/bin/lldb` is Apple-signed (`Authority=Software Signing`)
and should be able to use `task_for_pid` against SS without sudo, since
Apple-signed system binaries are granted the debugger privilege by the
kernel.

Test:

```
$ /usr/bin/lldb --batch \
    -o "process attach --pid 71767 --continue" \
    -o "memory read --count 64 --force 0x1007c8000" \
    -o "process detach" -o "quit"
(lldb) process attach --pid 71767 --continue
error: attach failed: attach failed (Not allowed to attach to process. ...)
```

**Confirmed dead by evidence.** The premise of option B was wrong. Apple's
policy on SIP-enabled macOS:

- A target with hardened runtime AND no `com.apple.security.get-task-allow`
  cannot be debugged by a non-root caller, regardless of how the caller is
  signed.
- Apple-signed lldb gets `task_for_pid` against most user processes, BUT
  hardened-runtime targets without `get-task-allow` are explicitly excluded
  from debugger attach. This is the protection Apple introduced to stop
  malware spying on hardened apps.

SS satisfies both blocking conditions (`flags=0x10000(runtime)`, no
`get-task-allow` — both confirmed in this notebook).

The access-mechanism question collapses to a single axis:

- Caller is root → works (sudo, regardless of caller signature)
- Caller is non-root → blocked (regardless of caller signature)

There is no non-root path on stock macOS 15.x without disabling SIP or
patching SS's binary (both non-starters).

### Phase 0 — Option C test (signed debugger wrapper)

Attempted to ad-hoc sign a copied python with `com.apple.security.cs.debugger`
+ hardened runtime + supporting entitlements, to see if taskgated would
honor the entitlement for an ad-hoc signature.

Steps:

1. Copied `/opt/homebrew/Cellar/python@3.14/3.14.3_1/.../bin/python3.14` to
   `tools/signed_python/python3_dbg`.
2. Wrote `tools/signed_python/debugger.entitlements` with:
   - `com.apple.security.cs.debugger = true`
   - `com.apple.security.cs.disable-library-validation = true`
   - `com.apple.security.cs.allow-unsigned-executable-memory = true`
   - `com.apple.security.cs.allow-jit = true`
   - `com.apple.security.cs.allow-dyld-environment-variables = true`
   - `com.apple.security.get-task-allow = true`
3. `codesign --force -s - --entitlements debugger.entitlements --options runtime python3_dbg`
   — succeeded (`flags=0x10002(adhoc,runtime)`, all entitlements embedded).
4. `python3_dbg -c "..."` runs fine; ctypes imports.
5. `tools/signed_python/python3_dbg tools/ss_memory_probe.py smoketest 71767`
   → still `KERN_FAILURE` on `task_for_pid`.

Available signing identities on this machine: `security find-identity -v -p
codesigning` returns `0 valid identities found`. No Apple Developer ID
certificate, no provisioning profile. `DevToolsSecurity -status` reports
developer mode disabled (would need sudo to enable, and even then doesn't
unlock cs.debugger for ad-hoc).

**Confirmed dead by evidence**: `taskgated` rejects ad-hoc signatures for
`cs.debugger`. Apple's docs explicitly require a Developer ID or Apple
signature; this test verifies it on 15.3 specifically.

To revive option C would require: (a) Apple Developer Program enrollment
($99/yr), (b) a Developer ID Application certificate, (c) signing the
wrapper with that cert plus the entitlements file, (d) likely a notarization
exception or Apple-granted provisioning profile for `cs.debugger`. Out of
scope for this investigation.

### Artifacts produced this session

- `tools/ss_memory_probe.py` — read-only probe CLI
- `tools/signed_python/python3_dbg` — ad-hoc-signed python binary (failed test)
- `tools/signed_python/debugger.entitlements` — entitlements template
  (kept for documentation / future Developer ID use)
- `docs/research/soundswitch/history/ss_memory_discovery.md` — this notebook

### Phase 0 — Option A/E test (sudo)

After B and C were confirmed dead, the remaining hypothesis was that root
would bypass the entitlement check (option A — straight sudo, the basis of
hybrid E). This was based on the conventional pre-Big-Sur understanding
that root + `task_for_pid` always succeeds. **It does not.**

Test 1 — sudo + homebrew python (ad-hoc signed, no entitlements):

```
$ sudo python3 tools/ss_memory_probe.py smoketest 71767
[smoketest] FAIL: task_for_pid(71767) failed: KERN_FAILURE.
```

Verified euid:

```
$ sudo python3 -c "import os; print('euid=', os.geteuid()); print('python=', __import__('sys').executable)"
euid= 0
python= /opt/homebrew/opt/python@3.14/bin/python3.14
```

So sudo did escalate, and the homebrew python at `/opt/homebrew/opt/python@3.14/bin/python3.14`
was running as root, and `task_for_pid` still returned `KERN_FAILURE`.

Test 2 — sudo + ad-hoc cs.debugger-entitled python (the C-test binary):

```
$ sudo tools/signed_python/python3_dbg tools/ss_memory_probe.py smoketest 71767
[smoketest] FAIL: task_for_pid(71767) failed: KERN_FAILURE.
```

Same result. **Confirmed dead by evidence.**

### Phase 0 — Decision: NO-GO

#### Combined evidence table

| caller binary | signature | euid | task_for_pid(SS) |
|---|---|---|---|
| /opt/homebrew/.../python3.14 | ad-hoc | user | KERN_FAILURE |
| /opt/homebrew/.../python3.14 | ad-hoc | root | KERN_FAILURE |
| tools/signed_python/python3_dbg | ad-hoc + runtime + cs.debugger | user | KERN_FAILURE |
| tools/signed_python/python3_dbg | ad-hoc + runtime + cs.debugger | root | KERN_FAILURE |
| /usr/bin/lldb | Apple Software Signing | user | "Not allowed to attach" |

#### Root cause

On macOS 15.3 with SIP enabled, AMFI (Apple Mobile File Integrity, kernel)
enforces this rule for `task_for_pid` against hardened-runtime targets:

> The target must have `com.apple.security.get-task-allow=true`,
> OR the caller must be signed by a trusted authority (Apple or Developer
> ID) with `com.apple.security.cs.debugger=true`.

Root-vs-user is **not part of the check**. Ad-hoc signatures fail the
"trusted authority" half regardless of which entitlements they embed.

SS has hardened runtime (`flags=0x10000(runtime)`) and no `get-task-allow`
— confirmed by `codesign -d --entitlements -` earlier in this notebook.

#### Unblocking would require

| approach | cost / risk | recommendation |
|---|---|---|
| `csrutil enable --without debug` (recovery-mode boot) | reduces SIP slightly system-wide; permits debugger attach to hardened apps. Survives reboots. One-time recovery-boot setup. | **Plausible** if user wants to keep the door open for SS introspection. |
| `csrutil disable` (full SIP off) | larger system-wide trade-off; gives up filesystem and kernel-extension protections too | Not recommended just for this. |
| Re-sign SS with `get-task-allow` patched into entitlements | breaks ArKaos's notarized signature; SS will refuse to launch until re-signed each session, breaks on every SS update | Not recommended. Fragile and high-maintenance. |
| Acquire Apple Developer ID + sign a wrapper with `cs.debugger` | $99/yr, plus Apple-blessed provisioning profile for `cs.debugger` (not standard) | Not realistic for this project. |
| Pivot to PR D+E (Art-Net acknowledgment path) | abandon SS memory reading; production-realistic path; no system changes; explicitly named in the plan as the alternative | **Recommended.** |

#### Conclusion

PR-F is not viable on this machine without system-level configuration
changes (recovery-mode SIP partial-disable). The plan named this as the
go/no-go decision point and instructed to pivot rather than push through.

**Recommendation: pivot to PR D+E.**

If the user wants to keep memory-reading on the table for a future SS
version (one that adds `get-task-allow`, or if `csrutil enable --without
debug` becomes acceptable), the probe tool and methodology in this
notebook are reusable. Nothing in this investigation is wasted; the
specific blocker is documented and the path back in is clear.

### Session 2 — 2026-05-22

#### External-observation reconnaissance

After Phase 0 declared no-go on memory reads, ran a recon batch on
externally-observable SS state channels. Key findings:

| channel | finding |
|---|---|
| `lsof -p 71767` | SS binds UDP 6454 (Art-Net standard port — confirms PR D+E viability) plus two random TCP listeners (61795, 41401, likely OS2L + Bonjour) |
| Info.plist | minimal; no URL schemes, no API hints |
| `~/Library/Application Support/Onesixone/Soundswitch/Logs/` | **AppLog.txt rotating at 10 MB; SS writes live state changes here** |
| `~/Music/SoundSwitch/default.ssproj/` | project bundle, last modified at SS launch only |
| CGWindowList | pyobjc unavailable in stock pythons; deferred |
| Bridge OS2L code | not inspected this session |

**Major discovery: SS log contains real-time state transitions.**

Sample lines:

```
[2026-05-21 22:06:48.009] [SoundSwitch] [info] [AutoLoopTrackPriData.h:242] Deck 0 running autoloop bank -1, index 0
[2026-05-21 22:04:19.660] [SoundSwitch] [info] [SoundSwitchDoc.cpp:1366] Deck 0 running scripted track {A5B0ACD1-D426-4BDB-9C8C-D05EA084F9CF}
```

Coverage in one 10-MB rotated log:
- 31 × `AutoLoopTrackPriData.h:242` — autoloop bank/index changes (fires on change only)
- 2  × `SoundSwitchDoc.cpp:1366` — scripted track UUID assignments
- 2  × `SoundSwitchDoc.cpp:1340` — track file resolution
- 985 × `MidiClock.cpp:438` — MTC clock retry warnings (noise)

This is the "current autoloop" answer that PR-F was trying to extract from
memory. **No SIP, no AMFI, no entitlements** — just tail a file in the
user's own directory. Open as PR-G candidate.

#### Phase 0 — Option 2 test (re-sign SS copy with `get-task-allow`)

Hypothesis: AMFI's `get-task-allow` check only requires the entitlement
value on the target, not signature trust on the target. Apple's docs are
ambiguous; tested empirically.

Steps:
1. APFS-cloned `/Applications/SoundSwitch.app` → `/tmp/SoundSwitch-probe.app`
   (CoW, near-zero extra disk).
2. Stripped 101 dylibs + 46 frameworks + main + crashpad_handler
   signatures.
3. Re-signed inside-out: dylibs → framework binaries → frameworks →
   crashpad → main (with entitlements) → app bundle (with entitlements).
   Entitlements file at `/tmp/ss-probe.entitlements` included
   `get-task-allow=true` + `cs.disable-library-validation=true` plus SS's
   original entitlement set.
4. `codesign --verify`: "valid on disk", satisfies Designated Requirement.
5. `codesign -d --entitlements -` against the running process confirmed
   `get-task-allow=true` was loaded (flags `0x10002(adhoc,runtime)`).
6. Quit original SS, launched re-signed copy as PID 20884.
7. Ran `python3 tools/ss_memory_probe.py smoketest 20884` → `KERN_FAILURE`.
8. Ran `sudo python3 tools/ss_memory_probe.py smoketest 20884` → `KERN_FAILURE`.

**Confirmed dead by evidence.** AMFI requires BOTH:
1. `get-task-allow=true` entitlement on target ✅
2. Trusted-authority signature on target (Apple or Developer ID) ❌
   (ad-hoc fails)

Re-signing with ad-hoc doesn't satisfy AMFI's trust check, regardless of
the entitlement value. This is the *same* trust-anchor wall that blocked
option C (caller-side ad-hoc cs.debugger).

The user's "Approach 2" writeup overlooked this. The writeup recommended
Approach 1 (csrutil --without debug) — that recommendation still stands
and is the only viable memory-access path. Approach 1 was not tested this
session because it requires recovery-mode boot, which is user-driven.

Cleanup: re-signed copy and entitlements file removed from /tmp. Original
SS relaunched (PID 21251 at session close). Bridge remained stopped
throughout.

### Updated decision matrix

| approach | tested | result |
|---|---|---|
| ad-hoc python, user | ✅ | KERN_FAILURE |
| ad-hoc python, root | ✅ | KERN_FAILURE |
| ad-hoc cs.debugger python, user | ✅ | KERN_FAILURE |
| ad-hoc cs.debugger python, root | ✅ | KERN_FAILURE |
| Apple lldb | ✅ | "Not allowed to attach" |
| re-signed SS with get-task-allow, user | ✅ | KERN_FAILURE |
| re-signed SS with get-task-allow, root | ✅ | KERN_FAILURE |
| `csrutil enable --without debug` (recovery-boot) | not tested | unknown — requires user action |
| **log-tail (PR-G candidate)** | discovered | **works, no system changes** |
| Art-Net sniff (PR D+E) | not implemented | viable, port 6454 confirmed |

### Session 2 — PR-G (log-tail) validation

User restarted bridge and did a live test session at ~00:48–00:53 on
2026-05-22 (loaded 2 scripted tracks, played autoloop transitions). Test
event capture:

**Scripted track loads** (`SoundSwitchDoc.cpp:1340` lookup + `:1366`
assignment, fire as paired entries microseconds apart, both decks
simultaneously):

```
00:48:47.184 [info] [SoundSwitchDoc.cpp:1340] track file found: .../{74044FA4-...}.ssfile
00:48:47.185 [info] [SoundSwitchDoc.cpp:1366] Deck 0 running scripted track {74044FA4-...}
00:48:47.191 [info] [SoundSwitchDoc.cpp:1340] track file found: .../{74044FA4-...}.ssfile
00:48:47.191 [info] [SoundSwitchDoc.cpp:1366] Deck 1 running scripted track {74044FA4-...}
00:49:46.194 [info] [SoundSwitchDoc.cpp:1366] Deck 0 running scripted track {AD786435-...}
00:49:46.202 [info] [SoundSwitchDoc.cpp:1366] Deck 1 running scripted track {AD786435-...}
00:51:16.288 [info] [SoundSwitchDoc.cpp:1366] Deck 0 running scripted track {AD786435-...}
00:51:16.295 [info] [SoundSwitchDoc.cpp:1366] Deck 1 running scripted track {AD786435-...}
```

**Autoloop changes** (`AutoLoopTrackPriData.h:242`, 22 entries in the
post-rotation window, all `bank=-1`, both decks):

```
00:51:29.500 Deck 0 running autoloop bank -1, index 1
00:51:29.510 Deck 0 running autoloop bank -1, index 6
... [22 changes total over 104s]
00:53:12.941 Deck 1 running autoloop bank -1, index 5
```

**Log rotation observed live during the test** (`AppLog.txt` → `AppLog.1.txt`
between 00:51:16 and 00:51:29 when the 10-MB threshold hit). Without
inode-watch rotation handling, an implementation would miss every event
straddling rotation.

**PR-G unknowns resolved:**

| # | question | answer |
|---|---|---|
| 1 | `bank=-1` meaning | always -1 in observed data; likely "current/default loop bank" sentinel |
| 2 | index → look name | parse `default.ssproj` (already done in `filepath_resolver.py`) |
| 3 | flush latency | <10 ms (back-to-back writes captured at 8 ms apart) |
| 4 | full coverage | yes — both scripted and autoloop events fire, paired across decks |
| 5 | rotation handling | required (observed live); standard inode-watch tail is sufficient |

**Decision: PR-G is the recommended replacement for PR-F.** No SIP changes,
no AMFI work, no Art-Net decoding. Implementation surface is a file watcher
+ two regex patterns + log-rotation handling + `.ssproj` index resolver.

### Artifacts produced this session (final)

- `tools/ss_memory_probe.py` — read-only probe CLI, syntax-clean,
  functional under root once AMFI permits access
- `tools/signed_python/python3_dbg` — ad-hoc-signed python with hardened
  runtime + cs.debugger (kept for documentation)
- `tools/signed_python/debugger.entitlements` — entitlements template
  (kept; reusable if Developer ID is ever acquired)
- `docs/research/soundswitch/history/ss_memory_discovery.md` — this notebook

### Not done this session

- No Phase 1 anchor-string work (blocked by AMFI; would have been the
  next step if any caller could `task_for_pid`).
- No Phase 2/3/4 work.
- No commits. The probe tool and notebook are uncommitted; the user can
  decide whether to keep or remove them.

### Decision (2026-05-22, session 2 close)

PR-G alone is insufficient for the bridge's full requirement. The real
need is not just "what is SS currently playing" — it's **proactive
gating** of SS's autonomous mid-set rotation into drop autoloops at
musically wrong moments. PR-G is reactive (sees rotation after commit,
~8–10 ms log flush + ~30–40 ms total round-trip to correct). Proactive
gating requires reading SS's "next queued look" state *before* SS
commits, which means memory access.

**User chose Path A**: recovery-boot + `csrutil enable --without debug`.
This unlocks AMFI for hardened-runtime targets system-wide while
preserving all other SIP protections. After the boot:

- The probe tool (`tools/ss_memory_probe.py`) works unchanged
- Phases 1–4 of the original plan resume
- PR-G is kept as the parallel signal for know/ack (cheap, no system
  cost) — production design probably uses memory for proactive gating,
  log-tail for confirmation

Next session work after the reboot:
1. Smoketest under new SIP config → confirm `task_for_pid` returns 0
2. Phase 1 anchor-string sweep (NEON STUTTER, BLUE FANNING, look UUIDs)
3. Phase 2 memory diff to locate "current autoloop" + "next queued"
   fields per deck
4. Phase 3 pointer-chain back to a stable `__DATA`-relative anchor
5. Phase 4 stability validation across SS restarts + load
6. PR-F seed: `docs/data/offsets-ss-macos.yaml` + skeleton `ss_memory.py`

---

## Session 3 — 2026-05-22 (post-reboot)

### Environment

| item | value |
|---|---|
| SIP | Custom Configuration — `Debugging Restrictions: disabled`, all other protections enabled |
| SS PID at probe time | 3060 (after one mid-session crash of PID 1984 — see below) |
| bridge state during probe | menubar running, watcher state unverified — should be confirmed stopped before any further probing |

### Phase 0 — Smoketest re-run under new SIP config

Tested four caller variants against the same SS PID. The signal we
needed was a change in `task_for_pid` outcome vs. session 1.

| caller | session 1 (pre-reboot) | session 3 (post-reboot) |
|---|---|---|
| ad-hoc python, user | KERN_FAILURE | KERN_FAILURE (unchanged) |
| ad-hoc cs.debugger python, user | KERN_FAILURE | KERN_FAILURE (unchanged) |
| Apple lldb | "Not allowed to attach" | "tried to attach to process already being debugged" |
| sudo + ad-hoc python | KERN_FAILURE | **task_for_pid=0, port=0xe03, vm_read OK** |

Successful sudo run:

```
[smoketest] pid=3060
[smoketest] task_for_pid -> port=0xe03
[smoketest] reading 64B from __TEXT /Applications/SoundSwitch.app/Contents/MacOS/SoundSwitch @ 0x104194000
[smoketest] OK: read 64 bytes
[smoketest] head: cf fa ed fe 0c 00 00 01 00 00 00 00 02 00 00 00 …
[smoketest] confirmed mach-o magic (MH_MAGIC_64) at region head
```

### What the new SIP config did and didn't change

- **Did change**: AMFI's "hardened-runtime target without `get-task-allow`
  cannot be attached" rule is relaxed. lldb's error shifted from
  policy-deny ("Not allowed to attach") to lock-contention ("already
  being debugged" — crashpad's exception handler holds the slot).
  sudo + ad-hoc python now succeeds where it KERN_FAILED before.
- **Did not change**: non-root callers still cannot call
  `task_for_pid` against SS, even with `cs.debugger` entitlement on
  an ad-hoc signature. `csrutil enable --without debug` relaxes the
  hardened-runtime check; it does not grant ad-hoc binaries the
  trust authority that taskgated requires for cs.debugger.

### Mid-session SS crash (PID 1984)

While testing the lldb attach path on PID 1984, SS exited. A new
crashpad orphan (PID 2000) appeared. Causal link to lldb attach is
**suspected, not proven**; no minidump inspected yet. After SS was
relaunched (PID 3060), all non-attach probes (user, sudo, signed) ran
cleanly without further crashes. Conclusion for the playbook: lldb
attach is unnecessary for production access and should be dropped
from the probe-tool playbook to eliminate this crash vector.

### Production-access implications

Memory reads require root. The bridge today runs as the user, not
root. Three production patterns to choose between (defer until after
Phase 1 confirms there is something worth reading):

1. **Bridge-as-root** — simplest; LaunchAgent → LaunchDaemon migration.
   Larger blast radius if the bridge has a bug. Restart procedure
   changes (sudo required for menubar toggle).
2. **Root helper** — small daemon runs as root, exposes a unix socket
   or shared-memory mirror with just the resolved `(deck, current,
   next)` tuple. Bridge stays user-mode. Mirrors the
   `rb_shm_plugin.dylib` pattern that already works.
3. **Developer ID + cs.debugger** — out of scope (see session 1).

### Phase 0 — Decision: GO

`task_for_pid` works under sudo; `vm_read` works against `__TEXT`;
the probe tool is operational. Phase 1 (anchor-string sweep) is
unblocked.

### Next session work

1. ✅ Smoketest under new SIP config (done — sudo path works)
2. Phase 1 anchor-string sweep — `find-string` for `NEON STUTTER`,
   `BLUE FANNING`, `BREAKDOWN`, and 2–3 look UUIDs. Record region,
   offset, and stability across SS restart.
3. Phase 2 memory diff for "current autoloop" + "next queued" fields
4. Phase 3 pointer-chain to `__DATA`-relative anchor
5. Phase 4 stability validation
6. PR-F seed + production-access pattern decision

---

## Session 3 — Phase 1 anchor sweep results

Ran 10 probes via `sudo bash /tmp/ss_phase1_probe.sh` against SS PID 3060
(SS __TEXT base 0x104194000). Total wall time ~18 min. SS survived all
probes. Bridge stopped throughout. Full results in
`/tmp/ss_phase1_results.txt`.

### Hit counts

| anchor | UTF-16LE | UTF-8 |
|---|---|---|
| `NEON STUTTER` | 2 | 2 |
| `BLUE FANNING` | 6 | 6 |
| `BREAKDOWN` | 11 (capped at 20; likely more) | 2 |
| `{025C1DDF-...}` (real ssfile name) | **0** | **0** |
| `{02E3AA51-...}` (real ssfile name) | **0** | **0** |

### Key observations

1. **Autoloop look names live in heap as Qt 6 QStrings.** Both UTF-16
   and UTF-8 representations coexist. The contexts reveal the Qt
   QArrayData header clearly — refcount + flags + length prefix before
   the character bytes:
   ```
   01 00 00 00 00 00 00 00   ← refcount (1)
   20 00 00 00 0d 00 00 00   ← flags(0x20) + length(0x0d = 13 chars)
   4e 00 45 00 4f 00 4e 00   ← "N\0E\0O\0N\0"
   ...
   ```
   This is `QString::DataPointer → QArrayData` layout. SS holds these
   in `MALLOC_NANO` (UTF-16, refcounted) and `MALLOC_TINY` (UTF-8,
   simpler layout — looks like preformatted name table).

2. **Multiple copies per look name.** "BLUE FANNING" appears 6 times
   in each encoding — implies SS does not COW-share QStrings for the
   look catalog. Each "view" of the catalog holds its own copy.

3. **Variant look names discovered:** `BLUE FANNING`, `BLUE FANNING 2`,
   `BREAKDOWN`, `BREAKDOWN 1`, `BREAKDOWN 2`, `BREAKDOWN CHILL`,
   `BREAKDOWN CHILL 2`, `BREAKDOWN CHILL 3`, `BREAKDOWN TURQOIS[E]`,
   etc. — the look catalog is larger than the 45 numbered SSAutoLoop
   files; the .ssfile may be a bank with multiple named looks inside.

4. **UUIDs are not stored as strings.** Both tested UUIDs returned
   zero hits in either encoding despite being real `.ssfile`
   filenames present in `~/Music/SoundSwitch/default.ssproj/`. This is
   the most actionable finding — it changes Phase 2's approach for
   scripted shows. Almost certainly SS parses UUID strings on load
   and stores them as `QUuid` (a 16-byte little-endian binary
   structure). The Phase 2 differ must include a binary-UUID scan
   path, not just string-pointer diffing.

5. **Heap zone addresses are deterministic-looking.** Both hit zones
   are `MALLOC_NANO DefaultMallocZone_0x106554000` and `MALLOC_TINY
   MallocHelperZone_0x105a58000`. These zone-base addresses are at
   fixed offsets from SS __TEXT base (0x106554000 - 0x104194000 =
   0x23C0000). Either ASLR-slid in lockstep or pinned by malloc zone
   bootstrap. Promising for Phase 3 anchoring.

### Phase 1 decision: GO with Branch C (mixed)

The plan's branch decision tree:

- **Autoloop tracking → Branch B** (integer-based). AppLog says
  `bank=-1, index=N`; SS's internal identifier is the int pair, not
  the name string. The name QStrings we found are catalog/UI data,
  not active state.
- **Scripted-show tracking → Branch C** (UUID as binary). The
  16-byte QUuid form is the likely identifier; must be searched as
  binary, not as text.

### What this means for Phase 2 (revisions)

The original Phase 2 plan assumed string-pointer diffing would
suffice. Updated approach:

1. **Add `find-binary` subcommand to probe tool** — scan for arbitrary
   byte sequences. Use to search for the 16-byte little-endian QUuid
   form of `{025C1DDF-2CDC-4E54-BD8C-156B90DD8247}` =
   `DF 1D 5C 02 DC 2C 54 4E BD 8C 15 6B 90 DD 82 47`.
   (Note: QUuid byte order in memory is implementation-defined;
   search both little-endian and big-endian variants.)
2. **Build an integer-pair differ** for the autoloop case. Scan for
   aligned `(int32 bank, int32 index)` pairs whose first int is
   0xFFFFFFFF (-1) and second is a small non-negative int. This
   pre-filter dramatically narrows the candidate set before applying
   the A1==A2, A1!=B membership tests.
3. **Reuse the QString catalog hits as anchors.** The 25+ heap
   addresses we now have for look names are useful targets for
   `walk-back` in Phase 3 — they'll lead us to the catalog-holder
   QObject, which is likely close to the active-state QObject in the
   QObject parent/child tree.

### Updated Phase 2 prerequisites

Before snapshot/diff work begins, build:

- `find-binary` subcommand in `tools/ss_memory_probe.py`
- `snapshot` and `diff` subcommands (per existing Phase 2 design)
- `tools/ss_os2l_poke.py` — standalone autoloop trigger via SS's
  OS2L TCP port (61795 from session 2 recon) — needed to drive
  deterministic state changes for the diff sequence

No SS-touching work in Phase 2 prep; all tool dev is local.

### Artifacts this Phase 1 segment

- `/tmp/ss_phase1_probe.sh` — batch probe script (kept; useful for
  re-running after SS restarts to validate offset stability)
- `/tmp/ss_phase1_results.txt` — raw probe output (~30 hits with
  context)
- This notebook section (Phase 1 results + Phase 2 revision)

### Phase 1 user clarification on naming

User correction during session 3: SS uses overlapping name spaces.
- `SoundSwitchAutoLoops.bin` (default catalog): unambiguous autoloop
  names like `RED // AG1`, `RAINBOW LAGGY`, `BLACKOUT`, `BLUE // AG1`,
  `WHITE // AG1`.
- `SoundSwitchAutoLoopsEx.bin` (extended catalog): `NEON`, `NEON
  STUTTER`, `BLUE FANNING`, `BLUE FANNING 2`, `CONVERGING`, etc. **These
  are also valid autoloops** (despite my initial mis-claim that they
  were attribute cues only).
- Names like `BREAKDOWN CHILL 3`, `BREAKDOWN TURQOIS[E]`, `BLUE
  FANNING 2` variant hits in scripted regions ARE scripted-show
  attribute cues — separate concern from autoloop tracking.
- Phase 1 results are valid as-is: NEON STUTTER and BLUE FANNING
  appear in heap as Qt 6 QStrings representing real autoloop catalog
  entries; the BREAKDOWN CHILL 3 hits are scripted-cue text on
  `.ssfile` timelines.

---

## Session 3 — Phase 2 attempt (collector v1)

### Setup

| item | value |
|---|---|
| SS PID at probe time | 15066 (restarted from prior session) |
| Bridge | running PID 16634 (manual session w/ extensive env flags) |
| Bridge watcher script | running PID 16612 (didn't spawn second bridge — coexisted) |
| SS mode | RANDOM autoloop selection (user toggled from SEQUENTIAL) |
| Track | unscripted, RB playing live (audio on, OK per user) |
| Collection duration | 180s |
| Configured interval | 500ms (target 360 polls) |

### Collector v1 results — bottlenecked

**Files produced** (in /tmp, root-owned):
- `ss_phase2_collector.py` — v1 collector (~12KB)
- `ss_phase2_analyze.py` — generic time-correlation analyzer
- `ss_phase2_meta.json` — run metadata
- `ss_phase2_applog.jsonl` — EMPTY (tailer failed; AppLog rotated
  mid-run from `AppLog.txt` → `AppLog.1.txt` at ~08:18 and tailer
  kept stale fd)
- `ss_phase2_deltas.jsonl` — 4.5 GB, 33M lines, 13M unique addrs

**Actual collection stats:**
- Completed polls: 5 (not 360). Each poll took ~36s.
- Slow polls: 5/5 (every one exceeded the 500ms interval).
- Rotations during window: 34 (recovered post-hoc from rotated logs).
- Per-deck balance: deck 0 = 17 rotations, deck 1 = 17 rotations.
- Distinct indices seen (random mode): `{0, 1, 2, 3, 4, 5, 6, 7, 11, 16,
  32, 38, 39, 42, 43, 44}` — 16 distinct values, healthy diversity.

**Bottleneck breakdown** (~36s per poll):
- 71 MALLOC writable regions × 32MB cap = 484MB virtual to read each poll
- JSON encoding + write + flush for every delta (5.4M deltas per poll
  pair = bulk of the time)
- No inode-watch on AppLog (silent failure when rotated)

### Recovery work performed

Wrote `/tmp/ss_phase2_recover_applog.py`. Parsed `AppLog.txt`,
`AppLog.1.txt`, `AppLog.2.txt` for events in the 08:16:53–08:19:53
run window. Recovered all 34 rotations → `ss_phase2_applog_recovered.jsonl`.

Wrote `/tmp/ss_phase2_filter.py` — streaming pre-filter on the 4.5GB
deltas file. Two-pass: count changes per addr, then keep only addrs
with change_count in `[5, 80]`. Output: `ss_phase2_deltas_filtered.jsonl`
(1.8M lines, 359K addrs).

**Change-count histogram** (across 13M unique addrs):
- count=1: 1.2M addrs (one-shot allocations)
- count=2: 7.2M addrs
- count=3-5: 4.7M addrs
- count≥6: 0 addrs (impossible — max is 5 with 5 polls = 4 transitions
  + 1 initial value)

### Analysis on v1 data

Three lens runs against the filtered data:

**1. Time-correlation (`ss_phase2_analyze.py`)**: useless — per-delta
timestamps are bucketed at ~36s wall-time (when each poll finished),
not when SS actually changed memory. The 1.5s correlation window can't
work against 36s coarseness.

**2. Value-pattern matcher (`ss_phase2_value_match.py`)**: 27 addrs
had all values in [0, 50] (small-int candidate range). Top scorer
(`0x600001cf02b8`) had values `3, 1, 4, 1, 3` — partial match against
deck 0/1 indices but no clean winner. **Zero "perfect deck-N match"
addrs** because polling was too coarse to associate values with the
right rotation event in time.

**3. (bank=-1, index=N) packed-pair scan (`ss_phase2_bank_index.py`)**:
**0 hits.** Neither layout — `(idx<<32)|0xFFFFFFFF` nor
`0xFFFFFFFF<<32 | idx` — exists at any 8-byte aligned offset that
changed. SS does NOT store (bank, index) as a packed adjacent int32
pair. The log message assembles those values from non-adjacent
fields, or the bank=-1 is hardcoded in the log statement.

**4. Pointer-trajectory scan (`ss_phase2_ptrs.py`)**: most promising
result. 751 addrs transition between two distinct NANO heap pointers
(values in `0x6000_xxxxxxxx` range). Adjacent words at
`0x12118e000, +8, +10, +18, +20, +28…` (in MALLOC_SMALL
`MallocHelperZone_0x101cf4000`) all show 6 distinct nano_ptr values
in lockstep — looks like a **QObject* array** (e.g., array of
LookData pointers or QString pointers for "current look per
fixture/deck"). **Not validated** because timing is too coarse to
confirm pointer changes correlate with specific rotations.

### Phase 2 v1 verdict

**Methodologically sound, instrumentation too slow.** All three
identified issues are fixable in a v2 collector. No need to change
the experimental design — keep observational + RB-playing + random-
mode. Just make the collector fast enough.

### Phase 2 v2 collector (built, not yet run)

`/tmp/ss_phase2_collector_v2.py` (~9KB) addresses v1's three failures:

1. **Zone scope** — restrict to `DefaultMallocZone` (Phase 1 UTF-16
   hits) + `MallocHelperZone` (UTF-8 + pointer-array hits) by default.
   Configurable via `--zones default,helper,nano,tiny,small,medium,all`.
   Expected drop: 484MB → ~50MB virtual.
2. **In-memory binary buffer** — `list[(ts, addr, old, new)]` in RAM,
   dumped at end as `struct.pack('<dQQQ', …)` records (32 bytes each).
   No JSON encoding in hot path. Header: `b"SSPHASE2V2\n"` + comment
   line + records.
3. **AppLog inode-watch** — stat the log each tick; reopen on inode
   change; only seek to end on the first open (so rotation captures
   all subsequent events).

Other v2 changes:
- Default region cap 8MB (was 32MB)
- Default interval 200ms (was 500ms); status print every 5s
- Status includes `applog_reopens` counter so the AppLog rotation is
  visible during the run

`/tmp/ss_phase2_analyze_v2.py` (~7KB) — binary-format-aware analyzer.
Computes:
- **Time correlation per deck** (boundary_hits within ±1.5s window)
- **Value-at-time-T matches per-deck index** (most-recent rotation
  before T)
- **Deck affinity classification** (deck0-only / deck1-only / both /
  neither)
- Combined score with bonuses for [2, 16] distinct values

### Decision pending after v2 run

**Pointer-array signal from MALLOC_SMALL** (`0x12118e000` and ±N
offsets) is the highest-value hypothesis to validate or reject:

- If v2 confirms it (the same offsets show pointer-changes timed
  with rotations): we have a `QObject* array` candidate. Phase 3
  walks back from these to find the holder.
- If v2 finds different offsets that score higher: re-prioritize.
- If v2 finds nothing aligned (zero high-scoring candidates):
  reconsider — SS may distribute autoloop state across many
  fixture-level objects with no single "current_autoloop" field,
  which forces a pivot back to PR-G + Art-Net.

### Files persisted from session 3 (Phase 1 + Phase 2 v1)

Owned by `bbui:staff` unless noted; safe to keep, none are giant:

| file | size | owner | purpose |
|---|---|---|---|
| `/tmp/ss_phase1_probe.sh` | 2KB | bbui | Phase 1 anchor sweep script |
| `/tmp/ss_phase1_results.txt` | 12KB | bbui | Phase 1 raw output |
| `/tmp/ss_phase2_collector.py` | 13KB | bbui | v1 collector (kept for reference) |
| `/tmp/ss_phase2_collector_v2.py` | 9KB | bbui | **v2 collector** (next session) |
| `/tmp/ss_phase2_analyze.py` | 8KB | bbui | v1 generic analyzer |
| `/tmp/ss_phase2_analyze_v2.py` | 7KB | bbui | **v2 analyzer** |
| `/tmp/ss_phase2_recover_applog.py` | 3KB | bbui | rotated-log recovery |
| `/tmp/ss_phase2_filter.py` | 3KB | bbui | streaming pre-filter |
| `/tmp/ss_phase2_value_match.py` | 4KB | bbui | value-pattern matcher |
| `/tmp/ss_phase2_bank_index.py` | 2KB | bbui | (bank, index) pair search |
| `/tmp/ss_phase2_ptrs.py` | 3KB | bbui | pointer-trajectory analysis |
| `/tmp/ss_phase2_meta.json` | 8KB | bbui | v1 run metadata |
| `/tmp/ss_phase2_applog_recovered.jsonl` | 5KB | bbui | recovered rotations |
| `/tmp/ss_phase2_deltas_filtered.jsonl` | ~200MB | bbui | pre-filtered deltas (kept; useful baseline) |
| `/tmp/ss_phase2_addr_counts.json` | 8MB | bbui | per-addr change counts |
| `/tmp/ss_phase2_value_matches.json` | ~30KB | bbui | value-pattern results |
| `/tmp/ss_phase2_ptr_candidates.json` | ~50KB | bbui | pointer-array candidates |
| `/tmp/ss_phase2_deltas.jsonl` | 4.5GB | **root** | RAW v1 deltas — DELETE (`sudo rm`) |
| `/tmp/ss_phase2_applog.jsonl` | 0B | **root** | empty (failed tailer) — DELETE |

### Next-session checklist

**Read these first to recover context:**

1. This file (`docs/research/soundswitch/history/ss_memory_discovery.md`) — full investigation log
2. Memory entry `~/.claude/projects/-Users-bbui/memory/project_pr_f_blocked_amfi.md`
   (will be renamed `pr_f_phase2_in_progress.md` — see below)
3. The original plan: `~/.claude/plans/ss-memory-discovery.md`
4. The master plan: `~/.claude/plans/lets-plan-out-this-gleaming-marble.md`
   (PR-F is the high-risk row this discovery serves)

**Verify state at session start:**

```sh
csrutil status                              # should say Debugging Restrictions: disabled
pgrep -x SoundSwitch                        # SS PID (will differ from 15066)
launchctl list | grep bui                   # check watcher state
ls -la /tmp/ss_phase2_collector_v2.py       # confirm v2 collector still in place
```

**To run Phase 2 v2 collection:**

1. **Audio safety check** with user (no live performance, headphones/speakers OK)
2. User loads unscripted track in RB, starts bridge watcher via menubar
3. Verify ONE bridge process: `pgrep -f "rb_ss_bridge_v2.*__main__" | wc -l` should be 1
4. User confirms SS is rotating (check AppLog tail)
5. User runs (sudo via `!` prefix):
   ```
   ! sudo python3 /tmp/ss_phase2_collector_v2.py --duration 180 --interval 0.2
   ```
6. Expected: ~900 polls, ~5-10 rotations per 30s window, fine-grained per-rotation isolation
7. Run analyzer: `python3 /tmp/ss_phase2_analyze_v2.py --top 40`
8. **Validate**: top candidates should have `boundary_hits >> non_aligned`,
   `index_match_d0` or `index_match_d1` ≈ rotation count for that deck,
   `n_distinct` in [2, 16], deck_affinity is `deck0-only` or `deck1-only`
9. **If candidates confirm pointer-array theory**: proceed to Phase 3 (walk-back
   from candidate offsets to find `__DATA`-relative anchor). Tool to add:
   `walk-back` subcommand on `ss_memory_probe.py`.
10. **If no clear winners**: try `--zones all --max-region-mb 4` to broaden;
    or pivot the experiment to MIDI-direct or UI-driven (option 1 or 2 from
    the methodology choice earlier in this session).

**Cleanup before next probe** (optional, requires sudo):

```
sudo rm /tmp/ss_phase2_deltas.jsonl /tmp/ss_phase2_applog.jsonl
```

**Production access pattern decision** is still deferred to post-Phase 4:
bridge-as-root vs. root-helper-with-shm-mirror. Don't decide before
Phase 3 confirms the chain is stable across SS restarts.

---

## Session 4 — 2026-05-22 (Phase 2 v2 successful collection + analysis)

### Setup

| item | value |
|---|---|
| SS PID | 22998 (restarted between session 3 and 4; addresses fresh) |
| Bridge | PID 23139, manual session with `RBSS_SMART_DROP=1 RBSS_SMART_BREAKDOWN=1` |
| RB | PID 22997, playing "Fourword - Snake Charmer (Extended Mix)" unscripted, 126 BPM |
| SS mode | RANDOM autoloop selection |
| Collection duration | 180s |
| Interval | 200ms (target 900 polls @ 5Hz) |

### Collector v2 — three bottlenecks fixed mid-session

The collector as built in Session 3 hit two new bottlenecks beyond v1's diff loop:

1. **Inner diff loop** (lines 218–223) — Python word-by-word compare over ~22M
   8-byte words per poll. Fixed by replacing with `np.frombuffer(..., uint64)
   + np.nonzero(arr_new != arr_old)`. Verified ~150× faster on 8MB regions.
2. **`vm_read_safe` byte conversion** (line 82) — `bytes(buf[:N])` triggers
   ctypes slice → Python list of int objects → bytes() iteration. For 8MB:
   1408ms vs 8.9ms with `ctypes.string_at(addr, N)`. **158× speedup**.
   This was the dominant cost; the Python diff was on top of it.
3. **Python append loop over diffs** (post-numpy patch, still present) — for
   high-delta polls (when SS does a lot of writes between polls) the Python
   `buf.append((ts, addr, old, new))` over millions of diffs adds 200–2000ms.
   Acceptable in practice given 5Hz cadence keeps per-poll diff counts small.

After all fixes, observed: 184 polls / 180s, mean tick ~700ms (variable 169–2906ms),
slow_polls=172 but **rotation isolation is the metric that matters** — 184
polls / 139 rotations = 1.3 polls per rotation gap. That's good enough.

Patches live in `/tmp/ss_phase2_collector_v2.py`. **Production note**: if
restarted from scratch in another session, run with `--zones default,helper`
defaults and verify `last=<500ms` in first 5s of status output.

### Analyzer v2 — two bottlenecks fixed mid-session

1. **Per-event list rebuilds** — original analyzer had inner loops that
   rebuilt `times = [t for t, _ in rots]` once per event. Fixed by hoisting
   `deck_times`/`deck_indices` dicts above the loop.
2. **Full-load memory explosion** — loading 82M `<dQQQ>` tuples into a Python
   list was ~5GB; `by_addr` dict added another ~5GB. Mac ran out of RAM,
   used 10GB of swap, CPU dropped to 5% (paging). Fixed by replacing
   `read_binary_deltas` with two-pass streaming:
   - Pass 1: `count_changes_per_addr(path)` → `{addr: count}` dict, ~600MB peak
   - Filter: keep addrs with `min_changes ≤ count ≤ max_changes` (defaults [2, 200])
   - Pass 2: `collect_events_for_addrs(path, keep_addrs)` → tens of MB

Now invokable as: `python3 /tmp/ss_phase2_analyze_v2.py --top 40 [--min-changes 2 --max-changes 200]`.

Note: the original analyzer DID eventually complete on the 82M-delta dataset
(took ~3.5h wall-clock with swap thrashing) and wrote
`/tmp/ss_phase2_v2_candidates.json`. Patches above are correctness-preserving
optimizations for future runs.

### Phase 2 v2 results — strong signal

`/tmp/ss_phase2_v2_candidates.json` (94KB) has top 200 candidates by score.

**Top single candidate**: `0x00012ea07268`
- score=105.4, change_count=126 (~ rotation count 139)
- boundary_hits=55 (changes within ±1.5s of any rotation)
- d0/d1 = 46/9 — **strong deck-0 bias (5:1)**
- n_distinct=4, sample_values={0, 1, 2, 3}
- 8 changes within 2 seconds of a single deck-0 rotation event

**Per-deck affinity**: every top-200 candidate scored as `aff=both` (not
`deck0-only` or `deck1-only`). This is expected given ±1.5s window × 70
rotations per deck — accidental overlap is unavoidable. The d0:d1 ratio
on top scorers (5:1 to 8:1) is the real per-deck signal.

### v1 pointer-array hypothesis — NOT confirmed

Session 3's v1 finding identified a cluster at `0x12118e000 + 8/10/18/20/28…`
in MALLOC_SMALL with 751 addrs flipping between two distinct nano-heap
pointers. Hypothesis was a `QObject*` array (per-fixture LookData pointers).

**Re-examination in v2 data**:
- The high-scoring v2 candidates' values are **all small ints (0–9)**, never
  nano-heap pointers (no values in the `0x600000xxxxxx` range).
- There IS a candidate group at `0x0003000499xx` (ranks 21–50) that looks
  cluster-like in the JSON, but on closer inspection the stride pattern is
  irregular: a tight ~10-addr group at `0x300049900–998` (within 0x100),
  then sparse pairs every ~0x4000 (16KB) apart. **More like "per-fixture
  struct instances 16KB apart" than a packed pointer array.**
- No top-200 candidate cluster shows the v1 pattern of "adjacent 8-byte
  words flipping between distinct heap pointers in lockstep."

Conclusion: v1's pattern was probably an artifact of the coarse-grained
collection (only 5 polls over 180s) producing spurious correlations in a
Qt internal data structure. The v2 fine-grained data does not reproduce it.

### What the top candidates probably are

Sample value sets across top 15:
- `{0, 1, 2, 3}` — addr [1] — cycles through 4 states
- `{3, 4, 9}` — addr [2] — 3 small ints
- `{2, 3, 4, 9}` — addr [3] — 4 small ints
- `{3, 196608=0x30000}` — addr [4] — flipping between small int and high-byte-2 value
- `{1, 2, 3, ..., 7}` — addr [6] — 8 distinct small ints
- `{2, 3}` — addr [9] — only 2 values

These do **not** match observed deck-0 indices (5, 7, 16, 41) or deck-1
indices (2, 3, 10, etc.). So none of these top candidates is directly
`current_autoloop_index`. They're likely **sub-state of an autoloop**:
- Beat-divisor counter (autoloops beat-sync)
- Step counter within a chase pattern
- LFO/animation phase
- Internal state machine (preparing → running → finishing)

The **real `current_autoloop_index` field** would hold values from the actual
observed index set ({2, 3, 5, 7, 10, 16, 38, 41, ...}). It may be present
but ranked lower because its change count is exactly ~70/deck (one per
rotation), and Δt should be very close to 0 — the scoring would reward it.
Worth a targeted value-search.

### Knowns vs unknowns going into next session

**Confirmed**:
- vm_read introspection works under sudo, stable for 180s observation windows
- Heap data **does** contain rotation-correlated state — the question is what kind
- Per-deck signal is real (5:1 to 8:1 d0/d1 ratios on top candidates)
- Collector + analyzer toolchain is now fast enough (5Hz sustained, two-pass analysis)

**Ruled out (this PID, this session)**:
- v1 "QObject* array" pointer cluster hypothesis
- "Top scored addresses hold the autoloop index" interpretation

**Unknown / next-session investigation**:
- Where the actual `current_autoloop_index` field lives (value-targeted search needed)
- Whether SS holds a separate `next_autoloop` field at all
- What the small-int state machines at top candidates actually represent
- Whether the `0x30004XXXX` per-16KB-stride pattern is per-fixture state

### Artifacts persisted from session 4

| file | size | owner | purpose |
|---|---|---|---|
| `/tmp/ss_phase2_collector_v2.py` | 14KB | bbui | **patched** (numpy diff + string_at) |
| `/tmp/ss_phase2_analyze_v2.py` | 10KB | bbui | **patched** (two-pass streaming + hoisted lists + filter args) |
| `/tmp/ss_phase2_inspect_top.py` | 5KB | bbui | **new** — per-event timeline for top-N candidates from JSON |
| `/tmp/ss_phase2_v2_candidates.json` | 94KB | bbui | top 200 scored candidates |
| `/tmp/ss_phase2_v2_applog.jsonl` | 16KB | root | 139 rotation events |
| `/tmp/ss_phase2_v2_meta.json` | 499B | root | run metadata |
| `/tmp/ss_phase2_v2_regions.json` | 5KB | root | zone snapshot |
| `/tmp/ss_phase2_v2_deltas.bin` | **2.6 GB** | **root** | raw deltas (keep for re-analysis or delete with `sudo rm`) |

The 2.6GB deltas.bin is the only large artifact. Keep if next session
wants to re-analyze with different filter bounds or value-targeted search;
delete via `sudo rm /tmp/ss_phase2_v2_deltas.bin` to reclaim disk.

### Decision tree for next session

1. **Value-targeted search** (recommended first step): scan `.bin` for
   addresses where new_value ∈ observed-index-set at the time of the
   corresponding rotation event. Tool to write:
   `/tmp/ss_phase2_value_search.py`. Reads applog + deltas; for each
   rotation event, find addrs that took the new index value at that ts ±0.5s.
   Top addrs = likely `current_autoloop_index`.
2. **If (1) finds clean candidates**: proceed to Phase 3 walk-back from the
   confirmed addr. Add `walk-back` subcommand to
   `/Users/bbui/rb_ss_bridge_v2/tools/ss_memory_probe.py`.
3. **If (1) finds nothing**: pivot to **controlled experiment** — user
   manually triggers known indices via SS UI on one deck at a time, in a
   known sequence. Eliminates random-mode noise; gives clean causal signal.
4. **If controlled experiment also fails**: SS may store autoloop state in a
   structure where the human-readable "index" never appears as an integer
   in memory (e.g., stored as a QString name like "BLUE FANNING 2" with a
   separate i32 enum). In that case revisit Phase 1 anchor-string approach
   to find per-deck "current look name" QString locations.

### Don't repeat in next session

- Don't re-run Phase 1 string sweep (done; results in this notebook).
- Don't trust the v1 `0x12118e000` finding; that PID is dead, and the pattern
  did not reproduce in v2. The "candidate cluster" idea is still valid but
  needs to be re-derived from v2 data.
- Don't re-collect unless current `.bin` is insufficient. Value-targeted
  search can run against the existing 82M deltas.
- Don't bump `--max-changes` above 1000 unless looking for very high-churn
  addrs — anything changing >200 times in 180s is almost certainly noise.

### Open question for user (deferred from Phase 2)

`aff=both` on every top candidate suggests the rotation events themselves
may be partially correlated across decks (e.g., SS schedules rotations on
shared bar boundaries). Worth checking: did the bridge's smart-drop /
smart-breakdown fires happen ~simultaneously on both decks during this
collection? If so, that's not memory noise — it's the bridge driving both
SS decks together. Look at `/tmp/bridge.log` for the collection window
(14:34:33 to 14:37:33) and count `autoloop-rearm` events per deck.

---

## Session 5 — 2026-05-22 (continuation, value-search + failed noise-reduce)

### Caveat audit (lockstep question from session 4)

Counted bridge-fired events during the collection window (14:34:33–14:37:33):
- Total: 46 events
- Deck 2 (= SS d1): rearm×4, smart-drop-crossing×4, smart-breakdown-cut×3,
  smart-breakdown-restore×2, phrase-anchor×2 = **15 events**
- Deck 1 (= SS d0): smart-drop-crossing×3 = **3 events**

Asymmetric bridge fires (5×) but rotation events were nearly even
(d0=68, d1=71). **Bridge was NOT driving both decks in lockstep.** The
`aff=both` pattern is more plausibly explained by ±1.5s window over 70
rotations/deck → accidental overlap, OR shared SS internal state that
toggles on any deck event.

### Value-targeted search

Built `/tmp/ss_phase2_value_search.py`. Single-pass stream of `.bin`,
fast-filters records where `new ∈ observed_index_set`, then checks ts
within ±0.5s of a rotation that committed that index. 30.8s runtime
on the 82M-delta file.

**Result: simple-integer hypothesis ruled out.** Top score = 21 hits
(vs ~70/deck expected if any addr held `current_autoloop_index`).
1.15M unique addrs match the loose criteria but no addr matches more
than 9 times total. Top candidates are the SAME small-int state
machines from the analyzer (0x12ea07268 etc.) — they sometimes happen
to hold matching values but are not authoritatively storing the index.

Wrote results to `/tmp/ss_phase2_v2_value_candidates.json` (200 entries).

### Failed noise-reduction experiment

Hypothesis: setting `RBSS_SMART_REARM_EXPERIMENT=0 RBSS_SMART_DROP=0
RBSS_SMART_BREAKDOWN=0` would silence the 46-event bridge volley and
let pure SS-autonomous rotation dominate the delta stream.

**Outcome: bridge couldn't detect tracks with these flags off.**
User attempted the noise-reduced launch; bridge log shows track-load
detection failing. Reverted to full-envs-on. The `_quiet` prefix
collection ran for 180s but the applog ended up 0 bytes (SS never
rotated) — useless dataset.

Lesson saved in memory file `feedback_bridge_required_for_ss_rotation.md`:
**do NOT propose disabling RBSS_SMART_* env flags as a noise-reduction
technique.** The DIRECT-memory features and the smart features have
undocumented coupling; flipping smart off breaks track detection.

### Files added in session 5

| file | size | owner | purpose |
|---|---|---|---|
| `/tmp/ss_phase2_value_search.py` | ~7KB | bbui | value-targeted search (small tool) |
| `/tmp/ss_phase2_v2_value_candidates.json` | ~50KB | bbui | top 200 value-matched candidates |

### Files to clean up

The failed-noise-reduce experiment left ~790MB of unusable data:

```sh
sudo rm /tmp/ss_phase2_v2_quiet_*  # ~790MB freed, no rotation events
```

The 2.6GB `/tmp/ss_phase2_v2_deltas.bin` from session 4 also has stale
absolute addresses (SS PID changed from 22998 to 52588 on session 5).
The *patterns* in candidates.json are still valid; the absolute
addresses are not. Keep candidates JSON for reference, can free the
.bin if disk pressure (`sudo rm /tmp/ss_phase2_v2_deltas.bin`).

### Session 5 close — current state

- SS PID 22998 dead; new SS PID 52588 then stopped; **all of bridge/SS/RB
  currently stopped** at session close (2026-05-22 ~18:30)
- Hypothesis space narrowed: simple-integer for `current_autoloop_index`
  in default+helper zones is **definitively ruled out** (value-search
  would have found it)
- Two unexplored directions:
  1. **Expand zones to `--zones all`** — covers NANO + TINY non-helper +
     SMALL non-helper + MEDIUM. May surface the field if it lives outside
     the malloc-helper zones.
  2. **Controlled UI experiment** — user manually clicks specific autoloop
     indices in SS UI in a known sequence. Eliminates random-mode noise
     entirely; gives clean causal signal at the cost of ~10-15 min of
     UI interaction.

User explicitly chose option 1 (recommended) but the recollect never
ran due to the failed noise-reduce detour. Resume there in next session.
