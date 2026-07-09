---
doc_status: current
truth_level: web-research-verified (multi-agent search + fetch + 3-vote adversarial verification per claim, cross-checked against a read-only repo code audit)
last_verified_commit: dcb8705
last_verified_date: 2026-07-09
validation_scope: read-only web research (deep-research harness: 5 search angles, 15+ sources fetched, adversarial refute-vote on every load-bearing claim) plus a read-only audit of this repo's existing Govee cloud/LAN wiring (govee_runtime_sender.py, govee_realtime_transport.py, led_look_director.py, config/led_look_director.example.json); zero Govee API calls made, zero commands sent to the strip, zero code changed — feasibility analysis only, not implementation-authorizing
---

# Govee DIY scene extraction feasibility (2026-07-09)

**What this is.** An overnight, read-only research pass into whether the operator's
~25 hand-built Govee DIY scenes (device H612D) can be extracted or reverse-engineered
well enough to recreate them as local renderer effects in `govee_frame_renderer.py`,
so the bridge can stop depending on Govee's cloud for those looks. No Govee API was
called, nothing was sent to the strip, and no code was written. This is analysis only —
a decision input, not a spec.

## Why this matters for the bridge (confirmed against current code)

The bridge already triggers DIY scenes today, but only as opaque numeric IDs sent to
Govee's cloud. `config/led_look_director.example.json` wires 27 looks with
`"action": "diy_scene"` and a numeric `"scene_ref"` (e.g. `"23259104"`).
`govee_runtime_sender.py` turns that into a POST to the official Govee Platform API
(`https://openapi.api.govee.com/router/api/v1/device/control`, header
`Govee-API-Key`) with a `dynamic_scene` capability payload built from the raw
`scene_ref` value — the bridge never sees or stores what that scene actually looks
like. Separately, the bridge already owns a full local LAN path:
`govee_realtime_transport.py` streams per-frame RGB to the strip over UDP (port 4003,
`{"cmd":"razer","data":{"pt": <base64>}}`), send-only, no cloud involved. That matters
for this research because it means **recreating a DIY scene locally doesn't require a
new output path** — it only requires learning each scene's colors, motion style, and
speed, then encoding that as a small render routine the existing LAN streamer already
knows how to drive.

## The four routes, verdict by verdict

### Route 1 — Govee Platform API / undocumented app endpoints: **enumerate/trigger yes, decode no**

The official Platform API (`GET /router/api/v1/device/scenes`, the
`get-light-scene` endpoint) returns only `{name, value}` per scene — no color,
motion, or segment data. The undocumented app endpoint
(`app2.govee.com/appsku/v1/light-effect-libraries?sku={SKU}`) goes further and
returns a real scene catalog, but for **DIY scenes specifically the payload fields
come back empty** — `"diyEffectCode": []`, `"diyEffectStr": ""`
([egold555/Govee-Reverse-Engineering #11](https://github.com/egold555/Govee-Reverse-Engineering/issues/11)).
`wez/govee2mqtt`, the most active community integration, reaches DIY scenes through
a *second*, account-credential-authenticated undocumented endpoint (`login_community()`
+ `get_saved_one_click_shortcuts`, exposed as `govee undoc dump-one-click` in its own
CLI — confirmed directly against that project's source) and lists them in Home
Assistant's Effects list. But every source that looked — the project's own README,
its maintainer's comments, and three independent GitHub issues — agrees this only
lets you **enumerate and trigger a scene by opaque code**, never recover its
color/motion/speed/segment definition
([govee2mqtt #3](https://github.com/wez/govee2mqtt/issues/3),
[#344](https://github.com/wez/govee2mqtt/issues/344)).

There's also a coverage risk worth flagging for the ~25-scene goal: the project
maintainer describes the underlying Govee API as "inconsistent and rather broken" —
scene lists change day to day, there's a roughly 40-scene cap some users hit, and
individual devices report scenes silently missing from the API that are visible in
the app ([govee2mqtt #13](https://github.com/wez/govee2mqtt/issues/13), corroborated
by #236, #274, #290 — this specific claim was independently re-verified twice against
the raw GitHub comment and held up both times). Even the "trigger by ID" path isn't
guaranteed to see all 25 scenes reliably.

**Verdict: LOW value for this goal.** This route gets you a working remote-control
button, not a definition you could build a local renderer effect from.

### Route 2 — HTTPS app-traffic MITM: **technically doable, but hits the same ceiling as Route 1**

Cert pinning is a real obstacle but not usually a hard blocker: mature, actively
maintained tooling exists for exactly this — Frida-based unpinning
([httptoolkit/frida-interception-and-unpinning](https://github.com/httptoolkit/frida-interception-and-unpinning)),
a no-root APK-patching alternative
([mitmproxy/android-unpinner](https://github.com/mitmproxy/android-unpinner)), and even
a no-tooling trick (run an older APK on an Android 6 emulator, which enforced
certificate trust far more loosely). A full worked walkthrough of intercepting a
pinned Android app's private API this way is documented end-to-end at
[data-dive.com](https://data-dive.com/reverse-engineer-android-api-app-secured-by-certificate-pinning).

The problem is what's waiting on the other side of that interception. A community
project already did exactly this against the Govee app —
[jimmyjammed/govee-lan-api-plus](https://github.com/jimmyjammed/govee-lan-api-plus)
uses Frida to hook the app's MQTT layer and capture the exact packet it sends when a
DIY scene is triggered. I read that project's own source, not just its README: the
captured object (`GoveeMqttDiyDevice` / `models/govee_mqtt_diy_scene.py`) stores
*only* the raw base64 command bytes — there is no color, motion, speed, or segment
field anywhere in it. It's built to capture-and-replay verbatim, not to decode.

**Verdict: LOW added value.** MITM is achievable, but it recovers the same opaque
blob Route 1's undocumented endpoint already hands out — it doesn't get you inside
the blob.

### Route 3 — LAN observation while a DIY scene plays: **answers the key question, but doesn't decode DIY specifically**

**Key question, answered:** DIY scenes render device-side from a payload pushed to
the strip once, not a continuous cloud stream. The mechanism is documented and
cross-corroborated by two independent community projects
([egold555 #11](https://github.com/egold555/Govee-Reverse-Engineering/issues/11),
[homebridge-govee #694](https://github.com/homebridge-plugins/homebridge-govee/issues/694)):
a scene is pushed over the LAN control port (UDP 4003, multicast discovery on
239.255.255.250:4001/4002 — this matches the ports `govee_lan_discovery.py` already
uses in this repo) as a `ptReal` command,
`{"msg":{"cmd":"ptReal","data":{"command":["<base64>"]}}}`, and the device renders it
locally from there. For *preset* scenes the byte layout inside that base64 blob is
fully decoded (`0x33 0x05 0x04` + byte-swapped scene code + checksum). For **DIY**
scenes specifically, though, nobody has published a decode of what's inside the
blob — the community's own DIY tooling (govee-lan-api-plus, above) still needs an
app-side capture to *get* the DIY payload at all; passively watching the LAN without
first grabbing that payload from the app gets you nothing for DIY scenes.

**Verdict: Confirms the mechanism, doesn't unlock DIY definitions on its own.**
Route 3 alone only pays off once paired with Route 2 or Route 4 to actually acquire
a DIY payload — and even then, what you get is a replay blob, not parameters.

### Route 4 — BLE fallback: **the one route that has actually decoded a DIY scene into real parameters**

This is the standout finding. On the Govee H6127 (an older, non-addressable RGB
strip), the DIY-scene BLE protocol has been fully decoded — independently, by
multiple community RE repos that all agree with each other
([BeauJBurroughs/Govee-H6127-Reverse-Engineering](https://github.com/BeauJBurroughs/Govee-H6127-Reverse-Engineering),
mirrored in [egold555's H6127.md](https://github.com/egold555/Govee-Reverse-Engineering/blob/master/Products/H6127.md),
forked by philhzss, mnpenner, and chevy1500z). A DIY scene write is a sequence of
plain BLE characteristic writes: a start packet (`0xa1 0x02 ...`), one to three data
packets that encode the **motion style** (Fade / Jumping / Flicker / Marquee / Music
/ Combo), a **speed** byte (`0x00`–`0x64`), and **up to 8 RGB colors**, an end
packet, and a `0x33 0x05 0x0a ...` activate command. That's colors, motion type, and
speed — the exact three things the recreation goal needs — recovered as a decoded,
portable structure, not an opaque replay blob. This was the single most important
claim in the whole research pass, so I checked it three separate times with
independent adversarial reviewers before trusting it; all three tried to refute it
and failed (two came back "confirmed, high confidence"; one "confirmed, medium
confidence" purely because of the device-generalization gap below — not because the
H6127 finding itself is shaky). Two rival claims that would have undercut this
("BLE DIY encoding is still unsolved," "BLE only exposes 8 hardcoded preset scenes,
no custom DIY") were themselves checked and **refuted** — both turned out to be
about different, older devices and don't hold up against the H6127 evidence.

The real gap: **none of this has been verified against the H612D specifically.**
H612D doesn't appear in that repo's device list at all, and it's architecturally
different from the H6127 — it's a newer RGBIC *addressable* strip (per-segment
color), where the H6127 is a simple non-addressable strip and its documented format
only carries "up to 8 colors" with no visible per-segment field. Whether H612D speaks
BLE at all in a compatible way, and whether its DIY format extends this same framing
or uses something else for per-segment patterns, is genuinely unknown — this is
exactly the gap a single probe would close, not something more web research will
resolve.

**Verdict: HIGH value if it transfers to H612D — unverified until probed.** This is
the only route in the entire body of evidence with a track record of decoding actual
scene parameters instead of just capturing an opaque code to replay.

## Recommended method: one BLE capture, on the operator's own hardware

Route 4 is the recommendation, for one plain reason: it's the only route that has
ever produced *parameters* instead of a *replay blob*. A replay blob only lets the
bridge re-trigger the exact original render through the exact original protocol —
it's not something a local renderer effect can be built from. Decoded
{motion style, speed, colors} is.

It's also the cheapest and lowest-risk route to actually test. It doesn't touch the
Govee API key, doesn't fight certificate pinning, and doesn't need a rooted phone —
it captures the Govee app doing exactly what the operator already does by hand.

**Concrete steps (for a future, operator-run probe — not run tonight):**

1. On an Android phone signed into the Govee account with the app installed (doesn't
   need to be the primary phone — a spare Android device works, since this only
   needs Developer Options, not root): enable **Bluetooth HCI snoop log** under
   Developer Options.
2. Manually play **one** known DIY scene on the H612D through the Govee app, as
   normal — this is the only step that talks to the strip, and it's the operator
   doing exactly what they'd do anyway.
3. Pull the capture: `adb bugreport`, unzip, open
   `FS/data/log/bt/btsnoop_hci.log` in Wireshark (this exact workflow is documented
   end-to-end at
   [Adafruit's BLE bulb RE writeup](https://learn.adafruit.com/reverse-engineering-a-bluetooth-low-energy-light-bulb/sniff-protocol),
   which is the same byte-diff methodology the H6127 decode used).
4. Filter to the write packets to the strip's BLE characteristic and check them
   against the documented `0xa1 0x02 ... 0x33 0x05 0x0a` framing.
5. **If it matches:** repeat once per remaining DIY scene (a few minutes each) — the
   result is a lookup table of {motion style, speed, colors} per scene, ready to hand
   to whoever builds the local renderer effects. No further API/MITM work needed.
6. **If it doesn't match:** the capture pipeline still isn't wasted. The same
   byte-comparison technique (diff packets across several scene triggers, find the
   fixed prefix vs. the varying payload) is how every one of these community formats
   was originally decoded from nothing — it just means the H612D needs its own
   decode-from-scratch pass rather than reusing the H6127 lookup, which is a bigger
   but still bounded effort.

**Effort estimate:**
- The single confirming probe (steps 1–4): under an hour, assuming a spare Android
  device is available. If the operator is iPhone-only, the alternative is a cheap
  dedicated BLE sniffer (~$10–30 Nordic nRF51822 dongle + Wireshark — same
  methodology, no Android device needed).
- Full 25-scene capture, if the H6127 format transfers: a few hours of manual
  per-scene captures, no new tooling.
- Full decode-from-scratch, if H612D uses a different DIY framing (likely, given the
  RGBIC per-segment difference): open-ended reverse-engineering effort, comparable to
  what the existing hobbyist repos each took — days, not hours, and would be its own
  follow-up research pass rather than a quick add-on to this one.

**What the one probe confirms, specifically:**
- Whether H612D speaks BLE control at all in a way compatible with the documented
  Govee family (some newer Govee lines are cloud-only with no local BLE control —
  this is the single biggest go/no-go unknown, and nothing short of touching the
  actual hardware answers it).
- Whether the captured DIY-trigger packets match the known `0xa102`/`0x33050a`
  framing (turns the rest of the 25-scene job into a cheap lookup) or don't (turns it
  into its own decode project).
- Whether H612D's DIY scenes are actually simple whole-strip patterns (style + speed
  + a handful of colors, like the H6127) rather than true per-segment programs. If
  so, that's genuinely good news for the recreation goal — the bridge's existing LAN
  renderer can reproduce a whole-strip Fade/Jump/Marquee pattern from three
  parameters far more easily than it could reproduce arbitrary per-pixel data.

## Fallback if Route 4 doesn't pan out

If the BLE capture shows H612D doesn't support local BLE control, or its DIY format
resists decoding, the practical fallback is Route 2 + Route 3 combined exactly as
`govee-lan-api-plus` already does it: Frida-capture each DIY scene's MQTT payload
once from the app, then replay it verbatim over the LAN `ptReal` path. That doesn't
give portable {colors, motion, speed} parameters to build a renderer *algorithm*
from, but it does let the bridge reproduce each of the 25 scenes exactly, locally,
without depending on Govee's cloud at trigger time — a smaller win than a real decode,
but still real, and it reuses tooling that's already proven against the Govee app
specifically (not just Govee-adjacent devices, unlike the BLE evidence).

## What this research did not establish

- Nothing here confirms H612D-specific behavior on any route — every finding above
  is either official-but-generic (Routes 1–3's LAN/cloud transport) or verified on a
  different, older Govee model (Route 4's BLE decode). The single probe above is the
  only thing that closes that gap.
- Coverage of all ~25 scenes is not guaranteed on any route — Route 1's own
  maintainers report the cloud scene list is flaky, and Route 4 needs one capture per
  scene regardless of format, so partial results (some scenes decode/capture cleanly,
  others don't) are a realistic outcome, not just a worst case.
