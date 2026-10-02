#!/bin/bash
# Construit la fenêtre native de Gambit Ridge Capital avec swiftc (sans Xcode)
# puis fabrique le bundle .app complet et l'installe dans ~/Applications.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SRC_DIR/mac"

echo "→ Compilation de la fenêtre native…"
swiftc -O -o "GambitRidgeCapital" GambitRidgeCapital.swift -framework Cocoa -framework WebKit -framework Speech -framework AVFoundation
echo "✓ Binaire natif : $SRC_DIR/mac/GambitRidgeCapital"

APP="$SRC_DIR/mac/Gambit Ridge Capital.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "GambitRidgeCapital" "$APP/Contents/MacOS/Gambit Ridge Capital"
chmod +x "$APP/Contents/MacOS/Gambit Ridge Capital"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Gambit Ridge Capital</string>
  <key>CFBundleIdentifier</key><string>com.gambitridgecapital.app</string>
  <key>CFBundleVersion</key><string>25</string>
  <key>CFBundleExecutable</key><string>Gambit Ridge Capital</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Le micro sert à parler à tes agents dans l'onglet Voix.</string>
  <key>NSSpeechRecognitionUsageDescription</key><string>La dictée transforme ta voix en question pour tes agents (sur l'appareil quand c'est possible).</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
</dict>
</plist>
PLIST

if [ -f "$SRC_DIR/mac/icon.icns" ]; then
  cp "$SRC_DIR/mac/icon.icns" "$APP/Contents/Resources/icon.icns"
  plutil -replace CFBundleIconFile -string "icon" "$APP/Contents/Info.plist"
fi

# signature ad hoc : macOS rattache les autorisations micro/dictée à l'identifiant de l'app
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
echo "✓ Bundle .app : $APP"

DEST="$HOME/Applications"
mkdir -p "$DEST"
rm -rf "$DEST/Gambit Ridge Capital.app"
cp -R "$APP" "$DEST/"
echo "✓ Installée dans ~/Applications — glisse-la dans ton dock."
