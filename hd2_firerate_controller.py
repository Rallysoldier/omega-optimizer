# hd2_firerate_controller.py

import csv
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import argparse
import shutil

# -----------------------------
# CONFIG – tweak to your liking
# -----------------------------
@dataclass
class Config:
    # Your NVIDIA FrameView PresentMon path (64-bit)
    presentmon_path: str = r"C:\Program Files\NVIDIA Corporation\FrameViewSDK\bin\PresentMon_x64.exe"
    game_exe_name: str = "helldivers2.exe"
    csv_path: str = r"C:\Users\Public\presentmon_hd2.csv"
    bridge_file: str = r"C:\Users\Public\hd2_fire_rate.txt"

    # Value Knobs
    change_eps: float = 10.0     # only log when rate changes by >= this amount
    verbose_each_update: bool = True  # True = print every update (spammy)
    show_fps_log: bool = True      # when True, print FPS periodically
    fps_log_interval_s: float = 10.0  # seconds between FPS logs

    # Controller behavior
    target_fps: float = 60.0       # FPS you consider "ideal"
    base_rate: float = 3000.0       # Fire-rate at target_fps
    min_rate: float = 1000.0         # Clamp lower bound
    max_rate: float = 8500.0        # Clamp upper bound
    response_gamma: float = 1.0     # 1.0 linear; >1 gentler below target
    ema_alpha: float = 0.2          # FPS smoothing (0..1). Higher = snappier.
    update_interval_s: float = 0.25 # How often to recompute/write fire-rate

CONFIG = Config()

# -----------------------------
# Utilities
# -----------------------------
def _strip_quotes(p: Optional[str]) -> Optional[str]:
    if not p:
        return p
    p = p.strip()
    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        return p[1:-1]
    return p

class Ema:
    def __init__(self, alpha: float, initial: Optional[float] = None):
        self.alpha = alpha
        self.value = initial
    def update(self, x: float) -> float:
        if self.value is None:
            self.value = x
        else:
            self.value = self.alpha * x + (1 - self.alpha) * self.value
        return self.value

def fps_to_rate(fps: float, cfg: Config) -> float:
    if fps <= 0:
        return cfg.min_rate
    frac = fps / cfg.target_fps
    if frac < 1.0:
        frac = frac ** cfg.response_gamma
    rate = cfg.base_rate * frac
    return max(cfg.min_rate, min(cfg.max_rate, rate))

# -----------------------------
# PresentMon runner & CSV tail
# -----------------------------
def resolve_presentmon_path(cfg_path: str, cli_override: Optional[str]) -> str:
    # Priority: CLI > env var > config default > PATH
    for candidate in (
        _strip_quotes(cli_override),
        _strip_quotes(os.environ.get("PRESENTMON")),
        _strip_quotes(cfg_path),
        shutil.which("PresentMon_x64.exe"),
        shutil.which("PresentMon.exe"),
        shutil.which("presentmon.exe"),
    ):
        if candidate and os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        "PresentMon executable not found.\n"
        "Provide it via --presentmon, set env PRESENTMON, keep CONFIG.presentmon_path correct, "
        "or put PresentMon on PATH."
    )

def start_presentmon(presentmon_exe: str, cfg: Config) -> subprocess.Popen:
    # Fresh CSV
    try:
        os.remove(cfg.csv_path)
    except FileNotFoundError:
        pass

    args = [
        presentmon_exe,
        "-process_name", cfg.game_exe_name,
        "-output_file", cfg.csv_path,
    ]
    return subprocess.Popen(
        args,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

def iter_fps_from_presentmon(csv_path: str):
    while not os.path.exists(csv_path):
        time.sleep(0.1)

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)

        # Read header
        header = None
        while header is None:
            try:
                header = next(reader)
            except StopIteration:
                time.sleep(0.05)

        header_lc = [h.lower() for h in header]
        # 'msBetweenPresents' is the canonical column name
        try:
            mbp_idx = header_lc.index("msbetweenpresents")
        except ValueError:
            # Fallback: locate any close variant
            mbp_idx = next((i for i, h in enumerate(header_lc) if "msbetweenpresent" in h), None)
            if mbp_idx is None:
                raise RuntimeError(
                    "Couldn't find 'msBetweenPresents' in PresentMon CSV header:\n" + ",".join(header)
                )

        # Follow appended rows
        f.seek(0, os.SEEK_END)
        while True:
            pos = f.tell()
            line = f.readline()
            if not line:
                time.sleep(0.05)
                f.seek(pos)
                continue

            row = next(csv.reader([line]))
            if len(row) <= mbp_idx:
                continue

            try:
                ms = float(row[mbp_idx])
                if ms > 0:
                    yield 1000.0 / ms
            except (ValueError, ZeroDivisionError):
                continue

def write_bridge_value(path: str, value: float):
    p = Path(path)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as w:
        w.write(f"{value:.3f}")
    try:
        os.replace(tmp, p)
    except PermissionError:
        time.sleep(0.05)
        os.replace(tmp, p)

# -----------------------------
# Main
# -----------------------------
def main(cfg: Config = CONFIG):
    parser = argparse.ArgumentParser()
    parser.add_argument("--presentmon", help="Path to PresentMon.exe or PresentMon_x64.exe", default=None)
    args = parser.parse_args()

    # Bootstrap: write a sane, clamped value immediately so stale 11000 gets replaced
    init_rate = max(min(cfg.base_rate, cfg.max_rate), cfg.min_rate)
    write_bridge_value(cfg.bridge_file, init_rate)
    print(f"[CTRL] BOOTSTRAP write → {init_rate:.1f}")

    last_fps_log = 0.0

    pm_exe = resolve_presentmon_path(cfg.presentmon_path, args.presentmon)

    print(f"[HD2] Starting PresentMon: {pm_exe}")
    pm = start_presentmon(pm_exe, cfg)

    ema = Ema(cfg.ema_alpha)
    last_write = 0.0
    prev_rate: Optional[float] = None

    try:
        for fps in iter_fps_from_presentmon(cfg.csv_path):
            smoothed = ema.update(fps)
            # Periodic FPS logging (EMA view of FPS)
            if cfg.show_fps_log and (time.time() - last_fps_log >= cfg.fps_log_interval_s):
                if smoothed is None:
                    print("[FPS] — (no frames yet)")
                else:
                    print(f"[FPS] {smoothed:6.1f}")
                last_fps_log = time.time()
            now = time.time()
            if now - last_write >= cfg.update_interval_s:
                rate = fps_to_rate(smoothed, cfg)
                write_bridge_value(cfg.bridge_file, rate)

                # ---- Logging logic ----
                if cfg.verbose_each_update and prev_rate is not None:
                    direction = "↑ RAISE" if rate > prev_rate else ("↓ LOWER" if rate < prev_rate else "→ HOLD")
                    print(f"{direction}: {prev_rate:7.1f} → {rate:7.1f}  (FPS {smoothed:6.1f})")
                elif prev_rate is None:
                    print(f"INIT:  Rate={rate:7.1f}  (FPS {smoothed:6.1f})")
                else:
                    delta = rate - prev_rate
                    if abs(delta) >= cfg.change_eps:
                        if delta > 0:
                            print(f"↑ RAISE: {prev_rate:7.1f} → {rate:7.1f}  (FPS {smoothed:6.1f})")
                        else:
                            print(f"↓ LOWER: {prev_rate:7.1f} → {rate:7.1f}  (FPS {smoothed:6.1f})")
                    # else: small jitter, stay quiet

                prev_rate = rate
                last_write = now
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pm.send_signal(signal.SIGTERM)
        except Exception:
            pass


if __name__ == "__main__":
    main()
