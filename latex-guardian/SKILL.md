---
name: latex-guardian
description: LaTeX 写作与编译的编译-诊断-交付闭环。机器先识别工程结构，多轮编译并解析日志，把错误归类到根因（缺宏包/未定义命令/数学错误/未解析引用等）并定位到文件与行号，Agent 按报告定点修复，最后门禁核验交付可编辑源码与可复现清单。不凭第一条报错猜，不交付无法编译的片段。
---

# latex-guardian：LaTeX 编译得通、改得对、交得可用、复现得了

## 运行预算纪律（先读）

- 必读文件只有本 SKILL.md；错误分类表 `assets/error_taxonomy.json` 在需要新增错误模式时再读。
- **不要通读完整 .log**（动辄数千行）：脚本已把日志解析成 `build_report.json`，只看报告的 errors/warnings 摘要；需上下文时用行号回读 .tex 源文件。
- 每完成一个阶段立即落盘：先跑一次 tex_build 拿报告，修复一处立即重跑验证，**保证中断时也有最近一次的报告与 PDF**。
- 你只手工改 .tex 源码；报告、清单、result.json 全部由脚本生成。

## 适用场景

输入是一个 LaTeX 工程（.tex/.bib/.cls/.sty/图片）加任务要求（编译通过、修复报错、迁入模板、补必填项等），输出是在指定模板下编译通过、引用收敛、可继续编辑的源码与 PDF，以及可复现构建清单。

## 工作流程（四步，修复循环在第 2-3 步之间）

### 第 1 步：识别工程结构

```bash
python scripts/tex_scan.py --project <工程目录> --out work/project.json
```

看摘要：主文件与文档类、子文件依赖、**缺失文件**、参考文献方式（bibtex/biber/手写）、引擎建议（fontspec/ctex → xelatex）。缺文件先解决，再谈编译。

### 第 2 步：机器编译与诊断

```bash
python scripts/tex_build.py --project <工程目录> --out work/build_report.json
# 找不到本地编译器时自动用远程公共服务（texlive.net latexcgi，TeX Live 官方后端）；
# 引擎与主文件可 --engine/--main 覆盖；--backend local 可强制只用本地（无则干净报错）
```

**后端选择（诚实标注）**：默认 auto——本地有 TeX 用本地；没有则用 `--remote-url` 指定的公共服务，清单中如实记 `backend=remote` 与服务地址，引擎版本从真实日志首行提取。远程模式下脚本给主文件加 `\nonstopmode` 包装器（服务端以 batchmode 运行会在首个错误处停下；包装后一次运行暴露全部错误，行号仍指向真实源文件）。**禁止因本地无 TeX 就假装编译成功。**

脚本自动完成 engine → bibtex/biber → engine ×N 的轮次（检测到"需再编译"信号自动加轮，上限 5 轮），然后输出：

- **errors**：每条错误归类根因（缺宏包/缺类文件/未定义命令/数学错误/环境不配平/字体错误等），定位**文件:行号**，附修复指引——不要停在第一条错误上，报告一次给全。
- **undefined_refs / undefined_citations**：`\ref`/`\cite` 指向不存在的 label/键——这类问题日志里只是 warning，但 PDF 里就是 "??"，必须清零。
- 同目录生成 `manifest.json`（引擎版本、宏包及版本、命令序列、页数）。

### 第 3 步：定点修复（Agent），改一处验一处

按 build_report.json 的 `file:line + guide` 修源码。规则：

- **改得对**：修根因不掩盖症状。宽表溢出用列宽/换行/longtable 正规手段，禁止 `\resizebox` 缩放掩盖；未定义命令先查拼写再查宏包；`\cite` 未解析先核对 .bib 键大小写。
- **不改无关内容**：每处修改记录到 `work/changes.json`：`[{"file","before","after","reason"}]`（before/after 为逐字片段，供复核）。
- 模板适配任务：必填项（\title \author 及任务指定项）写实质内容，不填占位符；材料里没有的信息标注 `% TODO: 待作者确认 <内容>`，不编造。
- 缺宏包且环境允许：先尝试安装（如 `tlmgr install <pkg>`）；装不了就换发行版自带方案并在 result.json 记录。
- 修完立即重跑第 2 步。errors 清零、无未解析引用、converged=true 才进下一步。

### 第 4 步：交付门禁与结果

```bash
python scripts/tex_check.py --project <工程目录> --main <主文件> \
  --report work/build_report.json --case /input/case.json \
  --changes work/changes.json --require title,author --outdir /app/output
```

四项门禁：编译干净（无错误/无未解析引用/有 PDF）；PDF 正文无 "??"（有 pdftotext 时真实抽取检查，无则诚实标注 skipped）；模板必填项非空；交付物是含完整 document 环境的可编辑 .tex。result.json 的 status 如实给 complete/partial/failed，problems 逐条列出。

## 输出契约

- 交付物：修复后的工程源码（原地修改）+ `build/main.pdf` + `work/build_report.json`（错误诊断）+ `work/manifest.json`（复现清单：引擎版本/宏包版本/命令/轮次）+ `result.json`。
- 复现：他人按 manifest 的引擎与宏包版本、相同命令序列即可得到同一 PDF。

## 异常处理

- 找不到编译器：默认自动切远程公共服务并在清单标注；`--backend local` 下找不到则 exit 2 并提示安装；**禁止假装编译成功**——没有 PDF 就没有 PDF，status 记 failed 并说明。
- 中文文档用 pdflatex 报一堆 "Unicode character … not set up"：taxonomy 归类 `unicode_char`，指引改用 ctexart/xeCJK + xelatex（tex_scan 的 engine_hint 会提前提示）。
- 报错级联（一个错引出几十条）：按报告顺序修最上面的根因，重跑后级联通常消失；不要逐条硬改下游错误。
- bibtex/biber 报错：看报告 bibtex 轮的 note（.blg 摘要），多为 .bib 语法问题（缺逗号/花括号不配平）。
- 编译超时（单轮 180s）：报告记录 TIMEOUT，检查死循环宏/特大图片。
- 多个 `\documentclass` 候选：tex_scan 会 warning，用 `--main` 显式指定。

## 最小示例

`example/project/` 是一个含 3 处典型错误（未定义命令、缺宏包、未解析引用）的最小工程，`example/expected_report.json` 为诊断报告示意（**仅说明接口，非正式案例结果**）。修复过程见 README。

## 已验证能力

- 真实演示（TeX Live 2026，texlive.net 公共服务）：含 4 处注入错误的化学稿件工程，诊断一次给出全部错误的文件:行号与根因（\\celsius 与 booktabs 命令未定义、fig:tem 无 label、cite 键不在 .bib）；按报告修复 4 处后重编译 converged、0 错误、引用文献真实解析（Suen et al., Chem. Soc. Rev. 2017, DOI 10.1039/c6cs00328a）；门禁四项全过（pdftotext 真实抽取无 "??"）。
- 破坏测试 8/8：缺宏包、数学错误（双下标）、环境不配平、label 拼错、cite 键拼错均正确归类且定位到 ./main.tex；无本地 TeX（--backend local）、工程目录不存在、无 \\documentclass 均 exit 2 干净失败。
- 错误分类表含 12 类（含 unicode_char：中文误用 pdflatex 时的识别与引擎指引）。
