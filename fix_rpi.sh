#!/bin/bash
# StudyGuard Ultimate Fix - Run this on RPi after basic venv setup
# Usage: bash fix_rpi.sh

set -e
cd ~/StudyGuard || { echo "Not in StudyGuard dir"; exit 1; }

echo "=== StudyGuard RPi3B Ultimate Fix ==="

# 1. Activate venv
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
else
    echo "Creating venv..."
    python3.13 -m venv .venv
    source .venv/bin/activate
fi

# 2. Ensure critical system packages
echo "Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y \
    flac sox ffmpeg v4l-utils \
    portaudio19-dev libopenblas-dev \
    2>&1 | tail -3 || true

# 3. Fix pip packages (correct versions for Pi3B)
echo "Installing Python packages..."
pip install --upgrade pip setuptools wheel -q

# Core packages - specific versions tested on RPi3B
pip install --no-cache-dir -q \
    numpy==1.26.4 \
    Pillow==10.1.0 \
    flask==3.0.0 \
    opencv-python==4.8.1.78

# AI/Vision packages
pip install --no-cache-dir -q \
    mediapipe==0.10.8 \
    google-genai==0.3.0

# Audio/Voice packages
pip install --no-cache-dir -q \
    edge-tts==6.1.9 \
    pyttsx3==2.90 \
    sounddevice==0.4.6 \
    soundfile==0.12.1 \
    SpeechRecognition==3.10.0

# YOLO (optional - slow on Pi3B, disabled by default)
pip install --no-cache-dir -q \
    ultralytics==8.0.228

# Utilities
pip install --no-cache-dir -q \
    psutil==5.9.6

echo "✅ Packages ready"

# 4. Download MediaPipe models
echo "Downloading MediaPipe models..."
mkdir -p models
cd models

if [ ! -f "pose_landmarker_lite.task" ]; then
    echo "  • pose_landmarker_lite.task..."
    curl -fsSL -o pose_landmarker_lite.task \
        https://storage.googleapis.com/mediapipe-assets/pose_landmarker_lite.task 2>/dev/null || \
    wget -q https://storage.googleapis.com/mediapipe-assets/pose_landmarker_lite.task 2>/dev/null || \
    echo "    ⚠ Download failed - manual download needed"
fi

if [ ! -f "hand_landmarker.task" ]; then
    echo "  • hand_landmarker.task..."
    curl -fsSL -o hand_landmarker.task \
        https://storage.googleapis.com/mediapipe-assets/hand_landmarker.task 2>/dev/null || \
    wget -q https://storage.googleapis.com/mediapipe-assets/hand_landmarker.task 2>/dev/null || \
    echo "    ⚠ Download failed - manual download needed"
fi

cd ..

# 5. Create systemd service
echo "Setting up systemd service..."
sudo tee /etc/systemd/system/studyguard.service > /dev/null <<EOF
[Unit]
Description=StudyGuard AI - Voice Assistant Study Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PWD
Environment="OMP_NUM_THREADS=1"
Environment="OPENBLAS_NUM_THREADS=1"
Environment="STUDY_ENABLE_YOLO=0"
ExecStart=$PWD/.venv/bin/python app.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable studyguard.service

echo "✅ Service installed"

# 6. Test camera
echo "Testing hardware..."
timeout 3 python3.13 -c "
import cv2
cap = cv2.VideoCapture(0, cv2.CAP_ANY)
if cap.isOpened():
    ret, frame = cap.read()
    cap.release()
    if ret:
        print('✅ Camera OK')
    else:
        print('⚠ Camera no frame')
else:
    print('⚠ Camera not available')
" || echo "⚠ Camera test skipped"

# 7. Test audio
timeout 2 python3.13 -c "
try:
    import sounddevice as sd
    info = sd.query_devices()
    mics = sum(1 for d in info if d['max_input_channels'] > 0)
    spks = sum(1 for d in info if d['max_output_channels'] > 0)
    print(f'✅ Audio: {mics} mics, {spks} spks')
except Exception as e:
    print(f'⚠ Audio: {e}')
" || echo "⚠ Audio test skipped"

# 8. Config
echo "Creating .env..."
cat > .env <<'ENVEOF'
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
PYTHONUNBUFFERED=1
STUDY_ENABLE_YOLO=0
ENVEOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Add Gemini API key in web UI or:"
echo "   export GEMINI_API_KEY=your_key"
echo ""
echo "2. Start service:"
echo "   sudo systemctl start studyguard"
echo "   sudo systemctl status studyguard"
echo ""
echo "3. View web UI:"
echo "   http://192.168.1.13:5000"
echo ""
echo "4. Monitor logs:"
echo "   sudo journalctl -u studyguard -f"
echo ""
