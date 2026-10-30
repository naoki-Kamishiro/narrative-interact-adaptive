"""
Console color-coding display module.
GM narration: yellow  Character dialogue (inside 「」): white  System: blue  Error: red  GM character comment: cyan  Turning point: bold yellow
"""

import re
import sys

RESET   = "\033[0m"
YELLOW  = "\033[33m"
WHITE   = "\033[97m"
BLUE    = "\033[94m"
RED     = "\033[91m"
DIM     = "\033[2m"
CYAN        = "\033[96m"
BOLD_YELLOW = "\033[93m"
MAGENTA = "\033[95m"
HR      = DIM + "─" * 60 + RESET

def _enable_ansi_windows():
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

_enable_ansi_windows()

def _colorize_gm(text: str) -> str:
    """Build a colorized string: text inside 「」 is white; everything else is yellow."""
    parts = re.split(r"(「[^」]*」)", text)
    result = []
    for part in parts:
        if part.startswith("「") and part.endswith("」"):
            result.append(WHITE + part + RESET)
        else:
            result.append(YELLOW + part + RESET)
    return "".join(result)

def gm_print(text: str) -> None:
    """Non-streaming GM output (internal use, e.g. plot generation errors)."""
    print(HR)
    print(BLUE + "GM:" + RESET)
    print(_colorize_gm(text))
    print(HR)

def gm_char_print(text: str) -> None:
    """Display a GM character one-liner comment (prefix is the same blue as normal GM; comment body is cyan)."""
    print(BLUE + "GM:" + RESET + " " + CYAN + text + RESET)

def gm_turning_point_print(text: str) -> None:
    """Display a turning-point enhanced-description message (bold yellow)."""
    print(BOLD_YELLOW + text + RESET)

_display_language: str = "ja"

def set_display_language(lang: str) -> None:
    global _display_language
    _display_language = lang

def system_print(text: str) -> None:
    prefix = "System" if _display_language == "en" else "システム"
    print(BLUE + f"[{prefix}: {text}]" + RESET)

def error_print(text: str) -> None:
    prefix = "Error" if _display_language == "en" else "エラー"
    print(RED + f"[{prefix}: {text}]" + RESET)

def hr() -> None:
    print(HR)
