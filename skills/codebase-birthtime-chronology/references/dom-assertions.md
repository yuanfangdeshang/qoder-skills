# 浏览器 DOM 断言

静态校验只能证明 HTML 里有数据和控件，不能证明页面真的渲染、筛选和搜索可用。最终交付前必须用浏览器跑一遍 DOM 断言。

## 1. 启动本地服务器

从输出目录启动，不要从源项目根目录启动：

```bash
cd "<out>/out"
python3 -m http.server 8765 --bind 127.0.0.1
```

在 browser-use 中打开：

```text
http://127.0.0.1:8765/timeline.html
```

不要用 `file://`；本地服务器更接近真实浏览器环境，也方便检查控制台。

## 2. 基础数量断言

用 `evaluate_script` 执行下面的函数，返回值应与内嵌 `chron-data` 完全一致：

```js
() => {
  const DATA = JSON.parse(document.getElementById('chron-data').textContent);
  const q = (s) => document.querySelectorAll(s).length;
  const stats = DATA.stats;
  const failures = [];
  const eq = (name, actual, expected) => {
    if (actual !== expected) failures.push(name + ': ' + actual + ' != ' + expected);
  };
  eq('title', document.title.includes(DATA.meta.title), true);
  eq('hours', q('.chron-hour'), stats.hours);
  eq('days', q('.chron-day'), stats.days);
  eq('details', q('.chron-code'), stats.hours);
  eq('groups', q('.chron-crow'), stats.localGroups);
  eq('phases', q('.chron-phase'), stats.phases);
  eq('heat cells', q('#heatTable td'), stats.heatCells);
  eq('files', q('#ftbody tr'), stats.files);
  eq('notes', q('.chron-note'), stats.notes);
  eq('tabs', q('.chron-tab'), 4);
  eq('panels', q('.chron-panel'), 4);
  eq('files heading', document.getElementById('filesHeading').textContent, '全部' + (DATA.meta.scopeLabel || '项目文件'));
  eq('files tab', document.getElementById('tabFilesBtn').textContent, (DATA.meta.itemLabel || '文件') + '全表');
  eq('date options', q('#dateSel option'), stats.days + 1);
  eq('verdict options', q('#verdictSel option'), Object.keys(DATA.verdictLabels).length + 1);
  return {
    pass: failures.length === 0,
    failures: failures,
    counts: {
      hours: q('.chron-hour'),
      days: q('.chron-day'),
      details: q('.chron-code'),
      groups: q('.chron-crow'),
      phases: q('.chron-phase'),
      heatCells: q('#heatTable td'),
      files: q('#ftbody tr'),
      notes: q('.chron-note'),
      tabs: q('.chron-tab'),
      panels: q('.chron-panel')
    },
    stats: stats
  };
}
```

期望：

- `pass: true`，`failures: []`。
- `groups` 等于 `stats.localGroups`，不是 `stats.uniqueGlobal`。
- `heatCells` 等于 `stats.days * 24`。
- `files` 等于 `stats.files`，包含同内容副本行。

## 3. 搜索断言

搜索索引覆盖标题、问题、做法、结果、数字、文件名、路径、证据、阶段和结论。逐项测试：

```js
() => {
  const DATA = JSON.parse(document.getElementById('chron-data').textContent);
  const q = document.getElementById('q');
  const vis = () => Array.from(document.querySelectorAll('.chron-hour'))
    .filter((el) => el.style.display !== 'none').length;
  const test = (label, term) => {
    q.value = term;
    q.dispatchEvent(new Event('input', { bubbles: true }));
    return { label: label, term: term, visible: vis() };
  };
  const first = DATA.hours[0];
  const result = first.narr.r || '';
  const num = (result.match(/\d+(?:\.\d+)?/) || [''])[0];
  const ev = (first.narr.e && first.narr.e[0] && first.narr.e[0].resolved) || '';
  const out = [
    test('title', first.narr.t.slice(0, 6)),
    test('file', first.groups[0].name),
    test('number', num),
    test('evidence', ev.split('/').pop())
  ];
  q.value = '';
  q.dispatchEvent(new Event('input', { bubbles: true }));
  return { pass: out.every((x) => x.visible > 0), results: out, reset: vis() };
}
```

注意：

- 数字可能为空；若该小时结果没有数字，换一个有数字的小时。
- 证据文件名可能太短；取最后一段路径即可。
- 搜索是 `includes` 匹配，不要求高亮。
- 清空后应恢复全部小时。

## 4. 日期与结论筛选

```js
() => {
  const DATA = JSON.parse(document.getElementById('chron-data').textContent);
  const vis = () => Array.from(document.querySelectorAll('.chron-hour'))
    .filter((el) => el.style.display !== 'none').length;
  const dateSel = document.getElementById('dateSel');
  const date = DATA.days[0].date;
  const expectedDate = DATA.hours.filter((h) => h.date === date).length;
  dateSel.value = date;
  dateSel.dispatchEvent(new Event('change', { bubbles: true }));
  const dateVisible = vis();
  dateSel.value = '';
  dateSel.dispatchEvent(new Event('change', { bubbles: true }));

  const verdictSel = document.getElementById('verdictSel');
  const counts = {};
  DATA.hours.forEach((h) => { counts[h.narr.v] = (counts[h.narr.v] || 0) + 1; });
  const verdict = Object.keys(counts)[0];
  verdictSel.value = verdict;
  verdictSel.dispatchEvent(new Event('change', { bubbles: true }));
  const verdictVisible = vis();
  verdictSel.value = '';
  verdictSel.dispatchEvent(new Event('change', { bubbles: true }));

  return {
    pass: dateVisible === expectedDate && verdictVisible === counts[verdict],
    date: { value: date, expected: expectedDate, visible: dateVisible },
    verdict: { value: verdict, expected: counts[verdict], visible: verdictVisible },
    reset: vis()
  };
}
```

## 5. 页签与文件表

```js
() => {
  const DATA = JSON.parse(document.getElementById('chron-data').textContent);
  const click = (sel) => document.querySelector(sel).click();
  const visible = (id) => !document.getElementById(id).hidden;
  const out = {};

  click('[data-tab="phases"]');
  out.phases = {
    panel: visible('tab-phases'),
    timelineHidden: !visible('tab-timeline'),
    cards: document.querySelectorAll('.chron-phase').length,
    heat: document.querySelectorAll('#heatTable td').length
  };

  click('[data-tab="files"]');
  out.filesPanel = visible('tab-files');
  const rows = Array.from(document.querySelectorAll('#ftbody tr'));
  const fq = document.getElementById('fq');
  const token = rows[0].querySelector('td.path').textContent.split('/').pop().slice(0, 6);
  fq.value = token;
  fq.dispatchEvent(new Event('input', { bubbles: true }));
  out.filter = {
    token: token,
    visible: rows.filter((r) => r.style.display !== 'none').length,
    total: rows.length
  };
  fq.value = '';
  fq.dispatchEvent(new Event('input', { bubbles: true }));
  out.filterReset = rows.filter((r) => r.style.display !== 'none').length;

  click('[data-tab="method"]');
  out.method = { panel: visible('tab-method'), notes: document.querySelectorAll('.chron-note').length };

  click('[data-tab="timeline"]');
  out.timeline = visible('tab-timeline');

  out.pass = out.phases.panel && out.phases.timelineHidden &&
    out.phases.cards === DATA.stats.phases &&
    out.phases.heat === DATA.stats.heatCells &&
    out.filesPanel && out.filter.visible > 0 && out.filter.visible < out.filter.total &&
    out.filterReset === rows.length &&
    out.method.panel && out.method.notes === DATA.stats.notes &&
    out.timeline;
  return out;
}
```

## 6. 展开与折叠

```js
() => {
  const all = () => document.querySelectorAll('.chron-code').length;
  const open = () => document.querySelectorAll('.chron-code[open]').length;
  document.getElementById('expandAll').click();
  const expanded = open();
  document.getElementById('collapseAll').click();
  const collapsed = open();
  return { pass: expanded === all() && collapsed === 0, all: all(), expanded: expanded, collapsed: collapsed };
}
```

## 7. 控制台

用 browser-use 的 `list_console_messages` 检查：

- 不允许出现 `error` 级别的 JavaScript 异常。
- 允许忽略 favicon 404 等与页面逻辑无关的网络噪音；在日志中说明忽略项。
- 若页面有 CSP 或本地服务器 404，先修资源路径，不要用“截图正常”掩盖。

## 8. 截图

`take_screenshot` 在应用内浏览器视口不可见时可能失败。失败时：

1. 记录失败原因。
2. 确认前面的 DOM 数量和交互断言已通过。
3. 不要声称“已通过视觉检查”；只声称“DOM 断言通过，截图不可用”。

## 9. 结果记录

把每个断言返回的 JSON 写入 `<out>/logs/dom.json`，至少包含：

- 基础数量断言的 `pass`、`failures`、`counts`、`stats`。
- 搜索、日期/结论筛选、页签、文件过滤、展开/折叠的 `pass`。
- 控制台 error 数量和忽略项。
- 浏览器与视口信息（如可获得）。

最终报告引用这些结果；如果任何一项失败，先修复再交付。
