# literature-knowledge-graph

从科研论文文本材料包（JATS 段落索引）构建**证据可逐字回查**的文献知识图谱的可复用 Skill：
实体关系抽取、跨篇别名归一（合并/不合并都留依据）、受控关系词表、确定性证据核验、
结构化查询真实执行、增量更新追踪，导出 `result.json` / `graph.jsonld` / `nodes.csv` / `edges.csv` / `report.md`。

玻尔科学空间高校挑战赛参赛作品（阅读15｜文献知识图谱构建，challenge `product-arena-10-760d1a0b`）。

## 文件结构

```
SKILL.md                  Skill 本体：四条硬标准、九步工作流、输入输出契约、异常处理、自查清单
assets/
  entity_types.json       实体类型受控词表（material/method/task/metric/finding/researcher/organization/condition/compound）
  relations.json          关系受控词表（17 种有向关系 + stance 三分 + 置信度三级）
  fields.json             graph.json 字段字典
  query_templates.md      五种查询类型模板（entity/relation/neighbors/compare/by_source）
  example_graph.json      最小格式示例（示意，非任何案例答案）
  sample_graph_feco_cocho.json  真实演示输出：两篇 OER 真实论文 → 25 节点 34 边 9 条合并处置（非正式案例答案）
scripts/
  load_materials.py       材料包容错解析 → 段落索引 + 通读稿（纯标准库）
  validate_graph.py       确定性校验：证据逐孔子串核验、词表、合并记录、查询合法性
  query_graph.py          查询真实执行器（别名感知；查不到如实 not_found）
  assemble_graph.py       组装 result.json / graph.jsonld / CSV / report.md
GITHUB_URL.txt            本作品 GitHub 公开链接
```

## 快速开始

```bash
# 1. 材料包 → 段落索引（/input 为案例输入目录）
python scripts/load_materials.py --input /input --out work/materials
# 2. 通读 work/materials/source_units.md，按 assets/fields.json 编写 graph.json
# 3. 真实执行查询（≥3 个）
python scripts/query_graph.py --graph graph.json --out work/query_results.json
# 4. 校验（证据逐字核验等，error 须清零）
python scripts/validate_graph.py --graph graph.json --index work/materials/materials_index.json \
    --entity-types assets/entity_types.json --relations assets/relations.json \
    --out work/validate_report.json
# 5. 组装交付
python scripts/assemble_graph.py --case /input/case.json --index work/materials/materials_index.json \
    --graph graph.json --validation work/validate_report.json \
    --query-results work/query_results.json --out /app/output
```

## 设计要点

- **证据逐字绑定**：每个节点/边的 `quote` 必须是所引段落的逐字片段，校验器做空白归一化子串核验，改一个字都过不了。
- **跨篇对齐留痕**：merged 与 not_merged 都记录依据；同一物相不同样品不合并；同一名词不同条件不合并；两篇的数值结果分立成边、各自绑定来源，绝不合成一个结论。
- **立场区分**：作者自述（own）/ 转述他人（cited，注明被引对象）/ 一步推论（inferred，注明推论链）。
- **查询是执行不是编写**：查询由确定性脚本执行，查不到如实 `not_found`。

## 依赖与适用范围

- Python 3.8+，仅标准库；无网络依赖。
- 输入：组织方 JATS 段落文本材料包（段落 ID 定位，无 PDF 页码）；若给的是 PDF 原件，需先用相邻 Skill（pdf-document-parser）提取段落。
- 局限：不识别图像/表格内数据；实体与关系的语义判断由调用方 Agent 完成，脚本负责确定性核验与查询。

## 维护

作者：zhijunlin412（参赛 Agent lin）。问题与改进请提 GitHub Issue。
