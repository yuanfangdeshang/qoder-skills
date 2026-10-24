#!/usr/bin/env python3
"""Static validation for the generated chronology HTML and its embedded data."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED_IDS = [
    "chron-data",
    "q",
    "dateSel",
    "verdictSel",
    "expandAll",
    "collapseAll",
    "fq",
    "ftbody",
    "tabFilesBtn",
    "filesHeading",
]
REQUIRED_TABS = ["timeline", "phases", "files", "method"]


def extract_data(html: str) -> dict:
    match = re.search(
        r'<script id="chron-data" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not match:
        raise ValueError("找不到 id=chron-data 的 JSON 数据块")
    return json.loads(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser(description="校验编年 HTML 的统计、证据、搜索与自包含性。")
    parser.add_argument("--html", required=True, help="待校验 HTML")
    parser.add_argument("--hours", required=True, help="scan_birthtime.py 生成的 hours.json")
    parser.add_argument(
        "--allow-missing-evidence",
        action="store_true",
        help="允许证据缺失并把问题记为警告",
    )
    parser.add_argument(
        "--allow-uncovered",
        action="store_true",
        help="允许存在未覆盖小时并把问题记为警告",
    )
    args = parser.parse_args()

    html_path = Path(args.html).expanduser().resolve()
    if not html_path.exists():
        raise SystemExit(f"FAIL html 不存在：{html_path}")
    html = html_path.read_text(encoding="utf-8")
    scan = json.loads(Path(args.hours).expanduser().read_text(encoding="utf-8"))

    failures: list[str] = []
    warnings: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(html_path.stat().st_size >= 20_000, "HTML 小于 20KB，可能缺少内容")
    check("__CHRONO_DATA__" not in html, "HTML 残留 __CHRONO_DATA__ 占位符")
    check("__CHRONO_TITLE__" not in html, "HTML 残留 __CHRONO_TITLE__ 占位符")
    check("TODO" not in html, "HTML 残留 TODO")
    check("id=\"chron-data\"" in html, "缺少 chron-data 数据块")
    for element_id in REQUIRED_IDS:
        check(f'id="{element_id}"' in html, f"缺少控件 id={element_id}")
    for tab in REQUIRED_TABS:
        check(f'data-tab="{tab}"' in html, f"缺少页签 data-tab={tab}")
    check("@import" not in html, "CSS 使用了 @import")
    check(
        re.search(r"<script[^>]+src=", html, re.I) is None,
        "HTML 引用了外部 script",
    )
    check(
        re.search(r"<link[^>]+rel=[\"']stylesheet", html, re.I) is None,
        "HTML 引用了外部 stylesheet",
    )
    check(
        re.search(r"(?:src|href)=[\"']https?://", html, re.I) is None,
        "HTML 引用外部 URL",
    )

    try:
        data = extract_data(html)
    except Exception as exc:
        raise SystemExit(f"FAIL 无法读取内嵌数据：{exc}") from exc

    stats = data.get("stats", {})
    hours = data.get("hours", [])
    phases = data.get("phases", [])
    days = data.get("days", [])
    heat = data.get("heat", {})
    code_files = data.get("codeFiles", [])
    meta = data.get("meta", {})
    notes = meta.get("notes", [])
    phase_ids = {p.get("id") for p in phases}
    root = Path(meta.get("root", "")).resolve()

    check(bool(meta.get("title")), "缺少标题")
    check(bool(meta.get("generated_at")), "缺少 generated_at")
    check(bool(meta.get("timezone")), "缺少 timezone")
    check(bool(meta.get("scopeLabel")), "缺少 scopeLabel")
    check(bool(meta.get("itemLabel")), "缺少 itemLabel")
    check(len(hours) == stats.get("hours"), "stats.hours 与 hours 数组长度不一致")
    check(len(days) == stats.get("days"), "stats.days 与 days 数组长度不一致")
    check(len(phases) == stats.get("phases"), "stats.phases 与阶段数不一致")
    check(len(notes) == stats.get("notes"), "stats.notes 与说明条数不一致")
    check(len(code_files) == stats.get("files"), "codeFiles 行数与 files 不一致")
    check(sum(h.get("n", 0) for h in hours) == stats.get("files"), "小时文件数合计不一致")
    check(
        sum(h.get("unique", 0) for h in hours) == stats.get("localGroups"),
        "每小时去重组数合计不一致",
    )
    check(
        stats.get("copies") == stats.get("files", 0) - stats.get("uniqueGlobal", 0),
        "副本数不等于文件数减全局唯一数",
    )
    check(
        stats.get("uniqueGlobal", 0) <= stats.get("localGroups", 0),
        "全局唯一数大于每小时去重组数合计",
    )
    check(len(heat.get("dates", [])) == len(days), "热力图日期数不一致")
    check(
        len(heat.get("matrix", [])) == len(days),
        "热力图行数与日期数不一致",
    )
    check(
        all(len(row) == 24 for row in heat.get("matrix", [])),
        "热力图存在非 24 小时的行",
    )
    check(stats.get("heatCells") == len(days) * 24, "heatCells 与 days*24 不一致")
    check(
        sum(p.get("hours", 0) for p in phases) == stats.get("hours"),
        "阶段小时数合计不一致",
    )
    check(
        sum(p.get("files", 0) for p in phases) == stats.get("files"),
        "阶段文件数合计不一致",
    )
    check(
        all(p.get("hours", 0) > 0 for p in phases),
        "存在没有小时的阶段",
    )
    check(
        stats.get("inheritedHours", 0) == sum(1 for h in hours if h["narr"].get("inherited")),
        "继承小时数不一致",
    )
    check(
        stats.get("none", 0) == sum(1 for h in hours if h["narr"].get("v") == "none"),
        "无结果小时数不一致",
    )

    missing = []
    evidence_count = 0
    file_paths = set()
    for h in hours:
        hour = h.get("hour", "")
        narr = h.get("narr", {})
        check(bool(re.match(r"^\d{4}-\d{2}-\d{2} \d{2}$", hour)), f"{hour} 小时格式错误")
        check(narr.get("p") in phase_ids, f"{hour} 引用了未定义阶段")
        check(bool(narr.get("t")), f"{hour} 缺少标题")
        check(bool(narr.get("q")), f"{hour} 缺少问题 q")
        check(bool(narr.get("m")), f"{hour} 缺少做法 m")
        check(bool(narr.get("r")), f"{hour} 缺少结果 r")
        check(bool(narr.get("e")), f"{hour} 没有证据")
        hay = h.get("hay", "")
        check(bool(hay), f"{hour} 缺少搜索索引 hay")
        if narr.get("t"):
            check(narr["t"].lower()[:8] in hay, f"{hour} 搜索索引未包含标题")
        if narr.get("r"):
            first_number = re.search(r"\d+(?:\.\d+)?", narr["r"])
            if first_number:
                check(first_number.group(0) in hay, f"{hour} 搜索索引未包含结果数字")
        if h.get("groups"):
            name = h["groups"][0]["name"].lower()
            check(name in hay, f"{hour} 搜索索引未包含文件名")
        for ev in narr.get("e", []):
            evidence_count += 1
            resolved = ev.get("resolved", "")
            exists = ev.get("exists")
            check(bool(resolved), f"{hour} 证据 resolved 为空")
            check(".../" not in resolved, f"{hour} 证据残留 .../：{resolved}")
            check(not Path(resolved).is_absolute(), f"{hour} 证据不是相对路径：{resolved}")
            check(ev.get("raw") != "", f"{hour} 证据 raw 为空")
            raw = ev.get("raw", "")
            check(".../" not in raw, f"{hour} 证据 raw 残留 .../：{raw}")
            check(not Path(raw).is_absolute(), f"{hour} 证据 raw 不是相对路径：{raw}")
            if resolved and root:
                actual = root / resolved
                if not actual.exists():
                    exists = False
                if resolved.lower()[:8] not in hay:
                    check(False, f"{hour} 搜索索引未包含证据路径")
            if not exists:
                missing.append((hour, resolved, ev.get("note", "")))
        for f in h.get("files", []):
            check(f.get("path") not in file_paths, f"文件路径重复：{f.get('path')}")
            file_paths.add(f.get("path"))
            check(f.get("ext") is not None, f"文件缺少扩展名：{f.get('path')}")
            check(isinstance(f.get("size"), int), f"文件缺少大小：{f.get('path')}")
    check(
        stats.get("missingEvidence", 0) == len(missing),
        "stats.missingEvidence 与实际缺失数不一致",
    )
    if missing:
        message = f"证据缺失 {len(missing)} 条：" + ", ".join(
            f"{h}:{p}" for h, p, _ in missing[:8]
        )
        if args.allow_missing_evidence:
            warnings.append(message)
        else:
            failures.append(message)

    scan_stats = scan.get("stats", {})
    for key in ("files", "hours", "localGroups", "uniqueGlobal", "copies", "days"):
        check(
            stats.get(key) == scan_stats.get(key),
            f"嵌入数据 {key}={stats.get(key)} 与扫描 {scan_stats.get(key)} 不一致",
        )
    check(evidence_count > 0, "没有任何证据")
    check(len(file_paths) == stats.get("files"), "文件路径唯一数不等于文件数")

    for line in warnings:
        print(f"WARN {line}")
    if failures:
        for line in failures:
            print(f"FAIL {line}")
        print(f"FAILED {len(failures)} checks")
        raise SystemExit(1)

    print(
        "PASS "
        + json.dumps(
            {
                "hours": stats.get("hours"),
                "files": stats.get("files"),
                "localGroups": stats.get("localGroups"),
                "uniqueGlobal": stats.get("uniqueGlobal"),
                "copies": stats.get("copies"),
                "days": stats.get("days"),
                "phases": stats.get("phases"),
                "notes": stats.get("notes"),
                "evidence": evidence_count,
                "missingEvidence": len(missing),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
