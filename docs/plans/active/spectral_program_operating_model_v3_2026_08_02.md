# Spectral program operating model v3 (2026-08-02)

**Status:** design proposal — `planned`, not adopted, nothing implemented. This revision answers
`ROUND_2_fable.md` and supersedes
`docs/plans/active/spectral_program_operating_model_v2_2026_08_02.md`. It does not authorize code,
a run, a blind test, a bridge restart, or live wiring.

**Claim labels:** **[confirmed]** means the named current file or code says it; **[assumed]** means
this document is choosing a build contract that has not been built; **[unknown]** means the program
does not yet have the measurement or evidence.

[confirmed] The goal and the operator's acceptance gate do not change: one per-track list must
carry laser moments, track energy, drop energy, and accented moments, with positions and lengths
where they apply, and the operator's ear decides whether it passes
(`docs/plans/active/spectral_program_failure_dossier_2026_08_02.md:59-68,229-246`).

[confirmed] The accepted repo status also does not change: **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**. This is an offline research operating model. It has no authority over the
running bridge, SoundSwitch, lasers, LEDs/Govee, Rekordbox, config, or hardware.

---

## 1. The correction this design makes

[confirmed] v1 failed because it called outputs outside a partial human key "invented" and then
made that invalid count the program's only referee. Outside the complete Lowkey growl key, the
operator recorded examples, not every valid moment in each track. An unmatched machine row is
therefore unjudged, not wrong
(`local/spectral_v5_2026_07_17/KNOWNSCORE_scorecard.md:9`,
`local/spectral_v5_2026_07_17/DEVGRADE1_scorecard.md:20-22`,
`local/spectral_v5_2026_07_17/PROBE13_report.md:17-19`).

[assumed] There is no one-number referee. Three kinds of evidence are kept separate and one never
pretends to be another:

1. **Released example:** the operator marked one or more moments, but did not certify the rest of
   that track. The program may report how its rows differ from those marks. Every other output is
   **unjudged**.
2. **Complete scope:** the operator explicitly certified that, for one named lane and one named
   sound class, every valid moment over the whole track is listed. Only inside that exact scope may
   an unmatched output be called extra or wrong. Completeness never spreads from "growl" to every
   possible laser moment.
3. **Fresh blind:** the worker's output is sealed before the operator reveals any answer for that
   track. The first presentation is cold. Later corrections may be checked, but they are not called
   cold again.

[confirmed] Lowkey's whole-track key is complete for its seven growls, but it is already
program-exposed and cannot prove fresh generalization
(`local/spectral_v5_2026_07_17/DEVSPLIT_2026_08_01.md:38-49`). I Cannot has distributed existing
keys, Palm has no sealed timestamped key on disk, and only a future track the operator springs can
still provide a genuinely fresh blind check at present
(`local/spectral_v5_2026_07_17/DEVSPLIT_2026_08_01.md:42-49`).

[assumed] **Complete-scope keys get the same custody as blind keys.** v2 called Lowkey "released"
while also ordering that it never become worker training material, and gave those two rules no
separating mechanism. v3 removes the ambiguity: the row-level content of any complete-scope key
(Lowkey today, any future one) lives only in the evaluator-side custody store described in §7,
outside the worker and builder environment. Builders and workers never read its rows — not "reads
are recorded," but reads are denied the same way blind-key reads are denied, with the same negative
test. What comes back to the development side is the evaluator's cell output only: paired /
not overlapped / unjudged, with differences. A regression on Lowkey is therefore something the
program can detect forever, because no builder can quietly fit code to the only complete key the
program owns.

[assumed] Development evidence can reject a regression. It cannot certify general hearing. A
generalization claim requires a first-run fresh blind result chosen and judged by the operator. If
he supplies only a veto or one example, that becomes a released example; it does not silently
become a complete key.

---

## 2. The operator sees one of two honest shapes — and the same machinery governs development

[assumed] The front door is exactly:

```text
python3 -m tools.spectral_listen listen --track "<library title or readable audio path>"
```

[confirmed] That module and command do not exist today. The nearest current runner requires a
manifest row, an unambiguous governing drop, a frame container, a sealed grid, and readable audio;
it skips a track when one is missing
(`local/spectral_v5_2026_07_17/combined1_runner.py:1127-1175`). Track energy and drop energy are
open rows, and accented moments has a ready design but no implementation
(`local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md:48-61`).

[assumed] `listen` has only two public shapes:

- **`READY`** — all four lanes finished, every output rule passed, an exact run record was saved,
  and an independent checker approved the exact list. The complete list is pasted in chat.
- **No list** — the state is `REFUSED`, `WAITING_FOR_CHECKER`, or `INTERNAL_FAILURE`. One plain
  sentence names the first blocking fact, followed by the other missing facts if more than one
  exists. A refusal is a result, never a skipped track and never a partial success.

[assumed] The fixed refusal reasons are:

| Code | What the operator sees |
|---|---|
| `TRACK_NOT_FOUND` | "I cannot read that track from its current location." |
| `TRACK_AMBIGUOUS` | "That name resolves to more than one track; no analysis ran." |
| `AUDIO_UNREADABLE` | "The track is present, but this audio format could not be decoded." |
| `GRID_MISSING_OR_INVALID` | "The track's timing map is missing or does not match the audio." |
| `FRAMES_MISSING_OR_INVALID` | "The analysis frames are missing or do not match the audio." |
| `DROP_PROOF_MISSING` | "The program cannot prove where the true drop begins, so it will not print laser moments." |
| `LANE_INCOMPLETE` | "At least one of the four required list parts is not available, so there is no list." |
| `LAW_VIOLATION` | "A proposed row broke an operator rule, so the whole list was withheld." |
| `EVIDENCE_NOT_RECONCILED` | "A recent operator message has not been recorded yet, so no result can be published." |
| `WAITING_FOR_CHECKER` | "The run finished, but an independent check is not available yet." |
| `INTERNAL_FAILURE` | "The run failed unexpectedly; no partial result was published." |

[assumed] All refusals exit nonzero and create a small run record with the requested track,
completed stages, missing stages, and the exact error. No refused track disappears from a count.
For a batch, the header always says `requested / ready / refused`, followed by every refusal reason.

[assumed] If the audio is readable but analysis material is missing, this same command builds the
missing grid, frames, and lane data. If the audio is on an unmounted stick, it returns
`TRACK_NOT_FOUND`; it never claims an old cache is the requested track. If drop evidence is
ambiguous, it returns `DROP_PROOF_MISSING`; it never guesses. No time promise is made until the
finished command has been measured.

[assumed] **The long path is never silent.** When `listen` must build missing material, its first
chat reply arrives before any long work starts and says, in plain words, what exists and what is
being built ("I have the audio; I am building the timing map and analysis frames; I will report
when each finishes"). Every completed build stage — the same stages the run record stores —
produces one short line. Silence longer than a stage is a defect, not a style choice. Prior big
runs took hours, not minutes, so this is not cosmetic
(`local/spectral_v5_2026_07_17/archive_probe_ladder/RBPALL5_report.md:102-110`).

[assumed] **The development door.** Until all four lanes exist, `listen` returns `LANE_INCOMPLETE`
and no acceptance list. But the program still has to build and judge single lanes for months, and
v2 left that work outside its own machinery — which would have meant every interim laser sheet was
produced by ungoverned side scripts. v3 closes that hole with a second run type on the same
command:

```text
python3 -m tools.spectral_listen develop --lane <laser|track_energy|drop_energy|accents> --track "<track>"
```

- It uses the **same** resolver, decoder, sealed grid, buildup proof, printer, run record,
  evaluator, and checker as `listen`. There is no other sanctioned way to produce lane output.
- Its output header is fixed: `Development output — <lane> only. Not the acceptance list.` It can
  never render without that header, and the sender never strips it.
- Everything that refuses in `listen` refuses identically here. A laser development row inside a
  buildup is withheld by the same proof.
- These runs are what `evaluate` (§6) scores during development. A refusal-only program with
  nothing evaluable, which is what v2's adoption order produced, cannot happen.

[assumed] **The sender only sends governed output.** Any list or lane sheet delivered to the
operator must carry the run id of a published run record, and the sender verifies the body against
that record's stored output hash before sending. A sheet produced by a side script has no run id
and cannot be sent. A seat pasting raw text into chat by hand remains possible — no design can
stop a person-shaped process from typing — so that residue is named in §13 instead of being
claimed away.

---

## 3. The list contract

[confirmed] The current detailed list design is
`local/spectral_v5_2026_07_17/acceptance_list_format_v3.md`, SHA-256
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910`. It is itself design-only,
not proof that the operator accepted or that all four lanes exist
(`local/spectral_v5_2026_07_17/acceptance_list_format_v3.md:1-6,830-904`).

[assumed] v3 adopts its core view and pins the minimum operator-facing fields here so the build does
not depend on an unnamed "accepted format":

```text
<library track title>
Track energy: <whole-track value and library position, or an explicit refusal>

Drops, biggest to smallest: <timestamp list, or an explicit refusal>

<m:ss.t>  Laser: <plain action>; starts <m:ss.t>, lasts <beats>, ends <m:ss.t>.
           Heard by: <model names>. Why: <plain evidence sentence>.

<m:ss.t>  Accent: <plain lighting action>; starts <m:ss.t>, lasts <beats>, ends <m:ss.t>.
           Heard by: <model names or "rule-based">. Why: <plain evidence sentence>.

No unmentioned moment is approved; it is unjudged unless a complete scope says otherwise.
```

[assumed] A development sheet (§2) renders its single lane in exactly this row format under its
mandatory development header. Drop-energy rows use the same `m:ss.t`, start, length, and end
fields. Track energy is a whole-track property and says `whole track` instead of inventing a
timestamp. All moment rows are in time order. Every row carries its lane, start beat on the sealed
grid, rendered start, length in beats, rendered end, plain behavior, evidence source, and model
attribution. A moment with no length cannot render. Internal scores, confidence values, candidate
ranks, hashes, and diagnostic names do not appear in operator chat.

[assumed] Seconds-apart duplicates merge only when they are from the same lane and class and their
beat intervals overlap or touch. The merged start is the earliest start, the end is the latest end,
model names are the sorted union, and the source row ids remain in the run record. Rows with a real
gap do not merge. Two different lanes may share a timestamp and remain separate.

[assumed] The printer refuses the whole list when any required field is absent, any two lanes render
the same beat to different time text, any lane is missing (for `listen`) or is not the named lane
(for `develop`), or any row contradicts the data named in its evidence record. It never repairs,
trims, or silently drops an invalid row.

---

## 4. The buildup rule fails closed

[confirmed] Current `smart_phrasing.py:782-797` is not proof of a true drop. When phrase data is
sparse or absent and every smart drop would be rejected, `select_true_drops` returns all smart drops
unchanged. Missing phrase data also produces a zero runway (`smart_phrasing.py:714-739`).

[assumed] The offline list builder must not use `select_true_drops` as its laser safety decision. It
uses a separate proof with these exact steps:

1. Require a sealed beat grid that matches the decoded audio.
2. Require non-empty phrase segments covering the proposed row and an unambiguous drop section.
3. Require exactly one governing drop boundary for the row.
4. Require `runway_beats(governing_drop, phrase_segments) > 0`.
5. Require the laser start to be at or after that governing drop boundary.
6. Require the entire laser interval to stay inside the governing drop section and to overlap no
   phrase segment labelled buildup or breakdown.
7. Save the grid id, phrase-data hash, governing drop beat, runway beats, section bounds, and row
   bounds in the run record.

[assumed] A failure at any step returns `DROP_PROOF_MISSING` or `LAW_VIOLATION` and withholds the
whole list. It does not restore smart drops, substitute a zero runway, trim the laser, skip the
track, or crash. A test built from the current fail-open case must prove that absent phrase data
refuses the list.

[unknown] How much of the 700–800-track library has phrase evidence good enough to pass step 2 is
unmeasured. The runtime fail-open exists precisely because sparse phrase data is common, so the
honest refusal rate may be large. §12 requires measuring it before adoption instead of discovering
it one refusal at a time.

---

## 5. Evidence capture that can show what was lost

[confirmed] Row count and last-added date cannot prove that every operator judgment was recorded.
They can look current while most messages are missing. v1 had no expected message count, unique
message id, conflict rule, transaction, backup, or recovery path.

[assumed] v3 uses one small SQLite database from Python's standard library. SQLite makes a group of
related writes succeed together or not happen at all. It is operational data, not a prose memory
file. It has these tables:

- `inbound_message`: unique source, source position, received time, exact text, and text hash.
- `disposition`: exactly one state for every inbound message — `evidence`, `no_evidence`,
  `duplicate`, or `conflict` — plus the deciding event and time.
- `judgment`: one or more typed rows linked to the exact inbound message: released mark, complete
  scope, veto, description, ruling, or blind verdict.
- `supersession`: a new judgment id that corrects an old one. Old rows are never edited or deleted.
- `evidence_use`: for each published run and judgment, one of `compared`, `compiled_check`,
  `analysis_input`, `human_only`, or `not_applicable`, with a reason. `analysis_input` also records
  the exact converted input hash and the code that received it.
- `run`, `experiment`, and `lease`: the current work state described below.

[assumed] The only allowed operator-facing session is behind an intake wrapper. The wrapper commits
the exact inbound message before delivering it to the model. If the commit fails, it does not hide
that fact: it tells the operator the message was not saved and blocks publication until recovery.
An operating model without this wrapper is not this design and may not claim complete capture.

[assumed] **The capture gap announces itself in chat.** Every published list, sheet, or evaluation
carries one header line the operator can check with his own memory: the time and first words of the
last operator message the program has on record ("Last thing I have recorded from you:
<time> — '<first few words>'"). If he said something important more recently than that line shows,
he can see the hole the moment the output arrives, instead of six weeks later. This turns silent
omission into a visible gap at the one surface he reads. It does not capture the missed message —
it exposes that one is missing.

[assumed] Before any list or evaluation is published, every captured message through the latest
message id must have one disposition. The public header says `messages captured / resolved /
unresolved`, not merely a row count and date. Any unresolved message returns
`EVIDENCE_NOT_RECONCILED`.

[assumed] The checker changes or withholds each row marked `analysis_input` and confirms that the
recorded input hash changes. If it does not, the receipt is false and publication stops. This proves
the row reached the named input path; it does not pretend the machine understood the words
correctly.

[assumed] **Evidence use is summarized where he can see it.** The same public header states, in one
line, how his recorded judgments are being used: "Your recorded judgments: N total — X compared
against output, Y enforced as checks, Z used as analysis input, W human-only." A program that has
quietly classified most of his corpus as `human_only` — the shape of the day it used six of his 54
judgments — shows that fact in chat on every publish, without him opening anything.

[assumed] SQLite runs with foreign keys enabled, `synchronous=FULL`, one writer, and all-or-nothing
transactions. Unique source-position and message-hash rules make replay safe. Updates and deletes
on inbound messages and judgments are rejected by database triggers. Corrections append a
superseding row. Conflicting active judgments block evaluation until a later ruling resolves them.

[assumed] Startup runs `PRAGMA integrity_check`. After each committed operator message, the database
backup API writes a temporary backup, checks it, and replaces the older rotating backup in one
step. Two last-known-good backups remain. On corruption, the wrapper refuses publication, restores
the newest checked backup, replays any later source messages by their unique ids, and reports how
many messages were recovered or remain unavailable.

[assumed] The wrapper can guarantee capture only for messages that pass through it. The most likely
uncaptured path is not a different app: it is an ordinary session on the same chat surface that was
started without the wrapper — which is how every session runs today. A session without the wrapper
must say so when the operator gives it a judgment ("I have no way to record that here — it does not
count as recorded evidence"), but that sentence is itself a remembered duty for a session the
wrapper does not control. This is an accepted limit, stated here instead of hidden: the mechanical
protections are the header lines above, which make the gap visible at publish time; they cannot
make an unwrapped session capture anything. Messages in a different app, an old unavailable
transcript, or spoken aloud remain outside reach the same way.

---

## 6. What an evaluation may and may not say

[assumed] There is no `score` command and no single combined ordering. The exact evaluator command
is:

```text
python3 -m tools.spectral_listen evaluate --run <run-id> --evidence released
```

It accepts both `listen` runs and `develop` runs; a development evaluation carries the same
mandatory development header as the sheet it scores.

[assumed] Evaluation happens separately for each lane and sound class. Only typed time-span marks
participate in time matching. Descriptions and rulings appear in the evidence-use receipt; they are
never converted into a number merely to make them scoreable.

[assumed] Matching is one-to-one. Human and machine spans become intervals that include their start
but stop just before their end, all on the same sealed timing map. The evaluator chooses the pairing
with the largest total overlap. Ties break by the smallest total absolute start difference, then
smallest total length difference, then earlier machine start, then stable row id. A machine row can
cover at most one human row. A 513-beat row can therefore never claim four human marks.

[assumed] For every released example the evaluator prints one of:

- `paired`, with start difference in tenths, length difference in beats, and overlap shown;
- `not overlapped`, when no machine interval overlaps the human interval; or
- `not evaluated`, with the refusal reason.

[assumed] `exact` means the rendered start tenth and beat length are both identical. There is no
"within a beat" bucket and no invented tolerance. On a partial key, unmatched machine rows are
printed as `unjudged output`; they do not count for or against the approach.

[assumed] On an explicitly complete scope only, the evaluator may additionally print missed human
rows and unmatched machine rows inside that same lane and class. It still prints the cells
separately. It does not turn them into one number or decide that one trade is better.

[assumed] **"Breaks a released example" has exactly one meaning.** v2 rejected approaches that
"break an existing released example" without defining "break" in the evaluator's own vocabulary,
which quietly reopened the judgment the removed one-number referee used to hide. The mechanical
definition is: with the same inputs, a released example that was `paired` under the current
approved baseline becomes `not overlapped` or `not evaluated`, or a track that was `READY` under
the baseline now refuses. That, and only that, is an automatic regression. Any other movement —
a start drifting by tenths, a length changing, an overlap shrinking — is printed as a difference
for judgment, never an automatic verdict in either direction, because calling it one would invent
a threshold.

[assumed] **Chat rendering of an evaluation is plain.** One line per released example, his mark
first: `Your 3:10.0 growl x8 — machine 3:10.4, 8 beats, paired`. No grids of symbols, no internal
column names. A batch evaluation leads with the sentence that answers the question asked, then the
lines.

[assumed] Every report includes all requested tracks, all refused tracks, every denominator, the
evidence snapshot id, and an evidence-use receipt. A description marked `human_only` is visibly not
being used by the analyzer — and the §5 header line counts it in chat. Any active judgment with no
receipt entry blocks publication.

---

## 7. Development work cannot certify itself

[assumed] Released development marks are teacher material. A worker may use them, and every use is
recorded. Movement on them is called a development change, never a cold result, a pass, or proof of
general hearing.

[assumed] **Complete-scope keys are not teacher material and are physically out of reach.** The
row-level content of every complete-scope key (Lowkey today) lives in the same custody store as
blind keys: a separate operating-system account or machine whose key directory is not mounted in
the worker or builder environment, with a mandatory negative test proving the worker cannot list or
read it. The development side receives only evaluator cells and differences. There is no "recorded
read" path for builders — a read is denied, not logged. If this separation is unavailable, any
result touching that key is labelled `KEY EXPOSED` and cannot support a regression claim.

[assumed] The analysis process receives decoded audio, the sealed timing map, and approved model
artifacts through meaningless temporary names. It receives no library title, path,
development-answer database, or exam-key store. Running identical audio under a different filename
and path must produce byte-identical list rows. A failure blocks publication.

[assumed] The independent checker reviews every changed analysis and data-path file, not only the
printer and evaluator. That includes track resolution, decoding, grid creation, cache choice, model
loading, candidate creation, lane assembly, refusals, rendering, and evidence intake. The checker
also scans changed source and config for track ids, titles, known timestamps, and answer lookups.
This does not prove a clever system cannot recognize a track from its audio; it prevents a
development result from being mistaken for generalization.

[assumed] Only the first sealed output on a future operator-chosen track can add fresh
generalization evidence. The blind key is not copied into the repo, development database, run
workspace, model prompt, or worker-visible filesystem. The worker gets no per-row key before its
output is sealed.

[assumed] Blind evaluation runs in that same separate account or machine. A negative test must
prove the worker cannot list or read the key directory. If that separation is unavailable, the run
is labelled `NOT BLIND` and cannot support a generalization claim. File naming, instructions, and
an exposure ledger alone are not access control.

[assumed] The first presentation is recorded as the cold attempt. Up to two later corrected
attempts may be shown under the existing three-attempt limit, but they are labelled corrections.
A fourth graded attempt is rejected in the custody database before the key is read. Lowkey and
other complete keys remain regression material behind custody, never reusable cold exams.

---

## 8. Exact run records and independent checking

[assumed] The program has three duties, not three irreplaceable sessions: the front desk captures
the operator's words and sends the final list; the builder changes the offline analyzer; the
independent checker tries to disprove the exact run. A replacement session takes the stored duty
and run id rather than reconstructing work from chat.

[assumed] Every run — `listen` and `develop` alike — writes its output into a temporary directory.
Nothing becomes publishable until the directory contains a complete run record and one
all-or-nothing rename gives it its run id.

[assumed] This run record, called the manifest, names and hashes every byte needed to explain or
reproduce the result:

- source commit and any dirty patch;
- exact command and arguments, including run type and lane;
- Python, operating-system, and dependency-lock versions;
- development-evidence snapshot id, or custody-store packet hash held outside the worker workspace;
- requested library identity, source audio hash, and decoded-audio hash;
- beat-grid, phrase, frame, stem, model, cache, and config hashes;
- resolver, decoder, analyzer, each lane, buildup proof, printer, and evaluator versions;
- requested, ready, and refused track counts with every refusal reason;
- operator-list hash, evidence-use receipt hash, timings, and peak storage;
- builder identity and checker identity, model family, provider family, and report hash.

[assumed] `reproduce --run <id>` uses only the retained manifest bundle. If any byte is absent or
different, it refuses and names the missing item; it never compares the new output to history as if
the inputs were the same.

[assumed] The checker works from a clean copy with only the manifest's allowed inputs. The check has
three parts: re-run the exact bundle; inspect every changed file on the complete `listen`/`develop`
path; and run failure tests for wrong identity, missing audio, missing lane, absent phrase data,
corrupted cache, unresolved evidence, key access, and process death. Repeating the same result
proves repeatability only. Musical truth still comes from the operator's blind judgment.

[assumed] Builder and checker may not be the same session, model family, or provider family for the
same publish decision. At least two provider families must be configured before adoption. If an
independent checker is unavailable, the run stays `WAITING_FOR_CHECKER`; it is never published as
checked.

---

## 9. Work state survives a dead seat

[assumed] A run has one of these stored states:

```text
QUEUED -> PREPARING -> RUNNING -> WAITING_FOR_CHECKER -> VERIFIED -> PUBLISHED
                       |                    |
                       +-> REFUSED          +-> CHECK_FAILED
                       +-> RECOVERY_NEEDED
```

[assumed] SQLite owns the single writer and the run lease, which is a temporary ownership record. A
lease records owner, stage, expiry, last complete stage stored under the hash of its contents, and
resume token. Work artifacts are written to temporary paths and published by one all-or-nothing
rename. A dead process can leave only a complete previous stage or an ignored temporary path, not
half a public result.

[assumed] A small local `launchd` job checks only active leases. It makes no model call and sends no
heartbeat prompt. On expiry it sets `RECOVERY_NEEDED`, records the last complete stage, and places a
plain local notice. The next worker runs `resume --run <id>` and starts from that stage. Concurrent
writers are rejected by the database lock and run lease.

[assumed] A front-desk session is a replaceable client of the same intake and run database; it is
not the sole owner of truth. If its provider dies, inbound capture and completed run state remain.
If all chat providers are unavailable, the system cannot talk in chat; the local notice and stored
state are the honest boundary. No time-to-recovery claim is made until kill, reboot, quota, and
resume drills are measured.

---

## 10. Work stops for evidence, not for a fake number

[assumed] An experiment starts with one database row: the question, files allowed to change,
technical falsifier, maximum compute/storage spend, and the evidence it may inspect. The resource
cap limits cost; it is not a verdict on the scientific idea. The falsifier must be stated as a test
the checker can actually run; a falsifier the checker cannot execute sends the row back before work
starts. A vacuous falsifier cannot protect work past its budget, because the budget pauses it
regardless.

[assumed] An approach is rejected only when its stated falsifier fires, it causes an automatic
regression as defined in §6 (a `paired` released example becoming `not overlapped` or
`not evaluated`, or a `READY` track refusing), it breaks a compiled law, it fails the
data-isolation checks, or the operator refutes it. When a cap expires without an answer, its state
is `paused — budget used`, not `failed`. A worker cannot keep favored work alive by choosing a
friendly score, and a flat development report cannot kill requirement zero.

[assumed] The fixed operator goal cannot be closed, weakened, or renamed by an experiment row. A
front desk still chooses which paused idea receives the next resource slot. That choice is judgment
and is recorded as such in the experiment row it funds; this design does not disguise it as
arithmetic.

---

## 11. Fewer papers without fewer checks

[assumed] Operational state lives in the evidence database and run records. Experiments do not
write progress essays, review chains, or one-off state files. A build wrapper gives the worker write
access only to the named code files and a temporary run directory. Publication refuses any
unexpected new prose file, loose root output, or out-of-scope edit.

[assumed] Derived artifacts live in a store that names each file by the hash of its contents and has
a required byte limit. No default is guessed: adoption is blocked with `STORAGE_LIMIT_UNSET` until
the current high-water use and one end-to-end run are measured and a limit is recorded.
Regenerable scratch data is removed oldest first. Published lists, evidence, blind packets,
decision-bearing run records, and the exact bytes needed to reproduce them are never silently
removed. If protected bytes reach the limit, new work refuses with `STORAGE_LIMIT_REACHED` until
space is added or an explicit archive is verified.

[assumed] The list sender requires the complete list body when the operator asked for a result; it
rejects a path-only reply and rejects internal diagnostic fields from operator chat. It sends only
output that carries a published run id and matches that run record's stored output hash (§2). No
mechanical check can prove that free prose understood the operator's question or sounds natural.
The independent cold-read remains, and a misunderstanding is recorded as a correction rather than
claimed impossible.

---

## 12. Adoption order — his surface first, the machine room second

[assumed] v2 ordered the build plumbing-first: intake database, then `listen`, then printer, then
evaluator, with the drill battery before first use. Under that order the operator sees nothing new
for weeks while seats build databases — the exact "rigor spent on the wrong object" shape the
failure dossier ranks second, recurring at the level of the redesign itself. v3 re-cuts the order
so every early step lands something he can touch that same week, hearing work never pauses, and
the machine room arrives behind the surface instead of in front of it.

The old operating safeguards stay in place until their replacements below pass. Adoption order:

1. **Buildup proof + pinned printer, bound to the existing runner.** Build §4 and §3 against the
   current offline path first. Test absent phrase data, a row inside a buildup, a row crossing the
   drop-section end, missing length, mismatched clocks, and a wrong lane. Every case must refuse.
   From this week on, no sheet reaching the operator can carry a buildup laser or an unattributed
   row, whatever else is still unbuilt.
2. **Evaluator (§6).** Test partial-key unmatched rows as `unjudged`, complete-scope extras,
   one-to-one long-row handling, deterministic ties, duplicate rows, refusals in the denominator,
   non-numeric descriptions, and the exact §6 regression definition. From this point, "did the
   machine match his marks" is answered by one pinned tool instead of per-seat arithmetic.
3. **`develop` runs (§2) with run records (§8).** All lane work now flows through the governed
   door and is evaluable. The sender's run-id requirement starts here.
4. **Refusal census.** Run the substrate checks (audio readable, grid, frames, phrase evidence,
   unambiguous drop) across the full library manifest — checks only, no heavy compute — and report
   in chat: "N of your ~750 tracks can currently print laser rows; the top reasons are X, Y, Z."
   The number is a fact for the operator to see, not a gate the program grades itself on. Without
   this, the honest fail-closed design could silently mean "refuses half the library" and nobody
   would know until he hit them one at a time.
5. **Intake wrapper + evidence database (§5).** Import the known evidence sources, reconcile every
   captured message to a disposition, and prove duplicate, conflict, corruption, backup, and
   recovery behavior. The capture-gap and evidence-use header lines start appearing on every
   publish.
6. **Leases, resume, storage limits, `reproduce` (§§8-9, 11).** Kill the process before and after
   every state change; reboot; corrupt a working copy; simulate a provider outage; prove the next
   state and message are deterministic.
7. **Custody store (§§1, 7).** Complete-scope and blind keys move outside the worker environment;
   the negative read test and the three-attempt rule are proven.
8. **`listen` itself (§2).** Wire the four lanes as they become real. Until all four exist it
   returns `LANE_INCOMPLETE` — but by this step that refusal is the last missing piece, not the
   whole program's front door.
9. **Measure, then say.** One cached track, one never-analyzed readable track, one refused track,
   and one 30–50 track batch. Report the measured times and storage; do not project them.
10. **Shadow, then switch.** Run beside the current process; the existing review and evidence
    checks stay authoritative until a non-author checker verifies every replacement and the failure
    tests. Retire an old safeguard only after its named replacement passes; archive old state, never
    delete it. Only the operator may initiate or accept a fresh blind presentation, and he approves
    the final switch after seeing the plain chat result.

[assumed] Lane and hearing work does not stop for any of this. Steps 1–3 exist precisely so that
work continues under governance while the rest lands behind it.

---

## 13. What remains uncertain or cannot be designed away

[unknown] The hearing problem itself remains unsolved. No operating model can guarantee the four
lanes will pass the operator's ear.

[unknown] End-to-end time, quota use, and storage for the proposed commands are unmeasured because
the commands do not exist. The surviving caches cover only part of the library; prior large runs
took hours, not minutes
(`local/spectral_v5_2026_07_17/archive_probe_ladder/RBPALL5_report.md:102-110`,
`local/spectral_v5_2026_07_17/claims1_embeddings/MANIFEST.json:898-915`).

[unknown] The library-wide refusal rate under the fail-closed buildup proof is unmeasured until
§12 step 4 runs. If it is large, the design is still honest — but the program must then decide,
with the operator, whether missing phrase evidence can be built or those tracks stay refused.

[unknown] A fresh blind track may expose a new sound class, codec, or missing timing substrate. The
cure is refusal with an exact reason, not a promise that arbitrary input always succeeds.

[assumed] An unwrapped session on the operator's own chat surface can still receive a judgment and
fail to record it. The header lines in §5 expose the gap at publish time; nothing can make an
unwrapped session capture. This is the largest accepted limit in the design.

[assumed] A seat can still hand-paste ungoverned text into chat. The sender's run-id rule blocks
the sanctioned path; it cannot stop a person-shaped process from typing. The mandatory development
header and the capture-gap line make governed output recognizable; their absence is the tell.

[assumed] Exact operator evidence and decision-bearing run bundles grow for the life of the
program. Deleting them would recreate evidence loss. Derived scratch storage is bounded and
protected-storage exhaustion blocks loudly, but the permanent evidence set does not stay small
forever.

[assumed] Free chat still requires human/model judgment. The sender can require the actual list,
the run id, and hide internal fields; it cannot prove relevance, clarity, or understanding. The
operator will see a blocked send when the mechanical shape is wrong, but he can still be the first
person to catch a meaning error.

[assumed] Front-desk slot allocation between paused experiments remains judgment. It is recorded,
visible, and bounded by budgets; it is not arithmetic, and pretending otherwise is how the invented
metric happened.

---

## 14. The short operator version

[assumed] If this is built, you name one track. You either get the full four-part list in chat, or
one plain reason why there is no list. While the four parts are still being built, the same command
can show you one part at a time, always labelled as development output, produced and checked by the
same machinery — never by a side script. Missing audio, missing analysis, a doubtful drop, a broken
rule, an unrecorded message, or an unavailable independent checker can never turn into a confident
partial answer.

[assumed] Every result that reaches you states the last message of yours it has on record and how
your recorded judgments are being used — so a hole in the program's memory of you shows up on the
page, not six weeks later. The development report shows exactly how the machine differs from the
moments you actually marked, one line per mark, your mark first. A fresh track you choose, heard
cold, remains the only evidence that the machine generalized; your ear remains the acceptance gate.
