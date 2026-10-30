"""
Plot generation module.
Plots are treated as immutable; updates only occur during the compression phase.
"""

import json
import re
import sys
from json_repair import repair_json
from api import chat_json
from prompt import SYSTEM_PLOT, build_plot_message
from display import system_print

DEBUG_MODE: bool = False

MAX_RETRIES = 3

def generate(genre: str, title: str, language: str = "ja") -> dict:
    if language == "en":
        system_print("Generating plot...")
    else:
        system_print("プロットを生成中...")
    messages = [
        {"role": "system", "content": SYSTEM_PLOT},
        {"role": "user",   "content": build_plot_message(genre, title)},
    ]
    for attempt in range(1, MAX_RETRIES + 1):
        raw = chat_json(messages, language=language)
        result = _parse(raw, language=language)
        if result and all(result.get(k) for k in ("ending", "protagonist", "characters", "climax")):
            if language == "en":
                system_print("Plot generation complete")
            else:
                system_print("プロット生成完了")
            _warn_missing_keys(result, language=language)
            return result
        if attempt < MAX_RETRIES:
            missing = [k for k in ("ending", "protagonist", "characters", "climax") if not result.get(k)] if result else ["parse"]
            if language == "en":
                system_print(f"Retrying... ({attempt}/{MAX_RETRIES}) Missing: {', '.join(missing)}")
            else:
                system_print(f"再試行中... ({attempt}/{MAX_RETRIES}) 不足: {', '.join(missing)}")
    if language == "en":
        system_print("Plot generation failed. Continuing without plot.")
    else:
        system_print("プロット生成に失敗しました。プロットなしで続行します。")
    return {}

def _parse(raw: str, language: str = "ja") -> dict:
    if raw.startswith("[ERROR"):
        if language == "en":
            system_print("An error occurred during plot generation")
        else:
            system_print("プロット生成中にエラーが発生しました")
        return {}

    cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip()
    cleaned = re.sub(r"```", "", cleaned).strip()

    # First attempt standard JSON parsing
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return _validate_and_repair(result)
    except json.JSONDecodeError:
        pass

    # If that fails, attempt auto-repair for minor syntax errors
    # (missing quotes, trailing commas, etc.)
    try:
        repaired = repair_json(cleaned)
        result = json.loads(repaired)
        if isinstance(result, dict):
            return _validate_and_repair(result)
    except Exception:
        pass

    if language == "en":
        system_print("Failed to parse plot JSON")
    else:
        system_print("プロットのJSON解析に失敗しました")
    return {}


# Keys that may be nested inside choices elements
_NESTED_KEYS = ("misconceptions", "failures", "twists", "conflicts", "climax", "characters")

_REQUIRED_KEYS = ("ending", "protagonist", "characters", "climax")

def _warn_missing_keys(plot: dict, language: str = "ja") -> None:
    """Warn if any required plot key is empty or missing."""
    for key in _REQUIRED_KEYS:
        val = plot.get(key)
        if not val:
            if language == "en":
                system_print(f"[Warning] Required plot key '{key}' is empty. Story progression may be affected.")
            else:
                system_print(f"[警告] プロットの必須キー「{key}」が空です。物語の進行に影響する可能性があります。")


def _validate_and_repair(plot: dict) -> dict:
    """
    If beat keys are nested inside choices elements, lift them to the top level
    and repair the plot structure.
    """
    _TOP_LEVEL_LIST_KEYS = ("misconceptions", "failures", "choices", "twists", "characters")

    extracted: dict[str, list] = {k: [] for k in _NESTED_KEYS}
    repaired = False

    choices = plot.get("choices", [])
    clean_choices = []
    for item in choices:
        if not isinstance(item, dict):
            continue
        nested_found = False
        for key in _NESTED_KEYS:
            if key in item and isinstance(item[key], list):
                extracted[key].extend(item[key])
                nested_found = True
        # Check whether any valid choice keys remain
        valid_keys = {"description", "cost", "timing", "outcome", "label", "name", "content"}
        has_valid = any(k in item for k in valid_keys)
        if has_valid:
            # Keep a clean choice entry with nested keys removed
            clean_item = {k: v for k, v in item.items() if k not in _NESTED_KEYS}
            clean_choices.append(clean_item)
        if nested_found:
            repaired = True

    if repaired:
        plot["choices"] = clean_choices
        for key in _NESTED_KEYS:
            if extracted[key]:
                existing = plot.get(key, [])
                if not isinstance(existing, list):
                    existing = []
                plot[key] = existing + extracted[key]
                if DEBUG_MODE:
                    print(f"[plot repair] Moved {len(extracted[key])} {key} item(s) to top level", file=sys.stderr)

    # Convert protagonist to a dict if it is a string or other non-dict type
    if not isinstance(plot.get("protagonist"), dict):
        raw_prot = plot.get("protagonist", "")
        plot["protagonist"] = {"name": str(raw_prot) if raw_prot else "", "wound": "", "goal_surface": "", "goal_deep": ""}

    # Normalize each characters entry to a dict (wrap non-dict values)
    chars = plot.get("characters", [])
    if isinstance(chars, list):
        plot["characters"] = [c if isinstance(c, dict) else {"name": str(c)} for c in chars]

    # Reset list-type fields to empty list if they are not a list
    for list_key in ("misconceptions", "failures", "twists", "choices"):
        val = plot.get(list_key)
        if val is not None and not isinstance(val, list):
            plot[list_key] = []
        elif isinstance(val, list):
            # Exclude elements that are not dicts
            plot[list_key] = [item for item in val if isinstance(item, dict)]

    # Fill in missing climax / ending / ending_note fields
    if not isinstance(plot.get("climax"), dict):
        plot["climax"] = {}
    climax = plot["climax"]
    # If all climax fields are empty, fill in minimal values from other plot data
    if not any(climax.get(k) for k in ("setting", "conflict_type", "loss", "gain", "peak")):
        protagonist = plot.get("protagonist", {})
        conflicts = plot.get("conflicts", [])
        twists = plot.get("twists", [])
        risks = plot.get("risks", {})
        main_conflict = next((c.get("content", "") for c in conflicts if isinstance(c, dict) and c.get("type") in ("main", "メイン")), "")
        final_twist = twists[-1].get("content", "") if twists and isinstance(twists[-1], dict) else ""
        climax["setting"] = climax.get("setting") or "story climax"
        climax["conflict_type"] = climax.get("conflict_type") or main_conflict or "resolution of the main conflict"
        climax["loss"] = climax.get("loss") or main_conflict or ""
        climax["gain"] = climax.get("gain") or protagonist.get("goal_surface") or ""
        climax["peak"] = climax.get("peak") or final_twist or "story turning point"
        plot["climax"] = climax
        if DEBUG_MODE:
            print("[plot repair] climax was empty; filled from other fields", file=sys.stderr)
    if not plot.get("ending"):
        plot["ending"] = ""
        if DEBUG_MODE:
            print("[plot repair] ending was missing; set to default", file=sys.stderr)
    if not isinstance(plot.get("ending_note"), dict) or not plot["ending_note"]:
        plot["ending_note"] = {"hook_resolution": "", "theme_closure": ""}
        if DEBUG_MODE:
            print("[plot repair] ending_note was missing; set to default", file=sys.stderr)

    return plot
