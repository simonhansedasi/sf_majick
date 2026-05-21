#!/bin/bash
set -e

DEST="simonhans@raspberrypi:~/coding/sf_majick/"

echo "Syncing sf_majick to Pi..."
rsync -avz \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='*.pkl' \
  --exclude='*.egg-info/' \
  --exclude='.ipynb_checkpoints/' \
  --exclude='*.ipynb' \
  ./ "$DEST"

echo ""
echo "Restarting service..."
ssh simonhans@raspberrypi "sudo systemctl restart sf_majick_gui && sudo systemctl is-active sf_majick_gui"

echo ""
echo "Done. GUI at http://raspberrypi:5008"
