#!/usr/bin/env python3
"""Merge hourly scan data with narratives and render a self-contained HTML timeline."""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    ".deps",
    ".venv",
    "venv",
    ".venv_pull",
    "site-packages",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
}
VERDICTS = {"pos", "neg", "mix", "none", "up", "infra"}
VERDICT_LABELS = {
    "pos": "正面",
    "neg": "负面 / 被证伪",
    "mix": "混合",
    "none": "无结果",
    "up": "上游 / 继承",
    "infra": "基础设施",
}
PHASE_COLORS = [
    "#5aa9ff",
    "#35d0ba",
    "#b18cff",
    "#f5b84d",
    "#62d26f",
    "#ff8a5c",
    "#ffb45c",
    "#ff6b8a",
    "#8b93a7",
    "#c084fc",
]


def load_json(path: Path, label: str):
    if not path.exists():
        raise SystemExit(f"错误：{label} 不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"错误：{label} 不是合法 JSON：{path}：{exc}") from exc


def load_narratives(path: Path) -> tuple[dict[str, dict], list[str]]:
    sources: list[tuple[str, dict]] = []
    if path.is_dir():
        part_files = sorted(path.glob("*.json"))
        if not part_files:
            raise SystemExit(f"错误：{path} 下没有 narratives JSON 文件")
        for part in part_files:
            raw = load_json(part, "narratives 分片")
            if isinstance(raw, dict) and isinstance(raw.get("hours"), dict):
                raw = raw["hours"]
            if not isinstance(raw, dict):
                raise SystemExit(f"错误：{part} 顶层必须是对象映射")
            sources.append((part.name, raw))
    else:
        raw = load_json(path, "narratives")
        if isinstance(raw, dict) and isinstance(raw.get("hours"), dict):
            raw = raw["hours"]
        if not isinstance(raw, dict):
            raise SystemExit("错误：narratives 顶层必须是对象映射")
        sources.append((path.name, raw))

    merged: dict[str, dict] = {}
    origin: dict[str, str] = {}
    for name, mapping in sources:
        for hour, narr in mapping.items():
            if hour in merged:
                raise SystemExit(
                    f"错误：小时 {hour} 在 {origin[hour]} 与 {name} 中重复出现"
                )
            if not isinstance(narr, dict):
                raise SystemExit(f"错误：{hour} 的叙事不是对象")
            merged[hour] = narr
            origin[hour] = name
    return merged, sorted(set(origin.values()))


def load_phases(path: Path) -> list[dict]:
    raw = load_json(path, "phases")
    if isinstance(raw, dict) and "phases" in raw:
        raw = raw["phases"]
    if not isinstance(raw, list) or not raw:
        raise SystemExit("错误：phases.json 必须是阶段数组")
    phases = []
    seen = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SystemExit("错误：阶段项必须是对象")
        pid = str(item.get("id", "")).strip()
        if not pid:
            raise SystemExit("错误：阶段缺少 id")
        if pid in seen:
            raise SystemExit(f"错误：阶段 id 重复：{pid}")
        seen.add(pid)
        phases.append(
            {
                "id": pid,
                "name": str(item.get("name") or pid),
                "short": str(item.get("short") or item.get("name") or pid),
                "color": str(item.get("color") or PHASE_COLORS[i % len(PHASE_COLORS)]),
                "summary": str(item.get("summary") or ""),
                "bullets": [str(x) for x in (item.get("bullets") or [])],
            }
        )
    return phases


def load_meta(path: Path | None) -> dict:
    if path is None:
        return {}
    raw = load_json(path, "meta")
    if not isinstance(raw, dict):
        raise SystemExit("错误：meta.json 必须是对象")
    notes = []
    for item in raw.get("notes") or []:
        if isinstance(item, str):
            notes.append({"h": "说明", "p": item})
        elif isinstance(item, dict) and item.get("p"):
            notes.append({"h": str(item.get("h") or "说明"), "p": str(item["p"])})
    return {
        "title": str(raw.get("title") or "").strip(),
        "subtitle": str(raw.get("subtitle") or "").strip(),
        "notes": notes,
    }


def build_path_index(root: Path) -> list[str]:
    paths = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in DEFAULT_EXCLUDES
            and not d.endswith(".egg-info")
            and not (Path(dirpath) / d).is_symlink()
        ]
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir != ".":
            paths.append(rel_dir)
        for name in filenames:
            paths.append((Path(dirpath) / name).relative_to(root).as_posix())
    return paths


def strip_line_suffix(value: str) -> tuple[str, str]:
    match = re.match(r"^(.*):(\d+)$", value)
    if match:
        return match.group(1), match.group(2)
    return value, ""


class EvidenceResolver:
    def __init__(self, root: Path, fix_map: dict[str, str]):
        self.root = root
        self.fix_map = fix_map
        self._index: list[str] | None = None

    def index(self) -> list[str]:
        if self._index is None:
            self._index = build_path_index(self.root)
        return self._index

    def _relative(self, raw: str) -> str:
        value = raw.strip().replace("\\", "/")
        if not value:
            return value
        p = Path(value)
        if p.is_absolute():
            try:
                value = p.resolve().relative_to(self.root).as_posix()
            except ValueError as exc:
                raise ValueError(f"证据不在项目根目录内：{raw}") from exc
        value = os.path.normpath(value).replace("\\", "/")
        if value.startswith("../") or value == "..":
            raise ValueError(f"证据越出项目根目录：{raw}")
        return value if value != "." else ""

    def _suffix_search(self, suffix: str) -> tuple[str | None, list[str]]:
        suffix = suffix.strip("/")
        candidates = [p for p in self.index() if p == suffix or p.endswith("/" + suffix)]
        candidates.sort(key=lambda x: (len(x), x))
        if not candidates:
            return None, []
        best = candidates[0]
        same_len = [p for p in candidates if len(p) == len(best)]
        if len(same_len) > 1:
            return None, same_len[:8]
        return best, []

    def resolve(self, raw: str, hour: str, index: int) -> dict:
        original = raw.strip()
        base, line = strip_line_suffix(original)
        notes = []
        if not base:
            return {
                "raw": original,
                "resolved": "",
                "exists": False,
                "line": line,
                "note": "空证据",
            }
        try:
            rel = self._relative(base)
        except ValueError as exc:
            return {
                "raw": original,
                "resolved": base,
                "exists": False,
                "line": line,
                "note": str(exc),
            }

        candidates = [
            f"{hour}|{original}",
            f"{hour}|{rel}",
            original,
            rel,
        ]
        for key in candidates:
            if key in self.fix_map:
                try:
                    rel = self._relative(self.fix_map[key])
                except ValueError as exc:
                    return {
                        "raw": str(self.fix_map[key]),
                        "resolved": str(self.fix_map[key]),
                        "exists": False,
                        "line": line,
                        "note": f"fix-map 无效：{exc}",
                    }
                notes.append("fix-map")
                break

        if rel.startswith(".../") or "/.../" in rel:
            suffix = rel[4:] if rel.startswith(".../") else rel.split("/.../", 1)[1]
            resolved, ambiguous = self._suffix_search(suffix)
            if resolved is None:
                return {
                    "raw": original,
                    "resolved": rel,
                    "exists": False,
                    "line": line,
                    "note": "缩写无法唯一解析"
                    + (f"：{', '.join(ambiguous)}" if ambiguous else ""),
                }
            rel = resolved
            notes.append("suffix-resolved")

        if any(ch in rel for ch in "*?["):
            matches = sorted(
                Path(x).resolve().relative_to(self.root).as_posix()
                for x in glob.glob(str(self.root / rel), recursive=True)
            )
            if len(matches) != 1:
                return {
                    "raw": original,
                    "resolved": rel,
                    "exists": False,
                    "line": line,
                    "note": f"glob 匹配 {len(matches)} 个路径，必须唯一",
                }
            rel = matches[0]
            notes.append("glob-resolved")

        check_path = self.root / rel
        exists = check_path.exists()
        if not exists and not notes:
            resolved, ambiguous = self._suffix_search(rel)
            if resolved is not None:
                rel = resolved
                check_path = self.root / rel
                exists = True
                notes.append("suffix-resolved")
            elif ambiguous:
                return {
                    "raw": original,
                    "resolved": rel,
                    "exists": False,
                    "line": line,
                    "note": "路径不存在，后缀有歧义：" + ", ".join(ambiguous),
                }
            else:
                notes.append("missing")

        return {
            "raw": f"{rel}:{line}" if line else rel,
            "resolved": rel,
            "exists": exists,
            "line": line,
            "note": "; ".join(notes),
        }


def make_haystack(hour: dict, narr: dict, phase: dict, evidence: list[dict]) -> str:
    parts = [
        hour["hour"],
        hour["date"],
        hour["weekday"],
        narr.get("p", ""),
        phase.get("name", ""),
        phase.get("short", ""),
        narr.get("v", ""),
        VERDICT_LABELS.get(narr.get("v", ""), ""),
        narr.get("t", ""),
        narr.get("q", ""),
        narr.get("m", ""),
        narr.get("r", ""),
    ]
    for group in hour["groups"]:
        parts.extend([group["name"], group["dir"], group.get("md5", "")])
        parts.extend(group["paths"])
    for item in hour["files"]:
        parts.extend([item["path"], item["ext"], item.get("md5", "")])
    for item in evidence:
        parts.extend([item.get("raw", ""), item.get("resolved", "")])
    return " ".join(str(x) for x in parts if x).lower()


def weekday(d: str) -> str:
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        dt.date.fromisoformat(d).weekday()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="合并 birthtime 扫描与逐小时叙事，生成自包含 HTML 编年时间线。"
    )
    parser.add_argument("--hours", required=True, help="scan_birthtime.py 生成的 hours.json")
    parser.add_argument("--narratives", required=True, help="叙事 JSON 文件或目录")
    parser.add_argument("--phases", required=True, help="阶段定义 JSON")
    parser.add_argument("--meta", help="可选 meta.json：标题、副标题、口径说明")
    parser.add_argument("--out", required=True, help="输出 HTML 路径")
    parser.add_argument("--template", help="覆盖内置 HTML 模板路径")
    parser.add_argument("--evidence-map", help="可选证据修正映射 JSON")
    parser.add_argument("--title", help="覆盖标题")
    parser.add_argument("--subtitle", help="覆盖副标题")
    parser.add_argument(
        "--allow-missing-evidence",
        action="store_true",
        help="允许证据缺失；缺失项会在 HTML 中标记，最终交付不应使用",
    )
    parser.add_argument(
        "--allow-uncovered",
        action="store_true",
        help="允许存在没有叙事的小时；最终交付不应使用",
    )
    args = parser.parse_args()

    hours_path = Path(args.hours).expanduser().resolve()
    scan = load_json(hours_path, "hours.json")
    root = Path(scan["root"]).resolve()
    narratives, part_files = load_narratives(Path(args.narratives).expanduser().resolve())
    phases = load_phases(Path(args.phases).expanduser().resolve())
    phase_by_id = {p["id"]: p for p in phases}
    meta = load_meta(Path(args.meta).expanduser().resolve() if args.meta else None)

    fix_map = {}
    if args.evidence_map:
        raw_fix = load_json(Path(args.evidence_map).expanduser().resolve(), "evidence-map")
        if not isinstance(raw_fix, dict):
            raise SystemExit("错误：evidence-map 必须是对象")
        fix_map = {str(k): str(v) for k, v in raw_fix.items()}

    resolver = EvidenceResolver(root, fix_map)
    scan_hours = {h["hour"]: h for h in scan["hours"]}
    scan_order = [h["hour"] for h in scan["hours"]]
    narr_order = sorted(narratives)
    missing_hours = [h for h in scan_order if h not in narratives]
    extra_hours = [h for h in narr_order if h not in scan_hours]
    if extra_hours:
        raise SystemExit("错误：叙事包含扫描中不存在的小时：" + ", ".join(extra_hours))
    if missing_hours and not args.allow_uncovered:
        raise SystemExit("错误：以下小时没有叙事：" + ", ".join(missing_hours))

    merged_hours = []
    missing_evidence = []
    uncovered = []
    for hour_key in scan_order:
        base = scan_hours[hour_key]
        narr = narratives.get(hour_key)
        if narr is None:
            uncovered.append(hour_key)
            narr = {
                "p": phases[0]["id"],
                "v": "none",
                "t": "未覆盖",
                "q": "",
                "m": "",
                "r": "无叙事记录",
                "e": [],
                "inherited": False,
            }
        pid = str(narr.get("p") or phases[0]["id"])
        if pid not in phase_by_id:
            if args.allow_uncovered:
                phase_by_id[pid] = {
                    "id": pid,
                    "name": pid,
                    "short": pid,
                    "color": PHASE_COLORS[len(phases) % len(PHASE_COLORS)],
                    "summary": "",
                    "bullets": [],
                }
                phases.append(phase_by_id[pid])
            else:
                raise SystemExit(f"错误：小时 {hour_key} 引用了未定义阶段：{pid}")

        phase = phase_by_id[pid]
        title = str(narr.get("t") or "").strip()
        question = str(narr.get("q") or "").strip()
        method = str(narr.get("m") or "").strip()
        result = str(narr.get("r") or "").strip()
        verdict = str(narr.get("v") or "none")
        if verdict not in VERDICTS:
            raise SystemExit(f"错误：小时 {hour_key} 的 v 必须是 {sorted(VERDICTS)}")
        if not args.allow_uncovered and not title:
            raise SystemExit(f"错误：小时 {hour_key} 缺少标题 t")

        raw_evidence = narr.get("e") or []
        if isinstance(raw_evidence, str):
            raw_evidence = [raw_evidence]
        if not isinstance(raw_evidence, list):
            raise SystemExit(f"错误：小时 {hour_key} 的 e 必须是数组")
        evidence = []
        seen_ev = set()
        for i, raw in enumerate(raw_evidence):
            item = resolver.resolve(str(raw), hour_key, i)
            key = (item["resolved"], item["line"])
            if key in seen_ev:
                continue
            seen_ev.add(key)
            evidence.append(item)
            if not item["exists"]:
                missing_evidence.append((hour_key, item))

        if not evidence and not args.allow_uncovered:
            raise SystemExit(f"错误：小时 {hour_key} 没有证据 e；至少引用一个代码或产物路径")

        merged = dict(base)
        merged["narr"] = {
            "p": pid,
            "v": verdict,
            "t": title or "未覆盖",
            "q": question,
            "m": method,
            "r": result or "无结果记录",
            "e": evidence,
            "inherited": bool(narr.get("inherited")) or verdict == "up",
        }
        merged["phase_name"] = phase["name"]
        merged["phase_short"] = phase["short"]
        merged["phase_color"] = phase["color"]
        merged["hay"] = make_haystack(merged, merged["narr"], phase, evidence)
        merged_hours.append(merged)

    if missing_evidence and not args.allow_missing_evidence:
        lines = [
            f"  {hour}: {item['raw']} -> {item['resolved']} ({item['note']})"
            for hour, item in missing_evidence[:20]
        ]
        raise SystemExit(
            "错误：存在未解析/不存在的证据，最终构建必须为零。\n"
            + "\n".join(lines)
            + (f"\n... 共 {len(missing_evidence)} 条" if len(missing_evidence) > 20 else "")
        )

    for h in merged_hours:
        h.pop("phase_name", None)
        h.pop("phase_short", None)
        h.pop("phase_color", None)

    total_files = sum(h["n"] for h in merged_hours)
    local_groups = sum(h["unique"] for h in merged_hours)
    md5_enabled = bool(scan.get("md5Enabled", True))
    global_keys = set()
    for h in merged_hours:
        for f in h["files"]:
            global_keys.add(f.get("md5") or f["path"])
    unique_global = len(global_keys) if md5_enabled else total_files
    copies = total_files - unique_global
    dates = sorted({h["date"] for h in merged_hours})
    code_files = []
    md5_counts = {}
    for h in merged_hours:
        for f in h["files"]:
            key = f.get("md5") or f["path"]
            md5_counts[key] = md5_counts.get(key, 0) + 1
    for h in merged_hours:
        for f in h["files"]:
            key = f.get("md5") or f["path"]
            code_files.append(
                {
                    "dt": f["birth"],
                    "hour": h["hour"],
                    "p": h["narr"]["p"],
                    "v": h["narr"]["v"],
                    "path": f["path"],
                    "ext": f["ext"],
                    "size": f["size"],
                    "md5": f.get("md5", ""),
                    "copies": md5_counts[key] - 1,
                }
            )
    code_files.sort(key=lambda x: (x["dt"], x["path"]))

    for phase in phases:
        hs = [h for h in merged_hours if h["narr"]["p"] == phase["id"]]
        phase["hours"] = len(hs)
        phase["files"] = sum(h["n"] for h in hs)
        phase["localGroups"] = sum(h["unique"] for h in hs)
        phase["start"] = hs[0]["date"] if hs else ""
        phase["end"] = hs[-1]["date"] if hs else ""
        phase["neg"] = sum(1 for h in hs if h["narr"]["v"] == "neg")
        phase["none"] = sum(1 for h in hs if h["narr"]["v"] == "none")
        phase["inherited"] = sum(1 for h in hs if h["narr"]["inherited"])
        phase["hourKeys"] = [h["hour"] for h in hs]
    if not args.allow_uncovered:
        empty_phases = [p["id"] for p in phases if p["hours"] == 0]
        if empty_phases:
            raise SystemExit("错误：以下阶段没有对应小时：" + ", ".join(empty_phases))

    days = []
    for d in dates:
        hs = [h for h in merged_hours if h["date"] == d]
        days.append(
            {
                "date": d,
                "weekday": weekday(d),
                "hours": len(hs),
                "files": sum(h["n"] for h in hs),
                "localGroups": sum(h["unique"] for h in hs),
                "phases": sorted({h["narr"]["p"] for h in hs}),
            }
        )
    heat = []
    for d in dates:
        row = [0] * 24
        for h in merged_hours:
            if h["date"] == d:
                row[int(h["hour"][11:13])] = h["n"]
        heat.append(row)

    base_notes = [
        {
            "h": "时间口径",
            "p": "所有小时按文件 st_birthtime 的本地时区分组，不使用 mtime；扫描根目录为 "
            f"{root.as_posix()}，时区 {scan.get('timezone', '')}。",
        },
        {
            "h": "文件范围",
            "p": (
                "扫描全部文件。"
                if scan.get("extensions") == "all"
                else "扫描扩展名：" + ", ".join(scan.get("extensions", [])) + "。"
            )
            + "数据、文献和压缩包等资产如需纳入，请显式使用 --extensions all；"
            "结果文件与日志是否计入，应在叙事中说明。",
        },
        {
            "h": "依赖排除",
            "p": f"排除 {', '.join(scan.get('excludes', []))}；本次跳过 "
            f"{scan['stats'].get('skippedDirs', 0)} 个目录、"
            f"{scan['stats'].get('skippedDirFiles', 0)} 个文件。",
        },
        {
            "h": "去重口径",
            "p": f"文件 {total_files} 个；每小时去重组数合计 {local_groups}；"
            f"全局唯一内容 {unique_global} 组；同内容副本 {copies} 个。"
            "每小时去重组数不能当作全局唯一数。",
        },
        {
            "h": "继承时间",
            "p": f"{sum(1 for h in merged_hours if h['narr']['inherited'])} 个小时标记为上游/继承；"
            "这些 birthtime 可能来自压缩包或复制，不代表当时在本机发生了原创工作。",
        },
        {
            "h": "证据检查",
            "p": f"证据路径已解析并检查存在性；缺失 {len(missing_evidence)} 条。"
            "最终交付不允许残留 .../ 缩写或未验证路径。",
        },
        {
            "h": "快照副本",
            "p": "同一 md5 的重复文件在逐小时卡标 ×N；全部代码表仍保留每一行，"
            "便于核对文件数。",
        },
        {
            "h": "搜索索引",
            "p": "搜索覆盖标题、问题、做法、结果、数字、文件名、路径、证据、阶段和结论。",
        },
        {
            "h": "结果缺口",
            "p": f"{sum(1 for h in merged_hours if h['narr']['v'] == 'none')} 个小时标记为无结果；"
            "没有产物的代码不能被写成已验证。",
        },
    ]
    if not md5_enabled:
        base_notes.append(
            {"h": "md5 关闭", "p": "本次扫描未计算 md5；同一小时按路径分组，副本数为 0。"}
        )
    if scan["stats"].get("birthFallbackFiles"):
        base_notes.append(
            {
                "h": "ctime 回退",
                "p": f"{scan['stats']['birthFallbackFiles']} 个文件没有 st_birthtime，"
                "使用了 ctime；ctime 不是创建时间，结论需谨慎。",
            }
        )
    notes = base_notes + meta.get("notes", [])

    stats = {
        **scan["stats"],
        "hours": len(merged_hours),
        "files": total_files,
        "localGroups": local_groups,
        "uniqueGlobal": unique_global,
        "copies": copies,
        "days": len(dates),
        "phases": len(phases),
        "notes": len(notes),
        "heatCells": len(dates) * 24,
        "missingEvidence": len(missing_evidence),
        "uncoveredHours": len(uncovered),
        "inheritedHours": sum(1 for h in merged_hours if h["narr"]["inherited"]),
        "none": sum(1 for h in merged_hours if h["narr"]["v"] == "none"),
    }

    if stats["files"] != sum(h["n"] for h in merged_hours):
        raise SystemExit("内部错误：文件总数不一致")
    if stats["localGroups"] != sum(h["unique"] for h in merged_hours):
        raise SystemExit("内部错误：每小时去重组数合计不一致")
    if stats["copies"] != stats["files"] - stats["uniqueGlobal"]:
        raise SystemExit("内部错误：副本数不等于文件数减全局唯一数")
    if stats["uniqueGlobal"] > stats["localGroups"]:
        raise SystemExit("内部错误：全局唯一数不应大于每小时去重组数合计")
    if stats["days"] != len(dates):
        raise SystemExit("内部错误：日历日数不一致")
    if stats["phases"] != len(phases):
        raise SystemExit("内部错误：阶段数不一致")
    if sum(p["hours"] for p in phases) != stats["hours"]:
        raise SystemExit("内部错误：阶段小时数合计不一致")
    if sum(p["files"] for p in phases) != stats["files"]:
        raise SystemExit("内部错误：阶段文件数合计不一致")
    if len(code_files) != stats["files"]:
        raise SystemExit("内部错误：文件全表行数与文件数不一致")

    data = {
        "meta": {
            "title": args.title
            or meta.get("title")
            or f"{root.name} 工作编年",
            "subtitle": args.subtitle
            or meta.get("subtitle")
            or "按文件创建时间（st_birthtime）重建的逐小时工作记录",
            "root": root.as_posix(),
            "generated_at": scan.get("generated_at", ""),
            "timezone": scan.get("timezone", ""),
            "scopeLabel": "文件资产" if scan.get("extensions") == "all" else "项目文件",
            "itemLabel": "文件",
            "parts": part_files,
            "notes": notes,
        },
        "stats": stats,
        "phases": phases,
        "hours": merged_hours,
        "days": days,
        "heat": {"dates": dates, "matrix": heat},
        "codeFiles": code_files,
        "verdictLabels": VERDICT_LABELS,
    }

    template_path = (
        Path(args.template).expanduser().resolve()
        if args.template
        else Path(__file__).resolve().parent.parent / "assets" / "timeline_template.html"
    )
    if not template_path.exists():
        raise SystemExit(f"错误：HTML 模板不存在：{template_path}")
    template = template_path.read_text(encoding="utf-8")
    if "__CHRONO_DATA__" not in template:
        raise SystemExit("错误：HTML 模板缺少 __CHRONO_DATA__ 占位符")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    output = template.replace("__CHRONO_DATA__", payload).replace(
        "__CHRONO_TITLE__", html.escape(data["meta"]["title"])
    )
    if "__CHRONO_DATA__" in output or "__CHRONO_TITLE__" in output:
        raise SystemExit("错误：模板占位符未完全替换")

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")

    print(f"wrote: {out_path}")
    print(f"bytes: {len(output.encode('utf-8'))}")
    print(
        "stats: "
        + json.dumps(
            {
                k: stats[k]
                for k in (
                    "hours",
                    "files",
                    "localGroups",
                    "uniqueGlobal",
                    "copies",
                    "days",
                    "phases",
                    "notes",
                    "missingEvidence",
                    "inheritedHours",
                )
            },
            ensure_ascii=False,
        )
    )
    print("phases: " + ", ".join(f"{p['id']}={p['hours']}h/{p['files']}f" for p in phases))
    if missing_evidence:
        print(f"WARNING: {len(missing_evidence)} 条证据缺失（允许模式）")
    if uncovered:
        print(f"WARNING: {len(uncovered)} 个小时未覆盖（允许模式）")


if __name__ == "__main__":
    main()
