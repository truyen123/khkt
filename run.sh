#!/bin/bash
# StudyGuard - Local execution wrapper for testing
# Run this file locally on RPi: bash run.sh

set -e

# Auto-setup venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating Python venv..."
    python3.13 -m venv .venv || python3 -m venv .venv
fi

source .venv/bin/activate

# Ensure requirements
echo "Checking dependencies..."
pip install -q --upgrade pip

# Minimal requirements
pip install -q --no-cache-dir \
    flask==3.0.0 \
    opencv-python==4.8.1.78 \
    numpy==1.26.4 \
    Pillow==10.1.0 \
    mediapipe==0.10.8 \
    google-genai==0.3.0 \
    sounddevice==0.4.6 \
    soundfile==0.12.1 \
    SpeechRecognition==3.10.0 \
    edge-tts==6.1.9 \
    pyttsx3==2.90 \
    psutil==5.9.6

# Environment
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export PYTHONUNBUFFERED=1
export STUDY_ENABLE_YOLO=0

# Run
echo "Starting StudyGuard..."
python app.py
