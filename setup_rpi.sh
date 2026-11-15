#!/bin/bash
# StudyGuard RPi 3B Complete Setup & Fix
# Python 3.13, MediaPipe, YOLO, Audio, TTS

set -e
trap 'echo "Loi: $?" >&2' ERR

echo "=== StudyGuard RPi3B Setup ==="
cd ~/StudyGuard || exit 1

# 1. Install system packages
echo "1. Cai dat goi he thong..."
sudo apt-get update || true
sudo apt-get install -y \
  python3.13 python3.13-venv python3.13-dev \
  build-essential cmake git \
  libopenblas-dev libatlas-base-dev libjasper-dev libtiff5 libjasper1 \
  libharfbuzz0b libwebp6 libopenjp2-7 libatlas3-base \
  libatlas-base-dev libjasper1 libtiff5 libwebp6 libharfbuzz0b libopenjp2-7 \
  libhdf5-dev libharfbuzz-icu0 libopenblas0 \
  liblapack3 liblapacke libf77blas0 libcblas0 \
  portaudio19-dev libportaudio2 libportaudiocpp0 \
  flac \
  sox ffmpeg \
  v4l-utils \
  sqlite3 \
  2>&1 | grep -i "^get\|^setting up\|^unpacking\|^done" || true

# 2. Create venv
echo "2. Tao venv..."
if [ ! -d ".venv" ]; then
  python3.13 -m venv .venv
fi
source .venv/bin/activate

# 3. Upgrade pip
echo "3. Nang cap pip..."
pip install --upgrade pip setuptools wheel 2>&1 | tail -5

# 4. Install Python packages (fix for Pi3B)
echo "4. Cai dat packages Python (nay khoang 30-40 phut)..."
pip install --no-cache-dir \
  numpy==1.26.4 \
  Pillow==10.1.0 \
  flask==3.0.0 \
  opencv-python==4.8.1.78 \
  mediapipe==0.10.8 \
  google-genai==0.3.0 \
  edge-tts==6.1.9 \
  pyttsx3==2.90 \
  sounddevice==0.4.6 \
  soundfile==0.12.1 \
  SpeechRecognition==3.10.0 \
  ultralytics==8.0.228 \
  psutil==5.9.6 \
  2>&1 | tail -10

# 5. Download MediaPipe models
echo "5. Tai MediaPipe models..."
mkdir -p models
cd models
if [ ! -f "pose_landmarker_lite.task" ]; then
  wget -q https://storage.googleapis.com/mediapipe-assets/pose_landmarker_lite.task || \
  curl -L -o pose_landmarker_lite.task \
    https://storage.googleapis.com/mediapipe-assets/pose_landmarker_lite.task || true
fi
if [ ! -f "hand_landmarker.task" ]; then
  wget -q https://storage.googleapis.com/mediapipe-assets/hand_landmarker.task || \
  curl -L -o hand_landmarker.task \
    https://storage.googleapis.com/mediapipe-assets/hand_landmarker.task || true
fi
cd ..

if [ ! -f "yolov8n.pt" ]; then
  echo "6. Tai YOLO model (lan dau khi chay)..."
fi

# 7. Config environment
echo "7. Cai dat environment..."
cat > .env <<'EOF'
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
PYTHONUNBUFFERED=1
STUDY_ENABLE_YOLO=0
EOF

# 8. Test run
echo "8. Test thiet bi..."
timeout 10 python app.py --help || true

echo ""
echo "✅ Setup xong! Dung lenh:"
echo "  cd ~/StudyGuard && source .venv/bin/activate && python app.py"
echo ""
