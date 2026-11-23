#!/bin/bash
# Signs Verbalis.app with a «Developer ID Application» certificate for notarization (docs/CODE-SIGNING.md).
#
#   tools/macos/sign_developer_id.sh <Verbalis.app> <identity> <keychain>
#
# Apple wants every piece of code signed on its own, from the inside out (no --deep), each with the hardened
# runtime (--options runtime) and a secure timestamp. Entitlements only on the executables:
# packaging/macos/verbalis.entitlements (app + verbalis-cli), packaging/macos/audiotap.entitlements (helper).
set -euo pipefail

app=$1
identity=$2
keychain=$3
here=$(cd "$(dirname "$0")/../.." && pwd)
entitlements="$here/packaging/macos/verbalis.entitlements"
helper_entitlements="$here/packaging/macos/audiotap.entitlements"

sign() {
  codesign --force --timestamp --options runtime --keychain "$keychain" --sign "$identity" "$@"
}

is_macho() {
  file -b "$1" | grep -q "Mach-O"
}

# 1. every Mach-O file outside Contents/MacOS, deepest path first (libraries, Python extensions, the helper)
count=0
while IFS= read -r f; do
  case "$f" in
    "$app/Contents/MacOS/"*) continue ;;
  esac
  is_macho "$f" || continue
  if [ "$(basename "$f")" = "verbalis-audiotap" ]; then
    sign --identifier ch.frehner.verbalis.audiotap --entitlements "$helper_entitlements" "$f"
    echo "helper: $f"
  else
    sign "$f" >/dev/null
  fi
  count=$((count + 1))
done < <(find "$app/Contents" -type f ! -path "*/_CodeSignature/*" \
           | awk -F/ '{ print NF "\t" $0 }' | sort -rn | cut -f2-)
echo "signed $count Mach-O files"

# 2. nested bundles (e.g. a .framework), innermost first
while IFS= read -r bundle; do
  sign "$bundle"
  echo "bundle: $bundle"
done < <(find "$app/Contents" -depth -type d \( -name "*.framework" -o -name "*.app" -o -name "*.bundle" \))

# 3. the executables in Contents/MacOS (Verbalis, verbalis-cli) with the app's entitlements
for exe in "$app/Contents/MacOS/"*; do
  if [ -f "$exe" ] && [ ! -L "$exe" ] && is_macho "$exe"; then
    sign --entitlements "$entitlements" "$exe"
    echo "executable: $exe"
  fi
done

# 4. the bundle itself (seals resources and Info.plist)
sign --identifier ch.frehner.verbalis --entitlements "$entitlements" "$app"

codesign --verify --strict --deep --verbose=2 "$app"
codesign --display --verbose=2 --entitlements - "$app"
codesign --display --requirements - "$app"
