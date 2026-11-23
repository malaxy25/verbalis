#!/bin/bash
# Sends a signed Verbalis.app or .dmg to Apple's notary service, waits and staples the ticket
# (docs/CODE-SIGNING.md). Needs an App Store Connect API key:
#
#   APPLE_API_KEY_FILE=AuthKey.p8 APPLE_API_KEY_ID=… APPLE_API_ISSUER=… tools/macos/notarize.sh <file>
set -euo pipefail

target=$1
: "${APPLE_API_KEY_FILE:?}" "${APPLE_API_KEY_ID:?}" "${APPLE_API_ISSUER:?}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

case "$target" in
  *.app)
    codesign --verify --strict --deep "$target"     # nothing changed since signing (e.g. by the self-test)
    upload="$work/$(basename "$target" .app).zip"
    ditto -c -k --keepParent "$target" "$upload"
    ;;
  *)
    upload=$target
    ;;
esac

xcrun notarytool submit "$upload" \
  --key "$APPLE_API_KEY_FILE" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" \
  --wait --timeout 45m --output-format json | tee "$work/result.json"
echo
id=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('id', ''))" "$work/result.json")
status=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1])).get('status', ''))" "$work/result.json")
if [ "$status" != "Accepted" ]; then
  echo "::error::Notarization of $(basename "$target") failed: ${status:-no answer}"
  if [ -n "$id" ]; then
    xcrun notarytool log "$id" \
      --key "$APPLE_API_KEY_FILE" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" || true
  fi
  exit 1
fi

xcrun stapler staple "$target"
xcrun stapler validate "$target"
case "$target" in
  *.app) spctl --assess --type execute --verbose=4 "$target" ;;
  *.dmg) spctl --assess --type open --context context:primary-signature --verbose=4 "$target" ;;
esac
echo "notarized: $target"
