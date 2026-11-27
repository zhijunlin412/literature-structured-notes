---
name: bilingual-literature-translator
description: 把科研论文 PDF 翻译成**可核验的双语对照结果**。先确定性提取带段号与页码锚点的源单元，再建术语表锁定译名并强制全篇执行，逐段翻译携带上下文，最后用脚本核验数字/单位/公式/图表引用/文献编号是否逐段保留，输出段级英中对照、术语执行报告与人工复核清单。当任务要求"文献翻译 / 论文翻译 / 术语一致性 / 长文分段翻译 / 双语对照 / 译文核验"时使用；输入是一份真实科研 PDF，输出是可复核、可继续修改的双语对照产物。不用于文献笔记总结、学术写作润色或脱离原文的自由改写。
---

# bilingual-literature-translator

## 用途

把一份真实科研 PDF 翻译成段落级英中对照结果。核心不是"给一段读起来通顺的译文"，而是让译文**术语统一、段落齐全、关系准确、可回查核验**：每段译文都能指回原文段号与页码，每个数字、单位、化学式、图表号、文献编号都经过确定性核验。

## 何时使用 / 何时不使用

- 使用：任务要求"文献翻译 / 论文翻译 / 术语一致性 / 长文分段翻译 / 双语对照 / 译文核验"。
- 不使用：文献笔记总结、学术写作、语言润色、脱离原文的改写。这些交给相邻工具。

## 四条硬标准（对应评分，做对与否就看这四条）

1. **术语稳**：从原文抽取领域术语建立 `glossary.json` 锁定译名，全篇（标题、摘要、正文、图注、结论）只用锁定译名；用 `glossary_check.py` 强制校验并逐处回填，术语表必须被**执行**，不是写在提示里。
2. **段落全**：源文按段号 P1…Pn（另有 H 标题 / C 题注 / T 表格 / F 公式 / R 参考文献）一一对应翻译，跨页、跨栏不漏段、不重复、不错位；页眉页脚等页边单元标 `skipped` 并说明。
3. **关系准**：数字与单位、化学式与上下标（Fe³⁺、H₂、CO₃²⁻）、公式编号、图表引用（Fig. 2、Table 1）、文献编号（[12]、上标¹²）逐段原样保留；否定与限定条件（no、only、except、not）不得译反。
4. **可核验**：每段译文带段号 + 页码锚点；译不准处标 `[待确认]` 并汇总进人工复核清单；`verify_translation.py` 的确定性核验必须清零阻塞问题后才组装交付。

## 输入契约（执行时按路径实际读取）

- `/input/case.json`：`case_id`、任务说明、材料路径、`output_contract` 字段；可能附带**指定翻译范围**（如"只翻 g001、g002 两个图的标签与图注"）与**给定术语表**。
- `/input/task.md`：本题提交约定（以它为准）。
- 论文材料：按 `case.json` 给的真实路径读取，可能是**论文 PDF**（无预提取文字层）或**出版商 XML**（JATS 风格）。两者分别走 `pdf_extract.py` / `xml_extract.py`，不要混用。
- 若 case 附带问题（"回答问题，也给出依据"）：每个问题都要给出带证据（单元 id + 页码/定位符 + 逐字引文）的回答；无法回答的如实写"未报告/无法判断"，不猜。

## 输出契约（全部落在 `/app/output`）

1. `result.json`：主结果，含 `case_id`、`status`、`document_meta`、`glossary`（含执行核验结果）、`translation_coverage`、`verification`、`sources`（每单元页码锚点）、`uncertainty`、`change_record`，并补齐 `task.md` 要求的全部 `output_contract` 字段。
2. `bilingual.md`：逐单元"段号（页码）→ 原文 → 译文 → 译注"的双语对照文档。
3. `human_checklist.md`：待人工确认项（`[待确认]` 标注 + 译注 + 核验问题）。
4. `figure_labels.json`：图内文字对照表（坐标轴、图例、图内标注逐条 原文→译文→备注），存疑处标 `[待确认]`。
5. `glossary.json`、`alignment.json`：可复用、可继续编辑的中间产物。

## 方法（八步，先想后做）

1. **读输入**：读 `case.json` 与 `task.md`，确认材料路径、输出字段、**指定范围**与**给定术语表**；明确翻译目标语言（默认英→中）。
2. **提取单元**（两种输入二选一）：
   - **PDF**：`python scripts/pdf_extract.py --pdf <PDF> --out work/extract` 产出 `extract.json`、`source_units.md`、`units_index.json`。每个单元有稳定 `id`、类型、页码 + bbox 锚点；`margin` 标记页眉页脚，`order_suspect` 标记可能串栏的单元，`continues_next_page` 标记跨页续段。
   - **出版商 XML**：`python scripts/xml_extract.py --xml <XML> --out work/extract`（有指定范围时加 `--only-ids g001,g002` 等）产出**句级**单元（id 形如 `P00018.S003`，锚点为 XML 定位符 `fig[1]/caption[1]/p[1]`）。XML 已带结构，不做栏检测；补充材料（S1 Fig、S1 Text 等）同样提取，不得漏。
   - **省预算**：先读 `units_index.json`（id/类型/页码/字数/标记），再用 `python scripts/get_units.py --extract work/extract/extract.json --ids P1,P2 --max-chars 9000` 小批量取单元，单次返回控制在约 1 万字符内；不要一次性读整个 `extract.json`。
3. **修序补段（仅 PDF）**：逐个检查 `order_suspect` 单元。混排页（通栏标题/摘要 + 双栏正文）串栏时，用 `pdftotext` 的裁剪参数按栏重取：`-f <页> -l <页> -x <左> -y <上> -W <宽> -H <高>` 分别取左栏、右栏文本，按"左栏读完再读右栏"重排；明显被拆开的题注续行并回所属题注。所有修改写进 `change_record`（哪个单元、改了什么、依据）。
4. **建术语表**：若 case **给定术语表**，直接采用为锁定术语表（冲突以给定为准，不另起炉灶），可补充新术语但不得改给定译名；否则通读单元索引与关键单元，抽取领域术语（反应名、材料名、方法名、性能指标）写入 `glossary.json`：`{"terms": [{"en","abbr","zh","note"}]}`。译名要有依据（领域通用译法 / 首次出现定义，如 credible interval=可信区间≠置信区间）；拿不准的译名在 `note` 里写明备选。**建表后立即跑一版第 8 步的组装脚本产出占位 `result.json`（全字段、诚实 partial），再开始翻译**——先把可交的骨架落盘，防止超时交白卷。
5. **分段翻译**：按单元 id 顺序逐段翻译，携带术语表与前一段上下文；把结果**增量写入** `alignment.json`（每条：`id`、`source`（从 extract 原样复制）、`translation`、`status`、`note`），每批存盘一次防超时丢失。规则：
   - 术语严格按 `glossary.json`；数字、单位、化学式、公式编号、图表引用、文献编号原样保留（`10 mA cm⁻²`、`Fe(OH)₃`、`Fig. 2c`、`[12]` 不改写）；
   - **XML 输入的内联标记原样保留**（`<sub>`、`<sup>`、`<italic>` 等：丢了 V<sub>max</sub> 就成了 Vmax）；面板编号（A2）（B1）必须随原句走，读者靠它对回子图；
   - 否定、限定、因果、让步关系必须译准——**关键词检查查不出否定翻转**（"不增加 A、但减少 B"误译后关键词一个不少），这类句子要逐句做"原文断言 ↔ 译文断言"对照；拿不准标 `[待确认]` 并在 `note` 说明；
   - `margin` 单元（页眉页脚、页码、版权行）`status=skipped`；参考文献单元默认 `skipped`（保留原文，不译），除非任务明确要求翻译；
   - 图片型公式/表格读不出的，`status=partial` 并在 `note` 写明缺失范围，不猜。
6. **图内文字识读**：图在 PDF 里通常是位图（`pdftotext` 读不到文字层），坐标轴、图例、图内标注需要单独处理：对每个图题注（C 单元），按其页码与锚点位置用 `pdf-render-tool`（或 `pdftoppm -f <页> -l <页> -r 300 -x <左> -y <上> -W <宽> -H <高> -png`）裁剪渲染该图上方区域，逐面板视觉识读文字，产出 `figure_labels.json`：每条 `{figure, panel, en, zh, note}`。规则：材料代号、元素符号、标尺（100 nm 等）、公式符号原样保留；识读存疑或原文本身可疑（如缩写无法解释、图例与正文不一致）标 `[待确认]` 并写入 `note`；图内数值与正文/题注不一致时在 `note` 指出，不擅自统一。
7. **核验修复**：`python scripts/glossary_check.py --glossary glossary.json --alignment alignment.json --out work/glossary_report.json` 查术语执行；`python scripts/verify_translation.py --extract work/extract/extract.json --alignment alignment.json --out work/verify_report.json --checklist human_checklist.md` 查覆盖率、数字/引用/公式保留与长度异常。**覆盖率分母必须来自原文独立清点**（extract.json 的单元总数；有指定范围时 = 范围内单元数，即 `xml_extract.py --only-ids` 的统计），不得用"已翻译数/已提取数"自报——提取器漏掉的东西两边都没有，比例永远虚高。**所有 blocking 问题（漏译、重复、空译文）必须修复后重跑，直至清零**；一般问题逐项修复或在 `note` 里说明理由。
8. **组装交付**：`python scripts/assemble_result.py --case /input/case.json --extract work/extract/extract.json --glossary glossary.json --alignment alignment.json --verify work/verify_report.json --glossary-report work/glossary_report.json --change-record work/change_record.json --out /app/output` 生成 `result.json` 与 `bilingual.md`；把 `human_checklist.md`、`glossary.json`、`alignment.json`、`figure_labels.json` 一并放入 `/app/output`。

## 使用脚本

- `scripts/pdf_extract.py`：确定性 PDF 提取器（仅标准库）。`pdftotext -bbox`（stdout 模式，无中间文件）取词坐标 → 栏检测 → 阅读顺序 → 行合并成段（纵向间距 + 首行缩进 + 断词连接）→ 题注续行吸收 → 页边/串栏/跨页标记 → 产出 `extract.json`、`source_units.md` 与 `units_index.json`。全文无文字层时自动走 `pdftoppm` + `tesseract` OCR。
- `scripts/xml_extract.py`：确定性出版商 XML 提取器（仅标准库，JATS 风格）。直接利用 XML 结构产出**句级**单元（id 如 `P00018.S003`，锚点为 XML 定位符）；内联标记（`<sub>`/`<sup>`/`<italic>`）原样保留；补充材料（S1 Fig、S1 Text 等）不遗漏；`--only-ids` 按 case 指定范围过滤并给出**范围内单元总数**（覆盖率的独立分母）。
- `scripts/get_units.py`：小批量取单元（`--ids` / `--pages` / `--type` / `--max-chars`），配合 `units_index.json` 把单次工具返回控制在约 1 万字符内，节省请求与上下文预算。
- `scripts/glossary_check.py`：术语执行核验——凡源文出现锁定术语处，译文必须含锁定译名；输出违规清单供逐处回填。
- `scripts/verify_translation.py`：确定性核验——覆盖率（漏译/重复/多余 id）、数字单位、方括号与上标引用、图表引用、上下标式逐段比对，长度比异常，`[待确认]` 汇总；产出 `verify_report.json` 与 `human_checklist.md`。
- `scripts/assemble_result.py`：校验 alignment 字段与状态合法性，组装 `result.json` 与 `bilingual.md`。

## 异常处理

- 加密/权限受限 PDF → 说明无法解析，`status=partial`，不补造数据。
- 无文字层扫描件 → 自动 OCR；OCR 错字在 `note` 标注，仍不确定的标 `[待确认]`。
- 混排页串栏 → 按第 3 步裁剪重取并记入 `change_record`；无法确定栏边界的单元在 `note` 标 `column_ambiguous`，不猜顺序。
- 图片型公式/表格 → 能视觉识读的按第 5 步处理并标 `[待确认]`；无法识读的 `status=partial`，写明"该公式/表格为图片，未转写"。
- 语言混杂（如论文中夹中文摘要）→ 按目标语言统一处理，原已为目标语的段落照录并在 `note` 说明。
- 预算紧张（64 次请求 / 900 秒）→ 先完成全部单元的 `skipped`/`partial` 占位存盘，再按摘要→结论→正文优先级填充译文，保证任何时刻都有诚实可交的部分结果。

## 自查（交付前逐项过）

1. 术语表是否被 `glossary_check.py` 验证零违规？标题、图注、结论里的术语是否同样锁定？
2. 段号是否与源单元一一对应？有没有漏段、重复、串栏未修？
3. 每段的数字、单位、化学式、图表引用、文献编号是否经 `verify_translation.py` 逐段比对通过？
4. 否定与限定条件是否译准？`[待确认]` 是否都进了 `human_checklist.md` 而不是含混带过？
5. 图内文字是否已渲染识读并产出 `figure_labels.json`？存疑标注、图例与正文不一致处是否如实写明？
6. `result.json` 是否含 `case_id`、诚实 `status`、`sources` 锚点与 `task.md` 要求的全部字段？是否只提交 Skill 与资源、不含预制正式答案？

## 最小调用示例

见 `assets/example_glossary.json` 与 `assets/example_alignment.json`（**示意示例**，非任何正式案例答案）；另附 `assets/demo_feco_glossary.json`（用本 Skill 在公开论文 Dalton Trans., 2024, 53, 1870–1877 上实跑出的 40 条术语表，**真实演示产物**，可复用为电催化领域术语表起点）。流程：读 PDF → `pdf_extract.py` 提取单元 → 修序 → 建 `glossary.json` → 逐段翻译写 `alignment.json` → `glossary_check.py` + `verify_translation.py` 核验修复 → `assemble_result.py` 组装 → 自查 → 交付。
