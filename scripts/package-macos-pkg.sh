#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-1.0.0}"
ARCH_ASSET="${ARCH_ASSET:-$(uname -m)}"
BIN="$ROOT/target/release/last-airblender"
[ -x "$BIN" ] || cargo build --release
PKGROOT="$ROOT/target/pkg/macos-root"
rm -rf "$PKGROOT"
mkdir -p "$PKGROOT/usr/local/bin" "$PKGROOT/usr/local/share/last-airblender/addon"
cp "$BIN" "$PKGROOT/usr/local/bin/last-airblender"
cp "$ROOT/addon/last_airblender.py" "$PKGROOT/usr/local/share/last-airblender/addon/last_airblender.py"
mkdir -p "$ROOT/dist"
pkgbuild --root "$PKGROOT" --identifier "dev.lmtlssss.last-airblender" --version "$VERSION" --install-location / "$ROOT/dist/last-airblender_${ARCH_ASSET}.pkg"
echo "$ROOT/dist/last-airblender_${ARCH_ASSET}.pkg"
