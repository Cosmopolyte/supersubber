#!/usr/bin/env bash
# Builds the portable Linux package (PyInstaller onedir) and packs it twice:
#   dist/supersubber-<version>-linux-x86_64.tar.gz   — unpack anywhere, run ./supersubber
#   dist/supersubber-<version>-x86_64.AppImage       — single file, chmod +x and run
# Needs: .venv with requirements.txt, bin/ filled by fetch-bins.sh. Built and tested on Debian 13.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
ver="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' supersubber/__init__.py)"
arch="$(uname -m)"

for b in alass-cli ffmpeg ffprobe; do
    [ -x "bin/$b" ] || { echo "bin/$b missing — run ./fetch-bins.sh first"; exit 1; }
done

# PyInstaller logs everything to stderr; only surface the interesting lines but keep its exit code.
set +o pipefail
"$PY" -m PyInstaller --noconfirm --clean --windowed --name supersubber \
    --add-data "bin:bin" \
    --add-data "assets:assets" \
    --add-data "THIRD-PARTY.md:." \
    --collect-all subliminal --copy-metadata subliminal \
    --collect-all guessit --collect-all babelfish --copy-metadata babelfish \
    --collect-all tkinterdnd2 \
    --collect-all keyring --copy-metadata keyring \
    --collect-all secretstorage --collect-all jeepney \
    --hidden-import dogpile.cache.backends.memory \
    run.py 2>&1 | grep -E 'ERROR|WARNING: Hidden import|not found|Traceback' || true
rc=${PIPESTATUS[0]}
set -o pipefail
[ "$rc" -eq 0 ] || { echo "PyInstaller failed (exit $rc)"; exit 1; }
chmod +x dist/supersubber/_internal/bin/alass-cli dist/supersubber/_internal/bin/ffmpeg dist/supersubber/_internal/bin/ffprobe

tarball="dist/supersubber-${ver}-linux-${arch}.tar.gz"
rm -f "$tarball"
tar czf "$tarball" -C dist supersubber
echo "Done: $tarball ($(du -m "$tarball" | cut -f1) MB)"

# AppImage: the onedir under opt/, AppRun forwards the arguments. appimagetool is fetched once into build/.
appdir="build/AppDir"
rm -rf "$appdir"
mkdir -p "$appdir/opt"
cp -a dist/supersubber "$appdir/opt/supersubber"
cp assets/supersubber.desktop "$appdir/"
cp assets/icon_256.png "$appdir/supersubber.png"
ln -sf supersubber.png "$appdir/.DirIcon"
cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/opt/supersubber/supersubber" "$@"
EOF
chmod +x "$appdir/AppRun"

tool="build/appimagetool-${arch}.AppImage"
if [ ! -x "$tool" ]; then
    curl -sSL -o "$tool" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${arch}.AppImage"
    chmod +x "$tool"
fi
appimage="dist/supersubber-${ver}-${arch}.AppImage"
rm -f "$appimage"
ARCH="$arch" "$tool" --appimage-extract-and-run "$appdir" "$appimage" 2>&1 | grep -v -E '^(Using|WARNING: AppStream|.*appstream)' || true
[ -s "$appimage" ] || { echo "AppImage not created"; exit 1; }
chmod +x "$appimage"
echo "Done: $appimage ($(du -m "$appimage" | cut -f1) MB)"
