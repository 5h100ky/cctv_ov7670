# OV7670 18-Pin Breakout → RP2040 Zero Wiring

## OV7670 18-Pin Breakout Board Layout

Standard 18-pin OV7670 modules have two single-row headers (9 pins each side),
or one double-row header (2×9). Pin numbering left-to-right, top-to-bottom:

```
  ┌─────────────────────┐
  │  ●  1  3V3          │
  │  ●  2  GND          │
  │  ●  3  SCL (SIOC)   │
  │  ●  4  SDA (SIOD)   │
  │  ●  5  VSYNC        │
  │  ●  6  HREF         │
  │  ●  7  PCLK         │
  │  ●  8  XCLK         │
  │  ●  9  D7           │
  │  ● 10  D6           │
  │  ● 11  D5           │
  │  ● 12  D4           │
  │  ● 13  D3           │
  │  ● 14  D2           │
  │  ● 15  D1           │
  │  ● 16  D0           │
  │  ● 17  RESET        │
  │  ● 18  PWDN         │
  │                     │
  │     [lens]          │
  └─────────────────────┘
```

> Pin order can vary by manufacturer. Always verify against your module's silkscreen.

---

## Wiring Table (OV7670 → RP2040 Zero)

| # | OV7670 Pin | RP2040 Zero | Notes |
|---|------------|-------------|-------|
| 1 | 3V3 / VCC  | 3V3         | **3.3 V only — never 5 V** |
| 2 | GND        | GND         | Common ground |
| 3 | SCL / SIOC | GP1         | SCCB clock — add 4.7 kΩ pull-up to 3.3 V |
| 4 | SDA / SIOD | GP0         | SCCB data  — add 4.7 kΩ pull-up to 3.3 V |
| 5 | VSYNC      | GP2         | Frame sync pulse |
| 6 | HREF       | GP13        | Line-valid gate |
| 7 | PCLK       | GP12        | Pixel clock input |
| 8 | XCLK       | GP15        | Master clock output (~8 MHz, PWM) |
| 9 | D7         | GP11        | Data bit 7 (MSB) |
|10 | D6         | GP10        | Data bit 6 |
|11 | D5         | GP9         | Data bit 5 |
|12 | D4         | GP8         | Data bit 4 |
|13 | D3         | GP7         | Data bit 3 |
|14 | D2         | GP6         | Data bit 2 |
|15 | D1         | GP5         | Data bit 1 |
|16 | D0         | GP4         | Data bit 0 (LSB) |
|17 | RESET      | 3V3         | Tie HIGH → camera active |
|18 | PWDN       | GND         | Tie LOW  → camera active |

> GP3, GP14 are unused (spare GPIO).

---

## Pull-up Resistors (required)

```
3V3 ──┬──────────────────────────────────
      │                │
     4.7kΩ            4.7kΩ
      │                │
    SIOD (GP0)       SIOC (GP1)
```

Without pull-up resistors the I2C/SCCB bus will not work and
`test_camera.py` will report `PID=0x00 VER=0x00`.

---

## Full Wiring Diagram

```
RP2040 Zero               OV7670 (18-pin)
───────────               ───────────────
3V3  ─────────────────── 3V3    (pin  1)
GND  ─────────────────── GND    (pin  2)
GP1  ─────────────────── SCL    (pin  3)  ──┐
GP0  ─────────────────── SDA    (pin  4)  ──┤── 4.7kΩ each to 3V3
GP2  ─────────────────── VSYNC  (pin  5)
GP13 ─────────────────── HREF   (pin  6)
GP12 ─────────────────── PCLK   (pin  7)
GP15 ─────────────────── XCLK   (pin  8)
GP11 ─────────────────── D7     (pin  9)
GP10 ─────────────────── D6     (pin 10)
GP9  ─────────────────── D5     (pin 11)
GP8  ─────────────────── D4     (pin 12)
GP7  ─────────────────── D3     (pin 13)
GP6  ─────────────────── D2     (pin 14)
GP5  ─────────────────── D1     (pin 15)
GP4  ─────────────────── D0     (pin 16)
3V3  ─────────────────── RESET  (pin 17)   (tie HIGH)
GND  ─────────────────── PWDN   (pin 18)   (tie LOW)
```

---

## RP2040 Zero GPIO Map (used pins)

```
        ┌──────────┐
   3V3 ─┤          ├─ GND
  GP29 ─┤          ├─ GP0  → SIOD
  GP28 ─┤ RP2040   ├─ GP1  → SIOC
  GP27 ─┤  Zero    ├─ GP2  → VSYNC
  GP26 ─┤          ├─ GP3  (free)
  GP15 ─┤          ├─ GP4  → D0
  GP14 ─┤          ├─ GP5  → D1
  GP13 ─┤          ├─ GP6  → D2
  GP12 ─┤          ├─ GP7  → D3
  GP11 ─┤          ├─ GP8  → D4
  GP10 ─┤          ├─ GP9  → D5
        └──────────┘
   ↑         ↑
  HREF      PCLK
  XCLK
```

---

## Common Issues

| Symptom | Likely cause |
|---------|-------------|
| `PID=0x00` on test_camera | Missing 4.7 kΩ pull-ups, or SIOD/SIOC swapped |
| No VSYNC toggling | PWDN not tied to GND, or XCLK not reaching camera |
| Scrambled / shifted image | D0–D7 connected in wrong order |
| Permanent black frame | RESET tied to GND instead of 3.3 V |
| I2C scan finds nothing | VCC not 3.3 V, or GND not shared |
