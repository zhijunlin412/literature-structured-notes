---
name: nanopublication-builder
description: 把科研论文的关键结论拆成**可独立判断真假的原子断言**，为每条断言绑定逐字摘自原文的最小证据片段（带段号与页码锚点），记录论文来源元数据，导出机器可读的 nanopub JSON-LD / CSV / 人读报告。当任务要求"Nanopublication / 断言拆解 / 证据绑定 / 知识结构化 / 断言校验 / 结构化导出"时使用；输入是一份真实科研 PDF，输出是可复核、可被下游程序直接解析的结构化知识单元。不用于全文翻译、文献笔记总结或学术写作。
---

# nanopublication-builder

## 用途

把论文里的关键结论（摘要、结果、结论段）拆成一条一条的原子断言，每条断言做到：**断言本身可独立判断真假**（拆得细）、**绑定逐字证据片段并指出原文位置**（对得上）、**断言—证据—论文—作者—年份链路完整**（追得回）、**导出结构符合字段字典可被程序直接解析**（读得懂）。

## 何时使用 / 何时不使用

- 使用：任务要求"Nanopublication / 断言拆解 / 证据绑定 / 断言校验 / 来源追溯 / 结构化导出"。
- 不使用：全文翻译、笔记总结、语言润色。这些交给相邻工具。

## 四条硬标准（对应评分，做对与否就看这四条）

1. **拆得细**：一段结论拆成若干条各自可判断真假的断言；一条断言只含一个主体-关系-客体；并列、因果拆成多条；条件与限定范围写进 `conditions` 而不是揉进断言文本。
2. **对得上**：每条断言至少一条 `evidence`，`quote` 必须**逐字摘自**所引源单元（`validate_nanopub.py` 做子串核验，改一个字都过不了）；区分 direct / indirect / figure_table，indirect 必须在 `note` 写明推论链。
3. **追得回**：`provenance` 记录标题、作者、期刊、年份、DOI、来源文件；断言有唯一 id；证据锚定段号 + 页码，他人可按记录回到原文逐条确认。
4. **读得懂**：字段定义见 `assets/fields.json`，关系类型取自受控词表 `assets/relations.json`；导出 `result.json` + `nanopub.jsonld` + `assertions.csv` + `report.md`，程序无需人工清洗即可解析。

## 输入契约（执行时按路径实际读取）

- `/input/case.json`：`case_id`、任务说明、材料路径、`output_contract` 字段。
- `/input/task.md`：本题提交约定（以它为准）。
- 论文 PDF：按 `case.json` 给的真实路径读取。**PDF 直接给原文件，没有预提取的文字层。**

## 输出契约（全部落在 `/app/output`）

1. `result.json`：主结果，含 `case_id`、`status`、`stats`、`assertions`（含证据页码锚点）、`provenance`、`uncertainty`、`change_record`、`validation`，并补齐 `task.md` 要求的全部 `output_contract` 字段。
2. `nanopub.jsonld`：nanopub 风格 JSON-LD（assertion / provenance / publicationInfo 三段式）。
3. `assertions.csv`：扁平表，供下游程序直接使用。
4. `report.md`：人读报告，逐条"断言 → 三元组 → 证据引用（段号/页码）→ 置信度"。

## 方法（七步，先想后做）

1. **读输入**：读 `case.json` 与 `task.md`，确认 PDF 路径、输出字段与抽取范围（默认聚焦摘要 + 结果 + 结论中的关键结论，任务另有指定从其指定）。**若 case 附带追问**（如"该结果能确立因果吗"）：用断言与证据支撑回答——依据研究设计（观察性/随机对照、样本量、是否原文自称 prognostic）给出判断，回答连同证据锚点写入 result.json 的答题字段；依据不足的如实写"无法确立"，不夸大。**省预算**：先读 `units_index.json`，再用 `scripts/get_units.py --extract work/extract/extract.json --ids P1,P2 --max-chars 9000` 小批量取单元，单次返回控制在约 1 万字符内；不要一次性读整个 extract.json。
2. **提取单元**：`python scripts/pdf_extract.py --pdf <PDF> --out work/extract` 产出带段号与页码锚点的 `extract.json`。串栏单元（`order_suspect`）按 `pdftotext -f/-l/-x/-y/-W/-H` 裁剪重取修复，修复记入 `change_record`（产出 `extract_fixed.json`，后续以它为准）。
3. **定来源元数据**：从首页标题、作者行、期刊信息与 DOI 块填 `provenance`；DOI 等缺失项填 `"未报告"` 并记入 `uncertainty`，不猜不编。
4. **断言拆解**：逐段读关键段落，把结论句拆成原子断言写入 `nanopub.json`。规则：
   - 一条断言 = 一个 subject + 一个 relation（受控词表）+ 一个 object；含数值的断言数值与单位进 `object`，测试条件进 `conditions`；
   - "A 且 B""A 导致 B 并改善了 C"必须拆成多条；拿不准是否可再拆时，问"这条还能不能再分成两条各自判断真假的话"；
   - 词表没有合适关系时用 `reports` 并在 `note` 说明，不自造关系词；
   - 每条断言写一句 `context` 解读（数值含义、领域水平、与其他断言的关联），让卡片对人有帮助；**解读必须标注为解读，不是证据，不参与逐字核验**；
   - **统计量进断言**：原文给出 p 值、置信区间、样本量 n 时写进 `object`/`conditions`（如"p = 0.33，n = 21"）；图里的统计标记（p < 0.03 等）以渲染图核对为准，文字层抽出的乱序片段（如 "(p ,0.03 2p ,0.001)"）不直接采用；
   - 译文/术语与原文保持一致，材料代号、化学式、数值、图表编号原样保留。
5. **证据绑定**：为每条断言找**最小充分**证据片段：`quote` 从源单元逐字复制（含空格形式），填 `unit` 与 `type`。找不到直接证据时：能给间接证据就标 `indirect` + 写推论链；证据在图表里标 `figure_table` 并在 `note` 写明图表编号；完全没有依据的断言**不写进 nanopub.json**，记入 `uncertainty`。
6. **校验修复**：`python scripts/validate_nanopub.py --nanopub nanopub.json --extract work/extract/extract.json --relations <skill>/assets/relations.json --out work/validate_report.json`。所有 error（证据非逐字、单元不存在、关系越出词表、字段缺失）必须修复重跑至清零；warning 逐条处理或在 `note` 说明。
7. **组装交付**：`python scripts/assemble_nanopub.py --case /input/case.json --extract work/extract/extract.json --nanopub nanopub.json --validation work/validate_report.json --change-record work/change_record.json --out /app/output`，生成全部四种产物后按自查清单过一遍。

## 使用脚本

- `scripts/pdf_extract.py`：确定性 PDF 段落提取器（仅标准库；`pdftotext -bbox` stdout 模式；扫描件自动走 `pdftoppm` + `tesseract` OCR）。产出带段号/页码/bbox 锚点的 `extract.json` 与 `source_units.md`。
- `scripts/validate_nanopub.py`：确定性校验——字段与枚举、id 唯一性、关系受控词表、**证据引用逐孔子串核验**、断言粒度启发（过长/并列连接词）、主体出现检查、来源元数据完整性。
- `scripts/assemble_nanopub.py`：组装 `result.json`、`nanopub.jsonld`、`assertions.csv`、`report.md`。

## 异常处理

- 加密/权限受限 PDF → 说明无法解析，`status=partial`，不补造数据。
- 无文字层扫描件 → 自动 OCR；OCR 不确定处在 `note` 标注。
- 断言找不到任何支撑片段 → 不写入断言集，记入 `uncertainty`（断言与材料冲突时同样处理，并在 `note` 写明冲突内容）。
- 证据跨图表（数值只在图里）→ `figure_table` 类型 + 指引句 quote + `note` 写明图表编号；图中读数标 `[待确认]`。
- 原文本身有冲突（如图注与正文不一致）→ 两条断言都列，`confidence=low` 并在 `note` 互相指明。
- 预算紧张（64 次请求 / 900 秒）→ 拆出第一批断言后**立即跑一版第 7 步组装**，把全字段占位 `result.json` 先落盘（未完成标 `partial`），再按摘要→结论→结果的优先级细化——排在流程最后的东西最先被超时砍掉，占位版保证任何时刻都有诚实可交的结果。

## 自查（交付前逐项过）

1. 每条断言是否能独立判断真假？还有没有可以再拆的？
2. 每条 `quote` 是否通过了逐孔子串核验？证据是不是真的支撑该断言（而不是只沾边）？
3. relation 是否全部来自受控词表？indirect 是否都写了推论链？
4. 来源元数据是否齐全真实？缺失项是否如实标"未报告"？
5. 数值断言是否带统计量（p/CI/n，原文给出的前提下）？`confidence=high` 是否都有 direct/figure_table 证据支撑（校验器 warning 已清零或逐条说明）？case 的追问是否已用证据支撑回答？
6. `result.json` 是否含 `case_id`、诚实 `status` 与 `task.md` 要求的全部字段？是否只提交 Skill 与资源、不含预制正式答案？

## 最小调用示例

见 `assets/example_nanopub.json`（**示意示例**，非任何正式案例答案）；另附 `assets/sample_assertions_feco.json`（基于公开论文 Dalton Trans., 2024, 53, 1870–1877 的真实演示输出，22 条断言，可复用为字段与粒度参照）与 `assets/demo_validation.md`（校验器实跑记录：干净断言集 0 错误；篡改引文中一个数字即被逐字核验抓住）。流程：读 PDF → `pdf_extract.py` 提取 → 修序 → 填来源 → 拆断言写 `nanopub.json` → 绑证据 → `validate_nanopub.py` 清零 → `assemble_nanopub.py` 组装 → 自查 → 交付。
