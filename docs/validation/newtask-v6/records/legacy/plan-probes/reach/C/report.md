# 探针 C：MoveCube 放宽区域 W + yaw 全 2π 的真实演示实测（2026-09-25）

仓库 newtaskRelease-v5，HEAD 215531e；没有改动任何被 git 跟踪的文件。脚本与产物都放在本目录（已被 gitignore）。

## 一、运行链路
`run_probe.py`（仿 `scripts/parity/train_split_runner.py`）→ `probe_worker.run` → `scripts/parity/train_split_worker.run_one`（V5 正式生成用的镜像 worker；`gym.make(..., sampling_config=v5-01 头部 MoveCube 块, native_episode_spec=本局规格)`；官方编排 `_execute_tasks`、FailAware 规划器、RecordWrapper（视频开启）都不变；`--no-recovery` 口径）。子进程里只打了两个只做观测的补丁：`RecordWrapper.close` 之前记下步数，`_execute_tasks` 换成同逻辑但带逐子任务轨迹的版本（evaluate 的调用次数与原版相同）。
- `generate_dataset_newseed._worker` 只会把 `episode_spec` 传进旧通道，MoveCube 只认 `native_episode_spec`，所以改走 run_one。
- 首版尝试用 `save_video=False` 提速，结果 h5 逐帧记录同样挂在 save_video 上，全部局都报 `no timesteps`。那一批已撤回，存档在 `_novideo_run/`，不计入结果。

## 二、回放时的范围校验清单（读代码得出）
| 校验 | 位置 | 回放值越界会不会被拒 |
|---|---|---|
| `_assert_peg_outside_zone` | MoveCube.py | **会**：杆轴线段 [root−0.15u, root+0.05u] 离 (0,0) 不到 0.05 就抛 EpisodeSpecError。它只查内禁区，不查外界 |
| `spawn_random_target` / `spawn_random_cube` 的 `_assert_center_rules_hold` | object_generation.py | 只查中心禁区 R=0.05，**不查** region_half_size，也不查与杆、goal 的距离 |
| region 框、OBB 避障、方块与 goal 距离 ≥0.10、方块候选框 | 同上与 `_sample_cube_center` | **只作用于随机抽样值**：回放时拒绝循环照常用随机数跑完，被接受后才换成冻结值，所以冻结值完全不受检查 |
| `_xhard_center_exclusion` | MoveCube.py | 只校验配置形状，不涉及布局值 |
| `_xhard_verify_peg_extent` | MoveCube.py | 只核对杆的几何，与位置无关 |
| `validate_demo_plan` | 只在 VideoPlace* 里用 | 与 MoveCube 无关 |
| 规格外壳 | episode_spec.py | spec_kind 必须是 `native-newvalue/1`，task 必须对上，缺少取值点就报错 |

处置方式：W 采样时直接加上「杆轴线段离原点 ≥0.05」这条（与 V5 现行规则相同），**没有用 monkeypatch 绕过任何校验**。潜在的回放副作用：执行段方块的随机拒绝循环会把回放后的演示段 goal 当成障碍，极端情况下可能误报 SceneGenerationError。本次 100 局一例也没有出现。

## 三、random_yaw 的范围
`spawn_random_cube(random_yaw=True)` 取 `yaw = u·2π`，也就是**全 [0, 2π)**；方块有 90° 对称，所以有效朝向是全覆盖的。goal 在 `spawn_random_target` 里被强制设为 `random_yaw=False`。

## 四、W 的定义（gen_layouts.py，numpy 主批种子 20260925、补充批种子 20260926）
- goal、方块、杆根都在环带 0.06≤|c|≤0.24 且 x≤0.20 的区域里按面积均匀抽取。
- 杆 yaw ∈ U(−π, π)，方块 yaw ∈ U(0, 2π)。
- 方块与 goal 相距 ≥0.10；方块离杆身线段 ≥0.04；杆轴线段离原点 ≥0.05。
- 演示段与执行段各自独立抽取；两次 initialization 的 way_idx 都填同一个值，三种 way 各占 1/3。
- 规格键：`peg_offsets=[±0.2, root_x, root_y∓0.2]`，`goal_xy=[x,y]`，`cube_pose=[x,y,yaw]`，`peg_yaw`。

## 五、结果（主批 36 + 补充批 108 = 144 局，已全部跑完）
| 批次 | peg_push | gripper_push | grasp_putdown | 合计 |
|---|---|---|---|---|
| 主批 36 局 | 5/12 (42%) | 10/12 (83%) | 12/12 | 27/36 |
| 补充批 108 局 | 19/36 (53%) | 25/36 (69%) | 36/36 | 80/108 |
| 合计 144 局 | 24/48 (50%) | 35/48 (73%) | 48/48 | 107/144 |
| V5 xhard 基线（P2） | 5/8 | 6/8 | 8/8 | 19/24 |

失败类别（144 局）：
- **peg_push**（24 例）：抓杆阶段 14 例（PlannerExhausted 9、FailsafeTimeout 3、没抓起 2），钩推阶段 10 例（推没到位 7、PlannerExhausted 3）。
- **gripper_push**（13 例）：推没到位 12 例（执行段 7、演示段 5），PlannerExhausted 1 例。
- 全部局都没有出现 SceneGenerationError 或 EpisodeSpecError。

失败布局的特征（按失败所在的那一段取值）：
- **peg_push 的关键因素是抓杆点（杆尾，root−0.1u）的 x 坐标**：失败段抓杆点 x 中位 0.196、离基座中位 0.816；成功段分别是 −0.056 和 0.589。按局统计：两段中抓杆点 x 较大者 >0.15 的局只成功 2/17，≤0.15 的成功 22/31；阈值换成 >0.10 时是 7/25 对 17/23。原因是杆根被限制在 x≤0.20，但 yaw 全 2π 让杆尾能伸到 x≈0.29。
- 方块、goal 自身离基座的距离与成败关系不大：失败段和成功段的中位数基本持平。
- **gripper_push 的关键因素是推距**：失败段推距中位 0.277，成功段 0.229；goal x 中位分别是 +0.043 和 −0.040。推距（两段取大）>0.30 的局成功 12/22，≤0.30 的成功 23/26。
- 杆 yaw、方块 yaw 所在的象限没有看出规律。
- grasp_putdown 在整个 W 里 48/48 全部成功，说明可达性本身不是瓶颈。

图：`w_results.png`（144 局；上排是俯视图，下排是按最远物体离基座距离分箱的成功率）。已经目视检查过。

## 六、结论：W 里建议砍掉的部分
1. **杆的放置区域要单独收紧**：限制抓杆点（杆尾）的 x ≤ 约 0.10，或者杆根沿用 V5 的 y=±0.2 小框。不要让「杆根在整个环带 + yaw 全 2π」组合出现，这是 peg_push 失败（主要是抓杆 PlannerExhausted）的主要来源。
2. **限制推距**：方块与 goal 的距离上限约 0.30，同时 goal 在 +x 侧不宜超过约 0.10。对应 gripper_push 推不到位的问题。
3. 方块与 goal 的环带 0.06～0.24、方块 yaw 全 2π 都可以保留：grasp_putdown 100%，方块与 goal 的位置本身和成败关系不大。
4. 局数少，这些阈值只能当方向，定参数之前应当按收紧后的 W 再复测一轮。

## 七、产物
gen_layouts.py、probe_worker.py、run_probe.py、analyze.py、features.py、plot_results.py；layouts.csv、results.jsonl、specs.json（主批）；supp/（补充批的同名文件）；features.json；w_results.png；summary.md。逐局 h5 和视频目录 episodes/ 已按「收尾只保留最终产物」删除；_novideo_run/ 只留关视频那批作废运行的日志与结果。
