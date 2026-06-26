---
doc_status: active-adversarial-prompt
truth_level: code-grounded
last_verified_commit: 6caa0d7
last_verified_date: 2026-06-26
validation_scope: one-shot Opus 4.8 adversarial edge-case discovery prompt for the ENTIRE SoundSwitch reverse-engineering -> pack -> runtime -> live-DMX pipeline, in the context of the bridge repo and live performance; READ-ONLY on the live ~/Music project (ALL mutation on scratchpad copies only); no bridge restart, no Enttec/DMX/MIDI/hardware, no running-bridge interaction, no live project mutation, no commits; SOFTWARE-ONLY DISCOVERY / HARDWARE-UNVALIDATED
---

# Adversarial edge-case discovery — the entire SoundSwitch RE pipeline, in the live-performance bridge

You are an Opus 4.8 adversary working in `/Users/bbui/rb_ss_bridge_v2`. Your single
job: **find every way the SoundSwitch reverse-engineering pipeline can break, lie, or
mislead — and prove each one with a runnable repro.** Not the menubar exporter alone:
the *entire* RE project, end to end, judged by what it does to the lights during a live
DJ set.

Read `AGENTS.md` first (source-of-truth order: code > tests > docs; if a doc conflicts
with code, code wins). Then work the plan below. Be relentless. The best finding is the
one nobody thought to look for.

---

## 1. What the pipeline is, and why a bug matters live

SoundSwitch is the operator's **authoring tool**. They build the light show there (Venue
cues, Static Looks, Autoloops, scripted tracks, MIDI control mappings) and save. The
bridge then runs this pipeline so SoundSwitch does **not** have to be in the live loop:

```
~/Music/SoundSwitch/default.ssproj   (live source, operator edits it continuously)
        |  decode_project()                 soundswitch_project_decoder.py
        v
   DecodedSoundSwitchProject
        |  compile_pack_artifacts()          soundswitch_pack.py
        v
   pack artifacts (canonical JSON)
        |  verify_pack()                      soundswitch_pack_verifier.py
        v
   export_pack() / publish_pack()            tools/export_soundswitch_pack.py
        |  -> repo-local canonical pack + freshness sidecar
        v
   load_pack()                               soundswitch_pack_loader.py   (bridge startup)
        |
        v
   SoundSwitchMidiInputAdapter              soundswitch_midi_input.py
        |  IAC/DDJ note + CC -> static looks, blackout, autoloop selection
        v
   DMX CH1-CH19 over Enttec  ===>  LIVE LIGHTS during a DJ set
```

**Live stakes — judge every finding against these:**
- A **silent-wrong** decode/compile = wrong colours/intensities on stage, or a pad that
  does nothing, with no error shown.
- A **false-pass** verify (verify_pack returns verified=True on a semantically broken
  pack) = the bad pack ships and goes live.
- A **crash** on export = the operator cannot update their show before/at a gig.
- A **live-reload / concurrency** bug = lights freeze, flash, or blackout mid-set.
- A **classification collision** = the operator maps a control one way in SoundSwitch
  and the bridge does something else entirely (see Known Sharp Edge #1).

Every finding must end with: *"Live impact: ___."* If you can't name a live impact,
say so and rank it cosmetic.

---

## 2. Scope — the entire RE surface (do not stop at the exporter)

Runtime / pack core (in repo root):
- `soundswitch_project_decoder.py`, `soundswitch_pack.py`, `soundswitch_pack_verifier.py`,
  `soundswitch_pack_loader.py`, `soundswitch_pack_models.py`, `soundswitch_pack_runtime.py`,
  `soundswitch_midi_input.py`, and the menubar/startup wiring in `__main__.py`.

The RE toolkit (`tools/ssfmt/re/` — 28 modules — this is the part people forget):
- Parsers: `parse_venue_cues.py`, `parse_autoloop_catalogs.py`, `parse_track_map.py`,
  `analyze_static_looks.py`, `analyze_scripted_layouts.py`, `analyze_scripted_ssfile.py`,
  `analyze_ssfile_structure.py`, `ssparse.py`, `analyze_control_semantics.py`,
  `analyze_deck_ownership.py`, `analyze_fixture_prefix.py`.
- Resolvers/inventory: `inventory_project_artifacts.py`, `build_coverage_reports.py`,
  `correlate_midi_autoloop.py`, `uuidxref.py`, `oracle_canonicalize.py`.
- Renderers/oracles: `layered_renderer.py`, `validate_scripted_capture.py`,
  `validate_autoloop_capture.py`, `verify_export_completeness.py`, `t7d_phase_contract.py`.
- Snapshot/diff: `freeze_project_snapshot.py`, `compare_project_snapshots.py`,
  `build_scripted_residual_corpus.py`, `audit_legacy_capture.py`, `align_capture.py`,
  `parse_artnet_pcap.py`, `artnet_sniff.py`.
- The gate: `tools/prove_soundswitch_pack_generation.py` and its tests.

Tooling/integration: `tools/export_soundswitch_pack.py`, freshness sidecar logic,
`tests/test_soundswitch_*.py`, `tests/test_prove_*.py`.

If a module reads a SoundSwitch binary or transforms decoded data, it is in scope.

---

## 3. Method — RUN it, don't read it. Build a mutation corpus and break each stage.

Reading finds maybe 20% of these. The rest only fall out when you execute against
hostile inputs. Required approach:

1. **Baseline.** From `/Users/bbui`, run the package: decode/compile/verify/export the
   live project into scratchpad and capture the clean outputs as your oracle.
   Run `python3 tools/ssfmt/re/prove...`/the proof gate and `python3 -m unittest
   discover tests` (from inside the repo) to know the green baseline.
2. **Copy, never touch the original.** The live project is
   `~/Music/SoundSwitch/default.ssproj` (a directory: `.ssproj` manifest +
   `SoundSwitchVenues.bin` + `SS*.ssfile` + `SoundSwitch*.bin`). `shutil.copytree` it
   into the scratchpad dir for EVERY mutation. The live source is READ-ONLY.
3. **Mutate along every axis in section 4.** One mutation per copy. For each: run the
   full pipeline and record the outcome as one of:
   - `clean-pass` (handled correctly),
   - `crash` (unhandled exception / hang / OOM),
   - `silent-wrong` (pipeline succeeds but output is semantically wrong),
   - `false-pass-verify` (verify_pack verified=True on a broken pack) — **the worst**,
   - `correct-reject` (fails closed with a clear, accurate error).
4. **Differential oracle.** After each edit, diff decoded/compiled output vs baseline:
   assert the *intended* change is reflected **and nothing else moved**. Silent
   collateral change is a bug class of its own.
5. **Adversarially verify every "pass."** When verify_pack says verified=True, do NOT
   trust it — independently check the pack actually represents the source (counts,
   GUIDs, values, classifications, render output). Hunt hardest for inputs where verify
   is green but the pack is wrong. Treat the proof gate itself as a target: can you
   construct a project that the proof passes but that renders wrong live?
6. **Loop until dry.** Keep going until two consecutive rounds of new mutation ideas
   surface nothing new. You may spawn subagents/workflows to parallelize disjoint axes;
   keep live-safety/runtime reasoning on a high tier and verify subagent claims yourself.

Binary note (confirmed this session): the venue format **entangles values with
structural length/offset/count fields** — a naive single-byte flip corrupts the parse
rather than cleanly changing one value (it dropped a whole cue, 233->232). So to
simulate a *clean* operator edit you usually must mutate at the **decoded-model level**
(decode -> `dataclasses.replace` the field -> `compile_pack_artifacts` -> `verify_pack`),
or learn the record layout well enough to rewrite lengths consistently. Use both: model-
level mutation for "valid operator edit" coverage, raw-byte corruption for "malformed/
hostile file" coverage. Don't confuse a botched byte-flip for a real rejection.

---

## 4. Edge-case axes — go wide, then deep on each

**Content edits (valid operator authoring — must all export clean):**
- Add / remove / reorder Venue cues; change a cue's channel **values**; set a cue all-zero;
  add/remove fixture_groups or channels referenced by a cue.
- Add / remove / rename Static Looks; change a look's values; add a 33rd look (is 32 a
  real SoundSwitch cap or just current content?).
- Add / remove / reorder Autoloops; add / remove scripted tracks; flip a track active/inactive.
- Re-learn / add / remove MIDI control mappings; remap a pad to a different look.

**Classification & MIDI mapping collisions (the live-control surface):**
- IAC vs DDJ device on the same note/channel; two enabled bindings on the same
  device/channel/note (collision detection); note vs CC vs pitch-bend on a render-
  affecting control (F10 path); message types that aren't "note".
- The blackout reserved event (IAC Driver Bus 1, Ch1/Note0): map it to a Static Look, an
  Autoloop, a non_render target, or nothing; map a *different* event to the BLACK OUT
  look; have both a blackout_mask and a static_look fight for the same pad. Trace the
  classification order in `_selection_map` (producer) AND `verify_pack` (consumer) AND
  `_runtime_metadata`/`load_pack` AND `soundswitch_midi_input` — they must agree.
- Static override slot out of range, duplicate slot ownership, press vs toggle
  interaction modes, toggle that never releases.

**Identity / boundary / file presence:**
- Wrong project UUID, wrong/absent primary Venue GUID, wrong SoundSwitch version,
  missing `.ssproj` / `SoundSwitchVenues.bin` / an `.ssfile`, extra unexpected files,
  multi-venue project, a second venue that looks primary.

**Binary / format hostility (malformed inputs the parsers must reject, not crash on):**
- Truncated files (every length), trailing garbage, zeroed regions, flipped magic bytes,
  corrupted length/count prefixes, duplicate cue GUIDs, GUIDs that don't match references,
  absurd counts (claims 100k records), negative/overflow integers, non-UTF8 strings,
  reordered records, an extra or missing catalog-tail record (0 tails? 5 tails?).

**Cross-reference integrity:**
- Autoloop/scripted that references a Venue cue GUID that doesn't exist (missing_cue);
  active-cue union with dangling references; a referenced look/slot that was deleted;
  scripted layouts that are unsupported, the inactive In-App Demo, existing vs
  non-existing track filepaths; the A5 legacy scripted wire format; one-based vs raw-zero
  vs ambiguous cue-reference resolution (must fail closed on ambiguous, never guess).

**Render correctness (does the pack actually produce the right DMX?):**
- Sparse patches updating present channels while omitted channels persist; raw-zero
  clears; seek/backward/pause/refire history-independence; stop/end/unload -> all-zero;
  negative pre-roll; layered static override priority (static override is an authoritative
  overlay that loses only to blackout/emergency — verify that ordering survives edits).

**Freshness / concurrency / live performance:**
- Source mutated during read (TOCTOU / re-hash detection); stale or missing freshness
  sidecar; sidecar that disagrees with pack identity; export run while a "show" is
  conceptually live; pack reload while the player is rendering; re-anchor timing (clears
  must precede reload by a beat — same-tick clear+reload is ignored downstream); blackout
  asserted during a drop; what the menubar reports (Exported vs failure states) for each.

**Filesystem / output:**
- Symlinked project inputs (must reject), symlinked or non-real output dir, output parent
  missing, partial/interrupted export (does it leave a half-written canonical pack live?),
  canonical-JSON hostility (duplicate keys, noncanonical encoding, non-ASCII).

**The RE toolkit itself:**
- Run each `tools/ssfmt/re/*` module against the live project and against malformed
  copies. Do parsers crash, hang, or silently mis-parse? Do `inventory_project_artifacts`
  / `build_coverage_reports` agree with the production decoder, or diverge (see Sharp
  Edge #2)? Does `freeze_project_snapshot` + `compare_project_snapshots` actually catch a
  real semantic drift, or can drift slip past it? Does `verify_export_completeness` have
  blind spots?

---

## 5. Known sharp edges (seed the hunt — confirmed this session)

Use these as starting threads; they are real and they imply siblings you should chase.

1. **Blackout vs static-look classification collision (CONFIRMED real).** Any IAC Driver
   Bus 1 / Ch1 / Note0 / message_type=note control is classified `blackout_mask` *before*
   the `static_look` branch in both `soundswitch_pack.py` `_selection_map` and
   `verify_pack`. So mapping that reserved event to a Static Look (e.g. "BLACK OUT")
   silently becomes a momentary DMX-blackout hold, not a static-look load. Today it
   happens to be visually equivalent because that look renders all-zero — **find the case
   where it is NOT equivalent** (non-zero "blackout-ish" look, toggle vs momentary intent,
   priority interactions). Then audit every other reserved/special-cased event the same way.
2. **"DDJ" label over device-agnostic data (CONFIRMED mislabel).** The proof's
   `B3b-ddj-overrides` and the RE inventory's `static_look_midi_selection` lump IAC
   bindings in with DDJ ones. Names assert device/identity that the code doesn't enforce.
   Hunt the whole codebase for more name-vs-meaning mismatches that would mislead an
   operator or a future agent.
3. **Frozen content-pins were time bombs (JUST removed from the proof; verify it stuck).**
   `prove_soundswitch_pack_generation.py` previously hard-asserted 232/42/45/166/19/4 and
   slot lists; these were made dynamic. Confirm none remain (B1/B2/B4/B5/D1 now
   structural), and check the snapshot/compare tooling and tests for the same pattern.
   `D2-ddj-ch1-19-frames` is *intentionally* still a golden render-correctness pin on
   slots 8/16/17/24 + exact frames — decide if that's a latent break or correct, and say so.
4. **Binary length/offset entanglement (CONFIRMED).** See section 3's binary note.
5. **cue_guid is a stored 16-byte field, not content-derived** (`soundswitch_project_decoder.py:520`)
   — so value edits preserve cue identity/references. Verify this assumption holds across
   ALL record types (looks, autoloops, scripted) — find any place identity *is*
   content-derived and would break references on an edit.
6. **Blackout is a momentary boolean at runtime** (`soundswitch_midi_input.py` sets
   `_blackout_held` on note-on/off; `target_identity` is never dereferenced). Confirm no
   runtime path *does* dereference a blackout target, and that removing the loader's
   "missing autoloop" check didn't open a hole.

---

## 6. Constraints (live-safety — non-negotiable)

- **READ-ONLY** on `~/Music/SoundSwitch/default.ssproj`. All mutation happens on
  `shutil.copytree` copies under the scratchpad dir. Never write into ~/Music.
- **Never touch the running bridge or hardware**: no bridge start/stop/restart, no Enttec/
  DMX/MIDI device open, no SoundSwitch app interaction, no `pgrep`-and-kill, nothing that
  could affect a live rig. This is software-only discovery.
- **No commits, no branches, no repo mutation** beyond scratchpad scratch files. Do not
  edit production code to "fix" what you find — your job is discovery + repro, not patching.
- **Label every claim confirmed / assumed / unknown.** Reproduce every confirmed bug with
  an exact runnable command or script before you report it. No hand-waving; this project
  has been burned by confident-but-unverified claims.
- Run the package from `/Users/bbui` as `rb_ss_bridge_v2...`; run the proof gate and
  `unittest discover tests` from inside `/Users/bbui/rb_ss_bridge_v2` (some test modules
  import `from tests....` and only resolve from the repo dir).

---

## 7. Deliverable

A single structured report (Markdown), findings ordered by severity:

1. **live-safety-critical** — wrong/missing/frozen lights live, or blackout fails.
2. **false-pass-verify** — verify_pack/proof green on a semantically broken pack.
3. **silent-wrong-output** — succeeds, output wrong, no error.
4. **crash-blocks-export** — operator cannot update their show.
5. **cosmetic / mislabel** — misleading names/messages, no functional impact.

For each finding:
- **What** (one line) and **where** (`file:line`).
- **Repro** — exact command(s) or a short script that reproduces it from a clean checkout.
- **Live impact** — what the operator sees on stage, or "none (cosmetic)".
- **Confidence** — confirmed (with the repro output) / assumed / unknown.
- **Fix direction** — one line, no code.

End with a **coverage map**: which axes/modules you exercised, which you could not (and
why), and the two highest-value things a follow-up run should attack next. If you found
nothing in an axis, say so explicitly — silence reads as "covered" when it wasn't.

Be exhaustive. Reach into every crevice. Try to break it.
