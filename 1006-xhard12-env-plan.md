> 本文是本分支“次数型 XHard1／XHard2”的实施候选方案，依据根 [readme.md](readme.md) 的需求与本轮用户提供的通用规则编写；不是开工令。代码核查锚点为 `13905997d45155ff1c98417511aedec92578042d`，生成代码起点仍为 `3a5951a834ea014f63724647ab0bc091eb9f109d`。唯一工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支为 `newtask-v3-MotionJepa1006`。提交编号沿用 `<大版本>.<小版本>[.<修订>] 中文描述`；本方案文档提交接续 `2.25`。外部 ManiSkill 来源钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，依赖以本分支的 `pyproject.toml` 与 `uv.lock` 为准。本轮仅核实源码、编写和检查方案；没有安装环境、改源码、生成轨迹或启动训练。每一实施阶段必须获得对应的明确“开工”，涉及 `src/robomme/` 的项目还要逐项批准。文中所有新增接口、次数和预算均是拟议项。

# 第一部分（给人看）

## 一、到底要做什么

**沿用 hard 的场景，让机器人多做几次动作，生成更长的任务。** 你的原话是：“澄清一下，就是用Hard的布局，但是把任务做得长一些。”

例如先做 `PickHighlight`：

| 档位 | 场景 | 要完成的动作 |
|---|---|---|
| 原 hard | 6 个方块 | 按顺序拾取 3 个 |
| 拟议 xhard1 | 同样的 hard 布局、仍为 6 个方块 | 拾取 4 个 |
| 拟议 xhard2 | 同样的 hard 布局、仍为 6 个方块 | 拾取 5 个 |

同 seed 对照时，假设目标顺序是 A、B、C、D、E、F，三档分别取前三、前四、前五个。**增加的是任务次数，完整录像也会变长；不压缩、不截断录像，不加快动作。** 4／5 是候选值，尚未批准或实跑。

已定口径：已有三档数据继续复用；物体、颜色规则、相机、机器人初态、速度和成功语义保持；`MoveCube、InsertPeg` 保留三档。每条新轨迹完整录制一次，后续模型共用原始 HDF5。本轮不改模型或训练输入，视频编码细节不在这里展开。

## 二、怎么改，先改哪里

**直接在 ENV 内增加两档配置，继续使用原任务循环。** 场景读 hard 配置，动作次数读 xhard1／xhard2 配置。例如 `PickHighlight` 的 `spawn=6` 不动，只把 `pickup=3` 扩为候选 4／5。

首例只改三个生产文件，另补测试：

| 文件与锚点 | 改什么 |
|---|---|
| `src/robomme/robomme_env/utils/difficulty.py::normalize_robomme_difficulty` | 允许已实现的任务显式接受新档；默认仍只接受原三档。 |
| `src/robomme/robomme_env/PickHighlight.py::configs、_load_scene` | 新增两档次数；场景仍按 hard 生成。 |
| `scripts/data-generation-newSeed/generate_dataset_newseed.py::_args、_run_jobs` | 新增 `--target-difficulty xhard1\|xhard2` 单档入口及记录、失败处理；与显式旧比例参数互斥。 |

不修改旧档配置、planner 或录像器。首例通过后，再考虑其余任务：

- **主要改配置的另外 4 项**：PickXtimes、SwingXtimes、RouteStick、PatternLock。
- **还需改局部逻辑的 4 项**：VideoRepick、StopCube、VideoUnmaskSwap、ButtonUnmaskSwap。两项 Swap 的第 4／5 次由谁发起，必须先确认。
- **BinFill 暂不定稿**：原 hard 场景里的库存不一定够，不能为了增加次数而加物体。
- **其余 6 项保留三档**：VideoUnmask、ButtonUnmask、VideoPlaceButton、VideoPlaceOrder、MoveCube、InsertPeg。

具体候选次数和受保护改动见第二部分“一、二”；这些分组不代表已经批准实施。

## 三、怎样确认改对了

| 验收 | 通过意味着什么／判定项 |
|---|---|
| 旧档不变、新档入口正确 | 原配置与默认调度未改，不支持的新档会被拒绝：`NATIVE_DEFAULTS`、`DIFFICULTY_API`。 |
| hard 布局确实保留 | 同 seed、执行前逐项比较物体、颜色、位姿、相机、初态和速度；不能只比 seed：`NATIVE_LAYOUT`、`HARD_LAYOUT_BRANCHES`。 |
| 次数真的增加且任务成功 | 核对实际动作事件与指令，独立报告 `TASK_SUCCESS=0|1`；正常退出不算任务成功：`COUNT_ONLY`。 |
| 完整录制且没有超限 | 检查 HDF5 连续帧、动作、状态和终态；保留 2000 步上限，随机次数档还要实跑上端次数：`H5_CONTRACT`、`STEPS_HEADROOM`。 |
| 原数据和数据划分安全 | 不覆盖原件，新 seed 与已有数据查重，同母场景不跨训练／验证／测试集：`ORIGINAL_REUSE`、`SEED_ISOLATION`、`SPLIT_ISOLATION`。 |
| 范围和预算受控 | 录像器保持冻结，每次 reset 与轨迹尝试都计数：`RECORD_WRAPPER_FREEZE`、`BUDGET`。 |

以上都是**待执行的验收要求，目前没有新档运行结果**。具体命令、字段和判定标准见第二部分“三、五”。任务失败如实保留，不换 seed 挑成功；基础设施故障只有获批后才能同 seed 有限重试。

## 四、按什么顺序做

| 阶段 | 内容与开始条件 |
|---|---|
| P0：确认 | 确认命名、首例 4／5、任务范围、新 seed 区间、环境和预算；逐项批准受保护源码改动。 |
| P1：实现首例 | 收到明确“开工”后，完成上面三个文件和定向测试，通过默认、入口和录像器冻结检查。 |
| P2：最小实跑 | 先 1 任务 × 1 新档 × 1 局 × 1 worker；成功后再补同 seed 的 hard 对照和另一新档，逐项验收。 |
| P3／P4：推广 | 另行获批后扩展可行任务；随机次数档验证上端，Swap 先定规则，BinFill 先核库存。 |
| P5：正式生成 | 另行确定数量、run_name、预算和留档；以 clean HEAD、Beta 锚点及明确开工令启动。 |

首例建议预算为 **3 次轨迹尝试、最多 10 次 reset**，不自动重试。推广 9 个任务的三档对照是 27 次轨迹尝试、约 54 次 reset；随机范围的上端验证还可能增加 10 次轨迹尝试、约 20 次 reset，须整体批准，不能拆小测试绕过预算。

### 子代理分工与合并（简述）

主会话负责获批的受保护源码；子代理分别负责生成器、测试、文档和只读审查，各管不同文件。按“解析器 → 首例 ENV → 生成器 → 测试 → 审查”整合，整合前检查范围和接口，整合后跑对应验证。详细分工见第二部分“四”。

**目前只完成方案和静态核实，没有改源码、录轨迹或启动训练。** 环境为 Aspen 本机、2 张 RTX A6000；项目缺正式 A/B 判据表和 `greatlakes.md`，实跑前需确认环境口径。本次精简正文不构成任何实施开工令。

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
