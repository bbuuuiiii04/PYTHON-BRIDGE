Target: Claude Opus 4.8, effort xhigh, max-output ~64k.

Ghidra MCP is set up for reverse engineering rekordbox 7.2.16.0342 (just updated). Claude did setup only, no RE work.

State:
- Project: `~/Desktop/Ghidra Projects/Rekordbox Mixer RE.gpr` (open with `/Users/bbui/Desktop/ghidra_11.3.2_PUBLIC/ghidraRun`, NOT the Homebrew 12.1.2 one — incompatible plugin manifest).
- New program `rekordbox_7.2.16_arm64` headless-imported into that project (arm64 slice of `/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox`). Auto-analysis was still running as of handoff — check it finished before trusting decompilation output.
- An older program already existed in the same project from a prior rekordbox version (imported Jun 28) — left untouched, useful for diffing.
- `Ghidra: TimecodeLink RE` was the active project/tool when work stopped — you'll need to close it and open `Rekordbox Mixer RE` instead (Ghidra only holds one active project per instance).
- Opening `rekordbox_7.2.16_arm64` in a CodeBrowser tool is what starts GhidraMCP's HTTP server on :8080 — verify with `curl -s http://127.0.0.1:8080/methods` before using the `mcp__ghidra__*` tools.

Gotchas hit during setup:
- Screen is 2x Retina. `screencapture` pixel coordinates must be divided by 2 before passing to `cliclick` (which uses logical points) — get exact window rects from `System Events` (`position`/`size` of window) rather than eyeballing screenshots.
- The real rekordbox app may be open/running live on screen (user's actual DJ library) — never click into it.
- `-analyze` is not a valid `analyzeHeadless` flag; analysis runs by default unless `-noanalysis` is passed.

Your job: do the actual RE — analyze/decompile as needed, verify against the current binary, don't guess.
