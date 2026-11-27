#!/usr/bin/env python3
"""Fetch source units from extract.json in small, budget-friendly batches.

The evaluation budget (64 requests / 900 s / limited context) is fixed: every
oversized tool return costs answer capacity. Read units_index.json first,
then fetch only the units you need, capped by --max-chars.

Usage:
  python get_units.py --extract work/extract/extract.json --ids P1,P2,C3
  python get_units.py --extract work/extract/extract.json --pages 2-3 --max-chars 9000
  python get_units.py --extract work/extract/extract.json --type caption
"""
import argparse
import json
import sys


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", required=True)
    ap.add_argument("--ids", default=None, help="comma-separated unit ids, e.g. P1,P2,C3")
    ap.add_argument("--pages", default=None, help="page range, e.g. 2 or 2-4")
    ap.add_argument("--type", default=None, help="unit type filter: heading/body/caption/table/formula/reference")
    ap.add_argument("--max-chars", type=int, default=9000,
                    help="stop emitting once this budget is exhausted (default 9000)")
    args = ap.parse_args()

    with open(args.extract, encoding="utf-8") as f:
        units = json.load(f).get("units", [])

    sel = units
    if args.ids:
        want = [i.strip() for i in args.ids.split(",") if i.strip()]
        order = {u["id"]: u for u in units}
        sel = [order[i] for i in want if i in order]
        missing = [i for i in want if i not in order]
        if missing:
            log(f"WARN unknown ids: {','.join(missing)}")
    if args.pages:
        if "-" in args.pages:
            lo, hi = (int(x) for x in args.pages.split("-", 1))
        else:
            lo = hi = int(args.pages)
        sel = [u for u in sel if u.get("page") is not None and lo <= u["page"] <= hi]
    if args.type:
        sel = [u for u in sel if u["type"] == args.type]

    used = 0
    shown = 0
    for u in sel:
        text = u["text"]
        if used + len(text) > args.max_chars and shown:
            log(f"... STOP: --max-chars {args.max_chars} reached after {shown} units; "
                f"refetch the rest by --ids or --pages")
            break
        flags = "".join(f" [{k}]" for k in ("margin", "order_suspect", "continues_next_page", "supplementary") if u.get(k))
        loc = "p%s" % u["page"] if u.get("page") else u.get("anchor", {}).get("locator", "")
        log(f"### {u['id']} ({loc}, {u['type']}){flags}\n{text}\n")
        used += len(text)
        shown += 1
    log(f"OK units={shown}/{len(sel)} chars={used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
