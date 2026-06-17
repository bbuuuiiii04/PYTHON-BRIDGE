---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Validation Policy

## Rule

Software tests and hardware validation are separate.

A passing test suite can support `software-tested`. It cannot support `hardware-validated` unless paired with an explicit hardware-validation record.

## Required matrices

When validation changes, update:

- `docs/status/validation_matrix.md`
- `docs/validation/software_test_inventory.md`
- `docs/validation/hardware_validation_log.md` when hardware is involved
- `docs/status/support_matrix.md` when compatibility changes
