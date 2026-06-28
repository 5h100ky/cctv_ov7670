#!/usr/bin/env python3
"""
Build script: creates a single UF2 file that contains
  1. MicroPython for RP2040 (downloaded from micropython.org)
  2. Our firmware files embedded as a LittleFS filesystem image

Flash layout (RP2040, 2MB):
  0x10000000 - 0x100A0000  MicroPython interpreter (~640 KB)
  0x100A0000 - 0x10200000  LittleFS filesystem   (1408 KB = 352 × 4096-byte blocks)

Usage:
  pip install littlefs-python requests
  python build_scripts/create_uf2.py
Output: dist/cctv_ov7670.uf2
"""

import json
import os
import struct
import urllib.request
import shutil
import sys

# ---------- constants for RP2040 / MicroPython flash layout ----------
FLASH_BASE          = 0x10000000
FS_OFFSET           = 0x000A0000   # MicroPython default for 2MB flash
FS_BASE             = FLASH_BASE + FS_OFFSET   # 0x100A0000
FS_BLOCK_SIZE       = 4096
FS_BLOCK_COUNT      = 352          # 1408 KB / 4 KB per block
RP2040_FAMILY_ID    = 0xE48BFF56
UF2_MAGIC_START0    = 0x0A324655   # "UF2\n"
UF2_MAGIC_START1    = 0x9E5D5157
UF2_MAGIC_END       = 0x0AB16F30
UF2_FLAG_FAMILYID   = 0x00002000
UF2_PAYLOAD_SIZE    = 256

# Files to embed in the LittleFS image (source_path, dest_name_on_device)
FIRMWARE_FILES = [
    ("firmware/ov7670.py", "ov7670.py"),
    ("firmware/main.py",   "main.py"),
]

MICROPYTHON_RELEASES_API = "https://api.github.com/repos/micropython/micropython/releases/latest"
DIST_DIR                 = "dist"


# ---------- UF2 helpers ----------

def _bin_to_uf2_blocks(data: bytes, base_addr: int) -> list[bytes]:
    """Convert a binary blob to a list of 512-byte UF2 blocks (sparse: skips 0xFF pages)."""
    payload = UF2_PAYLOAD_SIZE
    all_ff  = b'\xFF' * payload

    # Collect non-erased pages
    pages = []
    for i in range(0, len(data), payload):
        chunk = data[i : i + payload].ljust(payload, b'\xFF')
        if chunk != all_ff:
            pages.append((i, chunk))

    total = len(pages)
    blocks = []
    for seq, (offset, chunk) in enumerate(pages):
        header = struct.pack(
            '<IIIIIIII',
            UF2_MAGIC_START0,
            UF2_MAGIC_START1,
            UF2_FLAG_FAMILYID,
            base_addr + offset,
            payload,
            seq,
            total,
            RP2040_FAMILY_ID,
        )
        padding = b'\x00' * (476 - payload)
        footer  = struct.pack('<I', UF2_MAGIC_END)
        block   = header + chunk + padding + footer
        assert len(block) == 512
        blocks.append(block)

    return blocks


def _resequence_uf2(data: bytes, block_offset: int, total: int) -> bytes:
    """Re-number the block_no and num_blocks fields in every UF2 block."""
    out = bytearray(data)
    for i, pos in enumerate(range(0, len(data), 512)):
        struct.pack_into('<I', out, pos + 20, block_offset + i)  # blockNo
        struct.pack_into('<I', out, pos + 24, total)             # numBlocks
    return bytes(out)


# ---------- LittleFS image ----------

def _build_littlefs_image() -> bytes:
    try:
        import littlefs
    except ImportError:
        sys.exit("ERROR: 'littlefs-python' not installed.\n  pip install littlefs-python")

    fs = littlefs.LittleFS(
        block_size  = FS_BLOCK_SIZE,
        block_count = FS_BLOCK_COUNT,
        prog_size   = 256,
        read_size   = 256,
    )

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for src, dst in FIRMWARE_FILES:
        src_path = os.path.join(project_root, src)
        if not os.path.exists(src_path):
            sys.exit(f"ERROR: firmware file not found: {src_path}")
        with open(src_path, 'rb') as f:
            content = f.read()
        with fs.open(dst, 'wb') as f:
            f.write(content)
        print(f"  + {dst}  ({len(content):,} bytes)")

    return bytes(fs.context)


# ---------- main ----------

def main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist_dir     = os.path.join(project_root, DIST_DIR)
    os.makedirs(dist_dir, exist_ok=True)

    # 1. Download MicroPython UF2 (latest release from GitHub)
    mp_uf2_path = os.path.join(dist_dir, "micropython_rp2040.uf2")
    if os.path.exists(mp_uf2_path):
        print(f"[1] Using cached MicroPython UF2: {mp_uf2_path}")
    else:
        print("[1] Fetching latest MicroPython release info...")
        req = urllib.request.Request(
            MICROPYTHON_RELEASES_API,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "cctv_ov7670_builder"},
        )
        with urllib.request.urlopen(req) as r:
            release = json.loads(r.read())

        # Find asset: rp2-pico*.uf2 (not picow, not pico2)
        uf2_url = None
        for asset in release["assets"]:
            name = asset["name"].lower()
            if name.startswith("rp2-pico") and name.endswith(".uf2") \
               and "picow" not in name and "pico2" not in name:
                uf2_url  = asset["browser_download_url"]
                uf2_name = asset["name"]
                break

        if uf2_url is None:
            sys.exit("ERROR: Could not find rp2-pico UF2 in latest MicroPython release.\n"
                     f"  Release: {release.get('tag_name')} — assets: "
                     f"{[a['name'] for a in release['assets']]}")

        print(f"    Downloading: {uf2_name}")
        with urllib.request.urlopen(uf2_url) as r, open(mp_uf2_path, 'wb') as f:
            shutil.copyfileobj(r, f)
        print(f"    Saved {os.path.getsize(mp_uf2_path):,} bytes")

    mp_uf2_data = open(mp_uf2_path, 'rb').read()
    mp_blocks   = len(mp_uf2_data) // 512
    print(f"    MicroPython: {mp_blocks} UF2 blocks")

    # 2. Build LittleFS image
    print("\n[2] Building LittleFS filesystem image...")
    fs_image  = _build_littlefs_image()
    fs_blocks = _bin_to_uf2_blocks(fs_image, FS_BASE)
    print(f"    Filesystem: {len(fs_blocks)} UF2 blocks (non-erased pages only)")

    # 3. Merge: re-sequence all block numbers across both UF2 parts
    total_blocks = mp_blocks + len(fs_blocks)
    print(f"\n[3] Merging ({mp_blocks} + {len(fs_blocks)} = {total_blocks} blocks)...")

    mp_reseq = _resequence_uf2(mp_uf2_data, 0, total_blocks)
    fs_reseq  = _resequence_uf2(b''.join(fs_blocks), mp_blocks, total_blocks)

    combined = mp_reseq + fs_reseq

    # 4. Write output
    out_path = os.path.join(dist_dir, "cctv_ov7670.uf2")
    with open(out_path, 'wb') as f:
        f.write(combined)

    size_kb = len(combined) / 1024
    print(f"\n[4] Done!  {out_path}  ({size_kb:.0f} KB)")
    print("    Flash to RP2040 Zero:")
    print("      1. Hold BOOTSEL button, plug USB → RPI-RP2 drive appears")
    print("      2. Drag cctv_ov7670.uf2 onto the drive")
    print("      3. Board reboots and CCTV starts automatically")


if __name__ == "__main__":
    main()
