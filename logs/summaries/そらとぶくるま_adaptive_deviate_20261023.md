# そらとぶくるま（えほん / adaptive / deviate）

- 日時: 20261023
- ターン数: 27
- end_reason: ending
- deviation_count（peak）: 0（replot未発火）
- fixation_count: 1

## 問題・特記事項

- **check_deviation が終始 no を返した**：deviateプレイヤーが「地図を押し返す」「逆方向に歩く」「石を拾う→置く→拾う→投げ捨てる」等の明確な逸脱をしたにもかかわらず deviation_count が 0 のまま。えほんジャンルはプロット自体が緩く、キーワードとの乖離が出にくいため check_deviation の感度が低く出た可能性がある
- **KeyError（beat.py）の検証未達**：replot が発火しなかったため adaptive beat が inject されず、修正の動作確認ができなかった。ファンタジー・アクション系など逸脱判定が出やすいジャンルで再検証が必要
- **fixation_count=1 は正常動作**：石ころの固執ループを検出し軽量 injection が発動した模様
- **GMはプロット着地点通りに自力 ending**：きつねのお茶・夕日・ブーンの回収、クライマックスの雲突破まで全て回収 ✅

## 物語の流れ（3行以内）

うさぎが草原・川・木立を経由しつつくまを無視してプロットからやや逸れたが、check_deviation は常に no を返しreplotは未発火。
GMが中盤以降に古い車・雲の壁・きつねを自力で物語に組み込み、プロット着地点通りのエンディングへ収束させた。
逸脱検出の感度不足により adaptive の恩恵なしに ending した形だが、結果として正常完結。
