import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import apply_settings, current_config, load_config  # noqa: E402


def main():
    print("Nhap GEMINI_API_KEY (Enter de bo qua):")
    key = input().strip()
    if not key:
        print("Bo qua, giu nguyen.")
        return
    cfg = load_config()
    cfg["gemini_api_key"] = key
    apply_settings({"gemini_api_key": key})
    saved = json.loads(Path("config.json").read_text(encoding="utf-8"))
    print("Da luu. Key trong file bat dau bang:", saved["gemini_api_key"][:6] + "...")


if __name__ == "__main__":
    main()
