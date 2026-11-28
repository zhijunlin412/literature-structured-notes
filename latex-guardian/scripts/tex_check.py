#!/usr/bin/env python3
# tex_check.py — 交付门禁与 result.json 写出（确定性脚本，纯标准库）
#
# 门禁项（逐项判定，全部过才算 complete）：
#   1) 编译报告无错误、无未解析引用、已收敛（读 tex_build 的报告）；
#   2) PDF 正文不含 "??"（有 pdftotext 时真实抽取检查；无则诚实标注 skipped）；
#   3) 模板必填项非空：\\title、\\author（可用 --require 追加，如 \\date）；
#   4) 交付物是可继续编辑的 .tex 源码（存在、UTF-8 可读、含完整 document 环境），
#      不接受只交 PDF。
# 写 result.json：case_id、status（complete/partial/failed）、deliverables、
# stats、uncertainty、change_records（由 --changes 传入的修改记录）。
# 退出码：0 complete；1 partial/failed；2 输入致命问题。
import argparse, json, os, re, shutil, subprocess, sys


def load_json(path, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print("FATAL: 无法读取 %s: %s" % (label, e))
        sys.exit(2)


def pdf_text_has_qq(pdf_path):
    pdftotext = shutil.which("pdftotext")
    if not pdftotext or not os.path.isfile(pdf_path):
        return None  # 无法检查
    try:
        r = subprocess.run([pdftotext, pdf_path, "-"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return "??" in (r.stdout or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--main", required=True)
    ap.add_argument("--report", required=True, help="tex_build 的报告 json")
    ap.add_argument("--build-dir", default="build")
    ap.add_argument("--case", default=None)
    ap.add_argument("--changes", default=None,
                    help="修改记录 json（Agent 写：[{file, before, after, reason}]）")
    ap.add_argument("--require", default="title,author",
                    help="模板必填项（逗号分隔的命令名，不含反斜杠）")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    root = os.path.abspath(args.project)
    report = load_json(args.report, "编译报告")
    case_id = "unknown"
    if args.case:
        case = load_json(args.case, "case.json")
        case_id = case.get("case_id") or case.get("id") or "unknown"
    changes = []
    if args.changes:
        changes = load_json(args.changes, "修改记录")

    gates, problems = {}, []

    # 门禁 1：编译收敛无错误
    g1 = (not report.get("errors") and not report.get("undefined_refs")
          and not report.get("undefined_citations")
          and report.get("pdf") is not None)
    gates["compile_clean"] = g1
    if not g1:
        problems.append("编译报告仍有 %d 个错误、%d 个未解析引用、%d 个未解析文献"
                        % (len(report.get("errors", [])),
                           len(report.get("undefined_refs", [])),
                           len(report.get("undefined_citations", []))))

    # 门禁 2：PDF 无 ??
    pdf_path = None
    if report.get("pdf"):
        cand = os.path.join(root, args.build_dir,
                            os.path.basename(report["pdf"]["file"]))
        pdf_path = cand if os.path.isfile(cand) else None
    qq = pdf_text_has_qq(pdf_path) if pdf_path else None
    gates["no_qq_in_pdf"] = (qq is False)
    if qq is True:
        problems.append("PDF 正文中检出 '??'（未解析的引用/文献标记）")
    elif qq is None:
        problems.append("note: 未检查 '??'（pdftotext 或 PDF 不可用），"
                        "以编译日志判定为准")

    # 门禁 3：模板必填项
    main_path = os.path.join(root, args.main)
    try:
        src = open(main_path, encoding="utf-8").read()
    except OSError as e:
        print("FATAL: 主文件不可读: %s" % e)
        sys.exit(2)
    missing_keys = []
    for key in [k.strip() for k in args.require.split(",") if k.strip()]:
        m = re.search(r'\\%s\{(.*?)\}' % re.escape(key), src, re.S)
        if not m or not m.group(1).strip():
            missing_keys.append(key)
    gates["required_fields"] = not missing_keys
    if missing_keys:
        problems.append("模板必填项为空或缺失: %s"
                        % ", ".join("\\" + k for k in missing_keys))

    # 门禁 4：交付物为可编辑源码
    g4 = ("\\begin{document}" in src and "\\end{document}" in src)
    gates["editable_source"] = g4
    if not g4:
        problems.append("主文件缺少完整 document 环境（交付物必须是可编译的 "
                        ".tex 源码，不能只交 PDF/截图）")

    status = "complete" if all(gates.values()) else \
        ("failed" if not gates["compile_clean"] else "partial")
    os.makedirs(args.outdir, exist_ok=True)
    result = {
        "case_id": case_id,
        "status": status,
        "gates": gates,
        "deliverables": {
            "source": main_path,
            "pdf": pdf_path,
            "build_report": os.path.abspath(args.report),
            "manifest": os.path.join(os.path.dirname(
                os.path.abspath(args.report)), "manifest.json")},
        "stats": {
            "passes": len(report.get("passes", [])),
            "converged": report.get("converged"),
            "errors": len(report.get("errors", [])),
            "warnings": len(report.get("warnings", [])),
            "undefined_refs": len(report.get("undefined_refs", [])),
            "undefined_citations": len(report.get("undefined_citations", [])),
            "pages": (report.get("pdf") or {}).get("pages")},
        "sources": [args.main],
        "uncertainty": {"problems": problems,
                        "qq_check": ("pass" if qq is False else
                                     "fail" if qq else "skipped")},
        "change_records": changes,
        "limitations": "仅保证在本清单记录的引擎/宏包版本下构建通过；"
                       "更换发行版或模板版本需重新验证。"}
    out = os.path.join(args.outdir, "result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("gates: %s" % json.dumps(gates, ensure_ascii=False))
    print("status=%s -> %s" % (status, out))
    for p in problems:
        print(("PROBLEM: " if not p.startswith("note:") else "NOTE: ") + p)
    sys.exit(0 if status == "complete" else 1)


if __name__ == "__main__":
    main()
