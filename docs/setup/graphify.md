---
doc_status: current
truth_level: tooling-verified
last_verified_commit: 9705363
last_verified_date: 2026-07-03
validation_scope: local Graphify CLI 0.9.2, code-only graph, no cloud keys, manual-query only, no bridge/runtime/hardware action
---

# Graphify Setup

Graphify is installed locally as the `graphifyy` package through `pipx`; the CLI is `graphify`.
Use it only to orient before reading code. It is not source of truth.

Current repo policy:

- Code-only graph: `.graphifyignore` excludes docs, prompts, archives, captures, logs, images,
  experiments, local scratch, and generated data. The current manifest keeps repo-root code,
  `scripts/`, `streamdeck/`, `tests/`, `tools/`, and the tracked `config/*.example.json` files.
- No cloud/API-key workflow: do not configure semantic extraction keys for this repo.
- Manual query only: do not enable `graphify hook install`, `graphify claude install`, or
  `graphify codex install` unless the operator explicitly changes the hook policy. Hooks are
  avoided because a read-interception or post-commit graph workflow can add latency, serve a stale
  graph, and make agents over-trust generated edges.
- `graphify-out/` is generated and gitignored. Regenerate it on demand.
- For live-critical work, open the source files and tests after Graphify points at them. Never act on
  the map alone.
- Do not use `graphify plan`; the local 0.9.2 CLI help does not list that command.

## When to Use It

Use Graphify for broad orientation:

- "Where does this concept live?"
- "What files are near this symbol?"
- "What might be affected if I inspect this module?"
- "Which clusters should I read before editing a subsystem?"

Skip Graphify when `rg` is cheaper:

- exact symbol, string, line, or known-file lookup
- source/test confirmation of an architecture claim
- current live behavior, runtime state, config state, hardware behavior, or process status
- anything where a shortest path would be mistaken for a real call chain

Never report Graphify output as confirmed architecture, ownership, call flow, blast radius, or live
behavior. `INFERRED` / `AMBIGUOUS` edges and shortest paths are leads only.

## Rebuild and Update

For serious review, after deletions/refactors, or when stale graph risk matters, do a clean rebuild
of the ignored output:

```bash
rm -rf graphify-out
graphify extract . --no-cluster
graphify cluster-only . --no-label
```

## Freshness & Blind Spots

Rebuild before orientation-heavy work, after deletion/refactor sweeps, or after multi-day commit
bursts. A quick freshness check:

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess
git_ts = int(subprocess.check_output(["git", "log", "-1", "--format=%ct"]).strip())
graph = Path("graphify-out/graph.json")
print("graph_fresh", graph.exists() and int(graph.stat().st_mtime) >= git_ts)
PY
```

Known blind spots: dynamic imports, config-driven dispatch, environment-flag paths, hardware-only
behavior, gitignored `local/` data, generated captures, and any runtime state outside the checked-in
code graph. The graph is an orientation lead, never authority. `INFERRED` and `AMBIGUOUS` edges
need source and test confirmation before they become claims.

Manual-only policy is unchanged: no hooks, no CI, no read-interception workflow, and no post-commit
Graphify automation unless the operator explicitly changes that decision.

For quick local orientation after small code edits, an incremental update is acceptable:

```bash
graphify update . --no-cluster
graphify cluster-only . --no-label
```

If you intentionally delete or rename code and do not clean rebuild, use the CLI's deletion-aware
flag:

```bash
graphify update . --force --no-cluster
graphify cluster-only . --no-label
```

`graph.html` may be absent on this repo because the graph is larger than Graphify's default HTML
visualization limit.

Useful query commands:

```bash
graphify --help
graphify diagnose multigraph --graph graphify-out/graph.json --max-examples 8
graphify query "what owns active deck state?"
graphify explain "StateManager"
graphify path "LaserDirector" "MidiOutput"
graphify affected "soundswitch_frame_sender.py" --depth 2
```

## Known Misread: Laser Path

Do not trust `graphify path "LaserDirector" "MidiOutput"` as the runtime laser execution chain. A
shortest path can be an import/startup neighborhood. One prior graph returned a shortest path through
`__main__.py`; the current graph returned:

```text
LaserDirector <--uses [INFERRED]-- LaserStartupBundle --uses [INFERRED]--> MidiOutput
```

That is a lead, not a claim that laser policy directly executes MIDI. Confirm laser flow in source:
`laser_director.py` owns policy, `laser_executor.py` resolves decisions, `laser_output_backend.py`
adapts output, `midi_output.py` sends MIDI, and `__main__.py` wires startup.

## Rebuild Smoke Test

After a clean rebuild, run these small checks before relying on the graph for orientation:

```bash
graphify diagnose multigraph --graph graphify-out/graph.json --max-examples 8
graphify explain "StateManager" --graph graphify-out/graph.json
graphify path "LaserDirector" "MidiOutput" --graph graphify-out/graph.json
python3 - <<'PY'
import json
from collections import Counter
from pathlib import Path
data = json.loads(Path("graphify-out/graph.json").read_text())
links = data.get("links") or data.get("edges") or []
print("nodes", len(data.get("nodes", [])))
print("links", len(links))
print("confidence", dict(Counter(e.get("confidence", "<missing>") for e in links)))
print("relations", dict(Counter(e.get("relation", "<missing>") for e in links).most_common()))
print("json_nodes", sum(".json" in str(n) for n in data.get("nodes", [])))
PY
```

Expected shape as of local CLI 0.9.2 on `56a505e`:

- `graphify diagnose multigraph` reports no missing endpoints, dangling endpoints, self-loops, exact
  duplicates, or same-endpoint collapsed edges.
- `graphify explain "StateManager"` points at `state_manager.py`.
- `graphify path "LaserDirector" "MidiOutput"` may return a short `INFERRED` path. Treat that as a
  warning to open source, not as a pass/fail architecture proof.
- The graph has thousands of code nodes and links, with both `EXTRACTED` and `INFERRED` confidence.
- The tracked example JSON configs are listed in `graphify-out/manifest.json`, but they are not
  represented as graph nodes in the current build. Do not claim queryable config-graph coverage.
