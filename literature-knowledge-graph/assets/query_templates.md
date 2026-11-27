# 查询模板（query_graph.py 支持的五种查询类型）

查询写在 `graph.json` 的 `queries` 数组里，由 `query_graph.py` **真实执行**，
不是手写答案。实体名匹配：规范名与别名均可，大小写与横线形式不敏感，先精确后包含。

## 1. entity — 查一个实体的全部信息

```json
{"id": "Q1", "question": "Fe–CoCH NT/CC 是什么、有哪些性质与关联？",
 "type": "entity", "args": {"entity": "Fe–CoCH NT/CC"}}
```

返回：节点本身（含别名、证据）+ 所有关联边（双向）+ 每条边的证据原文。

## 2. relation — 查某类关系的全部边

```json
{"id": "Q2", "question": "两篇论文报告了哪些定量性能数值？",
 "type": "relation", "args": {"relation": "has_measured_value"}}
```

返回：该类型的全部边（含 value、conditions、证据）。

## 3. neighbors — 查一个实体的邻居子图

```json
{"id": "Q3", "question": "OER 这个任务与哪些材料、指标、方法直接相关？",
 "type": "neighbors", "args": {"entity": "析氧反应（OER）", "depth": 1}}
```

## 4. compare — 查两个实体之间的关系路径

```json
{"id": "Q4", "question": "Fe–CoCH NT/CC 与 RuO2 之间是什么关系？",
 "type": "compare", "args": {"entity_a": "Fe–CoCH NT/CC", "entity_b": "RuO2", "max_depth": 3}}
```

返回：直接边 + 不超过 max_depth 的关系路径；无路径时如实返回 not_found。

## 5. by_source — 查某篇论文贡献的节点与边

```json
{"id": "Q5", "question": "第二篇论文新增了哪些实体与关系？",
 "type": "by_source", "args": {"source_id": "paper2"}}
```

返回：sources 中含该 source_id 的节点与边（增量更新核查用）。

## 选题建议（≥3 个查询，类型尽量不重复）

- 一个**事实型**查询（entity / neighbors）：展示"查得到"；
- 一个**跨篇比较**查询（relation + 按论文分组解读，或 compare）：展示两篇材料在同一图谱中且数值不混；
- 一个**来源核查**查询（by_source）：展示"回得去"；
- 可附加一个**预期查不到**的查询（如实返回 not_found）：展示"无法确定如实说明"。
