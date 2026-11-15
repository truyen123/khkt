"""Voice assistant: wake-word listening (offline mic) + Gemini answers + offline TTS."""
import logging
import tempfile
import time
import wave
from pathlib import Path
from threading import Event, Lock, Thread

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"


class VoiceAssistant:
    def __init__(self, get_config, get_context, on_message, on_status):
        self.get_config = get_config
        self.get_context = get_context
        self.on_message = on_message
        self.on_status = on_status
        self.stop_event = Event()
        self.lock = Lock()
        self.status = {"state": "Tat", "error": "", "last_question": "", "last_answer": "", "last_heard": ""}
        self.thread = None
        self.startup_greeting_done = False

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = Thread(target=self._run, name="voice-assistant", daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _set(self, **kw):
        with self.lock:
            self.status.update(kw)
            cur = dict(self.status)
        self.on_status(cur)

    def answer(self, question):
        api_key = (self.get_config().get("gemini_api_key") or "").strip()
        if not api_key:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Chua cau hinh GEMINI_API_KEY (nhap tren web muc Cai dat).")
        from google import genai
        import os
        ctx = self.get_context()
        client = genai.Client(api_key=api_key, http_options={"timeout": 20000})
        try:
            resp = client.models.generate_content(
                model=(self.get_config().get("gemini_model") or os.environ.get("GEMINI_MODEL", MODEL_NAME)),
                contents=("Ban la tro ly hoc tap noi tieng Viet. Tra loi chinh xac, ngan gon, "
                          "khuyen khich tu hoc; neu khong chac hay noi ro.\n"
                          f"Thong tin hoc tap hom nay: {ctx}\n\nCau hoi: {question}"),
                config={"max_output_tokens": 250, "temperature": 0.4})
            ans = (resp.text or "").strip()
            if not ans:
                raise RuntimeError("Tro ly khong tra ve noi dung.")
            return ans
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                close()

    def ask(self, question):
        ans = self.answer(question)
        self.on_message(question, ans)
        self._set(last_question=question, last_answer=ans, error="")
        return ans

    def _speak(self, text):
        cfg = self.get_config()
        if not cfg.get("speaker_enabled"):
            return
        try:
            import sounddevice as sd
            # Giong Viet neural (Microsoft Edge TTS - Google Cloud also ok). Roi mang -> pyttsx3 offline.
            # List giong co san: vi-VN-HoaiMyNeural (nu), vi-VN-LinhNeural (nu), vi-VN-NamMinNeural (nam)
            voice = cfg.get("tts_voice") or "vi-VN-HoaiMyNeural"
            rate_str = "+0%"
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    tmp = Path(f.name)
                try:
                    import asyncio
                    import edge_tts
                    asyncio.run(asyncio.wait_for(
                        edge_tts.Communicate(text, voice=voice, rate=rate_str).save(str(tmp)),
                        timeout=20))
                except Exception as e:
                    logger.warning("edge-tts that bai (%s) -> dung pyttsx3 offline", e)
                    tmp.unlink(missing_ok=True)
                    self._speak_offline(text, cfg)
                    return
                import soundfile as sf
                audio, rate = sf.read(str(tmp), dtype="float32", always_2d=False)
                # Mot so loa (VD Bluetooth/USB) khong ho tro sample rate cua file TTS
                # -> resample ve dung default_samplerate cua thiet bi truoc khi play.
                dev = cfg.get("speaker_device")
                try:
                    info = sd.query_devices(dev, "output")
                    target = int(info.get("default_samplerate") or rate)
                except Exception:
                    target = rate
                if target != rate and rate > 0:
                    n_old = audio.shape[0]
                    n_new = max(1, int(round(n_old * target / rate)))
                    xp = np.linspace(0, 1, n_old)
                    fp = np.linspace(0, 1, n_new)
                    if audio.ndim == 1:
                        audio = np.interp(fp, xp, audio).astype(np.float32)
                    else:
                        audio = np.stack(
                            [np.interp(fp, xp, audio[:, i]) for i in range(audio.shape[1])],
                            axis=1).astype(np.float32)
                    rate = target
                try:
                    sd.play(audio, samplerate=rate, device=dev)
                    sd.wait()
                except Exception as e:
                    logger.warning(f"Loa khong mo duoc (rate {rate}Hz): {e}")
            finally:
                if tmp is not None:
                    tmp.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"_speak error (ignored): {e}")

    def _speak_offline(self, text, cfg):
        """Fallback khi mat mang: pyttsx3 giong Windows (co the khong co tieng Viet)."""
        try:
            import pyttsx3
            import sounddevice as sd
            engine = pyttsx3.init()
            tmp = None
            try:
                engine.setProperty("rate", 185)
                for v in engine.getProperty("voices"):
                    name = (v.name + " " + v.id).lower()
                    if "vietnam" in name or "vi-vn" in name:
                        engine.setProperty("voice", v.id)
                        break
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp = Path(f.name)
                engine.save_to_file(text, str(tmp))
                engine.runAndWait()
                with wave.open(str(tmp), "rb") as wf:
                    ch, sw, rate = wf.getnchannels(), wf.getsampwidth(), wf.getframerate()
                    raw = wf.readframes(wf.getnframes())
                types = {1: np.uint8, 2: np.int16, 4: np.int32}
                if sw not in types:
                    logger.warning(f"Dinh dang TTS khong ho tro: {sw} byte.")
                    return
                audio = np.frombuffer(raw, dtype=types[sw])
                audio = ((audio.astype(np.float32) - 128) / 128 if sw == 1
                         else audio.astype(np.float32) / float(2 ** (sw * 8 - 1)))
                if ch > 1:
                    audio = audio.reshape(-1, ch)
                dev = cfg.get("speaker_device")
                try:
                    info = sd.query_devices(dev, "output")
                    target = int(info.get("default_samplerate") or rate)
                except Exception:
                    target = rate
                if target != rate and rate > 0:
                    n_old = audio.shape[0]
                    n_new = max(1, int(round(n_old * target / rate)))
                    xp = np.linspace(0, 1, n_old)
                    fp = np.linspace(0, 1, n_new)
                    if audio.ndim == 1:
                        audio = np.interp(fp, xp, audio).astype(np.float32)
                    else:
                        audio = np.stack(
                            [np.interp(fp, xp, audio[:, i]) for i in range(audio.shape[1])],
                            axis=1).astype(np.float32)
                    rate = target
                try:
                    sd.play(audio, samplerate=rate, device=dev)
                    sd.wait()
                except Exception as e:
                    logger.warning(f"offline tts play error (ignored): {e}")
            finally:
                try:
                    engine.stop()
                except Exception:
                    pass
                if tmp is not None:
                    tmp.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"_speak_offline error (ignored): {e}")

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self._run_once()
            except Exception as e:
                logger.exception("Voice worker stopped unexpectedly; retrying")
                self._set(state="Loi tro ly", error=f"Voice worker restart: {e}")
                self.stop_event.wait(3)

    def _run_once(self):
        cfg = self.get_config()
        if cfg.get("speaker_enabled") and not self.startup_greeting_done:
            self.startup_greeting_done = True
            self._set(state="Dang khoi dong thiet bi", error="")
            logger.info("Khoi dong: dang phat loi chao qua loa.")
            try:
                self._speak("Xin chào, đang khởi động thiết bị.")
                logger.info("Khoi dong: da phat loi chao xong.")
            except Exception as e:
                logger.warning("Khong phat duoc loi chao khoi dong: %s", e)
                self._set(error=f"Không phát được lời chào: {str(e)[:100]}")

        import speech_recognition as sr
        rec = sr.Recognizer()
        rec.pause_threshold = 0.7
        rec.dynamic_energy_threshold = True
        talking = False
        deadline = 0
        while not self.stop_event.is_set():
            cfg = self.get_config()
            if not cfg.get("microphone_enabled"):
                self._set(state="Tat", error="")
                self.stop_event.wait(1)
                talking = False
                continue
            try:
                with sr.Microphone(device_index=cfg.get("microphone_device")) as src:
                    self._set(state="Dang nghe", error="")
                    try:
                        rec.adjust_for_ambient_noise(src, duration=0.25)
                    except Exception as e:
                        logger.warning("adjust_for_ambient_noise failed: %s", e)
                    while not self.stop_event.is_set():
                        cur = self.get_config()
                        if (not cur.get("microphone_enabled")
                                or cur.get("microphone_device") != cfg.get("microphone_device")):
                            break
                        try:
                            audio = rec.listen(src, timeout=1, phrase_time_limit=7)
                        except sr.WaitTimeoutError:
                            if talking and time.monotonic() >= deadline:
                                talking = False
                                self._set(state="Dang nghe", error="")
                            continue
                        except Exception as e:
                            logger.warning("listen error: %s", e)
                            continue
                        try:
                            text = rec.recognize_google(audio, language="vi-VN").strip()
                        except sr.UnknownValueError:
                            # Mic co tieng nhung khong nhan ra chu -> bao de user biet can noi lai
                            self._set(state="Dang nghe", error="nghe thay tieng nhung khong ro, hay noi lai to/ro hon",
                                      last_heard="(khong ro)")
                            logger.info("Mic: nghe thay tieng nhung khong nhan dang duoc.")
                            continue
                        except sr.RequestError as e:
                            self._set(state="Loi nhan dang", error=str(e)[:100])
                            logger.warning("Nhan dang Google loi: %s", e)
                            continue
                        except Exception as e:
                            logger.warning("recognize error: %s", e)
                            continue
                        self._set(last_heard=text)
                        logger.info("Mic nghe: %s", text)
                        norm = text.casefold()
                        if not talking:
                            if "trợ lý ảo" not in norm and "tro ly ao" not in norm:
                                self._set(state="Dang nghe",
                                          error=f"chua goi dung tu khoa — vua nghe: '{text[:50]}'")
                                continue
                            talking = True
                            deadline = time.monotonic() + 60
                            self._set(state="Dang tro chuyen", error="")
                            self._speak("Oi, toi nghe day. Ban muon hoi gi?")
                            continue
                        if any(w in norm for w in ("tạm biệt", "tam biet", "dừng lại", "dung lai", "thôi", "thoi")):
                            talking = False
                            self._speak("Tam biet ban!")
                            self._set(state="Dang nghe", error="")
                            continue
                        try:
                            self._speak(self.ask(text))
                            deadline = time.monotonic() + 60
                        except Exception as e:
                            logger.warning("assistant answer failed: %s", e)
                            self._set(state="Loi tro ly", error=str(e)[:100])
            except Exception as e:
                logger.warning("mic error: %s", e)
                self._set(state="Loi micro", error=str(e)[:100])
                self.stop_event.wait(3)
