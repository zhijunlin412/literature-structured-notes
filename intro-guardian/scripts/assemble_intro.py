# -*- coding: utf-8 -*-
"""assemble_intro.py — 组装引言与相关工作成稿与交付物。

引用编号按正文首次出现顺序由脚本确定性分配（模型不编号），
文献表按 GB/T 7714 期刊格式生成；转述-证据对照表随报告交付，供第三方复核。

用法:
  python assemble_intro.py --case /input/case.json --case-id demo \
      --draft work/draft.json --library library.json \
      --check work/check_report.json --out /app/output
"""
import argparse, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def fmt_authors_gbt(authors):
    if not authors:
        return ""
    out = []
    for a in authors[:3]:
        if "," in a:
            last, first = a.split(",", 1)
            inits = " ".join(re.findall(r"[A-Z]", first))
            out.append(f"{last.strip()} {inits}".strip())
        else:
            parts = a.strip().split()
            if len(parts) >= 2:
                inits = " ".join(re.findall(r"[A-Z]", " ".join(parts[:-1])))
                out.append(f"{parts[-1]} {inits}".strip())
            else:
                out.append(a.strip())
    return ", ".join(out) + (", et al." if len(authors) > 3 else "")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--case-id", default="unknown-case")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--check", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    case_id = a.case_id
    if a.case and os.path.exists(a.case):
        case_id = json.load(open(a.case, encoding="utf-8-sig")).get("case_id", case_id)

    draft = json.load(open(a.draft, encoding="utf-8-sig"))
    lib = json.load(open(a.library, encoding="utf-8-sig"))
    check = json.load(open(a.check, encoding="utf-8"))
    works = {w["key"]: w for w in lib.get("works", [])}

    # 确定性编号：按成稿中首次出现顺序
    order = []
    def cite(keys):
        for k in keys:
            if k in works and k not in order:
                order.append(k)
        nums = [order.index(k) + 1 for k in keys if k in works]
        return "[" + ",".join(str(n) for n in sorted(nums)) + "]" if nums else ""

    lines = ["## 1. 研究背景与意义", ""]
    for item in draft.get("background", []):
        lines.append(item["text"] + cite(item.get("citations", [])))
    lines += ["", "## 2. 相关工作", ""]
    for gi, g in enumerate(draft.get("related_work", {}).get("groups", []), 1):
        lines.append(f"### 2.{gi} {g['dimension']}")
        lines.append("")
        for w in g.get("works", []):
            lines.append(w["claim"] + cite([w["key"]]))
        if g.get("comparison"):
            lines.append("")
            lines.append(g["comparison"])
        lines.append("")
    lines += ["## 3. 研究空白与本文工作", ""]
    for g in draft.get("gap", []):
        tag = "（作者判断）" if g.get("status") == "author_judgment" else ""
        lines.append(g["statement"] + cite(g.get("derived_from", [])) + tag)
    lines += ["", "## 4. 主要贡献", ""]
    for i, c in enumerate(draft.get("contributions", []), 1):
        lines.append(f"({i}) {c['statement']}" + cite(c.get("citations", [])))
    lines += ["", "## 参考文献", ""]
    for i, k in enumerate(order, 1):
        w = works[k]
        auth = fmt_authors_gbt(w.get("authors", []))
        venue = w.get("venue", "")
        yr = w.get("year", "")
        title = (w.get("title") or "").rstrip(". ")
        doi = f" DOI: {w['doi']}." if w.get("doi") else ""
        ref = f"[{i}] {auth}. {title}[J]. {venue}, {yr}.{doi}"
        ref = re.sub(r"\.{2,}", ".", ref)
        lines.append(ref)
    manuscript = "\n".join(lines) + "\n"
    with open(os.path.join(a.out, "introduction.md"), "w", encoding="utf-8") as f:
        f.write(manuscript)

    status = "success" if check["status"] == "pass" else (
        "needs_fix" if check["status"] == "fail" else "success_with_warnings")

    result = {
        "case_id": case_id, "status": status,
        "stats": {
            "sections": ["background", "related_work", "gap", "contributions"],
            "groups": len(draft.get("related_work", {}).get("groups", [])),
            "works_cited": len(order),
            "gaps": len(draft.get("gap", [])),
            "contributions": len(draft.get("contributions", [])),
            "check_errors": len(check.get("errors", [])),
            "check_warnings": len(check.get("warnings", [])),
        },
        "citation_order": order,
        "evidence_map": [
            {"key": w["key"], "claim": w["claim"], "quote": w["evidence"]["quote"]}
            for g in draft.get("related_work", {}).get("groups", [])
            for w in g.get("works", []) if w.get("evidence", {}).get("quote")
        ],
        "gap_derivations": draft.get("gap", []),
        "contribution_anchors": draft.get("contributions", []),
        "check_errors": check.get("errors", []),
        "check_warnings": check.get("warnings", []),
        "human_review": draft.get("human_review", []),
        "uncertainty": draft.get("uncertainty", []),
        "sources": draft.get("sources", []),
    }
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    rep = [f"# 引言与相关工作报告\n",
           f"- 案例: {case_id} | 状态: {status}",
           f"- 分组 {result['stats']['groups']} | 引用 {len(order)} 篇 | 空白 {result['stats']['gaps']} | 贡献 {result['stats']['contributions']}",
           f"- 校验 error {result['stats']['check_errors']} / warning {result['stats']['check_warnings']}\n",
           "## 转述—证据对照（逐字绑定）\n"]
    for m in result["evidence_map"]:
        rep.append(f"- **{m['key']}**: {m['claim']}")
        rep.append(f"  证据: “{m['quote'][:120]}…”\n")
    if draft.get("gap"):
        rep.append("## 空白推导链\n")
        for g in draft["gap"]:
            rep.append(f"- {g['statement']}（源自 {g.get('derived_from')}；{g.get('basis','')}）")
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print(f"status={status} | 引用 {len(order)} 篇 | error {result['stats']['check_errors']} | warning {result['stats']['check_warnings']}")
    print("output:", a.out)

if __name__ == "__main__":
    main()
