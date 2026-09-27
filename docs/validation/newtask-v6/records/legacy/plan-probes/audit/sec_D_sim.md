# V6 计划审计 D 节：h5 实测 + 本机模拟器 reset 实测

审计对象：根目录 `NEWTASK_RELEASE_V6_PLAN.md`（1.3、1.5、2.3、2.7～2.12、第五节盲区）。只读审计，未改任何 git 跟踪文件；
脚本与原始输出全部在 `artifacts/newtask-v6/plan-probes/audit/sec_D/`。本机 GPU 1，未用 greatlakes。

## 口径说明

- **xhard 实测源**：`artifacts/newtask-v5/v5-01/rollout/run1/episodes/*/hdf5_files/*.h5`，16 环境 × 3 局 = 48 局（`h5_stats.py` → `h5_xhard.json`）。
- **hard 对照源**：仓库内 `artifacts/newtask-v5/v1/`、`s0/` 只有日志、没有 h5；改用原始 RoboMME 数据集 `/data/hongzefu/data-0306/record_dataset_<Task>.h5`，按 metadata 取 `difficulty=="hard"` 的局，16 环境 × 25 局 = 400 局（`h5_hard.py` → `h5_hard.json`）。前提假设：data-0306 就是原三档的「最原始基线」发布集。
- **fps**：录像器 `src/robomme/env_record_wrapper/RecordWrapper.py` 写视频 `fps=30`，V5 口径 9 也按 30 fps 计；演示帧 = `info/is_video_demo` 为真的 timestep 数；执行帧 = 总 timestep − 演示帧。
- **评估步数口径**：`scripts/evaluation.py` 写的是 `max_steps=1300`；`episode_config_resolver.py` 把它换成 `max_steps_without_demonstration = max_steps + 2 = 1302`；`DemonstrationWrapper._step_batch` 只在 `current_task_demonstration == False` 时累加 `steps_without_demonstration`，达到 ≥1302 时置 `truncated`。所以预算管的是**执行段（非演示）步数**，演示段不计入；上限实际约 1301～1302 步。计划写的「1301」与这一口径吻合。h5 的执行帧还多出末尾 1～2 帧（终止时额外补录一帧），差别可以忽略。
- **reset 探针**：`reset_probe.py` 从 `scripts/configs/newtask-v5/sampling_config.json` 取单任务 `{decision, native}`，在**内存里**把 xhard 的数值换成新档值，再照 `v4_specs._draw_one` 的写法调用 `gym.make(task, sampling_config=…, **v4_specs.env_kwargs(seed, 0))` 和 `env.reset()`，只做 reset、不跑演示。seed 从 9100000 起连号；同一环境的各个组合用同一批 seed，所以组合之间是配对比较。覆盖点：PH 改 `spawn_count.xhard` / `highlight_count.xhard`；BinFill 改 `configs.xhard.put_in_numbers`；PX/SX 把 `xhard.distractor.colors` 截成前 k 个（干扰块数 = 颜色数）。已核实覆盖真的生效：PH 成功局的 spawn/pick 等于设定值，BinFill 的 `target_numbers` 之和落在设定区间，PX/SX 的 `all_cubes` 等于 3+k。
- **reset 内部有没有重试**：四个环境的 xhard 分支都没有 reset 级重试。每块方块的拒绝采样在 `spawn_random_cube` 里（PH 默认 256 次，PX/SX 用 `XHARD_CUBE_MAX_TRIALS=1024`），用满预算就直接抛 `SceneGenerationError`；换 seed 重抽发生在抽签层（`v4_specs draw`，每次 attempt 换一个 seed）。所以「最终失败率」= 单 seed 的 reset 失败率，「平均抽签次数」= 1/成功率。每块内部的拒绝采样次数没有插桩，拿不到。

## 一、h5 实测（任务 1）

### 1.1 xhard 48 局逐局（帧数；秒数按 30 fps 换算）

| 环境 | ep0 总/演示/执行 | ep3 总/演示/执行 | ep6 总/演示/执行 | 演示时长 s |
|---|---|---|---|---|
| BinFill | 1523/0/**1523** | 1187/0/1187 | 956/0/956 | — |
| ButtonUnmask | 538/0/538 | 516/0/516 | 511/0/511 | — |
| ButtonUnmaskSwap | 716/0/716 | 689/0/689 | 721/0/721 | — |
| InsertPeg (ep0/1/5) | 451/238/213 | 496/248/248 | 484/242/242 | 7.9/8.3/8.1 |
| MoveCube | 481/263/218 | 281/167/114 | 280/170/110 | 8.8/5.6/5.7 |
| PatternLock | 1636/818/818 | 1744/872/872 | 1674/837/837 | **27.3/29.1/27.9** |
| PickHighlight | 1032/0/1032 | 872/0/872 | 1060/0/1060 | — |
| PickXtimes | 1017/0/1017 | 1309/0/**1309** | 1122/0/1122 | — |
| RouteStick | 2100/1050/1050 | 1700/850/850 | 1600/800/800 | **35.0/28.3/26.7** |
| StopCube | 428/0/428 | 846/0/846 | 553/0/553 | — |
| SwingXtimes | 649/0/649 | 826/0/826 | 926/0/926 | — |
| VideoPlaceButton | 1552/1365/187 | 1568/1373/195 | 1589/1368/221 | 45.5/45.8/45.6 |
| VideoPlaceOrder | 1700/1520/180 | 2171/1952/219 | 1832/1606/226 | 50.7/65.1/53.5 |
| VideoRepick | 1324/655/669 | 1696/851/845 | 1346/699/647 | 21.8/28.4/23.3 |
| VideoUnmaskSwap | 802/396/406 | 807/396/411 | 780/366/414 | 13.2/13.2/12.2 |
| VideoUnmask | 507/66/441 | 441/66/375 | 466/66/400 | 2.2/2.2/2.2 |

### 1.2 hard 对照（data-0306，每环境 25 局）

| 环境 | 总帧 min/中位/max | 演示 s min/max | 执行帧 max | 执行 >1301 的局 |
|---|---|---|---|---|
| BinFill | 608/871/1097 | — | 1097 | 0 |
| ButtonUnmask | 351/372/459 | — | 459 | 0 |
| ButtonUnmaskSwap | 432/463/577 | — | 577 | 0 |
| InsertPeg | 418/464/808 | 7.0/13.5 | 404 | 0 |
| MoveCube | 254/437/497 | 5.0/8.8 | 249 | 0 |
| PatternLock | 186/328/572 | 3.1/9.5 | 286 | 0 |
| PickHighlight | 497/544/623 | — | 623 | 0 |
| PickXtimes | 677/803/1006 | — | 1006 | 0 |
| RouteStick | 400/500/700 | 6.7/11.7 | 350 | 0 |
| StopCube | 121/236/579 | — | 579 | 0 |
| SwingXtimes | 447/495/573 | — | 573 | 0 |
| VideoPlaceButton | 899/965/1046 | 23.4/27.0 | 310 | 0 |
| VideoPlaceOrder | 918/1135/1336 | 23.8/37.5 | 298 | 0 |
| VideoRepick | 408/540/893 | 4.9/6.8 | 694 | 0 |
| VideoUnmask | 305/332/410 | 2.2/2.2 | 344 | 0 |
| VideoUnmaskSwap | 401/460/550 | 5.6/7.2 | 334 | 0 |

hard 400 局中执行帧超过 1301 的为 0 局（最大是 BinFill 的 1097）；xhard 48 局中有 2 局超过。

### 1.3 分段帧数（按 `simple_subgoal` 文本切段；相邻两段文本相同会被并成一段）

- **RouteStick**：xhard 三局的演示段全部是 50 的整数倍（50 / 100 / 150，100 和 150 是同方向连续段被合并）；执行帧 = 演示帧 = 50·L（L = 21/17/16）。hard 25 局同样如此：50×101 段、100×17 段、150×1 段。
- **PatternLock**：xhard 节点数 = 25（specs `path_nodes`），共 24 段；每段平均 818/24 = 34.1、872/24 = 36.3、837/24 = 34.9 帧，单段范围 21～56 帧（66/98/116 这几个值是合并段）。hard 单段最常见的是 35 帧。
- **VU/BU 的 pick / put down**：xhard（每环境 3 局 × 3 次 pick）中，VU pick 单段最大 125、put down 最大 52；BU pick 最大 109、put down 最大 51、按按钮 119。对照：原生 hard（15 容器布局）VU pick 最大 202、put down 最大 59；BU pick 最大 169、按按钮 130。

## 二、reset 布局可行性（任务 2；PH 每组合 1000 次，其余每组合 200 次）

| 环境 | 组合 | n | 成功 | 失败 | 成功率（95% CI） | 期望抽签次数 | 失败类型 | 每次 reset 墙钟 |
|---|---|---|---|---|---|---|---|---|
| PH | xhard1（pick 4 / spawn 7） | 1000 | 999 | 1 | 99.9%（99.4–100） | 1.001 | SceneGenerationError 放不满 ×1 | ~1.3 s |
| PH | xhard2（pick [4,5] / spawn 8） | 1000 | 987 | 13 | 98.7%（97.8–99.2） | 1.013 | 放不满（请求 8）×13 | ~1.3 s |
| PH | xhard3（pick [5,6] / spawn [8,9]） | 1000 | 962 | 38 | 96.2%（94.8–97.2） | 1.040 | 请求 8 ×7、请求 9 ×31 | ~1.2 s |
| PH | xhard 现值（pick [5,7] / spawn [8,10]） | 1000 | 894 | 106 | 89.4%（87.3–91.2） | 1.119 | 请求 8 ×1、9 ×32、10 ×73 | ~1.2 s |
| PH | 固定 N=8（pick [5,7]） | 1000 | 987 | 13 | **98.7%** | 1.013 | 放不满 | |
| PH | 固定 N=9 | 1000 | 929 | 71 | **92.9%** | 1.076 | 放不满 | |
| PH | 固定 N=10 | 1000 | 730 | 270 | **73.0%** | 1.370 | 放不满 | |
| BinFill | xhard1 投入 [4,5] | 200 | 200 | 0 | 100% | 1 | — | ~1.3 s |
| BinFill | xhard2 [4,6] | 200 | 200 | 0 | 100% | 1 | — | |
| BinFill | xhard3 [5,6] | 200 | 200 | 0 | 100% | 1 | — | |
| BinFill | xhard [5,7] | 200 | 200 | 0 | 100% | 1 | — | |
| PickXtimes | 干扰 1（共 4 块） | 200 | 200 | 0 | 100% | 1 | — | ~1.6 s |
| PickXtimes | 干扰 2（5 块） | 200 | 200 | 0 | 100% | 1 | — | |
| PickXtimes | 干扰 3（6 块，= xhard3 = xhard） | 200 | 200 | 0 | 100% | 1 | — | |
| SwingXtimes | 干扰 1 | 200 | 192 | 8 | 96.0% | 1.042 | 放置圆盘采样失败：First ×3、Second ×5 | ~1.8 s |
| SwingXtimes | 干扰 2 | 200 | 192 | 8 | 96.0% | 1.042 | 同上 | |
| SwingXtimes | 干扰 3（= xhard） | 200 | 192 | 8 | 96.0% | 1.042 | 同上 | |

要点：
- PH 固定 N 的实测（98.7 / 92.9 / 73.0%）与计划的离线数（98.7 / 93.4 / 71.8%）都落在彼此的误差范围内。新档成功率随难度单调下降（99.9 → 98.7 → 96.2 → 89.4%），全部高于 xhard。
- **xhard 有幸存者偏差**：它的成功局 spawn 分布是 8:9:10 = 350:302:242，名义上应各占三分之一；V5 抽签留档（drafts）里 PH 也是 12 次 attempt 失败 2 次。
- SwingXtimes 的 8 个失败 seed 在四个组合里**完全相同**（9100040、48、51、70、81、107、114、189）。失败发生在放置圆盘（target）采样，这一步在放干扰块之前，所以和干扰数无关。这说明 V5 的 xhard 本身就有约 4% 的 reset 失败（v5-01 抽签是 10 次 attempt 全部成功，样本太小没暴露出来）。计划 2.8 没有写 SX 的 reset 成功率，本项不算不一致，但不能写成「100%」。
- PX/SX 的干扰块都在所有取值点之后才放（源码注释 N5），干扰数少只会让放置更宽松；实测 PX 全部 100%，与之相符。

## 三、PH 干扰块数分布（任务 3，成功局，n=1000/组合）

| 档 | 实测干扰数 = spawn − pick | 计划表 |
|---|---|---|
| xhard1 | 3：999 | 3 ✓ |
| xhard2 | 3：484、4：503 | 3～4 ✓ |
| xhard3 | 2：251、3：489、4：222 | 2～4 ✓ |
| xhard | 1：134、2：210、3：283、4：181、5：86 | 1～5 ✓ |

## 四、逐条核对表

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注（实测数字） |
|---|---|---|---|---|
| 1.3 评估步数口径 | 「`evaluation.py` 评估 1301 步」 | 读 `evaluation.py`、`episode_config_resolver.py`、`DemonstrationWrapper` | 一致 | `max_steps=1300` 在代码里变成 `max_steps_without_demonstration=1302`；只数非演示步，≥1302 截断，所以演示段不占预算 |
| 1.3 xhard 已有超 1301 的局 | 「xhard 本身已有超 1301 的局，那是 V5 现状」 | 48 局 h5 的执行帧 | 一致 | 48 局中 2 局超：BinFill ep0 执行 1523 帧、PickXtimes ep3 1309 帧（约多 7 帧，扣掉补录帧后仍超）。hard 400 局 0 局超（最大 1097） |
| 1.3 新档执行步 / 总步数 ≤ xhard | 「新档全部落在 hard 与 xhard 之间」 | 无法跑演示；只能对照 hard/xhard 的端点 | 无法核实（端点相符） | 两个端点：hard 执行帧最大 1097、xhard 最大 1523。BinFill、PX 的新档次数上界在 xhard 以下，推断合理，但没有实测 |
| 1.5 演示 25～35 s 不变 | 「演示 25～35 s … 不变」 | 按 30 fps 换算 xhard PL/RS 的演示帧 | xhard 一致；**对新档的表述有歧义** | xhard：PL 27.3/29.1/27.9 s，RS 35.0/28.3/26.7 s，全部在带内（RS ep0 正好在 1050 上界）。但按 2.11/2.12 的新档参数，PL xhard1～3 的演示约 8～21 段 × 35 ≈ 9～24.5 s，RS xhard1～3 为 400～700 帧 = 13～23 s，**全部低于 25 s**。V5 报告里的 `demo_frames_out_of_band`（`v5_generation.py` 的 `DEMO_BAND=(750,1050)`，作用于 PL/RS）会把新档全部记成越界。计划要写明「25～35 s 只约束 xhard」，并让报告按档豁免。另：VPB/VPO 的 xhard 演示 45～65 s，不在口径 9 的管辖范围内（口径 9 只管 PL/RS） |
| 2.3 帧数 | 「pick 最坏 125 + put down 52，全部 ≤ xhard」 | xhard VU/BU 分段帧数 | 一致（样本小） | xhard VU pick 最大 125、put down 最大 52；BU pick 109、put down 51。每环境只有 9 次 pick 样本，「最坏」的说法依据不足。原生 hard（15 容器）VU pick 最大 202、put down 59，但新档用的是 8 容器 xhard 布局，不能直接套用 |
| 2.7 BinFill reset | 「reset 成功率在 hard 与 xhard 之间（xhard 离线 100%）」 | 本机 reset，每组合 200 次 | 一致 | xhard1/2/3/xhard 全部 200/200。投入数不影响杂乱布局（12 块总数固定） |
| 2.8 PickXtimes 干扰 1/2/3 | 「xhard 机制，中心距 0.08、框 0.25」 | reset，每组合 200 次 | 一致 | 全部 200/200；`all_cubes` = 4/5/6 |
| 2.8 SwingXtimes 干扰 1/2/3 | 同上（0.08） | reset，每组合 200 次 | 一致（附注） | 全部 192/200 = 96.0%，失败 seed 各组合完全相同，都是圆盘采样失败，与干扰数无关。xhard 现值本身就有约 4% 的 reset 失败 |
| 2.9 PH reset 离线数 | 「N=8 98.7%、N=9 93.4%、N=10 71.8%」 | reset，每组合 1000 次 | 一致 | 实测 98.7% / 92.9% / 73.0% |
| 2.9 PH 新档成功率 | 「随 N 单调下降，全部不低于 xhard」 | reset，每组合 1000 次 | 一致 | xhard1 99.9%、xhard2 98.7%、xhard3 96.2%、xhard 89.4% |
| 2.9 PH 干扰数 | 「xhard2 3～4、xhard3 2～4」 | 成功局 spawn − pick | 一致 | 分布见第三节 |
| 2.11 PatternLock | 「每段约 35 帧 ⇒ xhard3 最长约 735 帧」 | xhard 分段帧数 | 基本一致 | 每段平均 34.1～36.3 帧；按 36.3 算，xhard3（22 节点 = 21 段）约 763 帧 ≈ 25.4 s，比计划的 735 多约 4%，可能刚好碰到 25 s 线 |
| 2.12 RouteStick | 「每段恒 50 帧；xhard3 执行段 ≤ 700」 | xhard 与 hard 分段 | 一致 | hard 与 xhard 全部段都是 50 的倍数；执行帧 = 演示帧 = 50·L，L=14 时正好 700 |
| 第五节盲区 | 「全部帧数与成功率来自离线副本，无一格跑过模拟器」 | — | 本审计部分补上 | PH/BinFill/PX/SX 的新档 reset 成功率已用真实模拟器实测；帧数仍未实测（没跑演示） |

## 已实测通过

- 1.3「xhard 已有超 1301 的局」：BinFill ep0 1523、PickXtimes ep3 1309；评估预算只数执行段，上限 1302。
- 1.5 在 xhard 上成立：PL 27.3～29.1 s，RS 26.7～35.0 s。
- 2.3 xhard 的 pick 125 / put down 52（小样本）。
- 2.7 BinFill 四档 reset 100%（各 200 次）。
- 2.8 PickXtimes 三档 reset 100%（各 200 次）；SwingXtimes 三档 96.0%，与 xhard 相同。
- 2.9 PH：离线 N=8/9/10 的数复现（98.7 / 92.9 / 73.0%）；新档 99.9 / 98.7 / 96.2%，全部高于 xhard 的 89.4%；干扰数区间相符。
- 2.11 PL 每段约 35 帧（34.1～36.3）；2.12 RS 每段恒 50 帧、xhard3 执行段 ≤ 700。

## 不一致需改计划

1. **1.5「演示 25～35 s 不变」要限定到 xhard**：PL/RS 的 xhard1～3 按设计就短于 25 s（PL 约 9～25 s，RS 13～23 s）。计划要明写口径 9 只约束 xhard，并在生成报告的 `DEMO_BAND` / `demo_frames_out_of_band` 里对新档豁免，或改成按档给出区间，否则报告会把 PL/RS 的新档全部标成越界。
2. **2.11 PL「xhard3 最长约 735 帧」偏乐观**：按实测每段均值上界 36.3 帧算约 763 帧（25.4 s）。不影响任何预算（执行段远低于 1301），只是数字要改成「约 735～765 帧」。
3. **2.8 SwingXtimes 的 reset 成功率要补上**：实测 xhard 及三档新档都是约 96%（圆盘采样失败，与干扰数无关），抽签上限要按 0.96 估，不能按 100% 估。这不是计划的错误陈述，只是缺了这一项。
4. **2.3「pick 最坏 125」的依据只有 9 个样本**：建议改成「xhard 实测最大 125（n=9）」，不要称「最坏」。

## 产物

- `artifacts/newtask-v6/plan-probes/audit/sec_D/h5_stats.py`、`h5_xhard.json/.log`（xhard 48 局）
- `artifacts/newtask-v6/plan-probes/audit/sec_D/h5_hard.py`、`h5_hard.json/.log`（data-0306 的 hard 400 局）
- `artifacts/newtask-v6/plan-probes/audit/sec_D/reset_probe.py`、`combos.txt`、`run_all.sh`、`run_ext.sh`、`reset/*.jsonl`（19 组合 × 200）、`reset_ext/*.jsonl`（PH 7 组合 × 800）、`summarize_reset.py`、`ph_1000_summary.txt`、`reset_run.log`、`reset_ext.log`
