"""生成交互式采样窗口数轴的 HTML（供 Artifact 发布）。

内容与 plot_sampling_windows.py 同源：四任务 × 三难度 × {最短, 中位, 最长} 共 36 行。
区别是这里可交互——难度档切换、悬停看 subgoal 原文，且所有难度档共用同一根固定横轴，
切档时行的长度可以直接横比。

窗口起点与帧路不预先展开，只内联每条 episode 的 (total, demo, segments)，由页面脚本按同一套
公式现算，保证与报告口径一致：窗口 [f, f+32]、stride 16、不跨段；帧路 linspace(0, t, N)。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TASKS = ["PatternLock", "RouteStick", "BinFill", "PickXtimes"]
SUITES = {"PatternLock": "Imitation", "RouteStick": "Imitation",
          "BinFill": "Counting", "PickXtimes": "Counting"}
DIFFICULTIES = ["easy", "medium", "hard"]


def load(paths: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for kind, files in paths.items():
        for file in files:
            for key, rows in json.loads(Path(file).read_text(encoding="utf-8")).items():
                task, _, split = key.partition("-")
                for episode, row in rows.items():
                    out.setdefault(task, []).append(
                        {
                            "split": split,
                            "ep": int(episode),
                            "seed": row["seed"],
                            "diff": row["difficulty"],
                            "total": row["n_timesteps_total"],
                            "demo": sum(row["demo_durations"]) if kind == "imitation" else 0,
                            "segs": [
                                [s["start_timestep"], s["n_timesteps"], s["subgoal"]]
                                for s in row["segments"]
                            ],
                        }
                    )
    return out


def pick(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    picked = []
    for level in DIFFICULTIES:
        group = sorted([e for e in episodes if e["diff"] == level], key=lambda e: e["total"])
        if not group:
            continue
        for label, item in (("最短", group[0]), ("中位", group[len(group) // 2]), ("最长", group[-1])):
            picked.append({**item, "band": label})
    return picked


PAGE = """<title>采样窗口数轴</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root{
    --ground:#F4F6F4; --surface:#FFFFFF; --surface-2:#F8FAF9;
    --ink:#14181A; --ink-2:#48534F; --ink-3:#7B8783;
    --rule:#DDE4E1; --rule-2:#EBF0EE;
    --demo:#3E7FA8; --exec:#4E9B7C; --f32:#7B6FC9; --f8:#C2593E; --empty:#C9713D;
    --sg-a:#DDE3E0; --sg-b:#EEF2F0; --sg-line:#A3AFAA;
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --ground:#0F1413; --surface:#161C1A; --surface-2:#1C2321;
      --ink:#E6EDEA; --ink-2:#A5B2AD; --ink-3:#78857F;
      --rule:#28312E; --rule-2:#202826;
      --demo:#57A0C6; --exec:#6DBE9B; --f32:#9A90E4; --f8:#DE7A5E; --empty:#DB8B54;
      --sg-a:#313B38; --sg-b:#242C2A; --sg-line:#5D6A65;
    }
  }
  :root[data-theme="dark"]{
    --ground:#0F1413; --surface:#161C1A; --surface-2:#1C2321;
    --ink:#E6EDEA; --ink-2:#A5B2AD; --ink-3:#78857F;
    --rule:#28312E; --rule-2:#202826;
    --demo:#57A0C6; --exec:#6DBE9B; --f32:#9A90E4; --f8:#DE7A5E; --empty:#DB8B54;
    --sg-a:#313B38; --sg-b:#242C2A; --sg-line:#5D6A65;
  }
  *{box-sizing:border-box}
  body{
    background:var(--ground); color:var(--ink); margin:0; padding:26px 22px 44px;
    font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    font-size:14px; line-height:1.55;
  }
  .wrap{max-width:1680px; margin:0 auto; display:flex; flex-direction:column; gap:18px}
  h1{font-size:23px; font-weight:600; letter-spacing:-.015em; margin:0; text-wrap:balance}
  .sub{color:var(--ink-2); max-width:74ch; margin:0}
  code,.mono{font-family:"IBM Plex Mono",ui-monospace,monospace}
  code{font-size:12.5px; color:var(--ink)}
  .chips{display:flex; flex-wrap:wrap; gap:6px}
  .chip{
    font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-2);
    border:1px solid var(--rule); border-radius:3px; padding:3px 8px; background:var(--surface);
    font-variant-numeric:tabular-nums;
  }
  .chip b{color:var(--ink); font-weight:500}
  .tabs{display:flex; gap:6px; flex-wrap:wrap; align-items:center}
  .tabs .lbl{font-size:12px; color:var(--ink-3); margin-right:2px}
  .tab{
    font-family:"IBM Plex Mono",monospace; font-size:12px; color:var(--ink-2);
    background:var(--surface); border:1px solid var(--rule); border-radius:3px;
    padding:5px 12px; cursor:pointer;
  }
  .tab:hover{border-color:var(--ink-3)}
  .tab:focus-visible{outline:2px solid var(--exec); outline-offset:1px}
  .tab[aria-pressed="true"]{background:var(--ink); color:var(--ground); border-color:var(--ink); font-weight:600}
  .legend{
    display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; padding:10px 13px;
    background:var(--surface); border:1px solid var(--rule); border-radius:4px;
  }
  .lg{display:flex; align-items:center; gap:7px; font-size:12px; color:var(--ink-2)}
  .sw{width:24px; height:9px; border-radius:1.5px; flex:none}
  .sw.demo{background:var(--demo)} .sw.exec{background:var(--exec)}
  .sw.sg{background:linear-gradient(90deg,var(--sg-a) 0 50%,var(--sg-b) 50%)}
  .sw.f32{height:13px; width:20px; border-radius:0;
    background:repeating-linear-gradient(90deg,var(--f32) 0 1.4px,transparent 1.4px 4px)}
  .sw.f8{height:7px; width:7px; border-radius:50%; background:var(--f8)}
  .sw.empty{background:transparent; border:1.3px dashed var(--empty); height:11px}
  .board{background:var(--surface); border:1px solid var(--rule); border-radius:5px; overflow:hidden}
  .suite{
    display:flex; align-items:baseline; gap:11px; padding:9px 15px; background:var(--surface-2);
    border-top:1px solid var(--rule); border-bottom:1px solid var(--rule);
  }
  .board > .suite:first-child{border-top:none}
  .suite .nm{font-size:13px; font-weight:600; letter-spacing:.03em}
  .suite .dt{font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--ink-3)}
  .row{display:grid; grid-template-columns:132px 1fr 232px; border-bottom:1px solid var(--rule-2); align-items:center}
  .row:last-child{border-bottom:none}
  .rl{padding:9px 0 9px 15px; display:flex; flex-direction:column; gap:2px}
  .rl .bd{font-size:12.5px; font-weight:600}
  .rl .src{font-family:"IBM Plex Mono",monospace; font-size:10.5px; color:var(--ink-3)}
  .track{position:relative; height:52px; margin:5px 0}
  .track .seg-bg{position:absolute; top:0; height:100%; opacity:.09}
  .track .seg-edge{position:absolute; top:0; height:100%; width:1px}
  .track .sg{
    position:absolute; bottom:0; height:15px; border:.5px solid var(--sg-line);
    font-size:9.5px; line-height:14px; text-align:center; overflow:hidden; white-space:nowrap;
    color:var(--ink-2); cursor:default;
  }
  .track .win{position:absolute; height:5px; border-radius:1px; opacity:.8}
  .track .win-empty{position:absolute; height:12px; border:1px dashed var(--empty); border-radius:2px}
  .track .f32{position:absolute; top:0; width:1px; height:9px; background:var(--f32); opacity:.85}
  .track .f8{position:absolute; width:4px; height:4px; border-radius:50%; background:var(--f8); margin-left:-2px}
  .rr{
    padding:9px 15px 9px 10px; font-family:"IBM Plex Mono",monospace; font-size:11px;
    color:var(--ink-2); font-variant-numeric:tabular-nums; display:flex; flex-direction:column; gap:2px;
    text-align:right;
  }
  .rr b{color:var(--ink); font-weight:600}
  .rr .zero{color:var(--empty); font-weight:600}
  .axis{
    display:grid; grid-template-columns:132px 1fr 232px; background:var(--surface-2);
    border-top:1px solid var(--rule);
  }
  .axis .ticks{position:relative; height:26px}
  .axis .tk{position:absolute; top:5px; font-family:"IBM Plex Mono",monospace; font-size:10.5px; color:var(--ink-3)}
  .axis .tk i{position:absolute; left:0; top:-5px; width:1px; height:5px; background:var(--rule); display:block}
  footer{color:var(--ink-3); font-size:12px; border-top:1px solid var(--rule); padding-top:13px; line-height:1.75}
  footer code{color:var(--ink-2)}
  @media (max-width:900px){
    body{padding:20px 12px 36px}
    .row,.axis{grid-template-columns:104px 1fr 150px}
    .rr{font-size:10px}
  }
</style>

<div class="wrap">
  <header style="display:flex;flex-direction:column;gap:9px">
    <h1>采样窗口数轴</h1>
    <p class="sub">RoboMME 四个任务的 <b>test + val 合并</b>（每任务 100 条）里，按整条长度取
      <b>最短 / 中位 / 最长</b>三条，看 motion 窗口、subgoal 分段与两条帧路在同一根时间轴上怎么排布。
      横轴在四个难度档之间<b>固定不变</b>，可直接横比。悬停 subgoal 块看原文。</p>
    <div class="chips" id="chips"></div>
    <div class="tabs" id="tabs"><span class="lbl">难度档</span></div>
  </header>

  <div class="legend">
    <div class="lg"><span class="sw demo"></span>demo 段与其窗口</div>
    <div class="lg"><span class="sw exec"></span>exec 段与其窗口</div>
    <div class="lg"><span class="sw sg"></span>subgoal 分段（悬停看原文）</div>
    <div class="lg"><span class="sw f32"></span>帧路 N=32</div>
    <div class="lg"><span class="sw f8"></span>帧路 N=8</div>
    <div class="lg"><span class="sw empty"></span>段 &lt; 33 帧，铺不出窗口</div>
  </div>

  <div class="board" id="board"></div>

  <footer>
    窗口口径：<code>[f, f+32]</code>（33 帧）、stride <code>16</code>、<b>不跨段</b>——demo 与 exec 各自从段起点铺，
    每段窗口数 <code>len(range(0, max(0, L-32), 16))</code>，一条 episode 的 motion token = demo 窗口 + exec 窗口。
    帧路：<code>linspace(0, t, N)</code>（<code>t = T-1</code>），Δ = <code>t/(N-1)</code>；N=32 与 N=8 是帧预算
    （<code>512 // (16×1)</code> 与 <code>128 // (16×1)</code>），<b>不是</b>切分步长。<br>
    数据来自本仓库 <code>scripts/patternlock-routestick-params/</code>：val 取原版 h5，test 按 metadata 死 seed 实跑，
    逐条读 <code>info/is_subgoal_boundary</code> 与 <code>info/is_video_demo</code>。
    该套公式已用 policy 侧 16 个任务的中位集逐条对拍，窗口数与 Δ 全部一致。
    <span id="foot"></span>
  </footer>
</div>

<script>
const DATA = __DATA__;
const WIN = 33, STRIDE = 16, BUDGETS = [32, 8];
const DIFFS = ["all", "easy", "medium", "hard"];
const SUITES = __SUITES__;

const winStarts = L => { const o = []; for (let f = 0; f + WIN - 1 < L; f += STRIDE) o.push(f); return o; };
const framePath = (T, N) => { const t = T - 1, o = []; for (let i = 0; i < N; i++) o.push(Math.round(i * t / (N - 1))); return o; };
const XMAX = Math.max(...Object.values(DATA).flat().map(r => r.total));

function track(row){
  const el = document.createElement("div");
  el.className = "track";
  const pct = v => (v / XMAX * 100) + "%";
  const segs = row.demo ? [[0, row.demo, "demo"], [row.demo, row.total - row.demo, "exec"]]
                        : [[0, row.total, "exec"]];
  for (const [start, len, kind] of segs){
    const bg = document.createElement("div");
    bg.className = "seg-bg";
    bg.style.left = pct(start); bg.style.width = pct(len);
    bg.style.background = `var(--${kind})`;
    el.appendChild(bg);
    const edge = document.createElement("div");
    edge.className = "seg-edge";
    edge.style.left = pct(start); edge.style.background = `var(--${kind})`;
    el.appendChild(edge);
  }
  for (let i = 0; i < row.segs.length; i++){
    const [start, len, text] = row.segs[i];
    const d = document.createElement("div");
    d.className = "sg";
    d.style.left = pct(start); d.style.width = pct(len);
    d.style.background = i % 2 ? "var(--sg-b)" : "var(--sg-a)";
    d.title = text;
    if (len / XMAX > 0.035) d.textContent = shortLabel(text);
    el.appendChild(d);
  }
  // 窗口重叠 50%，奇偶分两行错开才数得出个数
  for (const [start, len, kind] of segs){
    const starts = winStarts(len);
    if (!starts.length){
      const e = document.createElement("div");
      e.className = "win-empty";
      e.style.left = pct(start); e.style.width = pct(Math.max(len, 1)); e.style.bottom = "17px";
      e.title = `${kind} 段只有 ${len} 帧，短于窗口所需的 ${WIN} 帧，铺不出窗口`;
      el.appendChild(e);
      continue;
    }
    starts.forEach((f, i) => {
      const w = document.createElement("div");
      w.className = "win";
      w.style.left = pct(start + f); w.style.width = pct(WIN - 1);
      w.style.bottom = (i % 2 ? 24 : 17) + "px";
      w.style.background = `var(--${kind})`;
      el.appendChild(w);
    });
  }
  for (const i of framePath(row.total, 32)){
    const f = document.createElement("div");
    f.className = "f32"; f.style.left = pct(i); el.appendChild(f);
  }
  for (const i of framePath(row.total, 8)){
    const f = document.createElement("div");
    f.className = "f8"; f.style.left = pct(i); f.style.bottom = "32px"; el.appendChild(f);
  }
  return el;
}

const RULES = [
  [/^move to the nearest (left|right) target.*counterclockwise$/i, m => "绕" + dir(m[1]) + "逆"],
  [/^move to the nearest (left|right) target.*clockwise$/i, m => "绕" + dir(m[1]) + "顺"],
  [/^move ([a-z-]+)$/i, m => "移" + dir(m[1])],
  [/^pick up the (\\w+) (red|blue|green) cube$/i, m => "抓" + col(m[2]) + ord(m[1])],
  [/^pick up the (red|blue|green) cube for the (\\w+) time$/i, m => "抓" + col(m[1]) + ord(m[2])],
  [/^put it into the bin$/i, () => "投箱"],
  [/^place the (red|blue|green) cube onto the target$/i, m => "置" + col(m[1]) + "标"],
  [/^press the button to stop$/i, () => "按钮停"],
  [/^press the button$/i, () => "按钮"],
  [/^All tasks completed$/i, () => "完成"],
];
const DIRS = {"backward-left":"后左","backward-right":"后右","forward-left":"前左","forward-right":"前右",
  "backward":"后","forward":"前","left":"左","right":"右"};
const ORDS = {first:"1",second:"2",third:"3",fourth:"4",fifth:"5",sixth:"6",seventh:"7"};
const COLS = {red:"红",blue:"蓝",green:"绿"};
const dir = s => DIRS[s.toLowerCase()] || s;
const ord = s => ORDS[s.toLowerCase()] || s;
const col = s => COLS[s.toLowerCase()] || s;
function shortLabel(text){
  for (const [re, fn] of RULES){ const m = text.match(re); if (m) return fn(m); }
  return text.slice(0, 6);
}

function render(diff){
  const board = document.getElementById("board");
  board.innerHTML = "";
  let shown = 0, tokens = 0;
  for (const suite of ["Imitation", "Counting"]){
    const tasks = Object.keys(DATA).filter(t => SUITES[t] === suite);
    const rows = tasks.flatMap(t => DATA[t].filter(r => diff === "all" || r.diff === diff).map(r => [t, r]));
    if (!rows.length) continue;
    const head = document.createElement("div");
    head.className = "suite";
    head.innerHTML = `<span class="nm">${suite}</span><span class="dt">${tasks.join(" · ")}</span>`;
    board.appendChild(head);
    for (const [task, row] of rows){
      shown++;
      const dw = winStarts(row.demo).length, ew = winStarts(row.total - row.demo).length;
      tokens += dw + ew;
      const el = document.createElement("div");
      el.className = "row";
      const left = document.createElement("div");
      left.className = "rl";
      left.innerHTML = `<span class="bd">${task}</span>` +
        `<span class="src">${row.diff} · ${row.band} · ${row.split}-ep${row.ep}</span>`;
      const right = document.createElement("div");
      right.className = "rr";
      const tk = dw + ew;
      right.innerHTML =
        `<span>T=<b>${row.total}</b> · seed ${row.seed}</span>` +
        `<span>窗口 ${dw}+${ew}=<b class="${tk ? "" : "zero"}">${tk}</b>` +
        (tk ? "" : "（无 motion token）") + `</span>` +
        `<span>Δ32=${((row.total - 1) / 31).toFixed(1)} · Δ8=${((row.total - 1) / 7).toFixed(1)}</span>`;
      el.appendChild(left); el.appendChild(track(row)); el.appendChild(right);
      board.appendChild(el);
    }
  }
  const axis = document.createElement("div");
  axis.className = "axis";
  const ticks = [];
  for (let v = 0; v <= XMAX; v += 200) ticks.push(`<span class="tk" style="left:${v / XMAX * 100}%"><i></i>${v}</span>`);
  axis.innerHTML = `<div></div><div class="ticks">${ticks.join("")}</div><div></div>`;
  board.appendChild(axis);
  document.getElementById("foot").textContent =
    `当前显示 ${shown} 行，合计 ${tokens} 个 motion token。`;
}

const tabs = document.getElementById("tabs");
for (const d of DIFFS){
  const b = document.createElement("button");
  b.className = "tab"; b.textContent = d; b.setAttribute("aria-pressed", d === "all");
  b.onclick = () => {
    for (const t of tabs.querySelectorAll(".tab")) t.setAttribute("aria-pressed", "false");
    b.setAttribute("aria-pressed", "true");
    render(d);
  };
  tabs.appendChild(b);
}
const all = Object.values(DATA).flat();
document.getElementById("chips").innerHTML = [
  `任务 <b>${Object.keys(DATA).length}</b>`,
  `代表集 <b>${all.length}</b>（4 任务 × 3 难度 × 最短/中位/最长）`,
  `窗口 <b>[f, f+${WIN - 1}]</b> · stride <b>${STRIDE}</b>`,
  `帧预算 <b>${BUDGETS.join(" / ")}</b>`,
  `横轴 <b>0–${XMAX}</b> ts`,
].map(s => `<span class="chip">${s}</span>`).join("");
render("all");
</script>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成采样窗口数轴的 artifact HTML")
    parser.add_argument("--imitation", action="append", required=True)
    parser.add_argument("--counting", action="append", required=True)
    parser.add_argument("--out", default=str(HERE / "outputs" / "sampling_axis.html"))
    args = parser.parse_args(argv)

    episodes = load({"imitation": args.imitation, "counting": args.counting})
    data = {task: pick(episodes[task]) for task in TASKS if task in episodes}
    html = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__SUITES__", json.dumps(SUITES, ensure_ascii=False)
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"已写出 {out}（{len(html) / 1024:.1f} KB，{sum(len(v) for v in data.values())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
