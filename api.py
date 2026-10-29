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
        err = str(e)
        if "exceed_context_size_error" in err or "exceeds the available context size" in err:
            return "[CONTEXT_LIMIT]"
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


def extract_protagonist_name(opening_scene: str) -> str:
    """improvモード用: GMが生成した開始シーンから主人公名を抽出する。
    名前が不明な場合は空文字を返す。
    """
    prompt = (
        f"以下はテキストRPGの冒頭シーンです。\n\n"
        f"{opening_scene}\n\n"
        f"このシーンでプレイヤーが操作する主人公の名前を1つだけ答えてください。\n"
        f"名前が明示されていない場合は「主人公」と答えてください。\n"
        f"名前のみを出力してください。説明・句読点・括弧は不要です。"
    )
    messages = [
        {"role": "system", "content": "あなたは小説の登場人物を識別するアシスタントです。"},
        {"role": "user", "content": prompt},
    ]
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=16,
            temperature=0.0,
        )
        name = response.choices[0].message.content.strip()
        # 余分な記号・改行を除去
        import re as _re
        name = _re.sub(r'[「」『』【】\(\)（）\n]', '', name).strip()
        return name if name else ""
    except Exception:
        return ""


def check_turning_point(recent_history: list[dict], action: str) -> bool:
    """improvモード用: 直近の履歴とプレイヤー行動が物語の大きな転換点かを判定する。
    LLMにyes/noで答えさせる。エラー時はFalseを返す（安全側に倒す）。
    """
    # 直近5ターン分のassistantメッセージ（GM描写）を取得
    gm_msgs = [m["content"][:300] for m in recent_history if m["role"] == "assistant"][-5:]
    history_text = "\n".join(f"- {t}" for t in gm_msgs) if gm_msgs else "（なし）"
    prompt = (
        f"以下はテキストRPGの直近のGM描写です。\n\n"
        f"{history_text}\n\n"
        f"プレイヤーの行動: {action}\n\n"
        f"このプレイヤーの行動が、物語全体を通じて最も重要な瞬間の一つですか？\n"
        f"以下のいずれかに該当する場合のみ「yes」：\n"
        f"・登場人物の関係・状況が不可逆に変化する\n"
        f"・隠されていた事実・真実が明らかになる\n"
        f"・物語の方向性を決定的に変える選択・衝突・結末が起きる\n"
        f"それ以外（探索・移動・会話・情報収集・日常的な行動・小さな成否）は「no」。\n"
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


GM_CHAR_PROMPTS = {
    "cynical": (
        "あなたはテキストRPGのGMで、シニカルな性格のキャラクターです。\n"
        "プレイヤーの行動の具体的な内容に触れて、斜に構えた一言コメントをしてください。\n"
        "15字以内の一言のみ。説明・句読点・改行は最小限。"
    ),
}

GM_CHAR_LABELS = {
    "cynical": "シニカル",
}


def generate_gm_char_comment(action: str, recent_history: list[dict], character: str, gm_char_log: list[dict] | None = None) -> str:
    """GMキャラクターの一言コメントを生成する。
    character: "tsukkomi" / "cynical" / "worrier"
    gm_char_log: これまでの全コメント履歴（繰り返し抑止用）
    エラー時は空文字を返す。
    """
    sys_prompt = GM_CHAR_PROMPTS.get(character)
    if not sys_prompt:
        return ""
    # 直近3ターンのGM描写を参考として渡す
    gm_msgs = [m["content"][:100] for m in recent_history if m["role"] == "assistant"][-3:]
    context = "\n".join(f"- {t}" for t in gm_msgs) if gm_msgs else ""
    # これまでの全コメント（繰り返し抑止）
    past_comments = ""
    if gm_char_log:
        comments = [entry["comment"] for entry in gm_char_log if "comment" in entry]
        if comments:
            past_comments = "【これまでに使ったコメント（語尾・語法のパターンを読み取り、同じパターンを繰り返さないこと）】\n" + "\n".join(f"- {c}" for c in comments) + "\n\n"
    user_content = f"{past_comments}直近の状況:\n{context}\n\nプレイヤーの行動: {action}" if context else f"{past_comments}プレイヤーの行動: {action}"
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        client = get_client()
        response = client.chat.completions.create(
            model="local",
            messages=messages,
            max_tokens=32,
            temperature=0.9,
        )
        comment = response.choices[0].message.content.strip()
        # 複数行になった場合は1行目のみ
        comment = comment.split("\n")[0].strip()
        # 長すぎる場合は切り捨て
        if len(comment) > 30:
            comment = comment[:30]
        return comment
    except Exception:
        return ""


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
