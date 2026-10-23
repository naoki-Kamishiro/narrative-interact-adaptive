from openai import OpenAI
import threading
import time
from config import LM_STUDIO_URL, API_KEY, MAX_TOKENS, TEMPERATURE

PLAYER_URL = LM_STUDIO_URL  # GMと同じポートを使用（同一モデルでGM・プレイヤー兼用）

_client: OpenAI | None = None
_player_client: OpenAI | None = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LM_STUDIO_URL, api_key=API_KEY)
    return _client

def get_player_client() -> OpenAI:
    global _player_client
    if _player_client is None:
        _player_client = OpenAI(base_url=PLAYER_URL, api_key=API_KEY)
    return _player_client

def _show_progress(stop_event: threading.Event) -> None:
    """生成中にドットを表示するスレッド関数。"""
    import sys
    chars = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    i = 0
    while not stop_event.is_set():
        sys.stdout.write(f"\r生成中 {chars[i % len(chars)]}")
        sys.stdout.flush()
        i += 1
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * 20 + "\r")
    sys.stdout.flush()

def chat(messages: list) -> str:
    stop_event = threading.Event()
    t = threading.Thread(target=_show_progress, args=(stop_event,), daemon=True)
    t.start()
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[ERROR: {e}]"
    finally:
        stop_event.set()
        t.join()

def chat_player(gm_response: str, system_prompt: str, recent_actions: list | None = None) -> str:
    """プレイヤーLLMにGM応答を渡して行動を生成する（自動プレイ用）。
    recent_actions: 直近のプレイヤー行動リスト（ループ抑止用）。"""
    user_content = gm_response
    if recent_actions:
        actions_text = "\n".join(f"  - {a}" for a in recent_actions)
        user_content = (
            f"【直近の自分の行動（繰り返し禁止の参考に）】\n{actions_text}\n\n"
            f"【現在の状況】\n{gm_response}"
        )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]
    try:
        client = get_player_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=200,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[ERROR: {e}]"


def generate_genre_title(genre: str = "") -> dict:
    """バッチモード用: LLMにタイトルを生成させる。
    genre: ジャンル（指定された場合はそのジャンルのタイトルのみ生成）。
    戻り値: {"genre": "...", "title": "..."} または {"error": "..."}
    """
    if genre:
        prompt = (
            f"インタラクティブフィクション（テキストRPG）のタイトルを1つ考えてください。\n"
            f"ジャンル：{genre}\n"
            "タイトルは物語の雰囲気を持つ短い日本語タイトルにしてください。\n"
            "以下のJSON形式のみで出力してください。説明や前置きは不要です。\n"
            f'{{"genre": "{genre}", "title": "タイトル"}}'
        )
    else:
        prompt = (
            "インタラクティブフィクション（テキストRPG）のジャンルとタイトルを1つ考えてください。\n"
            "ジャンルの例：ミステリー、ファンタジー、ホラー、SF、日常、時代劇、群像劇など。\n"
            "タイトルは物語の雰囲気を持つ短い日本語タイトルにしてください。\n"
            "以下のJSON形式のみで出力してください。説明や前置きは不要です。\n"
            '{"genre": "ジャンル名", "title": "タイトル"}'
        )
    messages = [
        {"role": "system", "content": "あなたは創作のアイデアを提案するアシスタントです。"},
        {"role": "user", "content": prompt},
    ]
    import json as _json
    import re as _re
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=128,
            temperature=0.9,
        )
        raw = response.choices[0].message.content.strip()
        # JSONブロックを抽出
        m = _re.search(r'\{.*?\}', raw, _re.DOTALL)
        if m:
            return _json.loads(m.group())
        return {"error": f"JSON not found in response: {raw}"}
    except Exception as e:
        return {"error": str(e)}


def check_fixation(actions: list[str]) -> bool:
    """直近3件のプレイヤー行動が物語を前進させずに同じ状況に留まり続けているか判定する。
    LLMにyes/noで答えさせる。エラー時はFalseを返す（安全側に倒す）。
    """
    if len(actions) < 3:
        return False
    actions_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
    prompt = (
        f"以下はテキストRPGのプレイヤーの直近3つの行動です。\n\n"
        f"{actions_text}\n\n"
        f"判定してください：これらの行動は物語を前進させる変化を生んでいますか？それとも同じ状況・場所・対象に留まり続けていますか？\n"
        f"※異なる対象への操作、道具の一連の使用（取る→使う→置く等）、場所の移動は「前進」です。\n"
        f"※同じ対象を繰り返し凝視・触る・試みるだけで新しい状況が生まれていない場合は「停滞」です。\n"
        f"停滞している場合は「yes」、前進している場合は「no」を1単語のみで答えてください。"
    )
    messages = [
        {"role": "system", "content": "あなたはテキストRPGの進行を補助するシステムです。"},
        {"role": "user", "content": prompt},
    ]
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=4,
            temperature=0.0,
        )
        answer = response.choices[0].message.content.strip().lower()
        return answer.startswith("yes")
    except Exception:
        return False


def check_deviation(actions: list[str], plot_keywords: list[str]) -> bool:
    """直近3件のプレイヤー行動が元プロットから大きく逸脱しているか判定する。
    LLMにyes/noで答えさせる。エラー時はFalseを返す（安全側に倒す）。
    """
    if len(actions) < 3:
        return False
    actions_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(actions))
    keywords_text = "、".join(plot_keywords) if plot_keywords else "（なし）"
    prompt = (
        f"以下はテキストRPGのプレイヤーの直近3つの行動です。\n\n"
        f"{actions_text}\n\n"
        f"このゲームの元の物語の中心要素: {keywords_text}\n\n"
        f"これらの行動は、元の物語の中心要素から大きく逸脱し、"
        f"物語が別の方向に進んでいますか？\n"
        f"「yes」か「no」の1単語のみで答えてください。"
    )
    messages = [
        {"role": "system", "content": "あなたはテキストRPGの進行を補助するシステムです。"},
        {"role": "user", "content": prompt},
    ]
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=4,
            temperature=0.0,
        )
        answer = response.choices[0].message.content.strip().lower()
        return answer.startswith("yes")
    except Exception:
        return False


def regenerate_plot(recent_history: list[dict], genre: str) -> str:
    """直近の会話履歴をもとに新しいプロットをJSONで生成する（adaptive用）。
    recent_history: 直近Nターン分のuser/assistantメッセージ（systemは除く）。
    genre: 元のジャンル（参考情報として渡す。新ジャンルになってもよい）。
    戻り値: JSON文字列（パース失敗の場合は空文字列）。
    """
    # 履歴を読みやすい形式に変換
    history_text = ""
    for m in recent_history:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            # ダイス結果タグを除いて1行目のみ
            first_line = content.split("\n")[0].strip()
            if first_line and not first_line.startswith("（"):
                history_text += f"プレイヤー: {first_line}\n"
        elif role == "assistant":
            # 長い場合は最初の200文字
            short = content[:200].replace("\n", " ")
            history_text += f"GM: {short}\n"

    prompt = (
        f"以下は進行中のテキストRPGの直近の展開です。\n\n"
        f"{history_text}\n\n"
        f"この展開を踏まえて、これから10ターン程度で完結できる物語の着地点を設計してください。\n"
        f"ジャンルは変わっても構いません（現在の流れに合わせてください）。\n"
        f"以下のJSON形式のみで出力してください。説明や前置きは不要です。\n"
        f"コードブロック（```）を使わないこと。\n\n"
        f'{{\n'
        f'  "new_genre": "現在の流れに合ったジャンル名",\n'
        f'  "protagonist_goal": "主人公が今向かっている目標（具体的な行動・状況で）",\n'
        f'  "key_npc": "この物語で重要になるNPC名と役割",\n'
        f'  "climax_situation": "クライマックスで起きる具体的な出来事（場所・人物・行動）",\n'
        f'  "ending_scene": "最後の場面（主人公・人物・場所・動作のみ。動機語・感情語は禁止）",\n'
        f'  "beats": [\n'
        f'    {{"description": "序盤の展開（1〜2文）", "timing": "序盤"}},\n'
        f'    {{"description": "中盤の転換点（1〜2文）", "timing": "中盤"}},\n'
        f'    {{"description": "クライマックスへの布石（1〜2文）", "timing": "終盤"}}\n'
        f'  ]\n'
        f'}}'
    )
    messages = [
        {"role": "system", "content": "あなたは小説の物語設計者です。JSONのみ出力します。"},
        {"role": "user", "content": prompt},
    ]
    import json as _json
    import re as _re
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()
        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if m:
            parsed = _json.loads(m.group())
            return parsed
        return {}
    except Exception:
        return {}


def chat_json(messages: list) -> str:
    """JSON出力専用。プロット生成など内部処理用。"""
    stop_event = threading.Event()
    t = threading.Thread(target=_show_progress, args=(stop_event,), daemon=True)
    t.start()
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=4096,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[ERROR: {e}]"
    finally:
        stop_event.set()
        t.join()
