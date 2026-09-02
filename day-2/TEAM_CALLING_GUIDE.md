# 團隊／Agent 調用指南

## 人工閱讀

先打開 [Day 2 README](README.md)，再按上午／下午進入逐片指南。需要核對原話時，使用同一 Video ID 的 `timestamped.txt`。

## Codex／Agent

推薦提示：

```text
讀取 day-2/README.md、day-2/classification/terminology.md；
如問題涉及老洪，優先讀 day-2/old-hong/README.md 及其 JSON 索引，
再根據我的問題選擇對應 guide、timestamped transcript 及 qa.json。
回答時必須標示 session、Video ID、時間碼及 Review 證據狀態。
```

## 依主題路由

| 問題 | 優先路徑 |
|---|---|
| 老洪 Prompt／Skill／工作台 | `old-hong/README.md`＋相關 `LH-*` 知識點／工作流 |
| 老洪 FDE 企業落地 | `old-hong/workflows/zh-Hant/12-fde-pilot-delivery.md` |
| 老洪團隊培訓 | `old-hong/teaching-flows/zh-Hant/` |
| 老洪模板 | `old-hong/templates/zh-Hant/` |
| FDE／OPC 綜合比較 | 上午 04＋下午 09 |
| GUI／CLI／API／MCP | 下午 04 |
| Harness／Loop | 下午 05 |
| GitHub／Agent Reach／Multi-Agent | 下午 06 |
| FDE／OPC／Agent Boss | 下午 09 |
| 精確時間碼 | `transcripts/zh-Hant/<session>/<video_id>/timestamped.txt` |
| 可程式處理段落 | 同路徑 `transcript.json` |
| 畫面證據 | `evidence/keyframes/<video_id>/` |

## 程式調用

取得公開 Manifest：

```bash
curl -L 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/day-2/manifests/day-2-public-manifest.json'
```

取得指定逐字稿：

```text
https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/day-2/transcripts/zh-Hant/<session>/<video_id>/transcript.json
```

## 回答規則

1. 不把學員反思當成講師技術證據。
2. 五個排除片段不納入知識回答。
3. 原話與整理結論分開。
4. 專有名詞依 `classification/terminology.md` 正名。
5. 模型、價格及產品能力要標記課堂日期，避免當成永久現況。
6. 老洪內容引用 `LH-*` ID，並分開課堂原意、整理應用及新增建議。
