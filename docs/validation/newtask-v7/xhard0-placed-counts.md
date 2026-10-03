# xhard0（官方 test hard 12 局）实际放置数探针（2026-09-28）

- 目的：核实官方 hard 配置里的物体数与桌上实际摆出来的数是否一致（用户原话「（内环 15）实际生成多少？有一部分取不到的！」「h5有segementation 你来测！给出定值」）。h5 只落 RGB／深度、无分割与 actor 列表，故用官方环境 reset 直接读属性。
- 方法：官方 `robomme.env_record_wrapper.BenchmarkEnvBuilder(task, dataset="test").make_env_for_episode(ep)` + `env.reset()`（与 `scripts/evaluation.py` 同路），对 `difficulty=="hard"` 的 12 局读 `len(env.unwrapped.spawned_bins)`／`len(all_cubes)`；断言 `u.seed == 元数据 seed` 且 `u.difficulty == "hard"`。
- 代码状态：仓库 HEAD `93b332a7`，`src/robomme/` 与官方 `1fadc0ec` 逐字节相同（`UPSTREAM_GUARD` 口径）；本机 sled-vail、RTX 6000 Ada（GPU 1）、仓库 `.venv`。位置采样由 CPU 侧 `torch.Generator(seed)` 决定，与显卡无关。
- 预算：7 任务 × 1 档 × 12 局 = 84 次 reset，另 smoke 时 VideoUnmask 第 3 局重复 2 次，合计 86；无轨迹、无录像。
- 判定行：`PROBE_DONE rows=84 errors=0`；`EXIT_CODE=0`。原始日志 `artifacts/newtask-v7/probe-hard-counts/probe.log`，探针 `probe_hard_counts.py`，汇总 `summarize.py`（不进 git）。

## 汇总

| 任务 | 配置 | 12 局实际 | 均值 | 最小 | 最大 |
|---|---|---|---|---|---|
| VideoUnmask | `{'bin': 15}` | 5,6,6,5,6,4,4,5,6,6,6,6 | 5.42 | 4 | 6 |
| ButtonUnmask | `{'bin': 15}` | 5,5,5,5,4,5,6,6,6,4,6,6 | 5.25 | 4 | 6 |
| VideoUnmaskSwap | `{'bin': 4}` | 4,4,4,4,4,4,4,4,4,4,4,4 | 4.00 | 4 | 4 |
| ButtonUnmaskSwap | `{'bin': 4}` | 4,4,4,4,4,4,4,4,4,4,4,4 | 4.00 | 4 | 4 |
| PickHighlight | `{'spawn': 6}` | 6,6,6,6,6,6,6,6,6,6,6,6 | 6.00 | 6 | 6 |
| PickXtimes | `{'color': 3}` | 3,3,3,3,3,3,3,3,3,3,3,3 | 3.00 | 3 | 3 |
| BinFill | `{'color': 3, 'spawn_cubes': [10, 12]}` | 10,11,11,11,12,11,10,10,12,12,10,11 | 10.92 | 10 | 12 |

结论：VideoUnmask／ButtonUnmask 配置 15 个容器，实际只放下 4～6 个（`except RuntimeError: break` 静默截断）；VideoUnmaskSwap／ButtonUnmaskSwap 4 个、PickHighlight 6 块、PickXtimes 3 块全部精确；BinFill 请求数＝实际数，但请求数本身是 `spawn_cubes=[10,12]` 抽出的 10～12。

## 逐局

| 任务 | 原 test episode | seed | 实际数 | 备注 |
|---|---|---|---|---|
| VideoUnmask | 3 | 560300 | 5 |  |
| VideoUnmask | 7 | 560700 | 6 |  |
| VideoUnmask | 11 | 561100 | 6 |  |
| VideoUnmask | 15 | 561500 | 5 |  |
| VideoUnmask | 19 | 561900 | 6 |  |
| VideoUnmask | 23 | 562300 | 4 |  |
| VideoUnmask | 27 | 562700 | 4 |  |
| VideoUnmask | 31 | 563100 | 5 |  |
| VideoUnmask | 35 | 563500 | 6 |  |
| VideoUnmask | 39 | 563900 | 6 |  |
| VideoUnmask | 43 | 564300 | 6 |  |
| VideoUnmask | 47 | 564700 | 6 |  |
| ButtonUnmask | 3 | 580300 | 5 |  |
| ButtonUnmask | 7 | 580700 | 5 |  |
| ButtonUnmask | 11 | 581100 | 5 |  |
| ButtonUnmask | 15 | 581500 | 5 |  |
| ButtonUnmask | 19 | 581900 | 4 |  |
| ButtonUnmask | 23 | 582300 | 5 |  |
| ButtonUnmask | 27 | 582700 | 6 |  |
| ButtonUnmask | 31 | 583100 | 6 |  |
| ButtonUnmask | 35 | 583500 | 6 |  |
| ButtonUnmask | 39 | 583900 | 4 |  |
| ButtonUnmask | 43 | 584300 | 6 |  |
| ButtonUnmask | 47 | 584701 | 6 |  |
| VideoUnmaskSwap | 3 | 550300 | 4 |  |
| VideoUnmaskSwap | 7 | 550700 | 4 |  |
| VideoUnmaskSwap | 11 | 551100 | 4 |  |
| VideoUnmaskSwap | 15 | 551500 | 4 |  |
| VideoUnmaskSwap | 19 | 551900 | 4 |  |
| VideoUnmaskSwap | 23 | 552300 | 4 |  |
| VideoUnmaskSwap | 27 | 552700 | 4 |  |
| VideoUnmaskSwap | 31 | 553100 | 4 |  |
| VideoUnmaskSwap | 35 | 553500 | 4 |  |
| VideoUnmaskSwap | 39 | 553900 | 4 |  |
| VideoUnmaskSwap | 43 | 554300 | 4 |  |
| VideoUnmaskSwap | 47 | 554700 | 4 |  |
| ButtonUnmaskSwap | 3 | 570300 | 4 |  |
| ButtonUnmaskSwap | 7 | 570700 | 4 |  |
| ButtonUnmaskSwap | 11 | 571100 | 4 |  |
| ButtonUnmaskSwap | 15 | 571500 | 4 |  |
| ButtonUnmaskSwap | 19 | 571900 | 4 |  |
| ButtonUnmaskSwap | 23 | 572300 | 4 |  |
| ButtonUnmaskSwap | 27 | 572700 | 4 |  |
| ButtonUnmaskSwap | 31 | 573100 | 4 |  |
| ButtonUnmaskSwap | 35 | 573500 | 4 |  |
| ButtonUnmaskSwap | 39 | 573900 | 4 |  |
| ButtonUnmaskSwap | 43 | 574300 | 4 |  |
| ButtonUnmaskSwap | 47 | 574700 | 4 |  |
| PickHighlight | 3 | 620301 | 6 |  |
| PickHighlight | 7 | 620700 | 6 |  |
| PickHighlight | 11 | 621100 | 6 |  |
| PickHighlight | 15 | 621500 | 6 |  |
| PickHighlight | 19 | 621900 | 6 |  |
| PickHighlight | 23 | 622300 | 6 |  |
| PickHighlight | 27 | 622700 | 6 |  |
| PickHighlight | 31 | 623100 | 6 |  |
| PickHighlight | 35 | 623500 | 6 |  |
| PickHighlight | 39 | 623900 | 6 |  |
| PickHighlight | 43 | 624300 | 6 |  |
| PickHighlight | 47 | 624700 | 6 |  |
| PickXtimes | 3 | 510300 | 3 | 圆盘 有 |
| PickXtimes | 7 | 510700 | 3 | 圆盘 有 |
| PickXtimes | 11 | 511100 | 3 | 圆盘 有 |
| PickXtimes | 15 | 511501 | 3 | 圆盘 有 |
| PickXtimes | 19 | 511900 | 3 | 圆盘 有 |
| PickXtimes | 23 | 512300 | 3 | 圆盘 有 |
| PickXtimes | 27 | 512700 | 3 | 圆盘 有 |
| PickXtimes | 31 | 513100 | 3 | 圆盘 有 |
| PickXtimes | 35 | 513500 | 3 | 圆盘 有 |
| PickXtimes | 39 | 513900 | 3 | 圆盘 有 |
| PickXtimes | 43 | 514300 | 3 | 圆盘 有 |
| PickXtimes | 47 | 514700 | 3 | 圆盘 有 |
| BinFill | 3 | 540302 | 10 | 请求 r/b/g = 6/1/3 |
| BinFill | 7 | 540701 | 11 | 请求 r/b/g = 1/4/6 |
| BinFill | 11 | 541100 | 11 | 请求 r/b/g = 5/3/3 |
| BinFill | 15 | 541500 | 11 | 请求 r/b/g = 3/6/2 |
| BinFill | 19 | 541900 | 12 | 请求 r/b/g = 1/6/5 |
| BinFill | 23 | 542300 | 11 | 请求 r/b/g = 3/5/3 |
| BinFill | 27 | 542700 | 10 | 请求 r/b/g = 4/4/2 |
| BinFill | 31 | 543100 | 10 | 请求 r/b/g = 2/4/4 |
| BinFill | 35 | 543501 | 12 | 请求 r/b/g = 5/5/2 |
| BinFill | 39 | 543900 | 12 | 请求 r/b/g = 3/4/5 |
| BinFill | 43 | 544300 | 10 | 请求 r/b/g = 3/3/4 |
| BinFill | 47 | 544700 | 11 | 请求 r/b/g = 3/6/2 |
