---
name: methods-guardian
description: 把散落的实验材料（配置、日志、代码、实验记录）整理成可复核的方法与实验章节。机器先建参数台账，Agent 只写带来源证据的小 draft 与章节正文，脚本逐条核验证据、审计正文每个数字、自动组装溯源表/复现清单/待确认清单。防补造数值，缺口显式标注。
---

# methods-guardian：方法与实验章节写作（完成产物，也保留来源）

## 运行预算纪律（先读）

- 必读文件只有本 SKILL.md；assets 按需读（draft 契约见 `assets/draft_schema.json`，六类要素清单见 `assets/element_checklist.json`）。
- 你（Agent）只亲手写两个文件：**`draft.json`**（声明+证据，通常 <8KB）和 **`prose.md`**（章节正文）。台账、溯源表、复现清单、待确认清单全部由脚本生成。
- 脚本输出（inventory.json、check_report.json）**只看统计与错误行**，不要整体 cat 大文件；用文件路径+行号回查原材料。
- 不要通读全部大材料文件：先跑 scan_materials 看台账摘要，再按台账行号定点打开材料。
- 每完成一个阶段立即落盘（draft → check → prose → assemble），保证中断时也有可交付的部分结果。

## 适用场景

输入是一个材料目录（配置文件、实验日志、代码、实验记录、数据文件）加任务要求，输出是结构化、可复核的方法与实验章节。覆盖六类要素：方法步骤 steps、实验设置 setup、参数 params、数据集与材料 data、对照实验 baselines、可复现性与限制 repro。

## 工作流程（四步，每步落盘）

### 第 1 步：机器建台账（外部分母）

```bash
python scripts/scan_materials.py --materials <材料目录> --out work/inventory.json
```

阅读 stdout 摘要（文件数、台账条数、版本、种子、**冲突列表**）。台账 tier A（配置/日志/代码中的键值参数、版本、种子）是覆盖率检查的分母——每一条最终都必须被正文引用或显式说明不用，不允许悄悄漏掉。

### 第 2 步：按台账定点读材料，写 draft.json

契约见 `assets/draft_schema.json`。规则：

- 正文要写的**每个数字**都登记一条 claim：`number` + `evidence`（source_file 中的**逐字**片段，不得转述）+ `chapter_span`（正文中将包含该数字的逐字片段）。
- 台账 tier A 每条：要么被某条 claim 以 `registry_id` 引用（取值必须与台账一致），要么进 `unused_registry` 附理由。
- 台账报告的每个冲突（同名参数不同取值）：`conflict_resolution` 里裁定取哪个值并说明依据；无法裁定就 `"choice": "gap"` 并登记一个 gap 交作者确认。**禁止自行猜测后静默采用。**
- 材料不足、信息缺失、需作者确认的一律登记 `gaps`；六类要素在 `element_coverage` 中逐个声明 `present` 或关联 gap——材料没有就如实报缺口，**禁止为凑齐要素编造内容**。

```bash
python scripts/check_chapter.py --materials <材料目录> --inventory work/inventory.json \
  --draft work/draft.json --stage draft --out work/check_report.json
```

全部 ERROR 清零后再进入下一步。

### 第 3 步：写章节正文 prose.md

按 `assets/element_checklist.json` 的子项组织正文（步骤/设置/参数/数据/对照/复现与限制）。要求：

- 正文中的**每个数字**都必须落在某条 claim 的 `chapter_span` 内（脚本逐个审计，无来源数字直接报错）。不要写任何材料之外的数值。
- 每个 gap 在正文相应位置以 `【待作者确认 G1：…】` 标注。
- 限制条件写具体失效场景（如"该流程仅验证过碱性电解液，酸性体系中的适用性未验证"），不写套话。
- 中文写作时用中文专业语域：电解水（而非"电催化水分解"这类直译）、碱式碳酸钴（而非"碳酸钴氢氧化物"）等；证据强度分级用动词：已验证用"表明"，初步结果用"初步表明"，前景用"有望"。
- 步骤按序写清每步的输入、操作、输出与判断条件，不把多步操作压成一句。

```bash
python scripts/check_chapter.py --materials <材料目录> --inventory work/inventory.json \
  --draft work/draft.json --stage final --prose work/prose.md --out work/check_report.json
```

### 第 3.5 步（默认不做图，该做才做）：技术路线图

**原则：该做图才做图，纯文字能说清就不做图。** 仅在两种情况下做图：①任务明确要求流程图/技术路线图；②方法步骤有明显分支或并行结构，纯文字确实难以表达。线性简单流程、常规章节一律不配图——多余的图不加分，还占预算。

需要做时，写一份小的 `flow.json`（契约见脚本 docstring：`nodes` 节点文字、`rows` 行结构（一行多框即分支，可带行标签）、`edges` 相邻行连接），脚本负责确定性排版：

```bash
python scripts/make_flowchart.py --flow work/flow.json --out /app/output/route.svg \
  --png /app/output/route.png --draft work/draft.json
```

- 输出学术风格 SVG 矢量图（灰框黑箭头白底，与论文章节图风格一致）；环境有 matplotlib 和中文字体时附带 PNG 预览，缺字体则诚实说明而不是出乱码图。
- `--draft` 开启数字一致性校验：路线图中每个数字必须已在 draft 的 claim 集合中——**图里同样不许出现材料外的数值**。
- 节点文字写主标题+括号补充（如"一步水热原位生长（2*4 cm2 碳布垂直浸入，120 °C 反应 8 h）"），不要写步骤序号。

### 第 4 步：组装成稿与结构化结果

```bash
python scripts/assemble_chapter.py --draft work/draft.json --prose work/prose.md \
  --inventory work/inventory.json --check work/check_report.json \
  --case /input/case.json --outdir /app/output
```

产出 `chapter.md`（正文 + 附表A 参数溯源表 + 附录B 复现清单 + 附录C 待作者确认）与 `result.json`（case_id、status、统计、来源、不确定性）。有未解决 gap 时 status 为 `partial`——这是诚实状态，不要为显示 complete 而删 gap。

## 输出契约

- `chapter.md`：可继续编辑的成稿；附表 A 列出每个参数的取值、单位、来源文件:行号与正文锚点；附录 B 列出版本/种子/数据文件；附录 C 列出全部待确认项。
- `result.json`：`case_id`、`status`（complete/partial）、`stats`（claim 核验数、台账覆盖数、正文数字审计数）、`sources`、`uncertainty.gaps_pending_author`、`change_records`。

## 异常处理

- 材料目录不存在/文件不可读：脚本 FATAL 退出码 2，按提示修正路径；不要凭空补造材料内容。
- draft.json 损坏：check 退出码 2 并指明 JSON 错误位置。
- check 报错"正文数字无来源"：该数字没有对应 claim——补 claim（材料里找证据）或删数字，二选一，不允许保留无来源数值。
- 冲突无法裁定：登记 gap 并在正文标注，不猜测。
- 图片、二进制、大文件（>2MB）scan 会跳过并列入 files（kind=skipped），若任务需要其中的信息，在 gaps 中登记。

## 最小示例

`example/` 目录有一份迷你输入（`case.json` + `materials/`）与 `expected_result.json` 示例输出（**仅说明接口，非正式案例结果**）。

## 已验证能力

- 真实演示：以 PMC8429493（CC-BY）实验记录为材料生成中文方法章节，全部数字通过证据核验；材料中注入的一处记录冲突被台账检出并按规则裁定。
- 技术路线图：同一份材料演示生成 SVG+PNG 路线图（主链+分支+汇合的学术风格）；图中数字经 draft 校验，注入材料外数值（999 g）被拦截；畸形 flow.json、缺失节点引用均干净退出。
- 破坏测试：正文写错数字、claim 证据不存在、claim 数字与证据不符、缺 gap 标注、冲突未裁定、台账漏交代，六类注入错误均被拦截。
- 损坏输入（畸形 JSON、缺字段、目录不存在）均以退出码 2 干净失败，不崩溃。
