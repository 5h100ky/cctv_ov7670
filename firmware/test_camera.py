# OV7670 diagnostic script — run this FIRST to verify wiring
# Upload to RP2040 Zero and run from Thonny REPL or mpremote
#
# Expected output if wiring is correct:
#   I2C scan: ['0x21']
#   OV7670 PID=0x76 VER=0x73
#   XCLK: OK (8000000 Hz on GP15)
#   VSYNC: TOGGLING (camera is alive)
#   Test PASSED

import time
from machine import Pin, I2C, PWM

SIOD_PIN  = 0
SIOC_PIN  = 1
VSYNC_PIN = 2
XCLK_PIN  = 15
OV7670_ADDR = 0x21

print("=" * 40)
print("OV7670 Camera Diagnostic")
print("=" * 40)

# --- Step 1: XCLK ---
print("\n[1] Starting XCLK on GP15...")
xclk = PWM(Pin(XCLK_PIN))
xclk.freq(8_000_000)
xclk.duty_u16(32768)
time.sleep_ms(200)
print(f"    XCLK: OK ({xclk.freq()} Hz)")

# --- Step 2: I2C scan ---
print("\n[2] Scanning I2C bus (GP0=SDA, GP1=SCL)...")
i2c = I2C(0, scl=Pin(SIOC_PIN), sda=Pin(SIOD_PIN), freq=100_000)
devices = i2c.scan()
print(f"    Found: {[hex(d) for d in devices]}")

if OV7670_ADDR not in devices:
    print("    ERROR: OV7670 (0x21) not found!")
    print("    Check: SIOD→GP0, SIOC→GP1, 4.7k pullups to 3.3V, VCC=3.3V, PWDN→GND, RESET→3.3V")
    xclk.deinit()
    raise SystemExit

print(f"    OV7670 found at 0x{OV7670_ADDR:02X}  OK")

# --- Step 3: Read chip ID ---
print("\n[3] Reading OV7670 chip ID...")
try:
    i2c.writeto(OV7670_ADDR, bytes([0x0A]))
    pid = i2c.readfrom(OV7670_ADDR, 1)[0]
    i2c.writeto(OV7670_ADDR, bytes([0x0B]))
    ver = i2c.readfrom(OV7670_ADDR, 1)[0]
    print(f"    PID=0x{pid:02X}  VER=0x{ver:02X}")
    if pid == 0x76 and ver == 0x73:
        print("    Chip ID matches OV7670  OK")
    elif pid == 0x76:
        print("    PID matches (OV7670 family) but VER unexpected — may still work")
    else:
        print("    WARNING: unexpected chip ID — check module type")
except Exception as e:
    print(f"    ERROR reading ID: {e}")
    xclk.deinit()
    raise SystemExit

# --- Step 4: VSYNC check ---
print("\n[4] Checking VSYNC on GP2 (3 second window)...")
vsync = Pin(VSYNC_PIN, Pin.IN)
transitions = 0
last_val = vsync.value()
t_end = time.ticks_add(time.ticks_ms(), 3000)

while time.ticks_diff(t_end, time.ticks_ms()) > 0:
    v = vsync.value()
    if v != last_val:
        transitions += 1
        last_val = v

if transitions >= 2:
    print(f"    VSYNC is toggling ({transitions} transitions)  OK")
else:
    print(f"    WARNING: VSYNC not toggling ({transitions} transitions)")
    print("    Check: camera may need register init, or VSYNC pin wiring")

# --- Step 5: Write/read register test ---
print("\n[5] Register write/read test (COM2 = 0x09)...")
try:
    i2c.writeto_mem(OV7670_ADDR, 0x09, bytes([0x02]))  # COM2: set output drive 2x
    time.sleep_ms(5)
    i2c.writeto(OV7670_ADDR, bytes([0x09]))
    val = i2c.readfrom(OV7670_ADDR, 1)[0]
    if val == 0x02:
        print("    Write/read OK")
    else:
        print(f"    Mismatch: wrote 0x02, read 0x{val:02X} — possible I2C issue")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n" + "=" * 40)
if transitions >= 2:
    print("Test PASSED — proceed to flash main.py")
else:
    print("Test PARTIAL — camera responds over I2C but VSYNC needs checking")
print("=" * 40)

xclk.deinit()
