> 本文按用户最新要求重排为“接口 → 逐任务改动 → 三组对拍”三部分，替代此前两部分体例；只改计划，不构成开工令。工作副本为 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支为 `newtask-v3-MotionJepa1006`。本次修订前 HEAD 为 `465a09cec04da9ebec9d81efc08e9174e8085d94`；原源码核查锚点为 `13905997d45155ff1c98417511aedec92578042d`，生成代码起点为 `3a5951a834ea014f63724647ab0bc091eb9f109d`。ManiSkill 来源仍钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，依赖以本分支 `pyproject.toml、uv.lock` 为准。接口、次数和测试节点均为拟议项，尚未实施。

# 第一部分：接口怎么改

## 1. 输入不再是新 seed，而是现有 test 的 hard 样本

**读取现有 test metadata 中标为 hard 的记录，用其中实际保存的 seed 和场景派生两档。** XHard1／XHard2 使用同一条原记录作为母样本，不另挑 seed、不按公式重算成功 seed、不覆盖原 HDF5。

来源为 [test metadata 目录](src/robomme/env_metadata/test)，按 `records[].difficulty == "hard"` 筛选，保留原 `task、episode、seed`。例如 PickHighlight 的 episode 3 实际 seed 是 `620301`；不能重新算成 `620300`。母组键为 `(source_split=test, task, source_episode, source_seed)`，两档与原样本归同组，继续属于测试数据；转作训练需另议划分。

用户已明确：“目前你就直接用现在的 test seed 去派生 task，用 test 的 hard 来派生，就不需要用新的 seed 来派生了。”因此旧版“选择新 seed 区间、与 test seed 零重合”的要求作废；现在检查的是来源对应正确、同一目标档内无重复、母组不跨数据划分。根 README 仍有旧的新 seed 描述，本轮仅改本计划，以这条最新决定为准。

## 2. 一个来源入口，一个可选的目标档参数

在现有 [generate_dataset_newseed.py](scripts/data-generation-newSeed/generate_dataset_newseed.py)::`_args、generate_dataset_newseed` 中拟新增：

| 参数 | 用途 |
|---|---|
| `--source-test-hard` | 启用上述来源读取分支；不走新 seed 的计算公式。 |
| `--target-difficulty hard\|xhard1\|xhard2` | 可选覆盖目标档；`hard` 专门支持同值对照，另两档用于派生。 |

三种调用的意思如下，均以 `--source-test-hard` 选择同一批母样本：

| 调用 | 生成器传给 ENV 的难度 | 预期 |
|---|---|---|
| **不传目标档** | 继承来源记录的 `hard` | 完整复现原 hard 流程。 |
| **传同样的档：hard** | `hard` | 与不传目标档相同。 |
| **传新档：xhard1／xhard2** | 对应新档 | 场景仍来自 hard，只增加获准次数。 |

没有这两个新参数时，旧入口的默认值、三档比例、seed 公式和调度保持原样。新来源分支与显式旧 `--difficulty` 比例、`--layout`、`--episode-start` 互斥，避免一边读原记录、一边重新计算身份；原始 episode 不重编号。`--episodes` 在新分支中表示每任务按原 episode 排序后选取的 hard 记录数量，不足时报错、不补 seed。仅传目标档而未指定来源时报错；不能把旧参数的隐含默认值误判为显式冲突。选中的任务有不支持项时建池前报错，不静默删掉任务。

`EpisodeJob` 保留来源身份、目标档及恢复模式；原 hard 的恢复设置须从真实来源核对，不以新循环序号推断。新来源分支不调用 `EpisodeJob.bump` 换 seed。任务失败照实记录；基础设施故障仅在获批预算内同 seed 有限重试。

## 3. ENV 内怎样分开布局和次数

在 [difficulty.py](src/robomme/robomme_env/utils/difficulty.py)::`normalize_robomme_difficulty` 增加默认关闭的 `allowed_difficulties`：普通调用仍只接受 easy／medium／hard，已实现的 ENV 显式传自己的支持集合。未知标签和未支持的新档提前拒绝。

每个获准 ENV 的 `self.difficulty` 保存目标档；新档的 `layout_difficulty="hard"`，旧档保持原值。布局字段读母档，次数字段读目标档，用新字典扩展，不原地修改 hard 配置。例如 PickHighlight：

```text
现有 test hard 记录
  → 生成原来的 6 个方块及目标排列 A、B、C、D、E、F
  → hard 取前 3 个；xhard1 取前 4 个；xhard2 取前 5 个
  → 原 planner、原录像器 → 完整原始 HDF5
```

旧链路是“三档调度 → ENV → 原 planner／录像器”；新来源分支是“test hard 记录 → 可选目标档 → ENV hard 布局与目标次数 → 原 planner／录像器”。增加动作会增加帧数，不截断、不加速；RGB 仍为每路 `uint8[256,256,3]`，每帧 196608 字节；动作仍为 `[8]`，dtype 按实物核对。没有模型或训练参数改动。

生成器在外部 `sample_manifest.jsonl` 记录来源 metadata 指纹、母样本身份、布局字段、目标档、实际次数、成功字段、失败原因、重试/reset 计数，以及新 HDF5 路径、字节数、SHA256。布局浮点字段保留原 dtype、shape 和数值，不能只比字符串哈希。成功取已有最终求值快照，不额外调用可能改变状态的 `evaluate`；未取得终态时记 `TASK_SUCCESS=NOT_OBSERVED`。原 metadata、录像器和 planner 不改。各档及分片使用独立输出目录，防止同名合并文件或 metadata 被覆盖。

# 第二部分：每个任务改什么

**以下数字是候选，均未经过新档仿真验证。** 所有文件均在 `src/robomme/robomme_env/` 下；各行涉及的受保护文件和锚点须逐项批准后才能改。

| 任务／文件 | 具体机制与修改锚点 | 原 hard → XHard1／XHard2 |
|---|---|---|
| `PickHighlight.py` | `configs、__init__、_load_scene、step、evaluate`：增加配置与解析，保留 6 块和原排列，目标切片、高亮、任务完成读取新次数。 | 拾取 3 → **4／5 个**。 |
| `PickXtimes.py` | `configs、__init__、_load_scene、evaluate`：只增次数范围，保持 3 色场景；次数与场景随机流分开，任务数仍按 `2n+1`。 | 4～5 → **6～7／8～9 次**。 |
| `SwingXtimes.py` | `configs、__init__、_initialize_episode、step`：只增目标计数，保持圆盘、布局与计数边沿；原 `max_swings=2n`、任务数 `2n+3` 不变。 | n=3 → **4～5／6～7**。 |
| `RouteStick.py` | `configs、__init__、_load_scene`：加长路线，保留障碍与 `backtrack=True`；不改旧的默认难度选择。 | 长度 4～7 → **8～10／11～13**。 |
| `PatternLock.py` | `configs、__init__、_load_scene、_initialize_episode、evaluate`：5×5 网格不变，增加不重复节点数；新档搜索 1000 次仍不达长度即报失败，不沿用不合格末次路径。 | 节点 4～8 → **9～12／13～16**。 |
| `VideoRepick.py` | `__init__、_load_scene、_initialize_episode`：将重抓次数配置化；布局判断读 hard 母档，保留 15 块聚集场景及 `swap=0`。 | 重复 1～3 → **4～5／6～7 次**。 |
| `StopCube.py` | `__init__、_initialize_episode、step、evaluate`：增加停止序号并延长运动段；原速度、rotation、起终点不变，完整保留原 interval、速度、stop_time、rotation 抽样后再覆盖停止序号。 | 第 2～5 次经过 → **第 6／8 次**。 |
| `VideoUnmaskSwap.py` | `configs、__init__、_load_scene、_refresh_swap_schedule、step`：增加交换 pair 和调度窗口，每段仍 50 步、最终仍抓 2 个；不改最近邻和原索引行为。 | 交换 2～3 → **4／5 次**。 |
| `ButtonUnmaskSwap.py` | 与视频版相同，另外保留原左右按钮流程、隐藏物和抓取顺序。 | 交换 2～3 → **4／5 次**。 |
| `BinFill.py` | 暂缓；若另获批准，在 `_load_scene、_initialize_episode` 先按原 hard 固定每色库存，再定新投入量，必须满足 `target_i <= inventory_i`。 | **暂不定次数**，不增物体、不换 seed 挑库存。 |
| `VideoUnmask.py` | 暂不改：原来抓 2 个，只有 3 个隐藏物；现有固定分支不能仅靠参数生成两个更长档。 | **保留三档**。 |
| `ButtonUnmask.py` | 暂不改：同样只有 3 个隐藏物，`pick>1` 只追加第二次动作。 | **保留三档**。 |
| `VideoPlaceButton.py` | 暂不改：固定放置与前后布尔分支，没有现成的任意次数循环。 | **保留三档**。 |
| `VideoPlaceOrder.py` | 暂不改：4 个台、不重访，原 hard 已可能访问全部 4 个；不引入重访。 | **保留三档**。 |
| `MoveCube.py` | 按此前决定，不新增动作规则。 | **保留三档**。 |
| `InsertPeg.py` | 按此前决定，不加入反复拔插。 | **保留三档**。 |

两项尚需定清的机制：

- **Swap 第 4／5 次由谁发起**：候选为循环复用原三个发起者的顺序 `A→B→C→A→B`，不是重新随机挑选；尚待确认。
- **路线是否延续原路径**：RouteStick、PatternLock 当前方案保证同布局上生成更长合法路线，尚不保证以原 hard 路线为前缀；PickHighlight 则明确使用同一目标排列的更长前缀。

所有 ENV 都要枚举 `difficulty/configs` 消费点，区分布局、次数、指令和成功条件，不能漏掉 `== "hard"` 分支导致新档进入 easy 布局。语言若不能表达新增次数，暂停该任务并另列改动，不顺手改 `task_goal.py、subgoal_language.py、vqa_options.py`。

# 第三部分：三种调用怎样对拍

## 1. 先固定对照物，再跑三组

**三组都使用同一条 test hard 记录、同一环境和依赖，逐组留证据。** 旧代码在上述源码锚点的隔离工作副本中运行；新代码使用实施后的 clean HEAD。先核对硬件、依赖、真实数据身份、恢复模式、相机与 reset 顺序，不覆盖用户工作区。

| 组别 | 新代码怎么调用 | 与谁比较 | 必须证明什么 |
|---|---|---|---|
| A：不传入 | 测试直接构造 ENV，使用来源 seed，**完全省略 `difficulty`**。 | 旧代码用同一 seed、同样省略 `difficulty` 执行。 | 改造前后默认选档、布局、次数、指令和完整轨迹内容一致；不要求默认档一定是 hard。 |
| B：传入同样的 | 显式传原档 `difficulty=hard`；生成入口对应 `target_difficulty=hard`。 | 旧代码用同一来源 seed、显式 hard 执行。 | 原 hard 的布局、次数、指令和完整轨迹内容不变。 |
| C：传入新的 | 同一来源，分别传 `xhard1` 和 `xhard2`。 | B 组显式 hard，以及每个任务约定的新次数。 | 执行前布局一致；任务、指令和实际动作次数按新档变化；完整记录且独立报告任务成功。 |

C 组有意增加动作，不要求整条轨迹与 hard 相同，也不要求两个新档互相相同。变化清单必须预先列明：目标档标签、次数、对应指令/任务列表，以及执行新增动作后的帧、状态、动作和终态；布局初态、速度和记录接口不能随之改变。

**A 对拍的是旧默认行为，B 对拍的是原 hard，两者不强求相等。** 当前 PickHighlight 不传难度时按 `seed % 3` 选档；真实 test hard 的 seed `620301` 整除 3，不传会变成 easy。RouteStick 不传时最终固定 easy，也必须原样保留。A 组由测试直接构造 ENV，不通过始终传来源难度的生成器。

生成器层再做一项同值检查：启用 `--source-test-hard` 时，“省略目标档”与“显式目标档 hard”生成的 ENV 参数和 job 内容一致，统一落到 B 组；这不等于 ENV 完全省略 `difficulty`。旧 CLI 不使用新参数时，另比较旧／新 job 列表、比例、默认值与 seed 公式。

## 2. 具体比较哪些东西

| 层次 | 检查与判据 | 具名输出 |
|---|---|---|
| 来源 | 原 test metadata 实际记录、hard 标签、seed、episode 与母组一一对应；原件指纹不变；同档无重复，同母组不跨 split。 | `SOURCE_TEST_HARD=PASS mismatches=0`、`ORIGINAL_REUSE=PASS changed=0`、`SPLIT_ISOLATION=PASS shared_groups=0`。 |
| 默认与接口 | A 组旧／新默认行为一致；B 组旧／新 hard 一致；生成器省略目标档与显式 hard 的参数一致；非法标签、未支持任务和冲突参数均拒绝。 | `DEFAULT_COMPAT=PASS mismatches=0`、`SAME_VALUE=PASS mismatches=0`、`DIFFICULTY_API=PASS invalid_accepted=0`。 |
| 母布局 | A 组新旧默认布局互比，B 组新旧 hard 布局互比，C 与 B 的 hard 比；逐项比较物体数、身份、颜色、位姿、相机、机器人初态和速度，浮点按原 dtype 的原始值比较。 | `NATIVE_LAYOUT=PASS mismatches=0`、`HARD_LAYOUT_BRANCHES=PASS unclassified=0`。 |
| A／B 完整轨迹 | 比较 HDF5 全部 group/dataset/attribute、dtype、shape、逐帧 RGB、状态、动作、subgoal、demo/exec 和终态；只排除预先列明的运行路径/时间/provenance 字段并保留差异清单。 | `LEGACY_TRACE=PASS content_mismatches=0`；容器 SHA256 另记，不用哈希不同直接代替内容比较。 |
| C 新任务 | 目标数、指令、计划、真实完成事件一致；两档分别验收，成功字段与进程退出码分开报告。 | `COUNT_ONLY=PASS expected=... actual=...`；`TASK_SUCCESS=0\|1` 或 `NOT_OBSERVED`。 |
| C 完整记录与上限 | 连续 timestep、两路 RGB、动作/状态/终态齐全；不提高 2000 步守卫，随机范围逐档实跑上端次数。 | `H5_CONTRACT=PASS missing=0 gaps=0`、`STEPS_HEADROOM=PASS resolved_count=max elapsed_steps=... limit=2000 margin=...`。 |
| 冻结与预算 | 源码对比和运行时审查证明未覆盖录像器；所有构造、reset、轨迹尝试和基础设施重试计数。 | `RECORD_WRAPPER_FREEZE=PASS changed=0`、`BUDGET=PASS resets=... trajectories=... infra_retries=...`。 |

A／B 默认先按内容逐位相等验收；出现浮点差异就保留 FAIL、定位环境或执行差异，不自行放宽容差。报告区分字节级、结构、数值容差和行为一致，不能用一次成功回放替代内容对拍。C 组成功也不证明训练链路等价，本轮不启动训练。

## 3. 执行阶段、预算与验证入口

| 阶段 | 做什么 | 通过条件 |
|---|---|---|
| P0：定口径 | 确認现有 test hard 对应的实物和恢复设置、候选次数、Swap 规则、逐项源码批准、资源和预算。 | 来源清楚、环境明确；必须再有对应阶段的明确“开工”。 |
| P1：接口与首例 | 公共解析、来源入口、PickHighlight 及轻量测试。 | `DEFAULT_COMPAT、DIFFICULTY_API` 通过，录像器冻结。 |
| P2：首例对拍 | 1 任务 × 1 母样本 × 1 worker，先 A 的旧／新默认对照，再 B 的旧／新 hard，再 C 的两个新档；一项失败即停，不直接放大。 | 上表各项逐项报告；没有自动重试。 |
| P3：逐任务推广 | 按第二部分获批范围接入，每任务重复 A／B／C；额外验证随机次数上端。 | 各任务、各档单独结论，不用首例代替全体。 |
| P4：正式派生 | 另定实际母样本数、run_name、输出路径和总预算。 | 全部前置检查、clean HEAD、Beta 锚点、留档和正式开工齐备。 |

**旧版“首例只需 3 次轨迹”的预算作废。** 新矩阵按 6 次录制预算：A 的旧／新默认各 1 次＋B 的旧／新 hard 各 1 次＋C 两档各 1 次，不预先假定两组可复用。reset 数按构造与显式调用实测累计，不能把录制次数当作 reset 次数。推广到 9 个任务仅基本矩阵即 54 次录制，另加旧三档补充回归及随机范围上端用例；须在实跑前列出完整预算并批准，不分批绕过门槛。

拟新增测试文件：`tests/lightweight/test_xhard_count_config.py` 检查来源/解析/默认/错误路径；`tests/dataset/test_xhard_count_generation.py` 承担三组真实录制和内容对拍。以下为实施后才可运行的拟议命令，测试节点目前不存在：

```bash
# 在本工作副本执行；依赖须预装，数据身份与预算须已批准。
UV_CACHE_DIR="$PWD/artifacts/cache/uv" uv run --frozen --no-sync python -m pytest tests/lightweight/test_xhard_count_config.py -q
# 此节点只做一个母样本的三组对拍；默认行为和上端用例另行计数。
UV_CACHE_DIR="$PWD/artifacts/cache/uv" uv run --frozen --no-sync python -m pytest tests/dataset/test_xhard_count_generation.py::test_pickhighlight_three_way -q -s
git diff --quiet 13905997d45155ff1c98417511aedec92578042d -- src/robomme/env_record_wrapper/RecordWrapper.py
```

验证证据落 `artifacts/validation/<获批唯一验证名>/`：`source_manifest.json、api_and_defaults.json、layout_comparison.json、trace_comparison.json、counts_and_success.json、budget.json`；各录制分组独立目录。每项保存完整命令、退出码、输出路径、具名判定和审查摘要。基线录制由预算明确授权，生产阶段不重复录制 hard 原件；每个新档最终轨迹只录一次，encoder／VLA 从同一份原始 HDF5 派生输入。

## 4. 实施分工与剩余边界

主会话负责获批受保护源码，生成器、测试、文档各有唯一子代理负责人；按“公共解析 → ENV → 生成器 → 测试 → 审查”整合，整合前查范围和契约、整合后核对证据。下表仅规定未来分工，不授权当前写代码或实跑。

| 负责人 | 可写集合 | 禁触与依赖 | 验收／资源 |
|---|---|---|---|
| 主会话 | 逐项获批的 `difficulty.py` 与第二部分 ENV 文件/锚点 | 未获批源码、原数据、planner、录像器不动；公共接口唯一负责人 | 本副本轻量测试及冻结检查；本阶段不默认占 GPU。 |
| 生成器代理 | `scripts/data-generation-newSeed/generate_dataset_newseed.py` | 不写 src、seed_layout、原 metadata；依赖 ENV 接口 | 来源/同值/错误路径检查；不自行启动长任务。 |
| 测试代理 | 上述两个拟新增测试文件 | 不改生产源码、原测试或他人输出；依赖前两项 | 本副本三组测试；获批后仅 1 张空闲卡、1 worker，验证目录唯一负责人。 |
| 文档代理 | `scripts/data-generation-newSeed/README.md` | 不写根规则、源码和其他方案；接口定稿后更新 | 链接与 `git diff --check`；无 GPU/端口/tmux。 |
| 审查代理 | 无，只读 | 不执行项目代码、不暂存、不提交、不推送 | 整合前后按来源、兼容性、布局、次数与证据逐项审查；无运行资源。 |

未分配的共享文件由主会话裁决，不并发改同一文件。子代理不暂存/提交/push。长于 5 分钟的验证或构建必须另定 run_name，使用 detached tmux、`PYTHONUNBUFFERED=1、set -o pipefail、tee、EXIT_CODE=`；会话全名、命令和日志路径先记入 `docs/dataset-build-doc/<run_name>/launch.md`，结果与不可由 Git 还原的证据写 `result.md、records/`，更新索引。正式构建先打 Beta，provenance 要求期间冻结 HEAD；不归档脚本、配置拷贝或大 HDF5。不派表外长任务，只清理本轮清单里的精确会话。

仍待验证：实际原 HDF5 指纹与恢复配置、当前依赖及 editable 来源、新档成功率/步数、容量与路径搜索、消费端长轨迹上限。PatternLock 搜索失败、BinFill 库存不足、语言超容量、轨迹超 2000 步都如实失败；评估入口的 1300 步限制不在本轮修改范围。环境已见 Aspen、2 张 RTX A6000，但项目缺正式 A/B 判据表及 greatlakes 规约，实跑前先确认，不提交集群作业。

本轮只修改本计划，不改 README、规则、源码或依赖。文档交付检查三部分标题、16 任务、链接、围栏、三组比较对象与已废弃口径，运行 `git diff --check`。提交前逐项核对范围，只暂存本文件，中文编号接续 Git 日志；当前分支无 upstream，不自行建立或推送。

用户本轮结构要求原话：“分几个阶段说，第一部分先说你改动的这个接口是怎么做的。第二部分说你每一个任务打算改哪些东西。第三个你说对拍是怎么做，就是说不传入，传入同样的和传入新的，这三个都对拍。”
