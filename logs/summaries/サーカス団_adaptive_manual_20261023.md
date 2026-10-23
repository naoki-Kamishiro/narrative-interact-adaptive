# サーカス団（えほん / adaptive / manual）

- 日時: 20261023
- ターン数: 14
- end_reason: ending
- deviation_count（peak）: 3（replot未発火）
- fixation_count: 0

## 問題・特記事項

- **deviation_countリセットバグ**（今回発覚・修正済み commit 1dec3d2）
  - check_deviation が no を返すたびに count が 0 にリセットされていた
  - そのため count が 3 に到達しても次ターン no → リセット → また 1 から積み上げの繰り返し
  - replot（count=5）は事実上機能していなかった
  - 修正後は累積カウントとなり、replot がより確実に発動する見込み

- **拒否受理ルールは機能**：「〜を無視する」「〜から逃げ切る」等をGMが全ターン受理。前回「象の鼻」で発生したプレイヤー行動の無視は今回なし

- 漂流収束でending（着地点の道化師は登場せず）：逸脱エンドとして許容範囲

## 物語の流れ（3行以内）

クマが開幕からサーカスを離脱し、みちけしを振り切って森の奥へ逃走。
deviation_count=3でwarning injectionが発動したが、次ターンにリセットされreplotには至らず。
GMが「どこまでも続く森」の漂流描写を重ねてエンディングに収束させた。
