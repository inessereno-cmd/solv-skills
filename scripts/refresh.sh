#!/bin/bash
# Refresh the NextCare ClearPay Observatory and push to GitHub Pages.
# Run manually: ./scripts/refresh.sh
# Or install auto-run: ./scripts/setup_autorun.sh

set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$REPO/scripts/refresh.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting observatory refresh..." | tee -a "$LOG"

# Use Homebrew Python which has redshift_connector installed
PYTHON=/opt/homebrew/bin/python3

# Run the data refresh
$PYTHON "$REPO/scripts/generate_observatory.py" 2>&1 | tee -a "$LOG"

# Commit and push if there are changes
cd "$REPO"
git add ines/nextcare-clearpay-observatory.html
if git diff --cached --quiet; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] No changes to push." | tee -a "$LOG"
else
  git commit -m "chore: refresh observatory data $(date '+%Y-%m-%d')"
  git push
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pushed updated observatory." | tee -a "$LOG"
fi
