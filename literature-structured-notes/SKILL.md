---
name: literature-structured-notes
description: 把一篇科研论文（PDF）转换成与原文章节对齐、字段化、每条结论都能回链到原文位置的**结构化笔记**（论文卡片 + 章节总结 + 知识点 + 证据锚点 + 原理深挖 + 术语词典），并对核心结论给出原理层解释与定量验证。当任务要求"文献总结 / 结构化笔记 / 论文卡片 / 章节摘要 / 知识点提取 / 带出处的阅读笔记 / 文献精读"时使用；输入是一篇真实论文或科研材料，输出是可检索、可比较、可复核、面向非专业读者也能读懂的笔记。不用于生成脱离原文结构的通篇摘要、通用笔记软件整理、学术写作或语言润色。
---

# literature-structured-notes

## 用途

把一篇真实科研论文或材料，整理成**与原文章节对齐、字段化、可回链证据、可继续复用**的结构化笔记。核心不是"把摘要压缩一遍"，而是把论文的研究结构、关键证据和限制条件保留下来，让每一条关键结论都能回到原文的章节、段落、页码或图表。

## 何时使用 / 何时不使用

- 使用：任务要求"文献总结 / 结构化笔记 / 论文卡片 / 章节摘要 / 知识点提取 / 证据回链 / 可检索笔记"。
- 不使用：生成脱离章节的通篇摘要、通用笔记软件里的随手记录、学术写作或润色。这些交给相邻工具。

## 四条硬标准（做对与否就看这四条）

1. **对得上**：笔记骨架与论文自身的章节和论证顺序一致，而不是套用通用摘要模板。
2. **留得住**：研究问题、数据、方法条件、主要发现、结论、局限都记录；**尤其要保留让结论成立的前提条件**。
3. **找得回**：每条关键笔记都指回原文的具体章节 / 段落 / 页码 / 图表 / 公式，而不是笼统的"见原文"。
4. **用得上**：笔记字段化、可检索、可比较，能被下一次阅读或写作直接使用。
5. **讲得清**：每个关键结论不仅记录"是什么"，还解释"为什么"（底层原理 / 公式 / 机制），并对可定量的结论做量级验证；每条结论标注证据强度（直接测量 / 领域共识 / 初步推测），不把推测写成事实。

## 输入契约（执行时按路径实际读取，不要按标签假设内容）

- `/input/case.json`：`case_id`、任务说明、材料路径、模板/格式约束、本题要求的 `output_contract` 字段。
- `/input/task.md`：本题的提交约定与字段要求（以它为准）。
- 论文 PDF / 材料：按 `case.json` 给的真实路径读取。PDF 解析用平台提供的 `pdf-text-tool`；扫描件 / 无文本层用 `ocr-tool`；双栏 / 版式用 `pdf-render-tool`。

## 输出契约（全部落在 `/app/output`）

1. `result.json`：结构化笔记主结果，含 `case_id`、`status`、`one_liner`、`paper_card`、`sections`、`knowledge_points`、`principle_analysis`、`glossary`、`evidence_map`、`sources`、`uncertainty`、`change_record`，**并补齐 `task.md` 要求的全部 `output_contract` 字段**。
2. `notes.md`：可读的笔记正文（论文卡片 + 章节总结 + 知识点 + 原理深挖 + 术语词典）。
3. `evidence_map.json`：逐条"结论 → 锚点"的证据映射，供独立复核。
4. `notes_plain.md`：面向非专业读者的易懂版正文（可选，spec 给出 `notes_plain` 时写出）。

字段与锚点的规范见 `assets/fields.json`；写完用 `scripts/validate_notes.py` 校验。

## 方法（九步，先想后做）

1. **提取锚点单元**：`python scripts/pdf_extract.py --pdf <PDF> --out work/extract` 产出带段号（H/P/C/T/F/R）与页码锚点的 `extract.json` / `source_units.md`（栏检测、阅读顺序、段落合并、页边/串栏/跨页标记全自动）。**后续所有笔记的锚点都引用这些单元 id**，不再凭印象写"第几页"。串栏单元（`order_suspect`）用 `pdftotext -f <页> -l <页> -x <左> -y <上> -W <宽> -H <高>` 按栏裁剪重取修复，修复记入 `change_record`。
2. **解析与章节对齐**：在修复后的单元上读全文，识别论文真实的章节结构（含摘要、引言、方法、结果、讨论、结论、附录），保留章节之间的承接关系。不强行套用五段式。
3. **一句话概括 + 论文卡片**：先写 `one_liner`（用一句话说清"问题—方法—最关键结果"）；再按字段字典填研究问题、数据、方法条件、主要发现、结论、局限，并单列"结论成立的前提条件"。
4. **章节总结**：逐章提炼目的、方法、结果、结论与过渡句，保持原章顺序。
5. **知识点提取**：把重要概念、变量、方法、结论拆成可检索条目；处理缩写、同义表述，归并重复条目，冲突处显式标注；可选填 `principle`（为什么）与 `evidence_strength`（证据强度）。
6. **证据锚点 + 逐字引文**：为每条关键结论写锚点（章节/段落/页码/图表/公式/**单元 id** 至少其一）；**主要发现、结论、原理深挖条目必须带 `unit` + `quote`**——`quote` 从该单元逐字复制（含空格形式），作为"这条笔记不是我编的"的可机检证据。找不到支撑单元的论断不写成事实，记入 `uncertainty`。
7. **原理深挖（`principle_analysis`）**：对每个关键结论回答"为什么"——给底层原理/公式/机制（`basis`），对可定量的结论做量级验证（`quantitative_check`，用原文数字反算核对，不一致要写明），并标 `evidence_strength`：`direct`（本文直接测量/陈述）、`consensus`（领域共识背景知识，本文未直接测量）、`preliminary`（本文自述初步/推测/需确认）、`not_reported`（未报告）。**区分"本文直接证据"与"领域共识解释"，绝不把推测写成事实。**
8. **术语词典 + 易懂化（`glossary` / `notes_plain`）**：把领域黑话（OER、过电位、双极膜、Tafel、ECSA 等）用通俗中文解释；`notes_plain` 按 `assets/精读笔记模板.md` 的 13 个格子组织（现象层与原理层一体），面向非专业读者，不含 JSON/代码/英文字段名。
9. **校验与自检**：`python scripts/validate_notes.py --spec notes_spec.json --extract work/extract/extract.json --out /app/output --case-id <id>`；**所有 error（含证据非逐字、单元不存在）必须修复重跑至清零**。区分"机器可判定的字段"与"必须人工确认的字段"；未报告、无法判断、材料冲突分别写明。预算紧张时先交全字段占位版（未完成标 `partial`），再按论文卡片→章节→知识点→原理深挖的优先级填充。

## 使用脚本

- `scripts/pdf_extract.py`：确定性 PDF 段落提取器（仅标准库；`pdftotext -bbox` stdout 模式；扫描件自动走 `pdftoppm` + `tesseract` OCR）。产出带段号/页码/bbox 锚点的 `extract.json` 与 `source_units.md`，串栏单元标 `order_suspect` 供修复。
- `scripts/validate_notes.py`：读 Agent 产出的 `notes_spec.json`（按 `assets/fields.json` 的 schema），校验必填字段与锚点格式；加 `--extract` 时做**逐字证据核验**（`unit` 必须存在、`quote` 必须是该单元的逐孔子串）。生成 `result.json`、`notes.md`、`evidence_map.json`。
  - 依赖：仅 Python 标准库，无需第三方包。
  - 调用：`python scripts/validate_notes.py --spec notes_spec.json --extract work/extract/extract.json --out /app/output --case-id <id>`
  - 校验失败返回非零，并给出缺失字段；不编造内容。

## 异常处理

- 扫描件 / 加密 / 权限受限文档 → 用 `ocr-tool` 或说明无法解析；不补造数据。
- 双栏错序 / 图表公式缺失 → 记录到 `change_record`，结论降级为"部分完成"。
- 超长文 → 优先保留主线与关键证据，必要时分块处理并注明。
- 非中文论文 → 按原文语言处理，术语保留原文 + 中文释义，避免翻译改写事实。
- 材料冲突 / 未报告 → 分别标注 `conflict` / `not_reported`，绝不写成事实。

## 自查（提交前逐项过）

1. 笔记骨架是否按论文原章节？是否套用了通用模板？
2. 研究问题、数据、方法条件、发现、结论、局限、前提条件是否齐全？
3. 每条关键结论是否有具体锚点（章节/段落/页/图表/公式/单元 id）？主要发现、结论、原理深挖条目是否带 `unit` + 逐字 `quote`，且通过 `validate_notes.py --extract` 的逐孔子串核验？
4. 数字、变量、方法名、结论是否与原文一致？是否把他人结果写成本文结果？
5. 每个关键结论是否回答了"为什么"（原理深挖）？可定量的结论是否用原文数字做了量级验证？
6. 每条结论是否标注证据强度（direct/consensus/preliminary/not_reported）？是否把"初步/推测"写成了"事实"？
7. 是否给出术语词典？是否有面向非专业读者的易懂版（notes_plain）？
8. `result.json` 是否含 `case_id` 与 `task.md` 要求的全部字段？是否只提交 Skill 与资源、不含预制正式答案？

## 资源清单

- `assets/fields.json`：字段字典与锚点格式规范（含 `principle_analysis`、`evidence_strength`、`glossary`、`one_liner`、`notes_plain` 与锚点的 `unit`/`quote` 逐字证据字段）。
- `assets/精读笔记模板.md`：面向非专业读者的 13 格精读笔记模板（现象层 + 原理层），`notes_plain` 的输出格式以此为准。
- `assets/example_notes.json`：最小调用示例（**示意示例**，非任何正式案例答案）。
- `scripts/pdf_extract.py`：确定性 PDF 段落提取器，产出带段号/页码锚点的源单元。
- `scripts/validate_notes.py`：确定性校验（含逐字证据核验）与组装脚本。

## 最小调用示例

见 `assets/example_notes.json`（内容为**示意示例**，非任何正式案例答案）。流程：读论文 → 按字段字典产出 `notes_spec.json` → `validate_notes.py` 校验并组装 → 自查 → 交付。
