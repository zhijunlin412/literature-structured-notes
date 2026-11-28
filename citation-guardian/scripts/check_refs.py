# -*- coding: utf-8 -*-
"""check_refs.py — 引用一致性与格式校验（挂得对/编得顺/对得上的机器防线）。

校验项：
1. 双向闭合：正文每个 [n] 都有条目（悬空 error）；每条目至少被引一次（未引 warning）
2. 编号连续：1..N 无缺号（error）
3. GB/T 7714 字段完备：按文献类型查 required 字段（缺失 error）
4. 引用位置：段落多句而标记只挂在段末 → warning（可能"挂错位置"，列 human_review）
5. 来源核验记录：条目带 doi 但 verification 为空 → warning（未核验不许标 verified）

用法:
  python check_refs.py --manuscript manuscript_updated.md \
      --entries entries_synced.json --styles ../assets/citation_styles.json --out check_report.json
"""
import argparse, json, sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from parse_refs import parse_manuscript, norm  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--entries", required=True)
    ap.add_argument("--styles", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    text = norm(open(a.manuscript, encoding="utf-8-sig").read())
    data = json.load(open(a.entries, encoding="utf-8-sig"))
    entries = data["entries"] if isinstance(data, dict) else data
    styles = json.load(open(a.styles, encoding="utf-8"))
    gbt_types = styles["styles"]["gbt7714"]["types"]

    errors, warnings = [], []
    markers, n_paras = parse_manuscript(text)
    cited = sorted({n for mk in markers for n in mk["numbers"]})
    have = sorted(int(e["key"]) for e in entries if str(e["key"]).isdigit())

    for n in cited:
        if n not in have:
            errors.append(f"正文引用 [{n}] 在文献表中无对应条目（悬空引用）")
    for k in have:
        if k not in cited:
            warnings.append(f"条目 [{k}] 全篇未被引用")

    if have and have != list(range(1, len(have) + 1)):
        errors.append(f"编号不连续：现有 {have}，应为 1..{len(have)}")

    for e in entries:
        t = e.get("type", "journal")
        req = gbt_types.get(t, gbt_types["journal"])["required"]
        missing = [f for f in req if not e.get(f)]
        if missing:
            errors.append(f"条目 [{e['key']}]（{t}）缺必需字段: {missing}")
        if e.get("doi") and not e.get("verification"):
            warnings.append(f"条目 [{e['key']}] 有 DOI 但无来源核验记录")
        if e.get("verification", {}).get("status") == "verified" and not e["verification"].get("evidence"):
            errors.append(f"条目 [{e['key']}] 标 verified 但无核验证据（渠道+时间+比对字段）")

    for mk in markers:
        if mk["is_paragraph_end"] and mk["n_sentences_in_paragraph"] >= 3:
            warnings.append(
                f"第 {mk['paragraph']} 段共 {mk['n_sentences_in_paragraph']} 句，引用 {mk['raw']} 挂在段末："
                f"请确认它支撑的是哪一句（必要时应挂到论断句后）")

    rep = {"status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
           "errors": errors, "warnings": warnings,
           "summary": {"markers": len(markers), "cited": cited, "entries": len(entries)}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"check: {rep['status']}（error {len(errors)} / warning {len(warnings)}）")
    for e in errors:
        print("  ERROR:", e)
    for w in warnings[:10]:
        print("  warn :", w)
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
