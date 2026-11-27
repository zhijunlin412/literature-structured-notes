#!/usr/bin/env python3
"""Glossary enforcement checker (stdlib only).

Verifies that the locked translation of every glossary term is actually used
wherever the term appears in the source units -- this is what makes the
glossary *executed* rather than written in a prompt.

Inputs:
  --glossary   glossary.json   {"terms": [{"en":..., "abbr":..., "zh":..., "note":...}]}
  --alignment  alignment.json  {"units": [{"id","source","translation","status",...}]}
  --out        report path (glossary_report.json)

Exit code 0 = clean, 1 = violations found, 2 = input error.
"""
import argparse
import json
import re
import sys


def log(m):
    print(m, flush=True)


def word_re(term):
    return re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", re.I)


def check(glossary, alignment):
    terms = glossary.get("terms", [])
    units = alignment.get("units", [])
    violations = []
    hits = {t["en"]: 0 for t in terms}
    for u in units:
        src = u.get("source", "")
        zh = u.get("translation", "")
        status = u.get("status", "")
        if status in ("skipped", "untranslated"):
            continue
        # longest match wins: an occurrence covered by a longer glossary term
        # (e.g. "carbonate hydroxide nanotube array" covering "nanotube array")
        # is governed by that longer entry only
        spans = []
        for t in terms:
            for m in word_re(t["en"]).finditer(src):
                spans.append((m.start(), m.end(), t))
        for s, e, t in spans:
            if any(s2 <= s and e <= e2 and (e2 - s2) > (e - s) for s2, e2, _ in spans):
                continue
            hits[t["en"]] += 1
            if t.get("zh") and t["zh"] not in zh:
                violations.append({
                    "unit": u.get("id"),
                    "term_en": t["en"],
                    "expected_zh": t["zh"],
                    "translation_excerpt": zh[:120],
                })
    # unused glossary entries: extracted but never seen in source -> harmless, report
    unused = [en for en, n in hits.items() if n == 0]
    return {
        "terms_total": len(terms),
        "terms_used": sum(1 for n in hits.values() if n > 0),
        "occurrences_checked": sum(hits.values()),
        "violations": violations,
        "unused_terms": unused,
        "clean": not violations,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--alignment", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        with open(args.glossary, encoding="utf-8") as f:
            glossary = json.load(f)
        with open(args.alignment, encoding="utf-8") as f:
            alignment = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log(f"FATAL input: {e}")
        return 2
    report = check(glossary, alignment)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    if report["clean"]:
        log(f"OK terms={report['terms_total']} checked={report['occurrences_checked']} clean")
        return 0
    log(f"VIOLATIONS {len(report['violations'])} (see {args.out})")
    for v in report["violations"][:20]:
        log(f"  {v['unit']}: '{v['term_en']}' 应译为 '{v['expected_zh']}'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
