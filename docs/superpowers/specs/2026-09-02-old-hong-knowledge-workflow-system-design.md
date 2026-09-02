# 老洪知識點、工作流與教學流系統設計

日期：2026-09-02

狀態：Approved Design

Project：AI 培訓廣州／Empower With AI

公開目標：`opc-zachary/ai-training-knowledge`

## 1. 目標

把第二天上午老洪的四段課程，由「逐片摘要」提升為一套可學習、可執行、可授課、可被 Agent 精確調用的公開知識系統。

系統必須同時回答四類問題：

1. 老洪講了哪些可重用知識？
2. 這些知識如何變成實際工作流程？
3. 團隊如何將流程教給其他人？
4. 每個整理結論的影片、時間碼與證據在哪裡？

## 2. 來源與邊界

### 2.1 權威來源

- 四組繁體清理逐字稿，合計約 30,028 字、2,881 個時間碼段落。
- 四份逐片指南。
- 四組字幕、逐段 JSON 及 QA JSON。
- 對應關鍵畫面及公開 Manifest。

### 2.2 使用規則

- 知識點必須能追溯至至少一個 Video ID 及時間碼範圍。
- 老洪原話、整理後解釋、延伸應用及編者建議必須分開標示。
- 不把課堂日期的工具、模型、價格或平台能力寫成永久現況。
- 不重新上傳原始影片、壓縮影片、原始 PDF、ZIP 或 Raw Whisper 幻覺稿。
- 公開內容只包含整理後知識、清理逐字稿、關鍵畫面與非敏感 Manifest。

## 3. 設計方向

採用「實戰操作手冊」混合模式，而非純百科或純教案。

```text
影片證據
→ 原子知識點
→ 可執行工作流
→ 教學模組
→ 可複製模板
→ 角色學習路線
→ 團隊／Agent 調用
```

第一版目標不是建立過重的全量內容工程，而是在現有公開倉庫內建立一個輕量、可驗證、可繼續擴充的老洪專區。

## 4. 目錄架構

```text
day-2/old-hong/
├── README.md
├── TEAM_AND_AGENT_GUIDE.md
├── knowledge-points/
│   ├── zh-Hant/
│   ├── zh-Hans/
│   └── knowledge-index.json
├── workflows/
│   ├── zh-Hant/
│   ├── zh-Hans/
│   └── workflow-index.json
├── teaching-flows/
│   ├── zh-Hant/
│   ├── zh-Hans/
│   └── teaching-index.json
├── templates/
│   ├── zh-Hant/
│   └── zh-Hans/
├── learning-paths/
│   ├── zh-Hant/
│   └── zh-Hans/
└── evidence/
    ├── evidence-map.json
    └── coverage-report.md
```

技術檔名、資料夾及 JSON keys 維持英文；閱讀內容提供繁體及簡體中文。

## 5. 原子知識點

### 5.1 數量

第一版建立 50 至 70 個知識點。知識點只在具有獨立判斷、方法或可操作意義時成立，不以逐句切割追求數量。

### 5.2 分類

- `PE`：Prompt Engineering。
- `CTX`：Context 與排錯。
- `SKL`：Skill 搜尋、建立、架構及驗收。
- `WB`：個人 AI 工作台。
- `AUTO`：企業自動化演進。
- `FDE`：FDE 試點及陪伴式交付。
- `QA`：測試、復盤及持續改進。

### 5.3 知識點欄位

每個知識點至少包含：

- `id`：例如 `LH-PE-001`。
- 標題。
- 一句話結論。
- 老洪課堂原意。
- 整理後解釋。
- 為甚麼重要。
- 何時使用／不適用情況。
- 實際例子。
- 可執行下一步。
- 關聯工作流。
- Video ID、起止時間碼及證據狀態。

JSON 索引提供相同核心欄位及 Markdown 路徑，供 Agent 搜尋及路由。

## 6. 工作流

第一版建立至少 12 條工作流：

1. 行業研究 Prompt 共創流程。
2. Prompt 新窗口隔離測試流程。
3. Prompt 結果復盤與版本升級流程。
4. Context 超載診斷與任務切分流程。
5. Prompt 四層排錯流程。
6. 現成 Skill 搜尋、篩選與風險檢查流程。
7. 已驗證工作封裝成 Skill 的流程。
8. Skill 頂層設計與規則拆分流程。
9. 個人 AI 工作台 MVP 建立流程。
10. 內容數據回流與自主復盤流程。
11. 企業自動化方案選型流程。
12. FDE 低風險試點選擇與交付流程。

如逐字稿支持，增加 Skill 驗收、失敗歸因及陪伴式交接等獨立流程，但不得以常識補寫成老洪原話。

### 6.1 工作流格式

每條工作流包含：

- 目的及適用場景。
- 必要輸入。
- 角色及責任。
- 前置檢查。
- Mermaid 流程圖。
- 逐步操作。
- 決策分支。
- 產出物。
- 驗收標準。
- 常見失敗及修復方法。
- 對應知識點與時間碼。

## 7. 教學流

建立四個 60 至 90 分鐘模組，以及一套可組合的一日課程：

1. Prompt Engineering 與行業方法。
2. Context、Prompt 排錯及 Skill 入門。
3. Skill 架構與個人 AI 工作台。
4. 企業自動化與 FDE 試點。
5. 一日版：把四個模組串成「由個人方法到企業落地」完整路線。

每個教學流包含：

- 對象、先備知識及課堂成果。
- 分鐘級教學流程。
- 講師講解提示。
- 示範內容。
- 學員練習。
- 檢查問題。
- 課後作業。
- 評分量規及通過標準。
- 所需模板及證據來源。

## 8. 模板與學習路線

至少建立八份可複製模板：

- 行業研究 Prompt 設計表。
- Prompt 隔離測試記錄。
- Prompt 排錯清單。
- Skill 候選評估表。
- Skill 規格及驗收表。
- AI 工作台 MVP 畫布。
- 月度數據復盤表。
- FDE 試點評估及交接表。

建立四條角色路線：

- 管理者。
- 內容／市場營運。
- AI 顧問／解決方案設計者。
- FDE／企業落地人員。

每條路線列出推薦順序、必讀知識點、必做工作流、完成證據及能力出口。

## 9. 證據與資料流

```text
transcript.json／timestamped.txt／qa.json
→ 時間碼片段
→ knowledge point
→ workflow／teaching flow／template
→ evidence-map.json
→ coverage-report.md
```

`evidence-map.json` 記錄每個知識點與工作流對應的 Video ID、時間碼、逐字稿路徑及畫面路徑。`coverage-report.md` 說明四段影片的知識覆蓋率、未使用片段及理由。

## 10. 繁簡體策略

- 繁體中文是編輯真源。
- 簡體版本由本機 ICU 轉換後，抽查專有名詞、Markdown links、程式碼、Video ID 及 JSON 路徑。
- 技術詞如 Prompt、Context、Skill、Agent、FDE 不強制翻譯。
- 簡體內容不得改變證據時間碼及引用關係。

## 11. 團隊及 Agent 調用

`TEAM_AND_AGENT_GUIDE.md` 提供：

- 按問題類型選擇知識點、工作流或教學流的方法。
- 推薦 Agent prompt。
- JSON 索引及 Raw GitHub URL。
- 回答時引用 Video ID、時間碼及證據狀態的規則。
- 如何將模板複製到團隊實際項目。

## 12. 驗證標準

完成必須同時證明：

- 50 至 70 個知識點，全部有有效 ID 及證據引用。
- 至少 12 條工作流，全部有輸入、步驟、輸出及驗收。
- 四個教學模組及一套一日教學流。
- 至少八份模板及四條角色學習路線。
- 繁簡體文件數量及路徑完全對應。
- JSON 全部可解析，ID 及關係目標不存在缺失。
- Markdown links 全部有效。
- 公開資料不含本機絕對路徑、原始影片、PDF、ZIP、credential 或 Raw 幻覺稿。
- 倉庫 Validator 及單元測試通過。
- GitHub `main` commit 與本機一致。
- GitHub Public readback 可讀取 README、至少一個知識點、工作流、教學流、模板及 JSON 索引。

## 13. 非目標

- 不製作新的影片或重新剪輯原片。
- 不把課程內容包裝成已獲老洪授權的官方教材。
- 不建立需要登入、資料庫或獨立前端的學習平台。
- 不因追求知識點數量而加入沒有課堂證據的通用 AI 常識。

## 14. 完成定義

當團隊成員只打開 `day-2/old-hong/README.md`，便能依角色找到應學內容、執行工作流、使用模板、設計內部教學，並追溯每項結論至影片證據；Agent 亦能透過 JSON 索引完成相同路由。GitHub 公開回讀成功後，才可稱為完成。
