# 老洪知識點截圖證據層

狀態：Visual-checked Review

內容版本：1.6.0

## 內容

- 56 張 1920×1080 JPEG 主截圖。
- 每個 `LH-*` 知識點恰好對應一張截圖。
- 四段老洪課堂影片全部覆蓋。
- 所有圖片均由本地 4K 原片在知識點時間範圍內抽取。
- 56 張圖片均完成本機繁體中文、簡體中文及英文 OCR。
- [完整畫廊](GALLERY.md)
- [截圖 JSON 索引](screenshot-index.json)
- [教學流 × 截圖索引](teaching-screenshot-index.json)

## 使用方式

### 人工查看

由 [GALLERY.md](GALLERY.md) 按 Prompt、Context、Skill、工作台、企業自動化、FDE 及 QA 七個知識域瀏覽。

### Agent 調用

先用 `knowledge_id` 在 `screenshot-index.json` 找到：

- 截圖路徑。
- Video ID 及實際抽圖時間。
- 知識點 Evidence 起止時間。
- 圖片尺寸、大小及 SHA-256。
- 本機 OCR 文字及狀態。
- 對應知識文件。

教案需要配圖時，以 `LH-TF-*` 在 `teaching-screenshot-index.json` 取得該教學流涉及的全部截圖 ID。

## 圖片規格

| 項目 | 規格 |
|---|---|
| 數量 | 56 |
| 尺寸 | 1920×1080 |
| 格式 | JPEG |
| 單檔上限 | 1 MB；實際最大約 300 KB |
| 畫面修改 | 沒有加字、遮擋或替換內容 |
| OCR | 本機 macOS Vision，繁中／簡中／英文 |

## 證據邊界

- 截圖用來輔助理解和定位，不取代影片及清理逐字稿。
- `ocr_text` 是機器辨識結果，投影角度及距離會造成錯字。
- `description` 來自知識點整理，不是畫面逐字 OCR。
- 課堂原意以知識點、時間碼逐字稿及 QA 為準。
- 原片保持在 Case 3TB，不放入一般 Git history。

## QA

- 全部 56 張已用四張 contact sheet 人工檢視。
- 沒有黑畫面、明顯轉場或無法解碼圖片。
- 每張均可看到投影幕或課堂操作內容。
- 圖片 path、尺寸、大小及 SHA-256 由倉庫 Validator 重驗。
