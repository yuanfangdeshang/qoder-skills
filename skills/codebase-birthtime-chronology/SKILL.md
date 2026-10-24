---
name: codebase-birthtime-chronology
description: "按文件 st_birthtime 重建代码库或项目资产的逐小时工作编年，生成自包含 HTML 时间线、阶段总览、24 小时热力图、文件全表与证据链；用于回答哪个小时创建了哪些文件、解决了什么问题、得到什么结果、下载或清洗了什么数据、读了什么文献，也用于项目历史审计、复现材料核对和工作汇报。English triggers: reconstruct hourly codebase chronology from file birthtimes, build a self-contained timeline HTML, audit what was created each hour, file birthtime timeline, project work timeline."
---

# 文件出生时间工作编年

## 适用场景

- 用户要求按时间顺序梳理项目：哪个小时创建了哪个文件、解决了什么问题、得到什么结果。
- 用户要求覆盖所有文件资产：代码、数据下载、数据清洗、日志、结果、文献笔记、上游复现材料。
- 用户要做项目历史审计、交接材料、复现核对或工作汇报，并需要可点击的证据链。
- 不适用于：只看 git 提交历史（用 `git log`）、只看最近修改（用 mtime）、或没有本地文件的纯讨论。

## 硬性规则

1. 只用 `st_birthtime` 分组，绝不用 mtime 冒充创建时间。缺少 birthtime 时默认跳过并报告；只有用户明确同意后才能用 `--allow-ctime-fallback`，且必须在结果中标注 ctime 不是创建时间。
2. 源项目只读。不得在源根目录内写文件、改权限、移动文件或执行 git 操作；所有输出放在项目外。
3. 排除依赖和缓存目录：`.git`、`.deps`、`.venv`、`.venv_pull`、`site-packages`、`node_modules`、`__pycache__` 等。报告跳过了多少目录和文件。
4. 用 md5 折叠同内容副本。区分三个数：每小时去重组数合计 `localGroups`、全局唯一内容 `uniqueGlobal`、同内容副本 `copies = files - uniqueGlobal`。不要把 `localGroups` 当成全局唯一数。
5. 证据必须是项目根目录下真实存在的相对路径，最终产物中不得残留 `.../`、绝对路径或未验证的通配符。证据解析失败时修叙事或修映射，不得用允许缺失的开关交付。
6. 每个小时都要有叙事；每个阶段至少有一个小时；最终构建必须 `missingEvidence = 0`、`uncoveredHours = 0`。
7. 不编造数字、结论和“已读”。没有结果就写“无结果记录”并标 `none`；没有读过的文献不要声称读过。
8. 继承时间必须标注。压缩包解压、上游仓库复制、快照恢复会让 birthtime 变成“落地时间”，不是原创工作时间；同一秒出现大量文件、路径含 `papers_repo`/`vendor`/`external`/`archive` 等是强信号。
9. HTML 必须自包含：不引用外部脚本、样式、字体、图片或网络资源。
10. 交付前必须同时通过静态校验和浏览器 DOM 校验；截图失败不等于 DOM 失败，但也不能用截图代替 DOM 断言。

## 运行时先确认

开始扫描前，确认三件事；用户已经给出的直接采用，缺失的才问，最多问一轮：

1. **项目根目录**：要审计的本地目录。默认当前工作目录，但必须先确认它不是整个 home 目录或文件系统根。
2. **文件范围**：
   - `项目文件`（推荐）：代码、配置、文档，使用脚本默认扩展名集合。
   - `全部文件资产`：加 `--extensions all`，覆盖数据、PDF、压缩包等；大目录更慢，md5 成本更高。
   - 自定义扩展名：按需传入逗号分隔列表。
3. **输出位置**：必须是项目根目录之外的目录，例如 `./chronology-output/<项目名>-<日期>/` 或 `/tmp/<项目名>-chronology/`。不得写进源项目。

同时记录：当前时区、Python 版本、是否启用 md5、是否允许 ctime 回退。若用户要求“直接做完”，采用推荐项并在最终报告中写明假设。

## 工作流

### 0. 建输出目录

在源项目外建立：

```text
<out>/
  scan/          # hours.json, hours.csv, hour_code_list.txt, scan_summary.json
  narratives/    # part-01.json, part-02.json, ...
  out/           # timeline.html
  logs/          # 校验输出、DOM 断言结果
```

先确认 `<out>` 不在 `<root>` 内。扫描脚本也会拒绝把输出写进扫描根目录。

### 1. 扫描 birthtime

把 `<skill-dir>` 替换为本 Skill 所在目录：

```bash
python3 "<skill-dir>/scripts/scan_birthtime.py" \
  --root "<project-root>" \
  --out "<out>/scan"
```

默认扩展名覆盖常见代码、配置和文档（Python、JS/TS、Go、Rust、Java、C/C++、SQL、Markdown、YAML、JSON 等）。全部资产模式使用 `--extensions all`；只关注某几类文件时传逗号分隔的自定义列表。超大目录可先用 `--no-md5` 做侦察，但最终交付应重新启用 md5；关闭 md5 时 `copies` 为 0，必须在报告中说明。

扫描后先读 `<out>/scan/scan_summary.json`，报告并检查：

- `files`、`hours`、`days`、`localGroups`、`uniqueGlobal`、`copies`。
- `skippedDirs` / `skippedDirFiles`：依赖目录是否被正确排除。
- `missingBirthtime` / `birthFallbackFiles`：是否有不能用 birthtime 的文件。
- `clusters`：同一秒出现 3 个以上文件，可能是解压或批量复制。
- `archiveLike`：疑似上游仓库、压缩包、快照路径。

发现继承时间信号时，不要把它写成“当时在本机原创”。在阶段划分和叙事中显式标注 `inherited: true` 或结论 `up`。

### 2. 划分阶段并分片

先根据时间断点、目录变化和扫描摘要定义 2–6 个阶段，写入 `<out>/phases.json`：

```json
[
  {
    "id": "p1",
    "name": "阶段名称",
    "short": "短名",
    "color": "#5aa9ff",
    "summary": "这个阶段在做什么，为什么转向下一个阶段。",
    "bullets": ["可核对的具体结论 1", "具体结论 2"]
  }
]
```

阶段只是阅读单位，不改变小时和文件的原始归属。不要为了凑阶段把同一小时拆开；每个阶段必须至少有一个小时。

把 `hours.json` 的小时按时间顺序切成连续分片，默认每片 6–10 个小时；文件特别多时降到 4–6 个。每个分片交给一个只读子代理，使用 `references/subagent-brief.md` 的模板，给出：

- 精确的小时列表，不得多写、漏写或改小时。
- 这些小时对应的文件路径（从 `hour_code_list.txt` 复制）。
- 阶段 id 和定义。
- 输出 JSON 的绝对路径（在 `<out>/narratives/` 内）。
- 证据规则和“不编造”要求。

小时很少（少于 8 个）时可以自己做，不必强行派子代理。多个子代理可以并行；每个分片只能写自己的 JSON 文件。

### 3. 写逐小时叙事

每个小时必须包含：

```json
{
  "2026-10-24 09": {
    "p": "p1",
    "v": "mix",
    "t": "一句话标题",
    "q": "这个小时要解决的问题，为什么现在做。",
    "m": "具体做法、脚本、数据、参数或阅读材料。",
    "r": "得到的结果；数字必须来自证据；没有结果写‘无结果记录’。",
    "e": ["relative/path/to/code.py", "relative/path/to/result.json:12"],
    "inherited": false
  }
}
```

约束：

- `v` 只能是 `pos`、`neg`、`mix`、`none`、`up`、`infra`。
- `t` 简短；`q`/`m`/`r` 各 1–3 句，写清“为什么、怎么做、结果如何”。
- `e` 至少一条，优先引用主代码文件；有运行结果时同时引用日志或结果 JSON。
- `r` 中的数字必须能在被引用的文件中找到；不确定就删掉数字，不要猜。
- 代码写完但没运行：写“已实现，未运行/未验证”，不要写“有效”。
- 数据下载/清洗：写清数据源、时间范围、行数、清洗规则和输出清单。
- 文献：只有存在笔记、标注或引用记录时才写“读了”；否则写“下载/归档，未记录阅读结论”。
- 继承材料：`inherited: true`；整小时都是上游材料时 `v: "up"`。
- 没有产物的基础设施小时用 `infra`；完全无结果用 `none`，结果写“无结果记录”。

### 4. 收口证据

先跑严格构建。若报证据缺失：

1. 打开 `<out>/scan/scan_summary.json` 和 `hour_code_list.txt`，确认真实路径。
2. 修叙事里的 `e`，不要改扫描结果。
3. 确实需要缩写映射时，写一个临时 `evidence_map.json`：

```json
{
  "2026-10-09 21|.../current_panel_sync_review.json": "relative/exact/path/current_panel_sync_review.json"
}
```

4. 重新构建，直到缺失为 0。`--allow-missing-evidence` 和 `--allow-uncovered` 只用于草稿；最终交付不允许使用。

解析顺序和边界见 `references/evidence-rules.md`。

### 5. 构建 HTML

```bash
python3 "<skill-dir>/scripts/build_timeline.py" \
  --hours "<out>/scan/hours.json" \
  --narratives "<out>/narratives" \
  --phases "<out>/phases.json" \
  --meta "<out>/meta.json" \
  --evidence-map "<out>/evidence_map.json" \
  --out "<out>/out/timeline.html"
```

`meta.json` 可选，用来放标题、副标题和补充说明：

```json
{
  "title": "项目工作编年",
  "subtitle": "按文件创建时间重建的逐小时记录",
  "notes": [
    {"h": "口径", "p": "补充这个项目特有的统计口径或已知缺口。"}
  ]
}
```

构建脚本会检查：文件数合计、每小时去重组数合计、副本数、全局唯一数、日历日数、阶段小时/文件合计、文件全表行数。任何一项不一致都会直接失败，不要绕过。

### 6. 静态校验

```bash
python3 "<skill-dir>/scripts/validate_timeline.py" \
  --html "<out>/out/timeline.html" \
  --hours "<out>/scan/hours.json"
```

必须看到 `PASS` 和 `missingEvidence: 0`。校验内容包括：占位符、外部资源、统计一致性、阶段/日期/热力图、每小时字段、搜索索引、证据存在性与相对路径、文件路径唯一性。

### 7. 浏览器 DOM 校验

在输出目录启动本地静态服务器（不要从源项目根目录启动），按 `references/dom-assertions.md` 用 browser-use 检查：

- 小时卡、日期分组、文件明细、阶段卡、热力图单元格、文件表行数、说明条数与内嵌数据一致。
- 四个页签可切换，面板显示正确。
- 搜索能命中标题、文件名、结果数字和证据路径。
- 日期筛选、结论筛选、文件表过滤生效。
- 展开全部/折叠全部生效。
- 浏览器控制台没有 error。

若应用内浏览器视口不可见导致截图失败，记录原因，但 DOM 断言仍必须完成；不能只凭截图宣称通过。

### 8. 展示与交付

- 用 `present_visualization` 展示 HTML（宽屏模式适合时间线）；不可用时给出绝对路径。
- 交付清单：`timeline.html`、`hours.json`、`hours.csv`、`hour_code_list.txt`、`scan_summary.json`、`narratives/`、`phases.json`、`meta.json`、校验日志。
- 最终报告写清：小时数、文件数、`localGroups`、`uniqueGlobal`、`copies`、日历日数、阶段数、`inheritedHours`、`none`、`missingEvidence`。
- 必须写 caveats：继承时间、缺失 birthtime、被排除的依赖目录、全部资产模式的规模、无结果小时、未验证的实现。
- 不要把“扫描到文件”说成“读懂了每个文件”；叙事只覆盖实际读过的证据。

## 失败模式与处理

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 时间线整体偏移 | 用了 mtime 或解压时间 | 重扫 birthtime；继承时间单独标注 |
| 文件数暴涨到几万 | 依赖/缓存目录被计入 | 加排除规则，报告 skipped 统计 |
| `localGroups` 与 `uniqueGlobal` 混淆 | 把每小时去重合计当全局唯一 | 分别展示，`copies` 用文件数减全局唯一 |
| 日历日数不对 | 用小时数除以 24 | 改为不同 birth 日期数 |
| 证据里有 `.../` | 叙事用了缩写 | 用精确相对路径或临时映射解析 |
| 搜索不到结果数字 | 索引只含标题 | 把问题、做法、结果、文件名、路径、证据、md5 全部入索引 |
| 旧项目的漂亮数字复现不了 | 代码路径或评估口径已变 | 先审计实现，再决定是否引用；不要把旧数字直接搬进新叙事 |
| 同一秒出现大量文件 | 解压/复制/快照 | 标 `inherited`，不要算作原创工作 |
| 阶段为空 | 阶段划分与小时不匹配 | 重分阶段或删除空阶段，重建 |
| 子代理写了没有证据的结论 | 只凭文件名猜测 | 退回重读文件；没有证据就删结论或标 `none` |
| 全量扫描太慢 | 数据文件太多、md5 太重 | 先用 `--no-md5` 侦察；最终启用 md5，或与用户确认缩窄范围 |
| 输出写进源项目 | 默认路径选错 | 立即停止，改用项目外目录；源项目只读 |

## 质量门槛

- [ ] 已记录根目录、范围、输出位置、时区；源项目未被修改。
- [ ] 只使用 `st_birthtime`；ctime 回退有明确同意和标注。
- [ ] 依赖目录已排除，跳过统计已报告。
- [ ] 每个扫描小时都有叙事；每个阶段非空；`uncoveredHours = 0`。
- [ ] 每小时有 `t/q/m/r/e`；数字可追溯；无结果已标 `none`。
- [ ] 所有证据是存在的相对路径；最终无 `.../`；`missingEvidence = 0`。
- [ ] 构建严格通过；静态校验 `PASS`。
- [ ] DOM 数量、页签、搜索、筛选、展开/折叠、控制台全部通过。
- [ ] HTML 自包含，无外部 URL。
- [ ] 最终报告包含统计和 caveats，没有“全读过”的夸大。

## 资源

- `scripts/scan_birthtime.py`：按 birthtime 扫描、排除依赖、md5 去重、输出小时数据。
- `scripts/build_timeline.py`：合并叙事与阶段，严格解析证据，生成自包含 HTML。
- `scripts/validate_timeline.py`：静态校验统计、证据、搜索索引和自包含性。
- `assets/timeline_template.html`：四页签深色时间线模板，无外部依赖。
- `references/subagent-brief.md`：并行叙事子代理的只读任务模板。
- `references/evidence-rules.md`：证据路径、继承时间、去重口径和常见错误。
- `references/dom-assertions.md`：浏览器 DOM 断言与交互检查脚本。

需要 Python 3.10+；脚本仅使用标准库。
