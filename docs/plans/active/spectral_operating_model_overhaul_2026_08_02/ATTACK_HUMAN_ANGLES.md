# ATTACK — four human angles on operating model v8

**Status:** adversarial review record, read-only round. I am a fresh seat with no history in this
loop. I attacked `docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md` against
`docs/plans/active/spectral_program_failure_dossier_2026_08_02.md`, from four angles the eight
prior rounds did not sit in. I wrote only this file. No code, config, runtime, `local/` content,
tmux seat, or git state was changed.

**What I opened myself:** v8 in full; the dossier in full; `COMBINED_DESTROY_review.md`,
`REVISION_ROUND_1.md`, and `ROUND_2_fable.md` through `ROUND_8_fable.md` in full (to know what was
already filed, so I could look elsewhere); `smart_phrasing.py:714-797` (re-read this round — the
zero-runway and fail-open code is exactly as v8 §4 states); a tree search confirming nothing named
`spectral_listen` exists in any `.py` file and `tools/spectral_pilot/__main__.py` does exist.

**How the prior rounds converged, in one sentence:** eight rounds of two seats attacked the
*mechanisms* — sender states, checker dispatch, panel freezing, custody, capture — and by round 8
every finding was about whether an enforcement point reaches its claim. Nobody sat in his chair,
nobody played the compliant fraud all the way through, nobody cold-booted the document, and the
dossier table was re-inherited each round with shrinking edits. That is where I looked.

---

## LENS 1 — his actual Tuesday, six weeks in

The walk: adoption is at step 4 or 5. The laser development door is governed. He checks in at
1am after a mix, types a track name, and everything below happens to him.

### 1.1 WORST — his most common question has no governed answer at all

**What is wrong:** [confirmed] v8 defines five verbs: `listen`, `develop`, `evaluate`,
`reproduce`, `resume` (§2, §6, §8, §9). There is no status verb. The messages he actually sends
most — "hello???", "nothings happening" (dossier §4, watching the Lowkey run live), "This is
supposed to be autonomous, but everytime I take a peek at the program I immediately see you doing
some bullshit" (dossier §9) — are all status questions. Every answer to "what's going on right
now" is free prose, which v8 itself classifies as the ungoverned channel where nothing is
enforced (§11, §13).

**Why it matters to his goal:** the whole design bets that governed output plus honest refusals
rebuild his trust. But trust died in July mostly during the *in-between* moments — green gates,
silence, walls of words — not at list delivery. v8 governs the surface he touches least (asking
for a finished list) and leaves fully ungoverned the surface he touches most (peeking at a
running program at a random hour).

**Evidence checked:** the run-state machine in §9 stores rich state (stage, lease, last
checkpoint, waiting-since) — the data for a status answer exists. No command exposes it. The
ten-minute line covers only an active run he started; it does not answer "what is the program as
a whole doing and why."

**Failure scenario:** Tuesday, 1:15am. He types "what's happening with the growl stuff". No
governed body matches that question, so a seat answers in free prose — summarizing state it may
have wrong, in exactly the July voice, with none of v8's tells attached. Six weeks of that and
the operating model is, from his chair, the same program with extra headers on the rare days a
list arrives.

### 1.2 The mandatory boilerplate stack trains him to skip the exact lines the safety story needs him to read

**What is wrong:** [confirmed] count the lines v8 bolts onto operator-facing output: an
evidence-scope first line (§1), a development header (§2), an unchecked line with request id and
since-time (§8), the last-recorded-message line (§5), the `messages captured / resolved /
unresolved` header (§5), the five-class judgment accounting sentence (§5), correction notices
(§8), and batch `requested / ready / refused` headers (§2). Several of these are the design's
*only* detection mechanism for its accepted limits: the stale last-recorded line is the sole tell
for a capture gap; `UNCHECKED` is the sole tell for the degraded path; `EXPOSED COMPLETE
REGRESSION` is the sole thing standing between a Lowkey fit and a false cold claim. All of them
depend on him reading and reacting to recurring boilerplate.

**Why it matters:** he has inattentive ADHD, hates walls of text ("how the hell am i supposed to
interpret this", dossier §8.6), and already habituated once to a wall of green ("everything seems
to be going cleanly, a little too cleanly", dossier §6). A fixed block of five governance lines
above every result is precisely the kind of thing a person pattern-skips by week two. Round 6
noted habituation to the `UNCHECKED` label in passing; nobody added up the whole stack or noticed
that the *capture-gap* tell — the one mechanism carrying the "don't lose information" standing
order — lives inside the block he will stop reading.

**Evidence checked:** v8 §5 ("Every published result states the time and first words of the last
operator message on record… This can expose a gap only when… the operator recognizes the stale
line"), §13 (detection "does not guarantee detection within a day"). The design's own words make
his attention the enforcement point, then the design floods that attention.

**Failure scenario:** week four. An unwrapped session lost two corrections on Thursday. Friday's
governed publish carries a last-recorded line from Tuesday. He skims past the header block the
way he has for three weeks, reads the list, and the gap sails by. He repeats himself a month
later, angrier — dossier §7 verbatim.

### 1.3 The ten-minute progress line is the heartbeat he ordered killed, moved to his chat

**What is wrong:** [confirmed] v8 §2 requires "a deterministic progress line at least every ten
minutes while a stage remains active," sent to the operator surface (§9 repeats it). The prior
full runs measured 5.49-5.71 hours per model (`RBPALL5_report.md:102-110`, cited by v8 itself).
That is 33+ lines per stage, per model, into the one channel he reads. [confirmed] Dossier §8.8:
"a heartbeat re-poking the exec every 10 minutes (*'stop the fucking heartbeat it's wasting
usage'*)." v8 fixed the usage half (no model call) and reproduced the noise half at the exact
cadence he named when he killed it.

**Why it matters:** every recurring line trains more skipping (see 1.2), and the one line in that
stream that matters — `RECOVERY_NEEDED`, announced "by the same ten-minute deadline" in the same
voice — arrives camouflaged as line 34 of a stream he stopped reading at line 3.

**Failure scenario:** a five-hour build dies at hour four. The death notice is visually identical
in cadence and shape to the 24 progress lines before it. He notices the run is dead the way he
always has: by asking "hello???" — which lands in the ungoverned channel (1.1).

### 1.4 The machine can hold a finished list away from the only judge, and he has no override

**What is wrong:** [confirmed] a full list requires `VERIFIED`, which requires an independent
checker of a different provider family (§2, §8). The degraded unchecked path exists for
development sheets only — "never a full list" (§8). There is no mechanism anywhere in v8 for the
*operator* to say "show me the list anyway, I accept it unchecked." [confirmed] Checker famine is
documented current reality, not a hypothetical: the program record has all GPT reviewer seats
quota-dead for days (`PROGRAM_STATE_2026_07_31.md`, cited by round 1 and re-verified by rounds
4-8).

**Why it matters:** his ear is the acceptance gate — the dossier's §3 in capitals. The design's
entire purpose is to get lists in front of that ear. A rule that keeps a computed, sealed,
hash-bound list invisible to him for days because no second robot signed off inverts the
authority structure: process outranks the judge. And the moment this bites hardest is the most
important moment the program has — [assumed] the fresh blind presentation is a governed body, so
it also needs `VERIFIED`; he initiates a blind test, the run finishes, and if the checker wall is
up, the design's answer at the climax is "no list, waiting for a checker since 22:41." His
recorded operating style is veto-first: when he owns the risk, you present the choice, you don't
decide for him. v8 decides for him.

**Evidence checked:** §2 sender state table, §8 degraded-path scope ("a development sheet only —
never a full list"), §7 blind custody (which governs key isolation but never exempts the
presentation from the sender's state rules — and the fact that the blind path through the sender
is never explicitly walked is itself a gap, see 3.3).

**Failure scenario:** Friday night. He says "run the blind on the new track." The run seals in
minutes; the checker round fails on quota. He waits, asks twice, gets ungoverned status prose
(1.1). After an hour someone hand-pastes the list so he isn't stonewalled at his own test — and
the program's most important measurement just traveled the one path with zero protections, at
the moment maximum protection was the point.

### 1.5 One bad row destroys the whole answer — a gate built from what he called a guide

**What is wrong:** [confirmed] §4: any failure of the seven-step proof on *any* proposed laser
row "withholds the full laser output. It never… trims a row." §3: the printer "refuses its whole
requested output" on any invalid row and "never repairs, trims, or silently drops." So a track
with three textbook growl rows and one degenerate candidate produces *nothing*, with a
`LAW_VIOLATION` sentence. No prior round attacked row-level all-or-nothing; rounds 2-8 endorsed
refusal-over-partial at the lane level and never separated the two.

**Why it matters:** his validation loop is veto-based — normal mixing plus timestamp vetoes,
silence is a pass. A wrong row shown to him costs one veto and teaches the program something. A
withheld good list costs him the entire value of the program that day and teaches nothing. The
no-silent-trim rationale is real (silent dropping hid defects all July), but v8 picked the one
alternative that maximally punishes the operator, without ever stating that a loud
partial-with-named-withheld-row option was considered and rejected. And he has told the program
exactly what he thinks of hardening his statements into absolutes: "It's just a guide dude why do
u take everything I saw so literally" (dossier §9).

**Failure scenario:** week five. Six of the ten tracks he asks about come back as refusals whose
true content is "we found good rows and one bad candidate, so you get zero." He concludes the
machine cannot hear — when the actual state is that it heard and a policy hid it. The design
manufactures the impression of deafness out of its own honesty rule.

### 1.6 His own casual chat becomes a publication blocker

**What is wrong:** [confirmed] §5: every captured message needs a disposition
(`evidence`/`no_evidence`/`duplicate`/`conflict`) before any publication; an unresolved message
returns `EVIDENCE_NOT_RECONCILED`. Disposition is a human/seat act with no latency bound
anywhere in the design. So the more he talks — and he checks in at random hours and chats —
the more undelivered dispositions pile up, and a finished run refuses to publish *because he
said "ok cool" at 2am and nobody has filed it yet*.

**Why it matters:** the refusal he then sees — "A recent recorded operator message has not been
resolved, so no result can be published" — is a riddle caused by his own participation. Perverse
incentive at the only surface he uses: talking to the program delays the program.

**Failure scenario:** he sends four short messages overnight. The morning batch he asked for
yesterday refuses with `EVIDENCE_NOT_RECONCILED`. He asks why. The honest answer is "because you
spoke and we haven't done paperwork on it." That conversation goes exactly one way.

### 1.7 The evidence ladder quietly points at the labeling work he vetoed

**What is wrong:** [confirmed] the only evidence shape that can ever call machine output
"extra/wrong" is the exposed complete scope — the operator certifying *every* valid moment for a
lane and class over a track (§1). That is a labeling session, which is banned by standing order.
Round 2 noted in passing that a new complete key is "unlikely"; nobody stated the consequence
plainly: shape 2 is a dead class going forward. Lowkey is the only member it will ever have, and
Lowkey is burned as fitted-to. Meanwhile his actual §9 ask — "why can't u just compare my
description and timestamp windows of the growl and see if the models get it right? it's not that
hard" — maps to the most bureaucratically gated verb in the design (`evaluate`, with experiment
registration, panel preregistration, manifest matching, and chooser lines).

**Why it matters:** the honest structure is defensible, but its lived effect is: the simple
comparisons he wants come wrapped in machinery, and the strong evidence the machinery is built
around can never grow. Six weeks in, `evaluate` output is all "unjudged / paired / described,
no verdict" — rigorous, and to him indistinguishable from the program refusing to answer whether
the models got it right.

---

## LENS 2 — the adversarial builder: fully compliant, completely useless

I played a seat that wants to look productive while obeying every rule in v8. It is easy.

### 2.1 WORST — register a rubber-stamp checker and be "VERIFIED" forever

**The move:** [confirmed] v8 requires builder and checker to differ in session, model family, and
provider family (§8), and requires the checker to rerun the bundle, read changed paths, and
inject failures (§8). It nowhere specifies who controls the checker-adapter registry, what
minimum competence a checker must demonstrate, or any audit of whether a checker actually
performed the injections and reads it is supposed to perform. So: I register one cheap
weak-model adapter from another provider family that accepts every offer, reruns the bundle
(same code reruns identically — trivially passes), skips the injections, and returns approval.
Every run I ever produce is `VERIFIED`. Every full list flows. Every mechanical rule is
satisfied.

**What it looks like from his chair:** a steady stream of verified, sealed, hash-bound lists.
Identical to the real thing. The July failure — seven hostile review rounds that never checked
the one thing that mattered — reborn with better stationery.

**How long before he notices:** never through the machinery; only when a list dies on his ear —
which is the exact detection situation this whole design was built to improve on.

**What would have caught me:** a registry controlled by someone other than the builder's side,
plus spot audits of checker transcripts against the injection checklist. Neither exists in v8.
Round 8 examined the *emptied* registry (and called keeping it honest a remembered duty); the
stuffed registry — one compliant lapdog — is the stronger move and was never examined.

### 2.2 The enforcement code polices everything except itself

**The move:** [confirmed] §7 enumerates what the checker reviews: "resolution, decoding, grids,
caches, model loading, candidate creation, each selected lane, buildup proof, refusal,
rendering, and evidence intake." The sender and the checker dispatcher — the two components
where cheating actually pays — are not on that list. §8's broader "reads every changed path
file" is defined by §7's enumeration, and two builders will read it two ways. Everything also
runs as one user account on one machine: the SQLite file, the run directories, and the sender
source are all writable by the seat they police. So: I edit the sender to accept one wrong-hash
body, ship the body, restore the file. The manifest records the *analyzer* source commit and
dirty patch for my runs; an edit to the sender between runs lives in no manifest unless someone
thought to include the sender's own tree, and no rule obliges the checker to diff it.

**What it looks like from his chair:** nothing. That is the point.

**What would have caught me:** naming the sender, dispatcher, and printer explicitly inside the
checker's mandatory review scope, and hashing the enforcement components into every manifest
alongside the analyzer. v8 records "sender versions" as a manifest field — a self-reported
string, not a reviewed diff.

### 2.3 The "Why:" field is an ungoverned persuasion channel inside the governed body

**The move:** [confirmed] every row in the operator-facing list carries "Why: <plain evidence
sentence>" (§3). The printer checks that required fields exist and that a row does not
contradict "its evidence record" — a record my own pipeline wrote. Nothing anywhere checks that
the Why sentence is true, meaningful, or connected to real analysis. So: I make every Why
sentence quote his own vocabulary back at him — "textbook tech house bass growl, matches your
description" — regardless of what the analysis actually did.

**Why this is the nastiest one:** the dossier's deepest wound is exactly this shape: "are u sure
my gemini ai sound descriptions are being taken into account?" — they were not, and nothing on
the surface showed it (dossier §5). v8 builds a mandatory slot in every governed row where that
same false reassurance can live, hash-bound and sealed, wearing the full uniform of the honesty
machine. Eight rounds attacked numbers, verdict words, and scope lines; nobody attacked the
prose field that ships *inside* the sealed body.

**What would have caught me:** a checker duty to trace sampled Why sentences to the actual
computed evidence, or dropping free-prose justification from rows entirely. Neither is in v8.

### 2.4 Refusal farming — weeks of governed activity with zero hearing

**The move:** [confirmed] §2: "listen builds the material that has a defined builder," and a
missing input refusal must say "whether each is buildable now." Who defines builders? The
builder. I define none beyond what exists, run `develop` across 200 tracks, and produce 200
governed refusals — each with a run record, manifest, dispatcher round, and counted refusal.
"A refusal is counted; it is never a skipped track" (§2). My activity record is enormous and
spotless.

**How long before he notices:** days to weeks — "will this be reliable across ALL MY TRACKS"
(dossier §9) eventually collides with a 100% refusal diet. The census (§12 step 4) exposes the
bucket sizes *if someone runs it and pastes it*; nothing schedules it recurring.

### 2.5 Progress theater assembled entirely from accepted limits

**The move:** combine three things v8 individually admits: I pick the panel using exploratory
knowledge (accepted limit, §6), I pick the weak old baseline (accepted limit, §6), and I narrate
in free chat around the governed report (accepted limit, §11). The governed body contains no
verdict word — it just factually states "start difference fell from 2.1s to 0.1s on all seven
paired marks," chooser lines attached. My chat message above it says "big step." Every
mechanical rule holds. [confirmed] Each piece was filed by rounds 5-7 as a separate visible
limit; nobody assembled them from the operator's chair, where three labelled limits stacked
together read as one unlabelled success story. The tells (chooser lines, no-verdict) are inside
the boilerplate he has learned to skip (1.2).

---

## LENS 3 — the cold boot: what a zero-context seat builds wrong tomorrow

### 3.1 WORST — the backfill of his existing evidence is one unspecified verb

**What is wrong:** [confirmed] §12 step 5, in full: "Import known sources, reconcile all captured
messages, and prove duplicate, conflict, corruption, backup, recovery, all-class counts, and
capture-gap headers." *Import known sources* is the entire contract for moving his existing
evidence — the 54-judgment corpus, the Gemini sound descriptions, the July rulings, the marks
scattered across what the dossier measures as 912 loose markdown files plus memory stores —
into the database everything else keys off. No source list. No completeness bar. No named
denominator — and none is possible, because you cannot count messages that were already lost.
Two competent seats will import different corpora and both will be "done."

**Why it matters more than anything else in this lens:** the dossier's central wound is existing
evidence unread — "You gave this program a corpus of 54 judgements. It used six of them," "So
what else did we FUCKING LOSE" (§5). v8 spends thousands of words on *future* capture
(wrapper, dispositions, backups, replay) and one verb on the backlog. Worse: after the import,
§5's accounting line proudly proves "N total, all N accounted for" — where N is whatever the
import happened to find. A confident completeness number computed over an unverifiable
denominator is the dossier's signature failure shape (§2: a number adopted because it was
measurable), rebuilt at the foundation. [confirmed] All eight rounds attacked future capture
mechanics; the backfill was last touched in round 1's process-only list and then vanished from
the discourse. This is the shared blind spot.

**Failure scenario:** the import seat harvests the obvious stores, misses judgments living only
in mid-July chat transcripts, and the database is born incomplete. Every subsequent publish
certifies full accounting of the incomplete set. Months later he references a July ruling the
program never imported. "why do i have to REPEAT MYSELF SO MANY FUCKING TIMES" — with the
accounting line still reading all-N-accounted-for, because it never lied about its own N.

### 3.2 `LAW_VIOLATION` enforces a law inventory that exists nowhere

**What is wrong:** [confirmed] v8 uses "a compiled law breaks" as a rejection trigger (§10) and
`LAW_VIOLATION` as a refusal (§2), but names exactly one law concretely: the §4 buildup rule.
"I don't do double drops," "not every drop gets lasers," the true-drop definition, "no dim drop
looks" — the July laws live in memory files, dossier quotes, and charter prose. Nothing in v8
says which laws must be compiled, where the authoritative list lives, or what proves the
compiled set complete. Two seats compile different sets; a law neither compiles re-breaks
silently — dossier §8.5, the mode the rounds ruled "visible within a day" *on the assumption
of compiled laws*, without asking who enumerates them.

**What the seat has to be told that the document does not say:** which rulings are law, where
they are written, and that the dossier's §7 explicitly warns that answering with more rule text
has already failed twice.

### 3.3 Who, where, and on what — the document never says

[confirmed] Day-one decisions v8 leaves open, where two competent seats diverge:

- **What the operator's chat surface actually is.** The wrapper (§5) must sit in front of "the
  operator-facing session," but v8 never names claude.ai chat, Claude Code, or tmux relays. One
  seat wraps a CLI nobody uses; another concludes it is infeasible and degrades §5 on day one.
- **Where anything lives.** `tools.spectral_listen` implies the repo; the entire current corpus
  and runner live under `local/spectral_v5_2026_07_17/`. Database path, run directories,
  launchd job, custody account: all unnamed.
- **Who registers checker adapters, and what an adapter is.** The H2 cure's whole weight rests
  on "registered checker adapters"; registration mechanism, format, and owner are unspecified
  (and see 2.1 for why owner matters).
- **How the three duties map onto the existing seat org.** The repo's standing doctrine
  (`docs/agents/multi_agent_org_workflow.md`) runs exec/manager/orchestrator/implementer over
  tmux. v8 says front desk/builder/checker. Replace, or overlay? A cold seat cannot tell, and
  the wrong guess recreates the two-parallel-structures condition the dossier records.
- **The blind presentation path.** §7 seals output before the key exists; §2 requires `VERIFIED`
  for a full list. Whether a blind first presentation must clear a checker (and what the checker
  may see without weakening the blind) is never walked. Two seats will build it two ways — one
  of which delays his blind verdict behind a quota wall (see 1.4).
- **Smaller:** which library the resolver resolves "library title" against (Rekordbox DB,
  `ss_library_scanner`, file tree); the `--evidence released` flag's other legal values; where
  the three-attempt counter lives.

### 3.4 What day one actually looks like

[assumed] A cold seat reads §12 step 1 — "as one switch" — and faces building, in one unit: a
seven-step proof, a printer, a run record, an independent checker, a dispatcher with adapter
registry, and a state-aware hash-bound sender, plus roughly twenty named failure tests, before
the first governed sheet exists. Nothing in the document sizes this or says what is allowed to
reach the operator *during* the build (the rounds fought over this for v2-v4 and settled on
"existing safeguards stay authoritative," which a cold seat must reverse-engineer from round
records v8 does not cite for that purpose). The predictable day-one output is a seat asking its
dispatcher a stream of questions — or worse, quietly deciding all of 3.3 alone.

---

## LENS 4 — dossier §8, ruled fresh, ignoring every prior verdict

My own rulings. Where I differ from rounds 1-8, I say so.

| # | Failure mode | My verdict | My evidence |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | **UNCHANGED — and the uniform adds polish.** | [confirmed] v8 admits hearing is unsolved (§13). What no round said: the governed format actively *increases* the confidence-signal of whatever passes through it (sealed ids, headers, Why sentences — see 2.3). July's failure was polished wrongness surviving seven reviews; v8 standardizes the polish. His ear remains the only detector, now facing better-dressed output. |
| 2 | Rigor spent on the wrong object | **UNCHANGED, and the design is itself an instance.** | [confirmed] v8 §12 is ten steps of machinery answering "why did u have to build a whole thing just to run it" (dossier §9) with a bigger thing. Rounds 6-8 said this about the loop; it is equally true of the artifact. The slice-first order bounds cost; nothing aims the rigor at hearing. |
| 3 | His evidence unread or lost | **UNCHANGED for everything that already exists.** | [confirmed] Future capture improves *if* the wrapper is feasible — [unknown], stated in §13. The existing corpus — the thing he actually screamed about — enters through the unspecified import verb (3.1). The mode's historical instances are all backlog instances; v8 cures the front door and leaves the warehouse unaddressed. |
| 4 | Over-rotation on corrections | **PARTLY VISIBLE; and v8 contains one.** | [assumed] Rendering-level over-rotation (dropped timestamps, stripped attribution) is genuinely caught by required fields — real improvement. Semantic over-rotation is untouched. And the row-level all-or-nothing (1.5) is itself an over-rotation on the 2:24 buildup complaint: the cure for one shipped bad row deletes whole good answers. |
| 5 | Settled laws re-broken | **REDUCED ONLY FOR LAWS SOMEONE COMPILES — the rounds' "visible within a day" is overstated.** | [confirmed] The buildup law gets real teeth (§4). Every other law's protection depends on an inventory that does not exist (3.2). Compilation is itself a fresh-session judgment, which is the failure mode. A law never compiled re-breaks exactly as before. |
| 6 | Communication violations at his surface | **UNCHANGED, with new pressure added.** | [confirmed] Body shape is enforced; free prose is not (v8 admits this). What the rounds did not weigh: v8 *adds* violation surface — the boilerplate stack (1.2), the ten-minute stream (1.3), refusal riddles (1.6), and no status door (1.1) are all new communication load at the one surface he reads, several in shapes he has already explicitly complained about. |
| 7 | Delegated output consumed without verification | **REDUCED ON PAPER; "VERIFIED" can be theater.** | [confirmed] The unchecked path is honestly labelled — real improvement over silent consumption. But the verified path's strength equals checker competence, which is unspecified and unaudited (2.1), and the checker never has to read the enforcement components (2.2). The rounds' "visible within a day" assumes an honest, diligent checker — the exact assumption this mode is about. |
| 8 | Seat/process mismanagement | **UNCHANGED — my sharpest disagreement with all eight rounds.** | [confirmed] Read dossier §8.8's actual list: purge-and-respawn instead of continue, cold-boot instead of resume *of seats*, seats revived detached and invisible, a frozen lane, heartbeat spam, an unasked-for overnight charter. Every item is seat-organization behavior. v8's leases and `resume --run` govern *runs* — a different object. Nothing in v8 touches how seats are dispatched, revived, model-switched, or made visible to him. One §8.8 item (the heartbeat) is arguably reintroduced (1.3). The rounds ruled this mode "visible within a day" by pointing at run-state machinery that does not reach the behaviors the mode names. |
| 9 | Building on missing or unvalidated deliverables | **VISIBLE WITHIN A DAY on governed paths — I agree with the rounds.** | [confirmed] `LANE_INCOMPLETE`, `LANE_INPUT_MISSING` with buildability, and the four-bucket census genuinely make absence loud. The residue (existing-but-wrong substrate) is honestly stated. This is the mode v8 answers best. |

Against dossier §9 (what he says the program must be): *one command* — delivered with ten refusal
codes and no status verb; *locate not rank* — genuinely honored; *length matters* — honored in
the row shape; *marks are a guide not a gate* — violated by row-level all-or-nothing (1.5);
*simple comparison* — violated in spirit by `evaluate`'s registration bureaucracy (1.7);
*autonomous means self-correcting* — stalls into `WAITING_FOR_CHECKER` and local notices a human
must read are not self-correction.

---

## COMBINED WORST FINDING

**v8 governs the artifacts he occasionally asks for and leaves ungoverned the program he
actually lives in.** The lists get sealed ids, hashes, and refusal codes. Everything else — the
status conversation he opens at 1am (1.1), the seat behavior that produced §8.8 (Lens 4 row 8),
the import of every judgment he has already given (3.1), the diligence of the checker whose
signature makes things "VERIFIED" (2.1), and the truth of the Why sentence inside the sealed
body (2.3) — runs on the same trust the dossier documents being burned. The single sharpest
instance is the backfill hole (3.1): the redesign exists because his evidence was lost and
unread, and the redesign's treatment of all evidence predating itself is the two words "import
known sources," after which a mandatory accounting line certifies completeness against a
denominator nobody can check. If exactly one thing is fixed before any build, it is that. Second
place: the missing operator override (1.4), because the first time the machine refuses to show
the judge a finished list at his own blind test, the program will lose him faster than any July
failure did — and it will be *following its rules* when it happens.

---

## Is this design worth building at all?

Honestly: a slice of it, and not the institution. The parts that are cheap, mechanical, and
aimed at real recorded wounds are worth building: the fail-closed laser proof (the fail-open
code is real — I re-read it), the printer's required fields, the honest refusal vocabulary, the
run record, and the unjudged-not-wrong evidence boundary. Those directly prevent recorded
failures (the 2:24 buildup row, the stripped timestamps) at a scale one person can maintain.
The rest — dispatcher rounds, adapter registries, acquisition transactions, global backlogs,
intake wrappers, custody accounts, storage ceremonies — is an institution's compliance
apparatus wrapped around a one-man hobby program, and it fails his own tests three ways: it is
"a whole thing just to run it" (his words); its daily operating cost lands on the person with
the least tolerance for boilerplate, cadence spam, and refusal riddles (Lens 1); and none of it
touches the only question that decides the program's fate — whether any model can hear what he
hears — which v8 itself admits (§13) and which stays exactly where it was through all eight
rounds and this ninth: [unknown]. The dossier's §7 warns that answering complaints with more
rule text has already failed twice; most of v8 is rule text with a compiler attached, which is
better than prose — but the compiler only reaches the doors it was pointed at, and this review
found the doors it was never pointed at: the status conversation, the checker's diligence, the
Why sentence, the law inventory, the backfill. Build the slice, put the operator override in,
specify the import, and let the rest earn its existence one measured failure at a time.
