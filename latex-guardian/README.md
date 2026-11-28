# latex-guardian

LaTeX 写作与编译的**编译-诊断-交付闭环**：编译得通、改得对、交得可用、复现得了。

## 工作原理

```
LaTeX 工程 ──tex_scan.py──> project.json（主文件/依赖图/缺文件/文献方式/引擎建议）
              │
              ▼
tex_build.py  多轮编译（engine→bibtex/biber→engine×N，自动加轮至收敛）
              │  解析日志：错误归类根因 + 定位 文件:行号 + 修复指引
              │  未解析 \ref/\cite 单独列出（PDF 里的 "??"）
              ├──> build_report.json（诊断报告）
              └──> manifest.json（引擎/宏包版本、命令、轮次 → 可复现构建）
              │
              ▼
Agent 按报告定点修复 .tex（根因修复，不掩盖症状；每处修改记入 changes.json）
              │  改一处，重跑一次 tex_build
              ▼
tex_check.py  四项门禁：编译干净 / PDF 无 "??" / 模板必填项非空 / 可编辑源码
              └──> result.json（status 如实：complete/partial/failed）
```

## 目录

| 路径 | 说明 |
|---|---|
| `SKILL.md` | 使用说明（预算纪律、工作流程、输出契约、异常处理） |
| `scripts/tex_scan.py` | 工程结构识别（纯标准库） |
| `scripts/tex_build.py` | 编译驱动 + 日志诊断 + 复现清单（纯标准库，调用系统 TeX） |
| `scripts/tex_check.py` | 交付门禁与 result.json（纯标准库） |
| `assets/error_taxonomy.json` | 错误分类表：模式 → 根因 → 修复指引（可扩展） |
| `example/` | 最小示例工程（含 3 处典型错误）+ 诊断报告示意 |

## 设计要点

- **不停在第一条错误**：nonstopmode 跑完整轮，一次给出全部错误的根因分类与文件:行号。
- **引用未解析视同未完成**：undefined refs/citations 在日志里只是 warning，但交付标准里它们是 PDF 中的 "??"，必须清零才算 converged。
- **复现得了**：manifest 记录引擎版本、宏包及版本（从日志 Package: 行提取）、文献样式、逐轮命令与耗时。
- **诚实状态**：没有编译器就报 exit 2，绝不假装编译成功；PDF "??" 检查工具缺失时标注 skipped 而不是默认通过。

## 已验证

- 真实演示（TeX Live 2026，texlive.net 公共服务后端）：4 处注入错误全部被归类定位（文件:行号+修复指引），修复后收敛、引用真实解析、门禁四项全过（含 pdftotext 抽取查 "??"）。
- 破坏测试 8/8：缺宏包/数学错误/环境不配平/label 拼错/cite 键拼错全部正确归类；无本地 TeX、目录不存在、无主文件干净失败。
- 远程后端细节：服务端 batchmode 只报第一个错误，脚本用 `\nonstopmode` 包装器让一次运行暴露全部错误且行号不变；后端与版本如实写入 manifest。
