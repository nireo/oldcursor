#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
mkdir -p .build
xcrun swiftc -O -swift-version 6 -warnings-as-errors \
  -target "$(uname -m)-apple-macosx26.0" \
  -module-cache-path .build/module-cache \
  -import-objc-header PrivateCursor.h main.swift Artwork.swift \
  -framework AppKit -framework ApplicationServices -o .build/apple-cursor
# Local ad-hoc signature with hardened runtime, with no exception entitlements.
codesign --force --sign - --identifier local.tiny-apple-cursor --options runtime .build/apple-cursor
./.build/apple-cursor check --all-themes
