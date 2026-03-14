import time
import datetime
import os
import random
import sys
from colorama import Fore, Style, init

# Initialize colors
init(autoreset=True)

# ==========================================
#          CONFIGURATION
# ==========================================
CONFIG = {2,
    "MODE_NAME": "Standard",
    "SIMULATION_MODE": True
}


# ==========================================
#          SIMULATED ENGINE
# ==========================================

def configure_mode(mode_choice):
    if mode_choice == '2':
        CONFIG["MODE_NAME"] = "Massive Hall / Long Range"
    else:
        CONFIG["MODE_NAME"] = "Small Room / Lab"


def calibrate_noise_floor():
    print(Fore.YELLOW + "   [CALIBRATION] Measuring room silence (1s)...", end="\r")
    time.sleep(1.0)
    # Return a fake noise floor value
    return 0.0032


def run_simulation_scan():
    """Generates realistic fake data for demo purposes."""

    print(Fore.CYAN + f"   [SIMULATION] Firing {CONFIG['MODE_NAME']}...", end="\r")
    time.sleep(0.8)  # Simulate processing time

    # Generate random distance based on mode
    if "Massive" in CONFIG["MODE_NAME"]:
        # Big room logic: mostly far, sometimes close
        rand_val = random.random()
        if rand_val > 0.8:
            dist = round(random.uniform(1.0, 3.0), 2)  # Close object
        elif rand_val > 0.6:
            dist = round(random.uniform(5.0, 15.0), 2)  # Mid range
        else:
            dist = round(random.uniform(15.0, 45.0), 2)  # Far wall
    else:
        # Small room logic
        dist = round(random.uniform(0.5, 4.0), 2)

    # Calculate fake confidence
    conf = round(random.uniform(0.75, 0.98), 2)

    return dist, conf


# ==========================================
#          REPORT GENERATOR
# ==========================================

def print_summary_report(distance, confidence):
    wall_n = distance

    if "Massive" in CONFIG["MODE_NAME"]:
        wall_e = round(random.uniform(5.0, 8.0), 2)
        wall_w = round(random.uniform(5.0, 8.0), 2)
        wall_s = round(random.uniform(2.0, 5.0), 2)
        ceil_h = 4.50
    else:
        wall_e = round(random.uniform(1.2, 2.5), 2)
        wall_w = round(random.uniform(1.5, 2.5), 2)
        wall_s = round(random.uniform(1.5, 2.0), 2)
        ceil_h = 3.00

    room_l = round(wall_n + wall_s, 2) if distance < 50 else 99.9
    room_w = round(wall_e + wall_w, 2)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    log_file_name = timestamp.replace(":", "") + ".json"

    os.system('cls' if os.name == 'nt' else 'clear')

    # --- HEADER ---
    print(Fore.CYAN + "____________________________________________________________\n")
    print(Fore.CYAN + f" 🏠 Acoustic Vision - {CONFIG['MODE_NAME']} (SIMULATION)")
    print(Fore.CYAN + "____________________________________________________________")
    print(f" Run ID : {Fore.MAGENTA}{timestamp:<20} {Fore.RESET} Device pos: {Fore.CYAN}Laptop Sim")

    status_icon = f"{Fore.GREEN}☑ Scan completed"
    print(f" Status : {status_icon:<20} {Fore.RESET} Confidence: {Fore.CYAN}HIGH ({confidence:.2f})")
    print(Fore.CYAN + "_" * 60 + "\n")

    # --- 1) Room dimensions ---
    print(Fore.MAGENTA + " 1) Geometry (estimated)")
    print(f"    • Length : {Fore.MAGENTA}{room_l:.2f} m   {Fore.CYAN}(± 0.2m)")
    print(f"    • Width  : {Fore.MAGENTA}{room_w:.2f} m   {Fore.CYAN}(± 0.2m)")
    print(f"    • Height : {Fore.MAGENTA}{ceil_h:.2f} m   {Fore.CYAN}(Scanner est.)\n")

    # --- 2) Wall distances ---
    print(Fore.CYAN + " 2) Wall distances (from device)")
    print(f"    • Wall A (front) : {Fore.MAGENTA}{wall_n:.2f} m   {Fore.CYAN}(uncertainty ±0.5m) [SIMULATED]")
    print(f"    • Wall B (right) : {Fore.MAGENTA}{wall_e:.2f} m   {Fore.CYAN}(uncertainty ±0.8m)")
    print(f"    • Wall C (back)  : {Fore.MAGENTA}{wall_s:.2f} m   {Fore.CYAN}(uncertainty ±0.5m)")
    print(f"    • Wall D (left)  : {Fore.MAGENTA}{wall_w:.2f} m   {Fore.CYAN}(uncertainty ±0.8m)\n")

    # --- 3) Major objects ---
    print(Fore.CYAN + " 3) Major objects detected")
    if distance > 10.0:
        print(f"    [1] {Fore.GREEN}Open Hall {Fore.CYAN}- Long range path clear ({distance:.2f} m)")
    elif distance > 2.0:
        print(f"    [1] {Fore.GREEN}Obstacle {Fore.CYAN}- Mid-range object ({distance:.2f} m)")
    else:
        print(f"    [1] {Fore.RED}Proximity {Fore.CYAN}- Close object ({distance:.2f} m)")

    print(f"    [2] {Fore.GREEN}Side Structure {Fore.CYAN}- Vertical element (approx. {wall_e:.2f} m)\n")

    print(Fore.CYAN + "_" * 60 + "\n")

    # --- 4) Overhead ---
    print(Fore.CYAN + " 4) Overhead / Ceiling")
    print(f"    • Ceiling detected at {Fore.CYAN}~{ceil_h} m height\n")

    # --- 5) Occupancy ---
    print(Fore.RED + " 5) Occupancy & motion")
    print(f"    • Motion detected : {Fore.CYAN}NO")
    print(f"    • Door zone       : {Fore.GREEN}OPEN\n")

    # --- 6) Sector map ---
    print(Fore.GREEN + " 6) Sector map (quick view)")
    if distance > 3.0:
        print(f"    • North : {Fore.GREEN}OPEN")
    else:
        print(f"    • North : {Fore.RED}BLOCKED")
    print(f"    • East  : {Fore.GREEN}Clear")
    print(f"    • South : {Fore.CYAN}Occupied")
    print(f"    • West  : {Fore.GREEN}Clear")

    # --- FOOTER ---
    print(Fore.CYAN + "\n____________________________________________________________")
    print(Fore.CYAN + " INTERPRETATION & SUGGESTED ACTIONS")

    if distance > 10.0:
        print(f" • {Fore.GREEN}LARGE SPACE:{Fore.RESET} Suitable for rapid navigation.")
    elif distance < 2.0:
        print(f" • {Fore.RED}ALERT:{Fore.RESET} Object nearby. Navigation caution.")
    else:
        print(f" • {Fore.YELLOW}STANDARD:{Fore.RESET} Navigation safe.")

    print(Fore.GREEN + f" (Full technical log saved: /home/user/scans/{log_file_name})")
    print(Fore.CYAN + "____________________________________________________________")


# ==========================================
#              MAIN LOOP
# ==========================================

if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')

    print(Fore.CYAN + Style.BRIGHT + "\n================================================")
    print(Fore.CYAN + Style.BRIGHT + "   AVD: ACOUSTIC VISION DEVICE (LAPTOP SIM)     ")
    print(Fore.CYAN + Style.BRIGHT + "================================================")

    print(Fore.YELLOW + "SELECT SIMULATION MODE:")
    print(" [1] Small Room / Bedroom / Office")
    print(" [2] Massive Lecture Hall / Warehouse")

    choice = input(Fore.WHITE + "\nSelect Mode (1 or 2): ")
    configure_mode(choice)

    print(Fore.GREEN + f"\n   Initializing {CONFIG['MODE_NAME']}...")
    time.sleep(1)

    # Calibration Simulation
    noise_level = calibrate_noise_floor()
    print(f"{Fore.GREEN}Calibration Complete. Noise Floor: {noise_level:.4f}")

    while True:
        try:
            input(Fore.GREEN + "\n   Press ENTER to Simulate Scan (CTRL+C to quit)...")

            # Run Simulation
            dist, conf = run_simulation_scan()

            # Processing FX
            print(Fore.YELLOW + "   [DSP] Filtering Reverb...", end="\r")
            time.sleep(0.4)
            print(Fore.YELLOW + "   [AI]  Mapping Geometry...", end="\r")
            time.sleep(0.4)

            # Report
            print_summary_report(dist, conf)

        except KeyboardInterrupt:
            print(Fore.RED + "\nSystem Halted.")
            break