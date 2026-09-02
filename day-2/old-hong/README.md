# 老洪實戰知識、工作流與教學系統

狀態：Evidence-linked Review Complete

內容版本：1.6.0

這個專區把第二天上午老洪四段課程整理成可學、可做、可教及可由 Agent 調用的完整系統。

## 交付規模

| 層次 | 數量 | 用途 |
|---|---:|---|
| 原子知識點 | 56 | 回答「老洪講了甚麼、何時使用」 |
| 可執行工作流 | 12 | 回答「團隊應該怎樣做」 |
| 教學流 | 5 | 四個模組及一套一日課程 |
| 可複製模板 | 8 | 直接填寫及交付 |
| 角色學習路線 | 4 | 管理者、內容營運、AI 顧問、FDE |
| 證據映射 | 56 | Video ID、時間碼及逐字稿路徑 |
| 知識點主截圖 | 56 | 1920×1080、OCR、SHA-256 及教學配圖關係 |

## 依目的進入

### 我要理解知識

- [繁體知識點](knowledge-points/zh-Hant/)
- [简体知识点](knowledge-points/zh-Hans/)
- [機器可讀知識索引](knowledge-points/knowledge-index.json)

七個知識域：Prompt Engineering、Context 與排錯、Skill 設計、AI 工作台、企業自動化、FDE 交付、QA 與持續改進。

### 我要實際執行

- [繁體工作流](workflows/zh-Hant/)
- [简体工作流](workflows/zh-Hans/)
- [工作流 JSON 索引](workflows/workflow-index.json)

建議由以下工作流開始：

1. [行業研究 Prompt 共創](workflows/zh-Hant/01-industry-research-prompt.md)
2. [Prompt 四層排錯](workflows/zh-Hant/05-four-layer-prompt-debugging.md)
3. [個人 AI 工作台 MVP](workflows/zh-Hant/09-ai-workbench-mvp.md)
4. [企業自動化方案選型](workflows/zh-Hant/11-automation-option-selection.md)
5. [FDE 低風險試點與交付](workflows/zh-Hant/12-fde-pilot-delivery.md)

### 我要教團隊

- [繁體教學流](teaching-flows/zh-Hant/)
- [简体教学流](teaching-flows/zh-Hans/)
- [教學流 JSON 索引](teaching-flows/teaching-index.json)

| 教學流 | 建議時間 | 適用場景 |
|---|---:|---|
| Prompt Engineering 與行業方法 | 75 分鐘 | 研究、策略、市場 |
| Context、Prompt 排錯與 Skill 入門 | 90 分鐘 | 長任務、排錯及 Skill 搜尋 |
| Skill 架構與個人 AI 工作台 | 90 分鐘 | 內容營運及內部能力建設 |
| 企業自動化與 FDE 試點 | 90 分鐘 | 管理層、顧問及轉型團隊 |
| 由個人方法到企業落地 | 360 分鐘 | 一日完整培訓 |

### 我要直接套用表格

- [繁體模板](templates/zh-Hant/)
- [简体模板](templates/zh-Hans/)

八份模板涵蓋研究 Prompt、隔離測試、四層排錯、Skill 評估、Skill 規格、工作台 MVP、月度復盤及 FDE 試點交接。

### 我要按角色學習

- [管理者](learning-paths/zh-Hant/01-manager.md)
- [內容／市場營運](learning-paths/zh-Hant/02-content-marketing-operator.md)
- [AI 顧問／解決方案設計者](learning-paths/zh-Hant/03-ai-consultant-solution-designer.md)
- [FDE／企業落地人員](learning-paths/zh-Hant/04-fde-enterprise-delivery.md)

## 證據入口

- [知識點證據映射 JSON](evidence/evidence-map.json)
- [四段影片覆蓋報告](evidence/coverage-report.md)
- [56 個知識點截圖畫廊](screenshots/GALLERY.md)
- [截圖 JSON 索引](screenshots/screenshot-index.json)
- [教學流 × 截圖索引](screenshots/teaching-screenshot-index.json)
- [第二天繁體時間碼逐字稿](../transcripts/zh-Hant/morning/)
- [第二天關鍵畫面](../evidence/keyframes/)

每個知識點都分開標示課堂原意、整理後解釋、使用邊界及下一步。整理內容不是逐字引述；遇到工具、公司或產品現況，必須按課堂日期重新核實。

## 團隊及 Agent

完整調用方法見 [TEAM_AND_AGENT_GUIDE.md](TEAM_AND_AGENT_GUIDE.md)。

最短提示：

```text
先讀 day-2/old-hong/README.md，再按我的角色及問題選擇知識點、工作流、模板或教學流。
回答時列出知識點 ID、工作流 ID、Video ID、時間碼，並分開課堂原意與延伸建議。
```

## 公開邊界

本專區提供衍生知識、流程、教案、模板及證據索引。原始及壓縮影片、原課件、來源壓縮包與未清理幻覺稿不放進一般 Git 歷史。
