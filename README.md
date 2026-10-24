# Qoder Skills

一组可复用的 Qoder Skills。每个 Skill 独立放在 `skills/<skill-name>/` 子目录里，**按需选择其中一个安装**，不要把整个 `skills/` 目录直接复制到 `~/.qoder/skills/`，否则会多出一层目录，Qoder 无法按技能名加载。

## 技能列表

| 子目录 | 用途 | 什么时候选它 | 状态 |
| --- | --- | --- | --- |
| [`skills/codebase-birthtime-chronology`](skills/codebase-birthtime-chronology/) | 按文件 `st_birthtime` 重建逐小时工作编年，生成自包含 HTML 时间线、阶段总览、24 小时热力图、文件全表和证据链 | 想知道“哪个小时创建了哪些文件、解决了什么问题、得到什么结果、下载/清洗了什么数据、读了什么文献”；做项目历史审计、交接或复现核对 | 已验证 |

## 安装其中一个

```bash
git clone https://github.com/yuanfangdeshang/qoder-skills.git
mkdir -p ~/.qoder/skills
cp -R qoder-skills/skills/codebase-birthtime-chronology ~/.qoder/skills/
```

确认文件在位：

```bash
ls ~/.qoder/skills/codebase-birthtime-chronology/SKILL.md
```

然后重启会话，或执行 `/skills reload`。可以用 `/codebase-birthtime-chronology` 调用，也可以直接说：

> 按文件创建时间，把这个项目逐小时梳理一遍：哪个小时创建了哪些文件、解决了什么问题、得到了什么结果，并生成一个可点击证据的 HTML 时间线。

安装时如果目标目录已存在，先备份或改名，不要直接覆盖。

## 这个 Skill 会先问什么

每次运行会确认三件事；已经在请求里给出的会直接采用：

1. **项目根目录**：要审计的本地目录。
2. **文件范围**：项目文件（代码/配置/文档）、全部文件资产（含数据/PDF/压缩包），或自定义扩展名。
3. **输出位置**：必须是项目根目录之外，例如 `./chronology-output/<项目名>-<日期>/`。

## 产出

```text
<out>/
  scan/
    hours.json              # 小时、文件、md5、统计、继承信号
    hours.csv               # 逐文件明细
    hour_code_list.txt      # 给叙事子代理的小时清单
    scan_summary.json       # 跳过目录、同秒聚集、上游路径警告
  narratives/               # 逐小时叙事分片
  phases.json               # 阶段定义
  meta.json                 # 标题、副标题、补充说明
  out/timeline.html         # 自包含时间线
  logs/                     # 静态校验与 DOM 断言结果
```

HTML 包含四个页签：

- **逐小时编年**：每个小时的问题、做法、结果、证据和文件明细；支持全文搜索、日期/结论筛选、展开/折叠。
- **阶段总览**：阶段卡片与 24 小时热力图。
- **文件全表**：每个文件的创建时间、路径、大小、副本数和 md5；支持过滤。
- **口径与更正**：时间基准、依赖排除、去重口径、继承时间、证据检查和结果缺口。

## 关键约束

- **只用 birthtime**：不用 mtime 冒充创建时间；缺少 birthtime 默认跳过并报告。
- **源项目只读**：不修改源目录，所有输出放在项目外。
- **证据可核对**：最终证据必须是存在且相对于项目根目录的路径，不允许 `.../` 缩写或未验证通配符。
- **不编造**：没有结果写“无结果记录”；没读过的文献不声称读过；数字必须能在证据文件中找到。
- **区分继承时间**：解压、复制、上游仓库落地的时间会标注为继承，不算原创工作。
- **自包含 HTML**：不引用外部脚本、样式、字体或网络资源。

## 环境

- Python 3.10+，仅使用标准库。
- 可选：browser-use MCP，用于最终 DOM 断言。没有浏览器工具时，仍可用静态校验，但不能声称页面交互已验证。
- macOS/APFS 通常提供 `st_birthtime`；Linux 文件系统可能没有，扫描会报告缺失数量。

## 仓库结构

```text
qoder-skills/
  README.md
  skills/
    codebase-birthtime-chronology/
      SKILL.md
      scripts/
      assets/
      references/
```

新增 Skill 时，在 `skills/` 下新建独立子目录，保持 `SKILL.md` 在子目录根部，并更新本文件的技能列表。每个子目录应能单独复制安装，不依赖仓库里的其他 Skill。
