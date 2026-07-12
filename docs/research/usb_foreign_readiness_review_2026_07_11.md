---
doc_status: current
truth_level: review
last_verified_commit: 6ba7af8
last_verified_date: 2026-07-11
validation_scope: >
  Independent adversarial (ultracode) readiness review of the MINK USB stick
  rebuilt on 2026-07-11 (HEAD 6ba7af8): the frozen "RBSS Bridge.app" bundle +
  DMG, the RBSS_payload (spectral cache, home configs, Govee key, SoundSwitch
  pack), and the refreshed lighting sidecar. Question: is this stick TRULY ready
  to light correctly on a FOREIGN Mac that has none of the operator's rekordbox
  collection? Read-only: the runtime bridge was never started (only the LED/laser
  pad tools + menubar were running). Method = a multi-agent fan-out of independent
  adversarial attackers (7 questions, each verified against a skeptic) plus direct
  operator-side verification (frozen-bytecode extraction, sidecar fingerprint
  parity against the shipped ANLZ, and the no-DB resolve trace). Software-staged
  and code-verified only; NO real foreign-Mac run has happened — that remains the
  gating hardware step.
---

# USB Foreign-Laptop Readiness Review — 2026-07-11

**Status:** `software-validated / hardware-unvalidated`. Everything below is code +
staged-artifact evidence. A real foreign-Mac run has **not** been performed; that
is the one thing this review cannot substitute for.

**Reviewer lane:** USB REBUILD + FOREIGN-LAPTOP READINESS (Claude, xhigh, zero-deference).
**Artifacts reviewed (all at HEAD `6ba7af8`):**
- `dist/RBSS Bridge.app` (PyInstaller onedir, arm64, ad-hoc signed) + `RBSS Bridge.dmg` (317 MB).
- On stick `/Volumes/MINK/RBSS BRIDGE USB/`: DMG, sibling `RBSS_payload/`, refreshed `lighting_sidecar/` (877 tracks), `install.command`, `purge.command`.

---

## Verdict: **READY-WITH-CAVEATS** (conditional), trending **NOT-READY** for two guest classes

Plain-language bottom line: **on an Apple-Silicon friend's Mac, handed the physical
stick, it will very likely light correctly after one Gatekeeper click** — the software
half is built right and I verified it end to end. But it is **not** "plug in and it
just works on any laptop." Two guest situations make it fail outright, and one live
step nobody has actually run yet.

| Guest situation | Outcome |
|---|---|
| Apple-Silicon Mac, **physical** stick handoff, one "Open Anyway" click | **Expected to work** (software verified; live run still unproven) |
| **Intel** Mac (any) | **Cannot launch at all** — the app is arm64-only (blocker) |
| DMG delivered over the **network** (AirDrop/email/cloud) | Gatekeeper **blocks**; the shipped "right-click → Open" recovery text is **stale for macOS 15** |

Per-question readiness (attacker verdicts, reconciled with my own checks):

| # | Question | Verdict |
|---|---|---|
| a | Can a foreign Mac LAUNCH the bundle? | **NOT-READY** (arch + Gatekeeper) |
| b | Does the frozen app contain tonight's code? | **READY** (proven from the built bytecode) |
| c | Does the sidecar-source path resolve a track (R3 MUST)? | **READY-WITH-CAVEATS** (identity join proven; live twin-resolution unrun) |
| d | Two-USB (his stick + a guest stick) | **READY-WITH-CAVEATS** (safe in the realistic case) |
| e | Does scripted Clarity light scripted? | **READY-WITH-CAVEATS** (Extended Mix yes; RAFAEL remix inactive by design) |
| f | Host paths / secrets / deps the guest lacks | **READY-WITH-CAVEATS** (overrides hold; caveats below) |
| g | What still needs an operator hardware step? | see the checklist |

---

## Findings (severity-ordered)

### BLOCKER — (a) arm64-only ship: an Intel foreign Mac cannot launch it at all
The main executable and **all 303 bundled dylibs/.so are thin arm64** — zero x86_64
slices anywhere. On an Intel Mac the app cannot start (LaunchServices refuses with
"bad CPU type"; Rosetta only translates x86→arm, never arm→x86). This is **by design**:
`packaging/make_stick.sh:45-50,150-158` ships Apple-Silicon-only and fails closed only
when the arm64 slice is *missing* — it never requires x86_64, so it happily ships
arm64-only; `packaging/rbss_launcher.spec` sets no `target_arch`, so PyInstaller builds
for the host arch (this build host is arm64). Independently verified: `lipo -archs` →
`arm64`; whole-bundle sweep → x86_64 count 0/303.
**Operator step:** decide explicitly — either confirm **every** target guest Mac is
Apple Silicon (M-series) before handing over the stick, or commission a universal2
build (PyInstaller `target_arch=universal2` with universal2 numba/llvmlite wheels). No
in-between; today an Intel guest lights nothing. (The failure is loud, not silent.)

### HIGH → (verified) MEDIUM — (a) ad-hoc signed, NOT notarized: Gatekeeper rejects it
The app is ad-hoc signed (`codesign -dvvv` → `flags=0x2(adhoc)`, `TeamIdentifier=not set`,
no stapled ticket) and `spctl -a -t exec` **rejects** both the `dist` app and the app
inside the shipped DMG. It launches on a foreign Mac **only** because the physical stick
(FAT32) carries no `com.apple.quarantine`, so Gatekeeper's assessment is never triggered
(`make_stick.sh:147-149` also strips xattrs on the build machine). The skeptic downgraded
this from blocker to **medium** precisely because the physical-handoff path survives — but
**any network delivery of the DMG re-stamps quarantine** and Gatekeeper then blocks it.
No Apple Developer cert exists on this Mac (`security find-identity -p codesigning` → 0),
so notarization was impossible on the build.
**Operator step:** for robust launch, notarize — enroll in the Apple Developer Program,
mint a Developer ID Application cert, re-run `packaging/sign.sh` (it auto-upgrades from
ad-hoc), then `notarytool submit` + `stapler staple` the app and DMG. Until then, hand
the **physical** stick over and expect one manual Gatekeeper step (below).

### MEDIUM — (a) shipped recovery instruction is stale for macOS 15 Sequoia
When quarantine *is* present, `install.command:14,85` and the in-app text tell the user to
"right-click → Open." macOS 15 Sequoia **removed** that Control-click bypass for apps that
fail notarization; the user must instead go to **System Settings → Privacy & Security →
"Open Anyway"** after a blocked launch. The build machine itself runs macOS 15.3.1, so the
operator's peers are likely on the same or newer OS, where the printed steps dead-end.
**Operator step (hand to Codex):** update `install.command:14,85` + the app's first-launch
text to the Sequoia path (System Settings → Privacy & Security → Open Anyway → relaunch).

### MEDIUM — (f) the 489-entry spectral pre-warm never hits on a *foreign library*
The spectral cache key is `sha1(realpath(audio) + mtime_ns + size + beatgrid_fingerprint)`
(`spectral_cache.py:337-352`) and freshness re-stats the **stored absolute path**. Every
shipped entry stores the operator's own file path, so on a foreign *import* scenario (guest
plays the operator's tracks from a different path, or re-analyzed audio) the pre-warm misses
and each track analyzes ~15 s on first play (lights stay beat-synced during that window).
Note this is the **cache**, not the sidecar — the **sidecar** v4 (R3 path) resolves by
content identity and *does* carry per-track spectral (see finding c). So a foreign laptop
resolving via the sidecar is fine; the App-Support pre-warm cache is the part that won't hit.

### MEDIUM — (f) Govee cloud key ships in plaintext on the stick (operator-approved)
`RBSS_payload/home/govee.env` carries the operator's **live** `GOVEE_API_KEY` (value
**redacted here** — do not commit secrets). This is intentional (secrets-on-stick approved
2026-07-09) and is what makes Govee cloud auth work on the guest — but anyone holding the
stick holds the key.
**Operator step:** treat the stick as carrying a live credential; rotate the Govee key if
the stick is lost or handed to someone untrusted.

### MEDIUM — (f) laser MIDI fallback assumes "IAC Driver Bus 1" (only bites without an Enttec)
`laser_director.json` ships `midi_output_port "IAC Driver Bus 1"` (`enabled=true, dry_run=false`).
IAC Driver is off by default on a fresh Mac. This only matters in the **no-Enttec legacy
fallback**: with the Enttec Pro plugged in, lasers go out DMX and IAC is not needed. Without
it, the port is unavailable and laser output silently degrades.
**Operator step:** bring + plug the Enttec Pro (lasers via DMX, IAC irrelevant). If running
without it, enable "IAC Driver Bus 1" in Audio MIDI Setup and wire SoundSwitch to consume it.

### MEDIUM — (d) no volume↔sidecar binding: a guest's overlapping tracks could get HIS scripted show
`_sidecar_lookup` (`filepath_resolver.py:641-668`) always resolves against the single cached
MINK index regardless of which `/Volumes/<name>` the loaded track sits on. In a **B2B on one
laptop running his bridge** with a guest stick whose tracks overlap his catalog (same
beatgrid/tags), a guest track could exact- or pdb-match his records and get his lighting.
This is **not** the target scenario (his stick, his laptop) and does not affect it — but it's
a real edge for shared-host B2B.
**Optional hardening (not required):** record the origin volume/device signature in
`index.json` at export and require `_sidecar_lookup` to match the playing volume.

### LOW — (d) discovery cache can lock onto a guest sidecar
`_discover_sidecar_index` (`filepath_resolver.py:513-523`) sorts `/Volumes` casefold and
caches the **first** mount carrying `RBSS BRIDGE USB/lighting_sidecar/index.json` into a
process-global that is never invalidated on unmount. If a guest stick *also* had a valid
bridge sidecar and sorted before "MINK", his show could be blanked/replaced for the session.
Very low probability (requires a guest running the same bridge export) but latent.

### LOW — (f) install.command "keep existing config" can strand a foreign Mac on stale configs
For each `RBSS_payload/home` file, `install.command` skips the copy if the destination exists
("kept existing …"). On a truly fresh Mac this is correct. But if App Support was pre-seeded
(a prior aborted install, or the native in-app installer ran first with example defaults), the
real configs + `govee.env` won't overwrite.
**Operator step:** on a foreign Mac, run `purge.command` (or confirm App Support is empty)
**before** `install.command`.

### INFO — (b) PROVEN: the frozen app carries tonight's code, not a stale copy
Real risk, did not materialize. The build venv holds a **non-editable copy** of the package at
`.build-venv-u2/lib/python3.13/site-packages/rb_ss_bridge_v2/` (mtime 03:10) whose
`filepath_resolver.py`/`__main__.py` **differ** from the working tree (pre-AWR-211 snapshot).
But I extracted the actual bytecode from the built app's embedded PYZ (CArchiveReader →
ZlibArchiveReader on `PYZ.pyz`) and confirmed the **frozen** modules are the fresh working-tree
code: frozen `filepath_resolver` contains `_discover_sidecar_index`, the `"RBSS BRIDGE USB"` +
`"lighting_sidecar"` literals, `_sidecar_lookup`, and the AWR-216 seed call; frozen `__main__`
contains `seed_soundswitch_scripted_id_cache`. All are post-03:10 additions absent from the
stale copy. PyInstaller's `pathex`/`sys.path` prepend of the repo parent (`rbss_launcher.spec:18-23`)
made the working tree win.
**Rebuild guard:** any future rebuild should re-run this PYZ-extract check (or delete/reinstall
the site-packages copy first) so a stale snapshot can never be frozen silently.

### INFO — (c) PROVEN: sidecar identity join is self-consistent (R3 exact-mirror match works)
The R3 make-or-break is whether the runtime-computed beatgrid fingerprint (from the mounted
USB's ANLZ) equals the fingerprint the exporter stored. I recomputed the fingerprint from each
track's **own shipped ANLZ** using the exact runtime functions (`_extract_beatgrid_from_anlz`
+ `spectral_cache._beatgrid_fingerprint`) and compared to the stored index value:
Clarity Extended Mix `e82db51a809a18fa` == stored; Clarity x ICBTO `e3724921a39be095` == stored;
3/3 random samples matched. So on a mirror USB (same rekordbox analysis) the runtime's
`sidecar-mirror-match` (`filepath_resolver.py:556-561`) fires. The no-DB fall-through is clean:
`Rekordbox6Database(RB_DB_PATH)` raises → `except` (`:888`) → device-export → `_sidecar_lookup`
(`:898`); the sidecar supplies the v4 spectral + phrase from `v4/<id>.json` (present on stick),
and the ssid from the record (`_payload_for_sidecar:633`). Sidecar validates 877/877 under the
loader's strict all-or-nothing check.

### INFO — (c) sidecar destination CORRECTED during the rebuild
The rebuild prompt specified `--dest "/Volumes/MINK"`, which writes to the stick **root**
(`/Volumes/MINK/lighting_sidecar/`). The runtime reads the sidecar **only** from
`mount/"RBSS BRIDGE USB"/lighting_sidecar/index.json` (`filepath_resolver.py:518`), and
`install.command` does not relocate it. Writing to the root would have silently produced a
sidecar the runtime cannot read — the R3 path would fail on the foreign Mac with no error. The
export was therefore run to `--dest "/Volumes/MINK/RBSS BRIDGE USB"`, matching both the runtime
read path and the pre-existing convention. Verified: fresh `index.json` sits at the runtime path,
877 tracks, HEAD `6ba7af8`.

### INFO — (e) scripted Clarity (Extended Mix) recognized + renders; RAFAEL remix inactive by design
The launcher forces `RBSS_SCRIPTED_SHOWFILE_DIRECT=1` (`launch_profile.py:34`, applied via
`os.environ.update` so it overrides any guest env), the pack loads and AWR-216 seeds the active
id `3974E696` (the only track_map entry with `active_existing_path: true`), normalization matches
on both sides of the join (`_normalize_soundswitch_id`), the no-DB path supplies the ssid **from
the sidecar record** (works even if the exported audio has no SoundSwitch tag), and the show
renders by ssid (`soundswitch_laser_player.select_scripted → render_scripted_frame`). **Caveat:**
the *second* Clarity — "Clarity x I Could Be the One (RAFAEL Remix)", `CA3D22AA`, sidecar id
158843778 — ships `active_existing_path: false`; it is not seeded and falls to autoloop/personality
lighting. Only the Extended Mix lights scripted. (This matches AWR-216's intent.)

### INFO — (f) verified-safe host assumptions (do not re-flag)
Three build-machine paths are each overridden at runtime, so the primary DMX/laser show path
carries no unmitigated host dependency: (1) the build-machine `pack_path` in
`soundswitch_pack_player.json` is overridden by `RBSS_SS_PACK_PATH`, which `usb_launcher.py:110-112`
sets to App Support/soundswitch_pack (populated by `install.command`) and the loader honors over
the config (`soundswitch_pack_player_config.py:116-118`); (2) the hard-coded Enttec serial is
rescued by identity auto-detect (`enttec_dmx_pro.py`); (3) `NUMBA_CACHE_DIR` is set to a writable
App-Support path (`usb_launcher.py:117`). The Govee LED "silent-nothing" claim was **refuted** by
the skeptic (there is a discovery fallback) — but the operational reality stands: Govee LED needs
his own strips on the venue LAN (same subnet, multicast not firewalled) to resolve.

---

## What is NOT ready — the exact operator checklist remaining (question g)

"Software-staged" is not "works on a foreign Mac." These steps/assumptions only a real
foreign-Mac run can settle:

1. **Confirm guest arch = Apple Silicon.** Intel = no launch (blocker above). No workaround short of a universal2 build.
2. **Hand over the PHYSICAL stick** (don't AirDrop/email the DMG) so no quarantine is applied; if quarantine does appear, use **System Settings → Privacy & Security → Open Anyway** (not right-click → Open on macOS 15).
3. On the foreign Mac, **run `purge.command` first if App Support is non-empty**, then `install.command` (or use the native in-app installer). Confirm it prints the app + payload copies (spectral cache, configs + Govee key, pack).
4. **Keep the stick plugged in during the show** — the runtime reads the lighting sidecar **live** from `/Volumes/<stick>/RBSS BRIDGE USB/lighting_sidecar/`; it is *not* copied to App Support.
5. **Plug in the DJ hardware:** Enttec Pro (DMX lasers), and if using the Govee cloud/LAN LEDs, bring his own Govee strips and join them to the venue LAN.
6. **Live-verify the R3 resolve:** load a track (e.g. Clarity Extended Mix) from the playing USB and confirm a `[SM] scripted-match … source=direct` log line + the pack renders cues, and that v4/phrase come back from the sidecar. The identity join is proven statically; the *live* twin-resolution (device-export classification of the guest's anlz_path + `.dat` beatgrid parse) is the one piece not exercisable read-only.
7. **SoundSwitch/OS2L wiring** on the guest (transport + MIDI look selection) as usual.

---

## Method note

Phase-2 review ran as a multi-agent adversarial fan-out (7 independent attackers, each
material finding re-checked by a skeptic instructed to refute it). Attackers for questions
(c) and (e) hit repeated mid-response API failures; (c) was backfilled with direct
operator-side verification (the fingerprint-parity proof above + code trace), and (e)
completed on a re-run. All load-bearing claims here were re-verified against current code and
the mounted stick before writing. The bridge runtime was never started.
