# 老洪專區｜團隊及 Agent 調用指南

## 人工使用

1. 先從 [README](README.md) 選擇理解、執行、授課、模板或角色路線。
2. 需要概念時讀知識點；需要完成工作時直接進工作流。
3. 工作流的表格由 `templates/zh-Hant/` 或 `templates/zh-Hans/` 複製使用。
4. 對外引用前，用 evidence map 找回 Video ID 和時間碼。
5. 需要畫面證據或教案配圖時，使用 `screenshots/screenshot-index.json` 及 `teaching-screenshot-index.json`。

## Agent 啟動提示

```text
你正在使用 AI Training Guangzhou 的老洪公開知識包。
先讀 day-2/old-hong/README.md 和三個 JSON 索引。
根據問題選擇最少但足夠的知識點、工作流、模板或教學流。
回答必須：
1. 列出引用的 LH 知識點及工作流 ID；
2. 保留 Video ID、時間碼和 Evidence status；
3. 分開「課堂原意」「整理後應用」「你新增的建議」；
4. 對模型、產品、價格及公司現況標記課堂日期，必要時重新查證；
5. 不把 Review 整理稿說成官方逐字稿。
```

## 問題路由

| 使用者問題 | 先讀 | 再讀 |
|---|---|---|
| 如何寫行業研究 Prompt | `LH-PE-*` | `LH-WF-01`、模板 01 |
| 為甚麼 Prompt 在另一窗口失敗 | `LH-CTX-001` 至 `LH-CTX-003` | `LH-WF-02`、`LH-WF-04` |
| Prompt 答非所問如何修 | `LH-CTX-005`、`LH-CTX-006` | `LH-WF-05`、模板 03 |
| 如何找或評估 Skill | `LH-SKL-003` 至 `LH-SKL-005` | `LH-WF-06`、模板 04 |
| 如何把工作變成 Skill | `LH-SKL-001`、`LH-SKL-006` 至 `LH-SKL-008` | `LH-WF-07`、`LH-WF-08` |
| 如何建立個人 AI 工作台 | `LH-WB-*` | `LH-WF-09`、模板 06 |
| 如何用數據自動復盤 | `LH-WB-004` 至 `LH-WB-007` | `LH-WF-10`、模板 07 |
| 企業應選工作流還是 Agent | `LH-AUTO-*` | `LH-WF-11` |
| 如何做 FDE 試點 | `LH-FDE-*`、`LH-QA-008` | `LH-WF-12`、模板 08 |
| 如何教團隊 | 相關知識及工作流 | `teaching-flows/` |

## JSON 調用

公開 Raw Base：

```text
https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/day-2/old-hong
```

主要索引：

```text
/knowledge-points/knowledge-index.json
/workflows/workflow-index.json
/teaching-flows/teaching-index.json
/evidence/evidence-map.json
/screenshots/screenshot-index.json
/screenshots/teaching-screenshot-index.json
```

篩選 Prompt 類知識點的示例：

```python
import json
from urllib.request import urlopen

url = "https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/day-2/old-hong/knowledge-points/knowledge-index.json"
data = json.load(urlopen(url))
prompt_points = [item for item in data["knowledge_points"] if item["id"].startswith("LH-PE-")]
```

## 引用格式

人工文件及 Agent 回答建議使用：

```text
[LH-PE-005｜AI 補廣度，人補行業判斷]
Video: DJI_20260830102734_0001_D
Time: 00:13:00–00:18:00
Evidence: Cleaned Review
```

## 產出規則

- 概念回答：最少提供一個知識點和一個實際例子。
- 執行回答：使用完整工作流，不跳過輸入和驗收。
- 授課回答：提供對象、課時、練習、量規及證據。
- 企業方案：分開 Prompt、固定工作流、Skill、Agent／工作台的適用條件。
- FDE 方案：必須包含現場觀察、原流程回退、四區責任及四類驗收。
- 畫面引用：列出 Screenshot ID、Video ID、時間碼及 OCR 狀態；OCR 文字不當作正式逐字稿。

## 不應做的事

- 不把編者延伸建議冒充老洪原話。
- 不以單一成功案例聲稱方法已可重用。
- 不把工具上線當作企業落地完成。
- 不在沒有當前資料時沿用課堂中的市場或產品結論。
