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

import machine
import time
import sys
import struct
import rp2
from machine import Pin, I2C, PWM
from ov7670 import OV7670

# --- Pin constants ---
SIOD_PIN  = 0
SIOC_PIN  = 1
VSYNC_PIN = 2
D0_PIN    = 4   # D0–D7 are GP4–GP11
PCLK_PIN  = 12
HREF_PIN  = 13
XCLK_PIN  = 15

# --- Frame geometry ---
WIDTH  = 160
HEIGHT = 120
BYTES_PER_PIXEL = 2
FRAME_BYTES = WIDTH * HEIGHT * BYTES_PER_PIXEL  # 38,400 raw YUV bytes

# --- USB-CDC frame protocol ---
# <MAGIC 4B> <width 2B LE> <height 2B LE> <YUYV pixels W*H*2 bytes>
MAGIC = b'\xAA\x55\xAA\x55'

# --- DMA constants (RP2040 datasheet) ---
_PIO0_RXF0     = 0x50200020  # PIO0 SM0 RX FIFO address
_TREQ_PIO0_RX0 = 4           # DREQ number for PIO0 SM0 RX
_DMA_NWORDS    = FRAME_BYTES // 4  # 9,600 words (4 bytes each)

# --- Pre-allocated buffers (module-level keeps them stable during DMA) ---
_raw_buf    = bytearray(FRAME_BYTES)  # full YUV422 frame from DMA
_header_buf = bytearray(8)            # fixed frame header

# Write fixed header once
_header_buf[0:4] = b'\xAA\x55\xAA\x55'
struct.pack_into('<HH', _header_buf, 4, WIDTH, HEIGHT)

_VSYNC_TIMEOUT = 8_000_000   # spin iterations (~2-3 s at 125 MHz)


# ---------------------------------------------------------------------------
# PIO program
# ---------------------------------------------------------------------------
# SHIFT_RIGHT: bytes arrive in natural memory order after DMA write
#   ISR fills from MSB end → little-endian DMA write gives [B0,B1,B2,B3]
# push_thresh=32: accumulate 4 bytes before pushing (4× fewer FIFO words,
#   4× fewer DMA transactions vs push_thresh=8)
# ---------------------------------------------------------------------------
@rp2.asm_pio(
    in_shiftdir=rp2.PIO.SHIFT_RIGHT,
    autopush=True,
    push_thresh=32,
)
def _ov7670_pio():
    wrap_target()
    wait(1, pin, 9)      # wait HREF high  (pin offset 9 = GP13)
    label("pixel")
    wait(0, pin, 8)      # wait PCLK low   (pin offset 8 = GP12)
    wait(1, pin, 8)      # wait PCLK rising
    in_(pins, 8)         # sample D0-D7; auto-push fires after 32 bits
    jmp(pin, "pixel")    # jmp_pin=HREF: if still high, next pixel
    mov(isr, null)       # clear any partial ISR bytes at line end
    wrap()               # HREF low → back to wait for next line


def _make_sm():
    return rp2.StateMachine(
        0,
        _ov7670_pio,
        freq=machine.freq(),    # PIO freq must not exceed sys clock
        in_base=Pin(D0_PIN),    # D0-D7 input base
        jmp_pin=Pin(HREF_PIN),  # HREF controls jmp(pin,...)
    )


# ---------------------------------------------------------------------------
# XCLK generation (~8 MHz square wave via PWM)
# ---------------------------------------------------------------------------
def _start_xclk():
    xclk = PWM(Pin(XCLK_PIN))
    xclk.freq(8_000_000)
    xclk.duty_u16(32768)
    return xclk


# ---------------------------------------------------------------------------
# Capture one full grayscale frame using DMA
# ---------------------------------------------------------------------------
def capture_frame(sm, vsync, dma, dma_ctrl):
    # Drain stale FIFO content from previous frame
    while sm.rx_fifo():
        sm.get()

    # --- Sync to VSYNC rising edge ---
    t = _VSYNC_TIMEOUT
    while vsync.value() == 1 and t:
        t -= 1
    if not t:
        return None
    t = _VSYNC_TIMEOUT
    while vsync.value() == 0 and t:
        t -= 1
    if not t:
        return None
    # VSYNC high → wait for it to fall (active lines start)
    while vsync.value() == 1:
        pass

    # --- DMA transfer: PIO RX FIFO → _raw_buf ---
    # DMA is paced by PIO DREQ so it flows at camera PCLK rate.
    dma.config(
        read=_PIO0_RXF0,
        write=_raw_buf,
        count=_DMA_NWORDS,
        ctrl=dma_ctrl,
        trigger=True,
    )
    t_start = time.ticks_ms()
    while dma.active():
        if time.ticks_diff(time.ticks_ms(), t_start) > 2000:
            return None  # safety timeout (camera stall)

    return _raw_buf  # full YUV422 (YUYV): even bytes=Y, odd bytes=Cb/Cr


# ---------------------------------------------------------------------------
# Send a YUYV color frame over USB-CDC
# ---------------------------------------------------------------------------
def send_frame(data):
    sys.stdout.buffer.write(_header_buf)
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
    sys.stderr.write(f"OV7670 PID=0x{pid:02X} VER=0x{ver:02X}\n")
    cam.init()
    time.sleep_ms(300)

    # 3. Set up PIO state machine
    vsync = Pin(VSYNC_PIN, Pin.IN)
    sm = _make_sm()
    sm.active(1)

    # 4. Set up DMA (pre-compute ctrl word once)
    dma = rp2.DMA()
    dma_ctrl = dma.pack_ctrl(
        size=2,           # 32-bit word transfers
        inc_read=False,   # FIFO address stays fixed
        inc_write=True,   # advance through _raw_buf
        treq_sel=_TREQ_PIO0_RX0,
    )

    # 5. Main loop: capture and stream frames
    sys.stderr.write("Streaming started (DMA mode).\n")
    frame_n = 0
    t_last  = time.ticks_ms()

    while True:
        try:
            frame = capture_frame(sm, vsync, dma, dma_ctrl)
            if frame is None:
                sys.stderr.write("Frame timeout - check camera wiring (VSYNC/HREF/PCLK)\n")
                time.sleep_ms(200)
                continue

            send_frame(frame)
            frame_n += 1

            if frame_n % 30 == 0:
                elapsed = time.ticks_diff(time.ticks_ms(), t_last)
                fps = 30_000 / elapsed if elapsed > 0 else 0
                sys.stderr.write(f"FPS: {fps:.1f}  frames: {frame_n}\n")
                t_last = time.ticks_ms()

        except KeyboardInterrupt:
            break
        except Exception as e:
            sys.stderr.write(f"Error: {e}\n")
            time.sleep_ms(100)

    sm.active(0)
    dma.close()
    xclk.deinit()


main()
