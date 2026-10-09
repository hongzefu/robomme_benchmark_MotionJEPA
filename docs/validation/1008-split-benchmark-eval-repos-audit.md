# 2026-10-08 仓库拆分计划完整对抗审计记录

> **审计锚点：`AUDIT_BASE=108c468f40bf8f445b766734806dcc31cd3f201b`。**
>
> 审计对象：[1008-split-benchmark-eval-repos-plan.html](../plans/1008-split-benchmark-eval-repos-plan.html)。本报告只依据该提交及其祖先提交；外部模型源码只依据该提交记录的 gitlink。所有源码引用采用文件与函数、类、配置键等稳定锚点，不依赖当前文件行号。
>
> 用户选择排除 `third_party/SimpleMemVLA` 的在途改动。审计未运行仓库脚本、测试、仿真、模型推理、编码实验或集群作业。报告中的失败链是静态推导；已有编码数字和历史实验结果注明其来源，不能当成本轮重测。
>
> **性质：审计报告，不是已经批准的实施计划或开工令。** 用户随后明确要求把完整审核记录写成 Markdown，才新增本文件；没有据此修改原 HTML、环境源码、模型源码或其他在途文件。本报告的交付提交发生在审计结束之后，不改变 `AUDIT_BASE`。

## 1. 结论与交接摘要

现方案已经明确多数产品目标，但还不能直接作为“一次认可后连续跑完”的执行依据。主要问题不是仓名、目录或 AV1 选择没定，而是迁移依赖没有闭合、Policy 接口不足以承接现有模型、媒体验收仍读取旧格式、预算单位混用，以及锁仓、接续与收尾顺序不成立。

```text
STATIC_PLAN_AUDIT=FAIL reason=execution_contracts_incomplete
SPEC_PINS_AT_BASE=PASS files=5 mismatches=0
SOURCE_CODE_DELTA=PASS from=9c78c076 to=108c468f files_changed=0
```

上述后两项只证明冻结源码之间的字节关系，不证明 wheel、真实对拍、GL 五策略或媒体链已运行通过。运行验证未执行。

交给接手代理的优先事项：

1. 保留已经确认的目标，不重新询问仓名、平铺入口、两个数据集、常驻 Policy、每局开头 reset、AV1 原始流、对拍工具进 eval 等口径。
2. 先修订计划中的确定工程错误；不要把测试夹具、扫描规则、文件计数、派工重叠等事项再次逐条交用户裁决。
3. 将真正的选择合成一张表：仓库可见性、四局身份口径、对拍基线、GroundSG 变体与种子、专家视频范围、网站编码边界、本轮资源和费用、首试与故障重试预算。
4. 完整呈现修订后的 HTML，包括全部 SVG；用户对完整方案不提修改而直接认可后，才开始实施。
5. 将最终 benchmark 锁定放在本轮相关验收全部通过之后。用户已说“这次改完之后”锁死，不应把 S1 初步完成解释成整体改完。

## 2. 用户要求、范围与实际审计过程

### 2.1 本会话用户要求

初始要求原文：

> /data/hongzefu/robomme_benchmark_MotionJEPANewTask/1008-split-benchmark-eval-repos-plan.html对抗验证尽可能详细
> 你需要确定有哪些事情用户没有确认还有哪些事情没有定下来然后最好让我能一波跑完

锚定时发现工作区有在途修改，用户选择：

> 只审该提交，排除 SimpleMemVLA 的在途改动（推荐）

随后新增的交付要求：

> 给我完整你的审核记录的这个 Markdown，然后我要发给另外一个 agent。

用户又询问进度：

> 运动好了吗？
> 你弄好了吗

这些进度询问不改变审计范围或赋予拆仓开工授权。

### 2.2 环境判定与冻结范围

开工第一步运行仓库规定的只读环境判定，退出码 0，结果：

```text
repo=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
hostname=sled-vail
/nfs/turbo/coe-chaijy-unreplicated/hongzefu：存在
/data/hongzefu：存在
~/.ssh/config：存在
GPU：2 × NVIDIA RTX 6000 Ada Generation
micromamba：有
agents.max_concurrent_threads_per_session=16
```

发起审计与静态审计结束时，以下两条命令退出码均为 0：

```bash
git rev-parse HEAD
git status --porcelain
```

两次输出均为：

```text
108c468f40bf8f445b766734806dcc31cd3f201b
 M third_party/SimpleMemVLA
```

排除该在途改动后，源码读取只用锚定的 Git 对象，不以工作区或后来分支状态补入审计内容。审计结论形成后，才进入用户明确要求的报告写入与文档交付阶段。

### 2.3 并行审计职责

| 职责 | 重点 | 写入权限 |
|---|---|---|
| benchmark 包审计 | builder 裁剪、规格、自签清单、官方覆盖边界、wheel | 无 |
| 对拍审计 | O/H/H2 基线、生成依赖、CLI、子集分母、预算 | 无 |
| Policy 与单局审计 | 模型输入、局身份、常驻状态、跨数据集、异常隔离 | 无 |
| 媒体审计 | AV1、原动作、重绘、专家演示、编码和清理 | 无 |
| 测试审计 | 搬迁闭包、公共夹具、契约总表、假通过 | 无 |
| GL 审计 | Astra、资源、环境、资产、费用、接续和释放 | 无 |
| 仓库生命周期审计 | 建仓、Git 命令、锁仓、标签、规则同步 | 无 |
| 授权账本审计 | 原话、已有确认、真正未决项与范围歧义 | 无 |
| 主会话 | 交叉核对、裁掉误报、预算定义整合、最终报告 | 用户要求之后仅写本报告 |

没有派发代码写入任务，没有子代理暂存、提交或推送。生成依赖审计另有只读子分工，同样受冻结与禁执行约束。

## 3. 已经确认的口径：不要重复询问

本节依据计划及其祖先提交记录的用户原话，不把代理拟定的细节冒充用户原话。

| 已确认事项 | 证据与适用边界 |
|---|---|
| 初稿 Q1～Q9 按推荐项确认 | `4c9e6136e5d2783d9eae026929fc67629c196f03` 记录“其他的我都确认了写入这个计划”；问题原表见祖先 `6021e241322d49ce3c7328931215afa492b4237d` 的初稿 Markdown。后续新原话覆盖旧推荐项 |
| 两个新仓名称 | `10a37213e653362e7fcd63e0a2d7fd46f4b2d208`：`RoboMME-benchmark-OOD`、`RoboMME-benchmark-OOD-eval`，新建业务仓，benchmark 历史接官方固定提交 |
| benchmark 入口平铺 | `a57fb7229a5a377bf48e8c98d012e46bf421590b`：`scripts/evaluation_ood.py`、`scripts/README_ood.md`，不建 hard 子目录 |
| eval 的两个脚本目录 | `61dc61ec21633ff12f9d330d3276b367867cc790`：`scripts/` 只留 `evaluate.py`，其他脚本进 `dev-scripts/` |
| 数据集与步数 | `hard-verify` 保持名称，说明它对应 xhard0；1300 步。`ood` 为 1800 步 |
| benchmark 的五处裁剪 | train 元数据、旧 V4 接口、xhard0 前置开关、外部规格根覆盖、允许数据集收窄，已经确认 |
| 规格不变、官方冻结 | 五份封存规格字节不变；官方源码与冻结录像器不改、不新增覆盖 |
| 评估留档去向 | 六个评估留档目录随 eval；其余历史生成留档只留旧仓归档 |
| 旧资产与站点不搬动 | 初稿 Q9 已确认。新产物仍需明确落入新 eval 的 artifacts，旧素材作只读输入 |
| 常驻 Policy、每局 reset | `8b9a84b7ed1a987dc93b7cea81e0327bc579a7f7`：加载、编译预热放加载阶段；每局第一句 `policy.reset()`；外层动态队列 |
| 原始流有损 AV1 | 已定 AV1 4:4:4、libaom、crf 24、cpu-used 4。无需重新问有损还是无损 |
| 官方版式与专家演示两版 | 官方文字区版式；专家无字红框版与带字版；保留原始素材和原始动作以支持以后转换 |
| 所有对拍工具进 eval | `10a37213…` 记录生成对拍、hard-verify 对拍与 GL 分发搬运工具集中迁入 |
| 模型仓由 eval 接入 fork | 初始原话“这个repo来fork所有的repo”；不等于本轮可以修改任何模型源码 |
| 本机对拍四局、GL 每策略两局 | `e221813ed0d7de999e9a64b11bb7f5cefd0bbd04` 记录原话，含 Astra 也两局、一个带 video demo 的任务。四局是否分入口分别计尚有歧义，见下一节 |
| 两个本机副本的位置 | `/data/hongzefu/RoboMME-benchmark-OOD` 与 `/data/hongzefu/RoboMME-benchmark-OOD-eval` |
| 第一部分验收表范围 | 本审计锚的提交记录“验收判定除了我关心的这些内容之外其他都收到第二部分里面”，因此机检闸门继续放第二部分 |
| benchmark 最终锁死 | 原话“这次改完之后Benchmark仓库就锁死了”；锁死目标不重问，实施顺序应修正 |

四个 gitlink 在审计锚点确实与计划一致：

| 模型路径 | 固定 SHA | 当前来源 |
|---|---|---|
| `third_party/mme-vla` | `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b` | `hongzefu/robomme_policy_learning_MotionJEPA` |
| `third_party/SimpleMemVLA` | `c564c17d276d7294200122b286c21901a3bfb99f` | `hongzefu/SimpleMemVLA` |
| `third_party/PonderPounce` | `723df35762bb641e1d520e4fa9359b98644adc21` | `worv-ai/ponderpounce`，目前仍是上游 URL |
| `third_party/Astra-on-RoboMME` | `4c3fd6a8667e7a219e547fe1a533a4b9726fc6db` | `bingaochen/Astra-on-RoboMME`，目前仍是上游 URL |

后两项不是“已有自己的 fork”。按照用户已经给出的 fork 要求，代理应补建或核实对应 fork，保持固定 SHA，改接 URL；无需再问是否满足该原要求。不得借此升级 SHA 或改模型代码。

## 4. 真正未定的选择：集中一次裁决

| 编号 | 尚未定的内容 | 推荐与需要写清的边界 |
|---|---|---|
| D1 | 两个新仓公开还是私有 | runbook 仍是 `--<public|private>`。用户需明确可见性；代理随后核保护能力和权限，不能根据上游公开推断新仓公开 |
| D2 | “本机对拍四局”是整项四个唯一身份，还是两个入口各选四局 | 推荐整项四身份复用：生成对拍 hard-verify 两局、ood 两局；reset 对拍复用这两局 hard-verify。若保留计划 reset 四局，则实际合计六个唯一身份，需要明确认可新增的两个身份 |
| D3 | OOD 生成对拍的对照基线 | 推荐 hard-verify 用官方 O 对新 H；OOD 用冻结拆仓前 H 对拆仓后 H，同规格、同机、同环境。不能继续把 OOD 的旧侧称为官方 O |
| D5 | GL 中 GroundSG 的变体、seed 与两个身份 | 推荐 GroundSG+Oracle、模型 seed 7；VideoUnmask，hard-verify builder 0/source 3、ood builder 0。现原话只定带视频任务，VideoUnmask 是代理选择；应整体确认身份表 |
| D6 | 专家演示范围 | 只 OOD：16 任务 × 1 数据集 × 50 局 = 800 局，两版共 1600 视频；两数据集：16 任务 ×（hard-verify 12 局 + ood 50 局）= 992 局，两版共 1984 视频。S4 目前只有前者，不得擅自扩为后者 |
| D7 | 网站 MP4 编码与“官方版式”的边界 | raw AV1 已定。官方/专家 MP4 是否继续原官方 H.264 编码、要求哪些浏览器，正文未统一。推荐区分绘图语义与编码，先固定网站输出契约；不是重新选择 raw 编码 |
| D8 | 本轮尝试上限、基础设施重试、停止条件、run_name | 必须先按第 6 节定义形成完整表，再一次确认。建议首版 0 次自动 episode 重试；业务失败不重跑。若要有限基础设施重试，应给增量上限，不继承旧默认重启次数 |
| D9 | Astra 本轮费用账本与资源安排 | 新两局数量已被明确要求；本轮独立账本、总费用最多 5 美元仍需明确。现 Astra 需同节点两 GPU；全部席位规格、数量、复用归属与结束释放写一张表 |

旧数据只读使用和新产物落点是必须补的技术表。已有同源资产直接核实复用；发现必须新增的大下载或大复制，先列规模、落点与必要性，再合入同一次裁决。不能凭拆仓授权自行重新下载全部模型。

### 4.1 四局口径的具体差异

用户原话没有分别给生成与 reset 两个入口各四局。当前 HTML 实际安排：

```text
生成对拍：VideoUnmask × {hard-verify 0、1；ood 0、1} → 四个身份
reset 对拍：VideoUnmask × {hard-verify 0、1、2、3} → 四个身份
二者并集：hard-verify 四个 + ood 两个 → 六个不同身份
```

如果采用整项四身份复用，reset 判定必须改为选中的两局，不能继续写 `shape=1x1x4`。同一身份复用也不减免两侧生成、重复 reset、演示与失败尝试的预算。

### 4.2 无需再次逐项确认的技术修正

测试公共件、mutation 基础设施、契约总表重切、夹具去旧依赖、明确函数签名、每步 info、原动作 dtype、媒体 schema 兼容、正确 grep/rg、manifest 重签、默认数据集、完整命令、子项目路径、规则同步先后、最终锁仓时点，都是既定目标下的工程补齐。

不要让用户选择 Python 参数形式、是否修正明显错误的 Git 命令、是否保留合法官方来源哈希。新增受保护源码改动、升级第三方来源、额外生成样本和大下载则仍需明确授权。

**T1（复核后从原 D4 移出的技术盘点）：对拍模式与依赖闭包。** 用户已明确要求“所有的对拍工具”，代理应先逐模式盘点 continue/split/aggregate 等的实际用途，默认保持已授权对拍能力，不能以“推荐仅 replay”自行缩减功能。只有发现某模式确实恢复新候选抽样、增加生成范围或超出预算执行时，才把具体新增能力、必要性和预算交用户裁决。迁入工具不等于本轮获准执行其全部模式。

## 5. 逐项发现、证据、反例与处置

本节 P1 表示会阻断实施或使关键验收失真的问题；P2 表示交付或验证不完整。明确区分已从代码证实的矛盾与尚未设计完成的风险，不把候选风险写成已经发生的运行故障。

### F01〔P1〕OOD 的官方 O/H 对照不是相同语义

**计划锚点：**第一部分 `PARITY_GEN_SMOKE` 与 S5 runbook。

**代码证据：**`scripts/parity/hard_parity.py::cmd_generate` 对 V9 只允许 H2；官方 `official/scripts/data-generation/generate_dataset.py::_worker` 只传 seed、原生 difficulty、恢复参数，不消费 OOD 的 `sampling_config`、`native_episode_spec`；`hard_builder.py::_ood_entries` 与 `_hard_env_kwargs` 正是靠这些封存参数恢复新值档。

官方 difficulty 只接受 easy、medium、hard。直接传 xhard 档会拒绝；改传 hard 也只是换成另一场景，不能成为 OOD 等价对照。

**处置：**按 D3 分两种基线，保持同机与独立进程；两侧绑定相同身份、规格、精度和依赖指纹。历史噪声接受不等于可以比较不同场景。

### F02〔P1〕被排除的 runner 仍是生成链路依赖

`hard_parity.py::RUNNER/cmd_generate` 和 `scripts/injection-dev/_rollout.py::RUNNER/run_batch` 都调用 `train_split_runner.py`。计划却将它与其他退役 train 工具一起排除。`train_split_worker.py::run_one` 也依赖父执行器准备官方生成模块导入路径，单迁 worker 不能替代执行器。

**反例：**搬完列出的文件后，生成进入子进程即找不到 runner。

**处置：**把必要职责迁成对拍专用执行器或归入保留模块，明确来源与接口；不恢复整套退役工具。同步裁夹具和比较器依赖。

### F03〔P1〕生成模块的迁移依赖闭包不完整

已证遗漏：

- `generate_h5.py`、`_rollout.py` 导入 `_common`，迁移表没有该模块。
- `_rollout.py::row_way` 使用 `_freeze._movecube_way`；`split_v8` 使用 `_freeze.write_jsonl_exclusive`。
- `hard_parity.py::_all_tasks` 仍从未迁入的 `seed_layout` 取规范任务序。
- `comparator_fixtures.py` 顶层导入未迁的 `train_split_comparison`。
- `train_split_worker.py::run_one` 的 builder route 仍只认 ood，需要明确 hard-verify 路由。
- `noise_gate.py::load_identities`、`gate_set.py::_hs/_delivery_index`、`Mover._load_noise_gate`、`noise_run_gl.sh` 保留旧脚本包名或路径。

**处置：**按 T1 盘点的已授权对拍能力逐符号闭包；从 `_freeze` 抽取必要纯函数，不把无关全生成设施重新带入，也不借清依赖缩减对拍功能。`dev-scripts` 带连字符，不能直接成为普通 Python 包名；须统一真正可导入包或明确模块加载方式。

### F04〔P1〕生成 smoke 的新 CLI 没有实现契约

runbook 的 `--task --datasets --sides` 和 `compare --run` 不存在于冻结的 `hard_parity.py::build_parser`。现入口要求 side、tier、manifest、src-root 等参数；本机 GPU 不是 A40 时还需显式开发 smoke 档。现 worker 默认 16，与计划“单 worker”不同。

**处置：**把这些明确列为新增 CLI，而非现有可运行命令；完整写参数、默认值、数据集区间、两侧独立输出、开发档和 `--workers 1`。不能把“参数名以 E2 定稿为准”留到起跑时。

### F05〔P1〕reset 四局子集与分母均未实现

`hard_regression.py::build_parser` 的 `xhard0-reset-parity` 没有 `--episodes`；`cmd_xhard0_reset_parity` 取任务全部 12 局，最终仍按 16 任务 × 12 局比较。

**反例：**按 runbook 传 `--episodes 4` 先参数错误；执行者删该参数“救场”，会跑单任务全部 12 局而仍不满足全量分母。保留旧探针时，这变为 1 任务 × 1 档 × 12 局 × 2 侧 × 2 次显式 reset = 48 次，越过写出的四局安排。

**处置：**真正实现身份子集、所选任务数和局数分母；按 D2 的两局或四局输出判定。不得通过删参数自动放大规模。

### F06〔P1〕双方都生成失败也可能输出对拍 PASS

`hard_parity.py::cmd_compare` 使用 `produced = both_success + both_fail`。native/xhard0 路线允许全部双方失败、setup/schema 实际比较数为零，仍满足旧的行为判据。

**处置：**单独要求两侧有效 HDF5、可读结构与真实比较数；明确列出 both_fail，不能用同样失败代替成功生成。正常生成失败报告失败并停；评估 `task_success=0` 则可以是有效的业务结果，两者不要混淆。

### F07〔P1〕轻量规格读取不能机械改成包 import

`hard_parity.py::hard_specs_light` 特意按文件加载规格模块，避免 `robomme_hard` 包初始化导入仿真、执行注册接管。计划将所有路径加载统一改成 `import robomme_hard...`，可能把纯 CPU 导入闸门变成真实仿真依赖。

**处置：**分别定义“生产环境包导入”和“纯规格读取”的契约，保留可验证的轻量路径。原侧独立进程中不得先导入 hard 包；包导入的 `override=True` 接管不会被后来的 `import robomme` 自动撤销。

### F08〔P1〕单局函数签名和局身份不统一

目录树与逐文件清单写 `run_episode(policy, dataset, episode, out_dir)`；调用链却传 task。每个任务都有 episode 0，dataset+episode 不能唯一定位环境。CLI 对 `--tasks` 的描述也不统一。

hard-verify 的 builder 局号是 0～11，输出希望保留官方原 episode 号；`hard_builder.py::resolve_identity` 已提供 `builder_episode/source_episode` 映射。公开区间参数没说明取哪套编号。

**处置：**统一带 task 的签名或完整身份对象；CLI、队列、结果、视频命名显式区分 builder 与 source 编号。推荐选择用 builder 编号，展示保留 source 编号，并明确反查。

### F09〔P1〕`act(obs)` 丢失 Oracle 与视频演示所需输入

`groundsg_client.py::SessionRunner` 每步更新 info；Oracle 从 `simple_subgoal_online/grounded_subgoal_online` 读取当前子目标。初始 `task_goal` 和纯 RGB obs 不足以替代。

`get_init_obs` 保留全部演示 images、wrist_images、states；FrameSamp 的执行起点依赖演示 buffer 长度；SimpleMemVLA reset 后观察全部演示帧。只保最后一帧会改变模型算法。

**处置：**定义包含每步 info、step、phase、演示边界与状态的策略输入。Oracle 可读其约定字段；其他模型不得因统一接口额外收到标准答案。用固定假观测核出站载荷，不增加真实 reset。

### F10〔P1〕常驻 GroundSG 跨 1300/1800 两档会被旧上下文拒绝

`groundsg_client.py::make_policy_context` 将 max_steps 固化进 Args；`run_episode` 对 Args 与连接 max_steps 不同直接报错。计划的 load_policy 只接模型和 seed，同一实例随后跑 hard-verify 与 ood。

**处置：**每局更新 dataset、cap、strict_cap、task、identity；权重跨局复用。固定假环境先 1300 后 1800，真实 GL 两局也证明使用同一个健康 Policy 实例。

首推理预热不能自动证明后续所有动态输入形状都不再编译。计划自己引用 MME 新演示长度会重编译的历史事实；须模型级写清预热覆盖、编译缓存身份和后续编译记录，不能凭“load 已调用”宣称全部编译完成。

### F11〔P1〕硬超时、单局结束与资源释放缺少可执行边界

现 `env_client.py::_on_deadline/_on_wall_timeout` 会硬退出客户端。仿真、CUDA 或 socket 卡住时，普通 try/except 无法安全取消调用并继续同进程模型。

Policy 接口没有单局结束钩子；当前 PonderPounce 需要 `EPISODE_END`，EnvSession 需要 close。计划调用链到 `record.finish` 就结束，未覆盖所有异常路径的 `env.close()`。

**处置：**明确普通异常、硬超时、服务死亡、CUDA 污染、费用拒发的处理矩阵；定义可终止的逐局边界和进程所有权；单局结束与整个 Policy close 分开，环境、记录器和模型会话在 finally 收尾。健康服务继续复用，污染服务按预算重建。

### F12〔P1〕Astra 不是普通 websocket 动作模型

`astra_hard_runner.py::run_cases` 常驻动作客户端、monitor、planner；每局通过 `astra.runner.episode` 的状态机编排。仅“从四个客户端抽 act”无法覆盖它。

必须保持身份先验、费用同步预留、守卫心跳与 STOP、云端 seed=null、语言与图片记录、BaseException 后结果落盘。`run_astra.sh` 还需要两张不同 GPU，旧 `run_seat.sh/run_eval_gl.sh` 只认其他四策略。

**处置：**单列 Astra 适配、启动、费用守卫与资产清单，给通用入口明确分派。两个单 GPU job 不保证同节点，不能替代同节点双卡方案。不能静默删异卡守卫来满足单卡图。

### F13〔P1〕AV1 新产物与旧重绘、检查和对拍消费者不兼容

`render_official_video.py::select_source/decode_raw_new` 要求两份帧索引、FFV1 codec、解码帧字节哈希等于编码前哈希。新 AV1 有损不会满足。旧重绘与 `gate2_compare.py::_load_arrays` 读取 arrays.npz；新计划仅写 actions.npz。

`official_media_check.py::verify_dir` 识别 `.a<attempt>/official/*.mp4` 和 render/provenance sidecar，新方案是并列 raw/videos，没定义相应身份与 provenance。旧无帧错误处理按 error 状态，新方案展示 error 并入 fail。

**处置：**明确版本化 schema 与适配器，保留历史读取兼容；AV1 校文件身份、时序、帧数、画质，不要求解码像素等于原 RGB。展示终态与原始 failure_kind 分开，no_frame 合法缺项明确记录。

### F14〔P1〕旧收尾会删除要保留的 raw，异步编码还可能永久等待

`seat_media_lib.sh::transcode_episode_dir` 默认转码后删除 front/wrist 原始 MKV。迁移时若仅改路径，用户要求保留的素材仍会被删除。

`recorder.py::close` 的 sentinel 入队循环只判断线程活着；writer 卡在 ffmpeg stdin、队列满时，后面的 900 秒 join 根本到不了。部分等待解码或重编码没有统一截止时间。

**处置：**永久 AV1 raw 不进入旧清理分支；临时 spool 成功校验前保留。整段收尾、管道写入、ffmpeg 和验证都有截止与失败结果；媒体失败只重处理已有素材，不重新消耗环境或 Astra 费用。使用队列满、磁盘满、截断流、SIGTERM 夹具。

### F15〔P1〕“原始动作 float64”和 trace 摘要不足以完整恢复

`trace_writer.py::array_record/log_response` 当前主要保存 hash、dtype、shape 和少量 float32 摘要；完整数组在 arrays.npz。只改文件名、删数组容器会丢失状态、动作块等数据。统一 float64 也会改变原 dtype 身份。

**处置：**保留实际执行动作的原 dtype、shape、字节；保存重绘所需状态、文本和帧到 step/phase 映射；计划已承诺的模型回包需明确完整载荷或可恢复引用。可收进约定容器，不必增许多永久文件。

有损 AV1 只能近似恢复图像；动作原字节可恢复与图像逐位恢复是不同保证，不能据此承诺重演完全相同物理轨迹。

### F16〔P2〕专家素材时序、官方版式与画质被混为一项

`RecordWrapper.py::close` 写 HDF5 的 `episode_<N>/timestep_<K>`，obs 含 front/wrist RGB、joint/gripper state，action 含 joint_action，info 含 is_video_demo，目标来自 setup/task_goal。

不能按字符串排序 timestep；原录制器不补 reset 帧。`evaluation.py::VideoRecorder.add_initial_obs` 的最后初始帧红框处理与 HDF5 来源不天然相同。

锁定官方 `RolloutRecorder::add_text_area` 根据文字换行动态决定高度，并非任何目标与子目标都固定 512×496。整帧 PSNR≥40 不足以证明文字、红框和小目标细节正确。

**处置：**现在就定数字排序、缺项、UTF-8、状态组成、演示边界和 fps；不补没有来源的 reset 帧。官方绘图语义和有损画质分开验收，允许的补边规则明确写出，不偷偷裁字或缩字。

### F17〔P2〕编码容量和速度只有单局外推

计划记录 InsertPeg xhard4 前视 254 帧、AV1 168 KB/44.1 dB，但冻结源码没有对应源指纹、完整命令、工具链版本和逐帧指标记录。祖先 commit body 记录了实验过程，不能代替本轮独立复核。

每局约 0.35 MB、整批约 5 GB、每路约 6 秒来自这一短流外推，不能成为所有任务与长超时局的容量和 GL CPU 保证。

**处置：**使用已有素材补输入 SHA、编码命令、ffprobe、完整解码、逐帧指标、实际 CPU 时间与线程上限，无需新仿真。`cpu-used 4` 是质量/速度档，不是四 CPU；默认线程数和 GL 编码器能力须核实。[FFmpeg 官方说明](https://ffmpeg.org/ffmpeg-codecs.html#libaom_002dav1)

raw MKV 的离线可读和网站 MP4 的目标浏览器可播分别验证，不把 AV1 这个 codec 名称当成浏览器兼容证明。

### F18〔P1〕测试嵌套、公共夹具与迁入文件仍有断链

benchmark 测试整体嵌套一层后，`tests._support`、`tests.contract` 导入和 `_support/loaders.py/resource_policy.py` 的 parents 根定位都会失效；SIM_DIR、nodeid、inventory 也需改。

eval 的 testpaths 若沿用当前四个目录，会漏掉计划新增 `tests/test_episode.py`，pytest 仍可能退出 0。

对拍的 `parity_fixtures.py::train_split`、`test_train_split.py`、`test_h5_comparators.py` 依赖被排除的 train_split 模块。gen 的 `gen_world.py` 顶层加载被排除的 freeze_specs，测试收集阶段就失败。

**处置：**公共件根发现与命名明确；按保留能力拆夹具，契约和 mutants 的 source/target/nodeid 同步重切。新核心测试必须被实际收集，不能只数文件。

### F19〔P1〕文本零命中闸门可能假通过，也会误杀合法证据

`grep -rn` 配合 `|` 并非正确的默认或匹配；不存在目录、读取错误不可当成零命中。`PARITY_IMPORT` 扫旧 scripts/parity，而新目录是 dev-scripts/parity。

`BENCH_NO_GEN` 的 env_metadata/train 会命中 UPSTREAM 中合法官方来源哈希；拒绝旧开关或参数的负例测试也可以合理出现那些字符串。包内规格变量 specs_root 不等于外部覆盖能力。

**处置：**生产 AST、实体目录、旧入口拒绝分别验；文本扫描只辅助，用 rg 并区分匹配、无匹配和读取错误。保留官方哈希和有效负例，不为了零命中删除证据。

### F20〔P1/P2〕裁剪默认值、manifest 自签、wheel 与入口守卫不完整

- `_ALLOWED_DATASETS` 裁成两个值，但 `BenchmarkEnvBuilder.__init__` 默认 dataset 仍是 test，默认构造会自拒绝。推荐默认 ood 或明确必填，所有文档和测试一致。
- 删除 UPSTREAM.json 四个 vendor 条目后，必须按既有 canonical JSON 规则重算 manifest_sha256。保留独立自签测试；cheap shim 检查不等同完整 manifest 校验。
- `tests/static/test_package.py` 的真实 wheel 构建/非 editable 安装属于 slow，默认 not slow 不覆盖；已有测试还允许构建失败 skip。锁仓前必须实际通过且 skipped=0。
- `tests/contract/test_registry.py` 同样属于 slow，需锁仓前定向执行且 skipped=0；核验 hard_only、official_then_hard、hard_then_official 的注册归属，并有 official_only 独立进程对照。这项只查注册表，不增加真实 reset；wheel通过不能替代它。
- `BENCH_ENTRY_DIFF hunks=4` 不能证明差异内容只有获准四项；同一个 hunk 可混入改成功字段等额外修改。需要内容白名单。
- `BENCH_DELTA` 应定义两个逻辑新增根、五个独立新增文件和四个修改白名单，不把 Git 文件行数当目录数。
- `BENCH_UPSTREAM` 只比两个提交，不能发现未提交或未跟踪的官方改动；还须覆盖 LICENSE 等承诺冻结的官方文件，并核 clean 状态。

### F21〔P1〕锁仓顺序、API 类型和技术锁定条件不成立

S1 要求 BENCH_LOCKED，此闸门又要求 eval gitlink 等于该 HEAD，而 eval 在 S2 才建。S5 首次跨仓真实验收在锁死之后，发现裁剪问题就无法本轮修完。

保护命令使用 `gh api -f`，它将 true/null 发送为字符串，应使用 typed field 或 JSON。即使修好类型，enforce_admins=true 且其他条件为空仍允许正常 push，不能代表只读锁。[GitHub CLI 说明](https://cli.github.com/manual/gh_api)

**处置：**先候选冻结，完成验收后最终 tag、branch lock、标签保护和 gitlink 核对；核 lock_branch 而非只 enforce_admins。主分支只读参数的语义见[GitHub 官方 API](https://docs.github.com/en/rest/branches/branch-protection#update-branch-protection)。可见性/套餐导致保护不可用时如实停止，不自动降级成规则文字承诺。

### F22〔P1/P2〕runbook 的若干 Git 和冒烟命令会失败

| 命令 | 问题 | 修订方向 |
|---|---|---|
| clone 官方 main 后 checkout -b main | 默认 main 已存在时创建同名分支失败 | 明确固定 SHA 建立当前新仓主分支的步骤 |
| archive 后直接 git mv 新文件 | 解包出的文件未跟踪 | 对本轮新文件普通 mv，再逐路径暂存 |
| 在旧仓建 tag 后裸 git push | 当前目录已在 eval，推送对象/远端错误 | 创建与推送都显式旧仓 `git -C` |
| 归档轻量 tag | 无法承载已写定的归档说明 | 使用带说明的标签，区分源码锚与归档截止提交 |
| git init 不指定分支，首推不建 upstream | 后续裸 push 不具备明确目标 | 指定 main、正常首提交、首推建立 upstream |
| dummy --episodes 0:1 | 半开区间只一局，不满足两局常驻检查 | 明确区间语义，使用两局范围 |
| ffprobe 多个 front.mkv glob | 多输入不是批量 probe | 按身份逐文件 probe 汇总 |
| files=7 | 每局 raw 五文件+video一文件；两局共享一个log是13，不是7 | 按身份核实际产物和允许缺项，目录不当文件 |

### F23〔P1〕多 venv、嵌套子模块与资产路径未形成启动表

SimpleMemVLA 服务要求独立 Python 3.10/torch 2.4.1；扩展客户端使用 Python 3.11/torch 2.9.1；主环境一次 uv sync 不能覆盖全部模型。迁移子项目后 `robomme={path="../../.."}` 可能指向 eval 根而不是 benchmark submodule。

统一 `git submodule update --init --recursive` 与 `preflight_mme_vla` 要求嵌套 benchmark 不存在或为空冲突。旧资产准备记录本就只初始化部分嵌套模块。

**处置：**逐模型列 Python、独立 pyproject/lock、依赖组、解释器、editable 期望、checkpoint/tokenizer/adapter/缓存和 ffmpeg；按模型决定嵌套初始化。NFS 钉解释器与 copy link，显式缓存目录；计算节点只用预装环境。

旧 assets 脚本中存在来源记录只能证明历史来源，不证明现在文件完整可读。开工前只读核实存在、SHA、字节数、离线加载条件、存储空间和目录归属，不隐式回退在线下载。

### F24〔P1〕队列接续、失败监督和本轮留档没有闭环

计划承诺动态队列与断点续跑，但没有完整定义 claim/accept、权威结果、并发重复领取、过期任务、媒体阶段幂等、终态缺文件与重试 token 的处理。这里只判“契约未定义”，不宣称已有新队列发生过故障。

trap、tee、EXIT_CODE 不能替代宿主等待/唤醒与阶段接续。runbook 没有本轮 run_name、launch/result/records、tmux 会话和 JobID 清单、完成/异常监督、资源释放动作。

**处置：**用不触发仿真的真实 JSON 夹具跑“完成→报告读取→下一阶段”和“失败/缺项/监督器异常→停止→通知”。计数字段显式零值；不将未知缺项 `.get(...,0)` 全当成功。已有结果核身份后复用；不重跑已完成生成。

预计超过五分钟的 CPU 专家渲染也进 tmux。无成功注册的唤醒回执时，代理必须持续等待处理已授权工作，不能提前最终答复并承诺自动收尾。

### F25〔P1〕写入职责和规则同步时序需要调整

E2 的 tests/pipeline/** 与 E3 的 parity/gen 写集合重叠；docs、公共测试件、部分媒体脚本与 site 漏写负责人。“主会话可派 E3 渲染”又不在 E3 可写集合。分配表缺环境、资源、共享归属等必要字段。

计划套用 Claude 的 opus/sonnet、worktree/sub 提交流程，不能直接成为 Codex 子代理命令。Codex 默认继承当前模型、共享目录按不重叠文件集合，子代理不暂存/提交/push；主代理负责整合。

S1 就调用规则同步 apply，S6 才登记 sync-targets；apply 只替换已登记且有标记的目标，不会生成全部项目规则。锁仓之后再补规则又违背零提交。

**处置：**先登记目标并准备标记与项目专属规则，再同步检查；benchmark 锁定前完成最后规则变更。公共件、配置、lock、gitlink、规则文件由主会话唯一负责。

### F26〔P1/P2〕历史结果与 pytest 退出 0 不能替代新链路验收

`gate2_compare.py::compare_ext` 完整性成功后可以给 INFO，并不保证动作或轨迹无差异。旧 Oracle 1600 步、Astra未实跑等结果也不是五策略新两档的统一基线。

`test_inventory.py::check_contracts` 允许 pytest 门禁过而 TEST_CONTRACTS 判定失败；“无缺条目”与“无 planned/pending”不是同一条件。不能删除契约条目或改变状态来变绿。

**处置：**复用 `client_replay_eq.py` 的四路线×成功/环境异常/超时夹具，核请求、动作 dtype/shape/字节、顺序和终态，保留动作/请求/顺序篡改自检与双方同崩失败。扩为常驻两局、异常后下一局；Astra 用零外联 planner/monitor 夹具。

真实 GL 两局验收模型实际调用、步骤与记录、Policy加载/状态隔离、视频解码与同步；task_success 独立报告 0/1，不要求挑成功局。历史数据比较定位为解析和展示回归，不能冒充新旧语义逐位一致。

## 6. 预算完整核查：不要混淆单位

### 6.1 当前 HTML 安排的首跑展开

本表假定两个本机入口各选四局，即当前 HTML 的六个唯一身份版本；不含任何失败重试、递补、额外仿真测试或恢复重跑。

| 操作与乘式 | 逐侧/逐策略身份执行尝试 | 显式 env.reset 下限 | 假设统一 build+顶层reset 各1的预约额度 |
|---|---:|---:|---:|
| BENCH_SMOKE：1任务×2数据集×1局 | 2 | 2 | 4，尚需接入 |
| EVAL_EPISODE：1任务×1数据集×2局 | 2 | 2 | 4，新接口未实施 |
| 生成对拍：1任务×2数据集×2局×2侧 | 8 | 8 | 16，尚需统一 |
| reset 对拍：1任务×1档×4局×2侧 | 8 | 16 | 32，尚需接入 |
| GL普通模型：4策略×1任务×2数据集×1局 | 8 | 8 | 16，现普通客户端已有计量 |
| GL Astra：1策略×1任务×2数据集×1局 | 2 | 2 | 4，当前无共享reset claim |
| 合计 | 30次身份执行 | 至少38次 | 76仅是新统一计量提案 |

这 30 次不是 30 个唯一身份。完整交互/专家生成是 dummy 4 局 + 两侧专家生成 8 局 + GL policy 10 局 = 22 局；另有 1任务×1档×4局×2侧 = 8 次 reset 探针身份执行。

本机显式 reset 为 2+2+8+16=28，GL 为10，下限合计38；当前 R5 的本机20+GL10=30少算探针内部 reset。探针的包装 reset 还生成 8 段 VideoUnmask 演示，不是完全不生成演示轨迹的静态检查。

### 6.2 推荐“四身份复用”版本的变化

若用户确认 D2 采用整项四身份复用，生成仍是 hard-verify两局+ood两局，reset只复用两局hard-verify：

```text
生成：1任务 × 2数据集 × 2局 × 2侧 = 8次身份执行/完整专家生成
reset探针：1任务 × 1档 × 2局 × 2侧 = 4次身份执行
reset探针显式调用：1任务 × 1档 × 2局 × 2侧 × 2次 = 8次
全项身份执行：26次；完整交互/专家生成仍22局
全项显式env.reset下限：30次
按build+顶层reset各1的新统一计量提案：60额度
```

此版本有四段额外探针演示，必须同步更改判定形状与子集分母。30仍只是显式调用下限，60仍只是建议计量，均不是已经实现和实测的物理 reset 完整上限。

### 6.3 已有计量与实际调用的差别

| 事实 | 代码锚点 | 不能据此推出什么 |
|---|---|---|
| 普通客户端每次预约2额度 | `env_client.py::NEW_SIDE_RESETS_PER_ATTEMPT/EnvSession._claim/build/reset/_reserve` | 不能当每局只一个额度，也不能保证观察了所有内部reset |
| reset探针另建底层环境 | `hard_regression.py::_PROBE` 的 base.reset 和 env.reset | 四局两侧不是只8次显式reset |
| Astra两局显式环境reset为2，另有2 build事件 | 固定Astra gitlink的 `examples/champ/runner.py::episode` | client.reset清策略状态，不算仿真reset；不能把build事件未经定义变成物理次数 |
| Astra没有共享reset claim | `astra_hard_runner.py::TracedBuilder/TracedEnv/media_inputs` | 费用守卫不等于reset/轨迹预算守卫 |
| reset账本超限只告警 | `budget_ledger.py` 的超额 BUDGET_WARN 分支 | 保留旧账本不能保证授权预算硬限制 |
| 历史生成曾按每局3额度预约 | `docs/1003-noise-baseline.md` 的 attempts/resets记录 | 不能与普通eval每局2额度混成同一物理计数 |
| 包装reset向下转发并产生演示 | `DemonstrationWrapper::reset` | 各层super转发不重复当独立顶层尝试；演示也不能忽略 |

gym.make内部构造、拒绝采样与恢复是否增加底层调用，未由本轮静态审计完整证明。新 plan 必须定义计数层级、入口前硬守卫、每次失败与重试如何消耗、不能绕开的计量覆盖；不以“至少38”或“至少30”代替完整上限。

### 6.4 重试与 Astra 的独立限制

- 普通席位旧默认有客户端重启8、服务重启2、无进展重启1；本轮不能自动继承。
- 建议首版自动 episode 重试为0。若用户选择有限基础设施重试，先给全项额外尝试、reset、轨迹与费用上限，并纳入同一硬守卫。
- 正常业务失败、规划失败不为挑成功局重跑；媒体失败只处理已有素材。
- Astra `CostGate.register_episode` 去重身份而非总尝试。同身份换 RUN 可以重新建环境，不增加登记身份数，所以“最多两身份”不保证“最多两次尝试”。
- Astra API的特定429有界传输重试与episode重跑分开；每次发送都保留费用预留和心跳检查。
- 旧本机Astra批次已有1局、0.3043美元。本轮GL两局数量已由新要求给定，但新账本和最多5美元要明确；不能偷用旧账本剩一局或借旧大预算。
- 全项计量不按阶段、机器、worker或子代理重置。P3阈值不是授权 agent 自动追加样本的额度。

## 7. 测试迁移表与原“七条待裁决”的修正

### 7.1 推荐归属

| 对象 | benchmark | eval | 关键处理 |
|---|---|---|---|
| unit/hard、robomme、wrappers、common | 保留 | — | import、根定位、nodeid改接 |
| contract的包规格/builder/metadata/registry | 保留 | — | 裁退役功能，保拒绝负例 |
| challenge、recording | 保留 | — | 包含官方及hard包装器测试 |
| static的包装、入口、资源守卫、官方字节 | 保留 | 对应eval版 | 按新树建精确白名单 |
| tier_table/regression_on_packaged | 包规格断言保留 | hard_regression工具断言保留 | 按受测对象拆，不形成benchmark→eval依赖 |
| pipeline/eval、evalx | — | 保留 | 适配新Policy、记录与历史schema |
| pipeline/parity | — | 保留有效部分 | 裁退役train夹具，保HDF5有效比较矩阵 |
| gen选定rollout测试 | — | 保留有效部分 | 拆gen_world，去freeze加载依赖 |
| site与其测试 | — | 配套保留 | 不只搬站点代码漏测试 |
| _support、conftest、mutation | 各一份 | 各一份 | 主会话唯一负责人，重切路径与配方 |
| inventory、合同总表、delta、mutants | 重切 | 重切 | source/target/nodeid无悬空，新测试实际收集 |

公共件采用tests根还是全部嵌套，是代理在已批准tests目录内解决的工程布局；须写清并验证，不需要把每个import问用户。

### 7.2 七条原结论的校正

| 原条目 | 审计结论 |
|---|---|
| challenge/recording只测官方 | challenge属实；recording还参数化hard录像器，原理由不准确。两者仍建议归benchmark |
| mutation是共用基础设施 | 属实，应保留按新仓裁剪后的配方，不随生成测试删除 |
| support/conftest/总表未分配 | 属实且会阻断收集，应唯一归主会话 |
| 大约八个函数要改 | 低估；builder、constants等还有额外依赖。至少十一处已识别函数需要处理，不能以“八个”冻结实现清单 |
| BENCH_NO_GEN词表误报 | 属实，同时存在正则和目录错误导致假通过；改语义闸门，不删合法来源 |
| 91测试、66文件、592函数 | 91是跟踪文件数含夹具；66是test文件；592只属eval+evalx；原91文件范围顶层test函数约698。参数化收集数未实跑统计 |
| 漏写集合/P1/pytest | 属实；E2/E3写集合重叠，配置和公共件漏负责人 |

“800还是992专家局”是真正规模选择；“9c78源码锚过期”不是成立的代码漂移结论，见第9节。

## 8. 应补齐的验收与连续执行顺序

本节给接手代理修订计划的验收要求，不是新的完整实施计划。正文回写仍遵守两部分格式，用户关注的实跑三项留第一部分，其余机检留第二部分。

### 8.1 验收要逐项具名

| 判定族 | 应实际证明的内容 |
|---|---|
| BENCH_DELTA / BENCH_UPSTREAM | 精确路径白名单、官方核心字节与模式、工作区/索引/未跟踪归属、最终SHA |
| BENCH_SPECS_SHA / BENCH_DATASETS | 五份规格钉值、两数据集局数乘式、退役入口拒绝、默认构造契约 |
| BENCH_PACKAGE | 非editable wheel安装与资源齐全，真实执行，skipped=0 |
| BENCH_REGISTRY | 三种hard导入顺序与official_only独立对照，定向slow实际执行，skipped=0，不增加reset |
| BENCH_ENTRY_DIFF / BENCH_NO_GEN | 入口内容白名单、生产退役接口关闭、合法来源与负例保留 |
| EVAL_IMPORT | 主与各子环境editable实际指向；嵌套源码规则正确 |
| CLIENT_REPLAY_EQ | 请求/动作/顺序/终态、连续两局、异常后下一局、篡改自检；Astra零外联夹具 |
| EVAL_EPISODE | 两局实际模型调用、load/reset/end/close次数、cap跨档、原动作与记录映射、允许错误产物 |
| EVAL_RENDER_EQ | 官方绘图语义和有损画质分别验证，不只一个整帧PSNR |
| EVAL_TESTS / TEST_CONTRACTS | 实际收集与通过数、核心测试未漏收、合同状态与缺项分别报告 |
| PARITY_IMPORT | 目标目录存在、真正的依赖闭包、轻量导入、旧外部覆盖入口关闭 |
| PARITY_GEN_SMOKE | 正确双侧基线、有效HDF5、身份/规格绑定、实际比较数、双方失败独列 |
| XHARD0_RESET_PARITY | D2选定子集和分母、独立进程、计量完整、确定性层比较定义 |
| EVAL_SMOKE_GL | 五策略各两身份、实际服务状态、完整解码、步/帧/动作对应、权威终态无遗漏重复 |
| BENCH_LOCKED | 全部验收后远端main、解引用tag与gitlink一致，技术只读和标签保护实际生效 |
| 收尾判定 | 媒体发布完成、本轮服务清理、本轮JobID逐个处置、留档完整、当前upstream无ahead |

0/1业务成功字段独立呈现。执行退出0、文件存在、健康端点、GATE2=INFO、pytest无错误，都不能单独替代这些判定。

### 8.2 建议调整现步骤表

1. **一次定选择和完整预算。** 先补资产/环境/身份/资源表，再集中呈现D项；不在正式执行时才选变体或发明参数。
2. **完整方案再认可。** 正文、表、runbook和SVG同一口径；无未定CLI、无表外写任务。
3. **开工后按集群规则安排占位。** GL任务已确定时让排队与开发并行；记录全名单。超规格/数量的处理按AGENTS与greatlakes实际规则，不自行套旧运行权限。
4. **S1产生benchmark候选提交。** 完成包、测试、规则与字节检查；作为eval gitlink，不立即最终锁死。
5. **S2/S3完成eval与对拍依赖。** 先CPU真实格式夹具，覆盖错误、超时、常驻、媒体与接续；环境准备和来源校验通过后才进入仿真。
6. **最小smoke计入整项预算，再执行所选实跑。** 不为每阶段另外增加一轮“最小smoke”；复用已计身份及结果，禁止默认放大。
7. **专家视频只按D6范围离线渲染。** GPU/仿真预算不被渲染隐式扩大；长CPU任务同样tmux留档。
8. **完成相关验收与最终修补后锁benchmark。** 完成最后规则同步；固定tag、保护与eval gitlink。
9. **提交、同步与归档。** 所有已授权工作由接续/宿主等待处理到结束；按确切清单清理，不动旧任务资源、站点、在途修改。

### 8.3 故障处理必须事先写成矩阵

| 故障 | 可继续的部分 | 停止/恢复约束 |
|---|---|---|
| task_success=0 | 记录有效失败，继续下个身份 | 不挑成功重试 |
| 生成正常失败 | 保留失败证据 | 不把双方失败当生成通过，不递补成功样本 |
| 单局普通异常 | 健康Policy可继续 | 单局finally、明确产物缺项，尝试计数已消耗 |
| 硬超时/服务死亡/污染 | 独立监督器仍运行 | 按有限预算恢复；可终止边界与精确PID清理 |
| 媒体编码/发布失败 | 已完成仿真结果仍有效 | 只处理已有素材，不重新评估 |
| 费用守卫过期/额度不足 | 其他不受影响模型可按方案继续 | Astra发送前拒绝，保留账本，不新建账本绕额度 |
| 子检查器崩溃/报告缺键 | 保留日志与已有成果 | 外部监督失败、停止依赖阶段、通知；不把缺项当0 |
| Git push被拒 | 已有成果与报告保留 | 原始报错交用户，不force、不反复重试 |

## 9. 已确认静态证据与重要反证

### 9.1 源码锚没有漂移

执行：

```bash
git diff --name-status 9c78c076 108c468f40bf8f445b766734806dcc31cd3f201b
git diff --stat 9c78c076 108c468f40bf8f445b766734806dcc31cd3f201b -- src scripts tests pyproject.toml .gitmodules third_party
```

两条退出码0。第一条仅新增HTML、修改AGENTS/CLAUDE/greatlakes；第二条无输出。因此9c78可作源码来源锚。最终归档若要保留最新批准计划与规则，应另记归档截止提交，不把来源与归档锚混成一个字段。

### 9.2 五份规格指纹一致

对五档逐项计算，以下只读命令可复核锚定Git blob：

```bash
set -o pipefail
for audit_tier in xhard1 xhard2 xhard3 xhard4 xhard5; do
  git show "108c468f40bf8f445b766734806dcc31cd3f201b:src/robomme_hard/env_metadata/ood/${audit_tier}/specs.jsonl" | sha256sum || exit 1
done
```

五条退出码均0，输出逐项与冻结的 `tests/contract/packaged_specs.sha256` 相符：

| 档 | SHA256 |
|---|---|
| xhard1 | d46f451de0178da7358dcc98fd202a4c07c4c6380a27cd23decda6d652d565d8 |
| xhard2 | fc051c9061505d6401a1c0324f00096c62a6cb93124a7f8e4f695ae1f6e7baa3 |
| xhard3 | cee184ad403cce15d7f3aff7f80ff2c24af77ab4c71fae2ff1d34c1d3c645168 |
| xhard4 | 97cf20f94cfc276452a84cb85d435915dd75c5c91a6e5db1ca4b4b3f6d6d20c5 |
| xhard5 | 60f1157a9b119a3bcb48d93ac3667775fe5f96e0cf341a551a4f0de470844f5d |

未运行load_specs、wheel、reset，不扩展为运行通过。

### 9.3 AV1实验的证据边界

祖先 `4c9e6136…` 的commit body记录编码实验过程和工具链；计划HTML列单局数字。本轮未复跑。冻结docs/scripts/tests对 `libaom|AV1|crf24|cpu-used` 的只读检索零命中，退出码1。应将数字视为已有单局观察，补指纹与记录后才作可复核基准。

### 9.4 已有覆盖授权不重复申请

hard包当前导入注册16环境id、继承官方builder并覆写、使用shim。这些历史机制不是本轮新越权；已有文档记录与本轮五处裁剪确认可沿用。官方字节相同与“运行行为没有被覆盖”是不同结论，必须保持独立原侧进程。

新增官方录像器改动、未列方法覆写、第三方升级仍不在沿用授权范围。不得为了通过新媒体协议给冻结录像器打生产补丁。

## 10. 旧运行遗留：不应绑架本轮拆仓

`docs/1002-pending-decisions.md` 的T3仍有旧OOD事项：旧800局是否续跑、上下文超限如何计分、86局分母扩不扩、PP重跑token、历史产物清理、旧站点和占位去留。

它们不阻塞拆仓技术实现。除新任务实际需要复用其中资源之外，不合成“必须全部裁决才能拆仓”的额外条件；本轮也不顺手清旧产物、关站点或恢复旧800局评估。

2026-10-08用户已接受第一档生成与第二档hard0对拍的历史噪声。不要借新审计重新要求所有历史局逐位一致或擅改容差；新拆分用固定假接口检请求/动作语义，真实小样本如实报告差异。

## 11. 给接手代理的交接清单

### 11.1 必须先做

- 读取本报告固定锚；当前仓库若已变化，区分新报告交付提交与新的源码变更，不自动重锚。
- 只按用户明确要求修订原HTML，不实施拆仓，不运行仿真或GL，不上传HF。
- 把F项逐一标为“计划已补/无需改及依据/仍未决”；不静默删除审计发现。
- 将D项合成一次决策，不把已确认事项再次问一遍。
- 提供两种四局预算的完整计量定义，补所有入口硬守卫与重试上限后再请批准。
- 清点各模型环境、现有资产、身份、GL资源；大新增获取只列清单，不擅自下载。
- 回写两部分结构与子代理边界，完整复核HTML正文和所有SVG，避免只改正文图仍旧。

### 11.2 不得做

- 不将本报告视为开工令，不将“对抗验证”视为修改源代码授权。
- 不碰SimpleMemVLA在途内容，不暂存用户或其他代理改动。
- 不增加大规模reset、候选抽样或rollout，不以每个阶段重置预算。
- 不在锁死后自行修benchmark，不升级四个gitlink、不改冻结录像器。
- 不用双方失败、INFO、skip、读取错误或丢失字段制造PASS。
- 不把旧运行的大预算/费用/五天job当成1008新任务授权。
- 不把实际显式reset、build预约额度、policy.reset和唯一身份数混为一个总数。
- 不承诺未验过的自动接续或唤醒，不因进tmux就提前结束仍有已授权工作的回合。

### 11.3 本报告交付核验范围

本文件为纯文档交付，验证使用 `git diff --check`、文件范围与Markdown链接核对、审计锚和关键术语/计量一致性审阅；不启动无关训练、pytest或仿真。实际验证与提交推送结果由交付回合说明，不能把本节当成事先已通过的结果。

现行AGENTS第2条要求完整计划呈现之后才认可开工；对计划提出修改则要修改完再次呈现。接手代理应先把上述工程修正写成完整可审方案，最后取得一次明确认可，再按整份已定预算连续执行。
