# Setup Guide

Step-by-step instructions for flashing the RP2040 Zero and running the PC viewer,
for both **macOS** and **Windows**.

---

## Step 1 — Install Python

### macOS

Check if Python 3 is already installed:
```bash
python3 --version
```

If not installed, install via Homebrew (recommended):
```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://brew.sh/install.sh)"

# Install Python
brew install python
```

Or download the installer from [python.org](https://www.python.org/downloads/).

> **macOS — tkinter note**
> Homebrew Python does not include Tcl/Tk (required by the viewer GUI) by default.
> Install it separately and match your Python version:
> ```bash
> # Check your Python version first
> python3 --version          # e.g. Python 3.14.x
>
> # Install the matching Tk package
> brew install python-tk@3.14   # replace 3.14 with your version
> ```
> After installing, **delete and recreate your virtual environment** so it picks up tkinter:
> ```bash
> deactivate
> rm -rf .venv
> python3 -m venv .venv
> source .venv/bin/activate
> pip install pyserial pillow mpremote littlefs-python
> ```

---

### Windows

Download and run the installer from [python.org](https://www.python.org/downloads/).

> **Important:** On the first installer screen, check **"Add Python to PATH"** before clicking Install Now.

Verify in Command Prompt (`Win + R` → `cmd`):
```cmd
python --version
```

---

## Step 2 — Clone or Download the Repository

### macOS
```bash
git clone https://github.com/5h100ky/cctv_ov7670.git
cd cctv_ov7670
```

### Windows
```cmd
git clone https://github.com/5h100ky/cctv_ov7670.git
cd cctv_ov7670
```

Or download the ZIP from GitHub → **Code → Download ZIP**, then extract it.

---

## Step 3 — Create a Virtual Environment

### macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt will show `(.venv)` when active.
To deactivate later: `deactivate`

---

### Windows (Command Prompt)
```cmd
python -m venv .venv
.venv\Scripts\activate
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> If PowerShell blocks the activation script, run this once as Administrator:
> ```powershell
> Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Your prompt will show `(.venv)` when active.
To deactivate later: `deactivate`

---

## Step 4 — Install Required Packages

Run this after activating the virtual environment (same for both platforms):

```bash
pip install mpremote pyserial pillow littlefs-python
```

Verify:
```bash
mpremote --version
python -c "import serial, PIL; print('OK')"
```

---

## Step 5 — Flash MicroPython to RP2040 Zero

> **Recommended path: Steps 5 + 8 (mpremote upload).**
> The combined UF2 method (below) works on some systems but may leave an empty filesystem on others.
> Flashing plain MicroPython and then uploading via mpremote is always reliable.

### 5a — Flash plain MicroPython (recommended)

Download `micropython_rp2040.uf2` from the [dist/](dist/) folder in this repo,
or grab the latest stable release from [micropython.org/download/RPI_PICO](https://micropython.org/download/RPI_PICO/).

| Step | Action |
|------|--------|
| 1 | Hold the **BOOT button** on the RP2040 Zero |
| 2 | While holding BOOT, plug the USB cable into the PC |
| 3 | Release BOOT — a drive named **`RPI-RP2`** appears |
| 4 | Drag and drop `micropython_rp2040.uf2` onto that drive |
| 5 | The drive disappears and the board reboots into MicroPython |

Then continue to **Step 6** (verify wiring) and **Step 8** (upload firmware files).

### 5b — Flash the all-in-one UF2 (alternative)

This bundles MicroPython + firmware files into a single drag-and-drop image.

Go to [Releases](https://github.com/5h100ky/cctv_ov7670/releases/latest) and download `cctv_ov7670.uf2`, then flash it the same way as above.

> If the viewer shows "Waiting for frames…" after flashing this UF2, the embedded filesystem was not recognised — use the **Step 8** manual upload to fix it.

### Build the UF2 yourself (optional)

```bash
# Activate venv first, then:
python build_scripts/create_uf2.py
# Output: dist/cctv_ov7670.uf2
```

---

## Step 6 — Verify Camera Wiring

Before running the viewer, confirm the OV7670 is wired correctly.

### Find the serial port

#### macOS
```bash
ls /dev/tty.usbmodem*
# or
ls /dev/ttyACM*
```

#### Windows
Open **Device Manager** → **Ports (COM & LPT)** → look for **USB Serial Device** or **Raspberry Pi Pico** → note the COM number (e.g. `COM3`).

### Run the diagnostic script

#### macOS
```bash
mpremote run firmware/test_camera.py
```

#### Windows
```cmd
mpremote run firmware\test_camera.py
```

**Expected output (all OK):**
```
========================================
OV7670 Camera Diagnostic
========================================

[1] Starting XCLK on GP15...
    XCLK: OK (8000000 Hz)

[2] Scanning I2C bus (GP0=SDA, GP1=SCL)...
    Found: ['0x21']
    OV7670 found at 0x21  OK

[3] Reading OV7670 chip ID...
    PID=0x76  VER=0x73
    Chip ID matches OV7670  OK

[4] Checking VSYNC on GP2 (3 second window)...
    VSYNC is toggling (12 transitions)  OK

[5] Register write/read test (COM2 = 0x09)...
    Write/read OK

========================================
Test PASSED — proceed to flash main.py
========================================
```

**If it fails** → check [WIRING.md](WIRING.md) for the pin diagram.

---

## Step 7 — Run the PC Viewer

The viewer works on **macOS and Windows** (Python 3.9+, tkinter, pyserial, Pillow — all cross-platform).
It streams **live colour video** from the OV7670 at ~1–3 FPS over USB.

> ⚠️ **Close Arduino IDE, Thonny, or any other serial monitor before starting the viewer.**
> Only one program can hold the serial port at a time. If you see `[Errno 16] Resource busy`,
> another application is still using the port.

### macOS

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Launch the viewer (auto-detects the RP2040 port)
python pc_app/viewer.py

# If auto-detect fails, specify the port manually:
python pc_app/viewer.py /dev/cu.usbmodem1201
```

To find your port if needed:
```bash
ls /dev/cu.usbmodem*
```

### Windows

```cmd
:: 1. Activate virtual environment
.venv\Scripts\activate

:: 2. Launch the viewer (auto-detects the RP2040 COM port)
python pc_app\viewer.py

:: If auto-detect fails, specify the port manually:
python pc_app\viewer.py COM3
```

To find your COM port: open **Device Manager** → **Ports (COM & LPT)** → look for **USB Serial Device** or **Raspberry Pi Pico**.

### What to expect

- The window title is **RP2040 Zero CCTV Viewer**
- **FPS ~1–3** is normal — this is a MicroPython firmware limit over USB CDC
- **Frames counter** should increase steadily; if it stays at 0, check the port and wiring
- The live image is colour (YCbCr → RGB)

---

## Step 8 — Upload Firmware via mpremote (recommended)

This is the most reliable method. After flashing plain MicroPython (Step 5a),
upload the three firmware files directly:

#### macOS
```bash
source .venv/bin/activate

# Upload firmware files
mpremote cp firmware/ov7670.py :ov7670.py
mpremote cp firmware/main.py   :main.py

# Optional: auto-start on every power-up
mpremote cp firmware/boot.py :boot.py
```

#### Windows
```cmd
.venv\Scripts\activate

mpremote cp firmware\ov7670.py :ov7670.py
mpremote cp firmware\main.py   :main.py

:: Optional: auto-start on every power-up
mpremote cp firmware\boot.py :boot.py
```

Verify the files landed on the board:
```bash
mpremote fs ls
```
Expected output:
```
        7073 main.py
        4220 ov7670.py
```

After uploading, **unplug and replug the USB cable** (or run `mpremote reset`) to start streaming.
Then launch the viewer as described in Step 7.

---

## Viewer Features

| Button | Action |
|--------|--------|
| ⏺ Record | Choose a folder, then saves each frame as colour JPEG |
| ⏹ Stop | Stops recording; offers MP4 export if ffmpeg is installed |
| 📷 Snapshot | Save the current frame as JPG or PNG (colour) |
| 📁 Open folder | Open the recording folder in Finder / Explorer |
| 🔌 Reconnect | Reopen the port selector if the connection drops |

### Convert recorded frames to MP4

Requires [ffmpeg](https://ffmpeg.org/download.html) installed and on PATH.

#### macOS
```bash
# Install ffmpeg
brew install ffmpeg

# Convert
python pc_app/convert_frames.py ~/path/to/recording/folder
python pc_app/convert_frames.py ~/path/to/recording/folder 5   # set fps
```

#### Windows
```cmd
# Download ffmpeg from https://ffmpeg.org/download.html
# Extract and add the bin\ folder to your PATH, then:

python pc_app\convert_frames.py C:\path\to\recording\folder
python pc_app\convert_frames.py C:\path\to\recording\folder 5
```

---

## Troubleshooting

### Common (all platforms)

| Problem | Fix |
|---------|-----|
| `[Errno 16] Resource busy` / `Access is denied` | Another app (Arduino IDE, Thonny, serial monitor) is holding the port — close it first |
| Viewer connects but **Frames stays at 0** | Board filesystem is empty — run Step 8 (mpremote upload) |
| Viewer connects, frames count increases, but **screen is black** | HREF or PCLK wiring loose — check GP12/GP13 solder joints |
| `ValueError: freq out of range` in firmware | PIO freq exceeded system clock — update to latest `main.py` (already fixed) |
| `[Errno 5] EIO` when reading camera ID | Some OV7670 clones need 2-phase SCCB reads — update to latest `ov7670.py` (already fixed) |
| Horizontal banding / alternating light-dark rows | PIO ISR not cleared at line end — update to latest `main.py` (already fixed) |
| Image is greyscale instead of colour | Running an old firmware — re-upload `main.py` from this repo |

### macOS

| Problem | Fix |
|---------|-----|
| `mpremote: command not found` | Virtual environment not active — run `source .venv/bin/activate` |
| `ModuleNotFoundError: No module named '_tkinter'` | Run `brew install python-tk@3.14` (match your Python version), then recreate the venv |
| No `/dev/cu.usbmodem*` device | Try a different USB cable (some are charge-only) |
| `Permission denied` on serial port | `sudo chmod 666 /dev/cu.usbmodem*` |

### Windows

| Problem | Fix |
|---------|-----|
| `python` not found | Re-install Python with **"Add to PATH"** checked |
| `mpremote` not found | Virtual environment not active — run `.venv\Scripts\activate` |
| No COM port in Device Manager | Install the [Pico Windows driver](https://github.com/raspberrypi/pico-setup-windows) or use a different USB cable |
| `Access is denied` on COM port | Close Arduino IDE, Thonny, or any serial monitor using the port |
| PowerShell activation blocked | Run `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
