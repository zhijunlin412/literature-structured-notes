#!/usr/bin/env python3
"""知识图谱校验器（纯标准库）：对 graph.json 做确定性核验。

核验项：
  schema     必填字段、id 唯一性与编号模式、实体类型/关系/立场/置信度枚举
  evidence   每个节点与每条边 ≥1 条证据；source_id + paragraph_id 必须存在于
             段落索引；quote 必须是该段落的**逐字片段**（空白归一化后子串核验）
  relation   relation 取自受控词表；has_measured_value 必须有含数字的 value；
             stance=cited/inferred 必须写 note
  alignment  同名节点处置：规范化后同 label 同 type 的两个节点 → 警告（疑似重复）；
             同 label 不同 type → 必须有 not_merged 记录；
             跨篇节点（sources 来自 ≥2 篇）→ 必须有 merged 记录支撑
  merge      merge_records 引用的节点/别名真实存在，justification 非空
  queries    ≥3 个查询，id 唯一，type 合法

退出码：0 = 无 error（允许 warning），1 = 有 error，2 = 输入错误。
"""
import argparse
import json
import re
import sys

STANCES = {"own", "cited", "inferred"}
CONFIDENCE = {"high", "medium", "low"}
QUERY_TYPES = {"entity", "relation", "neighbors", "compare", "by_source"}


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def norm_label(s):
    """实体名归一：小写、统一横线与空白，用于发现同名候选。"""
    s = norm(s).lower()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"[\s_]+", "", s)
    return s


def validate(graph, index, entity_types, relations):
    errors, warnings = [], []
    E, W = errors.append, warnings.append

    type_vocab = {t["id"] for t in entity_types.get("entity_types", [])}
    rel_vocab = {r["id"] for r in relations.get("relations", [])}
    para_index = {}
    for p in index.get("paragraphs", []):
        para_index[(p["source_id"], p["paragraph_id"])] = p.get("text", "")
    paper_ids = {p["source_id"] for p in index.get("papers", [])}

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    merges = graph.get("merge_records") or []
    queries = graph.get("queries") or []

    if not nodes:
        E({"id": "-", "kind": "schema", "detail": "nodes 为空"})
    if not edges:
        W({"id": "-", "kind": "schema", "detail": "edges 为空，图谱没有关系"})

    def check_sources(owner_id, sources, owner_desc):
        if not isinstance(sources, list) or not sources:
            E({"id": owner_id, "kind": "evidence", "detail": f"{owner_desc}无证据绑定"})
            return set()
        src_papers = set()
        for s in sources:
            sid, pid = s.get("source_id"), s.get("paragraph_id")
            quote = s.get("quote", "")
            if (sid, pid) not in para_index:
                E({"id": owner_id, "kind": "evidence",
                   "detail": f"证据位置不存在: {sid}/{pid}"})
                continue
            src_papers.add(sid)
            if norm(quote) not in norm(para_index[(sid, pid)]):
                E({"id": owner_id, "kind": "evidence",
                   "detail": f"quote 不是 {sid}/{pid} 的逐字片段: {quote[:80]}"})
        return src_papers

    # ---- nodes ----
    node_ids, label_map = set(), {}
    merged_canonicals = {m.get("canonical") for m in merges
                         if m.get("decision") == "merged"}
    for n in nodes:
        nid = n.get("id", "?")
        for f in ("id", "label", "type", "sources", "added_in"):
            if f not in n:
                E({"id": nid, "kind": "schema", "detail": f"节点缺字段 {f}"})
        if not re.match(r"^N\d{3,}$", str(nid)):
            E({"id": nid, "kind": "schema", "detail": f"节点 id 不符合 ^N[0-9]{{3,}}$: {nid}"})
        if nid in node_ids:
            E({"id": nid, "kind": "schema", "detail": "节点 id 重复"})
        node_ids.add(nid)
        if n.get("type") not in type_vocab:
            E({"id": nid, "kind": "vocabulary", "detail": f"实体类型非法: {n.get('type')}"})
        if paper_ids and n.get("added_in") not in paper_ids:
            W({"id": nid, "kind": "schema",
               "detail": f"added_in={n.get('added_in')} 不在论文列表中"})
        src_papers = check_sources(nid, n.get("sources"), "节点")
        if len(src_papers) > 1 and nid not in merged_canonicals:
            E({"id": nid, "kind": "alignment",
               "detail": "节点证据跨越多篇论文，但 merge_records 中没有对应的 merged 记录"})
        for alias in n.get("aliases", []):
            key = (norm_label(alias), n.get("type"))
            label_map.setdefault(key, []).append(nid)
        label_map.setdefault((norm_label(n.get("label", "")), n.get("type")), []).append(nid)

    # 同名候选
    not_merged_pairs = {frozenset((m.get("node_a"), m.get("node_b")))
                        for m in merges if m.get("decision") == "not_merged"}
    for (nlabel, _type), ids in label_map.items():
        ids = sorted(set(ids))
        if len(ids) > 1:
            if any(frozenset(pair) in not_merged_pairs for pair in
                   ((ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids)))):
                continue
            W({"id": ",".join(ids), "kind": "alignment",
               "detail": f"规范化后同名的多个节点（{nlabel}），确认应合并或有 not_merged 记录"})

    # ---- edges ----
    edge_ids = set()
    for e in edges:
        eid = e.get("id", "?")
        for f in ("id", "subject", "relation", "object", "stance", "sources",
                  "confidence", "confidence_basis"):
            if f not in e:
                E({"id": eid, "kind": "schema", "detail": f"边缺字段 {f}"})
        if not re.match(r"^E\d{3,}$", str(eid)):
            E({"id": eid, "kind": "schema", "detail": f"边 id 不符合 ^E[0-9]{{3,}}$: {eid}"})
        if eid in edge_ids:
            E({"id": eid, "kind": "schema", "detail": "边 id 重复"})
        edge_ids.add(eid)
        if e.get("relation") not in rel_vocab:
            E({"id": eid, "kind": "vocabulary", "detail": f"relation 不在受控词表: {e.get('relation')}"})
        for ep in ("subject", "object"):
            if e.get(ep) not in node_ids:
                E({"id": eid, "kind": "schema", "detail": f"边 {ep} 指向不存在的节点: {e.get(ep)}"})
        if e.get("stance") not in STANCES:
            E({"id": eid, "kind": "schema", "detail": f"stance 非法: {e.get('stance')}"})
        if e.get("stance") in ("cited", "inferred") and not norm(e.get("note", "")):
            E({"id": eid, "kind": "evidence",
               "detail": f"stance={e.get('stance')} 但 note 未写明被引对象/推论链"})
        if e.get("confidence") not in CONFIDENCE:
            E({"id": eid, "kind": "schema", "detail": f"confidence 非法: {e.get('confidence')}"})
        if e.get("relation") == "has_measured_value":
            if not re.search(r"\d", str(e.get("value", ""))):
                E({"id": eid, "kind": "content",
                   "detail": "has_measured_value 但 value 缺失或无数值"})
        check_sources(eid, e.get("sources"), "边")

    # ---- merge_records ----
    for i, m in enumerate(merges):
        mid = m.get("decision", "?") + f"#{i}"
        if m.get("decision") == "merged":
            c = m.get("canonical")
            if c not in node_ids:
                E({"id": mid, "kind": "merge", "detail": f"merged 记录指向不存在的节点: {c}"})
            else:
                node = next(n for n in nodes if n["id"] == c)
                if m.get("alias") and m["alias"] not in node.get("aliases", []):
                    W({"id": mid, "kind": "merge",
                       "detail": f"别名 {m['alias'][:40]} 未列入 {c} 的 aliases"})
        elif m.get("decision") == "not_merged":
            for k in ("node_a", "node_b"):
                if m.get(k) not in node_ids:
                    E({"id": mid, "kind": "merge", "detail": f"not_merged 记录引用不存在节点: {m.get(k)}"})
        else:
            E({"id": mid, "kind": "merge", "detail": f"decision 非法: {m.get('decision')}"})
        if not norm(m.get("justification", "")):
            E({"id": mid, "kind": "merge", "detail": "缺 justification（合并/不合并依据）"})

    # ---- queries ----
    if len(queries) < 3:
        E({"id": "-", "kind": "queries", "detail": f"查询不足 3 个（当前 {len(queries)}）"})
    qids = set()
    for q in queries:
        qid = q.get("id", "?")
        if qid in qids:
            E({"id": qid, "kind": "queries", "detail": "查询 id 重复"})
        qids.add(qid)
        if q.get("type") not in QUERY_TYPES:
            E({"id": qid, "kind": "queries", "detail": f"查询类型非法: {q.get('type')}"})
        if not norm(q.get("question", "")):
            W({"id": qid, "kind": "queries", "detail": "查询缺自然语言 question"})

    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--index", required=True, help="materials_index.json")
    ap.add_argument("--entity-types", required=True)
    ap.add_argument("--relations", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        graph = json.load(open(args.graph, encoding="utf-8"))
        index = json.load(open(args.index, encoding="utf-8"))
        etypes = json.load(open(args.entity_types, encoding="utf-8"))
        relations = json.load(open(args.relations, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"FATAL input: {e}")
        return 2
    errors, warnings = validate(graph, index, etypes, relations)
    report = {"nodes": len(graph.get("nodes", [])),
              "edges": len(graph.get("edges", [])),
              "errors": errors, "warnings": warnings, "clean": not errors}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"OK nodes={report['nodes']} edges={report['edges']} "
        f"errors={len(errors)} warnings={len(warnings)}")
    for e in errors[:20]:
        log(f"  ERROR {e['id']} [{e['kind']}] {e['detail']}")
    for w in warnings[:12]:
        log(f"  warn  {w['id']} [{w['kind']}] {w['detail']}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
