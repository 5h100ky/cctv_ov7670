# RP2040 Zero + OV7670 CCTV

A minimal CCTV that streams QQVGA (160×120) grayscale video from an OV7670 camera module over USB-CDC to a PC viewer, built with MicroPython on the Waveshare RP2040 Zero.

## Flashing (easiest way)

Download `cctv_ov7670.uf2` from the [latest release](../../releases/latest) or the [Actions artifacts](../../actions).

1. Hold the **BOOT button** on the RP2040 Zero while plugging in USB
2. A `RPI-RP2` drive appears — drag `cctv_ov7670.uf2` onto it
3. The board reboots and starts streaming automatically

## Repository layout

```
cctv_ov7670/
├── firmware/
│   ├── main.py           RP2040 main firmware (MicroPython)
│   ├── ov7670.py         OV7670 SCCB/I2C driver + register table
│   ├── test_camera.py    Wiring diagnostic — run this first
│   └── boot.py           Optional auto-start on power-up
├── pc_app/
│   ├── viewer.py         PC viewer (live display, snapshot, recording)
│   ├── convert_frames.py Convert recorded JPEG frames to MP4
│   └── requirements.txt
├── build_scripts/
│   └── create_uf2.py     Builds the combined UF2 locally
├── .github/workflows/
│   └── build.yml         GitHub Actions — builds UF2 on every push
└── WIRING.md             Pin wiring reference
```

## Wiring

| OV7670 | RP2040 Zero | Notes |
|--------|-------------|-------|
| VCC | 3V3 | 3.3 V only — never 5 V |
| GND | GND | |
| SIOD | GP0 | SCCB data (I2C SDA) |
| SIOC | GP1 | SCCB clock (I2C SCL) |
| VSYNC | GP2 | Frame sync |
| D0–D7 | GP4–GP11 | 8-bit parallel data (must be consecutive) |
| PCLK | GP12 | Pixel clock |
| HREF | GP13 | Line-valid signal |
| XCLK | GP15 | ~8 MHz clock output (PWM-generated) |
| RESET | 3V3 | Tie HIGH to disable reset |
| PWDN | GND | Tie LOW to enable camera |

> Add **4.7 kΩ pull-up resistors** from SIOD and SIOC to 3.3 V.

See [WIRING.md](WIRING.md) for the full ASCII diagram.

## Manual firmware upload (alternative to UF2)

```bash
# Create a virtual environment and install tools
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install mpremote pyserial pillow

# Step 1 — verify wiring before uploading the main firmware
mpremote run firmware/test_camera.py

# Step 2 — upload and run
mpremote cp firmware/ov7670.py :ov7670.py
mpremote cp firmware/main.py   :main.py
mpremote run firmware/main.py
```

Or use **Thonny IDE** (drag-and-drop upload via the file browser).

## PC viewer

```bash
pip install pyserial pillow
python pc_app/viewer.py            # auto-detect port
python pc_app/viewer.py COM3       # Windows
python pc_app/viewer.py /dev/ttyACM0  # Linux / Mac
```

**Features:**
- Live video display (4× upscaled)
- Snapshot (JPG / PNG)
- Recording → saves individual JPEG frames
- Reconnect button if the serial connection drops
- Compiles recorded frames to MP4 via ffmpeg (if installed)

Convert a recording folder to MP4 from the command line:

```bash
python pc_app/convert_frames.py ~/recordings/my_session
python pc_app/convert_frames.py ~/recordings/my_session 3   # set fps
```

## How it works

```
OV7670 ──PCLK──▶ RP2040 PIO ──FIFO──▶ Python loop ──USB CDC──▶ PC viewer
                  (parallel            (extract Y           (parse frames,
                   capture)             channel)             display, record)
```

### Frame protocol (RP2040 → PC)

| Field | Size | Value |
|-------|------|-------|
| Magic | 4 B | `0xAA 0x55 0xAA 0x55` |
| Width | 2 B LE | 160 |
| Height | 2 B LE | 120 |
| Pixels | 160 × 120 B | Grayscale (Y channel from YUV422) |

## Building the UF2 locally

```bash
source .venv/bin/activate
pip install littlefs-python
python build_scripts/create_uf2.py
# → dist/cctv_ov7670.uf2
```

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `PID=0x00 VER=0x00` | SIOD/SIOC wiring; 4.7 kΩ pull-ups to 3.3 V required |
| Black screen | GP15 XCLK output (~8 MHz); PWDN tied to GND; RESET tied to 3.3 V |
| Horizontal stripes / noise | D0–D7 pin order; common GND between board and camera |
| Port not detected | MicroPython USB-CDC enabled; USB driver installed |
| Very low FPS | Expected — Python loop throughput; 1–5 fps is sufficient for CCTV |

## Specs

| Item | Value |
|------|-------|
| Resolution | QQVGA 160 × 120, grayscale |
| Expected FPS | 1–5 fps (MicroPython loop-bound) |
| USB transfer | USB-CDC (USB Full Speed, 12 Mbps physical) |
| MicroPython | Latest stable (auto-downloaded during UF2 build) |
| Board | Waveshare RP2040 Zero (any RP2040 with 2 MB flash works) |
