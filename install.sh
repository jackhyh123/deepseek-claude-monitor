#!/bin/bash
# DeepSeek Monitor — one-click installer for macOS
set -e

APP_NAME="DeepSeek Monitor"
INSTALL_DIR="$HOME/.deepseek-monitor"
APP_DIR="/Applications/$APP_NAME.app"

echo "========================================"
echo "  DeepSeek Monitor — macOS 菜单栏安装"
echo "========================================"
echo ""

# ── 1. Check Python ────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "❌ 需要 Python 3，请先安装: brew install python3"
    exit 1
fi
echo "✅ Python: $($PYTHON --version)"

# ── 2. Install dependencies ─────────────────────────────────
echo ""
echo "📦 安装依赖..."
$PYTHON -m pip install --quiet rumps requests pillow 2>&1 | tail -1
echo "✅ 依赖完成"

# ── 3. Copy monitor script ──────────────────────────────────
echo ""
echo "📋 部署监控脚本..."
mkdir -p "$INSTALL_DIR"
cp "$(dirname "$0")/monitor.py" "$INSTALL_DIR/monitor.py"
echo "✅ monitor.py -> $INSTALL_DIR/"

# ── 4. Build .app bundle ────────────────────────────────────
echo ""
echo "🏗️  构建 App Bundle..."

# Generate icon if not present
ICNS_PATH="$INSTALL_DIR/ds_icon.icns"
if [ ! -f "$ICNS_PATH" ]; then
    echo "  生成图标..."
    $PYTHON "$(dirname "$0")/generate_icon.py" "$INSTALL_DIR" 2>&1 | tail -3
    if command -v iconutil &>/dev/null; then
        iconutil -c icns "$INSTALL_DIR/ds_icon.iconset" -o "$ICNS_PATH" 2>/dev/null || true
    fi
fi

# Remove old app
rm -rf "$APP_DIR" 2>/dev/null || true

# Create AppleScript app
osacompile -o "$APP_DIR" -e "do shell script \"$PYTHON $INSTALL_DIR/monitor.py > /tmp/ds-monitor.log 2>&1 &\""

# Remove default icon assets
rm -f "$APP_DIR/Contents/Resources/Assets.car"
rm -f "$APP_DIR/Contents/Resources/applet.rsrc"

# Install custom icon
if [ -f "$ICNS_PATH" ]; then
    cp "$ICNS_PATH" "$APP_DIR/Contents/Resources/applet.icns"
fi

# Configure Info.plist
plutil -remove CFBundleIconName "$APP_DIR/Contents/Info.plist" 2>/dev/null || true
plutil -replace LSUIElement -bool YES "$APP_DIR/Contents/Info.plist" 2>/dev/null || true

# Set custom icon via NSWorkspace
$PYTHON -c "
import Cocoa
workspace = Cocoa.NSWorkspace.sharedWorkspace()
icon = Cocoa.NSImage.alloc().initWithContentsOfFile_('$APP_DIR/Contents/Resources/applet.icns')
if icon:
    workspace.setIcon_forFile_options_(icon, '$APP_DIR', 0)
    print('✅ 图标已设置')
" 2>/dev/null || echo "⚠️  图标设置需要 Accessibility 权限，可忽略"

touch "$APP_DIR"
echo "✅ App Bundle: $APP_DIR"

# ── 5. Launch ───────────────────────────────────────────────
echo ""
echo "🚀 启动 DeepSeek Monitor..."
# Kill existing instance first
pkill -f "monitor.py" 2>/dev/null || true
sleep 1
open -a "$APP_NAME"
sleep 2

# Verify
if pgrep -f "monitor.py" >/dev/null 2>&1; then
    echo "✅ DeepSeek Monitor 已启动"
    echo ""
    echo "========================================"
    echo "  菜单栏: 看 DS ¥0.00 图标"
    echo "  仪表盘: http://localhost:8899"
    echo "  数据库: $INSTALL_DIR/usage.db"
    echo "========================================"
else
    echo "⚠️  应用可能未正常启动，请手动打开:"
    echo "  open '$APP_DIR'"
fi
