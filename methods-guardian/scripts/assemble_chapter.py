#!/usr/bin/env python3
# assemble_chapter.py — 组装方法与实验章节成稿（确定性脚本，纯标准库）
#
# 输入：draft.json + prose.md（Agent 写的章节正文）+ inventory.json
# 输出（写入 --outdir）：
#   chapter.md   正文 + 附表A 参数溯源表 + 附录B 复现清单 + 附录C 待作者确认
#   result.json  结构化结果（case_id、状态、统计、来源、不确定性）
# Agent 只写正文散文；溯源表、复现清单、缺口清单全部由脚本从台账生成，
# 保证表格数值与材料一致、每条可回溯。
import argparse, json, os, sys

ELEMENT_NAMES = {"steps": "方法步骤", "setup": "实验设置", "params": "参数",
                 "data": "数据集与材料", "baselines": "对照实验",
                 "repro": "可复现性与限制"}


def load_json(path, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print("FATAL: 无法读取 %s: %s" % (label, e))
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--prose", required=True)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--check", default=None, help="check_report.json（final 阶段）")
    ap.add_argument("--case", default=None, help="case.json（取 case_id）")
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    draft = load_json(args.draft, "draft.json")
    inv = load_json(args.inventory, "inventory.json")
    try:
        with open(args.prose, encoding="utf-8") as f:
            prose = f.read()
    except OSError as e:
        print("FATAL: 无法读取 prose: %s" % e)
        sys.exit(2)
    check = load_json(args.check, "check_report.json") if args.check else None
    case_id = "unknown"
    if args.case:
        case = load_json(args.case, "case.json")
        case_id = case.get("case_id") or case.get("id") or "unknown"

    os.makedirs(args.outdir, exist_ok=True)
    title = (draft.get("meta") or {}).get("title") or "方法与实验"
    registry = {e["id"]: e for e in inv.get("registry", [])}
    claims = draft.get("claims", [])
    gaps = draft.get("gaps", [])

    # ---- 附表 A：参数溯源表（数值全部来自已验证 claim / 台账）----
    rows = []
    for c in claims:
        rid = c.get("registry_id")
        ent = registry.get(rid) if rid else None
        if ent:
            src = "%s:%d" % (ent["source_file"], ent["line"])
            name = ent["key"] or c.get("name") or c["id"]
            unit = ent["unit"] or c.get("unit", "")
        else:
            src = c.get("source_file", "")
            name = c.get("name") or c["id"]
            unit = c.get("unit", "")
        rows.append("| %s | %s | %s | %s | %s |" % (
            name, c.get("number", ""), unit, src, c["id"]))
    table = ["", "## 附表 A 参数溯源表", "",
             "正文中每个数值均可经 claim 锚点回溯到原始材料；本表由脚本生成，未手工填写。", "",
             "| 参数 | 取值 | 单位 | 来源（文件:行） | 正文锚点 |",
             "|---|---|---|---|---|"] + rows + [""]

    # ---- 附录 B：复现清单（版本/种子来自台账；缺失项显式列出）----
    repro = ["", "## 附录 B 复现清单", "",
             "以下版本与种子信息由脚本从材料中提取；未在材料中出现的项标注“材料未提供”。", ""]
    versions = inv.get("versions", [])
    if versions:
        repro.append("### 软件与环境版本")
        repro.append("")
        for v in versions:
            repro.append("- %s %s（%s:%d）" % (v["software"], v["version"],
                                               v["source_file"], v["line"]))
        repro.append("")
    else:
        repro += ["- 软件与环境版本：材料未提供（见附录 C）。", ""]
    seeds = inv.get("seeds", [])
    if seeds:
        repro.append("### 随机种子")
        repro.append("")
        for s in seeds:
            repro.append("- seed = %s（%s:%d）" % (s["value"],
                                                  s["source_file"], s["line"]))
        repro.append("")
    datasets = inv.get("datasets", [])
    if datasets:
        repro.append("### 数据文件")
        repro.append("")
        for d in datasets:
            repro.append("- %s：%d 行，列：%s" % (
                d["file"], d["rows"], ", ".join(d["columns"][:12])))
        repro.append("")

    # ---- 附录 C：待作者确认 ----
    repro.append("")
    appc = ["", "## 附录 C 待作者确认", ""]
    if gaps:
        appc += ["| 编号 | 要素 | 需确认的问题 |", "|---|---|---|"]
        for g in gaps:
            appc.append("| %s | %s | %s |" % (
                g.get("id", ""), ELEMENT_NAMES.get(g.get("element"), g.get("element", "")),
                (g.get("question") or "").replace("|", "/")))
        appc.append("")
    else:
        appc += ["无。", ""]

    chapter = "\n".join(
        ["<!-- 由 methods-guardian 组装：正文为作者/Agent 撰写，",
          "     附表与附录由脚本从参数台账生成，未手工填写数值。 -->", "",
          "# " + title, "", prose.rstrip(), ""]
        + table + repro + appc) + "\n"
    chapter_path = os.path.join(args.outdir, "chapter.md")
    with open(chapter_path, "w", encoding="utf-8") as f:
        f.write(chapter)

    gaps_unresolved = [g.get("id") for g in gaps]
    status = "partial" if gaps_unresolved else "complete"
    result = {
        "case_id": case_id,
        "status": status,
        "deliverables": {"chapter": chapter_path,
                         "prose": os.path.abspath(args.prose),
                         "draft": os.path.abspath(args.draft),
                         "inventory": os.path.abspath(args.inventory)},
        "stats": (check or {}).get("stats", {}),
        "check_status": (check or {}).get("status", "not_run"),
        "sources": [f["path"] for f in inv.get("files", [])
                    if f.get("kind") != "skipped"],
        "uncertainty": {
            "gaps_pending_author": gaps_unresolved,
            "conflicts": [c["id"] for c in inv.get("conflicts", [])],
            "note": "附录 C 列出全部待确认项；未确认前本章视为 partial。"},
        "change_records": (draft.get("meta") or {}).get("change_records", []),
        "limitations": "章节数值仅来源于所给材料；材料未覆盖的信息以缺口标注，未作推测补写。"}
    result_path = os.path.join(args.outdir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("chapter -> %s" % chapter_path)
    print("result  -> %s (status=%s, gaps=%d)" % (result_path, status,
                                                  len(gaps_unresolved)))


if __name__ == "__main__":
    main()
