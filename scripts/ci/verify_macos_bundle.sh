#!/usr/bin/env bash
# Check a built macOS bundle: one .app holding a universal (arm64 + x86_64) binary with a
# valid code signature, and one .dmg. Prints the signing authority so a release can tell
# a Developer ID build from an ad-hoc one. Usage: verify_macos_bundle.sh <bundle-dir>
set -euo pipefail
bundle_dir="$1"
shopt -s nullglob
apps=("$bundle_dir"/macos/*.app)
dmgs=("$bundle_dir"/dmg/*.dmg)
[ "${#apps[@]}" -eq 1 ] || { echo "expected one .app, found ${#apps[@]}" >&2; exit 1; }
[ "${#dmgs[@]}" -eq 1 ] || { echo "expected one .dmg, found ${#dmgs[@]}" >&2; exit 1; }
app="${apps[0]}"
binary="$app/Contents/MacOS/$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app/Contents/Info.plist")"
archs="$(lipo -archs "$binary")"
case " $archs " in *" arm64 "*) ;; *) echo "missing arm64 slice: $archs" >&2; exit 1 ;; esac
case " $archs " in *" x86_64 "*) ;; *) echo "missing x86_64 slice: $archs" >&2; exit 1 ;; esac
codesign --verify --deep --strict --verbose=2 "$app"
codesign -dv "$app" 2>&1 | grep -E '^(Authority|Signature|TeamIdentifier)=' || true
hdiutil verify "${dmgs[0]}"
echo "macOS bundle OK: $(basename "$app") [$archs], $(basename "${dmgs[0]}")"
