# vis/ — xhard1 合成参考数轴

用官方 hard 的现成数据，按 subgoal 段「复制粘贴」拼出 xhard1 档的参考时间轴并画成采样窗口数轴。**不跑仿真、不改源码**，只读 `/data/hongzefu/data_0226/`（`AGENTS.md` P3，只读）。用户 2026-10-06 原话：「上一版Hard的Data其实是有的是否可以通过SubGo级别的长度的复制粘贴来画出修改的数轴就是画出一个参考版当然和会有一些不一样但是可以作为参考」「参考数轴不作为任务内部的内容直接实现单独写一个单独在根目录有一个文件夹就是vis」。

## 跑法

```bash
uv run --no-sync python vis/synthesize_reference_timeline.py --h5-dir /data/hongzefu/data_0226 --metadata-dir src/robomme/env_metadata/train --out vis/output
```

约 50 秒；末行 `XHARD_REF=INFO tasks=14 episodes=350 synthetic=1`。产物在 `vis/output/`：每任务 `<Task>.png`（按合成 T 取最短 / 中位 / 最长三条，每条上行官方 hard 原样、下行 xhard1 合成）、`reference_<Task>.json`（逐条原段表、合成段表与统计）、`reference_summary.md`（汇总表，含与计划外推值的对账）。

## 口径

- 切段：`is_subgoal_boundary=True` 为段起点，段名取该步 `simple_subgoal`，demo 与尾段 `All tasks completed` 都算段（与 `scripts/patternlock-routestick-params/extract_move_durations.py` 一致）。
- 画图：复用 `scripts/patternlock-routestick-params/plot_sampling_windows.py` 的 `draw_row`（demo / exec 底色、subgoal 块、33 帧 stride-16 不跨段窗口三行堆叠、32 帧与 8 帧帧路）。
- 统计：T、demo 长度、窗 = demo 窗 + exec 窗、Δ8 = (T−1)/7、最短执行段、漏段8 = 8 帧帧路没有采样点落入的执行段数（执行段不含 demo 与尾段）。
- Unmask 系任务的 h5 只有 ep0–99，因此也只有 25 条 hard。

## 复制规则（`RULES`，取值与 `1006-xhard12-env-plan.md` 第一部分四节一致）

| 任务 | 复制的单元 | 规则 |
|---|---|---|
| PickXtimes | 执行段 [pick up … for the nth time → place … onto the target] 一对 | 对数 N → N+2 |
| SwingXtimes | [right-side → left-side] 一对 | 3 → 7 或 8（按 hard 序号轮流） |
| BinFill | [pick up the nth color cube → put it into the bin] 一对 | T → 5 或 6 |
| VideoRepick | 执行段 [pick up the correct cube … → put it down] 一对 | N → 4 或 5 |
| PickHighlight | [pick up the nth highlighted cube → place the cube onto the table] 一对，插在最后一个 pick 之前 | 3 → 5 |
| VideoPlaceOrder | demo 段 [pick up the cube → drop the cube onto target] 一对 | P → 4 |
| PatternLock | demo 与 exec 各自的 `move …` 段 | 节点 L → L′∈[10,14]，两侧各补 L′−L 段 |
| RouteStick | demo 与 exec 各自的 `move to the nearest …` 段 | S → S′∈[8,10]，两侧各补 |
| StopCube | `remain static` 段 | k′∈[8,10]、间隔钉 120：static 检查点每 100 步一段到 120k′−90 止；首段与按钮、尾段原样 |
| VideoUnmaskSwap | demo `static` 段 | S′∈{4,5}，demo 长度 = 6·ceil((64+50S′)/6) |
| ButtonUnmaskSwap | 无独立 demo 段 | 合成 = 原样（交换与按钮并行，时长基本不变） |
| VideoUnmask / ButtonUnmask | [put down the container → pick up the container …] 一对 | pick 2 → 3：在尾段前追加一对（2026-10-06 用户决定纳入） |
| VideoPlaceButton | demo 段 [pick up the cube → drop the cube onto target] 对、按钮、[pick → drop onto table] 对（代表回原位）、两段 static | 2 块各按钮前后放 1 次（共 4 对）→ 按钮 → 2 对回原位 → static 20 → static 60+100（swap 3 次）（2026-10-06 用户决定） |
| VideoPlaceOrder | 同上 | 2 块共访问 5 次（按钮前 2 对、后 3 对）→ 2 对回原位 → static 20 → static 160（swap 3 次）（2026-10-06 用户决定） |

复制的段沿用原文（含序数词），所以图上会出现「抓红4」后面又来「抓红1」，这是复制粘贴的痕迹，不代表真实序号。

## 2026-10-06 结果速览

合成中位 T 与计划外推值基本吻合（PickXtimes 1128 vs 1120、RouteStick 900 vs 900、StopCube 1054 vs 1020）；VideoPlaceOrder（1154 vs 1300）与 PatternLock（737 vs 810）外推偏乐观。**两个 Swap 任务与两个 Unmask 任务合成后都有 episode 的 8 帧帧路一段都不漏**（最少漏段 0），硬性判据对它们不一定成立。用户追加的两个 Place 任务（2 块 + 回原位 + swap 3）合成中位 1618 / 1773 帧、98 / 108 窗，远超 900 目标。详表见 `output/reference_summary.md`。
