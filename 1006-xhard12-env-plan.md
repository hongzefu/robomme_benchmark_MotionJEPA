> 本文是本分支“次数型 XHard1／XHard2”的实施候选方案，依据根 [readme.md](readme.md) 的需求与本轮用户提供的通用规则编写；不是开工令。代码核查锚点为 `13905997d45155ff1c98417511aedec92578042d`，生成代码起点仍为 `3a5951a834ea014f63724647ab0bc091eb9f109d`。唯一工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支为 `newtask-v3-MotionJepa1006`。提交编号沿用 `<大版本>.<小版本>[.<修订>] 中文描述`；本方案文档提交接续 `2.25`。外部 ManiSkill 来源钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，依赖以本分支的 `pyproject.toml` 与 `uv.lock` 为准。本轮仅核实源码、编写和检查方案；没有安装环境、改源码、生成轨迹或启动训练。每一实施阶段必须获得对应的明确“开工”，涉及 `src/robomme/` 的项目还要逐项批准。文中所有新增接口、次数和预算均是拟议项。

# 第一部分（给人看）

## 一、结论与已定口径

**可以直接在 ENV 内部实现，最简单的架构是“原生难度配置＋原任务循环”，再给现有生成器增加一个显式单档入口。** 不需要把场景导出后回注，也不需要在生成器外面用子类或运行时补丁改 ENV。新档表示为两个难度字符串 `xhard1`、`xhard2`，而不是一个难度字符串 `xhard12`。

但“能在 ENV 内部做”不等于“所有任务只增加两个字典”。最适合先打通的是 `PickHighlight`：原 hard 为 `spawn=6, pickup=3`，候选新档为 `spawn=6, pickup=4/5`，现有任务循环已经读取目标数。这个样例只需修改 **三个现有生产文件**：`utils/difficulty.py`、`PickHighlight.py`、`generate_dataset_newseed.py`，再增加定向验证。其余任务按第三节分组推进。

本轮用户原话：

> 参考这个我现在 README 的实现方式，告诉我最简单的实现 XHR 的零 XHR 一的方式是什么。能不能直接在 ENV 内部改，就是加入新的配置xhard12
>
> 给出方案落实在根目录，写方案的规则参考现在的 Agent Markdown，Cloud Markdown。

随后用户澄清原话：

> 澄清一下，就是用Hard的布局，但是把任务做得长一些。

本文暂将“XHR”“xhard12”按当前 README 的 `XHard1／XHard2` 理解，将“Agent Markdown、Cloud Markdown”对应到 `AGENTS.md、CLAUDE.md`。如果用户实际要求 `xhard0／xhard1` 或一个单独的 `xhard12`，应先修改本方案的命名口径，再实施。

已经确定、不能由本方案擅自更改的口径如下。

1. 原三档完整复用，README 保留的用户原话是：“已有原版三档数据继续复用，只新生成 XHard1/2”。原 HDF5、metadata 不被覆盖。依据见第二节和第四节。
2. 只增加已有动作次数，保持物体、颜色规则、区域、相机、机器人初态、速度与成功语义。新档不能借用 NewTask 发布分支的同名配置，因为那里还改变过布局等因素。依据见第二、三节。
3. `MoveCube、InsertPeg` 不增加新档，README 保留的用户原话是：“严格只改已有次数参数，这两项保留原版三档”。其他容量不足任务也不能自动扩展语义。依据见第三节。
4. 每个最终新档轨迹只录制一次，encoder 和 VLA 从同一份完整原始 HDF5 派生输入。生产生成不先录制 hard 完整轨迹；验证用的 hard 对照单独计入预算。依据见第四、五节。
5. 新档母场景固定使用 hard，用户已明确：“就是用Hard的布局，但是把任务做得长一些”。建议生产中两档使用不同新 seed，减少共享母布局与失败重跑的耦合；是否共享同一母布局仍待确认，不能把母档的确认延伸成 seed 配对的确认。依据见第二、四节。
6. 首轮建议只打通 `PickHighlight`，再扩展其余可以严格成立的任务；次数表不是批准表。依据见第三、六节。

## 二、ENV 内最小机制：目标档与母场景分开

### 2.1 原生配置保存次数，默认三档行为保留

当前 [utils/difficulty.py](src/robomme/robomme_env/utils/difficulty.py)::`normalize_robomme_difficulty` 只允许 `easy/medium/hard`。因此，即使 ENV 已有 `configs['xhard1']`，`gym.make(..., difficulty='xhard1')` 仍会先报错。

拟为解析器增加一个默认关闭的 `allowed_difficulties` 参数：未传入时仍只接收原三档；获准 ENV 显式传自己的 `configs.keys()`，才接受已经实现的新档。未改的 `MoveCube、InsertPeg` 等继续走默认三档限制，避免全局放行后在场景构造中才出现 `KeyError`。同时，生成器在建进程池前检查任务支持名单；第一阶段名单只含 `PickHighlight`，不能把 `--env all` 静默过滤成一部分任务。

以 [PickHighlight.py](src/robomme/robomme_env/PickHighlight.py)::`config_hard、configs、__init__、_load_scene` 为例，拟议结构如下；不是当前已有代码：

```python
# 候选次数，批准后才加入 ENV。
config_xhard1 = {**config_hard, "pickup": 4}
config_xhard2 = {**config_hard, "pickup": 5}
# configs 中分别加入 xhard1、xhard2；不修改 config_hard。

self.difficulty = normalize_robomme_difficulty(
    kwargs.pop("difficulty", None),
    allowed_difficulties=self.configs.keys(),
)
# difficulty 未显式提供时，仍执行原来的三档选择代码。
self.layout_difficulty = (
    "hard" if self.difficulty in {"xhard1", "xhard2"}
    else self.difficulty
)
scene_config = self.configs[self.layout_difficulty]
count_config = self.configs[self.difficulty]
```

物体生成读取 `scene_config['spawn']`，目标切片、任务循环与高亮读取 `count_config['pickup']`。不能把 easy、medium 的 `layout_difficulty` 也无条件写成 hard。配置必须用新字典，不原地修改 `config_hard`，否则同 worker 后续运行旧档也可能被污染。

对 `PickXtimes、SwingXtimes、RouteStick`，当前场景字段与次数字段已经基本分开，复制 hard 配置并只改次数即可；不为统一形式重写所有原版采样代码。`layout_difficulty` 用于表达和记录母档；只有确实需要区分场景读取的地方才改消费点。

每个获准 ENV 实施前都必须列出全部 `difficulty/configs` 消费锚点，逐个分类为“母布局／次数目标／任务与语言成功条件”。凡 `== 'hard'`、`!= 'hard'` 或按难度查表的布局分支，新档都按 hard 口径走；不能只在构造函数新增一个母档属性而遗漏后续分支。分类清单与代码对照留在验收报告，判定 `HARD_LAYOUT_BRANCHES=PASS tasks=N consumers=M unclassified=0`，有未分类项即停。

### 2.2 为什么 PickHighlight 可以保住母场景

[PickHighlight.py](src/robomme/robomme_env/PickHighlight.py)::`_load_scene` 先播种 `self.generator`，生成按钮与全部 6 个方块，再执行目标排列和 `pickup` 切片。新档不改变 `spawn=6`，因此改变切片长度不会影响此前的物体、颜色、位姿抽样：

```text
同一个新 seed + hard 场景字段
    → 按钮与 6 个方块全部生成
    → 同一目标排列 P
hard   取 P[:3]
xhard1 取 P[:4]
xhard2 取 P[:5]
```

⚠ 同 seed 只是对照条件，布局保证还要检查实际字段；不能用 seed 相等替代物体、颜色、位姿、相机和机器人状态核对。这里只保证次数改变之前的母场景，不要求后续“额外拾取已经发生”的画面或物体状态仍与 hard 相同。

静态容量收益明确：仍只生成 6 块，物体数增量为 0；目标数从 3 到 4／5，分别增加 1／2 个目标。当前没有新档吞吐或耗时实测，不能据此填写性能提升。

### 2.3 生成器只补一个入口，不重新设计三档比例

现有 [generate_dataset_newseed.py](scripts/data-generation-newSeed/generate_dataset_newseed.py)::`_args、generate_dataset_newseed` 中的 `--difficulty` 是三位比例，例如 `211`；[seed_layout.py](scripts/data-generation-newSeed/seed_layout.py)::`DIFFICULTY_ORDER、parse_difficulty_ratio` 也只处理原三档。

最小建议是新增 **拟议** `--target-difficulty xhard1|xhard2`，与显式 `--difficulty` 互斥：

```text
未提供 target-difficulty：原来的 ratio、默认值、seed 公式与调度保持原样。
提供 target-difficulty：本次所有 job 使用这一目标档，母档 hard。
同时显式提供 ratio 与 target-difficulty：在建池、建 ENV 前报错。
```

不把 `--difficulty` 改成五位比例，也不把 `xhard12` 塞进 seed 公式。`EpisodeJob.difficulty` 继续传到 `gym.make`，ENV 的 `self.difficulty` 保持目标档；原录像器在 `close` 中从该属性写 `setup/difficulty`，因此能记录真正的 `xhard1/xhard2`。

母档、目标次数、场景指纹和文件指纹由生成器写入外部样本清单，不修改录像器或往原 metadata 回写。最小清单字段见第二部分第三节。

## 三、16 任务的实际边界与候选次数

以下来自锚点源码的静态核查。**所有新档数值均待批准，尚未仿真验证。** 首例用固定次数减少抽样解释，其余表中范围沿用现有字段的闭区间口径。总体可分为：5 个主要改配置的任务、4 个需要局部逻辑改动的任务、1 个库存受限任务、6 个本方案建议保留三档的任务。

| 任务及稳定锚点 | 原 hard 有效次数／容量 | xhard1／xhard2 候选 | 最小实现与边界 |
|---|---|---|---|
| `PickHighlight.config_hard、_load_scene、step、evaluate` | `spawn=6, pickup=3` | `pickup=4 / 5` | 配置型首例；不加物体，目标取原排列更长前缀。 |
| `PickXtimes.__init__、_load_scene、evaluate` | `number_min=4, number_max=5, color=3` | `6～7 / 8～9` | 次数生成器与场景生成器独立播种；保留 `color=3`，现有任务数 `2n+1`。 |
| `SwingXtimes.__init__、_initialize_episode、step` | `number_min=number_max=3, color=3` | `4～5 / 6～7` | 保留 3 色场景；任务数 `2n+3`，`max_swings=2n`；检查计数边沿。 |
| `RouteStick.configs、_load_scene` | `length=[4,7], backtrack=True` | `8～10 / 11～13` | 保留 hard 回退规则；布局在路径抽样之前生成。必须显式传难度，不能依赖其无提示时回到 easy 的旧行为。 |
| `PatternLock._load_scene、_initialize_episode、evaluate` | `grid=5, length=[4,8]` | `length=[9,12] / [13,16]` | 网格容量 25 个不重复节点；节点数 L 对应 L−1 条移动边。新档在 1000 次搜索未命中后报长度失败，不能沿用最后一条不合格路径。 |
| `VideoRepick.__init__、_load_scene、_initialize_episode` | `num_repeats=1～3`；hard 固定 15 块聚集布局，`swap=0` | `num_repeats=4～5 / 6～7` | 将硬编码 `randint(1,4)` 配置化；场景判断改读母档 hard，防止 `xhard*` 误入非 hard 的 3 块布局。 |
| `StopCube._initialize_episode、step、evaluate` | `stop_time=2～5`，运动仅 `range(5)`，速度档 `[60,80,120]` | 固定第 `6 / 8` 次经过 | 当前没有 `configs`；增加停止次数字段，新档延长运动段。保留速度与原随机调用顺序，包括结果被覆盖为 30 的 `interval` 抽样。 |
| `VideoUnmaskSwap._load_scene、_refresh_swap_schedule、step` | `bin=4, swap=2～3, pick=2` | 固定 `swap=4 / 5`，仍 `pick=2` | 需扩展超过 3 次的 pair 与调度；每段仍 50 步，最近邻伙伴规则不变。第 4／5 个发起者的选择规则须另行确认。 |
| `ButtonUnmaskSwap._load_scene、_refresh_swap_schedule、step` | 同上，另有原左右按钮流程 | 同上 | 与视频版同构；保留按钮顺序、布局与目标抓取数。 |
| `BinFill._load_scene、_initialize_episode、evaluate` | 10～12 块，3 色，投入总数 3～5；每色库存受旧目标影响 | 暂不定稿 | 必须先按 hard 完成库存与物体生成，再从冻结库存决定投入量；不保证所有母场景能支持两个新档。 |
| `VideoUnmask._load_scene` | hard `bin=15, pick=2`，实际仅 3 个隐藏物 | 暂不新增 | `pick>1` 只追加第二次动作；改为 3 需要任务和语言逻辑，4 已超容量。 |
| `ButtonUnmask._load_scene` | 同上 | 暂不新增 | 同样不能只改 `pick`；未使用的 `num_repeats` 不是可直接启用的次数接口。 |
| `VideoPlaceButton._load_scene` | 固定主放置与前后布尔分支，无任意次数字段 | 暂不新增 | 不能通过增加对象或重写前后语义凑两档。 |
| `VideoPlaceOrder._load_scene` | 4 个台，不重访，hard 已随机访问 2～4 个 | 暂不新增 | 同一原场景没有两个高于 hard 上限的访问档；不能引入重访规则。 |
| `MoveCube.evaluate` | 没有已有动作次数字段 | 不新增 | 按已定口径保留三档。 |
| `InsertPeg._initialize_episode` | 固定演示与执行各一次插入 | 不新增 | 按已定口径保留三档。 |

表中的 ENV 均位于 `src/robomme/robomme_env/`。配置型组也要通过实际次数与成功验收；`PatternLock` 不能只检查配置范围就声称实际路径达标。

两处需要特别说明的反例：

* **BinFill 不能只复制 hard 再提高 `put_in_numbers`。** `_load_scene` 先抽 `target_numbers`，再以 `spawn_numbers[i]=max(target_numbers[i],1)` 分配库存，最后按库存生成物体。因此目标变化会反过来改变颜色库存与布局。后续若实施，必须满足逐色 `target_i <= frozen_inventory_i`；不足即记容量失败，不能增物体、降目标或换 seed 挑成功。
* **Swap 增加次数还要定义第 4／5 次谁发起。** 最少代码的候选是循环复用原 `swap_indices` 三项：`0,1,2,0,1`，但这是待确认的扩展规则，不能称为原版已有行为。额外随机抽发起者则需要新增随机流和来源记录，也不能自行选。原 pair 局部索引与 bin 索引的现有实现差异本轮保留，不顺手修正。

## 四、改动前后链路与原始数据身份

改动前：

```text
--difficulty 211 + seed_layout（字符串与整数，无训练参数）
    → EpisodeJob(difficulty=easy/medium/hard, seed)
    → gym.make → 三档解析 → ENV 场景与 task_list
    → 原 planner → 原 RobommeRecordWrapper → close
    → 原始 HDF5，T 帧
       RGB：front/wrist 各 uint8[256,256,3]，各 196608 字节/帧
       joint_action：[8]，dtype 由实际动作决定，8×itemsize 字节/帧
       demo/exec、subgoal、is_completed：原记录接口
```

改动后：

```text
--target-difficulty xhard1/xhard2 + 获批的新 seed 区间
    → 起跑前：任务支持、身份/seed 查重、预算
    → EpisodeJob(difficulty=目标档, seed) + 母档 hard
    → gym.make → ENV 原 hard 母场景（对象/颜色/位置/相机/速度不改）
    → ENV 目标次数 → 原任务循环、原 planner（此处有意增加动作与帧数）
    → 原 RobommeRecordWrapper → close（记录代码不改）
    → 新原始 HDF5，T' 帧 + 外部 sample_manifest.jsonl
       RGB 尺寸/dtype/每帧字节量不改；joint_action shape/dtype 契约不改
       setup/difficulty=目标档；指令与次数、终态随实际任务核对
```

生成链路可训练参数为 0。增加次数会改变轨迹和 T，不能宣称新旧 HDF5 字节级一致；应逐位核对的是同环境同 seed 的母场景字段和旧档配置，成功行为另核对。

后续消费接口仅作为 README 的接口背景，不在本方案实施范围：33 帧 front RGB 为 `33×196608=6488064` 字节；冻结 Wan VAE 的 FP32 `[9,16,32,32]` latent 为 `589824` 字节，encoder 的 768 维 FP32 token 为 `3072` 字节。新旧消费端 shape、dtype、模型参数和超参本轮均不改；encoder 与 VLA 的窗口协议仍不同。VLA 的合法 motion 网格容量 160 等限制另行检查，不能在生成方案中静默截断。

新 seed 最简策略复用已有 `--layout`、`--episode-start`，不改 `seed_layout.py`：在选定布局中划出新档专属 episode 区间。具体布局、区间、每格局数尚未定，不能预填一个起始数字就认为绝对隔离。起跑前对每个 `(task, seed)` 与实际原版 train/val/test、已存在新数据逐项相交检查，同时对完整新 job 集合查重。仅检查“下一代 offset”不够；当前公式不同任务也可能得到相同整数 seed，检查应按任务身份解释。

生产建议 XHard1／2 使用不同新 seed；同母场景对照只在测试中使用。划分组键为 `(task, layout_difficulty, mother_seed)`；同组及重复 demo 不跨 train/val/test。清单记录成功与失败，不能从成功集合反推未记录的失败尝试。

## 五、验收、预算与结论边界

下表是未来验收要求，当前没有任何新档运行 PASS。每条判定须带命令、退出码、输出路径和审查摘要。

| 查什么 | 怎么查／为什么能成立 | 判定行与结论边界 |
|---|---|---|
| 默认与旧档 | 定向测试比较锚点三档配置、原 CLI 参数与新实现无新 flag 的 job；真实旧档回归单独预算 | `NATIVE_DEFAULTS=PASS changed_defaults=0`；仅证明已检查的默认和配置，不代替轨迹一致性。 |
| 解析与支持矩阵 | 支持任务接受两档；未支持任务直接调用 ENV 也在构造场景前拒绝；CLI 组合冲突 fail-fast | `DIFFICULTY_API=PASS unsupported_accepted=0 conflicts_accepted=0`。 |
| 母场景 | 单 seed 的 hard/xhard1/xhard2 在执行前比较物体名、颜色、位姿、相机、初态与速度；浮点保存 dtype、shape 与原始值，不能只比 seed | `NATIVE_LAYOUT=PASS mismatches=0`；对照条件和采样时点随报告列出。 |
| 次数范围上端与步数 | 推广随机范围时，用测试进程内明确的上端次数用例真实执行；不靠反复换seed碰上端，不把单局低端成功当整档可用 | `STEPS_HEADROOM=PASS task=... tier=... resolved_count=max elapsed_steps=... limit=2000 margin=...`；只证明该上端用例，非所有布局耗时上界。 |
| 实际次数 | 从任务与真实完成事件分别核对；指令、成功条件和计数一致；例如 PickHighlight 为 4/5 个不同目标 | `COUNT_ONLY=PASS task=PickHighlight tier=... expected=... actual=...`。 |
| 完整记录 | 检查连续 timestep、两路 RGB、状态/动作、完整 subgoal、demo/exec 与终态；比较实际 dtype，不依赖历史说明猜测 | `H5_CONTRACT=PASS missing=0 gaps=0`；独立报告 `TASK_SUCCESS=0|1`，正常退出不等于成功。 |
| 原件与身份 | 原数据指纹、全 job seed 集合、组划分和文件 SHA256/字节数 | `ORIGINAL_REUSE=PASS changed=0`、`SEED_ISOLATION=PASS overlaps=0 duplicates=0`、`SPLIT_ISOLATION=PASS shared_groups=0`。 |
| 录像器冻结 | `git diff --quiet 13905997d45155ff1c98417511aedec92578042d -- src/robomme/env_record_wrapper/RecordWrapper.py` | `RECORD_WRAPPER_FREEZE=PASS changed=0`；同时审查没有运行时覆盖。 |
| 尝试预算与失败处置 | reset 包括构造内部调用，轨迹尝试和基础设施重跑单列；每次起跑前有余额 | `BUDGET=PASS resets=... trajectories=... infra_retries=...`。 |

一致性分两块处理：第一块不启动训练，核对母布局与 HDF5 接口、任务数及实际动作；旧档的字节/结构/数值/行为结论分层陈述。第二块的真实训练梯度比较属于后续消费端适配计划，本方案不授权训练。新档动作有意改变，不能要求与短轨迹的 loss/梯度相同，也不能据一次新档回放宣布训练链路等价。

建议第一阶段从 **1 任务 × 1 新档 × 1 局 × 1 worker** 开始，`max_attempts=1`、基础设施自动重试为 0。XHard1 成功后再按同一批准预算补 hard 对照和 XHard2；初步完整首例合计 3 个环境录制 job、3 次轨迹尝试，按构造初始化和显式 reset 各一次估计 6 次 reset。初始化次数必须从钉死的 ManiSkill 版本和测试计数确认，不能只数源码显式调用；硬上限建议设为本阶段 10 次 reset、3 次轨迹尝试，超出即停。相同 seed 仅用于这三条对照，完整对照只涉及 1 个唯一 seed。

若推广到候选 9 任务，每任务 hard 对照加两个新档会变成 `9×3=27` 次轨迹尝试、约 54 次 reset，已经跨过 README 的全任务 50 次 reset 门槛。旧三档实跑回归、失败重跑还会增加预算。必须提前一次性批准完整矩阵，不能拆成多个 smoke 来绕过累计门槛。

P3的PickXtimes、SwingXtimes、RouteStick、PatternLock、VideoRepick使用随机次数范围，每档还须至少一次上端次数的真实执行，不能由抽到低端的一局推断整档通过。测试仅固定目标次数，不改变母场景、速度、planner或记录上限；这10个上端用例若不与已执行样本重合，还要追加10次轨迹尝试、约20次reset到预算。是否重合以实际resolved_count为准，不预先扣掉。上端检查失败即保留FAIL，请用户裁决，不自动缩窄次数范围。通过后仍持续对每局检查2000步守卫，不把一次上端成功当成所有布局都能在上限内完成的证明。

新档任务/容量/路径长度失败如实记录，默认不换 seed 再挑成功；基础设施重跑只允许明确分类、同 seed、有限次数并在预算内。当前 `_run_jobs` 会通过 `EpisodeJob.bump` 换 seed，因此这是生成器新档分支的必要改动，不能继承其默认 100 次尝试。

## 六、子代理分工与合并（简述）

主会话负责将受保护源码清单提交用户逐项批准，获批并开工后实施，先完成公共解析接口和首例 ENV。生成器、定向测试、文档分别由持久子代理负责互不重叠的文件；各 ENV 扩展可并行只读设计，但受保护文件不进入子代理可写集合。主会话按“解析器→首例→生成器→测试→只读审查”的顺序整合。

每块接入前核对文件归属、旧档差异和接口契约，接入后跑针对该块的检查与最终最小 smoke。子代理不暂存、提交或推送；共享测试数据只有一个运行负责人。推广其余任务前重新核对逐项批准与累计预算。

## 七、阶段与验收

| 阶段 | 内容 | 判据与开始条件 |
|---|---|---|
| P0：定稿 | 沿用已确认的hard母场景；确认命名、首例4/5、任务范围、新seed区间、环境及预算；逐项批准两个受保护源码项 | 第二部分闸门全部明确；“同意方案”不等于开工。 |
| P1：首例 | 三个生产文件打通 PickHighlight；新增定向验证，保留旧三档和录像器 | `NATIVE_DEFAULTS`、`DIFFICULTY_API`、`RECORD_WRAPPER_FREEZE`。 |
| P2：最小验证 | 先单档单局，再在预算内补母场景对照与第二档；两次新档各录一次 | `NATIVE_LAYOUT`、`COUNT_ONLY`、`H5_CONTRACT`、独立 `TASK_SUCCESS`、`BUDGET`。 |
| P3：可行组推广 | 对其余配置型任务及局部逻辑组逐项批准后接入；Swap规则先定稿；随机范围逐档真实验证上端 | 每任务两档分别验收并有 `STEPS_HEADROOM`；完整矩阵含上端样本，不能超过已批预算。 |
| P4：库存受限项 | 仅在另行批准后设计 BinFill 的目标/库存分离；其他6项保留三档 | 容量不足如实报告，不制造不存在的新档。 |
| P5：正式生成 | 另行确认每格局数、run_name、资产身份、预算、留档与开工 | clean HEAD、构建 Beta 锚点、所有前置闸门通过后才运行。 |

### 本轮静态核实结果

已核实 16 个 ENV 与生成入口的配置/消费链，区分上述 5＋4＋1＋6 分组；未录制轨迹。`pyproject.toml` 的 SHA256 为 `bc2346e4526c2b5c2177fe5191710c81f883c21017d45928e615327cf29cb21a`，`uv.lock` 为 `983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`。环境实测为 `sled-aspen.eecs.umich.edu`、2 张 RTX A6000，`/data` 与 NFS、SSH 配置可见，`/scratch/hongze` 不存在。项目缺少正式 A/B 判据表及 `greatlakes.md`；本轮路径以 README 明确的 Aspen 本机工作副本为准，正式实跑前还需确认环境口径，不安排集群作业。

本轮文档检查由独立于项目环境的标准库检查器经 `uv run --no-project --offline --no-python-downloads python -` 执行，检查方案正文、既存链接与bash围栏；退出0，输出 `PLAN_STRUCTURE=PASS h1=2 links=6 tasks=16 bash_blocks=2`、`HARD_LAYOUT_REQUIREMENT=PASS user_quote=1 mother=hard`。源码/脚本/测试/依赖/README/规则文件相对核查锚点的 `git diff --quiet` 退出0，记 `SCOPE_FREEZE=PASS tracked_changes=0`。方案文件位于仓库根目录；这组结果只证明文档结构与本轮范围，不能替代任何新档运行验收。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线与授权边界

R1. 本文只规划 ENV 次数型难度及其生成入口，未授权下载、环境安装、建库、评估或训练。现有根计划 `NEWTASK_V2_PLAN.md` 与历史账本不构成本轮授权，不覆盖、不执行其中的删除清单。

R2. 真正实施须有明确“开工”，且只覆盖对应阶段；受保护改动清单逐项批准是独立条件。`src/robomme/` 的落盘改动和生产运行时覆盖同样受控，不能通过 monkeypatch 绕过。测试进程内允许的计数观察应只用于测试，不进入生产入口。

R3. 录像器、planner、原 metadata、原件冻结；不提高 2000 步上限，不用截断、加速或强制成功帮助新档过关。`scripts/evaluation.py` 的 `max_steps=1300` 属另一个入口，本方案不修改、不据生成成功声称评估兼容。

R4. 全部持久产物收敛到本副本 `artifacts/`；验证临时 run 只清理本轮已核实目标。禁止覆盖旧 run、全局 tmux 清理、全量暂存及操作他人在途改动。规则文件不追加账本。

R5. 依赖通过 uv 管理，缓存显式 `UV_CACHE_DIR=$PWD/artifacts/cache/uv`。当前副本未安装依赖，不执行下面的仿真命令；需先按另行获准的环境准备范围 `uv sync --frozen`。不使用裸 Python/pip，不迁移其他副本的 venv。

R6. 所有后续报告区分“源码已核实、接口拟新增、运行未验证、实测通过”。失败不改判据、不放宽阈值；任务成功字段独立于进程退出状态。

## 一、首轮逐文件改动清单与逐项批准项

| 文件 | 锚点／改什么 | 为什么、关闭态与开启态 | 批准状态 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/difficulty.py` | `normalize_robomme_difficulty` 增加默认三档的 `allowed_difficulties`；显式集合须包含合法已知标签，拒绝错误类型与未知字符串 | 原调用继续只收三档；实现新档的 ENV 显式选择支持集合 | 受保护项 A，待逐项批准 |
| `src/robomme/robomme_env/PickHighlight.py` | `config_xhard1/2、configs、__init__、_load_scene`：候选4/5，母场景hard；任务/高亮读取目标档 | 原档配置、随机调用与任务路径保留；新档不加物体 | 受保护项 B，待逐项批准 |
| `scripts/data-generation-newSeed/generate_dataset_newseed.py` | `_args、generate_dataset_newseed、EpisodeJob、_execute_tasks、_worker、_run_jobs`：互斥单档参数、支持检查、种子查重、新档失败与清单 | 无新 flag 保留旧 ratio/默认/换seed规则；新档失败不挑seed，基础设施重跑独立计数 | 非保护项，P1开工后实施 |
| `tests/lightweight/test_xhard_count_config.py`（拟新增） | 解析兼容、非法标签、CLI互斥、支持矩阵、配置不污染、seed集合查重和新档失败处理 | 测试真实入口及错误路径；不靠逐句复刻实现来判断正确 | 非保护项，P1开工后实施 |
| `tests/dataset/test_xhard_count_generation.py`（拟新增） | 单局、单worker真实录制，母场景对照、实际目标事件、H5契约及reset计数 | 首先只跑单档；扩展对照受累计预算约束 | 非保护项，P1开工后实施 |
| `scripts/data-generation-newSeed/README.md` | 现有“目录内容”后补新档单档入口、支持列表、失败口径与身份清单 | 现有三档命令保留；新增叙述与注释中文 | 非保护项，P1开工后实施 |

首轮不新增独立采样框架、JSON 次数配置或新的生产生成器。次数唯一真源在获准 ENV 的配置；生成器只选择档位并记录 ENV 实际解析值。`seed_layout.py`、`RecordWrapper.py`、两种训练仓库均不在改动清单。

## 二、推广组的受保护项目

以下每行都是独立批准项；本方案写入不代表批准。尚未批准时只读设计，不派写入任务。

| 文件 | 函数／类锚点与拟改动 | 理由与禁扩范围 |
|---|---|---|
| `src/robomme/robomme_env/PickXtimes.py` | `config_*、configs、__init__`：新档次数与显式解析支持 | 保持 `color=3`，场景独立随机流不改，候选最大9次在现有序数1～10内。 |
| `src/robomme/robomme_env/SwingXtimes.py` | 同上；核对 `_initialize_episode、step` 的计数消费 | 保持目标圆盘与3色布局，不改摆动判定。 |
| `src/robomme/robomme_env/RouteStick.py` | `configs、__init__、_load_scene`：新路线长度，显式新档解析 | 保留障碍、布局和 `backtrack=True`；不修旧默认回easy行为。 |
| `src/robomme/robomme_env/PatternLock.py` | `configs、__init__、_load_scene`：新长度，新档搜索耗尽后失败 | 保留5×5、不重访与旧档原兜底；不提高搜索预算。 |
| `src/robomme/robomme_env/VideoRepick.py` | `__init__、_load_scene`：配置化重复次数；hard场景分支读母档 | 保留15块聚集布局与swap=0，保留原其他分支和抽样顺序。 |
| `src/robomme/robomme_env/StopCube.py` | `__init__、_initialize_episode、step`：新次数字典与新档运动段延长 | 先完整消费原hard的interval、速度、stop_time、rotation抽样，再仅覆盖停止序号为6/8；不删原stop_time抽样。逐值对拍rotation、起终点和方块初态，旧档仍5段。 |
| `src/robomme/robomme_env/VideoUnmaskSwap.py` | `configs、__init__、_load_scene、_refresh_swap_schedule`：新档pair和循环窗口 | 第4/5发起者规则先确认；旧档原分支、最近邻、50步与pick=2不改。 |
| `src/robomme/robomme_env/ButtonUnmaskSwap.py` | 同上 | 左右按钮、隐藏物与顺序不改；不顺手修索引现有行为。 |
| `src/robomme/robomme_env/BinFill.py` | 后续候选：`_load_scene、_initialize_episode` 分离旧母库存与新目标 | P4另定目标次数/颜色分配及容量失败口径，当前不实施。 |

`VideoUnmask.py、ButtonUnmask.py、VideoPlaceButton.py、VideoPlaceOrder.py、MoveCube.py、InsertPeg.py` 保留原三档，默认解析继续拒绝新标签。当前范围不修改 `task_goal.py、subgoal_language.py、vqa_options.py`；若发现候选次数无法由既有语言准确表达，暂停对应任务并另列受保护项目，不静默扩展。

## 三、接口、随机流与样本清单

新增 `--target-difficulty` 的选择值只有 `xhard1/xhard2`。参数与 ratio 互斥；实现要区分“旧参数未提供”与“用户显式提供”，不能仅因旧 ratio 有默认值就误判冲突，也不能把显式 ratio 静默忽略。新档运行记录 `difficulty_ratio=null`、`layout_difficulty=hard`；旧运行仍记录原 ratio/cycle。

`allowed_difficulties=None` 使用原三档；非空显式集合直接作为该ENV允许的集合，合法标签总集合包含原三档和xhard1/xhard2。不能先用旧 `VALID_DIFFICULTIES` 拒绝xhard再检查扩展集合，否则显式放行永远无效；未知标签和错误集合类型直接报错。

ENV 输出目标难度与实际次数；`_worker` 在执行前读取实际母场景与目标信息，并在 `close` 后记录文件 SHA256/字节数。`_execute_tasks` 在新档分支交回原有solve后或末次终态 `evaluate` 的 `success/fail` 快照，`_worker` 据此写独立 `task_success`；明确环境失败时也保留对应快照。不为取字段多调用一次可能推进任务的 `evaluate`，也不从 `ok` 或 H5 的 `is_completed` 反推成功。构造、容量、规划、代码或基础设施失败若没有最终求值证据，成功字段记为空并注明 `TASK_SUCCESS=NOT_OBSERVED` 与原因；不能把solve前的暂态false当作最终失败字段，也不能伪造PASS。请求数、完成数和各类失败仍完整对账，未观测不从分母中删除。清单最低字段：

```text
task, episode, difficulty, layout_difficulty, seed, mother_group
requested_count, resolved_count, observed_count, count_unit
mother_scene_fields, mother_scene_sha256, code_commit, uv_lock_sha256
attempt, infra_retry, failure_class, task_success, h5_path, h5_bytes, h5_sha256
reset_count, trajectory_attempt_count, elapsed_s
```

新档的 `attempt` 不再表示“为了任务成功更换seed”；首轮固定0。若后续获准基础设施重跑，另增 `infra_retry`，仍保持原seed，每次都记账。任务/库存/长度/规划失败不调用 `EpisodeJob.bump`；旧三档分支保留既有行为。进程池整体崩溃时，对受到影响的每个job记录基础设施失败，不能整体清空失败记录再当初次尝试。

成功快照的拟议返回契约仅对新档启用：`_execute_tasks` 成功时返回最后已有的终态求值；明确求值失败时，以生成器文件内拟新增的失败异常携带 `evaluation` 快照交给 `_worker`。原三档返回和异常路径保留。直接抛原异常却不携带字段，无法记录明确的 `task_success=0`，不得把这条传递路径留成隐式假设。其他没有最终求值的异常仍按未观测处理；成功字段只写外部清单，不改H5录像器。

清单在 `artifacts/generated/<run_name>/sample_manifest.jsonl`；原成功metadata继续只描述原有字段，不回写 `env_metadata/train`。两个目标档和不同分片各自使用独立run/output目录，不能向同一个目录连续写两档：当前 `_write_metadata` 会覆盖同名metadata，`merge_episode_h5.py::merge_task` 也不按难度筛选。单档合并仍复用现有脚本；新数据通过明确的metadata/H5路径消费，不把 `dataset='xhard1'` 假装成已有resolver选项。失败条目即使无H5也必须有完整身份，文件字段可以为空。清单与运行结果对账，以计划请求数为分母。

随机流分类：Pick/Swing 的次数生成器不进入场景随机流；PickHighlight目标取样在完整物体生成之后；RouteStick/PatternLock改变的是路径抽样及其长度，布局之前的随机消费保持；StopCube不删除被覆盖的interval抽样；VideoRepick核对NumPy/Torch流与hard聚集分支；Swap新增窗口不能继续消费原失败恢复随机流。原 `EpisodeJob.recovery_mode` 由绝对episode号决定，既有 `ep0～2=z、ep3～5=xy、ep>=6=None`；新seed区间选择须记录有效模式，不能因改episode-start而悄悄引入不同恢复策略。

## 四、子代理分配表

宿主已核实 `[agents] max_concurrent_threads_per_session=16`，本轮无需修改配置。本轮仅只读子任务；未来派写入任务的前提是对应计划阶段批准和开工。受保护文件一律由主会话按逐项批准清单实施，不放进子代理可写集合。

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约／依赖 | 整合顺序 | 验收位置、命令与判定 | 资源占用／共享归属 |
|---|---|---|---|---|---|---|---|
| M0 主会话自做 | 两项受保护首例及后续逐项源码改动 | 用户逐项批准的明确文件和锚点 | 未批准src项目、原件、录像器 | 默认三档，显式新档；源码受保护故主会话负责 | 1解析器，2ENV | Aspen本副本；定向短测与冻结diff | 不默认占GPU；公共解析唯一负责人 |
| G1 持久实现 | 生成入口和失败/身份记录 | `generate_dataset_newseed.py` | 全部src、seed_layout、原metadata | M0提供目标档与实际次数；旧调用不改 | 3 | 定向轻量测试；`DIFFICULTY_API、SEED_ISOLATION` | 不启动长任务；该文件唯一写入者 |
| T1 持久验证 | 测试代码与实际smoke | 两个拟新增 `test_xhard_count_*.py` | 生产源码、旧测试、其他run | 依赖M0/G1，严格预算与任务成功字段 | 4 | Aspen本副本；第五节命令；具名各闸门 | 只有另获运行授权才用1张空闲卡、1worker；测试产物唯一写入者 |
| D1 持久文档 | 新档入口说明 | `scripts/data-generation-newSeed/README.md` | 根规则、旧方案、源码 | 接口实定后更新，不提前写成已有能力 | 5 | 链接检查、`git diff --check` | GPU/端口/tmux均无 |
| E1～E4 持久探索 | 配置型、路径型、交换型、库存型的独立核对 | 无 | 全部文件写入 | 源码与候选表，不扩大范围 | 与实施并行只读反馈 | 稳定符号证据、实际容量与未解决项 | 无GPU/端口/run_name |
| R1 持久审查 | 每次整合前后检查旧档、保护、预算和失败分母 | 无 | 全部写入/执行 | 接口、源码快照与测试证据 | 最后 | 逐条 `NAME=PASS|FAIL`；不将新版本自动算已审 | 无GPU/端口/tmux |

所有共享文件与公共接口归唯一负责人。子代理交付改动清单与验证证据，不git暂存/提交/push；主会话保留已有代理上下文，后续同职责使用追加任务。受保护文件不因分工表存在而自动获准。

## 五、闸门总表与运行手册

| 闸门 | 要求 | 不满足时 |
|---|---|---|
| `ENVIRONMENT` | 确认Aspen本机工作副本、A/B口径、可用卡及缓存；缺greatlakes规约不提交集群 | 只读与计划继续；不实跑、不猜集群权限。 |
| `AUTH_SCOPE` | hard母场景已定；命名、首例次数、逐项保护批准、对应开工明确 | 不写生产代码、不运行。 |
| `SEED_PLAN` | 实际原件身份、已有数据清单、区间与新job集合查重 | 无源数据清单就不能宣称隔离，不起跑。 |
| `BUDGET` | 先单档单局；完整reset/轨迹/重试矩阵有上限和余额 | 超上限即停；不分批绕门槛。 |
| `SHORT_CHECKS` | 依赖已预装、定向检查通过、录像器冻结 | 不跑完整网格。 |
| `HARD_LAYOUT_BRANCHES` | 每个获准ENV全部difficulty/config消费锚点已分类；所有布局分支按hard执行 | 未分类或仍按目标标签误走非hard布局即停。 |
| `SMOKE` | 前表每项分开判定，TASK_SUCCESS独立，失败完整记录 | 不放大、不换seed筛成功。 |
| `FORMAL` | run_name、局数、clean HEAD、Beta、留档和正式开工 | 只交付首例结果，不能自动启动建库或训练。 |

以下命令是**实施后、已安装依赖并获运行授权时**的拟议入口，本轮不执行。拟新增测试尚不存在。单档smoke所用seed区间须由SEED_PLAN定稿，本段不提供可误启动的生成命令。

```bash
cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006
command -v uv
export XHR_VERIFY_DIR="$PWD/artifacts/validation/<获批的唯一验证名>"
UV_CACHE_DIR="$PWD/artifacts/cache/uv" uv run --frozen --no-sync python -m pytest \
  tests/lightweight/test_xhard_count_config.py -q

# 先验证单档，具体seed/输出路径由测试读取获批的测试参数。
UV_CACHE_DIR="$PWD/artifacts/cache/uv" uv run --frozen --no-sync python -m pytest \
  tests/dataset/test_xhard_count_generation.py::test_pickhighlight_xhard1_single_episode -q -s

git diff --quiet 13905997d45155ff1c98417511aedec92578042d -- \
  src/robomme/env_record_wrapper/RecordWrapper.py
git diff --check
```

测试节点与报告路径的拟议契约如下，实施时固定节点名并回填真实命令及退出码。`XHR_VERIFY_DIR` 只用于本轮测试输出；第一条单档测试不得隐式执行后面的对照。

| 执行命令／节点 | 输出文件（相对XHR_VERIFY_DIR） | 必须出现的具名判定 |
|---|---|---|
| `uv run --frozen --no-sync python -m pytest tests/lightweight/test_xhard_count_config.py -q` | `api_and_defaults.json、hard_layout_consumers.json` | `DIFFICULTY_API、NATIVE_DEFAULTS、HARD_LAYOUT_BRANCHES`；无仿真reset。 |
| `uv run --frozen --no-sync python -m pytest tests/dataset/test_xhard_count_generation.py::test_pickhighlight_xhard1_single_episode -q -s` | `xhard1/verification.json、xhard1/sample_manifest.jsonl` | `COUNT_ONLY、H5_CONTRACT、TASK_SUCCESS、BUDGET`；仅1次轨迹尝试。 |
| `uv run --frozen --no-sync python -m pytest tests/dataset/test_xhard_count_generation.py::test_pickhighlight_hard_and_xhard2_followup -q -s`（拟新增后续节点） | `layout_comparison.json、hard/verification.json、xhard2/verification.json` | `NATIVE_LAYOUT`及第二档各项；读取第一档已留的母场景快照，不重录第一档，新增2次轨迹尝试。 |
| 获批新档生成命令在建池前自动调用G1的来源/seed/split/budget检查 | 该独立run目录的 `preflight.json` | `ORIGINAL_REUSE、SEED_ISOLATION、SPLIT_ISOLATION、BUDGET`；实际源清单未提供时不能标PASS，具体生成命令在P0区间与局数定稿后补入launch。 |
| 录像器冻结的上述 `git diff --quiet` 与人工运行时覆盖审查 | `scope_review.json` | `RECORD_WRAPPER_FREEZE`；命令退出0，审查无覆盖才算通过。 |

上表pytest命令均需与上面相同的显式 `UV_CACHE_DIR` 前缀；无真实原件指纹、完整job清单或split口径时，对应来源闸门记未验证，不用测试的小型伪造清单冒充真实来源证明。正式输出路径、命令、退出码和每个判定值进入 `result.md`。

若测试预计超过5分钟，按完整运行另行确认run_name与留档，置于detached tmux；会话前缀建议 `xhr-`，具体全名与日志路径起跑前记入 `launch.md`。使用 `PYTHONUNBUFFERED=1、set -o pipefail、tee、EXIT_CODE=`，由主会话监听；不派子代理自行启动表外长任务。只用清单中的精确会话名清理，禁止 `tmux kill-server` 等全局操作。

本轮文档交付检查：

```bash
grep -c '^# 第一部分\|^# 第二部分' 1006-xhard12-env-plan.md
git status --short
# 只在确定暂存属于本轮的这一份方案后检查其实际补丁。
git diff --cached --check -- 1006-xhard12-env-plan.md
git diff --cached --name-only
```

第一条必须为2，cached文件名单必须恰好只有本计划；普通 `git diff --check` 不覆盖未跟踪文件，不能据它单独宣称本计划已检查。另检查文中已存在文件链接、两部分骨架、围栏、16任务计数、未把拟新增接口写成已可用、未出现长期源码行号引用。本轮只提交这个根计划文件，不改AGENTS/CLAUDE的历史账本。

## 六、风险登记

| 风险 | 依据与处置 |
|---|---|
| 原始dtype说明与当前实物不同 | 历史格式文档将joint_action列为float32，生成报告曾观察float64；本轮不改dtype，实施时从当前真实H5取shape/dtype/字节数。 |
| 长轨迹触及硬上限 | `RecordWrapper.step` 的2000步守卫冻结，另有1300步评估默认；超过即记录FAIL，另请用户裁决次数或后续范围，不加速、不提升上限。 |
| 长路径搜索失败 | PatternLock当前1000次失败后仍使用末次路径；新档追加严格长度断言，旧档不顺手改。 |
| 次数与语言脱节 | 共用序数函数仅支持第1～10；首例及Pick/Swing/Repick候选不超此界。其他任务以实际语言/任务列表核对，发现缺口另行批准。 |
| 共享配置污染 | 新字典、显式参数、同worker多档顺序检查；不改class原hard字典。 |
| 不受支持任务误接受新标签 | 默认解析只允许三档＋生成前支持名单；CLI不静默过滤、不回退到easy。 |
| 任务失败被重试筛掉 | 新档不走换seed的bump分支；首次结果/失败身份保留，基础设施单列。 |
| BinFill或Swap偷偷改变场景规则 | BinFill先冻结库存；Swap扩展发起者需用户定稿，保留现有随机流和索引行为。 |
| 同母布局跨split | 母组键、来源指纹与重复demo一起查；不同新seed不替代成组划分检查。 |
| 消费端长轨迹容量不足 | 生成成功不代表两端建库通过；另开消费端适配计划，不静默截断motion。 |

## 七、盲区诚实清单

未安装本副本依赖、未验证editable来源、未读实际原数据的文件指纹；没有XHard轨迹、实测步数/耗时/成功率或motion网格计数。没有给原版/新样本分配最终seed区间、split与局数。hard母场景已确认；首例4/5、推广范围与Swap第4/5发起者未获批准。环境规则缺项目判据表，历史硬件不是当前事实。本轮不能宣称新档可用、全任务完成、训练输入等价或训练完成。

## 八、留档、提交与推送纪律

短于5分钟的本轮文档检查不建运行档案。正式构建或超过5分钟的验证遵守通用第12、13、17条：在本副本 `docs/dataset-build-doc/<run_name>/` 留 `launch.md、result.md、records/`，追加总索引；只归档无法从Git恢复的日志、指标、指纹和判定证据，不复制bash/yaml或大H5。正式构建先打独立Beta锚点，运行期间按provenance要求冻结HEAD。

每次整合检查 `git status --short`，只暂存明确属于本轮的文件。提交正文记录本轮用户原话、方案、改动、意外、验证命令和实测结论，中文subject接续仓库编号。当前 `newtask-v3-MotionJepa1006` 没有upstream；本轮文档可本地提交，**不得自行建立upstream并push**。用户确定发布分支后才设置并推送；已存在upstream时以后按原规约立即同步。推送拒绝即停，不force、不重写历史。
