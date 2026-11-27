#!/usr/bin/env python3
"""Assemble final deliverables (stdlib only).

Reads case.json (optional), extract.json, glossary.json, alignment.json,
verify_report.json and glossary_report.json; validates the alignment entries;
writes to --out:
  result.json       structured main result (case_id + status + evidence)
  bilingual.md      paragraph-level EN/中 aligned document with anchors

Exit 0 = assembled, 1 = validation problems (still writes what it can), 2 = input error.
"""
import argparse
import json
import os
import sys

VALID_STATUS = {"translated", "partial", "untranslated", "skipped"}
REQUIRED_UNIT_FIELDS = ("id", "source", "translation", "status")


def log(m):
    print(m, flush=True)


def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="/input/case.json (optional)")
    ap.add_argument("--extract", required=True)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--alignment", required=True)
    ap.add_argument("--verify", default=None)
    ap.add_argument("--glossary-report", default=None)
    ap.add_argument("--change-record", default=None, help="JSON list of change entries (optional)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    extract = load_json(args.extract)
    glossary = load_json(args.glossary)
    alignment = load_json(args.alignment)
    if extract is None or glossary is None or alignment is None:
        log("FATAL missing extract/glossary/alignment")
        return 2
    case = load_json(args.case, {}) or {}
    verify = load_json(args.verify, {}) or {}
    greport = load_json(args.glossary_report, {}) or {}
    change_record = load_json(args.change_record, []) or []

    problems = []
    src_by_id = {u["id"]: u for u in extract.get("units", [])}
    for u in alignment.get("units", []):
        for k in REQUIRED_UNIT_FIELDS:
            if k not in u:
                problems.append(f"{u.get('id','?')}: 缺字段 {k}")
        if u.get("status") not in VALID_STATUS:
            problems.append(f"{u.get('id','?')}: 非法 status {u.get('status')}")
        if u.get("status") == "translated" and not str(u.get("translation", "")).strip():
            problems.append(f"{u.get('id','?')}: status=translated 但译文为空")

    units = alignment.get("units", [])
    n_tr = sum(1 for u in units if u.get("status") == "translated")
    n_part = sum(1 for u in units if u.get("status") == "partial")
    n_un = sum(1 for u in units if u.get("status") == "untranslated")
    n_sk = sum(1 for u in units if u.get("status") == "skipped")
    uncertainty = []
    for u in units:
        if u.get("status") in ("partial", "untranslated"):
            uncertainty.append({"unit": u["id"], "reason": u.get("note", "未说明")})
    blocking = verify.get("blocking_issues", 0)
    if problems or blocking or n_un > 0 or n_part > 0:
        status = "partial"
    else:
        status = "success"

    os.makedirs(args.out, exist_ok=True)

    # bilingual.md
    with open(os.path.join(args.out, "bilingual.md"), "w", encoding="utf-8") as f:
        f.write("# 双语对照译文\n\n")
        f.write("> 逐单元对照：段号（页码）→ 原文 → 译文 → 译注。[待确认] 表示需人工复核。\n\n")
        for u in units:
            src = src_by_id.get(u["id"], {})
            page = src.get("page", "?")
            flags = []
            if src.get("margin"):
                flags.append("页边")
            if src.get("order_suspect"):
                flags.append("顺序存疑")
            tag = f"（{'、'.join(flags)}）" if flags else ""
            f.write(f"## {u['id']}（第{page}页）{tag} [{u.get('status')}]\n\n")
            f.write(f"**原文**\n\n{u.get('source','')}\n\n")
            f.write(f"**译文**\n\n{u.get('translation','')}\n\n")
            if u.get("note"):
                f.write(f"> 译注：{u['note']}\n\n")

    result = {
        "case_id": case.get("case_id", case.get("id", "unknown")),
        "status": status,
        "skill": "bilingual-literature-translator",
        "document_meta": {
            "source_pdf": extract.get("source_pdf"),
            "pages": extract.get("stats", {}).get("pages"),
            "words": extract.get("stats", {}).get("words"),
            "units": extract.get("stats", {}).get("units"),
            "ocr_used": extract.get("ocr_used"),
        },
        "glossary": {
            "terms_total": len(glossary.get("terms", [])),
            "terms": glossary.get("terms", []),
            "enforcement": {
                "occurrences_checked": greport.get("occurrences_checked"),
                "violations": len(greport.get("violations", [])),
                "clean": greport.get("clean"),
            },
        },
        "translation_coverage": {
            "units_total": len(extract.get("units", [])),
            "translated": n_tr,
            "partial": n_part,
            "untranslated": n_un,
            "skipped_margin_or_noise": n_sk,
            "coverage_pct": verify.get("coverage_pct"),
        },
        "verification": {
            "issues": verify.get("issues", []),
            "pending_human": verify.get("pending_human", []),
        },
        "sources": [
            {"unit": u["id"], "page": src_by_id.get(u["id"], {}).get("page"),
             "anchor": src_by_id.get(u["id"], {}).get("anchor"),
             "status": u.get("status")}
            for u in units
        ],
        "uncertainty": uncertainty,
        "change_record": change_record,
        "validation_problems": problems,
    }
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log(f"OK status={status} translated={n_tr} partial={n_part} untranslated={n_un} "
        f"problems={len(problems)} -> {args.out}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
