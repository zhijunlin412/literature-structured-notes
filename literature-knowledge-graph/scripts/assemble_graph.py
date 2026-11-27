#!/usr/bin/env python3
"""组装交付物（纯标准库）：

  result.json    主结果：case_id + status + stats + graph + merge_records +
                 查询结果 + uncertainty + change_record + validation；
                 并把 case.json 的 output_contract 字段平铺到顶层
  graph.jsonld   JSON-LD 图谱导出（节点/边/来源三元）
  nodes.csv      节点扁平表
  edges.csv      边扁平表
  report.md      人读报告（论文 → 统计 → 节点/边（含证据）→ 合并处置 → 查询问答 → 不确定性）

用法：
  python assemble_graph.py --case /input/case.json --index work/materials/materials_index.json \
      --graph graph.json --validation work/validate_report.json \
      --query-results work/query_results.json --out /app/output
"""
import argparse
import csv
import json
import os
import re
import sys


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def evidence_str(sources):
    parts = []
    for s in sources or []:
        q = re.sub(r"\s+", " ", s.get("quote", "")).strip()
        parts.append(f"{s.get('source_id')}/{s.get('paragraph_id')}: “{q[:120]}”")
    return " | ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--validation", default=None)
    ap.add_argument("--query-results", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = load(args.case, {}) or {}
    index = load(args.index, {}) or {}
    graph = load(args.graph)
    if graph is None:
        log("FATAL: graph.json 无法读取")
        return 2
    validation = load(args.validation, {}) if args.validation else {}
    qresults = load(args.query_results, {}) if args.query_results else {}

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    merges = graph.get("merge_records", [])
    papers = index.get("papers", graph.get("papers", []))
    nlabel = {n["id"]: n["label"] for n in nodes}
    errors = (validation or {}).get("errors", [])
    status = "success" if not errors else "partial"

    stats = {
        "papers": len(papers),
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_type": {},
        "edges_by_relation": {},
        "merge_records": len(merges),
        "queries_executed": len(qresults.get("queries", [])),
        "queries_not_found": sum(1 for r in qresults.get("queries", [])
                                 if r.get("status") == "not_found"),
    }
    for n in nodes:
        stats["nodes_by_type"][n.get("type", "?")] = \
            stats["nodes_by_type"].get(n.get("type", "?"), 0) + 1
    for e in edges:
        stats["edges_by_relation"][e.get("relation", "?")] = \
            stats["edges_by_relation"].get(e.get("relation", "?"), 0) + 1

    result = {
        "case_id": graph.get("case_id") or case.get("case_id", "未报告"),
        "skill": "literature-knowledge-graph",
        "status": status,
        "stats": stats,
        "papers": papers,
        "graph": {"nodes": nodes, "edges": edges},
        "merge_records": merges,
        "queries": qresults.get("queries", []),
        "uncertainty": graph.get("uncertainty", []),
        "change_record": graph.get("change_record", []),
        "validation": {
            "clean": (validation or {}).get("clean"),
            "errors": errors,
            "warnings": (validation or {}).get("warnings", []),
        },
    }
    # output_contract 字段平铺到顶层（Harbor 运行时约定）
    contract = case.get("output_contract")
    if isinstance(contract, dict):
        for k in contract:
            result.setdefault(k, None)
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                result.setdefault(item, None)
            elif isinstance(item, dict) and "field" in item:
                result.setdefault(item["field"], None)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- graph.jsonld ----
    jsonld = {"@context": {
                  "kg": "https://example.org/literature-kg#",
                  "source_id": "kg:source_id", "paragraph_id": "kg:paragraph_id",
                  "quote": "kg:quote", "label": "kg:label", "aliases": "kg:aliases"},
              "@graph": []}
    for n in nodes:
        jsonld["@graph"].append({
            "@id": f"kg:node/{n['id']}", "@type": f"kg:{n.get('type')}",
            "label": n["label"], "aliases": n.get("aliases", []),
            "added_in": n.get("added_in"), "evidence": n.get("sources", [])})
    for e in edges:
        jsonld["@graph"].append({
            "@id": f"kg:edge/{e['id']}", "@type": f"kg:{e.get('relation')}",
            "subject": f"kg:node/{e['subject']}", "object": f"kg:node/{e['object']}",
            "value": e.get("value"), "conditions": e.get("conditions"),
            "stance": e.get("stance"), "confidence": e.get("confidence"),
            "evidence": e.get("sources", [])})
    with open(os.path.join(args.out, "graph.jsonld"), "w", encoding="utf-8") as f:
        json.dump(jsonld, f, ensure_ascii=False, indent=2)

    # ---- CSV ----
    with open(os.path.join(args.out, "nodes.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "label", "type", "aliases", "added_in", "n_sources", "evidence"])
        for n in nodes:
            w.writerow([n["id"], n["label"], n.get("type"),
                        "; ".join(n.get("aliases", [])), n.get("added_in"),
                        len(n.get("sources", [])), evidence_str(n.get("sources"))[:500]])
    with open(os.path.join(args.out, "edges.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "subject", "relation", "object", "value", "conditions",
                    "stance", "confidence", "evidence"])
        for e in edges:
            w.writerow([e["id"], nlabel.get(e["subject"], e["subject"]), e["relation"],
                        nlabel.get(e["object"], e["object"]), e.get("value") or "",
                        e.get("conditions") or "", e.get("stance"), e.get("confidence"),
                        evidence_str(e.get("sources"))[:500]])

    # ---- report.md ----
    L = ["# 文献知识图谱构建报告", ""]
    L.append(f"- 案例: {result['case_id']}  | 状态: {status}")
    L.append(f"- 论文 {stats['papers']} 篇 | 节点 {stats['nodes']} | 边 {stats['edges']} | "
             f"合并处置 {stats['merge_records']} 条 | 查询 {stats['queries_executed']} 个"
             f"（{stats['queries_not_found']} 个无结果）")
    L.append("")
    L.append("## 一、论文来源")
    for p in papers:
        L.append(f"- **{p.get('source_id')}**: {p.get('title')}")
        L.append(f"  DOI: {p.get('doi')} | 作者: {p.get('authors')} | 许可: {p.get('license')}")
    L.append("")
    L.append("## 二、节点清单（按类型）")
    by_type = {}
    for n in nodes:
        by_type.setdefault(n.get("type", "?"), []).append(n)
    for t, ns in by_type.items():
        L.append(f"### {t}（{len(ns)}）")
        for n in ns:
            al = f"（别名: {'; '.join(n['aliases'])}）" if n.get("aliases") else ""
            L.append(f"- **{n['id']} {n['label']}**{al} — {n.get('summary', '')}")
            L.append(f"  证据: {evidence_str(n.get('sources'))}")
        L.append("")
    L.append("## 三、边清单（关系）")
    for e in edges:
        v = f" = {e['value']}" if e.get("value") else ""
        c = f"〔条件: {e['conditions']}〕" if e.get("conditions") else ""
        nt = f"〔{e['note']}〕" if e.get("note") else ""
        L.append(f"- **{e['id']}** {nlabel.get(e['subject'], e['subject'])} "
                 f"—{e['relation']}→ {nlabel.get(e['object'], e['object'])}{v}{c} "
                 f"[{e.get('stance')}/{e.get('confidence')}]{nt}")
        L.append(f"  证据: {evidence_str(e.get('sources'))}")
    L.append("")
    L.append("## 四、别名合并与冲突处置")
    for m in merges:
        if m.get("decision") == "merged":
            L.append(f"- 合并: “{m.get('alias')}” → **{m.get('canonical')} "
                     f"{nlabel.get(m.get('canonical'), '')}** — {m.get('justification')}")
        else:
            L.append(f"- 不合并: **{m.get('node_a')} {nlabel.get(m.get('node_a'), '')}** ↔ "
                     f"**{m.get('node_b')} {nlabel.get(m.get('node_b'), '')}** — "
                     f"{m.get('justification')}")
    L.append("")
    L.append("## 五、查询问答（真实执行）")
    for r in qresults.get("queries", []):
        L.append(f"### {r.get('id')}: {r.get('question')}")
        L.append(f"- 类型: {r.get('type')} | 状态: {r.get('status')}")
        if r.get("explanation"):
            L.append(f"- 说明: {r['explanation']}")
        for e in r.get("edges", []):
            v = f" = {e['value']}" if e.get("value") else ""
            L.append(f"- {e['subject_label']} —{e['relation']}→ {e['object_label']}{v}")
            L.append(f"  证据: {evidence_str(e.get('sources'))}")
        for p in (r.get("paths") or [])[:3]:
            if not p:
                continue
            segs = [nlabel.get(p[0]["from"], p[0]["from"])]
            for s in p:
                e = s["edge"]
                if s["from"] == e["subject"]:
                    segs.append(f"—[{e['relation']}]→ {e['object_label']}")
                else:
                    segs.append(f"←[{e['relation']}]— {e['subject_label']}")
            L.append("- 路径: " + " ".join(segs))
        L.append("")
    L.append("## 六、不确定性与边界")
    for u in graph.get("uncertainty", []):
        L.append(f"- {u.get('topic', '')}: {u.get('detail', '')}")
    if not graph.get("uncertainty"):
        L.append("- 无")
    L.append("")
    if graph.get("change_record"):
        L.append("## 七、处置记录")
        for c in graph["change_record"]:
            L.append(f"- {c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)}")
        L.append("")
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    log(f"OK status={status} 输出: result.json / graph.jsonld / nodes.csv / edges.csv / report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
