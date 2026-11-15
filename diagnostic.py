#!/usr/bin/env python3
"""
Minimal StudyGuard diagnostic
"""
import sys
import os

def test_imports():
    """Test critical imports"""
    print("🔍 Testing imports...")
    errors = []
    
    tests = [
        ("flask", "Flask web framework"),
        ("cv2", "OpenCV"),
        ("numpy", "NumPy"),
        ("mediapipe", "MediaPipe"),
        ("google.genai", "Google Gemini"),
        ("sounddevice", "Audio device access"),
        ("speech_recognition", "Google Speech API"),
    ]
    
    for module, desc in tests:
        try:
            __import__(module)
            print(f"  ✅ {module:20} - {desc}")
        except ImportError as e:
            print(f"  ❌ {module:20} - {desc}: {e}")
            errors.append(module)
    
    return errors

def test_hardware():
    """Test camera and audio"""
    print("\n🔍 Testing hardware...")
    
    # Camera
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_ANY)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret:
                print(f"  ✅ Camera: {frame.shape}")
            else:
                print(f"  ⚠️  Camera: no frames")
        else:
            print(f"  ❌ Camera: not available")
    except Exception as e:
        print(f"  ❌ Camera: {e}")
    
    # Audio
    try:
        import sounddevice as sd
        info = sd.query_devices()
        mics = [d for d in info if d['max_input_channels'] > 0]
        spks = [d for d in info if d['max_output_channels'] > 0]
        print(f"  ✅ Audio: {len(mics)} microphones, {len(spks)} speakers")
    except Exception as e:
        print(f"  ⚠️  Audio: {e}")

def test_models():
    """Check MediaPipe models"""
    print("\n🔍 Testing MediaPipe models...")
    from pathlib import Path
    
    base = Path(__file__).parent
    models = {
        "pose": base / "models" / "pose_landmarker_lite.task",
        "hand": base / "models" / "hand_landmarker.task",
    }
    
    for name, path in models.items():
        if path.exists():
            size_mb = path.stat().st_size / 1e6
            print(f"  ✅ {name:10} {path.name:30} ({size_mb:.1f} MB)")
        else:
            print(f"  ❌ {name:10} Missing: {path}")
    
    return all(p.exists() for p in models.values())

def test_app():
    """Test app can start"""
    print("\n🔍 Testing app initialization...")
    try:
        import app as app_module
        print(f"  ✅ app.py imports OK")
        print(f"  ✅ Flask app created: {app_module.app}")
        return True
    except Exception as e:
        print(f"  ❌ app.py error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    
    print("=" * 60)
    print("StudyGuard System Diagnostic")
    print("=" * 60)
    
    missing = test_imports()
    test_hardware()
    has_models = test_models()
    app_ok = test_app()
    
    print("\n" + "=" * 60)
    if not missing and has_models and app_ok:
        print("✅ System ready to run!")
        print("\nStart with: python app.py")
        sys.exit(0)
    else:
        print("❌ System has issues - see above")
        if missing:
            print(f"\n  Missing packages: {', '.join(missing)}")
            print(f"  Install: pip install {' '.join(missing)}")
        if not has_models:
            print(f"\n  Missing MediaPipe models in models/")
        sys.exit(1)
