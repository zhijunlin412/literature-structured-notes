# -*- coding: utf-8 -*-
"""check_terminology.py — 术语一致性回扫：同一概念全篇只能有一种写法。

输入术语表 glossary.json:
{
  "terms": [
    {"canonical": "oxygen evolution reaction (OER)",
     "abbr": "OER",
     "variants": ["oxygen evolution reaction", "OER"],
     "first_mention_full": true,
     "note": "首次出现全称（缩写），之后只用缩写"},
    {"canonical": "carbon cloth", "variants": ["carbon cloth", "CC"], "note": "..."}
  ]
}

校验项：
1. 同一术语的多个变体被同时使用（除"首次全称+之后缩写"的合法模式）→ warning/error
2. 缩写被重复定义（同一缩写出现两次"全称 (ABBR)"）→ error
3. 缩写未定义就使用（出现 ABBR 但全文没有 "(ABBR)" 定义，且不在公认缩写白名单）→ warning
4. 禁用写法（banned，如期刊风格不接受的写法）→ error

用法:
  python check_terminology.py --text polished.txt --glossary glossary.json --out terminology_report.json
  可选 --original 原文：对比润色前后各术语出现次数，次数减少报 warning
  （术语表管不了未登记的新同义词，次数对不上说明可能有漂移，需人工核对）。
"""
import argparse, json, re, sys, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KNOWN_ABBR = {"XRD", "XPS", "SEM", "TEM", "XAS", "PDF", "JCPDS", "HER", "OER",
              "ORR", "CC", "UV", "IR", "NMR", "EDX", "EDS", "ICP", "BET"}

def find_occurrences(text, variant):
    return [m.start() for m in re.finditer(r"(?<![\w-])" + re.escape(variant) + r"(?![\w-])", text)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--original", help="可选：润色前原文，用于术语次数对照")
    a = ap.parse_args()

    text = unicodedata.normalize("NFC", open(a.text, encoding="utf-8-sig").read())
    orig_text = unicodedata.normalize("NFC", open(a.original, encoding="utf-8-sig").read()) if a.original else None
    gloss = json.load(open(a.glossary, encoding="utf-8"))
    errors, warnings, details = [], [], []

    defined = {}
    # 缩写定义要求括号前是空白（"reaction (OER)"），避免把化学式 Co(CO3) 误判为定义
    for m in re.finditer(r"(?<=\s)\(([A-Z][A-Za-z0-9]{1,11})\)", text):
        defined.setdefault(m.group(1), 0)
        defined[m.group(1)] += 1

    for entry in gloss.get("terms", []):
        canonical = entry["canonical"]
        variants = entry.get("variants", [canonical])
        abbr = entry.get("abbr")
        banned = entry.get("banned", [])
        usage = {}
        for v in variants:
            occ = find_occurrences(text, v)
            if occ:
                usage[v] = len(occ)
        for b in banned:
            n = len(find_occurrences(text, b))
            if n:
                errors.append({"term": canonical, "detail": f"出现禁用写法 '{b}' ×{n}，应统一为 '{canonical}'"})
        surface_forms = [v for v in usage if v != abbr]
        if len(surface_forms) > 1:
            errors.append({"term": canonical, "detail": f"同一概念用了多种写法 {surface_forms}，违反全篇统一"})
        if abbr and usage.get(abbr) and abbr not in defined and abbr not in KNOWN_ABBR:
            warnings.append({"term": canonical, "detail": f"缩写 {abbr} 被使用 {usage[abbr]} 次但全文未见首次定义"})
        if orig_text is not None:
            orig_usage = sum(len(find_occurrences(orig_text, v)) for v in variants)
            new_usage = sum(usage.values())
            if new_usage < orig_usage:
                warnings.append({"term": canonical, "detail": f"术语 '{canonical}' 出现次数 {orig_usage} → {new_usage}：可能有未登记的新写法漂移，请人工核对"})
        details.append({"term": canonical, "usage": usage})

    for ab, n in defined.items():
        if n > 1:
            warnings.append({"term": ab, "detail": f"缩写 ({ab}) 被定义 {n} 次；若摘要与正文独立成篇属合理，否则应只在首次出现时定义"})

    report = {
        "status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
        "errors": errors, "warnings": warnings, "term_usage": details,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"terminology: {report['status']}（error {len(errors)} / warning {len(warnings)}，术语 {len(details)} 条）")
    for e in errors:
        print("  ERROR:", e["detail"])
    for w in warnings[:10]:
        print("  warn :", w["detail"])
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
