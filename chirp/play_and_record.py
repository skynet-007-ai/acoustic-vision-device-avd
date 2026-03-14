# chirp/play_and_record.py
# Short chirp emitter for room-scale scans.
# Saves:
#  - capture/chirp_emitted.npy  (template)
#  - capture/chirp_emitted.wav  (template WAV)
#  - capture/echo.wav           (recording)

import os
from pathlib import Path
import time
import sys

import numpy as np
from scipy.signal import chirp
import sounddevice as sd
import soundfile as sf

# Device configuration (change indices if needed)
OUTPUT_INDEX = 4   # your working speaker index
INPUT_INDEX = None # None -> default input (microphone)

# Paths
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
CAPTURE_DIR = PROJECT_ROOT / "capture"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

OUTPATH = CAPTURE_DIR / "echo.wav"
TPL_NPY = CAPTURE_DIR / "chirp_emitted.npy"
TPL_WAV = CAPTURE_DIR / "chirp_emitted.wav"

# Audio params (room)
fs = 44100
chirp_duration = 0.15  # seconds
record_duration = 0.6  # must be > chirp_duration
f0 = 2000               # start freq (Hz)
f1 = 8000               # end freq (Hz)
amplitude = 0.7

if record_duration <= chirp_duration:
    print("Error: record_duration must be > chirp_duration")
    sys.exit(1)

# Build chirp waveform
t = np.linspace(0, chirp_duration, int(chirp_duration * fs), endpoint=False)
chirp_sig = (chirp(t, f0=f0, f1=f1, t1=chirp_duration, method='linear') * amplitude).astype('float32')

# Save template (npy + wav)
try:
    np.save(str(TPL_NPY), chirp_sig)
    sf.write(str(TPL_WAV), chirp_sig, fs)
    print("Saved chirp template.")
except Exception as e:
    print("Failed saving template:", repr(e))

# Play buffer (chirp + silence)
silence_len = int((record_duration - chirp_duration) * fs)
play_buffer = np.concatenate([chirp_sig, np.zeros(silence_len, dtype='float32')])

# Set audio devices
sd.default.device = (INPUT_INDEX, OUTPUT_INDEX)
print("Using devices (input, output):", sd.default.device)
try:
    print("Output device info:", sd.query_devices(OUTPUT_INDEX))
except Exception as e:
    print("Error querying output device:", repr(e))

# Small pause
time.sleep(0.12)

# Play & record
try:
    print(f"Playing chirp ({chirp_duration}s) and recording {record_duration}s...")
    recording = sd.playrec(play_buffer, samplerate=fs, channels=1, dtype='float32')
    sd.wait()
    recording = recording.flatten()
    print("Recording complete. Samples:", len(recording))
except Exception as e:
    print("Error during playrec:", repr(e))
    raise

# Save recording
try:
    sf.write(str(OUTPATH), recording, fs, subtype='PCM_16')
    print("Saved echo recording ->", OUTPATH)
except Exception as e:
    print("Error saving WAV:", repr(e))
    raise

print("Done.")
