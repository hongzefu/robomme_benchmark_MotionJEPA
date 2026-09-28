# 0928 方案：test-hard v7 —— 接入 xhard0（原生 hard）+ xhard1～4 改为共用 20 个母布局（只规划不实施）

> **权威性与锚点**：本方案是 v7 的唯一现行计划，取代同日 [`0928-xhard0-native-hard-plan.md`](0928-xhard0-native-hard-plan.md) 里「xhard0 追加在旧四档之后」的编号建议，其余 xhard0 结论（身份来源、原生分支、零差验收）原样沿用、本文只引用不重抄。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-v5`，代码锚点 `8dfd09cb`（12.222）。官方源码锚点 `1fadc0ec`（`src/robomme/` 逐字节相同），官方编排锚点 `d53f21a7`（`scripts/parity/official/` vendor）。commit 编号沿用 `12.<小版本> 中文描述`。**本轮只写方案，不改代码、不起环境、不提交占位 job；实施的每一阶段须单独获批，reset／轨迹预算按 `AGENTS.md` P3 一次性授权。**
>
> **用户原话（2026-09-28，按时间顺序逐字保留）**：
> 1. 「给出方案 xhard现在有1-4 再加入xhard0 需要和原本的hard保持完全一致 每个task episode数量和以前一致 根目录写方案」
> 2. 「xhard1234改为同样reset布局 总共20个布局 只有现在的梯度区别不一样」（附四档梯度表，与 `scripts/README.md` 第 3 节逐字相同）
> 3. 「并且告诉我现在的多卡容差范围是多大 为什么」
> 4. 「保证接口和现在一致 /data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/README.md」
> 5. 「修改完定为v7的task」
> 6. 「拍链路（parity/）只需要原三档 144 局清单（16 任务 × 3 档 × 3 局）和新的v7 两次生成一致」
>
> 上一轮（12.222）关于 xhard0 数量的最后决定：「和test的hard数量一致」→ 每任务 12 局。本文对原话 1 里「每个task episode数量和以前一致」的解读：**xhard0 每任务 12 局（沿用 12.222 决定），xhard1～4 每格仍 20 局（与现在一致）**。若用户本意是 xhard0 也取 20 局，只需改第一部分 §2 的数量表与 xhard0 身份来源（那样就不能再是官方 test 的 hard 子集，见 §2 末的说明），其余机制不变。

# 第一部分（给人看）

## 1. 一句话方案与已定口径

**一句话**：v7 的 `test-hard` = 5 档 —— xhard0 逐任务原样引用官方 test 元数据里的 hard 子集（原生 hard 语义，不回注，每任务 12 局）；xhard1～4 每任务共用同一批 20 个「母布局」，母布局在 xhard4 配置下抽签一次，xhard1～3 把母布局的布局类取值点原样（按数量取前缀）注入、梯度类取值点在各自档位配置下现场重抽；对拍只保留两条：原三档 144 局 O:H，以及 v7 全部正式局在同型号卡上生成两次的一致性。

已定口径（编号供第二部分引用）：

| 编号 | 口径 | 依据 |
|---|---|---|
| D-1 | xhard0 = 官方 test 的 `difficulty=="hard"` 记录，seed 逐条照抄元数据（不套公式），运行难度传 `"hard"`，不进新值族、不回注 | 12.222 §2、§3；本文 §2 |
| D-2 | xhard0 每任务 12 局（官方 test 每任务 50 = easy 26 / medium 12 / hard 12，原 episode 号 3,7,…,47） | 12.222 用户决定「和test的hard数量一致」；本文引言 |
| D-3 | xhard1～4 每任务 20 个母布局，四档同一布局、同一 seed；13 个有梯度任务四档共用，StopCube／InsertPeg／MoveCube 只有 xhard4、母布局即自身 | 原话 2；§3 |
| D-4 | 「布局」= 各环境取值点里与梯度无关的位置／颜色／朝向／槽位／初始化类点（白名单见第二部分 §1.3）；「梯度」= 次数、数量、序列、演示选择类点，按档现场重抽 | 原话 2「只有现在的梯度区别不一样」；§3.2 |
| D-5 | 梯度维度与数值逐字沿用现行四档表（`scripts/README.md` 第 3 节），本轮不改任何梯度取值 | 原话 2 附表 |
| D-6 | 接口与 `scripts/README.md` 第 1 节四处差别完全一致：`dataset="test-hard"`、`resolve_episode → (seed, tier)`、`TIER_MAX_STEPS[tier]`、`make_env_for_episode(ep, max_steps=…)`；只多一个档名 `xhard0` 与一个步数项 `1300` | 原话 4；§4 |
| D-7 | 发布名 v7：包内规格换成 `hard-specs/3`（含 v7 seed 规则与母布局字段），产物落 `artifacts/newtask-v7/`，留档落 `docs/validation/newtask-v7/`；V6 规格文件由 git 历史保留 | 原话 5；§5 |
| D-8 | 对拍只做两条：`PARITY_O_H`（原三档 144 局清单，官方 vs `robomme_hard` 原生路径）与 `PARITY_V7_TWICE`（v7 全部正式局两次生成，同型号 A40、不同作业）；容差沿用现行 `hard-parity-tolerances.json`，不重标 | 原话 6；§6 |
| D-9 | 集群侧生成一律 A40@greatlakes 占位 job；两次生成必须同型号同驱动，否则只能做容差内一致、不能报 sha 相等数 | §7「多卡容差」 |
| D-10 | 母布局候选数、递补规则、xhard0 是否另生成 h5 等取整类细节由 agent 自定并写进本文，不再逐项询问（用户 2026-09-24「以后四舍五入这种问题都不要来找我」） | 记忆规则 |

## 2. 数量：v7 每任务多少局、编号怎么排

| 档 | 来源 | 任务数 × 局数 | 合计 |
|---|---|---|---|
| xhard0 | 官方 test hard 子集，原生 hard | 16 任务 × 1 档 × 12 局 | 192 |
| xhard1～3 | 母布局派生 | 13 任务 × 3 档 × 20 局 | 780 |
| xhard4 | 母布局本体 | 16 任务 × 1 档 × 20 局 | 320 |
| 合计 | — | 16×1×12 + 13×3×20 + 16×1×20 | **1292** |

builder 的 episode 号按「xhard0 → xhard1 → xhard2 → xhard3 → xhard4，档内按候选号升序」排：13 个有梯度任务 0～11 是 xhard0、12～31 xhard1、32～51 xhard2、52～71 xhard3、72～91 xhard4，共 92 局；三个只有 xhard4 的任务 0～11 xhard0、12～31 xhard4，共 32 局。**这与 12.222 的「xhard0 追加在末尾以保住旧编号」不同**：v7 的 xhard1～4 全部重抽，旧编号本来就保不住，所以直接按档序排、以后不再挪。

为什么 xhard0 不能同时是「与 hard 完全一致」又是「20 个母布局之一」：母布局是在 xhard4 配置下抽出来的场景（例如 VideoUnmask 15 个干扰容器、PatternLock 21～25 节点），而原生 hard 的场景由官方代码在 hard 配置下抽（0 个干扰容器、4～8 节点）；MoveCube 的 hard 是原生场景、xhard4 是圆环 U，VideoRepick 的 hard 甚至是另一种任务机制。要让 xhard0「和原本的 hard 完全一致」，它就只能走官方 hard 路径、用官方 test 的 seed，与母布局无关。**这是 D-1／D-3 并列而不合并的原因。**

xhard0 身份的静态核实（12.222 已用 `jq` 做过，本轮重跑一次原样）：16 个任务全部 hard 12 局、原 episode 号 `3,7,11,15,19,23,27,31,35,39,43,47`；seed 逐条来自元数据（例如 PickXtimes 原 episode 15 的 seed 是 `511501` 而非公式值 `511500`，BinFill 原 episode 3 的 seed 是 `540302`）。

## 3. 机制：母布局怎么来、低档怎么共用

### 3.1 现状为什么做不到共用

- 现在四档各有一套 seed 偏移（[`hard_specs.py`](src/robomme_hard/env_record_wrapper/hard_specs.py)::`V6_SEED_OFFSETS`：xhard4 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6），布局天然互不相同。
- 回注通道 [`episode_spec.py`](src/robomme_hard/robomme_env/utils/episode_spec.py)::`SpecRecorder.value` 在回注模式下**对每个取值点都先按本局 seed 真抽一次，再拿抽到的值与冻结值比对，最后返回冻结值**；`hard_specs.py::spec_binding` 把所有 value 点的不等都计入 `injected_mismatch`，而 [`hard_regression.py`](scripts/parity/hard_regression.py) 的 `reset-replay`／`eval-smoke` 要求它为 0。因此「把 xhard4 的规格改一改喂给 xhard1」会在每个布局点都记一条不等，直接触发闸门。
- 仓库里没有「给定母规格派生各档规格」的入口：[`generate_h5.py`](scripts/injection-dev/generate_h5.py) 的 `--mode replay` 只按 `(task, tier, seed)` 去已有规格行里查；`freeze_specs.py` 只会 reset 抽签。
- 纯 JSON 截断（xhard4 规格按低档数量取前缀）对 PickXtimes／SwingXtimes／PickHighlight／PatternLock／RouteStick 可行，但对 VideoRepick（`swap_initiators_remaining` 必须是 range(k−1) 的完整排列、`swap_pairs` 引用 ≥k 的块、可行图 G 随块集合变化）、VideoPlaceButton xhard1/2（台数 5→4、额外放台候选按占用表重算）、VideoUnmaskSwap／ButtonUnmaskSwap（`cube_bins`／`label_perm` 与 count 耦合、外环规划要重跑可行性）不可行，BinFill 的 `target_numbers` 是每色聚合值也没有「前缀」可取。**所以不能靠改 JSON，必须让梯度类取值点在环境里现场重抽。**

### 3.2 分层回注：布局注入、梯度重抽、记录点重导出

定义：每个环境的取值点分两类（白名单在第二部分 §1.3）。**布局类** `L`：位置、颜色、朝向、槽位、初始化、type_choice 之类，与档位无关或只随数量变长；**梯度类** `G`：`num_repeats`、`n_swaps`、`n_picks`、`target_numbers`、`cube_count`、`cube_bins`、`label_perm`、`swap_plan_seed`、`swap_pairs.k`、`highlight_*`、`demo_ids`、`visit_*`、`L` 等。记录点（`record()`）全部视为派生量，由派生运行重新导出。

```text
阶段 A  母布局抽签（每任务 24 个候选，xhard4 配置，v7 seed 规则，只 reset）
        ├─ 13 个有梯度任务：母布局规格 = xhard4 规格本体（spec_kind native-newvalue/2，mismatch=0）
        └─ StopCube / InsertPeg / MoveCube：同上，只此一档
阶段 B  派生（13 任务 × 3 档 × 每候选 1 次 reset，「layered」模式）
        SpecRecorder(mode="derive", parent=母规格, layout_paths=白名单)
        ├─ 路径 ∈ L：照常抽一次（随机流不漂移），返回母值；列表值按 len(抽到值) 取前缀；
        │            逐项路径（layout.distractors.<color>_0、layout.cubes.i、layout.targets.i、
        │            objects.distractors.bins.i、actions.directions.i）低档只访问前 k 个，多出的自动 unused
        ├─ 路径 ∈ G：照常抽、照常用（本档 config 决定范围）
        ├─ record()：照常记本档实际值
        └─ 导出：spec_kind="native-layered/3"，spec 树 = 本局实际使用值；
                  另存 layout_parent{sha256, tier="xhard4", candidate}、layout_drawn{path: 本档抽到的值}
阶段 C  生成 h5（55 格 × 20 局，回注模式）
        └─ 回注 native-layered/3：L 点比对对象改为 layout_drawn（核随机流），使用值 = 冻结值；
           G 点与原来一样比冻结值；spec_binding 新增 layout_injected 计数，injected_mismatch 仍须 0
```

⚠ 陷阱与反例：
- **不能用「四档同 seed、让 RNG 自己碰」代替注入**。同 seed 下 PickXtimes／SwingXtimes／VideoUnmask／PickHighlight／RouteStick 节点的布局前缀按代码顺序推断会逐位相同，但 BinFill（`target_numbers` 逐单位抽样次数随 put_in 变，后面 spawn 分配、槽位整体平移）、VideoPlaceOrder（`count_order` 只在 xhard1/3 抽）、PatternLock（搜索循环停在不同尝试次数）都不会相同；而且「天然相同」是推断不是保证。v7 用注入保证，同 seed 只是顺带（D-3 四档同 seed 便于身份对齐）。
- **前缀合法性靠什么保证**：依序放置的对象只对已放对象做中心距／OBB 检查，前缀天然合法；四档的区域、最小中心距、内环 bin 数（VU/BU 8 个、VUS/BUS 4 个）、BinFill 12 槽相同，母布局在 xhard4 下合法 ⇒ 前缀在低档下合法。回注时环境里的二次复核（`object_generation.py::_assert_center_rules_hold`、`unmask_distractor_sampler.py::verify_distractor_layout`、`swap_uniform.verify_swap_sequence`、`BinFill._spawn_cubes_xhard` 槽位复核、`PatternLock._check_xhard_path`）照常执行，不合法会响亮失败而不是静默通过。
- **派生仍可能失败**：梯度点现场重抽可能撞上 `SceneGenerationError`（外环交换某窗不可行、额外放台无候选），这时该候选在**四档同步作废**，按候选号顺延，不允许某档单独换布局（否则「同一布局」不成立）。
- **PatternLock 没有布局**：它唯一的取值点是 `actions.path_nodes`，v7 把它当作可取前缀的布局点（xhard4 的 21～25 节点路径，低档取前 L 个节点，8 邻接不重访的前缀仍合法）；RouteStick 的 `actions.nodes` 同理。这是 D-10 范围内的自定细节。
- **只把 `objects.num_repeats` 之类标量留给现场重抽**，不把 xhard4 的 14 次硬塞给 xhard1（不在 [6,7] 区间会被 `_assert_*` 拒绝）。

收益（静态盘点，未实测）：16 个环境全部落入「可行」——PickXtimes／SwingXtimes／PickHighlight／VideoUnmask／ButtonUnmask／RouteStick／PatternLock 只需白名单；BinFill／VideoPlaceOrder／VideoPlaceButton／VideoRepick／VideoUnmaskSwap／ButtonUnmaskSwap 由「梯度点现场重抽」消掉全部耦合问题；三个 xhard4 独有任务不涉及派生。

### 3.3 seed 与身份

v7 seed 规则（`hard_specs.py` 新增 profile `"v7"`）：`seed = 14_000_000 + env_code × 100_000 + candidate × 100 + attempt`，**四档同一 offset**，同一候选号在四档里 seed 相同；与 V5 段（4e6）、V6 四段（6e6～12e6）互不重叠。`validate_specs` 对 v7 文件要求：四档 header 的 `seed_rule` 相同；每行 `seed` 等于公式；派生行的 `layout_parent.sha256` 等于 xhard4 同候选行的 `spec_sha256`。

身份键仍是 `(task, tier, seed)`（[`hard_parity.py`](scripts/parity/hard_parity.py)::`ident`），同 seed 跨档靠 tier 区分。`resolve_identity` 对派生行多返回 `layout_parent`，对 xhard0 返回 `source_dataset="test"`、`source_episode`、`spec_sha256=None`。

### 3.4 改动前后链路

```text
改动前：
  官方 test 元数据 → (seed, hard) ────────────────────────────→ 官方 robomme 环境（无 xhard0）
  test-hard/xhard{1..4}/specs.jsonl（V6，四段 seed）→ 条目 → gym.make(sampling_config, native_episode_spec) → robomme_hard 环境

改动后：
  官方 test 元数据 hard 子集 → xhard0 条目（seed 原值，difficulty="hard"，无 sampling_config、无 spec）→ robomme_hard 原生 hard 分支
  test-hard/xhard4/specs.jsonl（v7 母布局）→ 条目 → gym.make(sampling_config[xhard4], native_episode_spec)      → 全量回注（同现在）
  test-hard/xhard{1..3}/specs.jsonl（v7 派生）→ 条目 → gym.make(sampling_config[tier], native_episode_spec=layered) → L 点注入 + G 点冻结值
```

每一跳的观测键集合、形状、dtype 与现在完全相同（本方案不改任何观测、动作、控制模式；`RUNTIME` 四项不变）；xhard0 局的观测与官方同局逐字段相同是 12.222 §5 的零差验收对象，不由本文重复宣称。本链路无可训练参数。

## 4. 接口：与 `scripts/README.md` 第 1 节逐条对照

| README 第 1 节的四处差别 | v7 |
|---|---|
| 换包 `robomme_hard.env_record_wrapper.BenchmarkEnvBuilder` | 不变 |
| `dataset="test-hard"` | 不变；每任务局数由 80 → 92（xhard4 独有三任务 20 → 32），16 任务合计 1100 → 1292 |
| `resolve_episode(ep) → (seed, tier)` | 不变；`tier` 取值多一个 `"xhard0"` |
| `make_env_for_episode(ep, max_steps=TIER_MAX_STEPS[tier])` | 不变；`TIER_MAX_STEPS` 增加 `"xhard0": 1300`（与官方 `evaluation.py` 默认相同，12.222 §3.2） |

`spec_binding(env)` 对 xhard0 局返回 `{"available": False}`（没有 recorder），对派生局多返回 `layout_injected`；两个策略仓库（SimpleMemVLA、MME-VLA）现有接法只是把返回字典写进 info，不用改。`scripts/evaluation_hard.py` 的查表循环不改逻辑。

README 要改的只有数字与说明：第 1 节「换数据集」的局数、「多拿一个档位」加 xhard0、「步数上限按档给」加 1300；第 3 节表加 xhard0 列（与 hard 列逐字相同）；第 4 节链路改为「母布局抽签 → 派生 → 生成」三阶段与 v7 seed 规则；第 5 节对拍改为两条。

## 5. 版本、文件与发布

- 包内 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl` 整体替换为 v7（schema `hard-specs/3`）；xhard0 不打包规格，builder 直接读官方 test 元数据（12.222 §3.1，读取时校验源文件摘要与 12 条／任务）。
- V6 的 `s4-setup-manifest.json`、`s4-to-delivery.json` 与 `scripts/configs/newtask-v6/v6-02/` 快照：v7 后失效，从工作树删除、git 历史保留（P1 允许删子目录内容；`configs/` 保留 `hard-parity-tolerances.json`）。`hard_regression.py` 的 `s4-subset`／`reset-replay` 子命令换成 v7 版（第二部分 §1.5）。
- `migrate_smvla_specs.py` 的 `check` 在 v7 后必然 FAIL（钉死 1100 与 `13x3x20+16x20`），删除该文件（历史迁移已完成、git 可取回）。
- h5 产物：v7 两次生成各 1100 局，落 `artifacts/newtask-v7/gen1/`、`gen2/`，上传 bucket 前缀 `H-v7-gen1-a40`、`H-v7-gen2-a40`；xhard0 不生成 h5（它是评估身份，不是生成产物；12.222 §5 的轨迹比较是可选项，本文不列入预算）。

## 6. 验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| xhard0 身份 | 官方 test 元数据 hard 子集 vs builder 条目：任务、原 episode、seed、源文件 sha256 逐条相等 | 引入的恰好是原来的 192 个身份 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192 missing=0 extra=0` |
| xhard0 原生分支 | 捕获 `gym.make` 实参：`difficulty=="hard"`、无 `sampling_config`、无 `native_episode_spec`；`spec_binding` 返回 `available=False` | 没有误入新值路径 | `XHARD0_NATIVE=PASS runtime_difficulty=hard injected=0 tasks=16` |
| 母布局共用 | 静态：xhard1～3 每行 `layout_parent.sha256 == xhard4 同候选 spec_sha256`，且该行 spec 里每个白名单路径的值等于母值（列表取前缀、逐项路径取子集）；四档 `seed` 相同 | 四档确实是同一批 20 个布局 | `V7_LAYOUT_SHARED=PASS tasks=13 layouts=20 tiers=4 rows=780 parent_mismatch=0 seed_mismatch=0` |
| 梯度单调 | 对每任务每布局，四档在用户指定维度的实际值按档非降且落在各档区间（沿用 `site/v6_tier_monotone.py` 口径） | 只有梯度不同，且梯度确实分档 | `V7_TIER_MONOTONE=PASS cells=55 violations=0` |
| 回注零差 | 每格取 1 局经评估链 `make_env_for_episode` + `reset` 后 `spec_binding`：`injected_mismatch==0`，派生局 `layout_injected==|L 白名单命中数|`，`unused` 只含母布局多出的逐项路径 | 评估时建出的场景与生成时同一局 | `V7_RESET_REPLAY=PASS shape=13x3+16 injected_mismatch=0 layout_drift=0` |
| 原三档一致 | `hard_parity generate --tier native` O 侧（官方 `1fadc0ec` worktree + 官方 `_worker`）与 H 侧（`robomme_hard` 镜像 worker），A40，`compare --pair O:H --tier native` | `robomme_hard` 的原生路径（xhard0 所走的路径）与官方行为一致 | `PARITY_O_H=PASS tier=native shape=16x3x3 compared=144 tol_over=0`（`sha_equal` 作参考） |
| v7 两次生成一致 | gen1 用 `generate_h5 --mode continue` 出正式 1100 局；gen2 用 `--mode replay --identities <gen1 交付清单>` 在另一占位 job（同型号 A40、同驱动）重放；`compare --pair H:H2 --tier v7` | 规格 → h5 的映射确定，只剩 RRT 墙钟噪声 | `PARITY_V7_TWICE=PASS shape=13x3x20+16x1x20 compared=1100 tol_over=0`（`sha_equal` 作参考） |
| 官方冻结 | `upstream_guard.py check --require-upstream`；三入口与录像器零 diff | 基线没被改写 | `UPSTREAM_GUARD=PASS` |
| 入口冒烟 | `hard_regression.py eval-smoke --task BinFill --episode 0`（xhard0 局）与 `--episode 12`（xhard1 局） | 评估入口两类局都能起 | `HARD_EVAL_SMOKE=PASS episodes=2` |

为什么这些判据能成立：身份类判据是纯静态集合比对；`V7_LAYOUT_SHARED` 比的是规格文件里的值树，不依赖运行；回注零差靠 `SpecRecorder` 的「抽一次核随机流、用冻结值」机制（第 3.2 节）；两条对拍在同型号同驱动 A40 上做，这是 §7 说明的逐位边界，所以才允许把 `sha_equal` 当参考数、把容差当判定。

## 7. 现在的「多卡容差」是多少、为什么

**结论先说**：现行容差只有一套，标定自**同型号（A40）、同驱动、不同节点**的 O:P 144 对，**不是跨 GPU 型号的容差**；跨型号只做过 1 条身份的逐位探针，结论是「逐位一致只在同型号 + 同驱动内成立」，跨型号的容差判据至今没有标定。

权威配置 [`scripts/configs/hard-parity-tolerances.json`](scripts/configs/hard-parity-tolerances.json)，消费者 `hard_parity.py::pair_metrics`／`calibrate`／`cmd_compare`：

| 指标 | 阈值 | 比较的量 |
|---|---:|---|
| `action_max_rad` | 0.041265913943240015（≈2.36°） | 共同时间步内 `action/joint_action` 全分量最大绝对差 |
| `state_max` | 0.04113650321960449 | `obs/joint_state` 与 `obs/gripper_state` 最大绝对差（混合字段，不能统一称米或弧度） |
| `image_mad` | 1.0 | 0～255 RGB 逐像素绝对差先逐画面平均、再两相机与共同时间步平均（不是逐像素上限） |
| `frames_max` | 5 | 两侧时间步数之差 |

公式 `阈值 = max(观测最大差 × 1.5, 下界)`，帧数先向上取整；下界 0.005／0.005／1.0／5；「合理性上界」0.05／0.05／10／200 检查的是**原始最大差**、超了只让标定 FAIL，不截断阈值。标定数据：O（gl1517，job 62126060）与 P（gl1504，job 62126061），均 A40、驱动 595.71.05、16 worker；144 对里 143 对逐字节相同，唯一非零的一对是 `PickHighlight/hard/seed 12300` 从第 549 步起分叉（动作最大差 0.0275、图像平均差 0.144、帧数相同），O 与 H 在该身份上逐字节相同，报告归因为 P 侧那次运行的 RRT 墙钟噪声（`docs/validation/newtask-v6/hard-split/stage4.md`「容差标定」）。所以：阈值 = 0.0275×1.5、0.0274×1.5，图像与帧数取下界。

**为什么它不是「多卡」容差**：[`20260927-cross-hardware-probe.md`](docs/validation/newtask-v6/hard-split/20260927-cross-hardware-probe.md) 用同一条身份（BinFill/ep0/seed 4000/easy）在四张卡上跑官方 A 路：A40 两个节点 sha 相同；RTX 6000 Ada（本机）vs RTX A6000（aspen）只有 16 个 `joint_action` 值差 ≤ 2.24e-18；**Ada vs A40 从第 7 步起全面分叉**：`joint_state` 最大 0.029 rad、`eef_state` 0.0377、`front_depth` 最大 2.67e3、RGB 逐像素最大 211～235。这说明 0.029 rad 的跨型号状态差已接近 0.041 的阈值，且图像逐像素差远超 1（`image_mad` 是平均值，单局是否超 1.0 未算），跨型号数据没有进过任何标定。因此 D-9 要求 v7 两次生成都在 A40 上做；本机 Ada 与 aspen A6000 只用于冒烟与静态验收，不产正式对拍数据。

另有一个容易混淆的数：`hard_specs.py::RECORDED_FLOAT_TOL = 1e-5` 是回注校验里「只记录不回注」的浮点观测点允许的漂移，与轨迹对拍容差无关；派生局的 `layout_drawn` 核随机流也用它。

## 8. 实施步骤表

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 静态准备 | 取回 144 清单与 `official_train/`（`git show 6e70c0bf:…`）到 `scripts/configs/newtask-v3/`；重跑 xhard0 身份 `jq` 核实；写 v7 白名单文件 | `XHARD0_IDENTITY`；`git diff --check` |
| 1 规格模块与 builder | `hard_specs.py`（v7 seed、`hard-specs/3`、`BUILDER_TIERS`、`TIER_MAX_STEPS["xhard0"]`）、`episode_spec.py`（derive 模式、layered 回注）、`hard_builder.py`（xhard0 条目、分派）、定向单测 | `XHARD0_NATIVE`；`UPSTREAM_GUARD`；定向短测通过 |
| 2 抽签／派生／生成工具 | `freeze_specs.py --seed-profile v7`、新增 `derive_specs.py`（阶段 B）、`generate_h5.py` 支持 layered、`_rollout.py` 四档同步递补 | 无仿真夹具：状态机、回滚、同步递补的单测 |
| 3 单格冒烟（本机） | 1 任务 × 1 母布局 × 4 档：抽签 1 次 reset、派生 3 次 reset、生成 4 局 | `V7_LAYOUT_SHARED`（单格）、`V7_RESET_REPLAY`（单格） |
| 4 正式抽签＋派生（GL，经 P3 一次性授权） | 16 任务 × 24 候选母布局 reset；13 任务 × 3 档 × 24 派生 reset | `V7_LAYOUT_SHARED`、`V7_TIER_MONOTONE` |
| 5 gen1 生成 + gen2 重放（GL，两个占位 job） | 55 格 × 20 局 × 2 | `PARITY_V7_TWICE` |
| 6 原三档对拍 | O 侧与 H 侧各 144 局（A40） | `PARITY_O_H` |
| 7 回注回放与入口冒烟 | 每格 1 局经评估链 | `V7_RESET_REPLAY`、`HARD_EVAL_SMOKE` |
| 8 发布与留档 | 替换包内四份 specs、删 V6 快照与迁移脚本、改 README 三份、`docs/validation/newtask-v7/`、bucket 上传、按清单 `scancel` | `BUCKET_SYNC`；`git diff --check` |

实施完成后实测结果以子节追加在本表之后，不改写原计划。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

R1. `src/robomme/` 零改动（P2）；三个官方入口与录像器零 diff。xhard0 只在 `src/robomme_hard/` 侧新增条目与分派。
R2. 不把 `"xhard0"` 加进 `difficulty.py::NEWVALUE_DIFFICULTIES`／`VALID_DIFFICULTIES`；xhard0 传给 `gym.make` 的 `difficulty` 是 `"hard"`（`normalize_robomme_difficulty` 不认 `"xhard0"`，`spec_kind_for` 据此选原值类别）。
R3. 不改任何梯度取值（D-5）；`sampling_config` 由 `_extract.build_sampling(..., release="newtask-v6")` 提取的结果必须与 v7 xhard4 header 内嵌值相同（`tests/lightweight/test_sampling_config_split.py::test_v6_snapshot_matches_source` 继续钉死）。
R4. 派生失败四档同步作废，不许单档换布局；失败不换 seed、不重试到成功；基础设施失败每身份最多重跑 1 次。
R5. 对拍只做 D-8 两条；`--calibrate` 仍只允许 `O:P`，v7 不重标、不改容差文件；两次生成必须同型号同驱动（A40），`generate` 的 A40 断言保留。
R6. reset／轨迹预算按 P3 一次性授权（§3 预算表），乘式写法（P5）；本方案不是启动许可。
R7. 主会话唯一整合与提交者；子代理只读或按互斥文件集合改动；子代理不 commit、不 push。
R8. `scripts/` 顶层四入口不变（P1）；新脚本落 `scripts/injection-dev/` 与 `scripts/parity/`。

## 1. 逐文件改动清单

### 1.1 `src/robomme_hard/env_record_wrapper/`

| 文件::锚点 | 改什么 | 关闭态／现有档 | v7 态 |
|---|---|---|---|
| `hard_specs.py::SCHEMA` → `SCHEMAS=("hard-specs/2","hard-specs/3")` | `validate_specs` 按 header schema 分支：`/2` 逻辑原样（读旧快照用），`/3` 增加 v7 校验 | V6 文件仍可读 | 包内四份为 `/3` |
| `hard_specs.py::SEED_PROFILES` 加 `"v7"`，新增 `V7_SEED_OFFSET=14_000_000`；`seed_rule_for(tier,"v7")` 四档同 offset；`_known_seed_rule` 遍历三族 | — | v6 规则族保持互斥断言 | v7 四档同 seed |
| `hard_specs.py::BUILDER_TIERS=("xhard0",*TIERS)`；`TIERS` 不变 | builder 档序与新值族分开（触点报告结论 1） | `TIERS` 仍四档 | builder 遍历五档 |
| `hard_specs.py::TIER_MAX_STEPS` 加 `"xhard0": 1300` | — | 四项不变 | 五项 |
| `hard_specs.py::XHARD0_CELLS`（16 任务）、`XHARD0_PER_TASK=12`、`XHARD0_EPISODES=(3,7,…,47)` 只作核对值，筛选仍按 `difficulty=="hard"` | — | — | 断言 12 条／任务 |
| `hard_specs.py` header 新键（`/3`，进 `IDENTITY_HEADER_KEYS`）：`layout_rule={"mode":"shared","parent_tier":"xhard4","whitelist_sha256":…}`；行新键（进 `IDENTITY_ROW_KEYS`）：`layout_parent`（xhard1～3 为 `{"tier":"xhard4","candidate":c,"spec_sha256":…}`，xhard4 为 `null`） | `validate_specs` 对 `/3`：四档 seed 同公式；派生行 `layout_parent.spec_sha256` 必须能在 xhard4 文件里找到同 candidate 行（跨文件校验放 `load_specs_v7(root)`，单文件校验只查形态） | — | — |
| `hard_specs.py::spec_binding` | 新增 `layout_injected`（L 点上 drawn≠frozen 且 drawn == `layout_drawn[path]` 的条数）与 `layout_drift`（drawn ≠ `layout_drawn` 的条数，计入 `injected_mismatch`） | 非 layered 规格两项为 0 | 派生局 `layout_injected>0`、`injected_mismatch==0` |
| `hard_builder.py::_xhard0_entries(env_id)` 新增 | 复用父类 `__init__` 以 `dataset="test"` 读到的元数据（清空 `metadata_index` 之前取出），筛 `difficulty=="hard"`，按原 episode 升序；校验源文件 sha256 在锁定清单内、12 条、seed 唯一 | — | 条目 `{tier:"xhard0", seed, source_episode, sampling_config:None, spec:None}` |
| `hard_builder.py::_test_hard_entries` | 先 xhard0 12 条，再 `for tier in TIERS` 原逻辑；每格断言 `delivery_per_cell==20` | — | 92／32 局 |
| `hard_builder.py::_hard_env_kwargs` | `tier=="xhard0"` 分支只返回 `seed, difficulty="hard"`；其余分支不变 | — | — |
| `hard_builder.py::resolve_identity` | xhard0 返回 `{episode, tier:"xhard0", source_dataset:"test", source_episode, seed, spec_sha256:None, source_run:None}`；派生行多返回 `layout_parent` | — | — |
| `__init__.py` | 导出 `BUILDER_TIERS` | — | — |

### 1.2 `src/robomme_hard/robomme_env/utils/episode_spec.py`

| 锚点 | 改什么 |
|---|---|
| `SPEC_KIND_LAYERED="native-layered/3"`，`SPEC_KINDS` 加入 | 派生规格类别；`spec_kind_for` 不变（按难度只区分原值／新值），layered 由构造参数决定 |
| `SpecRecorder.__init__(spec, task, identity, *, mode, parent=None, layout_paths=None)` | 新增 `mode="derive"`：`parent` 为母规格，`layout_paths` 为白名单（精确路径 + 前缀路径两类） |
| `SpecRecorder.value` | `derive`：路径命中白名单 → 照常抽、记 `layout_drawn[path]=drawn`、返回母值（列表值返回 `parent[:len(drawn)]`；母规格缺该路径 → 抛 `EpisodeSpecError`，不静默回退到抽样值）；未命中 → 照常抽、照常用。`replay` 且 `spec_kind==layered`：命中白名单 → 比对对象为 `spec["layout_drawn"][path]`，使用值为 `spec` 树里的冻结值；未命中 → 原逻辑 |
| `SpecRecorder.to_dict` | layered 导出多写 `layout_parent`、`layout_drawn`、`layout_paths_hit`（命中的白名单路径集合，供 `V7_LAYOUT_SHARED` 静态核对） |
| `leaf_paths`／`consumed_paths` | 不变；母规格多出的逐项路径不进派生规格（派生规格只含本局实际使用值），所以 `unused` 在派生局应为 0 |

### 1.3 布局白名单（写成 `src/robomme_hard/env_metadata/test-hard/layout_whitelist.json`，随包发布，sha 进 header）

| 环境 | L（注入；`*` 为逐项路径，`[:n]` 为列表按抽到长度取前缀） | G（现场重抽） |
|---|---|---|
| PickXtimes | `layout.button_xy`、`objects.color_order`、`objects.target_color_idx`、`layout.goal_xy`、`layout.cubes.*`、`objects.target_cube_idx`、`layout.distractors.*` | `objects.num_repeats` |
| SwingXtimes | 同上，另 `layout.targets.*` | `objects.num_repeats` |
| BinFill | `layout.dynamic`、`layout.button_xy`、`layout.board.offsets`、`objects.color_pool`、`objects.put_in_color`、`objects.spawn_numbers`、`objects.spawn_order`、`layout.slots.*`、`objects.slot_assignment`、`initializations.*.color_order` | `objects.target_numbers` |
| VideoUnmaskSwap／ButtonUnmaskSwap | `layout.type_choice`、`layout.bins.*`、`objects.color_order`、`objects.selected`、`objects.target_choice`、`objects.swap_initiator_indices`、`objects.swap_initiator_third`、`objects.distractors.bins.*`、`objects.distractors.color_order` | `objects.n_swaps`、`objects.n_picks`、`objects.swap_plan_seed`、`actions.swap_pairs.*`、`objects.distractors.cube_count`、`objects.distractors.cube_bins`、`objects.distractors.label_perm`、`objects.distractors.swap_plan_seed` |
| VideoUnmask／ButtonUnmask | `layout.button_xy`（BU）、`layout.bins.*`、`objects.color_order`、`objects.distractors.bins.*`、`objects.distractors.color_order` | `objects.distractors.cube_count`、`objects.distractors.cube_bins`、`actions.sampling_trace.constructor_draw`（BU） |
| VideoRepick | `objects.color_rgb`、`layout.cubes.*`（含 `layout.button_xy` 若存在） | `objects.num_repeats`、`objects.n_swaps`、`objects.target`、`objects.swap_initiators_remaining`、`objects.swap_plan_seed`、`actions.swap_pairs.*` |
| VideoPlaceButton | `layout.goal_xy`、`layout.button_xy`、`objects.color_order`、`layout.cubes.*`、`layout.targets.*` | `objects.demo_ids`、`objects.swap_pair_ids`、`objects.task_flag`、`objects.answer_demo_index`、`objects.extra_place_owner_ids`、`objects.extra_place_target_ids.*` |
| VideoPlaceOrder | 同 VideoPlaceButton 的 L | `objects.visit_counts_by_object`、`objects.demo_ids`、`objects.swap_pair_ids`、`objects.visit_ids_by_object.*`、`objects.answer_demo_index`、`objects.which_in_subset`、`objects.button_after_visit_index` |
| PickHighlight | `layout.button_xy`、`objects.color_rgba.*`、`layout.cubes.*` | `objects.n_cubes`、`objects.highlight_count`、`objects.highlight_ids` |
| PatternLock | `actions.path_nodes[:n]` | （无） |
| RouteStick | `layout.rotation_deg`、`layout.obstacle_rgb.*`、`actions.nodes[:n]`、`actions.directions.*` | `objects.L` |
| StopCube／InsertPeg／MoveCube | 不派生（只有 xhard4） | — |

白名单以子代理静态审计为准，实施阶段 1 须用「导出模式跑一次 xhard4 单局，比对 trace 里的全部 value 路径」核对每个环境的路径拼写，漏一条即 `EpisodeSpecError`。记录点一律不进白名单。

### 1.4 `scripts/injection-dev/`

| 文件::锚点 | 改什么 |
|---|---|
| `freeze_specs.py::main` | 加 `--seed-profile {v6,v7}`（默认 v7）、`--select` 支持 `0..19` 区间写法；`--tier xhard4 --candidates-per-env 24 --select 0..19`；header 写 `layout_rule` |
| `_draw.py::draw_task`／`merge_task_rows` | 传 v7 规则；其余不变 |
| `_freeze.py::freeze` | `/3` 封签；`delivery_per_cell=len(select)=20`；MoveCube 的 `stratified_select` 只对 xhard4 生效（不变） |
| 新增 `derive_specs.py` | 输入 xhard4 v7 文件 + 白名单 + 目标档；对每个候选起环境 `gym.make(task, sampling_config=cfg[tier], native_episode_spec=None, seed=母 seed, difficulty=tier)` 并把 recorder 置为 `derive` 模式（通过新的 `native_layout_parent=` kwarg 传入母规格与白名单）→ `reset` → 导出派生规格 → 按目标档 header 封签写 `xhard{1..3}/specs.jsonl`；失败记 `derive_fail`，并在四档同步把该候选标 `selected=False`；多 worker、`--workers`、`--gpus`、`--dry-run` 打印 reset 预算 |
| `_rollout.py::plan_pending`／`apply_results` | 递补改为跨档同步：某档某候选 rollout 失败 → 四档该候选全部退选，递补同一个下一候选（要求该候选四档规格都存在且 `tried=False`）；单档文件锁升级为四档目录锁 |
| `generate_h5.py` | `--mode continue` 输入 `--specs-root <test-hard 目录>`（四档一起）；`--mode replay` 不变（gen2 用） |
| `_report.py` | 报告增加 `derive_fail`、`sync_dropped` 计数（显式零值） |
| 删除 `migrate_smvla_specs.py` | 见第一部分 §5 |
| `site/v6_tier_monotone.py` | 加 `--specs-root` 读 v7 四档实际值输出 `V7_TIER_MONOTONE` |

### 1.5 `scripts/parity/`

| 文件::锚点 | 改什么 |
|---|---|
| `train_split_worker.py::run_one` | payload 增加可选 `layout_parent`；有则以 `derive` 模式构造 recorder；`spec_replay.json` 多写 `layout_injected`／`layout_drift` |
| `train_split_runner.py` | 透传 `--layout-parents <jsonl>`；`--identity-source formula` 接受 v7 规则 |
| `hard_parity.py` | `SIDES` 加 `H2`，`PAIRS` 加 `H:H2`，`TIERS` 加 `"v7"`（清单从 v7 四档 `delivered` 行导出，键 `task/tier/candidate/seed`，`xhard_rows` 同时接受 `tier` 与 `difficulty`）；`cmd_generate --tier native` 透传 `--metadata-root scripts/configs/newtask-v3/official_train`（取回后）；`cmd_compare` 的 `shape` 文案按 tier 取：native `16x3x3`、v7 `13x3x20+16x1x20`；`_binding_ok` 对 `H2` 与 `H` 同规则；`cmd_import_s4` 删除 |
| `hard_regression.py` | `s4-subset` 删除；`reset-replay` 改为从 v7 四档每格取 candidate 最小的正式局（55 局）经评估链回放，判定 `V7_RESET_REPLAY`；新增 `layout-shared`（静态，`V7_LAYOUT_SHARED`）；`eval-smoke` 的局数断言改 `32 if XHARD4_ONLY else 92`，并接受 episode 0 为 xhard0（`available=False`）、episode 12 为回注局 |
| `scripts/configs/newtask-v3/` | 从 `6e70c0bf` 取回 `subset_manifest.json` 与 `official_train/`（只读清单，不再删除；P1 允许 `configs/` 子目录） |

### 1.6 `scripts/evaluation_hard.py`、README 与测试

- `evaluation_hard.py`：不改逻辑；`diff scripts/evaluation.py scripts/evaluation_hard.py` 仍恰好 README 第 1 节那 4 处。
- README 三份（`scripts/README.md`、`src/robomme_hard/README.md`、`scripts/parity/README.md`）按第一部分 §4 改数字与链路说明；`readme.md` 不动。
- 测试：新增 `tests/lightweight/test_xhard0_native.py`（身份 16×1×12、分派实参、`TIER_MAX_STEPS` 五项）、`test_v7_layout_shared.py`（白名单形态、`derive`／layered 回注在无仿真夹具下的 `layout_injected`／`layout_drift` 行为、四档同步递补状态机）、`test_v7_seed_rule.py`（v7 四档同 seed、与 v5/v6 段互不重叠）；改 `test_v6_difficulty_tiers.py::test_v6_seed_rule_offsets_disjoint` 限定 v6 族；`test_hard_state_machine.py` 参数化 v6/v7；`test_hard_parity.py` 补 `H:H2`／`v7` 用例；`test_wrapper_chain.py`（gpu）对 test-hard episode 0（xhard0）与 episode 12（xhard1）各做一次。

## 2. 预算（P3 一次性授权用，乘式写法；本方案不是启动许可）

| 项 | 乘式 | 上限 |
|---|---|---|
| 母布局 reset（阶段 4，xhard4 配置） | 16 任务 × 24 候选 = 384 次成功目标；`--max-reset-attempts` 每任务 40 | ≤ 16 × 40 = 640 次 reset |
| 派生 reset（阶段 4） | 13 任务 × 3 档 × 24 候选 = 936 次，每候选只 1 次、失败不重抽 | ≤ 936 次 reset |
| gen1 轨迹（阶段 5） | (13 任务 × 4 档 + 3 任务 × 1 档) × 20 局 = 1100 局；同步递补上限每格 4 → 55 格 × 4 = 220 | ≤ 1320 次轨迹 |
| gen2 轨迹（阶段 5） | 1100 正式局重放；基础设施失败每身份最多 1 次 | ≤ 1100 + 1100 |
| O:H 原三档（阶段 6） | 2 侧 × 16 任务 × 3 档 × 3 局 = 288 | ≤ 288（+ 基础设施重跑 ≤ 288） |
| 回注回放（阶段 7） | 13 × 3 + 16 = 55 次 reset | 55 |
| 本机冒烟（阶段 3） | 1 任务 × (1 + 3) reset + 4 局 | 4 reset、4 轨迹 |

worker：GL 每占位 job 16 worker（1 CPU + 12 G／worker）；预计耗时以阶段 3 单格实测外推后填入，不预先编数。停止条件：任一阶段判定行 FAIL 即停该阶段及其后续，保留产物与日志。

## 3. runbook（命令为拟定形态，参数名以实施时定稿为准）

```bash
# 阶段 0
git show 6e70c0bf:scripts/configs/newtask-v3/subset_manifest.json > scripts/configs/newtask-v3/subset_manifest.json
git archive 6e70c0bf scripts/configs/newtask-v3/official_train | tar -x
for f in src/robomme/env_metadata/test/*.json; do jq -c '{task:.env_id, hard_count:([.records[]|select(.difficulty=="hard")]|length), eps:[.records[]|select(.difficulty=="hard")|.episode]}' "$f"; done
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream

# 阶段 3（本机，GPU 0）
uv run --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard4 --tasks BinFill --seed-profile v7 --candidates-per-env 1 --select 0 --workers 1 --gpus 0 --out artifacts/newtask-v7/smoke/xhard4/specs.jsonl
uv run --no-sync python scripts/injection-dev/derive_specs.py --parent artifacts/newtask-v7/smoke/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --whitelist src/robomme_hard/env_metadata/test-hard/layout_whitelist.json --out-root artifacts/newtask-v7/smoke --workers 1 --gpus 0
uv run --no-sync python scripts/parity/hard_regression.py layout-shared --specs-root artifacts/newtask-v7/smoke
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs-root artifacts/newtask-v7/smoke --output artifacts/newtask-v7/smoke/rollout --workers 1 --gpu 0

# 阶段 4～6（GL 占位 job 内 srun --overlap --gpu_cmode=shared；先 --dry-run 打印预算再起 tmux）
uv run --frozen --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard4 --tasks all --seed-profile v7 --candidates-per-env 24 --select 0..19 --max-reset-attempts 40 --workers 16 --gpus 0 --out <NFS>/v7/xhard4/specs.jsonl
uv run --frozen --no-sync python scripts/injection-dev/derive_specs.py --parent <NFS>/v7/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --out-root <NFS>/v7 --workers 16 --gpus 0
uv run --frozen --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs-root <NFS>/v7 --output <NFS>/v7/gen1 --workers 16 --gpu 0
uv run --frozen --no-sync python scripts/injection-dev/generate_h5.py --mode replay --identities <NFS>/v7/gen1/final-delivery.json --specs-root <NFS>/v7 --output <NFS>/v7/gen2 --workers 16 --gpu 0
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side O --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json --src-root <1fadc0ec worktree> --workers 16 --gpu 0 --out /tmp/hs/O-native --stage <NFS>/hs-stage/O-native
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json --workers 16 --gpu 0 --out /tmp/hs/H-native --stage <NFS>/hs-stage/H-native

# 本机比对
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/hs-stage --dest artifacts/newtask-v7/parity --segments O-native,H-native,H-v7,H2-v7
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python scripts/parity/hard_parity.py compare --pair H:H2 --tier v7 --manifest artifacts/newtask-v7/gen1/final-delivery.json
uv run --no-sync python scripts/parity/hard_regression.py reset-replay --out artifacts/newtask-v7/reset-replay
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 0
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 12
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

长任务一律 detached tmux（会话名前缀 `v7-`，清单记入留档）+ Monitor 行缓冲过滤管道，过滤词含 `NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|Traceback|EXIT_CODE=|全部完成`。集群操作按 `greatlakes.md`（48 h 占位 job、`--gpu_cmode=shared`、跑完按清单逐个 `scancel`）。

## 4. 风险登记

| 风险 | 处置 |
|---|---|
| 白名单漏路径或拼错 | 阶段 1 用导出 trace 逐环境核对；`derive` 模式对母规格缺路径直接抛错，不静默回退 |
| 派生时外环交换／额外放台不可行（VUS/BUS/VPB） | 计入 `derive_fail`，四档同步作废该候选；候选留 4 个余量；余量耗尽即停并报用户，不追加抽签 |
| 前缀在低档下不合法（理论上不会） | 环境二次复核会抛错；出现即视为白名单分类错误，回到阶段 1 |
| 派生规格的 `layout_drawn` 与回放不等（随机流漂移） | `layout_drift>0` 计入 `injected_mismatch`，`V7_RESET_REPLAY` FAIL；不放宽 |
| `record()` 点在派生局与母局不同（如 `objects.distractor_count`） | 派生规格只含本局实际值，回放比对的是派生规格，不比母局 |
| 同步递补让四档目录锁竞争 | 目录锁 + 单写者；`--self-check` 核 identity 未变 |
| gen1/gen2 落在不同型号卡 | `generate` 保留 A40 断言；launch 记 GPU 名与驱动，`compare` 前核对相同，否则只报容差、不报 `sha_equal` |
| 144 清单来自官方 train 元数据，不含 test 的 hard seed | 它验证的是 `robomme_hard` 原生路径与官方路径一致，这正是 xhard0 所走的路径；xhard0 逐身份零差是 12.222 §5 的可选项，不在本文预算 |
| xhard0 走官方 `_worker` 时 `EpisodeJob.recovery_mode` 按 episode 号定（≤2 z、≤5 xy） | xhard0 不生成 h5，评估链 `make_env_for_episode` 不经 runner，此陷阱不触发；若日后生成须显式 `--no-recovery` 与官方 test 口径核对 |
| 两个策略仓库读 `spec_binding` 字段 | 新增键只增不改；xhard0 返回 `available=False` 与现有 `None` 分支兼容，实施后各跑 1 局 smoke |

## 5. 盲区诚实清单

- 白名单与「前缀合法」结论来自静态审计，未运行任何环境；阶段 3 单格冒烟是第一次动态证据。
- 派生失败率未知；24 候选是否够 20 局要看阶段 4 实测，不够即停。
- 两次生成的 `sha_equal` 期望值不承诺（V6 时 P:H xhard 165 对逐字节相同，但 RRT 噪声存在）；判定只看容差与判定层。
- 跨型号容差从未标定；本机 Ada 与 aspen A6000 的任何 v7 产物都不进正式对拍。
- 本文未估算耗时；以阶段 3 单格实测外推后补。

## 6. 留档与 commit 纪律

- 本轮只提交本方案：`git diff --check`、`grep -c '^# 第一部分\|^# 第二部分'` 等于 2、链接目标存在；逐路径 `git add`，中文 commit（`12.223 …`）后立即 push。
- 实施各阶段：阶段 1～2 各一个 commit；阶段 4～6 起跑前 HEAD 精确等于所跑代码（起跑到 gen2 完成之间不 commit）；留档 `docs/validation/newtask-v7/`（判定行内联原文、GPU／驱动／依赖指纹、真实尝试计数、首个差异、退出码、输出路径、tmux 会话与 JobID 清单）；bucket 上传后 NFS 与 `/tmp` 不留大文件。
- 不把本文写入规则文件、不追加历史账本；用户原话与判定行按第 22 条进 commit body 与留档。
