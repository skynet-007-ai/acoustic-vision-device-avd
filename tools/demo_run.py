#!/usr/bin/env python3
"""
demo_run.py

Demo runner for AVD MVP:
 - runs hall chirp -> analyzes hall recording
 - runs short chirp -> analyzes short recording
 - collects analyzer JSONs and creates a combined markdown report and short text summary
 - safe, platform-independent copying and subprocess handling

Place this file in your project root and run:
    python demo_run.py
"""

from pathlib import Path
import subprocess, sys, shutil, json, time, datetime

PROJECT_ROOT = Path(__file__).resolve().parent
CHIRP_DIR = PROJECT_ROOT / "chirp"
DSP_DIR = PROJECT_ROOT / "dsp"
CAPTURE = PROJECT_ROOT / "capture"
LOGS = PROJECT_ROOT / "logs"

PLAY_HALL = CHIRP_DIR / "play_and_record_hall.py"
PLAY_SHORT = CHIRP_DIR / "play_and_record.py"
ANALYZE = DSP_DIR / "analyze_echo.py"

HALL_WAV = CAPTURE / "echo_hall.wav"
ECHO_WAV = CAPTURE / "echo.wav"
LAST_JSON = LOGS / "last_scan_report.json"

OUT_MARKDOWN = LOGS / f"demo_report_{datetime.datetime.now():%Y%m%d_%H%M%S}.md"
OUT_SUMMARY = LOGS / f"demo_readable_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"

PY = sys.executable

def run_cmd(args, timeout=240):
    """Run command list (no shell), return (rc, stdout). Always returns str stdout (errors replaced)."""
    print(f">>> Running: {' '.join(args)}")
    try:
        # ensure stable encoding and replace invalid chars
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = proc.stdout or ""
        rc = proc.returncode
        print(out.strip())
        return rc, out
    except subprocess.TimeoutExpired as e:
        print("[ERROR] Command timed out:", e)
        return -1, ""
    except Exception as e:
        print("[ERROR] Failed to run command:", e)
        return -2, ""

def ensure_dirs():
    CAPTURE.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)

def safe_copy(src: Path, dst: Path):
    if not src.exists():
        print(f"[WARN] source for copy missing: {src}")
        return False
    try:
        shutil.copy(str(src), str(dst))
        return True
    except Exception as e:
        print("[ERROR] copy failed:", e)
        return False

def load_json(p: Path):
    if not p.exists():
        print(f"[WARN] JSON not found: {p}")
        return None
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except Exception as e:
        print("[ERROR] failed to read/parse JSON:", e)
        return None

def write_text(p: Path, s: str):
    p.write_text(s, encoding="utf8")
    print(f"[SAVED] {p}")

def run_hall_scan():
    print("\n=== HALL SCAN ===")
    if not PLAY_HALL.exists():
        print("[ERROR] missing:", PLAY_HALL)
        return None
    # run play_and_record_hall.py
    rc, out = run_cmd([PY, str(PLAY_HALL)], timeout=240)
    if rc != 0:
        print("[ERROR] hall play/record failed (rc=%s)" % rc)
    # ensure analyzer analyzes hall wav => copy echo_hall.wav -> echo.wav
    if safe_copy(HALL_WAV, ECHO_WAV):
        print("[INFO] copied hall wav to echo.wav for analyzer")
    else:
        print("[WARN] couldn't copy hall wav; analyzer may analyze a different file")
    # run analyzer
    rc, out = run_cmd([PY, str(ANALYZE)], timeout=180)
    if rc != 0:
        print("[ERROR] analyzer failed on hall scan (rc=%s)" % rc)
    # read JSON and save a timestamped copy
    j = load_json(LAST_JSON)
    if j:
        hall_copy = LOGS / f"last_scan_hall_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
        hall_copy.write_text(json.dumps(j, indent=2), encoding="utf8")
        print(f"[SAVED] hall analyzer JSON -> {hall_copy}")
    return j

def run_short_scan():
    print("\n=== SHORT (near) SCAN ===")
    if not PLAY_SHORT.exists():
        print("[ERROR] missing:", PLAY_SHORT)
        return None
    rc, out = run_cmd([PY, str(PLAY_SHORT)], timeout=120)
    if rc != 0:
        print("[ERROR] short play/record failed (rc=%s)" % rc)
    rc, out = run_cmd([PY, str(ANALYZE)], timeout=120)
    if rc != 0:
        print("[ERROR] analyzer failed on short scan (rc=%s)" % rc)
    j = load_json(LAST_JSON)
    if j:
        short_copy = LOGS / f"last_scan_short_{datetime.datetime.now():%Y%m%d_%H%M%S}.json"
        short_copy.write_text(json.dumps(j, indent=2), encoding="utf8")
        print(f"[SAVED] short analyzer JSON -> {short_copy}")
    return j

def summarize_and_write(hall_json, short_json):
    tstamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = []
    md.append(f"# AVD Demo Report — {tstamp}\n")
    md.append("**What this demo shows**\n\n- Hall-mode long-range echo scanning (300→2500Hz sweep)\n- Short-range high-frequency detection for nearby objects/people\n- Adaptive analysis: chirp detection, adaptive bandpass, template-cancellation, robust peak detection\n\n---\n")
    def small_summary(j, title):
        if not j:
            return f"**{title}**: No JSON result.\n"
        s = []
        s.append(f"**{title}**\n")
        s.append(f"- Input file: `{j.get('input_file')}`")
        s.append(f"- Sample rate: {j.get('samplerate')}  samples: {j.get('samples')}")
        s.append(f"- Chirp start (s): {j.get('chirp_start_s')}")
        band = j.get('estimated_band', [])
        if band:
            s.append(f"- Estimated band (Hz): {band[0]} - {band[1]}")
        s.append(f"- Num echo peaks: {j.get('num_echo_peaks')}")
        dists = j.get('estimated_distances_m', [])
        if dists:
            first = ", ".join(str(x) for x in dists[:5])
            s.append(f"- First distances (m): {first}")
        notes = j.get('notes')
        if notes:
            s.append(f"- Notes: {notes}")
        return "\n".join(s) + "\n"
    md.append(small_summary(hall_json, "Hall scan (long chirp)"))
    md.append("---\n")
    md.append(small_summary(short_json, "Short-range scan (short chirp)"))
    md.append("\n---\n")
    md.append("## How to present to judges\n\n1. Run this script (it runs both scans).  \n2. Show `logs/demo_readable_<ts>.txt` on screen and `logs/demo_report_<ts>.md` if asked for more details.  \n3. Explain: long chirp = hall geometry, short chirp = nearby objects/people.\n")
    # save markdown
    write_text(OUT_MARKDOWN, "\n".join(md))
    # create short text summary
    summary_lines = []
    summary_lines.append("AVD DEMO SUMMARY — " + tstamp)
    summary_lines.append("")
    if hall_json:
        summary_lines.append("HALL: peaks=%d  first distances (m): %s" % (hall_json.get("num_echo_peaks", 0), ", ".join(str(x) for x in hall_json.get("estimated_distances_m", [])[:5])))
    else:
        summary_lines.append("HALL: no data")
    if short_json:
        summary_lines.append("SHORT: peaks=%d  first distances (m): %s" % (short_json.get("num_echo_peaks", 0), ", ".join(str(x) for x in short_json.get("estimated_distances_m", [])[:5])))
    else:
        summary_lines.append("SHORT: no data")
    summary_lines.append("")
    summary_lines.append("Files:")
    summary_lines.append(f"- Last analyzer JSON (final): {LAST_JSON}")
    summary_lines.append(f"- Demo markdown: {OUT_MARKDOWN}")
    summary_lines.append("")
    write_text(OUT_SUMMARY, "\n".join(summary_lines))
    print("\n[DEMO COMPLETE] Written demo report and summary.")

def main():
    ensure_dirs()
    print("AVD demo_run starting (project root):", PROJECT_ROOT)
    hall_json = run_hall_scan()
    # small pause
    time.sleep(0.3)
    short_json = run_short_scan()
    time.sleep(0.3)
    summarize_and_write(hall_json, short_json)
    print("\nYou can present the summary file:", OUT_SUMMARY)
    print("Full report (markdown):", OUT_MARKDOWN)

if __name__ == "__main__":
    main()
