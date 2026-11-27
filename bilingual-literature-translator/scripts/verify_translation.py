#!/usr/bin/env python3
"""Deterministic translation verifier (stdlib only).

Checks, per aligned unit:
  coverage   every source unit has exactly one alignment entry
  numbers    numeric tokens (incl. decimals, %, exponents) preserved
  citations  bracket markers [12] / [12,13] and superscript clusters ¹²³ preserved
  figrefs    Fig./Table/Scheme/Eq. references preserved
  formulas   tokens carrying Unicode sub/superscripts (Fe³⁺, H₂, CO₃²⁻) preserved verbatim
  markers    [待确认] / [未译] occurrences listed for human review
  length     translation/source length ratio within a plausible band

Inputs:  --extract extract.json --alignment alignment.json
Outputs: --out verify_report.json  --checklist human_checklist.md
Exit 0 = no blocking issues, 1 = issues found, 2 = input error.
"""
import argparse
import json
import re
import sys

NUM_RE = re.compile(r"\d+(?:\.\d+)?(?:\s*[×x]\s*10[-−⁺⁻\d]+)?\s*(?:%|°C|mV|kV|mA|A|cm|mm|nm|μm|eV|eV|M|mM|mol|mg|g|kg|min|h|s|kW|W|mL|L|rpm|K)?(?![A-Za-z0-9])")
CITE_BRACKET_RE = re.compile(r"\[[\d,，\-–—\s]+\]")
SUP_CHARS = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
SUB_CHARS = "₀₁₂₃₄₅₆₇₈₉₊₋"
CITE_SUP_RE = re.compile("[" + SUP_CHARS + "†‡*]+")
# formula tokens carry subscripts (H₂, CO₃²⁻) or charge signs (Fe³⁺);
# superscript digits alone are citations/units and are checked separately.
# The token is a run of formula characters only, so CJK text/punctuation
# cannot glue onto it (superscript ¹²³ are U+00B9/B2/B3, included explicitly).
FCHARS = r"A-Za-z0-9()·+#/\-₀-₉⁰-⁹⁺⁻¹²³"
FORMULA_RE = re.compile("[" + FCHARS + "]*[₀-₉⁺⁻][" + FCHARS + "]*")


def formula_tokens(text):
    # drop parentheses: CJK full-width parens in translations break pairing anyway
    return sorted(m.group(0).replace("(", "").replace(")", "")
                  for m in FORMULA_RE.finditer(text))
FIGREF_RE = re.compile(r"\b(?:Fig(?:ure)?s?\.?|Table|Scheme|Eq(?:uation)?s?\.?)\s*S?\d+[a-z]?(?:\s*(?:and|,|–|-)\s*S?\d+[a-z]?)*", re.I)
PENDING_RE = re.compile(r"\[(待确认|未译|不确定)\]")


def log(m):
    print(m, flush=True)


def tokens(rx, text):
    return sorted(m.group(0).strip() for m in rx.finditer(text))


def diff_multiset(src_list, zh_list):
    """items in src_list whose multiplicity is not covered by zh_list"""
    rest = list(zh_list)
    missing = []
    for t in src_list:
        if t in rest:
            rest.remove(t)
        else:
            missing.append(t)
    return missing


def verify_unit(u):
    """Per-unit checks. Must never crash on malformed entries (null fields,
    wrong types): report them as issues instead - a checker that crashes on
    unexpected input proves nothing."""
    issues = []
    if not isinstance(u, dict):
        return [{"kind": "schema", "detail": "译文条目不是对象"}]
    if u.get("status") in ("skipped", "untranslated"):
        return issues
    src = u.get("source", "")
    zh = u.get("translation", "")
    if not isinstance(src, str) or not isinstance(zh, str):
        issues.append({"kind": "schema",
                       "detail": f"source/translation 不是字符串（{type(src).__name__}/{type(zh).__name__}）"})
        return issues
    if u.get("status") not in ("translated", "partial"):
        issues.append({"kind": "schema", "detail": f"status 非法: {u.get('status')}"})
        return issues
    if not zh.strip():
        issues.append({"kind": "empty_translation", "detail": "译文为空"})
        return issues
    for kind, label in (("numbers", "数字/单位"),
                        ("citations_bracket", "方括号引用"),
                        ("citations_sup", "上标引用"),
                        ("figrefs", "图表引用")):
        rx = {"numbers": NUM_RE, "citations_bracket": CITE_BRACKET_RE,
              "citations_sup": CITE_SUP_RE, "figrefs": FIGREF_RE}[kind]
        missing = diff_multiset(tokens(rx, src), tokens(rx, zh))
        if missing:
            issues.append({"kind": kind, "detail": f"{label}缺失: {missing[:8]}"})
    missing = diff_multiset(formula_tokens(src), formula_tokens(zh))
    if missing:
        issues.append({"kind": "formulas", "detail": f"上下标式缺失: {missing[:8]}"})
    src_words = len(src.split())
    if src_words >= 20:
        ratio = len(zh) / max(1, src_words)
        if ratio < 0.3 or ratio > 6.0:
            issues.append({"kind": "length", "detail": f"译文/源文长度比 {ratio:.2f} 异常"})
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--alignment", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--checklist", required=True)
    args = ap.parse_args()
    try:
        with open(args.extract, encoding="utf-8") as f:
            extract = json.load(f)
        with open(args.alignment, encoding="utf-8") as f:
            alignment = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log(f"FATAL input: {e}")
        return 2

    src_units = {u["id"]: u for u in extract.get("units", []) if isinstance(u, dict) and "id" in u}
    al_units = alignment.get("units", [])
    if not isinstance(al_units, list):
        log("FATAL: alignment.units is not a list")
        return 2
    al_ids = [u.get("id") for u in al_units if isinstance(u, dict)]
    issues = [{"unit": "?", "kind": "schema", "detail": "译文条目不是对象"}
              for u in al_units if not isinstance(u, dict)]

    # coverage
    for uid in src_units:
        n = al_ids.count(uid)
        if n == 0:
            issues.append({"unit": uid, "kind": "coverage", "detail": "源单元无对应译文条目"})
        elif n > 1:
            issues.append({"unit": uid, "kind": "coverage", "detail": f"重复译文条目 x{n}"})
    for uid in al_ids:
        if uid not in src_units:
            issues.append({"unit": uid, "kind": "coverage", "detail": "译文条目无对应源单元（多余 id）"})

    # per-unit checks
    pending = []
    translated = 0
    for u in al_units:
        if not isinstance(u, dict):
            issues.append({"unit": "?", "kind": "schema", "detail": "译文条目不是对象"})
            continue
        if u.get("status") == "translated":
            translated += 1
        for iss in verify_unit(u):
            issues.append({"unit": u.get("id"), **iss})
        zh = u.get("translation", "")
        if isinstance(zh, str):
            for m in PENDING_RE.finditer(zh):
                pending.append({"unit": u.get("id"), "marker": m.group(0),
                                "context": zh[:150]})
        if u.get("note") and u.get("status") not in ("skipped",):
            pending.append({"unit": u.get("id"), "marker": "note",
                            "context": str(u["note"])[:200]})

    total = len(src_units)
    blocking = [i for i in issues if i["kind"] in ("coverage", "empty_translation", "schema")]
    report = {
        "units_total": total,
        "units_aligned": len(set(al_ids) & set(src_units)),
        "units_translated": translated,
        "coverage_pct": round(100.0 * len(set(al_ids) & set(src_units)) / max(1, total), 1),
        "issues": issues,
        "blocking_issues": len(blocking),
        "pending_human": pending,
        "clean": not issues,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(args.checklist, "w", encoding="utf-8") as f:
        f.write("# 人工复核清单\n\n")
        f.write(f"- 源单元 {total}，已对齐 {report['units_aligned']}，已译 {translated}，"
                f"覆盖率 {report['coverage_pct']}%\n")
        f.write(f"- 阻塞问题 {len(blocking)}，一般问题 {len(issues) - len(blocking)}，"
                f"待人工确认 {len(pending)}\n\n")
        if pending:
            f.write("## 待确认标注（[待确认]/[未译] 与译者备注）\n\n")
            for p in pending:
                f.write(f"- **{p['unit']}** {p['marker']}：{p['context']}\n")
        if issues:
            f.write("\n## 确定性核验问题\n\n")
            for i in issues:
                f.write(f"- **{i['unit']}** [{i['kind']}] {i['detail']}\n")

    log(f"OK coverage={report['coverage_pct']}% issues={len(issues)} blocking={len(blocking)} pending={len(pending)}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
