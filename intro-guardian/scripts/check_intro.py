# -*- coding: utf-8 -*-
"""check_intro.py — 引言与相关工作的机器校验（立得住/分得清/说得实/对得上）。

校验项（error 必须修复，warning 需逐条说明）：
1. 转述逐字绑定：每条 claim 的 evidence.quote 必须是被引**那一篇** text 的逐字片段
   ——引错篇、改写过的引文都是 error（位置绑定，不是全库集合比对）
2. 空话检测：background/gap 命中套话且同句无引用 → error
3. 空白推导：gap.status=derived 必须 derived_from ≥1 篇库内文献；
   derived_from 指向不存在的 key → error
4. 贡献核对：anchor 必须存在于底稿；贡献句中的数字必须出现在锚点 text/numbers 中
5. 引用覆盖：库中每篇文献都应被使用（分组或背景引用）；未用 → warning
6. 分组质量：每组 ≥1 篇、有 comparison 比较句；缺 comparison → warning

用法:
  python check_intro.py --draft work/draft.json --fact-draft fact_draft.json \
      --library library.json --phrases assets/boilerplate_phrases.json \
      [--zh-phrasing assets/zh_phrasing.json] --out check_report.json
"""
import argparse, json, re, sys, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def norm(t):
    t = unicodedata.normalize("NFC", t)
    return re.sub(r"\s+", " ", t.replace("−", "-").replace("–", "-")).strip()

NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--fact-draft", required=True)
    ap.add_argument("--library", required=True)
    ap.add_argument("--phrases", required=True)
    ap.add_argument("--zh-phrasing", help="可选：中文语境用词规范（直译腔检测）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    try:
        draft = json.load(open(a.draft, encoding="utf-8-sig"))
    except Exception as ex:
        print(f"FATAL: draft.json 不是合法 JSON: {ex}")
        sys.exit(2)
    fd = json.load(open(a.fact_draft, encoding="utf-8-sig"))
    lib = json.load(open(a.library, encoding="utf-8-sig"))
    phrases = json.load(open(a.phrases, encoding="utf-8"))

    works = {w["key"]: w for w in lib.get("works", [])}
    anchors = {x["id"]: x for x in fd.get("anchors", [])}
    errors, warnings = [], []

    # 1. 转述逐字绑定（位置绑定：必须在被引那一篇里）
    used_keys = set()
    for g in draft.get("related_work", {}).get("groups", []):
        for w in g.get("works", []):
            key = w.get("key")
            used_keys.add(key)
            if key not in works:
                errors.append(f"转述指向不存在的文献 key '{key}'")
                continue
            quote = norm(w.get("evidence", {}).get("quote", ""))
            if not quote:
                errors.append(f"文献 {key} 的转述缺 evidence.quote（转述必须有逐字证据）")
                continue
            if quote not in norm(works[key].get("text", "")):
                errors.append(f"文献 {key} 的 evidence.quote 不是该文献文本的逐字片段（不许凭印象转述、不许张冠李戴）")

    # 2. 空话检测（background + gap 的句子）
    all_phrases = [(p, "zh") for p in phrases["phrases_zh"]] + [(p, "en") for p in phrases["phrases_en"]]
    def boilerplate_hit(sentence):
        for p, _lang in all_phrases:
            if re.search(p, sentence, re.I):
                return p
        return None
    for item in draft.get("background", []):
        used_keys.update(item.get("citations", []))
        hit = boilerplate_hit(item.get("text", ""))
        if hit and not item.get("citations"):
            errors.append(f"背景句命中空话 '{hit}' 且同句无引用：'{item.get('text','')[:50]}…'（换具体脉络或补引用）")
    for g in draft.get("gap", []):
        hit = boilerplate_hit(g.get("statement", ""))
        if hit and not g.get("derived_from"):
            errors.append(f"空白句命中空话 '{hit}' 且无推导来源：'{g.get('statement','')[:50]}…'")

    # 3. 空白推导
    for g in draft.get("gap", []):
        st = g.get("status", "derived")
        src = g.get("derived_from", [])
        if st == "derived" and not src:
            errors.append("存在 status=derived 的空白但 derived_from 为空：空白必须从已引文献缺口推出，否则标 author_judgment")
        for k in src:
            used_keys.add(k)
            if k not in works:
                errors.append(f"空白推导指向不存在的文献 key '{k}'")
        if st not in ("derived", "author_judgment"):
            warnings.append(f"空白 status '{st}' 未知，应为 derived 或 author_judgment")

    # 4. 贡献核对（数字必须能在锚点或显式引用的文献中找到——位置绑定）
    for c in draft.get("contributions", []):
        aid = c.get("anchor")
        allowed = set()
        if aid not in anchors:
            errors.append(f"贡献 '{c.get('statement','')[:40]}…' 的 anchor '{aid}' 在底稿中不存在")
        else:
            anchor_text = anchors[aid].get("text", "")
            allowed = {n["value"] for n in anchors[aid].get("numbers", [])}
            allowed |= set(NUM_RE.findall(anchor_text))
        for k in c.get("citations", []):
            used_keys.add(k)
            if k not in works:
                errors.append(f"贡献引用了不存在的文献 key '{k}'")
            else:
                allowed |= set(NUM_RE.findall(works[k].get("text", "")))
        for num in set(NUM_RE.findall(c.get("statement", ""))):
            if num not in allowed:
                errors.append(f"贡献句数字 {num} 不在锚点 '{aid}' 或其引用文献中：数据必须有出处（底稿锚点或在贡献中显式引用文献）")

    # 5. 引用覆盖（分母 = 库内全部文献）
    for k in works:
        if k not in used_keys:
            warnings.append(f"文献 {k} 未被任何背景/分组/空白引用（确认是遗漏还是确实不需要）")

    # 6. 分组质量
    groups = draft.get("related_work", {}).get("groups", [])
    if not groups:
        errors.append("related_work.groups 为空：相关工作必须按维度分组，不接受逐篇罗列")
    for g in groups:
        if not g.get("works"):
            errors.append(f"分组 '{g.get('dimension','?')}' 没有文献")
        if not (g.get("comparison") or "").strip():
            warnings.append(f"分组 '{g.get('dimension','?')}' 缺 comparison 比较句（同维度取舍/适用条件/局限）")

    # 7. 中文学术语域检测（通用直译腔 + 学科领域词表；warning 级）
    if a.zh_phrasing:
        zp = json.load(open(a.zh_phrasing, encoding="utf-8-sig"))
        all_text = json.dumps([draft.get("background", []), draft.get("related_work", {}),
                               draft.get("gap", []), draft.get("contributions", [])], ensure_ascii=False)
        term_lists = [zp.get("general", {}).get("literal_terms", [])]
        for dom, terms in zp.get("domains", {}).items():
            if not dom.startswith("_"):
                term_lists.append(terms)
        for terms in term_lists:
            for t in terms:
                lit = t.get("literal", "")
                if lit and lit in all_text:
                    warnings.append(f"语域问题 '{lit}'：建议改为 {t.get('preferred','')}（{t.get('note','')}）")

    rep = {"status": "fail" if errors else ("pass_with_warnings" if warnings else "pass"),
           "errors": errors, "warnings": warnings,
           "summary": {"groups": len(groups), "works_used": len(used_keys),
                       "works_total": len(works), "gaps": len(draft.get("gap", [])),
                       "contributions": len(draft.get("contributions", []))}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"check: {rep['status']}（error {len(errors)} / warning {len(warnings)}）")
    for e in errors:
        print("  ERROR:", e)
    for w in warnings[:10]:
        print("  warn :", w)
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
