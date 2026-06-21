# LED Look Director Integration Plan

Status: Required Integration Plan / Architecture Reference
Target repo context: `rb_ss_bridge_v2` / Rekordbox → SoundSwitch bridge
Required companion orchestrator: `docs/plans/led_agent_orchestrator_workflow.md`
Repo path when promoted with orchestrator: `docs/plans/led_look_director_integration_plan_revised.md`
Precedence: this plan is required for architecture/design context; the orchestrator controls phase order, gates, allowed files, forbidden files, stop conditions, and agent prompts. If either document is stricter about secrets, hot-path safety, StateManager boundaries, or Govee API grounding, apply the stricter rule.
Revision focus: Incorporates architecture corrections from review, especially around `StateManager`, non-blocking output transports, Govee capability discovery, official Govee API grounding, secrets handling, and phase-gated automation safety.

Use this document together with the orchestrator. Do not use this document's phase section as the controlling execution schedule when `docs/plans/led_agent_orchestrator_workflow.md` is present. If there is a conflict, the orchestrator wins for execution control; the stricter safety rule wins for architecture, secrets, hot-path behavior, StateManager boundaries, and Govee API grounding.

Before automation begins, both repo-local documents must exist:

```text
docs/plans/led_agent_orchestrator_workflow.md
docs/plans/led_look_director_integration_plan_revised.md
```

If either document is missing, the automation loop must stop before Phase 1 rather than continuing from memory, copied paths, or stale Desktop/Downloads files.

## 0. Implementation Readiness Verdict

This plan is ready to hand to an implementation agent only when paired with `docs/plans/led_agent_orchestrator_workflow.md`. The orchestrator is the controlling execution document. This integration plan supplies the architecture, creative model, repo-local contracts, config/status/validation expectations, and risk rationale.

Readiness constraints:

```text
Ready for Phase 1:
  yes, if the orchestrator is present and the agent follows its phase gates.

Ready for direct bridge implementation:
  no, not until standalone Govee capability capture and manual live proof pass.

Ready for StateManager changes:
  no, not until the Phase 6 StateManager gate is explicitly approved.

Ready for automatic LED role-entry:
  no, not until Phase 7 StateManager manual/status ownership is implemented and approved.
```

The implementation path must minimize human interruption. Human/operator input is limited to physical LEDs, Govee account/environment setup, Govee app scene creation when required, and visual confirmation of actual LED behavior. Code review, phase approval, rollback decisions, test interpretation, file-scope policing, and API-shape interpretation are AI Supervisor responsibilities.

---

## 1. Big Picture

The bridge should add a separate LED output lane called **LED Look Director**.

This layer should control Govee RGBIC/RGBICW LED strips placed around the event room and crowd. The LEDs are not booth accents. They are the **room envelope**: the lighting layer that wraps the crowd, changes the atmosphere of the room, and supports the energy of the show.

The bridge already has a stable pattern:

```text
StateManager owns runtime coordination.
Policy layers make bounded decisions.
Execution/output layers translate decisions into transport commands.
Actual transport I/O must not block the StateManager hot path.
```

The LED integration should follow that pattern:

```text
Rekordbox state
  → StateManager
  → existing bridge timing / phrasing context
  → LEDLookDirector
  → GoveeSceneAdapter
  → Govee controller
  → RGBIC/RGBICW strips around the room
```

The Govee strips should not be treated as DMX fixtures. They should be treated as **macro scene devices**. The bridge should trigger supported Govee scenes, DIY scenes, snapshots, effects, or fallback basic controls depending on what the actual device exposes.

The goal is not:

```text
Make Govee behave like DMX.
```

The goal is:

```text
At meaningful musical moments, the bridge chooses a room-perimeter LED look and asks Govee to run it without disturbing SoundSwitch, lasers, or bridge timing.
```

---

## 2. Core Concept

The system should be split into two layers:

```text
LEDLookDirector
```

Creative decision layer. It decides which room LED look should be active based on musical context, manual overrides, bridge mode, and safety rules.

```text
GoveeSceneAdapter
```

Output transport layer. It translates the chosen LED look into a Govee action and ensures real Govee communication happens outside the hot path.

In plain English:

```text
LEDLookDirector = what should the room feel like?
GoveeSceneAdapter = safely tell Govee to do it.
```

This separation matters because Govee API/network behavior must never contaminate bridge timing. Consumer smart-home lights are latency-prone enough without letting them block the 200 Hz loop.

---

## 3. Corrected Architecture Principle

The key rule is **not**:

```text
No adapter threads inside the bridge.
```

The correct rule is:

```text
No blocking Govee I/O inside StateManager._push_tick.
```

An internal adapter worker thread is acceptable if it follows the same output-transport pattern already used by the bridge:

```text
public trigger call = bounded, non-blocking, queue-only
worker thread = owns slow I/O
status = exposes degraded/failure state
failure = does not crash the bridge
```

The LED adapter should be modeled after the existing output transport shape:

```text
StateManager calls a bounded trigger method.
The trigger method returns immediately.
The transport owns its own queue and I/O behavior.
```

So the v1 preferred structure is:

```text
StateManager
  → LEDLookDirector.tick(...)
  → GoveeSceneAdapter.trigger(...)
  → bounded queue
  → adapter worker sends Govee command outside hot path
```

A future external helper process is valid as a harder isolation layer, but it is not mandatory for the first implementation.

---

## 4. StateManager Ownership

`StateManager` remains the coordinator.

The LED system should not become an independent timing authority. It should consume context that `StateManager` already computes or owns.

Correct runtime relationship:

```text
StateManager computes bridge context.
SmartPhrasing state is available.
LaserDirector may evaluate laser policy.
LEDLookDirector may evaluate LED policy.
StateManager hands LED decision to GoveeSceneAdapter.
GoveeSceneAdapter queues outbound work and returns immediately.
```

Incorrect relationship:

```text
GoveeSceneAdapter independently reads Rekordbox state.
GoveeSceneAdapter runs timing decisions separately.
GoveeSceneAdapter blocks StateManager waiting for Govee.
LED layer mutates DeckState or OutputState.
```

The LED layer must remain subordinate to `StateManager` timing and state ownership.

---

## 5. Intended Show Model

The full show should be thought of as layered lighting:

```text
Layer 1: SoundSwitch / OS2L
  - track timing
  - autoloops
  - scripted show behavior
  - deck state and phrase alignment

Layer 2: Lasers
  - sharp beam looks
  - drops
  - aerial movement
  - strobe accents
  - fixture-specific high-impact moments

Layer 3: Govee room LEDs
  - crowd envelope
  - room mood
  - perimeter motion
  - buildup tension
  - drop impact support
  - breakdown reset
  - ambient glow

Layer 4: Manual operator control
  - blackout
  - force scene
  - clear override
  - safe default
  - auto resume
```

The LEDs should support the room and crowd first. They should not just mimic whatever the lasers are doing.

---

## 6. What The Govee LEDs Are Doing Creatively

Because the strips run around the room and crowd, they should answer this question:

```text
What should the room feel like right now?
```

Not:

```text
What exact LED scene should be glued to this exact laser cue?
```

The LEDs should create room-scale atmosphere:

- calm blue/purple room wash during intros
- slow perimeter motion during grooves
- red/purple ramp during buildups
- short white/red impact for drops
- darker lower-motion looks during breakdowns
- safe dim default during uncertain states
- blackout when needed

The lasers can remain the sharp, high-definition show layer. The LEDs become the venue/crowd atmosphere layer.

---

## 7. Why Not Hard-Pair LEDs To Lasers

Do not design the system like this:

```text
laser_drop_1 always triggers led_drop_1
laser_drop_2 always triggers led_drop_2
laser_breakdown_1 always triggers led_breakdown_1
```

That makes every show moment repetitive.

Instead:

```text
Musical role enters: drop
  → LaserDirector chooses from laser drop bank
  → LEDLookDirector chooses from LED drop bank
  → optional compatibility rules later keep them from clashing
```

The systems should be coordinated by musical context, not welded together. Fixed one-to-one pairings would reduce variety and make the room layer repetitive.

---

## 8. Corrected High-Level Architecture

Target shape:

```text
Rekordbox direct/fallback state
        ↓
BridgeEvent queue
        ↓
StateManager
        ↓
SmartPhrasing / timing / active deck context
        ↓
        ├── SoundSwitchEngine / OS2L
        │       └── SoundSwitch timing, scripted, autoloops
        │
        ├── LaserDirector
        │       └── LaserSceneExecutor
        │             └── MidiOutput
        │                   └── bounded queue + sender thread
        │
        └── LEDLookDirector
                └── GoveeSceneAdapter
                      └── bounded queue + API/LAN/cloud worker
                            └── Govee controller → RGBIC/RGBICW strips
```

Important boundary:

```text
StateManager may decide or enqueue.
StateManager must not perform Govee network/API calls.
```

The Govee adapter owns slow I/O.

### Repo-Local Integration Contracts

The current bridge already has the patterns the LED lane should reuse.

```text
Bounded output transport:
  midi_output.MidiOutput is the implementation model.
  Public trigger methods return quickly after put_nowait-style queueing or rejection.
  Worker threads own slow I/O and shutdown is bounded.

Runtime commands:
  runtime_status.CommandReader parses /tmp/rb_ss_bridge_v2_commands.jsonl.
  __main__.py callbacks enqueue BridgeEvent instances with put_nowait.
  models.Ev owns event kind constants.
  state_manager.StateManager._handle_event owns durable runtime policy state.

Runtime status:
  runtime_status.StatusWriter takes safe provider callbacks.
  Provider exceptions become degraded/default status blocks.
  Status writing must not expose secrets or call Govee network paths.

Validation:
  validation_runner.ValidationRunner may inspect config results, adapter status, and queue/degraded counters.
  Validation must not perform live Govee API calls.

StateManager:
  _push_tick may build a small immutable LED context from values already computed for SoundSwitch/laser policy.
  _push_tick may call LEDLookDirector.tick(...) and GoveeSceneAdapter.trigger(...) only after the StateManager gate opens.
  _push_tick must not call Govee client methods, adapter status(), config loaders, file I/O, DNS, network I/O, sleeps, retries, subprocesses, or blocking queue operations.
```

Manual command ownership is deliberately split by phase:

```text
Before the StateManager gate:
  parse JSONL commands, validate payloads, and define BridgeEvent contracts only.
  do not add adapter handoff, real bridge output, __main__.py callbacks, or durable policy state.
  do not create long-lived manual override, blackout latch, or auto-resume state outside StateManager.

After the StateManager gate:
  StateManager-side LED policy objects may own manual override, blackout, and clear semantics.
  bridge-side adapter trigger calls may begin only through StateManager-owned manual command handling.
  automatic role-entry still waits for the later automation phase.
```

---

## 9. Hot Path Rule

The bridge has timing-sensitive logic. The LED layer must respect that.

The LED integration should not perform these in the hot path:

- HTTPS requests
- LAN socket calls
- cloud API calls
- Govee scene discovery
- Govee device discovery
- DNS resolution
- retries
- sleeps
- file reads/writes
- config parsing
- blocking queue operations
- subprocess calls
- long validation
- dependency imports that can block or fail unpredictably

The hot path can produce a small decision like:

```text
role=drop
look=room_drop_white_burst
reason=drop_crossing
```

Then it can call a bounded, non-blocking trigger method:

```text
adapter.trigger(decision)
```

That call must return immediately after queueing or rejecting the command.

Concrete v1 bounds:

```text
adapter trigger target:
  under 1 ms after dedupe/rate-limit and put_nowait/reject

adapter queue:
  default maxsize = 8
  configurable hard cap = 16
  queue full = reject/drop command, increment visible degraded/drop counter, do not block

Govee request timeout:
  default = 2.0 seconds per request
  no unbounded retries

worker shutdown:
  join timeout = 1.0 second
  shutdown failure degrades LED lane only

scene retrigger cooldown:
  default = 4 seconds for ordinary scene re-triggers

high-impact/drop cooldown:
  default = 12 seconds between high-impact room looks
  drop flash duration max = 750 ms unless hardware scene semantics force a safer shorter value
```

---

## 10. Internal Worker vs External Helper Process

There are two viable transport isolation levels.

### Preferred v1: Internal Adapter Worker

Use a `GoveeSceneAdapter` inside the bridge process.

Shape:

```text
GoveeSceneAdapter.trigger(...)
  → validate basic local state
  → dedupe/rate-limit check
  → put_nowait into bounded queue
  → return true/false

Govee adapter worker thread
  → reads queue
  → sends Govee command
  → updates adapter status
  → logs success/failure
```

This matches the existing output-transport concept: non-blocking public method, bounded queue, worker-owned I/O, safe degradation.

This is the recommended first real implementation because it is simpler and aligns with the bridge's existing transport pattern.

### Optional later: External Govee Worker Process

Use a separate helper process only if needed.

Shape:

```text
Bridge process
  → LEDLookDirector
  → lightweight local IPC command
  → external govee_worker.py
  → Govee API/LAN client
```

This can be useful if:

- Govee libraries are unstable
- cloud calls hang in unpleasant ways
- API client dependencies pollute the main bridge environment
- stronger crash isolation is needed
- the Govee layer becomes complex enough to deserve its own runtime

Do not start with the external process unless live testing proves the internal adapter is too risky. Adding another process too early adds supervision, restart, logging, and deployment overhead before there is evidence it is needed.

---

## 11. Main Modules To Add

Surface-level plan only. Exact file names can change later, but this is the clean shape.

### `led_look_director.py`

Policy layer.

Responsibilities:

- track enabled/disabled state
- track emergency blackout state
- track manual override state
- choose LED look from current musical role
- choose from role banks
- dedupe repeated look triggers at the policy level where appropriate
- apply basic safety gates
- expose status
- stay bounded and non-blocking

It should not:

- call Govee directly
- do network I/O
- parse config every tick
- mutate deck state
- send OS2L
- send MIDI
- know low-level Govee API details

### `led_models.py`

Small dataclasses or equivalent models.

Conceptual models:

- `LEDLook`
- `LEDPersonality`
- `LEDContext`
- `LEDLookDecision`
- `LEDLookStatus`
- `LEDTarget`
- `LEDAdapterStatus`

No need to over-model at first. Keep the v1 model surface small and explicit.

`LEDContext` should mirror the laser-side boundary style: a small immutable snapshot built from values StateManager already computed for the current tick. It may include active deck, playing state, elapsed time, BPM, beat position, lighting mode, scripted id, active-track-loaded flag, stale-position flag, and SmartPhrasing state. It must not carry mutable `DeckState`, `OutputState`, adapter instances, config loaders, Govee client objects, or anything that requires I/O to inspect.

### `led_config.py`

Config loading and validation.

Responsibilities:

- load LED config
- validate look names
- validate bank references
- validate fallback/default/blackout references
- validate basic target structure
- return safe unavailable status if config is absent or invalid

### `govee_scene_adapter.py`

Output transport layer.

Responsibilities:

- read `GOVEE_API_KEY` from the environment at runtime
- reject any attempt to load Govee API credentials from config files
- resolve configured targets outside the hot path
- trigger scenes where supported
- trigger blackout/off where supported
- fallback to basic commands where scene support is absent
- rate-limit commands
- dedupe repeated scene requests
- own bounded queue/worker thread for outbound calls
- expose adapter status
- fail soft

It should not:

- decide creative roles
- know about laser scene selection
- alter StateManager state
- block bridge timing
- create Govee scenes
- log, print, store, or expose API keys/secrets

### Optional later: `scripts/govee_worker.py`

Only if stronger isolation is needed.

Responsibilities:

- own Govee client dependencies
- own network calls
- accept local commands from bridge
- publish status back to bridge
- restart independently if needed

This is future hardening, not required for v1.

### Optional later: `led_decision_log.py`

Only if useful.

Responsibilities:

- record recent LED decisions
- help debug why a room look triggered
- show role/reason/previous look/current look

This should not be required for v1.

---

## 12. Govee Capability Gate

The bridge must not assume that scene triggering is available just because the model is supported.

Startup discovery must confirm what the actual paired device exposes.

The LED layer should distinguish:

```text
model appears supported
```

from:

```text
this exact device exposes dynamic scenes / DIY scenes / snapshots / control capability through the available API path
```

At startup, the adapter should eventually determine:

- target device exists
- device is controllable
- model/SKU matches expected target
- available capabilities
- available scene/effect categories
- whether dynamic scenes are available
- whether fallback controls are available
- whether target is currently reachable enough for live control

If scene capability is absent, the layer should degrade:

```text
Scene looks unavailable.
Basic color/brightness/off looks may remain available.
Dry-run still works.
Status clearly reports scene capability missing.
```

Supported model list is a useful signal. It is not proof that the exact paired device exposes the scene controls needed for this integration.

---

## 13. Govee Control Path Strategy

The plan should support multiple possible Govee control routes without committing too early.

Potential paths:

```text
Govee Platform / cloud API
```

Useful if it exposes device capabilities and dynamic scenes for the target device.

```text
Govee LAN/local control
```

Useful if supported and if it exposes the controls needed for the target device. Likely better for latency, but model/capability support must be verified.

```text
Fallback basic control
```

Power, brightness, static color, or similar basic operations if scene triggering is unavailable.

Do not assume LAN is always better. Do not assume cloud is always enough. The adapter should be designed around capability discovery:

```text
What can this device actually do through the available route?
```

The creative target remains scene/effect triggering, but the system must survive fallback mode.

---

### Govee API Reference Grounding Requirements

This workflow is not enough by itself to write Govee API code.

Before writing or changing any code that performs Govee API requests, parses Govee API responses, defines endpoint constants, defines request payloads, or interprets Govee capability/scene-control fields, the implementation agent must inspect the current official Govee Developer Platform references.

Required official sources:

```text
https://developer.govee.com/docs/getting-started
https://developer.govee.com/docs/support-product-model
https://developer.govee.com/llms.txt
https://developer.govee.com/reference/get-you-devices
https://developer.govee.com/reference/get-devices-status
https://developer.govee.com/reference/get-light-scene
https://developer.govee.com/reference/control-you-devices
https://developer.govee.com/reference/subscribe-device-event
https://developer.govee.com/changelog/important-policy-update-important-notice-regarding-api-key-security-management
```

The agent must prefer the official Markdown/OpenAPI material linked from `llms.txt` when available. The getting-started page explicitly points AI agents to `llms.txt`; treat that index as the discovery entrypoint for current machine-readable reference material.

The agent must not infer any of the following from memory, old examples, third-party snippets, package defaults, or guesses:

```text
base URL
endpoint paths
HTTP methods
auth header name
API-key placement
request payload shapes
required request fields
response field names
capability names
scene-control command formats
dynamic-scene identifiers
device status formats
rate-limit/error semantics
```

Before Phase 1 API code is accepted, the agent must produce a short source-grounding note in the phase output that extracts from the official docs:

```text
base URL
auth header / API-key usage
device listing endpoint
device status endpoint
dynamic scene endpoint
control endpoint
required request payload fields
relevant response fields
capability and scene-control format
known error/rate-limit behavior if documented
whether subscribe-device-event is relevant to v1 or explicitly deferred
whether the supported-model list includes the target model, without treating model support as scene-control proof
current API-key security policy and any key-rotation implications
```

If the official docs are incomplete, ambiguous, contradictory, unavailable, or do not describe how to trigger the desired scene/control format for the target device, the agent must stop and report the ambiguity. It must not fill gaps by guessing.

Official examples are not exempt from the secrets rule. Any copied or summarized sample request, response, MQTT credential, topic, API key, device ID, or header from official docs must be sanitized before it appears in phase reports, `/tmp` summaries, docs, tests, logs, screenshots, or terminal output.

Phase-specific grounding rule:

```text
Phase 1 capability capture may create standalone API request code only after fresh official-doc extraction in the same phase report.
Phase 1 dry-run mode must not make live calls and must still write/validate the official-source extraction summary.
Phase 1 live capture must require --live, GOVEE_API_KEY in the environment, Supervisor approval of the exact command, 2.0 second request timeouts, and sanitized evidence.
Phase 2 manual trigger code must refresh or re-check official docs before any control/dynamic-scene request code is written.
Phase 2 live proof must use only documented request shapes and must record sanitized evidence of what was attempted.
Phase 3 bridge skeleton must not perform real Govee API calls.
Phase 5 may implement isolated adapter send logic and mocked tests, but must not create bridge-runtime live Govee output.
Bridge-runtime live Govee output waits until StateManager-owned manual handling after the Phase 6 gate.
```

Third-party libraries may be used later only after the official API contract is understood. A library wrapper does not replace official-doc grounding.

---

## 14. Config File Plan

Use a separate config file from the laser config.

Recommended:

```text
config/led_look_director.example.json
config/led_look_director.json
```

Reason:

- LED scenes are not MIDI notes.
- Govee targets are not SoundSwitch fixtures.
- room safety rules are different from laser safety rules.
- Govee scene IDs and device IDs have their own lifecycle and validation rules.
- LED mapping should not bloat laser mapping.
- lasers and room LEDs are separate creative systems.

Default posture:

```text
Before Phase 2 manual live proof:
  enabled = false
  dry_run = true

After Phase 2 manual proof, Phase 5 isolated transport tests, and Phase 7 StateManager-owned manual bridge output pass:
  live config may default to enabled = true
  dry_run = false requires explicit live config and capability-backed target mapping
  automatic role-entry still requires automation_enabled = true and the pre-Phase-8 rehearsal gate
```

That preserves dry-run safety for early phases while matching the user-selected posture that Govee output may be enabled by default once StateManager-owned bridge integration is proven.

Secret posture:

```text
GOVEE_API_KEY comes only from the process environment.
config/led_look_director.json must not contain API keys, tokens, secrets, auth headers, or bearer values.
config/led_look_director.example.json must not contain realistic secrets.
Logs, status JSON, command JSONL, capability notes, screenshots, and test fixtures must not expose the API key.
```

Config validation must fail if obvious secret-bearing keys appear, including:

```text
api_key
apikey
token
secret
authorization
auth_header
bearer
password
```

---

## 15. Minimal v1 Config Schema

Do not let the schema emerge accidentally during implementation. The v1 config should start with this minimal shape and add fields only when a phase requires them.

```json
{
  "schema_version": 1,
  "enabled": false,
  "dry_run": true,
  "automation_enabled": false,
  "targets": {
    "room_perimeter": {
      "label": "Room perimeter",
      "device_ref": "redacted-or-operator-local-id",
      "expected_model": "H612D",
      "control_route": "govee_platform",
      "capabilities": ["scene", "color", "brightness", "off"]
    }
  },
  "looks": {
    "room_safe_default": {
      "target": "room_perimeter",
      "action": "scene",
      "scene_ref": "operator_scene_name_or_id",
      "fallback": "room_blackout",
      "safety_class": "safe",
      "brightness": 35,
      "allow_strobe": false
    },
    "room_blackout": {
      "target": "room_perimeter",
      "action": "off",
      "safety_class": "blackout",
      "brightness": 0,
      "allow_strobe": false
    }
  },
  "banks": {
    "default": {
      "ambient": ["room_safe_default"],
      "groove": ["room_safe_default"],
      "buildup": ["room_safe_default"],
      "pre_drop": ["room_safe_default"],
      "drop": ["room_safe_default"],
      "post_drop": ["room_safe_default"],
      "breakdown": ["room_safe_default"],
      "utility": ["room_safe_default", "room_blackout"]
    }
  },
  "safe_default": "room_safe_default",
  "blackout": "room_blackout",
  "rate_limits": {
    "queue_maxsize": 8,
    "scene_retrigger_cooldown_s": 4.0,
    "high_impact_cooldown_s": 12.0,
    "request_timeout_s": 2.0,
    "worker_shutdown_timeout_s": 1.0
  },
  "safety": {
    "max_brightness": 70,
    "allow_strobe": false,
    "max_strobe_duration_ms": 750,
    "high_impact_cooldown_s": 12.0,
    "drop_flash_duration_ms": 750,
    "emergency_blackout_always_available": true,
    "scripted_mode_automation": false
  }
}
```

Validation rules:

```text
enabled, dry_run, and automation_enabled are required booleans.
dry_run=false requires enabled=true, a non-empty target map, capability-backed look mappings, and GOVEE_API_KEY in the environment at runtime.
automation_enabled=true is invalid until the pre-Phase-8 rehearsal gate passes.
targets must not contain API keys, auth headers, bearer tokens, passwords, or realistic secrets.
looks must reference existing targets.
banks must reference existing looks.
safe_default and blackout must reference existing looks.
queue_maxsize defaults to 8 and must not exceed 16.
request_timeout_s defaults to 2.0 and must be finite and positive.
worker_shutdown_timeout_s defaults to 1.0 and must be finite and positive.
scene_retrigger_cooldown_s defaults to 4.0.
high_impact_cooldown_s defaults to 12.0.
max_brightness must clamp output brightness before dispatch.
allow_strobe=false disables strobe-like looks even if a bank references them.
emergency_blackout_always_available must remain true in v1.
```

---

## 16. LED Look Banks

The LED system should be bank-based.

### Ambient Bank

Purpose:

```text
Low-intensity room mood.
```

Use for:

- intro
- warmup
- between tracks
- softer sections
- early set
- low-energy transitions

Examples:

```text
room_ambient_blue_slow
room_ambient_purple_low
room_ambient_red_tension
room_ambient_warm_dim
```

### Groove Bank

Purpose:

```text
Room motion during sustained sections.
```

Use for:

- house grooves
- bass house grooves
- techno loops
- non-drop movement
- crowd energy without chaos

Examples:

```text
room_groove_purple_runner
room_groove_blue_wave
room_groove_sidewall_chase
room_groove_soft_pulse
```

### Buildup Bank

Purpose:

```text
Tension and rising energy before a drop.
```

Use for:

- uplifters
- risers
- pre-drop ramps
- tension sections

Examples:

```text
room_build_purple_rise
room_build_red_ramp
room_build_white_pulse
room_build_compress
```

### Pre-Drop Bank

Purpose:

```text
Short cue before impact.
```

Use carefully. This may overlap with laser blackout or transition logic.

Examples:

```text
room_pre_drop_dim
room_pre_drop_white_ping
room_pre_drop_red_snap
```

### Drop Bank

Purpose:

```text
Short room-wide impact.
```

Use for:

- drop hits
- chorus entrance
- festival-style impact moments
- bass impact

Examples:

```text
room_drop_white_burst
room_drop_red_flash
room_drop_fast_runner
room_drop_short_strobe
```

Drop scenes should usually be short. Since the LEDs wrap the crowd, do not make every drop a full-room strobe or peak-brightness event.

### Post-Drop Bank

Purpose:

```text
Sustained high-energy room state after the initial hit.
```

Examples:

```text
room_post_drop_red_chase
room_post_drop_blue_fast_wave
room_post_drop_purple_motion
```

### Breakdown Bank

Purpose:

```text
Room reset.
```

Use for:

- breakdowns
- vocal sections
- melodic sections
- low-energy reset after intense drops

Examples:

```text
room_breakdown_blue_low
room_breakdown_warm_dim
room_breakdown_purple_drift
room_breakdown_dark_static
```

### Utility Bank

Purpose:

```text
Non-creative safety and setup states.
```

Examples:

```text
room_blackout
room_safe_dim_blue
room_setup_white_low
room_setup_white_full
room_end_show_off
```

Utility looks should always be available.

---

## 17. Role Selection

The LEDLookDirector should use a musical role vocabulary similar to the bridge and laser system, but interpreted for room lighting.

Core roles:

```text
idle
ambient
groove
buildup
pre_drop
drop
post_drop
breakdown
transition
manual
emergency
utility
```

The role is not the look. The role chooses a bank, and the bank chooses a look.

Example:

```text
role = drop
bank = drop_bank
selected look = room_drop_white_burst
```

Next eligible drop:

```text
role = drop
bank = drop_bank
selected look = room_drop_red_flash
```

This creates variety.

---

## 18. Priority Order

Recommended LEDLookDirector priority:

```text
1. Disabled
2. Emergency blackout
3. Manual override
4. Unsafe / unready state
5. Scripted mode policy
6. Breakdown
7. Drop impact
8. Post-drop hold
9. Buildup
10. Groove / phrase
11. Ambient / default
```

Notes:

- Emergency blackout wins over everything.
- Manual override wins over automation.
- Unsafe/unready state should not spam Govee.
- Scripted mode should be conservative at first.
- Drop impact should be one trigger, not repeated every tick.
- Groove/phrase should change slowly and intentionally.

---

## 19. Manual Control

Manual control is required from the first backend version.

The first v1 operator surface is only:

```text
/tmp/rb_ss_bridge_v2_commands.jsonl
```

Do not build UI, MIDI, keyboard, or multiple operator surfaces early. Those remain optional future work after the JSONL path, StateManager ownership, blackout recovery, and rehearsal gate are proven.

Conceptual manual actions:

```text
enable LED Look Director
disable LED Look Director
trigger LED look by name
trigger LED blackout
clear LED blackout
clear manual override
return to auto
```

Manual command priority:

```text
emergency blackout
  > manual override
  > automatic role selection
  > default / safe state
```

The bridge may eventually expose these through a UI, but the JSONL backend command path comes first.

Manual control must be useful during a real show. The operator should not need to open the Govee app mid-set for normal trigger, blackout, or recovery actions.

---

## 20. Runtime Status

Add LED status as its own status section.

Conceptual status:

```text
led_look_director:
  available
  enabled
  dry_run
  current_look
  last_triggered_look
  last_role
  last_reason
  manual_override
  emergency
  last_error
  trigger_count
  gated_count
  adapter_status
```

Adapter status may include:

```text
available
running
dry_run
degraded
degraded_reason
queue_depth
queue_max
dropped_count
rejected_count
sent_count
last_command_at
last_success_at
last_failure_at
last_error
resolved_targets
unresolved_targets
capability_summary
```

Status should make degraded states clear:

```text
not_configured
invalid_config
disabled
dry_run
target_unresolved
scene_capability_missing
scene_unavailable
adapter_error
rate_limited
queue_full
automation_gated
rehearsal_gate_missing
ok
```

---

## 21. Startup Flow

High-level startup after the StateManager-owned bridge integration phase:

```text
1. Load LED config.
2. If missing, mark LED unavailable and continue.
3. If invalid, mark LED unavailable and continue.
4. If valid, build LEDLookDirector.
5. Build GoveeSceneAdapter.
6. Start adapter worker thread only when the active phase and config permit it.
7. Run target/scene/capability discovery outside the hot path.
8. Attach LED status provider.
9. Continue normal bridge startup.
```

Startup must not block the rest of the bridge.

If Govee setup fails, the bridge should still start normally.

Discovery may run asynchronously or in a bounded startup-safe way. It should not delay core SoundSwitch/laser operation.

---

## 22. Runtime Flow

Automatic runtime flow after the automation phase opens:

```text
StateManager computes current bridge context.
SmartPhrasing state is available.
LaserDirector runs as usual.
LEDLookDirector evaluates current context.
LEDLookDirector returns a decision only when meaningful.
GoveeSceneAdapter receives the decision.
Adapter dedupes/rate-limits/queues command.
Adapter worker sends command.
Status updates.
```

Manual runtime flow after the StateManager gate opens:

```text
Operator command arrives.
Command is validated.
Bridge sets manual LED override or blackout state.
LEDLookDirector produces manual/emergency decision.
GoveeSceneAdapter queues selected look.
Adapter worker sends command.
```

Default inert behavior:

```text
not playing:
  no automatic LED command

stale position:
  no automation

unknown phrase or missing SmartPhrasing context:
  keep current safe/default look or do nothing; do not guess a high-impact look

queue full:
  reject/drop the command, increment visible degraded/drop counter, do not block

adapter unavailable/degraded:
  LED lane is inert and status-visible; SoundSwitch and lasers continue

unsupported scene or missing capability:
  disable only affected look; fall back to safe_default or do nothing

invalid config or not_configured:
  LED lane unavailable; bridge startup continues

scripted mode:
  manual-only by default; no automatic LED role changes unless explicitly enabled later

automation_enabled=false:
  manual commands and emergency blackout may work; automatic role-entry is inert

emergency blackout:
  always available when the LED lane is configured, even if automation is disabled
```

---

## 23. Triggering Philosophy

The LED system should be **event-ish**, not continuous.

Good triggers:

```text
role enters buildup
role enters drop
role enters breakdown
manual look selected
manual blackout selected
clear override selected
track starts
track stops
```

Bad triggers:

```text
send Govee command every tick
send Govee command every beat
fake strobe by repeated on/off calls
change color every elapsed update
discover scenes during playback hot path
```

The bridge should send one command and let the Govee controller run the scene internally where supported.

---

## 24. Govee Scene Creation Workflow

The actual RGBIC/RGBICW scenes should be created or selected in Govee first.

Workflow:

```text
1. Open Govee app.
2. Create/select built-in, DIY, snapshot, or effect scenes.
3. Give scenes operator-friendly names where possible.
4. Bridge discovers or references those scenes if exposed.
5. Bridge maps those Govee scenes to LED look names.
6. LED look names are placed into banks.
7. Bridge triggers LED look names during playback.
```

The bridge should not try to create complex RGBIC animations in v1.

The Govee controller should run the visual animation. The bridge should trigger the scene.

If the exact model/API path does not expose scene triggering, the bridge should report that clearly and fall back to basic commands.

---

## 25. Model Dependency

Govee model support may vary.

The integration should assume that not every Govee RGBIC/RGBICW strip supports the same control categories.

Possible capability differences:

```text
basic power/color/brightness only
dynamic scenes
DIY scenes
snapshots
music modes
LAN control
cloud-only control
partial scene support
multiple segment behavior
```

The bridge should discover and report what is available.

For the H612D/H612DAD1 use case, treat the model names as target evidence to verify, not as an implementation assumption. Capability capture must confirm the exact paired device, supported control route, dynamic-scene availability, basic control support, and blackout/off behavior before bridge integration.

If scene triggering is unsupported for a model, fallback behavior may be limited to:

```text
power off
solid color
brightness
safe default
```

But the creative target remains scene triggering.

---

## 26. Room Zones

Initial version can treat all LEDs as one room target.

Future design should allow zones.

Possible zones:

```text
front_wall
left_wall
right_wall
back_wall
ceiling_perimeter
dj_wall
crowd_perimeter
```

Future concept:

```text
one LED look
  → multiple target scene commands
```

Example concept:

```text
room_drop_white_burst
  → left_wall: white burst
  → right_wall: white burst
  → back_wall: red chase
```

Do not require zones in v1, but avoid designing the config so narrowly that zones are impossible later.

---

## 27. Scripted Mode Policy

The current bridge has scripted and autoloop modes. LED behavior during scripted tracks needs a clear policy.

Initial recommendation:

```text
During scripted mode:
  automatic LED role changes are disabled unless explicitly enabled later.
  manual LED commands still work.
  emergency blackout still works.
```

Reason:

A scripted SoundSwitch track may already have intentional lighting. The Govee room layer should not accidentally fight it.

Later, scripted LED mappings can be added deliberately.

---

## 28. Interaction With Laser Director

The LED layer should be independent.

Valid combinations:

```text
LaserDirector off, LEDLookDirector off
LaserDirector on, LEDLookDirector off
LaserDirector off, LEDLookDirector on
LaserDirector on, LEDLookDirector on
```

The LED layer should not require MIDI.

The laser layer should not require Govee.

Later compatibility rules can consider the laser role or intensity, but do not make that required for v1.

---

## 29. Future Compatibility Layer

Do not build this first, but plan for it.

Later, each LED look and laser look can have metadata:

```text
energy
color_family
motion
density
strobe_level
role
safety_class
```

Compatibility examples:

```text
If laser is dense/high-impact:
  choose simpler room LED support look.

If laser is sparse:
  allow more active room LED motion.

If laser is strobing:
  avoid long room strobe.

If room LEDs are doing fast chase:
  prefer cleaner laser look.

If both systems are peak intensity:
  require explicit high-impact mode.
```

This gives coordinated variety without fixed pairing.

---

## 30. Safety And Comfort

Because these LEDs surround the crowd, safety rules matter.

Initial safety rules:

```text
default disabled
default dry-run
manual blackout always available
safe dim default always available
dedupe repeated triggers
rate-limit outbound commands
avoid sustained full-room strobe
avoid repeated peak impact triggers too close together
do not spam on/off for strobe
do not allow Govee failure to crash bridge
max_brightness defaults to 70 unless the operator explicitly lowers it
allow_strobe defaults to false
max_strobe_duration_ms defaults to 750
high_impact_cooldown_s defaults to 12
drop_flash_duration_ms defaults to 750
emergency blackout remains available regardless of automation_enabled
```

Strobe-like looks should be short impact macros.

The room should feel exciting while remaining comfortable and controllable.

---

## 31. Dry-Run Mode

Dry-run should be supported from day one.

Dry-run behavior:

```text
LEDLookDirector still makes decisions.
GoveeSceneAdapter does not send real commands.
Logs/status show intended look.
Manual commands can be tested.
Config validation still runs.
Capability discovery may be skipped or simulated depending on config.
```

Dry-run lets the system be rehearsed safely.

---

## 32. Validation Plan

Initial validation should check:

```text
config parse succeeds
required config sections exist
look names are unique
bank entries reference valid looks
fallback looks exist
blackout/safe/default looks exist
target references exist
enabled banks are not empty when needed
manual look names are valid
dry-run setting is visible
adapter can initialize without blocking
secret-like keys are rejected from config
GOVEE_API_KEY is not present in config/status/log fixtures
```

Live validation later can check:

```text
official API reference extraction was completed for this phase
Govee target reachable
scene reference exists
target supports scene type
blackout/off command available
basic fallback command available
preferred control route available
live call was explicitly approved
live output evidence is sanitized
```

Unit tests should not require live Govee devices.

Standalone diagnostic tools may require operator visual confirmation for real Govee hardware behavior, but those live checks must be opt-in, documented, bounded by explicit request timeouts, and sanitized.

---

## 33. Logging Plan

Keep logs useful but low-noise.

Suggested tags:

```text
[LED] policy
[LED] manual
[LED] blackout
[LED_CONFIG]
[GOVEE] adapter
[GOVEE] trigger
[GOVEE] dry-run
[GOVEE] discovery
[GOVEE] capability
[GOVEE] error
```

Log:

- startup config state
- capability discovery summary
- manual triggers
- role-entry triggers
- blackout
- adapter errors
- dry-run actions
- target resolution results

Do not log every tick.

Never log:

```text
GOVEE_API_KEY
raw authorization/auth headers
full request headers
raw request/response bodies if they contain secrets
operator environment values
unredacted exception objects that include headers or secrets
```

---

## 34. Operator Workflow

Initial operator workflow:

```text
1. Create/select scenes in Govee.
2. Inspect official Govee docs through llms.txt / Markdown / OpenAPI before API code.
3. Put GOVEE_API_KEY in the environment only when running approved live tools.
4. Configure bridge LED target without secrets.
5. Run standalone discovery/capability check.
6. Confirm scene/control capability.
7. Map Govee scenes or fallback controls to LED look names.
8. Put LED looks into banks.
9. Start bridge with LED layer dry-run.
10. Test manual LED scene command.
11. Test manual blackout/off.
12. Watch runtime status.
13. Enable real adapter only after Supervisor approval.
14. Test scene triggering with one track.
15. Enable role-entry automation behind explicit flag.
16. Rehearse before event use.
```

Do not build a giant UI before this works from config and commands.

---

## 35. UI Plan

Backend first. UI later.

Eventually, the existing browser mapping surface could gain an LED tab.

Possible LED UI features:

```text
show configured Govee targets
show discovered capabilities
show discovered scenes
map Govee scenes to LED look names
assign looks to banks
manual test trigger
manual blackout
dry-run toggle
runtime status
validation errors
last triggered LED look
```

But initial integration should not depend on the UI.

---

## 36. Supporting Gate And Automation Safety Requirements

When this integration plan is used without the standalone orchestrator, this section can serve as a reference safety scaffold. When `docs/plans/led_agent_orchestrator_workflow.md` is present, the orchestrator controls phase order, gates, allowed files, forbidden files, stop conditions, and agent prompts; this section provides supporting safety requirements and rationale.

Supervisor means the Supervisor agent, not the human operator.

Authoritative phase map when the orchestrator is present:

```text
Phase 1: Standalone Govee capability capture
Phase 2: Standalone manual Govee trigger
Phase 3: LED bridge skeleton, dry-run/status/config only
Phase 4: Manual LED JSONL command contract and BridgeEvent parser, no StateManager changes
Phase 5: Isolated GoveeSceneAdapter transport/config/tests, no bridge runtime wiring
Phase 6: Hard StateManager gate review
Phase 7: StateManager LED manual/status ownership, no automation
Pre-Phase-8 rehearsal gate: manual bridge path and adapter safety evidence
Phase 8: Automatic LED role-entry triggers behind explicit enable flag
Phase 9: Rehearsal hardening and docs
Phase 10: Optional UI planning only
Phase 11: Optional external worker only if evidence requires it
```

The detailed requirement sets below are not phase numbers when the orchestrator is present. Use them only as supporting requirements and rationale.

The expected automation shape is:

```text
Cursor/Codex implementation agent performs the phase work.
Supervisor agent reviews phase output, diffs, tests, and evidence.
Supervisor agent approves, rejects, or requests revisions.
Implementation agent revises until the phase gate passes.
Human/operator input is requested only for physical or account/environment preconditions the agents cannot perform.
```

Human/operator input boundary:

```text
May request: place/power/pair LED strips, create/select scenes in the Govee app if not API-accessible, confirm observed physical light behavior, make GOVEE_API_KEY available in the runtime environment without revealing it, or fix external account/network/hardware state.
Must not request: ordinary code review, phase approval, test interpretation, rollback decision, file-scope policing, API-shape guessing, or bridge architecture decisions that the Supervisor can decide from evidence.
```

General rules for every phase:

```text
Do not implement work from a later phase.
Do not touch files outside the phase allowlist.
Do not touch forbidden files.
Do not create branches or commits unless the Supervisor explicitly asks.
Do not run live Govee API calls unless the phase allows live calls and the Supervisor explicitly approves live testing.
Do not request, print, log, persist, or expose GOVEE_API_KEY.
Do not place secrets in config files, docs, fixtures, status JSON, screenshots, or command logs.
Do not guess API details.
Do not continue after auth, rate-limit, hardware, capability, or official-doc ambiguity failures.
```

Phase report required from the implementation agent:

```text
phase number and scope
files changed
files intentionally not touched
tests run
tests skipped and why
live calls run, or "none"
official Govee references inspected, if API code was touched
sanitized evidence for any live proof
open blockers
rollback instructions for only this phase's changes
```

Supervisor rejection rules:

```text
Reject if state_manager.py is touched before the orchestrator Phase 6 gate explicitly opens StateManager LED changes.
Reject if any secret appears in a file, log excerpt, status fixture, screenshot, or command example.
Reject if API endpoint/payload/header details are added without citing official docs inspected in that phase.
Reject if bridge runtime files are changed in standalone phases.
Reject if tests are missing for runtime behavior changed in that phase.
Reject if live Govee calls run without explicit Supervisor approval.
Reject if the agent claims unsupported capability should work anyway.
```

Rollback rule:

```text
Rollback means revert only the current phase's edits.
Do not clean unrelated dirty files.
Do not delete operator-generated config/backups/artifacts unless explicitly directed by the Supervisor after confirming scope.
If a phase fails, stop with a failure report rather than pushing speculative fixes into the next phase.
```

Important execution note:

```text
The supporting requirement sets below are not the controlling Cursor execution schedule when docs/plans/led_agent_orchestrator_workflow.md is present.
Use them only as supporting safety/design rationale; the orchestrator phase map above controls execution.
For actual phase order, file allowlists, forbidden files, gates, and prompts, follow the orchestrator.
```

### Supporting Requirement Set 1: Standalone Dry-Run Foundation

Goal:

```text
Create the LED policy/config/model/adapter skeleton without touching bridge runtime wiring.
No real Govee calls.
No StateManager changes.
```

Allowed files:

```text
led_models.py
led_config.py
led_look_director.py
govee_scene_adapter.py
config/led_look_director.example.json
tests/test_led_config.py
tests/test_led_look_director.py
tests/test_govee_scene_adapter.py
docs/plans/led_agent_orchestrator_workflow.md
```

Forbidden files:

```text
state_manager.py
__main__.py
runtime_status.py
models.py
validation_runner.py
sound_switch_engine.py
laser_director.py
laser_executor.py
midi_output.py
tools/laser_pad_web.py
frontend/browser UI assets
config/led_look_director.json
```

Deliverables:

```text
dry-run LEDLookDirector skeleton
dry-run GoveeSceneAdapter skeleton
bounded non-blocking adapter trigger method
local status dicts
config loader that returns not_configured/invalid_config safely
example config with enabled=false and dry_run=true
secret-key rejection in config validation
unit tests for config, priority, dry-run trigger, and queue-full behavior
```

Exit criteria:

```text
No bridge runtime files touched.
No live Govee calls.
No API key needed.
Unit tests pass.
Dry-run adapter trigger returns immediately after queueing or rejecting.
Config validation rejects secret-like keys.
```

### Supporting Requirement Set 2: Standalone Official API Grounding, Capability Capture, And Manual Live Proof

Goal:

```text
Prove the target Govee device can be discovered and manually controlled outside the bridge runtime.
Still no StateManager changes.
```

Allowed files:

```text
govee_scene_adapter.py
led_models.py
led_config.py
tools/govee_capability_capture.py
tools/govee_manual_trigger.py
docs/govee_capability_notes.md
tests/test_govee_scene_adapter.py
tests/test_govee_tools.py
```

Forbidden files:

```text
state_manager.py
__main__.py
runtime_status.py
models.py
validation_runner.py
sound_switch_engine.py
laser_director.py
laser_executor.py
midi_output.py
frontend/browser UI assets
```

Mandatory pre-code step:

```text
Inspect official Govee docs, llms.txt, and official Markdown/OpenAPI reference material.
Extract base URL, auth header/API-key usage, endpoints, methods, payload fields, response fields, capability format, and scene-control format.
If any required detail is ambiguous, stop and report.
```

Live-call rules:

```text
Default is no live calls.
Live calls require explicit Supervisor approval for this phase.
Live tools must require --live.
Live tools must require GOVEE_API_KEY in the environment.
Live tools must never echo the key.
Request timeouts default to 2.0 seconds.
Retries must be conservative and documented.
Auth failure, rate limit, unavailable target, unsupported scene, or ambiguous capability stops the phase.
```

Deliverables:

```text
sanitized official-source extraction note
standalone capability capture tool
standalone manual trigger tool
sanitized capability notes for target devices such as H612D/H612DAD1 if present
clear unsupported-capability reporting
mocked tests for success, auth failure, timeout, rate limit, unsupported scene, unsupported capability, and malformed response
```

Exit criteria:

```text
Standalone device list/status/capability capture works or fails with a clear reason.
At least one manual scene/basic/off command works, or the docs/device prove it is unsupported.
No bridge runtime files touched.
No secrets written anywhere.
Failure does not crash the tool.
```

### Supporting Requirement Set 3: LED Look Config And Banks, No Runtime Wiring

Goal:

```text
Define the bridge-level LED look vocabulary and bank validation after real capability facts are known.
```

Allowed files:

```text
led_models.py
led_config.py
led_look_director.py
config/led_look_director.example.json
tests/test_led_config.py
tests/test_led_look_director.py
docs/govee_capability_notes.md
```

Forbidden files:

```text
state_manager.py
__main__.py
runtime_status.py
models.py
validation_runner.py
```

Deliverables:

```text
minimal v1 schema for enabled, dry_run, automation_enabled, targets, looks, banks, safe_default, blackout, rate_limits, and safety
safe/default/blackout look validation
capability-aware look availability
bank reference validation
manual look name validation
queue/request/shutdown/cooldown bound validation
strobe/brightness/high-impact safety validation
example config without secrets
```

Exit criteria:

```text
Missing look references fail validation.
Unsupported looks are reported without crashing.
Banks validate.
The schema leaves room for multiple zones later.
No runtime bridge wiring exists yet.
```

### Supporting Requirement Set 4: Manual Command Contract And Parser, No Automatic Runtime Wiring

Goal:

```text
Define safe manual command semantics before StateManager integration.
```

Allowed files:

```text
runtime_status.py
models.py
tests/test_runtime_status.py
tests/test_led_runtime_commands.py
docs/plans/led_agent_orchestrator_workflow.md
```

Forbidden files:

```text
state_manager.py
__main__.py
laser_director.py
laser_executor.py
midi_output.py
sound_switch_engine.py
```

Deliverables:

```text
allowlisted LED command names
strict command payload validation
bounded TTL/clamping where applicable
BridgeEvent constants/contracts for later StateManager ownership
no __main__.py callbacks
no adapter handoff
no durable blackout/manual override/auto-resume policy state
manual blackout command shape
manual clear-blackout command shape
manual look command shape
manual clear-override command shape
tests for invalid names, invalid TTL, missing fields, unknown command, and payload normalization
```

Exit criteria:

```text
Manual command parsing is safe.
No callback, queue, adapter, or live-output path exists yet.
No automatic LED policy runs.
No StateManager changes.
```

### Supporting Requirement Set 5: Isolated GoveeSceneAdapter Transport, No Bridge Runtime Wiring

Goal:

```text
Implement or harden the Govee adapter/config/test layer in isolation.
Do not start it from the bridge runtime.
```

Allowed files:

```text
govee_scene_adapter.py
led_config.py
led_models.py
tests/test_govee_scene_adapter.py
tests/test_led_config.py
```

Forbidden files:

```text
state_manager.py
__main__.py
runtime_status.py
validation_runner.py
laser_director.py
laser_executor.py
midi_output.py
sound_switch_engine.py
automatic role-entry policy paths
tools/govee_*.py
```

Deliverables:

```text
adapter trigger path with default queue maxsize 8 and hard cap 16
trigger call target under 1 ms after dedupe/rate-limit and put_nowait/reject
adapter worker start/stop with 1.0 second shutdown timeout
Govee request timeout default 2.0 seconds
ordinary scene retrigger cooldown default 4 seconds
high-impact/drop cooldown default 12 seconds
drop flash duration max 750 ms
status dict including queue depth, degraded state, counters, and capability summary
mocked tests for queue-full, degraded adapter, timeout/send error, malformed response, status, bounds, and shutdown
```

Exit criteria:

```text
Adapter/config tests pass in isolation.
No bridge runtime file starts or exposes the adapter.
No bridge-side dry-run or live Govee output path exists yet.
No StateManager changes yet.
```

### Supporting Requirement Set 6: StateManager Manual/Status Wiring Gate

Goal:

```text
Make StateManager aware of LEDLookDirector only after standalone proof and isolated transport tests are safe.
Do not add automatic role-entry triggering yet.
```

Allowed files:

```text
state_manager.py
models.py
__main__.py
led_look_director.py
govee_scene_adapter.py
tests/test_led_state_manager.py
tests/test_runtime_status.py
```

Forbidden behavior:

```text
No Govee network/API calls in StateManager.
No config parsing in _push_tick.
No file I/O in _push_tick.
No blocking queue calls in _push_tick.
No per-tick Govee command sends.
No automatic role-entry behavior yet.
```

Deliverables:

```text
StateManager accepts optional LEDLookDirector/adapter dependencies
manual/emergency LED state is owned by StateManager event thread where needed
first bridge-runtime adapter output path is StateManager-owned manual command handling only
adapter trigger calls are bounded and non-blocking
status includes LED layer without breaking existing status keys
tests prove _push_tick does not call Govee client/network methods
tests prove disabled/not_configured LED layer is inert
```

Exit criteria:

```text
StateManager remains central coordinator.
No blocking Govee I/O occurs in _push_tick.
Manual override and blackout priorities are correct.
Existing laser and OS2L tests still pass.
```

### Supporting Requirement Set 6.5: Pre-Automation Manual Rehearsal Gate

Goal:

```text
Prove manual bridge control and LED failure isolation before automatic role-entry begins.
```

Required evidence:

```text
manual scene trigger works through the JSONL command path
manual blackout/off works through the JSONL command path
clear blackout works and does not clear unrelated manual state incorrectly
adapter failure, timeout, degraded state, and queue-full do not affect SoundSwitch or lasers
no command spam occurs during a realistic manual run
Govee latency is acceptable for section-level room cues, not beat/frame precision
status exposes queue depth, degraded reason, last error, dry_run/live state, and capability state without secrets
emergency blackout remains available even when automation is disabled
```

Exit criteria:

```text
Supervisor explicitly confirms:
PHASE APPROVED - PRE-AUTOMATION REHEARSAL GATE PASSED
```

Without that exact gate result, Supporting Requirement Set 7 must not begin.

### Supporting Requirement Set 7: Automatic Role-Entry Triggers Behind Explicit Enable Flag

Goal:

```text
Add automatic LED role-entry triggering without command spam.
Requires the Pre-Automation Manual Rehearsal Gate to have passed.
```

Allowed files:

```text
state_manager.py
led_look_director.py
led_models.py
tests/test_led_look_director.py
tests/test_led_state_manager.py
tests/test_golden_trace.py if needed for runtime invariants
```

Forbidden behavior:

```text
No command every tick.
No command every beat.
No fake strobe by repeated on/off calls.
No scene discovery during playback hot path.
No dependency on LaserDirector being enabled.
No hard-pairing LED looks to laser scenes.
```

Deliverables:

```text
role-entry trigger logic
bank rotation
dedupe
minimum interval/rate-limit
manual override priority
blackout priority
scripted-mode conservative default
tests for buildup/drop/breakdown/groove role-entry and no-spam behavior
```

Exit criteria:

```text
Repeated _push_tick calls do not spam adapter.trigger.
Drop/buildup/breakdown fire at most once per eligible entry.
Manual override beats automation.
Blackout beats manual override.
Bridge timing remains unaffected.
```

### Supporting Requirement Set 8: Rehearsal Validation And Health Checks

Goal:

```text
Make the system observable and rehearsable before event use.
```

Allowed files:

```text
validation_runner.py
runtime_status.py
docs/led_look_mapping_workflow.md
docs/govee_capability_notes.md
tests/test_validation_runner.py
tests/test_runtime_status.py
```

Deliverables:

```text
operator-readable validation checks
status degradation reasons
rehearsal checklist
manual fallback checklist
documented dry-run-to-live procedure
```

Exit criteria:

```text
Operator can see not_configured, invalid_config, disabled, dry_run, degraded, capability_missing, queue_warn, and ok states.
Manual fallback is documented and tested.
Live use remains opt-in.
```

### Supporting Requirement Set 9: Rollback, Runbook, And Supervisor Handoff

Goal:

```text
Prepare a safe handoff before any event-facing use.
```

Allowed files:

```text
docs/led_look_mapping_workflow.md
docs/led_operator_runbook.md
docs/govee_capability_notes.md
```

Deliverables:

```text
rollback instructions by phase
how to disable LED layer quickly
how to clear manual override
how to trigger blackout/off
how to confirm no secret exposure
how to collect sanitized failure evidence
known unsupported capabilities
```

Exit criteria:

```text
Supervisor can disable or roll back the LED layer without touching lasers or SoundSwitch.
Known live-test evidence is sanitized and documented.
```

### Supporting Requirement Set 10: Optional Future Work Only

Goal:

```text
Keep nonessential ideas out of v1 until the basic integration is proven.
```

Allowed future scopes:

```text
external govee_worker.py process
Laser Pad LED tab
zone-aware multi-target looks
laser/LED compatibility metadata
subscribe-device-event handling
advanced UI mapping
capability cache
```

Exit criteria:

```text
Only begin optional future work after JSONL manual live output, StateManager wiring, pre-automation rehearsal validation, automatic role-entry, and rollback docs are complete.
```

---

## 37. Testing Strategy

Test categories:

```text
config validation
secret-field rejection
manual command parsing
dry-run adapter behavior
bounded queue behavior
status provider behavior
LEDLookDirector priority policy
bank selection
role-entry triggering
dedupe behavior
rate-limit behavior
capability-missing behavior
failure/degraded states
disabled isolation
official API grounding report for API-code phases
worker shutdown
StateManager hot-path isolation
```

Important tests:

```text
disabled LED layer does nothing
invalid config does not break bridge startup
config rejects api_key/token/secret/authorization fields
GOVEE_API_KEY is read only from environment
logs/status/test fixtures do not expose GOVEE_API_KEY
manual override beats automation
blackout beats manual override
not playing does not spam commands
stale position does not spam commands
same look does not retrigger every tick
automatic role-entry does not trigger every beat
adapter queue full is non-fatal
degraded adapter rejects without blocking
adapter worker shutdown is bounded
rate-limit/circuit-breaker behavior is visible
Govee error becomes status/log state
capability missing disables scene look cleanly
unsupported scene disables only affected looks
malformed Govee responses fail soft
StateManager._push_tick never calls Govee network/client methods directly
laser output remains independent
OS2L output remains independent
```

No unit test should require live Govee hardware.

Live integration tests should be opt-in only, never default.

---

## 38. Documentation Plan

Docs to add later:

```text
docs/plans/led_agent_orchestrator_workflow.md
```

Controlling phase-gated automation workflow. The orchestrator is required alongside this integration plan before handing the work to an implementation agent.

```text
docs/led_look_director_design.md
```

Implementation design once scope is approved.

```text
docs/led_look_mapping_workflow.md
```

Operator workflow for creating Govee scenes and mapping them to bridge looks.

```text
docs/govee_capability_notes.md
```

Sanitized notes on official API grounding, confirmed device capabilities, model behavior, unsupported scenes, and fallback behavior. Must not contain secrets.

```text
docs/architecture/current_architecture.md
```

Update only after implementation exists.

```text
docs/architecture/runtime_invariants.md
```

Update only after implementation exists.

This document stays as the planning record.

---

## 39. Rollout Plan

Conservative rollout:

```text
Follow the phase roadmap in docs/plans/led_agent_orchestrator_workflow.md when the orchestrator is present.
This plan's rollout section is reference context for the same safety shape:
- standalone Govee capability discovery before bridge runtime changes
- manual live proof before StateManager integration
- config and dry-run behavior before real output transport
- explicit StateManager gate before any StateManager changes
- automatic triggers only after manual paths and no-spam safeguards pass
- rehearsal hardening, rollback notes, and optional future UI/worker work last
```

Default state:

```text
Before manual live proof:
  enabled = false
  dry_run = true

After manual proof, isolated adapter tests, StateManager-owned manual bridge output, and the pre-automation rehearsal gate pass:
  live config may default to enabled = true
  dry_run = false requires explicit live config and capability-backed target mapping
  automation_enabled must remain false until Phase 8 explicitly opens automation
```

Hard gate:

```text
Do not touch state_manager.py before the orchestrator Phase 6 gate explicitly opens StateManager LED changes.
Do not run live Govee calls before Phase 2 Supervisor approval.
Do not enable automatic role-entry before the pre-Phase-8 rehearsal gate and orchestrator Phase 8 approval.
```

---

## 40. Risk Register

### Govee Latency

Govee scene triggering may not be beat-perfect. Treat it as section-level room lighting, not frame-accurate DMX.

### API Limits

Repeated commands may fail or lag. Use role-entry triggers, dedupe, and rate limiting.

### API Reference Drift Or Ambiguity

The Govee Developer Platform docs and supported capabilities may change. Every phase that writes API code must inspect current official docs and stop if endpoint, header, payload, capability, or scene-control details are ambiguous.

### API Key Exposure

The API key must come only from `GOVEE_API_KEY` in the environment. Any exposure in config, logs, status, docs, screenshots, fixtures, or command files is a phase failure.

Official docs may include example keys, request headers, device IDs, MQTT usernames/passwords, or topics. Those examples must be redacted before appearing in generated artifacts.

### Scene Capability Uncertainty

A supported model may still expose limited scene controls through a given route. Capability discovery must confirm what is actually usable.

### Control Route Differences

Cloud/platform API and LAN/local control may expose different capabilities. The adapter should report the route and capability actually used.

### Network Failure

Cloud or LAN control can fail. Failure should not affect the bridge.

### Worker Thread Bugs

The adapter worker must be bounded, daemon-safe, and fail-soft. It should not block shutdown or hold bridge-critical locks.

### Crowd Comfort

The LEDs surround people. Avoid sustained full-room strobe and repeated high-brightness impact looks.

### Overcoupling With Lasers

Hard-pairing laser and LED scenes will reduce variety. Keep banks separate.

### UI Scope Creep

Do not build UI before backend proof.

### Config Complexity

Keep v1 config simple. Operators should be able to edit LED config safely without needing to understand unrelated bridge internals.

---

## 41. Success Criteria

### Initial Success

```text
Bridge can manually trigger a named LED look in dry-run.
Bridge can manually trigger a named LED look for real if capability exists.
Bridge can blackout/off room LEDs if supported.
Bridge status reports LED layer state.
Capability mismatch is reported cleanly.
LED failure does not affect SoundSwitch or lasers.
Official Govee API grounding is documented before live API code.
No secrets are stored, logged, printed, or committed.
```

### Automation Success

```text
Bridge triggers ambient/groove/buildup/drop/breakdown LED looks on role-entry.
LED layer does not spam commands.
Manual override works during playback.
Emergency blackout wins.
Laser output remains independent.
```

### Creative Success

```text
Room LEDs create crowd atmosphere.
Lasers remain the sharp show layer.
The two systems feel coordinated without being hard-paired.
The room feels like a mini EDM venue instead of a smart-home demo that discovered bass.
```

---

## 42. Open Questions For Later

Do not block planning on these.

```text
Which exact Govee strip models are used?
How many strips/devices/zones exist?
Which scene types do they expose?
Which control route exposes the desired scenes most reliably?
Will one command control all strips or will multiple zones be triggered?
Should LEDs run during scripted SoundSwitch tracks?
Should LED personalities follow the existing laser personality resolver?
Should LED banks be genre-based, energy-based, or both?
How should brightness caps be represented?
Should strobe looks require explicit high-impact enable?
Should LED mapping live inside the existing Laser Pad UI later?
Should scene discovery be cached locally?
Which optional control surface, if any, should follow the v1 JSONL command path later?
Should an external govee_worker process be added only after adapter testing?
```

---

## 43. Final Summary

The LED Look Director should be a shallow, isolated auxiliary output lane for Govee RGBIC/RGBICW room-perimeter LEDs.

It should:

```text
consume existing bridge timing and phrasing context
keep StateManager as coordinator
choose room-level LED looks
trigger Govee actions through a non-blocking adapter
use a bounded queue/worker transport pattern
support manual override and blackout
capability-gate scene support
stay out of the hot path
fail soft
remain independent from lasers
```

The integration should not try to make Govee behave like DMX.

The practical target is:

```text
At meaningful musical moments, the bridge chooses a room-perimeter LED look and queues a Govee command safely, while the rest of the bridge keeps doing its job.
```

That is the corrected clean integration plan.
