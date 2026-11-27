#!/usr/bin/env python3
"""Deterministic PDF paragraph extractor for bilingual translation (stdlib only).

Purpose: turn a real scientific PDF into numbered, anchored translation units
(paragraphs P1..Pn, headings H.., captions C.., tables T.., formulas F..,
references R..) so that a translation can be aligned and verified per unit.

Pipeline:
  1. text layer : pdftotext -bbox -> word-level coordinates
  2. scanned    : pdftoppm + tesseract TSV -> word-level coordinates (OCR)
  3. column detection via x-center gap clustering (on body region)
  4. reading-order reconstruction (columns L->R, lines T->B)
  5. line -> paragraph merging (vertical gap + first-line indent + dehyphenation)
  6. heading/caption/table/formula detection, header/footer separation
  7. writes extract.json (units with page+bbox anchors) and source_units.md

Never invents text; unreadable content is marked honestly.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MATH_CHARS = set("=<>≤≥±×÷∑∫√∂∇∝∞≈≠∈αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ")
SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
SUP = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
SENT_END = tuple('.!?:;”")]}')


def log(m):
    print(m, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ---------- word extraction ----------

def parse_bbox_html(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_bbox_content(f.read())


def parse_bbox_content(content):
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
                level = int(cols[0])
                wordnum = int(cols[5])
                left, top, width, height = (int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9]))
                conf, text = float(cols[10]), cols[11]
            except (ValueError, IndexError):
                continue
            if level == 5 and wordnum > 0 and text.strip() and conf >= 0:
                words.append({"x": float(left), "y": float(top),
                              "x2": float(left + width), "y2": float(top + height),
                              "text": text})
    return words


# ---------- layout helpers ----------

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


def looks_like_table_grid(lines):
    """consecutive lines (>=3) whose word x-centers align to a shared tight grid."""
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
        if any(len(c.split()) > 4 for c in cells):
            return None
        md_rows.append("| " + " | ".join(cells) + " |")
    sep = "| " + " | ".join(["---"] * len(centers)) + " |"
    return "\n".join([md_rows[0], sep] + md_rows[1:])


# ---------- paragraph merging ----------

def merge_paragraphs(line_items):
    """Merge consecutive body lines into paragraphs.

    line_items: list of dicts {type, level, text, bbox, height, page, indent}.
    A new paragraph starts when:
      - the item is not 'body', or
      - vertical gap before this line is large (> 1.7x median interline gap), or
      - the line is indented AND the previous line ended a sentence.
    Dehyphenation: a line ending in '-' joins the next word directly.
    """
    gaps = []
    for a, b in zip(line_items, line_items[1:]):
        if a["page"] == b["page"]:
            g = b["bbox"][1] - a["bbox"][3]
            if g > 0:
                gaps.append(g)
    g0 = sorted(gaps)[len(gaps) // 2] if gaps else 3.0

    paras = []
    cur = None
    for it in line_items:
        if it["type"] != "body":
            if cur:
                paras.append(cur)
                cur = None
            paras.append(it)
            continue
        if cur is None or cur.get("type") != "body":
            cur = dict(it)
            cur["parts"] = [it]
            continue
        prev = cur["parts"][-1]
        same_page = prev["page"] == it["page"]
        vgap = it["bbox"][1] - prev["bbox"][3] if same_page else 1e9
        prev_text = prev["text"].rstrip()
        indented = it["indent"] > 0.012
        broke_sentence = prev_text.endswith(SENT_END)
        big_gap = same_page and vgap > max(1.7 * g0, 0.45 * prev["height"])
        new_para = (not same_page) or big_gap or (indented and broke_sentence)
        if new_para:
            paras.append(cur)
            cur = dict(it)
            cur["parts"] = [it]
        else:
            cur["parts"].append(it)
            cur["bbox"] = [min(cur["bbox"][0], it["bbox"][0]), min(cur["bbox"][1], it["bbox"][1]),
                           max(cur["bbox"][2], it["bbox"][2]), max(cur["bbox"][3], it["bbox"][3])]
    if cur:
        paras.append(cur)

    # absorb unfinished captions: a caption that does not end a sentence
    # continues into the following body unit(s) until it does
    merged = []
    for p in paras:
        if (merged and merged[-1]["type"] == "caption" and p["type"] == "body"
                and not merged[-1]["text"].rstrip().endswith(SENT_END)):
            prev = merged[-1]
            if "parts" not in prev:  # caption's own first line becomes its first part
                prev["parts"] = [{k: prev[k] for k in ("text", "bbox", "page", "margin", "height") if k in prev}]
            prev["parts"].extend(p.get("parts", [p]))
            prev["bbox"] = [min(prev["bbox"][0], p["bbox"][0]), min(prev["bbox"][1], p["bbox"][1]),
                            max(prev["bbox"][2], p["bbox"][2]), max(prev["bbox"][3], p["bbox"][3])]
        else:
            merged.append(p)
    paras = merged

    # join line texts with dehyphenation; line-level margin + order-suspect flags
    for p in paras:
        if "parts" not in p:
            continue
        text = ""
        for part in p["parts"]:
            t = part["text"]
            if text.endswith("-") and not text.endswith(" -"):
                text = text[:-1] + t
            else:
                text = (text + " " + t).strip()
        p["text"] = text
        p["continues_next_page"] = bool(p["parts"] and not p["text"].rstrip().endswith(SENT_END))
        p["margin"] = all(bool(part.get("margin")) for part in p["parts"])
        starts = sorted(part["bbox"][0] for part in p["parts"])
        if len(p["parts"]) >= 3 and starts[-1] - starts[0] > 90:
            p["order_suspect"] = True  # lines start in two distant x clusters: possible column interleaving
        del p["parts"]
    return paras


# ---------- per-page processing ----------

def page_line_items(p):
    words = [w for w in p["words"] if not is_rotated(w) and w["x2"] >= 0.04 * p["width"]]
    if not words:
        return []
    cols = detect_columns(words, p["width"], p["height"])
    all_h = sorted(w["y2"] - w["y"] for w in words)
    h_median = all_h[len(all_h) // 2] if all_h else 8.0
    items = []
    for col in sorted(cols, key=lambda c: min(cx(w) for w in c) if c else 0):
        col_lines = group_lines(col)
        col_left = min(w["x"] for w in col)
        i = 0
        while i < len(col_lines):
            grid = looks_like_table_grid(col_lines[i:i + 8])
            if grid:
                seg = col_lines[i:i + 8]
                bbox = line_bbox([w for ln in seg for w in ln])
                items.append({"type": "table", "level": None, "text": grid, "bbox": bbox,
                              "height": median_height(col_lines[i]), "page": p["page"], "indent": 0.0,
                              "margin": bbox[1] < 0.08 * p["height"] or bbox[3] > 0.92 * p["height"]})
                i += min(8, len(col_lines[i:i + 8]))
                continue
            ln = col_lines[i]
            txt = line_text(ln)
            i += 1
            if not txt.strip():
                continue
            typ, level, _ = classify_line(txt, h_median)
            indent = max(0.0, (min(w["x"] for w in ln) - col_left) / p["width"])
            bbox = line_bbox(ln)
            items.append({"type": typ, "level": level, "text": txt, "bbox": bbox,
                          "height": median_height(ln), "page": p["page"], "indent": indent,
                          "margin": bbox[1] < 0.08 * p["height"] or bbox[3] > 0.92 * p["height"]})
    return items


# ---------- id assignment ----------

PREFIX = {"heading": "H", "body": "P", "caption": "C", "table": "T", "formula": "F"}


def assign_ids(units):
    counters = {"H": 0, "P": 0, "C": 0, "T": 0, "F": 0, "R": 0}
    in_refs = False
    for u in units:
        t = u["type"]
        if t == "heading" and u["text"].strip().lower() in ("references", "参考文献"):
            in_refs = True
        if in_refs and t == "body":
            t = "reference"
            u["type"] = t
        key = PREFIX.get(t, "R")
        counters[key] += 1
        u["id"] = f"{key}{counters[key]}"
    return units


# ---------- main ----------

def ocr_pipeline(pdf):
    """Render + OCR. Intermediates go to uniquely-named files in the temp root
    (no subdir: restricted sandboxes may allow writes only at the temp root)."""
    pages = []
    tmp = tempfile.gettempdir()
    prefix = "pdfx_%d_" % os.getpid()
    staged = os.path.join(tmp, prefix + "src.pdf")
    try:
        # poppler/tesseract may not open non-ASCII paths; stage an ASCII copy
        shutil.copyfile(pdf, staged)
        r = run(["pdftoppm", "-r", "300", "-png", staged, os.path.join(tmp, prefix + "pg")])
        if r.returncode != 0:
            log("WARN pdftoppm failed; OCR unavailable")
            return pages
        langs = ["eng+chi_sim", "eng"]
        pngs = sorted(f for f in os.listdir(tmp) if f.startswith(prefix + "pg") and f.endswith(".png"))
        for i, f in enumerate(pngs):
            words = []
            for lang in langs:
                base = os.path.join(tmp, os.path.splitext(f)[0])
                try:
                    rr = run(["tesseract", os.path.join(tmp, f), base, "-l", lang, "tsv"])
                except FileNotFoundError:
                    log("WARN tesseract not found; OCR unavailable")
                    return pages
                tsv = base + ".tsv"
                if rr.returncode == 0 and os.path.exists(tsv):
                    words = parse_tsv(tsv)
                    if words:
                        break
            if words:
                pages.append({"page": i + 1, "width": 2480, "height": 3508, "words": words, "ocr": True})
        return pages
    except (OSError, shutil.Error) as e:
        log(f"WARN OCR staging failed: {e}")
        return pages
    finally:
        for f in os.listdir(tmp):
            if f.startswith(prefix):
                try:
                    os.remove(os.path.join(tmp, f))
                except OSError:
                    pass


def extract_pdf(pdf, out_dir, force_ocr=False):
    os.makedirs(out_dir, exist_ok=True)
    # text layer via stdout: no intermediate files, no path-encoding issues
    # (capture bytes and decode as UTF-8 ourselves: locale codecs may be GBK etc.)
    r = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True)
    content = r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""
    pages = parse_bbox_content(content) if content else []
    total_words = sum(len(p["words"]) for p in pages)
    ocr_used = False
    if total_words < 20 or force_ocr:
        pages = ocr_pipeline(pdf)
        ocr_used = True

    items = []
    for p in pages:
        items.extend(page_line_items(p))
    units = merge_paragraphs(items)
    units = assign_ids(units)
    for u in units:
        u.pop("indent", None)
        u.pop("height", None)
        u["anchor"] = {"page": u["page"], "bbox": [round(v, 1) for v in u["bbox"]]}
        del u["bbox"]

    counts = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1
    result = {
        "source_pdf": pdf,
        "ocr_used": ocr_used,
        "stats": {"pages": len(pages), "words": sum(len(p["words"]) for p in pages), "units": counts},
        "units": units,
    }
    with open(os.path.join(out_dir, "extract.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "source_units.md"), "w", encoding="utf-8") as f:
        for u in units:
            tag = u["id"]
            if u.get("margin"):
                tag += " [页边]"
            if u.get("order_suspect"):
                tag += " [顺序存疑]"
            if u.get("continues_next_page"):
                tag += " [跨页续]"
            f.write(f"### {tag}（第{u['page']}页）\n\n{u['text']}\n\n")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ocr", action="store_true")
    args = ap.parse_args()
    try:
        r = extract_pdf(args.pdf, args.out, args.ocr)
        s = r["stats"]
        log(f"OK pages={s['pages']} words={s['words']} units={s['units']} ocr={r['ocr_used']} -> {args.out}")
        return 0
    except FileNotFoundError as e:
        log(f"FATAL missing tool: {e}")
        return 2
    except Exception as e:
        log(f"FATAL {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
