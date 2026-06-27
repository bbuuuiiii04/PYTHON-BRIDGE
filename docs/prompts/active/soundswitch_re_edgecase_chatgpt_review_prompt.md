# ChatGPT adversarial review — SoundSwitch exporter + DMX runtime bug-hunt

You are a skeptical senior engineer reviewing another AI agent's bug-hunt report on a **live-performance
DJ lighting bridge**. Your job is to **challenge every finding**, not rubber-stamp it. The author has a
track record of confident-but-wrong claims and of mistaking intended features for bugs, so assume each
finding is wrong until its reasoning holds up. Be specific and adversarial.

This prompt is self-contained — the condensed findings are below. (If asked, the operator can also paste
the two full docs: `soundswitch_re_edgecase_findings.md` and `soundswitch_re_edgecase_hardening_spec.md`,
which carry the exact `file:line` claims and fix directions.)

## The system (just enough context)
A bridge turns a SoundSwitch lighting project into a "pack," then drives DMX lights from it:
`~/Music/.ssproj → decode → compile pack (canonical JSON) → independent verify → export → load_pack →
pack player (renders CH1-19) → MIDI input (DDJ pads / IAC) → Enttec DMX → lights`.

**SCOPE (strict):** ONLY the SoundSwitch **exporter** (decode→compile→verify→export + the `tools/ssfmt/re`
research toolkit) and the **DMX runtime** (load→pack player→MIDI input→frame sender→Enttec). NOT the
Rekordbox readers, the MIDI laser director, the LED/Govee engine, or the audio/spectral analysis.

## Real-world facts the operator CONFIRMED (use these to judge reachability — do not re-litigate them)
1. The new SoundSwitch **pack is NOT live yet** — there is no `config/soundswitch_pack_player.json`, so the
   bridge runs a legacy path; the pack does not currently drive DMX. So pack-*runtime* findings are
   pre-go-live, not live bugs today.
2. **BPM is ALWAYS known** (never 0) for any real track.
3. The **"BLACK OUT" pad is authored press-and-hold** (press = dark, release = restore).
4. **Drops should always fire**, even when cued exactly onto one.
5. The pack only opens the **DDJ-800** as a live MIDI input; the IAC blackout binding is never read by the pack.

## Findings to review (condensed; the author's claims — verify or dispute each)

**Exporter:**
- **F3** — Two controller pads learned to the SAME Static Override slot: the independent verifier returns
  "verified", but the loader then REJECTS the pack ("duplicate active static_override slot ownership"). Claim:
  the verifier should enforce the same rule the loader does, so a "verified" pack can't fail to load. Author
  proved it from raw bytes through the real decoder. Severity: real, bites the build/export workflow.
- **F5** — Same shape: a control mapped to a bridge-reserved scene event (`house_post_drop_1`, IAC ch0/note41)
  verifies "verified" but the loader rejects it. Same fix class as F3.
- **F4** — A truncated Autoloop catalog file makes the decoder raise a raw `struct.error` instead of the
  decoder's own clean error type, escaping `decode_project`. One unguarded `struct.unpack_from` (catalog
  entry loop); every sibling has a bounds check. Severity: corrupt/partial file crashes the export.
- **F6** — A research-inventory field labels an IAC binding as a "DDJ override" (device mislabel). Cosmetic.
- **F7** — The proof gate hardcodes the exact DMX frames of 4 static-look slots, so recolouring any of those
  4 looks fails the gate even though export/verify/load are fine. Latent gate brittleness.
- **F8** — The production export never cross-checks the parsed Venue cue count against SoundSwitch's own
  declared count; a corrupted venue that drops an *unreferenced* cue exports clean. Low (unreferenced).
- **F1** — A Static Look mapped to the reserved IAC blackout event is reclassified as a blackout. Author now
  marks this NOT a bug, because the operator wants that pad to BE a press-and-hold blackout (matches intent).
  → Challenge: is "not a bug" correct given facts 3 & 5?
- **F2** — Whether a scripted track's lights are "active" depends on whether its audio file exists on the
  machine doing the export. Author deferred it (operator didn't recognize the scenario; pack not live).
  → Challenge: is deferring right, or is this a real silent-wrong waiting for go-live?

**DMX runtime:**
- **F12** — A held blackout auto-releases after ~2s (a "stale" timer measured from the press, not from
  controller silence), so a press-and-hold longer than 2s un-blacks itself. Author: real bug, but pre-go-live
  (pack not driving DMX yet). Fix: measure controller silence, not time-since-press.
  → Challenge: is the 2s timer actually intended as a safety (controller-died failsafe) rather than a bug?
  Does the proposed fix reintroduce a stuck-blackout risk if the controller really does die mid-hold?
- **F14** — An autoloop arm-correction has a loop with no iteration cap that spins forever if fed BPM=0 with a
  too-short beat-map. Author marks NOT reachable (both callers are guarded; one path is dead because its flag
  is always false; and fact 2 says BPM is always known). → Challenge: did the author actually prove BOTH
  callers are guarded, or just assert it? Is the "dead flag" really always false?

**Found while out of scope (the author admits these are outside the exporter/DMX-runtime scope — judge whether
they should be in the report at all):**
- **F13** — In the phrasing engine (drives the MIDI laser, NOT the pack): a drop landing exactly on the first
  beat after a reset/cue is missed. Operator confirmed drops should always fire. Out of scope but real.
- **F15** — The 200Hz loop has no per-tick error catch and re-raises, so one unhandled error freezes the whole
  show (no auto-restart). Operator wants skip-and-continue. No reachable trigger was found. → Challenge: is
  fail-fast actually the safer choice for a lighting rig (go dark vs. run on possibly-corrupt state)? Could a
  "catch and continue" wrapper hide a real problem or loop on a persistent error?

## Your task — for EACH finding above
Give a verdict: **CONFIRM / DISPUTE / NEEDS-MORE-INFO**, with concrete reasoning. Specifically attack:
1. **Feature vs bug** — could this be intended behavior the author misread? (Weigh the operator facts.)
2. **Reachability** — is it actually reachable in the real config, or latent/dead-code? Did the author prove
   it or just assert it?
3. **Severity** — is the grade right given the pack isn't live yet?
4. **Repro validity** — does the repro bypass a guard the real code path has (e.g. injecting model state the
   decoder would never produce)?
5. **Fix safety** — is the proposed fix correct AND live-safe? Could it regress the show (e.g. F12's fix
   reintroducing a stuck blackout, F15's fix masking a real fault, F3/F5's new verifier checks rejecting a
   currently-valid pack)?

Then add:
- **New issues / missed edges** the author did NOT consider, within the exporter + DMX runtime scope only.
- **Any fix that could break a live show** — call it out loudly.
- **Anything the author claimed as verified that you think is actually unverified.**

## Output format
A table: `Finding | Verdict | Reasoning | Fix safe? (Y/N/—)`; then the three sections above. Keep it concrete —
cite the specific logic, not generalities. If you need a specific piece of code to decide, say exactly which
function/file and mark that finding NEEDS-MORE-INFO rather than guessing.
