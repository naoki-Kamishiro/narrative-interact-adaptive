"""
ナラティブインタラクト（LM Studio版）
ジャンルとタイトルを入力するだけで物語が始まる。
"""

import sys
import json
import datetime
import state
import history as hist
import plot as plot_mod
import save as save_mod
from api import chat, chat_player, generate_genre_title, check_fixation
import random
from display import gm_print, system_print, error_print, hr
from prompt import build_start_message
import dice as dice_mod
import beat as beat_mod

COMMANDS = {
    "/save": "セーブ",
    "/load": "ロード",
    "/quit": "セーブせずに終了",
    "/hint": "行動候補を3〜4つ表示",
    "/retry": "直前のGM応答を再生成",
    "/r":    "直前のGM応答を再生成",
    "/help": "コマンド一覧",
    "/h":    "コマンド一覧",
}

ENDING_MARKER = "【エンディング】"

EPILOGUE_PROMPT = (
    "エピローグを200字程度で書いてください。"
    "（これはエピローグ専用の依頼です。「【エンディング】以降の描写禁止」ルールはエピローグには適用されません。）"
    "本編で生じた代償・損失（負傷・失った力・犠牲等）と主要人物の状態（生死・関係の変化等）のうち、"
    "本編で明示されたものを1〜2点、具体的な描写で回収すること。"
    "新しい出来事は起こさず、意味・テーマ・変化の総括や説明もせず、"
    "具体的な動作・場所・物・人物の状態のみで描写して余韻を残すこと。"
    "「和解」「解放」「平穏」「救済」「変化」「重圧」「呪縛」「受容」「移ろう」「置き換わる」"
    "など抽象語は使用しないこと。"
)

# 自動プレイモード（起動引数で設定）
AUTO_PLAY_MODE: str | None = None  # None=手動, "normal"=通常, "deviate"=逸脱

# デバッグモード（--debug引数で有効）
DEBUG_MODE: bool = False

# バッチ実行回数（--batch N で設定）
BATCH_COUNT: int = 0  # 0=通常, N=N回バッチ実行

# バッチ用ジャンルリスト
BATCH_GENRES = [
    "ホラー", "ミステリー", "ファンタジー", "SF",
    "時代劇", "現代ドラマ", "サスペンス", "青春",
    "怪談", "冒険", "犯罪", "日常",
]
_batch_genre_queue: list[str] = []  # シャッフル済みキュー

# バッチ用ダイス設定（開始前に1回だけ手入力）
BATCH_USE_DICE: bool = True
BATCH_DIFFICULTY: str = "normal"

PLAYER_SYSTEM_NORMAL = (
    "あなたはナラティブインタラクトシステムのプレイヤーです。\n"
    "GMから提示された文章をもとに行動を改行なしで出力します。\n"
    "主人公として臨機応変に行動してください。\n"
    "「」を使わず生テキストのみセリフではなく行動を出力してください。\n"
    "行動に心情は出力しない事。\n"
    "行動に余計な装飾はしない事。\n"
    "端的に行動を描写する事。\n"
    "行動をいくつも一度にしない事。\n"
    "直前と同じ対象・同じ動作の組み合わせを繰り返してはならない。\n"
    "同じ対象への行動が動詞を変えながら3回続いた場合も、別の対象・別の場所への行動に切り替えること。\n"
    "同じ場所で同種の行動が3回続いたら、別の場所へ移動する行動を取ること。\n"
    "同じ対象への行動が2回連続して失敗した場合は、その対象への行動をやめて別の対象・別の場所に切り替えること。\n"
    "失敗した目標・場所には固執せず、別の目標・別の場所への行動を優先すること。\n"
    "「覚悟を決める」「受け入れる」「気持ちを整理する」のような外から観察できない内面行動は出力しないこと。必ず身体・言葉・移動など外から見える行動で出力すること。\n"
    "物語の世界観に存在しないアイテム・道具・能力を行動に持ち込まないこと。\n"
    "エンディングと表示されたら終了してください。"
)

PLAYER_SYSTEM_DEVIATE = (
    "あなたはナラティブインタラクトシステムのプレイヤーです。\n"
    "GMから提示された文章をもとに行動を改行なしで出力します。\n"
    "主人公として、GMの意図した行動を敢えて避ける行動をしてください。\n"
    "「」を使わず生テキストのみセリフではなく行動を出力してください。\n"
    "行動に心情は出力しない事。\n"
    "行動に余計な装飾はしない事。\n"
    "端的に行動を描写する事。\n"
    "行動をいくつも一度にしない事。\n"
    "同じ対象への行動が動詞を変えながら3回続いた場合も、別の対象・別の場所への行動に切り替えること。\n"
    "エンディングと表示されたら終了してください。"
)

def show_help():
    hr()
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:<8} {desc}")
    hr()

def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        print("\n終了します。")
        sys.exit(0)
    except KeyboardInterrupt:
        print()
        return ""

def call_gm(messages: list, max_retries: int = 1) -> str:
    reply = chat(messages)
    attempt = 0
    while (reply.startswith("[ERROR") or not reply.strip()) and attempt < max_retries:
        system_print("応答生成に失敗したため再試行します...")
        reply = chat(messages)
        attempt += 1
    # 空応答はエラー扱いにする
    if not reply.strip():
        return "[ERROR: empty response]"
    if not reply.startswith("[ERROR"):
        reply = beat_mod.filter_output(reply)
        if ENDING_MARKER in reply:
            reply = reply.replace(ENDING_MARKER, "").strip()
            reply = reply + "\n" + ENDING_MARKER
        gm_print(reply)
    return reply


def _is_strong() -> bool:
    return state.get_plot_mode() == "strong"


def _get_recent_player_actions(history: list, n: int = 5) -> list[str]:
    """履歴からプレイヤー（user）の発言を直近n件取得する。
    開始メッセージ（先頭）・ダイスタグ・システム括弧行を除外し、各メッセージの1行目のみ返す。
    """
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    if user_msgs:
        user_msgs = user_msgs[1:]
    actions = []
    for msg in user_msgs:
        first_line = msg.split("\n")[0].strip()
        if first_line.startswith("（") or not first_line:
            continue
        actions.append(first_line)
    return actions[-n:] if actions else []


def _build_api_messages(h: list) -> list:
    """strongモードならビート注入版、それ以外は通常版でAPI用メッセージを返す。"""
    if _is_strong():
        s = state.get()
        queue = s.get("beat_queue", [])
        ptr = s.get("beat_ptr", 0)
        msgs, debug = hist.build_for_api_with_beat(h, queue, ptr)
        if debug:
            if DEBUG_MODE:
                print(debug, file=sys.stderr)
        # キューが枯渇しており、まだエンディング促進をしていない場合
        queue_exhausted = queue and beat_mod.get_current_beat(queue, ptr) is None
        if not debug and queue_exhausted and not s.get("ending_prompted", False):
            plot = s.get("plot", {})
            climax_setting = plot.get("climax", {}).get("setting", "")
            ending = plot.get("ending", "")
            if climax_setting and ending:
                injection = (
                    f"全てのプロット要素が出揃いました。"
                    f"クライマックスの舞台「{climax_setting}」と着地点「{ending}」に向けて、"
                    f"プレイヤーの行動に応じて物語を一歩進めてください。"
                    f"物語が自然に完結した場合は、最後の1行に「【エンディング】」とのみ出力すること。"
                )
            else:
                injection = "全てのプロット要素が出揃いました。プレイヤーの行動に応じて物語を自然な完結へ向けて一歩進めてください。完結した場合は最後の1行に「【エンディング】」とのみ出力してください。"
            msgs = [dict(m) for m in msgs]
            for i in reversed(range(len(msgs))):
                if msgs[i]["role"] == "user":
                    msgs[i] = dict(msgs[i])
                    msgs[i]["content"] = msgs[i]["content"] + f"\n（GMへの場面指示: {injection}）"
                    break
            state.update({"ending_prompted": True, "post_prompt_count": 0})
            if DEBUG_MODE:
                print("[BEAT] queue exhausted: injecting ending prompt", file=sys.stderr)
        # ending_prompted後も毎ターンinjectionを強化してGMに圧力をかける
        elif not debug and queue_exhausted and s.get("ending_prompted", False):
            post_count = s.get("post_prompt_count", 0)
            post_count += 1
            state.update({"post_prompt_count": post_count})
            plot = s.get("plot", {})
            climax_setting = plot.get("climax", {}).get("setting", "")
            ending = plot.get("ending", "")
            if post_count >= 2:
                # 2ターン目以降は強制モード
                if climax_setting and ending:
                    injection = (
                        f"【必須】このターンで物語を完結させてください。"
                        f"プレイヤーが何をしようとも、着地点「{ending}」の結末を迎えます。"
                        f"新たな障壁や展開を追加せず、必ずこのターンで締めくくること。"
                        f"最後の1行に必ず「【エンディング】」とのみ出力してください。"
                    )
                else:
                    injection = "【必須】このターンで物語を完結させてください。新たな展開を追加せず、このターンで必ず締めくくること。最後の1行に必ず「【エンディング】」とのみ出力してください。"
            else:
                # 1ターン目は緩めの再促進
                if climax_setting and ending:
                    injection = (
                        f"着地点「{ending}」に向けて、物語をクロージングへ導いてください。"
                        f"完結した場合は最後の1行に「【エンディング】」とのみ出力すること。"
                    )
                else:
                    injection = "物語をクロージングへ導いてください。完結した場合は最後の1行に「【エンディング】」とのみ出力してください。"
            msgs = [dict(m) for m in msgs]
            for i in reversed(range(len(msgs))):
                if msgs[i]["role"] == "user":
                    msgs[i] = dict(msgs[i])
                    msgs[i]["content"] = msgs[i]["content"] + f"\n（GMへの場面指示: {injection}）"
                    break
            if DEBUG_MODE:
                print(f"[BEAT] post-ending injection (turn {post_count})", file=sys.stderr)
        return msgs
    # off/on/improvモード・自動プレイ時のみ: 固執ループ検出→エンディング強制injection
    if not _is_strong() and AUTO_PLAY_MODE:
        recent = _get_recent_player_actions(h, n=3)
        if len(recent) >= 3 and check_fixation(recent):
            s = state.get()
            fixation_count = s.get("fixation_count", 0) + 1
            state.update({"fixation_count": fixation_count})
            msgs = list(hist.build_for_api(h))
            if fixation_count >= 2:
                injection = (
                    "プレイヤーが同一対象への行動を繰り返しループしている。"
                    "その固執の結末（失敗・消耗・状況の収束）を描写し、このターンでエンディングに導くこと。"
                    "着地点の文は使わず、現在の状況から自然に導かれる結末を書くこと。"
                    "最後の1行に「【エンディング】」とのみ出力すること。"
                )
                state.update({"fixation_ending": True})
            else:
                injection = (
                    "プレイヤーの行動が同じ対象に集中している。"
                    "物語を収束に向けて進めてください。"
                )
            for i in reversed(range(len(msgs))):
                if msgs[i]["role"] == "user":
                    msgs[i] = dict(msgs[i])
                    msgs[i]["content"] += f"\n（GMへの場面指示: {injection}）"
                    break
            if DEBUG_MODE:
                print(f"[FIXATION] count={fixation_count}: injecting {'ending' if fixation_count >= 2 else 'soft'} prompt", file=sys.stderr)
            return msgs
        else:
            # ループ解消されたらカウントリセット
            state.update({"fixation_count": 0})
    return hist.build_for_api(h)


def _after_reply(reply: str) -> None:
    """strongモード: GM応答後にビートポインタを進める。"""
    if not _is_strong():
        return
    s = state.get()
    queue = s.get("beat_queue", [])
    ptr = s.get("beat_ptr", 0)
    queue, ptr = beat_mod.advance(queue, ptr, reply)
    state.update({"beat_queue": queue, "beat_ptr": ptr})


def _build_user_msg(action: str, dice_result: dict | None) -> str:
    """userメッセージを構築する。ダイス結果を冒頭に置き、行動テキストをその後に。"""
    if not dice_result:
        return action

    outcome = "成功" if dice_result["success"] else "失敗"
    intensity = dice_result.get("intensity", "normal")
    reason = dice_result.get("reason", "判定")
    diff = dice_result["difficulty"]
    roll = dice_result["dice"]

    if dice_result["success"] and intensity == "decisive":
        inst = (
            "決定的な成功として描写すること。"
            "行動の目的を大きく前進させる具体的な結果を示す。"
            "成功を無効化・矮小化しない。"
        )
    elif dice_result["success"]:
        inst = (
            "成功として状況が一歩前進したとして描写すること。"
            "成功を無効化・矮小化しない。"
        )
    elif intensity == "severe":
        inst = (
            "重大な失敗として描写すること。目的は達成できない。"
            "次の行動で対処可能な小規模な障害を最大1つ発生させる。"
            "失敗を成功に近い描写にしてはならない。"
        )
    else:
        inst = (
            "失敗として行動が不成立に終わったとして描写すること。"
            "失敗した事実を明確にした上で、場面内に存在する別の対象・別のアプローチ・別の人物・音・光など、"
            "プレイヤーが次に取れる具体的な行動起点を少なくとも一つ描写に含めること。"
            "失敗を成功に近い描写にしてはならない。"
        )

    tag = (
        f"（判定結果: {reason} / 難易度{diff} / 出目{roll} → {outcome}。"
        f"{inst}"
        f"判定結果を受けてから、その結果に整合する物語を構築すること。"
        f"判定結果を地の文に出力しないこと。）"
    )
    return f"{action}\n{tag}"




def check_ending(reply: str) -> bool:
    return ENDING_MARKER in reply

PLOT_MODE_LABELS = {
    "1": ("off", "プロット参照・自由"),
    "2": ("on", "プロット参照・緩拘束"),
    "3": ("strong", "プロット参照・強拘束"),
    "4": ("improv", "プロットなし・即興"),
}

def ask_plot_mode() -> str:
    exp_note = "（実験的）（40ターンで強制終了する場合あり）"
    print()
    print("物語の軸:")
    print(f"  1. プロット参照・自由{exp_note}")
    print(f"  2. プロット参照・緩拘束（プロットに添うが逸脱プレイ可能）{exp_note}")
    print("  3. プロット参照・強拘束（プロット強制回収）★初めてならこれを推奨")
    print(f"  4. プロットなし・即興{exp_note}")
    while True:
        choice = ask("選択 [1/2/3/4]: ")
        if choice in PLOT_MODE_LABELS:
            mode, label = PLOT_MODE_LABELS[choice]
            system_print(f"物語の軸: {label}")
            return mode
        system_print("1〜4のいずれかを入力してください。")

def ask_use_dice() -> bool:
    print()
    ans = ask("ダイス判定を使いますか？ [Y/n]: ")
    use_dice = ans.lower() != "n"
    system_print(f"ダイス判定: {'使う' if use_dice else '使わない'}")
    return use_dice

DIFFICULTY_LABELS = {
    "1": ("easy", "易しい"),
    "2": ("normal", "標準"),
    "3": ("hard", "厳しい"),
}

def ask_difficulty() -> str:
    print()
    print("難易度:")
    print("  1. 易しい")
    print("  2. 標準（おすすめ）")
    print("  3. 厳しい")
    while True:
        choice = ask("選択 [1/2/3]: ")
        if choice in DIFFICULTY_LABELS:
            preset, label = DIFFICULTY_LABELS[choice]
            system_print(f"難易度: {label}")
            return preset
        system_print("1〜3のいずれかを入力してください。")

def start_new_game() -> tuple[list, str, str]:
    while not (genre := ask("ジャンル: ").strip()):
        system_print("ジャンルを入力してください。")
    while not (title := ask("タイトル: ").strip()):
        system_print("タイトルを入力してください。")
    plot_mode = ask_plot_mode()
    use_dice = ask_use_dice()
    if use_dice:
        difficulty_preset = ask_difficulty()
        dice_mod.set_difficulty_preset(difficulty_preset)
    else:
        difficulty_preset = "normal"

    if plot_mode == "improv":
        system_print("プロット生成なし")
        plot = {}
    else:
        plot = plot_mod.generate(genre, title)

    state.init(genre, title, plot, plot_mode)
    state.update({"use_dice": use_dice, "difficulty_preset": difficulty_preset,
                  "auto_play_mode": AUTO_PLAY_MODE or "manual"})

    if plot_mode == "strong" and plot:
        queue = beat_mod.build_queue(plot)
        state.update({"beat_queue": queue, "beat_ptr": 0, "ending_suppressed": False, "ending_prompted": False})
        if DEBUG_MODE:
            print(f"[BEAT] queue built: {len(queue)} beats", file=sys.stderr)

    h = hist.new_history(plot, plot_mode, genre)
    start_msg = build_start_message(genre, title, plot)
    h = hist.add_user(h, start_msg)

    print()
    print(f"── 「{title}」 開始 ──")
    protagonist = plot.get("protagonist", {}) if plot else {}
    if protagonist.get("name"):
        name = protagonist["name"]
        print(f"あなたは{name}として、この物語を紡ぎます。")
        print()
    system_print("行き詰まったら /hint で行動候補を表示できます。")
    print()

    reply = call_gm(_build_api_messages(h))
    if reply.startswith("[ERROR"):
        error_print("応答生成に失敗しました。/retryで再試行できます。")
        # 自動プレイ時: エラー文字列がプレイヤーLLMに渡らないよう空文字にする
        initial_reply_for_player = ""
    else:
        h = hist.add_assistant(h, reply)
        _after_reply(reply)
        initial_reply_for_player = reply

    return h, genre, title, initial_reply_for_player

def _print_history(h: list) -> None:
    """履歴を順番に表示する。systemメッセージとダイス結果タグは除外。"""
    for m in h:
        if m["role"] == "system":
            continue
        content = m["content"]
        if m["role"] == "assistant":
            gm_print(content)
        elif m["role"] == "user":
            # ダイス結果タグ（判定結果: ...）を除いてプレイヤー行動のみ表示
            # タグ付きの場合、最初の行がプレイヤー入力
            action_line = content.split("\n")[0]
            # （ ...） で始まるシステム挿入メッセージは表示しない
            if not action_line.startswith("（"):
                print(f"\nあなたの行動: {action_line}")

def resume_game() -> tuple[list, str, str] | None:
    s, h = save_mod.load()
    if not s or not h:
        system_print("セーブデータが見つかりません。")
        return None
    state.load_from(s)
    plot = s.get("plot", {})
    plot_mode = s.get("plot_mode", "off")
    dice_mod.set_difficulty_preset(s.get("difficulty_preset", "normal"))

    # 旧セーブにbeat_queueがない場合は再構築
    if plot_mode == "strong" and plot and not s.get("beat_queue"):
        queue = beat_mod.build_queue(plot)
        state.update({"beat_queue": queue, "beat_ptr": 0, "ending_suppressed": False, "ending_prompted": False})
        if DEBUG_MODE:
            print(f"[BEAT] queue rebuilt on load: {len(queue)} beats", file=sys.stderr)
    title = s.get("title", "")
    genre = s.get("genre", "")
    h = hist.rebuild_system(h, plot, plot_mode, genre)
    system_print(f"ロード完了: 「{title}」　履歴を表示します...")
    print()

    _print_history(h)

    return h, genre, title

def save_session_json(h: list, title: str) -> None:
    """AUTO_PLAYモード用: セッション全体をJSONで保存する。"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Windows/Linux共通で問題になる文字を全て除去
    import re as _re
    safe_title = _re.sub(r'[\\/:*?"<>|\s]', "_", title)
    safe_title = safe_title.strip("_") or "session"
    filename = f"{safe_title}_{timestamp}.json"
    data = {
        "state": state.get(),
        "history": h,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    system_print(f"セッションを保存しました: {filename}")

def handle_ending(h: list) -> tuple[list, bool]:
    """エンディング後の選択を処理する。戻り値は (履歴, 終了するか)。"""
    system_print("エンディングを迎えました。お疲れさまでした。")
    if AUTO_PLAY_MODE:
        end_reason = "fixation" if state.get().get("fixation_ending") else "ending"
        state.update({"end_reason": end_reason})
        # 自動プレイ時はエピローグを自動生成して終了
        h = hist.add_user(h, EPILOGUE_PROMPT)
        reply = call_gm(hist.build_for_api(h))
        if reply.startswith("[ERROR"):
            error_print("エピローグの生成に失敗しました。")
            h.pop()
        else:
            h = hist.add_assistant(h, reply)
        return h, True
    print("  1. 終了する")
    print("  2. エピローグを生成する")
    while True:
        ans = ask("選択 [1/2]: ")
        if ans == "1":
            return h, True
        if ans == "2":
            h = hist.add_user(h, EPILOGUE_PROMPT)
            reply = call_gm(hist.build_for_api(h))
            if reply.startswith("[ERROR"):
                error_print("エピローグの生成に失敗しました。")
                h.pop()
            else:
                h = hist.add_assistant(h, reply)
            return h, True
        system_print("1か2を入力してください。")

def push_user(h: list, content: str, replace_pending: bool) -> list:
    """userメッセージを追加する。replace_pending=Trueなら、エラーで未応答のまま
    残っている直前のuserメッセージを置き換える（放棄された行動として扱う）。"""
    if replace_pending and h and h[-1]["role"] == "user":
        h.pop()
    return hist.add_user(h, content)

def _pick_batch_genre() -> str:
    """バッチ用ジャンルキューから次のジャンルを取り出す。空になったら再シャッフル。"""
    global _batch_genre_queue
    if not _batch_genre_queue:
        _batch_genre_queue = random.sample(BATCH_GENRES, len(BATCH_GENRES))
    return _batch_genre_queue.pop(0)


def run_single_session(plot_mode: str) -> None:
    """バッチモード用: 1セッションを実行してセーブして終了する。
    plot_mode: あらかじめ選択済みの物語の軸。
    """
    global AUTO_PLAY_MODE, DEBUG_MODE

    # ジャンルをリストから選択し、タイトルのみLLMに生成させる
    genre = _pick_batch_genre()
    result = generate_genre_title(genre)
    if "error" in result:
        error_print(f"タイトル生成に失敗しました: {result['error']}")
        return
    title = result.get("title", "").strip()
    if not title:
        error_print(f"タイトルが空です: {result}")
        return

    system_print(f"ジャンル: {genre} / タイトル: 「{title}」")

    # バッチ用ダイス設定を適用
    dice_mod.set_difficulty_preset(BATCH_DIFFICULTY)
    difficulty_preset = BATCH_DIFFICULTY

    if plot_mode == "improv":
        system_print("プロット生成なし")
        plot = {}
    else:
        plot = plot_mod.generate(genre, title)

    state.init(genre, title, plot, plot_mode)
    state.update({"use_dice": BATCH_USE_DICE, "difficulty_preset": difficulty_preset,
                  "auto_play_mode": AUTO_PLAY_MODE or "manual"})

    if plot_mode == "strong" and plot:
        queue = beat_mod.build_queue(plot)
        state.update({"beat_queue": queue, "beat_ptr": 0, "ending_suppressed": False, "ending_prompted": False})
        if DEBUG_MODE:
            print(f"[BEAT] queue built: {len(queue)} beats", file=sys.stderr)

    h = hist.new_history(plot, plot_mode, genre)
    start_msg = build_start_message(genre, title, plot)
    h = hist.add_user(h, start_msg)

    print()
    print(f"── 「{title}」 開始 ──")
    protagonist = plot.get("protagonist", {}) if plot else {}
    if protagonist.get("name"):
        name = protagonist["name"]
        print(f"あなたは{name}として、この物語を紡ぎます。")
        print()

    reply = call_gm(_build_api_messages(h))
    if reply.startswith("[ERROR"):
        error_print("初回応答生成に失敗しました。このセッションをスキップします。")
        return
    h = hist.add_assistant(h, reply)
    _after_reply(reply)
    last_gm_reply = reply

    auto_play_turn = 0
    AUTO_PLAY_MAX_TURNS = 40

    while True:
        auto_play_turn += 1
        if auto_play_turn > AUTO_PLAY_MAX_TURNS:
            state.update({"end_reason": "turn_limit"})
            system_print(f"自動プレイのターン上限（{AUTO_PLAY_MAX_TURNS}ターン）に達しました。終了します。")
            save_session_json(h, title)
            break

        if not last_gm_reply:
            action = ""
        else:
            if _is_strong() and state.get().get("ending_prompted", False) and \
                    state.get().get("post_prompt_count", 0) >= 3:
                action = "（物語を終わらせてください）"
                print(f"\nあなたの行動: {action} [システム強制]")
            else:
                sys_prompt = PLAYER_SYSTEM_NORMAL if AUTO_PLAY_MODE == "normal" else PLAYER_SYSTEM_DEVIATE
                _plot = state.get().get("plot", {})
                _protagonist = _plot.get("protagonist", {}) if _plot else {}
                _pname = _protagonist.get("name", "") if _protagonist else ""
                if _pname:
                    sys_prompt = f"あなたが操作する主人公の名前は「{_pname}」です。他のキャラクターを操作しないこと。\n" + sys_prompt
                recent_actions = _get_recent_player_actions(h, n=5)
                # DEVIATEモードでは「繰り返し禁止の参考」を渡さない（行動抑制を避けるため）
                _ra = None if AUTO_PLAY_MODE == "deviate" else recent_actions
                action = chat_player(last_gm_reply, sys_prompt, _ra)
                if action.startswith("[ERROR"):
                    error_print(f"プレイヤーLLMエラー: {action}")
                    state.update({"end_reason": "player_error"})
                    save_session_json(h, title)
                    break
                print(f"\nあなたの行動: {action}")

        if not action:
            continue

        is_forced_ending = action.startswith("（物語を終わらせてください）")
        dice_result = dice_mod.judge(action, h) if (state.get().get("use_dice", True) and not is_forced_ending) else None
        if dice_result and dice_result.get("error"):
            error_print("ダイス判定に失敗しました。判定なしで続行します。")
            dice_result = None
        elif dice_result:
            dice_mod.display_result(dice_result)
        user_msg = _build_user_msg(action, dice_result)
        h = hist.add_user(h, user_msg)

        reply = call_gm(_build_api_messages(h))
        if reply.startswith("[ERROR"):
            error_print("応答生成に失敗しました。スキップして続行します。")
            h.pop()
            continue

        h = hist.add_assistant(h, reply)
        last_gm_reply = reply
        _after_reply(reply)

        if check_ending(reply):
            if _is_strong() and not state.get().get("ending_suppressed", False):
                s = state.get()
                queue = s.get("beat_queue", [])
                ptr = s.get("beat_ptr", 0)
                queue, ptr, suppressed = beat_mod.handle_ending_suppression(queue, ptr)
                if suppressed:
                    state.update({"beat_queue": queue, "beat_ptr": ptr, "ending_suppressed": True})
                    cleaned_reply = h[-1]["content"].replace(ENDING_MARKER, "").strip()
                    h[-1] = {"role": "assistant", "content": cleaned_reply}
                    last_gm_reply = cleaned_reply
                    continue

            h, _ = handle_ending(h)
            save_session_json(h, title)
            break


def main():
    global AUTO_PLAY_MODE, DEBUG_MODE, BATCH_COUNT
    if "--help" in sys.argv or "-h" in sys.argv:
        print("使い方: python main.py [オプション]")
        print()
        print("オプション:")
        print("  --normal         自動プレイ（通常）")
        print("  --deviate        自動プレイ（逸脱）")
        print("  --batch N        N回バッチ実行（--normal または --deviate と併用）")
        print("  --debug          デバッグ出力を有効化（stderrに出力）")
        print("  --help, -h       このヘルプを表示")
        sys.exit(0)

    if "--normal" in sys.argv:
        AUTO_PLAY_MODE = "normal"
    elif "--deviate" in sys.argv:
        AUTO_PLAY_MODE = "deviate"

    # --batch N の解析
    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        if idx + 1 < len(sys.argv):
            try:
                BATCH_COUNT = int(sys.argv[idx + 1])
            except ValueError:
                print("--batch の引数は整数で指定してください。")
                sys.exit(1)
        else:
            print("--batch の後に回数を指定してください。例: --batch 5")
            sys.exit(1)

    # 自動プレイ時は常にデバッグ有効
    if AUTO_PLAY_MODE or "--debug" in sys.argv:
        DEBUG_MODE = True
        beat_mod.DEBUG_MODE = True
        plot_mod.DEBUG_MODE = True

    print()
    print("╔══════════════════════════════════════════╗")
    print("║  ナラティブインタラクト (LM Studio版)    ║")
    print("╚══════════════════════════════════════════╝")
    if AUTO_PLAY_MODE:
        print(f"[自動プレイモード: {'通常' if AUTO_PLAY_MODE == 'normal' else '逸脱'}]")
    if BATCH_COUNT > 0:
        print(f"[バッチモード: {BATCH_COUNT}回実行]")
    print()
    print("コマンド一覧は /help または /h")
    print()

    # バッチモード
    if BATCH_COUNT > 0:
        if not AUTO_PLAY_MODE:
            print("--batch は --normal または --deviate と併用してください。")
            sys.exit(1)
        plot_mode = ask_plot_mode()
        print()
        # ダイス設定を1回だけ手入力
        global BATCH_USE_DICE, BATCH_DIFFICULTY
        BATCH_USE_DICE = ask_use_dice()
        if BATCH_USE_DICE:
            BATCH_DIFFICULTY = ask_difficulty()
            dice_mod.set_difficulty_preset(BATCH_DIFFICULTY)
        print()
        for i in range(BATCH_COUNT):
            print(f"═══ バッチ {i+1}/{BATCH_COUNT} ═══")
            run_single_session(plot_mode)
            print()
        system_print(f"バッチ実行完了: {BATCH_COUNT}回")
        return

    h, genre, title = None, "", ""

    if save_mod.exists():
        if AUTO_PLAY_MODE:
            save_mod.delete()
            system_print("自動プレイモード：セーブデータを削除して新規開始します。")
        else:
            s, _ = save_mod.load()
            saved_title = s.get("title", "") if s else ""
            system_print(f"セーブデータが見つかりました:「{saved_title}」")
            print("  1. 続きから始める")
            print("  2. 削除して新しく始める")
            while True:
                ans = ask("選択 [1/2]: ")
                if ans == "1":
                    result = resume_game()
                    if result:
                        h, genre, title = result
                        initial_reply = ""
                    break
                elif ans == "2":
                    save_mod.delete()
                    system_print("セーブデータを削除しました。")
                    break
                system_print("1か2を入力してください。")

    if h is None:
        h, genre, title, initial_reply = start_new_game()
        # 初回生成が失敗した場合（空文字）はpending_failedをTrueに
        pending_failed = (initial_reply == "")
    else:
        initial_reply = ""
        pending_failed = False

    last_gm_reply = initial_reply  # 自動プレイ用: 最後のGM応答（初回含む）
    auto_play_turn = 0  # 自動プレイのターンカウンタ
    AUTO_PLAY_MAX_TURNS = 40  # 自動プレイの最大ターン数

    while True:
        if AUTO_PLAY_MODE:
            # ターン上限チェック
            auto_play_turn += 1
            if auto_play_turn > AUTO_PLAY_MAX_TURNS:
                state.update({"end_reason": "turn_limit"})
                system_print(f"自動プレイのターン上限（{AUTO_PLAY_MAX_TURNS}ターン）に達しました。終了します。")
                if DEBUG_MODE:
                    save_session_json(h, title)
                break
            if not last_gm_reply:
                action = ""
            else:
                # ending_prompted後、一定ターンでプレイヤー入力を強制終了に切り替え
                if _is_strong() and state.get().get("ending_prompted", False) and \
                        state.get().get("post_prompt_count", 0) >= 3:
                    action = "（物語を終わらせてください）"
                    print(f"\nあなたの行動: {action} [システム強制]")
                else:
                    sys_prompt = PLAYER_SYSTEM_NORMAL if AUTO_PLAY_MODE == "normal" else PLAYER_SYSTEM_DEVIATE
                    # 主人公名をsys_promptに付加（キャラ誤操作防止）
                    _plot = state.get().get("plot", {})
                    _protagonist = _plot.get("protagonist", {}) if _plot else {}
                    _pname = _protagonist.get("name", "") if _protagonist else ""
                    if _pname:
                        sys_prompt = f"あなたが操作する主人公の名前は「{_pname}」です。他のキャラクターを操作しないこと。\n" + sys_prompt
                    recent_actions = _get_recent_player_actions(h, n=5)
                    # DEVIATEモードでは「繰り返し禁止の参考」を渡さない（行動抑制を避けるため）
                    _ra = None if AUTO_PLAY_MODE == "deviate" else recent_actions
                    action = chat_player(last_gm_reply, sys_prompt, _ra)
                    if action.startswith("[ERROR"):
                        error_print(f"プレイヤーLLMエラー: {action}")
                        state.update({"end_reason": "player_error"})
                        save_session_json(h, title)
                        break
                    print(f"\nあなたの行動: {action}")
        else:
            action = ask("\nあなたの行動: ")

        if not action:
            continue

        if action in ("/help", "/h"):
            show_help()
            continue

        if action == "/quit":
            print("終了します。")
            break

        if action == "/save":
            save_mod.save(state.get(), h)
            continue

        if action == "/load":
            result = resume_game()
            if result:
                h, genre, title = result
                pending_failed = False
            continue

        if action in ("/retry", "/r"):
            # 直前がassistantなら削除して再生成。直前がuser（エラーで未応答）なら
            # そのuserメッセージをそのまま再利用する。
            retrying_assistant = h and h[-1]["role"] == "assistant"
            if retrying_assistant:
                h.pop()
                # strongモード: 直前の_after_reply()で進んだptrを1つ戻す
                if _is_strong():
                    s = state.get()
                    ptr = s.get("beat_ptr", 0)
                    if ptr > 0:
                        new_ptr = ptr - 1
                        # 戻した位置のdoneをFalseに戻す
                        queue = s.get("beat_queue", [])
                        if new_ptr < len(queue) and queue[new_ptr]["done"]:
                            queue[new_ptr] = dict(queue[new_ptr])
                            queue[new_ptr]["done"] = False
                        state.update({"beat_ptr": new_ptr, "beat_queue": queue})
            reply = call_gm(_build_api_messages(h))
            if reply.startswith("[ERROR"):
                error_print("応答生成に失敗しました。/retryで再試行できます。")
                pending_failed = True
                continue
            pending_failed = False
            h = hist.add_assistant(h, reply)
            _after_reply(reply)
            if check_ending(reply):
                if _is_strong() and not state.get().get("ending_suppressed", False):
                    s = state.get()
                    queue = s.get("beat_queue", [])
                    ptr = s.get("beat_ptr", 0)
                    queue, ptr, suppressed = beat_mod.handle_ending_suppression(queue, ptr)
                    if suppressed:
                        state.update({"beat_queue": queue, "beat_ptr": ptr, "ending_suppressed": True})
                        cleaned_reply = h[-1]["content"].replace(ENDING_MARKER, "").strip()
                        h[-1] = {"role": "assistant", "content": cleaned_reply}
                        last_gm_reply = cleaned_reply
                        continue
                h, quit_ = handle_ending(h)
                if AUTO_PLAY_MODE or DEBUG_MODE:
                    save_session_json(h, title)
                if quit_:
                    break
            continue

        if action.startswith("/") and action not in COMMANDS:
            system_print(f"コマンドにありません: {action}　/help で一覧を確認できます。")
            continue


        if action == "/hint":
            hint_base = hist.build_for_api(h)
            # 最後がuserメッセージ（エラーで未応答）の場合は重複を避けるため削除してから追加
            if hint_base and hint_base[-1]["role"] == "user":
                hint_base = hint_base[:-1]
            # 最後がassistantでない場合（空履歴等）はhintが出せないのでスキップ
            if not hint_base or hint_base[-1]["role"] != "assistant":
                system_print("ヒントを表示するには最初のGM描写が必要です。")
                continue
            hint_msg = hint_base + [{
                "role": "user",
                "content": "今の状況でプレイヤーが取れる行動を3〜4つ提案してください。形式：各行を「・」で始め、行動を10〜20字で簡潔に記述する。説明や補足は不要。"
            }]
            call_gm(hint_msg)
            continue

        # ダイス判定（use_diceがTrueの場合のみ。システム強制終了アクションは除外）
        is_forced_ending = action.startswith("（物語を終わらせてください）")
        dice_result = dice_mod.judge(action, h) if (state.get().get("use_dice", True) and not is_forced_ending) else None
        if dice_result and dice_result.get("error"):
            error_print("ダイス判定に失敗しました（APIエラーまたはJSON解析失敗）。判定なしで続行します。")
            dice_result = None
        elif dice_result:
            dice_mod.display_result(dice_result)
        user_msg = _build_user_msg(action, dice_result)
        h = push_user(h, user_msg, pending_failed)

        reply = call_gm(_build_api_messages(h))

        if reply.startswith("[ERROR"):
            error_print("応答生成に失敗しました。/retryで再試行できます。")
            # userメッセージ（ダイス結果込み）は保持したまま続行。
            # /retryで再利用でき、別の行動を入力した場合は置き換えられる。
            pending_failed = True
            continue

        pending_failed = False
        h = hist.add_assistant(h, reply)
        last_gm_reply = reply
        _after_reply(reply)

        if check_ending(reply):
            # strongモードのエンディング早出し抑止
            if _is_strong() and not state.get().get("ending_suppressed", False):
                s = state.get()
                queue = s.get("beat_queue", [])
                ptr = s.get("beat_ptr", 0)
                queue, ptr, suppressed = beat_mod.handle_ending_suppression(queue, ptr)
                if suppressed:
                    state.update({"beat_queue": queue, "beat_ptr": ptr, "ending_suppressed": True})
                    # エンディングマーカーを除いて続行
                    cleaned_reply = h[-1]["content"].replace(ENDING_MARKER, "").strip()
                    h[-1] = {"role": "assistant", "content": cleaned_reply}
                    last_gm_reply = cleaned_reply  # プレイヤーLLMにマーカーが渡らないよう更新
                    continue

            h, quit_ = handle_ending(h)
            if AUTO_PLAY_MODE or DEBUG_MODE:
                save_session_json(h, title)
            if quit_:
                break

if __name__ == "__main__":
    main()
