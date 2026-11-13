import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from study_store import StudyStore, local_timestamp  # noqa: E402
from vision import StatusSmoother, analyze_posture, phone_held  # noqa: E402


def lm_point(x, y, vis=0.9):
    return {"x": x, "y": y, "visibility": vis}


def straight_pose():
    pts = [lm_point(0.5, 0.5, 0.0)] * 33
    pts[0] = lm_point(0.5, 0.28, 0.9)     # nose
    pts[7] = lm_point(0.44, 0.30, 0.9)     # left ear
    pts[8] = lm_point(0.56, 0.30, 0.9)     # right ear
    pts[11] = lm_point(0.42, 0.45, 0.95)   # shoulders
    pts[12] = lm_point(0.58, 0.45, 0.95)
    pts[23] = lm_point(0.43, 0.75, 0.9)    # hips
    pts[24] = lm_point(0.57, 0.75, 0.9)
    return pts


CFG = {"back_angle_deg": 25, "head_dx_ratio": 0.45}


class VisionTests(unittest.TestCase):
    def test_good_posture(self):
        r = analyze_posture(straight_pose(), 320, 240, CFG)
        self.assertTrue(r["present"])
        self.assertEqual(r["status"], "good")
        self.assertLess(r["back_angle"], 10)

    def test_hunch_detected(self):
        pts = straight_pose()
        pts[11] = lm_point(0.60, 0.45, 0.95)
        pts[12] = lm_point(0.72, 0.45, 0.95)  # shoulders shifted forward
        r = analyze_posture(pts, 320, 240, CFG)
        self.assertEqual(r["status"], "hunch")

    def test_head_down_detected(self):
        pts = straight_pose()
        pts[7] = lm_point(0.20, 0.32, 0.9)
        pts[8] = lm_point(0.20, 0.32, 0.9)
        pts[0] = lm_point(0.20, 0.32, 0.9)
        r = analyze_posture(pts, 320, 240, CFG)
        self.assertEqual(r["status"], "head_down")

    def test_no_person(self):
        self.assertFalse(analyze_posture(None, 320, 240, CFG)["present"])
        low = straight_pose()
        low[11] = lm_point(0.42, 0.45, 0.1)
        low[12] = lm_point(0.58, 0.45, 0.1)
        self.assertFalse(analyze_posture(low, 320, 240, CFG)["present"])

    def test_smoother_needs_persistence(self):
        s = StatusSmoother(bad_seconds=3.0, good_seconds=2.0)
        self.assertEqual(s.update("hunch", 0.0), "good")
        self.assertEqual(s.update("hunch", 1.0), "good")   # chua du 3s
        self.assertEqual(s.update("hunch", 3.5), "hunch")  # du 3s -> bao
        self.assertEqual(s.update("good", 4.0), "hunch")   # good can 2s
        self.assertEqual(s.update("good", 6.5), "good")

    def test_phone_held(self):
        self.assertTrue(phone_held((100, 100), [(110, 105)], 65))
        self.assertFalse(phone_held((100, 100), [(300, 300)], 65))
        self.assertFalse(phone_held((100, 100), [], 65))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = StudyStore(Path(self.tmp.name) / "s.sqlite3")

    def test_presence_seconds_and_grace(self):
        self.store.update_presence(True, 100)
        self.store.update_presence(True, 101)
        self.assertEqual(self.store.dashboard()["study_seconds"], 1)
        self.assertIsNone(self.store.dashboard()["sessions"][0]["ended_at"])
        self.store.update_presence(False, 150)
        self.assertIsNone(self.store.dashboard()["sessions"][0]["ended_at"])
        self.store.update_presence(False, 162)
        self.assertIsNotNone(self.store.dashboard()["sessions"][0]["ended_at"])

    def test_gemini_test_endpoint_uses_model_and_never_returns_key(self):
        import app as app_module
        from unittest.mock import patch
        client = app_module.app.test_client()
        with patch.object(app_module.VoiceAssistant, "answer", return_value="OK") as answer:
            response = client.post("/api/gemini/test", json={
                "model": "gemini-test", "api_key": "secret-test-key"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(answer.call_args.args[0], "Trả lời đúng một từ: OK")
        self.assertNotIn("secret-test-key", response.get_data(as_text=True))
        self.assertEqual(client.post("/api/gemini/test", json={"model": ""}).status_code, 400)

    def test_app_routes_smoke(self):
        """Smoke: all routes respond even without camera/models."""
        import app as app_module
        client = app_module.app.test_client()
        for route in ("/", "/get_status", "/api/logs", "/api/dashboard", "/api/settings"):
            with self.subTest(route=route):
                r = client.get(route)
                self.assertEqual(r.status_code, 200, f"Route {route} failed: {r.status_code}")

    def test_yolo_disables_on_low_memory(self):
        """YOLO disables if _low_memory_device() returns True (mock env)."""
        import app as app_module
        from unittest.mock import patch
        with patch.object(app_module, "_low_memory_device", return_value=True):
            result = app_module.get_yolo()
            self.assertIsNone(result)
            self.assertIn("RAM thap", app_module.yolo_error)
        # Reset for other tests
        with patch.object(app_module, "_low_memory_device", return_value=False):
            app_module.yolo_model = None
            app_module.yolo_error = ""
            app_module.yolo_retry_after = 0

    def test_evidence_quota_enforces_limit(self):
        """Evidence cleanup removes oldest files when limit exceeded."""
        import app as app_module
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create mock evidence files
            for i in range(150):
                (tmppath / f"phone_{i}.avi").write_text(f"clip{i}" * 1000)
            old_dir = app_module.EVIDENCE_DIR
            app_module.EVIDENCE_DIR = tmppath
            app_module._enforce_evidence_quota()
            remaining = list(tmppath.glob("*"))
            self.assertLessEqual(len(remaining), app_module.EVIDENCE_MAX_FILES)
            app_module.EVIDENCE_DIR = old_dir

    def test_core_routes_smoke(self):
        for i in range(205):
            self.store.add_log("INFO", "test", f"row {i}")
        logs = self.store.get_logs(20)
        self.assertEqual(len(logs), 20)
        self.assertEqual(logs[0]["message"], "row 204")
        self.store.clear_logs()
        self.assertEqual(self.store.get_logs(), [])

    def test_clear_all_data_keeps_schema_and_accepts_new_data(self):
        self.store.update_presence(True, 1.0)
        self.store.add_task("backup")
        self.store.add_log("WARN", "test", "clear")
        self.store.clear_all_data()
        self.assertEqual(self.store.dashboard()["tasks"], [])
        self.assertEqual(self.store.get_logs(), [])
        self.assertEqual(self.store.add_task("after clear")["description"], "after clear")

    def test_phone_event_posture_tasks(self):
        self.store.update_presence(True, 10)
        eid = self.store.start_phone_event(local_timestamp(), "Nghi ngo")
        self.store.finish_phone_event(eid, local_timestamp(), "clip.avi")
        aid = self.store.start_posture_alert("hunch", "Gu lung")
        self.store.finish_posture_alert(aid, 7.0)
        t = self.store.add_task("On Toan")
        self.store.toggle_task(t["id"])
        d = self.store.dashboard()
        self.assertEqual(d["events"][0]["evidence_path"], "clip.avi")
        self.assertAlmostEqual(d["posture_alerts"][0]["duration_seconds"], 7.0)
        self.assertEqual(d["tasks"][0]["done"], 1)

    def test_recover_open(self):
        self.store.update_presence(True, 10)
        self.store.start_phone_event(local_timestamp(), "x")
        d2 = StudyStore(self.store.path).dashboard()
        self.assertIsNotNone(d2["sessions"][0]["ended_at"])


if __name__ == "__main__":
    unittest.main()
