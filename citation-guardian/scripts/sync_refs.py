# -*- coding: utf-8 -*-
"""sync_refs.py — 确定性重排编号并同步正文标记与文末列表。

模型不做算术：合并映射与取舍由 Agent 审定后写在 plan.json 里，
编号重排、正文改写、列表重建全部由本脚本确定性完成。

plan.json:
{
  "merges": [{"survivor": "1", "absorbed": ["6"], "justification": "...", "matched_criteria": [3]}],
  "drop_entries": [{"key": "2", "reason": "全篇未被引用"}],
  "keep_uncited": false
}

用法:
  python sync_refs.py --manuscript manuscript.md --entries entries.json \
      --plan plan.json --out-dir work/sync
输出: manuscript_updated.md（正文标记已重排）、entries_synced.json（新编号）、change_log.json
"""
import argparse, json, re, sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from parse_refs import RE_MARKER, expand_marker, norm  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--entries", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()

    import os
    os.makedirs(a.out_dir, exist_ok=True)
    text = norm(open(a.manuscript, encoding="utf-8-sig").read())
    entries = {e["key"]: e for e in json.load(open(a.entries, encoding="utf-8-sig"))}
    plan = json.load(open(a.plan, encoding="utf-8-sig"))

    # 1. 合并映射：被吸收号 → 保留号
    alias = {}
    for m in plan.get("merges", []):
        for ab in m["absorbed"]:
            alias[str(ab)] = str(m["survivor"])
    dropped = {str(d["key"]) for d in plan.get("drop_entries", [])}

    # 2. 正文所有被引号（应用合并映射、剔除被删条目）
    def map_num(n):
        k = str(n)
        while k in alias:  # 链式合并兜底
            k = alias[k]
        return None if k in dropped else int(k)

    order = []  # 首次出现顺序的旧号（映射后）
    def collect(m):
        for n in expand_marker(m.group(1)):
            mn = map_num(n)
            if mn is not None and mn not in order:
                order.append(mn)
        return m.group(0)
    RE_MARKER.sub(collect, text)

    # 3. 新编号：按首次出现顺序 1..N
    new_no = {old: i + 1 for i, old in enumerate(order)}

    # 4. 改写正文标记
    def rewrite(m):
        nums = []
        for n in expand_marker(m.group(1)):
            mn = map_num(n)
            if mn is not None:
                nums.append(new_no[mn])
        nums = sorted(set(nums))
        if not nums:
            return ""
        # 连续区间压缩：2,3,4 -> 2-4
        ranges, start, prev = [], nums[0], nums[0]
        for n in nums[1:] + [None]:
            if n is not None and n == prev + 1:
                prev = n
                continue
            ranges.append(f"{start}-{prev}" if prev > start else str(start))
            if n is not None:
                start = prev = n
        return "[" + ",".join(ranges) + "]"
    updated = RE_MARKER.sub(rewrite, text)

    # 5. 重建条目列表
    synced = []
    for old, new in new_no.items():
        e = dict(entries[str(old)])
        e["old_key"] = str(old)
        e["key"] = str(new)
        synced.append(e)
    synced.sort(key=lambda e: int(e["key"]))
    uncited = [e for k, e in entries.items()
               if k not in alias and k not in dropped
               and (not k.isdigit() or int(k) not in order)]

    import os
    with open(os.path.join(a.out_dir, "manuscript_updated.md"), "w", encoding="utf-8") as f:
        f.write(updated)
    with open(os.path.join(a.out_dir, "entries_synced.json"), "w", encoding="utf-8") as f:
        json.dump({"entries": synced, "uncited_entries": uncited}, f, ensure_ascii=False, indent=2)
    log = {
        "renumber_map": {str(k): v for k, v in sorted(new_no.items())},
        "merges_applied": plan.get("merges", []),
        "dropped": plan.get("drop_entries", []),
        "uncited_kept": [e.get("key") for e in uncited],
    }
    with open(os.path.join(a.out_dir, "change_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"重排 {len(new_no)} 条（旧→新 {log['renumber_map']}）| 合并 {len(plan.get('merges', []))} 组 | "
          f"删除 {len(dropped)} 条 | 未引用保留 {len(uncited)} 条")

if __name__ == "__main__":
    main()
