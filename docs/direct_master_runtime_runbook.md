# Direct Master Runtime Runbook

Use this runbook to collect repeatable live evidence from the bounded
runtime direct-master observer. This is evidence capture only; it does not
justify master authority promotion by itself.

## Start

From a fresh Terminal:

```bash
cd /Users/bbui
env RBSS_LIVE_BPM_FOLLOW=1 /opt/homebrew/bin/python3 -u -m rb_ss_bridge_v2 2>&1 | tee /tmp/bridge.log
```

If you use the local menu-bar/watcher launcher instead, keep that as the only
bridge instance and capture from `/tmp/bridge.log`.

Recommended runtime capture in a second Terminal:

```bash
tail -n 0 -F /tmp/bridge.log | grep --line-buffered '\[RBMASTER\]\[RUNTIME\]' | tee /tmp/direct_master_runtime_$(date +%Y%m%d_%H%M%S).log
```

Before each run, confirm there is only one bridge process:

```bash
pgrep -fl rb_ss_bridge_v2
```

## Record For Each Run

Copy the full `[RBMASTER][RUNTIME] phase=summary ...` line and record:

- `outcome`
- `final_direct_master`
- `final_tl_master`
- `transition_count`
- `mismatches`
- `first_valid_elapsed_ms`: derive from `first_valid_elapsed_s * 1000`
- `comparison_source`

Also keep the matching `phase=start`, `phase=initial`, `phase=first_valid`,
and first `phase=mismatch` line if present.

Expected fixed wording:

- `comparison_source=tl_master_snapshot`
- `authority=tl_log`

`authority=tl_log` is the fail-closed authority label. The comparison value is
the TL/ENGINE-derived `TLMasterSnapshot`, not bridge-local active-deck state.

## Scenario Checklist

### 1. Startup Into Playback

1. Load a track and start normal playback in Rekordbox.
2. Start the bridge.
3. Do not change master until the runtime summary appears.
4. Capture the summary line.

Encouraging:

- `outcome=became_valid_and_matched_tl`
- `final_direct_master` equals `final_tl_master`
- `transition_count=1`
- `mismatches=0`

Inconclusive:

- `outcome=never_became_valid`
- `outcome=became_valid_without_tl_available`

Concerning:

- `outcome=read_failed`
- `outcome=flapped`
- `mismatches>0` without an obvious TL timing race

### 2. Stable Playback, No Master Change

1. Start the bridge with a known Rekordbox master deck.
2. Keep playback stable and do not switch master during the bounded window.
3. Capture the summary line.

Encouraging:

- `outcome=became_valid_and_matched_tl`
- `transition_count=1`
- `mismatches=0`
- final direct and TL masters match the known master

Inconclusive:

- direct never becomes valid, but TL remains correct

Concerning:

- `transition_count>1` without an intentional master switch
- `final_direct_master` differs from `final_tl_master`
- `flapped`

### 3. Intentional Single Master Switch

1. Start the bridge.
2. During the bounded runtime window, switch master exactly once between decks.
3. Do not switch it again before the summary appears.
4. Capture the summary line and any first `phase=mismatch` line.

Encouraging:

- `transition_count=2`
- `outcome=became_valid_and_matched_tl`
- `final_direct_master` equals `final_tl_master`
- `mismatches=0`

Inconclusive:

- `became_valid_without_tl_available`
- small `mismatches` count that lines up with a plausible direct-vs-TL timing
  race around the manual switch

Concerning:

- `transition_count>2`
- direct returns to `none` after first valid
- `flapped`
- final direct and TL masters disagree after the switch has settled

## Outcome Reference

- `read_failed`: unsupported offsets, attach failure, or unreadable direct
  chain.
- `never_became_valid`: direct stayed readable but remained `none`.
- `became_valid_and_matched_tl`: direct became valid and all valid comparisons
  matched TL.
- `became_valid_but_mismatched_tl`: at least one valid direct-vs-valid TL poll
  disagreed.
- `became_valid_without_tl_available`: direct became valid before TL snapshot
  had `deck1` or `deck2`.
- `flapped`: direct returned to `none` after first valid, or had more than one
  valid deck transition.

Stop after these three scenarios. More runtime evidence can support a later
decision, but this runbook does not add promotion, arbitration, or broader
observer behavior.
