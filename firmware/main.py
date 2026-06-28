# OV7670 CCTV firmware for RP2040 Zero
# Streams QQVGA (160x120) grayscale frames over USB-CDC to PC viewer
#
# === WIRING (OV7670 → RP2040 Zero) ===
#  3.3V  → 3V3
#  GND   → GND
#  SIOD  → GP0  (SDA / SCCB data)
#  SIOC  → GP1  (SCL / SCCB clock)
#  VSYNC → GP2
#  D0    → GP4   \
#  D1    → GP5    |
#  D2    → GP6    |  8-bit parallel data
#  D3    → GP7    |  (must be consecutive GPIOs)
#  D4    → GP8    |
#  D5    → GP9    |
#  D6    → GP10   |
#  D7    → GP11  /
#  PCLK  → GP12
#  HREF  → GP13
#  XCLK  → GP15  (PWM ~8 MHz output to camera)
#  RESET → 3V3   (tie high to keep out of reset)
#  PWDN  → GND   (tie low to enable camera)

import time
import sys
import struct
from machine import Pin, I2C, PWM
import rp2
from ov7670 import OV7670

# --- Pin constants ---
SIOD_PIN  = 0
SIOC_PIN  = 1
VSYNC_PIN = 2
D0_PIN    = 4   # D0–D7 are GP4–GP11
PCLK_PIN  = 12  # GP4 + 8
HREF_PIN  = 13  # GP4 + 9  (also the PIO jmp_pin)
XCLK_PIN  = 15

# --- Frame geometry ---
WIDTH  = 160
HEIGHT = 120
# OV7670 YUV422: 2 bytes per pixel (Y, U/V alternating); we keep only Y
BYTES_PER_PIXEL = 2
FRAME_BYTES = WIDTH * HEIGHT * BYTES_PER_PIXEL  # raw bytes from PIO

# --- USB-CDC frame protocol ---
# <MAGIC 4B> <width 2B LE> <height 2B LE> <grayscale pixels W*H bytes>
MAGIC = b'\xAA\x55\xAA\x55'


# ---------------------------------------------------------------------------
# PIO program
# ---------------------------------------------------------------------------
# in_base = GP4 (D0).  Offsets from in_base:
#   pins 0-7  → D0-D7 (GP4-GP11)
#   pin  8    → PCLK  (GP12)   used in wait()
#   pin  9    → HREF  (GP13)   used in wait(); jmp_pin is also GP13
#
# Operation per frame line:
#   1. Wait for HREF high  → line active
#   2. On each PCLK rising edge, sample 8 data bits (auto-push every byte)
#   3. When HREF goes low  → wrap back and wait for next HREF
# ---------------------------------------------------------------------------
@rp2.asm_pio(
    in_shiftdir=rp2.PIO.SHIFT_LEFT,
    autopush=True,
    push_thresh=8,
)
def _ov7670_pio():
    wrap_target()
    wait(1, pin, 9)        # wait for HREF high (pin offset 9 = GP13)
    label("pixel")
    wait(0, pin, 8)        # wait PCLK low   (pin offset 8 = GP12)
    wait(1, pin, 8)        # wait PCLK rising
    in_(pins, 8)           # sample D0-D7; auto-push fires after 8 bits
    jmp(pin, "pixel")      # jmp_pin=HREF: if still high, next pixel
    wrap()                 # HREF low → back to wait for next line


def _make_sm() -> rp2.StateMachine:
    return rp2.StateMachine(
        0,
        _ov7670_pio,
        freq=133_000_000,
        in_base=Pin(D0_PIN),   # D0-D7 input base
        jmp_pin=Pin(HREF_PIN), # HREF controls jmp(pin,...)
    )


# ---------------------------------------------------------------------------
# XCLK generation (~8 MHz square wave via PWM)
# ---------------------------------------------------------------------------
def _start_xclk() -> PWM:
    xclk = PWM(Pin(XCLK_PIN))
    xclk.freq(8_000_000)
    xclk.duty_u16(32768)  # 50% duty cycle
    return xclk


# ---------------------------------------------------------------------------
# Capture one full grayscale frame
# Returns bytearray of WIDTH*HEIGHT bytes (Y channel), or None on timeout.
#
# VSYNC timing (OV7670 default, COM10=0x00):
#   VSYNC pulses HIGH for ~3 lines at the START of each frame.
#   After VSYNC falls LOW, HREF starts going HIGH for each active line.
# ---------------------------------------------------------------------------
_VSYNC_TIMEOUT = 8_000_000   # spin iterations (~2-3 s at 125 MHz)
_FIFO_TIMEOUT  = 300_000     # spin iterations (~few ms)

def capture_frame(sm: rp2.StateMachine, vsync: Pin):
    gray = bytearray(WIDTH * HEIGHT)

    # Drain stale FIFO content from previous frame
    while sm.rx_fifo():
        sm.get()

    # --- Sync to VSYNC rising edge ---
    t = _VSYNC_TIMEOUT
    while vsync.value() == 1 and t:   # skip if already in a pulse
        t -= 1
    if t == 0:
        return None
    t = _VSYNC_TIMEOUT
    while vsync.value() == 0 and t:   # wait for rising edge
        t -= 1
    if t == 0:
        return None
    # VSYNC is HIGH → wait for it to fall (end of sync pulse, lines follow)
    while vsync.value() == 1:
        pass

    # --- Collect WIDTH*HEIGHT*2 raw YUV bytes; keep even bytes (Y channel) ---
    total_raw = WIDTH * HEIGHT * BYTES_PER_PIXEL
    idx    = 0
    byte_n = 0

    while byte_n < total_raw:
        # Non-blocking poll with timeout so a stalled camera doesn't hang forever
        t = _FIFO_TIMEOUT
        while not sm.rx_fifo() and t:
            t -= 1
        if t == 0:
            return None   # camera stopped sending (PCLK/HREF problem)

        raw = sm.get()
        if not (byte_n & 1):          # even byte = Y (luminance)
            gray[idx] = raw & 0xFF
            idx += 1
        byte_n += 1

    return gray


# ---------------------------------------------------------------------------
# Send a grayscale frame over USB-CDC
# ---------------------------------------------------------------------------
def send_frame(data: bytearray) -> None:
    header = MAGIC + struct.pack('<HH', WIDTH, HEIGHT)
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # 1. Start XCLK before camera init
    xclk = _start_xclk()
    time.sleep_ms(50)

    # 2. Init OV7670 over SCCB (I2C0)
    i2c = I2C(0, scl=Pin(SIOC_PIN), sda=Pin(SIOD_PIN), freq=100_000)
    cam = OV7670(i2c)

    pid, ver = cam.read_id()
    # Expected: PID=0x76, VER=0x73  (print to stderr so it doesn't corrupt stream)
    sys.stderr.write(f"OV7670 PID=0x{pid:02X} VER=0x{ver:02X}\n")

    cam.init()
    time.sleep_ms(300)

    # 3. Set up PIO state machine
    vsync = Pin(VSYNC_PIN, Pin.IN)
    sm = _make_sm()
    sm.active(1)

    # 4. Main loop: capture and stream frames
    sys.stderr.write("Streaming started. Waiting for frames...\n")
    frame_n    = 0
    t_last_fps = time.ticks_ms()

    while True:
        try:
            frame = capture_frame(sm, vsync)
            if frame is None:
                sys.stderr.write("Frame timeout - check camera wiring (VSYNC/HREF/PCLK)\n")
                time.sleep_ms(500)
                continue

            send_frame(frame)
            frame_n += 1

            # Print FPS to stderr every 30 frames (doesn't disturb USB stream)
            if frame_n % 30 == 0:
                elapsed = time.ticks_diff(time.ticks_ms(), t_last_fps)
                fps = 30_000 / elapsed if elapsed > 0 else 0
                sys.stderr.write(f"FPS: {fps:.1f}  frames: {frame_n}\n")
                t_last_fps = time.ticks_ms()

        except KeyboardInterrupt:
            break
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            time.sleep_ms(100)

    sm.active(0)
    xclk.deinit()


main()
