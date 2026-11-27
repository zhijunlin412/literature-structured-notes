# literature-structured-notes

把一篇科研论文（PDF）转换成**与原文章节对齐、字段化、每条结论都能回链到原文位置**的结构化笔记：论文卡片 + 章节总结 + 知识点 + 原理深挖 + 术语词典 + 证据锚点，并对核心结论给出原理层解释与定量验证。

## 为什么需要它

基础 Agent 读论文做笔记的两个典型问题：

1. **找不回**：笔记写"见原文"，无法逐条回到原文核验。
2. **分不清**：把领域共识、初步推测写成"本文结果"。

本 Skill 用**确定性提取器**先把 PDF 变成带段号与页码锚点的源单元，笔记的每条关键结论必须引用单元 id 并附**逐字引文**，校验脚本做子串核验——改写一个字都过不了，从机制上杜绝"编证据"。

## 五条硬标准

| 标准 | 含义 |
|------|------|
| 对得上 | 笔记骨架与论文原章节顺序一致，不套通用模板 |
| 留得住 | 研究问题、数据、方法条件、发现、结论、局限、前提条件齐全 |
| 找得回 | 每条关键结论带单元 id + 逐字引文 + 页码锚点 |
| 用得上 | 字段化、可检索、可并排比较多篇论文 |
| 讲得清 | 每个关键结论回答"为什么"（原理/定量验证/证据强度分级） |

## 依赖

- Python 3（脚本仅用标准库）
- `pdftotext` / `pdftoppm`（poppler）；`tesseract`（可选，扫描件 OCR）

## 使用流程（详见 SKILL.md）

```bash
# 1. 提取带段号与页码锚点的源单元
python scripts/pdf_extract.py --pdf paper.pdf --out work/extract

# 2.（Agent）修序（order_suspect 单元按栏裁剪重取）→ 读单元写 notes_spec.json
#    字段规范见 assets/fields.json；关键结论必须带 evidence.unit + evidence.quote

# 3. 校验 + 组装（含逐字证据核验）
python scripts/validate_notes.py --spec notes_spec.json --extract work/extract/extract.json \
    --out /app/output --case-id <case_id>
# 产出 result.json / notes.md / evidence_map.json（有 notes_plain 时另存 notes_plain.md）
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 方法、输入输出契约、异常处理与自查清单 |
| `scripts/pdf_extract.py` | PDF → 带段号/页码/bbox 锚点的源单元（栏检测、阅读顺序、段落合并、串栏标记）+ 单元索引 |
| `scripts/get_units.py` | 小批量取单元（--ids/--pages/--max-chars），单次返回 ≤1 万字符，节省预算 |
| `scripts/validate_notes.py` | 字段与锚点校验 + **逐字证据核验** + 置信度-证据绑定检查 + 组装 result.json / notes.md / evidence_map.json |
| `assets/fields.json` | 字段字典与锚点格式规范 |
| `assets/精读笔记模板.md` | 面向非专业读者的 13 格精读笔记模板（notes_plain 格式） |
| `assets/example_notes.json` | 最小调用示例（示意，非任何正式案例答案） |

## 限制

- 笔记内容由 Agent 撰写，脚本负责确定性校验；逐字核验只保证"引文真实存在于原文"，论断与引文的语义对应由 Agent 自查清单把关。
- 混排页（通栏摘要 + 双栏正文）需按 SKILL.md 第 1 步裁剪修复；扫描件 OCR 不确定处如实标注。
- 非中文论文按原文语言处理，术语保留原文 + 中文释义。

## 许可证

MIT
