# -*- coding: utf-8 -*-
"""parse_materials.py — 读取事实底稿与文献库，建立独立清单（外部分母）。

清点：底稿锚点（贡献可引用的全部证据位）、文献库条目与必备元数据、
各文献可用证据文本长度——覆盖率的分母来自材料本身，不来自 Agent 自报。

用法:
  python parse_materials.py --fact-draft fact_draft.json --library library.json --out inventory.json
"""
import argparse, json, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fact-draft", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    fd = json.load(open(a.fact_draft, encoding="utf-8-sig"))
    lib = json.load(open(a.library, encoding="utf-8-sig"))
    anchors = fd.get("anchors", [])
    works = lib.get("works", [])

    problems = []
    anchor_ids = [x["id"] for x in anchors]
    if len(anchor_ids) != len(set(anchor_ids)):
        problems.append("事实底稿锚点 id 有重复")
    keys = [w["key"] for w in works]
    if len(keys) != len(set(keys)):
        problems.append("文献库 key 有重复")
    for w in works:
        for f in ("title", "authors", "year"):
            if not w.get(f):
                problems.append(f"文献 {w.get('key','?')} 缺元数据字段 {f}")
        if not (w.get("text") or "").strip():
            problems.append(f"文献 {w.get('key','?')} 无证据文本（text 为空，无法支撑逐字转述核验）")

    inv = {
        "anchor_ids": anchor_ids,
        "work_keys": keys,
        "works": [{"key": w["key"], "title": w.get("title"), "year": w.get("year"),
                   "text_chars": len(w.get("text", ""))} for w in works],
        "problems": problems,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)
    print(f"底稿锚点 {len(anchor_ids)} | 文献 {len(works)} 篇 | 材料问题 {len(problems)}")
    for p in problems:
        print("  !", p)
    print("written:", a.out)

if __name__ == "__main__":
    main()
