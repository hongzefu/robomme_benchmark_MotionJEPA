# V4 步 3b（g4）：VideoUnmask / ButtonUnmask 的 xhard

> 红线 N1 的逐步报告。对应 [NEWTASK_RELEASE_V4_PLAN.md](../../../NEWTASK_RELEASE_V4_PLAN.md) 2.7、2.8、2.9、2.21（Unmask 简图）。
> 起点 `00e2ef4`（12.66）。录像器未改（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 为真，`RECORDER_FROZEN=PASS`）。
> 用户已定数：G2（区域不动、`min_gap_factor` 0.75、容器数 N=8）、B2（干扰色黄/青/品红）、B3（干扰做成额外容器、不参与 swap）、
> B13（外环 `max(|x|,|y|) ∈ [0.2675, 0.45]`、3 个里 1~2 个含 cube）、H1（干扰容器进碰撞检查）、H2（只挂 xhard）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `src/robomme/robomme_env/VideoUnmask.py::VideoUnmask.config_xhard`／`configs`（`ButtonUnmask.py` 同名同改） | 新增 `config_xhard = {'bin': 8, 'pick': 3}` 并进 `configs` | 2.8/2.9：pick 3；G2：容器数 8 | `test_xhard_values_match_user_decisions`；原三档 `configs` 逐字不变由 `test_original_three_configs_unchanged` 锁住 |
| 两文件模块常量 `XHARD_BIN_LAYOUT` / `XHARD_DISTRACTOR`＋`_native_decision` | decision 增加 `bin_layout_policy.xhard = {min_gap_factor: 0.75}` 与顶层 `xhard.distractor = {count 3, ring_max_abs_xy [0.2675,0.45], cube_count_range [1,2], color_pool [yellow,cyan,magenta], min_gap_factor 0.75, max_trials 256}`；`pick_count`/`count` 两个按难度字典经 `configs` 自动多出 `xhard` 键；`distractor: None` 原样保留 | 公共说明：xhard 专属新键放在名为 `xhard` 的子键下，守卫自动放行、原三档可见部分不变；2.2②：每个叶子键都有消费点（见下两行） | `test_decision_visible_to_original_three_unchanged`（去掉 xhard 键后与改前逐字相同）；`test_guard`（默认放行、去 xhard 的旧快照放行、已申报 xhard 值可改、申报外 xhard 键拒绝、原三档值改动拒绝） |
| 两文件 `_load_scene` 的容器循环 | xhard 下：①间距系数取 `bin_layout_policy.xhard.min_gap_factor`（原三档仍读 `native.positions.bins.min_gap_factor`，表达式只是把系数提成局部变量，值与乘法完全相同）；②断言 `native.parameters.step_bin_scan ≥ 容器数`；③`record("layout.bin_count.requested/placed")`；④`except RuntimeError` 在 xhard 下改抛 `SceneGenerationError`（原三档照旧 `break`） | G2 定数；2.2④ 不许静默截断；2.8「step_bin_scan 须 ≥ 容器数」（现值 15 ≥ 8，无需改 native） | reset 探针原三档 diff=0；xhard 冒烟 40/40 局 `bin_count = {requested 8, placed 8}` |
| 两文件 `_load_scene` 的任务表＋新方法 `_append_xhard_pick_tasks` | xhard 走新方法：按 `pick_count` 循环追加「放下 bin_{k-1} → 抓 bin_k（藏 `color_names[k]`）」，条目逐项照抄原 hard 第 2 抓，只把写死的 `bin_0/bin_1`、`color_names[0]/[1]` 换成按 k 取；lambda 用默认参数绑定当次容器；记 `objects.n_picks`、`objects.pick_order`；设 `self.xhard_pick_count`。原 `> 1` 分支改成 `elif`，代码逐字未动。ButtonUnmask 第一个 pickup 的单元素列表形态（`failure_func`/`solve` 返回列表）在循环之前、原样保留 | 2.8/2.9：原分支写死两抓，pick=3 只会生成 2 抓 | `test_xhard_pick_loop_structure`（任务名、segment、lambda 绑定、`task4recovery` 扫到 3 个抓取）；xhard 冒烟每局 6 个任务（VideoUnmask：static + 3 抓 + 2 放；ButtonUnmask：按钮 + 3 抓 + 2 放）；演示时长中位 ≈480（Video）/≈515（Button）步，与计划估算 485/530 一致 |
| 两文件 `_load_scene` 末尾 | xhard 下调 `spawn_ring_distractor_bins`，结果存 `self.distractor_bins` / `self.distractor_cubes`；**不进** `spawned_bins`、**不用** `bin_<i>` 命名 | B3/B13；2.7①：不进揭示动画、不被当搭档；N5：放在全部既有取值点之后（VideoUnmask 在 `inject_fail_grasp` 之后，它与场景共用同一个 generator；ButtonUnmask 的恢复抽样走构造器的 `self.generator`，场景 generator 最后一次既有抽样是 `color_order`） | 冒烟 `bin_names_ok`（`bin_8..bin_19` 属性都不存在）；原三档不进入该分支 |
| `src/robomme/robomme_env/utils/unmask_distractors.py`（新增）::`spawn_ring_distractor_bins` 等 | 外环干扰容器：在 `[-0.45,0.45]²` 均匀抽点、拒绝 `max(|x|,|y|) < 0.2675`；相机可见判据（容器按任意 yaw 外接正方形取 8 个角点投到前视相机，全部在 256×256 画面内）；避让判据与 `spawn_random_bin` 同一套（actor OBB 外扩 `min_gap`、预制 OBB 原样、候选点距 ≥ 0.0275 + `min_gap`），`avoid` 里含 region 内 8 个容器、3 个藏物 cube、ButtonUnmask 的按钮 OBB，已放干扰容器随即入 `avoid`；通过后才抽 yaw；再抽 cube 个数 `randint(low, high+1)`、挑容器 `randperm(3)[:n]`、挑颜色 `randperm(3)[:n]`（不放回）；每个取值点经 `recorder.value(..., decision_key="xhard.distractor.*")`，请求/实际数经 `record`，放不满抛 `SceneGenerationError`；`color_pool` 与全局色池不等直接 `ValueError` | 共用工具 `spawn_random_bin` 只支持方形区域、不能插入可见性判据，且按 N12/公共说明不改工具函数 ⇒ 另写 xhard 专用路径；本组两环境无 swap，H1 的「碰撞检查」在这里就是放置期避让（Swap 组可直接复用本模块并把 `distractor_bins` 并入扫掠检查） | `test_distractor_geometry_helpers`；冒烟 40/40 局 `ring_ok`、`vis_ok` 全真，干扰容器与任何容器外廓最小间距 29.6 mm |
| `src/robomme/robomme_env/utils/task_goal.py::get_language_goal`（VideoUnmask/ButtonUnmask 两支）＋新增 `_unmask_pick_count` / `_unmask_multi_pick_clause` | 抓取次数 > 2 时逐个列出三个颜色；原 `> 1` / else 两支改成 `elif` / else，文本逐字不变；xhard 下次数优先读 `env.unwrapped.xhard_pick_count`（外部配置改了 decision 的 xhard 值时类属性不会跟着变） | 2.8：原来只有「1 抓 / >1 抓」两支，pick=3 会输出两抓文本，且该文本进视频文件名与 HDF5 metadata | `test_TaskGoal.py` 新增 3 条（逐字比对 pick=3 文本、次数优先读实际值）；原三档 4 条断言未改、仍通过 |
| `tests/lightweight/test_v4_xhard_videounmask_buttonunmask.py`（新增） | 13 条纯 CPU 结构性测试（只导入模块，不起 sapien 场景） | 公共说明「定向单测」 | 13 passed |

pick=3 的文本（实施方措辞，见「待用户决策」第 4 条）：
- VideoUnmask：`watch the video carefully, then pick up the container hiding the {c0} cube, next pick up another container hiding the {c1} cube, finally pick up another container hiding the {c2} cube`
- ButtonUnmask：`first press the button, then pick up the container hiding the {c0} cube, next pick up another container hiding the {c1} cube, finally pick up another container hiding the {c2} cube`

**2.7④（只影响 xhard）**：`inject_fail_grasp` 通过 `task4recovery` 扫描含 `solve_pickup_bin` 的非演示任务，xhard 下候选从 2 个变 3 个（任务表下标 VideoUnmask `[1,3,5]`、ButtonUnmask `[1,3,5]`），那次 `randint(0, len)` 的分布随之改变；结果照旧记进 `actions.recovery.selected_action_index`。原三档候选数不变。另外 VideoUnmask 的恢复抽样与场景共用同一个 generator，而干扰容器排在它之后 ⇒ **VideoUnmask xhard 的干扰容器位置取决于本局是否开了恢复模式**（开与不开是两套随机流位置）；这是 N5「追加在全部既有取值点之后」的直接后果，规格里两者都经 `value()` 冻结，回注不受影响。ButtonUnmask 的恢复走构造器 generator，不受影响。

**N5 核对**：ButtonUnmask 构造期那次 `randint(1,6)` 占位抽样（`actions.sampling_trace.constructor_draw`）未改一个字符；两环境新增的随机调用全部在 `_load_scene` 末尾、只在 xhard 分支。

## 二、原三档零差异

```bash
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks VideoUnmask,ButtonUnmask --out /tmp/g4_probe.json
# PROBE_DONE rows=18 ok=18
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json /tmp/g4_probe.json
# RESET_REGRESSION=FAIL compared=18 diff=0 missing=126
```

`missing=126` 全部是基线里其余 14 个环境（本次只采了本组两环境的 18 行，属预期）；本组 18 行 `diff=0`，两环境均不在「只在一侧」清单里 ⇒ 本组判定 **PASS**。

## 三、xhard reset 冒烟（每环境 20 seed，`seed = 900000 + 101·i`，只 reset）

脚本逻辑：`gym.make(..., difficulty="xhard")` → `reset` → 读规格与 actor 位姿；容器外廓间距按 actor 真实四元数取足迹（半边 0.03 的正方形）算两两凸多边形最小距离。

| 指标 | VideoUnmask | ButtonUnmask |
|---|---|---|
| reset 成功 | **20/20** | **20/20** |
| `spec_kind` | 全部 `native-newvalue/1` | 全部 `native-newvalue/1` |
| region 内容器（请求/实际） | 8/8（20 局全满） | 8/8（20 局全满） |
| 干扰容器个数 | 3（20 局） | 3（20 局） |
| 干扰 cube 个数分布 | 1 个 9 局、2 个 11 局 | 1 个 8 局、2 个 12 局 |
| 干扰容器中心全在外环 `[0.2675, 0.45]` | 是 | 是 |
| 干扰容器 8 角点全在画面内 | 是 | 是 |
| region 内容器外廓最小间距 | **15.8 mm** | **18.8 mm** |
| 干扰容器与任何容器外廓最小间距 | 29.6 mm | 29.6 mm |
| 任务数 / 抓取数 | 6 / 3 | 6 / 3 |
| 回注 mismatch | 0 | 0 |

15.8 mm 与 G2 报告的理论下界 `0.0275 + 2·0.015 − 0.03·√2 = 15.1 mm` 吻合（`spawn_random_bin` 的 `min_gap` 双计是既有行为，未改）。

## 四、xhard 演示小样本（本机 sm_89，GPU 1；只作调试，不进判据）

入口 `scripts.parity.v4_demo_probe`，输出在 `artifacts/newtask-v4/demo-probe/<环境>-g4*/`（已 gitignore）。组合按口径 14 取：
离散量 `cube_count ∈ {1, 2}` 逐值；连续量方环取端点带（内缘 `[0.2675, 0.2875]`、外缘 `[0.43, 0.45]`，经 `--sampling-config` 收窄已申报的 xhard 条目）；
其余 xhard 参数（pick 3、容器 8、间距 0.75、干扰容器 3）都是单值。恢复模式按 `--episode` 分档（1 ⇒ z，4 ⇒ xy，9 ⇒ 无）。

| 组合（seed 基） | 恢复模式 | VideoUnmask | ButtonUnmask |
|---|---|---|---|
| 默认 xhard（910000，cube 数随机） | 无 | 4/4 | 4/4 |
| cube=1、全环（920000） | 无 | 4/4 | 4/4 |
| cube=2、全环（930000） | 无 | 4/4 | 4/4 |
| cube=1、内缘带（940000） | 无 | 2/2 | 2/2 |
| cube=1、外缘带（950000） | 无 | 2/2 | 2/2 |
| cube=2、内缘带（960000） | 无 | 2/2 | 2/2 |
| cube=2、外缘带（970000） | 无 | 2/2 | 2/2 |
| 默认 xhard（980000） | z | 2/2 | 2/2 |
| 默认 xhard（990000 + 991000） | xy | **4/6** | **5/6** |
| **合计** | | **26/28** | **27/28** |
| 对照：hard（990000） | xy | — | 4/4 |

- **口径 14：没有任何端点组合演示 0 成功**（cube 个数 1/2 × 方环内缘/外缘，四个组合两环境各 2/2；全环两个端点各 4/4）。
- 演示时长：无恢复模式时 VideoUnmask 446~485 步、ButtonUnmask 500~520 步，与计划估算（≈485 / ≈530）一致，远低于 1302。
- **失败分类（3 例，全部在 xy 恢复模式）**：
  - VideoUnmask seed 990101、991000：`PlannerExhausted`（screw 三次与 RRTStar 三次均失败）——规划器在故意偏移的失败抓取之后找不到路径；
  - ButtonUnmask seed 990000：`DatasetGenerationError: 环境报告失败`——在第 2 抓（task_index 3）期间 `failure_func` 触发，即另一个非目标容器被抬离桌面超过阈值（`is_any_bin_pickup`）。从视频末段看是 xy 偏移失败抓取后的重抓碰到/带起了邻近容器。这正是「抓容器是否碰邻居（边距约 15 mm）」的风险表现，但样本太少（xy 模式 xhard 1/6、hard 对照 0/4），不能下结论。
  - 非恢复模式与 z 恢复模式 22/22（Video）、22/22（Button）全部成功，未见碰邻居失败。
- 盲区：演示成功只保证「没有邻居容器被抬过 0.15 m 阈值」，轻微碰撞/推移邻居不会判失败，本轮没有逐帧统计邻居位移。

## 五、测试

```bash
uv run --no-sync python -m pytest tests/lightweight/test_TaskGoal.py tests/lightweight/test_v4_xhard_videounmask_buttonunmask.py \
  tests/lightweight/test_v4_decision_guard.py tests/lightweight/test_xhard_utils.py -q
# 2 failed, 51 passed —— 两项失败为已知基线（test_TaskGoal 2 项：test_unknown_env_returns_single_goal_when_equal、test_swingxtimes_multiple），与本组无关
```

```bash
uv run --no-sync python -m pytest tests/lightweight/test_TaskGoalI_isList.py tests/lightweight/test_seed_layout.py -q
# 72 passed（363 s；test_TaskGoalI_isList 逐环境起 sapien，含本组两环境原三档）
uv run --no-sync python -m pytest tests/lightweight/test_sampling_config_split.py -q
# 1 failed, 32 passed —— 失败项 test_snapshot_matches_source：v4 快照与源码提取不一致（计划外第 6 条，预期；待主 agent 统一重导快照）
```

未跑轻量全量（CPU 被并行演示与别组测试占满，本组相关文件已逐个覆盖）；`test_native_sampling_config` / `test_episode_action_sampling` 不引用本组两环境的 decision 结构（grep 核对），未单跑。

## 六、实测数字（汇总）

| 验证项 | 判定行 / 数字 |
|---|---|
| 原三档 reset 零差异 | `compared=18 diff=0`（本组两环境 18 行；`missing=126` 为其他环境，预期） |
| xhard reset 冒烟 | VideoUnmask 20/20、ButtonUnmask 20/20；kind 全为 `native-newvalue/1`；容器 8/8、干扰容器 3、cube 1~2 个、外环与可见性全满足 |
| region 内容器最小外廓间距 | 15.8 mm（Video）/ 18.8 mm（Button）；理论下界 15.1 mm |
| xhard 演示 | VideoUnmask 26/28、ButtonUnmask 27/28；端点组合无 0 成功；失败 3 例全在 xy 恢复模式 |
| 定向单测 | 新增 13 条 + TaskGoal 3 条全过 |
| 录像器 | `RECORDER_FROZEN=PASS` |

## 七、计划外

1. **worktree 起点不对**：分配到的 worktree 起在 `3a5951a`（远早于 `00e2ef4`，不含 V4 任何共用件），工作区干净，已 `git reset --hard 00e2ef4` 后再开工。
2. **`step_bin_scan` 不用抬**：计划 2.8 字段表写「随容器数同步抬」，但 G2 定数后 xhard 容器数是 8（比 hard 的 15 还少），现值 15 已覆盖；只在 xhard 分支加了 `≥ 容器数` 的断言，native 值不动。
3. **B13 外环的 +x 远角出画**：外环上界 0.45 在 +x 侧超过相机可见范围（计划 B13 表：x=+0.4 处可见 y 仅 ±0.31，可见 x 上限 0.43）。「相机可见」因此不能只靠外环范围保证，已实现为显式投影判据（8 角点全在 256×256 画面内），落在外环里但出画的抽样点直接拒绝。实测 40 局全部可见，放置无压力。
4. **`build_bin` 的足迹 yaw 与规格 yaw 反号**：`build_bin` 先绕 x 轴翻 180° 再绕 z 转，实际足迹朝向是 `−yaw`。对仿真与现有判据无影响（`spawn_random_bin` 用 actor 真实 OBB）；只提醒以后按规格里的 `[x, y, yaw]` 做离线几何分析的脚本要取反（本组冒烟脚本第一版就因此把间距算成 7.4 mm，改读四元数后为 15.8 mm）。
5. **干扰 cube 在画面里永远看不见**：干扰容器按 2.7① 不进揭示动画 ⇒ 它不会被抬起，里面的黄/青/品红 cube 在整局视频里都被扣在容器下面。「增加其他颜色 distractor」的颜色信息因此只有抬起干扰容器才会暴露。按计划原样实现，是否要改见「待用户决策」第 1 条。
6. **快照测试会因源码新增 xhard 条目而失配**：`test_sampling_config_split.py::test_snapshot_matches_source` 用 `train_split_config.py extract --verify` 比对 v4 快照与源码；本组给两环境 decision 加了 xhard 条目，快照未重导前该用例必然报红（按公共说明，快照由主 agent 统一重导，本组未提交 `scripts/configs/newtask-v4/sampling_config.json`）。
7. **共用模块命名**：干扰容器工具放在新文件 `utils/unmask_distractors.py`，没有改 `utils/xhard.py` / `utils/object_generation.py`。两个 Swap 环境（别组）若需要同样的外环干扰容器，可直接复用 `spawn_ring_distractor_bins`；合并时请留意别组是否另写了同功能模块。

8. **xy 恢复模式是 xhard 下唯一出现失败的场景**：6 局里 VideoUnmask 失败 2（规划器耗尽）、ButtonUnmask 失败 1（邻居容器被带起）；hard 对照 4/4。容器间距从 hard 的 ≥65 mm 缩到 xhard 的 ≥15 mm 后，故意偏移的失败抓取与重抓更容易撞到邻居，属预期的难度上升，不是 0 成功组合，按 N10 如实记录、不调参。正式 V4f / V6 在 A40 上应单列 xy 恢复模式的成功率。

## 八、待用户决策

1. **干扰 cube 是否需要在视频里露出颜色**：现实现严格按 2.7①（干扰容器不进揭示动画），干扰 cube 全程不可见（计划外第 5 条）。若希望「其他颜色」在视频里可见，需要另定干扰容器是否也做一次抬起/放下（会改揭示段的画面与步数）。**本轮未实现，保持计划原文。**
2. **抓起干扰容器算不算失败**：现 `failure_func` 只看 `spawned_bins` 里的非目标容器；抓起干扰容器既不判失败也不推进子目标（等价于浪费步数直到超时）。计划未定，**本轮未改**，保持最保守的「不纳入」。
3. **干扰容器的间距系数与重试预算**：计划只定了外环范围与个数，未单列干扰容器与邻居的间距。本轮取与 xhard 容器同一系数 0.75（G2）与同一预算 256，二者都已申报在 `decision.xhard.distractor` 下、可由外部 `sampling_config` 覆盖。请确认或另定。
4. **pick=3 的任务目标措辞**：见第一节列出的两句（中间一抓用 `next`，末抓用 `finally`，与原两抓文本的 `another container hiding the … cube` 句式一致）。请确认措辞。
