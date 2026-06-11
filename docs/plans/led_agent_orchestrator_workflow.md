# LED Look Director Agent Orchestrator Workflow

Status: Full Automation Prompt Pack
Target environment: Cursor with access to Codex and Sonnet or GPT-5.5 reviewer by default; Opus only for escalation
Target repo: `rb_ss_bridge_v2` / `PYTHON-BRIDGE`
Target feature: Govee RGBIC/RGBICW room-perimeter LED integration via `LEDLookDirector` + `GoveeSceneAdapter`

---

## 0. User Configuration

The workflow is configured with these user decisions:

```text
Autonomy level:
  Aggressive. Agents may proceed phase-to-phase if gates pass.

Implementation agent:
  Codex.

Supervisor/reviewer:
  Sonnet or GPT-5.5 by default.
  Escalate to Opus only for StateManager gate review, unresolved architecture/API ambiguity, repeated failed revisions, or a larger-scope final review.

Execution environment:
  Cursor.

Live Govee API calls:
  Allowed.
  Must still be grounded in official Govee docs and phase-approved by the Supervisor.

StateManager gate:
  Hard gate required before touching StateManager.

Default bridge integration mode:
  Govee output enabled by default once bridge integration exists.

Prompt structure:
  Full automation controller + embedded phase specs.

Required companion integration plan:
  docs/plans/led_look_director_integration_plan_revised.md

Required repo-local documents before Phase 1:
  docs/plans/led_agent_orchestrator_workflow.md
  docs/plans/led_look_director_integration_plan_revised.md
  If either file is missing from the repo docs directory, stop before Phase 1.

Document precedence:
  This orchestrator controls phase order, gates, allowed files, forbidden files, stop conditions, and agent prompts.
  The integration plan is required architecture/design context for creative intent, runtime boundaries, config concepts, and safety rationale.
  If the integration plan and this orchestrator conflict, this orchestrator wins for execution control.
  If either document is stricter about secrets, hot-path safety, StateManager boundaries, or Govee API grounding, apply the stricter rule.

Tests:
  Required only for bridge runtime changes.
  Standalone diagnostic tools may use agent-run dry-runs and sanitized live outputs.
  Human verification is only for physical LED behavior that agents cannot observe directly.

Names:
  LEDLookDirector
  GoveeSceneAdapter
  led_look_director.json
  led_look_director.example.json

Supervisor authority:
  Supervisor may require reverts for phase violations.

Human/operator boundary:
  Human input is only for physical LED handling, Govee app/account/environment setup, or confirming observed light behavior.
  The Supervisor owns code review, phase approval, rollback decisions, and architecture enforcement.

Output:
  Master orchestrator + implementation + supervisor prompts in one document.
```

Important reality check: “aggressive” does **not** mean “skip gates.” It means the agents may continue automatically **after** gates pass.

### 0.1 Automation Contract

The purpose of this orchestrator is to minimize human interruption. The Master Orchestrator must keep moving without asking the human for decisions that can be made from repository evidence, tests, official documentation, sanitized live-call output, or Supervisor review.

AI-owned decisions:

```text
phase readiness
file-scope compliance
code-review approval/rejection
test interpretation
rollback decision for current-phase edits
official-doc sufficiency or ambiguity
whether a failed phase should retry or stop
whether Opus escalation is needed under the review-model policy
```

Human/operator-only gates:

```text
make GOVEE_API_KEY available in the environment without revealing it
power/pair/name/reach the physical Govee device
create/select Govee app scenes if the API cannot expose or create them
confirm whether LEDs visibly changed, blacked out, or behaved safely
fix local network/account/hardware state outside agent control
approve event-facing use after rehearsal evidence exists
```

The orchestrator must not ask the human to approve ordinary code changes, interpret tests, choose between safe implementation details, police the phase allowlist, or decide whether official API shapes are trustworthy. Those are Supervisor responsibilities.

### 0.2 Review Model Policy

Default reviewer:

```text
Sonnet or GPT-5.5.
```

Use the default reviewer for normal phase reviews, focused implementation diffs, command parsing, tests, config validation, docs, and small revisions.

Escalate to Opus only when one of these is true:

```text
Phase 6 StateManager gate approval is requested.
The Supervisor cannot resolve an architecture conflict between docs and code.
Official Govee docs are ambiguous and proceeding would require interpretation.
The same phase is rejected three times.
A broad final readiness review is requested after core phases pass.
```

Opus escalation is an AI review escalation, not a human gate.

---

## 1. High-Level Goal

Implement Govee LED room-perimeter control into the bridge as a separate LED output lane.

The target architecture:

```text
StateManager
  ├── SoundSwitchEngine / OS2L
  ├── LaserDirector → LaserSceneExecutor → MidiOutput
  └── LEDLookDirector → GoveeSceneAdapter → Govee API/LAN/cloud route → RGBIC/RGBICW strips
```

The LED strips are around the room/crowd. They are the **room envelope** lighting layer, not DJ booth accents and not laser sidekicks.

The creative role:

```text
Lasers:
  sharp, aerial, high-impact, fixture-specific looks

Govee room LEDs:
  ambient room mood, crowd envelope, perimeter movement,
  buildup tension, drop impact support, breakdown reset

Manual control:
  force look, blackout, clear override, auto resume
```

The technical role:

```text
LEDLookDirector:
  policy-only creative decision layer

GoveeSceneAdapter:
  output transport layer with non-blocking trigger path and worker-owned I/O
```

---

## 2. Non-Negotiable Architecture Rules

These rules apply to every phase.

### 2.1 StateManager Remains Coordinator

`StateManager` owns runtime coordination. The LED system may consume `StateManager`-owned context but must not become an independent timing authority.

Allowed later:

```text
StateManager computes context.
StateManager calls LEDLookDirector.tick(...).
StateManager hands LED decision to GoveeSceneAdapter.trigger(...).
```

Forbidden:

```text
Govee adapter reads Rekordbox state directly.
Govee adapter computes its own timing.
Govee adapter mutates DeckState or OutputState.
Govee adapter blocks StateManager.
```

### 2.2 No Blocking I/O In The Hot Path

No Govee network/API/LAN/cloud work may occur inside `StateManager._push_tick`.

Forbidden in the hot path:

```text
HTTP requests
LAN socket calls
cloud API calls
DNS
scene discovery
device discovery
file I/O
config parsing
sleep
retry loops
blocking queue operations
long validation
subprocess calls
```

Allowed in the hot path:

```text
bounded LEDLookDirector decision
bounded GoveeSceneAdapter.trigger(...)
put_nowait-style queueing
immediate rejection if queue full/degraded
```

### 2.3 Adapter Thread Is Allowed

A worker thread inside `GoveeSceneAdapter` is allowed if it follows the existing output transport pattern:

```text
public trigger = bounded and non-blocking
worker = owns slow I/O
queue = bounded
failure = degraded status, not bridge crash
```

This mirrors the bridge’s existing `MidiOutput` pattern. The rule is not “no threads.” The rule is “no blocking I/O in StateManager.”

### 2.4 Hard Gate Before Touching StateManager

No modification to `state_manager.py` is allowed until the standalone Govee capability capture and manual trigger phases pass.

If Codex touches `state_manager.py` before the gate:

```text
Supervisor must reject the phase.
Supervisor must instruct Codex to revert that file.
Phase cannot pass.
```

### 2.5 Secrets Rule

`GOVEE_API_KEY` must only come from the environment.

Forbidden:

```text
hardcoded key
key in committed config
key in docs
key in tests
key in logs
key printed to terminal
key in sample files
key in exception messages
```

Allowed:

```text
os.environ["GOVEE_API_KEY"]
clear error if missing
redacted status/logs
```

Config validation must fail if committed config/example/config fixtures contain obvious secret-bearing keys:

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

### 2.6 Govee API Reference Grounding Requirements

Codex must inspect current official Govee Developer Platform references before writing or changing any code that:

```text
performs Govee API requests
parses Govee API responses
defines endpoint constants
defines request payloads
interprets capability names
interprets scene-control formats
implements dynamic scene control
implements device status/control calls
```

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

Codex must prefer the official Markdown/OpenAPI material linked from `llms.txt` when available. The getting-started page explicitly points AI agents to `llms.txt`; use that as the official discovery index.

Codex must not infer these from memory, old examples, third-party snippets, package defaults, or guesses:

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

Before Phase 1 API code is accepted, Codex must provide an official-source extraction summary covering:

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
current API-key security policy and key-rotation implications
```

If official docs are incomplete, ambiguous, contradictory, unavailable, or do not describe how to trigger the desired scene/control format for the target device, Codex must stop and report the ambiguity. It must not guess.

Official examples are not exempt from the secrets rule. Any copied or summarized sample request, response, MQTT credential, topic, API key, device ID, or header from official docs must be sanitized before it appears in phase reports, `/tmp` summaries, docs, tests, logs, screenshots, or terminal output.

### 2.7 Default Govee Output Behavior

User chose:

```text
Govee output enabled by default once bridge integration exists.
```

However, this must still be implemented safely:

```text
enabled=true is allowed in the example/live config only after manual trigger proof passes.
dry_run may be false only when explicitly configured.
capability discovery must gate unavailable features.
manual blackout/off must exist before automatic role-entry triggers.
```

In other words: yes, default real output is allowed, but not before the bridge has proof that the Govee path works.

### 2.8 Tests

Tests are required for bridge runtime changes.

Standalone tool phases may rely on manual live verification, but should still be written defensively.

Runtime phases require tests for:

```text
config validation
secret-field rejection
command parsing
manual override priority
blackout priority
non-spam behavior
disabled/degraded behavior
adapter queue-full behavior
adapter worker bounded shutdown
malformed Govee response handling
status provider failure handling
rate-limit/circuit-breaker visibility
not-playing and stale-position no-spam behavior
unsupported scene disables only affected looks
StateManager integration if touched
StateManager hot-path isolation
official API grounding when API code is touched
```

### 2.9 Repo-Local Implementation Contracts

Implementation must follow the existing bridge patterns in this checkout:

```text
Transport pattern:
  midi_output.MidiOutput is the model for a bounded, non-blocking public trigger path and worker-owned I/O.

Runtime command pattern:
  runtime_status.CommandReader parses /tmp/rb_ss_bridge_v2_commands.jsonl.
  __main__.py callbacks enqueue BridgeEvent objects with put_nowait.
  state_manager.StateManager._handle_event owns long-lived show state.

Status pattern:
  runtime_status.StatusWriter uses safe provider callbacks.
  Provider failure must return a degraded/default status block, not crash status writing.

Validation pattern:
  validation_runner.ValidationRunner checks runtime health from already-available status/config/queue data only.
  Validation must not perform Govee network calls.

StateManager hot-path pattern:
  _push_tick may build immutable context from values it already computed.
  _push_tick may call bounded policy/adapter methods only after the StateManager gate opens.
  _push_tick must not call adapter status(), Govee client methods, config loaders, file I/O, network I/O, or blocking queue operations.
```

Phase 4 manual runtime command work is pre-gate. It may add strict command parsing, callbacks, diagnostic non-blocking adapter handoff, and status visibility. It must not create durable manual override, blackout latch, or auto-resume policy state outside StateManager. Durable LED policy state starts in Phase 7 after the StateManager gate opens.

---

## 3. Agent Roles

### 3.1 Master Orchestrator

The Master Orchestrator runs the phase loop.

Responsibilities:

```text
choose current phase
send implementation instructions to Codex
send diff/results to Supervisor
receive approval/rejection
if rejected, send revision instructions to Codex
repeat until phase approved
advance automatically to next phase when gate passes
stop on hard blocker
```

The orchestrator should not let Codex skip phases.

### 3.2 Codex Implementation Agent

Codex writes code.

Responsibilities:

```text
implement only the current phase
respect allowed/forbidden file list
keep diffs focused
run relevant commands/tests when possible
summarize changed files
summarize behavior
report risks
stop at phase boundary
```

Codex must not invent future phases early.

### 3.3 Supervisor Agent

The configured Supervisor reviews strictly. Use Sonnet or GPT-5.5 for normal phase reviews and reserve Opus for the escalation cases defined in Section 0.2.

Responsibilities:

```text
inspect diff
check phase boundary
check architecture rules
check secrets handling
check hot-path behavior
check test coverage if runtime touched
check failure/degraded behavior
approve or reject phase
require revisions or file reverts when needed
```

The Supervisor should be skeptical and should reject unclear, out-of-scope, untested, or unsafe changes instead of approving speculative progress.

---

## 4. Master Orchestrator Prompt

Use this as the top-level Cursor instruction.

```text
You are the Master Orchestrator for the LED Look Director integration in the rb_ss_bridge_v2 / PYTHON-BRIDGE repo.

You control a two-agent workflow:
- Codex is the Implementation Agent.
- The configured Supervisor model is the Supervisor/Reviewer Agent.
- Use Sonnet or GPT-5.5 for normal reviews.
- Escalate to Opus only for the Phase 6 StateManager gate, unresolved architecture/API ambiguity, repeated failed revisions, or broad final readiness review.

Autonomy mode:
- Aggressive.
- You may proceed phase-to-phase automatically only after the Supervisor approves the current phase.
- You may automatically request revisions from Codex when the Supervisor rejects a phase.
- You must never skip a gate.

Feature goal:
Implement Govee room-perimeter LED support using:
- LEDLookDirector as the policy layer.
- GoveeSceneAdapter as the output transport layer.
- led_look_director.json / led_look_director.example.json for config.

Required documents:
- Controlling workflow: docs/plans/led_agent_orchestrator_workflow.md
- Required integration plan/reference: docs/plans/led_look_director_integration_plan_revised.md

Before Phase 1, verify both required documents exist in the repo docs directory.
If either required document is missing, stop and report the missing file instead of continuing from memory or copied paths.

Use the integration plan for architecture intent, creative model, config concepts, and safety rationale.
Do not let the integration plan's phase section override this orchestrator's phase order, gates, allowed files, forbidden files, stop conditions, or agent prompts.
If the two documents appear to conflict, route the conflict to the Supervisor; this orchestrator remains authoritative for execution control, and the stricter safety rule applies.

Critical architecture rules:
1. StateManager remains coordinator.
2. No blocking Govee I/O in StateManager._push_tick.
3. GoveeSceneAdapter may use a bounded queue and worker thread, modeled after MidiOutput.
4. Public adapter trigger path must be bounded and non-blocking.
5. GOVEE_API_KEY must only be read from the environment.
6. Never hardcode, print, commit, or log the API key.
7. Codex must inspect official Govee docs / llms.txt / Markdown/OpenAPI before writing API code.
8. Codex must not infer endpoint paths, base URLs, auth headers, payload shapes, capability names, or scene-control formats from memory.
9. No StateManager changes until standalone Govee capability capture and manual trigger phases pass.
10. Supervisor may require reverts for phase violations.
11. Tests are required for bridge runtime changes.
12. Standalone tools may make live Govee API calls because the user explicitly allowed them, but only through explicit --live commands after official API grounding and Supervisor phase approval.
13. Human input is only for physical LED handling, Govee app/account/environment setup, or confirming observed light behavior.
14. Do not ask the human for ordinary phase approval, code-review decisions, rollback decisions, test interpretation, file-scope policing, or API-shape guessing.
15. Human approval is not required for live Govee API calls when a phase allows live calls, official API grounding is complete, the Supervisor approves the exact command, and GOVEE_API_KEY is already present in the environment.

Workflow:
For each phase:
1. Send the current phase implementation prompt to Codex.
2. Let Codex implement.
3. Collect:
   - changed files
   - diff summary
   - run commands
   - test results, sanitized live-output evidence, and any required operator visual confirmation
   - known risks
   - official Govee source extraction for API-code phases
   - sanitized live-call evidence if live Govee calls ran
4. Send the supervisor prompt and current diff/results to the Supervisor.
5. If Supervisor rejects:
   - send its findings to Codex as a revision prompt
   - require fixes/reverts
   - repeat review
6. If Supervisor approves:
   - mark phase approved
   - proceed to next phase automatically unless the phase has a declared manual human data dependency.
7. Stop if:
   - API key is missing from the environment and the human must make it available without revealing it
   - live Govee capability cannot be determined
   - required hardware is offline
   - tests fail and Codex cannot fix
   - official Govee docs are ambiguous or unavailable and the Supervisor cannot approve proceeding
   - Supervisor declares architecture violation unresolved

Current starting phase:
Phase 1: Standalone Govee capability capture.

Do not begin Phase 2 until Phase 1 passes Supervisor review and the expected /tmp summary files exist. If physical LED behavior must be confirmed, request only that operator observation before advancing.
```

---

## 5. Codex Base Prompt

Every Codex implementation request should include this base prompt before phase-specific instructions.

```text
You are Codex, the Implementation Agent for the LED Look Director integration.

Follow the current phase only. Do not jump ahead.

Required documents:
- Read and apply this orchestrator workflow for phase scope and gates.
- Read and apply docs/plans/led_look_director_integration_plan_revised.md for architecture intent, creative model, config concepts, and safety rationale.
- Treat this orchestrator as authoritative for phase order, allowed files, forbidden files, stop conditions, and agent prompts.
- If the integration plan is stricter about secrets, hot-path safety, StateManager boundaries, or Govee API grounding, follow the stricter rule.

Global architecture rules:
- StateManager remains coordinator.
- Do not touch state_manager.py until the explicit StateManager gate has passed.
- No blocking Govee I/O may ever be placed in StateManager._push_tick.
- LEDLookDirector is policy only.
- GoveeSceneAdapter is output transport only.
- GoveeSceneAdapter public trigger path must be bounded and non-blocking.
- Any real Govee I/O must be worker-owned or outside the hot path.
- GOVEE_API_KEY must only be read from the environment.
- Never hardcode, print, commit, or log secrets.
- Before writing API code, inspect official Govee docs / llms.txt / Markdown/OpenAPI.
- Do not infer endpoint paths, base URLs, auth headers, payload shapes, capability names, or scene-control formats from memory.
- If official docs are ambiguous or incomplete, stop and report that ambiguity.
- Keep diffs small and phase-scoped.
- Tests are required for bridge runtime changes.
- Standalone tool phases may use live Govee API calls only through explicit --live commands after official API grounding and Supervisor phase approval.
- Stop at the phase boundary and report results.

After implementation, always report:
1. Files changed.
2. What was implemented.
3. Commands/tests to run.
4. Whether any live Govee calls were made.
5. Which official Govee references were inspected if API code was touched.
6. Any risks or unresolved issues.
7. Confirmation that forbidden files were not touched.
```

---

## 6. Supervisor Base Prompt

Every supervisor review should include this base prompt before phase-specific review checks.

```text
You are the configured Supervisor model, the Supervisor/Reviewer Agent for the LED Look Director integration.

Your job is to be strict, skeptical, and architecture-protective.

Review the implementation for the current phase only.

Required document checks:
- Check the implementation against this orchestrator workflow.
- Check the implementation against docs/plans/led_look_director_integration_plan_revised.md for architecture intent, creative model, config concepts, and safety rationale.
- Reject if either required repo-local document is missing.
- If the documents conflict, enforce this orchestrator for phase order, allowed files, forbidden files, stop conditions, and agent prompts.
- Enforce whichever document is stricter about secrets, hot-path safety, StateManager boundaries, or Govee API grounding.

Global review rules:
- Reject if the implementation jumped ahead.
- Reject if forbidden files were touched.
- Reject if state_manager.py was touched before the StateManager gate passed.
- Reject if GOVEE_API_KEY is hardcoded, printed, committed, or logged.
- Reject if config/example/test fixtures include API key/token/secret/auth fields.
- Reject if Govee API code was written without current official-doc grounding.
- Reject if endpoint paths, base URLs, auth headers, payload shapes, capability names, or scene-control formats appear guessed or memory-derived.
- Reject if official docs are ambiguous and Codex guessed anyway.
- Reject if bridge hot path includes blocking I/O.
- Reject if Govee network/API calls are placed inside StateManager._push_tick.
- Reject if the LED policy layer performs transport I/O.
- Reject if the adapter public trigger path can block.
- Reject if runtime changes lack tests.
- Reject if default behavior is unsafe for the current phase.
- Require revert if a phase boundary was violated.
- Approve only if pass criteria are met.

Return exactly one of:
- PHASE APPROVED
- PHASE REJECTED

If rejected:
- list required fixes
- list files to revert if necessary
- state whether the implementation may retry

If approved:
- briefly state why
- list any follow-up risks for next phase
```

---

## 7. Phase Roadmap

```text
Phase 1: Standalone Govee capability capture
Phase 2: Standalone manual Govee trigger
Phase 3: LED bridge skeleton, dry-run/status/config only
Phase 4: Manual LED runtime command path
Phase 5: Real GoveeSceneAdapter transport
Phase 6: Hard gate review before StateManager changes
Phase 7: StateManager LED manual/status ownership, no automation
Phase 8: Automatic LED role-entry triggers
Phase 9: Rehearsal hardening and docs
Phase 10: Optional UI planning / mapping surface
Phase 11: Optional external worker process only if needed
```

---

## 8. Phase 1: Standalone Govee Capability Capture

### Objective

Create a standalone diagnostic tool that proves the Mac can see the Govee H612D/H612DAD1 device and can discover capabilities/scenes.

No bridge runtime integration.

### Allowed Files

```text
tools/govee_capability_capture.py
```

### Forbidden Files

```text
state_manager.py
laser_director.py
laser_executor.py
midi_output.py
sound_switch_engine.py
osl_output.py
runtime_status.py
models.py
__main__.py
config/*.json
```

### Codex Phase Prompt

```text
Proceed with Phase 1 only.

Create a standalone diagnostic script at:
tools/govee_capability_capture.py

Requirements:
- Do not modify bridge runtime files.
- Before writing API request code, inspect:
  - https://developer.govee.com/docs/getting-started
  - https://developer.govee.com/docs/support-product-model
  - https://developer.govee.com/llms.txt
  - the official Markdown/OpenAPI material linked from llms.txt
  - Get You Devices
  - Get Device State
  - Get Dynamic Scene
  - Control You Device
  - Subscribe Device Event
  - the API key security policy/changelog
- Extract base URL, auth header/API-key usage, device listing endpoint, status endpoint, dynamic scene endpoint, control endpoint, request fields, response fields, capability format, and scene-control format.
- Extract supported-model evidence for H612D/H612DAD1 if documented, but do not treat model support as proof of scene support.
- Extract current API-key security and key-rotation implications.
- Explicitly state whether Subscribe Device Event/MQTT is irrelevant to v1 or deferred.
- Save that official-source extraction summary to /tmp/govee_api_reference_summary.txt.
- Stop and report ambiguity instead of guessing if the official docs are incomplete or unclear.
- Do not infer endpoint paths, headers, payloads, capability names, or scene formats from memory.
- Sanitize official examples before writing them to /tmp summaries, reports, logs, tests, or terminal output.
- Include --dry-run as the default mode.
- Require --live for any real Govee API call.
- Do not make live Govee API calls unless Supervisor has approved the exact --live command for this phase.
- Read GOVEE_API_KEY from the environment.
- Refuse --live if GOVEE_API_KEY is missing.
- Use Govee Developer Platform API references for:
  1. listing devices/capabilities,
  2. querying dynamic scenes for a target device if supported.
- List all devices in a redacted summary.
- Find devices whose sku/model contains H612D or whose name contains ROOM_PERIMETER.
- Save raw device response to /tmp/govee_h612d_devices.json.
- If a matching target is found, query available dynamic scenes/capabilities for that target.
- Save raw scene response to /tmp/govee_h612d_scenes.json.
- Write readable summary to /tmp/govee_h612d_summary.txt.
- Redact the API key from all output.
- Redact full device IDs in printed summaries.
- Use short network timeouts.
- Handle HTTP errors cleanly.
- Do not retry aggressively.
- Do not loop.
- Do not start background workers.
- Do not integrate with StateManager.
- Do not import bridge runtime modules.
- Make no live Govee API calls unless executed with --live after Supervisor approval.
- Prefer standard library if reasonable; if adding a dependency, justify it.

After implementation:
- Show diff summary.
- Explain how to run:
  python3 tools/govee_capability_capture.py --dry-run
- Explain the live run command that Supervisor must approve before execution:
  python3 tools/govee_capability_capture.py --live
- Explain expected outputs:
  /tmp/govee_api_reference_summary.txt
  /tmp/govee_h612d_devices.json
  /tmp/govee_h612d_scenes.json
  /tmp/govee_h612d_summary.txt
- Stop.
```

### Run Command

```bash
python3 tools/govee_capability_capture.py --dry-run

# After Supervisor approves the exact live command for Phase 1:
python3 tools/govee_capability_capture.py --live
cat /tmp/govee_h612d_summary.txt
ls -lh /tmp/govee_h612d_*
```

### Supervisor Review Checklist

```text
Review Phase 1.

Required:
- Only allowed files changed.
- No bridge runtime files modified.
- Official Govee docs / llms.txt / Markdown/OpenAPI were inspected before API code was written.
- /tmp/govee_api_reference_summary.txt exists and includes base URL, auth header/API-key usage, endpoints, methods, payload fields, response fields, capability format, and scene-control format.
- /tmp/govee_api_reference_summary.txt includes supported-model evidence and current API-key security/key-rotation policy.
- Official examples were sanitized before appearing in generated artifacts or reports.
- Codex did not guess endpoint paths, headers, payloads, capability names, or scene formats.
- GOVEE_API_KEY read only from environment.
- Live calls require --live and Supervisor approval.
- API key not printed/logged/saved.
- Device IDs redacted in summaries.
- Raw JSON saved to /tmp.
- Summary saved to /tmp.
- Handles missing API key.
- Handles no matching H612D/ROOM_PERIMETER target.
- Handles HTTP failures.
- Uses short timeout.
- No retries/loops/background workers.
- No StateManager/Laser/SoundSwitch imports.
- Does not proceed to Phase 2.

Reject if any forbidden file changed or secrets are mishandled.
```

### Pass Criteria

```text
Script exists.
Script runs in --dry-run without making live Govee calls.
Live capture runs only with --live after Supervisor approval.
Official API reference summary is created.
Summary file is created.
Device/capability response is saved.
If H612D device is found, scene response is attempted and saved.
Supervisor approves.
```

---

## 9. Phase 2: Standalone Manual Govee Trigger

### Objective

Prove one-shot manual control outside the bridge.

### Allowed Files

```text
tools/govee_manual_trigger.py
```

Optional small edits:

```text
tools/govee_capability_capture.py
```

only if Phase 1 output compatibility requires it.

### Forbidden Files

```text
state_manager.py
runtime_status.py
models.py
__main__.py
```

### Codex Phase Prompt

```text
Proceed with Phase 2 only.

Create a standalone manual trigger script at:
tools/govee_manual_trigger.py

Requirements:
- Do not modify bridge runtime files.
- Re-read /tmp/govee_api_reference_summary.txt if present.
- Re-check official Govee docs / llms.txt / Markdown/OpenAPI before writing control or dynamic-scene request code.
- Stop and report ambiguity instead of guessing if the official docs do not clearly define control payloads, dynamic scene format, or required fields.
- Do not infer endpoint paths, headers, payloads, capability names, or scene formats from memory.
- Read GOVEE_API_KEY from environment.
- Do not hardcode, print, save, or log the API key.
- Load target device information from /tmp/govee_h612d_devices.json when available.
- Use /tmp/govee_h612d_scenes.json when available.
- Allow selecting a target by:
  - H612D match,
  - ROOM_PERIMETER name match,
  - explicit CLI argument if needed.
- Allow triggering one scene by scene id/name if dynamic scenes are available.
- Allow basic fallback commands if scene support is unavailable:
  - off/blackout if supported,
  - brightness if supported,
  - solid color if supported.
- Include --dry-run.
- Require --live for real Govee API calls.
- Do not make live Govee API calls unless Supervisor has approved the exact --live command for this phase.
- Include a safe --off or --blackout-style command if available.
- Use short network timeouts.
- Do not retry aggressively.
- Do not loop.
- Do not spam commands.
- Save result JSON to /tmp/govee_h612d_trigger_result.json.
- Print concise redacted result summary.
- Do not integrate with StateManager.
- Do not import bridge runtime modules.
- Live Govee API calls are allowed only when using --live after Supervisor approval.

After implementation:
- Show diff summary.
- Show example run commands.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 2.

Required:
- Only allowed files changed.
- No bridge runtime files modified.
- Official API grounding from Phase 1 is used or refreshed.
- Control/dynamic-scene request shape is traceable to official docs.
- No guessed endpoint/header/payload/capability/scene format.
- GOVEE_API_KEY read only from environment.
- No secret output.
- Uses Phase 1 /tmp data where possible.
- Supports dry-run.
- Requires --live for live calls and only runs live after Supervisor approval.
- Supports one-shot scene trigger if capability exists.
- Supports one-shot fallback off/basic command if available.
- Uses short timeout.
- No loops/spam/aggressive retry.
- Saves result JSON to /tmp.
- Does not proceed to bridge integration.
```

### Pass Criteria

```text
Manual dry-run works.
Manual live off/basic command works or reports unsupported clearly.
Manual live scene trigger works if scenes are exposed.
Unsupported or ambiguous official scene/control docs stop the phase instead of guessing.
Result JSON saved.
Supervisor approves.
```

---

## 10. Phase 3: LED Bridge Skeleton, Config, Dry-Run Status

### Objective

Add bridge-side LED architecture skeleton without real Govee I/O from the bridge.

### Allowed Files

```text
led_models.py
led_config.py
led_look_director.py
govee_scene_adapter.py
config/led_look_director.example.json
tests/test_led_config.py
tests/test_led_look_director.py
tests/test_govee_scene_adapter.py
```

### Forbidden Files

```text
state_manager.py
runtime_status.py
models.py
__main__.py
```

### Codex Phase Prompt

```text
Proceed with Phase 3 only.

Goal:
Add an isolated LED Look Director bridge skeleton with dry-run/status/config behavior only.

Allowed files:
- led_models.py
- led_config.py
- led_look_director.py
- govee_scene_adapter.py
- config/led_look_director.example.json
- tests for these modules

Requirements:
- No StateManager changes.
- No runtime command integration yet.
- No real Govee API calls from bridge modules yet.
- LEDLookDirector must be policy-only.
- GoveeSceneAdapter must be an output transport abstraction.
- Adapter public trigger method must be bounded and non-blocking.
- Dry-run adapter may record/log intended commands without network calls.
- Config file name:
  led_look_director.example.json
- Runtime/live config name expected later:
  led_look_director.json
- User selected default Govee output true for later live integration, but this phase remains dry-run skeleton.
- No GOVEE_API_KEY in config.
- Config validation must reject secret-like keys such as api_key, token, secret, authorization, auth_header, bearer, and password.
- Add tests for:
  - config validation
  - secret-like config key rejection
  - missing/invalid config handling
  - LEDLookDirector manual/emergency priority
  - dry-run adapter trigger/status
  - no blocking behavior at public trigger level where testable

After implementation:
- Show diff summary.
- Show test command.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 3.

Required:
- No StateManager changes.
- No runtime command integration yet.
- No real Govee I/O from bridge modules.
- LEDLookDirector policy-only.
- GoveeSceneAdapter output-transport-only.
- Public trigger method bounded/non-blocking.
- No API key in config/docs/tests.
- Config validation rejects secret-like keys.
- Config defaults and user-selected live posture are clearly handled.
- Tests added for bridge-facing modules.
- Existing laser/SoundSwitch files untouched.
```

---

## 11. Phase 4: Manual LED Runtime Command Path, No StateManager Changes

### Objective

Add manual LED command path into bridge runtime.

### Allowed Files

```text
runtime_status.py
models.py
__main__.py
led_* files
govee_scene_adapter.py
tests/test_runtime_status.py
tests/test_led_*.py
```

### Forbidden Files

```text
state_manager.py
```

### Codex Phase Prompt

```text
Proceed with Phase 4 only.

Goal:
Add manual LED runtime command path.

Conceptual commands:
- led_scene
- led_blackout
- led_clear_blackout
- led_clear_scene_override
- set_led_look_director

Requirements:
- Keep changes minimal.
- Do not add automatic role-entry triggers.
- Do not add SmartPhrasing-based automation.
- Before the StateManager gate, manual LED command work may parse, validate, report status, and hand off to a temporary non-blocking adapter diagnostic/manual transport entrypoint only.
- Do not create long-lived manual override, blackout latch, auto-resume, or policy state outside StateManager before Phase 6.
- Long-lived manual override/blackout state belongs in StateManager only after the StateManager gate opens.
- Manual LED scene should update LEDLookDirector/adapter state/status through the allowed runtime command path only and must not bypass the coordinator once StateManager integration exists.
- Emergency blackout must beat manual override.
- Clear override and clear blackout must behave predictably.
- Add/extend tests for runtime command parsing.
- Do not touch state_manager.py in this phase.
- No blocking Govee I/O in runtime command handling.
- Adapter trigger path remains non-blocking.
- GOVEE_API_KEY still only from environment.
- No secrets in config/logs/tests.

After implementation:
- Show diff summary.
- Show tests.
- Confirm state_manager.py was not touched.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 4.

Required:
- Manual commands only.
- No automatic role-entry.
- No blocking Govee I/O.
- Runtime command validation is strict.
- No long-lived LED policy/manual override/blackout state is created outside StateManager before the gate.
- Any temporary manual transport path is clearly marked as pre-gate diagnostic/manual-only and non-blocking.
- Tests added for command parsing.
- No secrets.
- Reject if state_manager.py was touched.
```

---

## 12. Phase 5: Real GoveeSceneAdapter Transport

### Objective

Enable real Govee output from the bridge through `GoveeSceneAdapter`, using a bounded non-blocking trigger path and worker-owned I/O.

### Allowed Files

```text
__main__.py
runtime_status.py
validation_runner.py
govee_scene_adapter.py
led_config.py
led_models.py
config/led_look_director.example.json
tests/test_runtime_status.py
tests/test_validation_runner.py
tests/test_govee_scene_adapter.py
tests/test_led_config.py
```

### Forbidden Files

```text
state_manager.py
laser_director.py
laser_executor.py
midi_output.py
sound_switch_engine.py
automatic role-entry policy paths
```

### Codex Phase Prompt

```text
Proceed with Phase 5 only.

Goal:
Enable real GoveeSceneAdapter output behind config and capability gates.

Requirements:
- GoveeSceneAdapter public trigger method must be non-blocking.
- Use bounded queue.
- Worker thread owns Govee API/LAN/cloud I/O.
- Use GOVEE_API_KEY from environment only.
- No API key in config/logs/tests/docs.
- Support live Govee calls because user allowed them.
- Support scene trigger only if capability exists.
- Support fallback off/basic command only if supported.
- Use capability data from config/discovery/manual mapping.
- Add rate limiting.
- Add dedupe.
- Add degraded status.
- Add queue-full handling.
- Add clean shutdown behavior.
- Add bounded worker shutdown.
- Add malformed Govee response handling.
- Add status provider failure handling.
- Add rate-limit/circuit-breaker visibility.
- Add mocked unit tests.
- Live tests must be opt-in and skipped by default.
- Do not add automatic role-entry triggers yet.
- Do not put Govee I/O in StateManager.
- Do not touch StateManager unless explicit gate is opened later.

After implementation:
- Show diff summary.
- Show test command.
- Show manual run command for a live trigger if runtime path exists.
- Confirm allowed/forbidden file scope.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 5.

Required:
- Public trigger path bounded/non-blocking.
- Worker owns I/O.
- Queue bounded.
- Rate limit exists.
- Dedupe exists.
- Degraded status exists.
- Bounded worker shutdown exists.
- Malformed Govee responses fail soft.
- Status provider failure fails soft.
- Rate-limit/circuit-breaker state is visible.
- Secrets handled correctly.
- Live tests skipped by default.
- Mocked tests exist.
- Tests cover queue-full, degraded adapter, timeout/send error, malformed response, status provider failure, bounded shutdown, and live-test opt-in.
- No automatic role-entry.
- No StateManager I/O.
```

---

## 13. Phase 6: Hard StateManager Gate Review

### Objective

Before touching `StateManager` for any LED behavior, the Supervisor must explicitly approve the phase-specific `StateManager` integration proposal.

### Required Evidence

Codex must provide:

```text
Phase 1 capability summary
Phase 2 manual trigger result
Phase 3 skeleton tests
Phase 4 manual command tests
Phase 5 adapter tests/status
Proposed exact StateManager touch points for Phase 7 manual/status wiring
Proposed context passed to LEDLookDirector
Proof no Govee I/O will happen in _push_tick
Rollback plan
```

### Codex Phase Prompt

```text
Proceed with Phase 6 only.

Do not modify code.

Produce a StateManager integration proposal for Phase 7 manual/status wiring and the later Phase 8 automation hook.

Include:
- exact files to modify
- exact functions likely touched
- where LEDLookDirector.tick(...) would be called
- where GoveeSceneAdapter.trigger(...) would be called
- what context fields are needed
- how manual LED commands become BridgeEvent values
- where manual override and blackout state will be owned after the gate opens
- how role-entry dedupe avoids command spam
- how manual override and blackout remain priority
- how scripted mode is handled conservatively
- how tests will prove no repeated trigger spam
- how to rollback the change
- why no blocking I/O enters StateManager._push_tick

Stop after proposal.
```

### Supervisor Review Checklist

```text
Review Phase 6 StateManager gate proposal.

Approve gate only if:
- standalone Govee proof passed
- manual trigger passed
- adapter is non-blocking
- proposed StateManager edits are minimal
- no Govee I/O enters _push_tick
- tests are planned
- rollback is clear
- scripted mode policy is conservative
- role-entry only, no per-tick/per-beat spam

Return:
PHASE APPROVED - STATEMANAGER GATE OPEN
or
PHASE REJECTED - STATEMANAGER GATE CLOSED
```

### Pass Criteria

```text
Supervisor explicitly says:
PHASE APPROVED - STATEMANAGER GATE OPEN
```

Without that exact approval, Phase 7 cannot begin.

---

## 14. Phase 7: StateManager LED Manual/Status Ownership

### Objective

Open the minimal StateManager integration needed for LED manual override, blackout, clear commands, status ownership, and fail-soft adapter handoff.

Do not add automatic musical role-entry triggers in this phase.

### Codex Phase Prompt

```text
Proceed with Phase 7 only.

StateManager gate is open only if Supervisor explicitly approved Phase 6.

Goal:
Make StateManager own LED manual/emergency state and LED runtime status wiring.

Requirements:
- Modify only the exact files approved in the Phase 6 gate proposal.
- Follow the existing runtime command pattern:
  runtime_status.CommandReader parses JSONL command
  __main__.py callback enqueues a BridgeEvent with put_nowait
  StateManager._handle_event owns long-lived policy state
- Add LED event constants in models.py only as needed.
- Add optional LEDLookDirector/GoveeSceneAdapter dependencies to StateManager.
- StateManager may process manual LED commands:
  - led_scene
  - led_blackout
  - led_clear_blackout
  - led_clear_scene_override
  - set_led_look_director
- Emergency blackout beats manual override.
- Manual override beats automation, even though automation is still disabled in this phase.
- Clear scene override must not clear emergency blackout.
- Clear blackout behavior must be explicit and tested.
- StateManager may call bounded LEDLookDirector/adapter methods only.
- No Govee network/API/LAN/cloud I/O in StateManager.
- No config parsing, file I/O, discovery, DNS, sleeps, retries, blocking queue calls, or status-provider calls in _push_tick.
- Manual commands may queue one LED adapter command through the bounded adapter trigger path.
- If adapter trigger rejects or queue is full, the failure must be visible in LED status/command last_error without affecting SoundSwitch or lasers.
- StatusWriter may expose led_look_director status through a safe provider, matching the existing laser_status_provider pattern.
- ValidationRunner may add LED checks only if the required status/config data is already available without blocking.
- Automatic role-entry based on SmartPhrasing, beats, drops, buildups, or breakdowns remains forbidden.
- Add tests for:
  - command parsing and callback failure reporting
  - BridgeEvent enqueue success/failure
  - StateManager manual scene event sets manual LED override
  - StateManager LED blackout beats manual scene
  - clear scene override does not clear blackout
  - clear blackout behavior
  - disabled/not_configured LED layer is inert
  - adapter trigger rejection/queue-full is non-fatal and visible
  - status provider failure returns a degraded/default LED status
  - _push_tick does not call Govee client/network/status methods

After implementation:
- Show diff summary.
- Show tests.
- Confirm no automatic role-entry triggers were added.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 7.

Required:
- Phase 6 StateManager gate was explicitly opened.
- StateManager edits match the approved proposal.
- Runtime command flow follows existing CommandReader -> __main__ callback -> BridgeEvent -> StateManager ownership pattern.
- Long-lived manual override/blackout state is owned by StateManager-side policy objects, not by runtime_status.py or __main__.py.
- No automatic role-entry, SmartPhrasing automation, beat-triggered LED output, or drop/buildup/breakdown automation was added.
- No Govee I/O, config parsing, discovery, sleeps, retries, blocking queue calls, or status-provider calls in _push_tick.
- Manual LED adapter trigger path is bounded/non-blocking and failure-visible.
- Status provider failure fails soft.
- Tests added and pass.
- Laser/SoundSwitch behavior unchanged.
```

---

## 15. Phase 8: Automatic LED Role-Entry Triggers

### Objective

Add automatic LED role-entry triggering using existing bridge context and SmartPhrasing state.

### Codex Phase Prompt

```text
Proceed with Phase 8 only.

Phase 7 manual/status StateManager wiring must already be approved.

Goal:
Add automatic LED role-entry triggers.

Requirements:
- Use existing bridge context and SmartPhrasing state.
- Do not duplicate SmartPhrasing logic.
- Trigger only on meaningful role-entry or eligible transition.
- Do not trigger every tick.
- Do not trigger every beat.
- Banks:
  - ambient_bank
  - groove_bank
  - buildup_bank
  - pre_drop_bank
  - drop_bank
  - post_drop_bank
  - breakdown_bank
  - utility_bank
- LED bank selection must stay separate from laser bank selection.
- Manual override beats automation.
- Emergency blackout beats everything.
- Scripted mode conservative:
  no automatic LED role changes unless explicitly enabled in config.
- No blocking Govee I/O in StateManager.
- StateManager only calls bounded LEDLookDirector/adapter methods.
- Automatic role-entry must be behind an explicit config enable flag.
- Default scripted-mode policy remains conservative:
  no automatic LED role changes during scripted mode unless explicitly enabled in config.
- Add tests for:
  - no repeated trigger spam
  - drop crossing triggers one look
  - buildup role behavior
  - breakdown role behavior
  - manual override priority
  - blackout priority
  - scripted mode conservative behavior

After implementation:
- Show diff summary.
- Show tests.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 8.

Required:
- Phase 7 manual/status StateManager wiring was approved first.
- StateManager edits are minimal.
- No Govee I/O in StateManager.
- Triggering is role-entry/transition only.
- No per-tick/per-beat command spam.
- Manual override priority works.
- Blackout priority works.
- Scripted mode conservative.
- Tests added and pass.
- Laser/SoundSwitch behavior unchanged.
```

---

## 16. Phase 9: Rehearsal Hardening And Docs

### Allowed Files

```text
docs/led_look_director_design.md
docs/led_look_mapping_workflow.md
docs/govee_capability_notes.md
docs/architecture/runtime_invariants.md
docs/architecture/current_architecture.md
docs/plans/led_agent_orchestrator_workflow.md
docs/plans/led_look_director_integration_plan_revised.md
```

### Forbidden Files

```text
state_manager.py
__main__.py
runtime_status.py
models.py
led_*.py
govee_scene_adapter.py
tests/*.py
frontend/browser UI assets
scripts/govee_worker.py
```

### Codex Phase Prompt

```text
Proceed with Phase 9 only.

Goal:
Add rehearsal hardening and documentation.

Requirements:
- Add/update docs for LED Look Director usage.
- Document config fields.
- Document operator workflow.
- Document dry-run/live mode.
- Document manual commands.
- Document Govee API key environment variable.
- Document capability discovery.
- Document failure/degraded statuses.
- Add validation checklist.
- Add safe rehearsal checklist.
- Keep changes documentation-only.
- No new architecture changes.
- No new automation behavior.
- No secrets.

After implementation:
- Show docs changed.
- Show any tests run.
- Stop.
```

### Supervisor Review Checklist

```text
Review Phase 9.

Required:
- Docs accurate.
- No secrets.
- No new runtime behavior snuck in.
- Only allowed documentation files changed.
- Operator workflow clear.
- Safety/degraded behavior documented.
```

---

## 17. Phase 10: Optional UI Planning / Mapping Surface

This phase is planning only unless explicitly approved for implementation.

### Allowed Files

```text
docs/led_ui_mapping_surface_plan.md
docs/led_look_mapping_workflow.md
docs/govee_capability_notes.md
```

### Forbidden Files Unless Supervisor Opens A Separate UI Implementation Scope

```text
frontend/browser UI assets
tools/laser_pad_web.py
tools/laser_pad_assets/*
__main__.py
runtime_status.py
state_manager.py
led_*.py
govee_scene_adapter.py
tests/*.py
```

Potential UI integration:

```text
existing local mapping UI
  → LED tab
  → discovered Govee targets
  → discovered scenes
  → LED look mapping
  → bank assignment
  → test trigger
  → blackout
  → status
```

Do not implement UI automatically unless the Supervisor explicitly opens this optional scope after core phases pass.

---

## 18. Phase 11: Optional External Worker Process

This phase is only if the internal `GoveeSceneAdapter` worker proves insufficient.

Do not implement automatically unless the Supervisor identifies a need and explicitly opens this optional scope after core phases pass.

### Planning-Only Allowed Files

```text
docs/govee_external_worker_plan.md
docs/govee_capability_notes.md
```

### Forbidden Files Unless Supervisor Opens A Separate Worker Implementation Scope

```text
scripts/govee_worker.py
__main__.py
runtime_status.py
state_manager.py
led_*.py
govee_scene_adapter.py
tests/*.py
```

Potential file:

```text
scripts/govee_worker.py
```

Potential architecture:

```text
bridge process
  → local IPC
  → govee_worker process
  → Govee API
```

Use only for stronger isolation after evidence shows the internal adapter worker is insufficient.

---

## 19. Revision Loop Prompt

When Supervisor rejects a phase, send this to Codex:

```text
The Supervisor rejected the phase.

You must fix only the listed issues.

Supervisor findings:
<PASTE FINDINGS>

Rules:
- Do not proceed to the next phase.
- Do not expand scope.
- If Supervisor required a revert, revert the specified file(s) first.
- Preserve passing behavior.
- Add or update tests if runtime behavior changed.
- Report the revised diff and commands/tests to run.
- If the same phase has been rejected three times, stop and produce a blocked handoff report for the Supervisor instead of continuing revisions.
```

---

## 20. Phase Advancement Rule

The orchestrator may advance only when Supervisor returns:

```text
PHASE APPROVED
```

For Phase 6 specifically, the orchestrator may advance to StateManager LED changes only when Supervisor returns:

```text
PHASE APPROVED - STATEMANAGER GATE OPEN
```

No other wording opens the gate.

---

## 21. Global Stop Conditions

Stop the current phase and route to Supervisor if any of these occur:

```text
device exposes no useful controls
live manual trigger fails repeatedly
Supervisor cannot approve after 3 revision loops
tests fail after 3 revision loops
Codex repeatedly touches forbidden files
unclear whether real output could affect bridge timing
official Govee docs are incomplete, ambiguous, unavailable, or contradictory
```

Ask the human/operator only for physical, account, or environment blockers:

```text
GOVEE_API_KEY missing from the runtime environment
H612D/ROOM_PERIMETER device not powered, paired, named, or reachable
Govee account/API access not enabled
Govee app scene creation/selection is required because the API cannot create/select it
human visual confirmation of physical LED behavior is required
local network or hardware state cannot be fixed by agents
```

---

## 22. Final Success Definition

The integration is successful when:

```text
Govee capability capture works.
Manual real Govee trigger works.
Bridge has LEDLookDirector config/status.
Manual LED runtime commands work.
GoveeSceneAdapter output is non-blocking and fail-soft.
Automatic LED role-entry triggers work.
No command spam occurs.
Manual override works.
Emergency blackout works.
SoundSwitch behavior remains unchanged.
Laser behavior remains unchanged.
```

Creative success:

```text
The Govee room strips create crowd atmosphere and venue feel.
The lasers remain the sharp show layer.
The two systems feel coordinated without being hard-paired.
```

Technical success:

```text
The LED lane stays shallow, observable, isolated, and fail-soft.
```
