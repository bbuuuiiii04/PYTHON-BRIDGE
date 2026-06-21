# ⚠️ STALE STAGE-1 SCRATCH — DO NOT TRUST THE MODEL BELOW

This is Stage-1 working scratch. Its **AUTOLOOP MODEL IS WRONG/OUTDATED**: it describes the
`SSAutoLoop{N}.ssfile` 12-slot table as "attribute-cue / 12 attribute UUIDs." The **corrected**
finding is that those 12 slots are **POSITION presets** (Disco Ball, Stage L/R, Dance Floor, DJ
Booth, …). Paths here say `/tmp/ss_re`; tools are now in `tools/ssfmt/re/` + `tools/ssfmt/captures/`.
**Authoritative now:** `docs/research/soundswitch/soundswitch_stage2_research_findings.md` and the Codex spec
`soundswitch_decode_export_codex_spec.md`. Kept only as historical scratch — do not rely on it.

# SoundSwitch → Bridge DMX — Working Notes (Stage-1 scratch; may hold GUIDs/IPs)
Updated 2026-06-19. Tags: [C]=confirmed (evidence)  [A]=assumed  [U]=unknown.
Tools: /tmp/ss_re/ssparse.py (container tokenizer), /tmp/ss_re/uuidxref.py (ref cross-ref),
/tmp/ss_re/artnet_sniff.py (passive ArtDmx capture → artnet_capture.jsonl).
Snapshot of small content files frozen at /tmp/ss_re/snap/. Baseline hashes: /tmp/ss_re/baseline/.

## Environment
- SS 2.10.3 (ArKaos), Qt6, links libftd2xx (FTDI/Enttec DMX), librtmidi, libtag. [C, prior RE + otool]
- SS binds UDP 6454 (Art-Net) [C lsof]. OS2L server advertised via Bonjour `_os2l._tcp` at a
  DYNAMIC localhost port per launch (seen 127.0.0.1:57391; stale 58716 = dead instance). [C]
- Bridge: exactly one `python -m rb_ss_bridge_v2` runtime; stdout tee'd to /tmp/bridge.log. [C]
- Enttec DMX Pro NOT connected right now. [C operator]  VLN at /Users/bbui/virtuallasernode = oracle only.

## Live observability channels (bridge ↔ SS)
1. /tmp/bridge.log — bridge DECISIONS: `[SM] pos deck=.. mode=autoloop|scripted`, `[BEAT] .. laser=<scene> led=<look> phrase=<>`,
   `[OS2L] deck-load deck=.. ssid=.. bpm=.. loop=8 play=on`, `[OS2L] dns-sd found ..`. [C]
2. ~/Library/Application Support/Onesixone/Soundswitch/Logs/AppLog.txt (rotates 10MB→.1/.2/.3) — SS STATE:
   - `AutoLoopTrackPriData.h:242  Deck D running autoloop bank -1, index N`  (fires on change) [C]
   - `SoundSwitchDoc.cpp:1366  Deck D running scripted track {UUID}` [C]
   - `SoundSwitchDoc.cpp:1340  track file found: ...{UUID}.ssfile` [C]
3. Art-Net UDP 6454 ArtDmx = faithful Enttec Universe-1 proxy (VLN equivalence). Captured passively. [C port]

## File inventory  ~/Music/SoundSwitch/default.ssproj/
- .ssproj                     JSON: project id + version {major2 minor10 hotfix3} = 2.10.3 [C]
- SoundSwitchVenues.bin 243K  venue "RAVE" + fixture profile + attribute defs + (Static Looks?) [A]
  (+ .backup identical)
- SoundSwitchAutoLoops.bin 1.1K   autoloop catalog: categories + look names [C]
- SoundSwitchAutoLoopsEx.bin 1.5K extended autoloop catalog [C]
- SSAutoLoop{1..56}.ssfile (~50)  autoloop attribute-cue timelines [C]
- {UUID}.ssfile (37)              scripted-track show timelines [C]
- SoundSwitchTrackMap.bin 786K    track filepath (UTF-16LE) ↔ ssfile UUID map [C ss_library_scanner.py]
- {E36664D0..}.ssa                audio-analysis sidecar? [U]

## Container format  (magic AA AA 09 55)
- 4-byte magic, int32 version(=3), then stream of int32(LE) + length-prefixed UTF-16LE strings. [C]
- String = [int32 L][2L bytes UTF-16LE]; L counts code units INCLUDING trailing NUL (visible text L-1). [C]
- Object references are 16-byte binary QUuid, never text. [C cross-ref + prior RE]

## AUTOLOOP MODEL  (reference / attribute-cue) [C]
- SSAutoLoopN.ssfile: own UUID → 12-entry slot table `[16B attr UUID][int32 slot 0..11]` → 8-bar timeline
  (evenly-spaced beat-grid positions; 0x80808080 = default/center 128 frames).
- The 12 attribute UUIDs are SHARED across ALL ssfiles and DEFINED in SoundSwitchVenues.bin. [C uuidxref]
- ⇒ a "look" = attribute-cue timeline over fixture attributes; DMX is produced by applying the fixture
  profile's attribute→channel mapping to attribute values. Renderer = attr→channel map + timeline replay. [A high]

## VENUES.bin (fixture + attributes) [partial]
- Venue "RAVE"; fixture profile "RGB Fullcolor Beam Effect Light" (Generic), ~36-ch laser/beam. [A]
- Attributes (strings): Static Pattern, Pattern, Pattern Size, H/V Adjustment, Color, Color Speed,
  Pattern Line, Strobe, Rotation X/Y/Z, H/V Movement, Zoom, Gradient, X/Y Wave, Main. [C]
- "Fixture 4" present → multiple fixture instances (1..4?). Patch (universe/addr/chan-count) NOT yet decoded. [U]

## CATALOGS
- AutoLoops.bin categories: BREAKDOWN / GROOVE // MID ENERGY / BUILDUP // RISING / DROP // HIGH ENERGY
  (phrase/energy) + looks: RED//AG1, CYAN//AG1, PURPLE//AG1, GREEN//AG1, BLUE//AG1, BLACKOUT, LAGGY 1/4 W,
  LAGGY 1/8 W, DEFAULT(2), stack out in, curve out in, pulsating, seizure, ruby, sperm race. [C]
- AutoLoopsEx.bin: same 4 categories + NEON, NEON STUTTER, BLUE FANNING(2), CONVERGING, GREEN IN/OUT,
  RED/GREEN/CYAN STATIC, MEGA DROP, GREEN//AG, RAINBOW//AG, WHITE//AG1, many "New Autoloop".
  Incrementing single-char keys between entries [U encoding].
- AppLog "index N" ↔ SSAutoLoop{N}.ssfile: every observed index (37,2,52,6,46,48,51,17) has a matching file [A];
  exact index→file/catalog mapping TBD via Art-Net correlation. [U]

## BRIDGE OS2L (live)
- sends deck-load {deck,active,file,ssid,bpm,loop=8,play}; Bonjour-discovers SS OS2L. ssid=no ⇒ autoloop mode. [C]
- Full OS2L vocabulary + StateManager/laser seams: bridge-runtime subagent in progress.

## OPEN EXPERIMENTS (next)
- E1  Art-Net correlation (FEASIBILITY GATE): artnet_capture.jsonl ↔ AppLog index N ↔ decoded SSAutoLoopN.
- E2  Venues patch decode: fixture→universe/address/chan-count; attribute→channel(s) mapping + value encoding.
- E3  ssfile timeline decode: per-step attribute values + positions (0x80=128 center).
- E4  Controlled diff (Brandon TEST_ objects): Static Look + dimmer 127→200 to pin value encoding & layer/replace.
- E5  Scripted {UUID}.ssfile timeline vs elapsed_ms; seek/pause behavior.

## OS2L PROTOCOL — VERIFIED [C osl_output.py]
- Bridge = VirtualDJ emulator (handshake name="VirtualDJ", :33). Sends ONLY transport+identity:
  beat{deck,bpm,pos,change} (:252) + subscribed get_text '%SOUNDSWITCH_ID'/get_filepath/get_firstbeat/
  get_bpm/song_title/loop/get_loop=AUTOLOOP_BEATS/get_time elapsed|total/get_beatpos/play (:271-340).
- NO look/index/scene-selection message exists. Comment :282-285 (Wireshark-confirmed): active deck has NO
  SOUNDSWITCH_ID => "SS derives show from filepath". => SS AUTONOMOUSLY selects+rotates the autoloop. [C]
- Scripted track (ssid set): SS plays authored {UUID}.ssfile deterministically, advanced by bridge elapsed/beat. [A high]
- Autoloop track (ssid empty): SS self-selects SSAutoLoopN (AppLog index N). Bridge sends loop on + get_loop=AUTOLOOP_BEATS.
- OS2L conn: fallback 127.0.0.1:58716 (config.py:5-6) + Bonjour _os2l._tcp override (:191-235); non-blocking Queue(500)+os2l-sender thread.

## ARCH FORK (for report)
- Who selects the look for AUTOLOOP tracks in the bridge-native target?
  (A RECOMMENDED) bridge owns selection via EXISTING phrase/role brain ([BEAT] phrase/laser/led roles
   groove/drop/buildup/breakdown <-> SS catalog categories BREAKDOWN/GROOVE/BUILDUP/DROP), then renders chosen look.
  (B) reproduce SS autonomous rotation (random/sequential "shop cycle"). Harder, less musical.
  Scripted tracks: reproduce authored timeline either way (deterministic).

## BRIDGE SEAMS (subagent, OS2L spot-verified)
- E _dispatch_led_automation state_manager.py:1848 — parallel-adapter pattern (BEST); fires on role-key change; look+role+params.
- C _build_laser_context :3877 — richest per-tick context (deck/elapsed/bpm/beatpos/abs_beat/phrase/smart-drop).
- A mode-transition :3083 ; B beat fan-out :3560 ; D autoloop rearm autoloop_controller.py:707.
- CONSTRAINT: 200Hz loop must stay I/O-free => DMX sender on its OWN thread (mirror OS2LConnection Queue+sender).

## ART-NET ORACLE STATUS
- Sniffer bound 6454 OK (REUSEPORT coexists w/ SS). frames=0 => SS NOT emitting ArtDmx (no Art-Net output node;
  renders to absent Enttec). NEED: operator enable SS Art-Net output -> live validation oracle. Capture left running.

## MIDI MAP = the selection mechanism [C laser_director.json + live correlation] (operator-confirmed)
- Bridge fires MIDI on "IAC Driver Bus 1". OS2L carries NO selection; MIDI does. SS MIDI-map structure (pad banks):
  ch1 n0-31=BREAKDOWN, n32-63=GROOVE, n64-95=BUILDUP, n96-127=DROP ; ch2 n0-31=STATIC LOOKS. [C]
- Active personality "house" (bpm124-138) scene->note: groove_1=32, breakdown_1=1, buildup_1=64,
  drop_1..16=96..111 (1:96 2:97 5:98 3:99 4:100 6:101 7:102 8:103 9:104 10:105 11:106 12:107 13:108 14:109 15:110 16:111),
  post_drop_1=41 ; ch2 utility safe_static=0 transition=1 emergency=2 ; blackout ch1 note0 (note_on/off). [C]
- LIVE note->SS index (correlator, high-conf): n1->idx2, n32->idx4, n98->idx5, n101->idx15, n102->idx16 (n100->idx13 single). [C]
- CHAIN PROVEN LIVE (1-13ms): bridge event -> MIDI note -> SS autoloop index N -> SSAutoLoop{N}.ssfile -> attr-cue timeline -> DMX.
- SCOPING WIN: renderer needs only ~20-25 looks the "house" personality references, NOT all 87 ssfiles / not SS's autoloop engine.

## CORE QUESTIONS — ANSWERED
1 export automatable? YES (files decodable + scene->look derivable from config+live).  2 storage: Venues.bin(fixture+attrs+static looks+MIDI map), SSAutoLoopN.ssfile(autoloop timelines), {UUID}.ssfile(scripted), catalogs(names), laser_director.json(bridge MIDI).
3 direct vs recipe? ATTRIBUTE-CUE RECIPE (refs fixture attrs by UUID in Venues; DMX via fixture-profile attr->channel map).  4 renderer: attr->channel mapper + timeline replay; selection already in bridge.  5 seam: BehaviorPlayer at Seam E/C, DMX on own sender thread.  6 first: extract ~25 used looks + fixture profile + Enttec out.  7 unknown: exact attr->channel & timeline value encoding (pin via controlled-diff E2-E4 + Art-Net).
