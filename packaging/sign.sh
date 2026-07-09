#!/bin/bash
# Re-runnable code-signing for the RBSS Bridge .app (USB launcher M1).
#
# Uses an Apple Development identity if one exists on this Mac (idea-8: a stable
# TCC identity so memory/Local-Network grants survive rebuilds), else falls back
# to ad-hoc signing (`-s -`), which satisfies Apple silicon's
# must-be-signed-to-run rule for local use. The Apple Development cert could not
# be minted on the build night (Xcode needs ~40 GB); re-run this once the cert
# exists to upgrade the signature without rebuilding.
set -euo pipefail

APP="${1:-dist/RBSS Bridge.app}"
if [ ! -d "$APP" ]; then
    echo "sign.sh: no app bundle at '$APP'" >&2
    exit 1
fi

IDENTITY="$(security find-identity -v -p codesigning \
    | grep -o '"Apple Development[^"]*"' | head -1 | tr -d '"' || true)"

if [ -n "$IDENTITY" ]; then
    echo "sign.sh: signing with Apple Development identity: $IDENTITY"
    codesign --force --deep -s "$IDENTITY" "$APP"
else
    echo "sign.sh: no Apple Development identity found — ad-hoc signing (-s -)"
    codesign --force --deep -s - "$APP"
fi

codesign --verify --deep --strict --verbose=2 "$APP"
echo "sign.sh: signed OK -> $APP"
