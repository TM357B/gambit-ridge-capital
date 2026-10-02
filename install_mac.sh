#!/bin/bash
# Installe Gambit Ridge Capital en application Mac (.app) avec icône dans le dock.
# Usage : bash install_mac.sh
set -euo pipefail

APP_NAME="Gambit Ridge Capital"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST_DIR="$HOME/Applications"
APP_DIR="$DEST_DIR/$APP_NAME.app"

echo "→ Installation de $APP_NAME dans $DEST_DIR…"

if [ -d "$APP_DIR" ]; then
  echo "  ! $APP_DIR existe déjà — mise à jour."
  rm -rf "$APP_DIR"
fi

mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

# Lancement : fenêtre native Swift si compilée, sinon serveur + navigateur
chmod +x "$SRC_DIR/run_server.sh" 2>/dev/null || true
if [ -x "$SRC_DIR/mac/GambitRidgeCapital" ]; then
  cp "$SRC_DIR/mac/GambitRidgeCapital" "$APP_DIR/Contents/MacOS/$APP_NAME"
else
  cat > "$APP_DIR/Contents/MacOS/$APP_NAME" <<HEREDOC
#!/bin/bash
cd "$SRC_DIR"
bash "$SRC_DIR/run_server.sh" &
SERVER_PID=\$!
sleep 2
open "http://127.0.0.1:8765"
wait \$SERVER_PID
HEREDOC
  chmod +x "$APP_DIR/Contents/MacOS/$APP_NAME"
fi

# Icône : carré stylisé "M" doré généré via SVG -> PNG -> icns via sips/qlmanage
cat > "/tmp/grc_icon.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#1a2233"/>
      <stop offset="1" stop-color="#0d1117"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="96" fill="url(#g)"/>
  <path d="M256 120 C 200 190 130 210 100 200 C 120 260 140 330 150 400 L 200 360 C 230 300 260 240 300 200 C 330 240 360 300 380 360 L 420 400 C 420 320 440 250 460 190 C 420 200 360 180 310 130 Z" fill="none" stroke="#d29922" stroke-width="24"/>
  <text x="256" y="470" font-family="Georgia, serif" font-size="72" font-weight="bold" fill="#d29922" text-anchor="middle">GRC</text>
</svg>
EOF

# Conversion SVG->PNG : macOS natif via qlmanage (pas de dépendance)
qlmanage -t -s 512 -o /tmp "/tmp/grc_icon.svg" >/dev/null 2>&1
if [ -f "/tmp/grc_icon.svg.png" ]; then
  mkdir -p "$APP_DIR/Contents/Resources/icon.iconset"
  for size in 16 32 64 128 256 512; do
    sips -z $size $size "/tmp/grc_icon.svg.png" \
      --out "$APP_DIR/Contents/Resources/icon.iconset/icon_${size}x${size}.png" >/dev/null
    sips -z $((size*2)) $((size*2)) "/tmp/grc_icon.svg.png" \
      --out "$APP_DIR/Contents/Resources/icon.iconset/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "$APP_DIR/Contents/Resources/icon.iconset" -o "$APP_DIR/Contents/Resources/AppIcon.icns" >/dev/null 2>&1
  rm -rf "$APP_DIR/Contents/Resources/icon.iconset"
fi

# Info.plist : application réelle, icône dock
cat > "$APP_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.gambitridgecapital.dashboard</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSUIElement</key><false/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF

echo "✓ Application installée : $APP_DIR"
echo ""
echo "Pour la mettre dans le dock :"
echo "  1. Ouvre Finder → Applications (ou ~/Applications)"
echo "  2. Glisse $APP_NAME sur le dock"
echo "  3. Clique : la fenêtre native s'ouvre (navigateur si binaire non compilé)"
echo ""
echo "Le serveur n'écoute QUE sur 127.0.0.1 (accessible uniquement depuis ce Mac)."
