#!/bin/bash
set -e

echo "Pulling fitted configs from Pi..."
mkdir -p data/fitted_configs/
rsync -avz simonhans@raspberrypi:~/coding/sf_majick/data/fitted_configs/ data/fitted_configs/

echo ""
echo "Available configs:"
ls data/fitted_configs/*.json 2>/dev/null | sed 's|data/fitted_configs/||' || echo "  (none yet)"
echo ""
echo "Run experiments:"
echo "  python3 run_experiment.py data/fitted_configs/<name>.json"
