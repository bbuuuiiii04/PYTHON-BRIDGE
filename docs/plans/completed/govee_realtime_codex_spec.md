# Govee Realtime (Razer/DreamView) — Codex Implementation Spec (Phase 2)

> **For:** Codex (implementer). **Author:** planning/analysis pass, reviewed by 3 adversarial
> sub-agents against the live repo. **Repo:** `/Users/bbui/rb_ss_bridge_v2/` (Python, pytest).
> **Status of facts:** every load-bearing claim below was verified against the actual code and
> is marked **[CONFIRMED]**; a few **[DECIDE]** items need an operator call (listed in §15).
>
> **Source-of-truth files (read these first):**
> - Protocol reference (PORT VERBATIM): `experiments/govee_h612d_realtime_probe/razer_realtime_probe.py`
> - Companion probes: `experiments/govee_h612d_realtime_probe/{play_effects,lan_basic_control,lan_scan}.py`
> - Architecture rationale: `docs/govee_realtime_design.md`
> - High-level plan: `~/.claude/plans/shiny-scribbling-hedgehog.md`

---

## 1. Goal & guardrails

Add a **realtime "razer"/DreamView backend** (LAN UDP, 30 fps, beat-synced) to the LED Look
Director, alongside the existing **cloud DIY** path, for the **home** strip
(`C1:0A:DA:B9:81:C6:3C:02`, target `room_perimeter`, IP `192.168.0.219`). Realtime is
**LAN/location-bound** → home-only until the venue strip is independently proven. The whole
feature is behind `RBSS_GOVEE_REALTIME` (default **off**); off ⇒ behavior identical to today.

**Hard constraints (do not violate):**
- The bridge tick thread runs at **200 Hz / 5 ms budget** (`state_manager.py:290`,
  `_TICK_INTERVAL = 1.0/200`). **No network I/O, no `.join()`, no blocking lock on the tick
  thread, ever.** All LAN sends happen on the runner's own thread.
- Existing cloud DIY path, looks, and tests must be untouched/green.
- Transport knows nothing about BPM/cues. Renderer is pure/stateless.

---

## 2. Architecture (verified sound)

```
LEDLookDirector.tick() → LEDLookDecision(backend,...) 
        │  (StateManager calls this at 4 sites, deduped by role_key)
        ▼
LEDDispatchCoordinator.trigger(decision)        ← NEW; wraps the adapter, duck-types trigger/status/shutdown/close
        ├── backend == cloud_diy  → GoveeSceneAdapter.trigger()  (UNCHANGED queue/worker → cloud HTTP)
        └── backend == realtime_razer → GoveeRealtimeRunner.set_desired(spec)   (actor; non-blocking)
                                              │
                              runner thread @ 30 fps:
                                pull BeatAnchor (incl. permitted flag) ── from StateManager.get_active_beat_anchor()
                                render frame ── GoveeFrameRenderer (pure)
                                send ── GoveeRealtimeTransport (UDP)   ← PORT from razer_realtime_probe.py
        owner coordination ── GoveeOwnerStateMachine (NONE|CLOUD_DIY|REALTIME_RAZER)
```

**Why a wrapper:** all four dispatch sites call `self._led_scene_adapter.trigger(decision)`
(`state_manager.py:1228,1308,1491,1625`); the adapter is injected via the StateManager ctor
param `led_scene_adapter=` (`:302-318`); `.status()` (`:608`) and `.shutdown()`
(`__main__.py:1185`) are the only other calls. **[CONFIRMED]** A coordinator implementing
`trigger/status/shutdown/close` substitutes transparently. The automation path is deduped by
`role_key` (`state_manager.py:1433`) so `trigger()` fires only on look changes — the runner
(not repeated triggers) sustains the effect. **[CONFIRMED]**

---

## 3. Exact wire protocol — PORT from the proof, do not re-derive

`razer_realtime_probe.py` is the proven implementation (`confirmed_visual_pass` 2026-06-13).
**Port these functions verbatim** into `govee_realtime_transport.py` and pin a test against
their output. Verified facts:

- **Frame packet** (`build_frame_packet`, probe lines 67-84):
  `header(5) + seg_count(1) + [R,G,B]×N + xor(1)`.
  - `seg_count = len(segments)` (the **count**, e.g. `20` = `0x14`; NOT byte length). **[CONFIRMED]**
  - Channel order **R,G,B**, each `& 0xFF`. **[CONFIRMED]** (no GRB swap)
  - **XOR is over the ENTIRE packet so far** — header + seg_count + all RGB — seed `0`, result
    appended as the final byte (`xor_checksum`, lines 59-64; called on the full list line 81). **[CONFIRMED]**
- **Header bytes** (`HEADERS["dreams"]`): `[0xBB,0x00,0xFA,0xB0,0x00]`. `header` string
  ("dreams") is just the variant name selecting these wire bytes; `header_bytes` IS the wire
  value. **[CONFIRMED]** Use `dreams` (the proven one).
- **`stretch`**: sets header **byte index 4** to `0x01` (probe lines 377-378); default `0x00`.
  So stretched dreams header = `BB 00 FA B0 01`. **[CONFIRMED]**
- **Activate** razer mode: literal payload `BB 00 01 B1 01 0A` → base64 `"uwABsQEK"`.
  **Deactivate**: `BB 00 01 B1 00 0B` → `"uwABsQAL"`. These are fixed 6-byte payloads (NO
  seg_count/XOR). **[CONFIRMED]**
- **Brightness** is a **UDP** command, not cloud: `{"msg":{"cmd":"brightness","data":{"value":100}}}`
  to `ip:4003` (probe lines 257-259). **[CONFIRMED]** → non-blocking; safe.
- **JSON wrapper** for frames/activate: `{"msg":{"cmd":"razer","data":{"pt":"<base64(packet)>"}}}`
  (probe lines 92-96). Sent via `sock.sendto(json_bytes, (ip, 4003))`.
- **Socket** (probe line 370): `socket.socket(socket.AF_INET, socket.SOCK_DGRAM)`. For
  production: create **once** in `__init__`, **`setblocking(False)`**, **no `connect()`**,
  `sendto(data, (ip, port))` per frame, catch `(BlockingIOError, OSError)` → increment
  `send_error_count`, **never raise** out of the frame loop.

**Pinned-fixture test:** port `xor_checksum`/`build_frame_packet` and assert a known vector,
e.g. `build_frame_packet([0xBB,0x00,0xFA,0xB0,0x00], [(255,0,0)]*20)` equals the bytes the
reference produces (compute once by running the reference; hard-code the expected `bytes`).
Also assert `len == 5+1+60+1 = 67`, and that `send_frame` length-guards `len(segments)==segments`.

---

## 4. New files

| File | Responsibility |
|------|----------------|
| `govee_realtime_transport.py` | Pure UDP. Ports §3. `__init__(ip,port=4003,segments=20,header_bytes=(...),stretch=False)`, `activate()`, `deactivate()`, `set_brightness(v)`, `send_frame(rgb_list)` (validates `len==segments`, clamps 0–255), `blackout()`, `close()`, static `build_packet`/`xor_checksum`. No bridge imports. |
| `govee_frame_renderer.py` | Pure. `render(name,*,beat_pos,local_t,frame_index,params,segments,seed)->list[(r,g,b)]`. `_EFFECTS: dict[str,fn]` registry. Unknown name → all-black (never raise). Clamps. See §10. |
| `govee_owner_state.py` | `OwnerState{NONE,CLOUD_DIY,REALTIME_RAZER}`; `GoveeOwnerStateMachine.{acquire,release,current,force_release}` under a `threading.Lock`. See §8. |
| `govee_realtime_runner.py` | Owns transport+renderer + one daemon thread @ `fps`. Actor: `set_desired(spec|None)`, `emergency_stop()`, `set_beat_provider(fn)`, `start()`, `stop()`. Reconciles desired↔actual; self-pauses on `permitted=False`. See §7. |
| `led_dispatch_coordinator.py` | Wraps adapter; routes by `decision.backend`; owner handoffs; `trigger/status/shutdown/close`. See §8. |
| tests | `test_govee_realtime_transport.py`, `test_govee_frame_renderer.py`, `test_govee_owner_state.py`, `test_govee_realtime_runner.py`, `test_led_dispatch_coordinator.py`. See §13. |

---

## 5. Data-model changes — `led_models.py` (APPEND-ONLY)

All four models are `@dataclass(frozen=True)`; **append** new fields after existing ones (never
reorder — preserves positional construction; all current call sites use kwargs anyway
**[CONFIRMED]**). Add:

```python
@dataclass(frozen=True)
class LEDRealtimeConfig:
    enabled: bool = False
    protocol: str = ""                 # "razer_dreamview"
    ip: str = ""
    port: int = 4003
    segments: int = 20
    header: str = ""                   # "dreams"
    header_bytes: tuple[int, ...] = () # (187,0,250,176,0)
    stretch: bool = False
    fps: int = 30
    activate_pt: str = ""              # "uwABsQEK"
    deactivate_pt: str = ""            # "uwABsQAL"
    proof_status: str = "not_proven"
    proof_date: str = ""
```
- `LEDTarget`: append `backend: str = "cloud_diy"`, `realtime: LEDRealtimeConfig = LEDRealtimeConfig()`.
- `LEDLook` **and** `LEDLookDecision`: append `backend: str = "cloud_diy"`,
  `params: Mapping[str, Any] = field(default_factory=dict, compare=False)`.
  `compare=False` keeps the frozen `__hash__`/`__eq__` valid with a dict field. **[CONFIRMED safe]**

> **DO NOT add `backend`/`params` to `LEDAdapterCommand`.** The coordinator consumes the
> **decision** and routes realtime *before* the adapter; the adapter only ever sees cloud
> commands. The design-doc test "backend threads through to command" is **removed** — it would
> require editing `govee_scene_adapter.py:109` (which stays Protected). **[Resolves review B6/B1]**

---

## 6. Beat anchor — snapshot the ALREADY-COMPUTED beat position (critical correctness fix)

**Do NOT recompute phase from `d.meta.bpm`.** The hot path's effective BPM and beat position
(`state_manager.py:2546-2571`) flow through autoloop-arm BPM override + `apply_live_bpm_follow`,
and during autoloop mode use `_compute_beatgrid_position(elapsed_ms, beatgrid_times_ms)` (grid),
**not** `_compute_beat_pos(d.meta.bpm,...)`. Live-BPM-follow / autoloop are LIVE in production, so
recomputing from meta.bpm would visibly drift the LEDs off the SoundSwitch beat. **[CONFIRMED]**

**Implement:**
1. In the LED automation dispatch (`_dispatch_led_automation`, the gate region
   `state_manager.py:1386-1414`), compute a per-tick snapshot once: set
   `self._led_rt_permitted = True/False` — `False` on **every** gated early-return
   (`not_configured, disabled, automation_disabled, emergency_blackout, manual_override,
   scripted_mode, not_ready/not playing, position_stale, not_autoloop, autoloop_not_ready`),
   `True` when dispatch proceeds.
2. Where the OS2L `beat_pos` + effective `bpm` are computed (`state_manager.py:~2554`), store
   `self._led_rt_beat = (beat_pos, abs_beat_pos, effective_bpm, time.monotonic())` so realtime
   locks to the **same** beat as SoundSwitch.
3. Add read-only `get_active_beat_anchor() -> Optional[BeatAnchor]` returning a snapshot of
   `(deck, abs_beat_pos, effective_bpm, captured_monotonic, playing, permitted)`; return `None`
   when `not permitted` or no track. This is the runner's sole bridge dependency.

```python
@dataclass(frozen=True)
class BeatAnchor:
    deck: int
    abs_beat_pos: float        # already-computed; runner advances it
    bpm: float                 # effective (live-follow/arm aware)
    captured_monotonic: float
    playing: bool
    permitted: bool
```
Runner interpolation each frame: `pos = abs_beat_pos + (monotonic()-captured_monotonic) * (bpm/60.0)`;
`phase_in_beat = pos % 1.0`; `bar = int(pos) % 4`.

> **Honest scope note:** this is two tiny hot-path writes (a bool + a tuple assignment) plus one
> read-only getter — *not* "zero hot-path change." It is required to (a) lock LEDs to the real
> musical beat and (b) tell the runner when to stand down (§7). Both writes are single
> assignments; negligible at 200 Hz. **[Resolves review B5/S1 + Agent-2 B1]**

---

## 7. The runner (`GoveeRealtimeRunner`) — actor + self-governing

One daemon thread. Tick-thread callers (`set_desired`, `emergency_stop`) only store intent.

**State:** `_desired_spec: EffectSpec|None`, `_active: bool`, `_emergency: threading.Event`,
`_beat_provider: Callable[[], Optional[BeatAnchor]]` (late-bound, may be `None` until wired),
`_idle_since: float|None`. `EffectSpec = (effect_name, params, seed, applied_monotonic)`.

**`set_desired(spec|None)`** (tick thread): store under a short lock; if spec changes effect,
reset `applied_monotonic` (the one-shot/local clock origin). Non-blocking.

**`emergency_stop()`** (tick thread): `self._emergency.set()`. Non-blocking.

**Frame loop (runner thread), each ~1/fps:**
```
if _emergency.is_set():
    if _active: transport.blackout(); transport.deactivate(); _active=False
    _desired_spec=None; sleep; continue        # immediate dark, no grace
spec = _desired_spec; anchor = _beat_provider() if _beat_provider else None
permitted = anchor is not None and anchor.permitted and anchor.playing
if spec is None or not permitted:
    # graceful stand-down with a small grace to avoid flicker on transient gates
    if _active:
        if _idle_since is None: _idle_since = monotonic()
        if monotonic() - _idle_since >= GRACE_S (e.g. 0.25):
            transport.deactivate(); _active=False; _idle_since=None
        else:
            transport.send_frame(last_frame)   # hold last frame, razer still active
    sleep; continue
_idle_since = None
if not _active: transport.activate(); transport.set_brightness(100); _active=True
pos = anchor.abs_beat_pos + (monotonic()-anchor.captured_monotonic)*(anchor.bpm/60)
local_t = monotonic() - spec.applied_monotonic
frame = renderer.render(spec.effect_name, beat_pos=pos, local_t=local_t,
                        frame_index=_fc, params=spec.params, segments=segments, seed=spec.seed)
if _emergency.is_set(): continue               # re-check immediately before send
transport.send_frame(frame); last_frame=frame; _fc+=1
```

- **Stuck-light fix:** because `permitted` goes `False` on every gated exit (§6), the runner
  stands down even though no `trigger()` fired on those paths. Deactivating razer returns the
  strip to its last cloud state (razer is an overlay). **[Resolves Agent-2 B1]**
- **Emergency:** checked at loop top AND immediately before `send_frame` → dark within one
  frame, independent of the cloud blackout. **[Resolves Agent-2 B2/S2]**
- **Idle frame** = hold last rendered frame during the grace window, then deactivate. **[Resolves S3]**
- Socket errors counted, never raised. `start()` spawns the thread; `stop()` sets a stop event,
  sends blackout+deactivate, joins with a bounded timeout (~1 s).

---

## 8. Coordinator & owner

`GoveeOwnerStateMachine`: enum `NONE|CLOUD_DIY|REALTIME_RAZER`, all methods under one
`threading.Lock`. `acquire(REALTIME)` succeeds from `NONE`/`REALTIME`; `release(x)` only from
`x`; `force_release()` → `NONE`. **Owner is mutated only by the coordinator (tick thread); the
runner never touches owner.** This keeps `force_release` (emergency) race-free vs `acquire`.
**[CONFIRMED safe given §7 — runner self-pauses via `permitted`, not via owner]**

`LEDDispatchCoordinator.trigger(decision) -> bool` (tick thread, must stay non-blocking):
1. **Operator/emergency blackout** (`decision.action=="off"` or `decision.look==config.blackout`):
   `runner.emergency_stop()`; `owner.force_release()`; return `adapter.trigger(decision)`
   (cloud blackout enqueues on the adapter worker — non-blocking **[CONFIRMED]**). This is the
   always-on hard kill.
2. **`backend=="realtime_razer"`**: `owner.acquire(REALTIME_RAZER)`;
   `runner.set_desired(spec_from(decision))`; return `True`.
   - realtime→realtime: just `set_desired(new spec)` — no deactivate/reactivate; owner stays.
3. **`backend=="cloud_diy"`**:
   - if `owner.current()==REALTIME_RAZER`: `runner.set_desired(None)` (runner deactivates on its
     thread), `owner.release(REALTIME_RAZER)`, then `adapter.trigger(decision)`.
   - else: `adapter.trigger(decision)` (today's path, byte-for-byte).

**`tactical_blackout()`** (NEW, for realtime drops — see §9). Called by the smart-drop dispatch
*instead of* `trigger(config.blackout)` **only when the DROP role is realtime**. Acquires razer
if not already owned (activating the transport if `buildup` was cloud), then asks the runner to
hold black for the pre-drop window: `owner.acquire(REALTIME_RAZER)` +
`runner.set_desired(EffectSpec("blackout", {}, ...))` — **no** `emergency_stop`, **no**
`owner.release`, **no** cloud command. The subsequent realtime drop look swaps in via branch 2
with razer never deactivating. (When the drop is cloud, the dispatch uses the normal cloud
blackout instead.) Distinguishing the tactical case from the operator emergency (branch 1) cannot
be done from the decision alone — both surface as `source="emergency"` **[CONFIRMED:
`_dispatch_led_smart_drop_blackout` sets context `emergency_blackout=True` → tick returns
role/source "emergency"]** — so the **caller** selects the method based on the drop role's
backend, per §9.

`spec_from(decision)` = `EffectSpec(decision.scene_ref, dict(decision.params), seed=stable_hash(decision.look), applied_monotonic=monotonic())`.

`status()` returns the adapter's status dict **plus** a `realtime` sub-block (owner state,
runner active, frames_sent, send_error_count, last_error). `shutdown()/close()` →
`runner.stop()` **then** `adapter.shutdown()`. **Lock ordering:** never hold the owner lock
while joining the runner thread. **[Resolves Agent-2 S3]**

---

## 9. Realtime drops — continuous-ownership design (the whole point of the feature)

**The hazard is the backend *switch* at the drop, not the drop effect.** Today the smart-drop
system injects a **cloud** pre-drop blackout (`_dispatch_led_smart_drop_blackout`,
`state_manager.py:1243`, forces context `emergency_blackout=True` -> `config.blackout` = cloud
`room_blackout` **[CONFIRMED]**), then ~1-2 beats later the `drop` role fires. If `drop` is
realtime, every drop becomes a **cloud->realtime handoff at the most visible moment**, across two
networks to one strip: the cloud blackout's HTTPS call can land *late, on top of the running
razer chase*, blinking the drop to black. The runner cannot prevent a slow HTTP call from the
prior step. This coupling is already flagged deferred in the live config
(`metadata.future_requirements: ["smart_drop_blackout_coupling_deferred_until_later_phase"]`
**[CONFIRMED]**). **[Agent-2 B3/S1]**

**Clarifying the constraint:** the strip is one output — at any instant it shows *either* the
razer stream *or* a cloud scene, never both. Switching is a handoff; handoffs are fine **when
there is timing room**. The *only* fragile spot is a **cloud** command issued in the tight ~1-2
beat window right before the drop: cloud goes over the internet (variable lag, often > the
blackout->drop gap), so it can land late and stomp the razer drop. It is a *timing* problem with
the cloud path, not an incompatibility. A *blackout* needs no cloud at all — razer renders black
instantly and on-beat — so the fix is to render the pre-drop blackout in razer.

**Solution - razer must own the strip continuously through the `pre_drop -> drop` window** (so the
pre-drop blackout is a razer frame and no cloud command is in flight at the drop). Two parts:

1. **Contiguous realtime through the drop (authoring rule, enforced in §11):** if `drop` is
   realtime, then **`pre_drop` must also be realtime** (razer owns the strip before the blackout).
   `buildup` is **free** — it may be cloud (the cloud->razer handoff then happens at the
   `buildup->pre_drop` boundary, which has timing room) or razer (fully continuous). `post_drop`
   is recommended-razer but may be cloud (the razer->cloud handoff after the drop is low-risk,
   bounded to ~1 frame by §7). `ambient`/`utility` stay cloud-only. *(The exact safe span is
   confirmed by the live-drop test, PR-11.)*
2. **Resolve the smart-drop blackout coupling (the one real new piece):** make the smart-drop
   dispatch **backend-aware, keyed on the DROP role's backend** (a static config fact, known at
   pre_drop time since banks are homogeneous per role) — **not** merely on who currently owns the
   strip:
   - **drop role is realtime** → `_dispatch_led_smart_drop_blackout` calls
     `coordinator.tactical_blackout()` (§8): razer is acquired/kept and renders the pre-drop dark
     as a **razer black frame**; razer never deactivates; the `drop` realtime look swaps in
     frame-accurately. No cloud command at the drop → no race; the dark is **beat-locked**.
   - **drop role is cloud** → the pre-drop blackout takes the **normal cloud path**
     (`trigger(config.blackout)`), which *also* serves as the razer→cloud handoff if `buildup` was
     razer. (Example: razer buildup → cloud blackout → cloud drop → razer groove — the blackout is
     cloud, the only switches are razer→cloud at buildup-end and cloud→razer at drop→groove,
     neither in the tight drop window.)

**Operator emergency blackout is unaffected** - the manual `LED_BLACKOUT` path and any
`action:"off"` still hit coordinator branch 1 (hard kill: `emergency_stop` + deactivate + cloud),
always available regardless of ownership.

**Sequencing:** build/prove the pipe on `groove`/`buildup` first (low-stakes), then add the
smart-drop coupling (part 2) and **live-test at real drops on the home strip** before trusting it
in a set. This is the trickiest concurrency in the feature; isolate it as the final build step.

**StateManager touch points for part 2** (backend-aware smart-drop):
`_dispatch_led_smart_drop_blackout` (`state_manager.py:1243-1308`, `:1422`) gains a branch keyed
on **"is the `drop` role's bank realtime?"** (a static lookup on the active bank's `drop` list —
homogeneous per role): if realtime → `coordinator.tactical_blackout()`; else the existing cloud
`trigger(config.blackout)` path (unchanged, and it doubles as the razer→cloud handoff when
`buildup` was razer). Helper e.g. `config_drop_role_is_realtime()` on the config. Keep it
non-blocking.

---

## 10. Effect set (~10) — exact contracts

`render(name,*,beat_pos,local_t,frame_index,params,segments,seed)`. Colors are `[r,g,b]`
ints 0–255; clamp all output. `bg` default `[0,0,0]`. Unknown `name` → all-black, no raise.
Registry `_EFFECTS: dict[str, fn]`.

| name | params (defaults) | formula |
|------|-------------------|---------|
| `solid` | `color` | every seg = color |
| `blackout` | — | every seg = (0,0,0) |
| `beat_chase` | `color, bg, trail=3, span_beats=1.0` | `head=int(((beat_pos%span_beats)/span_beats)*segments)`; seg i: fwd dist `d=(i-head)%segments`; `d==0`→color, `d<=trail`→color·`(1-d/(trail+1))`, else bg |
| `beat_strobe` | `color, subdivision=4, duty=0.5` | `on = ((beat_pos*subdivision)%1.0) < duty`; all segs = color if on else (0,0,0). **subdivision capped ≤8; requires allow_strobe** |
| `drop_burst` | `color, bg, decay=0.6` | one-shot: `b=exp(-local_t/decay)`; all = lerp(bg,color,b); `local_t>4·decay`→bg (terminal) |
| `breathe` | `color, period_beats=4.0, floor=0.1` | `b=floor+(1-floor)·(0.5-0.5·cos(2π·beat_pos/period_beats))`; all=color·b |
| `gradient_sweep` | `color_a, color_b, speed=1.0` | `off=(beat_pos·speed)%1.0`; seg i: `t=((i/segments)+off)%1.0`; lerp(color_a,color_b, triangle(t)) (linear RGB) |
| `sparkle` | `color, bg, density=0.2` | `rng=random.Random((seed,frame_index))`; per seg color if `rng.random()<density` else bg |
| `color_pulse` | `color, bg` | `b=max(0,1-(beat_pos%1.0)/0.5)`; all=lerp(bg,color,b) (sharp attack each beat) |
| `bar_wipe` | `color, bg` | `filled=int(((beat_pos%4)/4)·segments)`; seg i<filled→color else bg |

Determinism: `sparkle` is the only stochastic one and is seeded by `(seed, frame_index)`
**[Resolves B3/B4/S4]**. Default `seed = stable_hash(look_name)`.

---

## 11. Config (`led_config.py`) — schema + validation

- Add `"realtime"` to `_LOOK_ACTIONS` (`:47`). **[CONFIRMED required, else config = invalid → LED off]**
- `_build_config` (`:527-560`): populate new `LEDTarget.backend/realtime` and
  `LEDLook.backend/params`, else they vanish. For `realtime`, parse the nested block;
  `header_bytes` arrives as a JSON **list** → store `tuple(int(b)&0xFF for b in ...)`. Freeze
  `params` via `MappingProxyType(dict(...))` so the shared config isn't mutated downstream. **[S5]**
- `_validate_look`: for `action=="realtime"` require `backend=="realtime_razer"`, non-empty
  `scene_ref` naming a known effect, valid `params` (see clamps). **Strict param-key check:**
  reject unknown keys inside a realtime look's `params` (typos like `colour`). **[Resolves S7]**
- `_validate_target`: if `realtime.enabled==true`, require non-empty dotted-quad `ip`,
  `1≤port≤65535`, `segments≥1`, `len(header_bytes)>0` (each 0–255), non-empty
  `activate_pt`/`deactivate_pt`. **[Resolves B8]**
- **Cross-checks** (key off `realtime.enabled`, NOT target `backend` — the proven strip is
  `backend:cloud_diy` + `realtime.enabled:true`, dual-backend **[CONFIRMED]**):
  - a look with `backend:"realtime_razer"` must target a target with `realtime.enabled==true`.
  - **`config.blackout` and `config.safe_default` must be `backend:"cloud_diy"`** (the blackout
    path uses the cloud adapter). **[Resolves B7.2]**
  - a look's `fallback` must share the look's backend (no cross-backend fallback). **[B7.3]**
  - **Backend-homogeneous + drop-window rule (§9):** within a bank, each role list must be all
    one backend (no mixing). `ambient` and `utility` must stay **cloud-only**. **Drop window:** if
    `drop` is realtime, then **`pre_drop` must also be realtime** (razer owns the strip before the
    pre-drop blackout → the blackout is a razer frame, no cloud command at the drop). `buildup`
    and `post_drop` may be **either** backend (handoffs at the `buildup→pre_drop` / `post_drop→…`
    edges have timing room). Reject only a realtime `drop` paired with a cloud `pre_drop`. Empty
    role lists are compatible with either backend. **[Resolves B7.1; enables realtime drops per §9]**
- `_validate_live_ready` (`:446`) unchanged; realtime actions skip scene_ref placeholder checks
  (not in scene/music/diy set) — **[CONFIRMED no regression]**. Confirm `realtime` block keys
  don't trip `_SECRET_KEY_TOKENS` (they don't — no `token/secret/bearer/...` substring; keep
  `activate_pt`, do **not** rename to `auth_*`). **[CONFIRMED]**
- Numeric clamps: RGB 0–255; `beat_strobe.subdivision ∈ {1,2,4,8}`; strobe effects require
  `look.allow_strobe and safety.allow_strobe`. (30 fps inherently caps flash ≤ ~15 Hz.)

`led_look_director.py`: `_decision_for_look` (`:201-220`) copies `backend` and `params` onto
the `LEDLookDecision`. No policy change. **[CONFIRMED this is the decision, distinct from the
command in §5]**

---

## 12. Wiring (`__main__.py`) + flag + shutdown + crash

- Flag: `RBSS_GOVEE_REALTIME` read as `os.environ.get("RBSS_GOVEE_REALTIME")=="1"` (house
  pattern, cf. `__main__.py:1161`). **[CONFIRMED]**
- In `_build_led_startup_wiring` (`:360-408`):
  - flag **off** OR no target with `realtime.enabled` → build the plain `GoveeSceneAdapter` and
    pass it as today (zero change). `get_active_beat_anchor`/`_led_rt_*` are dead.
  - flag **on** → build `owner`, `transport`(s) from the enabled target(s), `renderer`,
    `runner` (with `beat_provider=None` for now), and `coordinator = LEDDispatchCoordinator(adapter, runner, owner, config)`.
    Pass the **coordinator** as `led_scene_adapter` into `StateManager(...)`.
- **Two-phase late-bind (resolves the build-order cycle):** the coordinator/runner are built at
  `:360-408` but `sm` (and `sm.get_active_beat_anchor`) only exists at `:681`. After `sm` is
  constructed and **before `sm.start()`**, call `runner.set_beat_provider(sm.get_active_beat_anchor)`
  and `runner.start()`. Until bound, the runner's provider is `None` ⇒ it stays idle (safe).
  Precedent: `RBMemoryReader` receives `sm.get_active_deck`/`get_deck_elapsed_ms` post-construction
  (`__main__.py:1037-1038`). **[Resolves B2/S2]**
- **Crash recovery:** at runner construction (before `sm.start()`), best-effort send
  `deactivate` to each configured realtime `ip` (UDP fire-and-forget; harmless if absent) so a
  strip left frozen by a hard kill returns to cloud control. **[CONFIRMED ordering + harmless]**
- Shutdown: the existing `led_scene_adapter.shutdown()` (`:1185`) now hits the coordinator →
  `runner.stop()` then `adapter.shutdown()`. (`close()` is implemented for parity but unused at
  teardown. **[CONFIRMED]**)
- **Operator status visibility:** the status sanitizer `_sanitize_led_adapter_status`
  (`state_manager.py:616`) is an **allow-list** (`_LED_ADAPTER_STATUS_SAFE_KEYS`) — extend it
  with the new `realtime` sub-block keys, or they're silently dropped from the operator payload.
  **[Resolves S2/Agent-1]**

---

## 13. Tests (match house style in `tests/test_govee_*`, `tests/test_led_*`)

**Pure-function seams — all unit tests run with NO real socket/thread/clock:**
- Transport: `build_packet`/`xor_checksum` pinned vector (§3); `send_frame` length guard;
  RGB clamp; activate/deactivate/brightness JSON shape. Inject a fake socket.
- Renderer: each of the 10 effects → exactly `segments` tuples, 0–255; deterministic for fixed
  `(beat_pos, local_t, frame_index, params, seed)`; `sparkle` reproducible; `beat_strobe`
  honors subdivision cap; `drop_burst` decays to bg after `4·decay`; unknown name → all-black.
- Owner: all transitions + `force_release`.
- Runner: **expose a synchronous `_tick_once(anchor, now)`** so tests drive frames without the
  daemon thread/sleep. Fake transport + fake provider + injected monotonic. Assert: activate on
  first permitted spec; swap without re-activate; `permitted=False` → hold then deactivate after
  grace; `emergency_stop` → blackout+deactivate immediately (even mid-spec); socket error
  doesn't kill the loop.
- Coordinator: cloud→realtime, realtime→realtime swap, realtime→cloud handoff, operator-blackout-
  from-realtime (hard kill); **`tactical_blackout()` keeps owner=REALTIME, no cloud command, no
  deactivate** (§9); cloud-while-realtime never reaches `adapter.trigger`; duck-typed
  `trigger/status/shutdown` parity. Use a fake adapter + fake runner.

**Config/model:** realtime action accepted; defaults; homogeneous-bank rule; **contiguous-span
rule** (realtime `drop` requires realtime `buildup`/`pre_drop`/`post_drop`; reject a realtime
`drop` with a cloud `buildup`); `ambient`/`utility` must-be-cloud; blackout/safe_default-must-be-
cloud; target cross-check on `realtime.enabled`; strict param keys; realtime-block field
validation; `backend`/`params` survive look→decision; **existing live `led_look_director.json`
AND `led_look_director.example.json` still load** (`test_led_config.py` asserts on the example —
update if needed). **[Resolves S6]**

**Smart-drop coupling (drops):** with realtime owning the strip, `_dispatch_led_smart_drop_blackout`
routes to `coordinator.tactical_blackout()` (not a cloud `config.blackout`), razer is **not**
deactivated across pre-drop→drop, and an operator emergency blackout mid-drop still hard-kills.

**StateManager:** unit-test `get_active_beat_anchor()` by setting `sm._deck[d].meta.*`,
`sm._os.active_deck`, `sm._deck[d].playing`, and the `_led_rt_*` snapshot fields, then calling
the getter (harness `_make_sm` supports this **[CONFIRMED]**). Assert `permitted=False` paths
return `None`.

**Regression:** `python -m pytest tests/` green. **Flag-off smoke:** with `RBSS_GOVEE_REALTIME`
unset, LED behavior is identical to today (coordinator not constructed).

**Manual (home strip, flag on):** existing cloud unchanged; a `groove` realtime chase locks to
beat; cloud↔realtime handoff at a groove→buildup transition is clean; emergency blackout →
instant dark; pause deck → strip returns to cloud/idle (no zombie frames); leave autoloop →
realtime stands down.

---

## 14. Build order (independently testable PRs)

1. **Models + config + director field-threading** (§5,§11 minus runner-coupling). Land with
   model/config tests green and **both** existing configs still loading. No runtime change.
2. **`govee_realtime_transport.py`** — port §3 + pinned-fixture tests.
3. **`govee_frame_renderer.py`** — §10 + determinism/clamp/unknown tests.
4. **`govee_owner_state.py`** — §8 + transition tests.
5. **`state_manager.py`** beat-anchor snapshot + `get_active_beat_anchor()` (§6) + unit test.
6. **`govee_realtime_runner.py`** — §7 + synchronous `_tick_once` tests (fake transport/provider).
7. **`led_dispatch_coordinator.py`** — §8 (incl. `tactical_blackout()`, `owner_state()`) + handoff/gating tests.
8. **`__main__.py`** wiring behind the flag (§12) + flag-off regression no-op + status allow-list.
9. **Config Option-C edits** + example `rt_*` looks. **Prove the pipe first** on a `groove`/`buildup`
   test bank at home before enabling drops.
10. **Manual live verification** (groove/buildup).
11. **DROPS (final step):** backend-aware smart-drop coupling (§9 part 2) — `_dispatch_led_smart_drop_blackout`
    routes to `coordinator.tactical_blackout()` when realtime owns; contiguous-span config
    (`buildup→pre_drop→drop→post_drop` realtime); + **live-test at real drops on the home strip.**

PRs 1–6 are isolated/low-risk; risk concentrates in 7–8 (flag-gated) and 11 (the drop coupling —
the trickiest concurrency; isolate and live-test it last).

### Option-C config edits (live `config/led_look_director.json`, gitignored, dry_run:false)
- `room_perimeter` (home, `C1:0A…`): add `backend:"cloud_diy"` + a `realtime` block
  (`enabled:true`, dreams header bytes, `ip:"192.168.0.219"`, `activate_pt`/`deactivate_pt`,
  `proof_status:"confirmed_visual_pass"`). Optionally fix `label`→"Bui Strip Light". No
  look/bank/mirror rewrites.
- `strip_light_mirror` (venue, `54:2C…`): add `realtime:{enabled:false,proof_status:"not_proven"}`.
- Add example `rt_*` realtime looks targeting `room_perimeter`. Start in a `groove`/`buildup`
  test bank to prove the pipe; once drops are wired (PR-11), add the contiguous realtime span
  `buildup→pre_drop→drop→post_drop` (per §9). Keep them out of venue-live banks.

---

## 15. Open items needing an operator decision

1. **[DECIDED] Realtime drops = YES (operator confirmed "I want drops").** Delivered via the
   continuous-ownership design (§9): a contiguous realtime span `buildup→pre_drop→drop→post_drop`
   so razer owns the strip with no backend switch at the drop, plus the backend-aware smart-drop
   coupling (`coordinator.tactical_blackout()`). Built as the **final** step (PR-11) on a proven
   pipe and live-tested at real drops. This resolves the long-deferred
   `smart_drop_blackout_coupling`.
2. **[DECIDE] Mirror during realtime.** Operator confirmed there's only ever one physical
   location present, so a frozen "other" strip has no audience cost → **M1 (leave as-is)** is the
   default. Confirm.
3. **[INFO] Hot-path honesty.** Contrary to the earlier "zero StateManager change" framing, §6
   adds two tiny snapshot writes to the tick plus one getter — required to lock LEDs to the live
   musical beat and to stop the runner on gated states. Net change is still small and fully
   flag-gated.

---

## 16. Phase 3 (out of scope — pointer only)
Composable effect *grammar* (primitives × motion × mask × blend, beat-bindable) instead of an
ever-growing catalog; a **headless preview** (`scripts/preview_realtime_cue.py`: render a cue
spec → PNG/GIF with a synthetic beat clock, no hardware) to give the AI authoring loop a
describe→render→adjust feedback cycle; validator-as-guardrail clamping agent-authored params;
venue-strip realtime (needs the independent venue-LAN proof + venue IP). See
`docs/govee_realtime_design.md` §"Phase 3 outline".
```
