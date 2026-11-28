# citation-guardian

参考文献与引用管理 Skill：可解释去重 + 编号双向同步 + GB/T 7714 格式化 + 来源核验，全部由"脚本确定性 + Agent 语义判断"分工完成。

## 它解决什么问题

基础 Agent 做引用管理的典型失败：重复条目看不出（CNKI 导出 vs 出版社格式）、删改后编号断档、正文 [3] 与列表第 3 条对不上、段末一挂了事、编造 DOI 与"已核验"。本 Skill 让脚本从原文独立清点清单（外部分母）、确定性重排编号、按模板格式化并跑一致性校验；Agent 只做结构化、去重审定与论断匹配判断。

## 组成

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 四条硬标准 + 七步工作流 + 异常处理 + 自查清单 |
| `assets/citation_styles.json` | GB/T 7714—2015 / APA7 模板与必需字段 |
| `assets/dedup_rules.md` | 去重分层判据（DOI > 题名+年 > 模糊匹配；预印本/同名作者特殊情形） |
| `assets/example_entries.json` | 结构化条目格式示例 |
| `assets/sample_case_feco.json` | 真实演示记录（Dalton 2024 引言与文献表） |
| `scripts/parse_refs.py` | 从稿件与文献库独立清点：标记、所在句、悬空引用、未引用条目 |
| `scripts/dedup_refs.py` | 按判据找候选重复对（带分数与对比证据） |
| `scripts/sync_refs.py` | 应用合并/删除，按首次出现重排编号，同步正文与列表 |
| `scripts/check_refs.py` | 双向闭合、编号连续、GB/T 字段完备、段末引用、核验记录 |
| `scripts/assemble_refs.py` | GB/T 7714 列表 + result.json + 报告 |

## 最小流程

```bash
python scripts/parse_refs.py --manuscript manuscript.md --library refs.txt --out work/inventory.json
# Agent 结构化 entries.json，审定 dedup 候选写 plan.json
python scripts/dedup_refs.py --entries work/entries.json --out work/dedup_candidates.json
python scripts/sync_refs.py --manuscript manuscript.md --entries work/entries.json --plan work/plan.json --out-dir work/sync
python scripts/check_refs.py --manuscript work/sync/manuscript_updated.md --entries work/sync/entries_synced.json --styles assets/citation_styles.json --out work/check_report.json
python scripts/assemble_refs.py --case-id demo --synced work/sync/entries_synced.json --change-log work/sync/change_log.json --manuscript work/sync/manuscript_updated.md --check work/check_report.json --styles assets/citation_styles.json --out output/
```

## 适用范围与限制

- 适用：顺序编码制（GB/T 7714）稿件的引用整理、去重、编号修复、格式转换；文献库为编号列表/BibTeX/JSON。
- 语义判断（论断—文献是否匹配、歧义条目归属）由 Agent 完成并留记录，脚本不替判；核验不到的一律 unverified。
- 纯 Python 标准库，无第三方依赖；Python ≥ 3.8。

## 维护

格式模板、去重判据可按目标期刊扩展；扩展判据时保持"候选由脚本找、决定由 Agent 写依据"的分工。
