#!/usr/bin/env python3
# check_chapter.py — 章节草稿与成稿的机器核验（确定性脚本，纯标准库）
#
# 两个阶段：
#   --stage draft  核验 draft.json：
#     1) 结构合法（sections/claims/gaps/unused_registry/conflict_resolution/
#        element_coverage）；
#     2) 每条 claim 的 evidence 必须逐字出现于其 source_file（允许空白折叠匹配），
#        claim.number 必须能在 evidence 中找到同值数字（防编造）；
#     3) 若带 registry_id，台账值与 claim 值必须一致（防写错）；
#     4) 覆盖率：tier A 台账每条必须被 claim 引用或列入 unused_registry（附理由），
#        分母来自 scan_materials 的台账，不接受自报；
#     5) 台账中的每个冲突必须被 conflict_resolution 裁定或以 gap 上报；
#     6) 六类要素（steps/setup/params/data/baselines/repro）每类必须
#        "present" 或关联一个 gap（材料不足时报缺口，而不是略过）。
#   --stage final  在 draft 核验基础上追加（需 --prose）：
#     7) 每条 claim 的 chapter_span 必须逐字出现于正文（位置绑定）；
#     8) 正文中的每个数字 token 必须落在某条已验证 claim 的 chapter_span 内，
#        否则报“无来源数值”（防为行文顺畅补数）；
#     9) 每个 gap 的 id 必须以【待作者确认 …】形式出现在正文。
# 退出码：0 通过；1 有错误；2 输入损坏等致命问题（脚本自身不崩）。
import argparse, json, os, re, sys

ELEMENTS = ["steps", "setup", "params", "data", "baselines", "repro"]
NUMTOKEN_RE = re.compile(r'(?<![\w.)])(\d+(?:\.\d+)?)(?![\w.@])')
CITATION_RE = re.compile(r'\[[\d,，\-–—\s]+\]')
HEADING_RE = re.compile(r'^\s{0,3}#{1,6}\s*[\d.]*|^\s*\d+(?:\.\d+)*[.、]\s*')


def collapse(s):
    return re.sub(r'\s+', ' ', s).strip()


def load_json(path, errors, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        errors.append("FATAL: 文件不存在: %s" % path)
    except json.JSONDecodeError as e:
        errors.append("FATAL: %s 不是合法 JSON: %s" % (label, e))
    except OSError as e:
        errors.append("FATAL: 无法读取 %s: %s" % (label, e))
    return None


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def number_in_text(number, text):
    """claim 的数字是否以同值形式出现在文本中（容差浮点比较 + 字面匹配）。"""
    num = str(number).strip()
    if num in text:
        return True
    try:
        target = float(num)
    except ValueError:
        return False
    for m in re.finditer(r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?', text):
        try:
            if abs(float(m.group(0)) - target) <= 1e-9 * max(1.0, abs(target)):
                return True
        except ValueError:
            continue
    return False


def find_span(span, text):
    """返回 (start, end, mode)；支持逐字与空白折叠两种匹配。"""
    i = text.find(span)
    if i >= 0:
        return i, i + len(span), "exact"
    # 空白折叠匹配：在折叠后的文本里定位，再映射回原坐标区间（近似）
    c_text = collapse(text)
    c_span = collapse(span)
    j = c_text.find(c_span)
    if j < 0:
        return -1, -1, "missing"
    # 回映射：从原文找到包含折叠起点字符的位置
    count, start = -1, -1
    for idx, ch in enumerate(text):
        if not ch.isspace():
            count += 1
            if count == j:
                start = idx
                break
    if start < 0:
        return -1, -1, "missing"
    # 终点：覆盖折叠串中最后一个非空白字符
    last_nonspace = j + len(c_span) - 1
    count, end = -1, len(text)
    for idx, ch in enumerate(text):
        if not ch.isspace():
            count += 1
            if count == last_nonspace:
                end = idx + 1
                break
    return start, end, "collapsed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials", required=True)
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--stage", choices=["draft", "final"], required=True)
    ap.add_argument("--prose", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    errors, warnings, notes = [], [], []
    inv = load_json(args.inventory, errors, "inventory.json")
    draft = load_json(args.draft, errors, "draft.json")
    if inv is None or draft is None:
        report = {"status": "fatal", "errors": errors}
        print(json.dumps(report, ensure_ascii=False, indent=1))
        sys.exit(2)

    root = os.path.abspath(args.materials)
    registry = {e["id"]: e for e in inv.get("registry", [])}
    conflicts = {c["id"]: c for c in inv.get("conflicts", [])}

    # ---- 结构核验 ----
    sections = draft.get("sections")
    claims = draft.get("claims")
    gaps = draft.get("gaps", [])
    unused = draft.get("unused_registry", [])
    cres = draft.get("conflict_resolution", [])
    ecov = draft.get("element_coverage", {})
    if not isinstance(sections, list) or not sections:
        errors.append("draft.sections 缺失或为空")
    if not isinstance(claims, list) or not claims:
        errors.append("draft.claims 缺失或为空：章节中的每个数字都必须有 claim")
    claims = claims if isinstance(claims, list) else []
    gaps = gaps if isinstance(gaps, list) else []
    unused = unused if isinstance(unused, list) else []
    cres = cres if isinstance(cres, list) else []

    claim_ids, gap_ids = set(), set()
    file_cache = {}

    def get_file(rel):
        if rel not in file_cache:
            p = os.path.join(root, rel)
            file_cache[rel] = read_text(p)
        return file_cache[rel]

    # ---- 逐条 claim 核验（防编造：证据逐字 + 数值一致）----
    validated = []
    for c in claims:
        cid = c.get("id", "?")
        if cid in claim_ids:
            errors.append("claim %s: id 重复" % cid)
            continue
        claim_ids.add(cid)
        ok = True
        for field in ("number", "evidence", "source_file", "chapter_span"):
            if not c.get(field):
                errors.append("claim %s: 缺少字段 %s" % (cid, field))
                ok = False
        if not ok:
            continue
        text = get_file(c["source_file"])
        if text is None:
            errors.append("claim %s: source_file 不可读: %s"
                          % (cid, c["source_file"]))
            continue
        s, e_, mode = find_span(c["evidence"], text)
        if mode == "missing":
            errors.append("claim %s: evidence 未逐字出现于 %s（不允许转述或编造）"
                          % (cid, c["source_file"]))
            continue
        if not number_in_text(c["number"], c["evidence"]):
            errors.append("claim %s: 数字 %s 不在其 evidence 中（防补数）"
                          % (cid, c["number"]))
            continue
        rid = c.get("registry_id")
        if rid:
            ent = registry.get(rid)
            if ent is None:
                errors.append("claim %s: registry_id %s 不存在" % (cid, rid))
                continue
            if not number_in_text(c["number"], ent["value"]):
                errors.append(
                    "claim %s: 取值 %s 与台账 %s（%s:%d, 值=%s）不一致"
                    % (cid, c["number"], rid, ent["source_file"],
                       ent["line"], ent["value"]))
                continue
        validated.append({"id": cid, "number": str(c["number"]),
                          "span": c["chapter_span"],
                          "registry_id": rid, "evidence_mode": mode,
                          "source_file": c["source_file"]})
        if mode == "collapsed":
            notes.append("claim %s: evidence 以空白折叠模式匹配（跨行）" % cid)

    # ---- 覆盖率：tier A 台账逐条交代（外部分母）----
    used_rids = {c.get("registry_id") for c in claims if c.get("registry_id")}
    unused_rids = set()
    for u in unused:
        rid, reason = u.get("registry_id"), (u.get("reason") or "").strip()
        if rid not in registry:
            errors.append("unused_registry: %s 不存在" % rid)
        elif not reason:
            errors.append("unused_registry %s: 必须附理由" % rid)
        else:
            unused_rids.add(rid)
    tier_a = [e for e in registry.values() if e["tier"] == "A"]
    uncovered = [e for e in tier_a
                 if e["id"] not in used_rids and e["id"] not in unused_rids]
    for e in uncovered:
        errors.append("台账 %s（%s=%s, %s:%d）未交代：引用或列入 unused_registry"
                      % (e["id"], e["key"], e["value"],
                         e["source_file"], e["line"]))

    # ---- 冲突裁定 ----
    resolved, escalated = set(), set()
    for r in cres:
        cid = r.get("conflict_id")
        if cid not in conflicts:
            errors.append("conflict_resolution: %s 不存在" % cid)
            continue
        choice = (r.get("choice") or "").strip()
        if choice == "gap":
            escalated.add(cid)
        elif choice and any(o["value"] == choice
                            for o in conflicts[cid]["options"]):
            resolved.add(cid)
        else:
            errors.append("conflict_resolution %s: choice 必须是台账中的取值"
                          "之一或 \"gap\"" % cid)
    for g in gaps:
        if g.get("conflict_id") in conflicts:
            escalated.add(g["conflict_id"])
    for cid, c in sorted(conflicts.items()):
        if cid not in resolved and cid not in escalated:
            errors.append("冲突 %s（%s: %s）未裁定：选择取值或以 gap 上报"
                          % (cid, c["key"],
                             "/".join(o["value"] for o in c["options"])))

    # ---- 六类要素覆盖 ----
    for g in gaps:
        gid = g.get("id", "?")
        if gid in gap_ids:
            errors.append("gap %s: id 重复" % gid)
        gap_ids.add(gid)
        if g.get("element") not in ELEMENTS:
            errors.append("gap %s: element 必须是 %s 之一"
                          % (gid, "/".join(ELEMENTS)))
        if not (g.get("question") or "").strip():
            errors.append("gap %s: 必须写明需作者确认的问题" % gid)
    for el in ELEMENTS:
        v = ecov.get(el)
        if isinstance(v, str) and v == "present":
            continue
        if isinstance(v, dict) and v.get("status") == "gap" \
                and v.get("gap_id") in gap_ids:
            continue
        errors.append("element_coverage.%s: 必须为 \"present\" 或 "
                      "{\"status\":\"gap\",\"gap_id\":\"<已登记的gap id>\"}" % el)

    # ---- final 阶段：正文绑定与数值审计 ----
    prose_stats = {"numbers_in_prose": 0, "numbers_covered": 0}
    if args.stage == "final":
        if not args.prose:
            errors.append("FATAL: --stage final 需要 --prose")
        else:
            prose = read_text(args.prose)
            if prose is None:
                errors.append("FATAL: prose 不可读: %s" % args.prose)
            else:
                covered = []
                for vc in validated:
                    # 同一 claim 的 span 在正文中多次出现时，全部计入覆盖区间
                    found = False
                    start = 0
                    while True:
                        idx = prose.find(vc["span"], start)
                        if idx < 0:
                            break
                        found = True
                        covered.append((idx, idx + len(vc["span"])))
                        start = idx + 1
                    if not found:
                        s, e_, mode = find_span(vc["span"], prose)
                        if mode == "missing":
                            errors.append("claim %s: chapter_span 未出现于正文"
                                          "（声明与正文必须绑定）" % vc["id"])
                        else:
                            covered.append((s, e_))
                # 数值审计：屏蔽引用标号与章节号
                scrub = CITATION_RE.sub("", prose)
                offset = 0
                scrub_lines = []
                for ln in scrub.splitlines(keepends=True):
                    m = HEADING_RE.match(ln)
                    if m:
                        ln = " " * m.end() + ln[m.end():]
                    scrub_lines.append((offset, ln))
                    offset += len(ln)
                for base, ln in scrub_lines:
                    for m in NUMTOKEN_RE.finditer(ln):
                        pos = base + m.start()
                        prose_stats["numbers_in_prose"] += 1
                        if any(s <= pos < e_ for s, e_ in covered):
                            prose_stats["numbers_covered"] += 1
                        else:
                            ctx = prose[max(0, pos - 30):pos + 30]
                            ctx = ctx.replace("\n", " ")
                            errors.append("正文数字 %s 无来源（…%s…）："
                                          "补写 claim 或删除该数字"
                                          % (m.group(1), ctx))
                # gap 标记
                for g in gaps:
                    if g.get("id") and g["id"] not in prose:
                        errors.append("gap %s 未在正文中以【待作者确认 %s …】"
                                      "标注" % (g["id"], g["id"]))

    stats = {
        "claims_total": len(claims), "claims_validated": len(validated),
        "registry_total": len(registry), "tier_A": len(tier_a),
        "tier_A_covered": len(tier_a) - len(uncovered),
        "conflicts": len(conflicts),
        "conflicts_resolved": len(resolved) + len(escalated),
        "gaps": len(gap_ids), **prose_stats}
    status = "pass" if not errors else "fail"
    report = {"status": status, "stage": args.stage, "errors": errors,
              "warnings": warnings, "notes": notes, "stats": stats}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print("check [%s] -> %s | errors=%d warnings=%d | %s"
          % (args.stage, status, len(errors), len(warnings),
             json.dumps(stats, ensure_ascii=False)))
    for e in errors[:20]:
        print("ERROR:", e)
    sys.exit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
