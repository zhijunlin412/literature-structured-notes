#!/usr/bin/env python3
# scan_materials.py — 材料清点与参数台账构建（确定性脚本，纯标准库）
#
# 作用：递归扫描材料目录，产出 inventory.json：
#   files     全部可读文本文件清单（类型、行数、大小）
#   registry  参数台账（tier A：配置/日志/代码中的键值参数、版本、随机种子；
#                        tier B：文档中的数值+单位事实，按 (值,单位) 去重）
#   versions  软件/环境版本记录      seeds  随机种子记录
#   conflicts 同名键在不同来源取值冲突清单（仅 tier A）
#   datasets  数据文件（csv/tsv）的行数与表头
# 台账是覆盖率检查的外部分母：Agent 不得自报分母。
#
# 用法：python scan_materials.py --materials <dir> --out inventory.json
import argparse, json, os, re, sys

TEXT_EXT = {".md", ".txt", ".log", ".json", ".yaml", ".yml", ".ini", ".cfg",
            ".toml", ".py", ".sh", ".tex", ".xml", ".conf", ".config",
            ".csv", ".tsv", ".out"}
KIND_MAP = {".json": "config", ".yaml": "config", ".yml": "config",
            ".ini": "config", ".cfg": "config", ".toml": "config",
            ".conf": "config", ".config": "config",
            ".log": "log", ".txt": "log", ".out": "log",
            ".py": "code", ".sh": "code",
            ".md": "doc", ".tex": "doc",
            ".csv": "data", ".tsv": "data", ".xml": "data"}
MAX_FILE = 2 * 1024 * 1024
MAX_REGISTRY = 2000

KV_RE = re.compile(r'^\s*(?:--)?([A-Za-z_一-鿿][\w.\-一-鿿]{0,40})\s*[:=：]\s*(\S.*?)\s*$')
NUM_RE = re.compile(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')
UNIT_RE = re.compile(
    r'(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*'
    r'(℃|°C|oC|K(?:/min)?|mM|μM|uM|M|mol/L|mol|mmol|μmol|umol|mg|μg|ug|g|kg|'
    r'mL|μL|uL|L|h|min|s|ms|V|mV|A|mA|μA|uA|rpm|wt%|at%|vol%|%|'
    r'nm|μm|um|mm|cm|m|Hz|kHz|MHz|GPa|MPa|kPa|Pa|bar|atm|Torr|eV|keV|'
    r'mA/cm2|mA cm-2|mV dec-1|mV/dec|dec-1|cm2|cm-2|W|kW|Wh|cycles|次|小时|分钟|天|周)\b')
VERSION_RE = re.compile(
    r'(?i)\b(python|torch|pytorch|tensorflow|numpy|scipy|pandas|cuda|cudnn|'
    r'matlab|origin|comsol|vasp|lammps|gromacs|gaussian|autolab|chi|'
    r'biologic|ec-lab|eclab|zview|gamry|ivium|git|docker)\s*[:vV=]?\s*(\d+(?:\.\d+){1,3})')
SEED_RE = re.compile(r'(?i)\b(seed|random_seed|randseed|随机种子)\s*[:=：]?\s*(\d{1,10})\b')


def norm_key(k):
    return re.sub(r'[\s_.\-]+', '', k.strip().lower())


def add_entry(registry, seen, key, value, unit, source_file, line_no, line, tier, kind):
    if len(registry) >= MAX_REGISTRY:
        return None
    if tier == "B":
        sig = ("B", value, unit)
        if sig in seen:
            return None
        seen.add(sig)
    eid = "P%04d" % (len(registry) + 1)
    registry.append({
        "id": eid, "tier": tier, "key": key, "value": value, "unit": unit,
        "source_file": source_file, "line": line_no,
        "evidence": line.strip()[:300], "file_kind": kind})
    return eid


def scan_file(path, rel, kind, registry, seen, versions, seeds):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return 0
    for i, line in enumerate(lines, 1):
        if len(line) > 500:
            line = line[:500]
        for m in VERSION_RE.finditer(line):
            versions.append({"software": m.group(1), "version": m.group(2),
                             "source_file": rel, "line": i,
                             "evidence": line.strip()[:300]})
            add_entry(registry, seen, m.group(1) + "_version", m.group(2),
                      "", rel, i, line, "A", kind)
        for m in SEED_RE.finditer(line):
            seeds.append({"value": m.group(2), "source_file": rel, "line": i,
                          "evidence": line.strip()[:300]})
            add_entry(registry, seen, "seed", m.group(2), "", rel, i, line,
                      "A", kind)
        if kind in ("config", "log", "code"):
            m = KV_RE.match(line)
            if m and NUM_RE.search(m.group(2)):
                key, val = m.group(1), m.group(2).strip()
                um = UNIT_RE.search(val)
                if um:
                    value, unit = um.group(1), um.group(2)
                else:
                    nm = NUM_RE.search(val)
                    value, unit = (nm.group(0), "") if nm else (val[:60], "")
                add_entry(registry, seen, key, value, unit, rel, i, line,
                          "A", kind)
        elif kind == "doc":
            for m in UNIT_RE.finditer(line):
                add_entry(registry, seen, "", m.group(1), m.group(2),
                          rel, i, line, "B", kind)
    return len(lines)


def scan_data_file(path, rel, datasets):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = [next(f, None) for _ in range(2)]
            n = 2 + sum(1 for _ in f)
    except OSError:
        return
    sep = "\t" if rel.endswith(".tsv") else ","
    header = (head[0] or "").strip().split(sep) if head[0] else []
    datasets.append({"file": rel, "rows": max(n - 1, 0),
                     "columns": [h.strip() for h in header][:40]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = os.path.abspath(args.materials)
    if not os.path.isdir(root):
        print("FATAL: 材料目录不存在: %s" % root)
        sys.exit(2)
    files, registry, versions, seeds, datasets = [], [], [], [], []
    seen = set()
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            ext = os.path.splitext(name)[1].lower()
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if ext not in TEXT_EXT or size > MAX_FILE:
                files.append({"path": rel, "kind": "skipped",
                              "size": size, "lines": 0})
                continue
            kind = KIND_MAP.get(ext, "doc")
            if kind == "data":
                scan_data_file(path, rel, datasets)
                nlines = datasets[-1]["rows"] + 1
            else:
                nlines = scan_file(path, rel, kind, registry, seen,
                                   versions, seeds)
            files.append({"path": rel, "kind": kind, "size": size,
                          "lines": nlines})
    # 冲突检测：tier A 中归一化键相同但取值不同
    by_key = {}
    for e in registry:
        if e["tier"] == "A" and e["key"]:
            by_key.setdefault(norm_key(e["key"]), []).append(e)
    conflicts = []
    for k, es in sorted(by_key.items()):
        vals = {}
        for e in es:
            vals.setdefault(e["value"], []).append(e)
        if len(vals) > 1:
            conflicts.append({
                "id": "C%d" % (len(conflicts) + 1), "key": es[0]["key"],
                "options": [{"value": v,
                             "sources": [{"source_file": e["source_file"],
                                          "line": e["line"]}
                                         for e in grp]}
                            for v, grp in sorted(vals.items())]})
    inv = {"materials_dir": root, "files": files, "registry": registry,
           "versions": versions, "seeds": seeds, "conflicts": conflicts,
           "datasets": datasets,
           "stats": {"files": len(files),
                     "registry_total": len(registry),
                     "tier_A": sum(1 for e in registry if e["tier"] == "A"),
                     "tier_B": sum(1 for e in registry if e["tier"] == "B"),
                     "versions": len(versions), "seeds": len(seeds),
                     "conflicts": len(conflicts),
                     "datasets": len(datasets)}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)
    s = inv["stats"]
    print("inventory -> %s" % args.out)
    print("files=%d  registry=%d (A=%d, B=%d)  versions=%d  seeds=%d  "
          "conflicts=%d  datasets=%d"
          % (s["files"], s["registry_total"], s["tier_A"], s["tier_B"],
             s["versions"], s["seeds"], s["conflicts"], s["datasets"]))
    for c in conflicts:
        print("CONFLICT %s %s: %s" % (
            c["id"], c["key"],
            "; ".join("%s @ %s:%d" % (o["value"], o["sources"][0]["source_file"],
                                      o["sources"][0]["line"])
                      for o in c["options"])))


if __name__ == "__main__":
    main()
