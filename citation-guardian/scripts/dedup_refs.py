# -*- coding: utf-8 -*-
"""dedup_refs.py — 按 assets/dedup_rules.md 的判据找出候选重复条目对。

脚本只做"候选 + 证据"，merge/not_merge 的决定由 Agent 按判据写下（可解释），
脚本不替模型做最终决定，也不让模型凭空决定——候选对与判据由脚本算出。

用法:
  python dedup_refs.py --entries entries.json --out dedup_candidates.json
  entries.json: 由 Agent 结构化的条目数组
    [{"key":"1","type":"journal","authors":["Suen, N.-T.",...],"title":"...",
      "journal":"...","year":"2017","volume":"46","issue":"2","pages":"337-365","doi":"..."}]
"""
import argparse, difflib, json, re, sys, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def norm_title(t):
    t = unicodedata.normalize("NFC", t or "").lower()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def norm_doi(d):
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", (d or "").strip().lower()).rstrip(".")

def first_author_lastname(a):
    if not a:
        return ""
    a0 = a[0]
    if "," in a0:
        return a0.split(",")[0].strip().lower()
    parts = a0.strip().split()
    return (parts[-1] if parts else "").lower()

def score_pair(x, y):
    """返回 (score, criteria, evidence)。判据编号对应 assets/dedup_rules.md。"""
    ev = {"titles": [x.get("title", ""), y.get("title", "")],
          "years": [x.get("year"), y.get("year")],
          "first_authors": [first_author_lastname(x.get("authors")), first_author_lastname(y.get("authors"))],
          "dois": [x.get("doi"), y.get("doi")]}
    dx, dy = norm_doi(x.get("doi")), norm_doi(y.get("doi"))
    if dx and dy and dx == dy:
        return 1.0, [1], ev
    tx, ty = norm_title(x.get("title")), norm_title(y.get("title"))
    if not tx or not ty:
        return 0.0, [], ev
    ratio = difflib.SequenceMatcher(None, tx, ty).ratio()
    same_year = x.get("year") and x.get("year") == y.get("year")
    same_first = ev["first_authors"][0] and ev["first_authors"][0] == ev["first_authors"][1]
    if tx == ty and same_year:
        return 0.95, [2], ev
    if ratio >= 0.9 and same_first and same_year:
        return 0.8, [3], ev
    # 预印本 ↔ 正式版：题名一致、作者一致、年相邻
    if tx == ty and same_first and x.get("year") and y.get("year") \
            and abs(int(x["year"]) - int(y["year"])) <= 2:
        return 0.85, ["预印本↔正式版"], ev
    return round(ratio, 3), [], ev

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=0.75)
    a = ap.parse_args()

    entries = json.load(open(a.entries, encoding="utf-8-sig"))
    cands = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            x, y = entries[i], entries[j]
            s, crit, ev = score_pair(x, y)
            if s >= a.threshold:
                cands.append({
                    "pair": [x["key"], y["key"]],
                    "score": s, "matched_criteria": crit, "evidence": ev,
                    "decision": "",        # Agent 填 merge / not_merge / unresolved
                    "survivor": "",        # merge 时保留的 key
                    "justification": "",   # 一句话依据
                })
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"candidates": cands}, f, ensure_ascii=False, indent=2)
    print(f"候选重复对 {len(cands)} 个（阈值 {a.threshold}）")
    for c in cands:
        print(f"  {c['pair'][0]} ↔ {c['pair'][1]}  score={c['score']}  判据={c['matched_criteria']}")
    print("written:", a.out)

if __name__ == "__main__":
    main()
