# -*- coding: utf-8 -*-
"""assemble_refs.py — 组装引用管理交付物（GB/T 7714 列表 + result.json + 报告）。

模型不做格式化算术：条目字段由 Agent 结构化，格式化与校验由脚本完成。

用法:
  python assemble_refs.py --case /input/case.json --case-id demo \
      --synced work/sync/entries_synced.json --change-log work/sync/change_log.json \
      --manuscript work/sync/manuscript_updated.md \
      --check work/check_report.json \
      --claim-map work/claim_map.json       # 可选：论断-引用匹配记录
      --styles assets/citation_styles.json --out /app/output
"""
import argparse, json, os, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def fmt_authors(authors, lang="en"):
    """GB/T 7714: 姓 + 名缩写（大写字母，空格分隔）；3 名以上取前 3 + ', et al.'。"""
    import re
    if not authors:
        return ""
    out = []
    for a in authors[:3]:
        if "," in a:
            last, first = a.split(",", 1)
            inits = " ".join(re.findall(r"[A-Z]", first))
            out.append(f"{last.strip()} {inits}".strip())
        else:
            out.append(a.strip())
    suffix = ", et al." if len(authors) > 3 else ""
    return ", ".join(out) + suffix

def format_entry(e, styles):
    t = e.get("type", "journal")
    tmpl = styles["styles"]["gbt7714"]["types"].get(t,
            styles["styles"]["gbt7714"]["types"]["journal"])["template"]
    s = tmpl
    s = s.replace("{authors}", fmt_authors(e.get("authors", [])))
    for k in ("title", "journal", "year", "volume", "issue", "pages",
              "proceedings", "place", "publisher", "institution", "url",
              "accessed", "doi"):
        s = s.replace("{%s}" % k, str(e.get(k) or ""))
    # 卷(期)
    if "{, volume(issue)}" in s:
        vi = ""
        if e.get("volume"):
            vi = ", " + str(e["volume"]) + ("(%s)" % e["issue"] if e.get("issue") else "")
        s = s.replace("{, volume(issue)}", vi)
    if "{: pages}" in s:
        s = s.replace("{: pages}", (": " + str(e["pages"])) if e.get("pages") else "")
    if "{. DOI: doi}" in s:
        s = s.replace("{. DOI: doi}", (". DOI: " + str(e["doi"])) if e.get("doi") else "")
    import re
    s = re.sub(r"\{[^}]*\}", "", s)          # 清掉未填的可选占位
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"\.{2,}", ".", s)   # et al. + 模板句点的重复
    if not s.endswith("."):
        s += "."
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--case-id", default="unknown-case")
    ap.add_argument("--synced", required=True)
    ap.add_argument("--change-log", required=True)
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--check", required=True)
    ap.add_argument("--claim-map")
    ap.add_argument("--styles", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    case_id = a.case_id
    if a.case and os.path.exists(a.case):
        case_id = json.load(open(a.case, encoding="utf-8-sig")).get("case_id", case_id)

    synced = json.load(open(a.synced, encoding="utf-8"))
    entries, uncited = synced["entries"], synced.get("uncited_entries", [])
    log = json.load(open(a.change_log, encoding="utf-8"))
    check = json.load(open(a.check, encoding="utf-8"))
    styles = json.load(open(a.styles, encoding="utf-8"))
    claim_map = json.load(open(a.claim_map, encoding="utf-8")) if a.claim_map and os.path.exists(a.claim_map) else {"claims": []}

    lines = []
    for e in entries:
        lines.append(f"[{e['key']}] {format_entry(e, styles)}")
    if uncited:
        lines.append("")
        lines.append("（以下条目全篇未被引用，未编入正文编号，是否删除请作者确认）")
        for e in uncited:
            lines.append(f"[未引用] {format_entry(e, styles)}")
    with open(os.path.join(a.out, "references_gbt7714.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    import shutil
    shutil.copy(a.manuscript, os.path.join(a.out, "manuscript_updated.md"))

    status = "success" if check["status"] == "pass" else (
        "needs_fix" if check["status"] == "fail" else "success_with_warnings")

    result = {
        "case_id": case_id,
        "status": status,
        "stats": {
            "entries_final": len(entries),
            "entries_uncited": len(uncited),
            "merges": len(log.get("merges_applied", [])),
            "dropped": len(log.get("dropped", [])),
            "renumber_map": log.get("renumber_map", {}),
            "check_errors": len(check.get("errors", [])),
            "check_warnings": len(check.get("warnings", [])),
            "claims_mapped": len(claim_map.get("claims", [])),
        },
        "files": {
            "manuscript_updated": "manuscript_updated.md",
            "references_gbt7714": "references_gbt7714.txt",
            "check_report": "check_report.json",
        },
        "claim_map": claim_map.get("claims", []),
        "merge_records": log.get("merges_applied", []),
        "uncited_entries": [e.get("key") for e in uncited],
        "check_errors": check.get("errors", []),
        "check_warnings": check.get("warnings", []),
        "human_review": claim_map.get("human_review", []),
        "uncertainty": claim_map.get("uncertainty", []),
        "sources": claim_map.get("sources", []),
    }
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    rep = [f"# 引用管理报告\n",
           f"- 案例: {case_id} | 状态: {status}",
           f"- 最终条目 {len(entries)} | 合并 {result['stats']['merges']} 组 | 未引用 {len(uncited)} | "
           f"校验 error {result['stats']['check_errors']} / warning {result['stats']['check_warnings']}\n",
           "## 编号重排（旧 → 新）\n"]
    for k, v in log.get("renumber_map", {}).items():
        rep.append(f"- [{k}] → [{v}]")
    if log.get("merges_applied"):
        rep.append("\n## 合并记录\n")
        for m in log["merges_applied"]:
            rep.append(f"- 保留 [{m['survivor']}]，吸收 {m['absorbed']} — {m.get('justification','')}（判据 {m.get('matched_criteria')}）")
    if claim_map.get("claims"):
        rep.append("\n## 论断—引用匹配\n")
        for c in claim_map["claims"]:
            rep.append(f"- {c}")
    if check.get("warnings"):
        rep.append("\n## 校验警告\n")
        for w in check["warnings"]:
            rep.append(f"- ⚠️ {w}")
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rep) + "\n")
    print(f"status={status} | 条目 {len(entries)} | 合并 {result['stats']['merges']} | "
          f"error {result['stats']['check_errors']} | warning {result['stats']['check_warnings']}")
    print("output:", a.out)

if __name__ == "__main__":
    main()
