# Codex 调用指南

## 直接使用 GitHub Repo

公开 Repo 可以直接 Clone：

```bash
gh repo clone opc-zachary/ai-training-knowledge
```

或：

```bash
git clone https://github.com/opc-zachary/ai-training-knowledge.git
```

## 安装 Skill

Skill 目录：

```text
skills/ai-training-guangzhou
```

将整个资料夹连同 `SKILL.md` 及 `references/` 放入使用者自己的 Codex Skills 目录。若已有同名 Skill，先比较版本，不要直接覆盖。

## 调用例子

```text
使用 $ai-training-guangzhou 解释第一天 K03 品牌研究流程，并给我一份可填写的 Brief。
```

```text
使用 $ai-training-guangzhou 比较第一天的 Skill 与第二天 Harness 概念。
```

```text
使用 $ai-training-guangzhou 为市场部建立 K03→K05→K07→K10 的工作流。
```

## JSON 调用

```bash
curl -L 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json'
```

检查内容版本：

```bash
curl -Ls 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json' \
  | jq -e '.content_version == "1.2.0"'
```

## 回答规则

- 使用者用繁体中文时，读取 `zh-Hant`。
- 使用者用简体中文时，读取 `zh-Hans`。
- 第一天回答标示 K00–K10 与时间码。
- 第二天必须标示 `reference_only`。
- 不把衍生笔记冒充官方逐字稿或官方课件。
