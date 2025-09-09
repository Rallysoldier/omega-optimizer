# hd2_firerate_controller_test.py
# Writes increasing values to the same bridge file used by the controller,
# so Cheat Engine (via your Lua bridge) should display the new value each tick.

import time
import argparse
from pathlib import Path

DEFAULT_FILE = r"C:\Users\Public\hd2_fire_rate.txt"

def write_bridge_value(path: str, value: float):
    p = Path(path)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as w:
        w.write(f"{value:.3f}")
    # Atomic replace to avoid CE reading partial writes
    tmp.replace(p)

def read_bridge_value(path: str):
    try:
        with open(path, "r", encoding="utf-8") as r:
            s = r.read().strip()
            return float(s)
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser(description="CE bridge smoke test: step value by +step each interval.")
    ap.add_argument("--file", default=DEFAULT_FILE, help="Bridge file path")
    ap.add_argument("--start", type=float, default=1000.0, help="Starting value if file unreadable/missing")
    ap.add_argument("--step", type=float, default=1000.0, help="Increment per tick")
    ap.add_argument("--interval", type=float, default=1.0, help="Seconds between writes")
    ap.add_argument("--count", type=int, default=10, help="Number of steps (use 0 for infinite)")
    args = ap.parse_args()

    # Baseline: use existing file value if valid, else --start
    current = read_bridge_value(args.file)
    if current is None:
        current = float(args.start)
        write_bridge_value(args.file, current)
        print(f"[TEST] Initialized bridge to {current:.1f} ({args.file})")
    else:
        print(f"[TEST] Starting from existing bridge value {current:.1f} ({args.file})")

    steps_done = 0
    try:
        while True:
            time.sleep(args.interval)
            next_val = current + args.step
            write_bridge_value(args.file, next_val)

            direction = "↑ RAISE"
            print(f"[TEST] {direction}: {current:7.1f} → {next_val:7.1f}")

            current = next_val
            steps_done += 1
            if args.count and steps_done >= args.count:
                print("[TEST] Done.")
                break
    except KeyboardInterrupt:
        print("\n[TEST] Stopped by user.")

if __name__ == "__main__":
    main()
