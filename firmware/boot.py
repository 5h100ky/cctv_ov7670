# boot.py — optional auto-start
# Rename this to boot.py on the RP2040 to launch CCTV automatically on power-up.
# Press Ctrl+C within 3 seconds in Thonny to abort and enter REPL.

import time
import sys

print("RP2040 CCTV booting... (Ctrl+C within 3s to abort)")
for i in range(3, 0, -1):
    print(f"  Starting in {i}...")
    time.sleep(1)

try:
    import main  # runs the CCTV stream
except KeyboardInterrupt:
    print("Aborted. REPL available.")
except Exception as e:
    sys.stderr.write(f"Boot error: {e}\n")
