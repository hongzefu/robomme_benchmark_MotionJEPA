> 本文按用户最新要求改为"子类继承"接口方案，并把全部新增内容归档到 `src/` 下一个独立包里；只改计划，不构成开工令。本轮只定义接口，不展开每个任务具体改哪些次数，那部分待接口定稿后另议。工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支为 `newtask-v3-MotionJepa1006`。本次修订前 HEAD 为 `ddd914c2`；原源码核查锚点为 `13905997d45155ff1c98417511aedec92578042d`，生成代码起点为 `3a5951a834ea014f63724647ab0bc091eb9f109d`。ManiSkill 来源仍钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，依赖以本分支 `pyproject.toml、uv.lock` 为准。文中所有新名字、新参数、新文件均为拟议项，尚未实施。

# 设计目标

用户的要求是：沿用 Hard 的所有配置，只在一两个参数上改动，比如 pick 5 次变成 pick 7 次；seed 先用现有的，直接拿 `src/robomme/env_metadata/train` 里已经生成过原版 hard 的那组 seed；新增部分用独立的 ENV 文件表示；所有改动只限于生成器 `generate_dataset_newseed.py` 这一个文件和新增的那些文件；新 seed 的事以后再说。后来又补充：把所有改的部分全部归档在一起，放在 `src` 里面。

所以本方案守住五条：原 16 个 ENV 文件一个字节不改；新档的全部差异只写在 `src/robomme_xhard/` 这一个新包里；生成器只加一个开关和一处拼名字的逻辑，逻辑本身也放在新包里，生成器只是调用；seed 直接取 train metadata 中 hard 记录的原 seed，不重算也不换；录像器和各种 wrapper 一个字不改，让子类自己把注册名"报成"原任务名。

# 第一部分：现在的脚本是怎么传参的，新参数接在哪里

## 先看现在的脚本是怎么跑的，分五环

第一环是命令行。你敲 `--env PickHighlight --episodes 100 --difficulty 211` 这类参数，`_args` 把它们读进来，交给 `generate_dataset_newseed` 这个函数。

第二环是排任务单。这个函数给每个 episode 造一个 `EpisodeJob`，可以理解成一张卡片，上面写着 task 名、episode 号、seed、difficulty、输出目录这几样。现在 seed 是用 `layout.seed(task, episode, attempt)` 公式算出来的，difficulty 是按 211 的比例轮着排的。100 个 episode 就是 100 张卡片。

第三环是发给工人。卡片扔进进程池，每个 worker 进程拿一张，执行 `_worker(job)`。

第四环是工人造环境并录制，这是最关键的一环。`_worker` 里真正和环境打交道的只有这几句：先拼一个 kwargs，里面是 obs_mode、control_mode、render_mode、reward_mode，再加上 `seed=job.seed` 和 `difficulty=job.difficulty`；然后 `base_env = gym.make(job.task, **kwargs)`；再用 `RobommeRecordWrapper(base_env, dataset=输出目录, env_id=job.task, episode=job.episode, seed=job.seed, save_video=True)` 把环境包一层；接着 `record_env.reset()`；再按 `job.task in STICK_TASKS` 决定用 stick planner 还是 arm planner；最后 `_execute_tasks` 让 planner 按 task_list 一步步做，录像器一路录 RGB、动作，最后写成 HDF5，文件名是 `{env_id}_ep{episode}_seed{seed}.h5`。

这里面 `gym.make(job.task)` 这一句要特别理解：它是拿着名字 `"PickHighlight"` 去 ManiSkill 的注册表里查，找到当初用 `@register_env("PickHighlight")` 登记的那个 class，然后 `PickHighlight(seed=..., difficulty="hard", ...)` 把它实例化。新档要做的，就是让这一句去找另一个 class。

第五环是失败换 seed。场景生成失败、planner 卡死这类情况，脚本调 `job.bump(新seed)` 换一个 seed 重来，最多重试到 `--max-attempts`。

## 新参数只加一个 `--xhard`

拟议加两个命令行参数。`--xhard` 可以不传，或者传 `xhard1`、`xhard2`。不传时脚本和现在完全一样，走原路径。传了就进入派生档分支。`--source-split` 默认 `train`，只在传了 `--xhard` 时生效，指定从 `src/robomme/env_metadata/<split>/` 读母样本。

传了 `--xhard` 之后，就不允许再传 `--difficulty`（比例）、`--layout`、`--episodes`、`--episode-start`、`--max-attempts` 这几项，传了就报错。原因是这几项都是公式 seed 那套的东西，派生档的 seed 来自 json，两套混用会说不清楚。

`EpisodeJob` 这张卡片加一栏 `xhard`，默认是空，原路径不受影响。

## 传了 `--xhard` 之后五环各自怎么变

第一环命令行，多解析 `--xhard` 和 `--source-split`，做上面说的互斥校验。

第二环排任务单变化最大，但生成器自己不写这段逻辑，而是调用新包里的 `robomme_xhard.jobs_from_metadata(tasks, split, xhard, output_root)`。这个函数打开 `src/robomme/env_metadata/train/record_dataset_<task>_metadata.json`，文件里每条记录长这样：`{"task": "BinFill", "episode": 3, "seed": 4301, "difficulty": "hard"}`。只挑 difficulty 是 hard 的记录，每条造一张卡片，task、episode、seed 原样抄过来，difficulty 固定写 hard，xhard 写成 `xhard1`。原来那个"seed 不能越过下一代布局 offset"的护栏在这个分支跳过，因为它只对公式 seed 有意义。

第三环发给工人，不变。

第四环造环境，只改名字。`gym.make(job.task, **kwargs)` 改成 `gym.make(robomme_xhard.make_name(job), **kwargs)`。`make_name` 的规则是：卡片的 xhard 为空就原样返回 `job.task`，否则返回 `f"{job.task}XHard1"` 这样的新名字。kwargs 一个不改，difficulty 还是 hard，seed 还是原 seed。注册表会找到新包里的子类，用同一个 seed 把它造出来。`RobommeRecordWrapper(..., env_id=job.task, ...)` 这一句不用改，因为 `job.task` 本来就是原名 `"PickHighlight"`。planner 的选择还是按 `job.task in STICK_TASKS`，同样是原名。后面 reset、planner、录制全走原路。

第五环，派生档不换 seed。新档的意义就是"同一个 seed 的更难版本"，失败就按原 seed 记成失败，attempt 固定为 0，不调用 `bump`。

另外生成器文件顶部要加一句 `import robomme_xhard`。这一句的作用是触发新包里所有 `@register_env` 执行，让新名字进入注册表。不加这句，`gym.make("PickHighlightXHard1")` 会找不到名字。因为是生成器自己 import，原来的 `robomme_env/__init__.py` 就不用动了。

把整条链串起来就是：

```text
--xhard xhard1
  → 生成器 import robomme_xhard，新子类完成注册
  → robomme_xhard.jobs_from_metadata 读 train json 的 hard 记录，每条一张卡片（原 seed、原 episode、difficulty=hard）
  → worker 拿卡片：gym.make(robomme_xhard.make_name(job)) 即 gym.make("PickHighlightXHard1", seed=原seed, difficulty="hard")
  → 注册表找到子类，子类只换了 configs["hard"] 里的一两个数，其余全是父类代码
  → RobommeRecordWrapper(env_id=job.task) 照常录制、写 HDF5
```

## 输出放哪、身份怎么分

输出目录由 `--output-dir` 指定，派生档必须用一个独立目录，不和原 hard 混放。因为 env_id 传的是原名，HDF5 文件名还是 `PickHighlight_ep3_seed620301.h5`，和原 hard 的同名，靠目录区分。生成器现有的 `_write_metadata` 照常在输出目录写一份 `record_dataset_<task>_metadata.json`，`parameters` 里多记 xhard、source_split、源 json 路径和母样本条数，方便追溯。HDF5 里的 `setup/difficulty` 仍然是 hard，派生身份只在目录和生成器摘要里体现。

# 第二部分：每个 ENV 的继承是怎么做的

## 为什么子类就够了

我把 16 个任务文件都查了一遍。除了 StopCube、InsertPeg、MoveCube 三个，其它 13 个都把三档参数写在类顶部的 `configs` 字典里，代码里统一用 `self.configs[self.difficulty][...]` 去读。具体来说，PickHighlight 读 `pickup`，而且是先把 6 个方块 `randperm` 随机排好序，再切片取前 n 个；PickXtimes 和 SwingXtimes 读 `number_min`、`number_max`，用 `randint` 抽次数；PatternLock 和 RouteStick 读 `length` 范围；VideoRepick 读 `swap_min`、`swap_max`；VideoUnmaskSwap 和 ButtonUnmaskSwap 读 `swap_min`、`swap_max`、`pick_min`、`pick_max`；BinFill 读整段 config 决定每色库存和目标；VideoUnmask、ButtonUnmask、VideoPlaceButton、VideoPlaceOrder 读 `pick`、`targets`、`swap` 这些固定分支。StopCube 没有 `configs`，它的"第几次经过时停"写死在 `_initialize_episode` 里的 `randint(2, 6)`。InsertPeg 和 MoveCube 没有 `configs`，本来也不打算改。

既然"几次"只是字典里的一个数，那要改它就不用碰读它的那些代码，只要换一本字典。`configs` 是类属性，Python 子类重新定义同名属性就能整体替换，父类的 `_load_scene`、`_initialize_episode`、`step`、`evaluate` 全部原样继承。

## 子类文件长什么样

子类文件放在新包 `src/robomme_xhard/envs/` 下，每个任务一个文件。以 `pick_highlight.py` 为例：

```python
# 拟议代码，尚未实施。只覆盖 hard 档的一两个键，其余全部继承父类。
from mani_skill.utils.registration import register_env
from robomme.robomme_env.PickHighlight import PickHighlight
from ..base import XHardMixin


@register_env("PickHighlightXHard1")
class PickHighlightXHard1(XHardMixin, PickHighlight):
    robomme_base_id = "PickHighlight"
    configs = {**PickHighlight.configs, "hard": {**PickHighlight.config_hard, "pickup": 4}}


@register_env("PickHighlightXHard2")
class PickHighlightXHard2(XHardMixin, PickHighlight):
    robomme_base_id = "PickHighlight"
    configs = {**PickHighlight.configs, "hard": {**PickHighlight.config_hard, "pickup": 5}}
```

这几行逐句解释。`{**PickHighlight.config_hard, "pickup": 4}` 是把原来 hard 的全部键复制一份，只把 pickup 换成 4。`{**PickHighlight.configs, "hard": ...}` 是把三档字典复制一份，只换 hard 那一项，easy 和 medium 原样保留。这就是"沿用 Hard 全部配置、只改一两个参数"的字面实现。`@register_env("PickHighlightXHard1")` 给子类登记一个新名字，生成器就靠这个名字找到它。`robomme_base_id = "PickHighlight"` 是告诉 `XHardMixin`"我本质上是 PickHighlight"，`XHardMixin` 是什么在第三部分讲。

运行时你传 `difficulty="hard"`，父类 `__init__` 里的 `normalize_robomme_difficulty` 原样解析出 `self.difficulty = "hard"`，之后所有 `self.configs["hard"]` 读到的都是子类的新数。原来的 PickHighlight 文件没有被动一个字。

新档具体改成几（4 还是 5 还是别的）属于"每个任务改什么"的范围，本轮不定，这里只把文件结构定型。

StopCube 这类没有 `configs` 的任务，子类要重写 `_initialize_episode`，把写死的 `randint(2, 6)` 换成新范围，其余照旧继承。改法也写在同一个新文件里，仍然不碰原文件。

子类注册时不加 `max_episode_steps` 之类的额外参数，和父类的 `@register_env` 保持一样。

## 随机流的提示，接口定稿后再议

PickHighlight 是先把全部方块随机排序再切片，改 pickup 不动随机流，母布局完全相同，新档是严格的前缀。用 `randint(min, max)` 抽次数的任务，改了范围后抽出的数不同，生成器调用次数没变，但下游如果依赖这个数，场景会跟着微变。要不要求"母布局逐项相等"是每个任务各自的决定，不属于本轮接口定义。

# 第三部分：所有新增内容归档在 `src/robomme_xhard/` 一个包里

## 这个包里放什么

你问能不能把所有改的部分放到 `src/robomme-xhard` 一起归档。可行，只是 Python 的包名不能带连字符，所以目录叫 `src/robomme_xhard/`，和 `src/robomme/` 并排。包里拟议四样东西。

第一是 `base.py`，放一个 `XHardMixin`，所有子类都混入它。它只做一件事，就是把环境的注册名"报成"原任务名，细节下面单独讲。

第二是 `envs/` 目录，每个任务一个文件，每档一个子类，就是第二部分那种写法。`envs/__init__.py` 把各文件 import 一遍，这样 `import robomme_xhard` 一句就能让全部 `@register_env` 执行完。

第三是 `jobs.py`，放两个函数。`jobs_from_metadata` 负责读 train 的 hard 记录、造卡片；`make_name` 负责按卡片的 xhard 拼出 `gym.make` 要用的名字。生成器只调用这两个函数，自己不写逻辑。

第四是 `README.md`，中文说明这个包是干什么的、怎么加一个新任务的子类、怎么跑。

## 为什么录像器和 wrapper 都可以不改

上一版计划说要在 `RecordWrapper.py` 加一个 `_task_id()` 方法。这次我又查了一遍，发现按注册名分支的地方远不止录像器那三处。`DemonstrationWrapper.py` 有六处 `self.unwrapped.spec.id`，判断是不是 PatternLock 或 RouteStick、取语言目标、取 VQA 选项；`MultiStepDemonstrationWrapper.py` 有两处；`EndeffectorDemonstrationWrapper.py` 有一处判断是不是无夹爪环境。如果逐个去改，就得动四个 wrapper 文件、十几处，和"全部归档在一起"的要求背道而驰。

所以换一个思路：既然大家都是去读 `self.unwrapped.spec.id`，那就让子类自己把 `spec.id` 报成原任务名，所有读的地方自然都对了。`gym.make` 的流程是先实例化 class，再执行 `env.unwrapped.spec = spec_` 把注册信息挂上去。Python 允许在子类里把 `spec` 定义成带 setter 的 property，这样赋值那一刻会被拦截，我们把 id 换成原名再存起来：

```python
# 拟议代码，尚未实施。放在 src/robomme_xhard/base.py。
import dataclasses


class XHardMixin:
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

效果是：`gym.make("PickHighlightXHard1")` 造出来的环境，任何人读 `env.unwrapped.spec.id` 得到的都是 `"PickHighlight"`，`spec` 里的其它字段（entry_point、max_episode_steps 等）原样保留。录像器的 stick 判断、语言目标、VQA 查表、无夹爪判断全部按原任务走，四个 wrapper 文件一个字不改。原 16 个任务没有混入这个 Mixin，行为完全不受影响。

这个 property 拦截的做法在实施时要先做一个最小 smoke：`gym.make` 一个子类，断言 `unwrapped.spec.id` 等于原名、外层 wrapper 的 `spec.id` 也等于原名、`spec.entry_point` 没变。本轮没有可用的虚拟环境，这一点还没有实跑验证，列为实施第一步。

另外要确认一下 `BaseEnv` 自己有没有把 `spec` 当普通属性用。`gym.Env` 只是声明了 `spec = None` 这个类属性，子类的 property 会覆盖它，预计没有冲突，但同样在 smoke 里核实。

## 生成器还剩哪几处要改

生成器 `scripts/data-generation-newSeed/generate_dataset_newseed.py` 是唯一要动的旧文件，改动缩到四处，每处一两行。

第一处，文件顶部 `import robomme_xhard`，触发注册。

第二处，`_args` 加 `--xhard` 和 `--source-split`，以及互斥校验。

第三处，`generate_dataset_newseed` 里排任务单那段：如果传了 xhard，就 `jobs = robomme_xhard.jobs_from_metadata(...)`，否则走原来的列表推导。`EpisodeJob` 加一栏 `xhard: str | None = None`。

第四处，`_worker` 里 `gym.make(job.task, **kwargs)` 改成 `gym.make(robomme_xhard.make_name(job), **kwargs)`；重试那段加一个判断，xhard 不为空时不 `bump`。

## 包怎么被安装到

`pyproject.toml` 用的是 hatchling，`[tool.hatch.build.targets.wheel]` 里 `packages = ["src/robomme"]` 写死了只打包 `robomme`。新包要能 `import robomme_xhard`，这一行得改成 `packages = ["src/robomme", "src/robomme_xhard"]`，然后 `uv sync` 一次。这是除生成器之外唯一要碰的旧文件，而且只是一行配置。

如果你连这一行都不想改，备选是把包放到 `src/robomme/xhard/`，作为 `robomme` 的子包自动被打包，生成器写 `import robomme.xhard`。代价是新东西混在原包目录里，没有并排那么干净。两种都可行，我倾向并排放 `src/robomme_xhard/`，改一行配置换来彻底隔离。

## 不改的文件

原 16 个任务文件不改。`robomme_env/__init__.py` 不改，注册由生成器 import 新包触发。`RecordWrapper.py`、`DemonstrationWrapper.py`、`MultiStepDemonstrationWrapper.py`、`EndeffectorDemonstrationWrapper.py` 四个 wrapper 不改，靠 `XHardMixin` 报原名。`utils/difficulty.py` 不改。`task_goal.py`、`subgoal_language.py`、`vqa_options.py` 不改；如果某个任务的语言模板写死了次数，那是"每个任务改什么"的范围，另议。`seed_layout.py` 不改。`env_metadata/train` 下的 json 只读。planner、`_execute_tasks`、HDF5 结构都不动。

## 改动清单汇总

新增一个包 `src/robomme_xhard/`，里面是 `base.py`、`envs/`、`jobs.py`、`README.md`。

改两个旧文件：生成器四处小改，`pyproject.toml` 一行。

新增一个轻量测试 `tests/lightweight/test_robomme_xhard.py`，验证这几件事：不传 `--xhard` 时卡片内容和 `make_name` 返回的名字与现在一致；传了之后卡片确实来自 train 的 hard 记录、seed 原样没变；互斥参数会报错；每个子类的 `configs` 除了目标键之外和父类完全相等；`XHardMixin` 让 `unwrapped.spec.id` 返回原名且其它字段不变。测试放在 `tests/` 是沿用仓库现有约定，如果你希望测试也归进包里，可以放 `src/robomme_xhard/tests/`，pytest 一样能收。

# 后续待定，本轮不展开

每个任务覆盖哪些键、改成什么数，另起章节，逐任务批准后再写。随机流是否要求母布局逐项相等，按任务决定。对拍怎么做（不传、同 seed 的原 hard、新档三者比较），等接口实施并通过轻量测试后再定预算。新 seed 的派生，用户明确以后再说，本方案不涉及。
