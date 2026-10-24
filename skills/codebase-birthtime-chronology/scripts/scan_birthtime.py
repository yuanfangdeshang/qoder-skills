#!/usr/bin/env python3
"""Scan file birthtimes, group project files by local hour, and deduplicate by md5."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter, OrderedDict
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

DEFAULT_EXTENSIONS = {
    ".py",
    ".pyx",
    ".ipynb",
    ".sh",
    ".bash",
    ".zsh",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".scala",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".m",
    ".jl",
    ".r",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".vue",
    ".svelte",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
}
SKIP_FILENAMES = {".DS_Store", "Thumbs.db"}
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def parse_extensions(value: str) -> set[str] | None:
    value = value.strip()
    if value.lower() == "all":
        return None
    items = [x.strip().lower() for x in value.split(",") if x.strip()]
    if not items:
        raise argparse.ArgumentTypeError("--extensions 不能为空，使用 all 表示全部文件")
    return {x if x.startswith(".") else "." + x for x in items}


def md5sum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def human_time(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def count_files_under(path: Path) -> int:
    n = 0
    for _, _, files in os.walk(path):
        n += len(files)
    return n


def scan(args: argparse.Namespace) -> dict:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"错误：--root 不是目录：{root}")

    out_dir = Path(args.out).expanduser().resolve()
    try:
        out_dir.relative_to(root)
    except ValueError:
        pass
    else:
        raise SystemExit(
            "错误：--out 不能位于 --root 内。源项目只读，请把扫描输出放到项目外。"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    extensions = parse_extensions(args.extensions)
    excludes = set(DEFAULT_EXCLUDES)
    if args.exclude:
        excludes.update(x.strip() for x in args.exclude.split(",") if x.strip())

    files: list[dict] = []
    skipped_dirs: list[dict] = []
    skipped_files: list[dict] = []
    visited_files = 0
    filtered_by_extension = 0
    missing_birthtime = 0
    birth_fallback_files = 0
    md5_failures = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)

        pruned = []
        for name in list(dirnames):
            child = current / name
            if name in excludes or name.endswith(".egg-info") or child.is_symlink():
                pruned.append(name)
                dirnames.remove(name)
                if not child.is_symlink():
                    skipped_dirs.append(
                        {
                            "path": child.relative_to(root).as_posix(),
                            "files": count_files_under(child),
                        }
                    )

        for name in filenames:
            visited_files += 1
            if name in SKIP_FILENAMES:
                filtered_by_extension += 1
                continue
            path = current / name
            if path.is_symlink():
                skipped_files.append(
                    {"path": path.relative_to(root).as_posix(), "reason": "symlink"}
                )
                continue

            ext = path.suffix.lower()
            if extensions is not None and ext not in extensions:
                filtered_by_extension += 1
                continue

            try:
                st = path.stat()
            except OSError as exc:
                skipped_files.append(
                    {"path": path.relative_to(root).as_posix(), "reason": str(exc)}
                )
                continue

            birth = getattr(st, "st_birthtime", None)
            if birth is None or birth <= 0:
                missing_birthtime += 1
                if not args.allow_ctime_fallback:
                    skipped_files.append(
                        {
                            "path": path.relative_to(root).as_posix(),
                            "reason": "no st_birthtime",
                        }
                    )
                    continue
                birth = st.st_ctime
                birth_fallback_files += 1

            digest = ""
            if not args.no_md5:
                try:
                    digest = md5sum(path)
                except OSError as exc:
                    md5_failures += 1
                    if args.strict:
                        raise SystemExit(f"错误：无法计算 md5：{path}：{exc}")

            birth_dt = dt.datetime.fromtimestamp(birth)
            mtime_dt = dt.datetime.fromtimestamp(st.st_mtime)
            files.append(
                {
                    "birth": birth_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": mtime_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "hour": birth_dt.strftime("%Y-%m-%d %H"),
                    "date": birth_dt.strftime("%Y-%m-%d"),
                    "weekday": WEEKDAYS[birth_dt.weekday()],
                    "ext": ext,
                    "size": st.st_size,
                    "md5": digest,
                    "path": path.relative_to(root).as_posix(),
                    "birth_source": "birthtime"
                    if getattr(st, "st_birthtime", None)
                    else "ctime-fallback",
                }
            )

    if not files:
        raise SystemExit("错误：没有扫描到任何文件，请检查 --root、--extensions 或排除规则。")

    files.sort(key=lambda x: (x["birth"], x["path"]))
    hours: dict[str, list[dict]] = OrderedDict()
    for item in files:
        hours.setdefault(item["hour"], []).append(item)

    hour_records = []
    for hour, fs in sorted(hours.items()):
        groups_by_key: dict[str, list[dict]] = OrderedDict()
        for f in fs:
            # 同一小时内 md5 相同的文件折叠为一组，n 表示快照副本数。
            key = f["md5"] or f["path"]
            groups_by_key.setdefault(key, []).append(f)

        groups = []
        for key, members in groups_by_key.items():
            members = sorted(members, key=lambda x: x["path"])
            first = members[0]
            parent = Path(first["path"]).parent.as_posix()
            groups.append(
                {
                    "name": Path(first["path"]).name,
                    "dir": "." if parent == "." else parent,
                    "t": first["birth"][11:],
                    "n": len(members),
                    "size": first["size"],
                    "md5": first["md5"],
                    "paths": [x["path"] for x in members],
                }
            )
        groups.sort(key=lambda x: (x["t"], x["name"]))
        hour_records.append(
            {
                "hour": hour,
                "date": hour[:10],
                "weekday": WEEKDAYS[dt.date.fromisoformat(hour[:10]).weekday()],
                "files": fs,
                "groups": groups,
                "n": len(fs),
                "unique": len(groups),
                "bytes": sum(x["size"] for x in fs),
            }
        )

    total_files = len(files)
    local_groups = sum(h["unique"] for h in hour_records)
    global_keys = {f["md5"] or f["path"] for f in files}
    unique_global = len(global_keys)
    copies_global = total_files - unique_global
    dates = sorted({f["date"] for f in files})

    content_counts = Counter(f["md5"] or f["path"] for f in files)
    duplicate_groups = {k: v for k, v in content_counts.items() if v > 1}

    second_counts = Counter(f["birth"] for f in files)
    clusters = [
        {"birth": k, "files": v}
        for k, v in second_counts.most_common(10)
        if v >= 3
    ]

    archive_like = [
        f["path"]
        for f in files
        if any(
            token in f["path"].lower()
            for token in (
                "papers_repo",
                "vendor",
                "third_party",
                "third-party",
                "external",
                "archive",
                "snapshot",
                "backup",
            )
        )
    ]

    stats = {
        "visitedFiles": visited_files,
        "totalSeenFiles": visited_files + sum(x["files"] for x in skipped_dirs),
        "files": total_files,
        "filteredByExtension": filtered_by_extension,
        "skippedDirs": len(skipped_dirs),
        "skippedDirFiles": sum(x["files"] for x in skipped_dirs),
        "skippedFiles": len(skipped_files),
        "missingBirthtime": missing_birthtime,
        "birthFallbackFiles": birth_fallback_files,
        "md5Failures": md5_failures,
        "hours": len(hour_records),
        "localGroups": local_groups,
        "uniqueGlobal": unique_global,
        "copies": copies_global,
        "days": len(dates),
        "duplicateGroups": len(duplicate_groups),
        "duplicateFiles": sum(duplicate_groups.values()),
    }

    data = {
        "root": root.as_posix(),
        "generated_at": dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "timezone": str(dt.datetime.now().astimezone().tzinfo),
        "extensions": sorted(extensions) if extensions is not None else "all",
        "excludes": sorted(excludes),
        "md5Enabled": not args.no_md5,
        "stats": stats,
        "hours": hour_records,
        "days": [
            {
                "date": d,
                "weekday": WEEKDAYS[dt.date.fromisoformat(d).weekday()],
                "hours": sum(1 for h in hour_records if h["date"] == d),
                "files": sum(h["n"] for h in hour_records if h["date"] == d),
            }
            for d in dates
        ],
        "clusters": clusters,
        "archiveLike": {
            "count": len(archive_like),
            "samples": archive_like[:20],
        },
        "skippedDirs": sorted(skipped_dirs, key=lambda x: (-x["files"], x["path"])),
        "skippedFiles": skipped_files[:200],
    }

    hours_path = out_dir / "hours.json"
    hours_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    with (out_dir / "hours.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["birth", "mtime", "hour", "ext", "size", "md5", "path"])
        for item in files:
            writer.writerow(
                [
                    item["birth"],
                    item["mtime"],
                    item["hour"],
                    item["ext"],
                    item["size"],
                    item["md5"],
                    item["path"],
                ]
            )

    with (out_dir / "hour_code_list.txt").open("w", encoding="utf-8") as f:
        for h in hour_records:
            f.write(f"## {h['hour']} ({h['n']} files, {h['unique']} groups)\n")
            for item in h["files"]:
                f.write(f"  {item['birth'][11:]} {item['path']}\n")
            f.write("\n")

    summary = {
        "root": data["root"],
        "generated_at": data["generated_at"],
        "timezone": data["timezone"],
        "stats": stats,
        "clusters": clusters,
        "archiveLike": data["archiveLike"],
        "skippedDirsTop": data["skippedDirs"][:20],
        "warnings": [],
    }
    if birth_fallback_files:
        summary["warnings"].append(
            f"{birth_fallback_files} 个文件没有 st_birthtime，已按 --allow-ctime-fallback 使用 ctime；ctime 不是创建时间。"
        )
    if missing_birthtime and not args.allow_ctime_fallback:
        summary["warnings"].append(
            f"{missing_birthtime} 个文件没有 st_birthtime，已跳过；不要用 mtime 代替。"
        )
    if data["archiveLike"]["count"]:
        summary["warnings"].append(
            f"{data['archiveLike']['count']} 个路径疑似来自上游仓库/压缩包/快照，需在叙事中标注继承时间。"
        )
    if args.no_md5:
        summary["warnings"].append(
            "已禁用 md5；同一小时只能按路径分组，copies 为 0。最终交付建议启用 md5。"
        )
    (out_dir / "scan_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"root: {data['root']}")
    print(f"visited files: {stats['visitedFiles']}")
    print(f"total seen files: {stats['totalSeenFiles']} (including pruned dirs)")
    print(f"selected files: {stats['files']}")
    print(f"filtered by extension: {stats['filteredByExtension']}")
    print(f"skipped dirs: {stats['skippedDirs']} ({stats['skippedDirFiles']} files)")
    print(f"hours: {stats['hours']}")
    print(f"days: {stats['days']}")
    print(f"local groups: {stats['localGroups']}")
    print(f"global unique: {stats['uniqueGlobal']}")
    print(f"copies: {stats['copies']}")
    print(f"wrote: {hours_path}")
    if summary["warnings"]:
        print("warnings:")
        for warning in summary["warnings"]:
            print(f"  - {warning}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按 st_birthtime 扫描项目文件，按小时分组并用 md5 折叠同内容副本。"
    )
    parser.add_argument("--root", required=True, help="项目根目录")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument(
        "--extensions",
        default=".py,.sh,.js,.ipynb",
        help="逗号分隔的扩展名；all 表示全部文件（默认 .py,.sh,.js,.ipynb）",
    )
    parser.add_argument("--exclude", default="", help="额外排除的目录名，逗号分隔")
    parser.add_argument("--no-md5", action="store_true", help="不计算 md5（大目录可加速）")
    parser.add_argument(
        "--allow-ctime-fallback",
        action="store_true",
        help="缺少 st_birthtime 时使用 ctime；结果会标注，不推荐",
    )
    parser.add_argument("--strict", action="store_true", help="md5 读取失败时直接退出")
    args = parser.parse_args()
    scan(args)


if __name__ == "__main__":
    main()
