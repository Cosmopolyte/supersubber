#!/usr/bin/env bash
# Downloads alass and a static ffmpeg/ffprobe build into bin/ — needed for development and build on Linux.
# License texts for both are tracked in the repo (bin/LICENSE-alass.txt, bin/LICENSE-ffmpeg-linux.txt).
set -euo pipefail
cd "$(dirname "$0")"

ALASS_URL="https://github.com/kaegi/alass/releases/download/v2.0.0/alass-linux64"
FFMPEG_VER="7.0.2"
FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-${FFMPEG_VER}-amd64-static.tar.xz"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p bin

echo "alass ..."
curl -sSL -o bin/alass-cli "$ALASS_URL"
chmod +x bin/alass-cli

echo "ffmpeg ${FFMPEG_VER} static ..."
curl -sSL -o "$tmp/ffmpeg.tar.xz" "$FFMPEG_URL"
tar xJf "$tmp/ffmpeg.tar.xz" -C "$tmp"
src="$(ls -d "$tmp"/ffmpeg-*-static)"
cp "$src/ffmpeg" "$src/ffprobe" bin/
chmod +x bin/ffmpeg bin/ffprobe

echo "bin/ populated:"
ls -l bin
bin/alass-cli --version
bin/ffmpeg -version | head -1
