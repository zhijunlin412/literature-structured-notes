#!/usr/bin/env python3
# tex_build.py — 编译-诊断-清单 一体化驱动（确定性脚本，纯标准库）
#
# 职责：
#   1) 按工程结构执行编译轮次：engine →（bibtex/biber）→ engine × N，
#      出现 "Rerun to get" / 引用未收敛信号时自动加轮，最多 --max-passes 轮；
#   2) 解析最终日志：错误按 assets/error_taxonomy.json 归类到根因，
#      定位到文件与行号（文件栈跟踪 + l.<n>），未解析引用单独列出；
#   3) 生成可复现清单 manifest.json：引擎与发行版版本、宏包及版本、
#      文献样式、每轮命令与耗时、PDF 页数——他人按此可复现构建。
# 退出码：0 编译通过且引用收敛；1 仍有错误或未解析引用；2 环境/输入致命问题。
#
# 用法：python tex_build.py --project <dir> [--main main.tex] [--engine pdflatex]
#        [--engine-dir <TeX bin 目录>] [--build-dir <dir>] [--out report.json]
import argparse, json, os, re, shutil, subprocess, sys, time, uuid
import urllib.request
import urllib.error

REMOTE_URL_DEFAULT = "https://texlive.net/cgi-bin/latexcgi"

ERR_LINE_RE = re.compile(r'^! (.*)')
LINE_NO_RE = re.compile(r'^l\.(\d+)\s*(.*)')
PKG_RE = re.compile(r'^Package: (\S+) +(.*)')
OUTPDF_RE = re.compile(r'Output written on (.+?\.pdf) \((\d+) pages?, (\d+) bytes?\)')
RERUN_RE = re.compile(r'(Rerun to get|Label\(s\) may have changed|'
                      r'Package rerunfilecheck)')
UNDEF_REF_RE = re.compile(r"LaTeX Warning: Reference `([^']+)' on page "
                          r"(\S+) undefined")
UNDEF_CITE_RE = re.compile(r"(?:LaTeX|Package natbib) Warning: Citation "
                           r"`([^']+)' on page (\S+) undefined")
MISSING_PKG_RE = re.compile(r"! LaTeX Error: File `([^']+\.sty)' not found")
MISSING_CLS_RE = re.compile(r"! LaTeX Error: File `([^']+\.cls)' not found")
MISSING_FILE_RE = re.compile(r"No file ([^\s.]+\.(?:tex|bib|bst|bbl|pdf|png|"
                             r"jpg|jpeg|eps))")


def run_cmd(cmd, cwd, env, timeout=180):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return {"cmd": " ".join(cmd), "exit": p.returncode,
                "seconds": round(time.time() - t0, 1),
                "stdout": p.stdout or "", "stderr": p.stderr or ""}
    except subprocess.TimeoutExpired:
        return {"cmd": " ".join(cmd), "exit": -1,
                "seconds": timeout, "stdout": "", "stderr": "TIMEOUT"}
    except OSError as e:
        return {"cmd": " ".join(cmd), "exit": -2,
                "seconds": 0, "stdout": "", "stderr": str(e)}


class FileStack:
    """跟踪 TeX 日志中的文件开闭括号，估算每条消息所在的源文件。
    非文件括号也入栈占位，保证配平，不被正文中的括号弹空。"""
    def __init__(self):
        self.stack = []

    def feed(self, line):
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "(":
                m = re.match(r'\(([^\s()]+)', line[i:])
                if m and re.search(r'\.(tex|sty|cls|bib|def|clo|fd|cfg)$',
                                   m.group(1)):
                    self.stack.append(("file", m.group(1)))
                    i += len(m.group(0))
                    continue
                self.stack.append(("other", None))
            elif ch == ")" and self.stack:
                self.stack.pop()
            i += 1

    def current(self):
        for kind, name in reversed(self.stack):
            if kind == "file":
                return name
        return None


def parse_log(text, taxonomy):
    errors, warnings = [], []
    undefined_refs, undefined_cites = {}, {}
    packages, overfull = [], 0
    pdf_info = None
    stack = FileStack()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stack.feed(line)
        m = PKG_RE.match(line)
        if m:
            packages.append({"name": m.group(1), "version": m.group(2).strip()})
        m = OUTPDF_RE.search(line)
        if m:
            pdf_info = {"file": m.group(1), "pages": int(m.group(2)),
                        "bytes": int(m.group(3))}
        if "Overfull \\hbox" in line or "Overfull \\vbox" in line:
            overfull += 1
        m = UNDEF_REF_RE.search(line)
        if m:
            undefined_refs[m.group(1)] = m.group(2)
        m = UNDEF_CITE_RE.search(line)
        if m:
            undefined_cites[m.group(1)] = m.group(2)
        em = ERR_LINE_RE.match(line)
        if em and re.match(r'! (Emergency stop| ==> Fatal|'
                           r'End of file on the terminal)', line):
            # 终止行是前面真实错误的后果，不单列为错误
            i += 1
            continue
        if em:
            ctx = [line]
            lineno, linetext = None, ""
            j = i + 1
            while j < len(lines) and j <= i + 6:
                ctx.append(lines[j])
                lm = LINE_NO_RE.match(lines[j])
                if lm:
                    lineno, linetext = int(lm.group(1)), lm.group(2)[:80]
                    break
                j += 1
            cls = classify("\n".join(ctx), taxonomy)
            err = {"class": cls["id"], "message": em.group(1)[:200],
                   "file": stack.current(), "line": lineno,
                   "line_text": linetext, "guide": cls["guide"]}
            mp = MISSING_PKG_RE.match(line) or MISSING_CLS_RE.match(line)
            if mp:
                err["missing"] = mp.group(1)
            mf = MISSING_FILE_RE.search("\n".join(ctx))
            if mf:
                err["missing"] = mf.group(1)
            errors.append(err)
            i = j
        else:
            for c in taxonomy["classes"]:
                if c["id"] in ("undefined_reference", "undefined_citation",
                               "rerun_needed", "generic_error", "missing_package",
                               "missing_class", "missing_file"):
                    continue
                if re.search(c["pattern"], line):
                    warnings.append({"class": c["id"],
                                     "file": stack.current(),
                                     "line": i + 1,
                                     "text": line.strip()[:200]})
                    break
        i += 1
    return {"errors": errors, "warnings": warnings,
            "undefined_refs": sorted(undefined_refs),
            "undefined_citations": sorted(undefined_cites),
            "packages": packages, "overfull_boxes": overfull,
            "pdf": pdf_info, "need_rerun": bool(RERUN_RE.search(text))}


def classify(ctx, taxonomy):
    for c in taxonomy["classes"]:
        if c["id"] in ("undefined_reference", "undefined_citation",
                       "rerun_needed", "overfull_box", "generic_error"):
            continue
        if re.search(c["pattern"], ctx):
            return c
    return taxonomy["classes"][-1]


def engine_version(engine, env):
    r = run_cmd([engine, "--version"], cwd=None, env=env, timeout=30)
    first = (r["stdout"].splitlines() or ["unknown"])[0]
    return first.strip()


# ---------------- 远程编译后端（无本地 TeX 时的诚实后备） ----------------
# 使用 texlive.net 公共 latexcgi 服务（learnlatex.org 官方后端，TeX Live）。
# 服务端自动完成多轮编译与 bibtex/biber；return=log 始终返回完整日志，
# return=pdf 返回 PDF。引擎版本从日志首行提取（真实来源，写入清单）。

def http_post_multipart(url, fields, timeout=300):
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields:
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n"
                 % (boundary, k)).encode("utf-8")
        body += v.encode("utf-8") if isinstance(v, str) else v
        body += b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"User-Agent": "latex-guardian/1.0",
                 "Content-Type": "multipart/form-data; boundary=%s" % boundary})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        print("FATAL: 远程编译服务不可达: %s" % e)
        sys.exit(2)


def collect_project_files(root, main_rel, build_dirname):
    files = []
    for dirpath, _d, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel.split("/")[0] == build_dirname:
                continue
            if os.path.splitext(name)[1].lower() in (
                    ".tex", ".bib", ".bst", ".cls", ".sty", ".clo", ".def",
                    ".pdf", ".png", ".jpg", ".jpeg", ".eps"):
                files.append(rel)
    return files


def remote_compile(root, main_rel, engine, url, ret, build_dirname):
    """向 latexcgi 提交整个工程，返回 (status, body, seconds)。

    主文件以真实文件名提交；document.tex 为包装器，先切 \\nonstopmode
    再 \\input 主文件——服务端以 batchmode 运行会在首个错误处停下，
    包装器保证一次运行暴露全部错误，且行号仍指向真实源文件。
    """
    fields = [("engine", engine), ("return", ret)]
    for rel in collect_project_files(root, main_rel, build_dirname):
        with open(os.path.join(root, rel), "rb") as f:
            content = f.read()
        fields.append(("filename[]", rel))
        fields.append(("filecontents[]", content))
    wrapper = ("\\nonstopmode\\errorcontextlines=6\\relax\n"
               "\\input{%s}\n" % main_rel)
    fields.append(("filename[]", "document.tex"))
    fields.append(("filecontents[]", wrapper))
    t0 = time.time()
    status, body = http_post_multipart(url, fields)
    return status, body, round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--main", default=None)
    ap.add_argument("--engine", default=None)
    ap.add_argument("--engine-dir", default=None,
                    help="TeX 二进制目录（prepend 到 PATH）")
    ap.add_argument("--backend", choices=["auto", "local", "remote"],
                    default="auto",
                    help="auto：有本地 TeX 用本地，否则用远程公共服务；"
                         "local：只用本地；remote：只用远程")
    ap.add_argument("--remote-url", default=REMOTE_URL_DEFAULT,
                    help="远程 latexcgi 服务地址（texlive.net 公共服务）")
    ap.add_argument("--build-dir", default="build")
    ap.add_argument("--max-passes", type=int, default=5)
    ap.add_argument("--out", default=None)
    ap.add_argument("--taxonomy", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "assets",
        "error_taxonomy.json"))
    args = ap.parse_args()

    root = os.path.abspath(args.project)
    if not os.path.isdir(root):
        print("FATAL: 工程目录不存在: %s" % root)
        sys.exit(2)
    try:
        with open(args.taxonomy, encoding="utf-8") as f:
            taxonomy = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print("FATAL: 无法读取错误分类表: %s" % e)
        sys.exit(2)

    env = dict(os.environ)
    if args.engine_dir:
        env["PATH"] = os.path.abspath(args.engine_dir) + os.pathsep \
            + env.get("PATH", "")

    # 主文件与引擎
    main_rel = args.main
    if not main_rel:
        proj = os.path.join(os.path.dirname(os.path.abspath(args.out or "x")),
                            "project.json")
        cand = []
        for name in sorted(os.listdir(root)):
            if name.endswith(".tex"):
                text = open(os.path.join(root, name), encoding="utf-8",
                            errors="replace").read()
                if "\\documentclass" in text:
                    cand.append(name)
        if not cand:
            print("FATAL: 未找到含 \\documentclass 的主文件，请用 --main 指定")
            sys.exit(2)
        main_rel = cand[0]
    main_path = os.path.join(root, main_rel)
    if not os.path.isfile(main_path):
        print("FATAL: 主文件不存在: %s" % main_path)
        sys.exit(2)
    main_text = open(main_path, encoding="utf-8", errors="replace").read()
    main_base = os.path.splitext(os.path.basename(main_rel))[0]

    engine = args.engine
    if not engine:
        engine = "xelatex" if re.search(
            r'\\usepackage[^{]*\{(fontspec|ctex|xeCJK|polyglossia)', main_text) \
            else "pdflatex"
    local_ok = bool(shutil.which(engine, path=env["PATH"]))
    if args.backend == "local" and not local_ok:
        print("FATAL: 找不到编译器 %s。请安装 TeX 发行版并用 --engine-dir "
              "指定其 bin 目录（评測环境的 latex-compiler 工具一般已在 PATH）"
              % engine)
        sys.exit(2)
    backend = "local" if (local_ok and args.backend in ("auto", "local")) \
        else "remote"
    if backend == "remote":
        print("NOTE: 本地无 %s，使用远程公共服务 %s（版本以日志为准，"
              "清单如实标注 backend=remote）" % (engine, args.remote_url))

    build = os.path.join(root, args.build_dir)
    os.makedirs(build, exist_ok=True)

    bib_mode = ("biber" if "\\addbibresource" in main_text else
                "bibtex" if "\\bibliography" in main_text else
                "manual" if "\\begin{thebibliography}" in main_text else "none")

    passes = []
    final_log = ""
    converged = False
    remote_pdf_path = None
    if backend == "remote":
        status, log_bytes, secs = remote_compile(
            root, main_rel, engine, args.remote_url, "log", args.build_dir)
        final_log = log_bytes.decode("utf-8", "replace")
        with open(os.path.join(build, main_base + ".log"), "w",
                  encoding="utf-8") as f:
            f.write(final_log)
        passes.append({"n": 1,
                       "cmd": "latexcgi POST engine=%s return=log"
                              "（服务端自动多轮+bibtex/biber）" % engine,
                       "exit": 0 if status == 200 else 1, "seconds": secs,
                       "backend": "remote", "url": args.remote_url})
        rep = parse_log(final_log, taxonomy)
        if not rep["errors"]:
            status2, pdf_bytes, secs2 = remote_compile(
                root, main_rel, engine, args.remote_url, "pdf",
                args.build_dir)
            passes.append({"n": 2, "cmd": "latexcgi POST return=pdf",
                           "exit": 0 if pdf_bytes[:5] == b"%PDF-" else 1,
                           "seconds": secs2, "backend": "remote"})
            if pdf_bytes[:5] == b"%PDF-":
                remote_pdf_path = os.path.join(build, main_base + ".pdf")
                with open(remote_pdf_path, "wb") as f:
                    f.write(pdf_bytes)
        converged = not rep["need_rerun"] and not rep["errors"]
        engver = (final_log.splitlines() or ["unknown"])[0].strip()
    else:
        engver = None
    for n in range(1, args.max_passes + 1):
        if backend == "remote":
            break
        r = run_cmd([engine, "-interaction=nonstopmode",
                     "-file-line-error",
                     "-output-directory", args.build_dir, main_rel],
                    cwd=root, env=env)
        passes.append({"n": n, "cmd": r["cmd"], "exit": r["exit"],
                       "seconds": r["seconds"]})
        log_path = os.path.join(build, main_base + ".log")
        if os.path.isfile(log_path):
            final_log = open(log_path, encoding="utf-8",
                             errors="replace").read()
        if r["exit"] == -1:
            print("FATAL: 编译超时（%ds）" % r["seconds"])
            break
        if bib_mode == "bibtex" and n == 1:
            rb = run_cmd(["bibtex", main_base], cwd=build, env=env)
            passes.append({"n": n, "cmd": "bibtex " + main_base,
                           "exit": rb["exit"], "seconds": rb["seconds"],
                           "note": (rb["stdout"] or "")[-400:]})
        elif bib_mode == "biber" and n == 1:
            rb = run_cmd(["biber", main_base], cwd=build, env=env)
            passes.append({"n": n, "cmd": "biber " + main_base,
                           "exit": rb["exit"], "seconds": rb["seconds"],
                           "note": (rb["stdout"] or "")[-400:]})
        rep = parse_log(final_log, taxonomy)
        if not rep["need_rerun"] and n >= (3 if bib_mode == "bibtex" else 2):
            converged = True
            break
    rep = parse_log(final_log, taxonomy)
    if rep["need_rerun"] and not converged:
        rep["warnings"].append({"class": "rerun_needed",
                                "text": "达到最大轮次仍未收敛"})
    if backend == "remote" and remote_pdf_path:
        # 服务端输出名为 document.pdf；本地已存为 <主文件名>.pdf，修正引用
        if rep["pdf"]:
            rep["pdf"]["file"] = os.path.basename(remote_pdf_path)
        else:
            rep["pdf"] = {"file": os.path.basename(remote_pdf_path),
                          "pages": None, "bytes": None}

    ok = not rep["errors"] and not rep["undefined_refs"] \
        and not rep["undefined_citations"] and rep["pdf"] is not None
    report = {"project": root, "main": main_rel, "engine": engine,
              "backend": backend,
              "bib_mode": bib_mode, "passes": passes, "converged": converged,
              **rep}
    manifest = {
        "engine": engine,
        "backend": backend,
        "remote_service": args.remote_url if backend == "remote" else None,
        "engine_version": engver if backend == "remote"
        else engine_version(engine, env),
        "commands": [p["cmd"] for p in passes],
        "passes_total": len(passes),
        "bib_mode": bib_mode,
        "packages": rep["packages"],
        "pdf": rep["pdf"],
        "note": "按以上引擎版本与宏包版本、相同命令序列与轮次可复现构建；"
                "字体依赖见日志，fontspec/ctex 工程请使用相同引擎。"}
    outdir = os.path.dirname(os.path.abspath(args.out)) if args.out else build
    os.makedirs(outdir, exist_ok=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    with open(os.path.join(outdir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print("build: passes=%d converged=%s pdf=%s"
          % (len(passes), converged,
             "%s(%d页)" % (rep["pdf"]["file"], rep["pdf"]["pages"])
             if rep["pdf"] else "无"))
    print("errors=%d warnings=%d undefined_refs=%d undefined_cites=%d "
          "overfull=%d" % (len(rep["errors"]), len(rep["warnings"]),
                           len(rep["undefined_refs"]),
                           len(rep["undefined_citations"]),
                           rep["overfull_boxes"]))
    for e in rep["errors"][:15]:
        print("ERROR [%s] %s:%s %s" % (e["class"], e["file"] or "?",
                                       e["line"] or "?", e["message"][:100]))
        if e.get("missing"):
            print("  缺: %s" % e["missing"])
        print("  指引: %s" % e["guide"][:100])
    for u in rep["undefined_refs"][:10]:
        print("UNDEF REF:", u)
    for u in rep["undefined_citations"][:10]:
        print("UNDEF CITE:", u)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
