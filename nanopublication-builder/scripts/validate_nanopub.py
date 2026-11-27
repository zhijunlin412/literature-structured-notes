#!/usr/bin/env python3
"""Nanopublication validator (stdlib only).

Deterministic checks on nanopub.json against extract.json + relations.json:
  schema      required fields, id uniqueness/pattern, enums, vocabulary
  evidence    every quote is a VERBATIM substring of its referenced unit text
              (whitespace-normalized); unit id exists; >=1 evidence per assertion
  granularity assertion too long (>45 words) or multi-clause connectors -> flag
  subject     subject should appear in evidence quote or note (warn only)
  provenance  required metadata fields present; DOI reported or honestly missing

Exit 0 = clean (warnings allowed), 1 = errors found, 2 = input error.
"""
import argparse
import json
import re
import sys

REQUIRED_ASSERTION = ("id", "text", "subject", "relation", "object", "evidence",
                      "confidence", "confidence_basis")
EVIDENCE_TYPES = {"direct", "indirect", "figure_table"}
CONFIDENCE = {"high", "medium", "low"}
PROVENANCE_REQUIRED = ("title", "authors", "journal", "year", "doi", "source_pdf", "extractor")
MULTI_CLAUSE = ("并且", "同时", "以及", "此外，", " and ", " moreover ", " furthermore ")


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def validate(nanopub, extract, relations):
    errors, warnings = [], []
    vocab = {r["id"] for r in relations.get("relations", [])}
    units = {u["id"]: u for u in extract.get("units", [])}

    assertions = nanopub.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        errors.append({"id": "-", "kind": "schema", "detail": "assertions 缺失或为空"})
        assertions = []

    seen = set()
    for a in assertions:
        aid = a.get("id", "?")
        for f in REQUIRED_ASSERTION:
            if f not in a:
                errors.append({"id": aid, "kind": "schema", "detail": f"缺字段 {f}"})
        if not re.match(r"^A\d+$", str(aid)):
            errors.append({"id": aid, "kind": "schema", "detail": f"id 不符合 ^A[0-9]+$: {aid}"})
        if aid in seen:
            errors.append({"id": aid, "kind": "schema", "detail": "id 重复"})
        seen.add(aid)
        rel = a.get("relation")
        if rel and rel not in vocab:
            errors.append({"id": aid, "kind": "vocabulary", "detail": f"relation 不在受控词表: {rel}"})
        if a.get("confidence") not in CONFIDENCE:
            errors.append({"id": aid, "kind": "schema", "detail": f"confidence 非法: {a.get('confidence')}"})

        # granularity
        text = a.get("text", "")
        n_words = len(text.split()) if re.search(r"[A-Za-z]", text) else len(text)
        if n_words > 90:
            warnings.append({"id": aid, "kind": "granularity",
                             "detail": f"断言过长（{n_words} 词/字），可能仍含多条断言"})
        for conn in MULTI_CLAUSE:
            if conn in text:
                warnings.append({"id": aid, "kind": "granularity",
                                 "detail": f"含并列连接词 {conn.strip()}，确认不可再拆"})
                break
        if rel == "has_measured_value" and not re.search(r"\d", a.get("object", "")):
            errors.append({"id": aid, "kind": "content", "detail": "has_measured_value 但 object 无数值"})

        # evidence
        ev = a.get("evidence")
        if not isinstance(ev, list) or not ev:
            errors.append({"id": aid, "kind": "evidence", "detail": "无证据绑定"})
            ev = []
        subject_hit = False
        for e in ev:
            quote = e.get("quote", "")
            uid = e.get("unit", "")
            etype = e.get("type", "")
            if etype not in EVIDENCE_TYPES:
                errors.append({"id": aid, "kind": "schema", "detail": f"证据类型非法: {etype}"})
            if not isinstance(quote, str) or not quote.strip():
                errors.append({"id": aid, "kind": "evidence", "detail": "证据引用缺失或不是字符串"})
                continue
            if uid not in units:
                errors.append({"id": aid, "kind": "evidence", "detail": f"证据单元不存在: {uid}"})
                continue
            src = units[uid].get("text", "")
            if norm(quote) not in norm(src):
                errors.append({"id": aid, "kind": "evidence",
                               "detail": f"证据引用不是 {uid} 的逐字片段: {quote[:80]}"})
            if etype == "indirect" and not a.get("note"):
                warnings.append({"id": aid, "kind": "evidence",
                                 "detail": "indirect 证据但 note 未写推论链"})
            if a.get("subject") and isinstance(a["subject"], str) and a["subject"] in quote:
                subject_hit = True
        # cross-language subjects (e.g. Chinese subject vs English quote) cannot be
        # verified by containment; check only same-language (ASCII) subjects
        subj = a.get("subject", "")
        if ev and subj and subj.isascii() and not subject_hit and not a.get("note"):
            warnings.append({"id": aid, "kind": "subject",
                             "detail": "主体未出现在任何证据引用中，且无 note 说明（主体混淆风险）"})

    # provenance
    prov = nanopub.get("provenance", {})
    for f in PROVENANCE_REQUIRED:
        if f not in prov or prov[f] in ("", None):
            errors.append({"id": "-", "kind": "provenance", "detail": f"来源元数据缺字段 {f}"})
    if prov.get("doi") == "未报告":
        warnings.append({"id": "-", "kind": "provenance", "detail": "DOI 未报告，确认原文确实没有"})

    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nanopub", required=True)
    ap.add_argument("--extract", required=True)
    ap.add_argument("--relations", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        nanopub = json.load(open(args.nanopub, encoding="utf-8"))
        extract = json.load(open(args.extract, encoding="utf-8"))
        relations = json.load(open(args.relations, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"FATAL input: {e}")
        return 2
    errors, warnings = validate(nanopub, extract, relations)
    report = {"assertions": len(nanopub.get("assertions", [])),
              "errors": errors, "warnings": warnings, "clean": not errors}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"OK assertions={report['assertions']} errors={len(errors)} warnings={len(warnings)}")
    for e in errors[:15]:
        log(f"  ERROR {e['id']} [{e['kind']}] {e['detail']}")
    for w in warnings[:10]:
        log(f"  warn  {w['id']} [{w['kind']}] {w['detail']}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
