# literature-structured-notes（文献总结与结构化笔记）

玻尔产品周赛 · 北京化工大学分站赛 · 第一期「阅读10｜文献总结与结构化笔记」参赛作品。

## 这是什么

一个可被 AI Agent 调用的 **Skill**：把一篇科研论文（PDF）整理成**结构化笔记**，让"读论文"不只停留在摘要压缩，而是留下可以检索、可以回查、可以复用的知识。

## 它能产出什么

每篇论文会被整理成三层结构：

- **现象层**：一句话概括、论文卡片（研究问题 / 数据 / 方法 / 主要发现 / 结论 / 局限 / 前提）、逐章总结、关键数据与出处。
- **原理层**：逐条"为什么"（底层公式 / 机制 + 数字验算），并标注证据强度（本文直接测量 / 领域共识 / 初步推测）。
- **可复用层**：术语词典、可迁移的通用方法、13 格《精读笔记模板》。

## 目录结构

```
literature-structured-notes/
  SKILL.md                    # Skill 主体（五硬标准 + 八步方法）
  assets/
    fields.json               # 字段字典与锚点格式规范
    example_notes.json        # 最小调用示例（示意示例）
    精读笔记模板.md            # 13 格精读模板（现象层 + 原理层）
  scripts/
    validate_notes.py         # 确定性校验与组装脚本（仅标准库）
demo-fe-coch-notes/           # 一篇真实论文的完整演示
  notes_spec.json             # 结构化输入
  output/                     # 校验后的 result.json / notes.md / evidence_map.json
  读书笔记-易懂版.md
  原理与基础知识深挖.md
```

## 演示论文

《An Fe³⁺ induced etching and hydrolysis precipitation strategy affords an Fe–Co hydroxide nanotube array toward hybrid water electrolysis》
*Dalton Transactions*, 2024, 53, 1870–1877（DOI: 10.1039/d3dt03520d）

## 用法（简要）

1. Agent 读取论文 PDF，识别真实章节结构；
2. 按 `assets/fields.json` 产出 `notes_spec.json`；
3. 运行 `scripts/validate_notes.py` 校验并组装 `result.json` / `notes.md` / `evidence_map.json`；
4. 按 `assets/精读笔记模板.md` 生成面向读者的精读笔记。
