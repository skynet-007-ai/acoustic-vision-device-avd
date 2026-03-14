'''(avd_sensor.py): The "Ears". It only handles the microphone and speaker. It captures raw audio and dumps it to a buffer. It runs fast and blindly.'''



import numpy as np
import scipy.signal
import sounddevice as sd
import time
import os
import pickle
from colorama import Fore, init

init(autoreset=True)

# CONFIG
SAMPLE_RATE = 44100
CHIRP_DURATION = 0.2
RECORD_DURATION = 1.5
MIN_FREQ = 2000
MAX_FREQ = 6000
DEVICE_ID = None  # Will prompt


def setup_hardware():
    print(Fore.CYAN + "--- HARDWARE SENSOR SETUP ---")
    print(sd.query_devices())
    try:
        dev_id = int(input(Fore.YELLOW + "Enter USB Device ID: "))
        return dev_id
    except:
        return None


def generate_chirp(fs, duration):
    t = np.linspace(0, duration, int(fs * duration))
    chirp = scipy.signal.chirp(t, f0=MIN_FREQ, f1=MAX_FREQ, t1=duration, method='linear')
    window = np.hanning(len(chirp))
    return chirp * window


def main():
    device_id = setup_hardware()
    fs = SAMPLE_RATE

    # Pre-generate chirp
    chirp = generate_chirp(fs, CHIRP_DURATION)
    silence = np.zeros(int(fs * RECORD_DURATION) - len(chirp))
    out_signal = np.concatenate((chirp, silence))

    # Stereo upmix
    out_signal = np.column_stack((out_signal, out_signal))

    print(Fore.GREEN + "\n>>> SENSOR ACTIVE: CONTINUOUS SCANNING <<<")
    scan_count = 0

    try:
        while True:
            start_time = time.time()

            # 1. HARDWARE IO
            print(Fore.CYAN + f"[{scan_count}] Pinging...", end="\r")
            recording = sd.playrec(out_signal, samplerate=fs, channels=1, dtype='float64', device=device_id)
            sd.wait()

            # 2. SAVE RAW DATA (The "Handoff")
            # We save the raw audio + the chirp parameters so the brain knows what to look for
            data_packet = {
                "timestamp": start_time,
                "fs": fs,
                "chirp_duration": CHIRP_DURATION,
                "raw_audio": recording.flatten()
            }

            # Atomic write (write to temp then rename to avoid read conflicts)
            with open("avd_buffer.tmp", "wb") as f:
                pickle.dump(data_packet, f)

            # Signal ready
            if os.path.exists("avd_data.pkl"):
                os.remove("avd_data.pkl")
            os.rename("avd_buffer.tmp", "avd_data.pkl")

            scan_count += 1
            # fast sleep just to let the drive catch up
            time.sleep(0.1)

    except KeyboardInterrupt:
        print(Fore.RED + "\nSensor Halted.")


if __name__ == "__main__":
    main()