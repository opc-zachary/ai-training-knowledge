# AI 培訓廣州｜公開知識庫

這是一個根據兩天課程重新整理的衍生知識庫，提供繁體中文、簡體中文及英文版本。內容包括逐片學習指南、操作手冊、實戰 Playbook、練習、模板、JSON 索引及可安裝的 Codex Skill。

## 語言版本

- [繁體中文完整版](locales/zh-Hant/README.md)
- [简体中文完整版](locales/zh-Hans/README.md)
- [English edition](README.en.md)

## 內容規模

- 第一天 10 段影片的詳細學習指南。
- K00–K10 共 11 個操作模組。
- 品牌研究、作者調性、視覺反推、電商視覺、AI 影片及數據分析 Playbook。
- 初階練習、實戰 Capstone、驗證題及可直接填寫的工作模板。
- 第二天 Channel 課件的 7 個參考章節。
- 老洪 56 個知識點、12 條工作流、5 套教學流、8 份模板及 4 條角色路線。
- 老洪 56 張知識點主截圖、OCR、畫廊及教學配圖索引。
- 任務路由、名詞表、學習路徑及 Codex Skill。

## 快速入口

- [繁體中文課程總覽](locales/zh-Hant/full-course.md)
- [繁體中文逐片指南](locales/zh-Hant/day-1-video-guides.md)
- [繁體中文 K00–K10 模組](locales/zh-Hant/modules.md)
- [繁體中文第二天上午／下午指南](locales/zh-Hant/day-2-video-guides.md)
- [簡體中文課程總覽](locales/zh-Hans/full-course.md)
- [简体中文逐片指南](locales/zh-Hans/day-1-video-guides.md)
- [简体中文 K00–K10 模块](locales/zh-Hans/modules.md)
- [简体中文第二天上午／下午指南](locales/zh-Hans/day-2-video-guides.md)
- [機器可讀 JSON](data/course-crosswalk.v1.json)
- [Codex Skill](skills/ai-training-guangzhou/SKILL.md)
- [第二天完整團隊知識包](day-2/README.md)
- [老洪實戰知識、工作流與教學系統](day-2/old-hong/README.md)
- [老洪 56 個知識點截圖畫廊](day-2/old-hong/screenshots/GALLERY.md)

## Raw JSON

公開 Raw URL：

```text
https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json
```

程式調用：

```bash
curl -L 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json'
```

## 證據狀態

- 第一天：已按 10 段處理後的影片建立時間碼對照。
- 第二天：18 組影片完成分類；13 段可用內容、5 段環境聲排除，狀態為 `video_classified_review`。
- JSON schema：`1.0.0`；內容版本：`1.6.0`。

本 Repo 包含重新撰寫的衍生知識、第二天繁體清理逐字稿／SRT／JSON、QA 及分類畫面；不包含原影片、Raw Whisper 幻覺稿、原課件或第三方程式碼。
