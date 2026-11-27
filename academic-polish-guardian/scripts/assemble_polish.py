# -*- coding: utf-8 -*-
"""assemble_polish.py — 应用修改清单、组装最终交付物。

核心机制：每处修改带原文片段（original_span），必须在当前文本中**逐字唯一命中**
才被替换——这是"讲得清"的机器保障：改文与原文的对应不靠记忆，靠逐字核验。

输入:
  --case      case.json（取 case_id；无则手写 --case-id）
  --original  原文文本
  --edits     edits.json: {"edits":[{"id","location","original_span","revised_span",
                                     "type","severity","reason"}],
                            "human_review":[...], "uncertainty":[...]}
  --glossary  术语表（可选）
  --lexicon   hedging_lexicon.json（可选；给了就跑强度校验）
  --out       输出目录

输出: polished.md, edits.csv, result.json, report.md（含校验结论）
"""
import argparse, csv, json, os, subprocess, sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from extract_facts import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

def run_checker(cmd):
    p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--case-id", default="unknown-case")
    ap.add_argument("--original", required=True)
    ap.add_argument("--edits", required=True)
    ap.add_argument("--glossary")
    ap.add_argument("--lexicon")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    case_id = a.case_id
    if a.case and os.path.exists(a.case):
        case_id = json.load(open(a.case, encoding="utf-8-sig")).get("case_id", case_id)

    original = open(a.original, encoding="utf-8-sig").read()
    edits_doc = json.load(open(a.edits, encoding="utf-8-sig"))
    edits = edits_doc["edits"]

    text = original
    applied, failed = [], []
    for e in edits:
        span = e["original_span"]
        n = text.count(span)
        if n == 0:
            failed.append({"id": e["id"], "reason": "original_span 在当前文本中找不到（可能被前面的修改覆盖或摘录有误）"})
            continue
        if n > 1:
            failed.append({"id": e["id"], "reason": f"original_span 命中 {n} 处，不唯一；请加长上下文"})
            continue
        text = text.replace(span, e["revised_span"], 1)
        applied.append(e)

    polished_path = os.path.join(a.out, "polished.md")
    with open(polished_path, "w", encoding="utf-8") as f:
        f.write(text)

    # CSV 修改清单
    csv_path = os.path.join(a.out, "edits.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "location", "type", "severity", "original_span", "revised_span", "reason", "applied"])
        for e in edits:
            w.writerow([e["id"], e.get("location", ""), e["type"], e.get("severity", ""),
                        e["original_span"], e["revised_span"], e["reason"],
                        "yes" if e in applied else "FAILED"])

    # 校验
    orig_tmp = os.path.join(a.out, "_orig_snapshot.txt")
    with open(orig_tmp, "w", encoding="utf-8") as f:
        f.write(original)

    checks = {}
    if a.lexicon:
        rc, log = run_checker([os.path.join(HERE, "check_preservation.py"),
                               "--original", orig_tmp, "--revised", polished_path,
                               "--lexicon", a.lexicon,
                               "--out", os.path.join(a.out, "preservation_report.json")])
        checks["preservation"] = json.load(open(os.path.join(a.out, "preservation_report.json"), encoding="utf-8"))
    if a.glossary:
        rc, log = run_checker([os.path.join(HERE, "check_terminology.py"),
                               "--text", polished_path, "--glossary", a.glossary,
                               "--original", a.original,
                               "--out", os.path.join(a.out, "terminology_report.json")])
        checks["terminology"] = json.load(open(os.path.join(a.out, "terminology_report.json"), encoding="utf-8"))
    os.remove(orig_tmp)

    n_err = sum(len(c.get("errors", [])) for c in checks.values())
    n_warn = sum(len(c.get("warnings", [])) for c in checks.values())

    if failed:
        status = "partial"
    elif n_err:
        status = "needs_fix"
    else:
        status = "success"

    result = {
        "case_id": case_id,
        "status": status,
        "stats": {
            "edits_total": len(edits),
            "edits_applied": len(applied),
            "edits_failed": len(failed),
            "check_errors": n_err,
            "check_warnings": n_warn,
            "by_type": {},
        },
        "files": {
            "polished": "polished.md",
            "edit_log": "edits.csv",
            "preservation_report": "preservation_report.json" if a.lexicon else None,
            "terminology_report": "terminology_report.json" if a.glossary else None,
        },
        "failed_edits": failed,
        "human_review": edits_doc.get("human_review", []),
        "uncertainty": edits_doc.get("uncertainty", []),
        "sources": edits_doc.get("sources", []),
    }
    for e in edits:
        result["stats"]["by_type"][e["type"]] = result["stats"]["by_type"].get(e["type"], 0) + 1
    with open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 人读报告
    lines = [f"# 学术润色报告\n",
             f"- 案例: {case_id} | 状态: {status}",
             f"- 修改 {len(applied)}/{len(edits)} 处生效 | 校验 error {n_err} / warning {n_warn}\n",
             "## 修改清单（原文 → 改文）\n"]
    for e in edits:
        mark = "✅" if e in applied else "❌ 未应用"
        lines.append(f"### {e['id']} [{e['type']} / {e.get('severity','')}] {mark}")
        lines.append(f"- 位置: {e.get('location','')}")
        lines.append(f"- 原文: {e['original_span']}")
        lines.append(f"- 改文: {e['revised_span']}")
        lines.append(f"- 理由: {e['reason']}\n")
    if failed:
        lines.append("## ⚠️ 未应用的修改\n")
        for x in failed:
            lines.append(f"- {x['id']}: {x['reason']}")
        lines.append("")
    for name, c in checks.items():
        lines.append(f"## 校验：{name} → {c['status']}\n")
        for e in c.get("errors", []):
            lines.append(f"- ❌ {e['detail']}")
        for w in c.get("warnings", []):
            lines.append(f"- ⚠️ {w['detail']}")
        lines.append("")
    if edits_doc.get("human_review"):
        lines.append("## 需人工确认\n")
        for h in edits_doc["human_review"]:
            lines.append(f"- {h}")
        lines.append("")
    if edits_doc.get("uncertainty"):
        lines.append("## 不确定性\n")
        for u in edits_doc["uncertainty"]:
            lines.append(f"- {u}")
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"status={status} | 应用 {len(applied)}/{len(edits)} | error {n_err} | warning {n_warn}")
    print("output:", a.out)

if __name__ == "__main__":
    main()
