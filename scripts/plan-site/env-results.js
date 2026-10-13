/* 每个任务固定一个已测 seed；数轴与总表、视频使用同一冻结快照。 */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('env-results-data').textContent);
  const levels = ['mother', 'xhard12', 'xhard14', 'xhard16', 'xhard18', 'xhard20'];
  const number = value => value === null ? '未测' : String(value);
  const displayedLevels = rows => {
    const derived = levels.slice(1).filter(level => rows[level]);
    // 严格大于才替换，实测长度相同时保留固定档序中较早的一档。
    const longest = derived.reduce((best, level) => !best || rows[level].timesteps > rows[best].timesteps ? level : best, null);
    return ['mother', ...(longest ? [longest] : [])];
  };
  const segmentLabel = (original, taskName) => {
    const value = original.trim().toLowerCase();
    if (value === 'all tasks completed') return '完成';
    if (value === 'static' || value === 'remain static') return '等待';
    if (value.startsWith('hook the cube')) return '钩块';
    if (value.startsWith('pick up the peg')) return '抓销';
    if (value.startsWith('insert the peg from the left side')) return '插左孔';
    if (value.includes('by circling around the stick')) {
      const side = value.includes('nearest left target') ? '左' : value.includes('nearest right target') ? '右' : null;
      if (side) return side + (value.includes('counterclockwise') ? '逆绕' : '顺绕');
    }
    const directions = {'move backward-left': '左后', 'move backward-right': '右后',
      'move forward-left': '左前', 'move forward-right': '右前',
      'move backward': '后移', 'move forward': '前移', 'move left': '左移', 'move right': '右移'};
    if (directions[value]) return directions[value];
    if (value.startsWith('move to the top of the left-side target')) return '左移';
    if (value.startsWith('move to the top of the right-side target')) return '右移';
    if (value.startsWith('move to the top of the button')) return '就位';
    if (value.startsWith('pick up the container')) return '抓容器';
    if (value === 'put down the container') return '放容器';
    if (value === 'put it into the bin') return '投桶';
    if (value.startsWith('press the first button')) return taskName === 'ButtonUnmaskSwap' ? '按右键' : '按首键';
    if (value.startsWith('press the second button')) return taskName === 'ButtonUnmaskSwap' ? '按左键' : '按次键';
    if (value.startsWith('press the button')) return '按键';
    if (value.startsWith('pick up ')) {
      const color = [['red', '红'], ['green', '绿'], ['blue', '蓝']].find(([word]) => value.includes(word));
      return color ? `抓${color[1]}块` : value.includes('correct cube') ? '抓对块' : '抓块';
    }
    if (/^(?:place|drop|put) /.test(value) && value.includes('target')) return '放目标';
    if (/^(?:place|drop|put) /.test(value) && value.includes('table')) return '放桌面';
    if (value === 'put it down') return '放下';
    throw new Error(`子目标缺少中文短标签：${original}`);
  };
  const svgNode = (tag, attrs, text) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const drawTimeline = (card, task, sample) => {
    const host = card.querySelector('.actual-timeline');
    const detail = card.querySelector('.timeline-detail');
    const shown = displayedLevels(sample.rows);
    const maximum = Math.max(...shown.map(level => sample.rows[level].timesteps));
    const width = 1200, left = 190, plotWidth = 980;
    const rowHeight = 182;
    const height = 62 + shown.length * rowHeight;
    const x = frame => left + frame / maximum * plotWidth;
    const svg = svgNode('svg', {
      viewBox: `0 0 ${width} ${height}`, role: 'img',
      'aria-label': `${task.task} seed ${sample.seed} ${shown.length === 1 ? '仅母档' : '母档与最长派生档'}实测数轴，最大 T ${maximum}`,
      'data-max-total': maximum, 'data-seed': sample.seed, 'data-task': task.task
    });
    svg.append(svgNode('title', {}, `${task.task}：${shown.length === 1 ? '仅母档' : '母档与最长派生档'}共用 0 至 ${maximum} 的真实录像帧轴`));
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
    for (const level of shown) {
      const row = sample.rows[level];
      const name = level === 'mother' ? '母档' : level;
      const group = svgNode('g', {class: 'timeline-row', 'data-level': level,
        'data-total': row.timesteps, 'data-missing': 'false'});
      svg.append(group);
      group.append(svgNode('rect', {x: 8, y: top, width: width - 16, height: rowHeight - 8, rx: 5, class: 'timeline-row-bg'}));
      text(group, 16, top + 17, name, {class: 'timeline-level'});
      text(group, left, top + 17,
        `T ${row.timesteps} · 窗 ${row.windows}（演示 ${row.demo_windows} ＋ 执行 ${row.exec_windows}） · 遗漏：动作 ${row.miss_units}/${row.units}，交换 ${number(row.miss_swaps)}，合计 ${number(row.miss)}`,
        {class: 'timeline-row-summary'});
      for (let i = 0; i <= 4; i++) {
        const frame = Math.round(maximum * i / 4);
        group.append(svgNode('line', {x1: x(frame), y1: top + 25, x2: x(frame), y2: top + 133, class: 'timeline-grid'}));
      }
      text(group, 16, top + 40, '演示 / 执行', {class: 'timeline-lane-label'});
      text(group, 16, top + 61, '原始子目标分段', {class: 'timeline-lane-label'});
      text(group, 16, top + 108, '33 帧 / 步长 16', {class: 'timeline-lane-label'});
      text(group, 16, top + 128, '已核实交换', {class: 'timeline-lane-label'});
      text(group, 16, top + 152, '8 个采样点', {class: 'timeline-lane-label'});

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
          `原始分段「${segmentLabel(segment.text, task.task)}」：[${segment.start}, ${segment.end}) · ${segment.demo ? '演示' : '执行'} · ${segment.text}`,
          {'data-demo': String(segment.demo), 'data-index': index});
      });
      row.missed_units.forEach(([start, end, label]) => {
        rect(group, 'timeline-missed-unit', start, end, top + 48, 18,
          `遗漏的合并动作：[${start}, ${end}) · ${label}`);
      });
      row.segments.forEach(segment => {
        const label = segmentLabel(segment.text, task.task);
        const available = x(segment.end) - x(segment.start);
        const fontSize = Math.min(10, Math.max(8.5, (available - 3) / label.length));
        const narrow = available < label.length * 8.5 + 3;
        const center = (x(segment.start) + x(segment.end)) / 2;
        const labelX = narrow ? Math.min(left + plotWidth - label.length * 5, Math.max(left + label.length * 5, center)) : center;
        if (narrow) group.append(svgNode('line', {x1: center, y1: top + 65, x2: center, y2: top + 72, class: 'timeline-label-guide'}));
        const node = text(group, labelX, top + (narrow ? 84 : 61), label,
          {'text-anchor': 'middle', class: 'timeline-segment-label',
            'data-start': segment.start, 'data-end': segment.end,
            style: `font-size:${narrow ? 10 : fontSize}px`});
        interactive(node, `原始分段「${label}」：[${segment.start}, ${segment.end}) · ${segment.text}`);
      });
      for (const [start, end, phase] of [[0, demo, 'demo'], [demo, row.timesteps, 'exec']]) {
        let index = 0;
        for (let at = start; at + 33 <= end; at += 16, index++) {
          rect(group, 'timeline-window', at, at + 33, top + 98 + index % 2 * 6, 5,
            `${phase === 'demo' ? '演示' : '执行'}窗口 ${index + 1}：[${at}, ${at + 33})，33 帧`, {'data-phase': phase});
        }
      }
      const swaps = row.swap_intervals || [];
      swaps.forEach(([start, end], index) => {
        rect(group, 'timeline-swap', start, end, top + 120, 10,
          `交换 ${index + 1}：[${start}, ${end})，${end - start} 帧`);
      });
      if (!swaps.length) text(group, left, top + 128,
        row.miss_swaps === null ? '未统计：缺少该档可核对的事件映射' : '无交换事件', {class: 'timeline-muted'});
      row.frames.forEach(frame => {
        group.append(svgNode('line', {x1: x(frame), y1: top + 26, x2: x(frame), y2: top + 140, class: 'timeline-sample-guide'}));
        const point = svgNode('circle', {class: 'timeline-sample-point', cx: x(frame), cy: top + 146, r: 3.5, 'data-frame': frame});
        group.append(interactive(point, `8 帧采样：录像索引 ${frame}`));
        text(group, x(frame), top + 163, frame, {'text-anchor': 'middle', class: 'timeline-frame-number'});
      });
      top += rowHeight;
    }
    const showDetail = event => {
      const target = event.target.closest('[data-detail]');
      if (target) detail.textContent = target.dataset.detail;
    };
    svg.addEventListener('pointerover', showDetail);
    svg.addEventListener('click', showDetail);
    host.replaceChildren(svg);
    detail.textContent = '显示母档与实测最长派生档；没有派生档时只显示母档。悬停或点选中文短标签、条带可查看完整子目标与区间。';
  };

  for (const task of data.tasks) {
    const card = document.querySelector(`.timeline-card[data-task="${task.task}"]`);
    drawTimeline(card, task, task.samples[0]);
  }
})();
