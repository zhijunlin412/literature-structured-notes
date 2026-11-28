# -*- coding: utf-8 -*-
"""parse_refs.py — 解析稿件与文献库，建立独立清单（覆盖率的"外部分母"）。

从原文本身清点：正文引用标记（含所在句）、文献条目原文——不依赖 Agent 自报。

用法:
  python parse_refs.py --manuscript manuscript.md --library refs.txt --out inventory.json
  library 支持：编号列表（"1 ..." / "[1] ..."）、BibTeX（@article{...}）、JSON 数组。
输出 inventory.json: {markers: [...], entries: [...], summary: {...}}
"""
import argparse, json, re, sys, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RE_MARKER = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)*)\]")
RE_BIB = re.compile(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\s*\}", re.S)
RE_FIELD = re.compile(r"(\w+)\s*=\s*[\{\"](.+?)[\}\"]\s*,?\s*$", re.M)

def norm(t):
    return unicodedata.normalize("NFC", t).replace("−", "-").replace("–", "-")

def sentence_of(text, pos):
    """取 pos 所在的句子（按 . ! ? 。！？ 切）。"""
    start = max(text.rfind(". ", 0, pos), text.rfind("! ", 0, pos),
                text.rfind("? ", 0, pos), text.rfind("。", 0, pos),
                text.rfind("\n", 0, pos)) + 1
    m = re.search(r"[.!?。！？]\s", text[pos:]) or re.search(r"$", text[pos:])
    end = pos + (m.end() if m else 0)
    return text[start:end].strip()

def expand_marker(body):
    """'4,6-8' -> [4,6,7,8]"""
    out = []
    for part in re.split(r"\s*,\s*", body):
        m = re.match(r"(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.strip().isdigit():
            out.append(int(part.strip()))
    return out

def parse_manuscript(text):
    markers = []
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    for i, para in enumerate(paras, 1):
        for m in RE_MARKER.finditer(para):
            nums = expand_marker(m.group(1))
            sent = sentence_of(para, m.start())
            markers.append({
                "raw": m.group(0), "numbers": nums,
                "paragraph": i, "sentence": sent,
                "is_paragraph_end": para.rstrip().rstrip(".。").endswith(m.group(0)) or m.end() >= len(para.rstrip()) - 2,
                "n_sentences_in_paragraph": len(re.findall(r"[.!?。！？](?:\s|$)", para)),
            })
    return markers, len(paras)

def parse_library(text):
    entries = []
    if "@" in text and "{" in text:  # BibTeX
        for m in RE_BIB.finditer(text):
            fields = {k.lower(): v.strip() for k, v in RE_FIELD.findall(m.group(3))}
            entries.append({"key": m.group(2).strip(), "entry_type": m.group(1).lower(),
                            "fields": fields, "raw": m.group(0)})
    else:
        # 编号列表：每条以 "数字 " 或 "[数字] " 起头
        chunks = re.split(r"\n\s*(?=\[?\d+\]?\s)", text)
        for c in chunks:
            c = c.strip()
            m = re.match(r"\[?(\d+)\]?\s+(.*)", c, re.S)
            if m:
                entries.append({"key": m.group(1), "raw": re.sub(r"\s+", " ", m.group(2)).strip()})
    return entries

def guess_fields(raw):
    """尽力从自由文本条目猜字段（供 Agent 核对，不作最终依据）。"""
    g = {}
    y = re.search(r"\b(19|20)\d{2}\b", raw)
    if y:
        g["year"] = y.group(0)
    d = re.search(r"(?:doi[:\s]*|https?://doi\.org/)(10\.\d{4,9}/\S+)", raw, re.I)
    if d:
        g["doi"] = d.group(1).rstrip(".")
    p = re.search(r"\b(\d+)\s*[-–]\s*(\d+)\s*\.?\s*$", raw)
    if p:
        g["pages"] = p.group(1) + "-" + p.group(2)
    return g

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    mtext = norm(open(a.manuscript, encoding="utf-8-sig").read())
    ltext = norm(open(a.library, encoding="utf-8-sig").read())

    markers, n_paras = parse_manuscript(mtext)
    entries = parse_library(ltext)
    for e in entries:
        if "fields" not in e:
            e["fields"] = guess_fields(e.get("raw", ""))

    cited_nums = sorted({n for mk in markers for n in mk["numbers"]})
    inv = {
        "markers": markers,
        "entries": entries,
        "summary": {
            "paragraphs": n_paras,
            "markers": len(markers),
            "distinct_cited": len(cited_nums),
            "cited_numbers": cited_nums,
            "entries": len(entries),
            "orphan_entries": [e["key"] for e in entries
                               if e["key"].isdigit() and int(e["key"]) not in cited_nums],
            "dangling_markers": [n for n in cited_nums
                                 if not any(e["key"] == str(n) for e in entries)],
        },
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)
    s = inv["summary"]
    print(f"段落 {s['paragraphs']} | 引用标记 {s['markers']}（去重 {s['distinct_cited']} 个号）| "
          f"条目 {s['entries']} | 未被引用条目 {len(s['orphan_entries'])} | 悬空引用 {len(s['dangling_markers'])}")
    print("written:", a.out)

if __name__ == "__main__":
    main()
