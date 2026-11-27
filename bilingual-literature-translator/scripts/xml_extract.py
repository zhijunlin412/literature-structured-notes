#!/usr/bin/env python3
"""Deterministic publisher-XML extractor (JATS-style, stdlib only).

Publisher XML (e.g. PLOS) already carries structure: sections, figures,
captions, tables, supplementary material. Use it directly instead of guessing
from layout. Emits sentence-level units with XML locators so that:

  - the translation scope requested by the case (e.g. "only fig g001/g002
    labels and captions") can be filtered deterministically (--only-ids);
  - the coverage denominator comes from the SOURCE inventory (this script's
    count of in-scope units), never from what the agent chose to translate;
  - every translated sentence keeps its XML locator for verification.

Inline markup is preserved literally (<sub>, <sup>, <italic>, ...): dropping it
turns V<sub>max</sub> into Vmax. Panel ids like (A2) stay inside the sentence
text. Supplementary material (S1 Fig, S1 Text, ...) is extracted like any
other content - nothing is silently skipped.

Usage:
  python xml_extract.py --xml article.xml --out work/extract [--only-ids g001,g002]
Output: extract.json / source_units.md / units_index.json (same shape as
pdf_extract.py; page is null, anchor carries the XML locator instead).
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

STYLE_TAGS = {"sub", "sup", "italic", "bold", "monospace", "sc", "small-caps",
              "underline", "overline", "strike", "roman", "sans-serif"}
TEXT_TAGS = {"p", "title", "article-title", "caption", "label", "abstract", "kwd"}
CELL_TAGS = {"td", "th"}
PREFIX = {"p": "P", "title": "T", "article-title": "T", "caption": "C", "label": "L",
          "abstract": "A", "kwd": "K", "td": "D", "th": "H", "ref": "R"}
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")
# do not split after common abbreviations ("e.g. K_m" is one sentence)
NO_SPLIT_AFTER = re.compile(
    r"\b(e\.g|i\.e|cf|Fig|Figs|Table|et al|vs|ca|approx|resp|viz|No|Dr|St)\.$")


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def strip_ns(root):
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def inner_xml(el):
    """Serialize element content, preserving inline style tags literally."""
    out = [el.text or ""]
    for ch in el:
        if ch.tag in STYLE_TAGS:
            out.append("<%s>%s</%s>" % (ch.tag, inner_xml(ch), ch.tag))
        else:
            # unwrap non-style inline elements (xref, named-content, inline-formula):
            # keep their visible text so citation markers like [12] survive
            out.append(inner_xml(ch))
        out.append(ch.tail or "")
    return "".join(out)


def split_sentences(text):
    raw = [s for s in SENT_SPLIT.split(text) if s and s.strip()]
    # rejoin pieces that were split after an abbreviation
    parts = []
    for s in raw:
        if parts and NO_SPLIT_AFTER.search(parts[-1].rstrip()):
            parts[-1] = parts[-1] + " " + s
        else:
            parts.append(s)
    return parts if len(parts) > 1 else ([text] if text.strip() else [])


def collect(root):
    """Walk the document; yield unit dicts for text-bearing elements."""
    counters = {}
    used_ids = {el.attrib["id"] for el in root.iter() if el.attrib.get("id")}

    def next_id(tag, xml_id):
        if xml_id:
            return xml_id
        while True:
            counters[tag] = counters.get(tag, 0) + 1
            cand = "%s%05d" % (PREFIX.get(tag, "U"), counters[tag])
            if cand not in used_ids:
                used_ids.add(cand)
                return cand

    def walk(el, path, ancestor_ids, in_supp):
        # index children by tag for locator paths
        idx = {}
        for ch in el:
            idx[ch.tag] = idx.get(ch.tag, 0) + 1
            loc_part = "%s[%d]" % (ch.tag, idx[ch.tag])
            ch_ids = list(ancestor_ids)
            xml_id = ch.attrib.get("id")
            if xml_id:
                ch_ids.append(xml_id)
            ch_supp = in_supp or ch.tag == "supplementary-material"

            if ch.tag in TEXT_TAGS or ch.tag in CELL_TAGS or ch.tag == "ref":
                # container elements with block-level <p> children (caption,
                # abstract) are emitted at the <p> level only - no double count
                has_block_child = any(g.tag == "p" for g in ch)
                text = "" if has_block_child else inner_xml(ch).strip()
                if text:
                    base = next_id(ch.tag, xml_id)
                    typ = {"p": "body", "title": "heading", "article-title": "heading",
                           "caption": "caption", "label": "label", "abstract": "abstract",
                           "kwd": "keyword", "td": "table_cell", "th": "table_cell",
                           "ref": "reference"}[ch.tag]
                    sentences = split_sentences(text)
                    if ch.tag in ("p", "caption", "abstract") and sentences:
                        for si, s in enumerate(sentences, 1):
                            yield {"id": "%s.S%03d" % (base, si), "type": typ,
                                   "text": s.strip(), "page": None,
                                   "anchor": {"locator": path + "/" + loc_part},
                                   "ancestor_ids": ch_ids,
                                   "supplementary": ch_supp or None}
                    else:
                        yield {"id": base, "type": typ, "text": text, "page": None,
                               "anchor": {"locator": path + "/" + loc_part},
                               "ancestor_ids": ch_ids,
                               "supplementary": ch_supp or None}
                # still recurse: captions/abstracts may nest structure
            for g in walk(ch, path + "/" + loc_part, ch_ids, ch_supp):
                yield g

    for u in walk(root, "", [], False):
        yield u


def write_outputs(units, out_dir, source_name):
    os.makedirs(out_dir, exist_ok=True)
    for i, u in enumerate(units):
        u["order"] = i
        u.pop("ancestor_ids", None)
    counts = {}
    for u in units:
        counts[u["type"]] = counts.get(u["type"], 0) + 1
    result = {"source_xml": source_name, "stats": {"units": counts, "total": len(units)},
              "units": units}
    with open(os.path.join(out_dir, "extract.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    index = [{"id": u["id"], "type": u["type"], "page": None,
              "chars": len(u["text"]),
              "flags": ["supplementary"] if u.get("supplementary") else []}
             for u in units]
    with open(os.path.join(out_dir, "units_index.json"), "w", encoding="utf-8") as f:
        json.dump({"units": index, "total_chars": sum(i["chars"] for i in index)},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "source_units.md"), "w", encoding="utf-8") as f:
        for u in units:
            tag = u["id"] + (" [补充材料]" if u.get("supplementary") else "")
            f.write("### %s（%s）\n\n%s\n\n" % (tag, u["anchor"]["locator"], u["text"]))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only-ids", default=None,
                    help="comma-separated element ids defining the requested scope "
                         "(e.g. g001,g002); units outside are excluded")
    args = ap.parse_args()

    try:
        tree = ET.parse(args.xml)
    except (ET.ParseError, OSError) as e:
        log("FATAL cannot parse XML: %s" % e)
        return 2
    root = tree.getroot()
    strip_ns(root)

    # collect needs ancestor ids for scope filtering; do a first pass keeping them
    units = []
    for u in collect(root):
        units.append(u)

    if args.only_ids:
        want = set(x.strip() for x in args.only_ids.split(",") if x.strip())
        scoped = [u for u in units if want & set(u.get("ancestor_ids", []))]
        dropped = len(units) - len(scoped)
        log("scope filter --only-ids %s: kept %d units, excluded %d out-of-scope units"
            % (sorted(want), len(scoped), dropped))
        units = scoped

    r = write_outputs(units, args.out, args.xml)
    log("OK units=%s -> %s" % (r["stats"], args.out))
    log("NOTE: coverage denominator = %d units from the source inventory; "
        "report coverage against THIS number, not against translated/extracted counts"
        % r["stats"]["total"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
