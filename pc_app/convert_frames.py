#!/usr/bin/env python3
# Standalone frame-to-video converter
# Requires: ffmpeg in PATH, pillow (pip install pillow)
#
# Usage:
#   python convert_frames.py <folder> [fps] [output.mp4]
#
# Examples:
#   python convert_frames.py ~/recordings/2026-06-28
#   python convert_frames.py ~/recordings/2026-06-28 3
#   python convert_frames.py ~/recordings/2026-06-28 5 my_video.mp4

import sys
import os
import glob
import shutil
import subprocess
import tempfile
from PIL import Image

def _detect_fps(folder: str) -> float:
    """Estimate fps from frame timestamps embedded in filenames."""
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.jpg")))
    if len(frames) < 2:
        return 5.0
    # filename format: frame_NNNNNN_YYYYMMDD_HHMMSS_ffffff.jpg
    # Extract datetime from first and last frame
    try:
        from datetime import datetime
        def _ts(name):
            base = os.path.basename(name)
            parts = base.split("_")
            # parts: frame, NNNNNN, YYYYMMDD, HHMMSS, ffffff
            dt_str = f"{parts[2]}_{parts[3]}_{parts[4].split('.')[0]}"
            return datetime.strptime(dt_str, "%Y%m%d_%H%M%S_%f")
        t0 = _ts(frames[0])
        t1 = _ts(frames[-1])
        total_s = (t1 - t0).total_seconds()
        if total_s > 0:
            fps = (len(frames) - 1) / total_s
            return round(fps, 1)
    except Exception:
        pass
    return 5.0


def convert(folder: str, fps: float | None = None, output: str | None = None,
            upscale: bool = True) -> None:
    frames = sorted(glob.glob(os.path.join(folder, "frame_*.jpg")))
    if not frames:
        print(f"ERROR: No frame_*.jpg files found in: {folder}")
        sys.exit(1)

    if fps is None:
        fps = _detect_fps(folder)
        print(f"Auto-detected FPS: {fps}")
    else:
        fps = float(fps)

    if output is None:
        output = os.path.join(folder, "cctv_recording.mp4")

    print(f"Converting {len(frames)} frames @ {fps} fps → {output}")

    # Check ffmpeg
    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found. Install ffmpeg and add to PATH.")
        print("  Mac:  brew install ffmpeg")
        print("  Win:  https://ffmpeg.org/download.html")
        print("  Linux: sudo apt install ffmpeg")
        sys.exit(1)

    # Check input frame size
    sample = Image.open(frames[0])
    w, h = sample.size
    print(f"Frame size: {w}×{h} px")

    with tempfile.TemporaryDirectory() as tmp:
        print("Preparing frames...")
        for i, f in enumerate(frames):
            dst = os.path.join(tmp, f"{i:06d}.jpg")
            if upscale and (w < 320 or h < 240):
                # Upscale small frames (QQVGA→VGA) to improve video codec efficiency
                img = Image.open(f).resize((w * 4, h * 4), Image.NEAREST)
                img.save(dst, "JPEG", quality=90)
            else:
                shutil.copy2(f, dst)

        out_w = w * 4 if (upscale and w < 320) else w
        out_h = h * 4 if (upscale and h < 240) else h
        # Ensure even dimensions (H.264 requirement)
        out_w = out_w + (out_w % 2)
        out_h = out_h + (out_h % 2)

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(tmp, "%06d.jpg"),
            "-vf", f"scale={out_w}:{out_h}",
            "-c:v", "libx264",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",   # web-friendly
            output,
        ]

        print("Running ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("ffmpeg FAILED:")
            print(result.stderr)
            sys.exit(1)

    size_mb = os.path.getsize(output) / 1_048_576
    print(f"\nDone!  {output}  ({size_mb:.1f} MB)")
    print(f"Duration: ~{len(frames)/fps:.1f} s  ({len(frames)} frames @ {fps} fps)")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(0)

    folder = sys.argv[1]
    fps    = float(sys.argv[2]) if len(sys.argv) > 2 else None
    output = sys.argv[3] if len(sys.argv) > 3 else None

    if not os.path.isdir(folder):
        print(f"ERROR: folder not found: {folder}")
        sys.exit(1)

    convert(folder, fps, output)


if __name__ == "__main__":
    main()
