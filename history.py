from prompt import build_system_prompt
import beat as beat_mod

def new_history(plot: dict = {}, plot_mode: str = "off", genre: str = "") -> list:
    return [{"role": "system", "content": build_system_prompt(plot, plot_mode, genre)}]

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
            # 同じroleが連続した場合は捨てず連結する（保存済み履歴は変更しない）
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
    strongモード用: sanitize後にビートを注入してAPI用メッセージを返す。
    戻り値: (注入済みメッセージリスト, デバッグ情報 or None)
    """
    msgs = sanitize(history)
    return beat_mod.inject(msgs, queue, ptr)


def rebuild_system(history: list, plot: dict, plot_mode: str = "off", genre: str = "") -> list:
    """ロード時にシステムプロンプトをプロットで再構築する。"""
    new_system = {"role": "system", "content": build_system_prompt(plot, plot_mode, genre)}
    other_msgs = [m for m in history if m["role"] != "system"]
    return [new_system] + other_msgs
