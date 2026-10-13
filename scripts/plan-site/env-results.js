/* 每个任务固定一个已测 seed；数轴与总表、视频使用同一冻结快照。 */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('env-results-data').textContent);
  const levels = ['mother', 'xhard12', 'xhard14', 'xhard16', 'xhard18', 'xhard20'];
  const number = value => value === null ? '未测' : String(value);
  const svgNode = (tag, attrs, text) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const drawTimeline = (card, task, sample) => {
    const host = card.querySelector('.actual-timeline');
    const detail = card.querySelector('.timeline-detail');
    const maximum = Math.max(...Object.values(sample.rows).map(row => row.timesteps));
    const width = 1200, left = 190, plotWidth = 980;
    const height = 62 + levels.reduce((sum, level) => sum + (sample.rows[level] ? 158 : 52), 0);
    const x = frame => left + frame / maximum * plotWidth;
    const svg = svgNode('svg', {
      viewBox: `0 0 ${width} ${height}`, role: 'img',
      'aria-label': `${task.task} seed ${sample.seed} 六档实测数轴，最大 T ${maximum}`,
      'data-max-total': maximum, 'data-seed': sample.seed, 'data-task': task.task
    });
    svg.append(svgNode('title', {}, `${task.task}：各档共用 0 至 ${maximum} 的真实录像帧轴`));
    const text = (parent, tx, ty, value, attrs = {}) => {
      const node = svgNode('text', {x: tx, y: ty, ...attrs}, value);
      parent.append(node);
      return node;
    };
    const interactive = (node, description) => {
      node.append(svgNode('title', {}, description));
      node.dataset.detail = description;
      return node;
    };
    const rect = (parent, className, start, end, y, barHeight, description, attrs = {}) => {
      const node = svgNode('rect', {class: className, x: x(start), y,
        width: x(end) - x(start), height: barHeight,
        'data-start': start, 'data-end': end, ...attrs});
      interactive(node, description);
      parent.append(node);
      return node;
    };
    text(svg, 16, 25, '绝对录像帧索引', {class: 'timeline-axis-title'});
    svg.append(svgNode('line', {x1: left, y1: 35, x2: left + plotWidth, y2: 35, class: 'timeline-axis'}));
    for (let i = 0; i <= 4; i++) {
      const frame = Math.round(maximum * i / 4);
      svg.append(svgNode('line', {x1: x(frame), y1: 30, x2: x(frame), y2: 39, class: 'timeline-axis'}));
      text(svg, x(frame), 22, frame, {'text-anchor': i === 0 ? 'start' : i === 4 ? 'end' : 'middle', class: 'timeline-tick'});
    }
    let top = 48;
    for (const level of levels) {
      const row = sample.rows[level];
      const name = level === 'mother' ? '母档' : level;
      const group = svgNode('g', {class: 'timeline-row', 'data-level': level,
        'data-total': row ? row.timesteps : '', 'data-missing': row ? 'false' : 'true'});
      svg.append(group);
      if (!row) {
        group.append(svgNode('rect', {x: 8, y: top, width: width - 16, height: 42, rx: 5, class: 'timeline-empty'}));
        text(group, 16, top + 26, name, {class: 'timeline-level'});
        text(group, left, top + 26, '缺档：无独立配置', {class: 'timeline-muted'});
        top += 52;
        continue;
      }
      group.append(svgNode('rect', {x: 8, y: top, width: width - 16, height: 150, rx: 5, class: 'timeline-row-bg'}));
      text(group, 16, top + 17, name, {class: 'timeline-level'});
      text(group, left, top + 17,
        `T ${row.timesteps} · 窗 ${row.windows}（演示 ${row.demo_windows} ＋ 执行 ${row.exec_windows}） · 遗漏：动作 ${row.miss_units}/${row.units}，交换 ${number(row.miss_swaps)}，合计 ${number(row.miss)}`,
        {class: 'timeline-row-summary'});
      for (let i = 0; i <= 4; i++) {
        const frame = Math.round(maximum * i / 4);
        group.append(svgNode('line', {x1: x(frame), y1: top + 25, x2: x(frame), y2: top + 109, class: 'timeline-grid'}));
      }
      text(group, 16, top + 40, '演示 / 执行', {class: 'timeline-lane-label'});
      text(group, 16, top + 61, '原始子目标分段', {class: 'timeline-lane-label'});
      text(group, 16, top + 84, '33 帧 / 步长 16', {class: 'timeline-lane-label'});
      text(group, 16, top + 104, '已核实交换', {class: 'timeline-lane-label'});
      text(group, 16, top + 128, '8 个采样点', {class: 'timeline-lane-label'});

      const demo = row.demo_timesteps;
      for (const [start, end, phase, name] of [[0, demo, 'demo', '演示'], [demo, row.timesteps, 'exec', '执行']]) {
        if (end <= start) continue;
        rect(group, `timeline-phase timeline-${phase}`, start, end, top + 29, 14,
          `${name}：[${start}, ${end})，${end - start} 帧`, {'data-phase': phase});
        if (x(end) - x(start) > 65) text(group, (x(start) + x(end)) / 2, top + 40, `${name} ${end - start}`,
          {'text-anchor': 'middle', class: 'timeline-phase-label'});
      }
      row.segments.forEach((segment, index) => {
        rect(group, `timeline-subgoal timeline-subgoal-${index % 2}`, segment.start, segment.end, top + 50, 14,
          `原始分段 ${index + 1}：[${segment.start}, ${segment.end}) · ${segment.demo ? '演示' : '执行'} · ${segment.text}`,
          {'data-demo': String(segment.demo), 'data-index': index});
      });
      row.missed_units.forEach(([start, end, label]) => {
        rect(group, 'timeline-missed-unit', start, end, top + 48, 18,
          `遗漏的合并动作：[${start}, ${end}) · ${label}`);
      });
      row.segments.forEach((segment, index) => {
        if (x(segment.end) - x(segment.start) >= 24) text(group, (x(segment.start) + x(segment.end)) / 2, top + 61, index + 1,
          {'text-anchor': 'middle', class: 'timeline-segment-number'});
      });
      for (const [start, end, phase] of [[0, demo, 'demo'], [demo, row.timesteps, 'exec']]) {
        let index = 0;
        for (let at = start; at + 33 <= end; at += 16, index++) {
          rect(group, 'timeline-window', at, at + 33, top + 74 + index % 2 * 6, 5,
            `${phase === 'demo' ? '演示' : '执行'}窗口 ${index + 1}：[${at}, ${at + 33})，33 帧`, {'data-phase': phase});
        }
      }
      const swaps = row.swap_intervals || [];
      swaps.forEach(([start, end], index) => {
        rect(group, 'timeline-swap', start, end, top + 96, 10,
          `交换 ${index + 1}：[${start}, ${end})，${end - start} 帧`);
      });
      if (!swaps.length) text(group, left, top + 104,
        row.miss_swaps === null ? '未统计：缺少该档可核对的事件映射' : '无交换事件', {class: 'timeline-muted'});
      row.frames.forEach(frame => {
        group.append(svgNode('line', {x1: x(frame), y1: top + 26, x2: x(frame), y2: top + 116, class: 'timeline-sample-guide'}));
        const point = svgNode('circle', {class: 'timeline-sample-point', cx: x(frame), cy: top + 122, r: 3.5, 'data-frame': frame});
        group.append(interactive(point, `8 帧采样：录像索引 ${frame}`));
        text(group, x(frame), top + 139, frame, {'text-anchor': 'middle', class: 'timeline-frame-number'});
      });
      top += 158;
    }
    const showDetail = event => {
      const target = event.target.closest('[data-detail]');
      if (target) detail.textContent = target.dataset.detail;
    };
    svg.addEventListener('pointerover', showDetail);
    svg.addEventListener('click', showDetail);
    host.replaceChildren(svg);
    detail.textContent = '悬停或点选图中条带查看详情；分段编号仅表示 H5 原始分段顺序。';
  };

  for (const task of data.tasks) {
    const card = document.querySelector(`.timeline-card[data-task="${task.task}"]`);
    drawTimeline(card, task, task.samples[0]);
  }
})();
