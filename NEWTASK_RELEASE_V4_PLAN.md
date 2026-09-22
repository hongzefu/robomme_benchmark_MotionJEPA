# 新值模式：十六环境加难度与可重放生成

> 本方案以用户本轮要求为准，**只规划，不实施**。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，
> 起点提交为本文件落盘时的 `newtaskRelease-v3` HEAD，commit 编号沿用仓库现行 `<大版本>.<小版本> <中文描述>` 体例。
> 外部权威锚点仍是官方 `dataset-gen` 提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`（只用于原值回归对拍，
> 新值局与官方无可比对象）。依赖锚点为当前 `uv.lock` `ff0ffd84…` / `pyproject.toml` `d03537d6…`。
>
> **授权边界**：本文是计划，不是实施授权。`src/robomme/` 的改动自 2026-09-21 起免逐项事前批准，但每步收尾
> 必须在 `docs/validation/newtask-v4/` 出 md 报告（文件／锚点／改什么／为什么／怎么验）；录像器
> `src/robomme/env_record_wrapper/RecordWrapper.py` 全程冻结。第二节里标「待决」的量**一个都不许在实施时
> 自行填默认值**，必须先回来问用户。

# 第一部分（给人看）

## 一、总览、已定死口径与开放项

**一句话方案**：**废弃链路甲**（`scripts/injection/` 的 candidates + rollout，只覆盖四环境），
**在链路乙**（`scripts/parity/train_split_*`，十六环境、`sampling_config` + `native_episode_spec`）**上扩出新值模式**——
把 V3 里锁死的 `sampling_config.decision` 打开，让环境**按新范围自己抽、`SpecRecorder` 导出**成每局规格（3.2 路线 C），
再**沿用甲的 jsonl 封套契约**冻成 `specs.jsonl`（一行 header + 每行一条规格，带来源指纹与 `identity_sha256`），
实跑落 `results.jsonl`；同时给**推理侧**补一条读同一份快照的环境构建路径，让策略能在新值数据上评测并落
`eval_results.jsonl`；改完跑**三类对拍**（原值回归零差异、新值二次重放零差异、规格绑定反例）。

### 1.1 已定死口径

每条注明依据小节；用户原话逐字保留。

1. **废弃链路甲。** 用户原话：「废弃原来链路甲」。`scripts/injection/candidates` 与 `scripts/injection/rollout`
   不再新增运行；已进 Git 的 `candidates.jsonl` / `results.jsonl` 与 `artifacts/injection/` 产物作为历史证据
   **原样保留、不删不改**。依据 5.1，退役方式见第二部分 9.1。
2. **在链路乙上实现。** 用户原话：「在乙的基础上实现」。新值生成走 `scripts/parity/` 这套十六环境接口，
   用 `sampling_config`（`decision` 启用新值 + `native` 原规则）与 `native_episode_spec`（`SpecRecorder` 的回注通道），
   **不复活甲的 `episode_spec` 旧通道**。依据 5.2。
3. **jsonl 机制参考甲。** 用户原话：「新值注入的jsonl生成机制 参考甲的实现」。要继承的是甲的**封套契约**：
   header 内嵌配置全文与来源指纹、每行一条规格、身份散列 `identity_sha256`、字段集合**精确比对**、
   读写两端共用一个校验入口、冻结后进 Git 且禁止覆盖。**不继承**甲的 PCG64 采样器、400 条交付配额、
   分层与跨局方向平衡（V3 红线 R6 已禁）。依据 3.1，字段设计见 3.2。
4. **推理必须兼容。** 用户原话：「推理也要兼容」。现状是**完全没实现**：`BenchmarkEnvBuilder` 不认
   `sampling_config` / `native_episode_spec` / 任何 jsonl，只从 `env_metadata/{train,test,val}` 读固定 seed；
   评估侧一个 jsonl 都不写。本轮要补出一条读 V4 快照起环境的路径与一个落 `eval_results.jsonl` 的评估入口。
   依据第四节。
5. **改完跑对拍。** 用户原话：「改完后还需要跑对拍」。新值局没有官方原版可比，所以对拍换成三类：
   **原值回归**（新值开关关闭时与 V3 的 144 条基线逐位一致）、**新值可重放**（同一份规格两次生成逐位一致）、
   **规格绑定**（改坏规格必须产生差异）。判据见第五节。
6. **十六环境的改动内容以用户本轮原文为准**（1.2 逐字保留），字段映射沿用
   [NEWTASK_RELEASE_V3_PLAN.md](NEWTASK_RELEASE_V3_PLAN.md) 第二节「拟修改」列与第二部分 8.3 的派生关系表。
7. **`scripts/` 顶层五个入口不变。** [AGENTS.md](AGENTS.md) 强制规则第 12 条：顶层只允许
   `generate_dataset_newseed.py` / `seed_layout.py` / `dataset_replay.py` / `evaluation.py` / `run_example.py`，
   新增顶层文件或新建子目录**必须先与用户沟通获准**。本方案需要的新子目录见 4.3，已列为待批准项。
8. **`evaluation.py` 与上游 main 逐字节相同这一性质要保住。** 它和 `run_example.py`、`dataset_replay.py`
   的 blob SHA 与上游一致，是「评估栈未被 fork 改动」的直接证据。新值评估**另起入口**，不改这三个文件。依据 4.3。
9. **正式验收单 worker、判据只认 A40。** V3 实测：`mplib` 的 RRT 用墙钟预算（`planning_time=1`），
   4 worker 时 `BASELINE_REPEAT=FAIL(different=3064)`，单 worker 才 PASS；本机 sm_89 与 A40 sm_86 产物不同。
   新值的可重放对拍同受此约束。依据第五节。
10. **未定的量一律保留为待决，不编造默认值。** 沿用 V3 第二部分 8.3「仍需决定或保持的边界」列的纪律。
    本轮的全部开放项集中在 1.3，实施前须逐项获得用户答复。
11. **录像器冻结**，`src/robomme/` 的改动免逐项事前批准但须出 md 报告（见题注）。

### 1.2 十六环境的改动内容（用户本轮原文，逐字保留）

```text
BinFill  全部clutter, 12, color 3 个, put_in_number [5,7]
PickXtimes, 把 target 生成的位置尽可能推向边角，color 3, num [6, 15], 增加其他颜色 distractor
SwingXtimes, number [4, 10]， 增加其他颜色 distractor
StopCube,  速度最快档， number [6,15]，

VideoUnmask     增加其他颜色 distractor, clutter bin, pick 3
ButtonUnmask     增加其他颜色 distractor, clutter bin, pick 3
VideoUnmaskSwap   swap [8, 12], pick 3, 增加其他颜色 distractor, swap 速度 x1.5
ButtonUnmaskSwap, swap [6, 8], pick 3, 增加其他颜色 distractor, swap 速度 x1.5

PickHighlight, clutter, highlight number [5, 7],  block颜色任意
VideoRepick, clutter, pick times [4,6],  block颜色任意,  如果是 swap [8, 12],
VideoPlaceButton, VideoPlaceOrder,  video 里面完成2 个 block, 各自放回原位，其余不变

MoveCube, 把 cube 和 stick 生成的位置尽可能推向边角, stick 的转角更大，可以和桌面平行,  更难抓
InsertPeg, 多生成一个 stick 里 target stick 更近，stick 的转角更大，可以和桌面平行,  更难抓
PatternLock RouteStick, 最难情形 video 部分生成 20-30s
```

逐环境的字段落点、源码锚点、硬限制与改法见第二节。

### 1.3 开放项：实施前必须先问用户

源码核实后，用户原文里有 **19 处**无法直接落到代码的量或方向。分四组，每项给出建议与代价。
**这些一个都不许在实施时自行填默认值。**

#### A 组：需求本身有歧义（不澄清就没法动手）

| # | 项 | 问题 | 建议 |
|---|---|---|---|
| A1 ✅ | **「stick 可以和桌面平行」** | **杆现在已经与桌面平行**（四元数只绕世界 z、z 恒 0），原话是重言式 | **已答复（2026-09-22）：yaw 从 ±45° 放宽到 ±180°，不引入 pitch/roll。** ⇒ 不需要 z 补偿；但引出与 Panda joint7 限位的新冲突，见 B11 |
| A2 ✅ | **20~30 秒按哪个 fps 算** | 两个口径结论相反 | **已答复：按 30 fps（录像器，V3 口径）** ⇒ 需 600~900 帧；RouteStick `L ∈ [12,18]`，PatternLock 必须改 grid 或搜索策略（B8 仍待定具体做法） |
| A3 ✅ | **VideoRepick 要不要启用 swap** | 用户原文是"**如果是** swap [8,12]"，条件句 | **已答复：启用，swap `[8,12]`** ⇒ 发起者池只有 3 个的问题成为必须处理项，见 B12 |
| A4 | **MoveCube / InsertPeg 没有难度分档** | 两个类无 `configs`，`self.difficulty` 全文件无消费点 | 建议**全局改参数**（不新增分档），与现状一致 |
| A5 | **「其他颜色 distractor」的"其他"相对谁** | 相对目标三色（红蓝绿）？还是相对本局出现的颜色？ | 建议定义为"不在本局目标色池内的颜色"，并给出固定的干扰色池 |

#### B 组：数值待定（方向明确但没给具体值）

| # | 项 | 现值与约束 | 建议 |
|---|---|---|---|
| B1 | **clutter 的密度／区域／间距** | BinFill 12 块在现区域 **100% 放得下**（饱和点 16~20）；PickHighlight 现 `min_gap_factor=2` 只稳放 8~10 块而 highlight [5,7] 要 spawn ≥ 7；VideoRepick hard 区域可放 30+ | 逐环境给 `region_half_size` 与 `min_gap_factor`；**PickHighlight 必须把 `min_gap_factor` 降到 1** |
| B2 | **distractor 数量与颜色池** | 六个环境都要加 | 建议每环境 2~4 个、共用一个固定干扰色池 |
| B3 | **distractor 放哪** | 四个 Unmask 可放容器内或桌面 | **强烈建议桌面散块**——做成额外容器会被选成交换搭档，`VideoUnmaskSwap` 直接 `SpecBindingError`、`ButtonUnmaskSwap` 静默改变交换对 |
| B4 | **swap 速度 ×1.5 的取整** | `50/1.5 = 33.33` | 建议 `round` 到 **33**，并把 50 提成具名常量再乘倍率（现在是分散字面量，ButtonUnmaskSwap 有六处） |
| B5 | **PickHighlight 的 spawn 总数** | highlight [5,7] ⇒ spawn ≥ 7 | 建议 `[10,12]` 并配 `min_gap_factor=1` |
| B6 | **InsertPeg「更近」的距离带** | **杆跨度 0.1 m > 现最小间距 0.075 m，现在就会穿插** | 建议定义为"落在 0.075~0.12 m 带内"，**不放松全局间距** |
| B7 | **MoveCube 边角偏置强度** | 无边角采样工具，要新增 | 建议做成 `corner_bias ∈ [0,1]` 可调标量并先跑成功率扫描 |
| B8 | **PatternLock 怎么够到 20~30 s** | 实测 hard 只有 3.1~8.6 s，差 4~6 倍；5×5 简单路径段数上限 24 ≈ 24.8 s，但随机 DFS 命中超长路径概率极低 | 建议 `grid` 提到 6×6 **并**把路径搜索改成长度定向。**两者都属 native 规则，需额外授权** |
| B9 | **RouteStick 的 L 目标值** | 按 30 fps 需 `L ∈ [12,18]`；但执行段也是 L×50，**L > 约 22 会被评估入口截断** | 建议 `[12,15]`，留步数余量 |
| B10 | **VideoPlace\* 的 easy `color`** | easy 场上只有 1 块，**演示 2 块是硬阻塞**；`color` 在 native 块 | 建议 easy 的 `color` 提到 2，或本轮只在 medium/hard 启用双演示 |
| **B11** | **yaw ±180° 撞 Panda joint7 限位**（A1 的连带） | 夹爪姿态 `Rz(yaw)·Rx(π)`，yaw 直接透传腕关节，而 **joint7 限位约 ±166°** ⇒ yaw 接近 ±180° 时 IK/`plan_screw` 大概率失败，且失败是**静默跳过演示段** | 杆是长轴对称的，可在抓取时把 yaw **归约到等价朝向**（加 ±180° 使其落进限位内）。⚠ **两个环境不能同等处理**：`MoveCube` 的杆头尾同色（都是 `#EC7357`），归约安全；**`InsertPeg` 的杆头尾异色**（`tail = 1 - head`）且 subgoal 是"grasp the **near/far** end"，归约会**改变抓的是哪一端**、改变任务语义。请定：(a) 只对 MoveCube 归约、InsertPeg 限到 ±166°；(b) 两个都限到 ±166°；(c) 两个都归约并接受 InsertPeg 的语义变化 |
| **B12** | **VideoRepick 发起者池写死 3 个**（A3 的连带） | `_load_scene` 只建 `swap_pair1..3`，`for k in range(3, swap_times)` 靠 `swap_indices[k % 3]` 循环复用 ⇒ swap 8~12 次会**反复是同 3 块发起**，语义单调；且 12 次 × 50 步 = 600 步静止段 | 请定：(a) 接受循环复用（改动最小）；(b) 扩大发起者池到 `min(swap_times, len(spawned_cubes))`（要同步改 `swap_remaining_count=2` 与 `object_selection` 的校验） |

#### C 组：方向性取舍（改了可能适得其反）

| # | 项 | 冲突 | 建议 |
|---|---|---|---|
| C1 | **PickXtimes「推向边角」与「加 distractor」互相抵消** | 目标推到边角会把圆盘挤向中心，**反而更简单**；且两者现在用同一个区域参数 | 建议把 `target_cube_position_policy` 与 `goal_position_policy` 拆开，或只做其一 |
| C2 | **VideoRepick easy/medium 颜色任意会降低难度** | 现在三块**同色**、只能靠位置记忆；异色后退化成靠颜色记忆 | 请确认是否接受；建议 easy/medium 保持同色，只在 hard 放开 |
| C3 | **PickHighlight 高亮会连片** | 白盘直径 0.10 m 是方块边长的 2.5 倍，现中心距才 0.06~0.08 m，**3 块时就可能相切**，5~7 块必然糊成一片 | 建议缩小 `disk_radius` 或改用同心环（`use_target_style=True`） |
| C4 | **StopCube 最快档 + number 15 可能变成"不可能"** | 停止窗口宽度 = `move_interval`，取 60 ⇒ 容错砍半到 60 步；阈值 0.06 配 0.01 m/step ⇒ 只在 ±6 步内；按钮提前量恒 30 = 半趟 | 建议**速度与判定阈值一起调**，或先只改 number、速度保持三档 |
| C5 | **InsertPeg 目标识别可能不可判** | 4 根杆外观完全相同（`head_rgb` 循环外只抽一次）、目标恒 `peg_0`、文本无"哪一根"线索 | 建议定下限距离并配人工看片验收 |

#### D 组：要不要顺手修的既有缺陷（clutter 后都会被高频触发）

| # | 缺陷 | 现状 | 建议 |
|---|---|---|---|
| D1 | `BinFill::_load_scene` 静默吞 `RuntimeError` + `_initialize_episode` 的 `cube_collection[i]` 无长度保护 | clutter 缩域后**必然 `IndexError`** | **必须修** |
| D2 | `PickXtimes::_load_scene` 的 `target` 未绑定 | 圆盘采样失败即 `UnboundLocalError`，加 distractor 后触发率从 ~0 升到几十个百分点 | **必须修** |
| D3 | `MoveCube::_sample_cube_center` 返回 `None` 后 `float(None[0])` | 边角推移后高频 `TypeError` | **必须修** |
| D4 | `PickHighlight` 首个按钮任务 `failure_func` 缺 lambda | 加载期求值为 `False` 再被 `or` 吞成 `None`，**这条判据从来没生效过** | 请决定——修了会突然多出大量失败样本 |
| D5 | 几何检查只认甲的旧通道（`if self._episode_spec is None: return`） | **V4 走 `native_episode_spec`，这些检查一次都不会跑**，clutter+swap 会穿模不报错 | **建议修**：开关条件改成"两条通道任一" |
| D6 | `BinFill` 的 `dynamic` 与块数耦合 | 12 块时 `end_step` 到 400~600，最后一块要几百步才落回 | 若 clutter 本意是"静态密集"，建议把 `dynamic` 钉成 `False` |

#### E 组：流程与授权

| # | 项 | 说明 |
|---|---|---|
| E1 | **新建 `scripts/eval/` 子目录** | `AGENTS.md` 规则 12 要求新建子目录先获批（见 4.3） |
| E2 | **`PickXtimes` 序数表上限** | `get_subgoal_with_index` 在 idx ≥ 10 抛错，`num [6,15]` 必崩。扩表还是改成 `SwingXtimes` 那种兜底写法？ |
| E3 | **`--check-config` 基线会报红** | `SAMPLING_OPERAND_PATHS` 冻结了 BinFill 的 `configs`/`cubes.*` 与 VideoRepick 的 `num_repeats` 操作元，一改就对基线 `94449db` 报"原版操作元不一致"，须同步重导快照 |

## 二、逐环境改动

### 2.0 四族共用的四条机制（先读，后面各节引用）

这四条是源码核实出来的**全局约束**，任何一个环境动手前都要先过一遍。

**① `assert_native_decision` 是所有 `decision` 改动的第一道闸。**
`src/robomme/robomme_env/utils/sampling_config.py::assert_native_decision` 会把传入的 `decision` 块与该环境
`_native_decision(cls)` 的返回值**逐键 JSON 全等比对**，不等就抛 `SamplingConfigError`。所以**改新值不是"传个新
配置进去"就行**，必须同步改 `_native_decision(cls)` 的返回结构；否则外部传入当场被拒。
`VideoRepick::_resolve_sampling_config` 还额外对 `parameters.object_selection` / `parameters.swap_selection`
做 JSON 全等校验，动这两块直接 `ValueError`。

**② `decision` 里有死键——改了不生效还不报错。**
已确认两类：`VideoRepick.decision.num_repeats_range` 有键但**没有任何消费点**（`__init__` 实际读的是
`native` 块的 `parameters.num_repeats`）；`VideoPlaceButton/Order.decision.demo_object_count = 1` 同样是死键，
`scripts/parity/train_split_audit.py::NEUTRAL_KEYS` 里明文写着「原代码没有按数量循环的结构；扩到 2 块时
才会出现消费点」。**实施前必须逐键确认消费点存在**，否则会出现"改了值、跑出来还是老样子、还没有任何报错"。
V4 要给审计加一条：`decision` 的每个叶子键都必须能在本局 `trace` 里找到至少一次消费。

**③ 几何安全检查在 V4 路径上不会触发。**
`VideoRepick` 的 `_check_swap_sweep_from_actual` / `_in_swap_window` / `_before_simulation_step` /
`_after_simulation_step` 全部以 `if self._episode_spec is None: return` 开头——它们只认**甲的旧通道**。
V4 走的是 `native_episode_spec`（乙的通道），所以**这些检查一次都不会跑**。clutter + swap 8~12 次会产出
物理穿模但不报错的 episode。`VideoPlaceButton` / `VideoPlaceOrder` 的 `swap_flat_two_lane` 连检查代码都没有。
**这是 V4 必须处理的一条**：要么把检查的开关条件从 `_episode_spec` 改成"两条通道任一"，要么在 V4 侧另做
一次只读的扫掠核验。属 `src/robomme/` 改动，须出 md 报告。

**④ 生成失败是"静默截断"，不是报错。**
`spawn_random_cube` 在 `max_trials`（多数调用点不传，默认 256）次内放不下就 `raise RuntimeError`，而环境侧
普遍是 `except RuntimeError: break` + 保存已生成数量、不补抽（`NATIVE_SAMPLING.parameters.spawn_failure`
就是这么写的）。clutter 把密度推高后，**实际块数可能少于设定值而没有任何信号**。V4 要在规格里记
"请求数 vs 实际数"，并把不相等直接判为该局失败。

### 2.1 Counting 族（BinFill / PickXtimes / SwingXtimes / StopCube）

**这一族有两条「不改就必然全部失败」的硬限制，排在所有工作之前。**

- **`StopCube::step` 写死 `for segment in range(5)`。** 方块只在 5 趟内往返，而 `stop_time` 现在的取值域
  `[2,5]`（`high_exclusive=6`）正好与之精确耦合。`number` 提到 `[6,15]` 后，方块在 `5*move_interval` 步
  之后就不再移动，**第 6 次及以后的"经过目标"根本不存在** ⇒ 必然失败。必须改成按实际停止序号展开，
  同时注意 `start_pos/end_pos` 的 `segment % 2` 交替逻辑。
- **`utils/subgoal_language.py::get_subgoal_with_index` 在 idx ≥ 10 直接 `raise ValueError`。**
  `PickXtimes::_load_scene` 的 `for i in range(self.num_repeats)` 把 `i` 原样传进去 ⇒ **`num` 改 `[6,15]` 必崩**。
  对照组：`SwingXtimes` 用的是自带兜底的 `ordinals[i] if i < len(ordinals) else f"{i+1}th"`，所以 `[4,10]` 没事。
  修法二选一：扩这张序数表，或把 PickXtimes 改成 SwingXtimes 那种兜底写法。**待决**。

#### BinFill：全部 clutter、12 块、color 3、put_in [5,7]

| 改什么 | 落到哪个键 | 现值 | 硬限制与风险 |
|---|---|---|---|
| clutter | `decision.layout_mode` | `"native_dynamic"` | **`_resolve_sampling_config` 里有一句硬守卫 `if decision.get("layout_mode") != "native_dynamic": raise SamplingConfigError("本轮只支持原布局模式")`**；且全仓 grep `clutter` **只命中一行注释**——**clutter 的摆放逻辑根本不存在，要新写** |
| 块数 12 | `configs[难度].spawn_cubes` | easy/medium/hard = `[4,6]`/`[8,10]`/`[10,12]`（闭区间） | **好消息**：容量模拟显示 12 块在现区域（中心可行域 0.36×0.46 m、`min_gap=0.02`、`max_trials=256`）**100% 放得下**，饱和点在 16~20 之间。hard 上界本来就是 12，今天已经在跑 |
| color 3 | `configs[难度].color` | 1/2/3 | 不抽随机数，只作 `torch.randperm(3)[:num_colors]` 的切片长度 |
| put_in [5,7] | `configs[难度].put_in_numbers` | `[1,3]`/`[2,4]`/`[3,5]`（闭区间） | 投入 7 块**没有物理容量问题**（入孔判定会把方块 `set_pose` 移走，不堆叠）。但单色最多分到 7，**逼近 `get_subgoal_with_index` 的 idx<10 上限**，再加码就越界 |

**三条要一起处理的**：

1. **静默截断 + `IndexError` 组合。** `_load_scene` 的 `except RuntimeError: logger.debug(...)` 不 raise 不补生成
   ⇒ `len(all_cubes)` 可能少于 `total_spawn`；而 `_initialize_episode` 的 `cube = cube_collection[i]`
   （`for i in range(target_number)`）**没有长度保护** ⇒ **clutter 缩小区域后必然 `IndexError`**。这是本族最高优先级。
2. **`min_gap` 是调用点写死的字面量**（`spawn_random_cube(..., min_gap=self.cube_half_size, ...)`），
   `NATIVE_SAMPLING.positions.cubes.min_gap` 只是个说明字符串、运行时不被读。放宽/收紧间距必须改调用点。
3. **`dynamic` 与块数的隐式时间耦合。** `step` 里 `for idx in range(1, len(cube_list)): lift_and_drop_objects_back_to_original(..., end_step=idx*100, ...)`，
   12 块 3 色时单色 4~6 块 ⇒ `end_step` 到 400~600，最后一块要 200~300 步才落回。**若 clutter 的本意是"静态密集"，
   应同时把 `dynamic` 钉成 False**，否则密集摆放的视觉前提被"方块还没落回"破坏。**待决**。

另：`SAMPLING_OPERAND_PATHS` 冻结了 `parameters.BinFill.configs` 与 `positions.BinFill.cubes.*`，
一动 `--check-config` 就会对基线 `94449db` 报"原版操作元不一致"，须同步重导快照。

#### PickXtimes：target 推向边角、color 3、num [6,15]、加其他颜色 distractor

| 改什么 | 落到哪个键 | 现值 | 硬限制与风险 |
|---|---|---|---|
| num [6,15] | `decision.number_range[难度]`（闭区间，在 `__init__` 抽） | `[1,3]`/`[1,3]`/`[4,5]` | **上限 10**（见本节开头的 `get_subgoal_with_index`），15 必崩 |
| color 3 | `decision.color[难度]` | 1/3/3 | hard 本来就是 3 |
| 推向边角 | `decision.target_cube_position_policy` | 中心 `[-0.1,0]`、`region_half_size=0.2` | `spawn_random_cube` 只有 `x = x_low + u*(x_high-x_low)` 的**均匀采样**，全仓 grep `corner`/`annulus`/`min_radius` **无任何边角采样工具 ⇒ 要新增采样模式**。**且与下条冲突**：目标块被推到边角，会把圆盘挤向中心，**反而更简单**；而 `target_cube_position_policy` 与 `goal_position_policy` 现在是**同一区域** |
| distractor | `decision.distractor` | `None` | 见下 |

**这个环境的真正瓶颈不是方块、是后生成的那个目标圆盘。** 方块本身 3~12 块都 100% 放得下，
但 `spawn_random_target`（`radius=0.04`、`min_gap=0.04`、`avoid` 含全部已放方块）的成功率随方块数急剧下降：

| 已放方块数 | 3（现 hard） | 5 | 6 | 8 | 10 | 12 |
|---|---|---|---|---|---|---|
| 圆盘放置成功率 | 100% | 98.7% | 93.7% | **66.0%** | **27.3%** | **6.0%** |

而一旦失败就撞上**未绑定变量**：`except RuntimeError: logger.debug(...)` 之后没有 `return`/`raise`，
紧接着 `setattr(self, "target", target)` ⇒ **`UnboundLocalError`**。加 distractor 前必须先做两件事：
① 修这个分支；② 放大 `goal_position_policy.region_half_size`，**或者把生成顺序改成"先放圆盘再放方块"**。

**distractor 的三处污染**（与 SwingXtimes 同构）：
- `objects.target_cube_idx = torch.randint(0, len(self.all_cubes), (1,))` ⇒ **distractor 会被抽成目标块**。
  要改成从显式候选列表里抽。
- `target_color_name` 靠 `if target_cube in self.red_cubes / blue_cubes / green_cubes` 三分支回填，
  新颜色三条都不命中 ⇒ **保留前一次 `target_color_idx` 的残值**，指令文本与实际目标颜色不符。
- `non_target_cubes = [c for c in all_cubes if c != target_cube]` 被 `failure_func` 用 ⇒
  **distractor 必须在这个列表里**，抓错才算失败。

另两处：`_load_scene` 的 `color_groups` 是**硬编码字面量**，而模块级 `NATIVE_SAMPLING.parameters.color_pool`
**声明了却从未被读**（双真值，改错地方会"看起来改了其实没生效"）；`for idx, group in enumerate(color_groups)`
与内层 `for idx in range(cubes_per_color)` **变量遮蔽**，`cubes_per_color` 一变大就会计数错乱。

#### SwingXtimes：number [4,10]、加其他颜色 distractor

| 改什么 | 落到哪个键 | 现值 | 硬限制与风险 |
|---|---|---|---|
| number [4,10] | `decision.number_range[难度]`（闭区间，`__init__` 抽） | `[1,3]`/`[1,2]`/`[3,3]` | **序数表有兜底，10 轮安全**；`max_swings = num_repeats*2` 随之自动放大，无写死上限 |
| distractor | `decision.distractor` | `None` | 见下 |

**加第四种颜色的第一道硬墙是 `KeyError`**：`_load_scene` 里
`_color_lists = {"red": (...), "blue": (...), "green": (...)}`，随后
`"list": _color_lists[entry["name"]][0]` ⇒ 往 `color_pool` 加第四色**直接 `KeyError`**。
必须同时给新颜色建 `self.<color>_cubes` 列表，或把 `_color_lists` 改成动态建表。
（注意：SwingXtimes 的 `color_pool` **是真被消费的**，这点与 PickXtimes 相反。）

容量宽松：区域 0.46×0.46 m，3~12 块全部 100% 放下，**加 3~6 个 distractor 不需要放大区域**。
但两个圆盘区域各只有 0.2×0.2 且与方块区域重叠，distractor 多了会压缩圆盘可行集 ⇒ 抬高 seed 重试率
（这里失败是 `raise SceneGenerationError`，不像 PickXtimes 那样崩在未绑定变量上）。

风险：`max_swings` 的迟滞阈值（enter 0.03/0.12、exit 0.04/0.3）在 10 轮=20 次摆动的长序列里，
**累积抖动误计一次就整局失败**；任务条数 `2*num_repeats+3` ⇒ 10 轮 23 条，`run_example.py` 的
`MAX_STEPS=300` 明显不够（`evaluation.py` 是 1300）。

#### StopCube：速度最快档、number [6,15]

`StopCube` **没有难度字典**——类里无 `config_*`、无 `configs`，`self.difficulty` 被赋值但**全文件无消费点**。
两个量都在 `decision` 里：

| 改什么 | 落到哪个键 | 现值 | 硬限制与风险 |
|---|---|---|---|
| 最快档 | `decision.move_interval_choices` | `[60, 80, 120]`，`randint` 半开等概率抽 | `move_interval` 是**单程步数**，值越小越快 ⇒ 最快档 = 只留 `[60]` |
| number [6,15] | `decision.stop_time_range` | `low=2, high_exclusive=6` ⇒ 实际 `[2,5]` | **撞 `range(5)`**（见本节开头） |

**速度与判定阈值必须一起评估，否则不是"更难"而是"几乎不可能"**：

- 停止窗口宽度恒等于 `move_interval`：`stop_time_range = (move_interval*(stop_time-1), move_interval*stop_time)`。
  取最快档 ⇒ 容错从 120 步**砍半到 60 步**。
- 而 `is_obj_stopped_onto` 的距离阈值是 `cube_half_size*3 = 0.06`，一趟 0.6 m / 60 步 = 0.01 m/step
  ⇒ **方块只在约 ±6 步内落在阈值内**。
- `interval` 恒为 30（按按钮的提前量），最快档下"提前 30 步去按"= 半趟，`solve_button` 的实际耗时若超 30 步
  就会错过窗口。

**还有三处会随 number 线性膨胀**：`static_checkpoints = range(100, int(steps_press - interval), 100)`
在 `move_interval=60, stop_time=15` 时变成 **9 条 "remain static" 任务**（现 hard 上限是 6 条）；
`evaluate` 的超时判据 `current_step > move_interval * stop_time` ⇒ 900 步；上游 `MAX_STEPS` 要跟上。
**并且 `utils/vqa_options.py::_options_stopcube` 复刻了同一套 checkpoint 公式**——改环境侧不同步改它，
VQA 选项就与实际子目标错位。

#### 本族的四条「先修再改」

1. `get_subgoal_with_index` 的 idx ≥ 10 上限（卡 PickXtimes 的 15）。
2. `PickXtimes::_load_scene` 的 `target` 未绑定（`UnboundLocalError`）与 `BinFill` 的静默吞 `RuntimeError`
   + `cube_collection[i]`（`IndexError`）——两处都是**场景一变拥挤才暴露**的既有缺陷。
3. 目标候选集合：PickXtimes / SwingXtimes 的 `randint(0, len(all_cubes))` 与三色 `in` 回填，是 distractor 的必经改造点。
4. `assert_native_decision` 等值守卫（全族）＋ `SAMPLING_OPERAND_PATHS` 基线比对（仅 BinFill 受影响）。

### 2.2 Permanence 族（VideoUnmask / ButtonUnmask / VideoUnmaskSwap / ButtonUnmaskSwap）

**头号阻碍：`ButtonUnmaskSwap::_refresh_swap_schedule` 是写死的三分支**，只处理 `swap_times` 等于 1/2/3；
`swap_times >= 4` 时**三个分支全不命中 ⇒ `self.swap_schedule` 从未被赋值 ⇒ `step` 里的
`len(self.swap_schedule)` 直接 `AttributeError`**。而 `_load_scene` 也只建了 `swap_pair1/2/3_idx1` 三套槽位。
做 swap `[6,8]` 必须**同时**改这两处，漏一处就是运行时崩。参照物现成：`VideoUnmaskSwap::_refresh_swap_schedule`
已经是通式（`64 + 50*k`），且带 `for k in range(3, self.swap_times)` 的槽位循环。

#### pick=3：四个环境全都挡，但挡法不同

| 环境 | 任务构造里的分支 | 设 pick=3 的实际结果 | 索引取法 |
|---|---|---|---|
| VideoUnmask | `if pick_count[难度] > 1:` | **只生成 2 抓**（不是 1 抓） | 写死 `self.bin_0` / `self.bin_1`、`color_names[0]` / `[1]` |
| ButtonUnmask | 同上 | **只生成 2 抓** | 同上；但 `failure_func`/`solve` 被包成单元素列表，照抄时要保持形态 |
| VideoUnmaskSwap | `if self.pick_times == 2:` **严格相等** | **只生成 1 抓 ⇒ 反而更简单** | `pickup_selected_indices = [0, 1]`，在 `NATIVE_SAMPLING.parameters.object_selection` 里 |
| ButtonUnmaskSwap | `if self.pick_times == 2:` **严格相等** | **只生成 1 抓** | 写死 `selected_bins[0]` / `[1]`；**没有** `pickup_selected_indices` 这个键 |

对象层面都够抓：四个环境的 `selected_bins` / `bin_2` 与 `color_names[2]` 都存在（各档 `bin >= 3`）。

**同一个坑在指令文本里复现一遍**：`utils/task_goal.py::get_language_goal` 里，两个 Swap 用
`self.pick_times == 2`、两个非 Swap 用 `configs[难度]['pick'] > 1`，pick=3 会产出**与实际子目标序列不一致的
指令文本**，而这个文本还会进视频文件名与 HDF5 metadata。`tests/lightweight/test_TaskGoal.py` 的
`test_videounmask_pick_one/two`、`test_videounmaskswap_pick_one/two` 需同步。

**`evaluate()` 都不用改**——四个环境的成功判定完全交给 `sequential_task_check` 按 `task_list` 顺推，
任务多了自然顺延；`is_bin_pickup` 只看 `z > 0.15`，**不看颜色**。

⚠ `VideoUnmaskSwap::_resolve_sampling_config` 末尾有一道额外铁闸：对 `parameters.object_selection` 与
`parameters.swap_selection` 做 `json.dumps` 全等比对，不等就 `ValueError`。**所以不能通过 `sampling_config`
把 `pickup_selected_indices` 改成 `[0,1,2]`**，必须直接改源码里的 `NATIVE_SAMPLING` 字面量。

#### decision 块的读写不对称——改错一边就"看起来改了其实没生效"

| 环境 | swap/pick 真正从哪读 | bin 从哪读 | decision 里的死键 |
|---|---|---|---|
| VideoUnmask / ButtonUnmask | `_load_scene` 读 `decision.pick_count`；但 `task_goal` 读**类属性** `configs[...]['pick']` | `decision.bin_layout_policy.count` | `distractor` |
| VideoUnmaskSwap | **`parameters.configs`**（由 `_resolve_sampling_config` 的 `setdefault` 从 `cls.configs` 拷来） | 同上 | **`swap_count_range`、`pick_count_range`、`swap_speed_multiplier`、`distractor` 全是死键** |
| ButtonUnmaskSwap | **`decision.swap_count_range` / `pick_count_range`**（与上一行相反） | **`parameters.bin_count`**（native） | `swap_speed_multiplier`、`distractor` |

#### swap 次数：窗口、步数与预算

窗口通式 `[64 + 50k, 64 + 50(k+1))`，起点 64、每段 50 步。`step` 的遍历没有写死上限。实测历史总步数
（取自 `artifacts/train-parity/**` 的 `timestep_count`）与外推：

| 环境 | 现 hard 中位/最大 | 目标 swap 次数 | 估计总步（含第三抓 +155） |
|---|---|---|---|
| VideoUnmaskSwap | 457 / 586 | 8 | ≈862 / ≈991 |
| VideoUnmaskSwap | — | 12 | ≈1062 / ≈1191 |
| ButtonUnmaskSwap | 461 / 555 | 6 | ≈766 / ≈860 |
| ButtonUnmaskSwap | — | 8 | ≈866 / ≈960 |

对照三条上限：`RecordWrapper` 的 `fail_safe_limit = 2000` 都不超；评测侧 `max_steps=1300`
（实际 `max_steps_without_demonstration = 1302`，**只统计非 demonstration 段**）——这里有个关键差异：

- **VideoUnmaskSwap 的第一个任务是 `static` 且 `demonstration=True`**，观看交换的 `64+50n` 步**不计入**配额
  ⇒ 12 次 swap 的实际非演示步只有约 527，余量极大。
- **ButtonUnmaskSwap 所有任务 `demonstration` 都是 `False`**（第一项就是"按第一个按钮"），
  **那段观看交换的步数计入配额** ⇒ 8 swap + 3 pick 的最大估计 ≈960 对 1302，**余量只剩约 25%**。
  速度 ×1.5（50→33 步）能把这段从 464 压到 328，正好是有效对冲。

**真正的风险不在步数上限，而在单条墙钟**：`generate_dataset_newseed.py` 的单条超时（600 秒）；
且 VideoUnmaskSwap 在注入态的子步 SAT 检查只在 `_in_swap_window()` 内跑，swap 窗口总长从 150 步涨到 600 步
⇒ 检查量 ×4（注释里实测该环境从 ~47 秒涨到分钟级）。

#### swap 速度 ×1.5：50 是分散的字面量，还有外部常量与测试绑着

`50/1.5 = 33.33`，取整规则**待决**。要同步的引用点（确认过的）：

1. 两个 `_refresh_swap_schedule` 里的字面量（VideoUnmaskSwap 一处通式、ButtonUnmaskSwap **六处**分散在三分支）；
2. `step` 里预交换锁定的 `end_step=32*2`（VideoUnmaskSwap）与 `start_step=64`（ButtonUnmaskSwap）——
   **必须等于首段 swap 的 start**，否则出现空窗或重叠；
3. `scripts/injection/rollout/windows.py` 的模块级常量 `SWAP_START, SWAP_LEN = 64, 50` 与 `unmask_swaps`；
4. `tests/lightweight/test_swap_schedule_generic.py`（硬断言 `base + 50*k`）与
   `test_window_timeline.py`（硬断言 `64+50*k`，以及 demo 段长按 **6 帧对齐** `6*ceil((64+50n)/6)`——取整会改变对齐量）；
5. `windows.py::MAX_SEGMENT_FRAMES = 400` 的"单 subgoal 超 400 帧判慢"，在 swap ≥ 8 时
   static 段 = `64+50n` ≥ 464 **会把正常样本误判为"磨"**。

`ButtonUnmaskSwap` 那边有个现成挂钩位：`NATIVE_SAMPLING.parameters.swap_window = {start_step: 64,
duration_steps: 50}` **声明了但一处都没被消费**——改造时应让 `_refresh_swap_schedule` 真的去读它，
而不是在六处字面量上手改。同理 `parameters.swap_path`（`lane_offset` / `smooth` / `keep_upright`）也未被消费，
`step` 里是内联字面量。

顺带一条：`swap_flat_two_lane` 的 `keep_upright` 与 `lock_cube_offset` 两个形参**在函数体内一次都没被引用**，
四元数混合是无条件执行的——所以"keep_upright 会不会受取整影响"这个问题不存在，它根本没生效。

#### clutter bin（只 VideoUnmask / ButtonUnmask 要做）

现值：region 中心 `[0,0]`、`region_half_size=0.2`、`min_gap = cube_half_size * min_gap_factor(=2) = 0.04`、
`max_trials=256`、`yaw_scale_deg=90`、bin 数 easy/medium/hard = 3/5/15、失败时 `except RuntimeError: break`。

**现在的 hard 本来就放不满。** 按 `spawn_random_bin` 的判据做等价数值模拟（20 组种子）：

| 请求容器数 | 3 | 5 | 8 | 10 | **15** |
|---|---|---|---|---|---|
| 实际放下（均值/最小/最大） | 3.0/3/3 | 5.0/5/5 | 8.0/8/8 | 9.75/9/10 | **10.25/9/12** |

也就是说 `bin=15` 实际只放下 9~12 个，**而且因为 `break` 完全无声**。ButtonUnmask 还更小一点——它的按钮
区（中心 `[-0.2,0]` ± `[0.1,0.1]`）与容器 region（x∈[-0.2,0.2]）重叠。

要加密必须动三者之一并同时抬 `step_bin_scan`：放大 `region_half_size`（受机器人基座可达性约束）、
降 `min_gap_factor`（2→1 可显著提容量，但 `solve_pickup_bin` 的抓取通道会变窄）、提 `max_trials`（收益最小，已近饱和）。
**`step_bin_scan = 15` 是真上限**：`step` 里 `for i in range(step_bin_scan)` + `hasattr(self, f"bin_{i}")`，
**第 16 个及以后的容器不会被揭示动画处理**，画面语义会不一致。

另：两个 Swap 环境**不做 clutter**，但它们的 `for i in range(bin)` 直接取 `region[i]`，
**bin 超过锚点数（三点/四点）会 `IndexError`**，不是静默 break。

#### distractor：放桌面远比放容器安全

四个环境的颜色都可以任意 RGBA（`spawn_fixed_cube` / `spawn_random_cube` 的 `color` 直通
`RenderMaterial.set_base_color`，无白名单），颜色**不参与 `evaluate()`**，只进 `name` / `subgoal_segment` /
`task_goal` 文本。`decision["distractor"]` 现值 `None` 且**全仓无消费点**。

**但"做成额外容器"会污染交换搭档**：两个 Swap 环境的最近邻搜索都遍历 `self.spawned_bins` **全体**
（VideoUnmaskSwap 读 `partner.position_axes`，ButtonUnmaskSwap 硬编码 `[:2]`）。干扰容器一旦进
`spawned_bins` 就**会被选为 partner**；VideoUnmaskSwap 在注入态还会用 `_verify_swap_binding` 逐段核验，
直接 `SpecBindingError`；ButtonUnmaskSwap 没有这个核验，于是**静默改变交换对**。
**放桌面散块（`spawn_random_cube`）完全绕开这条链路**，是风险低得多的方案。**待决**。

还有一条：藏物容器的选择是 `torch.randperm(hidden_bin_permutation_size=3)[:…]`，
**结构上只会挑 bin_0..bin_2**；想把干扰块塞进 bin_3 必须另写路径——**不要动那个 `randperm(3)`**，
它在随机流里的位置是冻结的（红线 R8），改了会平移其后所有取值。

#### 本族的两条连带

- **`inject_fail_grasp` 的抽样空间随 pick 数变化。** `utils/task4recovery.py::task4recovery` 自动扫描含
  `solve_pickup_bin` 的任务，pick 从 2→3 会把候选从 2 个变成 3 个，那次 `randint` 的结果分布随之改变；
  VideoUnmask / ButtonUnmask 还把结果记进 `actions.recovery.selected_action_index`，**旧规格回注会不匹配**。
- **颜色下标语义。** 干扰色若与目标三色共用 `color_names`，下标会被挤位——必须把"目标三色"与"干扰色"
  分成两个列表。

### 2.3 Imitation 族（MoveCube / InsertPeg / PatternLock / RouteStick）

**先说两件会改变需求本身的事实。**

**① MoveCube 与 InsertPeg 根本没有难度分档。** 两个类里**没有** `configs` / `config_*`；`__init__` 算出
`self.difficulty`（`seed % 3`）之后，**全文件再无任何读取点**。而 `env_metadata/train/` 里这两个任务的每条
record 都带 `difficulty` 字段——**环境不读它**。所以这两个任务的"加大难度"等于**全局改参数**，
不是"改某一档"。计划与配置都要按这个事实写。

**②「stick 的转角更大，可以和桌面平行」原是重言式——杆现在已经与桌面平行；用户已澄清为「yaw 放宽到 ±180°」。** 证据链三段：
`utils/object_generation.py::build_peg` 里长轴是 link 局部 x 轴；两个环境构造四元数都用
`euler_angles_to_matrix(torch.tensor([[0.0, 0.0, yaw]]), convention="XYZ")`，**前两位恒为 0，只绕世界 z**；
位置 `p=[x, y, 0.0]`，z 分量从头到尾没被改过。所以这句话**不可能**指 yaw 带来的"平行与否"变化。
**用户 2026-09-22 澄清（开放项 A1）：yaw 从 ±45° 放宽到 ±180°，不引入 pitch/roll。**
⇒ 杆仍在水平面内，**不需要 z 补偿**（否则会撞上"杆半厚 0.01 而中心在 z=0、下半截本来就埋在桌面下"这个问题）。

**但 ±180° 与 Panda joint7 的 ±166° 限位直接冲突**（开放项 B11）：`grasp_and_lift_peg_side` 让夹爪
q = `Rz(yaw)·Rx(π)`，yaw 直接透传腕关节。可行的解法是利用杆的长轴对称性做**朝向归约**（加 ±180° 使其落进限位内），
但**两个环境不能同等处理**：`MoveCube` 的杆头尾同色（`peg_color` 的 head/tail 都是 `#EC7357`），归约安全；
**`InsertPeg` 的杆头尾异色**（`head_rgb` 抽一次、`tail = 1 - head`）且 subgoal 文本是"grasp the **near/far** end"，
归约会**改变抓的是哪一端**、改变任务语义。这条须在实施前定死。

#### MoveCube：cube 与 stick 推向边角、转角更大、更难抓

现值（全部在 `_load_scene`，`_initialize_episode` 只做复位与 `way_idx` 抽样）：
peg 根点 `x ∈ [-0.05, 0.05]`、`y ∈ [±0.15, ±0.25]`、`z = 0`，yaw `[-45°, +45°]`；
cube 候选中心 `x, y ∈ [-0.1, 0.1]`，拒绝判据"离 goal > `cube_half_size*5`"，`max_trials=128`；
goal 区域 demo `region_half_size=0.15` / execution `0.1`。demo 与 execution **各抽一套**，代码是两段近乎复制的块。

**边角推移的直接崩溃点**：局部函数 `_sample_cube_center` 在 128 次拒绝采样失败后 `return None`，
而调用处紧接着 `float(cube_center[0])` ⇒ **`TypeError`，没有任何兜底**。推向边角 = 可行域变窄 + 更难满足
与 goal 的距离判据 ⇒ **触发概率大增**。其后的 `spawn_random_cube` 还会在内部 256 次失败后 `raise RuntimeError`。

**"更难抓"的失败是静默的，不会报错。** 抓取走求解器不是预置 pose，且分三条路
（`self.ways = ["peg_push", "gripper_push", "grasp_putdown"]` 每局三选一，**三条都必须活着**，
V3 已禁止"为了更难只留 peg_push"）。`grasp_and_lift_peg_side` 让夹爪 q = `Rz(yaw)·Rx(π)`，yaw 直接透传到腕关节，
而 Panda 的 joint7 限位约 ±166° ⇒ **yaw 接近 ±180° 时 IK/`plan_screw` 大概率失败**；失败后走
screw（1 次）→ RRT\* 重试，再失败则该段演示**被静默跳过、episode 继续跑完、最后判 fail**。
表现是"成功率悄悄掉"而不是"报错"。**所以边角强度必须做成可调标量并先跑成功率扫描**，不能只看有没有异常。

旁证：`record_dataset_MoveCube_metadata.json` 里已有 `seed 14602`（不是整百），InsertPeg 里有
`13101 / 13201 / 13403 / 13602`——推测是原版遇到演示失败后 seed+1 重试留下的痕迹，**说明当前参数下就已经有失败率**。

另一条：`spawn_random_cube` / `spawn_random_target` 的避让列表里**没有 peg** ⇒ 大 yaw 的杆与 cube/goal
**现在就可以重叠生成，没人拦**。

#### InsertPeg：多一根杆且离 target 更近、转角更大、更难抓

现值：杆数实际由 `decision.peg_offsets = [0.1, 0, -0.1]` 的**长度**决定（`peg_count=3` 只在一次
`randint(0, peg_count)` 里用过，且结果立刻被 `overridden_to=0` 覆盖）；目标杆**恒为 `peg_0`**；
孔板 xy `[-0.1, 0.1]`、yaw `90°±20°`；杆 `x ∈ [-0.2, 0.2]`、`y ∈ [-0.3, 0.3]`、yaw `±45°`，
拒绝判据"离孔板 > `radius*6` = 0.06"与"杆间 > `length*1.5` = 0.075"，`max_attempts=512` **耗尽直接 `raise RuntimeError`**（硬崩，不是软降级）。

**"更近"与现有拒绝判据直接冲突**：`build_peg` 的几何是 head 占 `[-0.025, +0.025]`、tail 中心在 `x=-0.05`
处占 `[-0.075, -0.025]` ⇒ **整根杆跨度 0.1 m，而最小间距只有 0.075 m** ⇒ **现行参数下两根杆本来就可能互相穿插**，
靠物理弹开。再对第 4 根放松必然重叠。V3 明确写了"不擅自放松碰撞间距"⇒ **必须先问用户**：
是放松间距、缩短 `length`、还是把"更近"定义为"落在 0.075~0.12 m 这个带内"。

**目标识别可能从"更难"变成"不可判"**：`peg_head_color` 是 `torch.rand(3)` **在循环外只抽一次**，
`tail = 1 - head` ⇒ **所有杆头尾同色、外观完全一致**；目标恒为 `peg_0`；subgoal 文本只有
`"grasping the {near|far} end"`，语言目标只说 "the same peg you've picked before" ⇒
**文本里没有任何区分"哪一根"的信息，全靠演示视频里的位置**。干扰杆越近，视觉依据越弱。
建议定一个明确的下限距离并配一次人工看片验收。

改动清单另有三处连带：`peg_count` 参与 `randint(0, peg_count)` 的**取值域**，改它会平移其后随机流（须按 R8 显式归因）；
`initializations.{idx}.pegs.{i}` 会多出 `i=3`，G4 的 `missing`/`unused` 要同步；
`vqa_options.py::_options_insertpeg` 的候选从 6 个涨到 8 个。
还有个既有失败判据会更容易触发：执行段的 `failure_func` 里"**碰起任何一根非目标杆 = 立即判失败**"。

#### PatternLock / RouteStick：最难情形 video 20~30 秒

**这一条的结论完全取决于按哪个 fps 算，而两个口径给出的答案是相反的。** 三个数字都核实过：
录像器 `RecordWrapper._video_write_mp4` 写死 **30 fps**；回放工具 `save_robomme_video` 默认 **20 fps**；
仿真 `control_freq = 20 Hz`（1 个 env.step = 1 帧 = 0.05 s 仿真时间）。V3 已指定**按交付录像器的 30 fps 算**
⇒ 20~30 秒 = **600~900 帧**。

**RouteStick：实测演示帧数 = L × 50，整齐到没有例外。**（L 为段数；50 帧/段来自
`solve_swingonto_withDirection` 的"贝塞尔 45 点 + 末端保持 5 点"，`follow_path` 一个位置一步。）

| 难度 | L | 实测演示帧数 | @30 fps | @20 fps |
|---|---|---|---|---|
| easy | 2~3 | 100 / 150 | 3.3 / 5.0 s | 5.0 / 7.5 s |
| medium | 4~5 | 200 / 250 | 6.7 / 8.3 s | 10.0 / 12.5 s |
| hard | 4~7 | 200 / 350 | 6.7 / 11.7 s | 10.0 / 17.5 s |
| xhard | 8~10 | 400~500 | **13.3 / 16.7 s** | **20.0 / 25.0 s** |

⇒ **按 30 fps 要 L ∈ [12, 18]；按 20 fps 则现有 `xhard = [8,10]` 恰好已经达标、什么都不用改。**
**用户 2026-09-22 已拍板按 30 fps（开放项 A2）** ⇒ RouteStick 取 `L ∈ [12,18]`（建议 `[12,15]` 留步数余量，见 B9），
PatternLock 必须改 `grid` 或换搜索策略（B8）。
结构上撑得住：`generate_dynamic_walk` 在 5 个节点的线性图上随机游走、**允许重复访问**，`steps` 任意大都合法。
但要注意**执行段也是 L×50 帧**，加上 `solve_strong_reset(timestep=200)` 的 200 步，
L=18 ⇒ 执行段 900 + 200 ≈ 1100，**逼近 `evaluation.py` 的 1300 与 `phase1_eval.py` 的 1500**
（`max_steps_without_demonstration` 只数非演示步，演示段不受限）⇒ **推测 L > 约 22 必然被截断**。

**PatternLock：现有结构几乎够不到。** 实测（62 个 episode）hard 演示帧数 93 / 157 / 257
（3.1 / 5.2 / 8.6 s @30fps），而目标是 600~900 帧 ⇒ **差 4~6 倍**。
路径搜索 `find_path_0_to_8` → `utils/adjacent.py::dfs_path` 是**简单路径 DFS**（`visited` 集合，不许重复节点）
⇒ **段数硬上限 = R×C − 1**，hard 的 5×5 = 24 段 ≈ 744 帧 ≈ 24.8 s，**刚好摸到下沿**；
但搜索是"随机起终点 + 随机邻居取第一条解"、不是长度定向搜索，`max_attempts=1000` 内命中这种近乎遍历全图的
超长路径**概率极低**。要达标只能改 `grid`（如 6×6=36 节点）或换搜索策略——**两者都属 native 规则**，
V3 明写"演示时长不自动授权改路径长度"⇒ **待决**。

**顺带纠正一处过时信息**：V3 记载的"RouteStick 白球尾迹现为 10 步、官方 40 步"**已经不成立**——
源码现在就是 40（`positions.tcp_trail.end_offset_steps = 40`，`step` 里消费），
`tests/lightweight/test_native_restore_step2.py::test_tcp_trail_is_official_forty_steps` 断言必须等于 40。
要切回 10 步得显式传 `sampling_config`。另注：`PatternLock::step` 的尾迹与按钮高亮是**写死的 `cur_step + 40`**，
没有外提到 `_sampling`；若要统一两个环境的高亮口径，这两处要一并外提。
尾迹不是纯装饰——它是会渲进 `front/wrist` 的 rgb 与 depth 的场景物体，属于进对拍的观测输入。

**PatternLock 的其余现状**（V3 字段表未展开，这里补齐）：难度字典
`config_easy {grid:3, length:[2,4]}` / `medium {4, [3,5]}` / `hard {5, [4,8]}`，**无 xhard**（传了会 KeyError）；
`length` 语义是**节点数**不是段数；演示段与执行段**复用同一条路径**，中间用两个 `NO RECORD` reset 分隔；
成功要同时过两道闸——`sequential_task_check` 全完成，且 `evaluate` 里 `recent_achieved == selected_labels`
的字符串匹配；失败判据是"碰到任何既不是当前期望、也不是上一个的节点"；
触碰阈值用默认的水平 0.01 m、z < 0.1（RouteStick 那边是 0.03 与 0.15）。

`RouteStick::_resolve_sampling_config` 还有一道额外硬校验：`parameters.walk` 除 `direction.threshold`
一个键外**必须完整保留原版**，否则 `ValueError`；改 `configs` 不受此约束。
另记一个易踩陷阱：`RouteStick::__init__` 在**不传 `difficulty` kwarg** 时会无条件
`self.difficulty = "easy"`（覆盖掉上面 `seed % 3` 的结果）。数据生成链路走 metadata 的 difficulty，实际不受影响。

### 2.1 Reference 族（PickHighlight / VideoRepick / VideoPlaceButton / VideoPlaceOrder）

#### PickHighlight：clutter、highlight [5,7]、block 颜色任意

| 改什么 | 落到哪个键 | 现值 | 硬限制与风险 |
|---|---|---|---|
| highlight 数 | `decision.highlight_count[难度]`（源自 `config_*['pickup']`） | easy/medium/hard = 1/2/3 | **`randperm(len(all_cubes))[:k]` 在 `k > len` 时静默截断，没有任何断言**；必须同步抬 `spawn_count` 并加硬断言 |
| 场上总块数 | `decision.spawn_count[难度]`（源自 `config_*['spawn']`） | 3/4/6 | highlight [5,7] ⇒ **spawn 必须 ≥ 7**；见下方容量估算 |
| clutter 可行域 | `decision.cube_region` + `native` 的 `positions.cubes.min_gap_factor` | 中心 `[-0.1,0]`、`region_half_size=0.2`、`min_gap_factor=2`（⇒ `min_gap=0.04`）、`max_trials` 默认 256 | 估算：中心可行矩形约 0.36×0.36 m²，按 RSA 饱和密度估上限约 14 块，**256 次 trial 下实际稳放 8~10 块**，还要扣掉按钮占位（约 0.075×0.075 m，且 `randomize_range=(0.1,0.4)` 会漂）。**要真 clutter 需把 `min_gap_factor` 降到 1 或 0.5 并抬 `max_trials`**——该键在 `native` 块，不触发守卫 ① |
| 颜色任意 | `native` 的 `parameters.color_pool` + `color_draw` | 红/蓝/绿三色，**逐块独立抽、可重复** | PickHighlight 是四个环境里**唯一 `task_goal` 不含颜色词**的（文案是 "all highlighted cubes"），`evaluate()` 也不看颜色。唯一要处理的是 subgoal 文案里的 `, which is {color}` 后缀 |

**两条必须先决定的**：

- **高亮视觉会连片。** 高亮实现是 `utils/statechange.py::highlight_obj` 在方块**正下方**加一个白色圆盘 actor，
  `disk_radius=0.05` ⇒ 直径 0.10 m，是方块边长 0.04 m 的 **2.5 倍**；而现 `min_gap=0.04`、典型中心距 0.06~0.08 m，
  **现在 3 个目标时白盘就可能相切**。5~7 块同时高亮（`highlight_window.simultaneous=True`，共用 `[10,100]` 窗口，
  `step` 里没有任何按序号偏移）必然大面积连片，人眼与模型都分不出"哪几块被高亮"。要么缩 `disk_radius`
  （现在 `step` 没给 `highlight_obj` 传这个参数），要么改用 `use_target_style=True` 的同心环。**待决。**
- **误抓失败会激增。** 每个 pick 的 `failure_func` 是"抓起任何一块非目标即失败"，clutter 下这个概率直接上升。

**顺手发现的既有 bug（不在本轮范围，但改动时会被误认为新引入）**：首个 press-button 任务的
`"failure_func": is_any_obj_pickup(self, [...])` **缺 lambda**，加载期就被求值成 `False`，而
`sequential_task_check` 用 `task_entry.get("failure_func") or task_entry.get("failure")` 取值，`False` 被 `or`
吞成 `None` ⇒ **这条失败判据从来没生效过**。要不要顺手修，需用户决定——修了会突然多出大量失败样本。

#### VideoRepick：clutter、pick times [4,6]、颜色任意、swap 若启用则 [8,12]

| 改什么 | 落到哪个键 | 现值 | 硬限制与风险 |
|---|---|---|---|
| 重复抓放次数 | **`native` 的 `parameters.num_repeats`**（不是 `decision.num_repeats_range`，那是死键） | `low=1, high_exclusive=4` ⇒ 实取 1/2/3 | **半开区间**：[4,6] 要写 `low=4, high_exclusive=7`。另外 `generate_dataset_newseed.py::SAMPLING_OPERAND_PATHS` 冻结了这三个操作元，`--check-config` 会报"与原版操作元不一致"，须同步更新快照 |
| swap 次数（**已定启用 `[8,12]`**，A3） | `parameters.configs[难度].swap_min/swap_max`（闭区间） | easy 1~2、medium 2~3、**hard 0**、xhard 4~5 | **发起者池写死 3 个**（⇒ 开放项 B12）：`_load_scene` 只建 `swap_pair1..3`，`for k in range(3, swap_times)` 靠 `swap_indices[k % 3]` 循环复用。swap 抬到 8~12 能跑但语义单调（反复是同 3 块发起）。窗口 `[start+50k, start+50(k+1))` 每段固定 50 步，12 次 ⇒ 600 步静止段，episode 显著变长 |
| clutter | hard 用 `positions.hard_cubes`（中心 `[-0.1,0]`、`region_half_size=[0.2,0.25]`、`min_gap=cube_half_size=0.02`）；easy/medium 用 `positions.easy_medium_cubes` 的**三组锚点**（每块围绕一个锚点、`region_half_size=0.07`） | hard 5 轮 × 红蓝绿 = 15 块；easy/medium 3 块 | hard 区域估算饱和上限约 30 块，**现放 15 块，抬到 18~20 有余量**；**easy/medium 要 clutter 必须放弃锚点结构**，否则 3 个 0.07 半宽的小格各自最多塞 2~3 块 |
| 颜色任意 | `_load_scene` 里的**局部字面量** `options`（`NATIVE_SAMPLING` 里没有 color_pool） | 红/蓝/绿 | 注入分支有 `idx = [item["name"] for item in options].index(spec["objects"]["color"])`，**依赖 name 字符串**，颜色连续化会打断这条路径 |

**一条反直觉的代价**：easy/medium 现在是**三块同色**，目标靠"视频里被抓过"识别。若颜色任意导致三块异色，
记忆任务会从"靠位置记忆"退化成"靠颜色记忆"，**反而更简单**。这一条要请用户确认是否接受。

**hard 改 clutter 的连带**：hard 分支用 `name_prefix=f"cube_{group['name']}_{idx}"`，而 easy/medium 用
`bin_{i}` 并 `setattr(self, f"bin_{i}", actor)`；`_cube_index_of`、`_object_states_for_collision`、
`_verify_swap_binding` **全部假设 `bin_<i>` 命名**。hard 统一成扁平 clutter 时必须一并统一命名，
且 `objects.hard_round_order.{idx}` 这个规格路径随之作废。另外 `scripts/injection/candidates/specs.py::_repick_group`
里有一句 `raise SpecGenerationError("VideoRepick hard 已由用户排除，不生成规格")`——**那是甲的代码，本轮废弃，
不必改**，但说明 hard 从未进过注入链路。

#### VideoPlaceButton / VideoPlaceOrder：video 里完成 2 个 block、各自放回原位

这两个是本轮**改动面最大**的，因为现有结构是"单演示对象"硬编码，不是"数量可配"。

| 阻碍 | 锚点 | 现状 | 后果 |
|---|---|---|---|
| **easy 场上只有 1 块** | `config_easy['color'] = 1`、`cubes_per_color = 1` 写死 | 方块数 = color 值 | **硬阻塞**：演示 2 块要求 easy 的 `color ≥ 2`；而 `color` 在 **`native` 块**（`native.parameters.color`），V3 明写"本轮没有要求改颜色数"。改它要么改类属性，要么把 `color` 迁进 `decision` 并更新 `_native_decision` |
| **演示模板是内联硬编码** | `VideoPlaceButton::_load_scene` 末段（不在 `_initialize_episode`）；`VideoPlaceOrder::_initialize_episode` | 没有 `demo_by_object` 这类函数，是一串 `tasks.append` | 扩 2 对象要重写整段序列，不是加个循环 |
| **目标选择是单值** | `objects.target_cube_idx = randint(0, len(all_cubes))` | 单块 | 改成 `randperm(...)[:2]` ⇒ **平移其后全部随机流**（swap 的 randperm、`task_flag`、`which_in_subset`、`button_after_pair_index` 都在其后） |
| **按钮插入位置公式失效** | `VideoPlaceOrder` 的 `button_task_index = k * 2 + 2` | `*2` 是"每个 visit 贡献 pick+drop 两条"的硬编码 | 2 个对象后 `pair_tasks` 结构变化，按钮会插进 pick 与 drop 之间，**直接毁掉"按钮前/后第 n 次放置"的可判定性**，公式必须重推 |
| **before/after 答案映射** | `VideoPlaceButton` 的 `task_flag` / `target_target = target_0 if task_flag else target_1` | 单块的二选一 | 2 块后"按钮前最后一次放置""按钮后第一次放置"对应哪一块、哪个 target，要重新定义 |
| **放回原位没有落点** | `solve_putonto_whenhold(target=...)` 与 `is_obj_dropped_onto(obj, target)` **都要 actor**（内部取 `target.pose.p`） | 演示末尾放的是**随机** `goal_site`（`_initialize_episode` 把它 z 压到 −0.05 隐藏），全仓**没有任何地方保存方块初始位姿** | 必须新建 home-site actor。**唯一安全的插入方式是 `spawn_random_target(randomize=False, region_center=<该方块 xy>)`——它不抽随机数，不会平移随机流**；且要放在所有其他 spawn 之后、`include_existing=False, include_goal=False, avoid=None` |
| **颜色进指令文本** | `target_color_name` 由 `if target_cube in self.red_cubes / blue_cubes / green_cubes` 三分支反查，直接 f-string 进 `task_goal` | 三个按色分组的列表写死 | 颜色任意后三分支全不命中，`target_color_name` **保持 `color_groups[0]["name"]` 的残值**（不是 None，更隐蔽，会指向错误颜色）。本轮这两个环境用户没要求改颜色，但若 2 块演示要分别指代，指令文本必须换一套指代方式（如"视频里第一个被移动的方块"） |
| **choice-action 候选表** | `utils/vqa_options.py::_options_videoplacebutton` / `_options_videoplaceorder` 的 `"available": env.targets` | home site 不在 `env.targets` 里 | 演示的"回原位"步若要走 choice-action 匹配会选不到，需扩 `available` |
| **审计豁免要撤** | `scripts/parity/train_split_audit.py::NEUTRAL_KEYS` 里两条 `demo_object_count` 豁免 | 明文写"扩到 2 块时才会出现消费点" | 新增消费点后必须删豁免，否则审计把它当未声明偏差 |

另记：`additional_place` 三档全 `False` ⇒ `pre_flag`/`post_flag` 恒 0，`target_2`/`target_3` 分支**永不执行**
（easy 只有 3 个 target，`target_3` 根本不存在）。这块死代码在重写演示模板时要一并处理。

## 三、新值规格怎么造、怎么冻

### 3.1 先看清乙这条链路的回注机制

`src/robomme/robomme_env/utils/episode_spec.py::SpecRecorder` 是乙的核心，一个环境实例一份，两种模式：

- **导出模式**（`native_episode_spec=None`）：在**原调用点**调 `value(path, drawn)`，把抽到的值按点路径
  （`layout.board.xy` 这种）记进文档，返回抽样值，不多抽不少抽。
- **回注模式**（传入规格）：同一调用点**照常执行原抽样**（红线 R8，随机流不漂移），但 `value()`
  **一定返回冻结值**——源码注释写死了「即便原抽样恰好抽出同样的数，也不允许用抽样值，否则就成了
  方案点名拒绝的『重抽相同却绕过规格』」。抽样值只进 `mismatches` 作兼容核验。

规格文档的形状：`{spec_kind, task, identity, layout / objects / actions / initializations, provenance}`，
`leaf_paths()` 只遍历中间那四个 section，`consumed_paths()` 给本局真正被消费的路径，两者之差就是
G4 的 `missing` / `unused`。

**这里有一个必须在 V4 处理掉的语义冲突**：V3 原值模式下 `mismatches` 非空意味着 RNG 漂移、判失败；
**新值模式下 `mismatches` 必然大量非空**——新值本来就和原抽样不同。所以 V4 必须：

1. **规格升版**：`SPEC_KIND` 从 `native-parity/1` 增加一个并列值 `native-newvalue/1`，
   `SpecRecorder.__init__` 按 `spec_kind` 区分两类，**不接受把新值规格当原值规格喂进来**；
2. **核验口径分叉**：`native-parity/1` 保持「`mismatches` 必须为 0」；`native-newvalue/1` 改为
   「`mismatches` 数量与被 `decision` 覆盖的取值点数量一致」，并把每条 mismatch 归因到是哪个
   `decision` 键导致的——归不了因的 mismatch 仍然判失败（这才是新值模式下的 RNG 漂移检测）。

### 3.2 造值走哪条路：两条路线，推荐 C

新值规格的 path 集合**必须与环境代码的取值点一一对应**，否则 G4 的 `missing` / `unused` 不可能为 0。
这决定了造值器不能凭空写。两条可行路线：

| | 路线 A：离线纯 CPU 造值器（甲的做法） | 路线 C：环境按新范围自抽 + 导出（**推荐**） |
|---|---|---|
| 怎么造 | 单独写一套 specs 生成器，逐环境复刻每个取值点的抽法与顺序 | 把新值写进 `sampling_config.decision`，**让环境自己按新范围抽**，`SpecRecorder` 导出模式把结果记下来 |
| path 一致性 | 靠人工对齐，环境改了就得跟着改 | 天然一致，改环境不用改造值器 |
| 双真值风险 | **有**——甲只覆盖四环境就写了一千多行 | **无** |
| 要不要起仿真 | 不用，纯 CPU | 要，但只做 `gym.make` → `reset` → 导出 → `close`，不建 h5、不录像、不 step |
| 可行性筛查 | 冻结前用独立 OBB 判据筛（与环境是两套判据） | reset 成功即布局可行（用的就是环境自己的判据）；「任务能否完成」仍要实跑才知道 |

**推荐路线 C**，理由是它消灭了双真值——这正是 V3 红线 R6 禁止继承甲的采样器的原因。
代价是造值这一步要占 GPU（可复用 `scripts/injection/rollout/reset_check.py` 的骨架，它已经在做
make/reset/close 且不套录像器）。**用户原话「jsonl 生成机制参考甲」，本方案理解为继承甲的 jsonl
封套契约（见 3.3），而不是继承「纯 CPU 造值」这一实现细节**——这一条如果理解错了，请在实施前纠正。

### 3.3 从甲继承的 jsonl 封套契约

要继承的（`scripts/injection/candidates/io.py` 的机制，**代码可直接复用其纯函数**
`canonical_json` / `digest` / `record_sha256` / `identity_sha256`）：

| 机制 | 怎么用到 V4 |
|---|---|
| 一行 header + 每行一条规格 | `specs.jsonl` 同样两段式 |
| header 内嵌配置全文 | 内嵌 `sampling_config` 全文（十六环境的 `decision` + `native`），实跑时**从快照取、不再读磁盘** |
| 来源指纹 | 环境源码 SHA-256（十六个任务文件 + 被改到的 utils）、`pyproject.toml` / `uv.lock`、造值器自身实现散列 |
| `runtime` 常量逐字校验 | 沿用四项 env kwargs（`obs_mode` / `control_mode` / `render_mode` / `reward_mode`），实跑与评估两侧都要比对 |
| `identity_sha256` | 「去掉可变字段的 header + 排序后同样去可变字段的全部行」的摘要；角色回填、换 `run_id` 不改它，改任一规格值必改 |
| 字段集合**精确比对** | 缺字段、多出未知字段一律报错，读写两端共用一个校验入口 |
| 冻结后进 Git、禁止覆盖 | 已存在 `specs.jsonl` / `results.jsonl` 直接拒绝，重试换新运行编号 |
| 逐行身份散列 | 每行 `spec_sha256` 须同时等于行内字段与 `record_sha256(spec)` |

**不继承的**（V3 红线 R6 明令）：甲的 PCG64 采样器、`delivery_400` 的 400 条配额与 margin、
分层抽样、跨 episode 的方向平衡、「碰撞筛查必须 PASS」这条硬规则（新值下可行性由 reset 自己说了算）。

### 3.4 三段式流程与产物

```text
scripts/configs/newtask-v4/sampling_config.json      ← 十六环境 decision（新值）+ native（原规则）
        │  ① 抽签段：gym.make → reset → SpecRecorder 导出 → close（占 GPU，不建 h5、不录像）
        ▼
artifacts/newtask-v4/<run-id>/draft/drafts.jsonl     ← 每行一条候选规格 + reset 是否成功 + 失败分类
        │  ② 冻结段：纯 CPU，挑通过的、算指纹与 identity、精确键集校验
        ▼
scripts/configs/newtask-v4/<run-id>/specs.jsonl      ← 冻结快照，进 Git，唯一环境输入
        │  ③ 实跑段：回注规格 → 出 h5 + 视频
        ▼
artifacts/newtask-v4/<run-id>/rollout/results.jsonl  ← 唯一结果表，进 Git
```

段①与段③都必须**单 worker**（口径 9）。段②纯 CPU，可在登录节点跑。
`identity` 块沿用官方身份体例 `(task, episode, seed, difficulty)`，但**新值局不再绑定官方 metadata**：
episode 与 seed 由 `seed_layout.py` 的公式现算（`offset + env_code × env_block + episode × 100 + attempt`），
header 里用 `identity_source=formula` 与 V3 的 `identity_source=train_metadata` 区分开。

## 四、推理侧怎么兼容

### 4.1 现状：完全没有

核实过的三条：`BenchmarkEnvBuilder`（`src/robomme/env_record_wrapper/episode_config_resolver.py`）里
grep `sampling_config` / `native_episode_spec` / `candidates` / `jsonl` **零命中**，它只从
`env_metadata/{train,test,val}/record_dataset_<task>_metadata.json` 读 `(seed, difficulty)`；
`scripts/evaluation.py` 不写任何文件，只有 stdout 的 `Success rate:`；
`challenge_interface/scripts/phase1_eval.py` 写的是 `metrics.json` / `progress.json`，读的也是官方 test 分片。
账本原话：「策略侧第三处只定义消费契约，本仓库未新增策略实现。」

### 4.2 要补的三块

1. **环境构建侧**：`BenchmarkEnvBuilder` 增加一条并列的构建路径——给定一份 `specs.jsonl` 与一条身份，
   取出该局规格与 header 里的 `sampling_config`，连同 `seed` / `difficulty` 一起进 `gym.make`。
   约束：**不改动现有的 metadata 路径**（`dataset="train"/"test"/"val"` 的行为逐字不变），新路径由显式参数开启；
   `runtime` 四项 env kwargs 必须与快照 header 逐字相等，不相等直接拒绝起环境；
   wrapper 栈与 `max_steps` 语义保持原样（演示帧不计入预算）。这一步动 `src/robomme/`，按题注出 md 报告。
2. **评估入口**：新入口按 `specs.jsonl` 的某个分片逐局跑策略，边跑边写 `eval_results.jsonl`。
   **不改 `scripts/evaluation.py`**（口径 8：它与上游逐字节相同这一性质要保住）；新入口另起，位置见 4.3。
3. **结果表**：`eval_results.jsonl` 每行的字段与 `results.jsonl` 对齐，这样「生成侧的这一局」与
   「评估侧的这一局」能按 `(task, difficulty, episode, seed, spec_sha256)` 直接 join：

   | 字段组 | 内容 |
   |---|---|
   | 身份 | `task` / `difficulty` / `episode` / `seed` / `spec_sha256` / `run_id` |
   | 结果 | `status`（`success` / `fail` / `timeout` / `error`，取自 `info["status"]`）、`steps`、`demo_steps`、`wall_s` |
   | 策略 | `policy_id` / `policy_sha256` / `action_space` / `max_steps` / `model_seed` |
   | 环境核验 | `runtime_ok`（四项 kwargs 是否与 header 相等）、`spec_binding`（`missing` / `unused` / 归因后的 `mismatch`） |
   | 产物 | `video_path`（可选）、`error_type` / `error` |

   汇总另落 `eval_summary.json`：`per_task[env] = {avg_success, success_count, num_episodes}` + `overall`，
   字段名与 `challenge_interface` 的 `metrics.json` 对齐，便于两边比对。

### 4.3 ⚠ 待批准：新入口放哪

`AGENTS.md` 规则 12 规定顶层只允许五个入口、**新建子目录须先与用户沟通获准**。三个候选：

| 方案 | 位置 | 代价 |
|---|---|---|
| **新建 `scripts/eval/`（推荐）** | 新值评估入口 + `eval_results.jsonl` 写入 + 汇总 | 需用户批准新子目录；但语义最干净，与 `injection/`（已废弃）、`parity/`（对拍）并列 |
| 放 `scripts/parity/` | 复用现有子目录，不用批准 | 语义不对：那是对拍链路，不是策略评估 |
| 改 `scripts/evaluation.py` | 不新增任何文件 | **破坏口径 8**，它与上游 main 的 blob SHA 将不再相同 |

本方案按「新建 `scripts/eval/`」写，实施前须获批。

## 五、改完怎么对拍

新值局**没有官方原版可比**，所以 V3 那套「五路 A1/A2/B/C/D 对官方逐位」不能照搬。V4 换成五条判据，
前三条是零容差硬判据，后两条是统计报告：

| 编号 | 查什么 | 怎么查 | 判定行 |
|---|---|---|---|
| **V1** | **原值回归**：加了新值能力之后，原值路径一个数都没改 | 关闭新值（`decision` 锁原值），重跑 V3 的 144 条子集，与 V3 留档的 B／C／D 产物逐位比 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=k field_mismatch=0` |
| **V2** | **新值可重放**：同一份冻结规格跑两次完全一致 | 同一 `specs.jsonl`、同一机型（A40）、**单 worker**，两次实跑的 HDF5 全字段零容差比较（复用 `compare_h5_pair`，不设容差、不跳字段） | `NEWVALUE_REPLAY=PASS compared=N sha_equal=k field_mismatch=0` |
| **V3g** | **规格真被消费**：改坏规格必须产生差异 | 取若干局，逐个改坏规格里的一个叶子值，重跑必须出现字段差异；同时 `missing=0`、`unused=0`、mismatch 全部可归因到 `decision` 键 | `SPEC_BINDING=PASS missing=0 unused=0 unattributed_mismatch=0` ＋ `SPEC_NEGATIVE=PASS cases=M diff_zero=0` |
| **V4f** | **新值可完成性**：新值局到底跑不跑得通 | 实跑段的成功率与失败分类（规格拒绝／碰撞／绑定不符／规划失败／超时），**按环境×难度分组报告** | `NEWVALUE_FEASIBILITY=REPORT tasks=16 attempted=N ok=M by_class=…`（**不设通过门槛**，见下） |
| **V5e** | **推理链路通**：新值数据能起环境、能评、能落表 | 用新入口跑一个小分片，核验 `runtime_ok` 全真、`eval_results.jsonl` 行数与分片一致、能按身份 join 上 `results.jsonl` | `EVAL_PIPELINE=PASS episodes=N runtime_ok=N join_missing=0` |

三条纪律：

1. **V4f 不设通过门槛。** 新值是故意加难度的，成功率下降是预期结果；把它写成 PASS/FAIL 会诱导
   「调低难度换通过」。它只如实报告，由用户看完数字再决定哪些环境的难度要回调——**回调属于新的用户决策**。
2. **V1 是硬闸门。** 只要 `NATIVE_REGRESSION` 不通过，说明为了做新值把原路径改坏了，必须停下修，
   不允许以「反正新值模式用不到原路径」为由放过。
3. **单 worker、A40。** 口径 9。V2 尤其敏感：多 worker 下 `mplib` 的 RRT 墙钟预算会让同一规格搜出不同路径，
   V3 实测 4 worker 时 `BASELINE_REPEAT=FAIL(different=3064)`。

## 六、实施步骤

| 步 | 内容 | 闸门 |
|---|---|---|
| 0 | 从当前 HEAD 切分支；把 1.3 的开放项逐条问过用户并把答复写回本文第二节 | 开放项全部有答复，无「待决」残留 |
| 1 | 链路甲退役：停用 `scripts/injection/candidates` 与 `rollout` 的新增运行，产物与代码原样留档；`hf_release.py` 维持现状 | 退役说明入 `scripts/README.md`；已进 Git 的产物零改动 |
| 2 | `SpecRecorder` 升版：加 `native-newvalue/1`，核验口径按 3.1 分叉；mismatch 归因到 `decision` 键 | 原值模式行为零变化（V1 的前置） |
| 3 | 十六环境逐个开 `decision` 新值（按第二节分组推进，每组先过 V1 再进下一组） | 每组 `NATIVE_REGRESSION` 局部通过 |
| 4 | 抽签段：`specs.jsonl` 的造值、冻结与封套校验（复用甲的 io 纯函数） | 键集精确比对、`identity_sha256` 自洽、禁覆盖生效 |
| 5 | 实跑段：回注规格出 h5 + 视频，落 `results.jsonl` | V2、V3g |
| 6 | 推理侧：`BenchmarkEnvBuilder` 新路径 + `scripts/eval/` 入口 + `eval_results.jsonl` | V5e |
| 7 | 全量新值生成与报告 | V1、V2、V3g 全过；V4f 出报告交用户 |
| 8 | 留档与提交：`docs/validation/newtask-v4/` 逐步报告 | 每步 md 报告齐备 |

测试预算沿用：每次提交前 ≤5 分钟（`timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`），
长任务用 detached tmux（`PYTHONUNBUFFERED=1` + `set -o pipefail` + `tee` + `EXIT_CODE=` 尾行）。
注意当前分支该命令的既有基线是 **46 failed / 502 passed / 22 skipped / 12 errors**（`configs/newtask-v2/native_sampling.json`
的来源指纹与已改源码不符所致），V4 实施中若要让它归零，须单独重新导出 v2 快照，属独立事项。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

以下编号可被正文引用；与 [AGENTS.md](AGENTS.md) 强制规则冲突时以后者为准。

- **N1 改动须留证。** `src/robomme/` 免逐项事前批准，但每步收尾必须在 `docs/validation/newtask-v4/` 出 md 报告，
  逐条写「文件／锚点／改什么／为什么／怎么验的」。
- **N2 录像器冻结。** `RecordWrapper.py` 不改不覆盖；验证 `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`。
- **N3 开放项不许自填默认值。** 1.3 里 19 项在未获答复前不得实施；实施中新发现的待决项同样追加进 1.3 再问。
- **N4 原值路径不许被改坏。** 任何一步收尾都要能过 `NATIVE_REGRESSION`（V1）；不允许以「新值模式用不到原路径」为由放过。
- **N5 随机流位置。** 新增的 `torch.rand*` 调用一律**追加在既有取值点之后**；插在中间会平移其后全部取值，
  使既有 `episode_spec` / `native_sampling.json` / parity 产物全部失效。`ButtonUnmask::__init__` 那次
  `randint(1,6)`（不决定行为、只占位）与 `ButtonUnmaskSwap::_load_scene` 未被选中分支的偏移抽样是明确样本，**不得删改**。
- **N6 甲的产物只读。** `artifacts/injection/**` 与已进 Git 的 `candidates.jsonl` / `results.jsonl` 不删不改；
  甲的代码保留，只停止新增运行。
- **N7 单 worker、A40。** 进入判据的生成一律 `--workers 1`，跑在 greatlakes `spgpu`；本机（sm_89）只用于调试，结果不进判据。
- **N8 测试预算。** 每次提交前 ≤5 分钟；长任务用 detached tmux（`PYTHONUNBUFFERED=1` + `set -o pipefail` + `tee` + `EXIT_CODE=`）。
- **N9 文档禁硬编码行号。** 只用函数／类／配置键锚点。
- **N10 状态如实。** 新值局跑不通就如实记失败分类，不得靠调低难度换通过；`NEWVALUE_FEASIBILITY` 只报告、不设门槛。

## 一、按阶段的逐项改动清单

**这是待实施清单，不是修改记录。** 每个环境动手前须把该环境实际涉及的函数与改法单独提交审批。

| 阶段 | 文件／锚点 | 拟改什么、为什么 | 新值关闭态的行为 |
|---|---|---|---|
| 步 2 | `utils/episode_spec.py::SpecRecorder.__init__` / `SPEC_KIND` | 增开 `native-newvalue/1`，按 `spec_kind` 分叉核验口径；新增 mismatch 的 `decision` 归因字段 | `native-parity/1` 的行为逐字不变，`mismatches` 仍须为 0 |
| 步 2 | `utils/sampling_config.py::assert_native_decision` | 新值模式下改为「与本次 `sampling_config` 声明的 decision 一致」，而不是与 `_native_decision()` 全等 | 原值模式仍走全等比对 |
| 步 2 | `scripts/parity/train_split_audit.py::NEUTRAL_KEYS` | 撤销 `VideoPlace*.decision.demo_object_count` 两条豁免；新增「每个 decision 叶子键必须在 trace 里有消费」的检查 | 原值审计结论不变 |
| 步 3 | `BinFill.py::_resolve_sampling_config` / `_load_scene` / `_initialize_episode` | 放开 `layout_mode` 守卫并**新写 clutter 摆放**（现不存在）；`min_gap` 从调用点字面量外提；修 D1 的静默截断＋`IndexError` | `native_dynamic` 分支逐字不变 |
| 步 3 | `PickXtimes.py::_load_scene`、`utils/subgoal_language.py::get_subgoal_with_index` | 边角采样模式（**新增**）；目标候选池与 `all_cubes` 解耦；`target_color_name` 回填改为按对象查；修 D2 未绑定分支；序数表扩容或改兜底（E2） | 不传新值时走原均匀采样与原三色回填 |
| 步 3 | `SwingXtimes.py::_load_scene` | `_color_lists` 改动态建表（否则第四色 `KeyError`）；目标候选池解耦 | 三色路径不变 |
| 步 3 | `StopCube.py::step` / `_initialize_episode`、`utils/vqa_options.py::_options_stopcube` | `range(5)` 改为按实际停止序号展开；`static_checkpoints` 与 VQA 侧公式**同步**改 | 5 趟以内行为不变 |
| 步 3 | 四个 Unmask 的 `_load_scene` / `_initialize_episode` | pick 分支循环化（两个用 `>1`、两个用 `==2`）；`ButtonUnmaskSwap::_refresh_swap_schedule` 三分支换成通式＋补槽位循环；`swap_window` 真正被消费 | pick ≤ 2、swap ≤ 3 的行为不变 |
| 步 3 | `PickHighlight.py::_load_scene` / `step`、`utils/statechange.py::highlight_obj` | spawn≥highlight 硬断言；`disk_radius` 可传参（C3）；subgoal 的 `, which is {color}` 后缀处理 | 现值下断言恒真、视觉不变 |
| 步 3 | `VideoRepick.py::_load_scene` | hard 统一成扁平 clutter 并统一 `bin_{i}` 命名；`num_repeats` 改 native 块的 `low`/`high_exclusive` | 不启用 clutter 时保留 5 轮 15 块 |
| 步 3 | `VideoPlaceButton.py` / `VideoPlaceOrder.py` 的 `_load_scene` / `_initialize_episode` | 演示模板从内联硬编码改为按对象循环；`button_task_index` 公式重推；新建 home-site actor（`spawn_random_target(randomize=False)`，不抽随机数） | `demo_object_count=1` 时序列逐字不变 |
| 步 3 | `MoveCube.py::_load_scene` | 边角偏置（**新增采样模式**）；yaw 域放宽（待 A1）；修 D3 的 `None` 返回 | 原均匀采样与 ±45° 不变 |
| 步 3 | `InsertPeg.py::_initialize_episode` | 第 4 根杆的独立采样分支与距离带判据；`peg_offsets` 扩容 | 三根杆路径不变 |
| 步 3 | `PatternLock.py::_load_scene` | `grid` 扩容与长度定向路径搜索（待 B8） | 现 grid 与随机 DFS 不变 |
| 步 3 | `RouteStick.py::configs` | 新增更难档的 `length`（待 B9）；`VALID_DIFFICULTIES` 白名单同步 | 四档不变 |
| 步 3 | `VideoRepick.py` 的扫掠检查四处 | 开关条件从 `self._episode_spec is None` 改为「两条通道任一」（D5） | 甲通道行为不变 |
| 步 4 | `scripts/parity/`（新增模块） | 抽签段：按新 `decision` 跑 make/reset/导出，产出 `drafts.jsonl`；冻结段：复用 `scripts/injection/candidates/io.py` 的 `canonical_json` / `digest` / `record_sha256` / `identity_sha256` 产出 `specs.jsonl` | 不影响既有 `train_split_*` 子命令 |
| 步 5 | `scripts/parity/train_split_parity.py` | `run` 增加读 `specs.jsonl` 的分片模式；结果落 `results.jsonl` | 原五路模式不变 |
| 步 6 | `src/robomme/env_record_wrapper/episode_config_resolver.py::BenchmarkEnvBuilder` | 并列的 from-spec 构建路径；`runtime` 四项逐字校验 | `dataset="train"/"test"/"val"` 路径**逐字不变** |
| 步 6 | `scripts/eval/`（**新建子目录，待 E1 批准**） | 新值评估入口 + `eval_results.jsonl` + `eval_summary.json` | 不改 `scripts/evaluation.py` |
| 全程 | `tests/lightweight/` | 新增：decision 消费点检查、新值 mismatch 归因、`specs.jsonl` 封套反例、pick=3 / swap≥4 的任务条数断言；同步 `test_TaskGoal.py`、`test_swap_schedule_generic.py`、`test_window_timeline.py` 的硬断言 | 原有断言不放宽 |

`utils/object_generation.py`、`utils/route.py`、`utils/task4recovery.py` 与求解器若确需改动，**必须再列出具体函数与理由**，
不能由环境文件获批推导出工具文件也获批。`RecordWrapper.py` 不在清单内（N2）。

## 二、对拍闸门总表

| 闸门 | 前置条件 | 判定行 |
|---|---|---|
| V1 `NATIVE_REGRESSION` | V3 的 144 条基线产物可读；新值开关关闭 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=k field_mismatch=0` |
| V2 `NEWVALUE_REPLAY` | `specs.jsonl` 已冻结；同机型 A40、单 worker | `NEWVALUE_REPLAY=PASS compared=N sha_equal=k field_mismatch=0` |
| V3g `SPEC_BINDING` ＋ `SPEC_NEGATIVE` | 步 2 的归因字段已落地 | `SPEC_BINDING=PASS missing=0 unused=0 unattributed_mismatch=0`；`SPEC_NEGATIVE=PASS cases=M diff_zero=0` |
| V4f `NEWVALUE_FEASIBILITY` | 实跑段完成 | `NEWVALUE_FEASIBILITY=REPORT tasks=16 attempted=N ok=M by_class=…`（**不设门槛**，N10） |
| V5e `EVAL_PIPELINE` | 步 6 完成；E1 已批 | `EVAL_PIPELINE=PASS episodes=N runtime_ok=N join_missing=0` |

比较实现复用 `scripts/parity/train_split_parity.py::compare_h5_pair`（先整文件 SHA-256，不同才 `visititems`
逐路径比 dtype／shape／attribute／`tobytes()`；不设容差、不跳字段）。

## 三、runbook

```bash
# 只读核验：录像器未改、五入口未增
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py && echo RECORDER_FROZEN=PASS
ls -1 scripts/*.py    # 应恰好五个

# 每次提交前（≤5 分钟）
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q

# 抽签段 / 实跑段（长任务，detached tmux）
tmux new-session -d -s v4-draft \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.<抽签入口> --run-id <编号> 2>&1 \
   | tee artifacts/logs/v4-draft-<编号>.log; echo EXIT_CODE=\$? >> artifacts/logs/v4-draft-<编号>.log"
```

产物落 `artifacts/newtask-v4/<run-id>/`（大件）与 `docs/validation/newtask-v4/`（轻量报告）；
冻结的 `specs.jsonl` 进 `scripts/configs/newtask-v4/<run-id>/`。

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 新值把演示成功率打到 0（MoveCube 边角＋大 yaw、StopCube 最快档、InsertPeg 近距干扰） | 每项做成可调标量，实施前先跑成功率扫描；失败是**静默跳过演示段**而非报错，必须看成功率不能只看异常 |
| 2 | clutter 后生成静默截断，实际数量少于设定 | 规格里记「请求数 vs 实际数」，不相等即判该局失败（2.0 ④） |
| 3 | 几何检查不触发导致穿模 | D5 必修；另在 V4 侧加只读扫掠核验 |
| 4 | 改 `decision` 撞 `assert_native_decision` 或两道额外铁闸 | 步 2 先把守卫分叉；`VideoUnmaskSwap` 的 `pickup_selected_indices` 只能改源码字面量 |
| 5 | 随机流平移使既有规格与 parity 产物失效 | N5；新抽样一律追加在最后，并在报告里显式归因 |
| 6 | 步数逼近评估上限（ButtonUnmaskSwap 8 swap + 3 pick ≈960/1302；RouteStick L>22 被截断） | 实施前按第二节的估算表核对；必要时用 swap 速度 ×1.5 对冲 |
| 7 | 50 步窗口的外部常量与测试硬断言失配 | 改前先把 `windows.py::SWAP_START/SWAP_LEN` 与两个测试的断言一并列出同步 |
| 8 | `--check-config` 对基线报红 | E3；同步重导 v2 快照，属独立事项 |

## 五、盲区诚实清单

- **新值局没有官方原版可比**，V2 只能证明"同一规格两次生成一致"，**不能证明"值是对的"**；"对不对"只能靠
  第二节的容量估算、成功率扫描与人工看片。
- **成功率扫描的样本量未定**，本方案未给出统计显著性口径。
- **PatternLock 能否真到 20~30 s 未经实跑验证**，只有"5×5 简单路径上限 ≈24.8 s"的理论估算与"随机 DFS 命中概率极低"的推断。
- **InsertPeg 四根同色杆的可判性未经人工验收**，存在"更难"变"不可判"的风险。
- **当前分支 `tests/lightweight` 既有 46 项失败**（v2 采样快照指纹与已改源码不符），V4 不承诺消解，属独立事项。
- **本机与 A40 产物不同**已由 V3 证实，本方案的一切数值结论都以 A40 为准。

## 六、留档与 commit 纪律

commit subject 沿用 `<大版本>.<小版本> <中文描述>`；body 按 AGENTS.md 规则 7 六项写全（用户原话／完整计划／
实施分节／计划外意外／重要实验与实测数字／当前状态与下一步）。每步收尾在 `docs/validation/newtask-v4/` 出 md 报告（N1）。
提交后立即 `git push`。
