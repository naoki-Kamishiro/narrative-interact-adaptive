"""
Dice-roll judgment module.
Asks the LLM whether a player action requires a dice roll,
then rolls 1d20 and returns the result if needed.

Difficulty is not output directly by the LLM; instead, risk and uncertainty
are each classified as low/mid/high, and Python converts them to a numeric
difficulty deterministically — preventing action text length or complexity
from skewing the difficulty rating.
"""

import json
import random
import re
from api import chat_json

JUDGE_PROMPT = """\
プレイヤーの行動を受け取り、ダイス判定が必要かどうかを判断してください。

以下のいずれかに該当する場合のみ判定が必要：
・成否が物語を分岐させる行動
・能力・技術・運・交渉・修理・調査など不確実性がある行動
・プレイヤーが重要なリスクを取る行動
・隠された情報の発見・原因究明・証拠収集など目的達成を伴う観察行動

以下は判定不要（need_roll: false）：
・主人公が自らの死・自滅・降伏・放棄を明示的に選択する行動（「死ぬ」「諦める」「降参する」など）
・内面の状態・感情・決意・受容を指す行動（「覚悟を決める」「受け入れる」「気持ちを整理する」など。外から観察できる行動を伴わないもの）

行動の文章の長さや複雑さ・専門用語の多さで難しさを判断しないこと。
行動そのものの実質的な内容だけを見て判断すること。

以下のJSON形式のみで返答してください。それ以外の文字は含めないこと。

判定不要の場合：
{"need_roll": false}

判定必要の場合：
{"need_roll": true, "risk": "low|mid|high", "uncertainty": "low|mid|high", "reason": "判定理由を10文字以内で"}

risk: 失敗した場合の代償の重さ（low=軽い, mid=中程度, high=重大）
uncertainty: 行動の結果がどれだけ読みにくいか（low=ほぼ確実, mid=半々, high=非常に不確実）
"""

JUDGE_PROMPT_EN = """\
Evaluate the player's action and decide whether a dice roll is required.

A roll is required ONLY if the action meets one of these:
- Success/failure would branch the story in a meaningful way
- The action involves skill, luck, negotiation, repair, investigation, or other uncertainty
- The player is taking a significant risk
- The action is an observational attempt to discover hidden information or gather evidence

No roll required (need_roll: false) if:
- The protagonist explicitly chooses death, self-destruction, surrender, or abandonment
- The action describes only an internal state, emotion, resolve, or acceptance (not externally observable)

Do NOT judge by the length or complexity of the action text. Judge only by the actual content.

Reply ONLY in the following JSON format. No other text.

If no roll needed:
{"need_roll": false}

If roll needed:
{"need_roll": true, "risk": "low|mid|high", "uncertainty": "low|mid|high", "reason": "brief reason in 5 words or less"}

risk: severity of failure consequence (low=minor, mid=moderate, high=severe)
uncertainty: how unpredictable the outcome is (low=near-certain, mid=50-50, high=very uncertain)
"""

# Table for deterministically computing difficulty from risk/uncertainty combinations
_LEVEL_VALUE = {"low": -2, "mid": 0, "high": 2}
_BASE_DIFFICULTY = 7  # Baseline: ~65% success rate on d20

# Difficulty presets (offset added by player selection at startup)
DIFFICULTY_PRESETS = {
    "easy": -2,
    "normal": 0,
    "hard": 2,
}
_difficulty_offset = 0  # set from main.py at startup

def set_difficulty_preset(preset: str) -> None:
    """Set the difficulty preset at startup."""
    global _difficulty_offset
    _difficulty_offset = DIFFICULTY_PRESETS.get(preset, 0)

def roll_d20() -> int:
    return random.randint(1, 20)

def _determine_intensity(dice: int, difficulty: int) -> str:
    """Determine result intensity from the margin between roll and difficulty."""
    margin = dice - difficulty
    if margin >= 8:
        return "decisive"
    elif margin >= -6:
        return "normal"
    else:
        return "severe"

def _compute_difficulty(risk: str, uncertainty: str) -> int:
    """Deterministically compute difficulty from the risk and uncertainty axes."""
    risk_v = _LEVEL_VALUE.get(risk, 0)
    unc_v = _LEVEL_VALUE.get(uncertainty, 0)
    difficulty = _BASE_DIFFICULTY + risk_v + unc_v + _difficulty_offset
    return max(6, min(18, difficulty))

def judge(action: str, history: list, language: str = "ja") -> dict | None:
    # Pass the most recent GM response as context (improves situation-aware judgment)
    last_gm = next(
        (m["content"] for m in reversed(history) if m["role"] == "assistant"),
        None
    )
    if language == "en":
        prompt = JUDGE_PROMPT_EN
        context_line = f"\nCurrent situation (last GM description):\n{last_gm[:300]}\n\n" if last_gm else ""
        user_content = f"{context_line}Action: {action}"
    else:
        prompt = JUDGE_PROMPT
        context_line = f"\n現在の状況（直前のGM描写）:\n{last_gm[:300]}\n\n" if last_gm else ""
        user_content = f"{context_line}行動: {action}"
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]
    raw = chat_json(messages)

    if raw.startswith("[ERROR"):
        return {"error": True}

    try:
        cleaned = re.sub(r"```[a-z]*\n?", "", raw).strip()
        cleaned = re.sub(r"```", "", cleaned).strip()
        data = json.loads(cleaned)
    except Exception:
        return {"error": True}

    # If data is not a dict (e.g. array or string returned), treat as error
    if not isinstance(data, dict):
        return {"error": True}

    # Also treat string "false" as False for need_roll
    need_roll = data.get("need_roll", False)
    if isinstance(need_roll, str):
        need_roll = need_roll.lower() not in ("false", "0", "no", "")
    if not need_roll:
        return None

    risk = data.get("risk", "mid")
    uncertainty = data.get("uncertainty", "mid")
    reason = data.get("reason", "roll" if language == "en" else "判定")

    difficulty = _compute_difficulty(risk, uncertainty)
    dice = roll_d20()
    success = dice >= difficulty
    intensity = _determine_intensity(dice, difficulty)

    return {
        "dice": dice,
        "difficulty": difficulty,
        "reason": reason,
        "success": success,
        "intensity": intensity,
    }

def display_result(result: dict, language: str = "ja") -> None:
    """Display the dice roll result to the console."""
    if language == "en":
        outcome = "Success" if result["success"] else "Failure"
        intensity_label = {
            "decisive": " (Decisive)",
            "normal": "",
            "severe": " (Severe)",
        }.get(result.get("intensity", "normal"), "")
        print(f"🎲 Roll: {result['reason']} / DC {result['difficulty']} / Rolled {result['dice']} → {outcome}{intensity_label}")
    else:
        outcome = "成功" if result["success"] else "失敗"
        intensity_label = {
            "decisive": "（決定的）",
            "normal": "",
            "severe": "（重大）",
        }.get(result.get("intensity", "normal"), "")
        print(f"🎲 判定: {result['reason']} / 難易度{result['difficulty']} / 出目{result['dice']} → {outcome}{intensity_label}")

