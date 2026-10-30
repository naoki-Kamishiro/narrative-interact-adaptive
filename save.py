"""
Save/load module.
Saves and loads state + history together.
Versioned for future compatibility.
"""

import json
from config import SAVE_FILE
from display import system_print, error_print

SAVE_VERSION = 1

def save(state: dict, history: list, filepath: str = SAVE_FILE) -> None:
    data = {
        "version": SAVE_VERSION,
        "state": state,
        "history": history,
    }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        system_print(f"Saved: {filepath}")
    except Exception as e:
        error_print(f"Save failed: {e}")

def load(filepath: str = SAVE_FILE) -> tuple[dict | None, list | None]:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        version = data.get("version", 0)
        if version != SAVE_VERSION:
            error_print(f"Save data version mismatch (v{version} → v{SAVE_VERSION}). Cannot load.")
            return None, None
        return data.get("state"), data.get("history")
    except FileNotFoundError:
        return None, None
    except Exception as e:
        error_print(f"Load failed: {e}")
        return None, None

def exists(filepath: str = SAVE_FILE) -> bool:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("state") and data.get("history"))
    except Exception:
        return False

def delete(filepath: str = SAVE_FILE) -> None:
    """Delete save data."""
    import os
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass
