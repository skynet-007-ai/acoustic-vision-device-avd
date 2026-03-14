# chirp/play_and_record_hall.py
# Hall-optimized chirp: lower freq, longer duration, longer recording to capture far echoes.
# Saves capture/echo_hall.wav and chirp_emitted.npy / chirp_emitted.wav

from pathlib import Path
import time, sys
import numpy as np
from scipy.signal import chirp
import sounddevice as sd
import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CAPTURE_DIR = PROJECT_ROOT / "capture"
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
OUTPATH = CAPTURE_DIR / "echo_hall.wav"
TPL_NPY = CAPTURE_DIR / "chirp_emitted.npy"
TPL_WAV = CAPTURE_DIR / "chirp_emitted.wav"

# Devices (adjust if necessary)
OUTPUT_INDEX = 4
INPUT_INDEX = None
sd.default.device = (INPUT_INDEX, OUTPUT_INDEX)
time.sleep(0.12)

# Hall-tuned parameters
fs = 44100
chirp_duration = 0.6      # longer chirp for more energy
record_duration = 3.0     # long record to capture late echoes
f0 = 300                  # low start frequency
f1 = 2500                 # end freq
amplitude = 0.9           # loud (reduce if speaker rattles)

# Build chirp and save template
t = np.linspace(0, chirp_duration, int(chirp_duration * fs), endpoint=False)
chirp_sig = (chirp(t, f0=f0, f1=f1, t1=chirp_duration, method='linear') * amplitude).astype('float32')

# Save template (npy + wav)
try:
    np.save(str(TPL_NPY), chirp_sig)
    sf.write(str(TPL_WAV), chirp_sig, fs)
    print("Saved chirp template (hall).")
except Exception as e:
    print("Failed saving template:", repr(e))

# Play buffer & record
silence_len = int((record_duration - chirp_duration) * fs)
play_buffer = np.concatenate([chirp_sig, np.zeros(silence_len, dtype='float32')])

print("Using device (in,out):", sd.default.device)
print(f"Playing hall chirp {chirp_duration}s ({f0}->{f1}Hz) and recording {record_duration}s ...")
try:
    rec = sd.playrec(play_buffer, samplerate=fs, channels=1, dtype='float32')
    sd.wait()
    rec = rec.flatten()
    sf.write(str(OUTPATH), rec, fs, subtype='PCM_16')
    print("Saved:", OUTPATH, "samples=", len(rec))
except Exception as e:
    print("Error during playrec:", repr(e))
    sys.exit(1)
