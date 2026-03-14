import numpy as np
import scipy.signal
import time
import os
import pickle
import random
import datetime
from colorama import Fore, Style, init

init(autoreset=True)

# CONFIG (Must match sensor logic)
MIN_FREQ = 2000
MAX_FREQ = 6000

def process_signal(data):
    fs = data['fs']
    received = data['raw_audio']
    duration = data['chirp_duration']

    # DSP: Bandpass
    sos = scipy.signal.butter(10, [MIN_FREQ, MAX_FREQ], btype='bandpass', fs=fs, output='sos')
    clean_signal = scipy.signal.sosfilt(sos, received)

    # Normalize
    if np.max(np.abs(clean_signal)) > 0:
        clean_signal = clean_signal / np.max(np.abs(clean_signal))

    # Ignore Direct Path
    ignore_samples = int(fs * (duration + 0.05))
    analysis_window = clean_signal[ignore_samples:]

    # Peak Detect
    peaks, _ = scipy.signal.find_peaks(np.abs(analysis_window), height=0.15, distance=1000)

    if len(peaks) > 0:
        first_peak = peaks[0] + ignore_samples
        time_delay = (first_peak / fs) - (duration / 2)
        if time_delay < 0: time_delay = 0
        dist = (time_delay * 343.0) / 2.0
        if dist > 40.0: dist = 99.9
        conf = min(0.99, np.abs(clean_signal[first_peak]) * 2.0)
        return dist, conf
    else:
        return 99.9, 0.0

def print_dashboard(dist, conf, latency):
    os.system('cls' if os.name == 'nt' else 'clear')
    ts = datetime.datetime.now().strftime("%H:%M:%S")

    print(Fore.CYAN + "========================================")
    print(Fore.CYAN + "   AVD INTELLIGENCE CORE (PROCESSING)   ")
    print(Fore.CYAN + "========================================")
    print(f" Time: {ts} | Latency: {latency*1000:.0f}ms")
    print("-" * 40)

    if dist < 50:
        print(f" TARGET: {Fore.GREEN}{dist:.2f} m  {Fore.WHITE}|  Conf: {int(conf*100)}%")

        # Simulating context for the demo
        print(f"\n {Fore.YELLOW}Contextual Analysis:")
        if dist < 1.0: print(f"  > CRITICAL PROXIMITY ALERT")
        elif dist < 3.0: print(f"  > Navigable Obstacle Detected")
        else: print(f"  > Open Space / Long Range")

        # Sector Map Visualization (Text UI)
        print(f"\n {Fore.MAGENTA}Sector Map:")
        bar = "█" * int(10 - dist) if dist < 10 else ""
        print(f"  [N] {bar} ({dist:.1f}m)")
        print(f"  [E] ...")
        print(f"  [W] ...")
    else:
        print(f" TARGET: {Fore.RED}NO RETURN SIGNAL")

    print(Fore.CYAN + "========================================")
    print(Fore.WHITE + " Waiting for next sensor packet...")

def main():
    print(Fore.YELLOW + "Initializing Brain... Waiting for Sensor Data stream...")
    last_process_time = 0

    while True:
        try:
            if os.path.exists("avd_data.pkl"):
                # Read Data
                try:
                    with open("avd_data.pkl", "rb") as f:
                        data = pickle.load(f)
                except:
                    continue # File lock contention, skip frame

                # Check if new
                if data['timestamp'] > last_process_time:
                    t0 = time.time()

                    # PROCESS
                    d, c = process_signal(data)

                    # DISPLAY
                    latency = time.time() - t0
                    print_dashboard(d, c, latency)

                    last_process_time = data['timestamp']

            time.sleep(0.05) # Poll rate

        except KeyboardInterrupt:
            print("\nBrain Shutdown.")
            break

if __name__ == "__main__":
    main()