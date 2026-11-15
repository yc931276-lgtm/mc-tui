#!/usr/bin/env bash
set -euo pipefail

# Determine repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo " Building Debian package for mc-tui"
echo "=========================================="

# 1. Run test suite
echo "==> Running unit tests..."
PYTHONPATH="$SCRIPT_DIR" python3 -m unittest discover -s tests

# 2. Extract version and metadata
PKG_NAME="mc-tui"
PKG_VERSION="$(grep -E '^Version:' debian/control | awk '{print $2}')"
ARCH="$(grep -E '^Architecture:' debian/control | awk '{print $2}')"
DEB_FILENAME="${PKG_NAME}_${PKG_VERSION}_${ARCH}.deb"

BUILD_DIR="$SCRIPT_DIR/build/deb-staging"
DIST_DIR="$SCRIPT_DIR/dist"
OUTPUT_DEB="$DIST_DIR/$DEB_FILENAME"

echo "==> Package: $PKG_NAME"
echo "==> Version: $PKG_VERSION"
echo "==> Architecture: $ARCH"

# 3. Clean previous build staging
rm -rf "$SCRIPT_DIR/build"
rm -rf "$DIST_DIR"
mkdir -p "$BUILD_DIR"
mkdir -p "$DIST_DIR"

# 4. Prepare directory layout
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/lib/python3/dist-packages/mc_tui"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$BUILD_DIR/usr/share/man/man1"
mkdir -p "$BUILD_DIR/usr/share/doc/$PKG_NAME"

# 5. Copy executable binary
echo "==> Installing /usr/bin/mc-tui..."
install -m 755 "$SCRIPT_DIR/debian/bin-mc-tui" "$BUILD_DIR/usr/bin/mc-tui"

# 6. Copy Python modules (excluding caches)
echo "==> Installing Python package files..."
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude '*.pyo' \
    "$SCRIPT_DIR/mc_tui/" "$BUILD_DIR/usr/lib/python3/dist-packages/mc_tui/"

# 6b. Generate build metadata for the About page
echo "==> Generating build metadata..."
python3 - "$BUILD_DIR/usr/lib/python3/dist-packages/mc_tui/build_info.py" <<'PY'
import datetime
import json
import os
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
epoch = os.environ.get("SOURCE_DATE_EPOCH")
if epoch:
    build_time = datetime.datetime.fromtimestamp(
        int(epoch), tz=datetime.timezone.utc
    ).isoformat(timespec="seconds")
else:
    build_time = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
target.write_text(
    '"""Generated build metadata (do not edit)."""\n'
    f"BUILD_TIME = {json.dumps(build_time)}\n",
    encoding="utf-8",
)
PY
chmod 644 "$BUILD_DIR/usr/lib/python3/dist-packages/mc_tui/build_info.py"

# 7. Desktop entry and icons
echo "==> Installing desktop entry and icon..."
install -m 644 "$SCRIPT_DIR/debian/mc-tui.desktop" "$BUILD_DIR/usr/share/applications/mc-tui.desktop"
install -m 644 "$SCRIPT_DIR/debian/mc-tui.svg" "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/mc-tui.svg"

# 8. Man page
echo "==> Compressing and installing man page..."
gzip -9n -c "$SCRIPT_DIR/debian/mc-tui.1" > "$BUILD_DIR/usr/share/man/man1/mc-tui.1.gz"
chmod 644 "$BUILD_DIR/usr/share/man/man1/mc-tui.1.gz"

# 9. Documentation and changelog
echo "==> Installing documentation..."
install -m 644 "$SCRIPT_DIR/README.md" "$BUILD_DIR/usr/share/doc/$PKG_NAME/README.md"
install -m 644 "$SCRIPT_DIR/README.zh-CN.md" "$BUILD_DIR/usr/share/doc/$PKG_NAME/README.zh-CN.md"
install -m 644 "$SCRIPT_DIR/debian/copyright" "$BUILD_DIR/usr/share/doc/$PKG_NAME/copyright"
gzip -9n -c "$SCRIPT_DIR/debian/changelog" > "$BUILD_DIR/usr/share/doc/$PKG_NAME/changelog.Debian.gz"
chmod 644 "$BUILD_DIR/usr/share/doc/$PKG_NAME/changelog.Debian.gz"

# 10. Normalize file & directory permissions in payload
find "$BUILD_DIR/usr" -type d -exec chmod 755 {} +
find "$BUILD_DIR/usr" -type f -exec chmod u=rw,go=r {} +
chmod 755 "$BUILD_DIR/usr/bin/mc-tui"

# 11. Calculate installed size (in KB)
INSTALLED_SIZE=$(du -sk "$BUILD_DIR/usr" | awk '{print $1}')

# 12. Create DEBIAN/control with Installed-Size
cp "$SCRIPT_DIR/debian/control" "$BUILD_DIR/DEBIAN/control"
if ! grep -q "^Installed-Size:" "$BUILD_DIR/DEBIAN/control"; then
    echo "Installed-Size: $INSTALLED_SIZE" >> "$BUILD_DIR/DEBIAN/control"
fi
chmod 644 "$BUILD_DIR/DEBIAN/control"

# 13. Maintainer scripts
install -m 755 "$SCRIPT_DIR/debian/postinst" "$BUILD_DIR/DEBIAN/postinst"
install -m 755 "$SCRIPT_DIR/debian/prerm" "$BUILD_DIR/DEBIAN/prerm"

# 14. Generate md5sums for all files in payload
echo "==> Generating DEBIAN/md5sums..."
(
    cd "$BUILD_DIR"
    find usr -type f -exec md5sum {} + > DEBIAN/md5sums
    chmod 644 DEBIAN/md5sums
)

# 15. Build the .deb file with dpkg-deb
echo "==> Building .deb archive with dpkg-deb..."
dpkg-deb --root-owner-group --build "$BUILD_DIR" "$OUTPUT_DEB"

echo ""
echo "=========================================="
echo " Package successfully built!"
echo " Location: $OUTPUT_DEB"
echo "=========================================="
echo ""

# 16. Inspect package info and contents
echo "--- Package Information ---"
dpkg-deb -I "$OUTPUT_DEB"
echo ""
echo "--- Package File Contents ---"
dpkg-deb -c "$OUTPUT_DEB"
