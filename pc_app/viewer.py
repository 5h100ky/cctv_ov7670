#!/usr/bin/env python3
# PC-side CCTV viewer for RP2040 Zero + OV7670
#
# Requirements: pip install pyserial pillow
#
# Usage:
#   python viewer.py              # GUI port selector
#   python viewer.py COM3         # Windows (skip selector)
#   python viewer.py /dev/ttyACM0 # Linux/Mac (skip selector)

import sys
import os
import struct
import threading
import queue
import time
import datetime
import glob
import shutil
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

# --- Protocol constants (must match firmware) ---
MAGIC = b'\xAA\x55\xAA\x55'
BAUD  = 115200   # USB-CDC ignores baud rate, but pyserial requires a value


# ---------------------------------------------------------------------------
# Serial reader thread
# Continuously reads from serial port and puts decoded frames into a queue.
# Sends ("frame", PIL.Image) or ("error", str) or ("disconnected", "") tuples.
# ---------------------------------------------------------------------------
def _serial_reader(port: str, frame_q: queue.Queue, stop_evt: threading.Event) -> None:
    try:
        ser = serial.Serial(port, BAUD, timeout=2)
    except serial.SerialException as e:
        frame_q.put(("error", str(e)))
        return

    buf = bytearray()

    while not stop_evt.is_set():
        try:
            chunk = ser.read(4096)
        except serial.SerialException as e:
            frame_q.put(("error", str(e)))
            break

        if not chunk:
            continue
        buf.extend(chunk)

        while True:
            idx = buf.find(MAGIC)
            if idx == -1:
                buf = buf[-3:]   # keep tail (partial magic guard)
                break
            if idx > 0:
                buf = buf[idx:]  # discard garbage before magic

            if len(buf) < 8:     # magic(4) + w(2) + h(2)
                break

            w = struct.unpack_from('<H', buf, 4)[0]
            h = struct.unpack_from('<H', buf, 6)[0]

            if w == 0 or h == 0 or w > 1280 or h > 1024:
                buf = buf[4:]    # bad header; skip magic and re-search
                continue

            total = 8 + w * h
            if len(buf) < total:
                break            # incomplete frame; wait for more data

            pixel_data = bytes(buf[8:total])
            buf = buf[total:]

            try:
                img = Image.frombytes('L', (w, h), pixel_data)
                if frame_q.full():
                    try:
                        frame_q.get_nowait()   # drop oldest frame to avoid lag
                    except queue.Empty:
                        pass
                frame_q.put(("frame", img))
            except Exception:
                pass

    frame_q.put(("disconnected", ""))
    try:
        ser.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Auto-detect RP2040 serial port
# ---------------------------------------------------------------------------
def _find_rp2040_port() -> str | None:
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        mfg  = (p.manufacturer or "").lower()
        vid  = f"{p.vid:04x}" if p.vid else ""
        if "rp2" in desc or "pico" in desc or "micropython" in mfg or "2e8a" in vid:
            return p.device
    for pat in ["/dev/ttyACM*", "/dev/tty.usbmodem*"]:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


# ---------------------------------------------------------------------------
# Port selection dialog (shown when auto-detect fails)
# ---------------------------------------------------------------------------
def _port_selector_dialog(root: tk.Tk) -> str | None:
    ports = serial.tools.list_ports.comports()
    port_list = [p.device for p in ports]

    win = tk.Toplevel(root)
    win.title("Select Serial Port")
    win.resizable(False, False)
    win.grab_set()

    tk.Label(win, text="Connect RP2040 Zero via USB, then select port:",
             padx=16, pady=8).pack(anchor=tk.W)

    frame = tk.Frame(win)
    frame.pack(fill=tk.BOTH, padx=16, pady=4)

    listbox = tk.Listbox(frame, width=40, height=max(4, min(len(port_list), 10)))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH)
    sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=listbox.yview)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    listbox.config(yscrollcommand=sb.set)

    for p in ports:
        label = f"{p.device}  —  {p.description or ''}"
        listbox.insert(tk.END, label)
    if port_list:
        listbox.select_set(0)

    manual_var = tk.StringVar()
    manual_frame = tk.Frame(win)
    manual_frame.pack(fill=tk.X, padx=16, pady=4)
    tk.Label(manual_frame, text="Or type port:").pack(side=tk.LEFT)
    tk.Entry(manual_frame, textvariable=manual_var, width=20).pack(side=tk.LEFT, padx=4)

    result = [None]

    def _refresh():
        listbox.delete(0, tk.END)
        port_list.clear()
        for p in serial.tools.list_ports.comports():
            port_list.append(p.device)
            listbox.insert(tk.END, f"{p.device}  —  {p.description or ''}")
        if port_list:
            listbox.select_set(0)

    def _ok():
        manual = manual_var.get().strip()
        if manual:
            result[0] = manual
        elif listbox.curselection():
            result[0] = port_list[listbox.curselection()[0]]
        win.destroy()

    def _cancel():
        win.destroy()

    btn = tk.Frame(win)
    btn.pack(pady=8)
    ttk.Button(btn, text="Refresh", command=_refresh).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn, text="Connect", command=_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn, text="Cancel",  command=_cancel).pack(side=tk.LEFT, padx=4)

    win.wait_window()
    return result[0]


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class CCTVApp:
    CANVAS_W = 480
    CANVAS_H = 360

    def __init__(self, root: tk.Tk, port: str):
        self.root = root
        self.port = port

        self._frame_q:     queue.Queue = queue.Queue(maxsize=4)
        self._stop_evt:    threading.Event = threading.Event()
        self._reader:      threading.Thread | None = None

        self._last_frame:  Image.Image | None = None
        self._recording    = False
        self._record_dir   = ""
        self._record_n     = 0
        self._fps_count    = 0
        self._fps_last     = time.time()
        self._fps_display  = 0.0
        self._total_frames = 0

        self._build_ui()
        self._connect(port)
        self.root.after(30, self._poll_frame)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.title("RP2040 Zero CCTV Viewer")
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(self.root, width=self.CANVAS_W, height=self.CANVAS_H, bg="black")
        self.canvas.pack(padx=8, pady=8)
        self._photo = None
        self._canvas_text = self.canvas.create_text(
            self.CANVAS_W // 2, self.CANVAS_H // 2,
            text="Waiting for frames...", fill="gray", font=("", 14)
        )

        # --- Status row ---
        sf = tk.Frame(self.root)
        sf.pack(fill=tk.X, padx=8, pady=2)
        self.lbl_status = tk.Label(sf, text=f"Port: {self.port}", fg="blue", anchor=tk.W)
        self.lbl_status.pack(side=tk.LEFT)
        self.lbl_fps = tk.Label(sf, text="FPS: --", anchor=tk.W)
        self.lbl_fps.pack(side=tk.LEFT, padx=12)
        self.lbl_frames = tk.Label(sf, text="Frames: 0", anchor=tk.W)
        self.lbl_frames.pack(side=tk.LEFT, padx=4)
        self.lbl_rec = tk.Label(sf, text="", fg="red", font=("", 10, "bold"))
        self.lbl_rec.pack(side=tk.RIGHT)

        # --- Button row ---
        bf = tk.Frame(self.root)
        bf.pack(pady=6)
        self.btn_record = ttk.Button(bf, text="⏺  Record", command=self._toggle_record)
        self.btn_record.pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="📷 Snapshot",  command=self._save_snapshot).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="📁 Open folder", command=self._open_folder).pack(side=tk.LEFT, padx=3)
        ttk.Button(bf, text="🔌 Reconnect", command=self._reconnect).pack(side=tk.LEFT, padx=3)

        # --- Folder label ---
        self.lbl_folder = tk.Label(self.root, text="", fg="gray", font=("", 9), anchor=tk.W)
        self.lbl_folder.pack(fill=tk.X, padx=8, pady=(0, 6))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def _connect(self, port: str) -> None:
        self.port = port
        self._stop_evt.clear()
        self._frame_q = queue.Queue(maxsize=4)
        self._reader = threading.Thread(
            target=_serial_reader,
            args=(port, self._frame_q, self._stop_evt),
            daemon=True,
        )
        self._reader.start()
        self.lbl_status.config(text=f"Port: {port}", fg="blue")

    def _disconnect(self) -> None:
        self._stop_evt.set()

    def _reconnect(self) -> None:
        self._disconnect()
        time.sleep(0.3)
        new_port = _port_selector_dialog(self.root)
        if new_port:
            self._connect(new_port)

    # ------------------------------------------------------------------
    # Frame polling (runs in main thread via after())
    # ------------------------------------------------------------------
    def _poll_frame(self) -> None:
        try:
            kind, data = self._frame_q.get_nowait()
        except queue.Empty:
            self.root.after(30, self._poll_frame)
            return

        if kind == "error":
            self.lbl_status.config(text=f"Error: {data}", fg="red")
            self.root.after(500, self._poll_frame)
            return

        if kind == "disconnected":
            self.lbl_status.config(text="Disconnected", fg="orange")
            self.root.after(500, self._poll_frame)
            return

        img: Image.Image = data
        self._last_frame = img
        self._total_frames += 1

        # Remove waiting text on first frame
        if self._canvas_text:
            self.canvas.delete(self._canvas_text)
            self._canvas_text = None

        # Scale up for display (keep NEAREST to avoid blur on small sensor)
        disp = img.resize((self.CANVAS_W, self.CANVAS_H), Image.NEAREST).convert("RGB")
        self._photo = ImageTk.PhotoImage(disp)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)

        # FPS counter (updated every second)
        self._fps_count += 1
        now = time.time()
        elapsed = now - self._fps_last
        if elapsed >= 1.0:
            self._fps_display = self._fps_count / elapsed
            self._fps_count   = 0
            self._fps_last    = now
            self.lbl_fps.config(text=f"FPS: {self._fps_display:.1f}")

        self.lbl_frames.config(text=f"Frames: {self._total_frames}")

        # Save to recording folder if active
        if self._recording and self._record_dir:
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = os.path.join(self._record_dir, f"frame_{self._record_n:06d}_{ts}.jpg")
            img.save(path, "JPEG", quality=85)
            self._record_n += 1
            self.lbl_rec.config(text=f"REC ●  [{self._record_n}]")

        self.root.after(30, self._poll_frame)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _toggle_record(self) -> None:
        if not self._recording:
            folder = filedialog.askdirectory(title="Choose recording folder")
            if not folder:
                return
            self._record_dir = folder
            self._record_n   = 0
            self._recording  = True
            self.btn_record.config(text="⏹  Stop")
            self.lbl_folder.config(text=f"Saving to: {folder}", fg="black")
            self.lbl_rec.config(text="REC ●")
        else:
            self._recording = False
            self.btn_record.config(text="⏺  Record")
            self.lbl_rec.config(text="")
            n = self._record_n
            messagebox.showinfo("Recording stopped", f"Saved {n} frames to:\n{self._record_dir}")
            self._maybe_compile_video()

    def _maybe_compile_video(self) -> None:
        if not shutil.which("ffmpeg"):
            return
        if messagebox.askyesno("Compile video?",
                               "ffmpeg found.\nCompile saved frames into MP4?"):
            self._compile_video(self._record_dir, fps=max(1, round(self._fps_display)))

    def _compile_video(self, folder: str, fps: int = 5) -> None:
        import subprocess, tempfile
        frames = sorted(glob.glob(os.path.join(folder, "frame_*.jpg")))
        if not frames:
            messagebox.showerror("No frames", "No frame_*.jpg files found.")
            return

        out_file = os.path.join(folder, "cctv_recording.mp4")

        with tempfile.TemporaryDirectory() as tmp:
            # Copy files to sequentially named temp copies (cross-filesystem safe)
            for i, f in enumerate(frames):
                shutil.copy2(f, os.path.join(tmp, f"{i:06d}.jpg"))

            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", os.path.join(tmp, "%06d.jpg"),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # ensure even dims
                "-c:v", "libx264", "-crf", "23",
                "-pix_fmt", "yuv420p",
                out_file,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                messagebox.showinfo("Done", f"Video saved:\n{out_file}")
            except subprocess.CalledProcessError as e:
                messagebox.showerror("ffmpeg error", e.stderr.decode(errors="replace"))

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------
    def _save_snapshot(self) -> None:
        if self._last_frame is None:
            messagebox.showwarning("No frame", "No frame received yet.")
            return
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            initialfile=f"snapshot_{ts}.jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("All", "*.*")],
        )
        if path:
            self._last_frame.save(path)
            messagebox.showinfo("Saved", f"Snapshot saved:\n{path}")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _open_folder(self) -> None:
        import subprocess, platform
        folder = self._record_dir or os.path.expanduser("~")
        if not os.path.isdir(folder):
            messagebox.showinfo("No folder", "No recording folder set yet.")
            return
        sys_name = platform.system()
        if sys_name == "Darwin":
            subprocess.Popen(["open", folder])
        elif sys_name == "Windows":
            os.startfile(folder)
        else:
            subprocess.Popen(["xdg-open", folder])

    def _on_close(self) -> None:
        self._disconnect()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    root = tk.Tk()
    root.withdraw()   # hide root while selecting port

    port = sys.argv[1] if len(sys.argv) > 1 else None

    if port is None:
        port = _find_rp2040_port()
        if port:
            print(f"Auto-detected: {port}")
        else:
            print("Auto-detect failed — showing port selector")
            port = _port_selector_dialog(root)
            if not port:
                print("No port selected. Exiting.")
                root.destroy()
                return

    root.deiconify()
    CCTVApp(root, port)
    root.mainloop()


if __name__ == "__main__":
    main()
