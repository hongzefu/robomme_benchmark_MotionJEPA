# V4 步 3b：VideoUnmaskSwap + ButtonUnmaskSwap 的 xhard（g5 组）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`）。录像器未改（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 通过）。
> 对应计划 2.7、2.10、2.11、2.21；A7（旧 xhard 作废）、B3/B4/B13、H1、H2、N5、N11、N12。

## 一、改动清单（文件／锚点／改什么／为什么／怎么验）

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/unmask_swap_xhard.py`（新增） | 两个 UnmaskSwap 共用件：`SWAP_WINDOW_START=64` / `SWAP_WINDOW_STEPS=50` / `XHARD_SWAP_SPEED_MULTIPLIER=1.5`；`scaled_window_steps`（倍率 1 原样返回整数基数，1.5 ⇒ 33）；`XHARD_DISTRACTOR` 申报值；`predict_swap_sweeps`（按 `step` 同一语义预演交换序列）；`sample_distractors`（外环＋相机可见＋避障＋避开预演扫掠的拒绝采样）；`build_distractors`；`distractor_generator`（专用随机流） | B4 取整；B3/B13 干扰容器；H1 碰撞；N5 随机流 | `test_v4_xhard_unmaskswap.py` 的窗口、采样、专用流、预演用例 |
| `VideoUnmaskSwap.py::config_xhard` | 覆盖旧 `{swap 4~5, pick 2}` 为 `{bin 4, swap [8,12], pick [3,3]}`；类属性 `SWAP_WINDOW_START/STEPS` | A7；2.10 | 单测锁原三档逐字不变、xhard 新值 |
| `VideoUnmaskSwap.py::NATIVE_SAMPLING` | 新增 `parameters.xhard.object_selection.pickup_selected_indices=[0,1,2]`（原 `object_selection` 一字不动） | 2.10 铁闸：外部改不了抓取序号，只能源码提供；单列而不塞进 `object_selection`，原三档的操作元视图不变 | 与 `00e2ef4` 的 `_operand_view` 逐项相等（空差集）；`test_historical_action_operands*` 仍过 |
| `VideoUnmaskSwap.py::_native_decision` | 加 `xhard: {swap_speed_multiplier: 1.5, distractor: {...}}` | 新 decision 键放 `xhard` 子键下，守卫对原三档可见部分仍全等 | `test_decision去掉xhard后与原值相同`、守卫放行/拒绝用例 |
| `VideoUnmaskSwap.py::_resolve_sampling_config` | 旧快照缺 `parameters.xhard` 时按源码补齐；`parameters.xhard` 并入 JSON 全等铁闸 | 兼容 v2/v3 旧格式快照；外部仍改不了 | `test_vus_外部改不了xhard抓取序号_旧快照缺项按源码补齐` |
| `VideoUnmaskSwap.py::__init__` | 计算 `swap_window_start`（64）与 `swap_window_steps`（原三档读 decision 顶层倍率 1 ⇒ 50；xhard 读 `decision.xhard` 的 1.5 ⇒ 33）；xhard 记 `actions.swap_window`；`_xhard_collision_checks`；`distractor_bins=[]`；n_swaps/n_picks 取值点带 `decision_key`；xhard＋链路甲 `episode_spec` 直接拒绝 | 2.10：`swap_speed_multiplier` 接上消费点；链路甲已退役 | reset 探针原三档零差异；xhard 冒烟窗口 64+33k |
| `VideoUnmaskSwap.py::_load_scene` | xhard 抓取序号改读 `parameters.xhard`；新增 `elif xhard and pick_times>2` 循环（每一抓前先放下上一个）；末尾（`inject_fail_grasp` 之后）调 `_spawn_xhard_distractors` | 原分支 `== 2` 严格相等，pick=3 会退化为 1 抓；N5 | 冒烟 `tasks=6`、3 个 pickup；AST 用例锁「末尾调用＋用专用流」 |
| `VideoUnmaskSwap.py::_spawn_xhard_distractors`（新增） | 以 4 个容器为障碍、以预演扫掠为约束采样 3 个干扰容器，建 actor，存 `distractor_bins/cubes/cube_colors` | B3/B13/H1 | 冒烟 40/40 外环且可见、请求=实际=3 |
| `VideoUnmaskSwap.py::_initialize_episode` | xhard 乙通道做初态复核（容器＋干扰容器两两真实碰撞盒），拒绝抛 `BinCollisionError` | H1 初态 | 冒烟 `_runtime_checks` 含两次 `initial`（构造期与外层 reset） |
| `VideoUnmaskSwap.py::_object_states_for_collision` / `_check_swap_sweep_from_actual` | 显式并入 `distractor_bins`（原三档为空列表） | H1 | 演示 6/6 无 `BinCollisionError` |
| `VideoUnmaskSwap.py::step` | 搭档解析后：甲通道不变；新增 `elif _xhard_collision_checks` 做含干扰容器的连续扫掠检查；两处 `32*2` 改读 `swap_window_start` | H1 扫掠；B4「预交换锁定终点 = 首段起点」 | `test_real_swap_resolution*` 仍过（用 `getattr` 兜底，SimpleNamespace 不受影响） |
| `VideoUnmaskSwap.py::_refresh_swap_schedule` | 通式改读 `swap_window_start/steps` | B4：把 50 提成具名常量 | `test_swap_schedule_generic.py` |
| `ButtonUnmaskSwap.py::config_xhard`（新建）、`configs` | `{bin 4, swap [6,8], pick [3,3]}` | 2.11 | 单测 |
| `ButtonUnmaskSwap.py::NATIVE_SAMPLING.swap_window` | 值仍 `{64, 50}`，改为引用具名常量 | 2.11「真正被消费」 | `test_bus_native_swap_window*` |
| `ButtonUnmaskSwap.py::_native_decision` | 加 `xhard: {swap_speed_multiplier: 1.5, distractor: {...}}`；swap/pick 取值点带 `decision_key` | 同上 | 单测 |
| `ButtonUnmaskSwap.py::__init__` | 读 `native.swap_window` 与倍率得 `{64, 50}`（原三档）/`{64, 33}`（xhard）；`_xhard_collision_checks`、`_runtime_checks`、`distractor_bins` | 2.11 | 冒烟窗口 64+33k |
| `ButtonUnmaskSwap.py::_refresh_swap_schedule` | 写死的三分支换成通式（对 n=1/2/3 逐项相同，n≥4 不再 `AttributeError`） | 2.11 头号阻碍 | `test_unmask_通式与原三分支逐项相同[ButtonUnmaskSwap-*]` |
| `ButtonUnmaskSwap.py::_load_scene` | 补 `for k in range(3, swap_times)` 发起者槽位；末尾调 `_spawn_xhard_distractors`（按钮 OBB 也作障碍、预演用 XY 轴） | 2.11；N5（本环境 `self.generator` 还要在 `_initialize_episode` 给 `inject_fail_grasp` 用，所以干扰采样必须走专用流） | 冒烟 20/20；原三档不进循环（swap≤3） |
| `ButtonUnmaskSwap.py::_initialize_episode` | xhard 初态复核；xhard 把「按第二个按钮」的 solve 换成 `_solve_press_then_wait_swaps`；新增 `if xhard and pick_times>2` 循环 | 见「计划外」第 1 条；pick 分支 `== 2` 严格相等 | 修前演示 0/2、修后 6/6 |
| `ButtonUnmaskSwap.py::_solve_press_then_wait_swaps`（新增） | 按按钮后 `solve_hold_obj_absTimestep` 等到 `swap_schedule[-1][3]`；按钮解法返回 -1 时原样返回 | 同上 | `test_bus_按钮后等待交换结束_失败信号不被吞` |
| `ButtonUnmaskSwap.py::_object_states_for_collision` / `_check_state_readonly` / `_check_swap_sweep_from_actual`（新增）、`step` | 本环境原先完全没有碰撞检查；只在 xhard 调用，旁观者含干扰容器；两处 `32*2`/`64` 改读 `swap_window_start` | H1；B4 | 演示 6/6 无碰撞拒绝 |
| `utils/task_goal.py::get_language_goal` | 两个 UnmaskSwap 分支各加 `elif pick_times >= 3` 三抓文本（原 1 抓／2 抓两支逐字不变） | 3 抓会落到 1 抓文本，且文本进视频文件名与 metadata | `test_三抓任务目标文本`；演示视频文件名为三抓文本 |
| `scripts/parity/train_split_audit.py::NEUTRAL_KEYS` | 撤销两条 `*.decision.swap_speed_multiplier` 豁免 | 已有消费点 | `test_审计已撤销两条swap_speed_multiplier豁免` |
| `tests/lightweight/test_swap_schedule_generic.py` | `_env` 增 `swap_window_start/steps`；加入 ButtonUnmaskSwap 的原三分支等价与「无写死分支」；`test_xhard_四五次首尾相接每段五十帧` 拆成 `test_repick_四五次…`（VideoRepick 通式不变）＋`test_xhard_v4_首尾相接每段三十三帧`（VUS 8/12、BUS 6/8） | 步 3a 连带：旧 xhard 语义作废 | 25 passed |
| `tests/lightweight/test_window_timeline.py` | `test_unmask_xhard_四五次调度` 改为 `test_unmask_xhard_v4调度不走甲链路窗口`（n=8/12：甲 `windows.py` 常量 = 源码原三档 64/50；V4 xhard 每段 33、与甲口径不同）。`GROUPS` 断言未改（见计划外 4） | 同上；`windows.py` 属链路甲按 N6 不动 | 34 passed |
| `tests/lightweight/test_v4_xhard_unmaskswap.py`（新增） | 33 个纯 CPU 用例（不起 SAPIEN 场景） | 定向单测 | 33 passed |

## 二、干扰容器怎么放（落地细节）

- 个数 3；装方块个数 `randint(1,2)`；方块颜色 = 色池 `[yellow, cyan, magenta]` 的一次 `randperm` 取前 k 个；前 k 个容器装方块，
  方块与藏物方块同尺寸（`cube_half_size/1.2`），被容器扣住。命名 `distractor_bin_<i>` / `distractor_cube_<色名>`，**不设 `bin_<i>` 属性**。
- 位置：在 `[-0.45,0.45]²` 里均匀抽，接受条件依次为 ① 外环 `max(|x|,|y|) ≥ 0.2675`；② 相机可见（外接圆保守判：`x+r ≤ 0.43` 且
  `|y|+r ≤ 0.49 − 0.45(x+r)`，由 B13 表 7 个点拟合，逐点误差 ≤ 0.005）；③ 与已在场容器、按钮避让圆、已放干扰容器的外接圆间隙 ≥ `min_gap=0.04`；
  ④ 对预演出的**每一段**交换扫掠做 `check_swap_sweep(发起者, 搭档, [候选])`，任一段不能证明分离就拒绝。yaw 与原容器同为 `[0,90)`°。
  每个 512 次预算，用尽抛 `SceneGenerationError`（2.2④，不静默截断）；`layout.distractors_requested/placed` 两个值都记进规格。
- 随机流：全部抽样走 `torch.Generator().manual_seed(seed + 0x5D157AC7)`，主流一次都不多抽。原三档根本不进此分支。
- 取值点：`objects.distractors.n_with_cube`（`decision_key=xhard.distractor.with_cube_range`）、`objects.distractors.cube_colors`
  （`xhard.distractor.colors`）、`layout.distractors.<i>`（`[x, y, yaw]`）、`layout.distractors_requested/placed`、`actions.swap_window`。
- 运行时（H1）：初态复核与每段交换开始时的连续扫掠复核都并入干扰容器；子步检查仍只在链路甲开（每个子步全量 SAT 代价过高，
  扫掠检查已是整段解析证明）。

## 三、实测数字

**① 原三档 reset 零差异（必须 PASS）**

```bash
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks VideoUnmaskSwap,ButtonUnmaskSwap --out /tmp/g5_probe.json
# PROBE_DONE rows=18 ok=18
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json /tmp/g5_probe.json
# RESET_REGRESSION=FAIL compared=18 diff=0 missing=126
```

本组两环境 18 行 `diff=0`；`FAIL` 只因 `missing=126`（基线里其余 14 个环境不在本次探针里，按约定属预期）。终版代码复跑一次，结果相同。

**② xhard reset 冒烟（每环境 20 个 seed，`900000+101i`）**

| 环境 | 成功 | swap 次数分布 | 装方块个数 | 方块颜色 | 其他 |
|---|---|---|---|---|---|
| VideoUnmaskSwap | 20/20 | 8:6, 9:3, 10:1, 11:3, 12:7 | 1:8, 2:12 | 品红 15 / 青 10 / 黄 7 | 全部 `native-newvalue/1`；pick=3、任务 6 条；窗口 64+33k 首尾相接 |
| ButtonUnmaskSwap | 20/20 | 7:8, 8:12（见计划外 5） | 1:8, 2:12 | 同上 | 同上；任务 7 条 |

每条都断言了：干扰容器 3 个、不在 `spawned_bins`、中心落在外环且整体可见、`requested=placed=3`、`_runtime_checks` 有两次 `initial` 且无拒绝。
失败类型：无。

**③ xhard 演示（本机 sm_89，只作调试，不进判据）**

| 组合 | 条数 | 成功 | 总步数 | 其中视频演示段 | 非演示段（计 1302 配额） | 单条墙钟 |
|---|---|---|---|---|---|---|
| VUS swap=8（端点） | 2 | 2 | 726 / 724 | 330 / 330 | 396 / 394 | 53 / 59 s |
| VUS swap=12（端点） | 2 | 2 | 855 / 887 | 462 / 462 | 393 / 425 | 87 / 68 s |
| VUS 默认范围＋recovery xy（ep 4，swap=10） | 2 | 2 | 882 / 913 | 396 / 396 | 486 / 517 | 71 / 70 s |
| BUS swap=6（端点） | 2 | 2 | 654 / 668 | 0 | 654 / 668 | 50 / 59 s |
| BUS swap=8（端点，修后） | 2 | 2 | 719 / 719 | 0 | 719 / 719 | 57 / 63 s |
| BUS 默认范围＋recovery z（ep 1） | 2 | 2 | 710 / 728 | 0 | 710 / 728 | 63 / 60 s |
| BUS swap=8（端点，**修前**） | 2 | 0 | — | — | — | 60 / 47 s，`DatasetGenerationError: 环境报告失败` |

口径 14 的四个端点（VUS 8/12、BUS 6/8）演示级各 2/2，**没有 0 成功的组合**；两环境合计演示 12/12（修后）。ButtonUnmaskSwap 全部任务 `demonstration=False`，
8 swap + 3 pick 实测最长 728 步，低于 1302（余量约 44%），比计划估计的 ≈960 低。

**④ 测试**

- 新增 `test_v4_xhard_unmaskswap.py` 33 passed；`test_swap_schedule_generic.py` 25 passed；`test_window_timeline.py` 34 passed。
- 轻量全量（`-m 'not gpu and not slow'`）：47 failed / 559 passed / 22 skipped / 12 errors（141 s）。与已知基线 46 项相比多 1 项：
  `test_sampling_config_split.py::test_snapshot_matches_source`——v4 快照 `scripts/configs/newtask-v4/sampling_config.json` 与改后源码提取结果不一致，
  属「改源码后快照待主 agent 统一重导」的预期现象（按约定本组不提交该快照）。其余 46 项文件分布与计数与基线相同。

## 四、计划外

1. **ButtonUnmaskSwap xhard 原解法会在容器还在交换时去抓**：本环境按完两个按钮通常只到约第 200 步，而 6~8 次交换要到
   `64+33n = 262~328` 步才结束（hard 的 3 次交换在 214 步结束，恰好赶上，所以原三档没暴露）。修前 swap=8 演示 0/2，抽帧可见
   第 250 帧已进入「pick up the container」子目标、容器仍在移动。处置：只在 xhard 把「按第二个按钮」的 solve 换成「按完后
   `solve_hold_obj_absTimestep` 等到最后一段交换结束」。放在按钮任务而不放在第一抓，是因为 `inject_fail_grasp` 会整个替换被选中抓取任务的
   solve，等待会被丢掉。修后 6/6（含 recovery z 两条）。这改变了 xhard 演示轨迹（按钮子目标末尾多一段原地等待），不影响任务判定与原三档。
2. **H1 的「运行时检查」在乙通道上原本不存在**：VideoUnmaskSwap 的初态／扫掠／子步检查全部只在链路甲（`episode_spec`）打开，
   ButtonUnmaskSwap 则完全没有检查代码。只「并入干扰容器」不会让 V4 路径多查任何东西，因此本组把 xhard 乙通道的初态＋扫掠检查也打开，
   并在 reset 时按确定性交换序列预演扫掠、用它约束干扰容器落点（运行时检查因此基本不会触发，是兜底）。原三档的乙通道仍不检查（H2）。
3. **VideoUnmaskSwap 的 xhard 抓取序号放在 `parameters.xhard` 而不是 `object_selection` 里**：`generate_dataset_newseed` 的
   `SAMPLING_OPERAND_PATHS` 把整个 `parameters.VideoUnmaskSwap.object_selection` 当操作元，与 `00e2ef4` 对照；塞进去会让原三档的操作元视图变化。
   单列后 `_operand_view` 与基线逐项相等，`_cross_check` 要求的 `pickup_indices = selection_cfg["pickup_selected_indices"]` 原句保留。
4. `test_window_timeline.py` 的 `GROUPS` 断言锁的是链路甲 `windows.py::GROUPS == GROUPS_V3`（14 组），属甲的产物按 N6 不动，本组没改；
   它不锁 UnmaskSwap 的 4~5 次语义。`test_episode_action_sampling.py` 里 xhard 参数化只涉及「Unmask 4 个容器」，V4 仍是 4 个，未改（该用例本就在 20 项既有失败里）。
5. ButtonUnmaskSwap 冒烟的 20 个种子（`900000+101i`）恰好一次都没抽到 swap=6：这是种子步长造成的，`randint(6,9)` 在种子 0~1999 上为 6:632 / 7:697 / 8:671，均匀；
   swap=6 端点已用收窄配置单独验证。
6. 同一 seed 下两个环境的干扰容器前几个位置相同（专用流只由 seed 决定）；正式抽签里两环境 seed 不同，无影响。

## 五、待用户决策

1. **干扰容器里的「其他颜色」方块是否要在揭示段被看到**：按计划 2.7①「不进揭示动画」，干扰容器不被 `lift_and_drop_objects_back_to_original`
   抬起，里面的黄/青/品红方块全程被扣住、画面里看不见（只有策略误抓干扰容器时才会露出）。若希望「其他颜色」在视觉上起干扰作用，
   需要让干扰容器也参与前 64 步的揭示——这会改变揭示画面，本组未做，等用户定。
2. **误抓干扰容器是否判失败**：现在各抓取任务的 `failure_func` 只列 `spawned_bins` 里的非目标容器，抓起干扰容器不会立刻判失败
   （子目标不完成，最终靠步数上限失败）。是否要把 `distractor_bins` 并入 xhard 的 `failure_func`，等用户定。
3. 干扰容器的专用随机流种子盐（`0x5D157AC7`）与采样预算（512）是实施方选的常量，未进 decision；如需与其他环境统一口径请指示。

## 六、复现命令

```bash
ln -s /data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv .venv
# 端点收窄配置：native_blocks 导出后把 xhard 交换次数钉成端点（VUS 改 native.parameters.configs.xhard，BUS 改 decision.swap_count_range.xhard）
uv run --no-sync python -m scripts.parity.v4_demo_probe --task VideoUnmaskSwap --n 2 --gpu 0 \
    --sampling-config <VideoUnmaskSwap-swap12.json> --out artifacts/newtask-v4/demo-probe/VideoUnmaskSwap-g5-swap12
uv run --no-sync python -m scripts.parity.v4_demo_probe --task ButtonUnmaskSwap --n 2 --gpu 0 \
    --sampling-config <ButtonUnmaskSwap-swap8.json> --out artifacts/newtask-v4/demo-probe/ButtonUnmaskSwap-g5-swap8
uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_unmaskswap.py tests/lightweight/test_swap_schedule_generic.py \
    tests/lightweight/test_window_timeline.py -q
```

演示产物在 worktree 的 `artifacts/newtask-v4/demo-probe/*-g5-*`（`artifacts/` 已 gitignore，不入库）。
