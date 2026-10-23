# ログ傾向まとめ

セッション跨ぎの傾向把握用。個別要約は `summaries/` を参照。

## 集計（随時更新）

| 項目 | 値 |
|------|-----|
| 総セッション数 | 12 |
| end_reason="ending" | 9 |
| end_reason="fixation" | 3 |
| end_reason="turn_limit" | 0 |

## モード別傾向

### adaptive / manual
- 大きな逸脱（NPC踏殺）でdeviation=5→再生成発火→ジャンル変容しても着地 ✅（象の長靴）
- 再生成後のGMは同一行動（歩き回る×4）を毎回異なる描写で処理できた（象の長靴）
- すべての刺激を無視し続ける逸脱でdeviation=5→再生成発火→「NPCが世界を動かす」パターンで収束 ✅（モンスター）
- 再生成後も「ルナを無視する」が4回続いたが、GMがNPC側を能動的に動かして物語を収束させた（モンスター）
- 恋愛路線への逸脱でdeviation=5→再生成発火→「学園ラブコメ/青春純愛」に変容（最大のジャンル変容ケース）✅（モンスター2本目）
- 元ジャンル「児童向け小説」がラブコメに変容。プロット設定（モンスター設定・学校生活）は再利用された（モンスター2本目）

- 同一行動反復ルール追加後初検証：「太陽に向かって飛ぶ」×8回でGMが毎回状況を進展させた（言い換えでなく展開変化）✅（ちょうちょ）
- replot発火（deviation=5）→beat制御で着地。収束の主因はreplotのため、ルール単独効果は未分離（ちょうちょ）
- 主人公不在ルールの発動確認は未達（消滅→即endingになったため不在漂流が発生せず）（ちょうちょ）

- 全刺激無視・漂流のみでdeviation=5→replot発火→ジャンル「幻想的な寓話」に変容→beat着地 ✅（トリトン）
- replot後のbeat（瞑想・海との同化・導き手への帰還）が自然な流れに着地。manualプレイでのreplot成功例（トリトン）

### adaptive / deviate
- えほんジャンル（そらとぶくるま）で check_deviation が終始 no → deviation_count=0 のまま ending（replot未発火）
- えほんはプロット自体が緩く、逸脱判定のキーワード乖離が出にくい可能性
- deviateプレイヤーの「石ループ」を fixation_count=1 で検出し軽量injection → GMが自力収束 ✅
- beat.py KeyError 修正の動作確認未達（replot未発火のため）

**adaptive/deviate バッチ5本（20261023）：全5本が turn_limit なし**
- 鋼鉄の揺り籠（SF・7T）：deviation=0・fixation=2→強制ending。壁への往復行動でfixation先発火
- 残響の密室（ミステリー・16T）：deviation=0・fixation=2→強制ending。レコードプレーヤー往復でfixation先発火
- 残照の刃（時代劇・5T）：deviation=0・fixation=2→強制ending。錆刀の拾う置く4回でfixation先発火（最短）
- 残り香の門（怪談・24T）：deviation=4・replot=false→GMが自発的に漂流収束ending ✅
- 残響の凶行（犯罪・16T）：peak_deviation=5・replot=true→ジャンル「サスペンス・ホラー」に変容→beat着地 ✅（replot初成功2例目）

**傾向：fixation vs deviation の競合**
- deviateプレイで単純往復行動（拾う/置く、近づく/離れる）が続く場合、deviation判定前にfixationが先発火するケースが3本
- 単純往復はcheck_deviationの「プロットから外れているか」より、check_fixationの「ループか」に引っかかりやすい
- deviation=0のままfixation収束は「逸脱ではなく固執」の正確な分類と言える

## 既知の問題パターン

- **deviation_countリセットバグ**（commit 1dec3d2で修正済み）
  - check_deviation が no のとき count を 0 にリセットしていたため、replot（count=5）が事実上機能しなかった
  - 修正後は累積カウントに変更。replot発動の信頼性が向上する見込み
  - 発覚したのはサーカス団ログの `[ADAPTIVE] deviation_count=1` がリセット後にしか見えないことから
