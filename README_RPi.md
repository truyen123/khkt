# StudyGuard - Raspberry Pi 3B Setup Guide

## Quick Start (RPi 已有 Python 3.13 + git)

```bash
cd ~/StudyGuard
bash run.sh
```

浏览器打开: `http://192.168.1.13:5000`

---

## 完整从零安装 (如果之前没装过)

### 1️⃣ SSH 进 RPi

```bash
ssh letrongtruyen@192.168.1.13
# password: letrongtruyen
```

### 2️⃣ 更新系统

```bash
sudo apt-get update
sudo apt-get install -y \
  python3.13 python3.13-venv python3.13-dev \
  build-essential cmake \
  libopenblas-dev libatlas-base-dev \
  portaudio19-dev \
  flac sox ffmpeg \
  v4l-utils sqlite3
```

### 3️⃣ 创建虚拟环境

```bash
cd ~/StudyGuard
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### 4️⃣ 安装 Python 包

```bash
pip install --no-cache-dir \
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
```

### 5️⃣ 下载 MediaPipe 模型

```bash
mkdir -p models
cd models

# Pose model
curl -fsSL -o pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-assets/pose_landmarker_lite.task

# Hand model  
curl -fsSL -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-assets/hand_landmarker.task

cd ..
```

### 6️⃣ 运行

```bash
bash run.sh
```

---

## 🌐 Web 界面访问

从任何设备浏览器：
- **本机 RPi**: http://127.0.0.1:5000
- **同网络设备**: http://192.168.1.13:5000
- **手机 WiFi**: http://192.168.1.13:5000

### 首次使用必需配置

1. **Gemini API Key**
   - 获取: https://aistudio.google.com/app/apikeys
   - 配置页面粘贴即可

2. **测试硬件** (设置页)
   - 测试摄像头
   - 测试麦克风
   - 测试扬声器
   - 测试 TTS 语音

---

## 📊 系统架构

| 部件 | 状态 | 说明 |
|------|------|------|
| **Camera** | ✅ | USB 或 CSI 摄像头（分辨率 320x240） |
| **MediaPipe** | ✅ | 姿态识别 + 手部检测（CPU） |
| **YOLOv8** | ⚠️ | 禁用（RPi3B RAM不足），可选启用 |
| **Gemini API** | ✅ | 在线问答功能 |
| **Edge-TTS** | ✅ | 越南语语音输出 |
| **Speech Recognition** | ✅ | 越南语语音输入 |

---

## 🔧 常见问题

### 问题1: "Khong mo duoc camera"
```bash
# 检查摄像头
v4l2-ctl --list-devices

# 重新连接或测试
python -c "import cv2; c=cv2.VideoCapture(0); print('OK' if c.isOpened() else 'FAIL'); c.release()"
```

### 问题2: "FLAC conversion utility not available"
```bash
sudo apt-get install flac
```

### 问题3: "Segmentation Fault (SEGV)"
- **原因**: MediaPipe 线程冲突 ✅ 已修复
- **验证**: 查看 app.py 中的 `mediapipe_lock`

### 问题4: 服务反复重启
```bash
# 查看日志
sudo journalctl -u studyguard -n 50 --no-pager

# 重启手动测试
cd ~/StudyGuard && source .venv/bin/activate && python diagnostic.py
```

---

## 📈 后台运行 (Systemd)

### 安装服务
```bash
sudo nano /etc/systemd/system/studyguard.service
```

粘贴下列内容:
```ini
[Unit]
Description=StudyGuard AI Study Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/StudyGuard
Environment="OMP_NUM_THREADS=1"
Environment="OPENBLAS_NUM_THREADS=1"
Environment="STUDY_ENABLE_YOLO=0"
ExecStart=$HOME/StudyGuard/.venv/bin/python app.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 启用和运行
```bash
sudo systemctl daemon-reload
sudo systemctl enable studyguard.service
sudo systemctl start studyguard.service

# 查看状态
sudo systemctl status studyguard.service

# 查看日志
sudo journalctl -u studyguard -f
```

---

## 🔍 诊断工具

### 检查系统状态
```bash
python diagnostic.py
```

输出范例:
```
🔍 Testing imports...
  ✅ flask               - Flask web framework
  ✅ cv2                 - OpenCV
  ✅ mediapipe           - MediaPipe
  ✅ google.genai        - Google Gemini
  ✅ sounddevice         - Audio device access

🔍 Testing hardware...
  ✅ Camera: (240, 320, 3)
  ✅ Audio: 1 microphones, 1 speakers

🔍 Testing MediaPipe models...
  ✅ pose       pose_landmarker_lite.task (25.2 MB)
  ✅ hand       hand_landmarker.task (20.3 MB)

✅ System ready to run!
```

---

## 💡 性能优化 (RPi3B)

### 已优化
- ✅ 单线程 OpenCV/NumPy (`OMP_NUM_THREADS=1`)
- ✅ MediaPipe 线程安全 (全局 lock)
- ✅ Lazy 初始化 Assistant 和 YOLO
- ✅ Camera 分辨率固定 320x240
- ✅ JPEG 压缩质量 60 (降低 CPU 占用)
- ✅ Camera 读取超时 5 秒

### 可进一步优化
```bash
# 禁用不需要的功能
export STUDY_ENABLE_YOLO=0              # 禁用手机检测
export GEMINI_API_KEY=""                # 禁用在线 AI

# 调整阈值 (config.json)
"phone_every_seconds": 5.0              # 减少手机检测频率
"alert_after_seconds": 10               # 增加警告延迟
```

---

## 📝 代码修复总结

最近修复的 SEGV 问题:

1. **MediaPipe 线程冲突** → 加全局 `mediapipe_lock`
2. **Assistant 延迟初始化** → Lazy `get_assistant()`
3. **YOLO 内存问题** → 自动禁用 (RPi < 1.5GB RAM)
4. **Voice 初始化失败** → 转为可选 (不影响启动)

✅ 所有修复已在 `app.py` 中完成

---

## 🆘 需要帮助?

### 重置配置
```bash
rm config.json
# 重启后会重新生成默认配置
```

### 清除缓存
```bash
python -c "import shutil; shutil.rmtree('__pycache__', ignore_errors=True)"
rm *.sqlite3 2>/dev/null || true
```

### 完全重新启动
```bash
sudo systemctl stop studyguard || true
pkill -f "python app.py" || true
sleep 2
python diagnostic.py
bash run.sh
```

---

**Last Updated**: 2026-11-13  
**Tested On**: Raspberry Pi 3 Model B, Python 3.13, Raspbian Bookworm
