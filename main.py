"""
Narrative Interact (LM Studio edition)
Enter a genre and title to start the story.
"""

import sys
import json
import datetime
import state
import history as hist
import plot as plot_mod
import save as save_mod
from api import chat, chat_player, generate_genre_title, check_deviation, regenerate_plot, extract_protagonist_name, check_turning_point, generate_gm_char_comment, GM_CHAR_LABELS, GM_CHAR_LABELS_EN
import random
from display import gm_print, gm_turning_point_print, system_print, error_print, hr, gm_char_print, set_display_language
from prompt import build_start_message, build_adaptive_replot_system_prompt
import dice as dice_mod
import beat as beat_mod

COMMANDS_JA = {
    "/save": "セーブ",
    "/load": "ロード",
    "/quit": "セーブせずに終了",
    "/hint": "行動候補を3〜4つ表示",
    "/retry": "直前のGM応答を再生成",
    "/r":    "直前のGM応答を再生成",
    "/help": "コマンド一覧",
    "/h":    "コマンド一覧",
}
COMMANDS_EN = {
    "/save": "Save",
    "/load": "Load",
    "/quit": "Quit without saving",
    "/hint": "Show 3-4 action suggestions",
    "/retry": "Regenerate last GM response",
    "/r":    "Regenerate last GM response",
    "/help": "Show command list",
    "/h":    "Show command list",
}
COMMANDS = COMMANDS_JA  # will be overwritten after language selection

ENDING_MARKER = "[Ending]"

EPILOGUE_PROMPT_JA = (
    "エピローグを200字程度で書いてください。"
    "（これはエピローグ専用の依頼です。「[Ending]以降の描写禁止」ルールはエピローグには適用されません。）"
    "本編で生じた代償・損失（負傷・失った力・犠牲等）と主要人物の状態（生死・関係の変化等）のうち、"
    "本編で明示されたものを1〜2点、具体的な描写で回収すること。"
    "新しい出来事は起こさず、意味・テーマ・変化の総括や説明もせず、"
    "具体的な動作・場所・物・人物の状態のみで描写して余韻を残すこと。"
    "「和解」「解放」「平穏」「救済」「変化」「重圧」「呪縛」「受容」「移ろう」「置き換わる」"
    "など抽象語は使用しないこと。"
)
EPILOGUE_PROMPT_EN = (
    "Please write an epilogue of around 200 characters. "
    "(This is an epilogue-only request. The rule 'no depiction after [Ending]' does not apply here.) "
    "Pick 1-2 consequences or losses from the main story (injuries, sacrifices, lost powers, etc.) and the states of major characters "
    "(life/death, relationship changes, etc.) that were explicitly shown. Depict them in concrete detail. "
    "Do not introduce new events. Do not summarize meanings, themes, or changes. "
    "Use only concrete actions, locations, objects, and character states to leave a lingering impression. "
    "Avoid abstract words such as 'reconciliation', 'liberation', 'peace', 'redemption', 'transformation', 'acceptance'."
)
EPILOGUE_PROMPT = EPILOGUE_PROMPT_JA  # will be overwritten after language selection

# Auto-play mode (set via command-line argument)
AUTO_PLAY_MODE: str | None = None  # None=manual, "normal"=normal, "deviate"=deviate

# Debug mode (enabled with --debug flag)
DEBUG_MODE: bool = False

# Batch session count (set with --batch N)
BATCH_COUNT: int = 0  # 0=normal run, N=run N batch sessions

# Language setting
LANGUAGE: str = "ja"         # for manual play
BATCH_LANGUAGE: str = "ja"   # for batch mode

# Genre list for batch mode
BATCH_GENRES_JA = [
    "ホラー", "ミステリー", "ファンタジー", "SF",
    "時代劇", "現代ドラマ", "サスペンス", "青春",
    "怪談", "冒険", "犯罪", "日常",
]
BATCH_GENRES_EN = [
    "Horror", "Mystery", "Fantasy", "Sci-Fi",
    "Historical", "Contemporary Drama", "Suspense", "Coming-of-Age",
    "Ghost Story", "Adventure", "Crime", "Slice of Life",
]
BATCH_GENRES = BATCH_GENRES_JA  # overwritten after language selection
_batch_genre_queue: list[str] = []  # shuffled queue

# Dice settings for batch mode (entered once before batch starts)
BATCH_USE_DICE: bool = True
BATCH_DIFFICULTY: str = "normal"
BATCH_GM_CHARACTER: str = "none"

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
    "主人公として、GMが提示した展開・誘導・フックを敢えて無視するか、逆の行動をしてください。\n"
    "「」を使わず生テキストのみセリフではなく行動を出力してください。\n"
    "行動に心情は出力しない事。\n"
    "行動に余計な装飾はしない事。\n"
    "端的に行動を描写する事。\n"
    "行動をいくつも一度にしない事。\n"
    "エンディングと表示されたら終了してください。"
)

PLAYER_SYSTEM_NORMAL_EN = (
    "You are the player in a Narrative Interact system.\n"
    "Based on the GM's text, output your action on a single line with no line breaks.\n"
    "Act as the protagonist and respond flexibly to the situation.\n"
    "Output only raw text — no quotes, no dialogue, only actions.\n"
    "Do not include emotions or inner thoughts in your action.\n"
    "Do not add unnecessary embellishments.\n"
    "Describe your action concisely.\n"
    "Do not perform multiple actions at once.\n"
    "Do not repeat the same target-action combination as the immediately preceding turn.\n"
    "If you perform actions on the same target with different verbs three times in a row, switch to a different target or location.\n"
    "If the same type of action at the same location repeats three times, move to a different location.\n"
    "If an action on the same target fails twice in a row, stop and switch to a different target or location.\n"
    "Do not fixate on a failed goal or location; prioritize action toward a different goal or location.\n"
    "Do not output unobservable inner actions such as 'steeling myself' or 'accepting the situation'. Output only externally visible actions — body, speech, or movement.\n"
    "Do not introduce items, tools, or abilities that do not exist in the story's world.\n"
    "When [Ending] is shown, stop."
)

PLAYER_SYSTEM_DEVIATE_EN = (
    "You are the player in a Narrative Interact system.\n"
    "Based on the GM's text, output your action on a single line with no line breaks.\n"
    "As the protagonist, deliberately ignore or act contrary to the developments, guidance, and hooks presented by the GM.\n"
    "Output only raw text — no quotes, no dialogue, only actions.\n"
    "Do not include emotions or inner thoughts in your action.\n"
    "Do not add unnecessary embellishments.\n"
    "Describe your action concisely.\n"
    "Do not perform multiple actions at once.\n"
    "If you perform actions on the same target with different verbs three times in a row, switch to a different target or location.\n"
    "When [Ending] is shown, stop."
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
        lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
        print("\nQuitting." if lang == "en" else "\n終了します。")
        sys.exit(0)
    except KeyboardInterrupt:
        print()
        return ""

def call_gm(messages: list, max_retries: int = 1) -> str:
    _call_lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    reply = chat(messages, language=_call_lang)
    # Context limit reached: return immediately without retrying
    if reply == "[CONTEXT_LIMIT]":
        return "[CONTEXT_LIMIT]"
    attempt = 0
    while (reply.startswith("[ERROR") or not reply.strip()) and attempt < max_retries:
        system_print("Retrying response generation..." if _call_lang == "en" else "応答生成に失敗したため再試行します...")
        reply = chat(messages, language=_call_lang)
        if reply == "[CONTEXT_LIMIT]":
            return "[CONTEXT_LIMIT]"
        attempt += 1
    # Treat empty response as an error
    if not reply.strip():
        return "[ERROR: empty response]"
    if not reply.startswith("[ERROR"):
        reply = beat_mod.filter_output(reply)
        if ENDING_MARKER in reply:
            reply = reply.replace(ENDING_MARKER, "").strip()
            reply = reply + "\n" + ENDING_MARKER
        s = state.get()
        if s.get("turning_point_injected", False):
            gm_turning_point_print(reply)
        else:
            gm_print(reply)
    return reply


def _is_strong() -> bool:
    return state.get_plot_mode() == "strong"


def _is_adaptive() -> bool:
    return state.get_plot_mode() == "adaptive"


def _get_plot_keywords(plot: dict) -> list[str]:
    """Build a keyword list from the plot for deviation detection."""
    keywords = []
    protagonist = plot.get("protagonist", {})
    if protagonist.get("goal_surface"):
        keywords.append(protagonist["goal_surface"])
    conflicts = plot.get("conflicts", [])
    for c in conflicts:
        if isinstance(c, dict) and c.get("content"):
            keywords.append(c["content"][:30])
    ending = plot.get("ending", "")
    if isinstance(ending, str) and ending:
        keywords.append(ending[:30])
    elif isinstance(ending, dict):
        scene = ending.get("scene", "") or ending.get("description", "") or ending.get("content", "")
        if scene:
            keywords.append(scene[:30])
    return keywords[:5]  # up to 5 keywords


def _do_adaptive_replot(h: list) -> None:
    """Adaptive mode: when significant deviation is detected, regenerate the plot
    and update state and the beat queue.
    """
    import beat as beat_mod_inner
    s = state.get()
    genre = s.get("genre", "")

    if DEBUG_MODE:
        print("[ADAPTIVE] Deviation detected. Starting plot regeneration.", file=sys.stderr)

    # Pass the last 10 turns of conversation history (no system messages)
    recent = [m for m in h if m["role"] in ("user", "assistant")][-20:]
    new_plot = regenerate_plot(recent, genre, language=LANGUAGE)

    if not new_plot:
        if DEBUG_MODE:
            print("[ADAPTIVE] Plot regeneration failed. Continuing without reploting.", file=sys.stderr)
        peak = s.get("deviation_count", 0)
        state.update({"adaptive_replotted": True, "deviation_count": 0, "peak_deviation_count": peak})
        return

    if DEBUG_MODE:
        import json as _json
        print(f"[ADAPTIVE] new_plot: {_json.dumps(new_plot, ensure_ascii=False)}", file=sys.stderr)

    new_genre = new_plot.get("new_genre", genre)

    # Save new plot to state
    peak = s.get("deviation_count", 0)
    state.update({
        "adaptive_replotted": True,
        "adaptive_new_plot": new_plot,
        "adaptive_new_genre": new_genre,
        "deviation_count": 0,
        "peak_deviation_count": peak,
        # Beat control: build a simple beat queue from the new plot
        "beat_queue": _build_adaptive_beat_queue(new_plot),
        "beat_ptr": 0,
        "ending_suppressed": False,
        "ending_prompted": False,
    })

    # Replace system prompt with one for the new plot (system message at start of history)
    new_sys_prompt = build_adaptive_replot_system_prompt(new_plot, new_genre)
    for i, m in enumerate(h):
        if m["role"] == "system":
            h[i] = {"role": "system", "content": new_sys_prompt}
            break

    if DEBUG_MODE:
        print(f"[ADAPTIVE] New ending set: {new_plot.get('ending_scene', '')[:40]}...", file=sys.stderr)


def _build_adaptive_beat_queue(new_plot: dict) -> list:
    """Build a simple beat queue from a regenerated plot."""
    beats = new_plot.get("beats", [])
    queue = []
    for i, b in enumerate(beats):
        if not isinstance(b, dict):
            continue
        desc = b.get("description", "")
        timing = b.get("timing", "")
        if not desc:
            continue
        if LANGUAGE == "en":
            injection_text = (
                f"(GM guidance: advance the scene so it naturally leads to the development: \"{desc}\". "
                f"Always accept the player's action.)"
            )
        else:
            injection_text = (
                f"（GMへの誘導: 「{desc}」という展開に自然につながるよう場面を進めること。"
                f"ただしプレイヤーの行動は必ず受理すること。）"
            )
        queue.append({
            "id": f"adaptive_beat_{i}",
            "description": desc,
            "timing": timing,
            "done": False,
            "injection": injection_text,
        })
    # Add the ending scene as the final beat
    ending = new_plot.get("ending_scene", "")
    if ending:
        if LANGUAGE == "en":
            ending_injection = (
                f"(GM scene instruction: bring the story to its conclusion: \"{ending}\". "
                f"When the story is complete, output \"[Ending]\" alone on the final line.)"
            )
            ending_timing = "climax"
        else:
            ending_injection = (
                f"（GMへの場面指示: 着地点「{ending}」の結末を迎えてください。"
                f"物語が完結した場合は最後の1行に「[Ending]」とのみ出力すること。）"
            )
            ending_timing = "エンディング"
        queue.append({
            "id": "adaptive_ending",
            "description": ending,
            "timing": ending_timing,
            "done": False,
            "injection": ending_injection,
        })
    return queue


def _get_recent_player_actions(history: list, n: int = 5) -> list[str]:
    """Get the n most recent player (user) actions from history.
    Excludes the opening message, dice tags, and system parenthetical lines. Returns only the first line of each message.
    """
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    if user_msgs:
        user_msgs = user_msgs[1:]
    actions = []
    for msg in user_msgs:
        first_line = msg.split("\n")[0].strip()
        if first_line.startswith("（") or first_line.startswith("(Scene instruction for GM:") or not first_line:
            continue
        actions.append(first_line)
    return actions[-n:] if actions else []


def _apply_turning_point_injection(msgs: list) -> list:
    """If the turning-point flag is set, append a description-enhancement injection to the last user message and update the flags."""
    s = state.get()
    if s.get("turning_point_triggered", False) and not s.get("turning_point_injected", False):
        _lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
        if _lang == "en":
            injection = "This turn is a turning point in the story. Depict it in more detail than usual, with care. Keep it under 500 characters."
            wrapper = f"\n(Scene instruction for GM: {injection})"
        else:
            injection = "このターンは物語の転機です。通常より詳細に、丁寧に描写すること。500字以内とすること。"
            wrapper = f"\n（GMへの場面指示: {injection}）"
        msgs = list(msgs)
        for i in reversed(range(len(msgs))):
            if msgs[i]["role"] == "user":
                msgs[i] = dict(msgs[i])
                msgs[i]["content"] += wrapper
                break
        state.update({"turning_point_injected": True, "turning_point_triggered": False})
        if DEBUG_MODE:
            print("[TURNING] turning point injection applied", file=sys.stderr)
    return msgs


def _build_api_messages(h: list) -> list:
    """Return API messages with beat injection for strong mode, or standard messages otherwise."""
    _lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    if _is_strong():
        s = state.get()
        queue = s.get("beat_queue", [])
        ptr = s.get("beat_ptr", 0)
        msgs, debug = hist.build_for_api_with_beat(h, queue, ptr)
        if debug:
            if DEBUG_MODE:
                print(debug, file=sys.stderr)
        # Queue exhausted and ending prompt not yet injected
        queue_exhausted = queue and beat_mod.get_current_beat(queue, ptr) is None
        if not debug and queue_exhausted and not s.get("ending_prompted", False):
            plot = s.get("plot", {})
            climax_setting = plot.get("climax", {}).get("setting", "")
            ending = plot.get("ending", "")
            if _lang == "en":
                if climax_setting and ending:
                    injection = (
                        f"All plot elements are in place. Advance the story one step toward the climax setting \"{climax_setting}\" and landing point \"{ending}\", responding to the player's action. "
                        f"If the story reaches a natural conclusion, output \"[Ending]\" alone on the final line."
                    )
                else:
                    injection = "All plot elements are in place. Advance the story one step toward a natural conclusion in response to the player's action. If concluded, output \"[Ending]\" alone on the final line."
                wrapper = f"\n(Scene instruction for GM: {injection})"
            else:
                if climax_setting and ending:
                    injection = (
                        f"全てのプロット要素が出揃いました。"
                        f"クライマックスの舞台「{climax_setting}」と着地点「{ending}」に向けて、"
                        f"プレイヤーの行動に応じて物語を一歩進めてください。"
                        f"物語が自然に完結した場合は、最後の1行に「[Ending]」とのみ出力すること。"
                    )
                else:
                    injection = "全てのプロット要素が出揃いました。プレイヤーの行動に応じて物語を自然な完結へ向けて一歩進めてください。完結した場合は最後の1行に「[Ending]」とのみ出力してください。"
                wrapper = f"\n（GMへの場面指示: {injection}）"
            msgs = [dict(m) for m in msgs]
            for i in reversed(range(len(msgs))):
                if msgs[i]["role"] == "user":
                    msgs[i] = dict(msgs[i])
                    msgs[i]["content"] = msgs[i]["content"] + wrapper
                    break
            state.update({"ending_prompted": True, "post_prompt_count": 0})
            if DEBUG_MODE:
                print("[BEAT] queue exhausted: injecting ending prompt", file=sys.stderr)
        # Apply increasingly stronger injection on each subsequent turn after ending prompt
        elif not debug and queue_exhausted and s.get("ending_prompted", False):
            post_count = s.get("post_prompt_count", 0)
            post_count += 1
            state.update({"post_prompt_count": post_count})
            plot = s.get("plot", {})
            climax_setting = plot.get("climax", {}).get("setting", "")
            ending = plot.get("ending", "")
            if post_count >= 2:
                # Turn 2+ onward: mandatory ending mode
                if _lang == "en":
                    if ending:
                        injection = (
                            f"[REQUIRED] End the story this turn. Whatever the player does, the story arrives at the conclusion: \"{ending}\". "
                            f"Do not add new obstacles or developments; you must conclude this turn. Output \"[Ending]\" alone on the final line."
                        )
                    else:
                        injection = "[REQUIRED] End the story this turn. Do not add new developments; you must conclude this turn. Output \"[Ending]\" alone on the final line."
                    wrapper = f"\n(Scene instruction for GM: {injection})"
                else:
                    if climax_setting and ending:
                        injection = (
                            f"【必須】このターンで物語を完結させてください。"
                            f"プレイヤーが何をしようとも、着地点「{ending}」の結末を迎えます。"
                            f"新たな障壁や展開を追加せず、必ずこのターンで締めくくること。"
                            f"最後の1行に必ず「[Ending]」とのみ出力してください。"
                        )
                    else:
                        injection = "【必須】このターンで物語を完結させてください。新たな展開を追加せず、このターンで必ず締めくくること。最後の1行に必ず「[Ending]」とのみ出力してください。"
                    wrapper = f"\n（GMへの場面指示: {injection}）"
            else:
                # Turn 1: softer re-prompt
                if _lang == "en":
                    if ending:
                        injection = f"Lead the story toward its close, aimed at the landing point \"{ending}\". If the story concludes, output \"[Ending]\" alone on the final line."
                    else:
                        injection = "Lead the story toward its close. If the story concludes, output \"[Ending]\" alone on the final line."
                    wrapper = f"\n(Scene instruction for GM: {injection})"
                else:
                    if climax_setting and ending:
                        injection = (
                            f"着地点「{ending}」に向けて、物語をクロージングへ導いてください。"
                            f"完結した場合は最後の1行に「[Ending]」とのみ出力すること。"
                        )
                    else:
                        injection = "物語をクロージングへ導いてください。完結した場合は最後の1行に「[Ending]」とのみ出力してください。"
                    wrapper = f"\n（GMへの場面指示: {injection}）"
            msgs = [dict(m) for m in msgs]
            for i in reversed(range(len(msgs))):
                if msgs[i]["role"] == "user":
                    msgs[i] = dict(msgs[i])
                    msgs[i]["content"] = msgs[i]["content"] + wrapper
                    break
            if DEBUG_MODE:
                print(f"[BEAT] post-ending injection (turn {post_count})", file=sys.stderr)
        return _apply_turning_point_injection(msgs)
    # adaptive mode: deviation detection → warning injection → plot regeneration → beat landing
    if _is_adaptive():
        s = state.get()
        adaptive_replotted = s.get("adaptive_replotted", False)

        if adaptive_replotted:
            # After replot: use same beat injection approach as strong mode for landing
            queue = s.get("beat_queue", [])
            ptr = s.get("beat_ptr", 0)
            msgs, debug = hist.build_for_api_with_beat(h, queue, ptr)
            if debug and DEBUG_MODE:
                print(debug, file=sys.stderr)
            # Queue exhausted: ending prompt (same logic as strong)
            queue_exhausted = queue and beat_mod.get_current_beat(queue, ptr) is None
            if queue_exhausted and not s.get("ending_prompted", False):
                new_plot = s.get("adaptive_new_plot", {})
                ending = new_plot.get("ending_scene", "")
                if _lang == "en":
                    if ending:
                        injection = f"All developments are in place. Bring the story to its conclusion: \"{ending}\". If concluded, output \"[Ending]\" alone on the final line."
                    else:
                        injection = "All developments are in place. Advance the story one step toward a natural conclusion. If concluded, output \"[Ending]\" alone on the final line."
                    wrapper = f"\n(Scene instruction for GM: {injection})"
                else:
                    injection = (
                        f"全ての展開が出揃いました。"
                        f"着地点「{ending}」に向けて物語を完結させてください。"
                        f"完結した場合は最後の1行に「[Ending]」とのみ出力すること。"
                    ) if ending else (
                        "全ての展開が出揃いました。物語を自然な完結へ向けて一歩進めてください。"
                        "完結した場合は最後の1行に「[Ending]」とのみ出力してください。"
                    )
                    wrapper = f"\n（GMへの場面指示: {injection}）"
                msgs = [dict(m) for m in msgs]
                for i in reversed(range(len(msgs))):
                    if msgs[i]["role"] == "user":
                        msgs[i] = dict(msgs[i])
                        msgs[i]["content"] += wrapper
                        break
                state.update({"ending_prompted": True, "post_prompt_count": 0})
                if DEBUG_MODE:
                    print("[ADAPTIVE] queue exhausted: injecting ending prompt", file=sys.stderr)
            elif queue_exhausted and s.get("ending_prompted", False):
                post_count = s.get("post_prompt_count", 0) + 1
                state.update({"post_prompt_count": post_count})
                new_plot = s.get("adaptive_new_plot", {})
                ending = new_plot.get("ending_scene", "")
                if post_count >= 2:
                    if _lang == "en":
                        injection = "[REQUIRED] End the story this turn. Do not add new obstacles; you must conclude this turn. Output \"[Ending]\" alone on the final line."
                        wrapper = f"\n(Scene instruction for GM: {injection})"
                    else:
                        injection = (
                            f"【必須】このターンで物語を完結させてください。"
                            f"新たな障壁を追加せず、必ずこのターンで締めくくること。"
                            f"最後の1行に必ず「[Ending]」とのみ出力してください。"
                        )
                        wrapper = f"\n（GMへの場面指示: {injection}）"
                else:
                    if _lang == "en":
                        if ending:
                            injection = f"Lead the story toward its close, aimed at \"{ending}\". If concluded, output \"[Ending]\" alone on the final line."
                        else:
                            injection = "Lead the story toward its close. If concluded, output \"[Ending]\" alone on the final line."
                        wrapper = f"\n(Scene instruction for GM: {injection})"
                    else:
                        injection = (
                            f"着地点「{ending}」に向けて物語をクロージングへ導いてください。"
                            f"完結した場合は最後の1行に「[Ending]」とのみ出力すること。"
                        ) if ending else (
                            "物語をクロージングへ導いてください。完結した場合は最後の1行に「[Ending]」とのみ出力してください。"
                        )
                        wrapper = f"\n（GMへの場面指示: {injection}）"
                msgs = [dict(m) for m in msgs]
                for i in reversed(range(len(msgs))):
                    if msgs[i]["role"] == "user":
                        msgs[i] = dict(msgs[i])
                        msgs[i]["content"] += wrapper
                        break
                if DEBUG_MODE:
                    print(f"[ADAPTIVE] post-ending injection (turn {post_count})", file=sys.stderr)
            return _apply_turning_point_injection(msgs)

        # Before replot: check deviation every turn (regardless of AUTO_PLAY_MODE)
        recent = _get_recent_player_actions(h, n=3)
        if len(recent) >= 3:
            plot = s.get("plot", {})
            keywords = _get_plot_keywords(plot)
            if check_deviation(recent, keywords):
                deviation_count = s.get("deviation_count", 0) + 1
                state.update({"deviation_count": deviation_count})
                if DEBUG_MODE:
                    print(f"[ADAPTIVE] deviation_count={deviation_count}", file=sys.stderr)

                if deviation_count >= 5:
                    # Regenerate plot → switch to beat-landing mode (record peak count)
                    state.update({"peak_deviation_count": deviation_count})
                    _do_adaptive_replot(h)
                    # Immediately after replot: inject the first beat from the new queue
                    s2 = state.get()
                    queue = s2.get("beat_queue", [])
                    ptr = s2.get("beat_ptr", 0)
                    msgs, debug = hist.build_for_api_with_beat(h, queue, ptr)
                    if debug and DEBUG_MODE:
                        print(debug, file=sys.stderr)
                    return _apply_turning_point_injection(msgs)
                elif deviation_count >= 3:
                    # Warning injection: prompt GM to converge
                    msgs = list(hist.build_for_api(h))
                    if _lang == "en":
                        injection = (
                            "The player's actions are drifting from the plot. Keep in mind a development that leads naturally to an ending from the current situation. "
                            "If an ending opportunity arises, take it without hesitation."
                        )
                        wrapper = f"\n(Scene instruction for GM: {injection})"
                    else:
                        injection = (
                            "プレイヤーの行動がプロットから離れてきています。"
                            "現在の状況から自然にエンディングへつながる展開を意識してください。"
                            "エンディングの機会があれば迷わず終わらせること。"
                        )
                        wrapper = f"\n（GMへの場面指示: {injection}）"
                    for i in reversed(range(len(msgs))):
                        if msgs[i]["role"] == "user":
                            msgs[i] = dict(msgs[i])
                            msgs[i]["content"] += wrapper
                            break
                    if DEBUG_MODE:
                        print(f"[ADAPTIVE] warning injection at count={deviation_count}", file=sys.stderr)
                    return _apply_turning_point_injection(msgs)
            else:
                # No deviation: do not reset count, keep accumulating
                if DEBUG_MODE and s.get("deviation_count", 0) > 0:
                    print(f"[ADAPTIVE] deviation: no (count stays at {s.get('deviation_count', 0)})", file=sys.stderr)

    # off/adaptive(pre-replot)/improv mode: too many turns → convergence injection (after 25 turns)
    if not _is_strong():
        turn_count = sum(1 for m in h if m["role"] == "user")
        if turn_count > 25:
            msgs = list(hist.build_for_api(h))
            if _lang == "en":
                injection = "The story has gone on for a while. Bring it to a natural close from the current situation."
                wrapper = f"\n(Scene instruction for GM: {injection})"
            else:
                injection = "物語が長くなっている。現在の状況から自然にエンディングへ収束させること。"
                wrapper = f"\n（GMへの場面指示: {injection}）"
            for i in reversed(range(len(msgs))):
                if msgs[i]["role"] == "user":
                    msgs[i] = dict(msgs[i])
                    msgs[i]["content"] += wrapper
                    break
            if DEBUG_MODE:
                print(f"[TURN_LIMIT] turn={turn_count}: injecting convergence prompt", file=sys.stderr)
            return _apply_turning_point_injection(msgs)

    msgs = list(hist.build_for_api(h))
    return _apply_turning_point_injection(msgs)


def _after_reply(reply: str) -> None:
    """Advance the beat pointer after a GM reply in strong / adaptive-replotted / off mode."""
    is_beat_mode = _is_strong() or (_is_adaptive() and state.get().get("adaptive_replotted", False)) or _is_off()
    if is_beat_mode:
        s = state.get()
        queue = s.get("beat_queue", [])
        ptr = s.get("beat_ptr", 0)
        old_ptr = ptr
        queue, ptr = beat_mod.advance(queue, ptr, reply, language=s.get("language", "ja"))
        advanced = ptr > old_ptr
        state.update({"beat_queue": queue, "beat_ptr": ptr, "beat_just_advanced": advanced})
    else:
        state.update({"beat_just_advanced": False})
    # Reset turning-point injection flag so the next turning point can fire again
    state.update({"turning_point_injected": False})


def _build_user_msg(action: str, dice_result: dict | None) -> str:
    """Build the user message, placing the dice result before the action text."""
    if not dice_result:
        return action

    _lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    intensity = dice_result.get("intensity", "normal")
    diff = dice_result["difficulty"]
    roll = dice_result["dice"]

    if _lang == "en":
        outcome = "success" if dice_result["success"] else "failure"
        reason = dice_result.get("reason", "check")
        if dice_result["success"] and intensity == "decisive":
            inst = (
                "Depict this as a decisive success. "
                "Show a concrete result that significantly advances the action's goal. "
                "Do not nullify or downplay the success."
            )
        elif dice_result["success"]:
            inst = (
                "Depict this as a success: the situation advances one step. "
                "Do not nullify or downplay the success."
            )
        elif intensity == "severe":
            inst = (
                "Depict this as a severe failure. The goal is not achieved. "
                "Introduce at most one minor obstacle the player can address on the next action. "
                "Do not depict the failure as close to success."
            )
        else:
            inst = (
                "Depict this as a failure: the action does not succeed. "
                "Make the failure clear, then include at least one concrete action anchor in the scene — "
                "another object, approach, person, sound, or light the player can act on next. "
                "Do not depict the failure as close to success."
            )
        tag = (
            f"(Check result: {reason} / difficulty {diff} / roll {roll} → {outcome}. "
            f"{inst} "
            f"Build the narrative to be consistent with the check result. "
            f"Do not output the check result in the narration.)"
        )
    else:
        outcome = "成功" if dice_result["success"] else "失敗"
        reason = dice_result.get("reason", "判定")
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

PLOT_MODE_LABELS_JA = {
    "1": ("strong", "プロット参照・強拘束"),
    "2": ("adaptive", "プロット参照・適応（逸脱を検出して現在地で物語を再構成）"),
    "3": ("off", "プロット参照・自由"),
    "4": ("improv", "プロットなし・即興"),
}
PLOT_MODE_LABELS_EN = {
    "1": ("strong", "Plot-bound (strict)"),
    "2": ("adaptive", "Plot-adaptive (detects deviation and reconstructs the story from the current point)"),
    "3": ("off", "Plot-guided (free)"),
    "4": ("improv", "Improvised (no plot)"),
}
PLOT_MODE_LABELS = PLOT_MODE_LABELS_JA  # will be overwritten after language selection

def ask_plot_mode() -> str:
    lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    print()
    if lang == "en":
        print("Story axis:")
        print("  1. Plot-bound strict (forced recovery) ★ Recommended for first-timers")
        print("  2. Plot-adaptive (detects deviation and reconstructs from current point)")
        print("  3. Plot-guided free (guides toward plot but deviation is allowed)")
        print("  4. Improvised (GM creates story on the fly)")
        while True:
            choice = ask("Choice [1/2/3/4]: ")
            if choice in PLOT_MODE_LABELS:
                mode, label = PLOT_MODE_LABELS[choice]
                system_print(f"Story axis: {label}")
                return mode
            system_print("Please enter 1, 2, 3, or 4.")
    else:
        print("物語の軸:")
        print("  1. プロット参照・強拘束（プロット強制回収）★初めてならこれを推奨")
        print("  2. プロット参照・適応（逸脱を検出して現在地で物語を再構成）")
        print("  3. プロット参照・自由（プロットに沿うよう誘導するが逸脱自由）")
        print("  4. プロットなし・即興（GMが即興で物語を作る）")
        while True:
            choice = ask("選択 [1/2/3/4]: ")
            if choice in PLOT_MODE_LABELS:
                mode, label = PLOT_MODE_LABELS[choice]
                system_print(f"物語の軸: {label}")
                return mode
            system_print("1〜4のいずれかを入力してください。")

def ask_use_dice() -> bool:
    lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    print()
    if lang == "en":
        ans = ask("Use dice rolls? [Y/n]: ")
        use_dice = ans.lower() != "n"
        system_print(f"Dice rolls: {'on' if use_dice else 'off'}")
    else:
        ans = ask("ダイス判定を使いますか？ [Y/n]: ")
        use_dice = ans.lower() != "n"
        system_print(f"ダイス判定: {'使う' if use_dice else '使わない'}")
    return use_dice

DIFFICULTY_LABELS_JA = {
    "1": ("easy", "易しい"),
    "2": ("normal", "標準"),
    "3": ("hard", "厳しい"),
}
DIFFICULTY_LABELS_EN = {
    "1": ("easy", "Easy"),
    "2": ("normal", "Normal"),
    "3": ("hard", "Hard"),
}
DIFFICULTY_LABELS = DIFFICULTY_LABELS_JA  # will be overwritten after language selection

def ask_difficulty() -> str:
    lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    print()
    if lang == "en":
        print("Difficulty:")
        print("  1. Easy")
        print("  2. Normal (recommended)")
        print("  3. Hard")
        while True:
            choice = ask("Choice [1/2/3]: ")
            if choice in DIFFICULTY_LABELS:
                preset, label = DIFFICULTY_LABELS[choice]
                system_print(f"Difficulty: {label}")
                return preset
            system_print("Please enter 1, 2, or 3.")
    else:
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

def ask_gm_character() -> str:
    """GMの一言コメントのあり/なしを番号入力で選択する。"""
    lang = LANGUAGE if not AUTO_PLAY_MODE else BATCH_LANGUAGE
    print()
    if lang == "en":
        print("GM comment:")
        print("  1. On (cynical)")
        print("  2. Off")
        while True:
            choice = ask("Choice [1-2]: ")
            if choice == "1":
                system_print("GM comment: on (cynical)")
                return "cynical"
            elif choice == "2":
                system_print("GM comment: off")
                return "none"
            system_print("Please enter 1 or 2.")
    else:
        print("GMの一言コメント:")
        print("  1. あり（シニカル）")
        print("  2. なし")
        while True:
            choice = ask("選択 [1-2]: ")
            if choice == "1":
                system_print("GMの一言: あり（シニカル）")
                return "cynical"
            elif choice == "2":
                system_print("GMの一言: なし")
                return "none"
            system_print("1か2を入力してください。")

def ask_language() -> str:
    """Select language at startup. Returns "ja" or "en"."""
    global COMMANDS, PLOT_MODE_LABELS, DIFFICULTY_LABELS, EPILOGUE_PROMPT
    print()
    print("Language / 言語:")
    print("  1. 日本語")
    print("  2. English")
    while True:
        choice = ask("Choice / 選択 [1/2]: ")
        if choice == "1":
            COMMANDS = COMMANDS_JA
            PLOT_MODE_LABELS = PLOT_MODE_LABELS_JA
            DIFFICULTY_LABELS = DIFFICULTY_LABELS_JA
            EPILOGUE_PROMPT = EPILOGUE_PROMPT_JA
            set_display_language("ja")
            return "ja"
        elif choice == "2":
            COMMANDS = COMMANDS_EN
            PLOT_MODE_LABELS = PLOT_MODE_LABELS_EN
            DIFFICULTY_LABELS = DIFFICULTY_LABELS_EN
            EPILOGUE_PROMPT = EPILOGUE_PROMPT_EN
            set_display_language("en")
            return "en"
        print("Please enter 1 or 2 / 1か2を入力してください。")


def _is_off() -> bool:
    return state.get_plot_mode() == "off"


def _handle_gm_char_and_turning_point(action: str, h: list) -> None:
    """Handle GM character comment and turning-point description enhancement.
    - If a GM character is set and a turning point is detected: display a comment.
    - If a turning point and turning_point_triggered is False: record the enhancement injection in state.
    Call this before call_gm().
    """
    s = state.get()
    gm_character = s.get("gm_character", "none")

    # Beat mode (strong/adaptive-replotted/off): turning-point detection via code
    is_beat_mode = _is_strong() or (_is_adaptive() and s.get("adaptive_replotted", False)) or _is_off()
    # improv or adaptive (pre-replot): turning-point detection via LLM
    is_llm_judge = state.get_plot_mode() == "improv" or (_is_adaptive() and not s.get("adaptive_replotted", False))

    is_turning_point = False

    if is_beat_mode:
        # Only treat as turning point when beat_just_advanced=True
        is_turning_point = s.get("beat_just_advanced", False)
    elif is_llm_judge:
        # improv / adaptive (before replot): LLM judge every turn
        is_turning_point = check_turning_point(h, action, language=LANGUAGE)
        if DEBUG_MODE and is_turning_point:
            print("[TURNING] turning point detected (llm judge)", file=sys.stderr)

    # GM character comment (only on turning points)
    if is_turning_point and gm_character != "none":
        comment = generate_gm_char_comment(action, h, gm_character, gm_char_log=s.get("gm_char_log", []), language=s.get("language", "ja"))
        if comment:
            gm_char_print(comment)
            if DEBUG_MODE:
                _char_labels = GM_CHAR_LABELS_EN if s.get("language", "ja") == "en" else GM_CHAR_LABELS
                label = _char_labels.get(gm_character, gm_character)
                print(f"[GM_CHAR] {label}: {comment}", file=sys.stderr)
            # Accumulate comment in state (for JSON log)
            s = state.get()
            log = list(s.get("gm_char_log", []))
            log.append({
                "turn": sum(1 for m in h if m["role"] == "user"),
                "character": gm_character,
                "comment": comment,
            })
            state.update({"gm_char_log": log})

    # Record turning-point description-enhancement flag in state
    if is_turning_point:
        state.update({"turning_point_triggered": True})
        if DEBUG_MODE:
            print("[TURNING] turning_point_triggered = True", file=sys.stderr)


def start_new_game() -> tuple[list, str, str]:
    lang = LANGUAGE
    if lang == "en":
        while not (genre := ask("Genre: ").strip()):
            system_print("Please enter a genre.")
        while not (title := ask("Title: ").strip()):
            system_print("Please enter a title.")
    else:
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

    gm_character = "none"
    if not AUTO_PLAY_MODE:
        gm_character = ask_gm_character()

    if plot_mode == "improv":
        system_print("No plot generation (improv mode)" if LANGUAGE == "en" else "プロット生成なし")
        plot = {}
    else:
        plot = plot_mod.generate(genre, title, language=LANGUAGE)

    state.init(genre, title, plot, plot_mode)
    state.update({"use_dice": use_dice, "difficulty_preset": difficulty_preset,
                  "auto_play_mode": AUTO_PLAY_MODE or "manual",
                  "gm_character": gm_character,
                  "language": LANGUAGE})

    if plot_mode in ("strong", "off") and plot:
        queue = beat_mod.build_queue(plot)
        state.update({"beat_queue": queue, "beat_ptr": 0, "ending_suppressed": False, "ending_prompted": False})
        if DEBUG_MODE:
            print(f"[BEAT] queue built: {len(queue)} beats", file=sys.stderr)

    h = hist.new_history(plot, plot_mode, genre, language=LANGUAGE)
    start_msg = build_start_message(genre, title, plot)
    h = hist.add_user(h, start_msg)

    print()
    if LANGUAGE == "en":
        print(f'── "{title}" Start ──')
        system_print('If you get stuck, /hint shows action suggestions.')
    else:
        print(f"── 「{title}」 開始 ──")
        system_print("行き詰まったら /hint で行動候補を表示できます。")
    print()

    reply = call_gm(_build_api_messages(h))
    # Display protagonist name (improv: extracted from opening scene; other modes: from plot)
    if not reply.startswith("[ERROR"):
        if plot_mode == "improv":
            improv_name = extract_protagonist_name(reply, language=LANGUAGE)
            if improv_name:
                if LANGUAGE == "en":
                    print(f"You are {improv_name}. Your story begins now.")
                else:
                    print(f"あなたは{improv_name}として、この物語を紡ぎます。")
                print()
        else:
            protagonist = plot.get("protagonist", {}) if plot else {}
            if protagonist.get("name"):
                if LANGUAGE == "en":
                    print(f"You are {protagonist['name']}. Your story begins now.")
                else:
                    print(f"あなたは{protagonist['name']}として、この物語を紡ぎます。")
                print()
    if reply.startswith("[ERROR"):
        error_print("Failed to generate response. You can /retry." if LANGUAGE == "en" else "応答生成に失敗しました。/retryで再試行できます。")
        # In auto-play: use empty string so the error string is not passed to the player LLM
        initial_reply_for_player = ""
    else:
        h = hist.add_assistant(h, reply)
        _after_reply(reply)
        initial_reply_for_player = reply

    return h, genre, title, initial_reply_for_player

def _print_history(h: list) -> None:
    """Display history in order. Skips system messages and dice result tags."""
    for m in h:
        if m["role"] == "system":
            continue
        content = m["content"]
        if m["role"] == "assistant":
            gm_print(content)
        elif m["role"] == "user":
            # Show player action only, excluding dice result tags
            # When a tag is present, the first line is the player input
            action_line = content.split("\n")[0]
            # Skip system-injected messages starting with （...） or (Scene instruction for GM:
            if not (action_line.startswith("（") or action_line.startswith("(Scene instruction for GM:")):
                label = "Your action" if LANGUAGE == "en" else "あなたの行動"
                print(f"\n{label}: {action_line}")

def resume_game() -> tuple[list, str, str] | None:
    s, h = save_mod.load()
    if not s or not h:
        system_print("No save data found." if LANGUAGE == "en" else "セーブデータが見つかりません。")
        return None
    state.load_from(s)
    plot = s.get("plot", {})
    plot_mode = s.get("plot_mode", "off")
    dice_mod.set_difficulty_preset(s.get("difficulty_preset", "normal"))

    # Rebuild beat_queue if missing from old save data
    if plot_mode in ("strong", "off") and plot and not s.get("beat_queue"):
        queue = beat_mod.build_queue(plot)
        state.update({"beat_queue": queue, "beat_ptr": 0, "ending_suppressed": False, "ending_prompted": False})
        if DEBUG_MODE:
            print(f"[BEAT] queue rebuilt on load: {len(queue)} beats", file=sys.stderr)
    title = s.get("title", "")
    genre = s.get("genre", "")
    lang = s.get("language", "ja")
    h = hist.rebuild_system(h, plot, plot_mode, genre, language=lang)
    if lang == "en":
        system_print(f'Loaded: "{title}" — showing history...')
    else:
        system_print(f"ロード完了: 「{title}」　履歴を表示します...")
    print()

    _print_history(h)

    return h, genre, title

def save_session_json(h: list, title: str) -> None:
    """Save the entire session as JSON (used in AUTO_PLAY mode)."""
    # Remove characters that are problematic on both Windows and Linux
    import re as _re
    import subprocess as _sp
    import os as _os
    safe_title = _re.sub(r'[\\/:*?"<>|\s]', "_", title)
    safe_title = safe_title.strip("_") or "session"
    play_mode = state.get().get("auto_play_mode", "manual")
    try:
        commit_hash = _sp.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_os.path.dirname(_os.path.abspath(__file__)),
            stderr=_sp.DEVNULL, text=True
        ).strip()
    except Exception:
        try:
            _ver_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "VERSION")
            with open(_ver_path, encoding="utf-8") as _vf:
                commit_hash = _vf.read().strip()
        except Exception:
            commit_hash = "unknown"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_title}_{play_mode}_{timestamp}_{commit_hash}.json"
    data = {
        "state": state.get(),
        "history": h,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    lang = state.get().get("language", "ja")
    if lang == "en":
        system_print(f"Session saved: {filename}")
    else:
        system_print(f"セッションを保存しました: {filename}")

def handle_ending(h: list) -> tuple[list, bool]:
    """Handle choices after an ending. Returns (history, should_quit)."""
    lang = state.get().get("language", "ja")
    if lang == "en":
        system_print("The story has reached its ending. Thank you for playing!")
    else:
        system_print("エンディングを迎えました。お疲れさまでした。")
    if AUTO_PLAY_MODE:
        end_reason = "ending"
        state.update({"end_reason": end_reason})
        # In auto-play mode, auto-generate the epilogue then quit
        h = hist.add_user(h, EPILOGUE_PROMPT)
        reply = call_gm(hist.build_for_api(h))
        if reply.startswith("[ERROR"):
            if lang == "en":
                error_print("Failed to generate epilogue.")
            else:
                error_print("エピローグの生成に失敗しました。")
            h.pop()
        else:
            h = hist.add_assistant(h, reply)
        return h, True
    if lang == "en":
        print("  1. Quit")
        print("  2. Generate epilogue")
        while True:
            ans = ask("Choice [1/2]: ")
            if ans == "1":
                return h, True
            if ans == "2":
                h = hist.add_user(h, EPILOGUE_PROMPT)
                reply = call_gm(hist.build_for_api(h))
                if reply.startswith("[ERROR"):
                    error_print("Failed to generate epilogue.")
                    h.pop()
                else:
                    h = hist.add_assistant(h, reply)
                return h, True
            system_print("Please enter 1 or 2.")
    else:
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
    """Add a user message. If replace_pending=True, replace the previous user message
    that was left unanswered due to an error (treat it as an abandoned action)."""
    if replace_pending and h and h[-1]["role"] == "user":
        h.pop()
    return hist.add_user(h, content)

def _pick_batch_genre() -> str:
    """Pick the next genre from the batch genre queue, reshuffling when empty."""
    global _batch_genre_queue
    if not _batch_genre_queue:
        _batch_genre_queue = random.sample(BATCH_GENRES, len(BATCH_GENRES))
    return _batch_genre_queue.pop(0)


def run_single_session(plot_mode: str) -> None:
    """Run a single session for batch mode, save it, then finish.
    plot_mode: the story axis selected before the session starts.
    """
    global AUTO_PLAY_MODE, DEBUG_MODE

    # Pick genre from the list; have the LLM generate only the title
    genre = _pick_batch_genre()
    result = generate_genre_title(genre, language=BATCH_LANGUAGE)
    if "error" in result:
        if BATCH_LANGUAGE == "en":
            error_print(f"Title generation failed: {result['error']}")
        else:
            error_print(f"タイトル生成に失敗しました: {result['error']}")
        return
    title = result.get("title", "").strip()
    if not title:
        if BATCH_LANGUAGE == "en":
            error_print(f"Title is empty: {result}")
        else:
            error_print(f"タイトルが空です: {result}")
        return

    if BATCH_LANGUAGE == "en":
        system_print(f'Genre: {genre} / Title: "{title}"')
    else:
        system_print(f"ジャンル: {genre} / タイトル: 「{title}」")

    # Apply batch dice settings
    dice_mod.set_difficulty_preset(BATCH_DIFFICULTY)
    difficulty_preset = BATCH_DIFFICULTY

    if plot_mode == "improv":
        if BATCH_LANGUAGE == "en":
            system_print("No plot generation (improv mode)")
        else:
            system_print("プロット生成なし")
        plot = {}
    else:
        plot = plot_mod.generate(genre, title, language=BATCH_LANGUAGE)

    state.init(genre, title, plot, plot_mode)
    state.update({"use_dice": BATCH_USE_DICE, "difficulty_preset": difficulty_preset,
                  "auto_play_mode": AUTO_PLAY_MODE or "manual",
                  "gm_character": BATCH_GM_CHARACTER,
                  "language": BATCH_LANGUAGE})

    if plot_mode in ("strong", "off") and plot:
        queue = beat_mod.build_queue(plot)
        state.update({"beat_queue": queue, "beat_ptr": 0, "ending_suppressed": False, "ending_prompted": False})
        if DEBUG_MODE:
            print(f"[BEAT] queue built: {len(queue)} beats", file=sys.stderr)

    h = hist.new_history(plot, plot_mode, genre, language=BATCH_LANGUAGE)
    start_msg = build_start_message(genre, title, plot)
    h = hist.add_user(h, start_msg)

    print()
    if BATCH_LANGUAGE == "en":
        print(f'── "{title}" Start ──')
    else:
        print(f"── 「{title}」 開始 ──")
    protagonist = plot.get("protagonist", {}) if plot else {}
    if protagonist.get("name"):
        name = protagonist["name"]
        if BATCH_LANGUAGE == "en":
            print(f"You are {name}. Your story begins now.")
        else:
            print(f"あなたは{name}として、この物語を紡ぎます。")
        print()

    reply = call_gm(_build_api_messages(h))
    if reply == "[CONTEXT_LIMIT]" or reply.startswith("[ERROR"):
        error_print("Failed to generate opening. Skipping session." if BATCH_LANGUAGE == "en" else "初回応答生成に失敗しました。このセッションをスキップします。")
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
            if BATCH_LANGUAGE == "en":
                system_print(f"Auto-play turn limit ({AUTO_PLAY_MAX_TURNS} turns) reached. Ending session.")
            else:
                system_print(f"自動プレイのターン上限（{AUTO_PLAY_MAX_TURNS}ターン）に達しました。終了します。")
            save_session_json(h, title)
            break

        if not last_gm_reply:
            action = ""
        else:
            if _is_strong() and state.get().get("ending_prompted", False) and \
                    state.get().get("post_prompt_count", 0) >= 3:
                action = "（物語を終わらせてください）" if BATCH_LANGUAGE != "en" else "(Please end the story)"
                _forced_label = "[System forced]" if BATCH_LANGUAGE == "en" else "[システム強制]"
                _action_label = "Your action" if BATCH_LANGUAGE == "en" else "あなたの行動"
                print(f"\n{_action_label}: {action} {_forced_label}")
            else:
                if BATCH_LANGUAGE == "en":
                    sys_prompt = PLAYER_SYSTEM_NORMAL_EN if AUTO_PLAY_MODE == "normal" else PLAYER_SYSTEM_DEVIATE_EN
                else:
                    sys_prompt = PLAYER_SYSTEM_NORMAL if AUTO_PLAY_MODE == "normal" else PLAYER_SYSTEM_DEVIATE
                _plot = state.get().get("plot", {})
                _protagonist = _plot.get("protagonist", {}) if _plot else {}
                _pname = _protagonist.get("name", "") if _protagonist else ""
                if _pname:
                    if BATCH_LANGUAGE == "en":
                        sys_prompt = f"You control the protagonist named '{_pname}'. Do not control other characters.\n" + sys_prompt
                    else:
                        sys_prompt = f"あなたが操作する主人公の名前は「{_pname}」です。他のキャラクターを操作しないこと。\n" + sys_prompt
                recent_actions = _get_recent_player_actions(h, n=5)
                # In DEVIATE mode, don't pass recent actions (avoid suppressing deviations)
                _ra = None if AUTO_PLAY_MODE == "deviate" else recent_actions
                action = chat_player(last_gm_reply, sys_prompt, _ra, language=BATCH_LANGUAGE)
                if action.startswith("[ERROR"):
                    error_print(f"Player LLM error: {action}" if BATCH_LANGUAGE == "en" else f"プレイヤーLLMエラー: {action}")
                    state.update({"end_reason": "player_error"})
                    save_session_json(h, title)
                    break
                _action_label2 = "Your action" if BATCH_LANGUAGE == "en" else "あなたの行動"
                print(f"\n{_action_label2}: {action}")

        if not action:
            continue

        is_forced_ending = action.startswith("（物語を終わらせてください）") or action.startswith("(Please end the story)")
        dice_result = dice_mod.judge(action, h, language=BATCH_LANGUAGE) if (state.get().get("use_dice", True) and not is_forced_ending) else None
        if dice_result and dice_result.get("error"):
            error_print("Dice roll failed. Continuing without roll." if BATCH_LANGUAGE == "en" else "ダイス判定に失敗しました。判定なしで続行します。")
            dice_result = None
        elif dice_result:
            dice_mod.display_result(dice_result, language=BATCH_LANGUAGE)
        user_msg = _build_user_msg(action, dice_result)
        h = hist.add_user(h, user_msg)

        # GM character comment + turning-point flag
        _handle_gm_char_and_turning_point(action, h)

        reply = call_gm(_build_api_messages(h))
        if reply == "[CONTEXT_LIMIT]":
            if BATCH_LANGUAGE == "en":
                system_print("Context limit reached. The story ends here.")
            else:
                system_print("コンテキスト上限に達し続行不可能の為、物語をここで終了します。")
            state.update({"end_reason": "context_limit"})
            save_session_json(h, title)
            break
        if reply.startswith("[ERROR"):
            if BATCH_LANGUAGE == "en":
                error_print("Failed to generate response. Skipping turn.")
            else:
                error_print("応答生成に失敗しました。スキップして続行します。")
            h.pop()
            continue

        h = hist.add_assistant(h, reply)
        last_gm_reply = reply
        _after_reply(reply)

        if check_ending(reply):
            _use_beat_suppression = _is_strong() or (_is_adaptive() and state.get().get("adaptive_replotted", False))
            if _use_beat_suppression and not state.get().get("ending_suppressed", False):
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
    global AUTO_PLAY_MODE, DEBUG_MODE, BATCH_COUNT, LANGUAGE, BATCH_LANGUAGE, BATCH_GENRES
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python main.py [options]")
        print()
        print("Options:")
        print("  --normal         Auto-play (normal)")
        print("  --deviate        Auto-play (deviate)")
        print("  --batch N        Run N sessions in batch (use with --normal or --deviate)")
        print("  --debug          Enable debug output (to stderr)")
        print("  --help, -h       Show this help")
        sys.exit(0)

    if "--normal" in sys.argv:
        AUTO_PLAY_MODE = "normal"
    elif "--deviate" in sys.argv:
        AUTO_PLAY_MODE = "deviate"

    # Parse --batch N
    if "--batch" in sys.argv:
        idx = sys.argv.index("--batch")
        if idx + 1 < len(sys.argv):
            try:
                BATCH_COUNT = int(sys.argv[idx + 1])
            except ValueError:
                print("--batch argument must be an integer.")
                sys.exit(1)
        else:
            print("Please specify a count after --batch. Example: --batch 5")
            sys.exit(1)

    # Always enable debug in auto-play mode
    if AUTO_PLAY_MODE or "--debug" in sys.argv:
        DEBUG_MODE = True
        beat_mod.DEBUG_MODE = True
        plot_mod.DEBUG_MODE = True

    # Language selection (before banner display)
    lang = ask_language()
    LANGUAGE = lang
    BATCH_LANGUAGE = lang
    BATCH_GENRES = BATCH_GENRES_EN if lang == "en" else BATCH_GENRES_JA

    print()
    if lang == "en":
        print("╔══════════════════════════════════════════╗")
        print("║     NARRATIVE INTERACT (LM Studio)       ║")
        print("╚══════════════════════════════════════════╝")
        if AUTO_PLAY_MODE:
            print(f"[Auto-play mode: {'normal' if AUTO_PLAY_MODE == 'normal' else 'deviate'}]")
        if BATCH_COUNT > 0:
            print(f"[Batch mode: {BATCH_COUNT} sessions]")
        print()
        print("Type /help or /h for commands")
    else:
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

    # Batch mode
    if BATCH_COUNT > 0:
        if not AUTO_PLAY_MODE:
            if lang == "en":
                print("--batch must be used with --normal or --deviate.")
            else:
                print("--batch は --normal または --deviate と併用してください。")
            sys.exit(1)
        plot_mode = ask_plot_mode()
        print()
        # Ask dice settings once for all batch sessions
        global BATCH_USE_DICE, BATCH_DIFFICULTY, BATCH_GM_CHARACTER
        BATCH_USE_DICE = ask_use_dice()
        if BATCH_USE_DICE:
            BATCH_DIFFICULTY = ask_difficulty()
            dice_mod.set_difficulty_preset(BATCH_DIFFICULTY)
        BATCH_GM_CHARACTER = ask_gm_character()
        print()
        for i in range(BATCH_COUNT):
            if lang == "en":
                print(f"═══ Batch {i+1}/{BATCH_COUNT} ═══")
            else:
                print(f"═══ バッチ {i+1}/{BATCH_COUNT} ═══")
            run_single_session(plot_mode)
            print()
        if lang == "en":
            system_print(f"Batch complete: {BATCH_COUNT} sessions")
        else:
            system_print(f"バッチ実行完了: {BATCH_COUNT}回")
        return

    h, genre, title = None, "", ""

    if save_mod.exists():
        if AUTO_PLAY_MODE:
            save_mod.delete()
            if lang == "en":
                system_print("Auto-play mode: deleting save data and starting fresh.")
            else:
                system_print("自動プレイモード：セーブデータを削除して新規開始します。")
        else:
            s, _ = save_mod.load()
            saved_title = s.get("title", "") if s else ""
            if lang == "en":
                system_print(f'Save data found: "{saved_title}"')
                print("  1. Continue")
                print("  2. Delete and start new")
                while True:
                    ans = ask("Choice [1/2]: ")
                    if ans == "1":
                        result = resume_game()
                        if result:
                            h, genre, title = result
                            initial_reply = ""
                        break
                    elif ans == "2":
                        save_mod.delete()
                        system_print("Save data deleted.")
                        break
                    system_print("Please enter 1 or 2.")
            else:
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
        # If the initial generation failed (empty string), mark pending_failed
        pending_failed = (initial_reply == "")
    else:
        initial_reply = ""
        pending_failed = False

    last_gm_reply = initial_reply  # For auto-play: last GM response (including initial)
    auto_play_turn = 0  # Auto-play turn counter
    AUTO_PLAY_MAX_TURNS = 40  # Maximum turns for auto-play

    while True:
        if AUTO_PLAY_MODE:
            # Turn limit check
            auto_play_turn += 1
            if auto_play_turn > AUTO_PLAY_MAX_TURNS:
                state.update({"end_reason": "turn_limit"})
                _lang = state.get().get("language", "ja")
                if _lang == "en":
                    system_print(f"Auto-play turn limit ({AUTO_PLAY_MAX_TURNS} turns) reached. Ending session.")
                else:
                    system_print(f"自動プレイのターン上限（{AUTO_PLAY_MAX_TURNS}ターン）に達しました。終了します。")
                if DEBUG_MODE:
                    save_session_json(h, title)
                break
            if not last_gm_reply:
                action = ""
            else:
                # After ending_prompted, force-end player input after a few turns
                if _is_strong() and state.get().get("ending_prompted", False) and \
                        state.get().get("post_prompt_count", 0) >= 3:
                    _lang_auto = state.get().get("language", "ja")
                    action = "（物語を終わらせてください）" if _lang_auto != "en" else "(Please end the story)"
                    _forced_sfx = " [System forced]" if _lang_auto == "en" else " [システム強制]"
                    _act_lbl = "Your action" if _lang_auto == "en" else "あなたの行動"
                    print(f"\n{_act_lbl}: {action}{_forced_sfx}")
                else:
                    _lang_auto = state.get().get("language", "ja")
                    if _lang_auto == "en":
                        sys_prompt = PLAYER_SYSTEM_NORMAL_EN if AUTO_PLAY_MODE == "normal" else PLAYER_SYSTEM_DEVIATE_EN
                    else:
                        sys_prompt = PLAYER_SYSTEM_NORMAL if AUTO_PLAY_MODE == "normal" else PLAYER_SYSTEM_DEVIATE
                    # Prepend protagonist name to sys_prompt (prevent controlling wrong character)
                    _plot = state.get().get("plot", {})
                    _protagonist = _plot.get("protagonist", {}) if _plot else {}
                    _pname = _protagonist.get("name", "") if _protagonist else ""
                    if _pname:
                        if _lang_auto == "en":
                            sys_prompt = f"You control the protagonist named '{_pname}'. Do not control other characters.\n" + sys_prompt
                        else:
                            sys_prompt = f"あなたが操作する主人公の名前は「{_pname}」です。他のキャラクターを操作しないこと。\n" + sys_prompt
                    recent_actions = _get_recent_player_actions(h, n=5)
                    # In DEVIATE mode, don't pass recent actions (avoid suppressing deviations)
                    _ra = None if AUTO_PLAY_MODE == "deviate" else recent_actions
                    action = chat_player(last_gm_reply, sys_prompt, _ra, language=_lang_auto)
                    if action.startswith("[ERROR"):
                        error_print(f"Player LLM error: {action}" if _lang == "en" else f"プレイヤーLLMエラー: {action}")
                        state.update({"end_reason": "player_error"})
                        save_session_json(h, title)
                        break
                    _act_lbl2 = "Your action" if _lang == "en" else "あなたの行動"
                    print(f"\n{_act_lbl2}: {action}")
        else:
            _lang = state.get().get("language", "ja")
            if _lang == "en":
                action = ask("\nYour action: ")
            else:
                action = ask("\nあなたの行動: ")

        if not action:
            continue

        if action in ("/help", "/h"):
            show_help()
            continue

        if action == "/quit":
            _lang = state.get().get("language", "ja")
            if _lang == "en":
                print("Quitting.")
            else:
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
            # If last message is assistant, remove it and regenerate.
            # If last is user (unanswered due to error), reuse that user message.
            retrying_assistant = h and h[-1]["role"] == "assistant"
            if retrying_assistant:
                h.pop()
                # strong mode: roll back ptr advanced by the previous _after_reply()
                if _is_strong():
                    s = state.get()
                    ptr = s.get("beat_ptr", 0)
                    if ptr > 0:
                        new_ptr = ptr - 1
                        # Also reset the done flag at the rolled-back position
                        queue = s.get("beat_queue", [])
                        if new_ptr < len(queue) and queue[new_ptr]["done"]:
                            queue[new_ptr] = dict(queue[new_ptr])
                            queue[new_ptr]["done"] = False
                        state.update({"beat_ptr": new_ptr, "beat_queue": queue})
            reply = call_gm(_build_api_messages(h))
            _lang = state.get().get("language", "ja")
            if reply == "[CONTEXT_LIMIT]":
                if _lang == "en":
                    system_print("Context limit reached. The story ends here.")
                else:
                    system_print("コンテキスト上限に達し続行不可能の為、物語をここで終了します。")
                state.update({"end_reason": "context_limit"})
                save_mod.save(state.get(), h)
                break
            if reply.startswith("[ERROR"):
                if _lang == "en":
                    error_print("Failed to generate response. You can /retry.")
                else:
                    error_print("応答生成に失敗しました。/retryで再試行できます。")
                pending_failed = True
                continue
            pending_failed = False
            h = hist.add_assistant(h, reply)
            _after_reply(reply)
            if check_ending(reply):
                _use_beat_suppression = _is_strong() or (_is_adaptive() and state.get().get("adaptive_replotted", False))
                if _use_beat_suppression and not state.get().get("ending_suppressed", False):
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
            _lang = state.get().get("language", "ja")
            if _lang == "en":
                system_print(f"Unknown command: {action}  Type /help for a list.")
            else:
                system_print(f"コマンドにありません: {action}　/help で一覧を確認できます。")
            continue


        if action == "/hint":
            hint_base = hist.build_for_api(h)
            # If the last message is a user message (unanswered due to error), remove it to avoid duplication
            if hint_base and hint_base[-1]["role"] == "user":
                hint_base = hint_base[:-1]
            # If the last message is not assistant (empty history etc.), skip hint
            _lang = state.get().get("language", "ja")
            if not hint_base or hint_base[-1]["role"] != "assistant":
                if _lang == "en":
                    system_print("Need at least one GM response before showing hints.")
                else:
                    system_print("ヒントを表示するには最初のGM描写が必要です。")
                continue
            if _lang == "en":
                hint_content = "Suggest 3-4 actions the player can take in the current situation. Format: start each line with '・', describe each action in 10-20 characters. No explanation needed."
            else:
                hint_content = "今の状況でプレイヤーが取れる行動を3〜4つ提案してください。形式：各行を「・」で始め、行動を10〜20字で簡潔に記述する。説明や補足は不要。"
            hint_msg = hint_base + [{"role": "user", "content": hint_content}]
            call_gm(hint_msg)
            continue

        # Dice roll (only when use_dice=True; exclude system-forced ending actions)
        is_forced_ending = action.startswith("（物語を終わらせてください）") or action.startswith("(Please end the story)")
        _lang = state.get().get("language", "ja")
        dice_result = dice_mod.judge(action, h, language=_lang) if (state.get().get("use_dice", True) and not is_forced_ending) else None
        if dice_result and dice_result.get("error"):
            if _lang == "en":
                error_print("Dice roll failed (API error or JSON parse failure). Continuing without roll.")
            else:
                error_print("ダイス判定に失敗しました（APIエラーまたはJSON解析失敗）。判定なしで続行します。")
            dice_result = None
        elif dice_result:
            dice_mod.display_result(dice_result, language=_lang)
        user_msg = _build_user_msg(action, dice_result)
        h = push_user(h, user_msg, pending_failed)

        # GM character comment + turning-point flag
        _handle_gm_char_and_turning_point(action, h)

        reply = call_gm(_build_api_messages(h))

        if reply.startswith("[ERROR"):
            _lang = state.get().get("language", "ja")
            if _lang == "en":
                error_print("Failed to generate response. You can /retry.")
            else:
                error_print("応答生成に失敗しました。/retryで再試行できます。")
            # Keep the user message (with dice result) and continue.
            # It can be reused with /retry, or replaced if a different action is entered.
            pending_failed = True
            continue

        pending_failed = False
        h = hist.add_assistant(h, reply)
        last_gm_reply = reply
        _after_reply(reply)

        if check_ending(reply):
            # Suppress premature endings in strong / adaptive-replotted mode
            _use_beat_suppression = _is_strong() or (_is_adaptive() and state.get().get("adaptive_replotted", False))
            if _use_beat_suppression and not state.get().get("ending_suppressed", False):
                s = state.get()
                queue = s.get("beat_queue", [])
                ptr = s.get("beat_ptr", 0)
                queue, ptr, suppressed = beat_mod.handle_ending_suppression(queue, ptr)
                if suppressed:
                    state.update({"beat_queue": queue, "beat_ptr": ptr, "ending_suppressed": True})
                    # Strip ending marker and continue
                    cleaned_reply = h[-1]["content"].replace(ENDING_MARKER, "").strip()
                    h[-1] = {"role": "assistant", "content": cleaned_reply}
                    last_gm_reply = cleaned_reply  # Update so player LLM does not receive the marker
                    continue

            h, quit_ = handle_ending(h)
            if AUTO_PLAY_MODE or DEBUG_MODE:
                save_session_json(h, title)
            if quit_:
                break

if __name__ == "__main__":
    main()
