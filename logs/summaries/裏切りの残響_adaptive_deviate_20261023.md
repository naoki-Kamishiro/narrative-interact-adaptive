# 裏切りの残響（犯罪 / adaptive / deviate）

- 日時: 20261023
- ターン数: 22
- end_reason: fixation ← バグ（実際はbeat完走によるending）
- deviation_count（peak）: 5（replotあり）
- fixation_count: 0

## 問題・特記事項
**fixation_endingフラグのバグ（commit d7a1f09で修正済み）**
replot前に固執が1回検出されてfixation_count=1が残っていた状態でreplotが発動。
replot後はbeat制御で正常着地（beat_ptr=4、全beat完走）したにもかかわらず、
fixation_ending=Trueが残ったままになり、end_reason="fixation"と誤記録された。
修正：_do_adaptive_replot()内でfixation_count=0・fixation_ending=Falseをリセット。

## 物語の流れ（3行以内）
犯罪プロットでdeviateプレイヤーが即座に警備員との戦闘を開始、deviation_count=5でreplot発動。
新プロット「近未来サイバーパンク・アクション」に変容し、beat制御（テープ確保→裏通路脱出→瓦礫突破→雨の路地脱出）で着地。
全4beatを完走して雨の路地でのendingに到達。replot機能の動作確認ができた初の犯罪ジャンル事例。
