# Security and Safety Notes

This project reads local Rekordbox runtime state and can drive lighting hardware. Treat it as local, experimental tooling.

## Scope

Security concerns worth reporting include:

- accidental secret exposure
- local config or device IDs committed to the repo
- unsafe network binding defaults
- command parser hardening issues
- behavior that could accidentally drive lighting hardware without explicit operator intent

## Out of scope

This is not a hosted service and not a packaged product. Broad production security support is not claimed.

## Local secrets

Govee API keys, device IDs, local config, and generated backup files must stay out of git.
