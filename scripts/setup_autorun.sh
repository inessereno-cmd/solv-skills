#!/bin/bash
# One-time setup: installs the daily auto-refresh as a macOS background job.
# Run once: ./scripts/setup_autorun.sh

set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$REPO/scripts/com.solv.observatory.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.solv.observatory.plist"

echo "=== NextCare ClearPay Observatory — Auto-refresh Setup ==="
echo ""

# 1. Install Python deps
echo "Installing Python dependencies..."
if ! python3 -c "import redshift_connector" 2>/dev/null && ! python3 -c "import psycopg2" 2>/dev/null; then
  python3 -m pip install --quiet redshift-connector
fi
echo "  OK"

# 2. Create .env if it doesn't exist
if [ ! -f "$REPO/.env" ]; then
  cp "$REPO/.env.example" "$REPO/.env"
  echo ""
  echo "  Created .env — please fill in your Redshift password:"
  echo "  Edit: $REPO/.env"
  echo ""
  read -p "  Press Enter after you've added your password, or Ctrl+C to exit..."
fi

# 3. Install launchd plist
sed "s|REPO_PATH|$REPO|g" "$PLIST_SRC" > "$PLIST_DEST"
chmod 644 "$PLIST_DEST"

# Unload if already loaded (to apply changes)
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "Done! The observatory will refresh automatically every day at 8am."
echo "If your Mac is asleep at 8am, it refreshes as soon as you open it."
echo ""
echo "To refresh manually anytime:  ./scripts/refresh.sh"
echo "To uninstall auto-refresh:    launchctl unload $PLIST_DEST && rm $PLIST_DEST"
echo ""
echo "Live URL: https://inessereno-cmd.github.io/solv-skills/ines/nextcare-clearpay-observatory.html"
