# Spectral program operating model v8 (2026-08-02)

**Status:** design proposal — `planned`, not adopted, nothing implemented. This revision answers
`ROUND_7_sol.md` and supersedes
`docs/plans/active/spectral_program_operating_model_v7_2026_08_02.md`. It does not authorize code,
a run, a blind test, a bridge restart, or live wiring.

**Claim labels:** **[confirmed]** means the named current file or code was read; **[assumed]** means
this document chooses a build contract that does not exist yet; **[unknown]** means the required
measurement or evidence does not exist yet.

[confirmed] The goal does not change: one per-track list must carry laser moments, track energy,
drop energy, and accented moments, with positions and lengths where they apply, and the operator's
ear decides whether it passes
(`docs/plans/active/spectral_program_failure_dossier_2026_08_02.md:59-68,229-246`).

[confirmed] The repo remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**. This is an
offline research operating model. It has no authority over the running bridge, SoundSwitch,
lasers, LEDs/Govee, Rekordbox, config, or hardware.

---

## 1. Evidence is useful only inside its real boundary

[confirmed] Outside Lowkey, the operator marked examples rather than every valid moment on each
track. An unmatched machine row is therefore unjudged, not wrong
(`local/spectral_v5_2026_07_17/KNOWNSCORE_scorecard.md:9`,
`local/spectral_v5_2026_07_17/DEVGRADE1_scorecard.md:20-22`,
`local/spectral_v5_2026_07_17/PROBE13_report.md:17-19`).

[assumed] There is no one-number referee. Evidence has three shapes:

1. **Released example.** The operator marked one or more moments but did not certify the rest of
   the track. The evaluator may show how output differs from those marks. Every other output is
   unjudged.
2. **Exposed complete scope.** The operator certified every valid moment for one named lane and
   sound class over one track, and the rows are available to the program. Only in that exact scope
   may an unmatched row be called extra or wrong. Because builders can know the rows, this is a
   regression example, not evidence of general hearing.
3. **Fresh blind.** The worker output is sealed before the operator reveals any answer for that
   track. Only the first presentation is cold. Later attempts are corrections.

[assumed] Every evaluation body opens with exactly one fixed evidence-scope line matching the
evidence shape it used:

- `RELEASED EXAMPLES — unmatched output is unjudged, not wrong`
- `EXPOSED COMPLETE REGRESSION — not a blind result`
- `FRESH BLIND — first presentation`

The §3 printer refuses an evaluation body whose evidence-scope line is missing or does not match
the evidence shape recorded in that run's manifest. The label is enforced by the printer and
sender, not by a seat remembering it.

[confirmed] Lowkey is an **exposed complete scope**, not a protectable hidden key. Its seven exact
timestamps and seven-beat lengths are printed in the current failure dossier at lines 97-98, in
`LOWKEY1_scorecard.md:3-18`, and in many worker-readable program files. Moving a copy behind access
control cannot make those already published rows secret. `DEVSPLIT_2026_08_01.md:38-49` also calls
it program-exposed.

[assumed] Lowkey may catch a change to known behavior. It may not be described as held out,
builder-inaccessible, cold, or proof of generalization. A builder can fit to it, so every Lowkey
evaluation carries the `EXPOSED COMPLETE REGRESSION` scope line above, under the same printer
refusal.

[assumed] A future key cannot be both a permanently hidden test and a diagnostic tool queried
forever. While a fresh key is hidden, it lives in the blind evaluator account described in §7 and
returns no row-level differences before the first operator presentation. Once its timestamps,
lengths, cell differences, or other answer-reconstructing details are released to builders, it is
reclassified as exposed complete scope. Access control may protect future keys before release; it
cannot unpublish an old one.

[assumed] Development evidence may expose a regression or a changed trade. It cannot certify
general hearing. Only a first-run future track chosen and judged by the operator can add fresh
generalization evidence.

---

## 2. One full-list door and one honest development door

[assumed] The full-list command is:

```text
python3 -m tools.spectral_listen listen --track "<library title or readable audio path>"
```

[confirmed] This module and command do not exist today. The nearest current runner requires a
manifest row, an unambiguous governing drop, a frame container, a sealed grid, and readable audio,
and skips a track when one is missing
(`local/spectral_v5_2026_07_17/combined1_runner.py:1127-1175`). Track energy and drop energy are
open rows, and accented moments is designed but not implemented
(`local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md:48-61`).

[assumed] `listen` has only two public shapes:

- **`READY`** — all four lanes finished, every output rule passed, a complete run record received a
  sealed run id, and an independent checker approved the exact list. The full list is pasted in
  chat.
- **No list** — `REFUSED`, `WAITING_FOR_CHECKER`, or `INTERNAL_FAILURE`. One plain sentence names
  the first block and then any other blocks. A refusal is counted; it is never a skipped track or a
  partial success.

[assumed] The fixed refusal reasons are:

| Code | What the operator sees |
|---|---|
| `TRACK_NOT_FOUND` | "I cannot read that track from its current location." |
| `TRACK_AMBIGUOUS` | "That name resolves to more than one track; no analysis ran." |
| `AUDIO_UNREADABLE` | "The track is present, but this audio format could not be decoded." |
| `LANE_INPUT_MISSING` | "The named list part is missing these required inputs: <names>." |
| `DROP_PROOF_MISSING` | "The program cannot prove where the true drop begins, so it will not print laser moments." |
| `LANE_INCOMPLETE` | "At least one of the four required list parts is unavailable, so there is no full list." |
| `LAW_VIOLATION` | "A proposed row broke an operator rule, so the output was withheld." |
| `EVIDENCE_NOT_RECONCILED` | "A recent recorded operator message has not been resolved, so no result can be published." |
| `WAITING_FOR_CHECKER` | "The run finished, but no registered eligible checker has accepted it since <time>." |
| `INTERNAL_FAILURE` | "The run failed unexpectedly; no partial result was published." |

[assumed] Every refusal exits nonzero and writes a small run record containing the requested
track, completed stages, missing stages, and exact error. Batch headers always state
`requested / ready / refused`, followed by every refusal reason.

[assumed] If readable audio is missing analysis material, `listen` builds the material that has a
defined builder. A missing lane implementation returns `LANE_INCOMPLETE`. An unmounted audio path
returns `TRACK_NOT_FOUND`, never an old cached identity. Ambiguous drop evidence returns
`DROP_PROOF_MISSING`, never a guess. No time promise is made before measurement.

[assumed] Long work cannot disappear into a multi-hour stage. The wrapper sends the first plain
line before work starts, one line at every stage completion, and a deterministic progress line at
least every ten minutes while a stage remains active. The ten-minute line is emitted by the local
wrapper without a model call and states the stage, elapsed time, last completed checkpoint, and a
real completed/total count when one exists. If no internal count exists it says that plainly. A
dead process becomes `RECOVERY_NEEDED` and is announced by the same ten-minute deadline. Prior
large runs took about 5.5-5.7 hours per model, so stage-only updates are not sufficient
(`local/spectral_v5_2026_07_17/archive_probe_ladder/RBPALL5_report.md:102-110`).

[assumed] Single-lane work uses:

```text
python3 -m tools.spectral_listen develop --lane <laser|track_energy|drop_energy|accents> --track "<track>"
```

[assumed] `develop` shares resolver, decoded-audio identity, run records, lane printer, evidence
checks, independent checking, and sender with `listen`. It does **not** inherit irrelevant lane
gates. `LANE_INCOMPLETE` for another lane can never refuse a `develop` run.

[assumed] The initial dependency contract is:

| Lane | Required before output | Must not block this lane |
|---|---|---|
| laser | readable decoded audio; sealed matching grid; required model/frame inputs; §4 phrase and drop proof | track-energy, drop-energy, or accent implementation |
| track energy | readable decoded audio; the declared track-energy descriptor inputs | phrase data, a drop boundary, laser frames, or any other lane |
| drop energy | readable decoded audio; sealed matching grid; unambiguous drop/section identity; declared drop-energy inputs | laser buildup proof, accent implementation, or track-energy output |
| accents | readable decoded audio; sealed matching grid; the accent implementation's declared inputs | laser buildup proof or either energy lane |

[assumed] Before a lane implementation is accepted, its exact input names and builders replace the
generic `declared inputs` cell in code and tests. A missing selected-lane input returns
`LANE_INPUT_MISSING`, names every missing input, and says whether each is buildable now. It never
silently borrows the full-list prerequisites.

[assumed] A development sheet always begins
`Development output — <lane> only. Not the acceptance list.` It uses the same row shape as the
full list for that lane. The header cannot be removed by the sender.

[assumed] The sanctioned sender accepts exactly three governed result body types — a full list, a
development sheet, and an evaluation report — and each only with a sealed run id and a body whose
hash matches that run's stored output. It is state-aware:

- a full list or evaluation report requires `VERIFIED`; a successful send moves the run to
  `PUBLISHED`;
- a checked development sheet requires `VERIFIED`; a successful send moves the run to `PUBLISHED`;
- an unchecked development sheet requires `WAITING_FOR_CHECKER`, the stored checker-wait start,
  the §8 dispatcher-owned completed acquisition round, and the mandatory unchecked line. Its
  delivery is stored, but the run remains `WAITING_FOR_CHECKER`.

Anything without a sealed run id, in the wrong state, with a wrong hash, or with a missing or wrong
mandatory first line for its type is rejected. It rejects side-script output. A seat can still
paste arbitrary text into chat; that is an accepted limit, not a solved enforcement problem.

---

## 3. The list contract

[confirmed] The current detailed design is
`local/spectral_v5_2026_07_17/acceptance_list_format_v3.md`, SHA-256
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910`. It is design-only and does
not prove operator acceptance or four implemented lanes
(`local/spectral_v5_2026_07_17/acceptance_list_format_v3.md:1-6,830-904`).

[assumed] The minimum operator-facing shape is:

```text
<library track title>
Track energy: <whole-track value and library position>

Drops, biggest to smallest: <timestamp list>

<m:ss.t>  Laser: <plain action>; starts <m:ss.t>, lasts <beats>, ends <m:ss.t>.
           Heard by: <model names>. Why: <plain evidence sentence>.

<m:ss.t>  Accent: <plain lighting action>; starts <m:ss.t>, lasts <beats>, ends <m:ss.t>.
           Heard by: <model names or "rule-based">. Why: <plain evidence sentence>.

No unmentioned moment is approved; it is unjudged unless an exposed complete scope says otherwise.
```

[assumed] A lane refusal never appears inside this body. If any lane refuses or is incomplete, §2's
no-list path is the entire operator response. A present refusal string cannot satisfy the printer's
four-lane completeness check.

[assumed] A development sheet renders only its selected lane under the mandatory development
header. Drop-energy rows carry timestamp, start, beat length, and end. Track energy says
`whole track`; it does not invent a timestamp. Every moment row carries lane, sealed-grid beat,
rendered start, beat length, rendered end, plain behavior, evidence source, and model attribution.
A moment with no length cannot render. Internal scores, ranks, hashes, and diagnostic names never
appear in operator chat.

[assumed] An evaluation report renders under its mandatory §1 evidence-scope first line. Evaluation
reports cannot use §8's unchecked path.

[assumed] Rows merge only when they share lane and class and their beat intervals overlap or touch.
The merged start is earliest, end is latest, model names are the sorted union, and source row ids
remain in the run record. A real gap never merges. Different lanes stay separate.

[assumed] The printer refuses its whole requested output when a required field is absent, two
lanes render the same beat differently, a full list lacks a lane, a development sheet contains an
unnamed lane, an evaluation body's evidence-scope line is missing or does not match the manifest's
recorded evidence shape, a required unchecked line is missing, or a row contradicts its evidence
record. It never repairs, trims, or silently drops an invalid row.

---

## 4. Laser buildup proof fails closed

[confirmed] `smart_phrasing.py:782-797` is not a safe laser proof. If sparse or absent phrase data
would remove every smart drop, `select_true_drops` returns all smart drops unchanged. Missing
phrase data also yields zero runway (`smart_phrasing.py:714-739`).

[assumed] The offline laser builder never uses `select_true_drops` as its safety decision. For
every proposed laser row it must:

1. Require a sealed beat grid matching the decoded audio.
2. Require non-empty phrase segments covering the row and an unambiguous drop section.
3. Require exactly one governing drop boundary.
4. Require `runway_beats(governing_drop, phrase_segments) > 0`.
5. Require the laser start at or after the governing drop boundary.
6. Require the whole interval inside that drop section and outside every buildup or breakdown.
7. Store the grid id, phrase hash, governing drop beat, runway, section bounds, and row bounds.

[assumed] Any failure returns `DROP_PROOF_MISSING` or `LAW_VIOLATION` and withholds the full laser
output. It never restores smart drops, substitutes zero runway, trims a row, skips the track, or
crashes. A test built from the current fail-open case must prove absent phrase data refuses.

[unknown] The share of the library with sufficient phrase evidence is not measured. §12 separates
ready, buildable, refused, and unknown tracks rather than pretending missing material is refusal.

---

## 5. Evidence capture shows both use and non-use

[confirmed] A row count and last-added date cannot prove that operator judgments were captured.
The old program lost judgments while its paperwork appeared current
(`docs/plans/active/spectral_program_failure_dossier_2026_08_02.md:110-183`).

[assumed] One Python-standard-library SQLite database stores operational evidence and work state:

- `inbound_message`: unique source, source position, received time, exact text, and text hash;
- `disposition`: exactly one of `evidence`, `no_evidence`, `duplicate`, or `conflict` per message;
- `judgment`: released mark, exposed complete scope, veto, description, ruling, or blind verdict,
  linked to the exact message;
- `supersession`: a new judgment correcting an old one; old rows are never edited or deleted;
- `evidence_use`: one or more public use rows per active judgment per run — `compared`,
  `compiled_check`, `analysis_input`, `human_only`, or `not_applicable` — with a reason;
  `not_applicable` is exclusive, while the other classes may overlap;
- `run`, `experiment`, and `lease`: the stored work state in §§8-10.

[assumed] The operator-facing intake wrapper commits each exact inbound message before delivering
it to a model. A failed commit is announced immediately and blocks publication. Only sessions
behind this wrapper may claim complete capture. Whether the operator's actual chat surface can sit
behind such a wrapper is unmeasured; if it cannot, §5's capture claims degrade to the
last-recorded header tell alone, and that must be said the day it is discovered.

[assumed] Every published result states the time and first words of the last operator message on
record. This can expose a gap only when a later governed result is published and the operator
recognizes the stale line. It does not guarantee detection within a day and does not recover the
missing message.

[assumed] Every captured message through the latest id must have one disposition before
publication. The header states `messages captured / resolved / unresolved`; any unresolved message
returns `EVIDENCE_NOT_RECONCILED`.

[assumed] The public evidence-use line includes **all** classes:

```text
Your recorded judgments: N total, all N accounted for — A compared,
B enforced as checks, C used as analysis input, D human-only,
E not applicable; M were used in more than one way.
```

[assumed] The union of the five classes must contain exactly all `N` active judgments, or
publication stops. The class counts may exceed `N` only because non-`not_applicable` uses can
overlap, and `M` makes that overlap visible. `not_applicable` can no longer hide outside the public
accounting. A large `human-only` or `not applicable` count is visible in chat; the correctness of
those classifications remains human judgment.

[assumed] For `analysis_input`, the checker withholds or changes the converted input and confirms
the named code path receives a different hash. This proves delivery to that path, not semantic
understanding, and the public wording says `used as analysis input`, not `understood`.

[assumed] SQLite uses foreign keys, `synchronous=FULL`, one writer, transactions, unique replay
keys, and triggers rejecting update/delete of messages and judgments. Startup runs
`PRAGMA integrity_check`. After each committed message, the SQLite backup API writes and checks a
temporary backup before replacing a rotating backup. Two checked backups remain. Recovery restores
the newest checked backup, replays later uniquely identified source messages, and reports what is
still missing.

[assumed] An ordinary session on the same chat surface can bypass the wrapper. No database can
observe a message it never received. The last-recorded header is only a tell on the next governed
publish, and an unwrapped seat warning the operator is a remembered duty. This is an accepted
limit.

---

## 6. Evaluation describes differences; it does not invent progress

[confirmed] A legacy offline command named `python3 -m tools.spectral_pilot score` exists at
`tools/spectral_pilot/__main__.py:463-473`; it is not the proposed operating-model evaluator and its
output is not a sanctioned §2 result body. [assumed] The proposed `tools.spectral_listen` interface
has no `score` subcommand and no combined ordering. Its command is:

```text
python3 -m tools.spectral_listen evaluate --baseline <run-id> --candidate <run-id> --evidence released
```

[assumed] An evaluation is itself a run: it writes a manifest and run record like any other run,
and its chat body reaches the operator only through the §2 sender, bound to its sealed run id and
body hash, under its §1 evidence-scope first line. An invented number or comparison pasted in
free prose has no run id and no scope line; those missing tells are what expose it.

[assumed] An experiment registers its evaluation panel before its builder work begins: ordered
track identities, audio hashes, selected lanes/classes, evidence snapshot, substrate hashes, and
required refusal rows, with the registration time stored in the experiment row. `evaluate` refuses
comparative output unless baseline and candidate manifests both match one panel whose registration
time precedes the candidate's first builder change. A missing, added, substituted, or newly
refused track returns `NOT_COMPARABLE`; membership cannot change inside that comparison. With no
such preregistered panel, `evaluate` prints each run as a single-run description labelled
`NO PREREGISTERED PANEL — differences not assessed`.

[assumed] Even with a preregistered panel, `evaluate` never emits `improved`, `progress`, `better`,
or a positive verdict. It may emit the automatic regression floor below and otherwise describes
the row differences. Panel membership is still a human choice. A worker may choose a convenient
panel using earlier exploratory knowledge and then register it before the formal candidate change;
no timestamp can erase that knowledge. The report prints every panel track and says
`PANEL CHOSEN BY <identity> — not evidence of library-wide improvement`. This is an accepted limit,
not a solved anti-gaming mechanism.

[assumed] The baseline is a human choice of the same kind. The report prints the baseline and
candidate run identities and `BASELINE CHOSEN BY <identity>`. A deliberately old or weak baseline
has few paired rows, so the automatic regression floor below protects little in that comparison;
printing who chose it makes the choice visible, not wise. This is an accepted limit.

[assumed] Evaluation is separate by lane and sound class. Only typed spans participate in time
matching. Descriptions and rulings appear in evidence-use, never in a number.

[assumed] Matching is one-to-one on the same sealed grid. The pairing maximizes total overlap;
ties break by smallest total start difference, then length difference, earlier machine start, then
stable row id. One machine span can pair with at most one human span.

[assumed] Each released mark prints `paired`, `not overlapped`, or `not evaluated`. A paired row
shows the human start and length first, then machine start and length, start difference, length
difference, and overlap. `exact` means identical rendered start tenth and beat length. There is no
within-a-beat bucket.

[assumed] On a partial key, unmatched machine rows are `unjudged output`. On an exposed complete
scope only, missed human rows and unmatched machine rows in that exact lane/class may be called
missed and extra. No cells are collapsed into one number.

[assumed] A baseline `paired` row becoming `not overlapped` or `not evaluated`, or a baseline-ready
track refusing on the identical panel, is an automatic regression floor. Start drift, length
change, or shrinking overlap stays visible but is not an automatic verdict because no authorized
tolerance exists. A 513-beat span may pair with one mark, but its 513-beat length and difference
must print; `paired` is never rendered as `pass`, `match`, or progress. Degenerate output can remain
musically wrong until the operator vetoes it. That is an accepted limit, not a hidden score.

[assumed] Chat uses one plain line per mark, his mark first. Batch output begins with the sentence
answering the question, then every requested track, every refusal, all denominators, the evidence
snapshot, and the complete evidence-use counts. No glyph grids or internal column names appear.

---

## 7. Development cannot certify itself; fresh blind custody is one-way

[assumed] Released marks and exposed complete scopes are teacher material. Workers may use them,
and every use is recorded. Movement is a development change, never a cold result or proof of
general hearing.

[assumed] Analysis receives decoded audio, timing material, and approved model artifacts through
meaningless temporary names. It receives no library title, path, answer database, or blind-key
store. Renaming and relocating identical audio must leave list rows byte-identical.

[assumed] The checker reviews every changed file on resolution, decoding, grids, caches, model
loading, candidate creation, each selected lane, buildup proof, refusal, rendering, and evidence
intake. It scans changed source/config for track ids, titles, known timestamps, and answer lookups.
This blocks obvious hardcoding; it cannot prove a model did not recognize audio identity.

[assumed] A future blind key lives under a separate operating-system account or machine whose key
directory is not mounted in the worker or builder environment. A negative test must prove the
worker cannot list or read it. The first worker output is sealed before the operator's answer enters
that store. If separation fails, the result is `NOT BLIND`.

[assumed] The first presentation is the cold attempt. Up to two later corrected attempts may be
shown under the existing three-attempt limit, labelled corrections. A fourth graded attempt is
rejected before key access. Once diagnostic key details are released, that key becomes exposed
complete regression evidence and can never be called blind again.

---

## 8. Exact run records and independent checking

[assumed] The program has replaceable duties: front desk captures and sends; builder changes the
offline analyzer; independent checker tries to disprove the exact run. A replacement uses stored
duty and run id rather than reconstructing from chat.

[assumed] Every run writes to a temporary directory. Nothing is publishable until the directory
contains a complete manifest and one all-or-nothing rename assigns its run id.

[assumed] The manifest hashes or identifies every byte needed to explain and reproduce the result:

- source commit and dirty patch;
- exact command, run type, lane, and arguments;
- Python, operating system, and dependency lock;
- evidence snapshot or blind packet hash held outside the worker;
- requested track identity, audio hash, and decoded-audio hash;
- grid, phrase, frame, stem, model, cache, and config hashes;
- resolver, decoder, analyzer, lane, proof, printer, evaluator, and sender versions;
- requested/ready/refused counts and every refusal reason;
- output, evidence-use, timings, peak storage, builder, and checker identities;
- the evidence shape used and, for a comparison, the preregistered panel id;
- whether the body was shown unchecked before verification and, when it was, the dispatcher-owned
  acquisition request id, eligible-checker registry hash, per-adapter outcomes, and queue lease.

[assumed] `reproduce --run <id>` uses only the retained bundle. Missing or changed bytes cause a
named refusal, never a comparison presented as identical input.

[assumed] The checker works from a clean copy with only manifest-allowed inputs. It reruns the
bundle, reads every changed path file, and injects wrong identity, missing audio, selected-lane
missing input, absent phrase data for lasers, corrupted cache, unresolved evidence, blind-key
access, and process death. Repetition proves repeatability only; musical truth remains the
operator's blind judgment.

[assumed] Builder and checker cannot share session, model family, or provider family for one
publish decision. At least two provider families are required before adoption. Otherwise the run
stays `WAITING_FOR_CHECKER`.

[assumed] Checker unavailability has one labelled degraded path, so quota walls do not push work
back to side scripts. While a run is `WAITING_FOR_CHECKER`, a **development sheet only** — never a
full list and never a comparative claim — may be shown through the sender with the line
`UNCHECKED — no registered eligible checker accepted request <request-id> since <time>` directly
under its development header.

[assumed] The checker dispatcher, not the builder or front desk, owns acquisition records. For each
request it snapshots the registered checker adapters and their provider/model families, filters out
every adapter ineligible under the builder/checker separation rule, and offers the exact run to
every remaining adapter. An adapter fails that acquisition round only by returning an explicit
decline/quota error or by not accepting within ten minutes. The dispatcher stores the registry and
config hash, offer time, and outcome for every eligible adapter in one transaction. The sender
accepts the unchecked state only when that completed round was created after the run entered
`WAITING_FOR_CHECKER`; a caller-created, incomplete, earlier, or reused round is rejected. Each
unchecked send requires a new completed round. This proves what the registered dispatcher tried; it
does not prove that every possible provider or manually started seat was unavailable.

[assumed] Delivered-unchecked runs form one global checker backlog across all builders. The
dispatcher may lease a checker only the oldest delivered-unchecked run still in
`WAITING_FOR_CHECKER`; it rejects a lease for any newer governed run until that oldest run leaves
the backlog. Delivery time then stable run id break ties. The selection and lease are one
transaction, so rotating builder identity cannot jump the queue. The run stays
`WAITING_FOR_CHECKER`, its delivery is stored, and the §4 proof, §3 printer, run record, and
hash-bound sender all still applied to it. Nothing can force a check while no registered eligible
checker accepts work; that boundary stays visible because each further unchecked sheet carries its
own since-time and request id.

[assumed] When a checker later returns `CHECK_FAILED` on a shown sheet, the checker transaction also
creates a pending correction. Before accepting any newer governed body, the sender automatically
posts `CORRECTION — unchecked development sheet <run-id> failed independent check: <plain reason>.
Do not use it.` and stores the delivery time. The block clears only after that exact notice is
delivered. If chat is unavailable, the correction and every newer governed result wait; a seat
cannot clear the block by acknowledging it in free prose. The correction is a fixed control notice,
not a fourth result body. An unchecked sheet can still be wrong in ways the checker would have
caught; the label and later correction are visibility, not prevention.

---

## 9. Work state survives a dead seat

[assumed] Stored analysis states are:

```text
QUEUED -> PREPARING -> RUNNING -> WAITING_FOR_CHECKER -> VERIFIED -> PUBLISHED
                       |                    |
                       +-> REFUSED          +-> CHECK_FAILED
                       +-> RECOVERY_NEEDED
```

[assumed] Delivery is recorded separately from analysis state. A verified body reaches
`PUBLISHED` only after the sender records successful delivery. The sole exception is an unchecked
development sheet: its delivery row is recorded while its analysis state remains
`WAITING_FOR_CHECKER`. No other body can be delivered from that state. This separation prevents a
delivered unchecked sheet from pretending to be verified and prevents `PUBLISHED`-only sender
logic from making the degraded path unusable.

[assumed] SQLite owns the single writer and temporary run lease. A lease stores owner, stage,
expiry, last complete content-hashed stage, and resume token. Temporary writes plus one rename
prevent half a public result. Concurrent writers are rejected.

[assumed] A local `launchd` job checks active leases without a model call or heartbeat prompt. On
expiry it sets `RECOVERY_NEEDED`, records the last complete stage, and posts a plain local notice.
The next worker uses `resume --run <id>`. The ten-minute progress rule in §2 reports the expired
lease at the operator surface when that surface is available.

[assumed] Provider loss cannot erase captured input or completed state. Total chat-provider loss
still prevents chat; stored state and a local notice are the honest boundary. No recovery-time
claim is made before kill, reboot, quota, and resume drills.

---

## 10. Work stops for evidence, not a fake number

[assumed] Each experiment stores its question, allowed files, executable falsifier, preregistered
evaluation panel, maximum compute/storage spend, and allowed evidence. An unrunnable falsifier is
rejected before work. A budget caps cost; it is not a scientific verdict.

[assumed] Work is rejected only when the stated falsifier fires, the identical-panel regression
floor in §6 fires, a compiled law breaks, data isolation fails, or the operator refutes it. Budget
exhaustion changes state to `paused — budget used`, not `failed`.

[assumed] A worker cannot swap tracks, omit refusals, or change evidence/substrate inside a
registered comparison and call it comparable, because §6 checks the panel against both manifests.
A worker can still choose a convenient initial panel, a weak but runnable falsifier, or a weak
baseline. The report names the panel and baseline choosers and every track, emits no positive
verdict, and the budget limits the cost; none of that makes the choices representative or wise.

[assumed] The operator goal cannot be closed, weakened, or renamed by an experiment. The front desk
chooses which paused idea gets the next slot; that is recorded judgment, not arithmetic.

---

## 11. Fewer papers without fewer checks

[assumed] Operational state lives in SQLite and run records. Experiments do not write progress
essays or one-off state files. A build wrapper grants writes only to named code files and a
temporary run directory. Publication refuses unexpected prose, loose output, or out-of-scope edits.

[assumed] Derived artifacts use content hashes and a required byte limit. Adoption blocks with
`STORAGE_LIMIT_UNSET` until high-water use and one end-to-end run are measured. Regenerable scratch
is removed oldest first. Evidence, blind packets, published lists, decision-bearing records, and
reproduction bytes are never silently removed. Protected bytes reaching the limit cause
`STORAGE_LIMIT_REACHED` until space is added or an archive is verified.

[assumed] The sender requires the actual body, a sealed run id, a matching output hash, the §2
state allowed for that body, and the correct mandatory first lines for its type: the full-list
shape, the development header (plus the unchecked line when §8 applies), or the evaluation
evidence-scope line. It rejects path-only replies, internal diagnostics, and any body type it does
not recognize. An outstanding failed-unchecked correction blocks every newer governed body until
the fixed notice is delivered. The sender cannot prove free prose is relevant or natural; that
remains an accepted limit.

---

## 12. Adoption order — a complete visible slice before more machinery

[confirmed] v3 placed the proof and printer first but did not activate the run-id sender until step
3, so its step-1 claim that no bad sheet could reach the operator had no enforcing path
(`spectral_program_operating_model_v3_2026_08_02.md:538-548`).

[assumed] Existing safeguards stay authoritative until each replacement passes. The order is:

1. **One governed laser development slice.** Build `develop --lane laser` around the current
   offline runner with §4 proof, §3 printer, a minimal §8 run record, independent checking, the
   development header, checker dispatcher, and the run-id/hash sender **as one switch**. Test
   missing phrase data, a buildup row, a row crossing section end, missing length, clock mismatch,
   wrong lane, wrong body hash, a lane refusal placed inside a full-list body, no checker, an
   unchecked sheet missing its unchecked line, an unchecked sheet accepted from
   `WAITING_FOR_CHECKER`, a caller-created acquisition row, a round made before the wait state, a
   round omitting an eligible adapter, reuse of a completed round for a second send, a full list or
   evaluation attempted from that state, delivery without a sealed run id, `CHECK_FAILED` after an
   unchecked delivery, a failed correction delivery, and a newer result attempted before
   correction. With an older unchecked run from builder A, a checker request for a newer run from
   builder B must be refused and the older run leased first. Do not claim the operator surface is
   governed until the dispatcher and sender are active.
2. **Evaluator and preregistered comparison panel.** Build §6. Test partial-key unjudged output,
   exposed complete extras, one-to-one long rows, deterministic ties, duplicate rows, refusals,
   descriptions, changed track selection, changed audio identity, the regression floor, a missing
   or mismatched evidence-scope line, a comparison attempted without a preregistered panel, and a
   positive-verdict word attempted in generated evaluation output.
3. **Other development lanes, one at a time.** Add track energy, drop energy, and accents using the
   §2 dependency matrix. Prove that missing laser phrase data cannot refuse track energy and that
   an unbuilt other lane cannot refuse any selected-lane development run.
4. **Library prerequisite census.** Use the same resolver and decoder probe as the command, then
   report four buckets for every library row: `ready now`, `build required` with named stages,
   `refused now` with a terminal reason, and `unknown until full run`. Missing grid or frames are
   not called refused when the command promises to build them. Do not say a track "can print laser
   rows" unless an exact checked laser development run did so. This is a substrate census, not the
   still-unknown end-to-end refusal rate.
5. **Intake wrapper and evidence database.** Import known sources, reconcile all captured messages,
   and prove duplicate, conflict, corruption, backup, recovery, all-class counts, and capture-gap
   headers.
6. **Leases, resume, storage limits, and reproduce.** Kill before and after every state change;
   reboot; corrupt a working copy; simulate provider outage; prove deterministic recovery.
7. **Fresh-blind custody.** Build §7 for future keys. Do not pretend moving Lowkey makes it hidden.
8. **`listen`.** Wire all four lanes. Until then it returns `LANE_INCOMPLETE`; development remains
   available through the governed lane paths.
9. **Measure, then say.** Measure one cached track, one unseen readable track, one refusal, and one
   30-50 track batch. Report time and storage without projection.
10. **Shadow, then switch.** Keep current checks authoritative until a non-author verifies each
    replacement and its failure tests. Archive old state. Only the operator may initiate or accept
    a fresh blind presentation and approve the final switch.

[assumed] Adoption work has its own recorded quota and may not consume the last available hearing
slot. What a machine can enforce there is narrow, and this design claims only that part. After §5
exists, the stored priority rule is mechanical for governed runs: the launcher never grants an
adoption-purpose lease while a hearing-purpose run request is waiting for one. That refusal
reaches only work that asks the launcher for a lease. Most adoption spend never does: the seats
that design, build, review, and check this machinery use provider allowance in ordinary sessions
the launcher never sees; the adoption-versus-hearing label on any lease is declared by whoever
requests it; and no local code can measure how much provider allowance remains for anyone. So the
reservation over what actually starved hearing work in the recorded program — seat and reviewer
allowance — is a duty held by whoever dispatches seats, before **and** after the build. If seat
dispatch is ever routed through dispatch tooling, that tooling can consult the stored rule; this
design does not claim it does. Neither ordering, quota rows, nor the launcher guarantees hearing
progress or hearing capacity.

[assumed] Even after the sender exists, a person can hand-paste ungoverned text. The honest claim is
that the sanctioned surface is governed, not that arbitrary typing is impossible.

---

## 13. What remains uncertain or cannot be designed away

[unknown] The hearing problem is unsolved. No operating model guarantees the four lanes will pass
the operator's ear.

[unknown] End-to-end time, quota, storage, and actual library refusal rate are unmeasured because
the commands do not exist. The prerequisite census separates what it knows from what needs a full
run.

[unknown] A fresh track may expose a new sound class, codec, or missing timing substrate. The
contract refuses with an exact reason rather than promising arbitrary-input success.

[unknown] Whether the operator's actual chat surface can be placed behind a commit-before-model
wrapper is unproven. If it cannot, capture is a header tell, not a mechanism, and §5 must say so
the day that is discovered.

[assumed] Lowkey is already exposed and can be overfit. It remains a useful known regression
example but cannot validate generalization.

[assumed] An unwrapped session can lose a judgment. The last-recorded header may expose the gap on
the next publish; nothing guarantees detection within a day or capture of the missing words.

[assumed] A seat can hand-paste ungoverned output. Missing run id, scope lines, and headers are
tells, not a physical block on typing.

[assumed] A development sheet shown unchecked during checker unavailability can be wrong in ways
the checker would have caught. The mandatory unchecked line, the dispatcher-owned acquisition
round, the stored delivery, the global oldest-first backlog, and the sender's automatic correction
block on a later `CHECK_FAILED` make that visible and prevent newer governed work from jumping a
known unchecked backlog; they do not prevent the original error. The dispatcher proves only that
its registered eligible adapters did not accept. It cannot see unregistered provider capacity or
force a checker to exist, and total chat loss delays both the correction and every newer governed
result.

[assumed] The reserved hearing slot is machine-enforced only as lease-queue priority over governed
runs. Seat dispatch, the honesty of the adoption-versus-hearing label, and provider allowance sit
outside every enforcement point this design has. Protecting hearing capacity from adoption spend
is a human duty; this design says so plainly instead of calling it solved.

[assumed] Exact evidence and decision-bearing run bundles grow for the program's life. Scratch is
bounded; permanent evidence is not.

[assumed] Free prose, `human_only`/`not_applicable` classification, falsifier quality, panel
membership choice, baseline choice, and slot choice still require judgment. Recording and exposing
those choices does not make them correct.

[assumed] Preregistration cannot prove a panel was chosen without knowledge from earlier
exploratory runs. It freezes membership only for the named comparison. The chooser line and ban on
generated positive verdicts make the limitation visible; they do not make the panel representative.

[assumed] The evaluator can expose a wildly long paired span but cannot declare a musical length
wrong without an operator ruling or compiled law. The visible difference and budget bound the
failure; they do not cure hearing.

---

## 14. The short operator version

[assumed] If this is built, you name a track. You get either the complete four-part list in chat or
one plain reason there is no list. While lanes are still being built, you can request one lane; it
uses only that lane's real prerequisites and always says it is development output.

[assumed] A long run reports at least every ten minutes without spending a model call. Every result
states the last message of yours it recorded and accounts for every judgment, including those
classified not applicable. A comparison never reaches you unless both runs used the same tracks
pinned before the named work started. A swap inside that comparison is refused, but the original
panel and the baseline it is measured against can still be convenient choices, and every report
says who chose them; the evaluator never calls a change progress or improvement. If the independent
checker is unavailable, a one-lane development sheet can still reach you, but only after the
dispatcher offered that exact run to every registered eligible checker and none accepted. It names
the request, always says it is unchecked, and the oldest unchecked sheet across every builder gets
the next checker before newer work. That proves what the registered dispatcher tried, not that
unused provider capacity does not exist; a later failed check is corrected by name.

[assumed] The rule that building this machinery must never crowd out hearing work is enforced by
the machine only where the machine hands out the work: its own run queue puts hearing first. What
the seats themselves spend while designing and reviewing this machinery is something the machine
cannot see or ration, so that protection stays a duty people owe you — said plainly here instead
of being called solved.

[assumed] Lowkey stays a known exposed regression track — every Lowkey evaluation says so on its
first line. A future track you choose and hear cold is the only new evidence that the machine
generalized. Your ear remains the acceptance gate.
