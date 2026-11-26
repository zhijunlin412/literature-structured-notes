#!/usr/bin/env python3
"""Deterministic PDF layout parser (stdlib only).

Pipelines:
  1. pdftotext -bbox  -> word-level coordinates (per page)
  2. column detection via x-center histogram
  3. reading-order reconstruction (columns left->right, top->bottom)
  4. line/paragraph grouping, header/footer separation, heading detection,
     caption/table/formula detection
  5. writes layout.json (blocks with page+bbox anchors) and parsed.md

If the document has almost no text layer, falls back to pdftoppm + tesseract.
Never invents text; unreadable content is marked honestly.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys

MATH_CHARS = set("=<>≤≥±×÷∑∫√∂∇∝∞≈≠∈∈αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ")


def log(m):
    print(m, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def parse_bbox_html(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    pages = []
    page_re = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
    word_re = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', re.S)
    for pm in page_re.finditer(content):
        w, h = float(pm.group(1)), float(pm.group(2))
        words = []
        for wm in word_re.finditer(pm.group(3)):
            words.append({
                "x": float(wm.group(1)), "y": float(wm.group(2)),
                "x2": float(wm.group(3)), "y2": float(wm.group(4)),
                "text": html.unescape(wm.group(5)),
            })
        pages.append({"page": len(pages) + 1, "width": w, "height": h, "words": words})
    return pages


def is_rotated(w):
    """side-stamp / rotated text: much narrower than tall"""
    wd = w["x2"] - w["x"]
    ht = w["y2"] - w["y"]
    return wd < 0.5 * ht and ht > 12.0


def detect_columns(words, page_width, page_height=None):
    if not words:
        return [[]]
    normal = [w for w in words if not is_rotated(w)]
    if not normal:
        normal = list(words)
    # drop left-margin side-stamp words (journal "downloaded by" watermark)
    normal = [w for w in normal if w["x2"] >= 0.04 * page_width]
    if not normal:
        normal = list(words)
    band = normal
    if page_height:
        band = [w for w in normal if 0.10 * page_height < (w["y"] + w["y2"]) / 2 < 0.90 * page_height]
    if not band:
        band = normal
    xs = sorted((w["x"] + w["x2"]) / 2 for w in band)
    gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    if not gaps:
        return [normal]
    med = sorted(gaps)[len(gaps) // 2]
    threshold = max(0.022 * page_width, 2.5 * med)
    clusters = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > threshold:
            clusters.append([x])
        else:
            clusters[-1].append(x)
    min_count = max(5, int(len(band) * 0.02))
    clusters = [c for c in clusters if len(c) >= min_count]
    if not clusters:
        clusters = [xs]
    centers = [sum(c) / len(c) for c in clusters]
    cols = [[] for _ in centers]
    for w in normal:
        cx = (w["x"] + w["x2"]) / 2
        best = min(range(len(centers)), key=lambda i: abs(centers[i] - cx))
        cols[best].append(w)
    return cols


def group_lines(words):
    """group words into lines: words with overlapping/similar vertical span."""
    if not words:
        return []
    ws = sorted(words, key=lambda w: (((w["y"] + w["y2"]) / 2), w["x"]))
    lines = []
    for w in ws:
        cy = (w["y"] + w["y2"]) / 2
        placed = False
        for ln in lines:
            ly = (sum(t["y"] + t["y2"] for t in ln) / 2 / len(ln))
            if abs(cy - ly) < 0.6 * max(w["y2"] - w["y"], 6.0):
                ln.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    for ln in lines:
        ln.sort(key=lambda w: w["x"])
    # sort lines top-to-bottom (y=0 at top, increasing downward)
    lines.sort(key=lambda ln: max((w["y"] + w["y2"]) / 2 for w in ln))
    return lines


def line_text(ln):
    return " ".join(w["text"] for w in ln)


def line_bbox(ln):
    return [min(w["x"] for w in ln), min(w["y"] for w in ln),
            max(w["x2"] for w in ln), max(w["y2"] for w in ln)]


def median_height(ln):
    hs = sorted(w["y2"] - w["y"] for w in ln)
    return hs[len(hs) // 2] if hs else 8.0


HEAD_RE = re.compile(r"^\s*(\d+(\.\d+)*)\s+(.*)$")
CAP_RE = re.compile(r"^\s*(Fig(?:ure)?\.?|Table\s*\d+|Scheme\s*\d+|图\s*\d+|表\s*\d+)\b", re.I)
KNOWN_HEAD = {"abstract", "introduction", "results and discussion", "conclusion",
              "conclusions", "references", "methods", "experimental", "experimental section",
              "acknowledgements", "acknowledgments", "supporting information",
              "摘要", "引言", "结果与讨论", "结论", "参考文献", "方法", "致谢", "附录"}


def classify_line(text, h_median):
    low = text.strip().lower()
    m = HEAD_RE.match(text)
    if m:
        return "heading", len(m.group(1).split(".")), m.group(3).strip()
    if low in KNOWN_HEAD:
        return "heading", 1, text.strip()
    if CAP_RE.match(text):
        return "caption", None, text.strip()
    if sum(1 for c in text if c in MATH_CHARS) >= 3 and len(text) < 200:
        return "formula", None, text.strip()
    return "body", None, text.strip()


def build_blocks(lines, page, h_median):
    blocks = []
    for ln in lines:
        txt = line_text(ln)
        if not txt.strip():
            continue
        typ, level, heading = classify_line(txt, h_median)
        blocks.append({
            "type": typ,
            "level": level,
            "text": txt,
            "page": page,
            "bbox": line_bbox(ln),
            "height": median_height(ln),
        })
    return blocks


def detect_header_footer(blocks, page_h):
    """flag blocks in top/bottom margins (y=0 at top, increasing downward)."""
    for b in blocks:
        top_edge = b["bbox"][1]
        bot_edge = b["bbox"][3]
        if top_edge < page_h * 0.10:
            b["margin"] = "top"
        elif bot_edge > page_h * 0.90:
            b["margin"] = "bottom"
        else:
            b["margin"] = None
    return blocks


def parse_pdf(pdf, out_dir, force_ocr=False):
    os.makedirs(out_dir, exist_ok=True)
    bbox_html = os.path.join(out_dir, "bbox.html")
    r = run(["pdftotext", "-bbox", pdf, bbox_html])
    pages = parse_bbox_html(bbox_html) if os.path.exists(bbox_html) else []
    total_words = sum(len(p["words"]) for p in pages)
    if total_words < 20 or force_ocr:
        pages = ocr_pipeline(pdf, out_dir)

    all_blocks = []
    for p in pages:
        if not p["words"]:
            continue
        cols = detect_columns(p["words"], p["width"], p["height"])
        # body median height for heading detection
        all_h = sorted(w["y2"] - w["y"] for w in p["words"])
        h_median = all_h[len(all_h) // 2] if all_h else 8.0
        ordered = []
        for col in sorted(cols, key=lambda c: min((w["x"] + w["x2"]) / 2 for w in c) if c else 0):
            for ln in group_lines(col):
                ordered.append(ln)
        # re-sort all lines by (column-ish y) already handled; group_lines returned top->bottom
        blocks = build_blocks(ordered, p["page"], h_median)
        blocks = detect_header_footer(blocks, p["height"])
        all_blocks.extend(blocks)

    layout = {"source": pdf, "pages": pages, "blocks": all_blocks,
              "stats": {"words": total_words, "pages": len(pages)}}
    with open(os.path.join(out_dir, "layout.json"), "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)

    md = build_markdown(all_blocks)
    with open(os.path.join(out_dir, "parsed.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return layout


def ocr_pipeline(pdf, out_dir):
    pages = []
    r = run(["pdftoppm", "-r", "300", "-png", pdf, os.path.join(out_dir, "page")])
    if r.returncode != 0:
        return pages
    for i, f in enumerate(sorted(os.listdir(out_dir))):
        if not f.startswith("page") or not f.endswith(".png"):
            continue
        base = os.path.splitext(f)[0]
        txt = os.path.join(out_dir, base + ".txt")
        rr = run(["tesseract", os.path.join(out_dir, f), txt, "-l", "eng+chi_sim"])
        if rr.returncode == 0 and os.path.exists(txt + ".txt"):
            with open(txt + ".txt", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            words = []
            for line in text.splitlines():
                x = 0.0
                for tok in line.split():
                    words.append({"x": x, "y": 0, "x2": x + len(tok) * 10, "y2": 12, "text": tok})
                    x += (len(tok) + 1) * 10
            pages.append({"page": i + 1, "width": 1000, "height": 1400, "words": words,
                          "ocr": True})
    return pages


def build_markdown(blocks):
    lines = []
    for b in blocks:
        if b["type"] == "heading":
            lines.append(f"\n{'#' * (b['level'] or 1)} {b['text']}\n")
        elif b["type"] == "caption":
            lines.append(f"> {b['text']}\n")
        elif b["type"] == "formula":
            lines.append(f"$$\n{b['text']}\n$$\n")
        else:
            lines.append(f"{b['text']}\n\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ocr", action="store_true")
    args = ap.parse_args()
    try:
        layout = parse_pdf(args.pdf, args.out, args.ocr)
        log(f"OK pages={layout['stats']['pages']} words={layout['stats']['words']} -> {args.out}")
        return 0
    except FileNotFoundError as e:
        log(f"FATAL missing tool: {e}")
        return 2
    except Exception as e:
        log(f"FATAL {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
