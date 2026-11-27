---
name: literature-knowledge-graph
description: 从一组科研论文（JATS 段落文本材料包：corpus-manifest.json + material.json + primary/secondary-material.json）构建**证据可逐字回查的文献知识图谱**：抽取实体与关系、绑定 source_id+paragraph_id+逐字引文证据、跨篇别名归一并记录合并/不合并依据、真实执行结构化查询、增量纳入新论文，导出 result.json / JSON-LD / CSV / 人读报告。当任务要求"文献知识图谱 / 实体关系抽取 / 实体对齐 / 证据绑定 / 图谱查询 / 增量更新"时使用；输入是组织方提供的论文文本材料包（段落 ID 定位，无 PDF 页码），不是 PDF 原件。不用于全文翻译、文献笔记总结或单篇断言拆解。
---

# literature-knowledge-graph

## 用途

把一批论文（通常两篇）转成**一张图谱**：节点是论文里真实出现的科研对象（材料、方法、任务、指标、结论、研究者、机构、条件），边是有证据支持的关系；每个节点和每条边都能回到具体论文的具体段落和原文片段；同名对象跨篇对齐时写明凭什么合并、凭什么不合并；图谱能真实回答查询。

## 四条硬标准（对应评分，做对与否就看这四条）

1. **抽得准**：节点必须是论文里真实出现的对象，每个节点 ≥1 条证据（`source_id` + `paragraph_id` + 逐字 `quote`）；不靠常识补全概念。作者自述（`stance=own`）与转述他人（`cited`）分开标注。
2. **连得对**：关系类型取自受控词表 `assets/relations.json`，方向 subject→object，适用条件写进 `conditions`；共现、综述转述、推测**不算直接证据**——转述标 `cited`、推论标 `inferred` 并在 `note` 写明。
3. **对得齐**：跨篇同名候选逐一处置并写进 `merge_records`：合并要有依据（同一 JCPDS 物相、同一指标定义、同一基底），**不合并也要有依据**（同一物相但不同物理样品、同一通用方法术语但不同实验条件）；不同论文的条件、样本和数值结果**绝不合成一个结论**（同一实体在两篇的数值用分立边各自绑定来源）。
4. **查得到、回得去**：至少 3 个真实查询由 `query_graph.py` 确定性执行（不是手写答案），每个结果都带证据；查不到的查询如实返回 `not_found`。

## 输入契约（执行时按路径实际读取）

- `/input/case.json`：`case_id`、任务说明、材料清单、`output_contract`。**根级 doi/title/authors 只属于第一篇（primary），不得套到第二篇。**
- `/input/task.md`：本题提交约定（以它为准）。
- 材料包：`corpus-manifest.json`（各论文 DOI/作者/哈希/许可证）、`material.json`（两篇段落汇总索引）、`primary-material.json`、`secondary-material.json`。段落位置是**组织方 JATS 段落 ID**，本包无 PDF 页码，不得自造页码。
- 实际文件结构可能与预期略有出入：`load_materials.py` 会容错解析并报告它实际发现了什么；以脚本输出为准，不要凭文件名想象内容。

## 输出契约（全部落在 `/app/output`）

1. `result.json`：主结果，含 `case_id`、诚实 `status`、`stats`、`graph`（nodes+edges）、`merge_records`、`queries`（含真实执行结果）、`uncertainty`、`change_record`、`validation`，并把 `output_contract` 字段平铺到顶层。
2. `graph.jsonld`：JSON-LD 图谱导出。
3. `nodes.csv` / `edges.csv`：扁平表，供下游程序直接使用。
4. `report.md`：人读报告——论文来源、节点/边清单（每条带证据引文）、合并处置、查询问答、不确定性。

## 方法（九步，先想后做）

1. **读输入**：读 `case.json` 与 `task.md`，确认 `case_id`、输出字段、材料文件位置。
2. **建索引**：`python scripts/load_materials.py --input /input --out work/materials`，产出 `materials_index.json`（papers + paragraphs）与 `source_units.md`。检查 warnings：root 元数据归属、缺 paragraph_id、来源不明段落。
3. **通读全文**：读 `source_units.md`（两篇都要读），按 `corpus-manifest.json` 填论文元数据；缺失字段填 `"未报告"`，不猜不编。
4. **抽实体**：逐段识别真实出现的科研对象，写入 `graph.json` 的 `nodes`。字段见 `assets/fields.json`。规则：
   - 先建第一篇（primary）的节点，编号从 N001 起；第二篇作为增量加入，**沿用连续编号，不改动、不复用既有编号**，`added_in` 记录首次出现的论文；
   - 每个节点 ≥1 条证据，`quote` 从 `source_units.md` 对应段落**逐字复制**（含大小写与空格形式）；
   - 节点是"对象"不是"句子"：数值放边的 `value`，条件放 `conditions`，结论性认识用 `finding` 类型节点。
5. **抽关系**：写入 `edges`。规则：
   - relation 只从 `assets/relations.json` 选；选不出时用 `reports` 并在 `note` 说明，不自造新词；
   - 每条边 ≥1 条逐字证据；原文只是提到两者同框（共现）不足以建边，必须有表述该关系的原文；
   - 转述他人工作的边 `stance=cited` 并在 `note` 写明被引对象（文献编号或作者年）；由原文一步推论的边 `stance=inferred` 并写推论链；
   - 跨篇数值（如同一催化剂在两篇的不同测量值）建**分立边**、各自绑定来源与条件，记入 `uncertainty`。
6. **别名归一**：对每对跨篇/同篇同名候选，决定 merged 或 not_merged，写入 `merge_records`（含依据段落与理由）。判断口径：化学组成与物相卡片一致 → 物相可合并；同一物理样品 → 样品才合并；通用方法/材料术语相同 ≠ 同一样品、同一实例、同一条件。拿不准时**宁可不合并**并在 `uncertainty` 说明。
7. **写查询并真实执行**：在 `graph.json` 的 `queries` 写 ≥3 个查询（类型模板见 `assets/query_templates.md`，建议事实型 + 跨篇比较 + 来源核查各一，可加一个预期查不到的），运行 `python scripts/query_graph.py --graph graph.json --out work/query_results.json`。
8. **校验修复**：`python scripts/validate_graph.py --graph graph.json --index work/materials/materials_index.json --entity-types assets/entity_types.json --relations assets/relations.json --out work/validate_report.json`。所有 error（证据非逐字、位置不存在、词表外关系、跨篇节点缺合并记录等）必须修复重跑至清零；warning 逐条处理或说明。
9. **组装交付**：`python scripts/assemble_graph.py --case /input/case.json --index work/materials/materials_index.json --graph graph.json --validation work/validate_report.json --query-results work/query_results.json --out /app/output`，生成全部产物后按自查清单过一遍。

## 使用脚本

- `scripts/load_materials.py`：容错解析材料包（递归发现段落状对象、推断 source_id、按 (source_id, paragraph_id) 去重），产出段落索引与通读稿；结构无法识别时输出结构摘要并诚实报错，不猜不编。
- `scripts/validate_graph.py`：确定性校验——字段与枚举、id 唯一性、受控词表、**每条证据 quote 的逐孔子串核验**、同名节点处置核查、跨篇节点合并记录核查、查询合法性。
- `scripts/query_graph.py`：确定性查询执行（entity / relation / neighbors / compare / by_source），别名感知匹配，查不到如实 `not_found`。
- `scripts/assemble_graph.py`：组装四种产物，平铺 output_contract。

## 异常处理

- 材料文件缺失或结构完全不认识 → `load_materials.py` 报错并给结构摘要；`status=partial`，说明缺什么，不补造数据。
- 段落缺 `paragraph_id` 或来源不明 → 加载器自动编号/标 unknown 并告警；人工核查后再建证据，判定不了的记入 `uncertainty`。
- 同名候选判断不了该不该合并 → 不合并 + 记入 `uncertainty`（错合并比不合并更伤）。
- 两篇数据冲突（同一对象不同数值）→ 分立边各自绑定来源，`uncertainty` 写明冲突；禁止取平均或只留一个。
- 查询无结果 → 如实返回 `not_found` 与说明，这是有效结果不是失败。
- 预算紧张（64 次请求 / 900 秒）→ 先跑通"加载→骨架图（每篇核心 5-8 节点）→校验→组装"全链路拿到诚实的部分结果，再逐步补充实体与边；任何时刻保证 `/app/output` 里是可交付状态。

## 自查（交付前逐项过）

1. 每个节点、每条边都有 ≥1 条证据，且 `validate_graph.py` 的逐字核验全部通过？
2. relation 全部来自受控词表？`cited`/`inferred` 都写了 `note`？
3. 跨篇同名候选是否全部有 merged 或 not_merged 记录？有没有被错误合并的不同样品/条件？
4. 两篇的数值结果是否各自分立绑定来源，没有合成一个结论？
5. ≥3 个查询是 `query_graph.py` 真实执行的？`not_found` 是否如实保留？
6. `result.json` 是否含 `case_id`、诚实 `status` 与 `output_contract` 全部字段？是否只提交 Skill 与资源、不含预制正式答案？

## 最小调用示例

见 `assets/example_graph.json`（**示意示例**，非任何正式案例答案）：两个节点、一条边、一条合并记录、一个查询的最小完整写法。完整流程：`load_materials.py` 建索引 → 通读 `source_units.md` → 写 `graph.json`（实体→关系→合并记录→查询）→ `query_graph.py` 执行 → `validate_graph.py` 清零 → `assemble_graph.py` 组装 → 自查 → 交付。
