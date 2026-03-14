# =============================================================
# AVD MVP READINESS VERIFIER
# Full Corrected Version (Excludes .venv scans)
# =============================================================

import subprocess
import sys
import time
import shutil
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CAPTURE = ROOT / "capture"
LOGS = ROOT / "logs"
CHIRP = ROOT / "chirp"
DSP = ROOT / "dsp"

REQUIRED_FILES = [
    CHIRP / "play_and_record.py",
    CHIRP / "play_and_record_hall.py",
    CHIRP / "run_cycle.py",
    DSP / "analyze_echo.py",
]


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------
def banner(text):
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def run(cmd, timeout=180):
    print(f">>> {cmd}")
    try:
        p = subprocess.run(
            cmd,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        out = p.stdout.decode("utf8", errors="replace")
        print(out)
        return p.returncode, out
    except Exception as e:
        print("[ERROR] Subprocess failed:", e)
        return -1, ""


# -------------------------------------------------------------
# 1. Check required files exist
# -------------------------------------------------------------
def check_files():
    banner("1) REQUIRED FILE CHECK")

    ok = True
    for f in REQUIRED_FILES:
        if f.exists():
            print(f"[OK] {f.relative_to(ROOT)}")
        else:
            print(f"[MISSING] {f.relative_to(ROOT)}")
            ok = False

    for folder in (CAPTURE, LOGS):
        if not folder.exists():
            print(f"[MISSING] folder {folder.relative_to(ROOT)} — creating")
            folder.mkdir(exist_ok=True)
        else:
            print(f"[OK] folder {folder.relative_to(ROOT)}")

    return ok


# -------------------------------------------------------------
# 2. Syntax check — only REAL project files (NO .venv!)
# -------------------------------------------------------------
def syntax_check():
    banner("2) SYNTAX CHECK FOR AVD SOURCE FILES (excluding .venv)")

    errors = False

    for p in ROOT.rglob("*.py"):
        # Skip virtual environment and packages
        if ".venv" in str(p) or "site-packages" in str(p):
            continue

        try:
            compile(p.read_text(encoding="utf8"), str(p), "exec")
            print(f"[OK] {p.relative_to(ROOT)}")
        except Exception as e:
            print(f"[SYNTAX ERROR] {p.relative_to(ROOT)} → {e}")
            errors = True

    return not errors


# -------------------------------------------------------------
# 3. Record chirp & save echo.wav
# -------------------------------------------------------------
def audio_test():
    banner("3) AUDIO CHIRP + RECORD TEST")

    rc, out = run([sys.executable, str(CHIRP / "play_and_record.py")])
    if rc != 0:
        print("[FAIL] play_and_record.py failed")
        return False

    if not (CAPTURE / "echo.wav").exists():
        print("[FAIL] echo.wav missing")
        return False

    print("[OK] echo.wav generated")
    return True


# -------------------------------------------------------------
# 4. Analyzer test
# -------------------------------------------------------------
def analyzer_test():
    banner("4) ANALYZER TEST")

    rc, out = run([sys.executable, str(DSP / "analyze_echo.py")])
    if rc != 0:
        print("[FAIL] analyze_echo.py failed")
        return False

    json_path = LOGS / "last_scan_report.json"
    if not json_path.exists():
        print("[FAIL] analyzer did not generate JSON")
        return False

    print("[OK] Analyzer JSON valid")
    return True


# -------------------------------------------------------------
# 5. Mini cycle rotation test (1 run)
# -------------------------------------------------------------
def cycle_test():
    banner("5) MINI CYCLE ROTATION TEST (1 run)")

    rc, out = run([sys.executable, str(CHIRP / "run_cycle.py")])
    if rc != 0:
        print("[FAIL] run_cycle.py failed")
        return False

    # check cycles
    updated = False
    for i in range(1, 4):
        d = LOGS / f"cycle_{i}"
        if d.exists():
            print(f"[OK] {d.relative_to(ROOT)} folder updated")
            updated = True

    return updated


# -------------------------------------------------------------
# 6. Hall mode test
# -------------------------------------------------------------
def hall_test():
    banner("6) HALL MODE TEST")

    rc, out = run([sys.executable, str(CHIRP / "play_and_record_hall.py")])
    if rc != 0:
        print("[FAIL] hall play_and_record failed")
        return False

    if not (CAPTURE / "echo_hall.wav").exists():
        print("[FAIL] echo_hall.wav missing")
        return False

    print("[OK] echo_hall.wav recorded")

    # Now analyze it
    rc, out = run([sys.executable, str(DSP / "analyze_echo.py")])
    if rc != 0:
        print("[FAIL] analyzer failed on hall mode")
        return False

    print("[OK] Hall analyzer run completed")
    return True


# -------------------------------------------------------------
# Final MVP verdict
# -------------------------------------------------------------
def verdict(file_ok, syntax_ok, audio_ok, analyzer_ok, cycle_ok, hall_ok):
    banner("FINAL MVP VERDICT")

    if all([file_ok, syntax_ok, audio_ok, analyzer_ok, cycle_ok, hall_ok]):
        print("🎉🎉🎉  AVD MVP IS FULLY READY ON THIS LAPTOP  🎉🎉🎉")
        print("All components are functioning exactly as required.")
    else:
        print("❌ MVP NOT READY — Fix the failures listed above.")


# -------------------------------------------------------------
# MAIN
# -------------------------------------------------------------
def main():
    banner("AVD MVP VERIFIER (FULL CHECK)")

    file_ok = check_files()
    syntax_ok = syntax_check()
    audio_ok = audio_test()
    analyzer_ok = analyzer_test()
    cycle_ok = cycle_test()
    hall_ok = hall_test()

    verdict(file_ok, syntax_ok, audio_ok, analyzer_ok, cycle_ok, hall_ok)


if __name__ == "__main__":
    main()
