#!/usr/bin/env python3
"""材料包加载器（纯标准库）：把组织方提供的 JATS 文本材料包解析成统一的段落索引。

识别的输入文件（在 --input 目录内递归查找）：
  case.json               案例标识与 output_contract
  corpus-manifest.json    两篇论文的 DOI / 作者 / 来源哈希 / 许可证
  material.json           两篇正文段落的汇总索引
  primary-material.json   第一篇论文正文
  secondary-material.json 第二篇论文正文

实际文件结构可能与示例不完全一致，本脚本递归发现"段落状对象"
（含文本字段的 dict），并尽量从字段、祖先键、文件名推断 source_id。
无法识别时输出结构摘要并诚实报错（exit 2），不猜不编。

输出：
  materials_index.json  {"papers": [...], "paragraphs": [...], "warnings": [...]}
  source_units.md       供 Agent 通读的段落清单（按论文/章节分组）

用法：python load_materials.py --input /input --out /app/work/materials
"""
import argparse
import json
import os
import re
import sys

TEXT_KEYS = ("text", "content", "paragraph", "body_text", "body", "value")
ID_KEYS = ("paragraph_id", "pid", "jats_id", "para_id", "id")
SECTION_KEYS = ("section", "section_title", "heading", "section_id")
SOURCE_KEYS = ("source_id", "source", "paper_id", "paper", "doc_id", "document_id")
SKIP_KEYS = {"output_contract", "papers", "references_list"}


def log(m):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(m, flush=True)


def find_files(root):
    """递归查找已知材料文件，返回 {kind: path}。"""
    found = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            low = fn.lower()
            if not low.endswith(".json"):
                continue
            p = os.path.join(dirpath, fn)
            if low == "case.json":
                found.setdefault("case", p)
            elif low == "corpus-manifest.json":
                found.setdefault("manifest", p)
            elif low == "material.json":
                found.setdefault("material", p)
            elif low == "primary-material.json":
                found.setdefault("primary", p)
            elif low == "secondary-material.json":
                found.setdefault("secondary", p)
            elif "material" in low:
                found.setdefault("extra:" + fn, p)
    return found


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def structure_summary(obj, depth=0, max_depth=3):
    """无法识别时输出结构摘要，帮助人工接管。"""
    pad = "  " * depth
    if isinstance(obj, dict):
        lines = [f"{pad}<dict> keys={list(obj.keys())[:12]}"]
        if depth < max_depth:
            for k, v in list(obj.items())[:6]:
                lines.append(f"{pad}  [{k}]")
                lines.extend(structure_summary(v, depth + 2, max_depth))
        return lines
    if isinstance(obj, list):
        lines = [f"{pad}<list> len={len(obj)}"]
        if obj and depth < max_depth:
            lines.extend(structure_summary(obj[0], depth + 1, max_depth))
        return lines
    s = str(obj)
    return [f"{pad}<{type(obj).__name__}> {s[:60]}"]


def norm_source(s):
    if s is None:
        return None
    s = str(s).strip()
    s = re.sub(r"\s+", "_", s)
    return s or None


def parse_manifest(obj, warnings):
    """从 corpus-manifest.json 提取论文元数据列表（容错多种布局）。"""
    papers = []
    candidates = None
    if isinstance(obj, list):
        candidates = obj
    elif isinstance(obj, dict):
        for key in ("papers", "sources", "documents", "corpus", "items"):
            if isinstance(obj.get(key), list):
                candidates = obj[key]
                break
        if candidates is None and ("doi" in obj or "title" in obj):
            candidates = [obj]
    if not candidates:
        warnings.append("corpus-manifest.json 结构未识别，无法提取论文元数据")
        return papers
    for i, p in enumerate(candidates):
        if not isinstance(p, dict):
            continue
        authors = p.get("authors")
        if isinstance(authors, list):
            authors = "; ".join(str(a) if not isinstance(a, dict)
                                else str(a.get("name", a)) for a in authors)
        papers.append({
            "source_id": norm_source(p.get("source_id") or p.get("id")
                                      or p.get("paper_id")) or f"paper{i + 1}",
            "title": p.get("title", "未报告"),
            "authors": authors or "未报告",
            "doi": p.get("doi", "未报告"),
            "license": p.get("license", p.get("licence", "未报告")),
            "hash": p.get("hash", p.get("sha256", "未报告")),
            "file": p.get("file", p.get("filename", "未报告")),
        })
    return papers


def looks_like_paragraph(d):
    if not isinstance(d, dict):
        return False
    if not any(k in d and isinstance(d[k], str) and len(d[k]) > 20 for k in TEXT_KEYS):
        return False
    # 元数据 dict（含 doi/title/authors）不算段落
    if "doi" in d and "title" in d:
        return False
    return True


def extract_paragraphs(obj, default_source, inherited_source=None,
                       inherited_section=None, out=None, warnings=None, path=""):
    """递归发现段落状对象，尽量继承 source/section 上下文。"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        src = inherited_source
        for k in SOURCE_KEYS:
            if k in obj and isinstance(obj[k], str):
                src = norm_source(obj[k])
                break
        sec = inherited_section
        for k in SECTION_KEYS:
            if k in obj and isinstance(obj[k], str):
                sec = obj[k]
                break
        if looks_like_paragraph(obj):
            text = None
            for k in TEXT_KEYS:
                if k in obj and isinstance(obj[k], str) and len(obj[k]) > 20:
                    text = obj[k]
                    break
            pid = None
            for k in ID_KEYS:
                if k in obj and isinstance(obj[k], (str, int)):
                    pid = str(obj[k])
                    break
            out.append({
                "source_id": src or default_source,
                "paragraph_id": pid,
                "section": sec,
                "text": re.sub(r"\s+", " ", text).strip(),
            })
            return out  # 段落内部不再下钻，避免把字段当子段落
        for k, v in obj.items():
            if k in SKIP_KEYS or k in TEXT_KEYS + ID_KEYS:
                continue
            # 顶层以论文为键的布局：{"paper1": {...}, "paper2": {...}}
            child_src = src
            if isinstance(v, (dict, list)) and re.match(r"(?i)^(paper|source|doc)[_\-\s]?\w*$", str(k)):
                child_src = norm_source(k)
            extract_paragraphs(v, default_source, child_src, sec, out, warnings,
                               path + "/" + str(k))
    elif isinstance(obj, list):
        for item in obj:
            extract_paragraphs(item, default_source, inherited_source,
                               inherited_section, out, warnings, path + "[]")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="输入目录（如 /input）")
    ap.add_argument("--out", required=True, help="输出目录（如 /app/work/materials）")
    args = ap.parse_args()
    warnings = []

    found = find_files(args.input)
    log("发现文件: " + (", ".join(f"{k}={os.path.basename(v)}" for k, v in found.items()) or "无"))
    if "manifest" not in found and "material" not in found and "primary" not in found:
        log("FATAL: 未找到 corpus-manifest.json / material.json / *-material.json")
        return 2

    papers, paragraphs = [], []

    # 1) 论文元数据
    if "manifest" in found:
        papers = parse_manifest(load_json(found["manifest"]), warnings)
        log(f"manifest 解析出 {len(papers)} 篇论文: " +
            "; ".join(f"{p['source_id']} doi={p['doi']}" for p in papers))

    # 2) case.json 提示：根 DOI/title/authors 属于第一篇，不得套到第二篇
    if "case" in found:
        case = load_json(found["case"])
        root_meta = [k for k in ("doi", "title", "authors") if k in case]
        if root_meta:
            warnings.append(
                f"case.json 根级字段 {root_meta} 仅属于第一篇论文（primary），"
                "不得赋给第二篇")
        if papers and "case_id" not in papers[0]:
            papers[0]["case_id"] = case.get("case_id", "未报告")

    default_ids = [p["source_id"] for p in papers] or ["paper1", "paper2"]

    # 3) 逐文件抽段落
    def source_for(kind, order):
        if order < len(default_ids):
            return default_ids[order]
        return f"paper{order + 1}"

    file_order = [k for k in ("primary", "secondary", "material") if k in found]
    file_order += [k for k in found if k.startswith("extra:")]
    for order, kind in enumerate(file_order):
        obj = load_json(found[kind])
        fallback = source_for(kind, order) if kind != "material" else None
        before = len(paragraphs)
        extract_paragraphs(obj, fallback, out=paragraphs, warnings=warnings)
        log(f"{os.path.basename(found[kind])}: 提取段落 {len(paragraphs) - before} 条")

    if not paragraphs:
        log("ERROR: 未能从材料文件识别任何段落。结构摘要：")
        for kind in file_order[:1] or ["material"]:
            if kind in found:
                for line in structure_summary(load_json(found[kind])):
                    log(line)
        return 2

    # 4) 清洗：去重、补 id、校验 source
    seen, cleaned = set(), []
    known_sources = {p["source_id"] for p in papers}
    auto = {}
    for para in paragraphs:
        src = para["source_id"]
        if src is None:
            warnings.append("存在无法判定来源论文的段落，已标 source_id=unknown，需人工核查")
            src = "unknown"
        pid = para["paragraph_id"]
        if pid is None:
            n = auto.get(src, 0) + 1
            auto[src] = n
            pid = f"auto-{n:03d}"
            warnings.append(f"{src} 有段落缺少 paragraph_id，已按出现顺序编为 {pid}")
        key = (src, pid)
        if key in seen:
            continue  # material.json 与单篇文件重复收录，只留一条
        seen.add(key)
        para["source_id"], para["paragraph_id"] = src, pid
        cleaned.append(para)
    for src in sorted({p["source_id"] for p in cleaned} - known_sources):
        if not papers:
            papers.append({"source_id": src, "title": "未报告", "authors": "未报告",
                           "doi": "未报告", "license": "未报告", "hash": "未报告",
                           "file": "未报告"})
        elif src != "unknown":
            warnings.append(f"段落来源 {src} 不在 manifest 论文列表中，请核查 source_id 对应关系")

    index = {"papers": papers, "paragraphs": cleaned, "warnings": warnings}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "materials_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    # 5) 供 Agent 通读的 markdown
    lines = ["# 材料段落索引（source_units）", ""]
    for p in papers:
        lines.append(f"## {p['source_id']}: {p['title']}")
        lines.append(f"- DOI: {p['doi']}  | 许可: {p['license']}  | 作者: {p['authors']}")
        lines.append("")
        for para in cleaned:
            if para["source_id"] != p["source_id"]:
                continue
            sec = f" [{para['section']}]" if para.get("section") else ""
            lines.append(f"### {para['paragraph_id']}{sec}")
            lines.append(para["text"])
            lines.append("")
    others = [para for para in cleaned
              if para["source_id"] not in {p["source_id"] for p in papers}]
    if others:
        lines.append("## 来源未判定段落（需人工核查）")
        for para in others:
            lines.append(f"### {para['source_id']} / {para['paragraph_id']}")
            lines.append(para["text"])
            lines.append("")
    with open(os.path.join(args.out, "source_units.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    for w in warnings:
        log("WARN " + w)
    log(f"OK papers={len(papers)} paragraphs={len(cleaned)} warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
