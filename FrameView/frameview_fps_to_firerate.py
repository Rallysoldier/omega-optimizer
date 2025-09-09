# frameview_fps_to_firerate.py
# Reads FPS from NVIDIA FrameView per-frame logs and writes a smoothed fire-rate
# to C:\Users\Public\hd2_fire_rate.txt for Cheat Engine to pick up.

import csv
import glob
import os
import time
import subprocess

# ---------- CONFIG ----------
FRAMEVIEW_EXE = r"C:\Program Files\NVIDIA Corporation\FrameView\FrameView_x64.exe"
BENCHMARK_DIR = r"C:\Users\Gaming\Documents\FrameView"
GAME_EXE_NAME = "helldivers2.exe"  # used in the FrameView log filename
OUTPUT_TXT = r"C:\Users\Public\hd2_fire_rate.txt"

# Control mapping (same defaults as before)
TARGET_FPS = 100.0
BASE_RATE = 2000
MIN_RATE = 400
MAX_RATE = 4000
EMA_ALPHA = 0.2           # smoothing factor for FPS
POLL_INTERVAL = 0.20      # seconds; aligns with CE poll cadence
RESCAN_EVERY = 3.0        # if no new data arrives for this many seconds, look for a newer log
# ---------------------------


def ensure_frameview_running():
    """Best-effort: launch FrameView if not already running."""
    try:
        subprocess.Popen(
            [FRAMEVIEW_EXE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
    except FileNotFoundError:
        print("[WARN] FrameView executable not found. Check FRAMEVIEW_EXE path.")


def latest_frameview_log(benchmark_dir: str, app_exe_name: str) -> str | None:
    """Find the newest per-frame log CSV for the target app."""
    pattern = os.path.join(benchmark_dir, f"FrameView_{app_exe_name}_*_Log.csv")
    candidates = glob.glob(pattern)
    if not candidates:
        return None
    # choose most recently modified
    return max(candidates, key=os.path.getmtime)


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def fps_to_rate(fps: float) -> int:
    """Scale smoothed FPS relative to TARGET_FPS into [MIN_RATE, MAX_RATE]."""
    scaled = BASE_RATE * (fps / TARGET_FPS)
    return int(round(clamp(scaled, MIN_RATE, MAX_RATE)))


def write_rate(path: str, rate: int):
    # Write atomically-ish: write to temp then replace to avoid partial reads
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(rate))
    try:
        os.replace(tmp, path)
    except Exception:
        # Fallback in case replace not permitted
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(rate))


def stream_fps_from_log(log_path: str):
    """
    Tail the per-frame CSV, yielding FPS values as new rows arrive.
    FPS is computed as 1000.0 / MsBetweenPresents for non-dropped frames.
    """
    # We’ll open once and keep the file handle; re-open if file rotates.
    last_pos = 0
    header = None
    ms_idx = None
    dropped_idx = None

    while True:
        if not os.path.exists(log_path):
            # Log disappeared (rotation?). Give caller a chance to pick a new one.
            time.sleep(POLL_INTERVAL)
            yield None
            continue

        with open(log_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            # If file shrunk, reset
            size = os.path.getsize(log_path)
            if last_pos > size:
                last_pos = 0

            f.seek(last_pos, os.SEEK_SET)
            reader = csv.reader(f)

            # Initialize header if needed
            if header is None:
                try:
                    header = next(reader)
                except StopIteration:
                    # no data yet
                    last_pos = f.tell()
                    yield None
                    continue

                # locate relevant columns (case-sensitive names typical of FrameView)
                try:
                    ms_idx = header.index("MsBetweenPresents")
                except ValueError:
                    ms_idx = None
                try:
                    dropped_idx = header.index("Dropped")
                except ValueError:
                    dropped_idx = None

                # If header line was just read, continue to next lines in the same pass.

            had_new_data = False
            for row in reader:
                had_new_data = True
                # Ignore dropped frames if column exists and is "1"
                if dropped_idx is not None and len(row) > dropped_idx and row[dropped_idx].strip() == "1":
                    continue

                ms = None
                if ms_idx is not None and len(row) > ms_idx:
                    raw = row[ms_idx].strip()
                    try:
                        ms = float(raw)
                    except ValueError:
                        ms = None

                if ms and ms > 0.0:
                    fps = 1000.0 / ms
                    yield fps

            last_pos = f.tell()

            if not had_new_data:
                # No new lines; let caller know
                yield None

        time.sleep(POLL_INTERVAL)


def main():
    print("[INFO] Starting FrameView FPS → FireRate controller.")
    ensure_frameview_running()
    os.makedirs(os.path.dirname(OUTPUT_TXT), exist_ok=True)

    ema = None
    last_written = None
    last_data_time = 0.0

    current_log = None
    last_rescan = 0.0

    try:
        while True:
            now = time.time()

            # (Re)acquire or refresh the current log file
            if current_log is None or (now - last_rescan) >= RESCAN_EVERY:
                new_log = latest_frameview_log(BENCHMARK_DIR, GAME_EXE_NAME)
                if new_log and new_log != current_log:
                    print(f"[INFO] Using log: {new_log}")
                    current_log = new_log
                    # Reset data timers so we don’t immediately rescan again
                    last_data_time = now
                last_rescan = now

            if not current_log:
                print("[WAIT] No FrameView per-frame log found yet. Start a benchmark in FrameView...")
                time.sleep(POLL_INTERVAL)
                continue

            # Tail FPS from the current log
            for measurement in stream_fps_from_log(current_log):
                now = time.time()
                if measurement is None:
                    # No new data this tick; if stale too long, force a rescan (maybe a new log rolled)
                    if (now - last_data_time) >= RESCAN_EVERY:
                        current_log = None
                    break

                last_data_time = now
                fps = measurement
                if ema is None:
                    ema = fps
                else:
                    ema = EMA_ALPHA * fps + (1.0 - EMA_ALPHA) * ema

                rate = fps_to_rate(ema)

                # Avoid spamming disk: only write if the value changed
                if rate != last_written:
                    write_rate(OUTPUT_TXT, rate)
                    last_written = rate
                    print(f"[OK] FPS~{ema:5.1f} → rate {rate}")

            # small idle between scan cycles
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")


if __name__ == "__main__":
    main()
