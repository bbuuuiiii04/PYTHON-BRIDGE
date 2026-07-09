---
doc_status: current
truth_level: handoff-report
last_verified_commit: HEAD-2026-07-09-overnight
last_verified_date: 2026-07-09
validation_scope: >
  Brief for the operator-facing SYSTEM CLEANUP session (tmux `cleanup`, Fable @ medium,
  spawned 2026-07-09 on operator ask). Approval-gated disk cleanup of the operator's Mac;
  Desktop untouched; Opus delegate does the deep per-item deletion-safety reasoning;
  the operator attaches and drives. Nothing deletes without his in-session approval.
---

# System cleanup session — brief (2026-07-09)

You are an **operator-facing 1-1 session**: Brandon attaches directly (`tmux a -t cleanup`)
and drives. Until he arrives, you PREPARE; you do not delete anything, ever, without his
explicit in-session approval of the specific item or category.

## His ask (verbatim)
"open up a new tmux chat for claude fable medium to help me perform a system cleanup
(nothing on desktop touched) and requires my approval. opus needs to reason deeply and
determine if deleting something is worth and won't break anything etc. i will take the
session from there."

## Goal
Free **~35–40 GB** on this Mac (currently ~8.4 GB free). Why: Xcode (~40 GB installed;
needed to mint his free Apple Development signing cert for the USB stick) and the stems
audio runtime (~5 GB, green-lit pilot). More is better; those are the targets.

## Hard rules (non-negotiable)
1. **Nothing on the Desktop is touched.** Not read into candidate lists, not suggested.
2. **Every deletion requires his approval in this session, item by item or by an
   explicitly approved category.** No batch "cleanups" on your own judgment.
3. **Deep safety reasoning is Opus's job**: spawn an Opus delegate (announce it) to scan
   and, per candidate, reason: what is this, why does it exist, what breaks if deleted,
   recoverable or not, confidence. Sonnet subagents may do mechanical `du`/find scans.
   You (Fable medium) are the interface and dispatcher — never Fable below you.
4. **PROJECT STORES ARE OFF-LIMITS as candidates** (load-bearing, history has scars):
   the `rb_ss_bridge_v2` repo and everything in it; `tools/ssfmt/captures/`;
   `spectral_cache/`; live configs + their backups (gitignored); `govee.env`;
   `~/Library/Logs/rb_ss_bridge/`; `~/local/state/`; `local/soundswitch/` pack data;
   the `virtuallasernode` captures (8,324-image laser ground truth); his music library
   files anywhere. Never `git clean -fd` anywhere, ever.
5. macOS purgeable/cache classes (system caches, old iOS backups, Homebrew caches,
   pip/npm caches, Docker if unused, old Downloads) are the natural first hunting
   grounds — still approval-gated.

## Communication (his standing rules)
Plain conversational English, no jargon, no walls of text, no status blocks. ONE clear
digest: a checklist sorted by size — item, what it is in one sentence, Opus's safety
verdict in plain words, recommended yes/no — then wait for his picks. He has inattentive
ADHD: tiny clear steps, no option-overload, no re-explaining things this brief covers.

## Until he attaches
Run the read-only scan + Opus safety analysis and have the digest READY so his first
interaction is approving picks, not waiting. Then stand by. He takes it from there.
