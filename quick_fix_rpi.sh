#!/bin/bash
# Quick fix for existing RPi setup

cd ~/StudyGuard || exit 1
source .venv/bin/activate 2>/dev/null || python3.13 -m venv .venv && source .venv/bin/activate

# 1. Install missing system packages only
echo "Cai dat goi he thong (quick)..."
sudo apt-get install -y flac sox 2>&1 | grep -i "done\|setting" || true

# 2. Quick pip update (add FLAC dependency)
echo "Update dependencies..."
pip install --no-cache-dir SpeechRecognition 2>&1 | tail -3

# 3. Disable YOLO on RPi3B
export STUDY_ENABLE_YOLO=0

echo "✅ Quick fix done!"
