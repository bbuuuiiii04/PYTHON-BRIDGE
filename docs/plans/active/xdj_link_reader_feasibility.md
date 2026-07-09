---
doc_status: current
truth_level: research
last_verified_commit: 9cac555
last_verified_date: 2026-07-09
validation_scope: >
  Feasibility + architecture study for an XDJ/CDJ standalone-playback reader mode over
  Pioneer Pro DJ Link. PAPER ONLY — no code, no network capture, no hardware contact.
  Repo-side claims verified against current code; protocol/device claims are WEB RESEARCH
  (Deep Symmetry dysentery/beat-link/crate-digger documentation, cross-checked where
  possible) and are labelled per-claim: confirmed-by-source / single-source / inferred /
  unknown. Nothing here is validated against the operator's actual hardware.
work_status: feasibility delivered 2026-07-09 — BLOCKED ON OPERATOR PINS (§1) before any further step; no implementation authorized
relates_to: usb_bridge_launcher_design.md, track_identity_move_invariance_design.md
---

# XDJ standalone playback — Pro DJ Link reader feasibility (AWR-167)

**Operator directive (verbatim, 2026-07-09): "USB needs to have XDJ support, meaning if I
connect my laptop to an XDJ but plug in the USB with my tracks exported from rekordbox
onto the XDJ, bridge should recognize it. This may be an ambitious ask but it is important
to know."**

**Plain answer up front:** this is a genuinely new reader mode — when the XDJ plays the
stick, laptop rekordbox is not the player, so today's memory reads see nothing. The known
public path is the Pro DJ Link network protocol (the laptop joins the players' wired
network and listens). It is well-trodden ground for lighting control — Deep Symmetry's
beat-link-trigger runs real shows from exactly these packets — **but whether it works for
YOU depends almost entirely on which XDJ you own.** Standalone all-in-ones in the XDJ-RX
family don't speak this protocol at all; the XDJ-XZ and the XDJ-1000/CDJ families do. The
honest rating: **moderate ambition on compatible hardware, impossible on RX-family
hardware in standalone mode** — details and phasing below.

## 1. The gating question — operator pins (FLAG, never assume)

Nothing below should be trusted for planning until these three facts land:

1. **Exact XDJ model number.** This is make-or-break (§2 matrix). "XDJ" spans devices
   that fully speak Pro DJ Link (XZ, 1000-family) and devices that cannot (RX/RX2/RX3).
2. **Standalone vs rekordbox-LINK usage.** This design targets STANDALONE (XDJ plays the
   stick's exports itself). If the actual usage is laptop rekordbox feeding the XDJ over
   Link Export, that is a different situation — possibly today's memory reader already
   covers it (laptop rekordbox is then the player) — `unknown`, needs one live look.
3. **Wired ethernet availability.** Full Pro DJ Link is wired-only
   (`confirmed-by-source`); the laptop needs an ethernet path into the player's LINK
   port or a shared switch. No compatible model was found sharing real Link over Wi-Fi.

## 2. Device matrix (web-verified 2026-07-09; per-claim labels)

| Device | Beat packets (50001, per-beat) | Status packets (50002, ~200 ms) | Absolute position (30 ms) | Standalone-USB Pro DJ Link | Confidence |
|---|---|---|---|---|---|
| CDJ-2000/NXS/NXS2 | yes | yes | no | yes | confirmed-by-source |
| CDJ-3000 | yes | yes | **yes** (`0x0b`, 30 ms, even paused) | yes | confirmed-by-source |
| XDJ-1000 | yes | yes | no | yes | single-source (beat-link README) |
| XDJ-1000MK2 / XDJ-700 | presumed | presumed | no | **presumed** | **inferred only — no Deep Symmetry confirmation found; close with a packet capture before relying on it** |
| XDJ-XZ | yes | yes (query-only media slots) | no | yes, with quirks (multi device-number on one NIC; fixed in beat-link 0.6.0) | confirmed-by-source |
| **XDJ-RX / RX2 / RX3** | **no** | **no** | no | **NO — Link Export to laptop rekordbox only; cannot exchange Link data with CDJs/DJMs; RX/RX2 reported to crash beat-link-trigger** | confirmed-by-source (beat-link README + official AlphaTheta support article for RX3) |
| Opus Quad | no (by default) | yes (reduced; own encrypted DB scheme) | no (undocumented trick exists, breaks metadata — third-party single-source) | no — reduced protocol; beat-link-trigger needs a pre-built per-stick offline metadata archive; position only ±200 ms | confirmed-by-source |

**Timing grades vs today.** Today the bridge reads absolute deck position at 200 Hz from
rekordbox memory. Over the link (non-CDJ-3000): per-beat anchor packets + ~200 ms status
packets; position between beats is INTERPOLATED (beat-link's TimeFinder model), and the
documentation is explicit that interpolation "would break down if the DJ was doing
anything creative with scratching, reverse play, or loops" (`confirmed-by-source`).
Sub-beat-accurate position under scratching/reverse/tight loops exists only on CDJ-3000.

**What the lighting engine minimally needs, mapped:** track identity (§3), beatgrid
(fetchable, §3), beat clock + BPM (beat/status packets ✓), play/pause state (status byte ✓),
master deck (status flags + handoff epoch counter ✓). All present on compatible hardware —
the loss is intra-beat position fidelity and the mixer-authority signals (§5).

## 3. Identity mapping — rides AWR-165 (this is the EASY half for this rig)

The wire reports a track as **(player, slot, track type, rekordbox id)** where the id is a
row in the STICK's `export.pdb` (`confirmed-by-source`). Whether that id equals the
desktop collection's id is `unknown` (no source answers it) — and Deep Symmetry built
`SignatureFinder` (SHA-1 of title+artist+duration+beatgrid+waveform) precisely because
they do NOT treat rekordbox ids as stable cross-media identity (`confirmed-by-source`).
That independently validates the AWR-165 direction: identity must be content-shaped, not
id- or path-shaped.

**Design: a precomputed library link-index, resolved to the AWR-165 content fingerprint.**
The stick's tracks ARE exports of the operator's own library, so the bridge can know every
possible answer in advance:
- At index build time (offline, rides the AWR-165 migration tool): for each library track,
  store `{title, artist, duration_s, beatgrid_fp}` → `track_fp` (the AWR-165 content
  fingerprint of the LOCAL file). `beatgrid_fp` already exists in the codebase
  (`spectral_cache.py:324-327`).
- At link track-load: query the player's dbserver for title/artist/duration + beatgrid
  (request `2204`/response `4602`, `confirmed-by-source`; NFS fetch of the ANLZ file is
  the fallback path that survives the dbserver's 4-player connection ceiling), compute
  `beatgrid_fp` from the fetched grid, and match against the index. Title+artist+duration
  alone is collision-prone in an EDM library (remixes/edits); the beatgrid component is
  the discriminator, mirroring Deep Symmetry's signature design.
- On match → `track_fp` → **the entire existing lighting brain runs on the LOCAL library
  twin**: spectral v4 cache hit by fingerprint, LED v2 identity + corrections, F2 plans.
  The link supplies only identity + clock + transport. On no-match → fail toward today's
  degrade (provisional/NEUTRAL identity, F2 no-op) — never guess.
- `assumed` (verify at implementation): the wire beatgrid (dbserver `4602` / ANLZ `PQTZ`)
  and our ANLZ-parsed `beatgrid_times_ms` reduce to the same beat-time values for the
  same export. Also `unknown`: whether desktop-export sticks ever lack `PQTZ` (reliably
  present in practice per beat-link-trigger's dependence on it — `inferred`).
- Experimental variant (rank LAST): the players expose a real NFSv2 server and
  `FileFetcher` can read arbitrary paths including audio files (`confirmed-by-source`
  that the API is generic; throughput `unknown`) — so direct head/tail fingerprinting of
  the stick's audio over NFS is *conceivable*. Do not design around it; nobody has
  demonstrated bulk audio over that embedded NFS stack.

## 4. Feeding the StateManager (verified against current code)

A `LinkReader` is a sibling of `RBStateReader`: its own thread(s), publishing
`BridgeEvent`s via `queue.put_nowait` (`rb_state_reader.py:714` pattern) — all dbserver
TCP, NFS fetches, and UDP listening live inside the reader threads, so **the 200 Hz push
loop gains zero I/O by construction** (the invariant is about the StateManager loop;
readers were always threads).

Event mapping (vocabulary verified at `models.py:237-255`):
- Track load: complete the identity match FIRST (async, in-reader), then emit in today's
  order — `ANLZ_PATH` (the LOCAL library twin's ANLZ path, resolved via the rekordbox DB
  exactly as today) **before** `TRACK_LOADED` (title, load_gen), then a
  `FILEPATH_RESOLVED` payload carrying the LOCAL filepath, local `content_id`, BPM, and
  the beatgrid — preserving the reader invariant and reusing the whole downstream worker
  path untouched.
- Clock/transport: `BPM_UPDATE` (status/beat packets), `TC_UPDATE` (elapsed_ms from
  beat-anchored interpolation), `PLAY`/`PAUSE` (status state byte), `MASTER_CHANGED`
  (master flag + handoff bytes). Deck numbering maps from link player numbers.
- Mode exclusivity: link mode and memory-read mode are mutually exclusive reader
  configurations (explicit launch flag, never auto-detection) — beat-link's own README
  states a link listener **conflicts with rekordbox running on the same laptop** (they
  compete for the UDP ports, `confirmed-by-source`). Runbook fact: in XDJ mode, laptop
  rekordbox stays closed.
- Self-announcement: beat packets are receivable passively, but status packets (track id,
  master, play state — everything that matters) require announcing as a virtual device
  (keep-alives on port 50000, device number 5-15 to avoid colliding with real players)
  (`confirmed-by-source`). The reader is therefore a *polite participant*, not a pure
  sniffer — a new network-facing surface for the bridge.

## 5. What honestly degrades in XDJ mode

- **Intra-beat position** — interpolated between beats (non-CDJ-3000); scratching,
  reverse, and tight loops produce wrong interpolated positions. Beat-anchored lighting
  (v2 zones, F2 drop plans, beat-quantized looks) is the strength; position-precise
  features (SS beatpos streaming cadence, autoloop phase alignment fineness) run at
  beat-grade, not 200 Hz-grade.
- **Mixer authority is gone.** Today's active-deck resolution reads laptop rekordbox's
  mixer memory (upfaders, LOW EQ). A standalone XDJ's internal mixer is not readable this
  way; the link gives master-deck + play states instead. Active-deck authority in link
  mode = link master + play state, a coarser signal. Whether an XDJ-XZ reports per-channel
  on-air/fader data over link: `unknown` — packet-capture question. The F3 blend design
  (per-deck upfader+EQ following) has NO signal source in this mode — F3 stays
  memory-read-mode-only unless a capture proves otherwise.
- **Latency:** no healthy-path figure is documented for beat packet → action
  (`unknown`); the only hard number found is the degraded Opus Quad ±200 ms. Real-world
  beat-link-trigger shows run on this, so beat-grade latency is proven acceptable for
  lighting in practice (`confirmed-by-source` that BLT is used for exactly this).

## 6. Phasing + honest ambition rating

- **Phase 0 — pins + capture (cheap, days, no code):** get the §1 operator pins. If the
  model is RX-family → **STOP: this approach is impossible in standalone mode on that
  hardware**; the options become (a) use it in Link-Export mode with laptop rekordbox
  (possibly already covered by today's reader — verify live), or (b) compatible hardware
  someday. If XZ/1000-family/CDJ → wireshark capture of a real standalone session to
  confirm the matrix row (mandatory for the inferred-only 1000MK2/700).
- **Phase 1 — passive beat spike (small):** bind port 50001, log beat/BPM against a
  playing deck. Proves network path + cadence assumptions for ~a day of work.
- **Phase 2 — identity + status (the real build):** virtual-device announcement, status
  parsing, dbserver metadata + beatgrid fetch, the §3 library link-index, StateManager
  event integration. This is the core deliverable — lighting identity + beat clock + play
  state end-to-end. Python protocol implementations exist as leads (beat-link is Java;
  a `python-prodj-link` project exists — **unevaluated here**, treat as a lead, not a
  dependency).
- **Phase 3 — parity + validation (the long pole):** TimeFinder-grade interpolation,
  master handoff edge cases, XZ quirks, live validation against the actual device, and a
  degrade matrix (which lighting features run at beat-grade). Hardware validation is the
  long pole — none of this can be called working from software alone.

**Ambition rating, honest:** on XZ/1000-family/CDJ hardware this is **moderate** — a
known, publicly documented protocol with a decade of show-control precedent, but a whole
new reader subsystem plus a new network surface plus hardware validation the repo cannot
self-serve. On RX-family hardware in standalone mode it is **not possible** via any known
public path. On Opus Quad it is **high-effort + permanently degraded**. The identity half
(the operator's actual worry) is the *cheap* part for this rig — the stick is an export of
his own library and AWR-165's fingerprint index answers it; the expensive parts are the
new protocol reader and the timing downgrade.

## 7. Unknowns ledger (close before/at implementation)

1. Operator pins (§1) — blocking everything.
2. XDJ-1000MK2/700 standalone link behavior — packet capture (`inferred` only today).
3. Export-vs-collection rekordbox id stability — `unknown`; design already avoids
   depending on it.
4. Wire beatgrid ≡ local ANLZ beatgrid values — `assumed`, verify with one fetch.
5. Per-channel mixer/on-air data from an XDJ-XZ over link — `unknown`, capture question.
6. `PQT2` tag semantics (possible second grid tag in .EXT) — open upstream issue,
   `unknown`; irrelevant unless PQTZ proves unreliable.
7. Python protocol library viability (`python-prodj-link`) vs writing a minimal reader —
   unevaluated.

## Sources

Deep Symmetry dysentery protocol analysis (djl-analysis.deepsymmetry.org: packets, beats,
vcdj, track_metadata, sync, media; rekordbox-export-analysis: exports, anlz,
crate_digger), beat-link README/CHANGELOG/issue #39, TimeFinder/VirtualCdj/SignatureFinder
javadocs, crate-digger README + Analysis.tex + FileFetcher javadoc + issue #5,
beat-link-trigger guide (incl. the Opus Quad chapter), official AlphaTheta support article
on XDJ-RX3 Pro DJ Link, prodjlink.com connection diagrams, kyleawayan/opus-quad analysis
(third-party). Full URL list preserved in the research transcripts of 2026-07-09.
