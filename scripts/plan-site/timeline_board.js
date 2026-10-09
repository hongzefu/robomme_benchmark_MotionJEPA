// 数轴的浏览器内渲染（替代 matplotlib PNG）：画法同 vis/v2_plot.py::draw_track 与 vis/site_template.html::drawTrack。
// 数据由 scripts/plan-site/align_section.py 内联进根计划为 window.TL_DATA；页面里每个 <div class="tl-board" data-board="<键>"> 画一张（一图一轴）。
(function () {
  const DATA = window.TL_DATA;
  if (!DATA) return;
  const C = DATA.color, SW = DATA.swap_colors, WIN = DATA.win, STRIDE = DATA.stride;
  const NS = "http://www.w3.org/2000/svg";
  const SIMPLE = !!DATA.simple;  // 简化模式：数轴内部原样（窗口、32 帧、8 帧、分段、swap），去掉左右两栏文字与图例
  const LEFT = SIMPLE ? 20 : 230, AXIS = 1240, RIGHT = SIMPLE ? 20 : 190, ROW = 78, HEAD = 28;

  function el(tag, attrs, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  const winStarts = L => { const o = []; for (let f = 0; f < Math.max(0, L - (WIN - 1)); f += STRIDE) o.push(f); return o; };
  const framePath = (T, n) => Array.from({length: n}, (_, i) => Math.floor(i * (T - 1) / (n - 1) + 0.5));
  const phases = r => r.demo ? [[0, r.demo, "demo"], [r.demo, r.total - r.demo, "exec"]] : [[0, r.total, "exec"]];

  function drawTrack(g, r, y, sx) {
    for (const [s, L, k] of phases(r)) {
      el("rect", {x: sx(s), y: y + 3, width: sx(s + L) - sx(s), height: ROW - 8, fill: C[k], "fill-opacity": .09}, g);
      el("line", {x1: sx(s), x2: sx(s), y1: y + 3, y2: y + ROW - 5, stroke: C[k], "stroke-opacity": .7}, g);
    }
    // swap 事件：贯穿整行的半透明竖带，顶部小字「换k a↔b」；校验不过画虚线空框
    r.swaps.forEach(([a, b, lab], k) => {
      const col = SW[k % SW.length];
      const rc = el("rect", {x: sx(a), y: y + 3, width: Math.max(1, sx(b) - sx(a)), height: ROW - 8, fill: r.swap_ok ? col : "none",
        "fill-opacity": .18, stroke: col, "stroke-width": .8, "stroke-dasharray": r.swap_ok ? "" : "4 3"}, g);
      el("title", {}, rc, `第 ${k + 1} 次 swap：${a}–${b}${lab ? "（" + lab + "）" : ""}`);
      const txt = `换${k + 1}${lab ? " " + lab : ""}`;
      el("text", {x: (sx(a) + sx(b)) / 2, y: y + 12, "text-anchor": "middle", "font-size": 10, fill: col, "font-weight": 700},
         g, (sx(b) - sx(a)) > txt.length * 7 ? txt : String(k + 1));
    });
    // 32 帧帧路（紫竖线）与 8 帧帧路（红点）
    for (const f of framePath(r.total, DATA.budgets[0]))
      el("line", {x1: sx(f), x2: sx(f), y1: y + 15, y2: y + 23, stroke: C.f32, "stroke-width": 1}, g);
    for (const f of framePath(r.total, DATA.budgets[1])) {
      const c = el("circle", {cx: sx(f), cy: y + 28, r: 3, fill: C.f8}, g);
      el("title", {}, c, `8 帧帧路 timestep ${f}`);
    }
    // 窗口：demo 蓝 / exec 绿，三行堆叠；段短于窗口时画虚线空框
    for (const [s, L, k] of phases(r)) {
      const st = winStarts(L);
      if (!st.length) { el("rect", {x: sx(s), y: y + 35, width: Math.max(2, sx(s + L) - sx(s)), height: 14, fill: "none", stroke: C.empty, "stroke-dasharray": "4 3"}, g); continue; }
      st.forEach((f, i) => el("rect", {x: sx(s + f), y: y + 46 - (i % 3) * 6, width: sx(s + f + WIN - 1) - sx(s + f), height: 4.5,
        fill: C[k], "fill-opacity": .9, stroke: "#fff", "stroke-width": .4}, g));
    }
    // subgoal 分段（悬停看英文全文与起止 timestep）
    r.segs.forEach(([s, L, lab, full], i) => {
      const w = sx(s + L) - sx(s);
      const rc = el("rect", {x: sx(s), y: y + 54, width: w, height: 17, fill: i % 2 ? C.sg_b : C.sg_a, stroke: C.sg_line, "stroke-width": .5}, g);
      el("title", {}, rc, `${full}\n${s}–${s + L}（${L} timestep）`);
      const shown = w >= lab.length * 11 + 4 ? lab : (w >= 14 ? lab[0] : "");
      if (shown) el("text", {x: sx(s) + w / 2, y: y + 66.5, "text-anchor": "middle", "font-size": 10.5, fill: C.ink2, "pointer-events": "none"}, g, shown);
    });
  }

  function drawBoard(host, bd) {
    host.innerHTML = "";
    const width = LEFT + AXIS + RIGHT;
    const height = bd.items.reduce((h, x) => h + (x.kind === "head" ? HEAD : ROW), 0) + (SIMPLE ? 18 : 34);
    const svg = el("svg", {viewBox: `0 0 ${width} ${height}`, width: "100%", preserveAspectRatio: "xMinYMin meet",
      style: `display:block;min-width:${SIMPLE ? 900 : 1100}px;font-family:inherit`, role: "img", "aria-label": bd.title}, host);
    const sx = v => LEFT + v / bd.xmax * AXIS;
    const step = bd.xmax <= 1200 ? 100 : 200;
    const top = 4;
    for (let t = 0; t <= bd.xmax; t += step) {
      el("line", {x1: sx(t), x2: sx(t), y1: top, y2: height - (SIMPLE ? 14 : 30), stroke: "#EEF2F0"}, svg);
      el("text", {x: sx(t), y: height - (SIMPLE ? 2 : 14), "text-anchor": "middle", "font-size": 11.5, fill: C.ink3}, svg, t);
    }
    if (!SIMPLE) el("text", {x: LEFT + AXIS / 2, y: height - 1, "text-anchor": "middle", "font-size": 12, fill: C.ink2}, svg, "timestep");
    let y = top;
    for (const x of bd.items) {
      if (x.kind === "head") {
        el("rect", {x: LEFT, y: y + 4, width: AXIS, height: HEAD - 8, fill: "#F0F3F1"}, svg);
        el("text", {x: LEFT + 6, y: y + 19, "font-size": 12.5, "font-weight": 700, fill: C.ink}, svg, x.text);
        y += HEAD; continue;
      }
      const r = x.r;
      drawTrack(el("g", {}, svg), r, y, sx);
      if (!SIMPLE) x.left.forEach((t, i) => el("text", {x: LEFT - 10, y: y + 16 + i * 15, "text-anchor": "end", "font-size": i === 0 ? 12.5 : 11.5,
        "font-weight": i === 0 ? 700 : 400, fill: i === 0 ? C.ink : C.ink3}, svg, t));
      const [d, e] = r.windows;
      const right = SIMPLE ? [] : [`timestep ${r.total}${r.orig ? `（2×${r.orig}）` : ""}`, `窗口 ${d}+${e}=${d + e}`,
        `Δ32 ${((r.total - 1) / 31).toFixed(1)} · Δ8 ${((r.total - 1) / 7).toFixed(1)}`];
      right.forEach((t, i) => el("text", {x: LEFT + AXIS + 10, y: y + 22 + i * 16, "font-size": i === 0 ? 12.5 : 11.5,
        "font-weight": i === 0 ? 700 : 400, fill: i === 0 ? C.ink : C.ink2}, svg, t));
      el("line", {x1: 0, x2: width, y1: y + ROW, y2: y + ROW, stroke: "#EBF0EE"}, svg);
      y += ROW;
    }
  }

  function legend() {
    if (SIMPLE) return "";
    const items = [[C.demo, "demo 段窗口 [f, f+32]"], [C.exec, "exec 段窗口（stride 16，堆 3 行）"], [C.f32, "32 帧帧路（竖线）"],
      [C.f8, "8 帧帧路（圆点）"], [C.sg_a, "subgoal 分段（悬停看全文与 timestep）"], ...SW.map((c, k) => [c, `第 ${k + 1} 次 swap`])];
    return items.map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("");
  }

  document.querySelectorAll(".tl-board").forEach(host => {
    const bd = DATA.boards[host.dataset.board];
    if (!bd) { host.textContent = `缺少数轴数据：${host.dataset.board}`; return; }
    const fig = host.closest("figure");
    const cap = fig && fig.querySelector(".tl-sub");
    if (cap) cap.textContent = bd.sub;
    const lg = fig && fig.querySelector(".tl-legend");
    if (lg) lg.innerHTML = legend();
    drawBoard(host, bd);
  });
})();
