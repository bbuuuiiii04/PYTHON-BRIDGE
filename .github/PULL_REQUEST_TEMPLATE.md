## Summary

Describe what changed and why.

## Change type

- [ ] docs-only
- [ ] runtime behavior
- [ ] tests
- [ ] config/schema
- [ ] validation/status docs

## Agent context used

- [ ] Read `AGENTS.md`
- [ ] Read relevant task playbook
- [ ] Read relevant subsystem card
- [ ] Followed `docs/agents/change_contracts.md`
- [ ] Checked `docs/agents/change_contracts.yml` for required docs/tests

## Status/validation claims

- [ ] I did not claim production-ready, show-ready, plug-and-play, broad compatibility, general support, or hardware validation without evidence.
- [ ] I preserved early-alpha status unless explicit evidence supports a change.
- [ ] I preserved SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED unless validation docs prove otherwise.

## Tests/checks

- [ ] `python3 tools/check_docs_metadata.py`
- [ ] `python3 tools/check_agent_contracts.py`
- [ ] `python3 tools/check_docs_drift.py`
- [ ] `python3 -m unittest discover tests`
- [ ] Tests not run, explained below

## Docs updated

- [ ] README/AGENTS if public/agent behavior changed
- [ ] subsystem card if subsystem behavior changed
- [ ] support matrix if compatibility changed
- [ ] validation matrix if validation evidence changed
- [ ] active work registry if unfinished work changed
- [ ] doc index (`docs/architecture/doc_index.md`) if docs were reclassified
- [ ] runtime command docs if command parser/status surface changed
- [ ] task playbook/change contract if workflow changed

## Drift check

- [ ] Runtime command docs still match `runtime_status.py`
- [ ] Change contracts still point to existing files
- [ ] No old prompts/plans were treated as current truth without code verification

## Safety

- [ ] No local backup files staged
- [ ] No secrets/API keys/local IPs committed
- [ ] No unrelated runtime behavior changed
- [ ] No tests changed just to hide failures

## Notes

Add failures, skipped checks, or uncertainty here.
