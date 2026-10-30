"""
Module that holds the current game state.
Full-snapshot management; all updates must go through update().
In the future, engine.py will control state through this module.
"""

_state: dict = {}

def init(genre: str, title: str, plot: dict, plot_mode: str = "off") -> None:
    global _state
    _state = {
        "genre": genre,
        "title": title,
        "plot": plot,
        "plot_mode": plot_mode,
        "use_dice": True,
        "difficulty_preset": "normal",
        "summary": "",
        "beat_queue": [],
        "beat_ptr": 0,
        "ending_suppressed": False,
        "deviation_count": 0,
        "peak_deviation_count": 0,
        "adaptive_replotted": False,
        "gm_character": "none",
        "turning_point_triggered": False,
        "turning_point_injected": False,
        "beat_just_advanced": False,
        "gm_char_log": [],
        "language": "ja",
    }

def get() -> dict:
    return _state

def update(partial: dict) -> None:
    _state.update(partial)

def set_summary(summary: str) -> None:
    _state["summary"] = summary

def get_plot() -> dict:
    return _state.get("plot", {})

def get_plot_mode() -> str:
    return _state.get("plot_mode", "off")

def load_from(data: dict) -> None:
    global _state
    _state = data
