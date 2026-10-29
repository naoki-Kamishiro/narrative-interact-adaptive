"""
コンソール色分け表示モジュール。
GM地の文：黄　登場人物セリフ（「」内）：白　システム：青　エラー：赤　GMキャラコメント：シアン　転換点：太字黄
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
    """「」の内側を白、それ以外を黄色で出力する文字列を生成する。"""
    parts = re.split(r"(「[^」]*」)", text)
    result = []
    for part in parts:
        if part.startswith("「") and part.endswith("」"):
            result.append(WHITE + part + RESET)
        else:
            result.append(YELLOW + part + RESET)
    return "".join(result)

def gm_print(text: str) -> None:
    """非ストリーミング用（プロット生成エラーなど内部用途）。"""
    print(HR)
    print(BLUE + "GM:" + RESET)
    print(_colorize_gm(text))
    print(HR)

def gm_char_print(text: str) -> None:
    """GMキャラクターの一言コメントを表示する（プレフィックスは通常GMと同じ青、コメント本文はシアン）。"""
    print(BLUE + "GM:" + RESET + " " + CYAN + text + RESET)

def gm_turning_point_print(text: str) -> None:
    """転換点の描写強化メッセージを表示する（太字黄色）。"""
    print(BOLD_YELLOW + text + RESET)

def system_print(text: str) -> None:
    print(BLUE + f"[システム: {text}]" + RESET)

def error_print(text: str) -> None:
    print(RED + f"[エラー: {text}]" + RESET)

def hr() -> None:
    print(HR)
