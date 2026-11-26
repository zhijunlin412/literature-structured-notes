#!/usr/bin/env python3
"""Deterministic validator/assembler for literature-structured-notes.

Reads an Agent-produced notes_spec.json and writes, under --out:
  result.json         case_id + status + paper_card + sections + knowledge_points
                      + principle_analysis + glossary + one_liner
                      + evidence_map + sources + uncertainty + change_record
                      (+ any output_contract fields passed through)
  notes.md            human-readable notes (paper card + sections + knowledge
                      points + principle deep-dive + glossary)
  notes_plain.md      plain-language version for non-experts (if notes_plain set)
  evidence_map.json   claim -> anchor map for independent review

Only validates structure and anchors; it never invents paper content.
"""
import argparse
import json
import os
import sys

# Windows 控制台默认可能不是 UTF-8，避免中文日志乱码；失败无碍。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

PAPER_CARD_FIELDS = [
    "research_question", "data", "method", "method_conditions",
    "main_findings", "conclusions", "limitations", "preconditions",
]
ANCHOR_FIELDS = ["section", "paragraph", "page", "figure", "table", "formula"]
EVIDENCE_STRENGTHS = ["direct", "consensus", "preliminary", "not_reported"]
PRINCIPLE_FIELDS = ["id", "claim", "why", "basis", "quantitative_check",
                    "evidence_strength", "evidence", "glossary_terms", "transferable"]


def log(m):
    print(m, flush=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def anchor_ok(a):
    if not isinstance(a, dict):
        return False
    return any(a.get(k) not in (None, "") for k in ANCHOR_FIELDS)


def validate(spec):
    problems = []
    warnings = []
    if not spec.get("case_id"):
        problems.append("missing case_id")
    card = spec.get("paper_card", {})
    for f in PAPER_CARD_FIELDS:
        if f not in card:
            problems.append(f"paper_card.{f} missing")
        elif not anchor_ok(card[f].get("evidence")):
            problems.append(f"paper_card.{f}.evidence has no anchor")
    if not isinstance(spec.get("sections"), list) or not spec["sections"]:
        problems.append("sections must be a non-empty list")
    else:
        for i, s in enumerate(spec["sections"]):
            if not anchor_ok(s.get("evidence")):
                problems.append(f"sections[{i}].evidence has no anchor")
    if not isinstance(spec.get("knowledge_points"), list):
        problems.append("knowledge_points must be a list")

    # 一句话概括：推荐但可选。
    if spec.get("one_liner") is not None and not isinstance(spec.get("one_liner"), str):
        problems.append("one_liner must be a string")

    # 原理深挖：可选；若给出，逐条校验结构与证据强度。
    pa = spec.get("principle_analysis")
    if pa is not None:
        if not isinstance(pa, list):
            problems.append("principle_analysis must be a list")
        else:
            for i, p in enumerate(pa):
                if not isinstance(p, dict):
                    problems.append(f"principle_analysis[{i}] must be an object")
                    continue
                for k in ("claim", "why"):
                    if not p.get(k):
                        problems.append(f"principle_analysis[{i}].{k} missing")
                es = p.get("evidence_strength")
                if es is not None and es not in EVIDENCE_STRENGTHS:
                    problems.append(f"principle_analysis[{i}].evidence_strength invalid: {es}")
    else:
        warnings.append("principle_analysis absent: 建议为核心结论补充原理层解释")

    # 术语词典：可选。
    gl = spec.get("glossary")
    if gl is not None:
        if not isinstance(gl, list):
            problems.append("glossary must be a list")
        else:
            for i, g in enumerate(gl):
                if not isinstance(g, dict) or not g.get("term") or not g.get("definition"):
                    problems.append(f"glossary[{i}] needs term and definition")

    return problems, warnings


def _val(c):
    return c.get("value", "") if isinstance(c, dict) else ""


def _loc(c):
    ev = c.get("evidence", {}) if isinstance(c, dict) else {}
    return ev.get("locator", "") if isinstance(ev, dict) else ""


def build_notes_md(spec):
    lines = [f"# {spec.get('title', 'Untitled')}", ""]
    if spec.get("one_liner"):
        lines += ["## 一句话概括", spec["one_liner"], ""]
    card = spec.get("paper_card", {})
    lines.append("## 论文卡片")
    for f in PAPER_CARD_FIELDS:
        c = card.get(f, {})
        lines.append(f"- **{f}**: {_val(c)}  `{_loc(c)}`")
    lines.append("")
    lines.append("## 章节总结")
    for s in spec.get("sections", []):
        lines.append(f"### {s.get('heading') or s.get('section_id', '')}")
        for k in ("purpose", "method", "results", "conclusion", "transition"):
            if s.get(k):
                lines.append(f"- {k}: {s[k]}")
        ev = s.get("evidence", {})
        if isinstance(ev, dict) and ev.get("locator"):
            lines.append(f"- 定位: {ev['locator']}")
    lines.append("")
    lines.append("## 知识点")
    for kp in spec.get("knowledge_points", []):
        extra = ""
        if kp.get("evidence_strength"):
            extra += f" [强度:{kp['evidence_strength']}]"
        lines.append(f"- **{kp.get('term', '')}** [{kp.get('category', '')}]{extra}: {kp.get('definition', '')}")
        if kp.get("principle"):
            lines.append(f"  - 为什么: {kp['principle']}")
    lines.append("")
    pa = spec.get("principle_analysis") or []
    if pa:
        lines.append("## 原理深挖")
        for p in pa:
            lines.append(f"- **{p.get('claim', '')}**")
            lines.append(f"  - 为什么: {p.get('why', '')}")
            if p.get("basis"):
                lines.append(f"  - 底层原理: {p['basis']}")
            if p.get("quantitative_check"):
                lines.append(f"  - 定量验证: {p['quantitative_check']}")
            if p.get("evidence_strength"):
                lines.append(f"  - 证据强度: {p['evidence_strength']}")
            if p.get("transferable"):
                lines.append(f"  - 可迁移: {p['transferable']}")
        lines.append("")
    gl = spec.get("glossary") or []
    if gl:
        lines.append("## 术语词典")
        for g in gl:
            lines.append(f"- **{g.get('term', '')}**: {g.get('definition', '')}")
        lines.append("")
    if spec.get("uncertainty"):
        lines.append(f"## 不确定性\n{spec['uncertainty']}")
    return "\n".join(lines)


def build_evidence_map(spec):
    m = {"case_id": spec.get("case_id"), "entries": []}
    card = spec.get("paper_card", {})
    for f in PAPER_CARD_FIELDS:
        c = card.get(f, {})
        if isinstance(c, dict) and c.get("value"):
            m["entries"].append({"field": f"paper_card.{f}", "claim": c["value"],
                                 "anchor": c.get("evidence", {})})
    for i, s in enumerate(spec.get("sections", [])):
        m["entries"].append({"field": f"sections[{i}]", "claim": s.get("conclusion") or s.get("results", ""),
                             "anchor": s.get("evidence", {})})
    for p in spec.get("principle_analysis") or []:
        m["entries"].append({"field": "principle_analysis", "claim": p.get("claim", ""),
                             "anchor": p.get("evidence", {}),
                             "evidence_strength": p.get("evidence_strength")})
    return m


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
        log("FATAL: missing case_id (set in spec or --case-id)")
        return 2

    problems, warnings = validate(spec)
    for w in warnings:
        log(f"WARNING: {w}")
    if problems:
        log("VALIDATION FAILED:")
        for p in problems:
            log(f"  - {p}")
        return 1

    os.makedirs(args.out, exist_ok=True)
    result = {
        "case_id": spec["case_id"],
        "status": spec.get("status", "complete"),
        "one_liner": spec.get("one_liner", ""),
        "paper_card": spec.get("paper_card", {}),
        "sections": spec.get("sections", []),
        "knowledge_points": spec.get("knowledge_points", []),
        "principle_analysis": spec.get("principle_analysis", []),
        "glossary": spec.get("glossary", []),
        "evidence_map": "evidence_map.json",
        "sources": spec.get("sources", []),
        "uncertainty": spec.get("uncertainty", ""),
        "change_record": spec.get("change_record", []),
        "output": spec.get("output_contract", {}),
    }
    write_json(os.path.join(args.out, "result.json"), result)
    write_json(os.path.join(args.out, "evidence_map.json"), build_evidence_map(spec))
    with open(os.path.join(args.out, "notes.md"), "w", encoding="utf-8") as f:
        f.write(build_notes_md(spec))
    if isinstance(spec.get("notes_plain"), str) and spec["notes_plain"].strip():
        with open(os.path.join(args.out, "notes_plain.md"), "w", encoding="utf-8") as f:
            f.write(spec["notes_plain"])
    log(f"OK case={spec['case_id']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
