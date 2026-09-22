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

## 一、口径

**一句话方案**：**废弃链路甲**（`scripts/injection/`，只覆盖四环境），**在链路乙上**
（`scripts/parity/`，十六环境、`sampling_config` + `native_episode_spec`）**扩出新值模式**——
新值一律落在**新增的 `xhard` 档**，让环境按新范围自己抽、`SpecRecorder` 导出成规格，
沿用甲的 jsonl 封套契约冻成 `specs.jsonl`，实跑落 `results.jsonl`；
同时给推理侧补一条读同一份快照的环境构建路径；改完跑原值回归、新值重放、规格绑定三类对拍。

### 1.1 定死的口径

**实施中不得更改。** 每条给出依据小节。

| # | 口径 | 依据 |
|---|---|---|
| 1 | **废弃链路甲**。`candidates`/`rollout` 不再新增运行；已进 Git 的产物与代码**原样保留、不删不改** | 用户原话「废弃原来链路甲」；红线 N6 |
| 2 | **在链路乙上实现**，用 `sampling_config` + `native_episode_spec`，**不复活甲的 `episode_spec` 旧通道** | 用户原话「在乙的基础上实现」 |
| 3 | **jsonl 继承甲的封套契约**（header 内嵌配置全文与来源指纹、逐行 `spec_sha256`、`identity_sha256`、字段集合精确比对、冻结进 Git 禁覆盖）；**不继承**甲的采样器、配额、分层与方向平衡 | 用户原话「jsonl 生成机制 参考甲的实现」；3.3 |
| 4 | **推理必须兼容**。现状是完全没实现，要补出读 V4 快照起环境的路径与落 `eval_results.jsonl` 的入口 | 用户原话「推理也要兼容」；第四节 |
| 5 | **改完跑对拍**，换成五条判据（原值回归 / 新值重放 / 规格绑定 / 可完成性报告 / 推理链路） | 用户原话「改完后还需要跑对拍」；第五节 |
| 6 | **改动内容以 1.2 的用户原文为准** | 1.2 |
| 7 | **新值一律落新增的 `xhard` 档，从 `hard` 派生；`VideoRepick` 从 `medium` 派生。原三档一个数都不动** | 用户原话「v4派生的任务 都是基于hard来派生的 作为xhard，但是对于videorepick是以medium派生」；2.1 |
| 8 | **`scripts/` 顶层只允许五个入口**，新增顶层文件或子目录须先获批 | AGENTS.md 强制规则第 12 条；2.0④ |
| 9 | **`evaluation.py` / `run_example.py` / `dataset_replay.py` 与上游 main 逐字节相同这一性质要保住**，新值评估另起入口 | 2.0④ |
| 10 | **正式验收单 worker、判据只认 A40**（`mplib` 的 RRT 用墙钟预算；本机 sm_89 与 A40 sm_86 产物不同） | V3 实测；第五节 |
| 11 | **未定的量一律保留为待决，不编造默认值** | V3 8.3 的纪律 |
| 12 | **录像器全程冻结**；`src/robomme/` 改动免逐项事前批准但每步须出 md 报告 | 题注；红线 N1/N2 |

### 1.2 十六环境的改动内容（用户原文，逐字保留）

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

逐环境的字段落点、现值、新值与注入什么，见第二节的十六张表；布局改动的俯视图见 2.21。

### 1.3 用户决策速查

实施前的全部待决项**已在 2026-09-22 逐条闭环**。下表只记结论与落点，原始的"问题与建议"不再保留。

| 编号 | 决策结论 | 落在哪 |
|---|---|---|
| A1 | 「和桌面平行」= **yaw 放宽到 ±180°**，不引入 pitch/roll | 2.16 / 2.17 / 2.18 |
| A2 | 20~30 秒**按录像器的 30 fps 算**（⇒ 600~900 帧） | 2.19 / 2.20 |
| A3 | VideoRepick **启用 swap**，`[8,12]` | 2.13 |
| A4 | 认定 MoveCube / InsertPeg 现状就是全局参数、无分档 | 2.17 / 2.18 |
| A5 | 干扰物「其他颜色」= **固定 3 个颜色** | 2.0① |
| A6 | 三个无分档环境：**现值作 `hard`，在此基础上派生 `xhard`** | 2.1 / 2.6 / 2.17 / 2.18 |
| A7 | **旧 xhard 全部作废**，直接覆盖，不保留、不另起档名 | 2.1 / 第二部分步 3a |
| B1 | BinFill 区域与间距**不动**（12 块现区域 100% 放得下） | 2.3 |
| B2 | 干扰色**全局 3 色**：黄 / 青 / 品红，六环境共用 | 2.0① |
| B3 | 干扰做成**额外容器**，现 region 外、相机可见、部分含 cube、**不参与 swap** | 2.7① |
| B4 | swap 速度取整由实施方定 ⇒ `SWAP_WINDOW_STEPS = round(50/1.5) = 33` | 2.7③ |
| B5 | PickHighlight `spawn = [8,10]`（实测只稳放 8~10），间距不动 | 2.12 |
| B6 | InsertPeg 杆间距判据**不动**，新杆贴近 0.075 下限 | 2.18 |
| B7 | MoveCube 边角做成 `corner_bias ∈ [0,1]` + 先跑成功率扫描 | 2.17 |
| B8 | PatternLock **不改布局、只增加步骤长度**（须配合改搜索策略） | 2.19 |
| B9 | RouteStick **不改布局**，`L = [12,15]` | 2.20 |
| ~~B10~~ | 作废——口径 7 之后 VideoPlace\* 的 easy 阻塞不存在 | — |
| B11 | yaw ±180° 撞 joint7 限位 ⇒ **按等价朝向归约**（只改夹爪姿态，不碰杆位姿） | 2.16 |
| B12 | VideoRepick **发起者仍 3 个**，只把次数提到 8~12 | 2.13 |
| B13 | 干扰容器外环 `max(\|x\|,\|y\|) ∈ [0.2675, 0.45]`；**3 个里 1~2 个含 cube** | 2.7① / 2.21 |
| C1 | PickXtimes **圆盘可以出现在中间**（两套区域参数仍要拆开） | 2.4 |
| C2 | VideoRepick「颜色任意」= 每局 3 块**仍同色**、只是色值任意 | 2.13 |
| C3 | PickHighlight 缩小 `disk_radius` 或改同心环 | 2.12 |
| C4 | StopCube **只锁速度最快档与 number `[6,15]`**，其余阈值由实施方按实测调 | 2.6 |
| C5 | InsertPeg 目标识别**本来就靠 video demo**，不是本轮引入的问题 | 2.18 |
| D1~D5 | 五个既有缺陷**全部修复** | 2.0① / 2.3 / 2.4 / 2.12 / 2.17 |
| D6 | BinFill 的 `dynamic`：**xhard 固定 `false`**，原三档不动 | 2.3 |
| E1 | **批准新建 `scripts/eval/`** | 2.0④ |
| E2 | 序数表**扩到 20 + 规范英文序数兜底**（前十项逐字不变） | 2.0① / E2 方案 |
| E3 | **批准重导 v2 快照**（可能一并消解当前 46 项既有失败 ⇒ 须重测基线） | 2.0⑤ |

## 二、逐环境改动

**怎么读这一节**：2.0 是跨环境的公共改动（只写一次，各环境表里不重复）；2.1 是十六个环境的
xhard 派生基准；2.2 是四条动手前必须知道的机制；2.3 起是**十六张环境表**，每张四列
（字段 / 含义 / 派生基准档的现值 / xhard 新值与注入什么），表后跟该环境的「实施要点」。
2.7 与 2.16 是族内共用事项，不对应单个环境。

### 2.0 全局要改什么

#### ⓪ 「新值只落 xhard」带来的简化与代价

口径 7 规定新值一律落新增的 `xhard` 档、原三档一个数不动。这一条**消解了三个原本的硬阻塞**：

- **`VideoPlace*` 的 easy 只有 1 块方块**——原本是"演示 2 块"的硬阻塞（`color=1` × `cubes_per_color=1` 写死，
  而 `color` 在 native 块）。现在从 hard 派生、`color=3` ⇒ 场上 3 块够用，easy 完全不动。
- **`VideoRepick` hard 的 5 轮 × 红蓝绿 = 15 块特殊结构**——原本要为 clutter 统一 `bin_{i}` 命名、
  作废 `hard_round_order` 规格路径。从 **medium** 派生完全绕开；而且 medium 有 swap 而 hard 是 `swap=0`，
  `swap [8,12]` 正好接得上。
- **`NATIVE_REGRESSION`（V1）更强也更容易过**——原三档在结构上就不该有任何差异，
  任何非零差异都是明确的 bug，而不是"要去分析是不是可接受的漂移"。

**代价是三件新增工作**：

1. **十三个环境要新建 `config_xhard`**（其余三个已有、按 A7 覆盖）；
2. **`StopCube` / `MoveCube` / `InsertPeg` 连难度分档机制都没有**（类里无 `configs`，`difficulty` 无消费点）
   ⇒ 按 A6 取 `configs = {easy: X, medium: X, hard: X, xhard: 新值}`，`X` = 现有全局常量原值。
   **三档同值保证"不管传哪档行为都与现状一致"**——现状本就如此，所以这个写法不改变任何既有行为；
3. **抽签段入口必须显式传 `difficulty="xhard"`**：`--difficulty` 那个三位循环配额只管 easy/medium/hard，
   xhard 只经每条规格的 `difficulty` 字段进入。

下面是**跨环境的公共改动**，十六张环境表里不再重复。按"改完才能往下走"的依赖顺序排。

#### ① 机制层（`src/robomme/robomme_env/utils/`）

| 文件::锚点 | 改什么 | 为什么 | 关闭态 |
|---|---|---|---|
| `sampling_config.py::assert_native_decision` | 守卫**分叉**：原值模式仍与 `_native_decision(cls)` 逐键全等；新值模式改为"与本次 `sampling_config` 声明的 decision 一致" | 现在它逐键 JSON 全等比对，**改新值会当场被拒** | 原值模式行为逐字不变 |
| `episode_spec.py::SPEC_KIND` / `SpecRecorder.__init__` | 增开 `native-newvalue/1`，按 `spec_kind` 分叉核验；`mismatches` 增加"归因到哪个 `decision` 键"的字段 | 原值模式下 `mismatches` 非空 = RNG 漂移 = 失败；**新值模式下它必然大量非空**，两种语义必须分开 | `native-parity/1` 的 `mismatches` 仍须为 0 |
| `subgoal_language.py::get_subgoal_with_index` | 扩表到 20 + 规范英文序数兜底（方案见 E2） | 现在 idx ≥ 10 直接 `raise ValueError`，`PickXtimes` 的 `num [6,15]` 必崩 | **idx 0~9 输出逐字不变** |
| `object_generation.py`（新增采样模式） | 新增**边角偏置**采样（`corner_bias ∈ [0,1]`，0 = 现有均匀采样）；新增**干扰容器**生成入口 | 全仓 grep `corner`/`annulus`/`min_radius` 无任何边角采样工具，要新写 | `corner_bias=0` 时与现有均匀采样逐字等价 |
| 新增全局常量：干扰色池 | 黄 `(1,1,0,1)` / 青 `(0,1,1,1)` / 品红 `(1,0,1,1)`，六个环境共用（B2） | "其他颜色"需要一个跨任务一致的定义 | 不启用 distractor 时不被读 |
| `VideoRepick` 的四处扫掠检查（D5） | 开关条件从 `if self._episode_spec is None: return` 改为"两条通道任一" | 它们只认**甲的旧通道**，V4 走 `native_episode_spec` ⇒ **一次都不会跑**，clutter+swap 会穿模不报错 | 甲通道行为不变 |

**E2 扩表方案（`get_subgoal_with_index`）**——三条约束缺一不可：

1. **前十项逐字不变**：`idx = 0…9` 必须仍输出 `first … tenth`，否则原三档的 subgoal 文本变化、V0/V1 直接挂；
2. **表扩到 20**，与 `utils/task_goal.py::num2words` 的覆盖范围对齐（避免"任务目标说 fifteen、子目标却报错"）；
3. **超出表范围用规范英文序数兜底**，不沿用 `SwingXtimes` 那种会给出 "22th" 错形的 `f"{i+1}th"`。

```python
_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
             "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
             "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth")

def _ordinal_word(idx: int) -> str:
    if idx < 0:
        raise ValueError(f"Invalid index: {idx}")
    if idx < len(_ORDINALS):
        return _ORDINALS[idx]
    n = idx + 1                                   # 序数是 1-based
    suffix = "th" if n % 100 in (11, 12, 13) else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def get_subgoal_with_index(idx, template, **kwargs):
    return template.format(idx=_ordinal_word(idx), **kwargs)
```

配套测试：①`idx 0…9` 与改动前逐字相同；②`idx 10…19` 给 `eleventh … twentieth`；
③`idx 20/21/22/112` 给 `21st / 22nd / 23rd / 113th`；④负数仍 `ValueError`。

#### ② 每个环境都要做的三件事

1. **建 `xhard` 档**（按 2.1 的派生基准总表）：十三个新建、三个覆盖旧值；
   `StopCube`/`MoveCube`/`InsertPeg` 先按 A6 建 `configs = {easy/medium/hard: 现值, xhard: 新值}`。
2. **把新值接到消费点**：改 `_native_decision(cls)` 的返回结构（否则守卫拒），
   并确认每个新键**真有消费点**（现存多个死键，见 2.2 ②）。
3. **把新值取值点挂上 `SpecRecorder`**：新增的取值（干扰物位置/颜色、边角偏置后的 xy、
   扩展后的 swap 次数与窗口……）都要经 `self._spec.value(path, drawn)` 走一遍，
   否则规格里没有这些值、G4 的 `missing` 不为 0。
   ⚠ **新增的随机调用一律追加在既有取值点之后**（红线 N5），否则平移随机流、毁掉原三档。

#### ③ 链路层（`scripts/parity/`）

| 新增 | 做什么 |
|---|---|
| 抽签段入口 | 按新 `decision` 跑 `make → reset → 导出 → close`（复用 `rollout/reset_check.py` 骨架），产出 `drafts.jsonl` |
| 冻结段入口 | 纯 CPU，挑通过的规格、算来源指纹与 `identity_sha256`、做字段集合精确比对，产出 `specs.jsonl`；**复用甲的 `candidates/io.py` 纯函数**（`canonical_json`/`digest`/`record_sha256`/`identity_sha256`） |
| `train_split_parity.py::run` | 增加"读 `specs.jsonl` 跑一个分片"的模式，结果落 `results.jsonl` |

#### ④ 推理侧

| 改什么 | 约束 |
|---|---|
| `env_record_wrapper/episode_config_resolver.py::BenchmarkEnvBuilder` | 增加一条**并列**的 from-spec 构建路径；`dataset="train"/"test"/"val"` 的行为**逐字不变**；`runtime` 四项 env kwargs 必须与快照 header 逐字相等，不等直接拒绝起环境 |
| `scripts/eval/`（新建，E1 已批） | 新值评估入口 + `eval_results.jsonl` + `eval_summary.json`；**不改 `scripts/evaluation.py`** |

#### ⑤ 测试与快照

- **必改**：`test_swap_schedule_generic.py`、`test_episode_action_sampling.py`、`test_window_timeline.py`
  里锁着旧 xhard「4~5 次」语义的断言（A7 作废旧 xhard 后必然失配）。
- **必加**：decision 消费点检查、新值 mismatch 归因、`specs.jsonl` 封套反例、
  pick=3 / swap≥4 的任务条数断言、`get_subgoal_with_index` 的前十项不变 + 扩展项 + 兜底。
- **不动**：`tests/_shared/contract_builder_fixture.py` 与 `test_injection_delivery.py`（属甲的契约链路，红线 N6）。
- **重导** `configs/newtask-v2/native_sampling.json`（E3 已批）：改源码后 `--check-config` 会对基线报红；
  重导后当前那 46 项既有失败可能一并消解，**须重新测基线**。

### 2.1 派生基准总表

**所有改动都落在新增的 `xhard` 档（口径 12），原三档一个数都不动。** 十六个环境的派生基准与起手工作：

| 环境 | xhard 派生自 | 现状 | 起手要做的 |
|---|---|---|---|
| BinFill | hard `{color 3, spawn [10,12], put_in [3,5]}` | 无 xhard | 加 `config_xhard` |
| PickXtimes | hard `{color 3, number [4,5]}` | 无 xhard | 加 `config_xhard` |
| SwingXtimes | hard `{color 3, number [3,3]}` | 无 xhard | 加 `config_xhard` |
| **StopCube** | 现值即 hard（A6） | **无 `configs`，difficulty 无消费点** | `configs = {easy/medium/hard: 现值, xhard: 新值}` |
| VideoUnmask | hard `{bin 15, pick 2}` | 无 xhard | 加 `config_xhard` |
| ButtonUnmask | hard `{bin 15, pick 2}` | 无 xhard | 加 `config_xhard` |
| **VideoUnmaskSwap** | hard `{bin 4, swap [2,3], pick [2,2]}` | **已有 xhard** `{bin 4, swap [4,5], pick [2,2]}` | **旧 xhard 作废、直接覆盖**（A7） |
| ButtonUnmaskSwap | hard `{bin 4, swap [2,3], pick [2,2]}` | 无 xhard | 加 `config_xhard` |
| PickHighlight | hard `{spawn 6, pickup 3}` | 无 xhard | 加 `config_xhard` |
| **VideoRepick** | **medium** `{cube 3, swap [2,3]}` | **已有 xhard** `{cube 3, swap [4,5]}`，恰好就是 medium 派生 | **旧 xhard 作废、直接覆盖**（A7） |
| VideoPlaceButton | hard `{color 3, targets 4, swap True}` | 无 xhard | 加 `config_xhard` |
| VideoPlaceOrder | hard `{color 3, targets 4, swap True}` | 无 xhard | 加 `config_xhard` |
| **MoveCube** | 现值即 hard（A6） | **无 `configs`** | `configs = {easy/medium/hard: 现值, xhard: 新值}` |
| **InsertPeg** | 现值即 hard（A6） | **无 `configs`** | `configs = {easy/medium/hard: 现值, xhard: 新值}` |
| PatternLock | hard `{grid 5, length [4,8]}` | 无 xhard（传了会 KeyError） | 加 `config_xhard` |
| **RouteStick** | hard `{length [4,7], backtrack True}` | **已有 xhard** `{length [8,10], backtrack True}` | **旧 xhard 作废、直接覆盖**（A7） |

> **为什么 VideoRepick 走 medium**：它的 hard 是 5 轮 × 红蓝绿 = 15 块的特殊结构、且 `swap=0`、
> 连 `cube` 键都没有；medium 才是"3 块 + swap `[2,3]`"的常规结构，`swap [8,12]` 接得上。
> 下面 Reference 族里关于"hard 改 clutter 要统一 `bin_{i}` 命名、作废 `hard_round_order`"的整段讨论
> **因此不再适用**——从 medium 派生完全绕开了它。

### 2.2 四条共用机制

下面四条是源码核实出来的**全局约束**，任何一个环境动手前都要先过一遍。

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

### 2.3 BinFill（派生自 hard）

**要做**：全部 clutter、12 块、color 3、put_in `[5,7]`。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.layout_mode` | 方块摆放模式 | `"native_dynamic"` | **`"clutter"`（新增模式，代码不存在要新写）**；注入 `layout.mode` |
| `decision.configs.xhard.spawn_cubes` | 本局方块总数 | `[10,12]`（闭） | **`[12,12]`**；注入 `objects.spawn_total` 与实际生成数 |
| `decision.configs.xhard.color` | 本局出现几种颜色 | `3` | **`3`（不变）**；注入 `objects.colors_present` |
| `decision.configs.xhard.put_in_numbers` | 要投入孔板的总数 | `[3,5]`（闭） | **`[5,7]`**；注入 `objects.put_in_total` 与逐色 `target_count` |
| `native.put_in_color` | 投入哪几种颜色 | `[2,3]`（闭） | 规则不改；注入 `objects.target_pool` |
| `native.dynamic` | 开局是否全部出现 | `randint(0,2)` 转 bool | **固定 `False`**（D6）；注入 `layout.dynamic` |
| `native.cubes.region_*` / `min_gap` | 方块可行域与间距 | 中心 `[-0.1,0]`、半边长 `[0.2,0.25]`、`min_gap` 调用点写死 `cube_half_size` | **不动**（B1：12 块在现区域 100% 放得下，饱和点 16~20）；注入 `layout.cubes[].xy/yaw_rad` |
| `native.board` / `native.button` | 孔板与按钮位姿 | 板基位 `[0.15,0,0]` + 三组偏移；按钮中心 `[-0.2,0]` | 不动；注入 `layout.board.{xy,yaw_deg}`、`layout.button_xy` |
| `native.initialize_color_order` | 每次初始化的颜色遍历顺序 | 每次 `randperm` | 不动；注入 `initializations[].color_order` |

**实施要点**

- **clutter 要新写。** `_resolve_sampling_config` 里有硬守卫 `if decision.get("layout_mode") != "native_dynamic": raise`，
  而全仓 grep `clutter` **只命中一行注释** ⇒ 摆放逻辑根本不存在。
- **D1 必须先修**：`_load_scene` 的 `except RuntimeError: logger.debug(...)` 不 raise 不补生成，
  而 `_initialize_episode` 的 `cube_collection[i]` **没有长度保护** ⇒ 缺块即 `IndexError`。
- `min_gap` 是**调用点写死的字面量**，`positions.cubes.min_gap` 只是说明字符串、运行时不被读。
- `dynamic` 是 generator 播种后的**第一次抽样**，xhard 固定 False 会改变 xhard 自己的随机流（可接受），
  **但绝不能影响原三档**。
- `put_in [5,7]` 单色最多分到 7，**逼近 `get_subgoal_with_index` 的 idx<10 上限**（全局改动①已扩表到 20）。
- `SAMPLING_OPERAND_PATHS` 冻结了 `parameters.BinFill.configs` 与 `positions.BinFill.cubes.*` ⇒ E3 重导快照。

### 2.4 PickXtimes（派生自 hard）

**要做**：target 位置推向边角、color 3、num `[6,15]`、加其他颜色 distractor。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.number_range.xhard` | 同一目标重复抓放次数 | `[4,5]`（闭，在 `__init__` 抽） | **`[6,15]`**；注入 `objects.num_repeats` |
| `decision.color.xhard` | 出现几种颜色 | `3` | **`3`（不变）**；注入 `objects.color_order` |
| `decision.target_cube_position_policy` | **目标方块**的位置采样 | 中心 `[-0.1,0]`、半边长 `0.2`、均匀 | **加 `corner_bias`**（边角偏置，新增采样模式）；注入 `layout.cubes[].xy` |
| `decision.goal_position_policy` | **放置圆盘**的位置采样 | **与上同值同区域** | **拆成独立一套**（C1：圆盘可留在中间）；注入 `layout.goal` |
| `decision.distractor` | 干扰物 | `None`（无消费点） | **3 个、黄/青/品红各 1**；注入 `objects.distractors[]` |
| `native.color_and_target_selection` | 颜色排列与目标块选择 | `randperm` → `randint` → `randint(0, len(all_cubes))` | 规则不改，但**目标候选池要与 `all_cubes` 解耦**；注入 `objects.target_cube_id` |
| `native.button` | 按钮位姿 | 中心 `[-0.2,0]`、range `[0.1,0.4]` | 不动；注入 `layout.button_xy` |

**实施要点**

- **D2 必须先修**：`spawn_random_target` 失败后 `except` 里没有 `return`/`raise`，紧接着
  `setattr(self, "target", target)` ⇒ **`UnboundLocalError`**。
- **真正的瓶颈是后生成的圆盘**，不是方块。方块 3~12 块都 100% 放得下，但圆盘（`radius=0.04`、
  `min_gap=0.04`、避让全部方块）成功率随方块数急剧下降：3 块 100%、**8 块 66%**、10 块 27%、**12 块 6%**
  ⇒ 加 3 个 distractor 后必须**放大 `goal_position_policy` 区域，或把生成顺序改成"先放圆盘再放方块"**。
- **distractor 的三处污染**：①`target_cube_idx = randint(0, len(all_cubes))` 会把干扰物抽成目标
  ⇒ 改为从显式候选列表抽；②`target_color_name` 靠 `in self.red_cubes/blue_cubes/green_cubes` 三分支回填，
  新颜色全不命中 ⇒ **保留前一次的残值**（不是 None，更隐蔽）；③`non_target_cubes` 被 `failure_func` 用
  ⇒ 干扰物**必须**在里面，抓错才算失败。
- **双真值**：`_load_scene` 用硬编码 `color_groups` 字面量，而 `NATIVE_SAMPLING.parameters.color_pool`
  **声明了却从未被读** ⇒ 改错地方会"看起来改了其实没生效"。
- `for idx, group in enumerate(...)` 与内层 `for idx in range(cubes_per_color)` **变量遮蔽**。

### 2.5 SwingXtimes（派生自 hard）

**要做**：number `[4,10]`、加其他颜色 distractor。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.number_range.xhard` | 摆动轮数（一轮左右各一次） | `[3,3]`（闭，`__init__` 抽） | **`[4,10]`**；注入 `objects.num_repeats` |
| `decision.color.xhard` | 出现几种颜色 | `3` | 不变；注入 `objects.color_order` |
| `decision.distractor` | 干扰物 | `None`（无消费点） | **3 个、黄/青/品红各 1**；注入 `objects.distractors[]` |
| `native.color_pool` | 颜色池 | 红/蓝/绿（**真被消费**） | 扩入干扰色；注入逐块 `color` |
| `native.cube_region` / `target_regions` | 方块与两个圆盘区域 | 方块中心 `[-0.1,0]` 半边长 `0.25`；圆盘 `[-0.1,∓0.2]` 半边长 `0.1` | **不动**（容量宽松：3~12 块 100% 放下）；注入 `layout.cubes[]/targets[]` |
| `native.swing_thresholds` | 摆动判定阈值 | `distance 0.03`、`z 0.12`、`height 0.1` | 不动；进 `sampling_trace` |

**实施要点**

- **加第四色的第一道硬墙是 `KeyError`**：`_load_scene` 里 `_color_lists = {"red":…, "blue":…, "green":…}`
  随后 `_color_lists[entry["name"]][0]` ⇒ 往 `color_pool` 加新色**直接 KeyError**
  ⇒ 必须同时给新色建 `self.<color>_cubes` 列表或改成动态建表。
- **序数表本环境有兜底**（`ordinals[i] if i < len(ordinals) else f"{i+1}th"`），所以 10 轮不崩——
  这与 PickXtimes 是关键差异。但全局改动①统一扩表后更稳。
- 目标候选池与 `target_color_name` 回填的污染与 PickXtimes **完全同构**，同样要改。
- `max_swings = num_repeats*2` 随之自动放大；10 轮 = 20 次摆动，`step` 的迟滞阈值
  （enter 0.03/0.12、exit 0.04/0.3）在长序列里**累积抖动误计一次就整局失败**。
- 任务条数 `2*num_repeats+3` ⇒ 10 轮 23 条，注意步数预算。

### 2.6 StopCube（派生自"现值即 hard"，A6）

**要做**：速度最快档、number `[6,15]`。**本环境原本没有难度分档**（无 `configs`，`difficulty` 无消费点），
按 A6 先建 `configs = {easy/medium/hard: 现值, xhard: 新值}`。

| 字段 | 含义 | 现值（= 新建的 hard） | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.move_interval_choices` | 速度档位（单程步数，**越小越快**） | `[60, 80, 120]` 等概率抽 | **`[60]`**（最快档）；注入 `actions.move_interval` |
| `decision.stop_time_range` | 第几次经过目标时停 | `low=2, high_exclusive=6` ⇒ 实际 `[2,5]` | **覆盖 `[6,15]`**（半开则 `low=6, high_exclusive=16`）；注入 `actions.stop_time` |
| `native.target` / `button` / `color` | 目标与按钮位姿、方块颜色 | 目标 xy 各 `uniform(-0.1,0.1)`；方块色 `rand(3)`（**本来就是任意 RGB**） | 不动；注入 `layout.target_xy/button_xy`、`objects.cube_rgb` |
| `native.route_rotation` | 路线整体旋转 | `uniform(-30,30)` 度 | 不动；注入 `actions.rotation_deg` |
| `native.motion_segments` / `time_rules` | 往返段数、按钮时刻、停止窗口 | **`step` 里写死 `for segment in range(5)`**；`steps_press = move_interval*(stop_time-0.5)`；窗口 `[move_interval*(stop_time-1), move_interval*stop_time]` | **段数改为按实际停止序号展开**；注入 `actions.segments[]/steps_press/stop_window` |

**实施要点**

- **`for segment in range(5)` 不改就必然全部失败。** 方块只往返 5 趟，而 `stop_time` 现取值域
  `[2,5]` 与之精确耦合；`number [6,15]` 后第 6 次起的"经过目标"**根本不存在**。
  改时注意 `start_pos/end_pos` 的 `segment % 2` 交替逻辑。
- **速度与判定阈值必须一起看**（C4 已授权自行调整）：停止窗口宽度恒等于 `move_interval`，
  取 60 ⇒ 容错从 120 步**砍半**；而 `is_obj_stopped_onto` 的阈值 `cube_half_size*3 = 0.06`
  配 0.01 m/step ⇒ **方块只在约 ±6 步内落在阈值内**；`interval` 恒 30 的按钮提前量 = 半趟。
- **三处随 number 线性膨胀**：`static_checkpoints = range(100, steps_press-interval, 100)`
  在 `60 × 15` 下变成 **9 条** "remain static" 任务（现 hard 上限 6 条）；
  `evaluate` 的超时判据 `current_step > move_interval*stop_time` ⇒ 900 步；上游 `MAX_STEPS` 要跟上。
- **`utils/vqa_options.py::_options_stopcube` 复刻了同一套 checkpoint 公式** ⇒ 改环境侧必须同步改它，
  否则 VQA 选项与实际子目标错位。

### 2.7 四个 Unmask 环境的共用事项

**① 干扰容器怎么放**（B3/B13 已定）：做成**额外容器**，放在现 region 之外、相机可见处，
3 个里 1~2 个内含 cube，**一律不参与 swap**。落实的关键是——

| 要点 | 怎么做 |
|---|---|
| 不被选成交换搭档 | 干扰容器**单独存 `distractor_bins`，不进 `self.spawned_bins`**。两个 Swap 环境的最近邻搜索遍历的就是 `spawned_bins` ⇒ 天然排除，**不用改搜索逻辑** |
| 不进碰撞证据与绑定核验 | `_verify_swap_binding` / `_object_states_for_collision` / `_check_swap_sweep_from_actual` 同样只认 `spawned_bins` ⇒ 一并排除 |
| 不进揭示动画 | `step` 的 `for i in range(step_bin_scan)` + `hasattr(self, f"bin_{i}")` 只扫 `bin_<i>` ⇒ 干扰容器**不要用这个命名** |
| 采样区域 | 外环 `max(|x|,|y|) ∈ [0.2675, 0.45]`，见下方 B13 实测 |
| 随机流 | 干扰容器的位置抽样**必须追加在全部既有取值点之后**（红线 N5） |

**② 现有容器区域已接近饱和**：region 中心 `[0,0]`、`region_half_size=0.2`、
`min_gap = cube_half_size × min_gap_factor(2) = 0.04`、`max_trials=256`，失败时 `except RuntimeError: break`。
按 `spawn_random_bin` 判据做等价模拟（20 组种子）：

| 请求容器数 | 3 | 5 | 8 | 10 | **15** |
|---|---|---|---|---|---|
| 实际放下（均值/最小/最大） | 3.0/3/3 | 5.0/5/5 | 8.0/8/8 | 9.75/9/10 | **10.25/9/12** |

⇒ **现在的 hard（`bin=15`）本来就放不满**，实际只有 9~12 个，而且 `break` 完全无声。
`step_bin_scan = 15` 还是真上限：**第 16 个及以后的容器不参与揭示动画**。

#### B13 实测：相机可见范围与干扰容器容量

纯几何计算，不起渲染——前视相机在 `_default_sensor_configs` 里是写死的
（`eye=[0.3,0,0.4]`、`target=[0,0,-0.2]`、`fov=90°`、256×256），桌面来自 `TableSceneBuilder` 的碰撞盒
（`half_size=(1.209, 0.6045, 0.4598)`，`initial_pose` 含绕 z 轴 90° 旋转 + 平移 `[-0.12, 0, -0.9196]`
⇒ 世界系 **x ∈ [-0.7245, +0.4845]、y ∈ [-1.209, +1.209]**，顶面正好 z=0）。

**① 相机可见 ∩ 桌面**（z=0 平面）：`x ∈ [-0.720, +0.430]`，y 随 x 收窄——

| x | -0.70 | -0.60 | -0.40 | -0.20 | 0.00 | +0.20 | +0.40 |
|---|---|---|---|---|---|---|---|
| 可见 y 范围 | ±0.800 | ±0.760 | ±0.670 | ±0.580 | ±0.490 | ±0.400 | ±0.310 |

**② 能放几个**（容器外廓半边 0.0275、`min_gap=0.04` ⇒ 中心最小距 0.095；扣掉现 region、机器人基座、按钮区）：

| 区域 | 饱和容量 | 请求 3 个 |
|---|---|---|
| 现 region 之外的全部可见桌面 | **65~70 个** | 100% 放下 |
| **推荐外环** `max(\|x\|,\|y\|) ∈ [0.2675, 0.45]` | **37.7 个**（min 33 / max 43） | 100% 放下（请求 2~6 个均 100%） |

**③ 画面里有多大**（256×256，容器外廓 0.055 m 的投影宽度）：`(0,0)` 处 14.3 px、`(-0.3,0)` 处 11.2 px、
**外环典型位置 `(-0.45,0.45)` 处 10.2 px**、`(-0.6,0.6)` 处 9.3 px、`(+0.3,+0.3)` 处 19.7 px。

**结论与建议**：放 3 个干扰容器**毫无容量压力**（余量 10 倍以上）。但"能放"不等于"看得清"——
可见区域最远处（y≈±0.8）容器只有 9 px 宽、贴在画面边缘。**建议采样区域取外环
`max(|x|,|y|) ∈ [0.2675, 0.45]`**：下界 = 现 region 半边 0.20 + 容器半廓 0.0275 + `min_gap` 0.04
（保证与现 region 内的容器不干涉），上界 0.45 保证容器在画面里仍有约 10 px、位置明显。
**含 cube 比例按用户定的「3 个里 1~2 个有」**，建议实现为"随机取 1 或 2 个装 cube"。

**③ swap 速度 ×1.5 的取整**（B4 已定）：`SWAP_WINDOW_STEPS = round(50/1.5) = 33`，
窗口变 `[64 + 33k, 64 + 33(k+1))`，**起点 64 不变**。做法是把 50 提成类级具名常量再乘倍率取整，
**不在分散字面量上手改**（`ButtonUnmaskSwap` 有六处）。要同步的下游：`step` 里预交换锁定的
`end_step=32*2`（VideoUnmaskSwap）与 `start_step=64`（ButtonUnmaskSwap）须继续等于首段 start；
`test_swap_schedule_generic.py` 与 `test_window_timeline.py` 的硬断言（含 demo 段按 6 帧对齐）。
`scripts/injection/rollout/windows.py` 的 `SWAP_START/SWAP_LEN` 属**甲的链路、按 N6 不动**。

**正向副作用**：`ButtonUnmaskSwap` 的步数余量原本只剩约 25%（它所有任务 `demonstration=False`
⇒ 观看交换那段**计入** 1302 配额），33 步窗口把这段从 464 压到 **328**，正好对冲。
对照 `VideoUnmaskSwap`：它第一个任务是 `static` 且 `demonstration=True` ⇒ 那段**不计入**配额，余量极大。

**④ `inject_fail_grasp` 的抽样空间随 pick 数变化**：`task4recovery` 自动扫描含 `solve_pickup_bin` 的任务，
pick 2→3 会把候选从 2 个变 3 个，那次 `randint` 的分布随之改变；`VideoUnmask`/`ButtonUnmask` 还把结果记进
`actions.recovery.selected_action_index` ⇒ **旧规格回注会不匹配**。

### 2.8 VideoUnmask（派生自 hard）

**要做**：加其他颜色 distractor、clutter bin、pick 3。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.pick_count.xhard` | 要抓起几个容器 | `2` | **`3`**；注入 `objects.n_picks` 与 `objects.pick_order` |
| `decision.bin_layout_policy.count.xhard` | 容器数 | `15`（**实际只放下 9~12**） | **clutter：具体数待实现时按容量定**；注入 `layout.bins[]` |
| `decision.bin_layout_policy.region_*` | 容器区域 | 中心 `[0,0]`、半边长 `0.2` | 加密需同时调 `min_gap_factor` 与 `step_bin_scan`；注入逐容器 `xy/yaw` |
| `decision.distractor` | 干扰物 | `None`（无消费点） | **3 个额外容器**（外环、1~2 个含 cube、不参与揭示）；注入 `objects.distractors[]` |
| `native.bins.min_gap_factor` / `max_trials` | 间距与重试预算 | `2`（⇒ 0.04）/ `256` | 视 clutter 密度调；进 `sampling_trace` |
| `native.step_bin_scan` | `step` 里遍历容器的上限 | **`15`** | **随容器数同步抬**；进 `sampling_trace` |
| `native.color_order` | 藏物颜色排列 | `randperm(3)`，`_load_scene` 用**本地字面量**而非 `color_pool` | 规则不改；注入 `objects.color_order` |
| `native.reveal_window` | 揭示窗口 | `[0, 64]` | 不动；注入 `actions.reveal` |

**实施要点**

- **pick=3 现在只会生成 2 抓**：任务构造是 `if pick_count[难度] > 1:` 追加一次 putdown + 一次 pickup，
  索引**写死** `self.bin_0` / `self.bin_1`、`color_names[0]` / `[1]` ⇒ 要改成按 `pick_count` 的循环。
  对象层面够用（`bin_2` 与 `color_names[2]` 都存在）。
- **`task_goal.py` 里同一个坑再来一遍**：它读的是**类属性** `configs[难度]['pick'] > 1`，
  只有"1 抓 / >1 抓"两支 ⇒ pick=3 会输出"两个容器"的错误文本，而该文本还进视频文件名与 HDF5 metadata。
  `tests/lightweight/test_TaskGoal.py::test_videounmask_pick_one/two` 要同步。
- **`evaluate()` 不用改**：完全交给 `sequential_task_check` 顺推，`is_bin_pickup` 只看 `z > 0.15`、不看颜色。
- 步数估算：hard 中位 329 → 加一抓约 **+155 ⇒ ≈485**，最大 399 → ≈555，远低于 1302 与失败保护 2000。

### 2.9 ButtonUnmask（派生自 hard）

**要做**：与 VideoUnmask 完全相同（加 distractor、clutter bin、pick 3）。

字段表与 2.8 同构，差异只有三处：

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `native.button` | 按钮位姿 | 中心 `[-0.2,0]`、`randomize_range [0.1,0.1]`、`scale 1.5` | 不动；注入 `layout.button_xy` |
| `native.constructor_rng` | 构造期一次 `randint(1,6)` | **不决定任何行为、只占随机流位置**（红线 R8） | **原样保留、不得删改**；进 `sampling_trace` |
| 任务表结构 | — | **没有 `static` 任务**，第一项就是"按按钮"；揭示窗口 `[0,64]` 与"去按按钮"在时间上重叠 | 扩 pick 时保持这个结构 |

**实施要点**

- pick 分支同样是 `> 1`、索引同样写死 `bin_0`/`bin_1` ⇒ 同样只生成 2 抓。
- 第一个 pickup 任务的 `failure_func` 与 `solve` 被包成**单元素列表** ⇒ 照抄循环时要保持这个形态。
- 容器区域比 VideoUnmask **更小**：按钮区（中心 `[-0.2,0]` ± `[0.1,0.1]`）与容器 region（x∈[-0.2,0.2]）**重叠**。
- 步数：hard 中位 373 → ≈530，最大 452 → ≈610。

### 2.10 VideoUnmaskSwap（派生自 hard）

**要做**：swap `[8,12]`、pick 3、加 distractor、swap 速度 ×1.5。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| **`native.configs.xhard.swap_min/max`** | 交换次数 | `[2,3]`（闭） | **`[8,12]`**；注入 `objects.n_swaps` |
| **`native.configs.xhard.pick_min/max`** | 抓取个数 | `[2,2]` | **`[3,3]`**；注入 `objects.n_picks` |
| `native.configs.xhard.bin` | 容器数 | `4` | 不变（本环境不做 clutter）；注入 `layout.bins[]` |
| `native.object_selection.pickup_selected_indices` | 抓哪几个 | **`[0,1]`** | **`[0,1,2]`**；注入 `objects.pick_order` |
| `decision.swap_speed_multiplier` | 交换速度倍率 | `1`（**死键，无消费点**） | **`1.5`，并真正接上消费点**；注入 `actions.swap_windows[]` |
| `decision.distractor` | 干扰物 | `None`（**死键**） | **3 个额外容器**；注入 `objects.distractors[]` |
| `native.containers` | 容器锚点与旋转 | 三角/直线/四点，局部半边长 `0.07`、整体旋转 `[0,180]` **弧度**、`min_gap` 内联 `0.02` | 不动；注入 `layout.type/theta_rad/bins[]` |
| `native.swap_path` | 交换轨迹 | `lane_offset 0.07`、`smooth=True`、`keep_upright=True` | 不动（⚠ `keep_upright` 与 `lock_cube_offset` **在函数体内一次都没被引用**）；注入 `actions.swap_pairs[]` |

**实施要点**

- **swap/pick 读的是 `parameters.configs`（native），不是 decision** —— `decision.swap_count_range` /
  `pick_count_range` / `swap_speed_multiplier` **全是死键**。改错一边就"看起来改了其实没生效"。
- **pick=3 现在只生成 1 抓、反而更简单**：分支是 `if self.pick_times == 2:` **严格相等**，3 会落到 else。
- ⚠ **额外铁闸**：`_resolve_sampling_config` 对 `parameters.object_selection` 与 `swap_selection` 做
  `json.dumps` 全等比对 ⇒ **不能从外部改 `pickup_selected_indices`**，必须改源码里的 `NATIVE_SAMPLING` 字面量。
- **swap 8~12 结构上通得过**：`_refresh_swap_schedule` 已是通式，且有 `for k in range(3, swap_times)`
  的槽位循环（发起者按 a,b,c 循环复用）。
- 步数：8 次 ⇒ ≈862/991，12 次 ⇒ ≈1062/1191（含第三抓 +155）。**对 1302 配额安全**——
  它第一个任务 `demonstration=True`，观看交换那段不计入。真正的风险是**单条墙钟**：
  注入态的子步 SAT 检查只在 `_in_swap_window()` 内跑，窗口总长从 150 步涨到 600 步 ⇒ 检查量 ×4。
- `bin` 超过锚点数会 **`IndexError`**（`for i in range(bin)` 直接取 `region[i]`），不是静默 break。

### 2.11 ButtonUnmaskSwap（派生自 hard）

**要做**：swap `[6,8]`、pick 3、加 distractor、swap 速度 ×1.5。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| **`decision.swap_count_range.xhard`** | 交换次数 | `[2,3]`（闭，**读 decision**） | **`[6,8]`**；注入 `objects.n_swaps` |
| **`decision.pick_count_range.xhard`** | 抓取个数 | `[2,2]` | **`[3,3]`**；注入 `objects.n_picks` |
| `native.bin_count.xhard` | 容器数 | `4`（**读 native**） | 不变；注入 `layout.bins[]` |
| `decision.swap_speed_multiplier` | 交换速度倍率 | `1`（死键） | **`1.5`，接上消费点**；注入 `actions.swap_windows[]` |
| `decision.distractor` | 干扰物 | `None`（死键） | **3 个额外容器**；注入 `objects.distractors[]` |
| `native.swap_window` | 交换窗口 | `{start_step:64, duration_steps:50}`（**声明了但一处都没被消费**） | **改成真正被消费**，值取 `{64, 33}`；注入 `actions.swap_windows[]` |
| `native.buttons` | 两个按钮 | 左 `[-0.2,-0.1]`、右 `[-0.2,0.1]`、range 各 `[0.05,0.05]` | 不动；注入 `layout.buttons[]` |
| `native.anchors` | 容器锚点 | 四点/三角/直线 + `offset_scale 0.1`；**未被选中的分支仍照常消费随机数**（R8） | 不动，**不得省略未选中分支的抽样** |

**实施要点**

- **头号阻碍：`_refresh_swap_schedule` 是写死的三分支**（只认 1/2/3）。`swap_times >= 4` 时
  **三个分支全不命中 ⇒ `self.swap_schedule` 从未被赋值 ⇒ `step` 里 `len(self.swap_schedule)` 直接
  `AttributeError`**；`_load_scene` 也只建了三套发起者槽位。**必须同时改这两处**，
  参照 `VideoUnmaskSwap` 的通式 + `for k in range(3, swap_times)` 循环。
- **task_list 在 `_initialize_episode` 里构造**，不在 `_load_scene`（另外三个都在 `_load_scene`）。
  pick 分支同样是 `== 2` 严格相等 ⇒ pick=3 只生成 1 抓；索引写死 `selected_bins[0]`/`[1]`，
  本环境**没有** `pickup_selected_indices` 这个键。
- **步数余量最紧**：本环境**所有任务 `demonstration=False`** ⇒ 观看交换那段**计入** 1302 配额。
  8 swap + 3 pick 最大估计 ≈960，余量约 25%；速度 ×1.5 把这段压到 328 是有效对冲。
- `_initialize_episode` 每次 reset 重建 task_list 并重跑 `inject_fail_grasp` ⇒ 见 2.7 ④。
- partner 的最近邻是**硬编码 `[:2]`**（不像 VideoUnmaskSwap 读 `partner.position_axes`）；
  本环境**没有** `_verify_swap_binding` ⇒ 干扰容器若混进 `spawned_bins` 会**静默改变交换对**、不报错。

### 2.12 PickHighlight（派生自 hard）

**要做**：clutter、highlight number `[5,7]`、block 颜色任意。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.highlight_count.xhard` | 同时高亮并要抓的目标数 | `3` | **`[5,7]`**；注入 `objects.highlight_ids` |
| `decision.spawn_count.xhard` | 场上方块总数 | `6` | **`[8,10]`**（B5：实测只稳放 8~10）；注入 `objects.n_cubes` 与实际生成数 |
| `decision.cube_region` | 方块采样区域 | 中心 `[-0.1,0]`、半边长 `0.2` | **不动**（B1）；注入 `layout.cubes[].xy/yaw` |
| `native.cubes.min_gap_factor` | 间距系数 | `2` ⇒ `min_gap=0.04` | **不动**（B5 选了降 spawn 而非降间距） |
| `decision.block_color_policy` / `native.color_pool` | 逐块颜色 | 红/蓝/绿，**逐块独立抽、可重复** | **颜色任意**；注入逐块 `color` |
| `native.highlight_window` | 高亮时序 | `{start 10, end 100, simultaneous: True}`，所有目标**共用同一窗口、同时高亮** | 不动；注入 `actions.highlight_windows` |
| `native.button` | 按钮位姿 | 中心 `[-0.2,0]`、range `[0.1,0.4]` | 不动；注入 `layout.button_xy` |

**实施要点**

- spawn `[8,10]` 的下界 8 ≥ highlight 上界 7 ⇒ 恒有余量。但仍要加硬断言：
  `randperm(len(all_cubes))[:k]` 在 `k > len` 时**静默截断**，而 `except RuntimeError: break`
  会保存已生成数量、不补抽 ⇒ 没有任何报错。
- **高亮会连片（C3 已同意处理）**：高亮是在方块**正下方**加白色圆盘，`disk_radius=0.05`
  ⇒ 直径 0.10 m 是方块边长 0.04 m 的 **2.5 倍**，而现 `min_gap=0.04`、典型中心距 0.06~0.08 m
  ⇒ **3 块时就可能相切**，5~7 块必然糊成一片 ⇒ 缩小 `disk_radius` 或改用同心环。
  ⚠ 现在 `step` 调 `highlight_obj` 时**没传 `disk_radius`** ⇒ 要先把参数接出来。
- **误抓失败会激增**：每个 pick 的 `failure_func` 是"抓起任何一块非目标即失败"。
- `task_goal` **不含颜色词**、`evaluate()` **也不看颜色** ⇒ 颜色任意对本环境几乎无代价，
  唯一要处理的是 subgoal 里的 `, which is {color}` 后缀。
- **D4 已定修复**：首个按钮任务 `failure_func` 缺 lambda ⇒ 这条判据从来没生效过。
  补上后**原三档失败率可能上升**，V1 回归时单独观察。

### 2.13 VideoRepick（**派生自 medium**）

**要做**：clutter、pick times `[4,6]`、block 颜色任意、swap `[8,12]`（A3 已定启用）。

> **为什么从 medium 派生**：hard 是 5 轮 × 红蓝绿 = 15 块的特殊结构、`swap=0`、连 `cube` 键都没有；
> medium 才是"3 块 + swap `[2,3]`"的常规结构，`swap [8,12]` 接得上。

| 字段 | 含义 | medium 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| **`native.parameters.num_repeats`** | 同一目标重复抓放次数 | `low=1, high_exclusive=4` ⇒ **实取 1/2/3** | **`[4,6]` ⇒ 写 `low=4, high_exclusive=7`**（半开！）；注入 `objects.num_repeats` |
| `decision.num_repeats_range` | 同上 | 有键但**无消费点（死键）** | **要么接上消费点、要么删**，不能只改它 |
| `native.configs.xhard.swap_min/max` | 交换次数 | `[2,3]`（闭） | **`[8,12]`**；注入 `objects.n_swaps` |
| `native.configs.xhard.cube` | 方块数 | `3` | **clutter：按容量定**（hard 那套区域可放 30+）；注入 `layout.cubes[]` |
| `decision.layout_mode` | 摆放模式 | medium 用**三组锚点**（每块围绕一个锚点、局部半边长 `0.07`） | **clutter 必须放弃锚点结构**，改用整片区域（中心 `[-0.1,0]`、半边长 `[0.2,0.25]`） |
| `decision.block_color_policy` | 逐块颜色 | 整局**三块同色** | **保持同色语义、色值任意**（C2）；注入 `objects.color` |
| `native.swap_selection` | 发起者与搭档 | 发起者池**写死 3 个**（`swap_indices[k % 3]` 循环复用）；搭档为运行时 XY 最近邻 | **保持 3 个发起者**（B12）；注入 `actions.swap_pairs[]` |
| `native.swap_timing` | 交换窗口 | 第 k 次 `[start+50k, start+50(k+1))`，每段固定 50 步 | 次数提到 8~12，**本环境不做速度 ×1.5**；注入 `actions.swap_windows[]` |
| `native.button` | 按钮位姿 | 中心 `[-0.2,0]`、range `[0.1,0.1]` | 不动；注入 `layout.button_xy` |

**实施要点**

- **`num_repeats` 改错地方是最容易踩的坑**：`__init__` 读的是 **native** 的 `parameters.num_repeats`，
  而 `decision.num_repeats_range` **没有消费点** ⇒ 只改 decision 会**静默沿用 1/2/3**。
  另外 `SAMPLING_OPERAND_PATHS` 冻结了这三个操作元 ⇒ E3 重导快照。
- **swap 12 次 × 50 步 = 600 步静止段**，episode 显著变长。
- **clutter + swap 的穿模风险**：`swap_flat_two_lane` 的 `other_cube` 传的是"其余所有方块"，
  `lane_offset=0.07` 的绕行车道极可能扫过旁观块；而 **D5 未修之前几何检查一次都不跑**
  ⇒ **D5 是本环境的前置**。
- **注入分支依赖颜色名字符串**：`idx = [item["name"] for item in options].index(spec["objects"]["color"])`
  ⇒ 颜色连续化会打断这条路径。
- easy/medium/hard 本身不动（口径 12），hard 那套 `cube_{color}_{idx}` 命名与 `hard_round_order`
  规格路径**都不受影响**。

### 2.14 VideoPlaceButton（派生自 hard）

**要做**：video 里完成 2 个 block、各自放回原位，其余不变。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.demo_object_count` | 演示几个方块 | `1`（**死键**，审计里明文豁免） | **`2`**，并**新建消费点**；注入 `objects.demo_ids[]` |
| `decision.demo_return_policy` | 演示完放哪 | `"native_random_goal_site"` ⇒ 放到随机 `goal_site`（z 被压到 −0.05 隐藏） | **`"return_to_origin"`**；注入 `actions.return_pose_by_object_id` |
| `native.color.xhard` | 场上方块数（= color 值，`cubes_per_color=1`） | `3` | 不变 ⇒ **3 块够演示 2 块**（原 easy 只有 1 块的硬阻塞已因口径 12 消解） |
| `decision.targets.xhard` | 目标台数 | `4` | 不变；注入 `layout.targets[]` |
| `decision.swap.xhard` | 是否交换目标台 | `True` | 不变；注入 `objects.swap_pair_ids` |
| `decision.additional_place.xhard` | 额外放置 | `False` ⇒ `pre_flag`/`post_flag` 恒 0，**`target_2`/`target_3` 分支永不执行** | 保持 `False`；这块死代码在重写模板时一并处理 |
| `native.task_mapping` | before/after 答案映射 | `before→target_0`、`after→target_1` | **2 个对象后须重新定义**；注入 `objects.task_flag`、`actions.target_target_id` |

**实施要点**

- **演示模板是内联硬编码**（在 `_load_scene` 末段），不是"数量可配"的循环 ⇒ 要**重写整段序列**。
- **目标选择改动会平移随机流**：`randint(0, len(all_cubes))` 改成 `randperm(...)[:2]`
  ⇒ 其后的 swap randperm、`task_flag` 等全部平移。xhard 是新档、可接受，**但不得影响原三档**。
- **"放回原位"需要一个 actor 作落点**：`solve_putonto_whenhold(target=…)` 与
  `is_obj_dropped_onto(obj, target)` 内部都取 `target.pose.p`。全仓**没有任何地方保存方块初始位姿**。
  **唯一不平移随机流的插入方式是 `spawn_random_target(randomize=False, region_center=<该方块 xy>)`**
  （`randomize=False` 时不抽随机数），且放在所有其他 spawn **之后**、`include_existing=False`、
  `include_goal=False`、`avoid=None`。
- **`vqa_options.py::_options_videoplacebutton` 的 `"available": env.targets`** 不含 home site
  ⇒ "回原位"步若走 choice-action 匹配会选不到，需扩 `available`。
- **撤销审计豁免**：`train_split_audit.py::NEUTRAL_KEYS` 里 `demo_object_count` 那条。
- `target_color_name` 由三分支反查后直接进 `task_goal` ⇒ 2 个对象要分别指代时指令文本要重新设计
  （本轮不改颜色，风险较低）。

### 2.15 VideoPlaceOrder（派生自 hard）

**要做**：与 2.14 相同（video 里完成 2 个 block、各自放回原位，其余不变）。

字段表与 2.14 同构，差异与**额外阻碍**：

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `native.visit_selection` | 访问哪几个目标台、顺序 | 抽 2~4 个有序台 | 不变；注入 `objects.visit_ids` |
| `native.answer_selection` | 任务答案 | `which_in_subset` 取 1~序列长度 | 不变；注入 `objects.which_in_subset` |
| **`native.button_insertion`** | 按钮插在第几步 | **`button_task_index = k*2 + 2`** | **公式必须重推**；注入 `actions.button_task_index` |
| `decision.targets.xhard` | 目标台数 | `4` | 不变 |

**实施要点**

- **`button_task_index = k*2+2` 在 2 个对象下直接失效**：`*2` 是"每个 visit 贡献 pick+drop 两条"的硬编码；
  两个对象后按钮会被插进 **pick 与 drop 之间**，**毁掉"按钮前/后第 n 次放置"的可判定性**。
- 演示模板在 **`_initialize_episode`**（与 2.14 在 `_load_scene` 不同），改的位置不一样。
- 其余（home site、随机流平移、`vqa_options`、审计豁免）与 2.14 相同。

### 2.16 Imitation 族的两条前提

**① MoveCube 与 InsertPeg 本来没有难度分档**：两个类都无 `configs` / `config_*`，`self.difficulty`
算出来后**全文件无读取点**；`env_metadata/train/` 里它们每条 record 都带 `difficulty` 字段但**环境不读**。
按 A6 建 `configs = {easy/medium/hard: 现值, xhard: 新值}`。

**②「转角更大、可以和桌面平行」已澄清为「yaw 放宽到 ±180°」**（A1）。杆的长轴**现在就与桌面平行**
（`build_peg` 的长轴是 link 局部 x 轴；两个环境构造四元数都用
`euler_angles_to_matrix(torch.tensor([[0.0, 0.0, yaw]]), convention="XYZ")`，**前两位恒 0、只绕世界 z**；
位置 `p=[x, y, 0.0]`）⇒ 不引入 pitch/roll、**不需要 z 补偿**。

**±180° 与 Panda joint7 的 ±166° 限位冲突，按等价朝向归约解决**（B11）：
`grasp_and_lift_peg_side` 构造的是 `grasp_pose_q = peg_q ⊗ Rx(π)`（**夹爪目标姿态**），
而 `grasp_pose_p = pose.p` **原样不动**。推导
`R_grasp(yaw+π) = Rz(yaw)·Rx(π)·Rz(π) = R_grasp(yaw)·Rz(π)` ⇒ 两者只差一个绕夹爪自身 approach 轴的 180°，
对平行两指夹爪**夹持几何完全等价**。所以归约**只改夹爪姿态、不碰杆位姿**，
head/tail 空间位置不变，`InsertPeg` 的 near/far 判定不受影响，**两个环境同等处理**。

### 2.17 MoveCube（派生自"现值即 hard"，A6）

**要做**：cube 与 stick 位置推向边角、stick 转角更大、更难抓。

| 字段 | 含义 | 现值（= 新建的 hard） | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.demo_layout.peg_position_policy` | 演示段杆位置 | `base_y_abs 0.2`、`jitter_span 0.1` ⇒ 根点 `x ∈ [-0.05,0.05]`、`y ∈ [±0.15,±0.25]` | **加 `corner_bias`**；注入 `layout.demo.peg_offsets` |
| `decision.demo_layout.cube_position_policy` | 演示段方块位置 | `center_span 0.2`、`center_offset -0.1`、`region_half_size 0.05` | **加 `corner_bias`**；注入 `layout.demo.cube_xy` |
| `decision.execution_layout.*` | 执行段布局 | **与 demo 逐键同值、但各抽一套** | 同样加 `corner_bias`，**两套不可合并**；注入 `layout.execution.*` |
| `decision.peg_yaw_range` | 杆转角 | `span π/2`、`offset π/4` ⇒ **±45°** | **±180°**；注入 `layout.demo/execution.peg_yaw` |
| `native.cube_rejection` | 方块拒绝采样 | `max_trials 128`、`min_distance_factor 5`（离 goal > `cube_half_size*5`） | 不动；进 `sampling_trace` |
| `native.goal_regions` | 目标圆盘区域 | demo 半边长 `0.15`、execution `0.1` | 不动；注入 `layout.*.goal` |
| `native.way_selection` | 每次初始化用哪种操作 | `["peg_push","gripper_push","grasp_putdown"]` 三选一 | **三条都必须活着**（V3 已禁"只留 peg_push"）；注入 `initializations[].way` |
| `native.peg_size` | 杆尺寸 | `length 0.1`、`radius 0.01`（两次 rand 乘 0） | 不动，**两次抽样必须保留**（R8） |

**实施要点**

- **D3 必须先修**：局部函数 `_sample_cube_center` 在 128 次失败后 `return None`，
  调用处紧接 `float(cube_center[0])` ⇒ **`TypeError`，没有兜底**。边角推移会让触发概率大增。
  其后的 `spawn_random_cube` 还会在内部 256 次失败后 `raise RuntimeError`。
- **"更难抓"的失败是静默的**：抓取走求解器（`grasp_and_lift_peg_side` 用 link 位姿、
  `solve_pickup` 用 OBB 求解），失败后 screw（1 次）→ RRT\* 重试，再失败则该段演示
  **被静默跳过、episode 继续跑完、最后判 fail** ⇒ **必须跑成功率扫描**，不能只看有没有异常。
- `spawn_random_cube` / `spawn_random_target` 的避让列表里**没有 peg**
  ⇒ 大 yaw 的杆与 cube/goal **现在就可以重叠生成，没人拦**。
- 旁证：metadata 里已有 `seed 14602` 这种非整百 seed，推测是原版遇演示失败后 seed+1 重试的痕迹
  ⇒ **当前参数下就已经有失败率**。

### 2.18 InsertPeg（派生自"现值即 hard"，A6）

**要做**：多生成一根 stick 且离 target stick 更近、stick 转角更大、更难抓。

| 字段 | 含义 | 现值（= 新建的 hard） | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.peg_offsets` | 杆数（**实际由它的长度决定**） | `[0.1, 0, -0.1]` ⇒ 3 根 | **4 个元素 ⇒ 4 根**；注入 `initializations[].pegs[]` |
| `decision.peg_count` | 杆数（名义） | `3`，只在一次 `randint(0, peg_count)` 用过、**结果立刻被 `overridden_to=0` 覆盖** | 同步改为 `4`，⚠ 这会**改变那次抽样的取值域**、平移随机流（xhard 可接受） |
| `decision.near_target_distractor` | 新杆相对目标杆的约束 | `None`（**无消费点**，V3 预留键） | **接上消费点**：第 4 根在现判据允许范围内**尽量贴近下限 0.075 m**（B6：间距判据不动） |
| `decision.peg_yaw_range` | 杆转角 | `half_span_deg 45` ⇒ **±45°** | **±180°**（配 2.16 的等价朝向归约）；注入 `initializations[].pegs[].yaw` |
| `native.peg_sampling` | 杆位拒绝采样 | `x ∈ [-0.2,0.2]`、`y ∈ [-0.3,0.3]`、离孔板 > `radius*6`(0.06)、杆间 > `length*1.5`(0.075)、`max_attempts 512` | **判据不动**（B6）；注入每根杆的 `xy` |
| `native.box_pose` | 孔板位姿 | xy 各 `±0.1`、yaw `90°±20°` | 不动；注入 `initializations[].box_pose` |
| `native.color` | 杆头颜色 | `head_rgb = rand(3)` **循环外只抽一次**，`tail = 1 - head` ⇒ **所有杆外观完全一致** | 不动；注入 `objects.head_rgb` |
| `native.target_peg` | 目标杆 | `randint(0,3)` 抽完**立刻被 `overridden_to=0` 覆盖** ⇒ 恒为 `peg_0` | 不动；注入 `objects.target_peg_id` |

**实施要点**

- **"更近"与现有判据的张力**：`build_peg` 的几何是 head 占 `[-0.025,+0.025]`、tail 中心在 `x=-0.05`
  占 `[-0.075,-0.025]` ⇒ **整根杆跨度 0.1 m，而最小间距只有 0.075 m**
  ⇒ **现行参数下两根杆本来就可能互相穿插**，靠物理弹开。B6 已定**不放松间距**
  ⇒ "更近"的幅度因此有限（最近就是 0.075 m），且这个既有穿插风险**保持原样、不修复**。
- **`max_attempts=512` 耗尽会 `raise RuntimeError`**（硬崩，不是软降级）；加第 4 根会让预算更紧。
- **目标识别**：4 根杆外观完全相同、目标恒 `peg_0`、subgoal 只说 `grasp the near/far end`
  ⇒ **靠 video demo 判断**（C5 已确认这是既有设计，不是本轮引入的问题）。
- 执行段 `failure_func` 里有"**碰起任何一根非目标杆 = 立即判失败**" ⇒ 干扰杆越近误抓率越高。
- `initializations.{idx}.pegs.{i}` 会多出 `i=3` ⇒ G4 的 `missing`/`unused` 要同步；
  `vqa_options.py::_options_insertpeg` 的候选从 6 个涨到 8 个。

### 2.19 PatternLock（派生自 hard）

**要做**：最难情形 video 演示 20~30 秒。**不改布局、只增加步骤长度**（B8）。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.grid.xhard` | 网格边长 | `5`（⇒ 25 个节点） | **不动**（B8：不改布局） |
| `decision.length.xhard` | **节点数**（不是段数） | `[4,8]` | **`[20,25]`**；注入 `actions.path_nodes` |
| `native.path_selection.max_attempts` | 路径搜索预算 | `1000`，**耗尽不报错、用最后一条** | **搜索策略改为长度定向**（否则随机 DFS 命中不了超长路径） |
| `native.grid_geometry` | 网格几何 | 中心 `[-0.1,0]`、间距 `0.1` | 不动；注入 `layout.nodes[]` |
| `native.motion_template` | 每段动作 | 每目标 `solve_swingonto` 两次 screw + `close_gripper` | 不动；注入 `actions.demo_actions` |
| 运行记录 | 实际演示帧数 | 实测 hard 93 / 157 / 257 帧 ⇒ **3.1 / 5.2 / 8.6 s @30fps** | 目标 600~900 帧；记 `demo_frames/fps/duration_s` |

**实施要点**

- **不改布局时有物理上限**：`utils/adjacent.py::dfs_path` 是**简单路径 DFS**（`visited` 集合、不许重复节点）
  ⇒ 段数上限 = `R×C − 1` = **24 段 ≈ 744 帧 ≈ 24.8 s** ⇒ **30 s 够不到**，实际只能落在 **20~24.8 s**。
- **"只增加长度"必须配合改搜法**：现在是"随机起终点 + 随机邻居取第一条解"，
  `max_attempts=1000` 内命中近乎遍历全图的超长路径**概率极低**。
- **成功要过两道闸**：`sequential_task_check` 全完成，且 `evaluate` 里
  `recent_achieved == selected_labels` 的字符串匹配。
- 触碰阈值是**默认值**（水平 0.01 m、z < 0.1），比 RouteStick（0.03 / 0.15）严得多。
- 失败判据：碰到任何既不是当前期望、也不是上一个的节点 ⇒ 路径越长，误触概率越高。
- `step` 里的尾迹与按钮高亮是**写死的 `cur_step + 40`**、没有外提到 `_sampling`
  （RouteStick 那边外提了）⇒ 若要统一口径需一并外提。

### 2.20 RouteStick（派生自 hard）

**要做**：最难情形 video 演示 20~30 秒。**不改布局、只增加步骤长度**（B9）。

| 字段 | 含义 | hard 现值 | xhard 新值 / 注入什么 |
|---|---|---|---|
| `decision.configs.xhard.length` | **段数 L**（节点数 = L+1） | `[4,7]` | **`[12,15]`**；注入 `objects.L` |
| `decision.configs.xhard.backtrack` | 是否允许立即回头 | `True` | 不变；注入 `objects.allow_backtracking` |
| `native.walk` | 游走规则 | 节点 `[0,2,4,6,8]`、邻居 `[-1,1]`、端点强制反向 | **不动**（⚠ 受铁闸保护：除 `direction.threshold` 外改动即 `ValueError`）；注入 `actions.nodes` |
| `native.yaw_deg` | 整排旋转 | `rand*60 − 30` ⇒ ±30° | 不动；注入 `layout.rotation_deg` |
| `native.grid_geometry` | 网格与障碍柱 | 1×9、间距 `0.07`；柱位 1/3/5/7、半径 `0.015` 高 `0.1` | 不动；注入 `layout.node_poses/obstacle_poses` |
| `native.tcp_trail.end_offset_steps` | 白球尾迹存活步数 | **`40`**（官方原值，已恢复） | 不动（`test_native_restore_step2.py` 锁死 40） |
| 运行记录 | 实际演示帧数 | **实测 = L × 50，整齐无例外** | L=12~15 ⇒ 600~750 帧 ⇒ **20~25 s @30fps** |

**实施要点**

- **本环境天然支持"只增加长度"**：`generate_dynamic_walk` 在 5 个节点的线性图上随机游走、
  **允许重复访问**，`steps` 任意大都合法 ⇒ 无需改搜法（与 PatternLock 相反）。
- **50 帧/段的来源**：`solve_swingonto_withDirection` 的"贝塞尔 45 点 + 末端保持 5 点"，
  `follow_path` 一个位置一步 ⇒ 实测正好 50，说明 IK 没失败过。
- **执行段也是 L×50 帧**，加 `solve_strong_reset(timestep=200)` 的 200 步
  ⇒ L=15 时执行段 750+200=950，**对 `evaluation.py` 的 1300 尚有余量**；
  **L > 约 22 必然被截断** ⇒ 这是取 `[12,15]` 而非 `[12,18]` 的原因。
- 尾迹**不是纯装饰**：它是会渲进 `front/wrist` 的 rgb 与 depth 的场景物体，属于进对拍的观测输入
  ⇒ 演示变长会成比例增加尾迹累积渲染量。
- 易踩陷阱：`__init__` 在**不传 `difficulty` kwarg** 时会无条件 `self.difficulty = "easy"`
  （覆盖 `seed % 3`）。数据生成链路走 metadata 的 difficulty，实际不受影响。

### 2.21 布局简图（xhard 改动后）

俯视图，**横轴 y（左右）、纵轴 x（机器人在下方）**，每格约 0.1 m。所有坐标取自源码实测值。
`▒` = 原有区域（不动），`░` = 本轮新增/扩大的区域，`●` = 物体，`▲` = 机器人基座。

#### 通用坐标框架（十六个环境共用）

```text
                              ← y →
           -0.5  -0.4  -0.3  -0.2  -0.1   0.0  +0.1  +0.2  +0.3  +0.4  +0.5
          ┌──────────────────────────────────────────────────────────────┐
   x=+0.48│                    桌面远边 x = +0.4845                       │
   x=+0.4 │ · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·│  相机可见到 x=+0.43
   x=+0.2 │ · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·│
   x= 0.0 │ · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·│
   x=-0.2 │ · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·│
   x=-0.4 │ · · · · · · · · · · · · · · · · · · · · · · · · · · · · · · ·│
   x=-0.6 │ · · · · · · · · ▲ 机器人基座 (-0.615, 0) · · · · · · · · · · ·│
   x=-0.72│                    桌面近边 x = -0.7245                       │
          └──────────────────────────────────────────────────────────────┘
   相机：eye (0.3, 0, 0.4) → target (0, 0, -0.2)，fov 90°，256×256
   可见 ∩ 桌面：x ∈ [-0.720, +0.430]；y 随 x 收窄（x=-0.7 时 ±0.80，x=0 时 ±0.49，x=+0.4 时 ±0.31）
```

#### BinFill：clutter 12 块 + `dynamic=False`

```text
                 -0.3   -0.2   -0.1    0.0   +0.1   +0.2
   x=+0.2  │                                                  │
   x=+0.15 │                      ▒▒▒▒▒ 孔板 基位 [0.15, 0]     │  板边 0.1 / 孔边 0.08
   x=+0.1  │  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒                  │
   x= 0.0  │  ▒  ● ●   ●  ● ●    ● ●  ●  ▒  ← 方块区（不动）    │  中心 [-0.1, 0]
   x=-0.1  │  ▒    ●  ●    ●  ●     ●   ▒                      │  半边长 [0.2, 0.25]
   x=-0.2  │  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  ⊕ 按钮 [-0.2,0] │  min_gap 0.02
   x=-0.3  │                                                   │
   改动：spawn 10~12 → 固定 12；颜色 3；put_in [3,5] → [5,7]；dynamic 由 randint 改为固定 False
   区域与间距 **不动**（B1：12 块在现区域 100% 放得下，饱和点 16~20）
```

#### PickXtimes：目标推向边角 + 3 个干扰物

```text
                 -0.3   -0.2   -0.1    0.0   +0.1   +0.2
   x=+0.1  │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░                  │
   x= 0.0  │  ░ ●目标   ▒▒▒▒▒▒▒▒▒▒▒▒▒   ◇干扰 ░                │  ▒ = 圆盘仍可在中间（C1）
   x=-0.1  │  ░ ◇干扰   ▒ 圆盘区（拆成 ▒ 独立一套）▒   ░        │  ░ = 目标块加 corner_bias
   x=-0.2  │  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ⊕ 按钮          │      推向四角
   x=-0.3  │      ●目标                      ◇干扰            │
   改动：num [4,5] → [6,15]；target 位置加 corner_bias；圆盘区域拆成独立参数；+3 个干扰块（黄/青/品红）
   ⚠ 圆盘成功率随方块数急降（3 块 100% → 8 块 66% → 12 块 6%）⇒ 需放大圆盘区域或改成"先放圆盘"
```

#### 四个 Unmask：干扰容器放在外环（B3 / B13 实测）

```text
              -0.5   -0.4   -0.3   -0.2   -0.1    0.0   +0.1   +0.2   +0.3   +0.4   +0.5
   x=+0.45 │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 外环上界 0.45
   x=+0.3  │ ░░░   ▣干扰容器（含 cube）        ░░░                       │
   x=+0.2  │ ░░░ ┌────────────────────────────┐ ░░░                     │ ← 现 region 边界 0.20
   x=+0.1  │ ░░░ │ ▒ ▣ ▒ ▣  ▒ ▣  ▒ ▣  ▒       │ ░░░                     │
   x= 0.0  │ ░░░ │ ▒  ▣  ▒  ▣  ▒   ▣  ▒       │ ░░░  ▣干扰容器（空）     │ 现 region 中心 [0,0]
   x=-0.1  │ ░░░ │ ▒ ▣  ▒  ▣   ▒  ▣   ▒       │ ░░░                     │ 半边长 0.2、min_gap 0.04
   x=-0.2  │ ░░░ └────────────────────────────┘ ░░░                     │
   x=-0.3  │ ░░░       ▣干扰容器（含 cube）    ░░░                       │
   x=-0.45 │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ 外环下界 0.2675
   ░ 外环 = max(|x|,|y|) ∈ [0.2675, 0.45]；下界 = 0.20 + 容器半廓 0.0275 + min_gap 0.04
   实测：外环饱和 37.7 个，请求 2~6 个 100% 放下；容器在 256×256 画面里约 10 px
   干扰容器 **不进 spawned_bins**、**不用 bin_<i> 命名** ⇒ 天然不被选作交换搭档、不进揭示动画
```

#### PickHighlight：clutter 8~10 块 + 高亮 5~7 块

```text
                 -0.3   -0.2   -0.1    0.0   +0.1   +0.2
   x=+0.1  │  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒                  │  区域与间距不动（B5 选降 spawn）
   x= 0.0  │  ▒  ⊙ ⊙   ●  ⊙ ●    ⊙ ⊙  ●  ▒                    │  ⊙ = 高亮目标（5~7）
   x=-0.1  │  ▒    ●  ⊙    ●  ⊙     ●   ▒                     │  ● = 非目标
   x=-0.2  │  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  ⊕ 按钮          │
   ⚠ 高亮是方块**正下方**的白色圆盘，disk_radius 0.05 ⇒ 直径 0.10 m = 方块边长 2.5 倍
      而典型中心距只有 0.06~0.08 m ⇒ 3 块时就可能相切，5~7 块必然连成一片：

        现在（3 块）        xhard（5~7 块）
         ◯ ◯  ◯             ◯◯◯◯◯◯◯     ← 白盘糊成一片，看不出"哪几块被高亮"
        （已可能相切）        （必然重叠）
      ⇒ C3 已同意：缩小 disk_radius 或改用同心环
```

#### VideoRepick：三组锚点 → clutter

```text
   medium（派生基准，不动）                    xhard（clutter）
        -0.1   0.0   +0.1                        -0.3  -0.2  -0.1   0.0  +0.1
   +0.15│        ●  ← 锚点 3                +0.1 │ ░░░░░░░░░░░░░░░░░░░░░░░░░ │
   +0.05│   ●       ← 锚点 2                 0.0 │ ░ ● ●  ●  ● ●   ● ● ░     │
    0.0 │      ⊕按钮                       -0.1 │ ░  ●  ●  ● ●  ●   ● ░     │
   -0.05│   ●       ← 锚点 1                -0.2 │ ░░░░░░░░░░░░░░░░░░░░░░░░░ │
        每块围绕自己的锚点，局部半边长 0.07        整片区域：中心 [-0.1,0] 半边长 [0.2,0.25]
   改动：放弃锚点结构改整片 clutter；swap [2,3] → [8,12]；num_repeats 1~3 → [4,6]；
         三块保持**同色**、只是色值任意（C2）
```

#### MoveCube：cube 与 peg 推向边角

```text
              -0.3   -0.2   -0.1    0.0   +0.1   +0.2   +0.3
   x=+0.1  │ ░░░                              ░░░                │
   x=+0.05 │ ░░░      ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒         ░░░                │ ▒ = goal 区（不动）
   x= 0.0  │ ░░░  ═══ ▒  goal 半边长 0.15 ▒   ░░░ ═══            │ ═ = peg（根点 x ∈ ±0.05）
   x=-0.05 │ ░░░      ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒         ░░░                │      y ∈ [±0.15, ±0.25]
   x=-0.1  │ ░░░ ●cube                   ●cube ░░░               │ ░ = corner_bias 把 cube/peg
            y=-0.25              y=0               y=+0.25        │      推向四角
   改动：cube 与 peg 各加 corner_bias ∈ [0,1]；peg yaw ±45° → **±180°**（按等价朝向归约避开 joint7 限位）
   demo 与 execution 两套布局**各抽一套、不可合并**
   ⚠ 避让列表里**没有 peg** ⇒ 大 yaw 的杆与 cube/goal 现在就可以重叠生成
```

#### InsertPeg：3 根杆 → 4 根，新杆贴近目标杆

```text
              -0.3   -0.2   -0.1    0.0   +0.1   +0.2   +0.3
   y=+0.3  │                                                      │ 杆 y ∈ [-0.3, +0.3]
   y=+0.15 │        ═══ peg_1                                     │
   y=+0.05 │                    ▓▓ 孔板 xy ±0.1                   │ 离孔板 > 0.06
   y= 0.0  │   ═══ peg_0（目标）  ▓▓ yaw 90°±20°                  │
   y=-0.05 │    ═ peg_3（新增，贴近 0.075 下限）                   │ 杆间 > 0.075（**不动**，B6）
   y=-0.15 │        ═══ peg_2                                     │
            x=-0.2                x=0                x=+0.2
   改动：peg_offsets 3 个 → 4 个；新杆在现判据允许内尽量贴近目标杆；yaw ±45° → ±180°
   ⚠ 整根杆跨度 0.1 m > 最小间距 0.075 m ⇒ **现在就可能穿插**，B6 已定不放松、也不修复
   ⚠ 4 根杆外观完全相同（head_rgb 循环外只抽一次）⇒ 靠 video demo 区分目标（C5 确认是既有设计）
```

#### 布局**不变**的六个环境

| 环境 | 说明 |
|---|---|
| SwingXtimes | 方块区中心 `[-0.1,0]` 半边长 `0.25`、两圆盘 `[-0.1,∓0.2]` 半边长 `0.1` **全不动**；只加 3 个干扰块（容量宽松，3~12 块 100% 放下） |
| StopCube | 路线 `[0,-0.3]→[0,+0.3]` 绕目标旋转 ±30°、目标 xy ±0.1 **全不动**；只改速度档与停止序号 |
| VideoUnmaskSwap / ButtonUnmaskSwap | 容器锚点（三角/直线/四点，局部半边长 `0.07`）**不动**；只加外环干扰容器、改 swap 次数与窗口长度 |
| VideoPlaceButton / VideoPlaceOrder | 方块区、目标台、按钮、goal 区**全不动**；改的是"演示几个方块"与"演示完放哪"，属动作序列不属布局 |
| PatternLock | 5×5 网格、中心 `[-0.1,0]`、间距 `0.1` **不动**（B8 明确"不改布局"）；只把路径拉长 |
| RouteStick | 1×9 网格、中心 `[-0.1,0]`、间距 `0.07`、障碍柱位 1/3/5/7 **不动**（B9）；只把段数 L 拉长 |

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

### 3.2 新值规格由谁算出来：已定为「环境自己抽 + 导出」

**问题是什么。** 每局要用的具体值（这局 spawn 几块、各在哪个 xy、swap 哪两个、第几步交换……）
总得有人算出来。有两条路，**用户 2026-09-22 已选第 ① 条**：

| | **① 环境自己抽 + 导出（已选）** | ② 另写一套离线造值器（甲的做法） |
|---|---|---|
| 怎么做 | 把新值**范围**（如 `spawn 8~10`、`swap 8~12`）写进 `sampling_config` 传给环境，**环境按自己原有的抽样逻辑在新范围里抽**，抽完由 `SpecRecorder` 导出模式把结果记下来，写成 `specs.jsonl` | 单独写一个纯 CPU 程序，把十六个环境的取值逻辑**再实现一遍**，算出每局的值写进 jsonl，环境只负责读 |
| 取值逻辑有几份 | **一份**（就在环境里） | **两份**（环境里一份、造值器里一份） |
| 会不会和环境对不上 | 不会——规格的每个取值点就是环境跑出来的 | **会**。环境一改、造值器没跟上，产出的规格 `missing`/`unused` 立刻不为 0；甲只覆盖四个环境就写了一千多行 |
| 占不占 GPU | **占**。但只做 `gym.make → reset → 导出 → close`，**不建 h5、不录像、不 step** | 不占 |
| 复用现成骨架 | `scripts/injection/rollout/reset_check.py` 已经在做 make/reset/close，照搬即可 | 甲的 `candidates/specs.py`（但要从 4 个环境扩到 16 个） |

选 ① 的理由就是"取值逻辑只有一份"。V3 的红线 R6 之所以禁止继承甲的采样器，正是同一个道理。

⚠ **这条路有一个必须注意的点**：环境"按新范围抽"本身就是在跑新值，所以**抽签段的产物已经是新值局**；
冻结之后的实跑段是拿同一份规格**再跑一遍**。两次跑的随机种子相同、规格相同 ⇒ 理论上应逐位一致，
这正好就是 V2 `NEWVALUE_REPLAY` 的判据。换句话说**抽签段与实跑段互为对照**，不需要额外造对照组。

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
`identity` 块沿用官方身份体例 `(task, episode, seed, difficulty)`，其中 **`difficulty` 恒为 `"xhard"`**（口径 12）——
`--difficulty` 那个三位循环配额只管 easy/medium/hard，xhard 只经每条规格的 `difficulty` 字段显式进入。
**新值局不再绑定官方 metadata**：
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
| **V1** | **原值回归**：加了新值能力之后，原三档一个数都没改 | 重跑 V3 的 144 条子集（全在 easy/medium/hard），与 V3 留档的 B／C／D 产物逐位比。**口径 12 之后这条更强**：新值只落 xhard，原三档在结构上就不该有任何差异，任何非零差异都是明确的 bug | `NATIVE_REGRESSION=PASS compared=144 sha_equal=k field_mismatch=0` |
| **V0** | **原三档的定义没被动过**（静态，V1 的前置） | `git diff` 只看 `config_easy` / `config_medium` / `config_hard` 三个类属性与 `NATIVE_SAMPLING` 里被原三档消费的键，应全部无改动；三个新建分档的环境（A6）另按"三档同值"逐项核对 | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
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
| 3a | 按 2.0 的派生基准总表建 `xhard` 档：十三个新建、三个覆盖；`StopCube`/`MoveCube`/`InsertPeg` 先建分档机制（A6） | `NATIVE_DEFS_UNCHANGED`（V0） |
| 3b | 十六环境逐个在 xhard 档开新值（按第二节分组推进，每组先过 V0+V1 再进下一组） | 每组 `NATIVE_REGRESSION` 局部通过 |
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
| 步 3a | 十三个环境的 `config_xhard`（新建）＋ `StopCube` / `MoveCube` / `InsertPeg` 按 A6 建 `configs`（三档同值 + xhard）＋ 三个已有 xhard 按 A7 **直接覆盖** | 按 2.0 的派生基准总表建档：从 hard（VideoRepick 从 medium）拷一份再改新值 | **原三档定义逐字不变**（V0 判据） |
| 步 3a 连带 | `tests/lightweight/test_swap_schedule_generic.py`（`test_xhard_四五次首尾相接每段五十帧` 锁 4/5 次；另一处遍历 `config_xhard`）、`test_episode_action_sampling.py`（xhard 参数化，注释锁"Unmask 4、Repick 3"）、`test_window_timeline.py`（`test_unmask_xhard_四五次调度` 与 GROUPS 断言） | 旧 xhard 作废后这些断言必然失配，**须同步改成 V4 新值的语义**，不得为了让它们过而保留旧值 | 原三档相关断言不动 |
| 步 3a 不动 | `tests/_shared/contract_builder_fixture.py` 的 `XHARD_GROUPS` / `GROUPS_V3` 与 xhard 文案、`test_injection_delivery.py` 的 RouteStick xhard 配额 | 这些属**甲的契约链路**，甲已废弃但代码与产物按 N6 原样保留 ⇒ **不改** | — |
| 步 3 | `BinFill.py::_resolve_sampling_config` / `_load_scene` / `_initialize_episode` | 放开 `layout_mode` 守卫并**新写 clutter 摆放**（现不存在）；`min_gap` 从调用点字面量外提；修 D1 的静默截断＋`IndexError` | `native_dynamic` 分支与原三档逐字不变 |
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
| V0 `NATIVE_DEFS_UNCHANGED` | 无（静态检查，可在每步收尾跑） | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| V1 `NATIVE_REGRESSION` | V3 的 144 条基线产物可读；V0 已过 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=k field_mismatch=0` |
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
