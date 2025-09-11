# hd2_hotkeys.py / manual_control.py
from __future__ import annotations
from pathlib import Path
from functools import partial
import random
import time, threading, re

BRIDGE_FILE = Path(r"C:\Users\Public\hd2_bridge.txt")

# ======= Globals / limits / steps =======
FIRERATE_DEFAULT = 3000
FIRERATE_MAX     = 8000
FIRERATE_MIN     = 1000
FIRERATE_INC            = 1000
FIRERATE_DEC            = -1000
FIRERATE_INC_FINETUNE   = 500
FIRERATE_DEC_FINETUNE   = -500

SPEED_DEFAULT = 2
SPEED_MAX     = 1000
SPEED_MIN     = 1.8
SPEED_INC            = 1
SPEED_DEC            = -1
SPEED_INC_FINETUNE   = 0.5
SPEED_DEC_FINETUNE   = -0.5

RAND_MIN_INTERVAL = 15
RAND_MAX_INTERVAL = 60
# ----- Random mode ranges (independent of normal clamps) -----
RAND_FIRERATE_MIN = 1000 #1000
RAND_FIRERATE_MAX = 7000 #7000
RAND_SPEED_MIN     = 1.6    #1.6 #1.8
RAND_SPEED_MAX     = 4      #4
# ----- Random mode outlier for Enemy Multiplier -----
RAND_SPEED_OUTLIER = 250.0         # the spike value #250 #200
RAND_SPEED_OUTLIER_CHANCE = 0.25   # 2% chance each tick (0.0 - 1.0) #.25

# Map features to their random ranges
RAND_BOUNDS = {
    "Enter Firerate For Force Apply": {"min": RAND_FIRERATE_MIN, "max": RAND_FIRERATE_MAX},
    "Enemy Multiplier":               {"min": RAND_SPEED_MIN,     "max": RAND_SPEED_MAX},
}

# --- write lock prevents our own threads from colliding ---
WRITE_LOCK = threading.Lock()

FEATURES = {
    "Enter Firerate For Force Apply": {"min": FIRERATE_MIN, "max": FIRERATE_MAX, "default": FIRERATE_DEFAULT, "decimals": 3},
    "Enemy Multiplier":               {"min": SPEED_MIN,    "max": SPEED_MAX,    "default": SPEED_DEFAULT,   "decimals": 2},
}

def read_bridge() -> dict[str, float]:
    d = {}
    if BRIDGE_FILE.exists():
        for line in BRIDGE_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lstrip().startswith(("#",";","--")) or "=" not in line:
                continue
            k, v = line.split("=", 1); k = k.strip(); s = v.strip()
            m = re.search(r"[-+]?\d+(?:\.\d+)?|[-+]?\.\d+", s)
            if k and m:
                try:
                    d[k] = float(m.group(0))
                except ValueError:
                    pass
    for name, cfg in FEATURES.items():
        if name not in d:
            d[name] = float(cfg["default"])
    return d

def fmt_value(name: str, val: float) -> str:
    dec = FEATURES[name].get("decimals", 0)
    return f"{val:.{dec}f}" if dec > 0 else f"{int(round(val))}"

def write_bridge(values: dict[str, float]) -> None:
    content = "\n".join(
        f"{name} = {fmt_value(name, values.get(name, FEATURES[name]['default']))}"
        for name in FEATURES
    ) + "\n"

    for _ in range(20):  # short retry for transient sharing violations
        try:
            with WRITE_LOCK:
                with open(BRIDGE_FILE, "r+", encoding="utf-8") as f:
                    f.seek(0)
                    f.write(content)
                    f.truncate()
            return
        except FileNotFoundError:
            try:
                with WRITE_LOCK:
                    BRIDGE_FILE.write_text(content, encoding="utf-8")
                return
            except PermissionError:
                time.sleep(0.02)
        except PermissionError:
            time.sleep(0.02)
    raise PermissionError(f"Could not write {BRIDGE_FILE} (file in use).")

def clamp(name: str, v: float) -> float:
    cfg = FEATURES[name]
    return max(cfg["min"], min(cfg["max"], v))

def action_set(name: str, new_val: float):
    vals = read_bridge()
    vals[name] = clamp(name, float(new_val))
    write_bridge(vals)
    print(f"[SET] {name} = {fmt_value(name, vals[name])}")

def action_adjust(name: str, delta: float):
    vals = read_bridge()
    v = float(vals.get(name, float(FEATURES[name]["default"])))
    vals[name] = clamp(name, v + float(delta))
    write_bridge(vals)
    print(f"[ADJ] {name} = {fmt_value(name, vals[name])} (Δ {delta})")

# ---- Random Mode ----------------------------------------------------------------------
_rand_thread: threading.Thread | None = None
_rand_stop = threading.Event()

def _rand_interval() -> float:
    lo = float(RAND_MIN_INTERVAL)
    hi = float(RAND_MAX_INTERVAL)
    if hi < lo:
        lo, hi = hi, lo
    lo = max(0.05, lo)  # avoid zero/negative sleeps
    return random.uniform(lo, hi)

def _randomize_once():
    vals = read_bridge()
    outlier_hit = False

    for name, cfg in FEATURES.items():
        if name == "Enemy Multiplier" and random.random() < RAND_SPEED_OUTLIER_CHANCE:
            # Outlier: bypass RAND_* range, but still respect absolute SPEED_MIN/MAX via clamp()
            rnd = float(RAND_SPEED_OUTLIER)
            outlier_hit = True
        else:
            bounds = RAND_BOUNDS[name]
            lo, hi = float(bounds["min"]), float(bounds["max"])
            if hi < lo:
                lo, hi = hi, lo
            rnd = random.uniform(lo, hi)

        vals[name] = clamp(name, rnd)  # absolute feature clamp only

    write_bridge(vals)
    print(f"[RANDOM]{' [OUTLIER]' if outlier_hit else ''} "
          + " | ".join(f"{k}={fmt_value(k, vals[k])}" for k in FEATURES))

def _random_mode_worker(stop_evt: threading.Event):
    print("[RANDOM] mode ENABLED")
    try:
        while not stop_evt.is_set():
            _randomize_once()
            time.sleep(_rand_interval())
    finally:
        print("[RANDOM] mode DISABLED")

def toggle_random_mode():
    global _rand_thread
    if _rand_thread and _rand_thread.is_alive():
        _rand_stop.set()
        _rand_thread.join(timeout=1.0)
        _rand_thread = None
        _rand_stop.clear()
    else:
        _rand_stop.clear()
        _rand_thread = threading.Thread(target=_random_mode_worker, args=(_rand_stop,), daemon=True)
        _rand_thread.start()

# ======= Hotkey bindings ========================================================================
HOTKEYS = [
    # ----- Fire Rate (float)
    ("num 0+num 5", partial(action_set, "Enter Firerate For Force Apply", FIRERATE_DEFAULT)),
    ("num 0+num 9", partial(action_set, "Enter Firerate For Force Apply", FIRERATE_MAX)),
    ("num 0+num 1", partial(action_set, "Enter Firerate For Force Apply", FIRERATE_MIN)),
    ("num 0+num 8", partial(action_adjust, "Enter Firerate For Force Apply", FIRERATE_INC)),
    ("num 0+num 2", partial(action_adjust, "Enter Firerate For Force Apply", FIRERATE_DEC)),
    ("num 0+num 6", partial(action_adjust, "Enter Firerate For Force Apply", FIRERATE_INC_FINETUNE)),
    ("num 0+num 4", partial(action_adjust, "Enter Firerate For Force Apply", FIRERATE_DEC_FINETUNE)),

    # ----- Enemy Multiplier (float)
    ("add+num 5", partial(action_set, "Enemy Multiplier", SPEED_DEFAULT)),
    ("add+num 9", partial(action_set, "Enemy Multiplier", SPEED_MAX)),
    ("add+num 1", partial(action_set, "Enemy Multiplier", SPEED_MIN)),
    ("add+num 8", partial(action_adjust, "Enemy Multiplier", SPEED_INC)),
    ("add+num 2", partial(action_adjust, "Enemy Multiplier", SPEED_DEC)),
    ("add+num 6", partial(action_adjust, "Enemy Multiplier", SPEED_INC_FINETUNE)),
    ("add+num 4", partial(action_adjust, "Enemy Multiplier", SPEED_DEC_FINETUNE)),

    # Toggle Random Mode (numpad minus + numpad 7)
    ("subtract+num 7", toggle_random_mode),
]

# Optional: block keystrokes from reaching the game
HOTKEY_SUPPRESS = False

# Graceful quit event
STOP = threading.Event()

def main():
    if not BRIDGE_FILE.exists():
        write_bridge({name: float(cfg["default"]) for name, cfg in FEATURES.items()})

    import keyboard

    # Validate combos early
    for combo, _ in HOTKEYS:
        keyboard.parse_hotkey_combinations(combo)

    # Log active random settings
    print(f"[RANDOM] interval {RAND_MIN_INTERVAL}-{RAND_MAX_INTERVAL}s | "
          f"FR {RAND_FIRERATE_MIN}-{RAND_FIRERATE_MAX} | "
          f"SPD {RAND_SPEED_MIN}-{RAND_SPEED_MAX} (outlier {RAND_SPEED_OUTLIER} @ {RAND_SPEED_OUTLIER_CHANCE*100:.1f}%)")

    print("HD2 Hotkeys active. Editing:", BRIDGE_FILE)
    print("Press CTRL+ALT+Q to quit.\n")

    # Bind hotkeys
    for combo, func in HOTKEYS:
        keyboard.add_hotkey(combo, func, suppress=HOTKEY_SUPPRESS)
        print(f"  {combo:<22s} -> {func}")

    # Quit handler
    keyboard.add_hotkey("ctrl+alt+q", STOP.set)

    try:
        while not STOP.is_set():
            time.sleep(0.2)
    finally:
        if _rand_thread and _rand_thread.is_alive():
            _rand_stop.set()
            _rand_thread.join(timeout=1.0)
        print("Exiting hotkeys...")

if __name__ == "__main__":
    t = threading.Thread(target=main, daemon=False)
    t.start()
    t.join()

'''
MODE/PRESET IDEAS:
1. CODE VIRUS: Freezes all Automatons for 10 secs with 0 firerate and 0 speed.
2. Armor Sabotage: Ruins devastator HP or armor value and/or instantly kills a specific enemy type.
3. Omega Mortars: 
4. Factory Strider Up Armor: 
5. Super Wave: Eliminate all hulks and then set firerate to beyond safe bounds
6. Enhanced Anti-Detection Suite: Hide all sentries from enemy eyes
7. Hyper Sample Collection: Activates Samples Over Limit Reward
'''
