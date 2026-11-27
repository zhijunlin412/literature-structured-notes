# -*- coding: utf-8 -*-
"""check_preservation.py — "没改坏"校验：对比润色前后文本，事实与强度必须守恒。

校验项（违反为 error，存疑为 warning）：
1. 数值+单位多重集一致（317 mV 不能丢、不能改、不能新增）
2. 引用标记集合一致（[1] 不能少不能多）
3. 图表指向集合一致（Fig. 2 不能改成 Fig. 3）
4. 限定词强度 tier 多重集一致（may 不能被升级成 demonstrate）
5. 因果/方向词变化检测（correlated 不能变 lead to；increase 不能变 decrease）
6. 缩写：原文定义过的缩写改后仍保留；新增缩写必须也有定义

用法:
  python check_preservation.py --original orig.txt --revised polished.txt \
      --lexicon ../assets/hedging_lexicon.json --out preservation_report.json
退出码: 0=无 error; 1=存在 error 级违反。
"""
import argparse, json, re, sys, unicodedata
from collections import Counter

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from extract_facts import extract  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def norm_text(t):
    t = unicodedata.normalize("NFC", t)
    return t.replace("−", "-").replace("–", "-")

def num_multiset(facts, fold_unit_case=True):
    # 单位大小写折叠后比较（mL/ml 属风格统一，不算改坏）；
    # 单位写法变化由 check_preservation 另行以 warning 报告，供人工确认。
    if fold_unit_case:
        return Counter((n["value"], n["unit"].lower()) for n in facts["numbers"])
    return Counter((n["value"], n["unit"]) for n in facts["numbers"])

def multiset_diff(a, b):
    """返回 (a 有而 b 缺, b 有而 a 缺)，各项带数量。"""
    missing, added = [], []
    for k, v in a.items():
        if b.get(k, 0) < v:
            missing.append({"item": list(k), "count": v - b.get(k, 0)})
    for k, v in b.items():
        if a.get(k, 0) < v:
            added.append({"item": list(k), "count": v - a.get(k, 0)})
    return missing, added

def word_hits(text, words):
    hits = Counter()
    low = text.lower()
    for w in sorted(words, key=len, reverse=True):
        pat = re.compile(r"(?<![A-Za-z])" + re.escape(w.lower()) + r"(?![A-Za-z])")
        n = len(pat.findall(low))
        if n:
            hits[w.lower()] = n
            low = pat.sub(" ", low)  # 词组命中后移除，避免单词重复计数
    return hits

def tier_multiset(text, lexicon):
    tiers = lexicon["tiers"]
    en_all = {w for t in tiers.values() for w in t["en"]} | {w for t in tiers.values() for w in t["zh"]}
    hits = word_hits(text, sorted(en_all))
    out = Counter()
    for tier_key, tier in tiers.items():
        for w in tier["en"] + tier["zh"]:
            if w.lower() in hits:
                out[tier_key] += hits[w.lower()]
    return out, hits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True)
    ap.add_argument("--revised", required=True)
    ap.add_argument("--lexicon", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    orig = norm_text(open(a.original, encoding="utf-8-sig").read())
    rev = norm_text(open(a.revised, encoding="utf-8-sig").read())
    lexicon = json.load(open(a.lexicon, encoding="utf-8"))

    errors, warnings = [], []

    fo, fr = extract(orig), extract(rev)

    # 1. 数值+单位（单位大小写折叠比较；写法变化另报 warning）
    miss, add = multiset_diff(num_multiset(fo), num_multiset(fr))
    for m in miss:
        errors.append({"check": "numbers", "detail": f"改后丢失数值 {m['item'][0]} {m['item'][1]} ×{m['count']}"})
    for m in add:
        errors.append({"check": "numbers", "detail": f"改后新增数值 {m['item'][0]} {m['item'][1]} ×{m['count']}（润色不得新增材料外数字）"})
    exact_o, exact_r = num_multiset(fo, False), num_multiset(fr, False)
    for k in set(exact_o) | set(exact_r):
        if exact_o.get(k, 0) != exact_r.get(k, 0):
            folded = (k[0], k[1].lower())
            if num_multiset(fo).get(folded, 0) == num_multiset(fr).get(folded, 0):
                warnings.append({"check": "unit-style", "detail": f"数值 {k[0]} 的单位写法有变化（如 {k[1]}），数值未变，请确认为风格统一"})

    # 2. 引用标记
    co, cr = Counter(fo["citations"]), Counter(fr["citations"])
    miss, add = multiset_diff(co, cr)
    for m in miss:
        errors.append({"check": "citations", "detail": f"改后丢失引用 {m['item'][0]} ×{m['count']}"})
    for m in add:
        errors.append({"check": "citations", "detail": f"改后新增引用 {m['item'][0]} ×{m['count']}"})

    # 3. 图表指向
    go, gr = Counter(fo["figrefs"]), Counter(fr["figrefs"])
    miss, add = multiset_diff(go, gr)
    for m in miss:
        errors.append({"check": "figrefs", "detail": f"改后丢失图表指向 {m['item'][0]}"})
    for m in add:
        warnings.append({"check": "figrefs", "detail": f"改后新增图表指向 {m['item'][0]}，请确认是否本来就该有"})

    # 4. 限定词强度 tier
    to, ho = tier_multiset(orig, lexicon)
    tr, hr = tier_multiset(rev, lexicon)
    for tier in ("strong", "medium", "weak"):
        if to.get(tier, 0) != tr.get(tier, 0):
            errors.append({
                "check": "hedging-tier",
                "detail": f"限定强度 tier={tier} 原文 {to.get(tier,0)} 处 → 改后 {tr.get(tier,0)} 处；结论强度被改变",
            })
    # 词级别明细（warning，供人工复核同 tier 替换）
    for w in sorted(set(ho) | set(hr)):
        if ho.get(w, 0) != hr.get(w, 0):
            warnings.append({"check": "hedging-word", "detail": f"限定词 '{w}' 原文 {ho.get(w,0)} 次 → 改后 {hr.get(w,0)} 次"})

    # 5. 因果/方向词
    for group, words in lexicon["direction_words"].items():
        wo = word_hits(orig, words)
        wr = word_hits(rev, words)
        so, sr = sum(wo.values()), sum(wr.values())
        if group in ("causal", "correlative") and so != sr:
            errors.append({"check": "causality", "detail": f"{group} 类词数量 {so} → {sr}：因果与相关的界限可能被改变"})
        if group in ("increase", "decrease"):
            for w in sorted(set(wo) | set(wr)):
                if wo.get(w, 0) != wr.get(w, 0):
                    warnings.append({"check": f"direction-{group}", "detail": f"'{w}' {wo.get(w,0)} → {wr.get(w,0)} 次，请核对变化方向未被改写"})

    # 6. 缩写
    ab_o = {x["abbr"] for x in fo["abbreviations"]}
    ab_r = {x["abbr"] for x in fr["abbreviations"]}
    for ab in sorted(ab_o - ab_r):
        # 原文定义过的缩写，改后若该缩写仍在用却没有定义 → error；若缩写完全消失 → 仅提示
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(ab)}(?![A-Za-z0-9])", rev):
            errors.append({"check": "abbreviation", "detail": f"缩写 {ab} 仍在改后文本中使用，但其首次定义被删去"})
        else:
            warnings.append({"check": "abbreviation", "detail": f"缩写 {ab} 及其定义在改后文本中消失（若相关内容被删属正常，请确认）"})
    for ab in sorted(ab_r - ab_o):
        warnings.append({"check": "abbreviation", "detail": f"改后新增缩写定义 {ab}，请确认确有必要"})

    report = {
        "status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "original": len(fo["numbers"]),
            "revised": len(fr["numbers"]),
            "hedging_tiers_original": dict(to),
            "hedging_tiers_revised": dict(tr),
        },
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"preservation: {report['status']}（error {len(errors)} / warning {len(warnings)}）")
    for e in errors:
        print("  ERROR:", e["detail"])
    for w in warnings[:10]:
        print("  warn :", w["detail"])
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
