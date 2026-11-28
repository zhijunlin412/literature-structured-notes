# intro-guardian

引言与相关工作写作 Skill：证据绑定的四段成稿（背景—分组相关工作—空白推导—贡献对照），空话与材料外数据由脚本拦截。

## 它解决什么问题

基础 Agent 写引言的典型失败：背景"近年来受到广泛关注"空转、相关工作逐篇拼接、转述与原文不符、空白凭空而来、贡献写出论文里根本没有的数据。本 Skill 的分工：Agent 只做语义写作（一份 draft.json），编号、排版、文献表、校验全由脚本确定性完成；每条转述逐字绑定被引文献原文，每条贡献挂底稿锚点。

## 组成

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 四条硬标准 + 六步工作流 + 异常处理 + 自查清单 |
| `assets/draft_schema.json` | draft.json / fact_draft / library 结构契约 |
| `assets/boilerplate_phrases.json` | 空话套话正则清单（中英文） |
| `assets/example_draft.json` | 最小格式示例 |
| `assets/sample_intro_feco.json` | 真实演示记录 |
| `scripts/parse_materials.py` | 独立清点底稿锚点与文献库（外部分母） |
| `scripts/check_intro.py` | 六类校验：逐字绑定/空话/推导链/数字锚定/覆盖/分组 |
| `scripts/assemble_intro.py` | 成稿 + GB/T 文献表 + result.json + 报告 |

## 最小流程

```bash
python scripts/parse_materials.py --fact-draft fact_draft.json --library library.json --out work/inventory.json
# Agent 写 work/draft.json（契约见 assets/draft_schema.json）
python scripts/check_intro.py --draft work/draft.json --fact-draft fact_draft.json \
    --library library.json --phrases assets/boilerplate_phrases.json --out work/check_report.json
python scripts/assemble_intro.py --case-id demo --draft work/draft.json \
    --library library.json --check work/check_report.json --out output/
```

## 适用范围与限制

- 适用：论文引言/相关工作/研究现状的起草与核对；中英文；顺序编码制引用。
- 语义判断（分组维度、转述措辞、空白表述）由 Agent 完成并留证据；脚本只验证"绑没绑对、数字在不在、空话有没有"。
- 纯 Python 标准库，无第三方依赖；Python ≥ 3.8。
