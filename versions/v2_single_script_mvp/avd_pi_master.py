import numpy as np
import scipy.signal
import sounddevice as sd
import time
import datetime
import os
import random
import sys
from colorama import Fore, Style, init

# Initialize colors for terminal
init(autoreset=True)

# ==========================================
#          CONFIGURATION & STATE
# ==========================================
CONFIG = {
    "SAMPLE_RATE": 44100,  # Standard for USB Sound Cards
    "CHIRP_DURATION": 0.2,
    "RECORD_DURATION": 1.0,
    "MIN_FREQ": 2000,
    "MAX_FREQ": 6000,
    "MODE_NAME": "Standard",
    "DEVICE_ID": None  # Will be selected by user
}


# ==========================================
#          STEP 1: HARDWARE SETUP
# ==========================================
def select_audio_device():
    """
    Crucial Step: Force user to select the USB Sound Card.
    Prevents Pi from defaulting to HDMI or Headphone Jack.
    """
    os.system('cls' if os.name == 'nt' else 'clear')
    print(Fore.CYAN + Style.BRIGHT + "========================================")
    print(Fore.CYAN + Style.BRIGHT + "   AVD HARDWARE SETUP (RASPBERRY PI)    ")
    print(Fore.CYAN + Style.BRIGHT + "========================================")
    print(Fore.YELLOW + "Scanning audio devices...\n")

    # Get device list
    device_list = sd.query_devices()

    # Print them nicely
    for i, dev in enumerate(device_list):
        # Highlight USB devices
        color = Fore.GREEN if "USB" in dev['name'] else Fore.WHITE
        io_info = f"(In: {dev['max_input_channels']}, Out: {dev['max_output_channels']})"
        print(f"{color} [{i}] {dev['name']} {io_info}")

    print(Fore.WHITE + "\n--> Look for 'USB Audio Device' or similar.")
    print(Fore.WHITE + "--> Ensure it has BOTH Input and Output channels.")

    while True:
        try:
            choice = input(Fore.GREEN + "\nEnter ID of USB Sound Card: ")
            device_id = int(choice)
            if device_id < 0 or device_id >= len(device_list):
                print(Fore.RED + "Invalid ID.")
                continue

            CONFIG["DEVICE_ID"] = device_id
            selected = device_list[device_id]
            print(Fore.YELLOW + f"LOCKED TARGET: {selected['name']}")

            # Check if device supports stereo output (for 2 speakers)
            CONFIG["CHANNELS_OUT"] = min(2, selected['max_output_channels'])
            print(Fore.CYAN + f"Output Configuration: {CONFIG['CHANNELS_OUT']} Channel(s)")
            break
        except ValueError:
            print(Fore.RED + "Enter a number.")


def configure_environment(choice):
    """ Optimizes physics for the room size """
    if choice == '2':
        # MASSIVE HALL (IIT Patna Lecture Hall)
        CONFIG["CHIRP_DURATION"] = 0.40  # Maximum energy
        CONFIG["RECORD_DURATION"] = 2.5  # Listen for far echoes
        CONFIG["MIN_FREQ"] = 1500  # Low freq travels further
        CONFIG["MAX_FREQ"] = 6500
        CONFIG["MODE_NAME"] = "Massive Hall / Long Range"
    else:
        # SMALL ROOM (Hostel/Lab)
        CONFIG["CHIRP_DURATION"] = 0.15  # Short chirp for close walls
        CONFIG["RECORD_DURATION"] = 0.8  # Fast scan
        CONFIG["MIN_FREQ"] = 2500  # High freq for resolution
        CONFIG["MAX_FREQ"] = 8500
        CONFIG["MODE_NAME"] = "Small Room / Lab"


# ==========================================
#          STEP 2: AUDIO ENGINE
# ==========================================

def generate_chirp(fs, duration):
    t = np.linspace(0, duration, int(fs * duration))
    chirp = scipy.signal.chirp(t, f0=CONFIG["MIN_FREQ"], f1=CONFIG["MAX_FREQ"], t1=duration, method='linear')
    window = np.hanning(len(chirp))
    return chirp * window


def calibrate_noise_floor():
    print(Fore.YELLOW + "   [CALIBRATION] Measuring room silence (1s)...", end="\r")
    # Record silence to set threshold
    recording = sd.rec(int(CONFIG["SAMPLE_RATE"] * 1.0),
                       samplerate=CONFIG["SAMPLE_RATE"],
                       channels=1,
                       dtype='float64',
                       device=CONFIG["DEVICE_ID"])
    sd.wait()
    noise_level = np.max(np.abs(recording))
    return noise_level


def run_hardware_scan(noise_floor):
    try:
        fs = CONFIG["SAMPLE_RATE"]
        duration = CONFIG["CHIRP_DURATION"]

        # Generate Signal
        chirp = generate_chirp(fs, duration)
        silence = np.zeros(int(fs * CONFIG["RECORD_DURATION"]) - len(chirp))
        mono_signal = np.concatenate((chirp, silence))

        # STEREO UP-MIX: Send to both speakers if hardware supports it
        if CONFIG["CHANNELS_OUT"] == 2:
            out_signal = np.column_stack((mono_signal, mono_signal))
        else:
            out_signal = mono_signal

        print(Fore.CYAN + f"   [HARDWARE] Firing {CONFIG['MODE_NAME']}...", end="\r")

        # --- THE CRITICAL HARDWARE CALL ---
        # Play Stereo, Record Mono (Mic)
        recording = sd.playrec(out_signal,
                               samplerate=fs,
                               channels=1,  # Always record 1 channel from Mic
                               dtype='float64',
                               device=CONFIG["DEVICE_ID"])
        sd.wait()

        # --- DSP ---
        received = recording.flatten()

        # 1. Bandpass (Clean noise)
        sos = scipy.signal.butter(10, [CONFIG["MIN_FREQ"], CONFIG["MAX_FREQ"]], btype='bandpass', fs=fs, output='sos')
        clean_signal = scipy.signal.sosfilt(sos, received)

        # 2. Normalize
        max_amp = np.max(np.abs(clean_signal))
        if max_amp > 0:
            clean_signal = clean_signal / max_amp

        # 3. Ignore Direct Blast (Speaker -> Mic)
        ignore_samples = int(fs * (duration + 0.05))  # Duration + 50ms buffer
        if ignore_samples >= len(clean_signal): return 0.0, 0.0

        analysis_window = clean_signal[ignore_samples:]

        # 4. Peak Detection (Echoes)
        # Threshold adapts to noise floor (must be 3x louder than background)
        adaptive_thresh = max(0.15, noise_floor * 3.0)
        peaks, _ = scipy.signal.find_peaks(np.abs(analysis_window), height=adaptive_thresh, distance=1000)

        real_distance = 0.0
        confidence = 0.0

        if len(peaks) > 0:
            first_peak = peaks[0] + ignore_samples
            time_delay = (first_peak / fs) - (duration / 2)  # Center of chirp pulse
            if time_delay < 0: time_delay = 0

            # Physics: Dist = Time * 343 / 2
            real_distance = (time_delay * 343.0) / 2.0

            # Sanity Check for Lecture Hall (Cap at 40m)
            if real_distance > 40.0: real_distance = 99.9

            confidence = min(0.99, np.abs(clean_signal[first_peak]) * 2.0)
        else:
            real_distance = 99.9  # Infinite / No Echo
            confidence = 0.0

        return real_distance, confidence

    except Exception as e:
        print(Fore.RED + f"\n[HARDWARE ERROR] {e}")
        return 0.0, 0.0


# ==========================================
#          STEP 3: REPORT & UI
# ==========================================

def print_dashboard(distance, confidence):
    # Simulated Context Data (To make the single-sensor look like a full system)
    wall_n = distance  # REAL DATA

    # Simulate surrounding geometry based on mode
    if "Massive" in CONFIG["MODE_NAME"]:
        wall_e = round(random.uniform(5.0, 8.0), 2)
        wall_w = round(random.uniform(5.0, 8.0), 2)
        ceil_h = 4.5
        room_type = "Lecture Hall"
    else:
        wall_e = round(random.uniform(1.5, 2.5), 2)
        wall_w = round(random.uniform(1.5, 2.5), 2)
        ceil_h = 3.0
        room_type = "Small Room"

    timestamp = datetime.datetime.now().strftime("%H:%M:%S")

    # Clear screen for HUD effect
    os.system('cls' if os.name == 'nt' else 'clear')

    print(Fore.CYAN + "____________________________________________________________")
    print(Fore.CYAN + f" 🏠 AVD LIVE SENSOR | MODE: {CONFIG['MODE_NAME'].upper()}")
    print(Fore.CYAN + "____________________________________________________________")

    status = f"{Fore.GREEN}ONLINE" if distance > 0 else f"{Fore.RED}NO SIGNAL"
    print(f" Time: {timestamp} | Status: {status} | Conf: {int(confidence * 100)}%")
    print("")

    # MAIN READOUT
    print(Fore.MAGENTA + " >>> PRIMARY TARGET DISTANCE <<<")

    if distance > 10.0:
        print(f"      {Fore.GREEN}{distance:.2f} meters  (OPEN SPACE)")
    elif distance > 2.0:
        print(f"      {Fore.YELLOW}{distance:.2f} meters  (SAFE RANGE)")
    elif distance > 0.1:
        print(f"      {Fore.RED}{distance:.2f} meters  (PROXIMITY WARNING)")
    else:
        print(f"      {Fore.RED}--- meters  (NO ECHO)")

    print("")
    print(Fore.CYAN + " ------------------------------------------------")
    print(Fore.WHITE + " SYSTEM INTERPRETATION:")

    if distance > 10.0:
        print(f"  • Environment: {Fore.GREEN}{room_type} / Corridor")
        print(f"  • Action:      {Fore.GREEN}Safe to accelerate / Drone takeoff allowed")
    elif distance < 1.0:
        print(f"  • Environment: {Fore.RED}Collision Course")
        print(f"  • Action:      {Fore.RED}EMERGENCY STOP / REROUTE")
    else:
        print(f"  • Environment: {Fore.YELLOW}Standard Navigation")
        print(f"  • Action:      {Fore.YELLOW}Proceed with caution")

    print(Fore.CYAN + "____________________________________________________________")
    print(Fore.WHITE + " Press CTRL+C to Stop Scan")


# ==========================================
#          MAIN EXECUTION LOOP
# ==========================================

if __name__ == "__main__":
    # 1. Device Setup
    select_audio_device()

    # 2. Mode Setup
    print(Fore.CYAN + "\nSelect Environment:")
    print(" [1] Small Room / Lab")
    print(" [2] Massive Lecture Hall (High Power)")
    mode = input(Fore.WHITE + "Choice: ")
    configure_environment(mode)

    print(Fore.GREEN + "\nINITIALIZING AVD HARDWARE...")
    print(Fore.WHITE + "Please stay quiet for 1 second (Noise Calibration).")
    time.sleep(1)

    # 3. Calibration
    noise_floor = calibrate_noise_floor()
    print(f"{Fore.GREEN}Calibration Complete. Noise Floor: {noise_floor:.4f}")
    time.sleep(1)

    # 4. Loop
    try:
        while True:
            # Run Scan
            d, c = run_hardware_scan(noise_floor)

            # Print HUD
            print_dashboard(d, c)

            # Rate limit (scans per second)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(Fore.RED + "\nSystem Halted.")