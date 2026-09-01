# Day 2 LRF Preliminary Transcript QA v03

涵蓋上午老洪及下午 Channel；所有結果仍需在 4K MP4 完成後核對。

| Session | Video | Status | Audio | Segments | CJK | Overrun | Findings |
|---|---|---|---:|---:|---:|---:|---|
| 0830_morning_lao_hong | DJI_20260830102734_0001_D | SUSPECT_FOREIGN_TAIL_RECHECK | 1662.037s | 926 | 8109 | 17.463s | timestamp_overrun_17.463s, suspicious_foreign_tokens, empty_segments_70 |
| 0830_morning_lao_hong | DJI_20260830105517_0002_D | SUSPECT_FOREIGN_TAIL_RECHECK | 1663.040s | 875 | 7399 | 5.800s | timestamp_overrun_5.800s, suspicious_foreign_tokens, empty_segments_13 |
| 0830_morning_lao_hong | DJI_20260830112259_0003_D | PRELIMINARY_USABLE | 1119.659s | 619 | 5414 | 0.000s | none |
| 0830_morning_lao_hong | DJI_20260830114141_0004_D | PRELIMINARY_USABLE | 911.723s | 573 | 4625 | 0.017s | none |
| 0830_afternoon_channel | DJI_20260830135316_0001_D | SUSPECT_FOREIGN_TAIL_RECHECK | 1662.037s | 1104 | 7254 | 12.403s | timestamp_overrun_12.403s, suspicious_foreign_tokens, empty_segments_88 |
| 0830_afternoon_channel | DJI_20260830142059_0002_D | SUSPECT_FOREIGN_TAIL_RECHECK | 1203.349s | 708 | 4481 | 9.571s | timestamp_overrun_9.571s, suspicious_foreign_tokens, empty_segments_77 |
| 0830_afternoon_channel | DJI_20260830144104_0003_D | PRELIMINARY_USABLE | 153.408s | 65 | 573 | 0.000s | empty_segments_1 |
| 0830_afternoon_channel | DJI_20260830145621_0004_D | PRELIMINARY_USABLE | 943.851s | 382 | 3235 | 0.449s | empty_segments_17 |
| 0830_afternoon_channel | DJI_20260830152255_0005_D | SUSPECT_FOREIGN_TAIL_RECHECK | 1449.493s | 1042 | 5612 | 11.007s | timestamp_overrun_11.007s, suspicious_foreign_tokens, empty_segments_73 |
| 0830_afternoon_channel | DJI_20260830155647_0006_D | PRELIMINARY_USABLE | 1662.315s | 1057 | 6128 | 0.685s | empty_segments_101 |
| 0830_afternoon_channel | DJI_20260830162430_0007_D | SUSPECT_FOREIGN_TAIL_RECHECK | 89.451s | 106 | 242 | 11.909s | timestamp_overrun_11.909s, suspicious_foreign_tokens, empty_segments_73 |
| 0830_afternoon_channel | DJI_20260830162713_0008_D | REJECT_HALLUCINATION_OR_NO_SPEECH | 25.984s | 142 | 0 | 0.096s | suspicious_foreign_tokens, empty_segments_140 |
| 0830_afternoon_channel | DJI_20260830163448_0009_D | SUSPECT_FOREIGN_TAIL_RECHECK | 889.323s | 591 | 3356 | 0.000s | suspicious_foreign_tokens, empty_segments_74 |
| 0830_afternoon_channel | DJI_20260830165657_0010_D | REJECT_HALLUCINATION_OR_NO_SPEECH | 24.192s | 1 | 0 | 0.000s | suspicious_foreign_tokens |
| 0830_afternoon_channel | DJI_20260830165752_0011_D | REJECT_HALLUCINATION_OR_NO_SPEECH | 20.373s | 109 | 1 | 14.947s | timestamp_overrun_14.947s, suspicious_foreign_tokens, empty_segments_105 |
| 0830_afternoon_channel | DJI_20260830165827_0012_D | REJECT_HALLUCINATION_OR_NO_SPEECH | 16.832s | 1 | 10 | 13.148s | timestamp_overrun_13.148s |
| 0830_afternoon_channel | DJI_20260830165904_0013_D | PRELIMINARY_USABLE | 138.837s | 73 | 517 | 0.000s | none |
| 0830_afternoon_channel | DJI_20260830170257_0014_D | REJECT_HALLUCINATION_OR_NO_SPEECH | 16.725s | 1 | 10 | 13.255s | timestamp_overrun_13.255s |

## QA 邊界

- `PRELIMINARY_USABLE`：可用於主題分類，仍需專有名詞及 4K 畫面核對。
- `SUSPECT_FOREIGN_TAIL_RECHECK`：主體可用，尾段需 Clip 重轉。
- `REJECT_HALLUCINATION_OR_NO_SPEECH`：休息／環境聲／幻覺，不納入知識點。
