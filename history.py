from prompt import build_system_prompt
import beat as beat_mod

def new_history(plot: dict = {}, plot_mode: str = "off", genre: str = "", language: str = "ja") -> list:
    return [{"role": "system", "content": build_system_prompt(plot, plot_mode, genre, language)}]

def add_user(history: list, content: str) -> list:
    history.append({"role": "user", "content": content})
    return history

def add_assistant(history: list, content: str) -> list:
    history.append({"role": "assistant", "content": content})
    return history

def sanitize(history: list) -> list:
    system_msgs = [m for m in history if m["role"] == "system"]
    other_msgs  = [m for m in history if m["role"] != "system"]
    sanitized = []
    for msg in other_msgs:
        if sanitized and sanitized[-1]["role"] == msg["role"]:
            # Consecutive same-role messages are merged rather than dropped (saved history is not modified)
            sanitized[-1] = {
                "role": msg["role"],
                "content": sanitized[-1]["content"] + "\n\n" + msg["content"],
            }
            continue
        sanitized.append(dict(msg))
    return system_msgs + sanitized

def build_for_api(history: list) -> list:
    return sanitize(history)

def build_for_api_with_beat(history: list, queue: list, ptr: int) -> tuple[list, str | None]:
    """
    For strong mode: sanitize history, inject the current beat, and return the API message list.
    Returns: (injected message list, debug string or None)
    """
    msgs = sanitize(history)
    return beat_mod.inject(msgs, queue, ptr)


def rebuild_system(history: list, plot: dict, plot_mode: str = "off", genre: str = "", language: str = "ja") -> list:
    """Rebuild the system prompt with the plot on session load."""
    new_system = {"role": "system", "content": build_system_prompt(plot, plot_mode, genre, language)}
    other_msgs = [m for m in history if m["role"] != "system"]
    return [new_system] + other_msgs
