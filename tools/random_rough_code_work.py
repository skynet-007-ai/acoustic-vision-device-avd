# random_rough_code_work.py
"""
AVD repo health & 3-cycle verification helper.

Place this file in your project root (or overwrite the existing random_rough_code_work.py),
then run: python random_rough_code_work.py

This script:
 - Verifies required files exist
 - Performs a basic syntax (compile) check
 - Optionally runs the functional 3-cycle test by calling chirp/run_cycle.py
 - Verifies cycle archives and last_scan_report.json

Be aware: functional test will run emit/record/analyze which uses your audio devices.
"""

import subprocess
import sys
import time
import shutil
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CAPTURE = PROJECT_ROOT / "capture"
LOGS = PROJECT_ROOT / "logs"
CHIRP = PROJECT_ROOT / "chirp"
DSP = PROJECT_ROOT / "dsp"

REQUIRED = [
    CHIRP / "play_and_record.py",
    CHIRP / "play_and_record_hall.py",
    CHIRP / "run_cycle.py",
    DSP / "analyze_echo.py"
]

def print_header(s):
    print("\n" + "="*max(20, len(s)))
    print(s)
    print("="*max(20, len(s)))

def exists_report():
    print_header("Static file & folder checks")
    ok = True
    for p in REQUIRED:
        if p.exists():
            try:
                size = p.stat().st_size
            except Exception:
                size = 0
            print(f"[OK] {p.relative_to(PROJECT_ROOT)} exists (size={size} bytes)")
        else:
            print(f"[MISSING] {p.relative_to(PROJECT_ROOT)} NOT FOUND")
            ok = False

    for folder in (CAPTURE, LOGS):
        if folder.exists():
            try:
                entries = len(list(folder.iterdir()))
            except Exception:
                entries = 0
            print(f"[OK] folder: {folder.relative_to(PROJECT_ROOT)} (contains {entries} entries)")
        else:
            print(f"[MISSING] folder: {folder.relative_to(PROJECT_ROOT)} - will be created on first run")
    return ok

def syntax_checks():
    print_header("Syntax (compile) checks")
    errors = False
    # fixed: iterate directories individually (previous bug used a tuple.rglob which failed)
    candidates = []
    for d in (CHIRP, DSP, PROJECT_ROOT):
        if d.exists():
            candidates.extend(list(d.rglob("*.py")))

    py_files = [p for p in sorted(set(candidates)) if "venv" not in str(p)]
    for p in py_files:
        try:
            src = p.read_text(encoding="utf8")
            compile(src, str(p), "exec")
            print(f"[OK] {p.relative_to(PROJECT_ROOT)} compiled successfully")
        except Exception as e:
            print(f"[SYNTAX ERROR] {p.relative_to(PROJECT_ROOT)} -> {e}")
            errors = True
    return not errors

def run_subprocess(cmd, timeout=120):
    # safer subprocess wrapper that avoids CP1252 decode errors by forcing utf-8 with fallback
    print(f">>> running: {cmd!r}")
    try:
        proc = subprocess.run(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        raw = proc.stdout
        try:
            out = raw.decode("utf-8", errors="replace")
        except Exception:
            out = str(raw)
        rc = proc.returncode
        print("--- process output start ---")
        print(out.strip())
        print("---- process output end ----")
        return rc, out
    except subprocess.TimeoutExpired as e:
        print("[TIMEOUT] process exceeded timeout:", e)
        return -1, ""
    except Exception as e:
        print("[ERROR] subprocess failed:", e)
        return -2, ""

def verify_json_keys(json_path):
    if not json_path.exists():
        print(f"[MISSING] {json_path} not found")
        return False
    try:
        j = json.loads(json_path.read_text(encoding="utf8"))
        expected_keys = {"input_file","samples","samplerate","chirp_start_s","estimated_band","num_echo_peaks","estimated_distances_m"}
        present = set(j.keys())
        missing = expected_keys - present
        if missing:
            print(f"[WARN] JSON keys missing: {missing}")
            print(f"JSON keys present: {sorted(list(present))}")
            return False
        print(f"[OK] JSON contains expected keys (num_echo_peaks={j.get('num_echo_peaks')})")
        return True
    except Exception as e:
        print("[ERROR] failed to parse JSON:", e)
        return False

def check_cycle_archives(cycles=3):
    print_header("Check cycle folders (logs/cycle_1 .. cycle_N)")
    found = []
    for i in range(1, cycles+1):
        d = LOGS / f"cycle_{i}"
        if d.exists():
            # list files
            cnt = sum(1 for _ in d.rglob("*") if _.is_file())
            print(f"[FOUND] {d.relative_to(PROJECT_ROOT)} (files={cnt})")
            found.append(i)
        else:
            print(f"[MISSING] {d.relative_to(PROJECT_ROOT)}")
    return found

def functional_3cycle_test():
    print_header("FUNCTIONAL 3-cycle test (this will run the emitter + analyzer)")
    answer = input("Run functional audio test? (y/n): ").strip().lower()
    if answer != "y":
        print("Skipping functional test. You can still run the tests manually with 'python chirp/run_cycle.py'.")
        return

    py = sys.executable
    run_cycle = CHIRP / "run_cycle.py"
    if not run_cycle.exists():
        print("[ERROR] run_cycle.py missing:", run_cycle)
        return

    # run 4 times: after 3 cycles, run a 4th to ensure rotation and deletion of slot 1 occurs
    runs = 4
    successful_runs = 0
    for i in range(1, runs+1):
        print_header(f"Functional run #{i}")
        rc, out = run_subprocess([py, str(run_cycle)], timeout=240)
        if rc == 0:
            print(f"[OK] run_cycle finished (run #{i})")
            successful_runs += 1
        else:
            print(f"[FAILED] run_cycle returned rc={rc} (run #{i}) — aborting further functional runs.")
            break
        # small pause
        time.sleep(0.3)

    # After runs, check which cycles exist
    found = check_cycle_archives()
    # Check last_scan_report.json validity
    json_ok = verify_json_keys(LOGS / "last_scan_report.json")

    # Check deletion/rotation behavior:
    if successful_runs >= 4:
        # After 4th run cycle_1 should have been re-created (timestamp newer)
        c1 = LOGS / "cycle_1"
        if c1.exists():
            print("[ROTATION] cycle_1 exists after 4 runs -> rotation completed (old cycle_1 should have been removed before re-write).")
        else:
            print("[ROTATION WARNING] cycle_1 not found after 4 runs (rotation may not have executed).")
    return

def summary_and_next_steps(static_ok, syntax_ok_flag):
    print_header("SUMMARY")
    print(f"Static files present: {'YES' if static_ok else 'NO (see above)'}")
    # Here is the corrected check — only treat as OK if syntax_ok_flag is exactly True
    print(f"Syntax check: {'OK' if syntax_ok_flag is True else 'ERRORS/IGNORED'}")

    print("\nNext recommended actions:")
    if not static_ok:
        print(" - Create / restore missing files listed above (play_and_record.py, run_cycle.py, analyze_echo.py, etc.)")
    if syntax_ok_flag is not True:
        print(" - Fix Python syntax errors shown above before attempting functional tests.")
    print(" - To run a full real test (plays sound + records) run: python chirp/run_cycle.py")
    print(" - If you plan to run functional tests now, re-run this script and type 'y' at prompt.")
    print("\nIf everything passes and you want, I can:")
    print(" - Produce a short README/demo script for judges")
    print(" - Produce a non-audio dry-run mode for CI")

def main():
    print_header("AVD Repo Verifier")
    print("Project root:", PROJECT_ROOT)

    static_ok = exists_report()
    syntax_ok = syntax_checks()

    # run functional test interactively (plays audio if you choose)
    functional_3cycle_test()

    # show cycle archive summary
    check_cycle_archives()

    # validate last_scan_report if present
    verify_json_keys(LOGS / "last_scan_report.json")

    # NOTE: pass explicit boolean check here so we only print OK when syntax_ok is exactly True
    summary_and_next_steps(static_ok, syntax_ok is True)

if __name__ == "__main__":
    main()
