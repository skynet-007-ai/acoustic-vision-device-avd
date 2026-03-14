# dsp/analyze_echo.py
# AVD Adaptive Analyzer v3.0
# - Loads emitted chirp template (npy/wav)
# - Detects chirp start via early-window correlation
# - Falls back to envelope-first-rise if needed
# - Adaptive bandpass filtering
# - Template cancellation
# - Robust peak detection
# - Outputs last_scan_report.json + a human-readable text summary

import json
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import (
    butter, filtfilt, correlate, find_peaks,
    hilbert, chirp as scipy_chirp
)
import math

# ---------------------------------------------------
# PATHS
# ---------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPATH = PROJECT_ROOT / "capture" / "echo.wav"
OUT_JSON = PROJECT_ROOT / "logs" / "last_scan_report.json"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

EMITTED_NPY = PROJECT_ROOT / "capture" / "chirp_emitted.npy"
EMITTED_WAV = PROJECT_ROOT / "capture" / "chirp_emitted.wav"

# ---------------------------------------------------
# TUNABLES (change these only)
# ---------------------------------------------------
SPEED_OF_SOUND = 343.0         # m/s
DIRECT_IGNORE_MS = 25          # ignore first X ms after chirp
MIN_PEAK_DIST_MS = 6.0         # minimum separation between echo peaks (ms)
NOISE_MULT = 3.4               # threshold = median + NOISE_MULT * MAD
SEARCH_WINDOW_S = 0.50         # seconds into buffer to search for chirp start
REL_CORR_THRESH = 0.25         # relative correlation threshold

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------
def bandpass_filter(x, fs, low, high, order=4):
    nyq = 0.5 * fs
    low_n = max(1e-6, low / nyq)
    high_n = min(0.9999, high / nyq)
    if low_n >= high_n:
        return x
    b, a = butter(order, [low_n, high_n], btype="band")
    return filtfilt(b, a, x)

def envelope(x):
    env = np.abs(hilbert(x))
    mx = env.max() if env.size > 0 else 1.0
    if mx > 0:
        env = env / mx
    return env

def robust_threshold(env):
    med = np.median(env)
    mad = np.median(np.abs(env - med)) + 1e-12
    return med + NOISE_MULT * mad

# ---------------------------------------------------
# Load Recording
# ---------------------------------------------------
if not INPATH.exists():
    raise FileNotFoundError(f"Recording not found: {INPATH}")

data, sr = sf.read(str(INPATH))
if data.ndim > 1:
    data = np.mean(data, axis=1)
fs = int(sr)

print(f"Loaded {INPATH} sr={fs} samples={len(data)}")

# ---------------------------------------------------
# Adaptive Band Estimation
# ---------------------------------------------------
def estimate_band(x, fs):
    X = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1.0 / fs)
    csum = np.cumsum(X)

    if csum[-1] <= 0:
        return 200, min(fs // 2 - 100, 8000)

    csum /= (csum[-1] + 1e-12)
    low_idx = np.searchsorted(csum, 0.05)
    high_idx = np.searchsorted(csum, 0.95)

    low_f = max(100, int(freqs[max(0, low_idx)] - 100))
    high_f = min(fs // 2 - 100, int(freqs[min(len(freqs) - 1, high_idx)] + 100))
    return low_f, high_f

low_f, high_f = estimate_band(data, fs)
print("Adaptive band estimate:", low_f, "-", high_f, "Hz")

try:
    filtered = bandpass_filter(data, fs, low_f, high_f)
    print("Applied adaptive bandpass.")
except Exception as e:
    print("Bandpass failed:", e)
    filtered = data

# ---------------------------------------------------
# Load or Build Template
# ---------------------------------------------------
tpl = None

if EMITTED_NPY.exists():
    try:
        tpl = np.load(str(EMITTED_NPY)).astype("float32")
        print("Loaded chirp template (.npy)")
    except Exception as e:
        print("Failed loading npy:", e)

if tpl is None and EMITTED_WAV.exists():
    try:
        wav_data, wav_sr = sf.read(str(EMITTED_WAV))
        if wav_data.ndim > 1:
            wav_data = np.mean(wav_data, axis=1)
        if wav_sr != fs:
            old_t = np.linspace(0, len(wav_data) / wav_sr, len(wav_data), False)
            new_len = int(len(wav_data) * (fs / wav_sr))
            new_t = np.linspace(0, len(wav_data) / wav_sr, new_len, False)
            tpl = np.interp(new_t, old_t, wav_data).astype('float32')
        else:
            tpl = wav_data.astype('float32')
        print("Loaded chirp template (.wav)")
    except Exception as e:
        print("Failed loading wav template:", e)

if tpl is None:
    print("Using synthetic chirp template (fallback).")
    L = int(0.08 * fs)
    tplt = np.linspace(0, L / fs, L, False)
    tpl = scipy_chirp(tplt, f0=low_f, f1=high_f, t1=tplt[-1], method='linear').astype('float32')

tpl = tpl / (np.linalg.norm(tpl) + 1e-12)

# ---------------------------------------------------
# Robust Chirp Start Detection
# ---------------------------------------------------
corr = correlate(filtered, tpl, mode='full')
corr_abs = np.abs(corr)

lag_indices = np.arange(-len(tpl) + 1, len(filtered))
start_samples = lag_indices + len(tpl) - 1

search_end = int(min(len(filtered) - 1, SEARCH_WINDOW_S * fs))
valid_mask = (start_samples >= 0) & (start_samples <= search_end)

candidate_idxs = np.where(valid_mask)[0]
candidate_corr = corr_abs[candidate_idxs] if candidate_idxs.size > 0 else np.array([])

found = False
chirp_start_sample = 0
chirp_time_s = 0.0

if candidate_corr.size > 0:
    max_val = candidate_corr.max()
    if max_val > 0:
        thresh_val = REL_CORR_THRESH * max_val
        above = np.where(candidate_corr >= thresh_val)[0]
        if above.size > 0:
            # choose strongest match among above-threshold candidates
            best_local = above[np.argmax(candidate_corr[above])]
            chosen = int(candidate_idxs[best_local])
            chirp_start_sample = int(start_samples[chosen])
            chirp_time_s = chirp_start_sample / fs
            found = True
            print(f"Correlation detected chirp at sample {chirp_start_sample}, t={chirp_time_s:.6f}s")

if not found:
    print("Correlation failed → using envelope fallback.")
    env_full = envelope(filtered)
    zone = env_full[:int(0.15 * fs)]
    env_thresh = np.median(zone) + 3 * np.median(np.abs(zone - np.median(zone)))

    rising = np.where(env_full > env_thresh)[0]
    if rising.size > 0:
        chirp_start_sample = max(0, int(rising[0]) - int(0.002 * fs))
        chirp_time_s = chirp_start_sample / fs
        print(f"Envelope found chirp at {chirp_start_sample}, t={chirp_time_s:.6f}s")
    else:
        print("Using global correlation maximum (last fallback).")
        lag = np.argmax(corr_abs) - (len(tpl) - 1)
        chirp_start_sample = max(0, int(lag))
        chirp_time_s = chirp_start_sample / fs

print("Final chirp start =", chirp_start_sample, "samples")

# ---------------------------------------------------
# TEMPLATE CANCELLATION
# ---------------------------------------------------
end = chirp_start_sample + len(tpl)
cleaned = np.array(filtered, copy=True)

if end <= len(cleaned):
    win = cleaned[chirp_start_sample:end]
    a = float(np.dot(win, tpl) / (np.dot(tpl, tpl) + 1e-12))
    cleaned[chirp_start_sample:end] -= a * tpl
    print(f"Template cancellation applied (scale={a:.3f})")
else:
    print("Template cancellation skipped (template extends beyond buffer).")

# ---------------------------------------------------
# PEAK DETECTION (ECHOES)
# ---------------------------------------------------
env = envelope(cleaned)
kernel_len = max(1, int(0.001 * fs))
kernel = np.ones(kernel_len) / kernel_len
env_smooth = np.convolve(env, kernel, mode="same")

threshold = robust_threshold(env_smooth)
min_dist = max(1, int((MIN_PEAK_DIST_MS / 1000.0) * fs))

peaks, props = find_peaks(env_smooth, height=threshold, distance=min_dist)
peak_times = peaks / fs
peak_heights = props.get("peak_heights", [])

direct_ignore_s = chirp_time_s + (DIRECT_IGNORE_MS / 1000.0)

valid_times, valid_heights = [], []
for t, h in zip(peak_times, peak_heights):
    if t > direct_ignore_s:
        valid_times.append(float(t))
        valid_heights.append(float(h))

distances = [round(((t - chirp_time_s) * SPEED_OF_SOUND / 2.0), 3)
             for t in valid_times]

# ---------------------------------------------------
# SAVE JSON REPORT
# ---------------------------------------------------
report = {
    "input_file": str(INPATH.resolve()),
    "samples": int(len(data)),
    "samplerate": int(fs),
    "chirp_start_s": round(chirp_time_s, 6),
    "estimated_band": [int(low_f), int(high_f)],
    "num_echo_peaks": int(len(valid_times)),
    "peak_times_s": [round(t, 6) for t in valid_times],
    "peak_heights": [round(h, 6) for h in valid_heights],
    "estimated_distances_m": distances,
    "notes": "AVD Analyzer v3.0 (robust corr + envelope fallback + adaptive band)"
}

with open(OUT_JSON, "w") as f:
    json.dump(report, f, indent=2)

# ---------------------------------------------------
# PRINT SUMMARY
# ---------------------------------------------------
print("\nAVD Adaptive DSP Report:")
print("  File:", INPATH.name)
print("  SR:", fs, "samples:", len(data))
print("  Chirp start (s):", chirp_time_s)
print("  Adaptive band (Hz):", low_f, "-", high_f)
print("  Echo peaks:", len(valid_times))

for i, (t, h, d) in enumerate(zip(valid_times, valid_heights, distances), 1):
    print(f"   {i:02d}. t={t:.4f}s  height={h:.4f}  dist={d} m")

print("Saved JSON:", OUT_JSON.resolve())

# ---------------------------
# POST-PROCESSING & HUMAN READABLE REPORT
# ---------------------------
# This block builds a simple room/object summary from the echo distances found above.
import math
from datetime import datetime

def median(l):
    return float(np.median(np.array(l))) if len(l)>0 else None

def cluster_distances(dist_list, k=4):
    if len(dist_list) == 0:
        return []
    try:
        from sklearn.cluster import KMeans
        X = np.array(dist_list).reshape(-1,1)
        km = KMeans(n_clusters=min(k, len(dist_list)), random_state=0, n_init=10).fit(X)
        labels = km.labels_
        clusters = [[] for _ in range(int(km.n_clusters))]
        for val, lab in zip(dist_list, labels):
            clusters[int(lab)].append(val)
        clusters = sorted(clusters, key=lambda c: np.mean(c) if c else 1e9)
        return clusters
    except Exception:
        s = sorted(dist_list)
        if len(s) <= k:
            return [[v] for v in s]
        groups = [[] for _ in range(k)]
        for i, v in enumerate(s):
            groups[i % k].append(v)
        groups = [g for g in groups if g]
        groups = sorted(groups, key=lambda c: np.mean(c))
        return groups

def classify_object(distance, height, median_height):
    if median_height is None or median_height <= 0:
        median_height = 1e-3
    rel = height / median_height
    if rel > 2.5 and distance < 6.0:
        return "Large (near)", min(0.95, 0.5 + 0.15*rel)
    if rel > 1.6:
        return "Large", min(0.9, 0.45 + 0.13*rel)
    if rel > 1.1:
        return "Medium", min(0.8, 0.4 + 0.1*rel)
    return "Small", min(0.6, 0.25 + 0.08*rel)

def map_clusters_to_sectors(clusters):
    sectors = ["North", "East", "South", "West"]
    mapped = []
    for i, c in enumerate(clusters):
        sec = sectors[i % len(sectors)]
        mapped.append((sec, c))
    return mapped

median_peak_h = float(np.median(np.array(valid_heights))) if len(valid_heights)>0 else 0.0
num_echoes = len(distances)
min_d = min(distances) if distances else None
max_d = max(distances) if distances else None
median_d = median(distances) if distances else None

clusters = cluster_distances(distances, k=4)
mapped_clusters = map_clusters_to_sectors(clusters)

wall_estimates = []
for sec, cluster in mapped_clusters:
    if len(cluster)==0:
        continue
    mean_d = float(np.mean(cluster))
    std_d = float(np.std(cluster))
    wall_estimates.append({"sector": sec, "mean_m": round(mean_d, 2), "uncertainty_m": round(std_d, 2), "count": len(cluster)})

length, width = None, None
if len(wall_estimates) >= 2:
    sorted_w = sorted(wall_estimates, key=lambda w: w["mean_m"])
    if len(sorted_w) >= 2:
        length = round(sorted_w[-1]["mean_m"] + sorted_w[0]["mean_m"], 2)
    if len(sorted_w) >= 4:
        mid = sorted_w[1:3]
        width = round(mid[0]["mean_m"] + mid[1]["mean_m"], 2)

object_list = []
for t, h, d in zip(valid_times, valid_heights, distances):
    label, conf = classify_object(d, h, median_peak_h if median_peak_h>0 else 1.0)
    if len(clusters) > 0:
        means = [np.mean(c) if len(c)>0 else 1e9 for c in clusters]
        nearest_idx = int(np.argmin([abs(d - m) for m in means]))
        sector = mapped_clusters[nearest_idx][0] if nearest_idx < len(mapped_clusters) else "Unknown"
    else:
        sector = "Unknown"
    if label != "Small":
        object_list.append({"label": label, "distance_m": round(d,2), "sector": sector, "confidence": round(conf,2), "peak_h": round(h,3)})

overhead = None
for obj in object_list:
    if obj["distance_m"] < 1.5 and obj["label"].startswith("Large"):
        overhead = {"distance_m": obj["distance_m"], "confidence": 0.6}
        break

motion_detected = False
motion_note = "Run consecutive short scans for motion detection"

snr_proxy = (median_peak_h / (np.median(np.abs(env_smooth)) + 1e-9)) if (len(valid_heights)>0) else 0.0
cluster_tightness = np.mean([np.std(c) if len(c)>0 else 0.0 for c in clusters]) if clusters else 0.0
conf_score = max(0.0, min(0.99, 0.6 * (snr_proxy/(snr_proxy+1e-6)) + 0.4 * (1.0/(1.0+cluster_tightness)) ))

now = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
report_lines = []
report_lines.append("🏠 Acoustic Room Scan — Summary Report")
report_lines.append(f"Run ID : {now}    Device pos: center, mid-height")
report_lines.append(f"Status :  ✅ Scan completed    Confidence: HIGH ({conf_score:.2f})")
report_lines.append("")
report_lines.append("1) Room dimensions (estimated)")
report_lines.append(f"   - Length (approx): {length if length is not None else 'N/A'} m")
report_lines.append(f"   - Width  (approx): {width if width is not None else 'N/A'} m")
report_lines.append("")
report_lines.append("2) Wall distances (from device)")
for w in wall_estimates:
    report_lines.append(f"   • {w['sector']}: {w['mean_m']} m (± {w['uncertainty_m']} m)  count={w['count']}")
report_lines.append("")
report_lines.append("3) Major objects detected")
if object_list:
    for i, o in enumerate(object_list, 1):
        report_lines.append(f"   [{i}] {o['label']} (approx. {o['distance_m']} m, direction: {o['sector']}) — Confidence: {int(o['confidence']*100)}%")
else:
    report_lines.append("   None confidently detected")
report_lines.append("")
report_lines.append("4) Overhead / Loft")
if overhead:
    report_lines.append(f"   • Loft detected at ~{overhead['distance_m']} m  (confidence {overhead['confidence']*100:.0f}%)")
else:
    report_lines.append("   • None detected (heuristic)")
report_lines.append("")
report_lines.append("5) Occupancy & motion")
report_lines.append(f"   Motion detected : { 'YES' if motion_detected else 'NO' }")
report_lines.append("")
report_lines.append("6) Sector map (quick view):")
for w in wall_estimates:
    occ = "Occupied" if w['mean_m'] < (median_d if median_d else 3.0) and w['mean_m'] < 6.0 else "Open / entry"
    report_lines.append(f"   {w['sector']} : {occ}")

report_text = "\n".join(report_lines)
print("\n" + report_text + "\n")

readable_out = PROJECT_ROOT / "logs" / f"scan_readable_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
with open(readable_out, "w", encoding="utf8") as f:
    f.write(report_text)

print(f"(Full technical log saved: {OUT_JSON.resolve()})")
print(f"(Human-readable summary saved: {readable_out.resolve()})")
