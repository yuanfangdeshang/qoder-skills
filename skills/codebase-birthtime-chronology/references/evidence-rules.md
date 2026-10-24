# 证据、时间与去重口径

## 1. 时间基准

- 只用 `st_birthtime`。macOS/APFS 通常可用；Linux 的 ext4 往往没有 birthtime，此时脚本会跳过文件并在 `missingBirthtime` 中计数。
- 不使用 mtime。mtime 是最后修改时间，会把“后来改了一下”误判成“那时创建”。
- `ctime` 不是创建时间。只有用户明确同意后才加 `--allow-ctime-fallback`；输出会标 `birth_source=ctime-fallback`，最终报告必须写明。
- 小时按本地时区分组。跨时区复制、远程服务器训练、AutoDL 实例等场景要在叙事中写清实际发生地点和时区。

## 2. 继承时间

以下情况会让 birthtime 变成“落地时间”，而不是原创工作时间：

- 解压 zip/tar 后，所有文件共享解压时刻。
- 从上游仓库 `git clone` 或复制目录后，文件保留复制/检出时刻。
- 从快照、备份、网盘同步恢复。
- 路径包含 `papers_repo`、`vendor`、`third_party`、`external`、`archive`、`snapshot`、`backup`。
- 同一秒出现大量文件（`scan_summary.json` 的 `clusters`）。

处理：

- 整小时都是上游材料：`v: "up"`，`inherited: true`。
- 小时里混合原创和上游材料：用实际结论（`pos`/`neg`/`mix`/`none`/`infra`），同时 `inherited: true`。
- 不把上游代码的 birthtime 写成“我在那个小时写了它”；写“解压/复制/复现上游材料”。
- 阶段摘要和最终报告都要说明继承比例或至少列出继承小时。

## 3. 依赖排除

默认排除：

```text
.git .hg .svn .deps .venv venv .venv_pull site-packages node_modules
__pycache__ .mypy_cache .pytest_cache .tox .nox .idea .vscode
*.egg-info
```

这些目录里的文件不是项目工作产物，计入会让文件数从几百涨到几万，并污染时间线。

扫描输出会记录：

- `skippedDirs`：跳过的目录数。
- `skippedDirFiles`：这些目录下的文件数。
- `visitedFiles`：实际遍历到的文件数（不含被剪枝目录）。
- `totalSeenFiles`：`visitedFiles + skippedDirFiles`，即扫描过程中“看见”的总文件数。

不要把 `visitedFiles` 说成“项目总文件数”；也不要把 `totalSeenFiles` 说成“纳入统计的文件数”。

## 4. 去重口径

- `files`：纳入统计的文件行数，包含同内容副本。
- `localGroups`：每个小时内按 md5 折叠后的组数之和。同一文件在不同小时出现，会在两个小时各算一组。
- `uniqueGlobal`：全部文件按 md5 去重后的全局唯一内容数。
- `copies = files - uniqueGlobal`：同内容副本数。

关系：

```text
uniqueGlobal <= localGroups <= files
copies = files - uniqueGlobal
```

不要写“全局唯一 = 每小时去重组数之和”。只有所有重复都发生在同一小时时两者才相等。

关闭 md5（`--no-md5`）时：

- 小时内只能按路径分组。
- `copies` 为 0。
- 不能据此声称“没有副本”；只是没有计算。
- 最终交付应重新启用 md5。

## 5. 证据路径

最终证据必须是：

1. 相对于项目根目录的路径。
2. 真实存在。
3. 不含 `.../`、绝对路径、未验证的通配符。
4. 需要行号时写成 `path:line`，行号真实存在。

好例子：

```json
"e": [
  "research_loop/candidates/h34_china_wind_mechanism/artifacts/window_robustness.json",
  "mixed_frequency_end_to_end/availability_v6/logs/full_v6_seed7.log:42"
]
```

坏例子：

```json
"e": [
  ".../window_robustness.json",          // 缩写，最终不允许
  "/Users/me/project/result.json",       // 绝对路径
  "runs/*/summary.json",                 // 通配符，必须唯一解析
  "不存在的文件.json"                     // 不存在
]
```

## 6. 解析顺序

`build_timeline.py` 按以下顺序解析：

1. 精确相对路径。
2. 绝对路径：如果位于项目根目录内，转换为相对路径；否则失败。
3. 证据映射 `evidence_map.json`：键可以是 `小时|原始值`、`小时|相对值`、原始值、相对值。
4. `.../` 后缀搜索：在项目路径索引中找以该后缀结尾的路径；必须最短且唯一，否则失败。
5. 唯一 glob：通配符必须只匹配一个路径。
6. 行号后缀 `:N`：路径解析后单独保留行号。
7. 存在性检查：不存在则记为缺失；若没有使用映射，还会尝试一次唯一后缀解析。

最终构建在 `missingEvidence > 0` 时退出码非 0。不要用 `--allow-missing-evidence` 交付；那只是草稿模式。

## 7. 数字与结论

- `r` 里的数字必须能在 `e` 指向的文件中找到。找不到就删掉数字，或补充正确证据。
- 聚合数字（均值、百分比、收益、Sharpe、覆盖率）要能追溯到结果 JSON、日志或表格，不要从记忆里写。
- “跑通了”不等于“有效”。有日志但指标变差，应写负面结论。
- “代码写完”不等于“已验证”。没有运行记录就写“已实现，未运行/未验证”，`v` 用 `none` 或 `infra`。
- 文献只有存在笔记、标注、引用记录时才写“读了”。只下载/归档就写“归档，未记录阅读结论”。
- 旧项目的漂亮数字如果当前代码无法复现，先审计实现和口径；不要把旧数字直接搬进新叙事。

## 8. 只读与输出

- 源项目只读：不写文件、不改权限、不移动、不删除、不执行 git 写操作。
- 输出放在项目外，例如 `./chronology-output/<project>-<date>/` 或 `/tmp/<project>-chronology/`。
- 扫描脚本会拒绝 `--out` 位于 `--root` 内。
- 叙事子代理只能写自己分片的 JSON 文件；不得写源项目。
- 需要临时修正映射时，把 `evidence_map.json` 放在输出目录，不要放进源项目。
