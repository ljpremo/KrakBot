#!/usr/bin/env python3
import sys, os, subprocess, platform

# List of Python packages we need
REQUIREMENTS = ["krakenex", "keyring", "colorama"]

def install(packages):
    for pkg in packages:
        try:
            __import__(pkg)
            print(f"[✔] {pkg} already installed")
        except ImportError:
            print(f"[→] Installing {pkg}…")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

def main():
    print("\n=== krakbot Setup ===\n")
    # Detect OS
    sys_plat = sys.platform
    if sys_plat.startswith("win"):
        detected = "Windows"
    elif sys_plat == "darwin":
        detected = "macOS"
    else:
        detected = "Linux/Termux/Other"
    print(f"Detected OS: {detected}")
    choice = input("Press Enter to accept, or type 1)Windows  2)macOS  3)Linux/Termux: ").strip()
    # (We could override, but for simplicity, we'll skip custom logic here.)

    # Install dependencies
    install(REQUIREMENTS)

    # Create config directory
    if sys_plat.startswith("win"):
        base = os.getenv("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.config")
    cfg_dir = os.path.join(base, "krakbot")
    os.makedirs(cfg_dir, exist_ok=True)
    print(f"[✔] Config directory created at {cfg_dir}")

    print("\nSetup complete!  Run `python krakbot.py` to start your bot.\n")

if __name__ == "__main__":
    main()
