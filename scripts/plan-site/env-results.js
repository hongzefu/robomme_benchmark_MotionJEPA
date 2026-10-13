/* 切换同一任务的已有 seed，同时更新录像、来源与全部实测指标。 */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('env-results-data').textContent);
  const levels = ['mother', 'xhard12', 'xhard14', 'xhard16', 'xhard18', 'xhard20'];
  const number = value => value === null ? '未测' : String(value);
  const metricKeys = ['knob', 'expected-T', 'expected-windows', 'actual-T', 'windows', 'ratio', 'miss-actions', 'miss-swaps', 'miss-total'];
  const cell = (row, value, detail) => {
    const node = document.createElement('td');
    node.dataset.metric = metricKeys[row.querySelectorAll('td').length];
    node.textContent = value;
    if (detail) {
      const small = document.createElement('small');
      small.textContent = detail;
      node.append(small);
    }
    row.append(node);
  };
  for (const task of data.tasks) {
    const card = document.querySelector(`.env-card[data-task="${task.task}"]`);
    const select = card.querySelector('select');
    select.addEventListener('change', () => {
      const sample = task.samples.find(item => String(item.seed) === select.value);
      if (!sample) throw new Error('所选 seed 不在冻结样本中');
      card.dataset.seed = String(sample.seed);
      const video = card.querySelector('video');
      video.pause();
      video.src = sample.video;
      video.setAttribute('aria-label', `${task.task} seed ${sample.seed} 六列对照视频`);
      video.load();
      card.querySelector('.sample-source').textContent = `来源：${sample.batch} · seed ${sample.seed} · episode ${sample.episode}`;
      const body = card.querySelector('tbody');
      body.replaceChildren();
      for (const level of levels) {
        const row = document.createElement('tr');
        const label = document.createElement('th');
        label.textContent = level === 'mother' ? '母档' : level;
        row.append(label);
        const expected = task.expected[level];
        if (!expected) {
          row.className = 'unconfigured';
          const missing = document.createElement('td');
          missing.colSpan = 9;
          missing.textContent = '缺档：无独立配置';
          row.append(missing);
        } else {
          row.dataset.level = level;
          const real = sample.rows[level];
          if (!real) throw new Error('已配置档位缺少实测行');
          cell(row, expected.knob);
          cell(row, number(expected.timesteps));
          cell(row, expected.windows === null ? '待算' : number(expected.windows));
          cell(row, number(real.timesteps), `演示 ${real.demo_timesteps} ＋ 执行 ${real.exec_timesteps}`);
          cell(row, number(real.windows), `演示 ${real.demo_windows} ＋ 执行 ${real.exec_windows}`);
          cell(row, `${real.ratio_timesteps.toFixed(3)}×`, `窗口 ${real.ratio_windows.toFixed(3)}×`);
          cell(row, `${real.miss_units} / ${real.units}`);
          cell(row, number(real.miss_swaps));
          cell(row, number(real.miss));
        }
        body.append(row);
      }
      card.querySelector('.swap-note').textContent = [...new Set(Object.values(sample.rows).map(row => row.swap_reason))].join(' ');
    });
  }
})();
