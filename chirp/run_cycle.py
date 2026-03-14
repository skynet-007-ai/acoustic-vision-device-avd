# chirp/run_cycle.py
"""
THIS IS THE MAIN FILE FOR THE MVP!!

Run-cycle wrapper for AVD:
 - Runs play_and_record (short or hall), then analyzer
 - Maintains a run_count and archives each run into logs/cycle_1 .. cycle_3
 - When re-using a cycle slot, the previous cycle folder is removed first (so slot is reset)
Usage:
    python chirp/run_cycle.py
"""

import subprocess, sys, shutil, time
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent      # <project>/chirp
PROJECT_ROOT = HERE.parent
CAPTURE = PROJECT_ROOT / "capture"
LOGS = PROJECT_ROOT / "logs"
RUN_COUNT_FILE = LOGS / "run_count.txt"
CYCLES = 3

# ensure folders
CAPTURE.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

def read_run_count():
    try:
        s = RUN_COUNT_FILE.read_text().strip()
        return int(s)
    except Exception:
        return 0

def write_run_count(n):
    RUN_COUNT_FILE.write_text(str(n))

def run_command(cmd_args):
    print(">>> Running:", " ".join(cmd_args))
    proc = subprocess.run(cmd_args, shell=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd_args)} (rc={proc.returncode})")

def find_latest_readable():
    # latest file: scan_readable_*.txt inside LOGS
    files = sorted(LOGS.glob("scan_readable_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def archive_cycle(slot):
    dest = LOGS / f"cycle_{slot}"
    # delete existing dest if any (user requested)
    if dest.exists():
        print(f" -> Removing previous archive for cycle_{slot}: {dest}")
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    # create capture subfolder
    dest_capture = dest / "capture"
    dest_capture.mkdir(exist_ok=True, parents=True)

    # copy logs/last_scan_report.json
    last_json = LOGS / "last_scan_report.json"
    if last_json.exists():
        shutil.copy2(str(last_json), str(dest / "last_scan_report.json"))
    # copy latest readable summary
    latest_readable = find_latest_readable()
    if latest_readable:
        shutil.copy2(str(latest_readable), str(dest / latest_readable.name))

    # copy capture files if present
    candidates = ["chirp_emitted.npy", "chirp_emitted.wav", "echo.wav", "echo_hall.wav"]
    for fn in candidates:
        src = CAPTURE / fn
        if src.exists():
            shutil.copy2(str(src), str(dest_capture / fn))

    print(f"Archived files into: {dest}")

def main():
    print("AVD run-cycle starting. Project root:", PROJECT_ROOT)
    run_count = read_run_count()
    run_count += 1
    write_run_count(run_count)
    slot = ((run_count - 1) % CYCLES) + 1
    print(f"Next cycle slot: {slot} (run count {run_count})")

    # Decide which emitter to use — here we call the short chirp by default.
    # If you want hall-chirp always, change play_and_record.py -> play_and_record_hall.py
    play_script = str(HERE / "play_and_record.py")
    analyzer_script = str(PROJECT_ROOT / "dsp" / "analyze_echo.py")

    # Use the same Python executable
    py = sys.executable

    try:
        # 1) Run emitter -> capture
        run_command([py, play_script])

        # small pause to ensure files flushed
        time.sleep(0.12)

        # 2) Run analyzer
        run_command([py, analyzer_script])

        # 3) Archive results into cycle slot (delete previous slot first)
        archive_cycle(slot)

        print("Cycle complete. Next run will use cycle_%d." % (((slot) % CYCLES) + 1))
    except Exception as e:
        print("ERROR during run-cycle:", repr(e))
        raise

if __name__ == "__main__":
    main()
