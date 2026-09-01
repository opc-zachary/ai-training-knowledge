# Codex 調用指南

## 直接使用 GitHub Repo

公開 Repo 可以直接 Clone：

```bash
gh repo clone opc-zachary/ai-training-knowledge
```

或：

```bash
git clone https://github.com/opc-zachary/ai-training-knowledge.git
```

## 安裝 Skill

Skill 目錄：

```text
skills/ai-training-guangzhou
```

將整個資料夾連同 `SKILL.md` 及 `references/` 放入使用者自己的 Codex Skills 目錄。若已有同名 Skill，先比較版本，不要直接覆蓋。

## 調用例子

```text
使用 $ai-training-guangzhou 解釋第一天 K03 品牌研究流程，並給我一份可填寫的 Brief。
```

```text
使用 $ai-training-guangzhou 比較第一天的 Skill 與第二天 Harness 概念。
```

```text
使用 $ai-training-guangzhou 為市場部建立 K03→K05→K07→K10 的工作流。
```

## JSON 調用

```bash
curl -L 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json'
```

檢查內容版本：

```bash
curl -Ls 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json' \
  | jq -e '.content_version == "1.2.0"'
```

## 回答規則

- 使用者用繁體中文時，讀取 `zh-Hant`。
- 使用者用簡體中文時，讀取 `zh-Hans`。
- 第一天回答標示 K00–K10 與時間碼。
- 第二天必須標示 `reference_only`。
- 不把衍生筆記冒充官方逐字稿或官方課件。
