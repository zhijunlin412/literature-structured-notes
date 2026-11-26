#!/usr/bin/env python3
"""Deterministic validator/assembler for pdf-document-parser.

Reads parse_spec.json (Agent-produced structured parse) and writes result.json.
Only validates structure and anchors; never invents document content.
"""
import argparse
import json
import os
import sys


def log(m):
    print(m, flush=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def block_ok(b):
    if not isinstance(b, dict):
        return False
    return isinstance(b.get("page"), int) and isinstance(b.get("text"), str) and b["text"].strip()


def validate(spec):
    problems = []
    if not spec.get("case_id"):
        problems.append("missing case_id")
    meta = spec.get("document_meta", {})
    if not isinstance(meta, dict) or not (meta.get("title")):
        problems.append("document_meta.title missing")
    if not isinstance(spec.get("sections"), list):
        problems.append("sections must be a list")
    else:
        for i, s in enumerate(spec["sections"]):
            if not isinstance(s.get("page"), int) or not s.get("heading"):
                problems.append(f"sections[{i}] needs page and heading")
    if not isinstance(spec.get("paragraphs"), list):
        problems.append("paragraphs must be a list")
    else:
        for i, p in enumerate(spec["paragraphs"]):
            if not block_ok(p):
                problems.append(f"paragraphs[{i}] needs page and text")
    for key in ("tables", "figures", "formulas", "references"):
        if key in spec and not isinstance(spec.get(key), list):
            problems.append(f"{key} must be a list")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", default=None)
    args = ap.parse_args()
    try:
        spec = load_json(args.spec)
    except Exception as e:
        log(f"FATAL: cannot read spec: {e}")
        return 2
    if args.case_id:
        spec["case_id"] = args.case_id
    if not spec.get("case_id"):
        log("FATAL: missing case_id")
        return 2
    problems = validate(spec)
    if problems:
        log("VALIDATION FAILED:")
        for p in problems:
            log(f"  - {p}")
        return 1

    result = {
        "case_id": spec["case_id"],
        "status": spec.get("status", "complete"),
        "document_meta": spec.get("document_meta", {}),
        "sections": spec.get("sections", []),
        "paragraphs": spec.get("paragraphs", []),
        "tables": spec.get("tables", []),
        "figures": spec.get("figures", []),
        "formulas": spec.get("formulas", []),
        "references": spec.get("references", []),
        "headers_footers": spec.get("headers_footers", []),
        "sources": spec.get("sources", []),
        "uncertainty": spec.get("uncertainty", ""),
        "change_record": spec.get("change_record", []),
    }
    # merge output_contract fields at top level (graded "answer" fields)
    oc = spec.get("output_contract", {})
    for k, v in oc.items():
        if k.startswith("_"):
            continue
        result[k] = v
    write_json(os.path.join(args.out, "result.json"), result)
    log(f"OK case={spec['case_id']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
