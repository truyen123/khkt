# StudyGuard AI — Giám sát tư thế & hỗ trợ học tập

Nguyên mẫu: camera USB + Raspberry Pi 3 Model B (Python 3.10–3.13) hoặc PC.
Xử lý ảnh **tại thiết bị**; chatbot gọi **Gemini API** qua Internet.

## Chức năng (đối chiếu tài liệu 2.4–2.5)

| Khối | Triển khai | Ghi chú đúng tài liệu |
|---|---|---|
| Thu nhận hình ảnh | `open_camera()` 320×240, quét camera thật trên web | camera nhìn đầu–vai–thân trên |
| Xử lý tư thế | MediaPipe Pose lite + `vision.py`: góc lưng (vai–hông vs phương đứng), độ cúi đầu chuẩn hoá theo vai, trung bình trượt + hysteresis 5s/2s | không kết luận mất tập trung; chỉ gắn nhãn theo quy tắc |
| Làm việc riêng (điện thoại) | YOLOv8n (CPU, mỗi 2s) + tay gần điện thoại; xác nhận sau 30s, cho phép mất dấu 6s; chỉ ghi **"nghi ngờ sử dụng điện thoại"**, lưu clip AVI 2fps + 4s pre-roll | đúng ngưỡng tài liệu |
| Quản lý phiên học | hiện diện trước camera, idle-grace 60s, thời gian tính **đến giây** (giờ:phút:giây) | so được với đồng hồ bấm giờ |
| Chatbot | văn bản + giọng nói (wake-word "trợ lý ảo"), Gemini `gemini-2.5-flash`, TTS tiếng Việt Edge Neural (cần Internet), fallback pyttsx3 | AI chạy online, không chạy LLM trên Pi |
| App phụ huynh/học sinh | 1 trang web: live + trạng thái + test cam/mic/loa + cài đặt ngưỡng + thống kê ngày/7 ngày + bằng chứng clip | đăng nhập chưa làm (chạy LAN gia đình) |

## Cài đặt (Pi 3B, 64-bit, với điều kiện RAM thấp)

```bash
sudo apt update && sudo apt install -y python3-venv libportaudio2 espeak-ng
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
# For Raspberry Pi 3 (1GB RAM, no YOLO):
pip install -r requirements-pi.txt
# For Raspberry Pi 4+ or PC (enable phone detection):
pip install -r requirements.txt

mkdir -p models
curl -L https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task -o models/pose_landmarker_lite.task
curl -L https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task -o models/hand_landmarker.task
export GEMINI_API_KEY="..."
python app.py
```

Windows (Python 3.13): tương tự, dùng `py -3.13 -m venv .venv`.

Mở `http://<IP>:5000`. Server hiện phục vụ mạng LAN (`0.0.0.0`) và **chưa có đăng nhập**; chỉ chạy trong mạng tin cậy, không forward cổng ra Internet.

## Chạy lâu dài và tự phục hồi

### Chế độ thiết bị RAM thấp
- Trên Raspberry Pi 3 (1GB RAM): YOLO tự tắt để ưu tiên MediaPipe Pose. Nếu muốn bật YOLO: `pip install ultralytics && export STUDY_ENABLE_YOLO=1`.
- Tư thế vẫn hoạt động bình thường; nhận diện điện thoại báo "chế độ tắt trên thiết bị RAM thấp".
- Nếu YOLO lỗi: app thử lại sau 5 phút (YOLO_RETRY_SECONDS), không loop mỗi frame.

### Cơ chế tự phục hồi toàn bộ
- **Camera live**: Chỉ cho phép một stream/tab cùng lúc. Nếu frame mất >5 giây, trang tự `retry stream`. Lỗi camera đã thử lại < 5 giây nếu app khác chiếm tạm.
- **MediaPipe**: Lỗi khởi tạo → app vẫn stream hình + báo AI tạm không sẵn sàng; cần restart app để khắc phục model/dependency lỗi.
- **Trợ lý thoại**: Worker auto-restart sau lỗi; nhận dạng giọng + Edge TTS cần mạng. Timeout Gemini/TTS <20s; Edge TTS mất mạng → fallback pyttsx3 offline.
- **Dữ liệu**: System log giữ max 10.000 dòng; clip chứng cứ xoay vòng (max 100 files / 512MB). Evidence cleanup xóa file cũ nhất trước tạo mới.
- **Database**: SQLite WAL + busy_timeout 5s; recovery tự tắt session/event chưa đóng nếu app crash.

### Giám sát lỗi
- Xem System log để chẩn đoán lỗi thực tế (camera, mic, Gemini, YOLO).
- Endpoint `/api/gemini/test` kiểm tra key/model mà không lộ thông tin nhạy cảm.
- Endpoint `/api/system` báo YOLO retry status, memory usage, evidence quota.

- **Không khách biến**: Camera/mic/loa phải test thực tế trên thiết bị vì test CLI không dùng phần cứng thật.

## Kiểm thử

```bash
python -m unittest discover -s tests -v
```

Kiểm tra `python -m compileall -q app.py study_store.py voice_assistant.py vision.py`; log trong SQLite giữ tối đa 10.000 dòng mới nhất. Giọng Edge Neural cần Internet; khi mất mạng TTS fallback sang pyttsx3 (giọng tùy hệ điều hành).

Test gồm: tư thế chuẩn/gù/cúi/không người, bộ lọc chống nhấp nháy, phone-held,
phiên học tính giây, sự kiện phone, cảnh báo tư thế, recovery sau crash.

## Quyền riêng tư

- `data.sqlite3`: phiên hiện diện, sự kiện phone, cảnh báo tư thế, nhiệm vụ, hội thoại.
- Không lưu video liên tục; chỉ lưu clip khi đã xác nhận phone (thư mục `evidence/`).
- Nhật ký thoại lưu text, không lưu audio. Xoá clip cũ trong `evidence/` khi không cần.
