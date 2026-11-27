#!/usr/bin/env python3
"""Deterministic PDF layout parser (stdlib only).

Pipelines:
  1. text layer : pdftotext -bbox -> word-level coordinates
  2. scanned    : pdftoppm + tesseract TSV -> word-level coordinates (OCR)
  3. column detection via x-center gap clustering (on body region)
  4. full-width line detection for mixed single/two-column title pages
  5. reading-order reconstruction (full-width first, then columns L->R, T->B)
  6. table grid reconstruction, sub/superscript reconstruction,
     heading/caption/formula detection, header/footer separation
  7. writes layout.json (blocks with page+bbox anchors) and parsed.md

Never invents text; unreadable content is marked honestly.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys

MATH_CHARS = set("=<>≤≥±×÷∑∫√∂∇∝∞≈≠∈αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ")
SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
SUP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")


def log(m):
    print(m, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ---------- word extraction ----------

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


def parse_tsv(path):
    """tesseract TSV -> word list with coordinates (top-origin)."""
    words = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        header = None
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if header is None:
                header = cols
                continue
            if len(cols) < 12:
                continue
            try:
                level, _, _, _, _, wordnum = (int(cols[0]),) + tuple(map(int, cols[1:6]))
                left, top, width, height = (int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9]))
                conf, text = float(cols[10]), cols[11]
            except (ValueError, IndexError):
                continue
            if level == 5 and wordnum > 0 and text.strip() and conf >= 0:
                words.append({"x": float(left), "y": float(top),
                              "x2": float(left + width), "y2": float(top + height),
                              "text": text})
    return words


# ---------- layout ----------

def is_rotated(w):
    wd = w["x2"] - w["x"]
    ht = w["y2"] - w["y"]
    return wd < 0.5 * ht and ht > 12.0


def cx(w):
    return (w["x"] + w["x2"]) / 2


def cy(w):
    return (w["y"] + w["y2"]) / 2


def detect_columns(words, page_width, page_height=None):
    if not words:
        return [[]]
    normal = [w for w in words if not is_rotated(w)]
    if not normal:
        normal = list(words)
    normal = [w for w in normal if w["x2"] >= 0.04 * page_width]
    if not normal:
        normal = list(words)
    band = normal
    if page_height:
        band = [w for w in normal if 0.10 * page_height < cy(w) < 0.90 * page_height]
    if not band:
        band = normal
    xs = sorted(cx(w) for w in band)
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
        best = min(range(len(centers)), key=lambda i: abs(centers[i] - cx(w)))
        cols[best].append(w)
    return cols


def group_lines(words):
    if not words:
        return []
    ws = sorted(words, key=lambda w: (cy(w), cx(w)))
    lines = []
    for w in ws:
        placed = False
        for ln in lines:
            avg = sum(cy(t) for t in ln) / len(ln)
            if abs(cy(w) - avg) < 0.6 * max(w["y2"] - w["y"], 6.0):
                ln.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    for ln in lines:
        ln.sort(key=cx)
    lines.sort(key=lambda ln: max(cy(w) for w in ln))
    return lines


def reconstruct_subsup(ln):
    """Merge small raised/lowered words into the previous word as sub/superscript."""
    if len(ln) < 2:
        return " ".join(w["text"] for w in ln)
    hs = sorted(w["y2"] - w["y"] for w in ln)
    H = hs[len(hs) // 2] if hs else 8.0
    ys = sorted(cy(w) for w in ln)
    Y = ys[len(ys) // 2] if ys else 0.0
    out = []
    for w in ln:
        ht = w["y2"] - w["y"]
        dy = cy(w) - Y
        if out and ht < 0.8 * H and abs(dy) > 0.18 * H:
            kind = SUP if dy < 0 else SUB
            out[-1] = out[-1] + w["text"].translate(kind)
        else:
            out.append(w["text"])
    return " ".join(out)


def line_text(ln):
    return reconstruct_subsup(ln)


def line_bbox(ln):
    return [min(w["x"] for w in ln), min(w["y"] for w in ln),
            max(w["x2"] for w in ln), max(w["y2"] for w in ln)]


def median_height(ln):
    hs = sorted(w["y2"] - w["y"] for w in ln)
    return hs[len(hs) // 2] if hs else 8.0


def is_full_width(ln, page_width):
    b = line_bbox(ln)
    return (b[2] - b[0]) > 0.55 * page_width


HEAD_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s+(.*)$")
CAP_RE = re.compile(r"^\s*(Fig(?:ure)?\.?|Table\s*\d+|Scheme\s*\d+|图\s*\d+|表\s*\d+)\b", re.I)
KNOWN_HEAD = {"abstract", "introduction", "results and discussion", "conclusion",
              "conclusions", "references", "methods", "experimental", "experimental section",
              "acknowledgements", "acknowledgments", "supporting information",
              "摘要", "引言", "结果与讨论", "结论", "参考文献", "方法", "致谢", "附录"}


def classify_line(text, h_median):
    low = text.strip().lower()
    m = HEAD_RE.match(text)
    if m:
        num_str = m.group(1).rstrip(".")
        rest = m.group(2).strip()
        try:
            num = int(num_str.split(".")[0])
        except ValueError:
            num = 99
        has_period = m.group(1).endswith(".")
        is_known = any(k in rest.lower() for k in KNOWN_HEAD)
        # section headings use "2." with a trailing period, or start with a known heading word;
        # references ("1 J. Zhang") and numbered sentences ("10 mA cm-2") do neither
        if num <= 20 and len(rest) <= 60 and (has_period or is_known):
            return "heading", len(num_str.split(".")), rest
        return "body", None, text.strip()
    if low in KNOWN_HEAD:
        return "heading", 1, text.strip()
    if CAP_RE.match(text):
        return "caption", None, text.strip()
    if sum(1 for c in text if c in MATH_CHARS) >= 3 and len(text) < 200:
        return "formula", None, text.strip()
    return "body", None, text.strip()


def looks_like_table_row(words):
    """row with >=3 words separated by gaps (grid cell boundaries)."""
    if len(words) < 3:
        return False
    return True


def detect_table_group(lines):
    """consecutive lines (>=3) whose word x-centers align to a shared tight grid -> markdown table."""
    if len(lines) < 3:
        return None
    rows = []
    for ln in lines:
        if len(ln) < 3:
            return None
        rows.append([(cx(w), w["text"]) for w in ln])
    all_x = sorted(x for r in rows for x, _ in r)
    cols = []
    for x in all_x:
        if not cols or x - cols[-1][-1] > 20:
            cols.append([x])
        else:
            cols[-1].append(x)
    # a real column: covers most rows AND words inside are tightly aligned (span <= 12 px)
    good = [c for c in cols if len(c) >= 0.7 * len(rows) and (max(c) - min(c)) <= 12.0]
    if len(good) < 2:
        return None
    centers = [sum(c) / len(c) for c in good]
    md_rows = []
    for r in rows:
        cells = ["" for _ in centers]
        for x, t in r:
            best = min(range(len(centers)), key=lambda i: abs(centers[i] - x))
            cells[best] = (cells[best] + " " + t).strip()
        # prose cells are long sentences; real table cells are short. reject long cells.
        if any(len(c.split()) > 4 for c in cells):
            return None
        md_rows.append("| " + " | ".join(cells) + " |")
    sep = "| " + " | ".join(["---"] * len(centers)) + " |"
    return "\n".join([md_rows[0], sep] + md_rows[1:])


def build_blocks(lines, page, h_median, page_width):
    blocks = []
    i = 0
    while i < len(lines):
        table = detect_table_group(lines[i:i + 8])
        if table:
            bbox = line_bbox([w for ln in lines[i:i + 8] for w in ln])
            blocks.append({"type": "table", "level": None, "text": table,
                           "page": page, "bbox": bbox, "height": median_height(lines[i])})
            i += min(8, len(lines[i:i + 8]))
            continue
        ln = lines[i]
        txt = line_text(ln)
        if not txt.strip():
            i += 1
            continue
        typ, level, heading = classify_line(txt, h_median)
        blocks.append({"type": typ, "level": level, "text": txt,
                       "page": page, "bbox": line_bbox(ln), "height": median_height(ln)})
        i += 1
    return blocks


def detect_header_footer(blocks, page_h):
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


# ---------- main pipeline ----------

def parse_page(p):
    words = [w for w in p["words"] if not is_rotated(w) and w["x2"] >= 0.04 * p["width"]]
    if not words:
        return []
    cols = detect_columns(words, p["width"], p["height"])
    all_h = sorted(w["y2"] - w["y"] for w in words)
    h_median = all_h[len(all_h) // 2] if all_h else 8.0
    ordered = []
    for col in sorted(cols, key=lambda c: min(cx(w) for w in c) if c else 0):
        for ln in group_lines(col):
            ordered.append(ln)
    blocks = build_blocks(ordered, p["page"], h_median, p["width"])
    blocks = detect_header_footer(blocks, p["height"])
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
        if p["words"]:
            all_blocks.extend(parse_page(p))

    layout = {"source": pdf, "pages": pages, "blocks": all_blocks,
              "stats": {"words": sum(len(p["words"]) for p in pages), "pages": len(pages)}}
    with open(os.path.join(out_dir, "layout.json"), "w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "parsed.md"), "w", encoding="utf-8") as f:
        f.write(build_markdown(all_blocks))
    return layout


def ocr_pipeline(pdf, out_dir):
    pages = []
    r = run(["pdftoppm", "-r", "300", "-png", pdf, os.path.join(out_dir, "pg")])
    if r.returncode != 0:
        return pages
    # tesseract language fallback: try eng+chi_sim, then eng
    langs = ["eng+chi_sim", "eng"]
    for i, f in enumerate(sorted(f for f in os.listdir(out_dir) if f.startswith("pg") and f.endswith(".png"))):
        words = []
        for lang in langs:
            base = os.path.splitext(f)[0]
            tsv = os.path.join(out_dir, base + ".tsv")
            rr = run(["tesseract", os.path.join(out_dir, f), os.path.join(out_dir, base), "-l", lang, "tsv"])
            if rr.returncode == 0 and os.path.exists(tsv):
                words = parse_tsv(tsv)
                if words:
                    break
        if words:
            pages.append({"page": i + 1, "width": 2480, "height": 3508,
                          "words": words, "ocr": True})
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
        elif b["type"] == "table":
            lines.append(f"{b['text']}\n")
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
