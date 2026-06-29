---
doc_status: current
truth_level: tooling-verified
last_verified_commit: f5cfddd
last_verified_date: 2026-06-29
validation_scope: local Graphify CLI 0.9.2, code-only AST graph, no cloud keys, no bridge/runtime/hardware action
---

# Graphify Setup

Graphify is installed locally as the `graphifyy` package through `pipx`; the CLI is `graphify`.
Use it only to orient before reading code. It is not source of truth.

Current repo policy:

- Code-only graph: `.graphifyignore` excludes docs, prompts, archives, captures, logs, images, and generated data.
- No cloud/API-key workflow: do not configure semantic extraction keys for this repo.
- Manual query only: do not enable `graphify hook install`, `graphify claude install`, or `graphify codex install` unless the operator explicitly changes the hook policy.
- `graphify-out/` is generated and gitignored. Regenerate it on demand.
- For live-critical work, open the source files and tests after Graphify points at them. Never act on the map alone.

Useful commands:

```bash
graphify extract .
graphify cluster-only . --no-label
graphify update .
graphify query "what owns active deck state?"
graphify explain "StateManager"
graphify path "LaserDirector" "MidiOutput"
```

After code changes, run `graphify update .` and then `graphify cluster-only . --no-label` if you need
a refreshed `GRAPH_REPORT.md`. `graph.html` may be absent on this repo because the graph is larger
than Graphify's default HTML visualization limit.
