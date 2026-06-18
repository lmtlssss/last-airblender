#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-1.0.2}"
ARCH_DEB="${ARCH_DEB:-amd64}"
ARCH_ASSET="${ARCH_ASSET:-x86_64}"
BIN="$ROOT/target/release/last-airblender"
[ -x "$BIN" ] || cargo build --release
PKG="$ROOT/target/pkg/last-airblender_${VERSION}_${ARCH_DEB}"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/last-airblender/addon" "$PKG/usr/share/applications" "$PKG/usr/share/doc/last-airblender"
cp "$BIN" "$PKG/usr/bin/last-airblender"
cp "$ROOT/addon/last_airblender.py" "$PKG/usr/share/last-airblender/addon/last_airblender.py"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$PKG/usr/share/doc/last-airblender/"
cat > "$PKG/usr/share/applications/last-airblender.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=The Last AirBlender
Comment=Fly Blender cameras with an Xbox-style controller
Exec=last-airblender launch
Terminal=false
Categories=Graphics;3DGraphics;
DESKTOP
cat > "$PKG/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ] && command -v runuser >/dev/null 2>&1; then
  runuser -u "$SUDO_USER" -- /usr/bin/last-airblender install >/dev/null 2>&1 || true
fi
exit 0
POSTINST
chmod 755 "$PKG/DEBIAN/postinst"
cat > "$PKG/DEBIAN/control" <<CTRL
Package: last-airblender
Version: $VERSION
Section: graphics
Priority: optional
Architecture: $ARCH_DEB
Depends: libc6, libudev1
Maintainer: lmtlssss <lmtlssss@example.com>
Description: Controller camera flight recorder for Blender
 The Last AirBlender lets you fly Blender cameras with an Xbox-style controller and record cinematic takes.
CTRL
mkdir -p "$ROOT/dist"
dpkg-deb --build "$PKG" "$ROOT/dist/last-airblender_${ARCH_ASSET}.deb"
echo "$ROOT/dist/last-airblender_${ARCH_ASSET}.deb"
