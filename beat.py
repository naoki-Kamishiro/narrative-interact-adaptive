"""
Beat injection module (used by strong mode and off mode).
Manages the plot beat queue and injects one beat per turn into the API message copy.
"""

import re
import sys

# Debug output flag (enabled from main.py via beat_mod.DEBUG_MODE = True)
DEBUG_MODE: bool = False

def _debug(*args) -> None:
    if DEBUG_MODE:
        print(*args, file=sys.stderr)

# Timing sort dict (absorbs label variations)
TIMING_ORDER = {
    "early": 0,
    "mid": 1,
    "pre-climax": 2,
    "climax": 3,
    # Japanese fallbacks for plots generated in ja mode
    "序盤": 0,
    "中盤": 1,
    "クライマックス直前": 2,
    "クライマックス": 3,
}

# Secondary sort: beat type priority
TYPE_ORDER = {
    "misconception": 0,
    "failure": 1,
    "choice": 2,
    "twist": 3,
    "character": 4,
}

# Injection text templates (Japanese, for ja mode)
_TEMPLATES = {
    "misconception": "今回の描写で、現在いる場所で{content}という出来事を起こすこと。ただし内面の変化ではなく外から観察できる出来事として描写すること。事実はNPCが台詞で言ってよいが、その事実が主人公にとって何を意味するかはNPCも地の文も言わないこと。",
    "failure":       "今回の描写で、現在いる場所で{content}という状況を発生させること。プレイヤーの行動とは別に世界の側から引き起こすこと。",
    "choice":        "今回の描写で、{content}という局面をプレイヤーが直面する形で描写すること。選択を迫ること。代償は{cost}。",
    "twist":         "今回の描写で、{content}という出来事を世界の側から発生させること。プレイヤーが関係する行動をとらなくても起こすこと。事実はNPCが台詞で言ってよいが、その事実が主人公にとって何を意味するかはNPCも地の文も言わないこと。",
    "character":     "{name}が現在地へ現れ、プレイヤーと接触すること。",
}

def build_queue(plot: dict) -> list:
    """Build a beat queue from the plot dict."""
    queue = []

    for i, item in enumerate(plot.get("misconceptions", [])):
        if not isinstance(item, dict):
            continue
        queue.append({
            "src": "misconceptions",
            "src_idx": i,
            "type": "misconception",
            "timing": item.get("timing", "early"),
            "content": item.get("content", ""),
            "done": False,
        })

    for i, item in enumerate(plot.get("failures", [])):
        if not isinstance(item, dict):
            continue
        queue.append({
            "src": "failures",
            "src_idx": i,
            "type": "failure",
            "timing": item.get("timing", "early"),
            "content": item.get("content", ""),
            "done": False,
        })

    for i, item in enumerate(plot.get("choices", [])):
        if not isinstance(item, dict):
            continue
        queue.append({
            "src": "choices",
            "src_idx": i,
            "type": "choice",
            "timing": item.get("timing", "mid"),
            "content": item.get("description", ""),
            "cost": item.get("cost", ""),
            "done": False,
        })

    for i, item in enumerate(plot.get("twists", [])):
        if not isinstance(item, dict):
            continue
        queue.append({
            "src": "twists",
            "src_idx": i,
            "type": "twist",
            "timing": item.get("timing", "mid"),
            "content": item.get("content", ""),
            "done": False,
        })

    # Character appearance beats (generated from characters list)
    protagonist_raw = plot.get("protagonist", {})
    protagonist_name = protagonist_raw.get("name", "") if isinstance(protagonist_raw, dict) else ""
    for i, c in enumerate(plot.get("characters", [])):
        if not isinstance(c, dict):
            continue
        # Prefer {"name": "...", "role": "..."} format;
        # fall back to {"sword_master": "description"} style keys
        if "name" in c:
            name = c.get("name", "").strip(": ").strip()
        else:
            first_key = next(iter(c), "")
            name = first_key.strip(": ").strip()
        if name and name != protagonist_name:
            queue.append({
                "src": "characters",
                "src_idx": i,
                "type": "character",
                "timing": "early",
                "name": name,
                "done": False,
            })

    # Sort: timing → type
    queue.sort(key=lambda b: (
        TIMING_ORDER.get(b["timing"], 99),
        TYPE_ORDER.get(b["type"], 99),
    ))

    return queue


# Injection text templates (English)
_TEMPLATES_EN = {
    "misconception": "In this turn, cause the following event to occur at the current location: {content}. Depict it as an externally observable event, not an internal change. NPCs may state the fact in dialogue, but neither NPCs nor narration should say what it means to the protagonist.",
    "failure":       "In this turn, cause the following situation to arise at the current location: {content}. Trigger it as a world-side event, independent of the player's action.",
    "choice":        "In this turn, depict the protagonist facing this dilemma: {content}. Force a choice. The cost: {cost}.",
    "twist":         "In this turn, cause the following event to occur as a world-side happening: {content}. Trigger it even if the player has not taken a related action. NPCs may state the fact in dialogue, but neither NPCs nor narration should say what it means to the protagonist.",
    "character":     "{name} appears at the protagonist's location and makes contact with the player.",
}


def make_injection(beat: dict, language: str = "ja") -> str:
    """Generate injection text from a beat entry."""
    # Adaptive beats carry their own injection text
    if "injection" in beat:
        return beat["injection"]
    t = beat["type"]
    templates = _TEMPLATES_EN if language == "en" else _TEMPLATES
    tmpl = templates.get(t, "")
    if t == "character":
        return tmpl.format(name=beat.get("name", ""))
    elif t == "choice":
        return tmpl.format(content=beat.get("content", ""), cost=beat.get("cost", ""))
    else:
        return tmpl.format(content=beat.get("content", ""))


def get_current_beat(queue: list, ptr: int) -> dict | None:
    """Return the beat at the current pointer, skipping done entries. Returns None when queue is exhausted."""
    while ptr < len(queue):
        beat = queue[ptr]
        if not beat["done"]:
            return beat
        ptr += 1
    return None


def inject(messages: list, queue: list, ptr: int, language: str = "ja") -> tuple[list, str | None]:
    """
    Append beat injection text to the last user message in the API message list.
    Returns: (modified message list, debug string for the injected beat or None)
    """
    beat = get_current_beat(queue, ptr)
    if beat is None:
        return messages, None

    injection = make_injection(beat, language=language)
    if not injection:
        return messages, None

    # Work on a copy so the original history is not mutated
    msgs = [dict(m) for m in messages]
    for i in reversed(range(len(msgs))):
        if msgs[i]["role"] == "user":
            msgs[i] = dict(msgs[i])
            if language == "en":
                msgs[i]["content"] = msgs[i]["content"] + f"\n(Scene instruction for GM: {injection})"
            else:
                msgs[i]["content"] = msgs[i]["content"] + f"\n（GMへの場面指示: {injection}）"
            break

    beat_type = beat.get("type", "adaptive")
    debug = f"[BEAT] ptr={ptr} type={beat_type} timing={beat.get('timing', '-')}"
    return msgs, debug


def detect_character(response: str, name: str) -> bool:
    """Check whether a character name appears in the GM response.
    Splits composite names (・／ / または / or / parenthetical) and tests each token.
    Returns True if any token is found in the response.
    """
    if name in response:
        return True
    # Split on delimiters and strip parenthetical alternatives
    # Targets: ・ / （〜） / (〜) / または / or
    tokens = re.split(r'[・／/\s]|または|or|\(.*?\)|（.*?）', name)
    for token in tokens:
        token = token.strip()
        if token and token in response:
            return True
    return False


def advance(queue: list, ptr: int, response: str, language: str = "ja") -> tuple[list, int]:
    """
    Check whether the current beat was depicted and advance the pointer.
    Character beats are verified by name matching (EN mode uses trust-advance).
    Event beats are trusted after a single injection.
    Returns: (updated queue, new ptr)

    Note: get_current_beat() skips done entries and returns the first undone beat.
    advance() uses the same logic to find the actual injected beat index and marks
    that index done rather than blindly using queue[ptr].
    """
    # Locate the actual index of the injected beat
    actual_idx = ptr
    while actual_idx < len(queue) and queue[actual_idx]["done"]:
        actual_idx += 1

    if actual_idx >= len(queue):
        return queue, ptr

    beat = queue[actual_idx]

    if beat.get("type") == "character":
        name = beat.get("name", "")
        # In EN mode the GM outputs English, so Japanese name matching is unreliable.
        # Use trust-advance: mark done after a single injection.
        if language == "en":
            _debug(f"[BEAT] EN mode: trust-advance character beat '{name}'")
            queue[actual_idx]["done"] = True
            return queue, actual_idx + 1
        if detect_character(response, name):
            queue[actual_idx]["done"] = True
            return queue, actual_idx + 1
        else:
            # Not detected: keep pending and re-inject next turn
            _debug(f"[BEAT] character '{name}' not detected, re-injecting next turn")
            return queue, ptr
    else:
        # Event beats: trust and advance after a single injection
        queue[actual_idx]["done"] = True
        return queue, actual_idx + 1


def filter_output(response: str) -> str:
    """Remove full-width parenthetical-only lines from GM output (leaked GM reasoning)."""
    lines = response.split("\n")
    filtered = []
    for line in lines:
        stripped = line.strip()
        # Remove lines that consist solely of （...）
        if re.fullmatch(r'（[^）]*）', stripped):
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def handle_ending_suppression(queue: list, ptr: int) -> tuple[list, int, bool]:
    """
    Handle an early 【エンディング】 / [ENDING] tag from the GM.
    Keeps only pending character beats; discards everything else.
    Suppression is one-time (ending_suppressed flag is managed in state).
    Returns: (updated queue, new ptr, suppressed?)
    """
    # Collect pending character beats
    pending_chars = [b for b in queue[ptr:] if b.get("type") == "character" and not b["done"]]

    if not pending_chars:
        # Nothing left to inject: let the ending through
        return queue, ptr, False

    # Keep only character beats; discard the rest by marking them done
    for i in range(ptr, len(queue)):
        if queue[i].get("type") != "character":
            queue[i]["done"] = True

    _debug(f"[BEAT] ending suppressed: {len(pending_chars)} character beat(s) remaining")
    return queue, ptr, True
