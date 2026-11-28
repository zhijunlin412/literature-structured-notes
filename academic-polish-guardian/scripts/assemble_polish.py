# -*- coding: utf-8 -*-
"""assemble_polish.py — 应用修改清单、组装最终交付物。

核心机制：每处修改带原文片段（original_span），必须在当前文本中**逐字唯一命中**
才被替换——这是"讲得清"的机器保障：改文与原文的对应不靠记忆，靠逐字核验。

设计原则（预算守恒）：模型只写 edits.json 这一小份"答案补丁"，润色文本、CSV、
报告全部由脚本确定性生成；脚本输出只读，模型不得改写。

输入:
  --case      case.json（取 case_id；无则手写 --case-id）
  --original  原文文本
  --edits     edits.json: {"edits":[{"id","location","original_span","revised_span",
                                     "type","severity","reason"}],
                            "reviewed_units":["..."],"human_review":[...],"uncertainty":[...]}
  --glossary  术语表（可选）
  --lexicon   hedging_lexicon.json（可选；给了就跑强度校验）
  --out       输出目录

输出: polished.md, edits.csv, result.json, report.md（含校验结论）
"""
import argparse, csv, json, os, re, subprocess, sys
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from extract_facts import extract, norm_num  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))

EDIT_REQUIRED = {"id": str, "original_span": str, "revised_span": str, "type": str, "reason": str}


def run_checker(cmd):
    p = subprocess.run([sys.executable] + cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def span_multiset(span):
    """片段内的数值+单位多重集（单位大小写折叠）。"""
    f = extract(span)
    return Counter((n["value"], n["unit"].lower()) for n in f["numbers"]), f


def span_tiers(span, lexicon):
    """片段内限定词 tier 多重集（与 check_preservation 同一套词表逻辑）。"""
    tiers = lexicon["tiers"]
    words = sorted({w for t in tiers.values() for w in t["en"] + t["zh"]}, key=len, reverse=True)
    low = span.lower()
    hits = Counter()
    for w in words:
        pat = re.compile(r"(?<![A-Za-z])" + re.escape(w.lower()) + r"(?![A-Za-z])")
        n = len(pat.findall(low))
        if n:
            hits[w.lower()] = n
            low = pat.sub(" ", low)
    out = Counter()
    for key, tier in tiers.items():
        for w in tier["en"] + tier["zh"]:
            if w.lower() in hits:
                out[key] += hits[w.lower()]
    return out


def per_edit_checks(edit, lexicon):
    """片段级"没改坏"绑定：修改只允许动语言，不许动事实与强度。
    这正是"数字集合比对证明不了绑对位置"的对策——在每处修改的片段内部比对。"""
    errs = []
    o, r = edit["original_span"], edit["revised_span"]
    mo, _fo = span_multiset(o)
    mr, _fr = span_multiset(r)
    if mo != mr:
        errs.append(f"{edit['id']}: 片段内数值不守恒 {dict(mo)} → {dict(mr)}（数字只允许原文照搬）")
    co, cr = Counter(_fo["citations"]), Counter(_fr["citations"])
    if co != cr:
        errs.append(f"{edit['id']}: 片段内引用标记变化 {dict(co)} → {dict(cr)}")
    go, gr = Counter(_fo["figrefs"]), Counter(_fr["figrefs"])
    if go != gr:
        errs.append(f"{edit['id']}: 片段内图表指向变化 {dict(go)} → {dict(gr)}")
    if lexicon:
        to, tr = span_tiers(o, lexicon), span_tiers(r, lexicon)
        if to != tr:
            errs.append(f"{edit['id']}: 片段内限定强度变化 {dict(to)} → {dict(tr)}（may 不许升 demonstrate，强不许降弱）")
    return errs


def count_units(text):
    """清点原文的独立"审阅单元"（非空段落数）——这是覆盖率的**外部**分母：
    不来自 Agent 自己处理了哪些，而来自原文本身。"""
    return len([p for p in re.split(r"\n\s*\n", text) if p.strip()])

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
    lexicon = json.load(open(a.lexicon, encoding="utf-8")) if a.lexicon else None

    # ---- edits.json 输入校验：检查器自身不能先崩（坏条目报 failed，不抛异常）----
    try:
        edits_doc = json.load(open(a.edits, encoding="utf-8-sig"))
    except Exception as ex:
        print(f"FATAL: edits.json 不是合法 JSON: {ex}")
        sys.exit(2)
    edits_raw = edits_doc.get("edits", [])
    if not isinstance(edits_raw, list):
        print("FATAL: edits.json 的 edits 字段必须是数组")
        sys.exit(2)
    edits, failed = [], []
    for i, e in enumerate(edits_raw):
        if not isinstance(e, dict):
            failed.append({"id": f"#{i}", "reason": "条目不是对象"})
            continue
        bad = [k for k, t in EDIT_REQUIRED.items() if not isinstance(e.get(k), t)]
        if bad:
            failed.append({"id": str(e.get("id", f"#{i}")), "reason": f"字段缺失或类型错误: {bad}"})
            continue
        edits.append(e)

    # ---- 片段级"没改坏"绑定（在应用修改前先做，违规的修改直接拒绝）----
    span_errors = []
    rejected_ids = set()
    for e in edits:
        errs = per_edit_checks(e, lexicon)
        if errs:
            span_errors.extend(errs)
            rejected_ids.add(e["id"])
            failed.append({"id": e["id"], "reason": "片段级校验拒绝：" + "；".join(errs)})

    text = original
    applied = []
    for e in edits:
        if e["id"] in rejected_ids:
            continue
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

    # ---- 覆盖率：分母来自原文本身（外部清单），不来自 Agent 自报 ----
    units_total = count_units(original)
    reviewed = edits_doc.get("reviewed_units", [])
    coverage_warnings = []
    if not reviewed:
        coverage_warnings.append("未提供 reviewed_units：无法证明指定范围被逐段审阅（分母是原文的段落数，不是改过的段落数）")
    else:
        n_rev = len(reviewed)
        if n_rev < units_total:
            coverage_warnings.append(f"审阅单元 {n_rev}/{units_total}：有 {units_total - n_rev} 个段落未见审阅声明；无修改的段落也应列入 reviewed_units 以示'看过、无需改'")

    n_err = sum(len(c.get("errors", [])) for c in checks.values()) + len(span_errors)
    n_warn = sum(len(c.get("warnings", [])) for c in checks.values()) + len(coverage_warnings)

    if span_errors or any(len(c.get("errors", [])) for c in checks.values()):
        status = "needs_fix"
    elif failed:
        status = "partial"
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
            "units_total": units_total,
            "units_reviewed": len(reviewed),
            "by_type": {},
        },
        "files": {
            "polished": "polished.md",
            "edit_log": "edits.csv",
            "preservation_report": "preservation_report.json" if a.lexicon else None,
            "terminology_report": "terminology_report.json" if a.glossary else None,
        },
        "failed_edits": failed,
        "span_check_errors": span_errors,
        "coverage_warnings": coverage_warnings,
        "reviewed_units": reviewed,
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
             f"- 修改 {len(applied)}/{len(edits)} 处生效 | 审阅单元 {len(reviewed)}/{units_total} | 校验 error {n_err} / warning {n_warn}\n",
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
    if span_errors:
        lines.append("## 片段级校验（没改坏绑定）拒绝的修改\n")
        for x in span_errors:
            lines.append(f"- ❌ {x}")
        lines.append("")
    if coverage_warnings:
        lines.append("## 覆盖率（分母来自原文清点）\n")
        for x in coverage_warnings:
            lines.append(f"- ⚠️ {x}")
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
