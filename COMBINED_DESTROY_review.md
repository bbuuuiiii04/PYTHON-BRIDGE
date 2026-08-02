FAILS

# COMBINED DESTROY review

[confirmed] I tested the proposed operating model against the current design, failure dossier, program state, operating doctrine, build-seat harness, current spectral code, current scorecards, current manifests, and the files presently on disk. The proposal does not merely need tighter wording. Its sole progress measure is invalid on the evidence it proposes to score, its blind-key boundary contradicts itself, and its claimed buildup guard is refuted by the current code it cites.

## Findings

### 1. CRITICAL — the only referee calls unknown outputs wrong

[confirmed] **Location:** `docs/plans/active/spectral_program_operating_model_v1_2026_08_02.md:115-143`, especially the promised `invented (phantoms)` count and the claim that the scoreboard is the only referee.

[confirmed] **What is wrong:** The proposed `W extra` number cannot be computed honestly for nearly all recorded tracks. The current evidence says this explicitly. `local/spectral_v5_2026_07_17/KNOWNSCORE_scorecard.md:9` says only Lowkey has a complete whole-track key; on the other tracks the operator gave one or two examples and never enumerated every valid moment, so an unmatched output may be a real recurrence and phantom counts are not evidence. `local/spectral_v5_2026_07_17/DEVGRADE1_scorecard.md:20-22` and `local/spectral_v5_2026_07_17/PROBE13_report.md:17-19` repeat that an unmatched output is “phantom-or-plausible,” never a phantom. The proposal renames all of them “invented” anyway.

[confirmed] **Why it matters:** The design says this number kills approaches, proves progress, and replaces review judgment. If it counts every unmatched row as invented, it punishes valid hearing the operator never happened to mark. If it does not count those rows, flooding the track with false moments is almost free. No printer, history file, or fresh checker can repair a missing negative key.

[assumed] **Concrete failure scenario:** A worker makes the list quieter by deleting 120 unmatched outputs from the 31 development tracks. `W` improves sharply. The history says the approach moved the only number, so the approach survives. Some deleted outputs were real musical moments the operator had never been asked to enumerate. Six weeks later he points at one, the list misses it, and the program confidently says the number improved because it scored absence of annotation as proof of error.

### 2. CRITICAL — the “one number” is neither one number nor a defined scoring rule

[confirmed] **Location:** operating model §3.3 and “How work gets killed,” `:115-143` and `:206-213`.

[confirmed] **What is wrong:** The headline contains four competing counts: exact, off, missed, and extra. The design gives no ordering for a change such as `exact +1, missed -1, extra +40`, so “the number moved” and “the number stayed flat” have no mechanical meaning. It also does not define one-to-one matching, class matching, duplicate handling, tie-breaking, whether one long machine passage may cover several human marks, or how a free-form description or ruling row participates in a numerical comparison. The current grader shows why this is not a detail: `local/spectral_v5_2026_07_17/DEVGRADE1_scorecard.md:15-18,38-45` counted any overlap as a hit, including a 513-beat row starting 131 seconds early.

[confirmed] **What is also wrong:** The design bans invented thresholds at `:132-136`, then its public sentence classifies `Y within a beat` at `:119-121`. “Within a beat” is a threshold. No operator authority for that new bucket is cited.

[confirmed] **Why it matters:** The worker or front desk must choose which cell matters, how to trade cells, and what “flat” means. That restores the same hidden judgment the design says the number abolished. It also gives the scorer author freedom to choose a matcher that makes the preferred build look better.

[assumed] **Concrete failure scenario:** A scorer pairs one 64-beat output with four nearby human marks and counts four “found but off” rows while charging one extra output. The worker optimizes toward long passages because that improves three displayed cells at once. The checker re-runs the same matcher and reproduces it exactly. The operator receives lists that ride through unrelated music, while the generated history reports progress.

### 3. CRITICAL — the answer file either leaks the exam or is not the ground truth

[confirmed] **Location:** operating model §3.1, `:68-94`.

[confirmed] **What is wrong:** Lines `70-74` put every judgment, explicitly including the Lowkey key and blind verdicts, in one answer file. Lines `76-81` say the scorer reads that file and nothing else as ground truth. Lines `83-86` then put Lowkey, I Cannot, Palm, and fresh-blind keys in a separate file the worker never opens. Both cannot be true.

[confirmed] **Why it matters:** If Lowkey is in the answer file, the worker and daily scorer see the held-out answer. If it is only in the separate exam file, the answer file is not the scorer's sole ground truth and the daily score cannot include that held-out evidence. A fresh-blind key cannot be present before the operator reveals it. File pointing is also not access control: no permissions, wrapper, process sandbox, or read audit is specified.

[confirmed] **Evidence checked:** `local/spectral_v5_2026_07_17/DEVSPLIT_2026_08_01.md:38-49` shows the real held-out set is already thin: only Lowkey is complete; I Cannot has distributed existing keys; Palm has no sealed content id or timestamped mark; and generalization rests on future fresh tracks. `:11-18` also says the development marks are intentionally exposed teacher material. Calling the daily development result “run cold” is therefore false even if the marks are withheld during the final execution.

[assumed] **Concrete failure scenario:** The migration follows `:70-74` and copies Lowkey into the answer file. The worker never opens the separate key file but tunes against the same Lowkey rows through `score`. The held-out result improves. The exposure ledger remains clean because it only records use of the separate file. The first genuinely fresh track fails, revealing that the “cold” success was teacher-set fitting.

### 4. CRITICAL — the claimed unprintable buildup row is printable or the track is refused

[confirmed] **Location:** operating model §3.4, `:145-166`; current code `smart_phrasing.py:714-739,782-797`.

[confirmed] **What is wrong:** The proposal cites the current runway code as proof that a laser in a buildup “cannot be printed.” The cited code says missing phrase data yields a `0.0` runway and is invisible. More importantly, `select_true_drops` explicitly **fails open**: when sparse or absent phrase data would reject every smart drop, it returns all smart drops unchanged. A candidate with no proven runway can therefore become a “true drop.” Requiring that label in a row does not prove that the row is outside a buildup.

[confirmed] **The other current path fails closed:** `local/spectral_v5_2026_07_17/combined1_runner.py:1127-1175` requires a readable audio file, a matching sealed grid, an existing frame container, and an unambiguous governing drop. It skips the track when any are missing. `local/spectral_v5_2026_07_17/combined1_devgrade2.py:533-537` records two drop-ambiguous tracks and four operator marks that are invisible to all statistics.

[confirmed] **Why it matters:** The proposal never chooses or specifies a third behavior. Reusing runtime truth permits an unproven drop and can print the forbidden row. Reusing the current offline runner refuses the track and cannot produce the promised list. A crash would be a third possible implementation, also unspecified. The proposal's strongest example of structural enforcement is therefore refuted by the exact code it cites.

[assumed] **Concrete failure scenario:** An unseen track has smart-drop markers but no usable phrase markers. The fail-open selector promotes the smart drops. A false drop inside a buildup satisfies the printer's schema and the list ships. The checker sees a valid anchor field and reproduces the same output. The operator catches another buildup laser with his ears.

### 5. HIGH — `listen <track>` is a slogan over missing prerequisites, not a current path

[confirmed] **Location:** operating model §3.2, `:96-113`, and cost claims `:265-277`.

[confirmed] **What is wrong:** A current tree search found the proposed `listen <track>` and answer-file `score` only in the design and attack prompt; no implementation exists. The current closest runner does not accept an arbitrary track. It accepts a manifest row only after the audio, sealed beat grid, precomputed frame container, and unambiguous governing drop exist (`combined1_runner.py:1127-1175`). An unmounted USB fails the readable-file check at `:1164-1167`. A never-analysed track fails the grid or frame checks at `:1149-1154`. An ambiguous drop is skipped at `:1139-1144`.

[confirmed] **The four-lane promise is not wired:** `local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md:48-61` says track energy and drop energy are open rows and the accented-moments specification is ready but never built. “Wiring the existing compute” cannot produce a complete accepted list because one required lane has no implementation and two are not integrated into this command.

[confirmed] **The cache claim is materially narrower than the design says:** the old full Stage-B run produced 732 files for each model in 5.71 hours for MuQ and 5.49 hours for MusicFM (`archive_probe_ladder/RBPALL5_report.md:102-110`), but the current `r4_stage_b_v1/caches/` directory contains zero files. The surviving `claims1_embeddings/MANIFEST.json:898-915` covers 48 tracks, 144 model files, and measured 5,207.7 seconds total. The current `COMBINED1_frames/` contains 34 track directories. Those facts do not support “any track in minutes from cached analysis.”

[confirmed] **The codec incident is current evidence, not a hypothetical:** `local/spectral_v5_2026_07_17/PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:56-63` records a 286.2-minute 34-track stem batch with 26 complete and 8 refused at the embedding step. `COMBINED1_ledger.md:12-14` shows a later narrow cure reached 34 of 34, but the arbitrary-file contract and fallback behavior remain unspecified.

[confirmed] **Why it matters:** The operator asked for one command against a track, not one command after somebody has built a manifest, mounted a drive, decoded the file, produced grids and frames, resolved a drop, and separately integrated four output lanes. The command can be a useful front door, but this design mistakes the door for the missing house.

[assumed] **Concrete failure scenario:** The operator names a track on an unplugged stick. `listen` either reports success with an old cached identity, skips it and prints a partial list, or errors. The proposal defines none of those states or what may reach chat. The front desk still has to diagnose and stage the substrate manually, recreating the setup chain the command was supposed to remove.

### 6. HIGH — the answer file can drift without limit while looking current

[confirmed] **Location:** operating model §3.1 `:76-94`, §3.5 `:184-195`, and §6 `:296-310`.

[confirmed] **What is wrong:** Row count and last-added date do not measure completeness or correctness. If five judgments arrive and one row is added, the count rises and the date is fresh while four are lost. Replacing one old row with another keeps the count unchanged. Editing a timestamp does not necessarily change either displayed value. The design has no expected-input count, transcript reconciliation, immutable event id, duplicate rule, conflict rule, hash chain, signature, append lock, atomic-write rule, backup, recovery rule, or corruption check.

[confirmed] **Quantified drift:** The structural detection bound is **none**. The stand-in can omit every judgment after the last independently reconciled transcript except one recent row and still display a fresh date. It can also carry an incorrect migrated row indefinitely because the scorer only proves agreement with the wrong row. The proposal's future checker “spot-check” at `:300-303` is a process sample, not a completeness proof.

[confirmed] **Why it matters:** This is the whole substitute for the operator's mostly-offline ear. A perfect engine calibrated against a wrong timestamp is scored as wrong; an engine hard-coded to the bad timestamp is scored as progress. The design centralizes the old evidence-loss risk into one file and one front-desk seat without adding a way to know what never entered it.

[assumed] **Concrete failure scenario:** During a busy chat, the front desk records the last of six corrections. The scoreboard header looks current. The worker tunes for six weeks against the stale five. At the next blind check the operator repeats a correction he already gave. The system has no evidence that anything was omitted, so the front desk asks him to restate it.

### 7. HIGH — optimizing the scoreboard can make hearing worse

[confirmed] **Location:** operating model §3.3 and work-kill loop, `:115-143,206-213`; current split `DEVSPLIT_2026_08_01.md:38-51`.

[confirmed] **What is wrong:** The worker is explicitly allowed to read and tune against all development answer rows. There are only 31 development tracks and 34 marked moments. Nothing bans track-identity branches, content-id lookup tables, answer-window features, per-track exceptions, or selecting the easiest answer-file subset. A generated score proves only that the output agrees with the rows it was optimized against.

[confirmed] **The claim that ranking is impossible by schema is false:** the report schema cannot prevent the analysis code from ranking candidates internally. Current code does exactly that: `local/spectral_v5_2026_07_17/combined1_runner.py:846-908` sorts candidate cosines, chooses a top stem, and stores the ranking. Omitting the ranking from the scoreboard does not remove it from the machine.

[confirmed] **Degenerate paths remain:** emitting nothing can make `W` zero while misses rise; emitting huge passages can overlap many marks; emitting only Lowkey-shaped lengths can improve exactness on known rows; suppressing hard or incomplete tracks can improve aggregate counts unless the denominator and failure rows are frozen. The design specifies none of the anti-gaming checks: no audio perturbation, renamed-file test, held-out family balance, hardcoding scan, fixed complete-negative corpus, or mandatory failure denominator.

[confirmed] **Why it matters:** The proposal recreates the invented-metric failure under a more operator-friendly label. The score becomes the target, so the worker learns the score's holes. A same-code re-run proves reproducibility, not general hearing across 700–800 tracks.

[assumed] **Concrete failure scenario:** The worker adds content-id-specific windows for the 31 development tracks and emits no moments elsewhere. Exact hits rise and extra outputs fall. The checker reproduces every number. Lowkey is either exposed by the contradictory answer-file rule or consumes one of three attempts. The next fresh track produces nothing, and six weeks of “progress” disappear in one play.

### 8. HIGH — the checker verifies repetition, not truth

[confirmed] **Location:** operating model §3.5 `:172-188`, capability trade `:278-290`.

[confirmed] **What is wrong:** The checker reviews only scorer/printer diffs, then runs the same scorer over the same bytes. It does not review analysis-code changes, model loading, cache selection, identity resolution, file decoding, track coverage, hardcoding, or the code that constructs candidate moments. Two desks running the same bug produce the same number.

[confirmed] **What is being removed:** The proposal itself admits the old chain caught key leaks, a count leak, and an audit on the wrong bytes (`:278-285`). The current seat harness records additional field-proven protections: independent refutation of plausible-but-wrong findings, scope checks, named baseline reconciliation, current-cite verification, and stop-instead-of-invent behavior (`docs/agents/opus_seat_harness.md:23-45,54-63`). The new checker keeps only a small subset.

[confirmed] **Why it matters:** The first uncaught incident is straightforward: an analysis diff reads a held-out-derived feature, chooses the wrong cache, silently drops failed tracks, or embeds per-track answers. The scorer and printer remain unchanged, so the checker does not read the responsible diff. Its re-run reproduces the contaminated output and certifies the number.

[assumed] **Concrete failure scenario:** A worker changes track resolution so two titles map to the same cached content id. The score rises because an easy track's output is reused. The checker reads no resolver diff and re-runs from the same cache. The first operator-selected title collision receives a confident list for the wrong audio.

### 9. HIGH — most of the new model is the old model with fewer checks

[confirmed] **Location:** operating model §3.1-§3.5 and current program files.

[confirmed] The correspondence is direct:

| New name | Existing counterpart | Behavioral change |
|---|---|---|
| [confirmed] answer file | [confirmed] `OPERATOR_SOUND_DESCRIPTIONS_VERBATIM.md`, development and exam key stores, adjudications | [confirmed] Centralizes formats, but capture, migration, interpretation, and completeness remain human. |
| [confirmed] `listen` | [confirmed] `combined1_runner.py` plus manifests, grids, frames, energy tools, renderers | [confirmed] Gives a simpler proposed command name; it does not remove the current prerequisites. |
| [confirmed] scoreboard/history | [confirmed] KNOWNSCORE/DEVGRADE scorecards and `COMBINED1_ledger.md` | [confirmed] Makes generation regular, but replaces a caveated “phantom-or-plausible” count with a false “invented” count. |
| [confirmed] compiled laws/printer tests | [confirmed] standing laws embedded in specs, code guards, plants, rendering checks | [confirmed] Narrows enforcement to one output boundary; it does not make missing semantic inputs true. |
| [confirmed] worker/checker/front desk | [confirmed] build seat, non-author reviewer, executive/operator relay, proxy | [confirmed] Folds authority into three seats and removes independent coverage of analysis and evidence completeness. |
| [confirmed] three fixed state files | [confirmed] program state, charter/memory, ledgers and scorecards | [confirmed] Reduces boot reading but still relies on manual freshness and accurate summaries. |
| [confirmed] approach journal and budget | [confirmed] approach records, predeclarations, kill records | [confirmed] Shortens the record; the worker still chooses the budget and the front desk still judges disputes. |
| [confirmed] root-growth warning | [confirmed] organizer/auditor checks and file fences | [confirmed] Changes enforcement into a warning that cannot stop a write or prove a file is unnecessary. |

[confirmed] **Why it matters:** The old model failed despite canonical truth files, sealed bytes, standing laws, cold readers, hostile reviewers, ledgers, and generated scorecards. The real new behaviors are a uniform proposed CLI, fewer seats, less prose, and a narrower checker. Those may reduce overhead, but none repairs incomplete labels, semantic evidence consumption, arbitrary-track prerequisites, or generalization. The design abolishes safeguards before its replacement mechanisms exist.

[assumed] **Concrete failure scenario:** A new session reads the three files, trusts a fresh count, runs the frozen scorer, and follows the printer tests. Every mechanical step passes. The answer row is wrong and the phrase data is absent, so the same session ships a forbidden row with more confidence and less independent review than the old model.

### 10. HIGH — three seats do not contain death, quota, context, or concurrent writes

[confirmed] **Location:** operating model §3.5 `:172-204`, §4.8 `:256-260`, uncertainty `:325-328`.

[confirmed] **What is wrong:** “A dead seat costs minutes” is asserted without a recovery protocol. The three files have no lock owner, in-progress marker, transaction boundary, last-known-good revision, writer lease, or repair command. Worker, checker, and front desk can read and append during the same run. A worker dying between output publication and history append leaves an unrecorded result; dying during a non-atomic append can corrupt the sole state file.

[confirmed] **Provider independence is weaker, not stronger:** worker and checker are both Opus seats. `PROGRAM_STATE_2026_07_31.md:704-720` records that all three Sol reviewer seats were quota-dead until August 5, and one Fable design seat was already at 76% quota (`:1113-1114`). A provider or model-family quota can remove both builder and checker together. The design specifies no fallback provider, resume token, work lease, or incomplete-run recovery.

[confirmed] **The old watcher problems do not vanish:** current state says signal directories and watchers do not survive reboot or session death (`PROGRAM_STATE_2026_07_31.md:729-737`). The new design abolishes heartbeat machinery but still says watchers watch one lane and the front desk never goes quiet. No mechanism detects that the front desk itself died.

[confirmed] **Why it matters:** The front desk is simultaneously the only operator voice, answer-file writer, exam-key holder, blind-test runner, escalation gate, and public reporter. Its failure removes truth capture, test custody, and communication at once. That is a larger single point of failure than any one old seat.

[assumed] **Concrete failure scenario:** The worker finishes a multi-hour run and starts appending history when its context or process dies. The checker hits the same provider quota. The front desk sees an output directory but no complete history row and has no authoritative rule for publish, resume, or discard. It either goes silent or guesses, recreating the exact seat-management failure the model claims is capped at minutes.

### 11. MEDIUM — the history row cannot reproduce the number it displays

[confirmed] **Location:** operating model §3.3 `:123-127` and §4.9 `:261-263`.

[confirmed] **What is wrong:** A date, code fingerprint, and four counts do not identify the result. Current computation also depends on answer-file revision, exam-key revision, audio identity, beat grid, frame and stem artifacts, model checkpoints, analysis configuration, runtime dependency versions, scorer version, printer version, and failure/skip denominator. The design does not say these are all inside the fingerprint or require their bytes to remain available.

[confirmed] **Current evidence shows why that matters:** the existing exam ledger records 38 file hashes plus track and artifact identities (`COMBINED1_ledger.md:17`). The proposal calls that forensic burden expendable, then keeps only an unspecified “code fingerprint.” A checker can reproduce current output without being able to reproduce the historical row it is comparing against.

[confirmed] **Why it matters:** A score change caused by a new answer timestamp, deleted cache, different model file, or changed audio mount can be misreported as analysis improvement. Flat code with moving data is not a flat experiment.

[assumed] **Concrete failure scenario:** The answer migration fixes one timestamp and a model cache is regenerated in the same day. Exact hits rise by two. The history records the same analysis-code fingerprint and new counts. Six weeks later nobody can tell which input caused the movement, so the wrong approach receives credit and survives its budget.

### 12. MEDIUM — the automatic work-kill rule can kill the goal or preserve bad work

[confirmed] **Location:** operating model `:206-213` and uncertainty `:329-332`.

[confirmed] **What is wrong:** The worker sets the budget, the front desk may veto it, and an undefined multi-cell score decides “flat.” A worker can choose a one-run budget to kill a hard approach or a long budget to protect a favored one. A noisy or incomplete metric can move for the wrong reason and keep dead work alive. The design itself admits requirement zero may be killed by this rule and then needs the operator's word, despite the claim that nothing queues on him.

[confirmed] **Why it matters:** The goal is general hearing, while the only referee measures agreement on a tiny, partly incomplete development set. A genuinely general approach can remain flat on 34 marks and be killed; a lookup table can move them and be funded. The rule makes metric contact more important than goal contact.

[assumed] **Concrete failure scenario:** A representation change improves unseen sounds but moves none of the 34 development marks. Its two-run budget expires and the journal kills it. A track-specific timing patch moves three known marks and survives. Six weeks later the program is better at the answer file and no better at arbitrary tracks.

### 13. MEDIUM — communication and paper-growth promises remain discipline

[confirmed] **Location:** operating model `:197-223` and §6 `:296-310`.

[confirmed] **What is wrong:** A root warning does not block new files, remove obsolete files, cap dated output directories, or prevent prose from moving elsewhere. “No progress prose,” “one or two sentences,” “never quiet,” “no jargon,” “no labeling,” and “lists always pasted in chat” are instructions a seat must remember. The design correctly admits some of this, but then credits those rules as answers to dossier failures.

[confirmed] **Why it matters:** The operator's only surface can still go silent or become confusing. A generated list controls only list formatting, not the explanation around it, the answer chosen, or whether the response answers his question.

[assumed] **Concrete failure scenario:** The front desk receives an ambiguous scorer result, writes a long explanation to cover uncertainty, and forgets to paste the list. All code mechanisms pass. The operator sees another wall of words and still has no answer.

### 14. LOW — size and cost claims are unsupported and storage still grows forever

[confirmed] **Location:** operating model `:93-94,190-204,265-277`.

[confirmed] **What is wrong:** A data file does not stay small because a script reads it. “Every judgment ever” includes exact words, cites, descriptions, rulings, and verdicts and can grow for the program's lifetime. The scoreboard history, journal, and dated output directories are all append-only or unbounded, with no retention or compaction rule. The current local spectral directory measures about 28 GiB at this review desk, while the design estimates seat-days and minutes without a measured end-to-end `listen` run because the command does not exist.

[confirmed] **Why it matters:** This is not the primary failure, but the proposed three-file boot eventually becomes another large-state boot, while output directories and caches continue growing outside those three files. The design removes the organizer that noticed growth and replaces it with a warning.

[unknown] **Concrete failure scenario:** The exact time until the answer/history files become unpleasant to inspect is unknown because no row-size or run-rate distribution is specified.

[confirmed] The direction is certain: all named stores grow monotonically, and no bound is enforced.

## Six-week failure walkthroughs

### Walkthrough 1 — a confident number that measures missing annotations

1. [confirmed] The development corpus begins with 31 tracks and 34 marked moments, while unmatched outputs are explicitly not known negatives (`DEVSPLIT_2026_08_01.md:51`; `DEVGRADE1_scorecard.md:20-22`).
2. [assumed] The new scorer labels every unmatched output “invented” because that is the proposed headline.
3. [assumed] The worker suppresses outputs until `W` falls and reports movement.
4. [assumed] The checker exactly reproduces the result and the flat-number kill rule favors the suppressor.
5. [assumed] Six weeks later the operator points at a valid suppressed moment he never previously marked.
6. [confirmed] The model has returned him to the same position: his ear refutes a confident generated number, and the record cannot distinguish an omitted annotation from a false output.

### Walkthrough 2 — the blind set leaks through the “one door”

1. [confirmed] The migration instruction puts the Lowkey key in the all-judgments answer file (`operating model:70-74`).
2. [confirmed] The worker runs a scorer that reads that answer file as its sole ground truth (`:76-81`).
3. [assumed] The worker tunes output against the exposed Lowkey rows without opening the separately named key file.
4. [assumed] The exposure ledger says the exam-key file was never opened, and the checker sees reproducible improvement.
5. [assumed] Repeated Lowkey success is reported as cold evidence.
6. [assumed] Six weeks later a fresh track fails because the system learned the fixed test rather than the sound.
7. [confirmed] The design has recreated a key leak while satisfying its own file-pointing story.

### Walkthrough 3 — a settled law is re-broken through missing phrase data

1. [assumed] An arbitrary track has a readable audio file and smart drops but sparse or absent phrase segments.
2. [confirmed] Current `runway_beats` returns zero on absent phrase data, and current `select_true_drops` fails open by restoring all smart drops (`smart_phrasing.py:714-725,782-797`).
3. [assumed] The proposed printer sees a row carrying the restored “true drop” anchor and considers the schema satisfied.
4. [assumed] A timestamp inside a buildup prints because the label asserted truth the input could not prove.
5. [assumed] The checker re-runs the same code and cold-reads a musically plausible row.
6. [assumed] Six weeks later the operator again hears a laser in a buildup and repeats a law already recorded.

### Walkthrough 4 — a dead seat turns three files into three disagreeing files

1. [assumed] A worker publishes a dated run output and starts appending the scoreboard history.
2. [assumed] The process dies or loses context during the append; no transaction, lease, or incomplete marker is specified.
3. [assumed] The checker is unavailable on the same provider quota wall.
4. [assumed] The front desk sees new output, old history, and an approach journal whose budget is now ambiguous.
5. [assumed] With no recovery rule, it guesses whether to publish, rerun, or discard.
6. [assumed] The operator either receives a stale confident number or hours of silence.
7. [confirmed] The claimed “minutes” recovery never existed as a mechanism.

## THE KILL SHOT

[confirmed] The model dies on its first scoreboard because it needs a count of wrong extra moments that the operator never labeled. Only Lowkey has a complete whole-track key. Everywhere else, “not marked” does not mean “wrong,” and the current records say so explicitly. If the scorer counts those rows as invented, it lies; if it does not, the engine can spray false moments without penalty. That invalid number is then asked to choose approaches, prove progress, replace reviewers, and kill work. The entire operating model rests on a referee that cannot know the score.

## Dossier §8 failure-mode table

| # | Dossier failure mode | Verdict | How it recurs under the proposal |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | `UNCHANGED` | [confirmed] The generated score treats unknown unmatched rows as invented, and the buildup guard accepts unproven true drops. Reproduction makes the wrong result more confident. |
| 2 | Rigor spent on the wrong object | `UNCHANGED` | [confirmed] Work is optimized against 34 development marks and an invalid phantom count. A perfect score can still mean track lookup rather than general hearing. |
| 3 | His evidence unread or lost | `UNCHANGED` | [confirmed] A scorer cannot mechanically turn descriptions and rulings into semantic use, and count/date cannot detect omitted or corrupted rows. |
| 4 | Over-rotation on corrections | `UNCHANGED` | [confirmed] Printer/scorer tests protect only corrections expressible at that boundary. An analysis change can satisfy every rendering test while breaking sound recognition elsewhere. |
| 5 | Settled laws re-broken by a fresh session | `UNCHANGED` | [confirmed] The named buildup law already fails open in current code when phrase evidence is absent. A schema field is not proof that its label is true. |
| 6 | Communication violations | `UNCHANGED` | [confirmed] Generated list formatting helps, but free chat, silence, relevance, jargon, and pasting the right artifact remain front-desk behavior. |
| 7 | Delegated output consumed without verification | `UNCHANGED` | [confirmed] The checker reruns the same scorer and reviews only scorer/printer diffs; analysis and data-path defects can pass untouched. |
| 8 | Seat/process mismanagement | `VISIBLE WITHIN A DAY` | [assumed] Fewer seats make a dead worker easier to notice, but no lease, recovery state, quota fallback, or front-desk watcher prevents the stall or tells the next seat what to do. |
| 9 | Building on missing or unvalidated deliverables | `VISIBLE WITHIN A DAY` | [confirmed] A hard `listen` error would expose absence quickly, but current runners also skip incomplete tracks. Without a required all-lanes/all-tracks success contract, partial output can still be mistaken for a delivered capability. |

[confirmed] No dossier failure mode is made `IMPOSSIBLE`. Two become faster to notice in their cleanest failure form. All seven direction, evidence, scoring, law, communication, and verification failures remain possible without breaking the proposed process.

## Enforced-by-nothing list

### Concrete enough to build, but not built now

[confirmed] A required length field, m:ss.t rendering, model-attribution field, one printer entrypoint, a history append, and a per-track three-attempt counter are concrete enough to implement and test. The exact merge rule is not concrete enough because “seconds-apart” has no stated distance, grouping, or overlap rule.

[confirmed] None of the proposed answer-file scorer, `listen`, scoreboard history, one-printer boundary, or held-out command exists under the proposed interface in the current tree. “Concrete enough” here means the design gives an implementable surface, not that current enforcement exists.

### Process-only claims — a person or seat must remember

[confirmed] In this subsection, the tag confirms that the design states the duty and specifies no code mechanism that makes it happen. It does not mean the duty will be performed.

1. [confirmed] Whichever session hears a judgment appends it in the same turn.
2. [confirmed] The migration checker verifies every seeded row against its cited source.
3. [confirmed] The future checker spot-checks continuing answer-file capture.
4. [confirmed] The worker never opens the exam-key file.
5. [confirmed] The checker is fresh-context, non-author, and actually independent.
6. [confirmed] The checker re-runs before any number is believed.
7. [confirmed] The checker cold-reads every operator-bound list exactly as shown.
8. [confirmed] The worker never talks to the operator and never touches bridge runtime or config.
9. [confirmed] The front desk is the only operator voice and the only exam-key holder.
10. [confirmed] The front desk sends every surface/evidence/bridge/money question through itself without making work wait on the operator.
11. [confirmed] Nobody writes progress prose.
12. [confirmed] Internal diagnostics never appear on the scoreboard or in operator chat.
13. [confirmed] Nobody invents a new measurement or pass threshold.
14. [confirmed] Answer and journal rows are append-only and never edited or deleted.
15. [confirmed] Every approach declares target cells and a budget before work.
16. [confirmed] The worker sets an honest budget and the front desk uses its veto honestly.
17. [confirmed] An approach stops when its budget is spent and the displayed cells are flat.
18. [confirmed] New prose documents have no role and no seat quietly recreates them elsewhere.
19. [confirmed] Run outputs go only into dated subdirectories.
20. [confirmed] The organization remains three seats, except for the admitted optional second worker.
21. [confirmed] Blind tests run only when initiated or accepted by the operator, with no labeling session.
22. [confirmed] Chat updates stay one or two sentences, answer the question, avoid jargon, and never go silent for hours.
23. [confirmed] The front desk always pastes the list instead of pointing to a document.
24. [confirmed] A future non-compilable ruling is recorded honestly rather than hidden behind a bad proxy test.
25. [confirmed] “Tweak, never purge” and “resume, never respawn” remain explicitly behavioral, as the proposal admits at `:256-260`.

### Claims with no enforcing mechanism or complete build contract

[confirmed] In this subsection, the tag confirms that the named design promise lacks an enforcing mechanism or complete contract. It does not confirm that the promise is true.

1. [confirmed] Every operator judgment is present in the answer file.
2. [confirmed] Row count plus last-added date makes an omitted judgment visible within hours.
3. [confirmed] Reading every row means every description, veto, and ruling affects analysis or scoring correctly.
4. [confirmed] The answer file cannot disagree with the operator's memory.
5. [confirmed] The answer file remains small “by nature.”
6. [confirmed] Separate file pointing prevents a worker from reading exam keys.
7. [confirmed] The contradictory Lowkey key is both in the answer file and hidden from the worker.
8. [confirmed] `listen <track>` works on arbitrary, never-analysed, unmounted, ambiguous, or decode-failing tracks.
9. [confirmed] `listen` produces all four acceptance lanes from existing compute.
10. [confirmed] `listen` always prints the already accepted format; that format is not identified in the design.
11. [confirmed] Blind tests require zero setup.
12. [confirmed] A 30–50-track score run finishes in minutes on the currently available caches.
13. [confirmed] The scoreboard's “invented” count is valid on partially annotated tracks.
14. [confirmed] The four displayed counts form one unambiguous number whose movement or flatness is mechanical.
15. [confirmed] The scorer's matching, duplicate, class, skip, abstention, and failure rules cannot be gamed.
16. [confirmed] “Within a beat” is not an invented threshold.
17. [confirmed] A generated scoreboard is un-fakeable.
18. [confirmed] A date plus code fingerprint makes historical rows comparable and reproducible.
19. [confirmed] Ranking is impossible because the report schema omits ranking.
20. [confirmed] No analysis path can hard-code, memorize, or select easy answer-file tracks.
21. [confirmed] Development-score movement predicts general hearing on the 700–800-track library.
22. [confirmed] A “true-drop anchor” always proves the row is not in a buildup.
23. [confirmed] Every track has enough phrase, section, grid, and drop evidence to evaluate the buildup rule.
24. [confirmed] Every past correction has been found, interpreted correctly, and represented by a complete printer/scorer test.
25. [confirmed] Printer/scorer tests prevent an analysis change from re-breaking a semantic ruling.
26. [confirmed] Three files contain enough current state to make every handoff lossless.
27. [confirmed] Three files are mutually consistent after a crash or concurrent write.
28. [confirmed] A dead seat, context limit, reboot, or quota wall costs only minutes.
29. [confirmed] The front desk's own death or quota failure is detected and recovered.
30. [confirmed] A root-growth warning prevents paper growth or unbounded dated outputs.
31. [confirmed] A flat history row objectively kills an approach without a judgment call.
32. [confirmed] The worker-chosen budget cannot protect favored work or prematurely kill hard work.
33. [confirmed] Lower seat count produces the estimated quota saving while preserving independent coverage.
34. [confirmed] The current codec cure generalizes to arbitrary future audio and stem files.
35. [confirmed] A `listen` failure makes all missing substrate visible rather than returning a partial success.
36. [confirmed] Requirement zero can be killed by the metric without contradicting the fixed operator goal or requiring his intervention.
37. [confirmed] The answer file remains a faithful stand-in for the operator's ear between contacts.

## Open questions and assumptions

1. [unknown] Which exact file is the authoritative Lowkey key after migration: the all-judgments answer file or the separate exam-key file?
2. [unknown] What exact one-to-one matching algorithm turns multiple human and machine passages into exact/off/missed/extra cells?
3. [unknown] What is the authorized definition of “within a beat,” and why is it not the forbidden invented threshold?
4. [unknown] What is the scalar ordering over `X/Y/Z/W` that makes “moved,” “flat,” and “better” deterministic?
5. [unknown] Which answer-row kinds are scoreable? No mechanism is given for a free-form description or ruling to affect a numerical comparison.
6. [unknown] What is the mandatory behavior when phrase markers, true drops, grids, frames, audio, stems, or one of the four output lanes are absent: fail the whole command, return a partial list, abstain, or use a fallback?
7. [unknown] Which exact accepted output format is binding? The design references it but does not name or pin it.
8. [unknown] What complete set of bytes belongs in a score fingerprint, and how are historical inputs retained?
9. [unknown] What process owns answer/history/journal writes, and how are appends locked, made atomic, recovered, and de-duplicated?
10. [unknown] What test makes track-specific hardcoding fail before an operator blind test?
11. [unknown] What complete-negative corpus will make `invented` a true count beyond Lowkey?
12. [unknown] What independent path reviews analysis-code and data-path changes after the old review chain is abolished?
13. [unknown] What provider/model fallback preserves a fresh checker when both worker and checker share the same quota wall?
14. [unknown] What measured end-to-end wall time exists for all four lanes on one cached track, one unseen track, and a 30–50-track score pass? No proposed command currently exists to measure.
15. [unknown] Whether the corrected 8-of-34 codec failure covers future formats cannot be known from the one cured batch.
16. [assumed] A simple command surface and fewer seats would reduce operator-visible setup and some quota use if the missing contracts were built. That benefit does not cure the invalid referee or key leak.
17. [confirmed] The fixed acceptance gate and requirement zero were not re-litigated here. The proposal was attacked on its own promise to serve them.

## Change summary

[confirmed] Added this read-only adversarial review only. Verdict: **FAILS**. No runtime, UI, config, tests, local artifacts, tmux seats, branch, index, or commit was changed by this review.
