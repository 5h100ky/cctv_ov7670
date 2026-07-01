# OV7670 SCCB driver for RP2040 Zero
# SCCB is I2C-compatible for writes; standard machine.I2C works fine

import time
from machine import I2C

OV7670_ADDR = 0x21  # 7-bit write address (0x42 >> 1)

# QQVGA (160x120) YUV422 init register table
# [0]=COM7 reset must come first, then 300ms delay before rest
OV7670_QQVGA_REGS = [
    # --- Phase 1: Full reset ---
    (0x12, 0x80),  # COM7: software reset

    # --- Phase 2: Clock ---
    (0x11, 0x00),  # CLKRC: use ext clock / 2  (8MHz XCLK → 4MHz internal)
    (0xB0, 0x84),  # Undocumented; required by many OV7670 inits

    # --- Phase 3: Output format YUV422 ---
    (0x12, 0x00),  # COM7: YUV output, VGA
    (0x3A, 0x04),  # TSLB: YUYV byte order
    (0x3D, 0xC0),  # COM13: Gamma + UV auto-adjust

    # --- Phase 4: Downscale VGA→QQVGA (160×120) ---
    (0x0C, 0x04),  # COM3: scale enable, DCW enable
    (0x3E, 0x1A),  # COM14: PCLK divider /4, manual scaling on
    (0x70, 0x3A),  # SCALING_XSC
    (0x71, 0x35),  # SCALING_YSC
    (0x72, 0x22),  # SCALING_DCWCTR: 1/4 horizontal, 1/4 vertical
    (0x73, 0xF2),  # SCALING_PCLK_DIV: divide by 4
    (0xA2, 0x02),  # SCALING_PCLK_DELAY

    # --- Phase 5: Active window for QQVGA ---
    (0x17, 0x16),  # HSTART
    (0x18, 0x04),  # HSTOP
    (0x32, 0x80),  # HREF (LSBs)
    (0x19, 0x03),  # VSTART
    (0x1A, 0x7B),  # VSTOP
    (0x03, 0x0A),  # VREF (LSBs)

    # --- Phase 6: Exposure / gain / AWB ---
    (0x13, 0xE7),  # COM8: AGC + AEC + AWB auto
    (0x14, 0x68),  # COM9: max gain 4×
    (0x24, 0x75),  # AEW: upper stable region bound
    (0x25, 0x63),  # AEB: lower stable region bound
    (0x26, 0xA5),  # VPT: fast-mode thresholds
    (0x9F, 0x78),  # HAECC1
    (0xA0, 0x68),  # HAECC2
    (0xA1, 0x03),  # reserved (AEC ceiling MSB)
    (0xA6, 0xDF),  # HAECC6
    (0xA7, 0xDF),  # HAECC7

    # --- Phase 7: Gamma curve ---
    (0x7A, 0x20), (0x7B, 0x10), (0x7C, 0x1E),
    (0x7D, 0x35), (0x7E, 0x5A), (0x7F, 0x69),
    (0x80, 0x76), (0x81, 0x80), (0x82, 0x88),
    (0x83, 0x8F), (0x84, 0x96), (0x85, 0xA3),
    (0x86, 0xAF), (0x87, 0xC4), (0x88, 0xD7),
    (0x89, 0xE8),

    # --- Phase 8: Color matrix (YUV) ---
    (0x4F, 0x80), (0x50, 0x80), (0x51, 0x00),
    (0x52, 0x22), (0x53, 0x5E), (0x54, 0x80),
    (0x58, 0x9E),

    # --- Phase 9: AWB ---
    (0x43, 0x0A), (0x44, 0xF0), (0x45, 0x34),
    (0x46, 0x58), (0x47, 0x28), (0x48, 0x3A),
    (0x59, 0x88), (0x5A, 0x88), (0x5B, 0x44),
    (0x5C, 0x67), (0x5D, 0x49), (0x5E, 0x0E),
    (0x6C, 0x0A), (0x6D, 0x55), (0x6E, 0x11),
    (0x6F, 0x9F), (0x6A, 0x40),
    (0x01, 0x40),  # BLUE gain
    (0x02, 0x60),  # RED gain
    (0x13, 0xE7),  # COM8: turn on AWB update

    # --- Phase 10: Misc ---
    (0x15, 0x00),  # COM10: default (PCLK, HREF polarity)
    (0x3B, 0x0A),  # COM11: 50 Hz banding filter
    (0x41, 0x08),  # COM16: AWB gain enable
    (0x3F, 0x00),  # EDGE: edge enhancement off
    (0x75, 0x05),  # REG75
    (0x76, 0xE1),  # REG76
    (0x4C, 0x00),  # DNSTH: denoise
    (0x77, 0x01),  # REG77
    (0xC9, 0x60),  # SATCTR: saturation
    (0x0D, 0x40),  # COM4
    (0x55, 0x00),  # BRIGHT: brightness 0
    (0x56, 0x40),  # CONTRAST
    (0x1E, 0x00),  # MVFP: no mirror/flip (set 0x20 for vertical flip, 0x10 for mirror)
]


class OV7670:
    def __init__(self, i2c: I2C):
        self._i2c = i2c

    def _write_reg(self, reg: int, val: int) -> None:
        self._i2c.writeto_mem(OV7670_ADDR, reg, bytes([val]))

    def _read_reg(self, reg: int) -> int:
        # SCCB requires a separate write (reg addr) + read transaction;
        # this module NACKs a combined repeated-start readfrom_mem().
        self._i2c.writeto(OV7670_ADDR, bytes([reg]))
        return self._i2c.readfrom(OV7670_ADDR, 1)[0]

    def init(self) -> None:
        # Send reset first, then delay, then the rest
        self._write_reg(0x12, 0x80)
        time.sleep_ms(300)
        for reg, val in OV7670_QQVGA_REGS[1:]:  # skip reset (already done)
            self._write_reg(reg, val)
            time.sleep_ms(1)
        time.sleep_ms(100)

    def read_id(self) -> tuple:
        """Return (PID, VER) - should be (0x76, 0x73) for OV7670."""
        return self._read_reg(0x0A), self._read_reg(0x0B)

    def set_flip(self, vflip: bool = False, hmirror: bool = False) -> None:
        val = 0x00
        if vflip:
            val |= 0x10
        if hmirror:
            val |= 0x20
        self._write_reg(0x1E, val)
