# 第二天繁體清理逐字稿

## 結構

```text
zh-Hant/
├── morning/<video_id>/
└── afternoon/<video_id>/
    ├── transcript.txt
    ├── timestamped.txt
    ├── subtitle.srt
    ├── transcript.json
    └── qa.json
```

## 使用優先次序

1. 一般閱讀：`transcript.txt`
2. 引用及定位：`timestamped.txt`
3. 播放字幕：`subtitle.srt`
4. Agent／程式：`transcript.json`
5. 可信度：`qa.json`

全部內容為 Review 清理稿，不是官方逐字稿。Raw Whisper 幻覺已排除，但專有名詞仍應與 `classification/terminology.md` 及畫面證據交叉核對。
