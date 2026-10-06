> 本文按用户最新要求改为"子类继承"接口方案，替代此前"ENV 内加 xhard 变量再 if/else"的设计；只改计划，不构成开工令。本轮只定义接口，不展开每个任务具体改哪些次数，那部分待接口定稿后另议。工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支为 `newtask-v3-MotionJepa1006`。本次修订前 HEAD 为 `70f55d958cfd8d79da212e730a1b852c34c58ed0`；原源码核查锚点为 `13905997d45155ff1c98417511aedec92578042d`，生成代码起点为 `3a5951a834ea014f63724647ab0bc091eb9f109d`。ManiSkill 来源仍钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，依赖以本分支 `pyproject.toml、uv.lock` 为准。文中所有新名字、新参数、新文件均为拟议项，尚未实施。

# 设计目标

用户要求（原话）："我就是要沿用 Hard 的所有配置但只是在一两个参数上进行修改"，"我只改环境生成中一两个参数比如说我 PICK 5 次变成 PICK 7 次"，"能不能用一个独立的 ENV 文件来表示它的新增部分"，"我所有的改动就仅限于这个 generate dataset 的这一个文件和这些新增的十六个文件"，"seed 我先用现有的 seed 来做"，来源为 `src/robomme/env_metadata/train` 里已经生成过原版 hard 的记录。

因此本方案的硬约束：

1. 原 16 个 ENV 文件（`src/robomme/robomme_env/*.py`）一个字节不改。
2. 新档的全部差异只落在新增的子类文件里，每个任务只覆盖一两个数。
3. 生成器 `scripts/data-generation-newSeed/generate_dataset_newseed.py` 只加一个开关和一处拼名字逻辑。
4. seed 直接取 train metadata 中 `difficulty == "hard"` 记录的原 seed，不重算、不换 seed。
5. 录像器允许"稍微改一点"，但只改为"按原任务名识别"，不改录制逻辑。

# 第一部分：现在的脚本怎么传参，新参数接在哪

## 1. 现有调用链，分五环

`generate_dataset_newseed.py` 从命令行到写出 HDF5 的路径如下，括号内是稳定锚点：

| 环 | 代码位置 | 现在做什么 |
|---|---|---|
| ① 命令行 | `_args` → `main` → `generate_dataset_newseed` | 读 `--env、--episodes、--episode-start、--difficulty（三档比例）、--layout、--max-attempts、--workers、--gpus` 等。 |
| ② 排任务单 | `generate_dataset_newseed` 内构造 `EpisodeJob` 列表 | 每个 episode 一张卡片，字段 `task、episode、attempt、seed、difficulty、output_root、repo_root`。seed 由 `layout.seed(task, episode, attempt)` 公式算出，difficulty 由 `difficulty_for(episode, cycle)` 按比例轮排。 |
| ③ 发给工人 | `_run_jobs` 进程池 | 每个 worker 进程拿一张卡片执行 `_worker(job)`。 |
| ④ 造环境并录制 | `_worker` | `kwargs = {obs_mode, control_mode, render_mode, reward_mode, seed=job.seed, difficulty=job.difficulty}`；`base_env = gym.make(job.task, **kwargs)`；`record_env = RobommeRecordWrapper(base_env, dataset=output_root, env_id=job.task, episode=job.episode, seed=job.seed, save_video=True)`；`record_env.reset()`；按 `job.task in STICK_TASKS` 选 planner；`_execute_tasks` 逐个 subgoal 求解并录制。 |
| ⑤ 失败换 seed | `_run_jobs` 内调用 `EpisodeJob.bump(new_seed)` | 场景生成失败、planner 耗尽等五类可重试异常时换 seed 重来，直到 `--max-attempts`。 |

`gym.make(job.task)` 这一句的含义：到 ManiSkill 注册表里按名字 `"PickHighlight"` 找到用 `@register_env("PickHighlight")` 登记的 class，然后 `PickHighlight(seed=..., difficulty="hard", ...)` 实例化。新档就是让这一句找到另一个 class。

## 2. 新参数：只加一个 `--xhard`，并改卡片来源

拟议 CLI：

| 参数 | 取值 | 含义 |
|---|---|---|
| `--xhard` | 不传 / `xhard1` / `xhard2` | 不传时脚本与现在完全相同；传入时进入"派生档"分支。 |
| `--source-split` | 默认 `train` | 只在 `--xhard` 传入时生效，指定从 `src/robomme/env_metadata/<split>/` 读母样本。 |

`--xhard` 与 `--difficulty（比例）、--layout、--episodes、--episode-start、--max-attempts` 互斥：传了 `--xhard` 就不允许再传这几项，传了即报错，避免两套 seed 来源混用。

`EpisodeJob` 增加一个可选字段 `xhard: str | None = None`，默认 `None`，旧路径不受影响。

## 3. 派生档分支下五环各自怎么变

| 环 | 不传 `--xhard`（原路径，零改动） | 传 `--xhard xhard1`（新路径） |
|---|---|---|
| ① 命令行 | 同现在 | 多解析 `--xhard、--source-split`，做互斥校验。 |
| ② 排任务单 | 公式算 seed、比例轮 difficulty | 读 `src/robomme/env_metadata/train/record_dataset_<task>_metadata.json`，筛 `records[].difficulty == "hard"`，每条记录造一张卡片：`task、episode、seed` 原样抄，`difficulty="hard"` 固定，`xhard="xhard1"`。不再调用 `layout.seed`，也跳过"seed 越界下一代布局"护栏（该护栏只对公式 seed 有意义）。 |
| ③ 发给工人 | 同现在 | 同现在。 |
| ④ 造环境 | `gym.make(job.task, **kwargs)` | `env_name = job.task if job.xhard is None else f"{job.task}{XHARD_SUFFIX[job.xhard]}"`，例如 `"PickHighlightXHard1"`；`gym.make(env_name, **kwargs)`，**kwargs 一个不改**，`difficulty` 仍是 `"hard"`，seed 仍是原 seed。`RobommeRecordWrapper(..., env_id=job.task, ...)` **仍传原任务名**（原因见第三部分）。planner 选择仍按 `job.task in STICK_TASKS`，不受新名字影响。 |
| ⑤ 失败换 seed | `bump` 换 seed 重试 | **不换 seed**。新档的意义是"同一 seed 的更难版本"，失败就按原 seed 记失败，`attempt` 固定 0，`--max-attempts` 在该分支不可用。 |

调用关系一句话：

```text
--xhard xhard1
  → 读 train json 的 hard 记录，每条一张卡片（原 seed、原 episode、difficulty=hard）
  → worker 拿卡片：gym.make("PickHighlightXHard1", seed=原seed, difficulty="hard")
  → 注册表找到子类，子类只换了 configs["hard"] 里的一两个数，其余全是父类代码
  → RobommeRecordWrapper(env_id="PickHighlight") 照常录制、写 HDF5
```

## 4. 输出与身份

- 输出目录由 `--output-dir` 指定，派生档必须用独立目录，不与原 hard 混放。因 `env_id` 传原名，HDF5 文件名仍是 `PickHighlight_ep3_seed620301.h5`，与原 hard 同名，靠目录区分。
- 生成器现有的 `_write_metadata` 照常在输出目录写 `record_dataset_<task>_metadata.json`；`parameters` 里增记 `xhard、source_split、source_metadata_path` 及母样本记录数，供追溯。
- HDF5 内 `setup/difficulty` 仍为 `hard`，派生身份只在目录与生成器摘要里体现。

# 第二部分：每个 ENV 的继承怎么做

## 1. 为什么子类就够了

16 个任务里 13 个把三档参数写在类顶部的 `configs` 字典，代码里统一用 `self.configs[self.difficulty][...]` 读取。核查结果：

| 任务 | 次数所在键 | 读取方式 |
|---|---|---|
| PickHighlight | `pickup` | `configs[difficulty]["pickup"]`，`randperm` 后切片取前 n 个 |
| PickXtimes、SwingXtimes | `number_min / number_max` | `randint(min, max+1)` |
| PatternLock、RouteStick | `length` | 范围 |
| VideoRepick | `swap_min / swap_max` | `randint` |
| VideoUnmaskSwap、ButtonUnmaskSwap | `swap_min / swap_max、pick_min / pick_max` | `randint` |
| BinFill | 整段 config | 每色库存与目标 |
| VideoUnmask、ButtonUnmask、VideoPlaceButton、VideoPlaceOrder | `pick / targets / swap` 等 | 固定分支 |
| StopCube、InsertPeg、MoveCube | 无 `configs` | StopCube 的停止序号写死在 `_initialize_episode` 里的 `randint(2, 6)` |

`configs` 是类属性，Python 子类重新定义同名属性即可整体替换，父类的 `_load_scene、_initialize_episode、step、evaluate` 全部原样继承。

## 2. 子类文件的样子

拟议新增目录 `src/robomme/robomme_env/xhard/`，每个任务一个文件，例如 `PickHighlightXHard.py`：

```python
# 拟议代码，尚未实施。只覆盖 hard 档的一两个键，其余全部继承父类。
from mani_skill.utils.registration import register_env
from ..PickHighlight import PickHighlight


@register_env("PickHighlightXHard1")
class PickHighlightXHard1(PickHighlight):
    robomme_base_id = "PickHighlight"  # 供录像器按原任务名识别
    configs = {**PickHighlight.configs, "hard": {**PickHighlight.config_hard, "pickup": 4}}


@register_env("PickHighlightXHard2")
class PickHighlightXHard2(PickHighlight):
    robomme_base_id = "PickHighlight"
    configs = {**PickHighlight.configs, "hard": {**PickHighlight.config_hard, "pickup": 5}}
```

要点：

- `{**父类.config_hard, "pickup": 4}` 表示复制原 hard 的全部键，只改一个；`{**父类.configs, "hard": ...}` 表示 easy、medium 原样保留。这就是"沿用 Hard 全部配置、只改一两个参数"的字面实现。
- 传入 `difficulty="hard"` 后，父类 `__init__` 里的 `normalize_robomme_difficulty` 原样解析出 `self.difficulty = "hard"`，随后所有 `self.configs["hard"]` 读到的都是子类的新数。
- `robomme_base_id` 是拟议的类属性，告诉录像器"我本质上是 PickHighlight"，用途见第三部分。
- 新档的具体数字（4／5 还是别的）属于"每个任务改什么"，本轮不定；文件结构先按上面定型。
- StopCube 这类没有 `configs` 的任务，子类需要重写 `_initialize_episode` 把写死的 `randint(2, 6)` 换成新范围，其余照旧继承；改法也在同一个新文件里，仍不碰原文件。
- 子类不注册 `max_episode_steps` 等额外参数，与父类 `@register_env` 保持同样的签名。

## 3. 随机流提示（接口定稿后再议）

PickHighlight 是先 `randperm` 全部方块再切片，改 `pickup` 不动随机流，母布局完全相同、新档是严格前缀。`randint(min, max)` 类任务改范围后抽到的次数变了，生成器调用次数不变，但下游若依赖该次数则场景会微变。是否要求"母布局逐项相等"是每任务的决策，不属于本轮接口定义。

# 第三部分：除生成器和新增文件外，还要改什么

## 1. 必改：让新子类被注册

`@register_env` 只有在模块被 import 时才执行。现有 `src/robomme/robomme_env/__init__.py` 用 `from .PickHighlight import *` 等逐个导入 16 个任务。需要在末尾加一行 `from .xhard import *`（并在 `xhard/__init__.py` 里导入各子类文件），否则 `gym.make("PickHighlightXHard1")` 找不到名字。这是一行改动。

## 2. 必改：录像器按原任务名识别（三处取名改成一个小函数）

`src/robomme/env_record_wrapper/RecordWrapper.py` 有两类按任务名分支的逻辑：

- 传入的 `self.env_id`：用于 HDF5 文件名、视频名，以及 `task_goal.get_language_goal(self.env, self.env_id)`。`get_language_goal` 内部是 `if env == "BinFill": ... elif env == "PickHighlight": ...` 这样按字符串分支；`get_vqa_options(..., env_id)` 同样用 `OPTION_BUILDERS.get(env_id, _options_default)` 查表。**名字对不上就会退到默认分支，语言目标和 VQA 选项直接出错。** 这就是生成器必须传 `env_id=job.task`（原名）的原因。
- 自取的 `self.unwrapped.spec.id`：录像器有三处写的是 `getattr(getattr(self.unwrapped, "spec", None), "id", None) or self.env_id`，即优先用环境注册名。新子类的注册名是 `"PatternLockXHard1"`，会导致 `_STICK_IDS = ("PatternLock", "RouteStick")` 判断失效、VQA 选项查表落空。

拟议最小改法：在 `RobommeRecordWrapper` 里加一个小方法

```python
# 拟议代码，尚未实施。
def _task_id(self) -> str:
    base = getattr(self.unwrapped, "robomme_base_id", None)
    spec_id = getattr(getattr(self.unwrapped, "spec", None), "id", None)
    return base or spec_id or self.env_id
```

把那三处 `getattr(getattr(self.unwrapped, "spec", None), "id", None) or self.env_id` 替换为 `self._task_id()`。原 16 个任务没有 `robomme_base_id`，走 `spec_id`，行为与现在完全一致；新子类走 `robomme_base_id`，被识别为原任务。改动是三处同一表达式换成一个调用，不触碰录制、写 HDF5 或 reset 逻辑。

## 3. 不改的文件

| 文件 | 原因 |
|---|---|
| `src/robomme/robomme_env/<16 个原任务>.py` | 子类覆盖即可。 |
| `src/robomme/robomme_env/utils/difficulty.py` | `difficulty` 仍只有 easy／medium／hard。 |
| `task_goal.py、subgoal_language.py、vqa_options.py` | 按原任务名工作；若某任务的语言模板写死了次数，属于"每个任务改什么"的范围，另议。 |
| `scripts/data-generation-newSeed/seed_layout.py` | 派生档不用公式 seed。 |
| `src/robomme/env_metadata/train/*.json` | 只读，不追加、不改写。 |
| planner、`_execute_tasks`、HDF5 结构 | 不动。 |

## 4. 改动清单汇总

| 文件 | 改动量 | 性质 |
|---|---|---|
| `scripts/data-generation-newSeed/generate_dataset_newseed.py` | `--xhard、--source-split` 与互斥校验；`EpisodeJob.xhard`；读 train hard 记录造卡片；`gym.make` 拼名字；该分支不 `bump`；摘要增记来源 | 唯一的生成器改动 |
| `src/robomme/robomme_env/xhard/` 下新增文件 | 每任务一个文件、每档一个子类，只覆盖 `configs["hard"]` 的一两个键（StopCube 重写一个方法） | 新增 |
| `src/robomme/robomme_env/__init__.py` | 加一行导入 | 一行 |
| `src/robomme/env_record_wrapper/RecordWrapper.py` | 新增 `_task_id()`，三处取名改为调用它 | 小改，不动录制逻辑 |
| `tests/lightweight/test_xhard_interface.py`（拟议） | 校验：不传 `--xhard` 时卡片与 `gym.make` 名字与现在一致；传入时卡片来自 train hard 记录且 seed 原样；互斥参数报错；子类 `configs` 除目标键外与父类相等；`_task_id()` 对原任务返回 `spec.id`、对子类返回 `robomme_base_id` | 新增 |

# 后续待定（本轮不展开）

- 每个任务覆盖哪些键、改成什么数：另起章节，逐任务批准后再写。
- 随机流是否要求母布局逐项相等：按任务决定。
- 对拍矩阵（不传／同 seed 原 hard／新档）：接口实施并通过轻量测试后再定预算。
- 新 seed 的派生：用户明确"以后再说"，本方案不涉及。
