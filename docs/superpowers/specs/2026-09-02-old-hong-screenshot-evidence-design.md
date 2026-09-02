# 老洪知識點截圖證據層設計

日期：2026-09-02

狀態：Approved Design

Project：AI 培訓廣州／Empower With AI

## 目標

為 `day-2/old-hong/` 的 56 個知識點建立一對一主截圖，使團隊可以由知識點直接查看當時畫面，並由 Agent 透過 JSON 取得圖片、時間碼、OCR、SHA-256 及教學流關係。

## 來源

- Case 3TB 上四段第二天上午老洪 4K 原片，只讀取、不移動、不重新命名、不覆寫。
- `knowledge-index.json` 的 56 個時間碼範圍。
- `teaching-index.json` 的知識點關係。

## 輸出結構

```text
day-2/old-hong/screenshots/
├── README.md
├── GALLERY.md
├── screenshot-index.json
├── teaching-screenshot-index.json
└── images/
    ├── LH-PE-001_...jpg
    └── ...共 56 張
```

## 圖片規格

- 每個知識點一張主圖，共 56 張。
- 從該知識點 Evidence 時間範圍的中點開始選擇。
- 若中點為轉場、嚴重模糊或黑畫面，在範圍內前後最多八秒選較清楚畫面。
- 由 4K 來源縮放至寬 1920px；維持原比例。
- JPEG，高品質壓縮；目標每張少於 1 MB。
- 不添加、替換或遮蓋任何可見內容。
- 檔名以知識點 ID、Video ID 及毫秒時間碼組成。

## OCR 與說明

- 使用本機 macOS Vision 執行繁體中文、簡體中文及英文 OCR，不使用雲端服務。
- `ocr_text` 保存可辨識文字；沒有可靠文字時使用空字串並標示狀態。
- `description` 使用知識點標題和課堂原意生成，不冒充畫面逐字 OCR。
- OCR、編輯說明和課堂逐字稿必須保持不同欄位。

## JSON 欄位

每個 `screenshot-index.json` 記錄包含：

- `id`
- `knowledge_id`
- `title`
- `description`
- `video_id`
- `timestamp`
- `evidence_start`
- `evidence_end`
- `path`
- `width`
- `height`
- `size_bytes`
- `sha256`
- `ocr_status`
- `ocr_text`
- `knowledge_path`

`teaching-screenshot-index.json` 依 `LH-TF-*` 教學流列出相關知識點和截圖 ID。

## 人工入口

- `README.md` 說明使用方式、規格和證據邊界。
- `GALLERY.md` 按七個知識域展示 56 張圖、標題、Video ID 及時間碼。
- 老洪首頁、團隊指南、根 README、Crosswalk 和 Codex Skill 加入截圖入口。

## 驗證

- 知識點 ID 與截圖 ID 一對一，數量均為 56。
- 每張圖片可解碼、寬 1920px、大小低於 1 MB。
- JSON path、大小、尺寸及 SHA-256 與實檔一致。
- 四段影片均有截圖覆蓋。
- 五個教學流的截圖關係全部可解析。
- Gallery 內所有連結有效。
- 不含本機絕對路徑、來源檔名、credential 或未獲允許的其他媒體。
- 本機 Validator、單元測試及 GitHub Public Raw readback 全部通過。

## 完成邊界

本次交付是 56 張精選知識證據圖及其索引，不是逐幀複製整套影片或逐頁重製課件。原始及壓縮影片仍保留在 Case 3TB，不進一般 Git history。
