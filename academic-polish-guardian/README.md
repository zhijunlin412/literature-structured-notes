# academic-polish-guardian

学术语言润色 Skill：最小编辑 + 逐句修改记录 + 机器校验的"没改坏"保障。

## 它解决什么问题

基础 Agent 润色学术文本的典型失败：整段重写后限定词消失（`may` 变 `demonstrate`）、术语在章节间漂移、数字被顺手改动、修改说不清理由。本 Skill 用"受控修改类型 + 逐字替换 + 两道机器校验"把润色变成可复核的过程。

## 组成

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 四条硬标准 + 九步工作流 + 异常处理 + 自查清单 |
| `assets/edit_types.json` | 18 种受控修改类型（语法/术语/语气/表达四类） |
| `assets/hedging_lexicon.json` | 限定强度三级词表 + 因果/方向词表（强度守恒校验依据） |
| `assets/style_guide.md` | 期刊/学位论文/基金/审稿回复四种文体的语气与排版约定 |
| `assets/example_glossary.json` | 术语表格式示例 |
| `assets/example_edits.json` | 修改清单格式示例 |
| `assets/sample_polish_fchem.json` | 真实演示的修改记录（PMC8429493 摘要等，CC-BY） |
| `scripts/extract_facts.py` | 抽取数字+单位/引用/图表/缩写基线 |
| `scripts/check_preservation.py` | "没改坏"校验：事实与强度守恒 |
| `scripts/check_terminology.py` | "说得像"校验：术语全篇一致 |
| `scripts/assemble_polish.py` | 逐字应用修改 + 跑校验 + 组装交付物 |

## 最小使用流程

```bash
# 1. 建事实基线
python scripts/extract_facts.py --text original.txt --out work/facts_original.json
# 2. 逐句诊断，写 edits.json（格式见 assets/example_edits.json）与术语表
# 3. 应用 + 校验 + 组装
python scripts/assemble_polish.py --original original.txt --edits work/edits.json \
    --glossary work/glossary.json --lexicon assets/hedging_lexicon.json \
    --case-id demo --out output/
```

## 适用范围与限制

- 适用：中英文学术文本的润色、校对、术语统一；期刊论文/学位论文/基金/审稿回复。
- 不适用：整篇翻译（只做语言层面修正）、内容重写、文献调研。
- 机器校验覆盖数字/引用/图表/限定词/术语；逻辑与专业正确性仍需人读（第 8 步）。
- 纯 Python 标准库，无第三方依赖；Python ≥ 3.8。

## 维护

修改类型、强度词表、文体规则均可按学科扩展；扩词表时保持 tier 语义（strong/medium/weak = 确定/暗示/推测）。
