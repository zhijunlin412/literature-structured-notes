#!/usr/bin/env python3
# tex_scan.py — LaTeX 工程结构识别（确定性脚本，纯标准库）
#
# 递归扫描工程目录，产出 project.json：
#   main_file    含 \documentclass 的主文件（多个候选时报 warning 并取最像的）
#   files        全部 .tex/.bib/.bst/.cls/.sty/图片文件清单（大小、行数）
#   includes     \input/\include 依赖图（含缺失文件检测）
#   bibliography 参考文献方式：bibtex(\bibliography) / biber(\addbibresource) / 手写 thebibliography
#   engine_hint  引擎建议：fontspec/ctex/polyglossia -> xelatex；否则 pdflatex
#   packages     导言区 \usepackage 清单
# 用法：python tex_scan.py --project <dir> --out project.json
import argparse, json, os, re, sys

TEX_EXT = {".tex", ".bib", ".bst", ".cls", ".sty", ".clo", ".def"}
IMG_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".eps"}
DOCCLASS_RE = re.compile(r'\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}')
INPUT_RE = re.compile(r'\\(?:input|include)\{([^}]+)\}')
USEPKG_RE = re.compile(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}')
BIBLIO_RE = re.compile(r'\\bibliography\{([^}]+)\}')
ADDBIB_RE = re.compile(r'\\addbibresource(?:\[[^\]]*\])?\{([^}]+)\}')
THEBIB_RE = re.compile(r'\\begin\{thebibliography\}')
BIBSTYLE_RE = re.compile(r'\\bibliographystyle\{([^}]+)\}')


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = os.path.abspath(args.project)
    if not os.path.isdir(root):
        print("FATAL: 工程目录不存在: %s" % root)
        sys.exit(2)

    files, tex_files = [], []
    for dirpath, _d, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            ext = os.path.splitext(name)[1].lower()
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if ext in TEX_EXT or ext in IMG_EXT:
                kind = ("tex" if ext == ".tex" else
                        "bib" if ext == ".bib" else
                        "style" if ext in (".sty", ".cls", ".clo", ".def", ".bst")
                        else "figure")
                n = read(full).count("\n") + 1 if ext in TEX_EXT else 0
                files.append({"path": rel, "kind": kind, "size": size,
                              "lines": n})
                if ext == ".tex":
                    tex_files.append(rel)

    # 主文件识别
    mains = []
    for rel in tex_files:
        m = DOCCLASS_RE.search(read(os.path.join(root, rel)))
        if m:
            mains.append({"path": rel, "class": m.group(1)})
    warnings = []
    if not mains:
        print("FATAL: 未找到含 \\documentclass 的主文件（.tex 共 %d 个）"
              % len(tex_files))
        sys.exit(2)
    if len(mains) > 1:
        warnings.append("多个 \\documentclass 候选：%s；取 %s，若非主文件请用 "
                        "tex_build --main 指定"
                        % (", ".join(m["path"] for m in mains),
                           mains[0]["path"]))
    main_file = mains[0]

    # 依赖图与缺失检测
    includes, missing = [], []
    queue = [main_file["path"]]
    seen = set()
    while queue:
        rel = queue.pop(0)
        if rel in seen:
            continue
        seen.add(rel)
        text = read(os.path.join(root, rel))
        for m in INPUT_RE.finditer(text):
            dep = m.group(1)
            if not os.path.splitext(dep)[1]:
                dep += ".tex"
            dep = os.path.normpath(os.path.join(os.path.dirname(rel), dep)) \
                .replace(os.sep, "/")
            includes.append({"from": rel, "to": dep})
            if os.path.isfile(os.path.join(root, dep)):
                queue.append(dep)
            else:
                missing.append(dep)

    main_text = read(os.path.join(root, main_file["path"]))
    packages = []
    for m in USEPKG_RE.finditer(main_text):
        for p in m.group(1).split(","):
            p = p.strip()
            if p and p not in packages:
                packages.append(p)

    # 参考文献方式
    bibliography = {"mode": "none"}
    if BIBLIO_RE.search(main_text):
        sm = BIBSTYLE_RE.search(main_text)
        bibliography = {"mode": "bibtex",
                        "style": sm.group(1) if sm else "plain",
                        "bibs": [b.strip()
                                 for m in BIBLIO_RE.finditer(main_text)
                                 for b in m.group(1).split(",")]}
    elif ADDBIB_RE.search(main_text):
        bibliography = {"mode": "biber",
                        "bibs": [m.group(1)
                                 for m in ADDBIB_RE.finditer(main_text)]}
    elif THEBIB_RE.search(main_text):
        bibliography = {"mode": "manual"}
    if bibliography["mode"] in ("bibtex", "biber"):
        for b in list(bibliography.get("bibs", [])):
            bf = b if b.endswith(".bib") else b + ".bib"
            if not os.path.isfile(os.path.join(root, bf)):
                missing.append(bf)

    # 引擎建议
    engine_hint = "pdflatex"
    if any(p in packages for p in ("fontspec", "ctex", "xeCJK", "polyglossia")):
        engine_hint = "xelatex"
    if "luatex" in packages:
        engine_hint = "lualatex"

    proj = {"project_dir": root, "main_file": main_file,
            "candidates": mains, "files": files, "includes": includes,
            "packages": packages, "bibliography": bibliography,
            "engine_hint": engine_hint, "missing_files": sorted(set(missing)),
            "warnings": warnings,
            "stats": {"tex": len(tex_files),
                      "bib": sum(1 for f in files if f["kind"] == "bib"),
                      "style": sum(1 for f in files if f["kind"] == "style"),
                      "figure": sum(1 for f in files if f["kind"] == "figure"),
                      "includes": len(includes),
                      "missing": len(set(missing))}}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=1)
    s = proj["stats"]
    print("project -> %s" % args.out)
    print("main=%s (class=%s)  tex=%d bib=%d style=%d figure=%d  "
          "engine_hint=%s  bib_mode=%s  missing=%d"
          % (main_file["path"], main_file["class"], s["tex"], s["bib"],
             s["style"], s["figure"], engine_hint, bibliography["mode"],
             s["missing"]))
    for w in warnings:
        print("WARNING:", w)
    for m in proj["missing_files"]:
        print("MISSING:", m)


if __name__ == "__main__":
    main()
