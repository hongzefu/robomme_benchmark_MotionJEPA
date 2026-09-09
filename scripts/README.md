# scripts/ 说明（newtask-v2）

本目录是数据生成侧的全部入口。

`BinFill` / `RouteStick` / `VideoUnmaskSwap` / `VideoRepick` 这四个任务**原来就在用**的
位置分布与参数候选，过去散落在源码里当字面量；现在被提取成一份冻结的显式配置
[configs/newtask-v2/native_sampling.json](configs/newtask-v2/native_sampling.json)，
可以检查、可以显式传入。**取值、抽样方式与整条执行链保持原版行为不变**，这一点用逐位对拍
验证过（第二节）。

---

## 一、固定了哪些

### 1.1 十二份难度字典（四任务 × 三难度）

| 任务 | easy | medium | hard |
| --- | --- | --- | --- |
| `BinFill` | `color=1`<br>`spawn_cubes=[4,6]`<br>`put_in_color=[1,1]`<br>`put_in_numbers=[1,3]` | `color=2`<br>`[8,10]`<br>`[1,2]`<br>`[2,4]` | `color=3`<br>`[10,12]`<br>`[2,3]`<br>`[3,5]` |
| `RouteStick` | `length=[2,3]`<br>`backtrack=False` | `[4,5]`<br>`False` | `[4,7]`<br>`True` |
| `VideoUnmaskSwap` | `bin=3`<br>`swap 1–2`<br>`pick 1–2` | `bin=4`<br>`swap 1–2`<br>`pick 1–1` | `bin=4`<br>`swap 2–3`<br>`pick 2–2` |
| `VideoRepick` | `cube=3`<br>`swap 1–2` | `cube=3`<br>`swap 2–3` | `swap 0–0`<br>（`cluster`/`swap` 是死字段，源码从不读它们） |

区间语义按来源区分：写在难度字典里的 `[min,max]` 由 `torch.randint(low, high+1)` 消费，
**含两端**；直接写在源码里的 `torch.randint(a, b)` 是半开区间，不含 `b`。

### 1.2 构造期的其它抽样常量

| 任务 | 项 | 原值 |
| --- | --- | --- |
| `BinFill` | `dynamic` | `randint(0,2)` 转 bool，是 generator 播种后的**第一次**抽样 |
| `RouteStick` | 难度兜底档 | `easy`（对应 `self.configs.get(..., self.config_easy)`） |
| `VideoRepick` | `num_repeats` | `randint(1,4)`（半开，即 1/2/3） |
| `VideoRepick` | hard 生成轮数 | `5` 轮，每轮红蓝绿各一块 = 15 块 |

### 1.3 位置输入

| 任务／对象 | 固定的项 |
| --- | --- |
| `BinFill` 按钮 | 中心 `(-0.2, 0)`、随机范围 `(0.1, 0.4)`、缩放 `1.5` |
| `BinFill` 孔板 | 基准位 `[0.15, 0, 0]`；三组偏移运算元 x `u×0.2−0.2`、y `u×0.4−0.2`、yaw `u×40−20`（度）；板边长 `0.1`、孔边长 `0.08`、厚 `0.05` |
| `BinFill` 方块 | 区域中心 `[-0.1, 0]`、半边长 `[0.2, 0.25]`、随机 yaw、`include_existing=False`、`include_goal=False` |
| `RouteStick` 布局 | 网格中心 `[-0.1, 0]`、行列间距各 `0.07`、整体旋转 `u×60−30`（度）、障碍柱半径 `0.015` / 高 `0.1` |
| `VideoUnmaskSwap` 容器 | 三组锚点（三角 / 直线 / 四点）、锚点二选一的 `randint(0,2)`、整体旋转 `(0,180)` **弧度**、区域半边长 `0.07`、容器自转 `u×90`（度） |
| `VideoRepick` 按钮 | 中心 `(-0.2, 0)`、随机范围 `(0.1, 0.1)`、缩放 `1.5` |
| `VideoRepick` easy/medium 方块 | 同上三组锚点与二选一抽样、整体旋转 `(0,180)` 弧度、区域半边长 `0.07`、随机 yaw、`include_existing=True`、`include_goal=True` |
| `VideoRepick` hard 方块 | 区域中心 `[-0.1, 0]`、半边长 `[0.2, 0.25]`、随机 yaw、两个避让开关均 `False` |

三组容器/方块锚点的实际坐标（按原顺序，不排序、不归一化、不平移）：

```text
三角  [[-0.05, -0.1], [-0.05, 0.1], [0.1, 0]]
直线  [[0, -0.15],    [0, 0.15],    [0, 0]]
四点  [[-0.05, -0.1], [-0.05, 0.1], [0.1, 0.1], [0.1, -0.1]]
```

### 1.4 **没有**开放为可配的东西

物体尺寸、材质、碰撞几何、相机、速度、交换时序、失败恢复、成功阈值都属于原实现，没有动。

`cube_half_size`（= `0.02`）是个特例：它同时是四任务 `min_gap` 的实际值、容器半边长的
收缩量、方块可行域的收缩量 —— 不是纯尺寸参数。它被**冻结为派生输入记进快照**，
但**不开放为可配**。

源码里的若干旧问题（RouteStick 结尾无条件覆盖难度、创建后从未使用的局部 generator、
无调用者的死代码、`VideoRepick` 永不命中的 `region4` 分支、与实际不符的注释等）
按计划**原样保留、没有顺手修**，只在快照与计划文档里记录。

### 1.5 「固定」是怎么保证的

取值有两个落点，但**不是两套真值**：

- `configs/newtask-v2/native_sampling.json` —— 冻结快照，也是 `--sampling-config` 的输入；
- 每个任务模块顶层的 `NATIVE_SAMPLING` —— 既是**不传配置时的运行默认值**，
  也是快照的提取目标。难度字典则只在类属性 `config_easy/medium/hard` 一处。

三道闸拦住漂移：

1. **结构与类型校验** —— 字段缺失、多出未知字段、类型或数组长度不对，直接报错；
2. **来源指纹** —— 生成时核对七份源码文件的 SHA-256，改过源码就必须重新导出快照；
3. **表达形式约束** —— JSON 里只存源码里真实出现的运算元（`scale` / `subtract` /
   `base_position`），**不许**折算成 `[min,max]`：`0.15 + (u×0.2 − 0.2)` 与
   `−0.05 + u×0.2` 数学等价，但 float64 位模式不同，逐位对拍会挂。

配置值一律以 Python 标量参与运算，不要包成 `torch.tensor` —— 那会把下游的 float32 路径
提升成 float64。

初版只支持原来就存在的表达形式（区间、固定值、原抽取方式），**不支持**新增非连续候选、
权重或新拓扑。

---

## 二、对拍测试了哪些

### 2.1 三路

| 路 | 是什么 | 源码 |
| --- | --- | --- |
| **A** | 固定原版，跑两次（A1/A2）做重复性校准 | 基线提交 `94449db` 的 detached worktree |
| **B** | 新版**不传**配置 | 当前工作树 |
| **C** | 新版**显式传入**原值配置 | 当前工作树 |

逐格比较 `A1↔A2`、`A1↔B`、`A1↔C`、`B↔C` 四对。同一格固定任务、难度、episode、seed、
`attempt=0`、GPU 与全部参数，四路独立进程运行。

**比较口径：全字段、逐元素、浮点按位模式、不设容差。**

### 2.2 比了四类东西

| 类别 | 比较对象 |
| --- | --- |
| HDF5 落盘产物 | 遍历实际落盘树，group / dataset / attribute 全集、dtype、shape、字符串编码与逐元素内容；`obs`（RGB、深度、关节、夹爪、末端、外参）、`action`、`info`、`setup` 一个不落 |
| 随机流 | 每次 `torch.rand/randint/randperm` 的调用序号、上下界、shape、所属随机源与状态散列、抽样结果；覆盖任务级 generator（局部与实例）、全局 numpy 流（`VideoRepick` 的 `np.random.seed`）、全局 torch 流。拒绝采样保留**全部尝试**，不只记成功样本 |
| 内部状态与物体事件 | 构造期与两次 `_initialize_episode` 的边界快照（任务参数、全部 actor 位姿与速度、`task_list` 顺序）；逐物理步的任务状态与位姿；抬起/回落、交换、高亮、显隐等事件的身份、类型、发生步与前后值 |
| 关键帧图像 | 首末帧、子目标边界、演示切换、完成标志变化处的正面与腕部原图，三路取并集并加前后邻帧 |

### 2.3 覆盖了 15 格

| 任务 | 格 |
| --- | --- |
| `BinFill` | easy / medium / hard × `dynamic=True` / `dynamic=False`，共 6 格 |
| `RouteStick` | easy / medium / hard，3 格 |
| `VideoUnmaskSwap` | easy / medium / hard，3 格 |
| `VideoRepick` | easy / medium / hard（hard 覆盖五轮循环共 15 块），3 格 |

单格规模：HDF5 对象 5008–23583 个、随机调用 11–131 次、事件 748–17014 条、
逐步状态 652–1886 条。

### 2.4 结论

| 项目 | 结果 |
| --- | --- |
| HDF5 全字段 | **15 格通过，差异 0**；合并产物（`record_dataset_<Task>.h5`）三路也是 0 差异 |
| 随机流 | 15 格通过 |
| 内部状态与事件 | 15 格通过 |
| 同一 worker 连续生成互不污染 | 两路通过（甲→乙→甲，逐局与独立运行 0 差异） |
| 关键帧目视 | **9 格通过、6 格待目视**；354 张关键帧机检全部一致（差分为 0、逐帧散列三路相同） |
| 其余 12 任务生成能力 | `--env all` 加配置，16/16 成功 |
| attempt 重试分支 | 三路的失败分类与第二次 seed 完全一致，重试产物 0 差异 |

另有一条独立于生成的证据：`--check-config --source-ref 94449db` 用另一套提取器，
从**改造之前的源码**里还原 61 项运算元并与快照逐项比对 —— 这是「接入过程一个原值都没改」
的自动化证明，不靠人眼比 diff。

15 格的 30 次原版运行 `rrt_fallback_count` 全为 0，即全部落在「原版逐位可复现」的
适用范围内（screw→RRT\* 回退走 mplib/OMPL，种子接口未暴露且有 1 秒墙钟预算，
触发回退的局本就不具备逐位可复现性）。

### 2.5 没覆盖到的

- `BinFill` 六格的关键帧**目视**：138 张只人工看了 1 张，其余只有机检结论；
- RRT\* 回退局一次都没触发，因此「触发回退怎么办」的退出路径未被启用也未验证；
- 清理旧目录后只重跑了每任务 easy 一格做复验，其余 11 格沿用清理前证据；
- 合并产物比较只在 1 格上做过。

完整报告、逐格数据与轻量证据见
[docs/validation/newtask-v2/](../docs/validation/newtask-v2/README.md)；
交付清单与未覆盖项全表见
[DELIVERY.md](../docs/validation/newtask-v2/DELIVERY.md)。

---

## 三、几个脚本入口分别做什么用

| 文件 | 干什么 |
| --- | --- |
| `generate_dataset_newseed.py` | **主入口**，三种模式：生成数据集 / 核对导出原值快照 / 按需合并 |
| `seed_layout.py` | seed 公式、难度循环、16 任务规范序。纯标准库，被主入口导入 |
| `dataset_replay.py` | 回放已生成的数据集（未改动） |
| `evaluation.py` | 评估示例（未改动） |
| `run_example.py` | 单环境运行示例（未改动） |

主入口的三种模式互斥，靠参数区分；命令都在仓库根目录执行。

### 3.1 生成数据集（默认模式）

```bash
# 最小例子：BinFill 一局
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/binfill-smoke \
  --env BinFill --episodes 1 --workers 1 --gpus 0 \
  --layout train --difficulty 100 --max-attempts 1

# 全量例子：16 任务 × 100 局，双卡
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/full-16x100 \
  --env all --episodes 100 --workers 20 --gpus 0,1 \
  --layout train --difficulty 211

# 显式传入原值配置（结果与不传时逐位相同，已验证）
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/binfill-explicit \
  --env BinFill --episodes 1 --workers 1 --gpus 0 --difficulty 100 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

配置只覆盖那四个任务；`--env all` 时其余 12 个任务照原默认值生成，不报错。

**常用参数**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--output-dir` | 必填 | 输出目录，**必须在仓库内** |
| `--env` | `all` | `all` 或逗号分隔的任务名 |
| `--episodes` / `--episode-start` | `100` / `0` | 条数与起始 episode 号（接续生成用后者） |
| `--workers` / `--gpus` | `20` / `0` | 总 worker 数；`--gpus 0,1` 为每卡一个进程池 |
| `--layout` | `train` | seed 布局代：`train` / `test` / `val` / `heldout` |
| `--difficulty` | `211` | **三位数字的难度配额**，见下 |
| `--max-attempts` | `100` | 单个 episode 最多尝试几次 |
| `--max-tasks-per-child` | `8` | 每个池进程跑多少 job 后回收 |
| `--sampling-config` | 不传 | 显式传入四任务的采样输入 |

> ⚠️ `--difficulty` 是 easy/medium/hard 的**循环配额**，不是难度值。
> `211` = 每 4 局里 2 easy + 1 medium + 1 hard；`100` = 全 easy，`010` = 全 medium，
> `001` = 全 hard。它不是「难度 100」。

**seed 不读表，由公式现算**（`seed_layout.py`）：

```text
seed = offset + env_code × env_block + episode × 100 + attempt
```

`env_code` 是任务在 16 任务规范序里的 1-indexed 位置：
`BinFill=4`、`VideoUnmaskSwap=5`、`VideoRepick=9`、`RouteStick=16`。
train 布局是 `offset=0, env_block=1000`，所以 BinFill 的 episode 0 首次尝试是 `4000`，
失败重试变 `4001`。难度只由 `--difficulty` 决定，**不进入 seed**。

**输出目录长这样：**

```text
<--output-dir>/
├── hdf5_files/
│   └── BinFill_ep0_seed4000.h5              逐 episode 轨迹，文件名含 任务_ep号_seed
├── videos/
│   └── BinFill_ep0_seed4000_<难度与目标描述>.mp4
├── episode_results.jsonl                    边跑边写，一行一次 attempt
├── record_dataset_BinFill_metadata.json     每任务一份：episode / seed / difficulty
├── run_parameters.json                      本次运行的全部参数
├── run_summary.json                         成功数、放弃数、耗时、吞吐、峰值内存
└── sampling_config_used.json                仅在传了 --sampling-config 时才有
```

- 文件名天然唯一（含任务、episode、seed），多 worker 共享同一输出根不会打架。
- `episode_results.jsonl` 每行含 `ok` / `attempt` / `seed` / `failure_class` / `error_type` /
  各阶段耗时 / 峰值 RSS / 绑到哪张卡，中途崩溃不丢已完成的部分。
- 失败的 attempt 不留空 h5（会被删掉），但 `FAILED_` 视频保留作为失败演进的证据。
- 体量：单局 BinFill 约 350 MB（h5）+ 11 MB（视频）。`artifacts/` 已整体 gitignore。

### 3.2 核对／导出原值快照（`--extract-config`）

只读源码 AST，**不加载仿真、不占 GPU、不采样**。

```bash
# 只核对：快照必须与当前工作树源码逐项一致
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config

# 再加一层：与固定基线提交的原版取值对照（第二节末尾说的那 61 项）
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8

# 不带 --check-config 就是重新导出快照（改过源码之后必须做）
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json
```

### 3.3 按需合并（`--merge-only`）

生成期**不会**自动合并（避免体量翻倍，也让单条失败不牵连其它产物）。需要每任务一个文件时
单独跑：

```bash
uv run --no-sync python scripts/generate_dataset_newseed.py --merge-only \
  --input-dir artifacts/generated/binfill-smoke \
  --output-dir artifacts/generated/binfill-merged \
  --env BinFill
```

产物是 `record_dataset_<Task>.h5`。`--output-dir` 不给时默认写回 `--input-dir`；
加 `--delete-source` 会在合并成功后删掉逐 episode 源文件（默认保留；合并期间两份并存，
需要双倍空间）。源文件按生成期写出的 metadata 逐条定位、不 glob，所以目录里混有失败残留
也不会被误吸。
