#!/usr/bin/env sh
set -eu
REPO="lmtlssss/last-airblender"
VERSION="${LAST_AIRBLENDER_VERSION:-latest}"
TMP="$(mktemp -d)"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) arch="x86_64" ;;
  aarch64|arm64) arch="aarch64" ;;
  *) echo "unsupported arch: $arch" >&2; exit 1 ;;
esac
if [ "$VERSION" = "latest" ]; then
  base="https://github.com/$REPO/releases/latest/download"
else
  base="https://github.com/$REPO/releases/download/$VERSION"
fi
if [ "$os" = "linux" ]; then
  if command -v apt-get >/dev/null 2>&1 || command -v dpkg >/dev/null 2>&1; then
    asset="last-airblender_${arch}.deb"
    installer="sudo apt install -y"
  elif command -v rpm >/dev/null 2>&1; then
    asset="last-airblender_${arch}.rpm"
    installer="sudo rpm -Uvh"
  else
    asset="last-airblender_linux_${arch}.tar.gz"
    installer="tarball"
  fi
elif [ "$os" = "darwin" ]; then
  asset="last-airblender_${arch}.pkg"
  installer="sudo installer -pkg"
else
  echo "unsupported OS for install.sh: $os" >&2
  exit 1
fi
curl -fsSL "$base/checksums.txt" -o "$TMP/checksums.txt"
curl -fL "$base/$asset" -o "$TMP/$asset"
verify_checksum() {
  expected="$(grep "  $asset$" "$TMP/checksums.txt" | awk '{print $1}' || true)"
  if [ -z "$expected" ]; then
    echo "checksum missing for $asset" >&2
    exit 1
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$TMP/$asset" | awk '{print $1}')"
  else
    actual="$(shasum -a 256 "$TMP/$asset" | awk '{print $1}')"
  fi
  if [ "$actual" != "$expected" ]; then
    echo "checksum mismatch for $asset" >&2
    exit 1
  fi
}
verify_checksum
if [ "$installer" = "tarball" ]; then
  mkdir -p "$HOME/.local/bin"
  tar -xzf "$TMP/$asset" -C "$HOME/.local/bin"
  echo "installed to $HOME/.local/bin"
elif [ "$os" = "darwin" ]; then
  sudo installer -pkg "$TMP/$asset" -target /
else
  $installer "$TMP/$asset"
fi
if ! command -v last-airblender >/dev/null 2>&1 && [ -x "$HOME/.local/bin/last-airblender" ]; then
  PATH="$HOME/.local/bin:$PATH"
fi
last-airblender install || true
last-airblender doctor || true
