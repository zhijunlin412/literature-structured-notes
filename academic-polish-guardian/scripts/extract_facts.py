# -*- coding: utf-8 -*-
"""extract_facts.py — 从学术文本中抽取"润色中不许变"的事实清单。

抽取四类不变量：
1. 数值（含单位）：317 mV、10 mA cm-2、27 h、120 oC ……
2. 引用标记：[1]、[2,3]、[4-6]、(Yan et al., 2021)
3. 图表指向：Fig. 2 / Figure 3a / Table 1 / Eq. (2) / Scheme 1
4. 缩写定义：full term (ABBR) 首次出现形式

用法:
  python extract_facts.py --text original.txt --out facts.json
  python extract_facts.py --paragraphs material.json --out facts.json   # JATS 段落包
"""
import argparse, json, re, sys, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

UNITS = [
    "mV dec-1", "mA cm-2", "kW h", "kg H2", "mA cm−2",
    "mmol", "mol L-1", "mol", "mV", "mA", "eV", "kV",
    "nm", "mm", "cm2", "cm-2", "cm", "μm", "um",
    "oC", "°C", "K", "degrees", "degree",
    "h", "min", "s", "mg L-1", "mg", "g", "ml", "mL", "L",
    "M", "mM", "wt%", "mol%", "at%", "%", "A", "V", "dec-1", "r.p.m.",
]
UNITS.sort(key=len, reverse=True)
UNIT_ALT = "|".join(re.escape(u) for u in UNITS)

NUM = r"(?<![\w.])(?:~|ca\.?|≈)?\d+(?:\.\d+)?(?:\s*[×x*]\s*\d+(?:\.\d+)?)?"
RE_NUM_UNIT = re.compile(rf"({NUM})(\s+({UNIT_ALT}))?(?![\w-])")
RE_CIT_BRACKET = re.compile(r"\[(?:\d+(?:\s*[,\-–]\s*\d+)*)\]")
RE_CIT_AUTHOR = re.compile(r"\(([A-Z][A-Za-z'’\-]+(?: et al\.| and [A-Z][A-Za-z'’\-]+)?,?\s+(?:19|20)\d{2}[a-z]?)\)")
RE_FIGREF = re.compile(r"\b(Fig(?:ure)?s?|Table|Scheme|Eq(?:uation)?s?|Section|Chapter)s?\.?\s*\(?\d+[a-z]?(?:\s*[,–-]\s*\d+[a-z]?)*\)?")
RE_ABBR = re.compile(r"([A-Z][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+){1,6}?)\s*\(([A-Z][A-Za-z0-9]{1,11})\)")

def norm_num(s):
    return s.replace("−", "-").replace("×", "x").replace("*", "x").replace(" ", "").strip()

def extract(text):
    facts = {"numbers": [], "citations": [], "figrefs": [], "abbreviations": []}
    for m in RE_NUM_UNIT.finditer(text):
        facts["numbers"].append({
            "value": norm_num(m.group(1)),
            "unit": (m.group(3) or "").replace("−", "-"),
            "context": text[max(0, m.start() - 40):m.end() + 15].strip(),
        })
    for m in RE_CIT_BRACKET.finditer(text):
        facts["citations"].append(m.group(0))
    for m in RE_CIT_AUTHOR.finditer(text):
        facts["citations"].append("(" + m.group(1) + ")")
    for m in RE_FIGREF.finditer(text):
        facts["figrefs"].append(re.sub(r"\s+", " ", m.group(0)).strip())
    for m in RE_ABBR.finditer(text):
        facts["abbreviations"].append({
            "abbr": m.group(2),
            "full": m.group(1).strip(),
        })
    return facts

def summarize(facts):
    from collections import Counter
    num_counts = Counter((n["value"], n["unit"]) for n in facts["numbers"])
    return {
        "n_number_mentions": len(facts["numbers"]),
        "n_distinct_value_unit": len(num_counts),
        "n_citations": len(facts["citations"]),
        "n_figrefs": len(facts["figrefs"]),
        "n_abbreviations": len(facts["abbreviations"]),
        "value_unit_multiset": {"|".join(k): v for k, v in sorted(num_counts.items())},
    }

def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="纯文本/Markdown/LaTeX 文件")
    src.add_argument("--paragraphs", help="含 paragraphs[{paragraph_id,text}] 的 JSON")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if a.text:
        raw = open(a.text, encoding="utf-8-sig").read()
        text = unicodedata.normalize("NFC", raw)
    else:
        data = json.load(open(a.paragraphs, encoding="utf-8-sig"))
        paras = data.get("paragraphs", data if isinstance(data, list) else [])
        text = "\n\n".join(p.get("text", "") for p in paras)

    facts = extract(text)
    facts["summary"] = summarize(facts)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)
    s = facts["summary"]
    print(f"数值 {s['n_number_mentions']} 处（{s['n_distinct_value_unit']} 种值+单位组合）| "
          f"引用 {s['n_citations']} | 图表 {s['n_figrefs']} | 缩写 {s['n_abbreviations']}")
    print("written:", a.out)

if __name__ == "__main__":
    main()
