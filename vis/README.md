# vis/ — xhard1 合成参考数轴

用官方 hard 的现成数据，按 subgoal 段「复制粘贴」拼出 xhard1 档的参考时间轴并画成采样窗口数轴。**不跑仿真、不改源码**，只读 `/data/hongzefu/data_0226/`（`AGENTS.md` P3，只读）。用户 2026-10-06 原话：「上一版Hard的Data其实是有的是否可以通过SubGo级别的长度的复制粘贴来画出修改的数轴就是画出一个参考版当然和会有一些不一样但是可以作为参考」「参考数轴不作为任务内部的内容直接实现单独写一个单独在根目录有一个文件夹就是vis」。

## 跑法

```bash
uv run --no-sync python vis/synthesize_reference_timeline.py --h5-dir /data/hongzefu/data_0226 --metadata-dir src/robomme/env_metadata/train --out vis/output
```

约 90 秒；倒数第二行 `XHARD_REF_SWAP=INFO tasks=4 ...`，末行 `XHARD_REF=INFO tasks=14 episodes=350 synthetic=1`。产物在 `vis/output/`：每任务 `<Task>.png`（按合成 T 取最短 / 中位 / 最长三条，每条上行官方 hard 原样、下行 xhard1 合成，竖带为 swap）、`overview.png`（14 任务各取 xhard1 最短 / 中位 / 最长三条，全局横轴，V2 总览图画法）、`reference_<Task>.json`（逐条原段表、合成段表与统计）、`reference_summary.md`（汇总表，含与计划外推值的对账）。

## 口径

- 切段：`is_subgoal_boundary=True` 为段起点，段名取该步 `simple_subgoal`，demo 与尾段 `All tasks completed` 都算段（与 `scripts/patternlock-routestick-params/extract_move_durations.py` 一致）。
- 画图：V2 画法（2026-10-07 用户「然后恢复v2的图片数轴」）。`vis/v2_plot.py` 是 origin/newtask-v2 `70bc2ce0` 的 `scripts/injection-before-2d/{plot_sampling_windows,window_timeline,plot_injection_before_2d}.py` 中 `draw_track`、`_draw_board` 及其依赖的逐字搬运，只改 import；本仓库只在其后追加 `EXTRA_RULES`（V2 没覆盖的 12 个任务的中文短标）。每行：demo / exec 底色、subgoal 块（中文短标）、33 帧 stride-16 不跨段窗口三行堆叠、32 帧紫线与 8 帧红点帧路、每次 swap 一条半透明竖带（第 1～5 次紫 / 橙 / 青 / 玫红 / 棕），右栏 `T · 窗口 d+e=n · Δ32 · Δ8`。图例沿用 V2 原文，其中「慢条剔除」「BinFill 重复两遍」两项本仓库不出现。
- V2 实测原图：`v2/windows_overview.png`（origin/newtask-v2 `c0e7f046` 入库的 `scripts/injection-before-2d/figures/windows_overview.png`，1,066,060 字节，07 实跑 14 组）。
- swap 事件（2026-10-07 用户「v2有一个swap的标注 也作为subgoal 你也要考虑这个问题 swap采不到也不行」，追问后定「每次 swap 算一段」）：h5 里没有 swap 标签（整段 `static`），时刻按调度推出。VideoUnmaskSwap / ButtonUnmaskSwap 第 k 次 = `[64+50(k−1), 64+50k]`（`_refresh_swap_schedule`；ButtonUnmaskSwap 从第 0 步起算、与按钮并行，次数 h5 读不到，按 episode 序号在区间里轮流估）；VideoPlaceButton / VideoPlaceOrder 从最后一个 demo `static` 段起点每 50 timestep 一次（hard 与 xhard1 都是 1 次，2026-10-07 起两任务不加档；真实 h5 里 `step()` 闩锁 swap 的步可能比段边界晚十几帧，同 V2 VideoRepick 实测 B1−S = 12～17，合成接受这个近似）。
- 统计：T、demo 长度、窗 = demo 窗 + exec 窗、Δ8 = (T−1)/7、最短执行段；8 帧帧路用 V2 的 `floor(i·(T−1)/7 + 0.5)`（2026-10-07 起，此前是 Python 银行家舍入）。`exec_skip8` = 帧路没有点落入的执行段数（不含 demo 与尾段）；`swap_skip8` = 帧路没有点落入的 swap 事件数；`skip8_total` = 两者之和，是「8 帧必漏」判据用的数。
- Unmask 系任务的 h5 只有 ep0–99，因此也只有 25 条 hard。

## 复制规则（`RULES`，取值与 `1006-xhard12-env-plan.html` 第一部分四节一致）

表格、汇总、总览图里的任务一律按 [robomme.github.io](https://robomme.github.io/) 的四类顺序排列（计数 → 永久性 → 参考 → 模仿，类内按官网编号；`SUITE_ORDER`，`AGENTS.md` P6）。

| 任务 | 复制的单元 | 规则 |
|---|---|---|
| BinFill | [pick up the nth color cube → put it into the bin] 一对 | T → 5 或 6 |
| PickXtimes | 执行段 [pick up … for the nth time → place … onto the target] 一对 | 对数 N → N+2 |
| SwingXtimes | [right-side → left-side] 一对 | 3 → 7 或 8（按 hard 序号轮流） |
| StopCube | `remain static` 段 | k′∈[8,10]、间隔钉 120：static 检查点每 100 步一段到 120k′−90 止；首段与按钮、尾段原样 |
| VideoUnmask / ButtonUnmask | [put down the container → pick up the container …] 一对 | pick 2 → 3：在尾段前追加一对（2026-10-06 用户决定纳入） |
| VideoUnmaskSwap | demo `static` 段 | S′∈{4,5}，demo 长度 = 6·ceil((64+50S′)/6) |
| ButtonUnmaskSwap | 无独立 demo 段 | 合成 = 原样（交换与按钮并行，时长基本不变） |
| PickHighlight | [pick up the nth highlighted cube → place the cube onto the table] 一对，插在最后一个 pick 之前 | 3 → 5 |
| VideoRepick | 执行段 [pick up the correct cube … → put it down] 一对 | N → 4 或 5 |
| VideoPlaceButton | 不复制 | 不加档，新版 = 原版（2026-10-07 用户「改计划 两个任务用 --xhard 按原 hard 配置重新生成」；10-06 的「2 块 + 回原位 + swap 3」撤回） |
| VideoPlaceOrder | 不复制 | 同上 |
| PatternLock | demo 与 exec 各自的 `move …` 段 | 节点 L → L′∈[10,14]，两侧各补 L′−L 段 |
| RouteStick | demo 与 exec 各自的 `move to the nearest …` 段 | S → S′∈[8,10]，两侧各补 |

复制的段沿用原文（含序数词），所以图上会出现「抓红4」后面又来「抓红1」，这是复制粘贴的痕迹，不代表真实序号。

## 2026-10-06 结果速览（当时漏段只数执行段、不计 swap，计入后见下节）

合成中位 T 与计划外推值基本吻合（PickXtimes 1128 vs 1120、RouteStick 900 vs 900、StopCube 1054 vs 1020）；VideoPlaceOrder（1154 vs 1300）与 PatternLock（737 vs 810）外推偏乐观。**两个 Swap 任务与两个 Unmask 任务合成后都有 episode 的 8 帧帧路一段都不漏**（最少漏段 0），硬性判据对它们不一定成立。两个 Place 任务不加档，新版即官方 hard：中位 961 / 1115 timestep、57 / 67 窗。详表见 `output/reference_summary.md`。

## 2026-10-07 结果速览（swap 计入后）

| 任务 | swap 次数 hard → xhard1 | 合计漏最少 hard → xhard1 | 0 漏条数 hard → xhard1 |
|---|---|---|---|
| VideoUnmaskSwap | 2–3 → 4–5 | 0 → **1** | 11/25 → **0/25** |
| ButtonUnmaskSwap | 2–3 → 4–5（估） | 0 → 0 | 21/25 → 7/25（7 条全是 swap=4；swap=5 的 12 条每条至少漏 1） |
| VideoPlaceButton | 1 → 1（不加档） | 1 → 1 | 0/25 → 0/25 |
| VideoPlaceOrder | 1 → 1（不加档） | 2 → 2 | 0/25 → 0/25 |

计入 swap 后，VideoUnmaskSwap 的「8 帧必漏」在合成参考上成立；ButtonUnmaskSwap 只在 swap=5 时成立，swap=4 时 Δ8≈66 的采样点恰好落进 4 段连续的 50 帧交换；两个 Unmask 任务没有 swap，仍有 0 漏条（VideoUnmask 24/25、ButtonUnmask 10/25）。其余 10 个任务 swap 漏为 0，合计漏与执行段漏相同。

## 交互网页（2026-10-07）

用户原话：「重新画数轴 根据最新的内容 并且host成aspen的网站给我 原版新版都要画 默认显示中位数长度 可以选择显示min max」「并且按照对比v2的来分组显示」。

- 生成：`uv run --no-sync python vis/build_site.py --out artifacts/vis-site`（读 `output/reference_*.json` 与 `v2/windows_timeline.json`，模板 `site_template.html`，数据内联进单个 `index.html`；产物在 `artifacts/` 下不进 git）。判定行 `XHARD_SITE=INFO groups=4 tracks=34`。
- 分组同计划第一部分四节长度对比表的「对比的 V2 参照」：V2 BinFill hard、V2 RouteStick xhard、V2 VideoUnmaskSwap xhard、V2 VideoRepick xhard（PickHighlight 两组都出现）；组内按官网编号。每组先画 V2 参照一条，再画每个任务的原版（官方 hard）与新版（xhard1 合成）。
- 顶部切换最短 / 中位 / 最长（默认中位），每条轨迹各自按 timestep 数取对应那一条；组内横轴对三档固定。
- `v2/windows_timeline.json` 是 origin/newtask-v2 `scripts/injection-before-2d/windows_timeline.json` 的原样拷贝（20260911-contract-v3-07 实跑，每组 ep0–29），网页剔除其中 `excluded_slow` 的慢条。
- 托管：本机 tmux 会话 `xh-vis-web`（`python -m http.server 8090 --bind 0.0.0.0 --directory artifacts/vis-site`，日志 `artifacts/logs/xh-vis-web.log`），地址 http://sled-aspen.eecs.umich.edu:8090/ 。
- 计划网页：`uv run --no-sync python scripts/plan-site/build_plan_site.py` 把根目录 `1006-xhard12-env-plan.html` 拆成四页（首页 / 接口怎么改 / 逐环境与长度对齐 / 技术细节）输出到 `artifacts/plan-site/`；本机 tmux 会话 `xh-plan-web`（`python -m http.server 8092 --bind 0.0.0.0 --directory artifacts/plan-site`，日志 `artifacts/logs/xh-plan-web.log`），地址 http://sled-aspen.eecs.umich.edu:8092/ 。计划改动后重跑生成脚本即可，服务不用重启。envs 页的两张数轴总览（xhard1 合成、V2 实测）不再用 PNG，由 `scripts/plan-site/timeline_boards.py` 把 `output/reference_*.json` 与 `v2/windows_timeline.json` 内联进页面、`timeline_board.js` 在浏览器里画 SVG（取条与画法同原 PNG；2026-10-08 用户「改在原生在浏览器内部渲染」），建站末尾多一行 `TIMELINE_BOARDS=OK xhard1_rows=42 v2_rows=42`。
