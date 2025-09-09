# hd2_hotkeys.py / manual_control.py
from __future__ import annotations
from pathlib import Path
from functools import partial
import time, threading, re

BRIDGE_FILE = Path(r"C:\Users\Public\hd2_bridge.txt")

# ======= Globals / limits / steps =======
FIRERATE_DEFAULT = 3000
FIRERATE_MAX     = 5000
FIRERATE_MIN     = 1000
FIRERATE_INC            = 1000
FIRERATE_DEC            = -1000
FIRERATE_INC_FINETUNE   = 200
FIRERATE_DEC_FINETUNE   = -200

SPEED_DEFAULT = 2
SPEED_MAX     = 500
SPEED_MIN     = 1.5
SPEED_INC            = 1
SPEED_DEC            = -1
SPEED_INC_FINETUNE   = 0.1
SPEED_DEC_FINETUNE   = -0.1

FEATURES = {
    "Enter Firerate For Force Apply": {"min": FIRERATE_MIN, "max": FIRERATE_MAX, "default": FIRERATE_DEFAULT, "decimals": 3},
    "Enemy Multiplier":               {"min": SPEED_MIN,    "max": SPEED_MAX,    "default": SPEED_DEFAULT,   "decimals": 2},
}

def read_bridge() -> dict[str, float]:
    d = {}
    if BRIDGE_FILE.exists():
        for line in BRIDGE_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lstrip().startswith(("#",";","--")) or "=" not in line: continue
            k, v = line.split("=", 1); k = k.strip(); s = v.strip()
            m = re.search(r"[-+]?\d+(?:\.\d+)?|[-+]?\.\d+", s)
            if k and m:
                try: d[k] = float(m.group(0))
                except ValueError: pass
    for name, cfg in FEATURES.items():
        if name not in d: d[name] = float(cfg["default"])
    return d

def fmt_value(name: str, val: float) -> str:
    dec = FEATURES[name].get("decimals", 0)
    return f"{val:.{dec}f}" if dec > 0 else f"{int(round(val))}"

# replace your write_bridge with this
import time

def write_bridge(values: dict[str, float]) -> None:
    content = "\n".join(
        f"{name} = {fmt_value(name, values.get(name, FEATURES[name]['default']))}"
        for name in FEATURES
    ) + "\n"

    for _ in range(20):  # short retry for transient sharing violations
        try:
            with open(BRIDGE_FILE, "r+", encoding="utf-8") as f:
                f.seek(0)
                f.write(content)
                f.truncate()
            return
        except FileNotFoundError:
            # first-time create
            try:
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

# Use canonical key names to avoid parsing issues    
# ======= Hotkey bindings =======
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
]


# Optional: block keystrokes from reaching the game
HOTKEY_SUPPRESS = False

def main():
    if not BRIDGE_FILE.exists():
        # create with defaults so CE can read immediately
        write_bridge({name: float(cfg["default"]) for name, cfg in FEATURES.items()})

    import keyboard
    # validate combos early
    for combo, _ in HOTKEYS: keyboard.parse_hotkey_combinations(combo)

    print("HD2 Hotkeys active. Editing:", BRIDGE_FILE)
    print("Press CTRL+ALT+Q to quit.\n")
    for combo, func in HOTKEYS:
        keyboard.add_hotkey(combo, func, suppress=HOTKEY_SUPPRESS)
        print(f"  {combo:<22s} -> {func}")

    keyboard.add_hotkey("ctrl+alt+q", lambda: (_ for _ in ()).throw(SystemExit))
    try:
        while True: time.sleep(1)
    except SystemExit:
        print("Exiting hotkeys...")

if __name__ == "__main__":
    t = threading.Thread(target=main, daemon=False); t.start(); t.join()

