# Govee Realtime — Phase 2 Integration Handoff

> Status: **IMPLEMENTED / REVIEW HANDOFF**. Authored as a design note 2026-06-13;
> updated after implementation on 2026-06-13.
> Scope: add a LAN realtime (Razer/DreamView) backend to the LED Look Director,
> alongside the existing cloud DIY path, for the single **proven** strip.
> Companion to: `docs/current_architecture.md`, `docs/bridge_design.md`,
> `docs/runtime_invariants.md`.

## Current implementation snapshot

Runtime code now exists in:

- `govee_realtime_transport.py`
- `govee_frame_renderer.py`
- `govee_owner_state.py`
- `govee_realtime_runner.py`
- `led_dispatch_coordinator.py`
- `led_models.py`
- `led_config.py`
- `led_look_director.py`
- `state_manager.py`
- `__main__.py`

The implemented config uses Option C: the proven home strip remains target
`room_perimeter`, cloud DIY remains available, and realtime cues are mixed into
the same `buildup`, `groove`, and `drop` role lists as the cloud cues.

Verification from the current implementation:

- Focused realtime/LED regression: 97 tests passing.
- Full unittest discovery: 1365 tests passing, 3 skipped, 1 expected failure.
- Config load: `config/led_look_director.json` loads with realtime enabled for
  `room_perimeter` at `192.168.0.219:4003`.
- Cue wiring: all 18 requested EDM cues from `play_effects.py` are present in
  the default bank alongside cloud cues and render valid 20-segment frames.
- Timing offsets: cloud LED automation keeps a `0.6s` lead to compensate for
  cloud latency; realtime Razer automation uses a `0.0s` lead so LAN cues fire
  on the live beat instead of inheriting cloud-delay compensation.
- LAN discovery: multicast scan finds `C1:0A:DA:B9:81:C6:3C:02`, SKU `H612D`,
  at `192.168.0.219`.
- Live smoke transport result: 56 realtime frames, 4 control commands, and 0
  send errors.
- Performance benchmark: about 0.064 ms per render+packet frame across the 18
  requested cues, or about 0.19% of one CPU core at 30 fps for one strip.

Remaining proof gap: UDP send success does not acknowledge physical output.
Treat live visual behavior as pending until the operator confirms that the strip
showed the authorized blue-chase smoke and returned afterward.

The sections below are retained as design rationale. Some wording still describes
the pre-implementation build plan; the implementation snapshot above is the
current state for review.

Every claim below is labeled:
- **[CONFIRMED]** — verified by reading the live code/config in this repo.
- **[ASSUMED]** — reasonable inference, not yet verified; must be checked before build.
- **[UNKNOWN]** — open question requiring an experiment or an operator decision.

---

## 0. TL;DR for the implementer

> **Operator context (2026-06-13):** there are two physical strips — one at **home**
> (for programming/testing) and one at the **venue**. The realtime razer proof works
> over **LAN UDP**, which only reaches the strip on the bridge machine's current
> network. Therefore the proven realtime device (`C1:0A…` @ `192.168.0.219`) is the
> **home** strip; the strip that did not answer the LAN scan (`54:2C…`) is the
> **venue** strip, reachable only via Govee cloud. **[CONFIRMED by operator 2026-06-13]**
> Consequence: **realtime is location-bound.** Realtime at the venue requires proving
> the venue strip on the venue LAN (§9) — that proof is on the critical path for gigs,
> not optional.

1. The realtime device is the strip currently configured as target **`room_perimeter`**
   (`device_ref = C1:0A:DA:B9:81:C6:3C:02`, IP `192.168.0.219`) — the **home** strip.
   The *name* is misleading but the *device* is the proven one. **[CONFIRMED config / ASSUMED home]**
2. **Do not** remap `room_perimeter`'s `device_ref` to the second strip. Every live
   look targets `room_perimeter`; remapping silently redirects the whole show to an
   unproven device. **[CONFIRMED]** — see §3.
3. Realtime is a **continuous 30 fps frame pump**, not a one-shot scene command. It
   needs its own runner/clock and a beat-phase feed. It must **not** be bolted into
   the existing `GoveeSceneAdapter` command queue. **[CONFIRMED arch / ASSUMED design]** — see §5.
4. The cloud path and the realtime path drive the **same physical device** over two
   different networks (HTTPS cloud vs LAN UDP). They will fight unless a single owner
   lock gates **both**. The lock must gate the cloud automation tick too, not just the
   new code. **[CONFIRMED risk]** — see §6.
5. Several frozen dataclasses and one validator constant must change or the config
   won't even load. The original plan missed these. **[CONFIRMED]** — see §4.

---

## 1. Verified current architecture

### 1.1 Data flow (cloud DIY, today) **[CONFIRMED]**

```
live_bpm / phrasing  ──► LEDContext(role=…)
                              │
                    LEDLookDirector.tick()        (led_look_director.py)
                              │  picks a look from the per-role bank
                              ▼
                    LEDLookDecision               (frozen: look,target,action,scene_ref,…)
                              │
                    GoveeSceneAdapter.trigger()   (govee_scene_adapter.py)
                              │  bounded queue (maxsize≤16), dedupe, rate-limit,
                              │  circuit breaker, emergency-blackout bypass
                              ▼  worker thread, one command at a time
                    self._send_command(cmd, timeout)   ← injected callable
                              │
                    GoveeRuntimeSender.send()     (govee_runtime_sender.py)
                              │  resolves capability, POSTs Govee Cloud HTTP API
                              │  ALSO fans out to target.mirror_targets
                              ▼
                    Govee Cloud  ──► physical strips
```

Wiring point **[CONFIRMED]** `__main__.py:380-389`:
```python
led_director = LEDLookDirector(cfg, shuffled_roles=("drop",))
govee_sender = GoveeRuntimeSender(cfg) if not cfg.dry_run else None
led_adapter  = GoveeSceneAdapter(
    cfg,
    send_command=govee_sender.send if govee_sender else None,
    status_provider=govee_sender.status if govee_sender else None,
)
```
There is exactly **one** `send_command` callable. The adapter is transport-agnostic;
all transport knowledge lives in `GoveeRuntimeSender`.

### 1.2 The frozen data models **[CONFIRMED]** (`led_models.py`)

| Model | Carries today | Missing for realtime |
|-------|---------------|----------------------|
| `LEDTarget` (frozen) | name,label,device_ref,expected_model,control_route,capabilities,mirror_targets | `backend`, `realtime` block |
| `LEDLook` (frozen) | name,target,action,scene_ref,fallback,safety_class,brightness,allow_strobe | `backend`, `params` |
| `LEDLookDecision` (frozen) | look,target,action,scene_ref,reason,source,priority,role | `backend`, `params` |
| `LEDAdapterCommand` (frozen) | look,target,action,scene_ref,reason,source,role | `backend`, `params` |

> **Original plan gap:** it proposed adding `backend`/`realtime` only to the *target*
> dataclass. But `backend` and the render `params` must travel **all the way to the
> adapter**: Director → Decision → Command. The Decision and Command are built field
> by field in `led_look_director.py:211` and `govee_scene_adapter.py:109`; any field
> not explicitly copied is dropped. Without threading `backend` through, the adapter
> cannot route by backend. **[CONFIRMED]**

### 1.3 Validation gates that will block realtime **[CONFIRMED]**

- `led_config.py:47` — `_LOOK_ACTIONS = frozenset({"scene","music_mode","diy_scene","off","unmapped"})`.
  `_validate_look()` (`:281`) rejects any other action. `action:"realtime"` ⇒ the
  **entire** config returns `invalid_config` ⇒ LED director disabled at startup
  (`__main__.py:365`). Must add `"realtime"` to this set.
- `_build_config()` (`:549-560`) constructs `LEDLook` from a fixed field list. New
  fields (`backend`, `params`) must be parsed here with defaults or they vanish.
- `_validate_live_ready()` (`:446`) runs because the live config has `dry_run:false`
  **[CONFIRMED `led_look_director.json:4`]**. It only inspects scene/music/diy
  scene_refs, so a realtime look won't trip placeholder checks — **but** confirm new
  realtime looks don't carry a placeholder-like field. **[ASSUMED safe]**

### 1.4 Adapter & cloud-sender behavior for an unknown action **[CONFIRMED]**

- `GoveeSceneAdapter._capability_error()` (`:437`) only checks scene/diy/music/off.
  An unrecognized `action:"realtime"` returns `""` (no error) → command is **accepted**
  into the queue and handed to `send_command`.
- `GoveeRuntimeSender._capability_payload()` (`:393`) returns `None` for any action
  other than scene/diy_scene/music_mode/off → `_send_to_target` returns
  `{"ok": False, "error": "unresolved_capability"}`.
- Net: if a realtime look is left to flow through the existing path, it is **accepted
  then fails every send**, tripping the circuit breaker after 3 failures
  (`_CIRCUIT_FAILURE_THRESHOLD`). So realtime **must be intercepted before** the cloud
  sender. **[CONFIRMED]**

### 1.5 Runtime sender construction is device-cache-dependent **[CONFIRMED]**

`GoveeRuntimeSender.__init__` (`:252-289`) iterates every target with
`control_route == "govee_platform_dynamic_scene"`, looks it up in
`/tmp/govee_h612d_devices.json`, and **raises `target_not_found:<name>`** if absent.
That exception is caught in `__main__.py:390` and **disables the entire LED subsystem**.

Implication: any new cloud-capable target (e.g. a separate `bui_strip_light`) must
have its device present in the cached devices file, or LED startup dies. The proven
device `C1:0A…` is already cached (room_perimeter works today), and `54:2C…` is cached
via `strip_light_mirror`. A pure rename keeps both present; *adding* a third target
name pointing at an already-cached device is also fine. **[CONFIRMED]**

### 1.6 Mirror fan-out **[CONFIRMED]** (`govee_runtime_sender.py:352-360`)

`send()` sends to the primary target, then replays the **same command** to every
`mirror_targets` entry. Today `room_perimeter.mirror_targets = ["strip_light_mirror"]`,
so **every cloud look lights both physical strips**. Realtime (LAN UDP to one IP) has
no equivalent fan-out.

---

## 2. Device inventory (corrected, evidence-backed)

### 2.1 `C1:0A:DA:B9:81:C6:3C:02` — PROVEN realtime device (HOME strip)

| Field | Value | Source |
|-------|-------|--------|
| Physical location | **home** (programming/test strip) | **[ASSUMED]** — answered LAN scan ⇒ on the local network |
| Configured as target | `room_perimeter` (label "Bui light test") | **[CONFIRMED]** `led_look_director.json:10-12` |
| IP | `192.168.0.219` | **[ASSUMED]** from realtime proof; DHCP — see §7 |
| SKU | `H612D` | **[CONFIRMED]** config |
| Cloud DIY | working in production today | **[CONFIRMED]** live config, mirror count |
| Realtime razer | `confirmed_visual_pass` 2026-06-13 | **[ASSUMED]** per Phase-1 proof (not reproducible from repo) |
| Segments | 20 | **[ASSUMED]** from proof |
| Activate / deactivate `pt` | `uwABsQEK` / `uwABsQAL` | **[ASSUMED]** from proof |
| Packet | `header(5)+seg_count(1)+RGB×N+XOR(1)`, JSON `{"msg":{"cmd":"razer","data":{"pt":b64}}}` | **[ASSUMED]** from proof |

> The packet/proof values come from the Phase-1 experiment, not from anything in this
> repo. Treat them as authoritative for the proven device but **pin them in a fixture**
> (see §8) so a regression is detectable.

### 2.2 `54:2C:DA:B9:81:C6:3C:38` — NOT proven for realtime (VENUE strip)

| Field | Value | Source |
|-------|-------|--------|
| Physical location | **venue** | **[ASSUMED]** — no LAN scan response ⇒ not on the home network |
| Configured as target | `strip_light_mirror` (label "Strip Light") | **[CONFIRMED]** `led_look_director.json:25-27` |
| IP | unknown / no LAN scan response (different LAN) | **[ASSUMED]** per plan |
| Cloud DIY | working (mirror of room_perimeter) | **[CONFIRMED]** |
| Realtime | **not proven** — cloud-only | decision |

---

## 3. The migration decision (critical, live-config safety)

### 3.1 The trap **[CONFIRMED]**

- All ~40 looks set `"target": "room_perimeter"`.
- `room_perimeter.device_ref = C1:0A…` (the proven device).
- `room_perimeter.mirror_targets = ["strip_light_mirror"]` → second strip mirrors.

The original plan §4 says *"Remap `room_perimeter` to device `54:2C…`"*. Doing that
while the looks still say `target: room_perimeter` would point the **entire live show**
at the unproven second strip and drop the proven device. This contradicts the plan's
own "existing looks must keep working" constraint. **Reject this step.**

### 3.2 Options

> **DECISION (operator, 2026-06-13): Option C selected.** Proceed minimal; defer any
> rename to a separate cleanup. Home/venue↔device mapping confirmed (home=`C1:0A`, venue=`54:2C`).

**Option C — minimal, SELECTED.** Keep target names as-is. Add a `realtime` block
(and `backend` default) to the existing proven target (`room_perimeter`). Optionally
fix its cosmetic `label` to "Bui Strip Light". Zero look rewrites, zero mirror rewrites,
zero risk to the live show. Cost: the target name `room_perimeter` stays semantically
wrong, which is a documentation/readability issue, not a functional one.

**Option A — rename for clarity, ACCEPTABLE but do it separately.** Rename
`room_perimeter` → `bui_strip_light` everywhere: 40 look `target` fields, every bank
list entry, `safe_default`, `blackout`, and the `mirror_targets` references. High-churn
edit on a LIVE config; one transcription slip silently breaks a cue. If chosen, do it as
an **isolated, separately-tested commit** *before* the realtime feature, validated by a
config-load test and a diff that shows only the rename.

**Option B — add a second target alongside.** Add `bui_strip_light` as a *new* cloud+realtime
target pointing at `C1:0A…`, leave `room_perimeter` untouched. Now two target names map to
the **same physical device**; cloud automation drives it as `room_perimeter` while realtime
drives it as `bui_strip_light`. This **guarantees** the owner-fight problem (§6) and doubles
the device's config surface. **Not recommended.**

> **Recommendation:** ship realtime on **Option C** (lowest live-risk). Schedule the
> `room_perimeter → bui_strip_light` rename (Option A) as an independent cleanup if the
> naming bothers us. This is the one decision that needs operator sign-off before build.

### 3.3 Second strip stays cloud-only

`strip_light_mirror` keeps `backend: cloud_diy` and gets `realtime: {enabled: false}`.
No realtime until the §9 proof passes independently.

---

## 4. Required code changes (corrected & complete)

### 4.1 `led_models.py`

```python
@dataclass(frozen=True)
class LEDRealtimeConfig:
    enabled: bool = False
    protocol: str = ""
    ip: str = ""
    port: int = 4003
    segments: int = 20
    header: str = ""
    header_bytes: tuple[int, ...] = ()
    stretch: bool = False
    fps: int = 30
    activate_pt: str = ""
    deactivate_pt: str = ""
    proof_status: str = "not_proven"
    proof_date: str = ""

# LEDTarget: add
    backend: str = "cloud_diy"
    realtime: LEDRealtimeConfig = LEDRealtimeConfig()   # default-frozen instance

# LEDLook / LEDLookDecision / LEDAdapterCommand: add
    backend: str = "cloud_diy"
    params: Mapping[str, Any] = field(default_factory=dict)   # render params (color, trail, …)
```
All four objects are frozen — new fields need defaults so existing construction sites
and existing tests keep working. **[CONFIRMED constraint]**

> `params` as a dict breaks frozen-dataclass hashability if anything hashes the command.
> The adapter's dedupe key (`govee_scene_adapter.py:434`) uses
> `(target,action,look,scene_ref)` — it does **not** hash `params`, so this is safe.
> **[CONFIRMED]** Still, prefer storing params as an immutable mapping (e.g.
> `MappingProxyType` or a tuple of items) to keep the frozen contract honest.

### 4.2 `led_config.py`

- Add `"realtime"` to `_LOOK_ACTIONS`. **[CONFIRMED required]**
- `_validate_look`: for `action == "realtime"`, require `backend == "realtime_razer"`
  and a known `scene_ref` (effect name); validate `params` shape (color is `[int,int,int]`
  in 0–255, etc.).
- `_validate_target`: parse/validate optional `backend` (`cloud_diy`|`realtime_razer`)
  and the nested `realtime` block; default `backend="cloud_diy"`,
  `realtime.enabled=false` when absent.
- `_build_config`: populate the new `LEDTarget.backend/realtime` and
  `LEDLook.backend/params` fields (they're dropped otherwise).
- Consider a cross-check: a look with `backend:"realtime_razer"` must target a target
  whose `realtime.enabled` is true → else `invalid_config`. Prevents pointing realtime
  looks at the unproven strip. **[ASSUMED desirable]**

### 4.3 `led_look_director.py`

`_decision_for_look` (`:201`) must copy `backend` and `params` from the look onto the
`LEDLookDecision`. One-line-per-field additions; no policy logic change.

### 4.4 Routing — keep the adapter transport-agnostic (design choice)

Two viable shapes:

**(R1) Composite/dispatching sender — RECOMMENDED.** The adapter keeps its single
`send_command` callable. Inject a small dispatcher that branches on `command.backend`:
```python
def send(cmd, timeout):
    if cmd.backend == "realtime_razer":
        return realtime_runner.apply(cmd)     # hands off to the realtime runner
    return govee_cloud_sender.send(cmd, timeout)
```
- Pros: the clean bounded-queue adapter stays unchanged; mirrors existing wiring; the
  owner lock lives in one coordinator the dispatcher and runner share.
- Cons: discrete-command queue still mediates a *start/stop* of a continuous loop — the
  realtime command means "start pumping," and a subsequent non-realtime command (or
  blackout) means "stop pumping." That transition logic lives in the dispatcher/runner,
  not the adapter.

**(R2) Teach the adapter about backends** (original plan). Put owner state + transport +
renderer inside `GoveeSceneAdapter`. Rejected: it bloats a well-tested, single-responsibility
queue and couples it to UDP/threading concerns. **[ASSUMED — recommend R1]**

### 4.5 Build the cloud sender with backend awareness

`GoveeRuntimeSender.__init__` raises `target_not_found` for cloud-route targets not in
the device cache (§1.5). Ensure the proven device remains cached and that no new
realtime-only target is given `control_route: govee_platform_dynamic_scene` *without*
a cached device. The proven strip is dual-backend, so it keeps the cloud route and
stays cached — fine. **[CONFIRMED]**

---

## 5. The realtime runner (the part the original plan under-specified)

### 5.1 Why it can't be a queue command

`GoveeSceneAdapter` processes **discrete, fire-and-forget** commands: trigger → one send →
done. Realtime is a **continuous clock**: ~30 frames/sec, each frame a function of the
**current beat phase**, until superseded. These are different lifecycles. **[CONFIRMED]**

### 5.2 Proposed component: `GoveeRealtimeRunner`

```
GoveeRealtimeRunner
  owns:  GoveeRealtimeTransport  (pure UDP; no bridge knowledge)
         GoveeFrameRenderer      (stateless: beat_phase+params -> 20 RGB tuples)
         a daemon thread @ fps    (the frame clock)
         a reference to the beat-phase source (read-only)
         a reference to the shared GoveeOwnerStateMachine

  apply(cmd):                     # called by the dispatcher for a realtime look
     acquire owner REALTIME_RAZER (gate cloud out)
     transport.activate()
     set active effect = (cmd.scene_ref, cmd.params)
     ensure frame thread running

  on each tick (1/fps):
     phase = beat_source.beat_phase()        # 0..1 within the beat
     frame = renderer.render(effect, phase, params)
     transport.send_frame(frame)

  stop():                         # called on handoff to cloud / blackout / cue end
     stop frame thread
     transport.deactivate()
     release owner
```

### 5.3 Beat-phase source — RESOLVED **[CONFIRMED 2026-06-13]**

The plan's hard constraint "transport must not know BPM/phrases/cue logic" is correct
**for the transport**. The renderer driver (the runner) supplies phase. Investigation
findings:

- **The beat clock the runner needs already exists and is already computed live.**
  `StateManager` drives the existing LED director tick (`state_manager.py:1209/1270/1446/1595`)
  and already computes a beat position (`beatpos`) every tick to feed OS2L/SoundSwitch
  (`osl_output.send_elapsed(deck, elapsed_ms, beatpos)`, `osl_output.py:327`). So beat
  phase is **not** a new subsystem — it's an existing signal. **[CONFIRMED]**
- Ingredients, all available at the StateManager tick boundary where the runner should hook:
  - active/master deck — StateManager. **[CONFIRMED]**
  - `elapsed_ms` — `StateManager.get_deck_elapsed_ms(deck)` (`state_manager.py:526`). **[CONFIRMED]**
  - `bpm` — `live_bpm.get_bpm(deck)` / `get_status(deck).bpm` (+ `valid`). **[CONFIRMED]**
  - `first_beat_ms` / beatgrid — `filepath_resolver` beatgrid for the loaded track
    (`filepath_resolver.py:193/238`). **[CONFIRMED]**
  - the math — `beat_math._compute_beat_pos(elapsed_ms, bpm, first_beat_ms)` → fractional
    beat in `[0,4)`; or `_compute_beatgrid_position(elapsed_ms, beatgrid_times_ms)` for
    grid-accurate phase. **[CONFIRMED]** Reference consumer: `autoloop_controller.py`.
- **No ready-made `beat_phase()` call**, and StateManager ticks at the bridge poll rate
  (not 30 fps). So the runner must **interpolate**: on each StateManager tick, capture an
  anchor `(elapsed_ms0, bpm, first_beat_ms, t0 = monotonic())`; then each 30 fps frame
  compute `pos = _compute_beat_pos(elapsed_ms0 + (now - t0)*1000, bpm, first_beat_ms)`.
  - phase within the current beat = `pos % 1.0` (chases, pulses).
  - beat index in bar = `int(pos) % 4` (bar-aware effects, strobe subdivisions).
  - strobe "on-beat" pulse = detect `floor(pos)` increment between frames.
- **Staleness/safety:** if `bpm` is invalid/stale (`LiveBPMStatus.valid` /
  `LiveBPMReading.is_stale`) or the deck isn't playing, hold a static frame — do not
  chase a dead clock. **[ASSUMED — recommended]**

**Conclusion:** R4 is resolved and low-risk. The runner reads the *same* deck/elapsed/bpm/
beatpos the StateManager already maintains, hooking the same tick path that drives the LED
director today, and interpolates with `monotonic()` for smooth 30 fps phase.

### 5.4 Thread & shutdown discipline **[ASSUMED, matches existing conventions]**

- One daemon thread, bounded shutdown join (mirror the adapter's
  `worker_shutdown_timeout_s` pattern).
- The frame thread must never block on network: UDP `sendto` is non-blocking; on socket
  error, count-and-continue (don't crash the show), surface via status.
- Idempotent `stop()`; safe to call from the dispatcher, the blackout path, and
  bridge shutdown.

---

## 6. Owner coordination (the real fight)

### 6.1 The hazard **[CONFIRMED]**

Cloud and realtime reach the **same physical device** by two independent networks. The
automation loop keeps ticking: `LEDLookDirector.tick()` runs on the normal cadence and,
unless gated, will keep emitting **cloud** scene looks that the cloud sender will happily
POST — stomping the live razer stream. So the owner lock must gate the **cloud dispatch
path**, not merely the new realtime code.

### 6.2 Single coordination point

`GoveeOwnerStateMachine` (`NONE | CLOUD_DIY | REALTIME_RAZER`) is shared by the dispatcher
and the runner:

- Dispatcher, on a **cloud** command while owner == `REALTIME_RAZER`: either (a) drop the
  cloud command, or (b) treat it as an implicit handoff request (realtime → cloud). Pick
  one explicitly. **Recommend (a) drop-with-reason** unless the look is the blackout (which
  always wins), so automation churn can't yank realtime off mid-effect. The director will
  keep proposing cloud looks; the dispatcher silently no-ops them while realtime owns the
  device, exactly like the adapter already drops rate-limited commands. **[ASSUMED]**
- Dispatcher, on a **realtime** command while owner == `CLOUD_DIY`: perform the
  cloud→realtime handoff (§7).
- Blackout (`action:"off"` or `look == config.blackout`) bypasses everything (existing
  emergency semantics, `govee_scene_adapter.py:408`) and forces `force_release()`.

> The director itself stays untouched — it has no I/O and shouldn't learn about owners.
> Gating happens at the dispatch boundary, which already sees every command. **[CONFIRMED feasible]**

---

## 7. Handoff & mirror protocol

### 7.1 cloud_diy → realtime_razer
1. `owner.acquire(REALTIME_RAZER)` (blocks/forces out cloud ownership).
2. `transport.activate()` (brightness 100 + activate `pt`).
3. **Mirror decision (NEW — see §7.4):** address the second strip explicitly.
4. Start the frame loop.

### 7.2 realtime_razer → cloud_diy
1. Stop frame loop.
2. `transport.deactivate()` (deactivate `pt`). **Do not** pre-blackout (plan is right:
   deactivate suffices) unless the cue asks for it.
3. `owner.release(REALTIME_RAZER)` → `NONE`.
4. Issue the cloud look normally → owner becomes `CLOUD_DIY`.

### 7.3 Emergency blackout (any state)
1. If realtime active: send all-black frame, then `deactivate()`.
2. `owner.force_release()` → `NONE`.
3. Deliver blackout via the existing cloud/off path (already guaranteed-delivery).

### 7.4 Mirror handling during realtime — **NEW, plan didn't resolve [CONFIRMED gap]**

Today every cloud look also lights `strip_light_mirror`. When realtime takes over the
**primary** strip, the mirror strip is **not** driven by the LAN stream and will simply
**freeze on whatever cloud scene it last showed**. Visually: primary does a live beat
chase while the second strip holds a stale static scene.

Decide explicitly (operator/visual call):
- **(M1)** Leave the mirror on its last cloud scene (simplest; visible mismatch). 
- **(M2)** At cloud→realtime acquire, send the mirror a complementary cloud scene (e.g. a
  dim solid) so it doesn't look frozen. 
- **(M3)** Blackout the mirror during realtime.

**Recommend M2 (dim solid)** for a cleaner stage look, M3 if mismatch is distracting.
This is purely a cloud-side action on `strip_light_mirror` and doesn't need the second
strip to be realtime-proven. **[ASSUMED — needs a visual decision]**

---

## 8. Test plan

### 8.1 Pure-unit (no network, no bridge)
| Test | Verifies |
|------|----------|
| Packet byte layout | `header(5)+seg_count+RGB×N+XOR` exact bytes, **pinned to the proven fixture** |
| XOR checksum | known frame → known checksum |
| Base64/JSON wrapper | `{"msg":{"cmd":"razer","data":{"pt":…}}}` shape |
| `send_frame` length guard | rejects ≠ `segments` |
| RGB clamping | values <0 / >255 clamped |
| Renderer output shape | each of 5 effects → exactly 20 tuples |
| Renderer ranges | all channels 0–255 |
| Renderer determinism | same (phase,params) → same frame |

### 8.2 Config / model
| Test | Verifies |
|------|----------|
| `"realtime"` accepted | config with a realtime look loads (no `invalid_config`) |
| backend default | target/look without `backend` ⇒ `cloud_diy` |
| realtime defaults | absent `realtime` block ⇒ `enabled=false` |
| cross-check | realtime look targeting a non-realtime target ⇒ `invalid_config` |
| proven target enabled | `room_perimeter.realtime.enabled == true` |
| second strip disabled | `strip_light_mirror.realtime.enabled == false` |
| **backend threads through** | look→decision→command all carry `backend`/`params` |
| **live-config still loads** | existing `led_look_director.json` loads unchanged after model/validator edits |

### 8.3 Owner / dispatch
| Test | Verifies |
|------|----------|
| transitions | NONE↔CLOUD_DIY↔REALTIME_RAZER valid/invalid moves |
| cloud blocked under realtime | cloud command no-ops while owner==REALTIME (reason recorded) |
| blackout always wins | force_release + blackout from every state |
| handoff ordering | cloud→rt: acquire→activate→loop; rt→cloud: stop→deactivate→release→cloud |

### 8.4 Regression
`python -m pytest tests/` — **zero** regressions. Pay attention to
`test_govee_scene_adapter.py`, `test_govee_runtime_sender.py`, `test_led_config.py`,
`test_led_look_director.py`, `test_led_state_manager.py`. **[CONFIRMED these exist]**

### 8.5 Manual (live, single strip)
1. Existing cloud look on proven strip → unchanged.
2. `rt_beat_chase_red` → red chase locked to beat.
3. `rt_beat_strobe_white` → white strobe on beat subdivisions.
4. cloud→realtime → clean, no flicker.
5. realtime→cloud → deactivate then cloud scene.
6. End realtime, wait 5 s → no zombie frames; **no cloud automation stomping** (validates §6).
7. cloud look on second strip → unaffected.
8. Emergency blackout during realtime → instant black, owner released.
9. **Mirror behavior** during realtime matches the chosen M1/M2/M3.

---

## 9. Venue-strip realtime proof (REQUIRED for live gigs, not optional)

> Because realtime is LAN-bound (§0), the home-strip proof does **not** transfer to the
> venue. To run realtime *at the venue*, the **venue** strip (`54:2C…`,
> `strip_light_mirror`) must pass this proof **on the venue LAN**, and its venue IP must
> be captured (it will differ from the home `192.168.0.219`). Until then, realtime is a
> home-only capability and the venue runs cloud DIY as today.

Gate to flip `strip_light_mirror.realtime.enabled`:
LAN scan finds IP → device-id match `54:2C…` → SKU → `devStatus` → brightness/colorwc →
razer solid R/G/B → razer chase → razer strobe → segment count → working header. All ten
pass before `enabled=true`.

---

## 10. Risks & open questions

| # | Item | Severity | Note |
|---|------|----------|------|
| R1 | **Live-config migration** redirecting the show to the unproven strip | **High** | Avoided by Option C (§3). Do **not** remap `room_perimeter.device_ref`. |
| R2 | **Cloud automation stomping realtime** | **High** | Owner lock must gate the cloud dispatch path, not just new code (§6). |
| R3 | **DHCP IP drift** for `192.168.0.219` | Medium | Hard-coded in config; a lease change silently breaks realtime. Recommend a DHCP reservation on the router, or a discovery fallback (out of scope now but note it). **[ASSUMED]** |
| R4 | **Beat-phase source** at 30 fps | ~~Medium~~ **Resolved** | Beat clock already computed by StateManager (OS2L `beatpos`). Runner reuses deck/elapsed/bpm/beatgrid + `beat_math._compute_beat_pos`, interpolated with `monotonic()`. See §5.3. **[CONFIRMED]** |
| R5 | **Mirror freeze** during realtime | Low/visual | Pick M1/M2/M3 (§7.4). |
| R6 | **Proof values are external** to the repo | Low | Pin packet/activate bytes in a fixture so drift is caught (§8.1). |
| R7 | LAN razer + cloud HTTP racing on the same device during handoff | Medium | Strict acquire→activate / stop→deactivate→release ordering; never overlap (§7). |
| R8 | **Realtime is LAN/location-bound** | **High** | Realtime only reaches the strip on the bridge's current network. Venue realtime needs the §9 proof + venue IP. The realtime `ip` must be selected per-location (home vs venue), e.g. by environment/profile, not hard-pinned to `192.168.0.219`. |

### Decisions needed from the operator
1. **Migration option** — C (recommended, minimal), A (rename, separate commit), or B (reject). **Blocking.**
   - Given the home/venue model, consider renaming to `home_strip` / `venue_strip` (clearer than
     `room_perimeter` / `strip_light_mirror`) — but only under Option A's separate, tested commit.
2. **Mirror-during-realtime** — moot for audience (only one location is ever physically present);
   **M1 (leave as-is)** is fine. Real question: keep cloud mirroring on at all during testing?
3. **Cloud-under-realtime** — drop cloud commands (recommended) vs treat as handoff request.
4. **Confirm the home/venue ↔ device mapping** (`C1:0A`=home, `54:2C`=venue). The whole
   location-bound analysis rests on it.

---

## 11. Suggested build order (for Codex)

1. Models + validator + config builder (`led_models.py`, `led_config.py`) — add fields,
   `"realtime"` action, thread `backend`/`params`. Land with config/model tests green and
   the **existing live config still loading**. (No behavior change yet.)
2. `GoveeRealtimeTransport` (pure UDP) + unit tests pinned to the proven fixture.
3. `GoveeFrameRenderer` (5 effects) + unit tests.
4. `GoveeOwnerStateMachine` + tests.
5. `GoveeRealtimeRunner` (thread/clock) + beat-source wiring per §5.3 (R4 resolved):
   hook the StateManager tick path, anchor on `(elapsed_ms, bpm, first_beat_ms, monotonic())`,
   interpolate phase at 30 fps via `beat_math._compute_beat_pos`.
6. Dispatcher (R1) + owner gating of cloud path + `__main__.py` wiring.
7. Config: Option C edits (add `realtime` block + `backend` to proven target; `realtime.enabled:false`
   on second strip; example `rt_*` looks).
8. Manual live verification (§8.5).

Per project convention (memory: *bridge code → Codex; Claude = evidence/analysis/planning*),
this document is the planning artifact; implementation goes to Codex.
```
