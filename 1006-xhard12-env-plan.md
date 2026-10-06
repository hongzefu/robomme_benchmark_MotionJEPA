> 本文按用户最新要求改为"子类继承"接口方案，替代此前"ENV 内加 xhard 变量再 if/else"的设计；只改计划，不构成开工令。本轮只定义接口，不展开每个任务具体改哪些次数，那部分待接口定稿后另议。工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支为 `newtask-v3-MotionJepa1006`。本次修订前 HEAD 为 `f476610f`；原源码核查锚点为 `13905997d45155ff1c98417511aedec92578042d`，生成代码起点为 `3a5951a834ea014f63724647ab0bc091eb9f109d`。ManiSkill 来源仍钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，依赖以本分支 `pyproject.toml、uv.lock` 为准。文中所有新名字、新参数、新文件均为拟议项，尚未实施。

# 设计目标

用户的要求是：沿用 Hard 的所有配置，只在一两个参数上改动，比如 pick 5 次变成 pick 7 次；seed 先用现有的，直接拿 `src/robomme/env_metadata/train` 里已经生成过原版 hard 的那组 seed；新增部分用独立的 ENV 文件表示；所有改动只限于生成器 `generate_dataset_newseed.py` 这一个文件和新增的那些文件；新 seed 的事以后再说。

所以本方案守住五条：原 16 个 ENV 文件一个字节不改；新档的全部差异只写在新增的子类文件里，每个任务只覆盖一两个数；生成器只加一个开关和一处拼名字的逻辑；seed 直接取 train metadata 中 hard 记录的原 seed，不重算也不换；录像器允许稍微改一点，但只改"按原任务名识别"这一件事，不碰录制逻辑。

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

第二环排任务单变化最大。不再用公式算 seed，也不再按比例轮 difficulty，改成打开 `src/robomme/env_metadata/train/record_dataset_<task>_metadata.json`，这个文件里每条记录长这样：`{"task": "BinFill", "episode": 3, "seed": 4301, "difficulty": "hard"}`。只挑 difficulty 是 hard 的记录，每条造一张卡片，task、episode、seed 原样抄过来，difficulty 固定写 hard，xhard 写成 `xhard1`。原来那个"seed 不能越过下一代布局 offset"的护栏在这个分支跳过，因为它只对公式 seed 有意义。

第三环发给工人，不变。

第四环造环境，只改名字。先拼 `env_name`：如果卡片的 xhard 是空就用 `job.task`，否则拼成 `f"{job.task}XHard1"`，比如 `"PickHighlightXHard1"`。然后 `gym.make(env_name, **kwargs)`，kwargs 一个不改，difficulty 还是 hard，seed 还是原 seed。注册表会找到你新写的子类，用同一个 seed 把它造出来。接下来 `RobommeRecordWrapper(..., env_id=job.task, ...)` 这里要注意，env_id 仍然传原名 `"PickHighlight"`，不传新名字，原因在第三部分讲。planner 的选择还是按 `job.task in STICK_TASKS`，用原名判断，不受新名字影响。后面 reset、planner、录制全走原路。

第五环，派生档不换 seed。新档的意义就是"同一个 seed 的更难版本"，失败就按原 seed 记成失败，attempt 固定为 0，不调用 `bump`。

把整条链串起来就是：

```text
--xhard xhard1
  → 读 train json 里的 hard 记录，每条一张卡片（原 seed、原 episode、difficulty=hard）
  → worker 拿卡片：gym.make("PickHighlightXHard1", seed=原seed, difficulty="hard")
  → 注册表找到子类，子类只换了 configs["hard"] 里的一两个数，其余全是父类代码
  → RobommeRecordWrapper(env_id="PickHighlight") 照常录制、写 HDF5
```

## 输出放哪、身份怎么分

输出目录由 `--output-dir` 指定，派生档必须用一个独立目录，不和原 hard 混放。因为 env_id 传的是原名，HDF5 文件名还是 `PickHighlight_ep3_seed620301.h5`，和原 hard 的同名，靠目录区分。生成器现有的 `_write_metadata` 照常在输出目录写一份 `record_dataset_<task>_metadata.json`，`parameters` 里多记 xhard、source_split、源 json 路径和母样本条数，方便追溯。HDF5 里的 `setup/difficulty` 仍然是 hard，派生身份只在目录和生成器摘要里体现。

# 第二部分：每个 ENV 的继承是怎么做的

## 为什么子类就够了

我把 16 个任务文件都查了一遍。除了 StopCube、InsertPeg、MoveCube 三个，其它 13 个都把三档参数写在类顶部的 `configs` 字典里，代码里统一用 `self.configs[self.difficulty][...]` 去读。具体来说，PickHighlight 读 `pickup`，而且是先把 6 个方块 `randperm` 随机排好序，再切片取前 n 个；PickXtimes 和 SwingXtimes 读 `number_min`、`number_max`，用 `randint` 抽次数；PatternLock 和 RouteStick 读 `length` 范围；VideoRepick 读 `swap_min`、`swap_max`；VideoUnmaskSwap 和 ButtonUnmaskSwap 读 `swap_min`、`swap_max`、`pick_min`、`pick_max`；BinFill 读整段 config 决定每色库存和目标；VideoUnmask、ButtonUnmask、VideoPlaceButton、VideoPlaceOrder 读 `pick`、`targets`、`swap` 这些固定分支。StopCube 没有 `configs`，它的"第几次经过时停"写死在 `_initialize_episode` 里的 `randint(2, 6)`。InsertPeg 和 MoveCube 没有 `configs`，本来也不打算改。

既然"几次"只是字典里的一个数，那要改它就不用碰读它的那些代码，只要换一本字典。`configs` 是类属性，Python 子类重新定义同名属性就能整体替换，父类的 `_load_scene`、`_initialize_episode`、`step`、`evaluate` 全部原样继承。

## 子类文件长什么样

拟议新增目录 `src/robomme/robomme_env/xhard/`，每个任务一个文件。以 `PickHighlightXHard.py` 为例：

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

这几行逐句解释。`{**PickHighlight.config_hard, "pickup": 4}` 是把原来 hard 的全部键复制一份，只把 pickup 换成 4。`{**PickHighlight.configs, "hard": ...}` 是把三档字典复制一份，只换 hard 那一项，easy 和 medium 原样保留。这就是"沿用 Hard 全部配置、只改一两个参数"的字面实现。`@register_env("PickHighlightXHard1")` 给子类登记一个新名字，生成器就靠这个名字找到它。`robomme_base_id = "PickHighlight"` 是拟议的类属性，意思是"我本质上是 PickHighlight"，录像器靠它认回原任务，用途在第三部分讲。

运行时你传 `difficulty="hard"`，父类 `__init__` 里的 `normalize_robomme_difficulty` 原样解析出 `self.difficulty = "hard"`，之后所有 `self.configs["hard"]` 读到的都是子类的新数。原来的 PickHighlight 文件没有被动一个字。

新档具体改成几（4 还是 5 还是别的）属于"每个任务改什么"的范围，本轮不定，这里只把文件结构定型。

StopCube 这类没有 `configs` 的任务，子类要重写 `_initialize_episode`，把写死的 `randint(2, 6)` 换成新范围，其余照旧继承。改法也写在同一个新文件里，仍然不碰原文件。

子类注册时不加 `max_episode_steps` 之类的额外参数，和父类的 `@register_env` 保持一样。

## 随机流的提示，接口定稿后再议

PickHighlight 是先把全部方块随机排序再切片，改 pickup 不动随机流，母布局完全相同，新档是严格的前缀。用 `randint(min, max)` 抽次数的任务，改了范围后抽出的数不同，生成器调用次数没变，但下游如果依赖这个数，场景会跟着微变。要不要求"母布局逐项相等"是每个任务各自的决定，不属于本轮接口定义。

# 第三部分：除了生成器和新增文件，还要改什么

## 必改一：让新子类被注册

`@register_env` 只有在模块被 import 的时候才会执行。现在 `src/robomme/robomme_env/__init__.py` 是用 `from .PickHighlight import *` 这样逐个导入 16 个任务的。需要在末尾加一行 `from .xhard import *`，并在 `xhard/__init__.py` 里导入各个子类文件。不加这一行，`gym.make("PickHighlightXHard1")` 会找不到名字。这是一行改动。

## 必改二：录像器按原任务名识别

这一条解释了为什么 env_id 必须传原名，以及录像器要改哪里。

录像器 `src/robomme/env_record_wrapper/RecordWrapper.py` 里有两类按任务名分支的逻辑。

第一类用的是生成器传进来的 `self.env_id`。它决定 HDF5 文件名和视频名，还会传给 `task_goal.get_language_goal(self.env, self.env_id)`。我查了 `get_language_goal`，它内部是 `if env == "BinFill": ... elif env == "PickHighlight": ...` 这样按字符串分支的；`get_vqa_options(..., env_id)` 也是用 `OPTION_BUILDERS.get(env_id, _options_default)` 查表。名字对不上就会退到默认分支，语言目标和 VQA 选项直接出错。这就是生成器必须传 `env_id=job.task` 原名的原因，不能传新名字。

第二类是录像器自己去取的 `self.unwrapped.spec.id`。有三处写的是 `getattr(getattr(self.unwrapped, "spec", None), "id", None) or self.env_id`，意思是优先用环境的注册名，取不到才用传进来的 env_id。新子类的注册名是 `"PatternLockXHard1"`，拿这个名字去对那张写死的 `_STICK_IDS = ("PatternLock", "RouteStick")`，对不上，PatternLock 就会被当成普通抓取任务；VQA 选项查表也会落空。

拟议的最小改法是在 `RobommeRecordWrapper` 里加一个小方法：

```python
# 拟议代码，尚未实施。
def _task_id(self) -> str:
    base = getattr(self.unwrapped, "robomme_base_id", None)
    spec_id = getattr(getattr(self.unwrapped, "spec", None), "id", None)
    return base or spec_id or self.env_id
```

然后把那三处 `getattr(getattr(self.unwrapped, "spec", None), "id", None) or self.env_id` 换成 `self._task_id()`。原 16 个任务没有 `robomme_base_id` 这个属性，走 spec_id，行为和现在完全一样；新子类有这个属性，就被认成原任务。改动就是三处同一个表达式换成一个调用，不碰录制、写 HDF5 或 reset 的逻辑。

## 不改的文件

原 16 个任务文件不改，子类覆盖就够了。`utils/difficulty.py` 不改，difficulty 还是只有 easy、medium、hard 三个值。`task_goal.py`、`subgoal_language.py`、`vqa_options.py` 不改，它们按原任务名工作；如果某个任务的语言模板写死了次数，那是"每个任务改什么"的范围，另议。`seed_layout.py` 不改，派生档不用公式 seed。`env_metadata/train` 下的 json 只读，不追加、不改写。planner、`_execute_tasks`、HDF5 结构都不动。

## 改动清单汇总

总共动四个地方，外加一个测试文件。

第一是生成器 `scripts/data-generation-newSeed/generate_dataset_newseed.py`，这是唯一的生成器改动：加 `--xhard` 和 `--source-split` 及互斥校验；`EpisodeJob` 加 xhard 栏；读 train 的 hard 记录造卡片；`gym.make` 前拼名字；这个分支不 `bump`；摘要里多记来源。

第二是新增目录 `src/robomme/robomme_env/xhard/`，每个任务一个文件，每档一个子类，只覆盖 `configs["hard"]` 里的一两个键，StopCube 多重写一个方法。

第三是 `src/robomme/robomme_env/__init__.py`，加一行导入。

第四是 `src/robomme/env_record_wrapper/RecordWrapper.py`，新增 `_task_id()`，三处取名改成调用它，不动录制逻辑。

第五是拟议的轻量测试 `tests/lightweight/test_xhard_interface.py`，要验证这几件事：不传 `--xhard` 时卡片内容和 `gym.make` 用的名字与现在一致；传了之后卡片确实来自 train 的 hard 记录、seed 原样没变；互斥参数会报错；子类的 `configs` 除了目标键之外和父类完全相等；`_task_id()` 对原任务返回 spec.id、对子类返回 `robomme_base_id`。

# 后续待定，本轮不展开

每个任务覆盖哪些键、改成什么数，另起章节，逐任务批准后再写。随机流是否要求母布局逐项相等，按任务决定。对拍怎么做（不传、同 seed 的原 hard、新档三者比较），等接口实施并通过轻量测试后再定预算。新 seed 的派生，用户明确以后再说，本方案不涉及。
