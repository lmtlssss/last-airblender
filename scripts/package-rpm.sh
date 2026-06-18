#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${VERSION:-1.0.0}"
ARCH_ASSET="${ARCH_ASSET:-x86_64}"
BIN="$ROOT/target/release/last-airblender"
[ -x "$BIN" ] || cargo build --release
WORK="$ROOT/target/rpm"
rm -rf "$WORK"
mkdir -p "$WORK/BUILD" "$WORK/BUILDROOT" "$WORK/RPMS" "$WORK/SOURCES" "$WORK/SPECS" "$WORK/SRPMS"
TAR="$WORK/SOURCES/last-airblender-$VERSION.tar.gz"
TMP="$WORK/last-airblender-$VERSION"
mkdir -p "$TMP/usr/bin" "$TMP/usr/share/last-airblender/addon" "$TMP/usr/share/applications" "$TMP/usr/share/doc/last-airblender"
cp "$BIN" "$TMP/usr/bin/last-airblender"
cp "$ROOT/addon/last_airblender.py" "$TMP/usr/share/last-airblender/addon/last_airblender.py"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$TMP/usr/share/doc/last-airblender/"
cat > "$TMP/usr/share/applications/last-airblender.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=The Last AirBlender
Comment=Fly Blender cameras with an Xbox-style controller
Exec=last-airblender launch
Terminal=false
Categories=Graphics;3DGraphics;
DESKTOP
(cd "$WORK" && tar -czf "$TAR" "last-airblender-$VERSION")
cat > "$WORK/SPECS/last-airblender.spec" <<SPEC
Name: last-airblender
%global debug_package %{nil}
Version: $VERSION
Release: 1%{?dist}
Summary: Controller camera flight recorder for Blender
License: MIT
BuildArch: x86_64
Source0: last-airblender-$VERSION.tar.gz
Requires: systemd-libs

%description
The Last AirBlender lets you fly Blender cameras with an Xbox-style controller and record cinematic takes.

%prep
%setup -q

%build

%install
mkdir -p %{buildroot}
cp -a usr %{buildroot}/

%post
if [ -n "\${SUDO_USER:-}" ] && [ "\$SUDO_USER" != "root" ] && command -v runuser >/dev/null 2>&1; then
  runuser -u "\$SUDO_USER" -- /usr/bin/last-airblender install >/dev/null 2>&1 || true
fi

%files
/usr/bin/last-airblender
/usr/share/last-airblender/addon/last_airblender.py
/usr/share/applications/last-airblender.desktop
/usr/share/doc/last-airblender/README.md
/usr/share/doc/last-airblender/LICENSE
SPEC
rpmbuild --define "_topdir $WORK" -bb "$WORK/SPECS/last-airblender.spec"
mkdir -p "$ROOT/dist"
cp "$WORK"/RPMS/*/*.rpm "$ROOT/dist/last-airblender_${ARCH_ASSET}.rpm"
echo "$ROOT/dist/last-airblender_${ARCH_ASSET}.rpm"
