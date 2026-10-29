# ナラティブインタラクト — 設計引継書

LM Studio用インタラクティブフィクションシステム。
ジャンルとタイトルを入力するだけでGM（LLM）が物語を生成し、プレイヤーが行動を入力して進行する。
自動プレイモード（AUTO_PLAY_MODE）ではプレイヤーもLLMが担当する。

対象モデル：**Gemma4 12B**（LM Studio経由）

---

## リポジトリ運用方針（セッション跨ぎ必読）

- **narrative-interact**（このリポジトリ・本流）：安定版。ユーザーが配布・使用する版。慎重に変更する。
- **narrative-interact-adaptive**（フォーク）：不安定版・実験場。試験的修正はここで先行実装し、安定確認後に本流へマージする。

---

## 現在の開発方針（セッション跨ぎ必読）

**strongモードは完成・凍結。一切触らない。**
- strongは5本のログ検証済み（2026年10月21日）。ダイジェスト化なし、全beatクリア、全end_reason="ending"。
- 平均11〜12ターンはプロット密度に対して適切と判断。ターン数の引き延ばしも不要。
- **strongのプロンプト・コード・設定は今後いかなる修正も行わない。**
- **新しい修正を加える前に「strongに影響しないか」を必ず確認すること。**

**全モード検証完了。v1.0.0リリース済み（2026年10月26日）。**
- strongモード：凍結済み。
- adaptiveモード：通常・逸脱バッチ各5本で全ending正常終了を確認済み（2026年10月24日）。
- offモード：通常・逸脱バッチ各5本で全ending正常終了を確認済み（2026年10月24日）。平均30ターン程度。
- improvモード：通常・逸脱バッチ各5本で全ending正常終了を確認済み（2026年10月24日）。平均30ターン程度。
- 40ターン到達ケースはauto_playのプレイヤーLLM固有の細切れ行動が原因。手動プレイでは再現しない。
- 「実験的モード」表示は全モードで廃止。

**offモードの現状**
- 誘導形beat injectionを実装済み（プロットに沿うよう誘導するが逸脱は許容）。
- beatキューが尽きたらsoft ending promptをinjection。

**improvモードの現状**
- 通常・逸脱バッチ各5本で全ending正常終了を確認済み（2026年10月24日）。
- 手動での逸脱プレイでも30ターン以内で完了を確認。

---

## 作業ルール（セッション跨ぎ必読）

- **実装前に必ずユーザーに確認を取ること。** 内容を提示して承認を得てから実装する。
- 上位モデルからの分析・意見がある場合は、その内容を直接読んで照合してから実装すること。
- **新セッション開始時はこのファイル（CLAUDE.md）を最初に読むこと。**
- **ファイルを変更したら必ずgit pushすること。**

### plot_modeの修正優先度について

物語の軸（plot_mode）は以下の4種：
1. off：プロット参照・誘導（beat injectionで誘導するが逸脱自由）
2. adaptive：プロット参照・適応（逸脱検出→プロット再生成→beat制御で着地）
3. strong：プロット参照・強拘束（強制回収）
4. improv：プロットなし・即興

**「必ず回収・終わらせる」責務を持つのはstrongとadaptive（再生成後）。** off/improvにプロット回収を求めない。
**共通の最重要ゴールは「終われること」。**

**strongのプロンプトは一切変更しない。** off/adaptive/improvの改善のみ行うこと。strongへの影響がゼロであることを確認してから実装すること。

---

## ファイル構成

| ファイル | 役割 |
|---------|------|
| main.py | エントリポイント。ゲームループ、コマンド処理、AUTO_PLAY_MODE制御 |
| prompt.py | SYSTEM_GM_BASE（GMシステムプロンプト）、build_start_message() |
| api.py | LM Studio APIへのchat()、chat_player()呼び出し |
| state.py | ゲーム状態（ジャンル、タイトル、ターン数等） |
| history.py | 会話履歴管理 |
| plot.py | プロット生成（GMが最初に作る物語の骨格） |
| beat.py | ビート管理（プロット進行の節目） |
| save.py | セーブ/ロード |
| display.py | 表示ユーティリティ（gm_print, system_print等） |
| dice.py | ダイス判定 |
| config.py | LM Studio接続設定 |

---

## 主要プロンプトの設計思想

### SYSTEM_GM_BASE（prompt.py）

GMの行動原則を定義する。**追加するルールは必ず既存ルールと衝突しないか確認すること。**

主な制約の経緯：

- **地の文禁止事項**（感情・内面・意味付け）
  → GMが主人公の内面を代弁する問題への対処。外から観察できる事実のみ書く原則。

- **選択肢の箇条書き禁止**
  → GMが「A/B/C？」と聞く問題への対処。状況を描写して止め、プレイヤーが自分で判断する。

- **同一対象への反復調査制限**
  → プレイヤーが同じ場所を何度も調べる際に無限に新情報を生成しないため。

- **エンディング条件の詳細化**
  → 「帰宅」「休息」をエンディングとしてしまう問題への対処。葛藤の解消を明確に定義。

- **NPC台詞の制限**
  → NPCが主人公の行動の意味・内面をテーマ的に代弁する問題への対処。

### PLAYER_SYSTEM_NORMAL / PLAYER_SYSTEM_DEVIATE（main.py）

AUTO_PLAY_MODEでのプレイヤーLLMのシステムプロンプト。

- NORMAL：主人公として臨機応変に行動
- DEVIATE：「GMが提示した展開・誘導・フックを敢えて無視するか、逆の行動をする」という能動的な逸脱フレーミング。固執ループ抑止ルールはNORMALより少なく逸脱性を維持。

主な制約の経緯（NORMAL）：

- **繰り返し禁止**（直前と同じ対象・動作の組み合わせ禁止、3回同種行動で移動）
  → 自動プレイ時にプレイヤーLLMがループする問題への対処。
  → 例：カップを取る→置く→取る→置くのループ、手を握る→握りしめる→力を込めるのループ。

- **失敗対象への固執禁止**（同じ対象に2回連続失敗したら別の対象へ）
  → プレイヤーLLMが失敗した対象に延々と試行し続ける問題への対処。

- **内面行動の禁止**（外から観察できない行動は出力しない）
  → 「覚悟を決める」等の内面行動をプレイヤーLLMが出力する問題への対処。

- **世界観外アイテムの持ち込み禁止**
  → ホラー医療もので「銃」を使うような世界観不整合への対処。

DEVIATE固有：
- **同一対象への動詞変更ループ抑止**（同じ対象への行動が動詞を変えながら3回続いたら別対象へ）
  → 「首を絞める→力を込める→床に叩きつける」のような動詞変更ループへの対処。

---

## 残存問題（未解決）

完全解消はモデル依存。プロンプトで抑制済みだが確率的に発生する。

### 問題A：GM地の文への内面・意味付けの混入
「疲れが色濃く浮かぶ」「誇りが宿る」等の形容詞・副詞レベルの内面表現がGM地の文に出続ける。
長い物語の後半やクライマックスで崩れやすい。
→ 地の文禁止ルール、クライマックスでの免除は文字数のみとする追記で抑制済み。

### 問題B：着地点先取り
endingフィールドの動機語・テーマ語（「執着」「守りたかったもの」等）を、GMがエンディング前のNPCの台詞や地の文で使い始める。
ミステリーなど動機が物語の核となるジャンルで発生しやすい。
→ 着地点先取り禁止ルール・動機直接説明禁止ルール・endingフィールドへの動機語排除指示で抑制済み。

### 問題C：プレイヤーLLMの対象言い換えループ
「兵士A」「重装兵」「前方の兵」のように対象名を毎回微妙に変えながら、実質的に同じ集団への同じ行動を繰り返す。
既存の「同じ対象への3回連続で別の場所へ移動」ルールは個別対象を判定するため、集団を相手にした場合は抜け穴になる。
→ 「失敗した目標・場所には固執せず、別の目標・別の場所への行動を優先すること」を追加で抑制済み。

### 問題D：off/improvモードで40ターン以内に終わらないことがある
プロット拘束がないため、GMがエンディング機会を認識できず40ターン上限に達する。
→ off・on・improvの3モードに「エンディングの機会を見つけたら迷わず終わらせること。プロット回収より完結を優先する」を追加済み。完全解消はモデル依存のため、UIに「実験的モード」と表示して周知する方針。

---

## GMプロンプトの構造

prompt.pyのGMプロンプトは2層構造になっている。新しいルールを追加するときは必ずどちらに入れるかを意識すること。

### SYSTEM_GM_BASE（固定層）
**ジャンル・プロット・プレイモードに関係なく、すべてのゲームで常に有効なルール。**
- 地の文禁止事項、NPC台詞制限、エンディング条件など「普遍的な原則」がここに入る。
- ここに追加するルールは全ジャンル・全プロットに影響する。影響範囲が広いので慎重に。

### build_system_prompt()の動的追加部（可変層）
**ジャンル・プロット内容・プレイモードによって変わるルール。**
- `【文体】`：プロットのstyleフィールドから生成。ジャンルごとに異なる。
- `【ジャンル制約】`：genre_traitsのtrue/falseで切り替わる。戦闘あり/なし、謎解きあり/なし等。
- `【プロット（GMのみが知る設計図）】`：プロット内容（登場人物・着地点・反転等）をそのまま渡す。
- `【物語の軸】`：PLOT_MODE_RULES（off/on/strong/improv）で切り替わる。

**判断基準：** 「このルールはどのジャンル・どのプロットでも必要か？」→YES なら固定層、NO なら可変層。

---

## プロンプト修正の原則

1. **修正前に既存ルール全体を読む**。特にprompt.pyのSYSTEM_GM_BASEは長い。
2. **1つの問題に対して最小限のルール追加**。肥大化を防ぐ。
3. **追加したルールは必ずこのファイルに経緯を記録する**（セッション跨ぎの記憶喪失対策）。
4. **ジャンル固有の問題か汎用の問題かを区別する**。ジャンル固有なら修正不要なことが多い。
5. **GMとプレイヤーの両方のプロンプトへの影響を確認する**。
6. **固定層か可変層かを判断してから追加する**（上記「GMプロンプトの構造」参照）。

---

## テスト方法

```bash
# 手動プレイ
python main.py

# 手動プレイ＋デバッグ出力
python main.py --debug

# 自動プレイ（通常モード）
python main.py --normal

# 自動プレイ（逸脱モード）
python main.py --deviate

# バッチ実行（ランダムなジャンル・タイトルでN回連続自動プレイ）
python main.py --normal --batch 5
python main.py --deviate --batch 3
```

---

## リリース目標

対象ユーザー：ローカルLLM利用者（LM Studio使用者）
ターゲットモデル：Gemma4 12B
公開形式：GitHub（v1.0.0）

---

## 修正履歴

時系列順。解決済みの問題・バグはここに記録する。

### 2026年10月（commit 94dc59d）：上位モデル洗い出しバグ11件修正

- beat.advance() のビート既読判定ずれ（ptr と actual_idx のずれ）
- 空のGM応答で自動プレイが無限ループ → `"[ERROR: empty response]"` を返すよう修正
- /retry でビートが1つ飛ぶ → beat_ptr を1つ戻し done フラグも復元
- ファイル名の特殊文字処理 → Windows/Linux 共通の禁止文字を re.sub で置換
- LLM出力が想定外の形でクラッシュ → protagonist/リスト系フィールドの型チェック追加
- beat.build_queue の characters フォールバック（`{"sword_master": "説明文"}` 形式への対応）
- エンディング抑止後も last_gm_reply に【エンディング】が残る → cleaned_reply で更新
- /hint でユーザーメッセージが2つ連続 → hint 用の base から末尾の user メッセージを除去
- エピローグが「エンディング後の描写禁止」ルールとぶつかる → EPILOGUE_PROMPT に適用外旨を追記
- 初回生成失敗時の扱い → 自動プレイ時に空文字を返す、手動プレイ時に pending_failed = True を設定
- 自動プレイに終了の保証がない → AUTO_PLAY_MAX_TURNS = 40 を追加

### 2026年10月（commit 66b982e）：GM地の文違反・NPCテーマ代弁の根本原因除去

群像ドラマ/日常ジャンルで GM地の文への内面混入・NPCのテーマ代弁が多発。
根本原因：styleフィールドに「内面を対比させる」等が入り、theme_closure・peak・risks・loss・gain等の抽象語がGMに渡っていた。

- PLOT_SCHEMA のstyleフィールド指示に「内面・心情・感情・解釈を求める表現は書かないこと」を追加
- build_system_prompt() 【文体】に「地の文ルールと衝突する場合は地の文ルールを優先する」を追加
- climax.loss / climax.gain / climax.peak / risks / ending_note.theme_closure をGMに渡さないよう削除
- beat.py _TEMPLATES の misconception と twist に「その事実が主人公にとって何を意味するかはNPCも地の文も言わないこと」を追加
- 自動プレイ時に protagonist.name を sys_prompt 先頭に付加（1ターン目で他キャラを操作する問題への対処）

### 2026年10月（session_01RKyUp4sTCBCsw1w27GGkwy）：各種プロンプト修正

**着地点先取り禁止（問題Bへの対処）**
ミステリー「止まった秒針」テストで、endingフィールドの動機語をGMがエンディング前に使い始める「着地点先取り」が深刻に残存。
- SYSTEM_GM_BASE 【出力ルール】に追加：「プロットの着地点・endingに記された言葉・概念・動機を、エンディング着地点の情景描写にのみ使用してよい。それ以前のターンのNPCの台詞・地の文のいずれにも使ってはならない」
- 同じく追加：「登場人物の動機・目的・執着の内容は、NPCが台詞で直接説明してはならない。証拠・物・状況・行動として示し、プレイヤーが読み取る形にすること」
- PLOT_SCHEMA / styleフィールドに違反例3つを追加（✗「内省的なモノローグを対比させる」等）
- build_system_prompt() の着地点渡し部分のラベルに「（情景のみ。動機・感情・テーマ語は含めない）」を追加

**問題A追加対策**
家族ものミステリー「父の帰還と消えた遺書」テストで抽象的格付け（「聖域」「砦」「核心」等）が連続発生。
- SYSTEM_GM_BASE 地の文禁止事項の抽象的格付け例示に「砦」「核心」「守り抜いた場所」を追加
- PLOT_SCHEMA / endingフィールドに動機語禁止の明示を追加（「〜したかった」「〜への執着」等は使わず情景・人物・物・動作のみで記述）

**off/on/improvモードの「完結優先」回復**
`plot_mode: "off"` で通信成功まで達成したのにエンディングが出ずターン上限になる問題。
エンディングルール群の積み重なりでGMが「本当に終わっていいのか」を迷うようになっていた。
- PLOT_MODE_RULES の off・on・improv に「エンディングの機会を見つけたら迷わず終わらせること。プロット回収より完結を優先する」を追加

**操作対象の「」明示**
「制御パネル」「マニュアルスイッチ」等の操作可能な対象が地の文に埋まり、ゲーム性が薄れていた。
- SYSTEM_GM_BASE 21行目を「プロットにかかわるものおよび場面内で操作・調査・移動の起点となる対象は「」で表現する」に変更

**その他（同セッション）**
- NPC台詞制限に追加：「反転・誤認の訂正・隠された真意はNPCが直接説明せず、出来事・状況の変化として示すこと」
- 300字ルールに追記：「この免除は文字数のみ。地の文禁止事項はクライマックス・エンディングでも免除されない」
- フック回収（hook.closing）の指示を【プロット】セクションと【末尾の回収と余韻】セクションの両方に追加
- 放棄・降参のGM即受理問題：「放棄の意思が繰り返され新たな変化がない場合のみエンディングに導いてよい。ただし第三者が代わりに解決・解説する展開は避けること」を追加
- GM出力肥大化対策：SYSTEM_GM_BASE 【出力ルール】に「1ターンの描写は300字以内を目安にすること。クライマックス・エンディング・重大失敗の描写はこの制限を超えてよい」を追加
- characters のキー形式不一致（`{"sword_master": "説明文"}` 形式）：prompt.py と beat.py の両方にフォールバック処理を追加
- PLAYER_SYSTEM_NORMAL/DEVIATE に追加：繰り返し禁止・失敗対象への固執禁止・内面行動禁止・世界観外アイテム持ち込み禁止

### 2026年10月（session_01RKyUp4sTCBCsw1w27GGkwy）：UI改善・バリデーション追加

- main.py：軸選択画面の auto_note を「（40ターンで強制終了する場合あり）」に変更（手動プレイ時にも表示）
- main.py：ジャンル・タイトルの空欄入力を禁止し再入力を促すバリデーションを追加
- main.py + README：off/improvモードを「実験的モード」として明示
- README：`## 開発経緯` セクションを追加（note.com 関連記事3本へのリンク含む）

### 2026年10月（commit 7aa5e9e）：バッチモード改善

**SF偏り解消**
バッチ実行時にLLMがジャンルを自動生成するとSFに偏る問題（Gemma4 12Bのバイアス）。
- `BATCH_GENRES`（12ジャンル：ホラー・ミステリー・ファンタジー・SF・時代劇・現代ドラマ・サスペンス・青春・怪談・冒険・犯罪・日常）を事前定義
- バッチ実行ごとにシャッフルして順番に使用。12回超えたら再シャッフル
- `generate_genre_title()` をジャンル指定時はタイトルのみ生成するよう変更

**バッチ用ダイス設定**
バッチ実行時にダイス有無・難易度の選択肢がなく `use_dice: True` / `normal` 固定だった問題。
- バッチ開始前に `ask_use_dice()` / `ask_difficulty()` を1回だけ手入力
- `BATCH_USE_DICE` / `BATCH_DIFFICULTY` グローバルで保持し、全セッションに適用

### 2026年10月（commit 0e6c063）：PLAYER_SYSTEM_DEVIATE 固執ループ抑止

deviate モードで「日常」「ミステリー」各1本が turn_limit（40ターン強制終了）に達した。
原因：PLAYER_SYSTEM_DEVIATEに繰り返し抑止ルールが一切なく、同一対象への行動を動詞だけ変えながら無限ループした（例：首を絞める→力を込める→床に叩きつける→引きずり回す、を何十ターンも）。

- PLAYER_SYSTEM_DEVIATEに「同じ対象への行動が動詞を変えながら3回続いた場合も、別の対象・別の場所への行動に切り替えること」を追加
- 「直前と同じ対象・動作の組み合わせ禁止」「失敗2回連続で別対象へ」はDEVIATEの逸脱性維持のため追加しない

### 2026年10月（commit 1030a86）：GM固執ループ時のバッドエンド誘導ルールを追加

onモードのdeviateバッチで40ターン超えが多発。プレイヤーLLMが脱線・固執してもGMが「葛藤未解消」と判断してエンディングを出せずループする問題。
SYSTEM_GM_BASEには「逸脱した場合エンディングに導く」ルールがあったが、「固執が継続中」のケースへの対処が抜けていた。

- SYSTEM_GM_BASE【エンディング】に追加：「プレイヤーが同一対象・同一行動への固執を繰り返し、プロットの主要な葛藤に向かう気配がない場合、その固執の結末（失敗・消耗・周囲の変化・状況の収束）を描写してバッドエンドとしてエンディングに導いてよい」
- ターン数に依存しないためhand動プレイにも有効

### 2026年10月（commit f62434d）：GMバッドエンド誘導の適用範囲を拡大

ミステリー「嘘の残滓」（onモード・deviate）で40ターン強制停止。
若手巡査の首を掴む→締める→踏む→掴む…と動詞を変えながら同一対象に固執し続け、GMがエンディングに導けなかった。
原因：前回追加したルールの「同一行動」条件が厳しすぎて、動詞変更ループを取りこぼしていた。

- SYSTEM_GM_BASE【エンディング】の条件を「同一対象・同一行動への固執」→「同一対象への行動を繰り返し」に変更（「同一行動」削除）

### 2026年10月（commit 1eb3907）：バッドエンド誘導ルールをstrongを除く可変層に移動

strongモードへの影響を排除するため、SYSTEM_GM_BASE（固定層）にあった2行をPLOT_MODE_RULESの可変層に移動。
あわせて「プロットと無関係な行動が続く漂流」への対処ルールを新規追加。

- SYSTEM_GM_BASEから削除：逸脱時エンディング誘導・同一対象固執バッドエンド誘導
- off/on/improvに追加（3行）：
  1. プレイヤーの逸脱時エンディング誘導（移動）
  2. 同一対象固執バッドエンド誘導（移動）
  3. プロットと無関係な行動が複数ターン続き進展しない場合の収束エンディング誘導（新規）
- strongには適用しない

### 2026年10月（commit 610841c）：off/on/improvにエンディング誘導ルールを復元

994c001のリセットで消えていたエンディング誘導ルール群をoff/on/improvの可変層に再追加。
strongには一切触れない。

追加内容（3モード共通）：
- 完結優先ルール（「エンディングの機会を見つけたら迷わず終わらせること。プロット回収より完結を優先する」）
- 逸脱時エンディング誘導（「逸脱した場合、世界の変化を示してエンディングに導く」）
- 固執バッドエンド誘導（「同一対象への行動を繰り返し葛藤に向かう気配がない場合、固執の結末を描写してバッドエンドに導く」）
- 漂流収束誘導（「無関係な行動を複数ターン続け進展がない場合、状況の収束としてエンディングに導く」）※off/improvのみ
- 逸脱エンディング受け入れ（「完結できる着地点に達した場合それをエンディングとして受け入れてよい」）

### 2026年10月（commit 7e5c3d0）：check_fixation による固執ループ検出＋エンディング強制injection

on/deviateバッチで固執ループ時にGMがエンディングに導けず40ターン強制停止になるケースへの追加対処。
プロンプトによるGM誘導だけでなく、コード側からも固執を検出してinjectionでエンディングを強制する仕組みを追加。

- `api.py` に `check_fixation(actions: list[str]) -> bool` を追加
  - プレイヤーの直近3行動をLLMに渡し「ループ状態か」をyes/noで判定
  - 温度0.0・max_tokens=4の軽量呼び出し
- `main.py` の `_build_api_messages()` 末尾に固執ループ検出+injection処理を追加
  - `_is_strong()` がFalseのとき（off/on/improvのみ）に発動
  - check_fixationがTrueを返した場合、GMへのユーザーメッセージ末尾に「固執の結末を描写してエンディングに導くこと」のinjectionを挿入
  - DEBUGモード時は `[FIXATION] loop detected` をstderrに出力

**5本のon/deviateバッチ実行結果（実装後初テスト）：全5本がend_reason: "ending"で正常終了**
- 怪談「黄昏の葬列」：プロット着地点通りのエンディング
- 時代劇「残響の刃」：8ターンで漂流バッドエンド（水桶→水面→地面の繰り返し→GMが収束）
- 現代ドラマ「残響の街」：逸脱エンディング受け入れ（レコードをカウンターに置く→開店）
- 青春「放課後の残光」：固執バッドエンド（柱の陰でじっとしている→GMが収束）
- 日常「放課後の図書室」：漂流バッドエンド（書架を移動し続ける→GMが時間切れで収束）

### 2026年10月（commit 610841c相当）：逸脱エンディング受け入れルールを追加

「ドラゴンを無視して温泉で結婚」のような、プロットの主要葛藤を回収せず別の文脈で自力エンディングを作る逸脱プレイをGMが受け入れられるようにした。
strongへの影響ゼロが必須条件。

- off/on/improvに追加（1行）：「プレイヤーが主要な葛藤とは無関係な場所・状況で、物語として完結できる着地点（関係の変化・決断・帰着）に達した場合、GMはそれをエンディングとして受け入れてよい」
- strongには適用しない

### 2026年10月（今セッション）：README修正・off/normalバッチ検証

**README修正（実測値への更新）**
- 想定ターン数「20〜40ターン」→「10〜20ターン程度（最大40ターン）」に修正（strong実測12〜13T、off/deviate実測9〜20T）
- システムプロンプトのトークン数「約7,700」→「約10,000」に修正（実測値）
- 推奨コンテキスト長の説明を「システムプロンプト約10,000トークン＋物語進行分で計約30,000トークン」に修正

**off/normalバッチ5本の検証結果**
全5本がend_reason: "ending"で正常終了（turn_limitなし）。
- サスペンス「嘘の断片」：24ターン・自然なending ✅
- ミステリー「残響の密室」：25ターン・自然なending ✅
- ホラー「底の無い密室」：28ターン・自然なending ✅
- 冒険「刻の残滓を求めて」：5ターン・早期ending ⚠️（プロット未展開のまま「破片入手＝目標達成」と判断）
- 青春「放課後の残響」：7ターン・早期ending ⚠️（葛藤ゼロのまま「ミサキと会えた＝機会」と判断）

**早期ending問題の原因と判断**
原因：「完結優先ルール」と「着地点に達したら迷わず締める」ルールをGMが甘く解釈して早期発火。
修正案（最低ターン数をコード側で設ける等）を検討したが、逸脱エンドとの区別が困難なため現状維持。
off/on/improvは「実験的モード」表示のまま継続する方針。

### 2026年10月（commit 8d01ba7）：逸脱エンドと衝突するルールを削除

`build_system_prompt()` の可変層（ending渡し部分）に入っていた「着地点に含まれる主要人物・場面がまだ物語に登場していない間は、エンディングにしない」を削除。
逸脱エンド（ドラゴン退治のはずが温泉街で結婚等）では主要人物が登場しないまま終わるのが正常なため、このルールが逸脱エンディング受け入れルールと真っ向から衝突していた。
strongはbeatで主要人物登場を制御しているため実害なし。

### 2026年10月（今セッション・続き）：上位モデルレビュー指摘への対処

上位モデルのレビュー（attachment.txt）を受け、4点を実装。

**1. SYSTEM_GM_BASEの続行条件2行を可変層へ移動**
上位モデル指摘：SYSTEM_GM_BASEの「エンディング候補を思いついたら終了してよい」「欲求が満たされた時点で終了してよい」がstrongモードのPLOT_MODE_RULESと矛盾。
- SYSTEM_GM_BASEから削除（47・50行目相当）：
  - 「エンディング候補を思いついたら、それ以上の展開を探さず終了してよい」
  - 「主人公の主要な欲求・目的が満たされた時点で物語を終了してよい」
- off/on/improvの各PLOT_MODE_RULESに移動（strongには一切触れない）

**2. check_fixation を AUTO_PLAY_MODE 限定・2段階化**
上位モデル指摘：手動プレイでも発動・1回で強制が致命的（扉3回調べるだけで終了）。
- AUTO_PLAY_MODE がTrueのときのみ発動
- fixation_countをstateで管理：1回目は「物語を収束へ向けて進めること」の軽量injection、2回目で「このターンでエンディングに導くこと」の強制injection
- state.pyの初期化にfixation_count・fixation_endingを追加

**3. end_reason="fixation"を追加**
上位モデル指摘：固執検出で強制されたエンディングをendingと区別できない。
- handle_ending()でfixation_endingフラグを確認し、end_reason="fixation"を記録
- それ以外は従来通りend_reason="ending"

**4. onモードに「無関係な行動が続いたら収束エンディング」を追加**
上位モデル指摘：offには存在するがonには削除されていた。onモードのミステリーで対象を回すループが40ターン打ち切りになっていた原因。
- onのPLOT_MODE_RULESに「無関係な行動を複数ターン続け進展がない場合、状況の収束としてエンディングに導く」を追加

**5. fixation injection文に着地点不使用の指示を追加（上位モデル指摘4）**
強制injection時にGMが手近な着地点テキストを貼る危険を防ぐため：
- fixation_count >= 2 の強制injection文末に「着地点の文は使わず、現在の状況から自然に導かれる結末を書くこと」を追加

**6. ダイス成功タグのending一文を削除（上位モデル指摘4）**
`_build_user_msg()` の decisive/normal_success タグの「この行動がプロットの目標を直接・完全に達成した場合のみエンディングに導いてよい。」を削除。
early endingの直接的な原因の一つだった。

### 2026年10月（commit 5ef5702）：直前ターン新情報時のエンディング禁止条件を追加

26Bモデルのonモード・normalプレイログで「保管庫の場所がわかった→即エンディング」の早期終了が発生。
GMが「情報獲得」を「目標達成」と誤解してエンディングを発火した。

- off/on/improvの各PLOT_MODE_RULESに追加：「直前のターンで新たな目標・手掛かり・情報が提示された場合、それを無視してエンディングにしない」
- strongには一切触れない

### 2026年10月（commit 1b92343）：adaptiveモードを本流にマージ（onモードを置き換え）

`narrative-interact-adaptive` フォークで検証済みの adaptive モードを本流 `narrative-interact` に移植。
onモードを廃止し、adaptiveモードで置き換え（UI表示・内部 plot_mode 名ともに `adaptive`）。

**adaptiveモードの設計思想**
- 逸脱を「失敗」ではなく「物語の転換点」として扱う
- 逸脱が大きいと判断したら直近の展開から新プロットを再生成し、beat制御で着地させる
- 再生成後はstrongモードと同等の着地保証（ターン上限を実質的に回避）
- ジャンル変化OK（例：ギャグ→神話）

**逸脱検出の仕組み（2段階）**
- 毎ターン `check_deviation()` を呼び出してyes/no判定（temperature=0.0, max_tokens=4）
- deviation_count >= 3：警告injection（「エンディングの機会があれば迷わず終わらせること」）
- deviation_count >= 5：`_do_adaptive_replot()` でプロット再生成 → beat制御に移行

**変更ファイル（本流）**

- `state.py`：`deviation_count` / `peak_deviation_count` / `adaptive_replotted` を追加
- `api.py`：`check_deviation()` / `regenerate_plot()` を追加
- `prompt.py`：PLOT_MODE_RULES の `"on"` → `"adaptive"` に変更、`build_adaptive_replot_system_prompt()` を追加
- `main.py`：
  - PLOT_MODE_LABELS の2番を adaptive に変更
  - `_is_adaptive()` / `_get_plot_keywords()` / `_do_adaptive_replot()` / `_build_adaptive_beat_queue()` を追加
  - `_build_api_messages()` に adaptive 逸脱検出→警告injection→再生成→beat着地ロジックを追加
  - `_after_reply()` を adaptive_replotted 時もビート進行するよう更新
  - エンディング抑止条件を adaptive_replotted 時にも適用（3箇所）
  - 25ターン超の収束injection を追加（off/adaptive/improvのみ）

**strongへの影響：ゼロ。** adaptive処理はすべて `_is_adaptive()` ブロックで完全分離。

**UI変更**
- adaptiveモードを「実験的」表示なしで提供（再生成後はbeat制御による着地保証があるため）
- 逸脱検出・再生成のシステムメッセージはDEBUG_MODEのみstderrに出力（プレイヤーには見せない）

### 2026年10月（commit 154c2ae / c876b70）：check_fixation削除・PLAYER_SYSTEM_DEVIATE刷新・adaptive正式化

**check_fixation の完全削除**
check_fixationはadaptiveモードへの移行に伴い不要となり削除済み。
- `api.py` から `check_fixation()` を削除
- `main.py` から fixation_count・fixation_ending・check_fixation呼び出しを削除
- `state.py` から fixation_count・fixation_ending を削除
- end_reason の "fixation" は廃止。現在の end_reason は "ending" / "turn_limit" / "player_error" の3種のみ

**PLAYER_SYSTEM_DEVIATE の刷新**
固執ループを抑制する多数のルールを削除し、「GMの誘導を敢えて無視するか逆の行動をする」という能動的な逸脱フレーミングに変更。
- 削除：「直前と同じ対象・動作の組み合わせ禁止」「失敗2回連続で別対象へ」等
- 残存：「同じ対象への行動が動詞を変えながら3回続いたら別対象へ」（DEVIATEの逸脱性維持のため最低限のみ）
- 効果：adaptiveモードのdeviate5本バッチで全ending正常終了を確認

**adaptiveモード【開発中】ラベル削除**
- `main.py` PLOT_MODE_LABELS および `ask_plot_mode()` から「【開発中】」を削除
- `README.md` / `README_EN.md` から「【開発中】」「[In Development]」を削除
- 根拠：通常・逸脱各5本バッチで全ending正常終了を確認済み

### 2026年10月（今セッション）：offモード通常・逸脱バッチ検証

**off/normalバッチ再検証（5本）**
全5本がend_reason: "ending"で正常終了。平均30ターン前後。Gemini評価良好。
早期ending（5〜7ターン）の再現なし。

**off/deviateバッチ検証（5本）**
全5本がend_reason: "ending"で正常終了。40ターンでエンディングに至ったケースが1件あり。Gemini評価良好。

**判断**
早期ending問題は実質的に解消。ただし40ターン到達ケースが存在するため「実験的モード」表示は維持する。
CLAUDE.md の「次のブラッシュアップ対象」をimprovに更新。

### 2026年10月（今セッション）：improvモード通常・逸脱バッチ検証

**improv/normalバッチ（5本）**
全5本がend_reason: "ending"で正常終了。平均30ターン。Gemini評価良好。

**improv/deviateバッチ（5本）**
全5本がend_reason: "ending"で正常終了。平均約30ターン。Gemini評価良好。1本のみ40ターン到達。
根本問題（プロット拘束なしによる漂流リスク）は未解決だが、手動プレイでは30ターン以内で完了することを確認。

### 2026年10月（commit 9a064bc）：improvモード「あなたは～として」表示を追加・全モード表示順を統一

improvモードでは`protagonist.get("name")`が常に空のため「あなたは～として、この物語を紡ぎます。」が表示されなかった。

- `api.py` に `extract_protagonist_name(opening_scene)` を追加（max_tokens=16, temperature=0.0）
  - GMが生成した開幕シーンから主人公名を抽出する軽量LLM呼び出し
  - 名前が明示されていない場合は「主人公」を返す
- `main.py` の主人公名表示ブロックを `call_gm()` の後に移動し全モードで統一
  - improvは `extract_protagonist_name(reply)` で名前を取得して表示
  - 他モードは `protagonist.get("name")` から取得（従来通り）
  - 表示順：本文 → 「あなたは{name}として、この物語を紡ぎます。」（全モード共通）
- strongへの影響ゼロ

### 2026年10月（今セッション）：「実験的モード」表示廃止・コンテキスト上限対処

**「実験的モード」表示を全モードで廃止**
- off/improv 通常・逸脱各5本バッチで全ending正常終了確認済み
- 40ターン到達ケースはauto_playのプレイヤーLLM固有の細切れ行動が原因（手動プレイでは再現しない）
- main.py `ask_plot_mode()` から `exp_note` と関連表示を削除
- README.md / README_EN.md の off/improv 行から実験的注記を削除
- CLAUDE.md の現状記述を「全モード検証完了・v1.0.0リリース準備段階」に更新

**コンテキスト上限到達時の専用終了処理を追加**
- api.py `chat()` でLM Studioの `exceed_context_size_error` / `exceeds the available context size` を検出 → `[CONTEXT_LIMIT]` を返す
- main.py `call_gm()` でリトライせず即返す
- 手動・自動プレイ両ループで「コンテキスト上限に達し続行不可能の為、物語をここで終了します。」を表示して終了
- end_reason="context_limit" として記録
- バッチ時は該当セッションのみ終了し次セッションへ継続

### 2026年10月（今セッション）：GMキャラクター機能・転換点による描写強化を実装

**GMキャラクター機能**
プレイヤーの行動に対し、選択したGMキャラクターが一言コメントを返す機能を実装。本文生成とは完全に独立した別呼び出し。

- `state.py`：`gm_character`（"none"/"tsukkomi"/"cynical"/"worrier"）を追加
- `display.py`：`gm_char_print()`（シアン表示）、`gm_turning_point_print()`（マゼンタ表示）を追加
- `api.py`：`GM_CHAR_PROMPTS`・`GM_CHAR_LABELS` dict、`generate_gm_char_comment()` を追加（temperature=0.9, max_tokens=32）
- `main.py`：`GM_CHARACTER_LABELS` dict、`ask_gm_character()` を追加。`start_new_game()` でAUTO_PLAY_MODE以外の時に選択画面を表示
- AUTO_PLAY_MODE時はコメント生成・表示をスキップ（バッチログに混入させない）
- キャラクターなし（"none"）選択時はLLM呼び出し自体をスキップ

**転換点による描写強化**
ビートが進んだターン（strong/adaptive/off）またはLLM判定で転換点を検出したターン（improv）に、GMへのinjectionで描写を強化する機能を実装。

- `state.py`：`turning_point_triggered`・`turning_point_injected` フラグを追加
- `api.py`：`check_turning_point()` を追加（improv用LLM判定、temperature=0.0, max_tokens=4）
- `main.py`：`_handle_gm_char_and_turning_point(action, h)` を追加
  - ビートモード（strong/adaptive-replotted/off）：beat_ptr > 0 かつ直前ビートdone = 転換点
  - improvモード：`check_turning_point()` 判定（未発動の場合のみ）
  - 転換点検出時：GMキャラコメント生成（gm_characterが"none"でない場合）＋`turning_point_triggered`をTrueに
- `_build_api_messages()` 末尾に転換点injection追加
  - `turning_point_triggered=True` かつ `turning_point_injected=False` のターンのみ発火
  - ユーザーメッセージ末尾に「このターンは物語の転機です。通常より詳細に、丁寧に描写すること。文字数制限は解除する。」を追加
  - `turning_point_injected=True` にセット（以降は再発火しない）
- 両機能の呼び出しを手動プレイループ・`run_single_session()`の両箇所に追加（strongは除外）
- strongへの影響ゼロ（`if not _is_strong():` ブロックで完全分離）

### 2026年10月（今セッション・続き）：GMキャラクター複数回発動バグ修正

初期実装でGMキャラコメントが1セッション中1回しか出ない問題。

**原因**：`_handle_gm_char_and_turning_point()` に `not turning_triggered` 条件があり、1回発動後に二度とTrueにならなかった。

**修正内容**
- `_handle_gm_char_and_turning_point()` の条件から `not turning_triggered` を削除（転換点ごとに毎回発動）
- `_build_api_messages()` で injection発火後に `turning_point_triggered=False` にリセット（injection済み後は再注入しない）
- `_after_reply()` で GM応答後に `turning_point_injected=False` にリセット（次の転換点で再び発火できるよう）

**動作フロー（修正後）**
1. 転換点検出 → `turning_point_triggered=True`、GMコメント表示
2. `_build_api_messages()` → injection発火、`turning_point_triggered=False` / `turning_point_injected=True`
3. GM応答後 `_after_reply()` → `turning_point_injected=False` にリセット
4. 次の転換点で1から繰り返し

### 2026年10月（今セッション）：バッチ処理でGMキャラクター選択対応・improvモード修正漏れ解消

**バッチ処理でGMキャラクター選択に対応**
バッチ実行時にGMキャラクターが常に"none"固定だった問題。バッチはデバッグ用途のためコメント出力も有効にした。
- `BATCH_GM_CHARACTER` グローバルを追加
- バッチ開始前に `ask_gm_character()` を1回呼び出し（`ask_use_dice()`/`ask_difficulty()` と同様）
- `run_single_session()` の `state.update()` に `"gm_character": BATCH_GM_CHARACTER` を追加
- `not AUTO_PLAY_MODE` ガードを削除（バッチでもGMキャラコメントを表示）

**improvモードの転換点検出が1回しか発動しない修正漏れを解消**
前セッションでbeatモードの `not turning_triggered` 条件を削除したが、improvモード側に同条件が残っていた。
- `_handle_gm_char_and_turning_point()` のimprovブロックから `if not turning_triggered:` を削除
- 全モードで転換点ごとに毎回GMキャラコメント・描写強化が発動するようになった

**転換点ターンのGM本文をマゼンタで表示する処理を追加**
`gm_turning_point_print()` はdisplay.pyに実装・importされていたが、呼び出し箇所がなかった（実装漏れ）。
- `call_gm()` 内の表示処理を `turning_point_injected` フラグで分岐
- フラグがTrueのターン（=転換点injection発火済み）は `gm_turning_point_print()`（マゼンタ）で表示
- それ以外は従来通り `gm_print()`（白）で表示

### 2026年10月（今セッション）：転換点検出バグ修正（off/adaptive/improv）

バッチ5本でGMキャラコメントも転換点マゼンタも一度も出なかった問題の原因調査・修正。

**バグ1：offモードでbeat_ptrが進まない**
`_after_reply()` が `strong` と `adaptive再生成後` のみビートを進めており、`off` が含まれていなかった。
転換点判定では `off` を beat モードとして `ptr > 0` で判定しているが、ptr が常に 0 のため一度も転換点が発火しなかった。
- `_after_reply()` の `is_beat_mode` に `or _is_off()` を追加

**バグ2：adaptive（再生成前）が転換点検出をスキップ**
`_handle_gm_char_and_turning_point()` の分岐が `is_beat_mode` と `is_improv` の2択で、
`adaptive`（再生成前）はどちらにも該当しないためスキップされていた。
- `is_improv` を `is_llm_judge` に変更し、`improv OR (adaptive かつ 再生成前)` の条件でLLM判定を行うよう修正

### 2026年10月（今セッション）：GMキャラクター・転換点をstrongモードにも対応

offモードのbuild_queue未呼び出しバグ（GMキャラコメント未発動）を修正し、あわせてstrongにも対応。

**offモードbuild_queue修正（commit eb00e95）**
offモードで `beat_queue` が常に空だったため、`beat_ptr` が進まず転換点が検出されず、GMキャラコメントが一度も発動しなかった。
- `start_new_game` / `load_session` / `run_single_session` の3箇所で `plot_mode == "strong"` → `plot_mode in ("strong", "off")` に変更

**strongモードへの対応（commit 9601314）**
`_handle_gm_char_and_turning_point()` 呼び出しを `if not _is_strong():` でガードしていたため、strongでGMキャラコメントと転換点injectionが発動しなかった。
- 2箇所の `if not _is_strong():` ガードを削除
- strongのプロンプト・beat制御・プロット生成には一切触れておらず、凍結ルールに抵触しない変更

---

### 次バージョンリリース方針（v1.1.0予定）

GMキャラクター機能・転換点による描写強化の動作試験完了後にv1.1.0としてリリースする。

**リリース手順**
1. README.md / README_EN.md のタイトルを `v1.1.0` に変更
2. `git tag v1.1.0` でタグを打つ
3. `git push origin v1.1.0` でGitHubにタグを上げる
4. GitHubのReleasesページで `v1.1.0` のリリースを作成

`v1.0.0` タグはそのまま残す（古いバージョンへのアクセス維持）。

**動作試験が完了するまでリリースしない。**

### 2026年10月（今セッション・続き）：GMキャラコメントをJSONログに記録

Gemini評価時にGMキャラコメントが「ログ非保持のためスキップ」と判定され、評価・デバッグ不能だった。

**変更内容**
- `state.py`：`gm_char_log: []` を初期値に追加
- `main.py` `_handle_gm_char_and_turning_point()`：コメント生成後に `state.gm_char_log` へ `{"turn": N, "character": "...", "comment": "..."}` をappend
- `save_session_json()` は `state.get()` をそのままJSONに書くため、追加実装なしで自動記録される

**ログフォーマット**
```json
"gm_char_log": [
  {"turn": 3, "character": "tsukkomi", "comment": "え、そこ調べます？"},
  {"turn": 7, "character": "tsukkomi", "comment": "また同じことしてる…"}
]
```

### 2026年10月（commit 2e96df4）：gm_char_logのturnが常に0になるバグを修正

サンプルログ確認で `gm_char_log` の全エントリが `"turn": 0` になっていることが発覚。

**原因**：`_handle_gm_char_and_turning_point()` 内で `s.get("turn_count", 0)` を参照していたが、`turn_count` は `state.init()` に定義されていないキーのためデフォルト値0が常に返っていた。

**修正**：`s.get("turn_count", 0)` → `sum(1 for m in h if m["role"] == "user")` に変更。引数 `h`（history）のuserメッセージ数から直接ターン数を算出するよう修正。

### 2026年10月（今セッション）：GMキャラ2種追加・選択UIのカーソルキー化・GM:色統一・README更新

**GMキャラクター2種追加**
- `all_positive`（全肯定）：何をやっても無条件に褒める。「天才！」「完璧な判断！」
- `easygoing`（のんき）：緊迫感ゼロのマイペース。「まあなんとかなるでしょ。」「ゆっくりいこう。」
- `api.py` の `GM_CHAR_PROMPTS` / `GM_CHAR_LABELS` に追加

**GMキャラクター選択UIをカーソルキー選択に変更**
- `readchar`（クロスプラットフォーム対応）を使用
- ↑↓キーで選択、Enterで決定
- `readchar`未インストール時は番号入力にフォールバック
- `requirements.txt` に `readchar` を追加
- `main.py` の `GM_CHARACTER_LABELS` dict を `GM_CHARACTER_OPTIONS` リストに変更
- `_select_with_cursor()` 関数を追加、`ask_gm_character()` を書き換え

**GM:プレフィックスの色統一**
- `display.py` `gm_char_print()`：`GM:` を通常GMと同じ青（BLUE）に、コメント本文はシアン（CYAN）のまま
- 変更前：`CYAN + "GM: {text}"` → 変更後：`BLUE + "GM:" + RESET + " " + CYAN + text`

**README.md / README_EN.md 更新**
- 動作環境に「対応OS：Windows / macOS / Linux」を追記
- `pip install -r requirements.txt` の行に `readchar` の記載を追加
- GMキャラクター選択表に全肯定・のんきを追加
- コンソール表示の説明を `GM:` 青・本文シアンに更新
- GMキャラクター選択が↑↓キー選択になった旨を追記

### 2026年10月（今セッション）：「全肯定」→「お調子者」に変更

褒め一辺倒の「全肯定」より、ノリよく盛り上がる「お調子者」の方がバリエーションが出ると判断。

- `api.py`：キー `all_positive` → `cheerful` に変更、プロンプトをノリよく乗っかるスタイルに変更
- `main.py`：`GM_CHARACTER_OPTIONS` の該当エントリを `("cheerful", "お調子者（ノリよく一緒に盛り上がる）")` に変更
- `README.md`：GMキャラクター表の「全肯定」→「お調子者」に更新
- `README_EN.md`：「All-Positive」→「Hype Man」に更新

### 2026年10月（今セッション）：GMキャラクターをシニカル固定・あり/なし選択に変更

シニカル5本バッチ検証でバリエーションが十分と確認。tsukkomi/worrier等は語尾・表現のパターン固着が問題で、プロンプトでは解消困難と判断。GMキャラクターをシニカル1種に固定し、選択肢をあり/なしのみに簡略化。

- `api.py`：`GM_CHAR_PROMPTS` / `GM_CHAR_LABELS` をシニカルのみに縮小（tsukkomi/worrier/cheerful/easygoing削除）
- `main.py`：`GM_CHARACTER_OPTIONS` リストと `_select_with_cursor()` 関数を削除。`ask_gm_character()` を1/2の番号入力（あり=cynical/なし=none）に変更
- `requirements.txt`：`readchar` を削除
- `README.md` / `README_EN.md`：GMキャラクター説明をシニカルあり/なしに縮小・更新

### 2026年10月（commit 76b960d）：転換点ターンのGM描写を明るい黄色で表示（実装漏れ修正）

`gm_turning_point_print()`はdisplay.pyに実装・明るい黄色で定義済みだったが、`main.py`でインポートも呼び出しもされていなかった（実装漏れ）。

- `main.py`：`gm_turning_point_print` をインポートに追加
- `main.py` `call_gm()`：`turning_point_injected` フラグがTrueのターンは `gm_turning_point_print()`（明るい黄色）で表示、それ以外は従来通り `gm_print()`（白）で表示

### 2026年10月（今セッション）：v1.1.0正式リリース・β版表記削除

- `README.md`：タイトルを `v1.1.0（β版）` → `v1.1.0` に変更、β版警告ブロック（⚠️）を削除
- `README_EN.md`：タイトルを `v1.1.0 (beta)` → `v1.1.0` に変更、beta警告ブロックを削除
- v1.1.0タグをGitHubにリリース済み（リリースノートはWebページから手動編集）
- 転換点ターンのGM描写を明るい黄色で表示する実装漏れを修正（commit 76b960d）

### 2026年10月（commit 2590d74）：check_turning_point 転換点判定の閾値を引き上げ

improv/adaptive（再生成前）モードでLLM判定による転換点が多発していた問題（28ターン中8回・約28%）への対処。

**原因**：判定プロンプトが「大きな転換点か？」という緩い基準で、NPC接触・感情変化等が広くyesになっていた。

**修正**（`api.py` `check_turning_point()`のプロンプト変更）：
- 「物語全体を通じて最も重要な瞬間の一つ」という基準に引き上げ
- yes条件を3つに限定：①登場人物の関係が不可逆に変化する、②隠された事実・真実が明らかになる、③物語の方向性を決定的に変える選択・衝突
- 探索・移動・会話・情報収集・日常的な行動は明示的にno
- クールダウン等の機械的制御は採用しない（大事な転換点を見逃すリスクがあるため）

**副作用**：閾値を上げすぎて今度は「一度も発動しない」問題が発生（犯罪ジャンル28ターン・gm_char_log空）。
- ジャンルによって転換点の出やすさが大きく異なる（捜査・情報収集系は地味なターンが多く、3条件をほぼ満たさない）
- 渡すGM描写の文字数が150字では文脈が薄すぎてLLMが判断できていた

### 2026年10月（commit 9d0ef58）：check_turning_point 参照文字数を拡大

- `api.py` の `gm_msgs` の切り出し文字数を `[:150]` → `[:300]` に変更
- 条件（3条件限定）は現状維持

### 2026年10月（commit 29f55a2）：転換点injection処理リファクタリング・全モードで発火するよう修正

**バグ**：GMキャラコメント（一言）は表示されるのにGM本文が明るい黄色にならない。

**原因**：`_build_api_messages()`にstrong/off/adaptive等のモード別ブロックがあり、それぞれで`return msgs`を途中実行していた。転換点injection処理は関数末尾（25ターン以下・通常パス）にしか存在せず、strong・off・adaptive(再生成後)・25ターン超では一度も転換点injectionに到達しなかった。

**修正**：
- `_apply_turning_point_injection(msgs)`ヘルパー関数を新設（従来の末尾処理を抽出）
- `_build_api_messages()`内の全`return msgs`（5箇所）を`return _apply_turning_point_injection(msgs)`に変更
- これにより全モード・全ターン条件で転換点injectionが確実に発火する

### 2026年10月（今セッション）：英語化構想（未実装）

**方針**
- GMシステムプロンプトは日本語のまま維持（再調整コスト・検証コストが高いため）
- GMの出力のみ英語化する最小変更アプローチ
- プロンプトに「出力は英語で」を追加する方向で検討中
- UIも言語選択対応にする（起動時に日本語/英語を選択）
- 二重管理を避けるためzipを分けずメニューで切り替える設計
- redditへの投稿を視野に入れている（r/LocalLLaMA想定）

**現時点の確認事項**
- 英語で行動を入力してもGMは日本語で返すことを確認済み
- 「出力は英語で」の一行追加で英語出力になる可能性が高い（未検証）
- **実装はユーザー確認後に着手すること**
