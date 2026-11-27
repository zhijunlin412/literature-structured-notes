#!/usr/bin/env python3
"""Assemble nanopublication deliverables (stdlib only).

Reads case.json (optional), extract.json, nanopub.json, validate report;
writes to --out:
  result.json       structured main result (case_id + status + anchors)
  nanopub.jsonld    JSON-LD export (np/prov/dcterms/schema context)
  assertions.csv    flat table for downstream programs
  report.md         human-readable assertion-by-assertion report

Exit 0 = assembled, 1 = validation problems present (still writes), 2 = input error.
"""
import argparse
import csv
import json
import os
import sys


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def load_json(path, default=None):
    if not path or not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--extract", required=True)
    ap.add_argument("--nanopub", required=True)
    ap.add_argument("--validation", default=None)
    ap.add_argument("--change-record", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    extract = load_json(args.extract)
    nanopub = load_json(args.nanopub)
    if extract is None or nanopub is None:
        log("FATAL missing extract/nanopub")
        return 2
    case = load_json(args.case, {}) or {}
    validation = load_json(args.validation, {}) or {}
    change_record = load_json(args.change_record, []) or []
    units = {u["id"]: u for u in extract.get("units", [])}

    os.makedirs(args.out, exist_ok=True)
    assertions = nanopub.get("assertions", [])
    prov = nanopub.get("provenance", {})
    case_id = case.get("case_id", case.get("id", "unknown"))

    n_errors = len(validation.get("errors", []))
    n_low = sum(1 for a in assertions if a.get("confidence") == "low")
    status = "partial" if (n_errors or n_low) else "success"
    uncertainty = [{"id": a["id"], "reason": a.get("note", "低置信度")}
                   for a in assertions if a.get("confidence") == "low"]

    # ---- result.json ----
    result = {
        "case_id": case_id,
        "status": status,
        "skill": "nanopublication-builder",
        "stats": {
            "assertions": len(assertions),
            "evidence_bindings": sum(len(a.get("evidence", [])) for a in assertions),
            "confidence": {c: sum(1 for a in assertions if a.get("confidence") == c)
                           for c in ("high", "medium", "low")},
            "evidence_types": {t: sum(1 for a in assertions for e in a.get("evidence", [])
                                      if e.get("type") == t)
                               for t in ("direct", "indirect", "figure_table")},
        },
        "assertions": [
            {**a,
             "evidence": [{**e, "page": units.get(e.get("unit", ""), {}).get("page"),
                           "anchor": units.get(e.get("unit", ""), {}).get("anchor")}
                          for e in a.get("evidence", [])]}
            for a in assertions
        ],
        "provenance": prov,
        "uncertainty": uncertainty,
        "change_record": change_record,
        "validation": validation,
    }
    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- nanopub.jsonld ----
    ctx = {
        "np": "http://www.nanopub.org/nschema#",
        "prov": "http://www.w3.org/ns/prov#",
        "dcterms": "http://purl.org/dc/terms/",
        "schema": "https://schema.org/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    graph = []
    for a in assertions:
        aid = a["id"]
        base = f"nano:{case_id}/{aid}"
        graph.append({
            "@id": base,
            "@type": "np:Nanopublication",
            "np:hasAssertion": {
                "@id": base + "/assertion",
                "@type": "schema:Claim",
                "schema:text": a["text"],
                "schema:about": a["subject"],
                "schema:propertyID": a["relation"],
                "schema:value": a["object"],
                "schema:conditions": a.get("conditions", ""),
            },
            "np:hasProvenance": {
                "@id": base + "/provenance",
                "prov:wasDerivedFrom": [
                    {"@id": f"nano:{case_id}/{e['unit']}",
                     "dcterms:type": e["type"],
                     "schema:quotation": e["quote"],
                     "schema:pageNumber": units.get(e["unit"], {}).get("page")}
                    for e in a.get("evidence", [])
                ],
            },
            "np:hasPublicationInfo": {
                "@id": base + "/pubinfo",
                "dcterms:isPartOf": {
                    "@type": "schema:ScholarlyArticle",
                    "schema:name": prov.get("title"),
                    "schema:author": prov.get("authors"),
                    "schema:isPartOf": prov.get("journal"),
                    "dcterms:issued": str(prov.get("year")),
                    "schema:sameAs": ("https://doi.org/" + prov["doi"]) if prov.get("doi") not in (None, "", "未报告") else None,
                },
                "schema:confidence": a.get("confidence"),
                "schema:comment": a.get("confidence_basis"),
            },
        })
    with open(os.path.join(args.out, "nanopub.jsonld"), "w", encoding="utf-8") as f:
        json.dump({"@context": ctx, "@graph": graph}, f, ensure_ascii=False, indent=2)

    # ---- assertions.csv ----
    with open(os.path.join(args.out, "assertions.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "text", "subject", "relation", "object", "conditions",
                    "evidence_quote", "evidence_unit", "evidence_page", "evidence_type", "confidence"])
        for a in assertions:
            ev = a.get("evidence", [{}])[0]
            w.writerow([a["id"], a["text"], a["subject"], a["relation"], a["object"],
                        a.get("conditions", ""), ev.get("quote", ""), ev.get("unit", ""),
                        units.get(ev.get("unit", ""), {}).get("page", ""), ev.get("type", ""),
                        a.get("confidence", "")])

    # ---- report.md ----
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(f"# 断言抽取报告\n\n> 论文：{prov.get('title')}（{prov.get('journal')}, {prov.get('year')}，DOI: {prov.get('doi')}）\n")
        f.write(f"> 断言 {len(assertions)} 条；状态 {status}；校验错误 {n_errors}\n\n")
        for a in assertions:
            f.write(f"## {a['id']} [{a.get('confidence')}] {a['text']}\n\n")
            f.write(f"- 三元组：{a['subject']} — **{a['relation']}** — {a['object']}\n")
            if a.get("conditions"):
                f.write(f"- 限定条件：{a['conditions']}\n")
            f.write(f"- 置信度依据：{a.get('confidence_basis')}\n")
            if a.get("context"):
                f.write(f"- 解读（非证据）：{a['context']}\n")
            for e in a.get("evidence", []):
                page = units.get(e.get("unit", ""), {}).get("page", "?")
                f.write(f"- 证据（{e['type']}，{e['unit']}，第{page}页）：\"{e['quote']}\"\n")
            if a.get("note"):
                f.write(f"- 备注：{a['note']}\n")
            f.write("\n")

    log(f"OK status={status} assertions={len(assertions)} errors={n_errors} -> {args.out}")
    return 1 if n_errors else 0


if __name__ == "__main__":
    sys.exit(main())
