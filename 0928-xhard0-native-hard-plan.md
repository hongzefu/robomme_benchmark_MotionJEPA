# 第一部分（给人看）

## 1. 目标、依据与授权边界

新增 xhard0，逐任务原样引用官方 test 中的 hard 子集：**16 任务 × 1 档（xhard0）× 12 局 = 192 局**。xhard0 是发布档名，底层运行难度仍为原生 `hard`；xhard1～4 的规格、数量、seed 和行为保持不变。

本方案工作副本为 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，代码锚点为 `447c041b733f70de84b320c5348347c6f27fe254`。官方源码锚点取自 [UPSTREAM.json](src/robomme_hard/UPSTREAM.json) 的 `src_commit=1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`，编排锚点为 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`。不从移动的远端分支重新取基线。本轮只写方案，不实现、不启动 reset、轨迹生成或集群作业；后续实施与完整动态验证须获授权，已确定的口径不重复询问。提交沿用 `12.<小版本> 中文描述`，以提交时日志为准。

用户原话按时间顺序保留：

1. 「给出方案 xhard现在有1-4 再加入xhard0 每个task50个episode 需要和原本的hard保持完全一致 根目录写方案 并且告诉我现在的容差范围是多大 为什么」
2. 对数量作用范围的确认：「仅 xhard0 每任务 50 局」。
3. 得知官方 test 混合三档后的最新决定：「和test的hard数量一致」。**本条替代每任务 50 局，不采用将 easy／medium 的 seed 强制改成 hard 的建议。**

### 已确定口径

1. 数量与身份来自官方 test 的 hard 子集，见 §2；没有新增抽样或补齐至 50 的步骤。
2. xhard0 执行原生 hard 语义，不属于新值族，见 §3。
3. “完全一致”按同身份、同环境、同输入的逐步数据零差验收；当前容差仅解释历史口径，不作为本次零差验收标准，见 §4、§5。
4. 本轮交付一份根目录方案；后续不改 `src/robomme/`，不新增 `scripts/` 顶层入口。

## 2. 当前数量与身份的实际情况

本轮用 `jq` 静态读取 [官方 test 元数据目录](src/robomme/env_metadata/test)：16 个任务全部为每任务 50 条，其中 easy 26、medium 12、hard 12。所有任务的 hard 原 episode 号均为：

```text
3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43, 47
```

筛选条件必须是记录的 `difficulty == "hard"`，再按原 `episode` 排序；这组号码用于当前锚点验收，不能替代字段筛选。seed 逐条照抄元数据，不能套公式重算，例如 PickXtimes 原 episode 15 的实际 seed 是 `511501`，不是 `511500`。

| 集合 | 当前／新增规模 | 合并后每任务局数 |
|---|---|---|
| xhard0 | 16 任务 × 1 档 × 12 局 = 192 局 | 所有任务新增 12 |
| xhard1～3 | 每档 13 任务 × 20 局，三档合计 780 局 | 对应任务原有 60 |
| xhard4 | 16 任务 × 1 档 × 20 局 = 320 局 | 所有任务原有 20 |
| 合并 | 16×1×12 + 13×3×20 + 16×1×20 = 1292 局 | 普通 13 任务各 92；StopCube、InsertPeg、MoveCube 各 32 |

这里的 episode 是评估身份数量，不表示已经拥有相应成功轨迹或 HDF5。官方 [episode_config_resolver.py](src/robomme/env_record_wrapper/episode_config_resolver.py)::`BenchmarkEnvBuilder.make_env_for_episode` 读元数据后现场构造环境；`DemonstrationWrapper.reset` 还会生成演示。现有 HDF5 回放是另一条链路。

## 3. 实现机制：发布档名与原生难度分开

### 3.1 身份索引直接引用官方元数据

在 [hard_builder.py](src/robomme_hard/env_record_wrapper/hard_builder.py) 中新增原生条目构造函数（拟名 `_test_hard_native_entries`）：读官方 test 元数据、筛选 hard，并保留 `source_dataset="test"`、`source_episode`、`seed`、`tier="xhard0"`、`runtime_difficulty="hard"`。读取时校验源文件摘要与锁定清单，以及任务、条数、原 episode 和 seed 唯一性；缺文件、重复、字段不符直接报错，不沿用官方加载器缺文件返回空字典的宽松行为。

不生成伪造的 `hard-specs/2` 行。现有 [hard_specs.py](src/robomme_hard/env_record_wrapper/hard_specs.py)::`TIERS`、`EXPECTED_CELLS`、`seed_rule_for`、`delivered` 服务于新值四档，要求冻结规格与成功 rollout。它们继续只管 xhard1～4；拟新增独立的发布档序列和 xhard0 数量约束。xhard0 来源用原元数据摘要固定，不需要复制一份容易漂移的 192 条新 seed 清单。

**建议保留旧全局 episode 编号**：`_test_hard_entries` 先保留原 xhard1→4 条目，再追加 xhard0。普通任务旧编号 0～79 不动，新增 80～91；三个仅 xhard4 的任务旧编号 0～19 不动，新增 20～31。xhard0 档内按原 episode 升序，`source_episode` 显式返回。展示与报表按 xhard0→4 排列，不把展示顺序强加为旧数据重编号。此编号安排为方案建议，并非用户原话。

### 3.2 构建时只走 hard 分支

`resolve_episode` 继续返回 `(seed, tier)`，xhard0 对外返回 `(seed, "xhard0")`；`make_env_for_episode` 必须区分发布档与实际难度，在调用 `gym.make` 前将该条目的难度明确设为 `hard`。

```text
xhard0 发布条目
  ├─ seed = 官方 test 的原值
  ├─ runtime difficulty = hard
  ├─ 不传 sampling_config
  └─ 不传 native_episode_spec
```

不把 xhard0 加入 [difficulty.py](src/robomme_hard/robomme_env/utils/difficulty.py)::`NEWVALUE_DIFFICULTIES`，不进入 `is_newvalue_difficulty`、新值 seed 公式、候选筛选与失败递补。这样 VideoRepick 保留原 hard 的任务机制，MoveCube 保留原生场景，其他任务也不会因把“档位 0”视为新值而误走新场景逻辑。原生 fail recover、随机调用顺序、演示、语言、成功条件均沿用现有 hard 路径，不能拿 xhard1 配置减去干扰物冒充 hard。

[evaluation_hard.py](scripts/evaluation_hard.py) 已用 `TIER_MAX_STEPS[tier]` 取步数；拟在表中加 `xhard0: 1300`，与 [evaluation.py](scripts/evaluation.py) 的默认评估设置相同。builder 自身默认仍为 10000，调用者显式覆盖时两侧必须使用相同值；wrapper 已有 `+2` 保留，不重复叠加。xhard1～4 仍为 1500／1700／2000／2600。

**注册表陷阱**：`robomme_hard/__init__.py` 导入即接管 16 个环境 ID。因此在同一进程调用官方父 builder，也不等于使用官方环境。方案候选侧沿用 hard 包的原生分支，官方对照必须在独立进程只加载官方环境；两侧记录实际环境类、wrapper 来源和依赖指纹。现有历史原生对拍提供参考，但不证明这次新增的全部身份已验过。

### 3.3 改动前后链路

```text
改动前：官方 test 元数据 → (seed, difficulty) → 官方环境进程 → 官方 wrapper → 观测/动作
        test-hard 四份 specs → 新值条目 → hard 包 gym.make + 回注 → hard 包 wrapper

改动后：官方 test 中 hard 子集 → xhard0 身份 → difficulty=hard，无回注 → hard 包原生分支 → wrapper
        test-hard 四份 specs → 原条目、原编号、原回注链路（不变）
```

身份层只增加发布标签和来源映射，不改 seed。传入环境的数值与官方对应局相同；返回观测的键集合、形状、dtype、逐数组字节长度都以官方同局实测为准，不在方案中猜定分辨率或演示长度。关节动作、状态和图像不新增转换、缩放或插值；本链路无可训练参数。本轮静态盘点确认不必新增场景抽签，实际运行耗时与逐步零差仍待验证。

## 4. 当前容差多大、为什么

权威配置是 [hard-parity-tolerances.json](scripts/configs/hard-parity-tolerances.json)，消费者为 [hard_parity.py](scripts/parity/hard_parity.py)::`pair_metrics`、`calibrate`、`cmd_compare`。

| 指标 | 当前允许上限（绝对差） | 实际比较范围 |
|---|---:|---|
| `action_max_rad` | 0.041265913943240015，角度分量约 2.364° | 共同时间步内 `action/joint_action` 所有分量最大差；字段名标 rad，但并不按夹爪分量拆单位 |
| `state_max` | 0.04113650321960449 | 共同时间步内 `obs/joint_state`、`obs/gripper_state` 最大差；混合字段，不能统一称为米或角度 |
| `image_mad` | 1.0 | 0～255 RGB 值的绝对差，先逐画面平均、再两相机与共同时间步平均；不是每像素最大差≤1 |
| `frames_max` | 5 | 两侧时间步数量绝对差；较长侧额外尾段不进入共同时间步数值比较 |

标定源为历史 O:P 原生对拍：**16 任务 × 3 档（easy／medium／hard）× 3 局 = 144 对**，2026-09-28 写入配置。O 是官方，P 是拆包前版本；143 对字节相同，一对 PickHighlight/hard/seed 12300 出现差异。详见 [阶段 4 报告](docs/validation/newtask-v6/hard-split/stage4.md) 的「容差标定」。

```text
阈值 = max(观测最大差 × 1.5, 人工设置的下界)
帧数项先向上取整，再与下界取大。

动作：0.027510609295493343 × 1.5 = 0.041265913943240015
状态：0.027424335479736328 × 1.5 = 0.04113650321960449
图像：max(0.14435587675847064 × 1.5, 1.0) = 1.0
帧数：max(ceil(0 × 1.5), 5) = 5
```

四项 p95 均为 0。1.5 倍用于给已观测漂移留余量；下界依次是 0.005／0.005／1.0／5，是工程选择，不是统计置信区间或浮点机器精度。历史报告把单对分叉归因于 RRT 墙钟噪声；本轮只核对了记录与实现，未做独立因果实验，不能承诺所有未来差异都是噪声。

代码还设合理性检查值 0.05／0.05／10／200，但实际检查对象是**原始最大差**，不是对最终阈值做截断；不能把它描述成最终阈值的硬上限。本轮不改阈值、不重新标定。

另有独立的回注校验容差：[hard_specs.py](src/robomme_hard/env_record_wrapper/hard_specs.py)::`RECORDED_FLOAT_TOL = 1e-5`。它只允许仅记录、未回注的浮点观测点在此绝对差内漂移，真正回注取值仍要求零差。它不是轨迹对拍容差，xhard0 不走规格回注，因此不拿它放宽 xhard0。

**这些非零容差只能支持“容差内一致”。** 当前比较器不逐个覆盖全部观测字段、属性和事件，RGB 平均还会稀释局部差异；即使四个阈值设成 0，也不自动变成完整数据零差检查器。

## 5. xhard0 的验收与实施步骤

“完全一致”分层报告：身份／配置完全相同，数据结构完全相同，逐字段数值零差，行为事件完全相同。HDF5 容器文件 SHA-256 相同另列为字节级一致；容器组织差异不能被描述成数值差异，也不能用容差通过代替字节相等。

| 查什么 | 怎么查 | 通过说明什么 | 拟定判定行 |
|---|---|---|---|
| 身份全集 | 精确比对官方 hard 子集的任务、原 episode、seed、难度和源摘要，拒绝空集／缺项／重复 | 引入恰好原来的身份，无新增抽样 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192 missing=0 extra=0` |
| 原生分支 | 捕获环境实参与实际类来源，检查 hard、不含回注字段，逐任务核对 wrapper／步数／恢复机制 | 没有误入新值路径 | `XHARD0_NATIVE=PASS runtime_difficulty=hard injected=0` |
| 旧档兼容 | 比较原四份 specs 的文件摘要、交付摘要与全局 episode 映射 | 原四档的身份、数量与编号未漂移 | `XHARD_EXISTING=PASS shape=13x3x20+16x1x20 identities=1100 remapped=0` |
| 逐步零差 | 独立进程同环境同身份，比较 reset、演示、相同动作驱动下每步所有观测、reward、终止／截断、任务目标与事件；键／shape／dtype／长度精确匹配，数值逐元素相等 | 被测范围的实际行为和输出零差 | `XHARD0_EXACT=PASS compared=N missing=0 fields_diff=0 numeric_diff=0 event_diff=0` |
| 轨迹与成功 | 生成侧独立规划另作比较，记录帧数、所有 HDF5 数据集／属性、终态成功与文件摘要 | 明确规划复现、数据字节和任务成功分别是否成立 | `XHARD0_TRAJECTORY=PASS compared=N frames_diff=0 data_diff=0`；`XHARD0_SUCCESS=INFO success=K total=N`；`XHARD0_H5_BYTES=PASS sha_equal=N` 仅全相等时输出 |
| 官方冻结 | 核对 `src/robomme/` 与三个官方入口无变更 | 基线没有被候选改写 | `XHARD0_UPSTREAM=PASS changed=0` |

上述是未来判据，**不是本轮实测结果**。相同失败可以证明该项行为一致，但不代表任务成功；失败不得用换 seed、递补成功局或重试到成功掩盖。逐元素比较需先拒绝意外非有限值，避免 NaN 比较漏判。发布标签与运行 provenance 放独立身份报告，不能为了消除差异而重写两侧原始 HDF5 内容。

| 阶段 | 内容 | 结束条件 |
|---|---|---|
| 0 | 静态确认来源、数量、源摘要与旧档映射 | `XHARD0_IDENTITY`、`XHARD_EXISTING` |
| 1 | 实现原生条目、builder 分派、步数项与只读身份接口 | `XHARD0_NATIVE`、`XHARD0_UPSTREAM` 与定向短测通过 |
| 2 | 实现完整零差检查与反例夹具 | 缺字段、缺帧、单像素变更、事件变更、NaN 均可靠失败 |
| 3 | 经规模授权后，先 1 任务 × 1 档 × 1 局双侧冒烟，再执行批准的范围 | 对应范围的 `XHARD0_EXACT`／`XHARD0_TRAJECTORY`，成功率独立报告 |
| 4 | 回写证据与使用文档，提交推送 | 范围、限制、失败与未验证部分均可核对 |

本轮完成的仅是方案与静态盘点。源 hard 数量经 `jq` 核实，未运行任何环境，因此尚无 xhard0 运行一致性结论。

# 第二部分（技术细节，供 agent 追踪）

## 0. 红线与依赖

R1. 仅实施获批的文件与范围；P2 保护的官方源码不改。修改既有 builder 覆写方法涉及官方行为覆盖，实施前将方法清单并入一次性授权，不能把旧批准自动延伸到新改动。

R2. 不向新值四档规格 schema、seed 偏移和 `NEWVALUE_DIFFICULTIES` 塞入 xhard0；不伪造成功 rollout，不新增候选池。

R3. 所有原身份固定，失败不换 seed、不递补；官方三入口逐字节保持。

R4. 零差失败就保存首个分叉证据，不放宽阈值；旧容差 JSON 不改。同种 GPU／驱动／依赖是比较前提，不保证天然逐位一致。

R5. 主代理唯一整合与提交者。可并行委派身份／builder、比较器、只读审查，各自文件集合互斥；单文件只有一个写入者。

## 1. 逐文件改动清单（尚未实施）

| 文件／锚点 | 拟改什么及原因 | 无 xhard0 时／现有档 | xhard0 时 |
|---|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_builder.py`：`_test_hard_entries`、`resolve_episode`、`resolve_identity`、`make_env_for_episode`、`_hard_env_kwargs` | 原生身份读取、严格源校验、显式分派；身份接口增加来源映射 | 原四档解析与回注参数不变 | 读取官方 hard 子集，传 hard，不调用新值实参生成 |
| `src/robomme_hard/env_record_wrapper/hard_specs.py`：`TIER_MAX_STEPS`，拟新增发布档常量 | 发布集合与新值集合区分，新增 1300 步项 | `TIERS`／`EXPECTED_CELLS` 仍只管四档 | 独立 12 条／任务断言 |
| `src/robomme_hard/env_record_wrapper/__init__.py` | 必要时导出发布档常量 | 既有导出兼容 | 能读取 xhard0 信息 |
| `scripts/parity/hard_regression.py` | 扩展原生子集清单与成对验证调度；独立官方进程 | 原命令不变 | 支持 source_episode 与发布标签分离 |
| `scripts/parity/hard_parity.py` | 新增显式零差比较模式，完整覆盖数据与事件；新输出目录不覆盖历史报告 | 默认容差模式与标定不变 | 只输出真实覆盖范围的零差结论 |
| `tests/lightweight/test_xhard0_native.py`（拟新增）、`tests/lightweight/test_hard_parity.py` | 无仿真身份／路由测试、完整比较器反例 | 保留既有用例 | 验证 16×1×12 身份与零差失败闸门 |
| `src/robomme_hard/README.md`、`scripts/README.md`、`src/robomme_hard/__init__.py` 的包说明 | 更新档位、数量、来源与编号说明 | 不重写历史验收事实 | 明示 xhard0 是原生 hard 别名 |

不预先修改 16 个环境类或 wrapper。若原生分支实测不等，按首个差异提出精确文件／符号修法，不把当前计划当作大范围修复授权。`scripts/evaluation_hard.py` 的现有查表循环原则上无需逻辑改动。

## 2. 闸门与验证范围

顺序为：静态身份与旧档冻结 → 无仿真路由测试 → 比较器反例 → 环境指纹与实际模块来源 → 最小双侧冒烟 → 经批准的完整比较 → 独立成功统计。每一阶段缺失时不宣称后续层级通过。

完整身份范围是 **16 任务 × 1 档 × 12 局 = 192 对**。两侧完整轨迹比较的名义运行量是 **2 侧 × 16 任务 × 1 档 × 12 局 = 384 次轨迹尝试**，冒烟选正式集合的首对并保留复用，不额外重跑。候选原生链路没有独立抽候选 reset；每次构建、wrapper reset、演示内部调用等真实 reset 次数须在实施前沿调用链计数，不能直接把 384 当作 reset 总上限。若另做固定动作回放，它也是独立的执行量，必须并入完整预算，不能藏在“验证”名下。

本轮不申请执行该批次、不提交占位作业。实施时先复核现有产物能否覆盖这些确切 task／source_episode／seed／环境指纹，给用户一次完整清单：复用数、缺失数、双侧运行与动作回放的 reset／轨迹尝试上限、worker 数、重试上限、预计耗时、run_name 和停止条件。无实测耗时与内部 reset 计数前不报虚假的精确预算。默认不安排任务失败重试；基础设施重试也须在该清单内预先限额。不得额外加 xhard1～4 的大规模回归生成，旧档先用静态摘要与映射保护。

## 3. 操作步骤与命令

以下静态命令可复核本方案的关键前提，不创建环境：

```bash
git rev-parse HEAD
git status --short
for f in src/robomme/env_metadata/test/*json; do
  jq -c '{task:.env_id, hard:[.records[]|select(.difficulty=="hard")|{episode,seed,difficulty}], hard_count:([.records[]|select(.difficulty=="hard")]|length)}' "$f"
done
cat scripts/configs/hard-parity-tolerances.json
git diff --check
grep -c '^# 第一部分\|^# 第二部分' 0928-xhard0-native-hard-plan.md
```

实施后的拟定短测命令如下；新增测试文件当前尚不存在，不得声称本轮已运行：

```bash
command -v uv
ls uv.lock pyproject.toml
UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/cache/uv timeout 280s uv run --no-sync python -m pytest tests/lightweight/test_xhard0_native.py tests/lightweight/test_hard_parity.py -q
```

新增比较模式的命令行参数与输出目录待实施时定稿，不提供貌似现成可运行的伪命令。长任务按仓库规则进入 detached tmux，先验证成功与失败通知链路，日志记录退出码；全部产物放 `artifacts/`，正式证据放 `docs/validation/`。若采用集群，再按届时 `greatlakes.md` 与完整授权预算准备资源，不能沿用历史 JobID 猜测仍可用。

## 4. 风险与盲区

| 风险 | 处置／诚实边界 |
|---|---|
| 只换标签却仍传新值参数 | 路由测试直接断言调用参数与分支，xhard0 禁用回注 |
| 同 seed 被误认为足够保证同场景 | 同时锁定原 episode、代码、随机调用顺序、恢复、wrapper 和环境指纹 |
| 官方与 hard 包注册表互相污染 | 两侧独立进程，记录实际类与模块路径，不能用 import 名称作唯一证据 |
| 自动重排旧 episode 导致评估结果串号 | 建议追加 xhard0；旧映射逐条冻结，新身份带 source_episode |
| 原生演示规划有非确定性 | 先定位 reset／演示／动作／物理／渲染的首次差异；不能用“噪声”直接放行 |
| 零差无法在当前环境实现 | 结论标失败或未验证，向用户报告；不自动改成 0.041 rad 容差验收 |
| 元数据有身份但没有现成 HDF5 | 先只读查产物及来源；不承诺复用全部，不为凑数量生成成功替代局 |
| 图像平均值漏掉局部错误、少帧漏尾段 | 零差模式完整逐字段／逐像素比较，要求帧数与键全集一致 |

已知的历史 **16 任务 × 3 原生档 × 3 局 = 144 对** O:H 字节相等，只说明历史被测身份；不是本次 **16 任务 × 1 档 × 12 局 = 192 对** 的全量证据。任意策略、跨硬件、所有未来运行的完全一致，都不能由有限测试普遍保证。

## 5. 留档与提交纪律

本轮只提交本方案：检查两部分标题、链接目标、数量算式、用户最后决定、容差公式及 `git diff --check`；逐个路径暂存，中文提交后立即推送当前既有 upstream。不会把方案写入规则文件或追加历史账本。

后续运行证据须记录双方代码／依赖／GPU／驱动、源元数据摘要、完整身份与真实尝试计数、首个差异、独立成功字段、退出码和输出路径；原始失败记录保留。最终报告逐项给出本方案 §5 的具名判定及覆盖范围，未跑部分明确为未验证。方案完成不等于实现完成，更不等于 xhard0 全量一致性已经成立。
