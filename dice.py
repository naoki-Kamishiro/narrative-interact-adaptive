"""
ダイス判定モジュール。
行動がダイス判定を必要とするかをLLMに問い合わせ、
必要なら1d20を振って結果を返す。

難易度はLLMに直接数値を出させず、risk/uncertaintyの2軸を
low/mid/highで分類させ、Python側で決定論的に難易度へ変換する。
これにより、行動説明文の長さや複雑さに難易度が引きずられることを防ぐ。
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

# risk/uncertaintyの組み合わせから難易度を決定論的に算出するテーブル
_LEVEL_VALUE = {"low": -2, "mid": 0, "high": 2}
_BASE_DIFFICULTY = 7  # d20で約65%の成功率を基準にする

# 難易度プリセット（起動時のプレイヤー選択でオフセットを加える）
DIFFICULTY_PRESETS = {
    "easy": -2,
    "normal": 0,
    "hard": 2,
}
_difficulty_offset = 0  # main.pyから設定される

def set_difficulty_preset(preset: str) -> None:
    """起動時に難易度プリセットを設定する。"""
    global _difficulty_offset
    _difficulty_offset = DIFFICULTY_PRESETS.get(preset, 0)

def roll_d20() -> int:
    return random.randint(1, 20)

def _determine_intensity(dice: int, difficulty: int) -> str:
    """出目と難易度のマージンから結果の強度を判定する。"""
    margin = dice - difficulty
    if margin >= 8:
        return "decisive"
    elif margin >= -6:
        return "normal"
    else:
        return "severe"

def _compute_difficulty(risk: str, uncertainty: str) -> int:
    """risk/uncertaintyの2軸から難易度をローカルで決定論的に計算する。"""
    risk_v = _LEVEL_VALUE.get(risk, 0)
    unc_v = _LEVEL_VALUE.get(uncertainty, 0)
    difficulty = _BASE_DIFFICULTY + risk_v + unc_v + _difficulty_offset
    return max(6, min(18, difficulty))

def judge(action: str, history: list) -> dict | None:
    # 直近のGM応答を文脈として渡す（状況依存の判定精度向上のため）
    last_gm = next(
        (m["content"] for m in reversed(history) if m["role"] == "assistant"),
        None
    )
    context_line = f"\n現在の状況（直前のGM描写）:\n{last_gm[:300]}\n\n" if last_gm else ""
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"{context_line}行動: {action}"},
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

    # data が dict でない場合（配列や文字列で返ってきた場合）はエラー扱い
    if not isinstance(data, dict):
        return {"error": True}

    # need_roll が文字列 "false" の場合も False として扱う
    need_roll = data.get("need_roll", False)
    if isinstance(need_roll, str):
        need_roll = need_roll.lower() not in ("false", "0", "no", "")
    if not need_roll:
        return None

    risk = data.get("risk", "mid")
    uncertainty = data.get("uncertainty", "mid")
    reason = data.get("reason", "判定")

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

def display_result(result: dict) -> None:
    """ダイス結果をコンソールに表示する。"""
    outcome = "成功" if result["success"] else "失敗"
    intensity_label = {
        "decisive": "（決定的）",
        "normal": "",
        "severe": "（重大）",
    }.get(result.get("intensity", "normal"), "")
    print(f"🎲 判定: {result['reason']} / 難易度{result['difficulty']} / 出目{result['dice']} → {outcome}{intensity_label}")

