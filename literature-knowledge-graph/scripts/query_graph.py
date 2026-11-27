#!/usr/bin/env python3
"""图谱查询执行器（纯标准库）：真实执行 graph.json 里 queries 数组中的查询。

查询类型（实体名匹配：规范名/别名均可，大小写与横线不敏感，先精确后包含）：
  entity     {"entity": "<名称>"}                 → 节点 + 全部关联边 + 证据
  relation   {"relation": "<关系id>"}             → 该类型全部边
  neighbors  {"entity": "<名称>", "depth": 1|2}   → 邻居子图
  compare    {"entity_a": "...", "entity_b": "...", "max_depth": 3}
                                                  → 直接边 + 不超过 max_depth 的路径
  by_source  {"source_id": "<论文id>"}            → 该论文贡献的节点与边

查不到的查询如实返回 status=not_found，不编造结果。

用法：python query_graph.py --graph graph.json --out query_results.json
"""
import argparse
import json
import re
import sys
from collections import deque


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def norm_key(s):
    s = re.sub(r"\s+", "", (s or "").lower())
    return s.replace("–", "-").replace("—", "-").replace("−", "-")


class Graph:
    def __init__(self, g):
        self.nodes = {n["id"]: n for n in g.get("nodes", [])}
        self.edges = g.get("edges", [])
        self.name_index = {}
        for n in self.nodes.values():
            self.name_index.setdefault(norm_key(n.get("label", "")), []).append(n["id"])
            for a in n.get("aliases", []):
                self.name_index.setdefault(norm_key(a), []).append(n["id"])

    def find(self, name):
        """先精确（归一后相等），后包含。返回去重后的节点 id 列表。"""
        key = norm_key(name)
        if key in self.name_index:
            return sorted(set(self.name_index[key]))
        hits = [nid for k, ids in self.name_index.items()
                if key and (key in k or k in key) for nid in ids]
        return sorted(set(hits))

    def incident(self, nid):
        return [e for e in self.edges if e.get("subject") == nid or e.get("object") == nid]

    def node_brief(self, nid, full=False):
        n = self.nodes.get(nid)
        if not n:
            return {"id": nid, "missing": True}
        b = {"id": nid, "label": n["label"], "type": n["type"],
             "aliases": n.get("aliases", [])}
        if full:
            b["summary"] = n.get("summary", "")
            b["sources"] = n.get("sources", [])
            b["added_in"] = n.get("added_in")
        return b

    def edge_brief(self, e):
        return {"id": e["id"], "subject": e["subject"],
                "subject_label": self.nodes.get(e["subject"], {}).get("label", e["subject"]),
                "relation": e["relation"],
                "object": e["object"],
                "object_label": self.nodes.get(e["object"], {}).get("label", e["object"]),
                "value": e.get("value"), "conditions": e.get("conditions"),
                "stance": e.get("stance"), "confidence": e.get("confidence"),
                "sources": e.get("sources", []), "note": e.get("note", "")}

    def paths(self, a, b, max_depth):
        """无向 BFS 找 a→b 的全部简单路径（≤max_depth 条边），路径记录边方向。"""
        found = []
        queue = deque([(a, [])])
        while queue:
            cur, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for e in self.incident(cur):
                nxt = e["object"] if e["subject"] == cur else e["subject"]
                if any(pnid == nxt for pnid, _ in [(x[0], None) for x in path]) or nxt == a:
                    continue
                step = {"edge": self.edge_brief(e), "from": cur, "to": nxt}
                new_path = path + [(nxt, step)]
                if nxt == b:
                    found.append([s for _, s in new_path])
                else:
                    queue.append((nxt, new_path))
        return found[:10]


def run_query(g, q):
    qtype, args = q.get("type"), q.get("args", {})
    res = {"id": q.get("id"), "question": q.get("question"), "type": qtype,
           "args": args, "status": "ok", "nodes": [], "edges": [], "paths": []}

    if qtype == "entity":
        ids = g.find(args.get("entity", ""))
        if not ids:
            res["status"] = "not_found"
            res["explanation"] = f"图中未找到实体 {args.get('entity')}"
            return res
        nid = ids[0]
        res["nodes"] = [g.node_brief(nid, full=True)]
        res["edges"] = [g.edge_brief(e) for e in g.incident(nid)]
        if len(ids) > 1:
            res["note"] = f"名称命中多个节点: {ids}，展示第一个；其余请核查是否应合并"
            res["also_matched"] = ids[1:]

    elif qtype == "relation":
        rel = args.get("relation", "")
        hits = [e for e in g.edges if e.get("relation") == rel]
        if not hits:
            res["status"] = "not_found"
            res["explanation"] = f"图中没有 relation={rel} 的边"
            return res
        res["edges"] = [g.edge_brief(e) for e in hits]
        involved = sorted({e["subject"] for e in hits} | {e["object"] for e in hits})
        res["nodes"] = [g.node_brief(i) for i in involved]

    elif qtype == "neighbors":
        depth = int(args.get("depth", 1))
        ids = g.find(args.get("entity", ""))
        if not ids:
            res["status"] = "not_found"
            res["explanation"] = f"图中未找到实体 {args.get('entity')}"
            return res
        seen_nodes, seen_edges, frontier = {ids[0]}, set(), {ids[0]}
        for _ in range(max(1, min(depth, 3))):
            nxt = set()
            for cur in frontier:
                for e in g.incident(cur):
                    seen_edges.add(e["id"])
                    other = e["object"] if e["subject"] == cur else e["subject"]
                    if other not in seen_nodes:
                        nxt.add(other)
                    seen_nodes.add(other)
            frontier = nxt
        res["nodes"] = [g.node_brief(i, full=True) for i in sorted(seen_nodes)]
        res["edges"] = [g.edge_brief(e) for e in g.edges if e["id"] in seen_edges]

    elif qtype == "compare":
        a_ids, b_ids = g.find(args.get("entity_a", "")), g.find(args.get("entity_b", ""))
        if not a_ids or not b_ids:
            res["status"] = "not_found"
            res["explanation"] = (f"实体未找到: "
                                  f"{'' if a_ids else args.get('entity_a')} "
                                  f"{'' if b_ids else args.get('entity_b')}").strip()
            return res
        a, b = a_ids[0], b_ids[0]
        max_depth = int(args.get("max_depth", 3))
        direct = [e for e in g.incident(a)
                  if b in (e.get("subject"), e.get("object"))]
        res["edges"] = [g.edge_brief(e) for e in direct]
        res["paths"] = [] if direct else g.paths(a, b, max(1, min(max_depth, 4)))
        if not direct and not res["paths"]:
            res["status"] = "not_found"
            res["explanation"] = f"{a} 与 {b} 之间在 {max_depth} 步内没有关系路径"
        res["nodes"] = [g.node_brief(a), g.node_brief(b)]

    elif qtype == "by_source":
        sid = args.get("source_id", "")
        n_hits = [n for n in g.nodes.values()
                  if any(s.get("source_id") == sid for s in n.get("sources", []))]
        e_hits = [e for e in g.edges
                  if any(s.get("source_id") == sid for s in e.get("sources", []))]
        if not n_hits and not e_hits:
            res["status"] = "not_found"
            res["explanation"] = f"没有证据来自 {sid} 的节点或边"
            return res
        res["nodes"] = [g.node_brief(n["id"]) for n in n_hits]
        res["edges"] = [g.edge_brief(e) for e in e_hits]

    else:
        res["status"] = "error"
        res["explanation"] = f"未知查询类型: {qtype}"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        graph = json.load(open(args.graph, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"FATAL input: {e}")
        return 2
    g = Graph(graph)
    queries = graph.get("queries", [])
    results = [run_query(g, q) for q in queries]
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"queries": results}, f, ensure_ascii=False, indent=2)
    for r in results:
        log(f"{r['id']} [{r['type']}] {r['status']}: "
            f"nodes={len(r['nodes'])} edges={len(r['edges'])} paths={len(r.get('paths', []))}")
    log(f"OK executed={len(results)} "
        f"not_found={sum(1 for r in results if r['status'] == 'not_found')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
