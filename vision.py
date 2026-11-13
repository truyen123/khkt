"""Vision helpers: posture analysis + phone-held logic.

Pure functions (no cv2/MediaPipe imports) so they are unit-testable
and reusable on Raspberry Pi 3B / PC.
"""
from collections import deque
import math

# Landmark indices (MediaPipe Pose, 33 points)
NOSE = 0
LEFT_EAR, RIGHT_EAR = 7, 8
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24


def _get(lm, idx):
    p = lm[idx]
    if isinstance(p, dict):
        return p.get("x", 0.0), p.get("y", 0.0), p.get("visibility", 0.0)
    return getattr(p, "x", 0.0), getattr(p, "y", 0.0), getattr(p, "visibility", 0.0) or 0.0


def _mid(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def angle_from_vertical(top, bottom):
    """Angle (degrees) of segment bottom->top vs vertical. 0 = straight."""
    dx = top[0] - bottom[0]
    dy = bottom[1] - top[1]  # image y grows downward -> flip
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0
    return abs(math.degrees(math.atan2(dx, max(dy, 1e-9)))) if dy >= 0 else 90.0


def analyze_posture(landmarks, width, height, cfg):
    """Analyse one person's pose.

    Returns dict with presence info, angles, normalised offsets and status.
    Uses both shoulders/hips (robust to side view) instead of one side only.
    """
    result = {
        "present": False, "status": "no_person", "label": "Không có người",
        "back_angle": 0.0, "head_dx_norm": 0.0, "shoulder_width_px": 0.0,
    }
    if not landmarks:
        return result
    try:
        ls = _get(landmarks, LEFT_SHOULDER)
        rs = _get(landmarks, RIGHT_SHOULDER)
        lh = _get(landmarks, LEFT_HIP)
        rh = _get(landmarks, RIGHT_HIP)
        le = _get(landmarks, LEFT_EAR)
        re = _get(landmarks, RIGHT_EAR)
        nose = _get(landmarks, NOSE)
    except (IndexError, TypeError):
        return result

    vis_sh = max(ls[2], rs[2])
    vis_hip = max(lh[2], rh[2])
    if vis_sh < 0.45 or vis_hip < 0.35:
        return result

    sh_px = _mid((ls[0] * width, ls[1] * height), (rs[0] * width, rs[1] * height))
    hip_px = _mid((lh[0] * width, lh[1] * height), (rh[0] * width, rh[1] * height))
    shoulder_w = math.hypot(ls[0] * width - rs[0] * width, ls[1] * height - rs[1] * height)
    shoulder_w = max(shoulder_w, 1.0)

    # best visible ear (fallback nose)
    ears = [e for e in (le, re) if e[2] >= 0.35]
    if ears:
        ear = max(ears, key=lambda e: e[2])
        ear_px = (ear[0] * width, ear[1] * height)
    elif nose[2] >= 0.35:
        ear_px = (nose[0] * width, nose[1] * height)
    else:
        ear_px = None

    back_angle = angle_from_vertical(sh_px, hip_px)
    head_dx_norm = abs(ear_px[0] - sh_px[0]) / shoulder_w if ear_px else 0.0

    back_thr = float(cfg.get("back_angle_deg", 25))
    head_thr = float(cfg.get("head_dx_ratio", 0.45))
    if back_angle > back_thr:
        status, label = "hunch", "Cảnh báo: Gù lưng / khom người"
    elif ear_px is not None and head_dx_norm > head_thr:
        status, label = "head_down", "Cảnh báo: Cúi đầu quá thấp"
    else:
        status, label = "good", "Đang học — tư thế chuẩn"

    result.update(present=True, status=status, label=label,
                  back_angle=round(back_angle, 1),
                  head_dx_norm=round(head_dx_norm, 3),
                  shoulder_width_px=round(shoulder_w, 1))
    return result


class StatusSmoother:
    """Hysteresis + persistence filter to avoid flickering alerts.

    bad_status must persist `bad_seconds`, good must persist `good_seconds`.
    """

    def __init__(self, bad_seconds=3.0, good_seconds=2.0):
        self.bad_seconds = bad_seconds
        self.good_seconds = good_seconds
        self.stable = "good"
        self._candidate = "good"
        self._candidate_since = None

    def update(self, raw, now):
        if raw == self.stable:
            self._candidate = raw
            self._candidate_since = None
            return self.stable
        if self._candidate != raw:
            self._candidate = raw
            self._candidate_since = now
            return self.stable
        since = self._candidate_since if self._candidate_since is not None else now
        need = self.bad_seconds if raw != "good" else self.good_seconds
        if now - since >= need:
            self.stable = raw
            self._candidate_since = None
        return self.stable


class AngleSmoother:
    def __init__(self, window=8):
        self.buf = deque(maxlen=max(1, int(window)))

    def update(self, value):
        self.buf.append(float(value))
        return sum(self.buf) / len(self.buf)


def phone_held(phone_center, wrists_px, threshold_px=65):
    """True when any wrist is near the phone centre."""
    if phone_center is None or not wrists_px:
        return False
    return any(math.hypot(w[0] - phone_center[0], w[1] - phone_center[1]) < threshold_px
               for w in wrists_px)
