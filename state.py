"""
ゲームの現在状態を保持するモジュール。
フルスナップショット管理。更新は必ずupdate()経由。
将来的にengine.pyがここを通じて状態を制御する。
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
        "fixation_count": 0,
        "fixation_ending": False,
        "deviation_count": 0,
        "peak_deviation_count": 0,
        "adaptive_replotted": False,
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
