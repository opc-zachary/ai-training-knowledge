# AI 培訓廣州｜第二天完整團隊知識包

狀態：Review Complete

範圍：0830 上午老洪＋下午 Channel

內容版本：1.4.0

## 快速入口

- [繁體逐片指南](guides/zh-Hant/)
- [简体逐片指南](guides/zh-Hans/)
- [繁體清理逐字稿／時間碼／SRT／JSON／QA](transcripts/zh-Hant/)
- [上午／下午分類與 QA](classification/)
- [117 張分類畫面](evidence/keyframes/)
- [畫面索引 JSON](evidence/keyframe-index.json)
- [公開交付 Manifest](manifests/day-2-public-manifest.json)
- [團隊／Agent 調用指南](TEAM_CALLING_GUIDE.md)

## 內容清單

| 類型 | 數量 |
|---|---:|
| 原始影片資訊 | 18 個 MP4 的檔名、大小、時長、SHA-256 |
| 720p 壓縮代理資訊 | 18 個；13 個含字幕 |
| 可用知識影片 | 13 |
| 排除環境聲片段 | 5 |
| 繁體獨立逐片指南 | 13 |
| 簡體獨立逐片指南 | 13 |
| 指南索引／兩天地圖 | 繁簡各 2 |
| 清理 transcript 套件 | 13 × 5 種格式 |
| 分類畫面 | 117 |

## 上午老洪

1. Prompt Engineering 演進與行業研究提示詞。
2. Context Window、Prompt 排錯與 Skill 建立。
3. Skill 頂層設計與個人 AI 工作台。
4. 企業自動化演進與 FDE 落地。

## 下午 Channel

1. AI 開發、系統思維、AI 年齡及模型。
2. 企業級模型、Codex 及 Superpowers。
3. Superpowers 需求澄清與計劃。
4. GUI、CLI、API、MCP。
5. Harness、Loop 及數字員工治理。
6. GitHub、Agent Reach、TradingAgents、Multi-Agent。
7. FDE、OPC、Agent Boss 及學習路線。
8. 學員反思訪問（非核心技術證據）。

## 證據邊界

- `transcript.txt`：繁體清理閱讀稿。
- `timestamped.txt`：時間碼閱讀及檢索。
- `subtitle.srt`：可配合本地影片。
- `transcript.json`：Agent／程式逐段調用。
- `qa.json`：時長、段落、重轉及幻覺清理證據。
- Raw Whisper 幻覺稿沒有上傳。
- 原片及 720p 影片不放入普通 Git history；以 manifest 與 SHA-256 對應 Case 3TB 交付。
