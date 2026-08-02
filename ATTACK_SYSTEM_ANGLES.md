# ATTACK_SYSTEM_ANGLES — adversarial system-angle attack on v8

**Design attacked:** `docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md`

**Requirement set held fixed:** `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md`
**Mode:** attack only. This report proposes no replacement design and changes no acceptance gate.

I read the dossier, v8, `COMBINED_DESTROY_review.md`, `REVISION_ROUND_1.md`, and every named round
through `ROUND_8_fable.md`. I treated their CURED and AGREED rulings as history, not proof. The four
passes below deliberately test current source evidence, run residue, corpus shape, storage, elapsed
time, and provider availability that those rounds did not settle.

## Overall attack ruling

[confirmed] V8 is much better at refusing to lie than the old program. It is not yet a credible
operating model for the stated 700–800-track goal. The worst problem is not another missing wording
guard: the current 34-track representation already occupies 10.47 GiB on a disk with about 18 GiB
free, while only 34 of the 721 measured tracks have that representation. [assumed] A rough linear
capacity check puts the same representation at about 222 GiB for 721 tracks and the recorded
stem/frame pass at about 101 hours before retries or independent checking. [confirmed] Meanwhile,
the existing development evidence is dominated by one sound class and contains a known operator
mark that the structural proof would reject because the section clock is one beat late. The design
can therefore become scrupulously governed and still spend the available disk, wait on quota, and
return honest refusals instead of locating laser moments across the library.

## Pass 1 — evidence custody and provenance

### 1.1 The first governed outputs are scheduled before the evidence system they claim to use

- **What is wrong:** [confirmed] V8 says every `develop` run shares the evidence checks and sender
  (`spectral_program_operating_model_v8_2026_08_02.md:141-143`). Its adoption order nevertheless
  builds and exposes the laser development slice, evaluator, other lanes, and library census in
  steps 1–4, then builds the intake wrapper and evidence database in step 5 (`:573-604`). The design
  calls step 1 governed but has not yet built the mechanism that captures every message, assigns a
  disposition, accounts for every active judgment, and blocks unreconciled evidence.
- **Why it matters to the goal:** [confirmed] The dossier's central custody failure was not merely
  that results lacked hashes; operator evidence was missing while the paperwork appeared current
  (`spectral_program_failure_dossier_2026_08_02.md:110-128`). A hash-bound laser sheet produced
  before the evidence ledger exists can repeat that exact failure with cleaner packaging.
- **Evidence checked:** [confirmed] I checked the `develop` contract, the §5 publication block at
  design lines 257–313, and all ten adoption steps at lines 573–614. [unknown] The design does not
  say that step 1 secretly implements a temporary evidence database; doing so would contradict the
  named purpose and order of step 5.
- **Concrete failure scenario:** [assumed] Step 1 publishes a checked laser development sheet with a
  valid run id and body hash. Step 5 later imports an earlier operator correction that changes the
  meaning or length of one row. The first sheet was called governed even though the evidence needed
  to reconcile it was not yet present.

### 1.2 Importing the current record can launder reconstructions into “exact inbound messages”

- **What is wrong:** [confirmed] The proposed schema stores an inbound message as unique source,
  source position, received time, exact text, and text hash, then links a judgment to that exact
  message (`spectral_program_operating_model_v8_2026_08_02.md:263-273`). Step 5 says only “Import
  known sources” (`:602-604`). The principal current source file calls itself raw verbatim text but
  says the descriptions had existed only in chat and were later transcribed
  (`local/spectral_v5_2026_07_17/OPERATOR_SOUND_DESCRIPTIONS_VERBATIM.md:1-9`). It also contains an
  approximately timed quote recovered from a charter because the original chat may be gone
  (`:224-232`), five exec-recorded recoveries whose originating chats are gone (`:486-492`), items
  explicitly not recoverable verbatim (`:540`), and an agent-authored gloss that was corrected in
  place after being found wrong (`:560-565`).
- **Why it matters to the goal:** [confirmed] A database can preserve bytes perfectly while
  misrepresenting what those bytes are. If a reconstruction is promoted to an exact operator
  message, every later evidence count, supersession, compiled check, and “all judgments accounted
  for” line inherits false provenance.
- **Evidence checked:** [confirmed] I checked the current source file's own provenance admissions,
  the dossier's warning that some `user`-typed turns were agent-authored
  (`spectral_program_failure_dossier_2026_08_02.md:250-256`), and v8's complete proposed evidence
  row list. [unknown] V8 defines no migration status for primary transcript bytes versus
  transcription, contemporaneous agent record, recovered paraphrase, mutable gloss, or lost source.
- **Concrete failure scenario:** [assumed] The importer assigns `~22:4x`, a charter line, and the
  recovered quote a synthetic source position and received time. The row then satisfies the exact
  message foreign key. A later checker proves that the row reached the analysis path, but cannot
  reveal that the supposedly exact source was already a derived record.

### 1.3 Exact-message linkage does not preserve how a message became a musical judgment

- **What is wrong:** [confirmed] V8 links a judgment to an exact whole message but does not require
  a character span, the extracting person/model, the extraction rule/version, or a derivation from
  text to beat/interval/class. Its own `analysis_input` check proves only that a different hash
  reaches a code path, not semantic understanding (`spectral_program_operating_model_v8_2026_08_02.md:304-306`).
  The current record proves that this transformation is consequential: the 54-row v7 ledger carried
  inferred intervals on 48 rows, while v11 discarded guessed geometry for 27 point judgments and
  retained only 21 stated spans (`local/spectral_v5_2026_07_17/scorer/scorer_gold_ledger_v11_author_note.md:17-30,65-67`).
- **Why it matters to the goal:** [confirmed] His evidence includes position, duration, description,
  veto, and context. Quietly converting a timestamp guide into an exact interval, or a descriptive
  sentence into an exclusion rule, is the fitting step that changes what the program is asked to
  hear. Storing the source message and final row does not expose that step.
- **Evidence checked:** [confirmed] I compared all three on-disk ledgers. They each have 54 rows but
  distinct SHA-256 hashes. V7 has 48 non-null judged intervals; the draft has 15; v11 has 21 span
  intervals plus 27 point judgments. Six rows in each have empty `provenance`. The authoritative
  v11 author note correctly documents that particular correction, but v8 does not make equivalent
  derivation custody a database invariant.
- **Concrete failure scenario:** [assumed] A mixed operator message contains a timestamp, “guide,”
  and a natural-language description. An importer turns it into a hard interval and class veto,
  links the row to the correct whole message, and marks it `compiled_check`. Every count and hash
  passes; the program has still fitted his words into a different requirement.

## Pass 2 — operations and failure

### 2.1 The database transaction and the sealed-directory rename cannot fail atomically together

- **What is wrong:** [confirmed] V8 makes a filesystem rename the act that assigns a sealed run id
  (`spectral_program_operating_model_v8_2026_08_02.md:422-423`) while SQLite separately owns run
  state and leases (`:493-515`). A SQLite transaction cannot atomically commit an unrelated
  filesystem rename. The design specifies backup/message recovery but no startup reconciliation of
  sealed directories against database rows, no orphan rule, and no commit order that makes both
  crash outcomes safe.
- **Why it matters to the goal:** [confirmed] The run id is the authority for checking, sending,
  correction, and reproduction. Disagreement between disk and SQLite can recover into the wrong
  run, rerun expensive work, or publish a database body whose retained bundle does not exist.
- **Evidence checked:** [confirmed] I checked §§8–9 and searched v8 for orphan handling, directory
  reconciliation, or filesystem sync; none is specified. Current artifacts show this is not a
  theoretical failure class: two partial CLAIMS1 runs were discarded at a cost of about 22 minutes
  because their process lineage could not be trusted
  (`local/spectral_v5_2026_07_17/CLAIMS1_embed_report.md:89-104`). Old run/cleanup lock files dated
  July 24 and a `stage2_offline_sweep.lock` containing PID 44964 dated July 30 remain on disk.
- **Concrete failure scenario:** [assumed] The worker renames the complete temporary directory, then
  dies before committing `WAITING_FOR_CHECKER`. Recovery sees no run and repeats it, leaving two
  sealed bundles for one request. In the reverse order, SQLite commits the run and the process dies
  before rename; the checker leases a run whose bundle is missing or still temporary.

### 2.2 “Successful delivery” cannot be made exactly once by a local row

- **What is wrong:** [confirmed] V8 moves a verified body to `PUBLISHED` only after the sender records
  successful delivery, and separately stores unchecked delivery and correction notices
  (`spectral_program_operating_model_v8_2026_08_02.md:480-505`). Sending to chat and committing
  SQLite are two independent effects. V8 names no remote message id, idempotency key, receipt
  lookup, or delivery reconciliation.
- **Why it matters to the goal:** [confirmed] This is the one surface the operator reads. Duplicate
  sheets, a duplicate “do not use it” correction, or a locally published body that never arrived
  are not bookkeeping defects; they directly change which result he believes.
- **Evidence checked:** [confirmed] I checked the complete sender and correction contracts at design
  lines 453–487 and 502–507 and searched the design for remote receipts and idempotency; none is
  present. [unknown] The eventual chat transport may offer an idempotency or history API, but v8
  neither requires nor measures it.
- **Concrete failure scenario:** [assumed] Chat accepts the body and returns success. The process
  dies before SQLite commits delivery. Recovery sees an undelivered verified run and sends it again.
  If local state is committed first to avoid that duplicate, the opposite crash loses the body.

### 2.3 Lease expiry can create two live owners because time is not a fence

- **What is wrong:** [confirmed] The design stores lease owner, expiry, stage, hash, and resume token,
  and a `launchd` job changes expired work to `RECOVERY_NEEDED` (`spectral_program_operating_model_v8_2026_08_02.md:509-516`). It says concurrent writers are rejected, but does not define a monotonically
  increasing lease generation that every stage/database commit must present. It also uses times for
  preregistration, checker offers, oldest-first ordering, and lease expiry without naming a trusted
  or monotonic clock (`:338-343,459-474,509-516`).
- **Why it matters to the goal:** [confirmed] A stale worker and a resumed worker can each produce a
  valid-looking stage from different inputs or code. SQLite serializes their individual writes; it
  does not by itself prevent the stale owner from writing after the new owner.
- **Evidence checked:** [confirmed] I checked every lease field and state transition in v8 and
  searched for fencing, generations, monotonic clocks, wall-clock skew, and clock correction; none
  is specified. [unknown] An implementation could add such checks, but they are not part of the
  finished design being attacked.
- **Concrete failure scenario:** [assumed] macOS time jumps forward, `launchd` expires a healthy
  five-hour model stage, and worker B resumes it. Worker A later finishes and acquires SQLite's
  single-writer lock after B. Both are serial database writers, but one is a stale run owner. A
  backward clock correction can likewise make a panel registered after work began appear earlier
  than the recorded first builder change.

### 2.4 Resume is not explicitly bound to the original input snapshot

- **What is wrong:** [confirmed] The final manifest must hash audio, decoded audio, grid, phrase,
  frames, stems, models, cache, and config (`spectral_program_operating_model_v8_2026_08_02.md:425-438`).
  The resume contract says only that the lease stores the last complete content-hashed stage and a
  resume token (`:509-516`). It does not say resume rechecks every original input hash before using
  that stage, or that the input snapshot is immutable before the final seal.
- **Why it matters to the goal:** [confirmed] The library lives on paths and removable media. A
  recovery that combines an old frame stage with remounted or replaced audio can produce a
  self-consistent final manifest for a mixed run while pointing at the wrong musical identity.
- **Evidence checked:** [confirmed] I checked the manifest, `reproduce`, lease, and resume clauses.
  `reproduce` is explicitly bundle-only (`:440-441`); `resume` has no equivalent input-binding
  sentence. [unknown] Existing per-stage hashes may be sufficient in a future implementation, but
  the design does not state the comparison that would make them sufficient.
- **Concrete failure scenario:** [assumed] A worker completes model frames for an audio file on a
  USB path and dies. The volume is remounted with a changed file at the same path. Resume trusts the
  completed frame token, computes later phrase/proof stages from the new bytes, and seals a hybrid
  run that cannot be honestly reproduced from either version alone.

## Pass 3 — the music itself

### 3.1 The fail-closed proof can faithfully enforce the wrong structural boundary

- **What is wrong:** [confirmed] V8 requires a laser start at or after the governing drop and the
  entire interval inside its drop section (`spectral_program_operating_model_v8_2026_08_02.md:237-250`).
  Current evidence contains the exact counterexample: for New Sky at 3:32.8, the operator's mark is
  beat 447, the section starts at 448, the frozen finder gives the mark `p=0.9746`, and its frozen
  16-beat length exactly matches his 16. It is refused solely because the section clock puts the
  mark one beat into the runway (`local/spectral_v5_2026_07_17/TEACH15_report.md:85-98`; the open
  conflict is also recorded at `PROGRAM_STATE_2026_07_31.md:62`).
- **Why it matters to the goal:** [confirmed] The goal is to locate the musical event and let the
  laser ride its real length. Integrity checks on a wrong section boundary turn a strong exact
  musical hit into `LAW_VIOLATION`. This attack does not dispute the no-buildup law; it disputes the
  unproved assumption that the phrase/drop substrate classifies the boundary correctly.
- **Evidence checked:** [confirmed] I checked TEACH15's sealed finding, the open program-state row,
  and v8's proof. The 34 development marks also include two labelled `in_build`, one at a -1-beat
  offset and one at -16 beats from the governing drop, so New Sky is not the only current mark whose
  context challenges a hard section boundary.
- **Concrete failure scenario:** [assumed] Across a bootleg with a pickup transient just before the
  downbeat, the grid or section detector places the drop one beat late. The sound recognizer locates
  the operator's event and length exactly. The proof rejects it, the full laser output is withheld,
  and the refusal is operationally honest but musically wrong.

### 3.2 The developed evidence is narrow in class, context, duration, codec, and coverage

- **What is wrong:** [confirmed] `COMBINED1_dev_run_manifest.json:1-12` has 31 tracks and 34 marks.
  Reading all rows yields 25 `growl`, 4 untyped, 4 `sustain`, and 1 `synth`; 25 marks are `at_drop`,
  7 `in_section`, and 2 `in_build`. No row is labelled stab, vocal accent, pause, repeated figure, or
  whole-drop accent. The dev audio formats are 19 WAV, 8 MP3, 3 FLAC, and 1 AIFF. The 721-track
  census also contains 9 M4A and 2 AIF tracks, neither represented in dev.
- **Why it matters to the goal:** [confirmed] The requirement is general recognition of any named
  sound across all tracks, not reproduction of the dominant growl examples
  (`spectral_program_failure_dossier_2026_08_02.md:229-244`). A class-separated evaluator cannot
  demonstrate classes for which it has no labelled rows.
- **Evidence checked:** [confirmed] I parsed the complete dev manifest and the complete
  `sweep_tracks_resolved.json`. The 721-track duration range is 59.2–590.4 seconds, with a median of
  229.1 seconds. [assumed] Duration estimated from the dev sealed grids spans about 186.6–422.2
  seconds; 194 of 721 tracks, 26.9%, lie outside that envelope. Only 34 track directories currently
  have the three-model/four-stem COMBINED1 frame material: 4.7% of the census.
- **Concrete failure scenario:** [assumed] A short M4A edit contains a vocal stab and a silent
  interruption that warrants a laser. All current model selection and duration behavior was chosen
  against longer, mostly WAV/MP3, mostly growl-at-drop examples. The command either refuses on
  codec/structure or produces an unvalidated sound-class guess; no current evidence distinguishes
  those outcomes.

### 3.3 The all-or-nothing list makes the least available lane control the whole product

- **What is wrong:** [confirmed] `listen` publishes only when all four lanes finish and withholds the
  entire list if any lane is incomplete (`spectral_program_operating_model_v8_2026_08_02.md:93-124`).
  Current track energy and drop energy remain open, accents is designed but unimplemented, and the
  laser lane needs phrase/drop evidence (`:86-91`). The 721-row sweep artifact contains only audio
  identity, duration, grid id, and beat times; zero rows contain phrase segments, true drops, or
  section maps.
- **Why it matters to the goal:** [confirmed] Even after three lanes can answer a track, one missing
  phrase map or one unimplemented sound class suppresses all useful output from the one-command
  surface. The refusal is visible rather than silent, but a visible refusal still does not locate a
  laser moment or deliver the energy/accent information the operator asked for.
- **Evidence checked:** [confirmed] I checked the full-list contract, lane dependency table, current
  status admissions, all 721 sweep rows, and the adoption census language. [unknown] The end-to-end
  refusal rate is explicitly unmeasured in v8 (`:252-253,637-645`). Nothing on disk currently shows
  that sufficient structural evidence exists for most of the library.
- **Concrete failure scenario:** [assumed] Track energy, drop energy, and accents complete for 600
  tracks, but phrase proof is absent on 400. Every one of those 400 full-list requests returns no
  list at all. The system can report perfect refusal accounting while serving less than half the
  library.

### 3.4 Adoption can measure cost on 30–50 convenient tracks without testing musical breadth

- **What is wrong:** [confirmed] Adoption step 9 measures one cached track, one unseen readable
  track, one refusal, and one 30–50-track batch, but asks only for time and storage and forbids
  projection (`spectral_program_operating_model_v8_2026_08_02.md:610-611`). The comparison panel is
  also a human choice that may use earlier exploratory knowledge, and v8 accepts that it may be
  convenient (`:338-358`). No adoption step requires the batch to cover codecs, durations, genres,
  phrase shapes, sound classes, true-drop counts, or difficult/refused cases.
- **Why it matters to the goal:** [confirmed] The current 34-mark slice is already narrow. A cost
  batch selected from nearby cached or known-good tracks can make the operating model look usable
  without testing the musical population it exists to serve.
- **Evidence checked:** [confirmed] I checked the preregistration limits, adoption steps, the full
  census composition, and every dev label. [unknown] The actual selection intended for the 30–50
  batch is not named, so representativeness cannot be evaluated in advance.
- **Concrete failure scenario:** [assumed] The batch is drawn from WAV/MP3 tracks close to the dev
  duration and growl-heavy genres because those are ready. Time and storage are reported honestly,
  the slice passes, and the later first M4A vocal-stab or ten-minute multi-drop track exposes a new
  decoder, memory, or hearing failure after the machinery is adopted.

## Pass 4 — economics: quota, wall clock, and disk

### 4.1 The measured representation does not fit this disk at library scale

- **What is wrong:** [confirmed] At review time, `du -sk` measured `local/` at 34,617,336 KiB
  (reported by `du -sh` as 33 GiB), versus the dossier's earlier 32 GB/87,008-file snapshot
  (`spectral_program_failure_dossier_2026_08_02.md:16-27`). `find local -type f` now counts 124,154
  files. The data volume has about 18,626,836 KiB free. `COMBINED1_frames` alone is 10,981,732 KiB,
  or 10.47 GiB, for 34 tracks.
- **Why it matters to the goal:** [confirmed] V8 retains evidence, published results, decision
  records, and reproduction bytes, and stops at `STORAGE_LIMIT_REACHED` rather than removing them
  (`spectral_program_operating_model_v8_2026_08_02.md:551-555`). That is honest preservation, but
  the current machine lacks the capacity to apply the measured representation to 721 tracks.
- **Evidence checked:** [confirmed] I measured the current filesystem, the full 721-track census,
  and the 34-track frame directory. [assumed] Linear capacity checks—not performance claims—put the
  same frame footprint at about 9.24 GiB for 30 tracks, 15.40 GiB for 50, and 222.09 GiB for 721.
  Track duration and refusal make the real number non-linear, but no plausible correction closes a
  roughly 204-GiB gap between the estimate and free space.
- **Concrete failure scenario:** [assumed] Adoption's 50-track unseen batch creates roughly 15.4 GiB
  of COMBINED1-style frames, leaving only a few GiB for temporary stems, SQLite backups, and model
  work. The run either pauses at the protected-byte limit or fills the disk before demonstrating
  even 7% of the library.

### 4.2 The recorded wall time is days before retries, checker work, or the other lanes

- **What is wrong:** [confirmed] The first 34-track stems/frame batch took 286.2 minutes and ended
  with 26 complete and 8 refused after separation succeeded but stem decoding failed
  (`local/spectral_v5_2026_07_17/PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:56-64`). A later narrow
  retry reached the 34-track artifact set, but the retry cost is not recorded in the cited batch
  line. The separate 721-track raw feature sweep measured a median 89.7 seconds per track and a
  frozen serial comparand of 24.91 hours per 1,000 tracks
  (`local/spectral_v5_2026_07_17/sweep_report.md:26-36`). V8 also records prior large model stages at
  about 5.5–5.7 hours per model (`spectral_program_operating_model_v8_2026_08_02.md:126-133`).
- **Why it matters to the goal:** [confirmed] The operator asked for one command against a track and
  expected prior scans to be reused (`spectral_program_failure_dossier_2026_08_02.md:242-244`). A
  governed command that needs days of preprocessing and then waits for a second provider family is
  not an operational library tool even if every ten-minute line is truthful.
- **Evidence checked:** [confirmed] I checked the trail, COMBINED1 ledger, sweep report, current
  artifact counts, and v8's checker rerun contract. [assumed] The first-pass rate alone scales to
  about 101.2 hours for 721 requested tracks; the raw-feature median comparand adds about 18 hours.
  [unknown] Retry cost, other-lane cost, and how much expensive work a clean independent checker can
  reuse are not measured, so the full wall time is higher but not honestly quantifiable.
- **Concrete failure scenario:** [assumed] A library build runs for four days at the observed
  first-pass rate, encounters the same 23.5% first-pass stem-read refusal class on part of the
  corpus, then queues a clean checker rerun. The operator has progress lines but still has no full
  list for the tracks he wants to play.

### 4.3 The required two-family publication path already fails against real provider quotas

- **What is wrong:** [confirmed] V8 requires builder and checker to differ in session, model family,
  and provider family; otherwise a full result remains `WAITING_FOR_CHECKER`
  (`spectral_program_operating_model_v8_2026_08_02.md:443-457`). The actual program record says all
  three Sol seats were quota-dead until August 5 at 17:23 and all reviews had moved to Claude seats
  (`local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md:706-722`). A Fable design seat was also
  already at 76% of its window (`:1115-1116`). Earlier, the operator stated he was on a Max x20 plan
  and did not want work rationed, yet the program subsequently reached those family walls
  (`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:4615-4621`).
- **Why it matters to the goal:** [confirmed] The degraded path permits only an unchecked development
  sheet, never the full four-lane list or a comparison. The real quota event therefore turns the
  sanctioned product surface off for days, irrespective of local compute or disk availability.
- **Evidence checked:** [confirmed] I checked the current quota records, v8's provider-separation
  rule, dispatcher behavior, and v8's own admission that local code cannot measure provider
  allowance or reserve hearing capacity (`spectral_program_operating_model_v8_2026_08_02.md:616-628`).
  [unknown] Dollar spend and token use are not recoverable from the inspected artifacts, so monetary
  affordability cannot be claimed either way.
- **Concrete failure scenario:** [assumed] Anthropic builds a full list while every eligible OpenAI
  checker is quota-dead. The dispatcher correctly records the failed acquisition. The operator gets
  no full list until the quota window resets, even though the local run is complete and he is paying
  for the highest plan he described.

### 4.4 Permanent reproduction has no specified deduplication economics

- **What is wrong:** [confirmed] V8 says derived artifacts use content hashes and reproduction bytes
  are retained, but does not state whether identical model, environment, frame, and evidence bytes
  are stored once or copied into every run bundle (`spectral_program_operating_model_v8_2026_08_02.md:425-441,551-555`).
  The current tree already contains 6.5 GiB of model files, including both a 1.333-GB MuQ PyTorch
  file and a 1.333-GB MuQ safetensors file, plus separate 1.32-GB MERT and two 1.32-GB MusicFM
  checkpoints. Three environments separately carry the same 337,911,904-byte
  `libtorch_cpu.dylib`.
- **Why it matters to the goal:** [confirmed] Hashing detects identity but does not itself save a
  byte. If “retained bundle” means physical copies, permanent reproducibility multiplies the
  largest fixed assets per run and makes the already impossible disk budget worse. If it means
  shared references, deletion and archive behavior depend on reference lifetime that v8 does not
  define.
- **Evidence checked:** [confirmed] I measured `r4_stage_b_v1/models` at 6,838,252 KiB and the three
  Python environments at about 1.16, 1.02, and 1.01 GiB. I checked every storage/reproduction clause
  in v8. [unknown] The eventual bundle's copy/reference granularity is not specified, so per-run
  permanent cost cannot be computed from the finished design.
- **Concrete failure scenario:** [assumed] Each published run preserves clean model and environment
  bytes to satisfy bundle-only reproduction. Two or three runs duplicate several GiB of fixed assets
  before adding track frames, crossing `STORAGE_LIMIT_REACHED` even though all hashes are correct.

## Combined worst finding

[confirmed] The combined worst finding is a governed refusal machine that cannot afford to test its
own generality. The system's strictest promises—complete bundles, permanent reproduction bytes,
clean independent reruns, two provider families, fail-closed phrase/drop proof, and an all-four-lane
list—multiply exactly the resources and prerequisites that are scarce on the current workstation.
Only 34 of 721 tracks have the large frame representation; that slice already uses 10.47 GiB, the
disk has about 18 GiB free, the first pass took 286.2 minutes with 8 of 34 refused, and the current
musical evidence is mostly growl-at-drop. [assumed] The likely terminal behavior is not a false
`READY`; it is `STORAGE_LIMIT_REACHED`, `WAITING_FOR_CHECKER`, `DROP_PROOF_MISSING`, or
`LANE_INCOMPLETE` across much of the library. That is more honest than the failed program, but it
still does not satisfy the goal of locating laser-worthy moments across the operator's music.

## Is this worth building?

[assumed] Not end to end in its present form. The custody, sealed-run, explicit-refusal, and
independent-checking ideas address real failures and are individually valuable. But the finished v8
design asks the operator to pay for a large governance system before it has shown broad musical
hearing, and the measured disk, time, corpus, and provider evidence says the complete system does not
fit the resources presently available. [unknown] It may become worth building after different
evidence demonstrates that a representative library slice can be heard, stored, rerun, and checked
within the real quota and disk envelope; that evidence is not on disk today.
