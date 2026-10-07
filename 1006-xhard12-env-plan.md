# 1006-xhard12-env-plan.md — 在原 16 任务 hard 母样本上派生 xhard 档：子类继承 + 独立包 + 生成器一个开关

> **权威与授权**：只规划不实施。开工须用户明确、无歧义地说「开工」（`AGENTS.md` 第 2 条）；计划获批、取值获批都不是开工令。本版 2026-10-06（2.32）把前两版「接口方案」（2.30.x）与「上次训练参照与逐任务高层方案」（2.31）合成一份完整计划；上次训练怎么做的、官方 hard 档统计、16 任务源码核查全部移到留档 [`1006-xhard12-prev-training-and-task-plan.md`](1006-xhard12-prev-training-and-task-plan.md)，本文只引用、不复述。
> **代码锚点**：`deb938e0`（2.31）。工作副本 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `newtask-v3-MotionJepa1006`，提交编号 `2.<小版本>`。生成代码起点 `3a5951a8`（2.24），源码核查锚点 `13905997`（2.25）。
> **外部锚点**：ManiSkill `07be6fbc66350ddca200abfb0a11b692f078f7fd`（`pyproject.toml` git rev，不改）；`.venv` gymnasium 0.29.1、torch 2.9.1；上次训练 run `wan-full1600-filter2-b176x4-72ep-a`（留档一节）。
> **事实核查**：2026-10-06 三个只读子代理逐文件核实了 ManiSkill `spec` 挂载与 reset 生命周期、生成器锚点与导入路径、11 个任务的覆写锚点（留档 5.0–5.2 节）；本文第二部分的代码锚点以此为准。所有 T、窗口数仍是线性外推 [估算]，实跑后要重算。

# 第一部分（给人看）

## 一、要做什么与全部运行一览

**一句话**：不改原 16 个任务文件，在新包 `src/robomme_xhard/` 里给 11 个任务各写一个子类，只换 `configs["hard"]` 里的一两个数（或重写一个方法）；生成器加一个 `--xhard` 开关，用 train metadata 里 hard 记录的**原 seed** 把这些子类跑一遍，录像器照原任务名录制。目标是每条 episode 更长（T 约 900、stride-16 窗口约 50–60），且 8 帧等距采样必然漏掉至少一类 subgoal。

```
 开工 ─┬─ 步骤 1  前置验证（6 项，全部只读或 ≤5 分钟 smoke）
       ├─ 步骤 2  主会话写新包骨架 S0：base.py（XHardMixin）、jobs.py、envs/__init__.py
       ├─ 步骤 3  4 个写入型子代理并行：S1 换字典组 6 任务 ｜ S2 重写方法组 5 任务 ｜ S3 生成器开关 ｜ S4 轻量测试
       ├─ 步骤 4  逐个合并 S1 → S2 → S3 → S4，每个两次审查、push 一次
       ├─ 步骤 5  每任务 3 个 hard seed smoke（单 worker、单卡），出 XHARD_LENGTH 对账表
       ├─ 步骤 6  用户审阅取值与对账表 → 再说一次「开工」→ 全量 425 条（tmux xh-full，单卡 32 worker）
       └─ 步骤 7  数轴图 + docs/xhard-doc 留档 + commit + push
 数据链路：--xhard xhard1 → worker 内 import robomme_xhard（子类注册）→ jobs_from_metadata 读 train json 的 hard 记录
           → gym.make("BinFillXHard1", seed=4301, difficulty="hard") → 子类只换 configs["hard"] 的一两个数
           → XHardMixin 把 unwrapped.spec.id 改回 "BinFill" → RobommeRecordWrapper(env_id="BinFill") 照常录制
```

| 范围 | 任务 | 条数（hard 母样本） | 改法 |
|---|---|---:|---|
| 纳入·换字典 | PickXtimes、SwingXtimes、PickHighlight、PatternLock、RouteStick、BinFill | 6 × 25 | 子类重写 `configs`（BinFill 另加 `_load_scene` 后置校验） |
| 纳入·重写一个方法 | VideoUnmaskSwap、ButtonUnmaskSwap（各 100）、StopCube、VideoRepick、VideoPlaceOrder（各 25） | 275 | 换字典 + 重写 `_refresh_swap_schedule`；重写 `_initialize_episode`+`step()`；`__init__` 后改写 `num_repeats`；重写 `_load_scene` |
| 不纳入 | ButtonUnmask、VideoUnmask（`pick` 只是 `>1` 开关）；VideoPlaceButton（无数值型次数键）；InsertPeg、MoveCube（不读 difficulty） | — | 加难度要新增逻辑，不是「少改参数」 |
| **合计** | **11 个任务** | **425** | |

**已定口径（用户原话，2026-10-06）**：①「沿用 Hard 的所有配置，只在一两个参数上改动，比如 pick 5 次变成 pick 7 次」；②「seed 先用现有的，直接拿 `src/robomme/env_metadata/train` 里已经生成过原版 hard 的那组 seed」「新 seed 的事以后再说」；③「新增部分用独立的 ENV 文件表示」「所有改动只限于生成器 `generate_dataset_newseed.py` 这一个文件和新增的那些文件」「把所有改的部分全部归档在一起，放在 `src` 里面」；④「不再把 BinFill 做成带 video 的任务」；⑤ 长度对齐 newtask-v2 xhard（T≈900、50–60 窗），token 落实为 stride-16 窗口数；⑥ 只硬性要求 8 帧有 subgoal 级遗漏，32 帧「尽量」；⑦ 只用现有 hard seed、本轮接受总量缺口（约为上次 stride-1 chunk 的四成）；⑧ 纳入「换字典 + 重写方法」共 11 个任务；⑨「积极调用一些子代理可以搞清楚一些事实」。2026-10-06 子代理核实后的两处修正：`pyproject.toml` **不改**（editable `.pth` 已把整个 `src/` 加进 `sys.path`，见二节）；两个 Swap 任务 swap≥4 必须重写 `_refresh_swap_schedule`，已不是纯改参数，列入「重写一个方法」组。

## 二、原侧是什么、我们改在哪

**生成器现状与开关后的变化**（`scripts/data-generation-newSeed/generate_dataset_newseed.py`，锚点已核实）：

| 步 | 函数 | 现在做什么 | 传 `--xhard xhard1` 后 |
|---|---|---|---|
| 0 | `main` / `_args` | 解析 `--env --episodes --difficulty --layout --episode-start --max-attempts --workers --gpus` | 多解析 `--xhard {xhard1,xhard2}` 与 `--source-split`（默认 train）；传了 `--xhard` 就禁止 `--difficulty --layout --episodes --episode-start --max-attempts`（公式 seed 那套与 json seed 混用说不清） |
| 1 | `generate_dataset_newseed` | 列表推导造 `EpisodeJob`（seed = `layout.seed(task, ep, 0)`，难度按 `ep % 4` 循环），写 `run_parameters.json` | 改调 `robomme_xhard.jobs_from_metadata(tasks, split, xhard, output_root, repo_root)`：读 `src/robomme/env_metadata/<split>/record_dataset_<Task>_metadata.json`，只取 `difficulty=="hard"` 的记录，task/episode/seed 原样抄、difficulty 固定 hard、`xhard` 字段填档名；跳过「不越过下一代布局 offset」护栏（只对公式 seed 有意义） |
| 2 | `_run_jobs` | 失败分类 `task`/`code`/`infra`；`task` 失败 `bump` 到 `attempt+1` 的新 seed；池损坏时 in-flight job 也 `bump` 后 `appendleft` | `job.xhard` 非空时**两处都不换 seed**：`task` 失败直接记 exhausted；池损坏时按原 job 退回队列（attempt 固定 0） |
| 3 | `_pool_init` / `_worker` | 绑卡 `CUDA_VISIBLE_DEVICES` → `import torch` → `import robomme.robomme_env`（16 个 `@register_env` 执行）→ `gym.make(job.task, **kwargs)` → `RobommeRecordWrapper(..., env_id=job.task, ...)` → reset → planner → `_execute_tasks` → close | 在 `import robomme.robomme_env` 之后加一行 `import robomme_xhard`（**不能放文件顶部**：顶层 import 会在绑卡前拉起 torch/mani_skill）；`gym.make(robomme_xhard.make_name(job), **kwargs)`，kwargs 一个不改；`env_id=job.task` 仍是原名，planner 选择仍按 `job.task in STICK_TASKS` |
| 4 | `_write_metadata` / summary | 写 `record_dataset_<task>_metadata.json`（task/episode/seed/difficulty）与 `run_summary.json` | 不变；`parameters` 多记 `xhard`、`source_split`、源 json 路径与母样本条数 |

**为什么子类就够**：13 个任务把三档参数写在类属性 `config_easy/medium/hard` 与 `configs = {'hard': config_hard, ...}` 里，运行时统一 `self.configs[self.difficulty][...]` 读；子类重新定义同名类属性就整体替换，父类 `_load_scene`/`_initialize_episode`/`step`/`evaluate` 原样继承。写法 `configs = {**父.configs, "hard": {**父.config_hard, "pickup": 5}}`，easy/medium 原样保留（RouteStick `_load_scene` 用 `configs.get(difficulty, config_easy)` 回退，所以三档都要在）。`normalize_robomme_difficulty` 只认 easy/medium/hard，新档仍传 `difficulty="hard"`。

**为什么要 `XHardMixin.spec` 把 id 改回原名**：四个 wrapper 共 10 处读 `unwrapped.spec.id`——判 stick 任务选 planner（`MultiStepDemonstrationWrapper::_get_planner`/`step`、`DemonstrationWrapper::reset`）、取语言目标（`DemonstrationWrapper::_augment_obs_and_info` → `task_goal.py::get_language_goal` 按 `env == "BinFill"` 字符串分支）、取 VQA 选项（`RecordWrapper::_resolve_choice_label`/`close` → `vqa_options.py` 查表）、判无夹爪（`EndeffectorDemonstrationWrapper::step`）。名字对不上时这两个函数**静默返回空列表**，不报错。gymnasium `make` 在实例化之后、套任何 wrapper 之前执行 `env.unwrapped.spec = EnvSpec(...)`，`EnvSpec` 是 dataclass，`BaseEnv` 自己不写 `spec`——所以子类把 `spec` 定义成带 setter 的 property，在 setter 里 `dataclasses.replace(value, id=原名)` 即可，四个 wrapper 一字不改（受保护，P1）。

## 三、逐任务改什么

T 与窗口数按官方 hard 中位加每个子任务平均段长线性外推（留档 4.2、4.3 节，公式见第二部分八节）；Δ8 = (T−1)/7；「母布局」指同一 seed 下场景是否逐项不变。

| 任务 | 改的键 | hard → xhard | 预计 T（中位） | 预计窗 | Δ8 对最短执行段 | 母布局 | 改法 |
|---|---|---|---|---|---|---|---|
| BinFill | `put_in_numbers` | [3,5] → [5,6] | 868 → 约 1140 | 53 → 约 69 | 162 > 71（投箱），必漏 | 变（共用 generator） | 换字典 + `_load_scene` 后置校验 |
| PickXtimes | `number_min/max` | 4/5 → 6/7 | 812 → 约 1120 | 49 → 约 68 | 160 > 70（放到 target），必漏 | 不变 | 换字典 |
| SwingXtimes | `number_min/max` | 3/3 → 7/8 | 488 → 约 840 | 29 → 约 50 | 120 > 40（摆到一侧），必漏 | 不变 | 换字典 |
| PickHighlight | `pickup` | 3 → 5 | 539 → 约 850 | 32 → 约 51 | 121 > 55（放回桌面），必漏 | 不变（目标是原排列前缀） | 换字典 |
| PatternLock | `length` | [4,8] → [10,14] | 324 → 约 810（666–960） | 18 → 约 49 | 116 > 25–40（每步 move），必漏 | 网格不变，路径变 | 换字典；接受率待验 |
| RouteStick | `length` | [4,7] → [8,10] | 500 → 800–1000 | 28 → 46–60 | 114–143 > 50（每步），必漏 | 障碍不变，路线前缀保留，方向变 | 换字典；与 newtask-v2 xhard 相同 |
| VideoUnmaskSwap | `swap_min/max` | [2,3] → [4,5] | 457 → 约 560 | 26 → 约 31 | 80 > 49（放下）、> 50（每次 swap），漏 | 不变 | 换字典 **+** 重写 `_refresh_swap_schedule` |
| ButtonUnmaskSwap | `swap_min/max` | [2,3] → [4,5] | 461 → 约 520（待验） | 27 → 约 31 | 74 > 46（放下），漏 | 不变 | 同上；交换结束是否晚于按钮完成待验 |
| StopCube | `stop_time`、`move_interval` | [2,5] → [8,10]；间隔 {60,80,120} 随机 → 钉 120 | 309 → 900–1140 | 18 → 54–69 | 128–163 > 100（remain static），必漏 | 不变（随机消耗量不变） | 重写 `_initialize_episode` 与 `step()` |
| VideoRepick | `num_repeats` | [1,3] → [4,5] | 543 → 约 935 | 31 → 约 56 | 134 > 58（放下），必漏 | 不变 | `__init__` 调 super 后改写 `num_repeats` |
| VideoPlaceOrder | 放置数 `num_targets_to_pick` | [2,4] → 固定 4 | 1115 → 约 1300 | 67 → 约 78 | 185 > 全部，必漏 | 目标子集不变，正确序号与按钮插入位变 | 重写 `_load_scene`；**改动弱，可剔除** |

- **BinFill 与 PickXtimes 本来就在 900 附近**，再加次数到 1100 以上、约 70 窗，超出 50–60 目标。这是「必须比 hard 更难」和「长度对齐 900」之间的取舍，选前者，且区间下沿取 hard 上沿（和 newtask-v2 的 hard 4–7 → xhard 8–10 一致）；要压回 900 只能让区间和 hard 重叠，那就不像新档。
- **两个 Swap 任务天生短**，加到 5 次 swap 也只有约 560 帧、31 窗，和 newtask-v2 的 VideoUnmaskSwap xhard 一样短；它们各有 100 条 hard seed，是总量主力，长度上不去是结构问题。
- **StopCube 改两个量**：只改 `stop_time` 时，`move_interval` 抽到 60 的三分之一 episode 只有 450–570 帧，Δ8 小于 100 帧的 static 段，8 帧漏不掉；钉住 120 才满足硬性判据。两处都在重写的同一个方法里。
- **VideoPlaceOrder 改动很弱**（固定 4 本来就在 hard 区间里），上限被目标点数 4 卡死；另有 `current_task_specialflag(s)` 命名不一致的源码缺陷待核（前置验证第 6 项）。实施时可剔除，剔除后总量 400 条。
- **预计成功率低于 hard**：原 hard seed 里 BinFill 11 条、VideoPlaceOrder 12 条、SwingXtimes 5 条、VideoRepick 6 条、PatternLock 1 条是重试后才成功的；xhard 不换 seed，这些任务更容易失败，失败即缺条、不补。

| 任务 | 条数 | 预计 T | 预计帧数 | 预计 stride-16 窗 |
|---|---:|---:|---:|---:|
| BinFill / PickXtimes / SwingXtimes / PickHighlight / PatternLock / RouteStick | 25 × 6 | 1140 / 1120 / 840 / 850 / 810 / 900 | 141,500 | 8,525 |
| VideoUnmaskSwap / ButtonUnmaskSwap | 100 × 2 | 560 / 520 | 108,000 | 6,200 |
| StopCube / VideoRepick / VideoPlaceOrder | 25 × 3 | 1020 / 935 / 1300 | 81,375 | 4,850 |
| **合计** | **425** | | **约 33.1 万** | **约 19,600** |

对照上次训练：stride-1 chunk 约 31 万（上次 796,001，约四成）；stride-16 窗约 1.96 万（上次 69,716）。缺口已按口径 ⑦ 接受，补齐路径是 9 个 25 条的任务各加约 75 条新 seed，另议。

## 四、验收

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 身份牌改回原名 | `gym.make("PickHighlightXHard1", ...)` 后断言 `unwrapped.spec.id == "PickHighlight"`、外层 `spec.id` 同、`spec.entry_point` 不变（需渲染栈，主检出跑） | 四个 wrapper 的 stick/语言/VQA/无夹爪分支全按原任务走 | `XHARD_SPEC=PASS tasks=11 id_mismatch=0 entry_point_changed=0` |
| 子类只改目标键 | 对 11 个子类比 `configs` 与父类：easy/medium 逐键相等，hard 只有表三的键不同 | 「沿用 Hard 全部配置只改一两个参数」字面成立 | `XHARD_CONFIGS=PASS tasks=11 unexpected_diff=0` |
| 卡片来自 train hard 记录 | `jobs_from_metadata` 结果条数 = 各任务 hard 条数（25/100），seed 与 json 逐条相等，attempt 全 0，difficulty 全 hard | 口径 ② 成立 | `XHARD_JOBS=PASS source=train tasks=11 jobs=425 seed_unchanged=425` |
| 原路径逐字节不变 | 不传 `--xhard` 时：`_args` 解析结果、造出的 jobs、`make_name(job)` 与 `BASE` 版本逐项相等；互斥参数组合报错 | 开关关闭态零行为变化 | `XHARD_BASELINE_EQ=PASS jobs_diff=0 names_diff=0 mutex_errors=5` |
| 受保护目录零 diff | `git diff --quiet <BASE> HEAD -- src/robomme/ pyproject.toml` | P1、R5 守住 | `PROTECTED=PASS` |
| 每任务 3 seed smoke | 每任务取 train hard 前 3 条，`--workers 1 --gpus 0`，记成功数、T、窗口数、Δ8、最短执行段 | 子类能跑通、长度与估算对账 | `XHARD_SMOKE=PASS task=<t> seeds=3 ok=<k>`；`XHARD_LENGTH=INFO task=<t> T=<min/med/max> windows=<..> delta8=<..> shortest_seg=<..> skip8=<n>` |
| 8 帧必漏 | smoke 的 `skip8`（8 帧帧路没有采样点落入的执行段数）每条 ≥1 | 口径 ⑥ 成立 | `XHARD_SKIP8=PASS task=<t> episodes=3 min_skip8=<n≥1>` |
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 没有碰坏既有链路 | passed |
| 全量 | 425 条跑完，`run_summary.json` 的 `success_count`，每任务 metadata 条数 | 交付规模 | `XHARD_FULL=INFO requested=425 success=<n> exhausted=<n>` |

## 五、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用户说「开工」 | — |
| 1 | 六项前置验证：① `spec` 拦截最小 smoke（临时子类，不落盘）；② PatternLock `length` [10,14] 在 5×5 的接受率（只读复现拒绝采样 1000 个 seed）；③ ButtonUnmaskSwap swap=5 时交换结束步（314）与两次按钮完成步的先后；④ BinFill 目标 6 个时生成成功率（临时 `_load_scene` 统计 25 个 hard seed）；⑤ VideoRepick super 后改写 `num_repeats` 后 reset 重建 task_list 读到新值；⑥ VideoPlaceOrder `current_task_specialflag(s)` 命名不一致是否影响 hard swap | 六项各出一行结论写进第二部分八节；①⑤ 为 PASS 才进步骤 2 |
| 2 | 主会话 S0：`src/robomme_xhard/{__init__,base,jobs}.py`、`envs/__init__.py` 骨架 + `README.md`，commit `2.33` | `XHARD_BASELINE_EQ=PASS`（此时 `make_name` 对无 xhard 卡片恒等） |
| 3 | 同一消息派 S1、S2、S3、S4（`isolation: "worktree"` + `model: "opus"`） | 各自验收命令 passed（第二部分二节） |
| 4 | 合并顺序 S1 → S2 → S3 → S4：合并前审查 → `--no-ff` 合并 → 合并后审查 → push | `PRE_MERGE_REVIEW=PASS`、`POST_MERGE_REVIEW=PASS`、`PROTECTED=PASS` |
| 5 | 主检出跑 `XHARD_SPEC`（11 子类）与每任务 3 seed smoke，出对账表 | `XHARD_SPEC=PASS`、`XHARD_SMOKE`、`XHARD_LENGTH`、`XHARD_SKIP8` |
| 6 | 把对账表交用户审阅取值（可改表三的数或剔除 VideoPlaceOrder）；用户再说「开工」后全量 425 条 | `XHARD_FULL=INFO` |
| 7 | 数轴图（每任务最短/中位/最长各一条，与原 hard 并排）、`docs/xhard-doc/<档案名>/` 留档、commit、push | `result.md` 落盘 |

## 六、子代理分工与合并（简述）

主会话先写新包骨架 S0（`XHardMixin`、`jobs_from_metadata`、`make_name`、空的 `envs/__init__.py`），提交后同一时刻派四个写入型子代理，各在自己的 worktree 里写、文件互不重叠：S1 写 6 个换字典任务的子类文件，S2 写 5 个重写方法任务的子类文件，S3 改生成器的四处与 `EpisodeJob`，S4 写轻量测试。合回顺序 S1 → S2 → S3 → S4：每合一个先查越界与 worktree 内验收、派一个只读 sonnet 审查，`--no-ff` 合入后跑核心短测与 `PROTECTED`，再 push 下一个。`envs/__init__.py` 的 11 行 import 由主会话在 S1、S2 合完后补齐（共享文件归主会话）。需要 `gym.make` 的验收全部留到合并后主检出串行跑。

逐文件代码、子代理分配表、闸门命令、runbook、风险与盲区、留档纪律、逐任务源码依据与估算公式见第二部分。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- **R1** `src/robomme/` 零 diff（P1）：`git diff --quiet <BASE> HEAD -- src/robomme/` 必须为真；四个 wrapper、`robomme_env/__init__.py`、`utils/`、planner、`seed_layout.py`、`env_metadata/train/*.json`（只读）一字不动。
- **R2** 开关关闭态逐字节不变：不传 `--xhard` 时生成器的解析结果、jobs、`gym.make` 名字、metadata 输出与 `BASE` 版本相同（`XHARD_BASELINE_EQ`）。
- **R3** seed 不换、attempt 固定 0：xhard 卡片失败不 `bump`，池损坏退回原卡片；不写任何「失败换 seed」的兜底。
- **R4** 不传、不移植 `--binfill-demo`（P4）。
- **R5** 不改 `pyproject.toml`、`uv.lock`（editable `.pth` 指向整个 `src/`，新包天然可 import；wheel 不含新包写进盲区）。
- **R6** worktree 内子代理只跑 ≤5 分钟 CPU 测试，不 `gym.make`、不起生成；GPU 验收归合并后主会话。
- **R7** 全量生成前须用户审阅步骤 5 对账表并再次说「开工」；smoke 每任务 3 条不扩（P5）。
- **R8** 子类只许改表三列出的键 / 方法；其它键、其它方法、其它任务一律不碰，顺手修不算获准（P1 逐个批准）。
- **R9** 输出目录独立：派生档一律写 `artifacts/xhard/<档名>-<日期>/`，不与原 hard 混放（HDF5 文件名与原 hard 同名 `BinFill_ep3_seed4301.h5`，靠目录区分；`setup/difficulty` 仍是 hard）。

## 一、逐文件改动清单

**新包 `src/robomme_xhard/`（全部新增，与 `src/robomme/` 并排；包名用下划线）**

`__init__.py`：
```python
"""xhard 新档：原 16 任务 hard 母样本的派生子类，与生成器开关。import 本包即完成全部 @register_env。"""
from . import envs  # noqa: F401  触发子类注册
from .jobs import jobs_from_metadata, make_name  # noqa: F401
```

`base.py`（S0，主会话）：
```python
import dataclasses

class XHardMixin:
    """放在父类之前多继承。gym.make 在套 wrapper 之前执行 env.unwrapped.spec = EnvSpec(...)，
    这里用 property setter 拦截，把 id 换回原任务名，其余字段原样保留。
    必须带 setter：没有 setter 时 gym.make 的赋值会抛 AttributeError。"""
    robomme_base_id: str | None = None

    @property
    def spec(self):
        return self.__dict__.get("_xhard_spec")

    @spec.setter
    def spec(self, value):
        if value is not None and self.robomme_base_id:
            value = dataclasses.replace(value, id=self.robomme_base_id)
        self.__dict__["_xhard_spec"] = value
```
已核实依据：gymnasium `envs/registration.py::make` 的 `env.unwrapped.spec = EnvSpec(...)` 在 `PassiveEnvChecker`/`OrderEnforcing`/`MSTimeLimit` 之前；`gymnasium.core.Env` 类属性 `spec = None` 被 property 遮蔽；`BaseEnv` 不写 `spec`；`BaseEnv.__init__` 期间 `spec` 为 None（getter 默认 None 兼容）。`dataclasses.replace` 是浅拷贝，`kwargs`/`additional_wrappers` 与原对象共享引用，不改它们。

`jobs.py`（S0，主会话）：
```python
XHARD_TIERS = ("xhard1", "xhard2")

def make_name(job) -> str:
    """卡片无 xhard → 原名；有 → f"{task}XHard{n}"（xhard1 → BinFillXHard1）。"""
    tier = getattr(job, "xhard", None)
    if not tier:
        return job.task
    return f"{job.task}XHard{tier[len('xhard'):]}"

def jobs_from_metadata(tasks, split, xhard, output_root, repo_root, job_cls):
    """读 src/robomme/env_metadata/<split>/record_dataset_<Task>_metadata.json 的 records，
    只取 difficulty == "hard"，每条一张卡片：task/episode/seed 原样，attempt=0，difficulty="hard"，xhard=<tier>。
    返回 (jobs, {task: 条数, 源路径})。tier 不在 XHARD_TIERS、split 目录不存在、某 task 没有 json → 抛 ValueError。"""
```
（`job_cls` 由生成器传入 `EpisodeJob`，避免新包反向 import 生成器脚本。）

`envs/__init__.py`（S0 建空文件；S1、S2 合完后由主会话补 11 行 `from . import <task>  # noqa: F401`）。

`envs/<task>.py`（S1 六个、S2 五个，每文件只含该任务的 `XHard1`（与预留 `XHard2`）子类；本轮只定 `XHard1` 的数，`XHard2` 先不写）：

| 文件 | 子类代码要点（锚点已核实） |
|---|---|
| `pick_xtimes.py` | `@register_env("PickXtimesXHard1") class PickXtimesXHard1(XHardMixin, PickXtimes): robomme_base_id="PickXtimes"; configs={**PickXtimes.configs,"hard":{**PickXtimes.config_hard,"number_min":6,"number_max":7}}`。`__init__` 用局部 generator 读 `configs[difficulty]['number_min/max']`，自动生效 |
| `swing_xtimes.py` | 同上，`"number_min":7,"number_max":8`；`max_swings = num_repeats*2` 在 `_initialize_episode` 自动派生 |
| `pick_highlight.py` | `{**PickHighlight.config_hard,"pickup":5}`；`step` 已 `min(pickup, len(target_cubes))` |
| `pattern_lock.py` | `{**PatternLock.config_hard,"length":[10,14]}`；拒绝采样 1000 次不中静默兜底，接受率由前置验证 ② 定，若过低改 [9,13] |
| `route_stick.py` | `{**RouteStick.config_hard,"length":[8,10]}`；`configs` 整体保留三档（`_load_scene` 用 `configs.get(..., config_easy)`） |
| `bin_fill.py` | `{**BinFill.config_hard,"put_in_numbers":[5,6]}`；另重写 `_load_scene(self, options)`：`super()._load_scene(options)` 后核对每个有目标颜色的实际方块数 ≥ 目标数，不足即 `raise SceneGenerationError(...)`（父类把生成失败吞成 debug 日志，否则 `_initialize_episode` 的 `cube_collection[i]` IndexError；`SceneGenerationError` 由生成器归为 `task` 失败、xhard 不换 seed）。`SceneGenerationError` 的 import 路径以 `_worker` 现用的为准 |
| `video_unmask_swap.py` / `button_unmask_swap.py` | `{**父.config_hard,"swap_min":4,"swap_max":5}`；重写 `_refresh_swap_schedule(self)`：k=1..3 照父类（64+50(k−1) 到 64+50k），k=4、5 新增：`swap_pair4_idx1`/`swap_pair5_idx1` 若不存在则按 `swap_indices[(k-1) % len(swap_indices)]` 取、`idx2=None`，区间 64+150 到 64+200、64+200 到 64+250；`step()` 用 `len(self.swap_schedule)` 与 `getattr(self, f'swap_pair{i+1}_idx2')` 泛化遍历，不必重写；VideoUnmaskSwap 的 static 演示 `static_steps = swap_schedule[-1][3]` 自动变长（264/314）。origin/newtask-v2 已实现过 swap 4–5，写之前 `git log origin/newtask-v2 -- src/robomme/robomme_env/VideoUnmaskSwap.py` 参考其 diff（只参考、不照搬进 `src/robomme/`） |
| `stop_cube.py` | 重写 `_initialize_episode(self, env_idx, options)`：照父类顺序用新建 generator（`manual_seed(self.seed)`）抽 `interval`（抽后覆盖 30）→ `move_interval` 的 `randint(0,3)`（抽后**覆盖为 120**）→ `stop_time = randint(8, 11)`（原 `randint(2,6)` 的位置，消耗量相同）→ `rotation_angle`，其余照抄父类；重写 `step()`：`for segment in range(5)` 改为 `range(self.stop_time)`。`evaluate` 的 `move_interval*stop_time` 超时自动随之变 |
| `video_repick.py` | 重写 `__init__(self, *args, seed=None, **kwargs)`：`super().__init__(*args, seed=seed, **kwargs)` 后 `self.num_repeats = int(torch.randint(4, 6, (1,), generator=torch.Generator().manual_seed(seed)).item())`——用独立 generator，不动 `self.generator` 的随机流；构造期间那次 `_initialize_episode` 用旧值，生成器随后 `record_env.reset()` 重跑 `_initialize_episode` 读到新值（已核实默认 `reconfiguration_freq=0`、reset 不重跑 `_load_scene`，hard 分支 `_load_scene` 不依赖 `num_repeats`）；前置验证 ⑤ 实证 |
| `video_place_order.py` | 重写 `_load_scene`：复制父类函数体，仅把 `num_targets_to_pick = torch.randint(2, len(self.targets)+1, ...)` 改为 `torch.randint(4, 5, ...)`（固定 4，消耗量不变），其余逐字相同；前置验证 ⑥ 若发现 `current_task_specialflag(s)` 缺陷影响 hard swap，则本任务剔除、不在新包里修 `src/robomme` |

`README.md`（S0）：中文说明包的用途、`XHardMixin` 原理、怎么加一个任务的子类（三步：建文件、写 `configs`/方法、在 `envs/__init__.py` 加一行）、怎么跑（见四节 runbook）、本轮取值表（表三）。

**生成器 `scripts/data-generation-newSeed/generate_dataset_newseed.py`（S3）**，四处：
1. `EpisodeJob` 加字段 `xhard: str | None = None`（放最后，默认 None，`bump`/`replace` 不受影响）。
2. `_args`：`--xhard` `choices=("xhard1","xhard2")` 默认 None；`--source-split` 默认 `"train"`；解析后若 `args.xhard` 非空且用户显式给了 `--difficulty --layout --episodes --episode-start --max-attempts` 任一（用 `parser.get_default` 比对或 `argparse.SUPPRESS` 哨兵判「是否显式传入」），`parser.error("--xhard 与 --difficulty/--layout/--episodes/--episode-start/--max-attempts 互斥")`。
3. `generate_dataset_newseed`：`if args.xhard: jobs, source_info = robomme_xhard.jobs_from_metadata(tasks, args.source_split, args.xhard, str(output), str(REPO_ROOT), EpisodeJob)`，跳过 seed 护栏；否则原列表推导。`parameters` 增 `xhard`、`source_split`、`source_json`、`source_hard_counts`。此处的 `import robomme_xhard` 在函数内、`sys.path` 已含 `src` 之后（主进程不绑卡，但 `jobs.py` 只读 json、不 import mani_skill，`robomme_xhard/__init__.py` 会 import `envs` → 父类 → mani_skill/torch；为避免主进程提前初始化 CUDA，主进程改为 `from robomme_xhard.jobs import jobs_from_metadata`，不走包 `__init__`）。
4. `_run_jobs`：失败分支 `elif job.xhard is None and job.attempt + 1 < max_attempts: pending.append(job.bump(...))`，xhard 卡片直接 `exhausted.append(result)`；池损坏分支 `pending.appendleft(job if job.xhard else job.bump(...))`。`_pool_init` 与 `_worker`：`import robomme.robomme_env` 之后加 `import robomme_xhard  # noqa: F401`；`_worker` 的 `gym.make(job.task, **kwargs)` 改 `gym.make(robomme_xhard.make_name(job), **kwargs)`。

**测试 `tests/lightweight/test_robomme_xhard.py`（S4，CPU，不 `gym.make`，不标 gpu）**：
- `test_configs_only_target_keys_differ`：对 11 个子类，`configs["easy"]`/`["medium"]` 与父类相等；`configs["hard"]` 与 `config_hard` 的差集键 == 表三所列键。
- `test_make_name`：无 xhard 返回原名；`xhard1` → `<Task>XHard1`。
- `test_jobs_from_metadata_train_hard`：对 11 任务条数 == {25,100}，seed 与 json 一致，attempt 全 0，difficulty 全 hard，排序稳定。
- `test_mutex_args`：5 组互斥参数各 `SystemExit`。
- `test_baseline_jobs_unchanged`：不传 `--xhard` 时 `_args` 与 jobs 与写死的期望（BinFill 4 条示例：seed 4000/4100/4200/4300、难度 e/e/m/h）一致。
- `test_register_names`：`import robomme_xhard` 后 `gym.registry` 含 11 个 `*XHard1`（只查注册表，不实例化）。
- 另有 `tests/lightweight/test_robomme_xhard_spec.py`（标 `gpu, slow`，主检出跑）：对 11 个子类 `gym.make(名, obs_mode=..., difficulty="hard", seed=<train 首条 hard seed>)`，断言 `unwrapped.spec.id` 原名、外层 `spec.id` 原名、`entry_point` 不变、`isinstance(env.unwrapped, 父类)`。

## 二、子代理分配表

`BASE` = S0 提交后的 HEAD。环境取法（R6）：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先 `python -c "import robomme,robomme_xhard;print(robomme.__file__, robomme_xhard.__file__)"` 确认都在 `<worktree>/src/`。

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| S0 | 新包骨架 | `src/robomme_xhard/{__init__,base,jobs}.py`、`envs/__init__.py`（空）、`README.md` | R1、R5 | `XHardMixin.robomme_base_id`；`make_name(job)`；`jobs_from_metadata(tasks, split, xhard, output_root, repo_root, job_cls)` | 派发前 | 主会话自做：`uv run --no-sync python -c "from robomme_xhard.jobs import make_name, jobs_from_metadata"` | CPU | 主会话 |
| S1 | 换字典组 6 子类 | `src/robomme_xhard/envs/{pick_xtimes,swing_xtimes,pick_highlight,pattern_lock,route_stick,bin_fill}.py` | `src/robomme/**`、`envs/__init__.py`、其它 envs 文件 | 继承 `XHardMixin` + 父类；`robomme_base_id`；只改表三的键；BinFill 后置校验抛 `SceneGenerationError` | 1 | `python -m pytest tests/lightweight/test_robomme_xhard.py -k "configs or register" -q`（S4 合入前用 S1 自带的最小断言脚本 `python -c` 逐类比 configs） | CPU | 无 |
| S2 | 重写方法组 5 子类 | `src/robomme_xhard/envs/{video_unmask_swap,button_unmask_swap,stop_cube,video_repick,video_place_order}.py` | 同上 | 同上；重写方法只许表一所列；复制父类函数体时逐字相同、只改指定行 | 2 | 同上 `-k configs`；另附 `git diff` 可读的「父类原文 vs 子类改行」对照写进交回 | CPU | 无 |
| S3 | 生成器开关 | `scripts/data-generation-newSeed/generate_dataset_newseed.py` | `src/**`、`seed_layout.py`、`pyproject.toml` | `EpisodeJob.xhard`；`--xhard`/`--source-split` 与互斥；两处不 bump；worker 内 import；`make_name` | 3 | `python -m pytest tests/lightweight/test_seed_layout.py -q` + `python scripts/data-generation-newSeed/generate_dataset_newseed.py --help`（含 `--xhard`）+ 自带 `python -c` 断言不传 `--xhard` 时 jobs 与 BASE 相等 | CPU | 无 |
| S4 | 轻量测试 | `tests/lightweight/test_robomme_xhard.py`、`tests/lightweight/test_robomme_xhard_spec.py` | `src/**`、`scripts/**` | 按一节用例清单；spec 测试标 `gpu, slow` | 4 | `python -m pytest tests/lightweight/test_robomme_xhard.py -q` passed（基于合入 S1–S3 后的分支） | CPU | 无 |
| 主会话 | `envs/__init__.py` 11 行 import；合并、审查、push；步骤 5 的 GPU 验收 | `src/robomme_xhard/envs/__init__.py` | — | S1、S2 合入后补 | S2 之后 | `XHARD_SPEC`、`XHARD_SMOKE`、`XHARD_LENGTH`、`XHARD_SKIP8` | GPU 0 | 主会话 |
| 运行型 R1 | 全量 425 条 | 无 | 一切代码 | 命令原文照四节 runbook 第 4 条；起跑判据 `succeeded with seed` 首行出现且 `tmux has-session -t '=xh-full'` 为真 | 步骤 6 用户再说「开工」后 | 交回 tmux 名、日志路径、起跑时间、首批判定行、`tmux ls` 原文 | GPU 0，32 worker，约 120 GB RSS | 账目归主会话 |

派发前核对：`~/.claude/settings.json` 的 `worktree.baseRef` 为 `"head"`（当前文件没有这一项，派发前先补）；`git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空；`git check-ignore -q .claude/worktrees/probe`；`git worktree list` 存档。

## 三、闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 核心短测（每次合并后） | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | passed |
| 受保护目录 | `git diff --quiet <BASE> HEAD -- src/robomme/ pyproject.toml uv.lock && echo PROTECTED=PASS` | `PROTECTED=PASS` |
| 关闭态不变 | `uv run --no-sync python -m pytest tests/lightweight/test_robomme_xhard.py -k baseline -q`；另对 `BASE` worktree 与 HEAD 各跑一次 `--help` 与 jobs dump 比对 | `XHARD_BASELINE_EQ=PASS jobs_diff=0 names_diff=0 mutex_errors=5` |
| 子类 configs | `... -k configs -q` | `XHARD_CONFIGS=PASS tasks=11 unexpected_diff=0` |
| 卡片 | `... -k jobs -q` | `XHARD_JOBS=PASS source=train tasks=11 jobs=425 seed_unchanged=425` |
| 身份牌（主检出） | `uv run --no-sync python -m pytest tests/lightweight/test_robomme_xhard_spec.py -q` | `XHARD_SPEC=PASS tasks=11 id_mismatch=0 entry_point_changed=0` |
| smoke（主检出，每任务） | 四节第 3 条命令 + 统计脚本 | `XHARD_SMOKE=PASS task=<t> seeds=3 ok=<k>`；`XHARD_LENGTH=INFO ...`；`XHARD_SKIP8=PASS task=<t> episodes=3 min_skip8=<n>` |
| 全量 | `run_summary.json` | `XHARD_FULL=INFO requested=425 success=<n> exhausted=<n>` |

## 四、runbook（主会话）

1. **前置验证**（步骤 1，六项，只读或 ≤5 分钟）：①⑤ 用临时脚本在 scratchpad 里定义一个最小子类（不落仓库）`gym.make` 一次（GPU 0，单进程），打印 `unwrapped.spec.id`、`spec.entry_point`、改写后 reset 的 `task_list` 长度；② `uv run --no-sync python -c` 复现 PatternLock 拒绝采样（只 import `find_path_0_to_8`，1000 个 seed，统计 [10,14] 命中率与平均尝试次数）；③ 读 ButtonUnmaskSwap 源码算 S=5 的交换结束步 314 与 `solve_button` 两次的步数（留档 4.3：按钮段均值约 104×2）；④ 临时脚本对 25 个 BinFill hard seed 跑子类 `_load_scene`（需渲染栈，GPU 0，单进程，不录像），统计每色实际数 ≥ 目标数的比例；⑥ grep `current_task_specialflag` 在 VideoPlaceOrder 的全部读写点。六项结论各一行写进八节。
2. **S0 → 派发 → 合并**：按二节；每次合并 `git merge --no-ff <TIP sha> -F <scratchpad 消息文件>`，subject 按 `2.<n>` 递增，body 按第 11 条六项。
3. **smoke**（步骤 5，每任务一条命令、串行、GPU 0）：
   ```bash
   uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py \
     --xhard xhard1 --env <Task> --workers 1 --gpus 0 --max-tasks-per-child 0 \
     --output-dir artifacts/xhard/smoke-$(TZ=America/New_York date +%m%d)/<Task>
   ```
   `jobs_from_metadata` 支持 `XHARD_SMOKE_LIMIT=3` 环境变量只取前 3 条（S0 实现，默认不限；写进 `parameters`）。统计用 `scripts/patternlock-routestick-params/extract_move_durations.py::extract_episode` 同口径的临时脚本算 T、stride-16 窗、Δ8、最短执行段、skip8，输出 `XHARD_LENGTH`/`XHARD_SKIP8` 行；脚本落 `docs/xhard-doc/<档案名>/records/`。
4. **全量**（步骤 6，用户再说「开工」后；按第 13 条先打 `2.<n>Beta` 锚点、`git status --short` 为空）：
   ```bash
   tmux new-session -d -s xh-full \
     "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py \
        --xhard xhard1 --env PickXtimes,SwingXtimes,PickHighlight,PatternLock,RouteStick,BinFill,VideoUnmaskSwap,ButtonUnmaskSwap,StopCube,VideoRepick,VideoPlaceOrder \
        --workers 32 --gpus 0 --output-dir artifacts/xhard/full-$(TZ=America/New_York date +%m%d) \
        2>&1 | tee artifacts/xhard/logs/xh-full.log; echo \"EXIT_CODE=\$?\" >> artifacts/xhard/logs/xh-full.log"
   ```
   单卡 32 worker 是 `scripts/data-generation-newSeed/CLAUDE.md` 实测安全上限（双卡无收益）；预计 425 条 × 约 780 帧均值，按 56 ep/min 的 hard 口径折算约 15–25 分钟，xhard 更长、更易失败，预留 1 小时。先 `nvidia-smi` 选空闲卡。
5. **监听**：`tail -n +1 -F artifacts/xhard/logs/xh-full.log | stdbuf -oL tr '\r' '\n' | grep --line-buffered -E "succeeded with seed|failed|进程池已损坏|ERROR:|Traceback|BrokenProcessPool|svulkan2|out of memory|EXIT_CODE="`；一份日志一个 Monitor。
6. **收尾**：`run_summary.json`、每任务 metadata 条数、`XHARD_FULL` 行；数轴图按留档 1.4 节口径（`plot_sampling_windows.py` 现只认 4 任务与 3 档，需在 `docs/xhard-doc/<档案名>/records/` 放一份改参数的临时副本，不改原脚本）；`docs/xhard-doc/<档案名>/{launch.md,result.md,records/}`；commit、push；smoke 产物按第 6 条清理（只删核实属于本轮的 `artifacts/xhard/smoke-*`，先 `ls -ld`）。

## 五、风险登记

| 项 | 说明 | 处置 |
|---|---|---|
| PatternLock 接受率 | `length` [10,14] 在 5×5 网格靠拒绝采样，1000 次不中静默用最后一条，长度可能落在区间外 | 前置验证 ②；过低改 [9,13]；smoke 的 `XHARD_LENGTH` 核实实际 L |
| ButtonUnmaskSwap 时序 | swap=5 时交换到第 314 步才结束，两次按钮约 221 步，抓容器时交换可能未完 | 前置验证 ③；失败率高则在子类加「等到交换结束」的 hold（那就不再是只改参数，需用户批准）或剔除 |
| BinFill 生成失败静默 | 目标 6 个时固定区域更挤，父类吞掉生成失败 → IndexError | 子类后置校验抛 `SceneGenerationError`，按 R3 记失败不换 seed；前置验证 ④ 给出成功率 |
| StopCube `range(5)` | 不改 `step()` 时 k>5 方块停在终点必失败 | `step()` 一并重写（表一） |
| 随机流偏移 | BinFill 共用 generator，改目标数后方块坐标全变；PatternLock/RouteStick 路径变 | 写进对拍预期，不要求母布局逐项相等；其余任务实测 randint 消耗量与区间无关（留档 5.0） |
| 成功率低于 hard | 不换 seed，原 hard 靠重试才成功的条目（BinFill 11、VideoPlaceOrder 12 等）更易失败 | 失败即缺条，`XHARD_FULL` 如实记；补齐留下一轮新 seed |
| 两个 Swap 任务短 | 最多约 560 帧、31 窗，达不到 50–60 | 结构限制，写明；它们贡献 200/425 条 |
| 名字对不上静默出空目标 | `get_language_goal`/`get_vqa_options` 未知名字返回 `[]` 不报错 | `XHARD_SPEC` 断言 `spec.id`；smoke 核对 HDF5 的 `simple_subgoal` 非空 |
| `Wrapper.spec` 缓存 | gymnasium `Wrapper.spec` deepcopy 并缓存，拦截前访问会固化旧 id | 仓库内无提前访问（已核实）；`XHARD_SPEC` 同时断言外层 `spec.id` |
| 主进程提前拉起 CUDA | 主进程 `import robomme_xhard` 会经 `envs` import mani_skill/torch | 主进程只 `from robomme_xhard.jobs import ...`；worker 内才 import 整包 |
| VideoPlaceOrder 源码缺陷 | `current_task_specialflag(s)` 命名不一致 | 前置验证 ⑥；有影响即剔除该任务（总量 400） |
| 本计划判定行 | 全部待实施 | — |

## 六、盲区诚实清单

1. 所有 T、窗口数、Δ8 为线性外推（公式八节），`move_to_pose_with_screw` 实际步数未实测。
2. `/data/hongzefu/data_0226/` 未与 HF revision 核 sha256（留档 6.1）。
3. wheel 不含 `robomme_xhard`（R5 不改 `packages`）；只影响非 editable 安装，本仓库不用。
4. `XHARD_SMOKE_LIMIT` 环境变量是本轮新增的测试便利，不是正式接口；全量不设。
5. VideoRepick 改写 `num_repeats` 依赖「reset 重跑 `_initialize_episode`」，已核实源码，前置验证 ⑤ 再实证一次。
6. `make_vec` 路径未验证（本仓库不走）。
7. `XHard2` 档只预留名字，不写数。
8. 数轴图脚本改参数副本放 records，不改 `scripts/patternlock-routestick-params/`。

## 七、留档与 commit 纪律

- S1–S4 各经 `--no-ff` 合并占一个 `2.<n>`；子代理提交前缀 `sub/S<k>: `；S0、`envs/__init__.py`、留档由主会话按第 11 条六项 body 提交，含第一部分一节的用户原话。
- 全量生成按第 13 条：起跑前 `2.<n>Beta` 锚点，`docs/xhard-doc/xhard1-<日期>/launch.md`（起跑即写：HEAD、命令原文、tmux 会话名、日志路径、`XHARD_*` 前置判定行）、`result.md`（跑完写：每任务条数、`XHARD_FULL`、`XHARD_LENGTH` 对账表、数轴图、结论边界）、`records/`（清洗后日志 `tr '\r' '\n' | grep -vE '%\|'`、统计 JSON、临时脚本逐字副本）；不归档 h5/mp4。
- 留档根 `docs/` 新建；`docs/ledger/` 只读不动。

## 八、逐任务源码依据与估算公式

估算：T_xhard ≈ T_hard 中位 + Δ次数 × 该次数对应子任务段长之和（留档 4.3 均值）；窗口 ≈ demo 窗 + exec 窗，各按 `len(range(0, max(0, L-32), 16))`；Δ8 = (T−1)/7。配置原文、随机流、语言上限、metadata 条数见留档 5.1 节，此处只列每任务的实施数与依据。

1. **BinFill**：`put_in_numbers` [5,6]。每多 1 个目标约 +179 帧（108.5+70.6）；hard 均值 4 → 5.5，T ≈ 868 + 1.5×179 ≈ 1137；窗 ≈ 69。`spawn_cubes` [10,12] ≥ 6 不必改；每色目标 ≤10 自然满足。`dynamic` 模式移走窗口随每色方块数变长。
2. **PickXtimes**：6/7。每次 +154 帧（84.2+69.6）；4.5 → 6.5，T ≈ 1120；窗 ≈ 68。同宽平移，抽到的 N 恒为原值 +2。
3. **SwingXtimes**：7/8。每次 +78 帧（37.5+40.6）；3 → 7.5，T ≈ 839；窗 ≈ 50。单值变双值不多消耗随机数。
4. **PickHighlight**：5。每个 +154 帧（98.7+55.4）；T ≈ 847；窗 ≈ 51。不取 6：6/6 全高亮让「记住哪些被高亮」失去意义。
5. **PatternLock**：[10,14]。每个 move 约 37 帧 × 2（demo+exec）；T ≈ 74×(L−1)：L=10 → 666，12 → 814，14 → 962；窗 ≈ 37–55。备选 [9,13] 或 [12,16]；不改 `grid`（母布局全变）。
6. **RouteStick**：[8,10]，与 newtask-v2 xhard 相同。T = 100·S = 800–1000；窗 = 2×wins(50S) = 46/54/60。
7. **VideoUnmaskSwap / ButtonUnmaskSwap**：[4,5]。VideoUnmaskSwap demo = 6·ceil((64+50S)/6) = 264/318，exec ≈ 263，T ≈ 527–581，窗 ≈ 15–18 + 14 ≈ 31。ButtonUnmaskSwap 交换结束 264/314 步，两次按钮约 221 步。第 4、5 对的 `idx1` 规则：`swap_indices[(k-1) % 3]`（即第 4 对复用第 1 对的第一个容器、第 5 对复用第 2 对的），`idx2` 运行时取最近，与父类 1–3 对的机制一致。
8. **StopCube**：`move_interval` 钉 120、`stop_time` [8,10]。T ≈ 120×(k−0.5) + 28 ≈ 928/1048/1168；窗 ≈ 56/63/71；static 段 100 帧，Δ8 ≥ 132 必漏。不钉 mi 时 mi=60 的 T 450–570，Δ8 64–81 < 100，不满足。
9. **VideoRepick**：[4,5]。每次 +157 帧（98.7+58.3）；2 → 4.5，T ≈ 935；窗 ≈ 9（demo 162）+ 47 ≈ 56。改写用独立 generator，不动 `self.generator`，15 块与目标逐项不变。
10. **VideoPlaceOrder**：固定 4。每组 +181 帧（约 90+91）；3 → 4，T ≈ 1296；窗 ≈ 78。上限被 `range(4)` 卡死；可剔除。

前置验证六项的结论（实施时填写）：① spec 拦截 — 待填；② PatternLock 接受率 — 待填；③ ButtonUnmaskSwap 时序 — 待填；④ BinFill 6 目标生成成功率 — 待填；⑤ VideoRepick reset 读新值 — 待填；⑥ VideoPlaceOrder specialflag — 待填。
