# 0927 方案：`robomme_hard` 分层继承双包 · 两阶段生成 · 单一 jsonl（只规划不实施）

> **权威性**：本文件是 [`0926-robomme-hard-split-plan.md`](0926-robomme-hard-split-plan.md) §〇′ 的精简定稿版，只写最新口径；两份冲突时以本文件为准。只规划，不实施；每一阶段须单独获批后才动手。
> **修订（2026-09-27 夜）**：吸收同日两份审计——Claude 对抗审查（7 维度 opus 审查、逐条 sonnet 反驳，91 条确认 87 条）与 Codex 审计（另派 3 个 sonnet 逐条核实）——以及用户四项裁决（§一 U-1～U-4）。两份审计锚点均为 `55f1b027`（12.204.10）。
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `55f1b02776b55daaa39c20131d0ac0fa98f67b5c`（`66d9a424` 至此只有文档改动）。官方两个锚点分开钉（审计确认 `1fadc0ec` 里没有 `scripts/data-generation/`）：
> - **官方环境源码** `src_commit` = `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`（tree `3006988f…`）；
> - **官方生成编排** `orchestration_commit` = `dataset-gen` @ `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`（tree `1d4c1369…`，即隔离树 `artifacts/train-parity/local-smoke-01/official-src/` 的 `.official_tree`，也是 `scripts/parity/train_split_parity.py` 的 `DEFAULT_SOURCE_REF`）。两者 `src/robomme` 零 diff（阶段 0 留证）。
>
> 现行规格 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（四档 550 行、selected 165 行，其中 2 行不是实际交付局，见 §5.3）；S4 交付清单 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`（`successes` 165 条，逐局记 h5 sha256／字节数／路径，`code_baseline=ca32e9b`）。
> **工作副本**：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（环境 A，sled-vail）。
> **对拍硬件**：四个 A40 @ greatlakes `spgpu` 占位 job，三侧统一在 A40 上生成；本机 RTX 6000 Ada 只做开发冒烟。按用户裁决 U-1，对拍判定是「行为一致」而不是「字节一致」（理由见 §5.4）。占位 job（用户 2026-09-27「这四个你可以自由跑」「就用现有的占位job」，不新交）：`62126060` gl1517、`62126061` gl1504、`62126062` gl1506（`hs-hold-20260927-1/2/3`）、`62018665` gl1510（本方案不再使用；释放须用户另行指示）。JobID、驱动、剩余时长都是写作时的快照，阶段 4 起跑前重新核实。
> **评估接口**（用户 2026-09-27「dataset传入test-hard内部再分xhard1234」「只保留着一个接口哦」）：对外只新增 `dataset="test-hard"` 一个取值；builder 内部把 xhard1～xhard4 串成每任务 12 局（xhard4-only 的 `StopCube`、`InsertPeg`、`MoveCube` 为 3 局）。`xhard1`～`xhard4` 不是合法 `dataset` 值。
> **三侧**：O 侧官方（编排 `d53f21a7` + 环境源码 `1fadc0ec`）；P 侧本仓库 tag `pre-hard-split` → `7c7118fa`（生产代码基线 `ca32e9b`，两者 `src/` 零 diff）；H 侧拆包后 HEAD。持久化 bucket：`HongzeFu/robomme-hard-parity`。
> **计数体例（P5）**：原三档 = 16 任务 × 3 档（easy/medium/hard）× 3 局 = 144；xhard = xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165（xhard1～3 缺 `require_xhard4_only` 的 `StopCube`、`InsertPeg`、`MoveCube`）。
> **commit 体例**：`<大>.<小>[.<修订>] <中文描述>`，实施从 12.205 起。
> **外部依赖**：`uv.lock` / `pyproject.toml` 的依赖不变，唯一改动是 wheel `packages` 增加 `src/robomme_hard`。bucket 操作用 sled-vail 上的一次性工具环境 `uvx --from huggingface_hub==1.8.0 hf …`，因为锁定的 `huggingface_hub` 1.4.1 没有 bucket API；不进项目依赖。
> **已完成、不再赘述**：V6 四档生成与 S0～S5 验收、审查修复、拆包阶段 0b 瘦身（12.200～12.203）。

---

# 第一部分（给人看）

## 一、总览

**一句话方案**：
- **双包并列**：`src/robomme/` 逐字节等于官方 `1fadc0ec`；`src/robomme_hard/` 只放差异。
- **复制、借用、子类化三种做法**：
  - 复制：16 个环境类，以及「改过、新增，或传递依赖改过模块」的 utils 与 wrapper；
  - 借用：依赖闭包干净的官方模块，用 shim 指过去；
  - 子类化：`BenchmarkEnvBuilder`，整段覆写构造环境的路径。
- **规格随包分发**：四档规格放在包内 `env_metadata/test-hard/xhardN/specs.jsonl`，迁移时从 S4 交付回填每局结果。
- **生成链路两阶段**，放在 `scripts/injection-dev/`：第一阶段只落一份 jsonl；第二阶段只读这份 jsonl 生成 h5，按明确的状态机回写。
- **评估侧**：`BenchmarkEnvBuilder(env_id, dataset="test-hard")` 自己读包内 jsonl，包装链与官方 `test` 完全相同；评估步数上限固定为 `HARD_MAX_STEPS=2658`。

**用户裁决（2026-09-27 夜，AskUserQuestion 原选项与原话逐字保留）**：

| 编号 | 问题 | 用户选择／原话 | 落到哪 |
|---|---|---|---|
| U-1 | 三侧对拍在 RRT 墙钟非确定性下怎么判 | 「C 维持 16 worker、全部降级」 | §5.4、§6.1 |
| U-2 | test-hard 评估步数上限 | 「test-hard 评估的步数上限 先定死一个上限 按照现在的h5生成结果 加上20%雨量」 | §4.3 |
| U-3 | 阶段 1 的 `override=True` 与 builder 子类覆写属 P2「覆盖」，怎么批准 | 「现在一次批准这两项」 | §3.3、第二部分 R10 |
| U-4 | h5 从 GL 节点落到 /data 与 bucket | 「需要保存h5 ac都可以」→ 取 A：NFS 按片短暂中转（主代理按 memory「取整等细节自己定」选定） | §5.4、第二部分 §3.2 |

**已定死口径**：

| 编号 | 口径 | 依据 |
|---|---|---|
| E-1 | 双包、分层继承：环境类，以及改过、新增或**传递依赖改过模块**的 utils／wrapper 一律复制；依赖闭包干净的借用；builder 子类化 | §3.1、§3.2 |
| E-2 | 环境类同 id，副本一律 `@register_env(<id>, override=True)`；包导入末尾断言注册表归属与命名空间归属 | §3.3（U-3 已批准） |
| E-3 | G1 用双锚点（`src_commit`／`orchestration_commit`）＋逐文件 sha256 清单＋守卫脚本＋导入时 cheap 校验；阶段 3 之前守卫输出 `PENDING` | §3.4 |
| E-4 | 生成链路两阶段，全部依赖放 `scripts/injection-dev/`；第一阶段只落一份 jsonl，首次落盘用排他发布 | §5.1 |
| E-5 | jsonl 行分「签」和「结果」两段：`identity_sha256` 只盖签；另设 `delivery_sha256` 盖正式交付集合；`selected` 只表示正式交付局 | §5.3 |
| E-6 | 包内 jsonl 迁移时从 S4 `final-delivery.json` 逐身份回填 `rollout` 与 `candidate`，selected 与实际交付对齐 | §5.3 |
| E-7 | 对外只新增 `dataset="test-hard"`；`scripts/evaluation.py` 原样不动；`evaluation_hard.py` 为第五入口，与它只差 import 行、`dataset`、`max_steps` 三处 | §四 |
| E-8 | h5 本体不写任何包指纹；来源、代码指纹、实际加载的环境类模块只进 results、manifest 和 jsonl `rollout` 块 | §3.3、§5.4 |
| E-9 | 官方 `scripts/data-generation` 四文件从 `d53f21a7` vendor 进 `scripts/parity/official/`；runner 显式传元数据根，不依赖官方脚本按 `__file__` 推出来的默认根 | §3.5 |
| E-10 | `tests/` 分三类逐文件处理，判据是可收集，并且残留的 `robomme.robomme_env` 引用清单为空或逐条注明 | 第二部分 R8 |
| E-11 | 预算表按乘式分别列 rollout 与 reset 的总尝试上限，含冒烟、阶段 3 后重跑、基础设施重跑上限、停止条件；实施前向用户一次性申请 | 第二部分 §3.1 |
| E-12 | 四个 Unmask 任务的 train 元数据 400 条放在 `robomme_hard`，builder 覆写元数据路径去读；`robomme` 回到官方 100 条 | §3.1、§4.2 |
| E-13 | 三侧统一在 A40@GL 上生成；原三档 S0 基线在 A40 重新生成，本机 Ada 产的 `artifacts/newtask-v6/v1/base` 不再作判据（用户 2026-09-27「123全部同意」） | §5.4 |
| E-14 | 三侧 O／P／H；对拍矩阵 `O↔P`、`P↔H`、`O↔H`（原三档）与 `P↔H`（xhard，P 侧复用 S4 交付存档） | §5.4 |
| E-15 | h5 全部持久化到 HF bucket `HongzeFu/robomme-hard-parity`，每侧附 `identities.jsonl`、`SHA256SUMS`、`manifest.json`；上传后逐对象读回核对 sha256，同源判定不用 xetHash | §5.4 |
| E-16 | **对拍判定为行为一致（U-1）**：身份集合、setup、结构、任务成功全等才算 PASS；sha 相等数与数值差异只作参考 | §5.4、§6.1 |
| E-17 | 单 GPU 16 worker（`--gpu_cmode=shared`，`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`），进程池不加 `max_tasks_per_child`；不再做 `WORKER_INVARIANT` 探针 | 第二部分 §3.2 |
| E-18 | 跨硬件只作参考 `XHW_REFERENCE=INFO`，只用现存 Ada 原三档产物对比 A40 的 O 侧，不新增 rollout | §6.2 |
| E-19 | `HARD_MAX_STEPS = 2658` = ⌈S4 交付 165 局最长非演示执行步数 2215 × 1.2⌉（U-2） | §4.3 |

## 二、要保证什么

| 保证 | 靠什么 | 判定行 |
|---|---|---|
| G1 `src/robomme/**` 与官方 `1fadc0ec` 逐字节相同 | §3.4 | `UPSTREAM_BYTES=PASS src_commit=1fadc0ec files=<n> diff=0 shims=18` |
| G2 `robomme_hard` 跑原三档，与官方、与修改前行为一致 | 三侧对拍 §5.4 | `PARITY_O_P` / `PARITY_P_H` / `PARITY_O_H` `=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 sha_equal=<k>`（16 × 3 × 3） |
| G3 `robomme_hard` 跑 xhard，与 S4 交付行为一致；回注通道逐值一致 | §5.4 | `PARITY_P_H=PASS tier=xhard compared=165 …`（13×3×3 + 16×3）、`HARD_RESET_REPLAY=PASS resets=55 spec_mismatch=0 goal_mismatch=0`（13×3 + 16） |
| G4 评估接口与 `dataset="test"` 同形，包装链相同，语言目标用的是 hard 版 | §四 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5`、`EVAL_HARD_DIFF=PASS lines=6`、`WRAPPER_CHAIN=PASS action_spaces=4` |
| G5 同进程 16 个环境 id 与命名空间归属唯一可查；各侧实际加载的包可证 | §3.3 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard`、`NAMESPACE_OWNER=PASS envs=16 stray=0`、`ENV_PACKAGE_BINDING=PASS` |
| G6 两阶段只依赖 jsonl；首次落盘排他；回写不破坏封存、不丢并发更新 | §五 | `FREEZE_ONLY_JSONL=PASS`、`ROLLBACK_WRITE=PASS`、`STATE_MACHINE=PASS` |
| G7 三侧 h5 在 bucket 里可按 sha 读回、可拉回重比 | §5.4 | `BUCKET_SYNC=PASS sides=3 objects=<n> readback_sha_equal=<n> mismatch=0` |

## 三、文件结构与分层继承

### 3.1 `src/` 目录：每个文件从哪来

```text
src/robomme/                          官方 1fadc0ec 原样；本仓库不再往里放任何自有文件
src/robomme_hard/
  __init__.py                         先注册自家 16 环境 → 断言注册表与命名空间归属 → 借用清单 cheap 校验（§3.3、§3.4）
  UPSTREAM.json                       双锚点、src/robomme 逐文件 sha256、shim 清单、自校验哈希
  README.md
  logging_utils.py                    借用 shim（复制文件里的 ..logging_utils／...logging_utils 相对导入落在这里）
  robomme_env/
    __init__.py                       复制；新增 ENV_IDS 16 元组
    <Task>.py × 16                    复制；装饰器改 @register_env("<id>", override=True)
    utils/
      __init__.py                     复制
      改过 8 个（difficulty object_generation route segmentation_utils subgoal_language
                task_goal subgoal_planner_func vqa_options）                              复制
      新增 9 个（bin_collision episode_spec sampling_config swap_uniform unmask_distractor_sampler
                unmask_distractors unmask_swap_xhard xhard xhard_home_site）              复制
      传递依赖改过模块的 2 个（subgoal_evaluate_func task4recovery）                      复制
      闭包干净的 13 个（adjacent choice_action_mapping constant obschange oracle_action_matcher
                planner_denseStep planner_fail_safe reset_panda rpy_util save_reset_video
                SceneGenerationError statechange generate_sample_action）                借用 shim
  env_record_wrapper/
    __init__.py                       from .RecordWrapper import *（含 FailsafeTimeout）＋自家 DemonstrationWrapper、
                                      BenchmarkEnvBuilder、hard_specs、HARD_MAX_STEPS ＋借用各项 re-export
    RecordWrapper.py                  复制（fail_safe_limit=5000 是 step() 内部字面量；改 import，不加 attrs）
    DemonstrationWrapper.py           复制（相对导入 task_goal／vqa_options，借用会绑到官方旧文本）
    OraclePlannerDemonstrationWrapper.py   复制（它 import 的 vqa_options 是改过的）
    EndeffectorDemonstrationWrapper.py FailAwareWrapper.py
    MultiStepDemonstrationWrapper.py episode_dataset_resolver.py            借用 shim × 4
    hard_builder.py                   class BenchmarkEnvBuilder(官方 BenchmarkEnvBuilder)（§四）
    hard_specs.py                     load_specs、封套校验、seed 规则、HARD_MAX_STEPS
  env_metadata/
    test-hard/xhard1/specs.jsonl … test-hard/xhard4/specs.jsonl      四档规格（§5.3）
    train/record_dataset_{ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap}_metadata.json   400 条（E-12）
pyproject.toml                        wheel packages 加 "src/robomme_hard"
```

按层归纳：

| 层 | 做法 | 数量 | 理由 |
|---|---|---|---|
| 环境类 | 复制 | 16 | xhard 改动交错在 `_load_scene`／`_initialize_episode` 等长方法里，继承只能整段覆写 |
| 改过／新增 utils | 复制 | 8 + 9 | 与官方不同 |
| 传递依赖改过模块的 utils | 复制 | 2 | 见下方 ⚠ |
| 闭包干净的 utils／wrapper／logging_utils | 借用 shim | 13 + 4 + 1 = 18 | 单一真源 |
| `RecordWrapper.py`、`DemonstrationWrapper.py`、`OraclePlannerDemonstrationWrapper.py` | 复制 | 3 | 前者是字面量改动；后两者依赖改过的 `task_goal`／`vqa_options` |
| `BenchmarkEnvBuilder` | 子类，整段覆写构造路径 | 1 | §4.2 |

自有 `.py` 44 个（包 `__init__` 1 + 环境层 1 + 16 + utils 1 + 8 + 9 + 2 + wrapper 层 6），shim 18 个。

⚠ **借用资格按传递闭包判定，不按单个文件字节**（审计实测反例）：
- 复制的 `utils/__init__.py` 先 `from .subgoal_planner_func import *`、`from .object_generation import *` 绑定自家版本，再 `from .subgoal_evaluate_func import *`。
- 官方 `subgoal_evaluate_func` 模块又 `from robomme.robomme_env.utils import *`，且全链路没有 `__all__`。于是官方 `spawn_random_cube`、`insert_peg` 等整批灌回 `robomme_hard.robomme_env.utils` 命名空间，覆盖自家版本：MoveCube 调用时带 `recorder=`／`spec_path=` 抛 TypeError，InsertPeg 静默丢掉 xhard 杆 yaw 分支。
- `task4recovery` 显式 `from .subgoal_planner_func import solve_pickup` 绑定官方版。
- 官方 `DemonstrationWrapper` 相对导入 `task_goal`／`vqa_options`，评估时 `info["task_goal"]` 会是官方旧文本。
- 阶段 1、2 期间 `src/robomme` 仍是改过的版本，灌回来的函数与自家版本字节相同，所有闸门都看不出问题；阶段 3 回退后才出事。所以 §6.3 的导入类闸门一律在「官方态」下跑（第二部分 §二）。

### 3.2 借用 shim 与 import 改写规则

**为什么借用必须和注册归属一起设计**：Python 导入子模块前先执行父包 `__init__`。`robomme/robomme_env/__init__.py` 就是 16 行 `from .BinFill import *`，所以任何一次借用都会顺带把官方 16 个环境注册进 ManiSkill 注册表。

shim（每个借用文件一个同名文件，不含逻辑）：

```python
# 借用：robomme 同名模块的别名，逻辑以官方为准；清单见 ../../UPSTREAM.json
import importlib, sys
sys.modules[__name__] = importlib.import_module("robomme.robomme_env.utils.rpy_util")
```

复制文件里的导入规则：
- **相对导入**：解析目标必须在 `robomme_hard` 内存在，靠复制或 shim 落地，`logging_utils` 就是这样补上的。
- **绝对导入**：`from robomme.<path>` 且 `<path>` 在 shim 清单内的，保持不动；`<path>` 是复制件的，一律改成 `robomme_hard.`。

AST 扫描同时解析相对与绝对导入，并对每个 shim 目标做传递闭包检查：
- `ABS_IMPORT=PASS files=44 retargeted=<k> kept=<m> unresolved=0`
- `BORROWED_DEPS=PASS shims=18 changed_hits=0`

### 3.3 注册表与命名空间归属

⚠ **实测语义**（`mani_skill/utils/registration.py::register_env`）：同一 uid 二次注册时，`override=False` 只 warn 并静默保留第一个；`override=True` 会把 `REGISTERED_ENVS` 与 gym registry 两处的旧登记一起弹出，再重新注册。

五道机制：

1. **16 个副本 `@register_env("<id>", override=True)`**：进程导入过 `robomme_hard.robomme_env` 后，16 个 id 一律归它，与导入顺序无关。
   - **P2 批准（U-3）**：这是对官方类的运行时替换，属于 P2「覆盖」。用户 2026-09-27 选「现在一次批准这两项」，另一项是 §4.2 的 builder 子类覆写。
2. **`robomme_hard/__init__.py` 的导入检查**：
   - 官方已先导入时 `warnings.warn`；
   - 注册期间压低 `mani_skill` logger 时用对象本身 `from mani_skill import logger`（它的名字带尾随空格 `"mani_skill "`，按名字取会拿到另一个 logger），在 `finally` 里恢复；
   - 导入自家 `robomme_env` 后遍历 `ENV_IDS`，`REGISTERED_ENVS[uid].cls.__module__` 不以 `robomme_hard.` 开头即 `raise ImportError`。
3. **命名空间归属**：
   - 对 16 个环境模块的全部全局可调用对象检查，凡名字在自家复制模块里有定义的，`__module__` 必须以 `robomme_hard.` 开头；
   - 判定行 `NAMESPACE_OWNER=PASS envs=16 stray=0`；
   - 这一条专挡 §3.1 ⚠ 的星号导入回灌，`REGISTRY_OWNER` 只看类的模块，对这类问题结构性失明。
4. **包来源不进 h5**：
   - `env_package`、`package_fingerprint`、`REGISTERED_ENVS[task].cls.__module__`、各 wrapper 类 `__module__` 写进每局 `results.jsonl`、`identities.jsonl` 与 jsonl `rollout` 块，不写进 h5 本体；
   - 原因：H 侧 h5 多写 attrs 会让字节必然与 O／P／S4 不同，而且 `compare_h5_pair` 用 `visititems` 遍历，看不到根节点 attrs。
5. **进程隔离**：同进程一旦导入 `robomme_hard`，16 个 id 全部归它；要官方行为另开进程只导入 `robomme`。runner 里需要 `robomme_hard` 的符号（xhard seed 规则）一律只在 xhard 分支里延迟导入，O／P 侧进程不得触发。

### 3.4 G1 强校验

- **`src/robomme_hard/UPSTREAM.json`**：
  - `src_commit`、`orchestration_commit` 各 40 位（禁 `main`）；
  - `robomme_files`：`git ls-tree -r 1fadc0ec -- src/robomme` 逐文件 sha256，含 `env_metadata`；
  - `shims`：18 项，每项记官方目标模块与目标文件 sha256；
  - `vendor`：四文件 sha256，来自 `d53f21a7`；
  - `manifest_sha256`：剔掉本键后 canonical JSON 的 sha256。
- **`scripts/parity/upstream_guard.py`**（纯 CPU、秒级，纳入核心短测）：
  - `src/robomme/**` 文件集合与 sha **相等**，多一个少一个都 FAIL；
  - 阶段 3 之前输出 `UPSTREAM_BYTES=PENDING diff=<n>`，不计作短测失败；
  - 网络可达时再 `git fetch <url> 1fadc0ec` 复核，不可达标 `net=skipped`；
  - 每个 shim 是 ≤ 3 行非注释行，目标命中清单；
  - `BORROWED_DEPS` 闭包检查。
- **导入时 cheap 校验**：对 shim 目标做 cheap 档（字节数 + 首尾 1 MiB blake2b），不符只 `warnings.warn`。显式声明 cheap 挡不住等长改中间字节，full 档由守卫负责。
- **源码指纹**：`base_fingerprint`（shim 目标总 sha）+ `hard_fingerprint`（`src/robomme_hard/**.py` 总 sha）放进 jsonl header 的 `provenance` 块，**不进 `identity_sha256`**；`load_specs` 不符只警告。

### 3.5 `scripts/` 目录

```text
scripts/
  seed_layout.py  dataset_replay.py  evaluation.py  run_example.py     四入口不动（后三者官方原样）
  evaluation_hard.py                                                    第五入口，与 evaluation.py 只差 3 处（§4.3）
  injection-dev/                V6 四档生产链路，不随包分发（§五）
    freeze_specs.py  generate_h5.py                                     两个入口（路径直跑，不 -m）
    _extract.py  _draw.py  _freeze.py  _rollout.py  _report.py           内部模块（包名参数化，默认 robomme_hard）
    site/                                                               v6_site*.py、v6_candidate_values.py 等只读出图 + _io.py
  parity/                       只做「与官方比」
    train_split_parity.py  train_split_runner.py  train_split_worker.py  train_split_config.py
    train_split_comparison.py  train_split_audit.py  comparator_fixtures.py     S0 基线对拍设施（runner／worker／config 有改动，见第二部分 1.3）
    hard_parity.py              三侧对拍入口：generate / publish / compare（§5.4）
    upstream_guard.py           G1 守卫
    hard_regression.py          reset-replay（经 builder 评估链）、eval-smoke、xhw-reference
    official/                   vendor d53f21a7 的 scripts/data-generation 四文件 + SOURCE.json
      scripts/data-generation/{generate_dataset,validate_generated_dataset_contract,
                               write_generation_report,compare_joint_actions}.py
    README.md
  configs/
    newtask-v3/                 parity 用，不动（subset_manifest.json 是原三档 144 局身份清单；official_train/ 是官方 16 份 train 元数据）
    newtask-v6/v6-02/           只读留档（S4 生成用的那份）；jsonl 真源改为包内
    newtask-v6/smvla-smoke-0927/  不动（不在本方案范围）
    其余（newtask-v4/ v5/ v6 的 sampling_config.json、v6-01/）  删（删前把 site/ 依赖改读包内 header）
```

- **vendor 四文件的原因**：`generate_dataset.py` import 同目录的 `validate_generated_dataset_contract` 与 `write_generation_report`，后者又 import `compare_joint_actions`，缺一个就 import 不了。
- ⚠ **元数据根**：官方 validator 用 `REPO_ROOT = Path(__file__).parents[2]` 推 `METADATA_ROOT`。vendor 之后它会指向不存在的 `scripts/parity/official/src/…`，runner 在默认 `identity_source=train_metadata` 下无参调用 `read_train_metadata()` 会抛 `DatasetContractError`。所以 runner 新增 `--metadata-root`（默认 `scripts/configs/newtask-v3/official_train`，并核对其 sha 与 `subset_manifest.json::records_sha256`），显式传参。
- `identities_16x3.txt`／`manifest_16x3.json` 只有 48 行，不作原三档清单，随阶段 2 删除。

## 四、评估过程中的 env make

### 4.1 合作者看到的

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, HARD_MAX_STEPS   # 与官方唯一不同的 import
builder = BenchmarkEnvBuilder(env_id="BinFill", dataset="test-hard", action_space="joint_angle", max_steps=HARD_MAX_STEPS)
for episode in range(builder.get_episode_num()):                       # BinFill 12 局：xhard1 三局 → xhard4 三局
    env = builder.make_env_for_episode(episode)
    seed, tier = builder.resolve_episode(episode)                        # 可选：想分档统计时取 tier
```

**与官方 `dataset="test"` 的对应关系**：
- `test` 每任务 50 局，easy/medium/hard 混排；
- `test-hard` 每任务 12 局，xhard4-only 的 `StopCube`、`InsertPeg`、`MoveCube` 为 3 局；按 xhard1→xhard4 排列，档内按正式交付局的 `candidate` 升序（多数是 0/3/6；MoveCube@xhard4 是 0/1/4，InsertPeg@xhard4 是 2/4/6）。

### 4.2 builder 内部

```text
dataset ∈ {train,test,val}   → 官方父类逻辑；子类覆写 _resolve_metadata_path：
                                train × 四个 Unmask 任务读 robomme_hard/env_metadata/train（400 条），其余读官方
dataset == "test-hard"       → 对 tier in (xhard1..xhard4) 依次 hard_specs.load_specs(包内 test-hard/<tier>/specs.jsonl)
                                → 取 task==env_id and selected and rollout.status=="ok" 的行，按 candidate 升序
                                → 每档该任务必须恰好 3 行或恰好 0 行（xhard1～3 × 三个 xhard4-only 任务），否则 raise
                                → 四档按序拼接编为 episode 0..11（或 0..2）
其他取值                      → ValueError（与官方一致）
make_env_for_episode 整段覆写 → runtime 四项、seed、difficulty 照抄官方拼法；test-hard 时在 gym.make 前加
                                sampling_config=header.sampling_config[env_id]、native_episode_spec=row.spec；
                                包装链与官方逐项相同：DemonstrationWrapper（用 robomme_hard 复制件）
                                → 按 action_space 选的 wrapper（OraclePlanner 用复制件）→ FailAwareWrapper；
                                wrapper 一律绝对导入；不套 RobommeRecordWrapper（它属于生成链）
```

- **回注**：`native_episode_spec` 是回注。reset 时抽样流程照常发生，但每个取值点用冻结值替换，原抽样只作核验，由 `SpecRecorder` 记 `mismatch/unused`。
- **`resolve_episode(episode)`**：返回 `(seed, tier)`，与官方二元组同形。档名与候选序号只通过它暴露，不另写 `info` 键。
- **runtime 比对**：四项与 header 逐字比对，`render_mode` 放行，所以 `gui_render=True` 可以用；其余不等即 raise。
- ⚠ **白名单绕行**：官方父类 `__init__` 的 `_ALLOWED_DATASETS` 只认 `train/test/val`，而官方代码不能改。子类对 `test-hard` 先喂 `dataset_for_parent="test"` 过校验，再把 `self.dataset` 改回原值；父类顺手读的 `test` 元数据不会被使用。
- **P2**：这组覆写（`__init__`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode`）属于 P2「子类覆写方法」，已由 U-3 批准；README 写实现说明。

### 4.3 评估步数上限（U-2）

- **怎么定的**：`HARD_MAX_STEPS = 2658`。2026-09-27 实测 S4 交付 165 局的 h5，逐局统计 `info/is_video_demo` 为假的时间步数，也就是评估里 `max_steps` 计的执行步数。
  - 各档最长：xhard1 1209、xhard2 1390、xhard3 1663、xhard4 2215（PickXtimes 候选 3）；
  - 超过官方 1300 的局：0 + 4 + 6 + 8 = 18 局；
  - 2215 × 1.2 = 2658。
- **放在哪、谁来用**：常量定义在 `robomme_hard/env_record_wrapper/hard_specs.py`，从 `env_record_wrapper` 导出。builder 不改写调用方传入的值；`evaluation_hard.py` 显式传 `max_steps=HARD_MAX_STEPS`。
- **与 N12 的关系**：这个固定上限取代 N12 的按档上限（`scripts/eval/v4_eval.py::NEWVALUE_MAX_STEPS` 随 `scripts/eval/` 删除）。统计脚本与输出落 `stage1.md`，判定行 `HARD_MAX_STEPS_SOURCE=PASS rows=165 max_exec=2215 cap=2658`。
- **`scripts/evaluation_hard.py` 与 `evaluation.py` 只差 3 行**：import 行、`dataset="test"` → `dataset="test-hard"`、`max_steps=1300` → `max_steps=HARD_MAX_STEPS`。按 `diff | grep -c '^[<>]'` 计是 6。

## 五、数据生成链条：两阶段

### 5.1 第一阶段 `freeze_specs.py`：定规则 → 抽签 → 封存，只落一份 jsonl

**本轮不执行完整抽签**：xhard 四档规格已由 S4 冻结，本轮只迁移。下面这条命令只示范将来重新生成时的调用方式，它本身意味着 13 任务 × 1 档 × 最多 30 次 = 390 次 reset，本轮不申请这笔预算。

```bash
uv run --no-sync python scripts/injection-dev/freeze_specs.py \
  --tier xhard3 --tasks all --candidates-per-env 10 --select default \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 \
  --out <新路径>/specs.jsonl
```

| 步 | 做什么 | 实现来源（搬过去不改语义） | 起环境 | 去向 |
|---|---|---|---|---|
| ① 定规则 | 对 16 任务 `import <pkg>.robomme_env.<Task>`（`pkg` 默认 `robomme_hard`，显式参数），读 `native_blocks` → 合成 `sampling_config` dict | `train_split_config.extract_task`（包名参数化） | 否 | 内存 → header |
| ② 抽签 | 每任务每档 10 候选：seed = `offset(tier) + env_code×1e5 + episode×100 + attempt`；`max_reset_attempts` 是每任务共享的总预算；reset 失败计入 `draw_stats`；子进程初始化导入同一 `pkg` 并断言注册归属 | `v4_specs._draw_one` / `draw_task` / `_draw_worker_init`（包名参数化） | 是（只 reset） | 内存 |
| ③ 封存 | 按完整选签函数选正式局：默认 0/3/6，MoveCube 在新值档按运动方式分层；算 `spec_sha256`、`identity_sha256`；封套校验 | `v4_specs.cmd_freeze` 的选签与哈希逻辑 | 否 | **唯一落盘** `--out` |

- **首次落盘**：沿用 `v4_specs._write_jsonl` 的排他发布——同目录临时文件 + `os.link`，目标已存在就原子失败。不用 `os.replace`，它会静默覆盖。
- **不再产生的文件**：`sampling_config.json`、`drafts.jsonl`；10 个候选与 `draw_stats` 都在 jsonl 里。
- **中断**：第一阶段中断即整批重抽，重抽次数计入预算。

### 5.2 第二阶段 `generate_h5.py`：只读 jsonl → 生成 → 按状态机回写

两种模式分开：

- **`--mode continue`（正常生产）**：
  - **待跑集**：每个 `(task,tier)` 格里 `selected=true` 且 `rollout` 缺失的行；已 ok 的行不重跑（`--redo <身份>` 显式重跑）。
  - **失败处理**：某行失败时，它的 `selected` 置 `false`，`rollout.status="failed"` 保留作历史，`tried=true`；从同格 `tried=false` 且 `selected=false` 的候选里按 `candidate` 升序递补一个，置 `selected=true`。
  - **每格不变式**：`selected=true` 的行数 ≤ 3，恢复时一样。
  - **基础设施失败**（进程超时、Vulkan 建不了设备、节点被抢）每身份最多重跑 1 次，计入预算，并记原因与次数；**任务失败不重试挑成功**。
- **`--mode replay --identities <清单>`（对拍专用）**：
  - 只按给定身份清单逐局重放，不递补、不回写包内 jsonl，结果只写 `--output`；
  - 清单与调度集合必须全等，判定行 `REPLAY_SET=PASS scheduled=<n> equal=<n>`。

执行细节：

1. `load_specs` 读入并封套校验，记下整份文件 sha256、`identity_sha256`、`delivery_sha256`。
2. 分批写 `jobs.json / sampling.json / specs.json` 到 `--output/_rounds/round_NN/`，子进程调 `scripts/parity/train_split_runner.py`。
   - 传 `--sampling-config`，所以走镜像 worker；环境变量 `ROBOMME_ENV_PACKAGE=robomme_hard`。
   - worker 内：`gym.make(task, sampling_config=…, native_episode_spec=row.spec, …)` → 套 `robomme_hard` 的 `RobommeRecordWrapper` → 官方 `_planner_classes` / `_execute_tasks`（vendor 的 `generate_dataset.py`）→ h5 / mp4。
3. **逐局落盘**：runner 每完成一局就追加一行 `results.partial.jsonl` 并 `fsync`；`--resume` 跳过其中已完成的身份。中断恢复只跑没完成的局，不重复消耗预算。
4. **回写**（continue 模式，全部批次结束后一次）：
   - 在 `<specs>.lock` 上 `O_EXCL` 取锁，锁文件记 pid、host、启动时间；锁已存在一律拒绝并交用户，不自动判陈旧。
   - 重读 `--specs`，**整份文件 sha256 必须等于第 1 步**，否则中止，防止两个不同 `--output` 的进程互相覆盖。
   - 只改 `selected`、`tried`、`rollout`；临时文件 + `os.replace`；写后再 `load_specs` 核对 `identity_sha256` 未变，并重算 `delivery_sha256`。

**递补闭合点**：评估侧只取 `selected && rollout.status=="ok"` 的行，而每格恰好 3 行由 builder 断言保证。

### 5.3 jsonl 结构（`schema="hard-specs/2"`）

```json
{"task": "BinFill", "tier": "xhard3", "candidate": 3, "episode": 3, "seed": 12400300, "attempt": 0,
 "selected": true, "tried": true, "initial_selected": true, "spec": {…}, "spec_sha256": "…",
 "rollout": {"status": "ok", "h5_sha256": "…", "bytes": 806055656, "frames": 412, "round": 0,
             "env_package": "robomme", "code_baseline": "ca32e9b7058ac1744be55cc6841c3ec66814a184",
             "source": "s4-relaunch-02/final-delivery.json", "written_at": "…"}}
```

一行分成「签」和「结果」两段：

```text
  ├── 签（第一阶段封存，identity_sha256 覆盖，定死）──────┤├── 结果（第二阶段回写，不进 identity）──────────┤
  task tier candidate episode seed attempt spec spec_sha256   selected tried initial_selected rollout{…}
```

- **header 键**：`schema`、`difficulty`、`tasks`、`per_env`、`runtime`、`seed_rule`、`select_rule`、`sampling_config`（全文）、`sampling_config_sha256`、`recovery_rule`、`identity_source`、`run_id`、`draw_stats`（从 v6-02 四份 `drafts.jsonl` 重建：attempted 合计 153/152/166/220 = 691）、`drafts_sha256`（保留）、`legacy_identity_sha256`（v6-02 原值，顶层键）、`provenance`{`base_fingerprint`, `hard_fingerprint`, `env_package`}、`identity_sha256`、`delivery_sha256`。行判别符 `record` 仍是字符串 `"header"`／`"spec"`。
- **`identity_sha256`**：只盖 header 里的规格键（`schema difficulty tasks per_env runtime seed_rule select_rule sampling_config_sha256 recovery_rule identity_source`），加上每行 `{task, tier, candidate, episode, seed, attempt, spec_sha256}`。`provenance`、`draw_stats`、`run_id`、结果段都不进。
- **`delivery_sha256`**：盖排序后的 `[(task, tier, candidate, seed, spec_sha256, rollout.h5_sha256)]`，只取 `selected && rollout.status=="ok"` 的行，锁住「哪几局是正式交付」。只交换两行的 `selected`，它就会变。
- **迁移（阶段 1）**：以 `final-delivery.json::successes` 为唯一来源逐身份回填。
  - `candidate ← episode`；`difficulty → tier`。
  - 165 条成功局：`selected=true`，`rollout.status="ok"`，写 `h5_sha256`、`bytes`、`frames`、`round`，来源如实写 `env_package="robomme"`、`code_baseline=ca32e9b`。
  - InsertPeg@xhard4 的原选中局 ep0、ep3 失败，ep1 触发 FailsafeTimeout：这三行写 `status="failed"`、`selected=false`、`tried=true`；ep2、ep4 是递补成功的局（round 2/3）。
  - 其余原选中行 `initial_selected=true`。

### 5.4 三侧对拍：A40@greatlakes、16 worker、行为一致判定，h5 持久化到 bucket

**为什么不做字节级（U-1）**：
- 仓库自己的实测（`docs/validation/newtask-v3/20260921-worker-nondeterminism.md`、V3 步 5d）：mplib RRT 规划器有墙钟预算 `planning_time=1` 秒，1 秒内的迭代次数取决于 CPU 当时的负载。
  - 4 worker 并发时，同一身份重跑有 3064 处字段不同；
  - 单 worker 跨节点也会分叉：PickHighlight/ep3 在 gl1517 上 647 帧、在 gl1508 上 641 帧；
  - 只有「单 worker、同一次运行内」可以逐位复现。
- 原计划「16 worker 共卡、三侧分在不同节点、整文件 sha 全等」必然会出现与拆包无关的 FAIL。原计划引用的「sha 与 worker 数无关」是反着引的。
- 用户裁决维持 16 worker，把所有边降级为行为一致判定，sha 只作参考。

**三侧定义**：

| 侧 | 代码 | 原三档 16 × 3 × 3 = 144 | xhard 13×3×3 + 16×3 = 165 |
|---|---|---|---|
| O 官方 | 编排：vendor 的 `d53f21a7` 四文件；环境源码：GL 克隆上 `git worktree` 检出的 `1fadc0ec`（`--src-root`）；走官方 `_worker` | A40 现跑 → bucket `O-1fadc0e-a40/native/` | 无 |
| P 修改前 | 同一编排；`--src-root` = tag `pre-hard-split` 的 worktree；走官方 `_worker` | A40 现跑 → bucket `P-7c7118f-a40/native/` | **复用 S4 交付存档** → bucket `P-ca32e9b-s4/xhard/`（manifest 如实写 `code_baseline=ca32e9b`、`workers=16`、驱动：gl1517／gl1510 以当日探针佐证，gl1526 那一批 78 局写 `unknown`） |
| H 修改后 | 拆包后 HEAD；`--force-mirror` + `ROBOMME_ENV_PACKAGE=robomme_hard` 走镜像 worker | A40 现跑 → bucket `H-<sha7>-a40/native/` | `generate_h5.py --mode replay --identities <S4 交付 165 身份>` → bucket `H-<sha7>-a40/xhard/` |

**身份清单**：原三档用 `scripts/configs/newtask-v3/subset_manifest.json`（`rows_total=144`、`per_cell=3`、`source_ref=d53f21a7`，sha256 `035d3405…`），三侧 generate 与 compare 都显式传它，它的 sha 写进三侧 manifest。xhard 用 `final-delivery.json::successes`。

**对拍矩阵**：

```text
原三档（tier=native，16 任务 × 3 档 × 3 局 = 144）
   O ──PARITY_O_P──▶ P      修改前 ≡ 官方（行为）
   P ──PARITY_P_H──▶ H      拆包不改原三档（行为；同时含官方 _worker → 镜像 worker 的差异，见盲区）
   O ──PARITY_O_H──▶ H      端到端
xhard（tier=xhard，xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165）
   P(S4) ──PARITY_P_H──▶ H  拆包不改 xhard（行为）
```

**compare 怎么比**：每侧旁写 `identities.jsonl`，每身份一行 `{task, tier, episode, seed, path, bytes, sha256, success, frames, env_module, wrapper_modules, worker}`。按身份键对齐后分两层：

1. **判定层（全等才 PASS）**：
   - 身份集合与清单全等；
   - 两侧 h5 都非空、可打开；
   - `setup` 相等：`seed`、`difficulty`、`task_goal`、`available_multi_choices`、相机内参；
   - 结构相等：`setup` 与每个 `timestep_*` 组的数据集名与 dtype 集合相同，不比帧数；
   - 任务成功相等：h5 只在 `episode_success` 为真时落盘，所以用 `results` 的状态加 h5 是否存在来判，不用末帧 `is_completed`，它只是子目标进度；
   - 各侧 `env_module` 归属正确，即 `ENV_PACKAGE_BINDING`。
2. **参考层（INFO）**：
   - `sha_equal` 计数；
   - 帧数相等计数与最大帧差；
   - 首个分叉时间步的分布；
   - 共同前缀上 `joint_action` 的最大绝对差。

**bucket 持久化**（`HongzeFu/robomme-hard-parity`，U-4 取 A）：
- **流转**：
  1. 节点 `/tmp` 生成；
  2. 每局完成即 `sha256sum` 并 rsync 到 NFS 暂存 `<NFS>/hs-stage/<side>-<tier>/`；
  3. sled-vail 上的拉取进程逐局拉回 `/data/.../artifacts/newtask-v6/hard-split/h5/<side>-<tier>/`，重算 sha 一致后删掉该局 NFS 副本。NFS 上只有在途的局。
- **上传**：每片结束后，在 sled-vail 用 `uvx --from huggingface_hub==1.8.0 hf buckets sync` 从 `/data` 上传整片，连同 `identities.jsonl`、`SHA256SUMS`、`manifest.json`。manifest 记 `side, src_commit/orchestration_commit/tag/code_baseline, tier, gpu_model, driver, python/mani_skill/sapien/torch/cuda 版本, job_ids, nodes, workers, subset_manifest_sha256, generated_at`。
- **读回核对**：上传后逐对象从远端下载到临时目录，重算 sha256 与 `SHA256SUMS` 比对，比完即删临时副本，得出 `BUCKET_SYNC`。`hf buckets list -R` 的原始输出只作留档佐证，不代替读回核对。
- **收尾**：`/data` 上的 h5 在全部 compare 判定行产出后保留，删不删交用户决定；删时显式逐目录列出。

**跨硬件参考**（不进总判定）：`hard_regression.py xhw-reference` 只对现存 Ada 原三档产物 `artifacts/newtask-v6/v1/base`（16 × 3 × 3 = 144）与 A40 的 O 侧做同样两层比较，输出 `XHW_REFERENCE=INFO …`。xhard 没有 Ada 产物，不覆盖。

## 六、验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

### 6.1 对拍结果（正式判定，全部 A40@greatlakes）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 修改前 ≡ 官方（原三档，行为） | O 侧与 P 侧各 16 任务 × 3 档 × 3 局，`hard_parity.py compare --pair O:P --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json` | 拆包前的代码在 A40 上原三档与官方行为一致 | `PARITY_O_P=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 sha_equal=<k> shape=16x3x3` |
| 拆包不改原三档 | P 侧 vs H 侧同上 | `robomme_hard` 原三档 ≡ 修改前（行为） | `PARITY_P_H=PASS tier=native compared=144 … shape=16x3x3` |
| 端到端 | O 侧 vs H 侧同上 | `robomme_hard` 原三档 ≡ 官方（行为） | `PARITY_O_H=PASS tier=native compared=144 … shape=16x3x3` |
| 拆包不改 xhard | S4 交付（P）vs H 侧 replay，xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 | `robomme_hard` xhard 产物 ≡ 修改前交付（行为，含 `task_goal` 文本） | `PARITY_P_H=PASS tier=xhard compared=165 … shape=13x3x3+16x3` |
| 各侧实际加载的包 | 每局 `identities.jsonl` 的 `env_module`／`wrapper_modules` | H 侧真的跑了 `robomme_hard`，O／P 侧真的是 `robomme` | `ENV_PACKAGE_BINDING=PASS sides=3 O=robomme P=robomme H=robomme_hard mismatch=0` |
| 回注通道与评估文本 | 每档每任务取 candidate 最小的 ok 行 1 条（13×3 + 16 = 55），**经 builder 评估链** `make_env_for_episode` + reset；导出 spec 与冻结值逐字段比，`info["task_goal"]`、多选项与 S4 h5 `setup` 逐字比 | 新包下回注不漂，评估链拿到的是 hard 版语言目标 | `HARD_RESET_REPLAY=PASS resets=55 spec_mismatch=0 goal_mismatch=0 shape=13x3+16` |
| 三侧产物可复核 | 逐对象远端读回核对 sha | G7 | `BUCKET_SYNC=PASS sides=3 objects=<n> readback_sha_equal=<n> mismatch=0` |

- **FAIL 的读法**：
  - 判定层任一项不等时，`compare` 落 `compare/h5_pairs.jsonl`（逐身份差异项、首个分叉时间步）。
  - 只记证据链与候选修法，不放宽、不重试挑成功。
  - 先看差异是否落在 RRT 敏感身份上，并结合参考层判断是否属于墙钟非确定性；交用户裁决后才归因到驱动、编排或拆包。
  - `setup_equal` 或 `schema_equal` 不等基本不可能来自 RRT 噪声，优先查代码。

### 6.2 跨硬件参考（不进总判定）

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| Ada 原三档存档与 A40 O 侧行为一致程度 | `hard_regression.py xhw-reference`，两层比较同 §5.4 | `XHW_REFERENCE=INFO pairs=144 setup_equal=<n> success_equal=<n> sha_equal=<n> …` |

### 6.3 静态与结构判定（前置）

标 ★ 的导入类闸门在「官方态」下跑：阶段 1、2 期间用 `PYTHONPATH=<官方 1fadc0ec worktree>/src` 让 `robomme` 解析到官方树，阶段 3 之后直接跑。

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| `src/robomme` 逐字节同官方 | §3.4 守卫 | `UPSTREAM_BYTES=PASS …`（阶段 3 前为 `PENDING`） |
| vendor 四文件同源 | 与 `git show d53f21a7:scripts/data-generation/<f>` 及隔离树同名文件 `sha256sum` 比较 | `VENDOR_SAME=PASS files=4 orchestration_commit=d53f21a7` |
| ★ 导入落点无漏改 | AST 扫描相对与绝对导入 | `ABS_IMPORT=PASS files=44 unresolved=0` |
| ★ 借用闭包干净 | shim 目标传递依赖不含改过或新增的模块 | `BORROWED_DEPS=PASS shims=18 changed_hits=0` |
| ★ 注册表归属 | 三种导入顺序各起一个进程 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` |
| ★ 命名空间归属 | 16 个环境模块的全局可调用对象 | `NAMESPACE_OWNER=PASS envs=16 stray=0` |
| ★ 包装链同形 | 1 任务 × 4 个 action_space × `test`／`test-hard` 各 make 一个环境（不 reset），比较 wrapper 类名序列与所属包 | `WRAPPER_CHAIN=PASS action_spaces=4 chain_equal=4 hard_modules_ok=4` |
| 签不变 | 用 `git show 55f1b027:scripts/parity/v4_specs.py` 的原算法重算 legacy identity，逐位等于 v6-02 header 已提交值；新口径对迁移投影重算自洽 | `SPECS_IDENTITY=PASS tiers=4 rows=550 legacy_equal=4` |
| 正式交付集合就是 S4 那份 | 包内 `selected && ok` 行与 `final-delivery.json::successes` 逐身份比 `task/tier/candidate/seed/spec_sha256/h5_sha256`；每格恰好 3 行 | `DELIVERY_SET=PASS compared=165 equal=165 cells=55 shape=13x3x3+16x3` |
| 冻结逻辑等价 | 纯 CPU：新 `_freeze` 吃 v6-02 四份 `drafts.jsonl`，输出的候选、seed、spec、`initial_selected` 与 v6-02 逐行相同（不起环境） | `FREEZE_EQUIV=PASS tiers=4 rows=550 selected_equal=165` |
| 步数上限来源 | 统计 S4 165 局非演示执行步数 | `HARD_MAX_STEPS_SOURCE=PASS rows=165 max_exec=2215 cap=2658` |
| 冻结脚本未破 | `cmp` 三脚本；`ls -1 scripts/*.py \| wc -l` = 5 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 评估入口只差 3 处 | `diff scripts/evaluation.py scripts/evaluation_hard.py \| grep -c '^[<>]'` | `EVAL_HARD_DIFF=PASS lines=6` |
| 第一阶段只落一份文件 | 2 任务 × 1 档 × 1 候选、`--workers 2` smoke（本机）；前后用 `find -newer` 快照做差集 | `FREEZE_ONLY_JSONL=PASS files_written=1` |
| 回写不破坏封存 | 对 smoke jsonl 跑第二阶段 1 任务 × 1 档 × 1 局（本机） | `ROLLBACK_WRITE=PASS identity_unchanged=1` |
| 状态机 | 纯 CPU 夹具（不起仿真）：「失败 → 递补 → 中断 → 恢复」「两个不同 `--output` 争同一 specs」「锁已存在」「文件被他人改过」四个场景 | `STATE_MACHINE=PASS cases=4` |
| 原三档 A 路／镜像 worker 能起跑 | O 侧 A 路与 H 侧镜像各 1 任务 × 1 档 × 1 局（本机） | `NATIVE_SMOKE=PASS sides=2` |
| 合作者入口可用 | `hard_regression.py eval-smoke` 限 1 任务 × 1 档 × 1 局（本机） | `HARD_EVAL_SMOKE=PASS` |
| tests 可收集且不测错包 | `--collect-only` + 残留 `robomme.robomme_env` 引用清单 | `TESTS_COLLECT=PASS errors=0 stray_official=0` |

## 七、实施步骤表

| 阶段 | 内容 | 判据 | 改 `src/robomme` | commit |
|---|---|---|---|---|
| 0 准备（写文件、推 tag、建 bucket，不跑仿真） | fetch 官方两锚点并核 tree；生成 `UPSTREAM.json`；vendor 四文件 + `SOURCE.json`；导入全量扫描（相对 + 绝对 + 闭包）；打 tag `pre-hard-split` → `7c7118fa` 并 push；建 bucket（私有） | `VENDOR_SAME`；清单落 `docs/validation/newtask-v6/hard-split/stage0.md` | 否 | 12.205 |
| 1 建 `robomme_hard` | 按 §3.1 复制／shim／子类；jsonl 迁移与回填；train 元数据 `cp`（不 `mv`）；`pyproject.toml`；步数上限统计 | ★ `ABS_IMPORT`、★ `BORROWED_DEPS`、★ `REGISTRY_OWNER`、★ `NAMESPACE_OWNER`、★ `WRAPPER_CHAIN`、`SPECS_IDENTITY`、`DELIVERY_SET`、`HARD_MAX_STEPS_SOURCE`、单局 `make_env_for_episode` 冒烟（官方态） | 否（U-3 已批覆盖项） | 12.206 |
| 2 `scripts/` 重组 | 按 §3.5 与第二部分 1.3；先迁移符号与调用方，再删旧文件；`tests/` 三类处理 | `FREEZE_EQUIV`、`FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE`、`STATE_MACHINE`、`NATIVE_SMOKE`、`HARD_EVAL_SMOKE`、`EVAL_PY_UPSTREAM`、`EVAL_HARD_DIFF`、`TESTS_COLLECT`、`git grep -n 'v4_specs\|v4_rollout\|v5_generation\|scripts.eval' -- scripts src tests` 零命中 | 否 | 12.207 |
| 3 回退 `robomme` | 按固定 sha `1fadc0ec` 逐文件回退（清单逐文件批准，单独点名 `RecordWrapper.py` 5000→2000），删 9 个新增 utils，train 元数据回到 100 条 | `UPSTREAM_BYTES=PASS`；阶段 1、2 全部判定行在真实官方态下重跑仍 PASS（含本机冒烟，计入预算） | **是（P2 逐文件批准）** | 12.208 |
| 4 三侧对拍 | GL 克隆准备（脏改动交用户处置）→ 三个占位 job 分片 → NFS 中转回 `/data` → bucket 上传并读回 → compare 四条边 → 回注 reset 13×3 + 16 | `PARITY_O_P`、`PARITY_P_H`（native／xhard）、`PARITY_O_H`、`ENV_PACKAGE_BINDING`、`HARD_RESET_REPLAY`、`BUCKET_SYNC` | 否 | 12.209 |
| 5 留档 | `robomme_hard/README.md`、`scripts/README.md`、`parity/README.md`、`docs/validation/newtask-v6/hard-split/`、`AGENTS.md` P1 五入口（阶段 2 起即为五入口）、`CLAUDE.md` 核实清单 | `git diff --check` | 否 | 12.210 |

- 阶段 3 放在阶段 2 之后、阶段 4 之前：先让 `robomme_hard` 在官方态模拟下跑通，再回退 `robomme`；阶段 3 失败时只需回滚一个 commit。
- 实施完成后，实测结果以子节追加在本表之后，不改写原计划。

---

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 `src/robomme/**` 从阶段 3 起是官方 `1fadc0ec` 原样，不放任何自有文件（`UPSTREAM.json`、README 补充一律放 `robomme_hard/` 或 `docs/`）。
- R2 `scripts/parity/official/` 四文件不改；shim 不含逻辑（≤ 3 行非注释行，守卫检查）。
- R3 `identity_sha256` 与 `delivery_sha256` 的覆盖范围（第一部分 §5.3）落地后不变；要变就换 `schema` 版本，并重跑 `SPECS_IDENTITY`／`DELIVERY_SET`。
- R4 第二阶段回写只改 `selected`、`tried`、`rollout`；锁在 `<specs>.lock`；回写前整份文件 sha 必须与读入时相同；`--force` 覆盖 jsonl 起跑前 `ls -ld` 并在回复里复述目标路径。
- R5 同进程导入 `robomme_hard` 后 16 个 id 归它；需要官方行为另开进程；O／P 侧进程不得导入 `robomme_hard`。
- R6 reset／rollout 按 §3.1 预算逐项计数，冒烟与重跑都计入；接近上限先停再补授权（P3）。
- R7 `injection-dev` 目录名保留连字符、各入口按路径直跑并自行 `sys.path.insert`；若实测 import 混乱，回来请示改名，不自行改。
- R8 `tests/` 分三类处理（第二部分 1.3），不做整目录 sed；判据 `TESTS_COLLECT`；语义未验证的测试在留档里标「未验证语义」（E-10）。
- R9 commit 只 add 本阶段文件；阶段 4 起跑前 HEAD 冻结，结果以子节追加；他人在途改动一律不碰，以实施时的 `git status --short` 为准。
- R10 **P2**：阶段 1 的两项覆盖（16 个 id `override=True` 接管；builder 子类覆写 `__init__`／`_resolve_metadata_path`／`resolve_episode`／`get_episode_num`／`make_env_for_episode`）已由用户 2026-09-27 选「现在一次批准这两项」批准，实施后出 md 报告。阶段 3 对 `src/robomme/` 的回退另列「文件 / 改什么 / 为什么」清单逐文件批准，冻结文件 `RecordWrapper.py` 单列（`fail_safe_limit` 5000 → 官方 2000；`robomme_hard` 副本保留 5000，原三档成功局都在 2000 步内）。shim 借用与复制 `RecordWrapper.py` 不改变 `robomme` 自身行为，不属于覆盖。
- R11 对拍只在 A40@greatlakes 上生成；各侧 manifest 如实记录硬件与驱动，P 侧 xhard 复用存档的驱动不明部分写 `unknown`，不得伪造；Ada 产物不混入 `PARITY_*`。
- R12 三侧 generate 的 src 来源必须能追溯到 commit／tag：O = `1fadc0ec` worktree + vendor `SOURCE.json`（`d53f21a7`）；P = tag worktree（不改动、不 commit）；H = 拆包后 HEAD。不得用带在途改动的工作区起跑。
- R13 bucket 只增不改：同一侧目录已存在时 `publish` 拒绝覆盖；需要重传先请示，并另起目录名（如 `-r2`）。
- R14 局数一律写乘式（P5）。
- R15 GL 执行：
  - 每个生成步骤 `export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`；
  - 生成步骤运行期间不另起申请 GPU 的 srun（S4 事故：shared 短步骤结束时会把卡切回 Exclusive_Process，导致 Vulkan 建不了设备）；辅助 srun 一律 `--gres=none`；
  - GPU 型号与驱动的断言放进生成步骤脚本开头；
  - sha 与 rsync 在生成步骤内完成，不另起 srun。
- R16 本轮不执行任何完整抽签（§5.1）。

## 一、逐阶段、逐文件改动清单

### 1.1 阶段 0（写文件、推 tag、建 bucket，不跑仿真）

| 动作 | 命令 / 产物 | 判定 |
|---|---|---|
| 取官方两锚点 | `git fetch https://github.com/RoboMME/robomme_benchmark 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；`git rev-parse <sha>^{tree}` 分别等于 `3006988f…`、`1d4c1369…`，**不等即停**；`git diff --quiet 1fadc0ec d53f21a7 -- src/robomme` 退出码 0 | 记入 `stage0.md` |
| `UPSTREAM.json` | `robomme_files` 用 `git ls-tree -r 1fadc0ec -- src/robomme` 列文件，逐个 `git cat-file blob \| sha256sum`；`shims` 按第一部分 §3.1；`manifest_sha256` 按 §3.4 | 文件就绪 |
| vendor | `git show d53f21a7:scripts/data-generation/<f>` × 4 → `scripts/parity/official/scripts/data-generation/`；`SOURCE.json`{`url, orchestration_commit, tree, path, files{sha256}, vendored_at`}；与隔离树同名文件逐个 `cmp` | `VENDOR_SAME=PASS files=4` |
| 导入扫描 | AST 遍历 `src/robomme/**.py`：相对、绝对、星号导入全部解析；对候选借用模块求传递闭包；分 copy／shim 两列写 `stage0.md`；预期结果即第一部分 §3.1 | 清单落盘 |
| tag | `git tag pre-hard-split 7c7118fa` 并 `git push origin pre-hard-split`（阶段 0 获批即含本项） | `git ls-remote --tags origin pre-hard-split` |
| bucket | sled-vail：`uvx --from huggingface_hub==1.8.0 hf buckets create HongzeFu/robomme-hard-parity --private`，沿用本机已登录凭据，不新落 token 文件 | `hf buckets list HongzeFu` 原文落 `stage0.md` |

### 1.2 阶段 1：`src/robomme_hard/`

| 文件 | 来源 | 改什么 |
|---|---|---|
| `robomme_env/<Task>.py` × 16 | `cp src/robomme/robomme_env/<Task>.py` | `@register_env("<id>")` → `@register_env("<id>", override=True)`；按 §3.2 改绝对导入 |
| `robomme_env/__init__.py` | cp | 追加 `ENV_IDS = ("BinFill", …)` 16 元组，顺序同导入顺序 |
| `robomme_env/utils/` 改过 8 + 新增 9 + `subgoal_evaluate_func`、`task4recovery` + `__init__.py` | cp | 按 §3.2 改绝对导入：`subgoal_planner_func.py` 两处（按 AST 扫描结果逐条列出）、`vqa_options.py` 一处，`subgoal_evaluate_func.py` 的 `from robomme.robomme_env.utils import *` → `robomme_hard.` |
| `robomme_env/utils/<借用>.py` × 13 | 新写 | 三行 shim；`planner-ref.py`、`vqa_options copy.py` 不可 import，不建 |
| `logging_utils.py` | 新写 | shim → `robomme.logging_utils` |
| `env_record_wrapper/RecordWrapper.py` | cp | `step()` 内延迟导入 `from robomme.robomme_env.utils.vqa_options import …` → `robomme_hard.`；**不加任何 h5 attrs** |
| `env_record_wrapper/DemonstrationWrapper.py` | cp | 相对导入不动，已落在 `robomme_hard` 复制件上 |
| `env_record_wrapper/OraclePlannerDemonstrationWrapper.py` | cp | 顶部 `from robomme.robomme_env.utils.vqa_options` → `robomme_hard.` |
| `env_record_wrapper/{EndeffectorDemonstrationWrapper,FailAwareWrapper,MultiStepDemonstrationWrapper,episode_dataset_resolver}.py` | 新写 | shim × 4 |
| `env_record_wrapper/hard_specs.py` | 从 `scripts/parity/v4_specs.py` 下沉 | 搬 `HEADER_KEYS`、`canonical_json`、`digest`、`identity_sha256`（按 §5.3 口径）、`delivery_sha256`（新增）、`seed_rule_for`、`_known_seed_rule`、`seed_for`、`DIFFICULTY`、`load_specs`、`RUNTIME`；新增 `base_fingerprint()`／`hard_fingerprint()`、`HARD_MAX_STEPS = 2658`；指纹不符只 `warnings.warn`；`draw`/`freeze` 不搬 |
| `env_record_wrapper/hard_builder.py` | 新写 | 第一部分 §4.2：`_ALLOWED = {train,test,val,test-hard}`；覆写 `__init__`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode`（整段，包装链照官方、全部绝对导入 `robomme_hard` 的 wrapper）；每档每任务行数断言；`from_v4_specs` 保留为薄包装 |
| `env_record_wrapper/__init__.py` | 新写 | `from .RecordWrapper import *`、`from .DemonstrationWrapper import *`、`BenchmarkEnvBuilder`、`hard_specs`、`HARD_MAX_STEPS` + 借用 re-export |
| `__init__.py` | 新写 | 顺序：读 `UPSTREAM.json` → 检查官方是否已导入（warn）→ `from mani_skill import logger` 临时提到 ERROR → `from . import robomme_env` → `finally` 恢复 → 遍历 `ENV_IDS` 断言注册归属 → 命名空间归属断言 → shim cheap 校验（warn） |
| `env_metadata/test-hard/xhard{1..4}/specs.jsonl` | `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl` 迁移 | 第一部分 §5.3「迁移」：`candidate ← episode`、`difficulty → tier`、从 `final-delivery.json` 回填 `rollout`、对齐 `selected`、写 `tried`／`initial_selected`；header 从四份 `artifacts/newtask-v6/v6-02/xhard*/draft/drafts.jsonl` 重建 `draw_stats`，保留 `drafts_sha256`，`legacy_identity_sha256` 放顶层，`provenance` 块；`schema` → `hard-specs/2`；新口径重算 `identity_sha256`／`delivery_sha256` |
| `env_metadata/train/` 4 份 | **`cp`** 自 `src/robomme/env_metadata/train/`（阶段 3 才把 `robomme` 侧恢复为官方 100 条） | 不改 |
| `UPSTREAM.json`、`README.md` | 阶段 0 产物 / 阶段 5 写 | — |
| `pyproject.toml` | 现有 | `packages = ["src/robomme", "src/robomme_hard"]`；确认 wheel 带上包数据（`specs.jsonl`、`UPSTREAM.json`、train 元数据） |
| 统计脚本 | scratchpad 或 `artifacts/` 临时脚本，不进 `scripts/` 顶层 | `HARD_MAX_STEPS_SOURCE` 命令与输出进 `stage1.md` |

### 1.3 阶段 2：`scripts/`

**先迁移、后删除**：下表「删除」一行最后执行，执行前跑完 `git grep` 零命中闸门。

| 文件 | 来源 | 改什么 |
|---|---|---|
| `injection-dev/_extract.py` | 新写 | 调用 `train_split_config.extract_task(task, pkg=…)`；`build_sampling(tasks, pkg="robomme_hard", release="newtask-v6") -> dict` |
| `injection-dev/_draw.py` | `parity/v4_specs.py` 抽签部分 | `_draw_one`、`draw_task`、`_draw_worker_init(pkg)`、`_parse_gpus`、`parse_task_max_reset_attempts`、`env_kwargs`、`recovery_mode`；`seed_for` 改从 `hard_specs` 导入；输入是 sampling dict，不读文件；返回 rows + `draw_stats`；worker 初始化后断言注册归属 |
| `injection-dev/_freeze.py` | `parity/v4_specs.py` 封存部分 | `cmd_freeze` 改成纯函数 `freeze(rows, header_parts) -> (header, rows)`，保留完整选签函数（含 MoveCube 分层）与 `reselect` 语义；哈希用 `hard_specs`；首次落盘排他写 `_write_jsonl`（`os.link`）一并搬来 |
| `injection-dev/freeze_specs.py` | 新写 | CLI（第一部分 §5.1）；串 ①②③；`--pkg`（默认 `robomme_hard`）；`--dry-run`；`--self-check` |
| `injection-dev/_rollout.py` | `parity/v4_rollout.py` | `_run_batch` 的 runner 命令带 `ROBOMME_ENV_PACKAGE`；输入改为 jsonl 行；`--mode continue/replay`；状态机与 `write_back`（第一部分 §5.2）；`<specs>.lock` |
| `injection-dev/generate_h5.py` | 新写 | CLI（§5.2）；`--mode`、`--identities`、`--redo`、`--resume`；调 `_rollout` |
| `injection-dev/_report.py` | `parity/v5_generation.py` 报告部分 | 输入改为 jsonl `rollout` 块 + `results.jsonl`；去掉 drafts 依赖；计数字段显式输出零值（P4 教训）；输出 `HARD_GENERATION=REPORT …` |
| `injection-dev/site/` | `git mv parity/{v6_site.py,v6_site.html,v6_site_catalog.py,v6_candidate_values.py,v6_tier_monotone.py,v6_v0_native_definitions.py,v6_gt_lengths.py,v6_gt_lengths.json}` | 内部导入路径随之改；`v6_candidate_values` 依赖的 `_read_jsonl`、`_check_sources` 搬进 `site/_io.py`；`DEFAULT_CONFIG` 改读包内 jsonl header 的 `sampling_config` |
| `parity/train_split_config.py` | 现有 | `extract_task(task, pkg="robomme")` 包名参数化，默认值不变，S0 语义保持 |
| `parity/train_split_worker.py` | 现有 | `pkg = os.environ.get("ROBOMME_ENV_PACKAGE", "robomme")`，所有 `import robomme…`（含 `FailsafeTimeout`）改成 `importlib.import_module(f"{pkg}…")`；每局在结果里写 `env_module`（`REGISTERED_ENVS[task].cls.__module__`）与 `wrapper_modules` |
| `parity/train_split_runner.py` | 现有 | `--official-root` 默认 `scripts/parity/official`；`.official_tree` 校验改读 `official/SOURCE.json["tree"]`；新增 `--metadata-root`（默认 `scripts/configs/newtask-v3/official_train`，核 sha），显式传给 `read_train_metadata(metadata_root)`；`--src-root` 在 vendor 默认下必填；formula 分支的 `from scripts.parity.v4_specs import …` 改为在分支内延迟 `from robomme_hard.env_record_wrapper.hard_specs import DIFFICULTY, _known_seed_rule, seed_for`；透传 `ROBOMME_ENV_PACKAGE`；逐局追加 `results.partial.jsonl` 并 fsync，`--resume` |
| `parity/hard_parity.py` | 现有，重构为三侧入口 | 见下方三个子命令；运行前断言 `nvidia-smi` 型号 = A40、驱动与 manifest 所记一致，否则拒跑；子进程环境沿用现有 `child_env()` 的 `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1` |
| `parity/upstream_guard.py` | 新写 | 第一部分 §3.4；`--manifest-md` 输出 README ③表；阶段 3 前输出 `PENDING` |
| `parity/hard_regression.py` | 新写 | `reset-replay`（13×3 + 16 = 55 次，经 `hard_builder.make_env_for_episode` + reset，比对 `SpecRecorder` 导出、`task_goal`、多选项与 S4 h5 `setup`；`SpecRecorder` 本体在 `robomme_hard.robomme_env.utils.episode_spec`，不再依赖 `v4_eval._binding`）；`eval-smoke`（本机 1 任务 × 1 档 × 1 局）；`xhw-reference`（§6.2） |
| `evaluation_hard.py` | `cp scripts/evaluation.py` | import 行、`dataset="test-hard"`、`max_steps=HARD_MAX_STEPS` 三处（第一部分 §4.3） |
| 删除（最后执行） | `git rm` `parity/{v4_specs,v4_rollout,v5_generation,legacy_keep_list}.py`、`parity/{identities_16x3.txt,manifest_16x3.json}`、`scripts/eval/`、`configs/newtask-v4/`、`configs/newtask-v5/`、`configs/newtask-v6/{sampling_config.json,v6-01/}`；`rm -r` 未跟踪 `scripts/injection/`（先列清单）；`parity/results/`（被 ignore，内有 aspen 16x3 的 `run.log`、`B.log`）**本方案不删**，列清单交用户 | `ls -1 scripts/*.py` = 5；`git grep` 零命中 |
| `tests/**` | 现有 | 分三类逐文件列清单：① 模块级导入已删／已搬脚本（8 个文件、共 30 处）→ 改路径或删除该测试；② 子模块路径导入 wrapper → 改包级导入，或靠 4 个 wrapper shim 解析；③ `importlib.import_module("robomme.robomme_env.<Task>")` 字符串导入（34 处）与按路径读文件 → 逐条决定测 `robomme_hard` 还是有意测官方，有意测官方的加注释；不做整目录 sed |

`hard_parity.py` 三个子命令：

- **`generate --side {O,P,H} --tier {native,xhard} --manifest <清单> --workers 16 --gpu 0 --out <节点 /tmp>`**：
  - O 侧：`--official-root scripts/parity/official --src-root <1fadc0ec worktree>`；
  - P 侧：`--src-root <tag worktree>`；
  - H 侧：`--force-mirror` + `ROBOMME_ENV_PACKAGE=robomme_hard`；
  - xhard 走 `injection-dev/generate_h5.py --mode replay --identities <S4 交付>`；
  - 每局写 `identities.jsonl` 行，完成即 sha + rsync 到 NFS 暂存。
- **`publish --side … --bucket HongzeFu/robomme-hard-parity`**：在 sled-vail 上跑，从 `/data` 上传，写 `SHA256SUMS`、`manifest.json`，逐对象读回核对。
- **`compare --pair {O:P,P:H,O:H} --tier … --manifest <清单>`**：按身份键对齐后做判定层与参考层（第一部分 §5.4），落 `compare/h5_pairs.jsonl`。

### 1.4 阶段 3：`src/robomme/`（P2）

1. **出清单交批**：`git diff --name-status 1fadc0ec HEAD -- src/robomme`，预期 30 M + 9 A：
   - 30 M = 16 个环境 + 8 个 utils + `RecordWrapper.py` + `episode_config_resolver.py` + 4 个 train json；
   - 9 A = 新增 utils。
   - 清单中单列 `RecordWrapper.py` 的改动内容与理由。
2. **批准后执行**：对批准的文件逐个 `git checkout 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 -- <文件>`（固定 sha，不用会变的 `FETCH_HEAD`，不整树 checkout），再 `git rm` 9 个新增 utils。
3. **提交前核对**：`git status --short -- src/robomme` 与清单逐项对上才 commit。

## 二、闸门总表

判定行见第一部分 §六，此处只补实现位置：

| 判定 | 实现位置 |
|---|---|
| `UPSTREAM_BYTES`、`VENDOR_SAME`、`ABS_IMPORT`、`BORROWED_DEPS` | `upstream_guard.py` |
| `REGISTRY_OWNER`、`NAMESPACE_OWNER` | `tests/lightweight/test_registry_owner.py`（三种导入顺序各用 `subprocess` 起一个进程） |
| `WRAPPER_CHAIN` | `tests/lightweight/test_wrapper_chain.py`（需要 GPU，标 `gpu`） |
| `SPECS_IDENTITY`、`DELIVERY_SET`、`FREEZE_EQUIV`、`HARD_MAX_STEPS_SOURCE` | 阶段 1、2 一次性核对脚本，命令与输出进 `stage1.md`／`stage2.md` |
| `FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE` | `injection-dev` 入口的 `--self-check` |
| `STATE_MACHINE` | `tests/lightweight/test_hard_state_machine.py`（纯 CPU 夹具） |
| `NATIVE_SMOKE`、`PARITY_*`、`ENV_PACKAGE_BINDING`、`BUCKET_SYNC`、`REPLAY_SET` | `hard_parity.py` |
| `HARD_RESET_REPLAY`、`HARD_EVAL_SMOKE`、`XHW_REFERENCE` | `hard_regression.py` |
| `TESTS_COLLECT` | `pytest --collect-only` + `git grep` 残留清单 |

★ 类闸门在阶段 1、2 用 `PYTHONPATH=<1fadc0ec worktree>/src` 模拟官方态运行。

## 三、预算与 runbook

### 3.1 预算（P3：实施前一次性向用户申请；全部按乘式；reset 与 rollout 分别计上限，轨迹内 reset 不另计）

| 项 | 乘式 | rollout 上限 | reset 上限 | worker | 硬件 |
|---|---|---|---|---|---|
| 阶段 1 单局 `make_env_for_episode` 冒烟（官方态） | 1 任务 × 1 档 × 1 局 | 0 | 1 | 1 | 本机 Ada |
| `WRAPPER_CHAIN` | 1 任务 × 4 action_space × 2 dataset，只 make 不 reset | 0 | 0 | 1 | 本机 Ada |
| `FREEZE_ONLY_JSONL` smoke | 2 任务 × 1 档（xhard1）× 1 候选，`--max-reset-attempts 5` | 0 | 2 × 5 = 10 | 2 | 本机 Ada |
| `ROLLBACK_WRITE` smoke | 1 任务 × 1 档 × 1 局 | 1 | 0 | 1 | 本机 Ada |
| `NATIVE_SMOKE` | 1 任务 × 1 档 × 1 局 × 2 侧（O A 路、H 镜像） | 2 | 0 | 1 | 本机 Ada |
| `HARD_EVAL_SMOKE` | 1 × 1 × 1 | 1 | 0 | 1 | 本机 Ada |
| 阶段 3 后重跑以上五项 | 同上 | 1 + 2 + 1 = 4 | 1 + 10 = 11 | 同上 | 本机 Ada |
| O 侧原三档 | 16 任务 × 3 档 × 3 局 | 144 | 0 | 16 | A40 |
| P 侧原三档 | 16 × 3 × 3 | 144 | 0 | 16 | A40 |
| H 侧原三档 | 16 × 3 × 3 | 144 | 0 | 16 | A40 |
| H 侧 xhard（按 S4 交付身份重放，不递补） | 13 × 3 × 3 + 16 × 3 | 165 | 0 | 16 | A40 |
| 基础设施重跑上限 | 每身份最多 1 次，合计上限 | 30 | 0 | 16 | A40 |
| `HARD_RESET_REPLAY` | 13 × 3 + 16（经评估链，含演示回放） | 0 | 55 | 1 | A40 |
| **合计** | | **本机 8 + A40 597 + 基础设施重跑 30 = 最多 635** | **本机 22 + A40 55 = 最多 77** | | |

- **不另计的**：`STATE_MACHINE`、`FREEZE_EQUIV`、`SPECS_IDENTITY`、`DELIVERY_SET`、`HARD_MAX_STEPS_SOURCE`、`XHW_REFERENCE` 都不起仿真；P 侧 xhard 复用 S4 存档。
- **原 0926 计划 D 项授权的 V1′ 144 局**（Ada 侧 vs S0 基线）作废不跑。
- **停止条件**：
  - 任一冒烟判定 FAIL 即停；
  - 基础设施重跑用满 30 即停；
  - 任一占位 job 剩余不足 6 小时即停，交用户决定；
  - 判定层 FAIL 不停止其他分片，但不做任何重试挑成功。
- **预计耗时**：每片 16 worker 原三档约 30 分钟；xhard 165 局约 30～60 分钟（relaunch-02 实测 16 worker 下 39 局 210～329 s、48 局 392 s）；回注 55 次在 H 原三档之后串行。
- **授权方式**：实施前把本表原样交用户，取得一次明确批准；没有批准不得起跑，不以代理复述数字代替授权。

### 3.2 GL 分片 runbook（阶段 4）

**前置**：

1. 三个 `hs-hold` job 存活，且剩余 ≥ 6 小时（`squeue -u hongzefu -o '%i %L'`）；任一到期即停下交用户，不自行 sbatch。
2. **GL 克隆准备**：克隆当前在 `1bb4190`，有 93 处脏改动（76 M，blob 等于 `ca32e9b`，是早先同步留下的；17 ??）。先把 `git status --short` 原文与 blob 比对结果交用户处置，不 stash、不 checkout 覆盖；获准后经 NFS 从本机 fetch 拆包后 HEAD 与 tag，再切到 HEAD，并 `git worktree add <NFS>/hs-p-side pre-hard-split`、`git worktree add <NFS>/hs-o-side 1fadc0ec…`。
3. `.venv` 的 editable `.pth` 是纯路径条目，`src/robomme_hard` 自动可导入；在计算节点上用 `uv run --frozen --no-sync python -c "import robomme_hard"` 核对，不在计算节点装依赖。
4. `df` 断言：节点 `/tmp` ≥ 160 GB；NFS 暂存余量 ≥ 100 GB（在途最多 16 worker × 约 1.5 GB × 3 片）；`/data` ≥ 400 GB。

**容量**（实测均值）：原三档约 349 MB／局 × 144 ≈ 50 GB／侧；xhard 约 706 MB／局 × 165 ≈ 116 GB。本轮新生成 3 × 50 + 116 ≈ 267 GB 落 `/data`；bucket 另加 P 侧 xhard 存档 116 GB，合计约 383 GB。

**启动方式**：每片在 GL 登录节点起 detached tmux，会话 `hs-<side>-<tier>`，记下登录节点主机名；会话内执行 `srun --jobid=<id> --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash <片脚本>`，片脚本自己 `tee` 日志到 NFS `<NFS>/hs-logs/<side>-<tier>.log`。本机 Monitor 直接 tail NFS 上的日志，一份日志一个 Monitor，所以 ssh 掉线不影响分片。sled-vail 上另起 tmux `hs-pull` 跑逐局拉取进程。

| job | 节点 | 片（同一 job 内的两段写进同一个片脚本，逐段写 `EXIT_CODE=`） |
|---|---|---|
| 62126060 | gl1517 | O 原三档 16×3×3 → H xhard 13×3×3 + 16×3（replay） |
| 62126061 | gl1504 | P 原三档 16×3×3 |
| 62126062 | gl1506 | H 原三档 16×3×3 → 回注 reset 13×3 + 16 = 55 |

- **片脚本固定动作**：
  - 开头：断言 GPU 型号与驱动，`export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`；
  - 每局：`sha256sum` 追加 `SHA256SUMS`，rsync 到 NFS 暂存，删掉节点 `/tmp` 副本；
  - 片结束：写 `EXIT_CODE=`。
- **接续夹具**：跑之前先用不起仿真的夹具验证「第一段完成 → 读真实格式报告 → 第二段」与「第一段失败 → 停止」（P4）。
- **Monitor 过滤词**：`NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|EXIT_CODE=|Traceback|=PASS|=FAIL|RUNNER_DONE`。

四片跑完并拉回 `/data` 后，在本机执行：

```bash
uv run --no-sync python -m scripts.parity.hard_parity publish --side O --tier native
uv run --no-sync python -m scripts.parity.hard_parity publish --side P --tier native
uv run --no-sync python -m scripts.parity.hard_parity publish --side H --tier native
uv run --no-sync python -m scripts.parity.hard_parity publish --side H --tier xhard
uv run --no-sync python -m scripts.parity.hard_parity publish --side P --tier xhard   # S4 存档，manifest 记 ca32e9b
uv run --no-sync python -m scripts.parity.hard_parity compare --pair O:P --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python -m scripts.parity.hard_parity compare --pair P:H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python -m scripts.parity.hard_parity compare --pair O:H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python -m scripts.parity.hard_parity compare --pair P:H --tier xhard  --manifest artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json
```

- **产物去向**：bucket 是权威归档；NFS 暂存逐局即删，片结束后确认目录为空再 `rmdir`；`/data` 上的 h5 保留到用户决定。
- **tmux 会话清单**：本机 `hs-pull`，GL 登录节点三个 `hs-*`，写进 `stage4.md`；清理时按清单逐个 `kill-session -t '=名'`。
- **FAIL 处置**：只记证据链与候选修法，不放宽、不重试挑成功；基础设施失败按 §3.1 上限重跑，先停对应会话、核对没有残留 worker，按 `results.partial.jsonl` 续跑。

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | RRT 墙钟非确定性让判定层（任务成功）在个别身份上不等 | 已降级为行为判定（U-1）；成功不等仍判 FAIL，交用户裁决；参考层帮助判断是否属于噪声 |
| 2 | shim 借用触发官方 16 环境注册，日志 16 条 `Override registered env` | 接受；只在自家注册段用 logger 对象临时压低 |
| 3 | 官方 `main` 前进，借用文件变化悄悄改 xhard 行为 | 双锚点钉 commit，守卫 FAIL 即停；升级是显式动作，要重跑全部闸门 |
| 4 | 父类 `__init__` 白名单绕行在官方改签名时断裂 | 属于风险 3 的升级流程 |
| 5 | 新增的复制件或官方改动让借用闭包变脏 | `BORROWED_DEPS` 与 `NAMESPACE_OWNER` 在官方态下跑 |
| 6 | 两个 `generate_h5.py` 同时回写同一 jsonl | `<specs>.lock` + 整份文件 sha 比对 + `STATE_MACHINE` 夹具 |
| 7 | `tests/` 替换后假 PASS／假 FAIL | R8 三类处理 + 残留清单 |
| 8 | 连字符目录名与 `-m` 不兼容 | R7 |
| 9 | GL 驱动升级后参考层数字漂移 | manifest 记驱动；判定层不依赖字节 |
| 10 | `O↔P` 判定层 FAIL | 不是拆包问题；先用 `compare/h5_pairs.jsonl` 定位，查编排、src 或 RRT 噪声，交用户裁决后再看 `P↔H` |
| 11 | 16 worker 共卡时 `svulkan2`／`EXCLUSIVE` 建设备失败 | `--gpu_cmode=shared` 写死；R15 不另起 GPU srun；Monitor 过滤词覆盖 |
| 12 | 登录节点重启导致远端 tmux 丢失 | 片脚本在 srun 步骤内独立运行；日志在 NFS；按 `results.partial.jsonl` 续跑 |
| 13 | bucket 上传或读回中断 | `publish` 可重入（只补缺对象）；只增不改（R13） |
| 14 | `P↔H` native 同时含官方 `_worker` 与镜像 worker 的差异 | 列入盲区；判定层 FAIL 时先对比同侧两种 worker 再归因 |

## 五、盲区诚实清单

- **①（已查清，关闭）**：官方 builder 只有 `__init__`、`get_task_list`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode` 六个成员；`evaluation.py` 只用其中四个；`self.dataset` 只在 `_resolve_metadata_path` 里用；`resolve_episode` 返回二元组。
- **②（已查清，关闭）**：`MultiStepDemonstrationWrapper` 只依赖闭包干净的 utils；真正的问题在 `DemonstrationWrapper`，已改为复制。
- **③**：官方 `_worker`（O／P 侧）与镜像 worker（H 侧）在 A40 原三档上是否行为一致，没有直接证据；`P↔H` native 的差异可能混有 worker 差异。
- **④（已查清，关闭）**：v6-02 四份 `drafts.jsonl` 都在，sha 与 header 一致，`draw_stats` 可以精确重建。
- **⑤**：A40 与 Ada／A6000 分叉的根因（驱动 595 vs 570、PhysX GPU 内核、渲染器）没有拆分；判定层不依赖字节，影响有限。
- **⑥**：P 侧 xhard 存档在 gl1526 上生成的 78 局（xhard1/2），驱动版本无记录。
- **⑦（已查清，关闭）**：`final-delivery.json` 记录了全部 165 局 h5 的 sha256 与字节数，文件都在 `/data`，`code_baseline=ca32e9b`，含 2 局递补（InsertPeg@xhard4 ep2、ep4）。
- **⑧**：`HARD_RESET_REPLAY` 经评估链时会回放演示，单次耗时未实测。

## 六、留档与 commit 纪律

- 每阶段一个 commit（12.205～12.210），subject 接体例，body 按 `AGENTS.md` 第 11 条六项；只 `git add` 本阶段文件。
- 判定行原文与命令进 `docs/validation/newtask-v6/hard-split/stage<n>.md`；阶段 1 另出 P2 覆盖项 md 报告（U-3「改完出报告」）；阶段 4 的 reset／rollout 逐项计数表进 `stage4.md`。
- 实施完成后，实测结果以子节追加在第一部分 §七步骤表之后，不改写原计划。
- `robomme_hard/README.md` 必含：
  - ① 一句话说明，以及三条 `PARITY_*`（native）+ 一条 `PARITY_P_H`（xhard）判定行原文，注明是行为一致判定；
  - ② 四档定稿表（从 `0925-newtask-release-v6-plan.md` 第一部分 §三逐字搬）；
  - ③ 复制／借用／子类／新增逐文件表（`upstream_guard.py --manifest-md` 生成）；
  - ④ 机制：`sampling_config` 两块、`SpecRecorder` 导出与回注、jsonl 签与结果两段及两个哈希、seed 偏移、注册表与命名空间归属、借用闭包规则；
  - ⑤ 使用：`dataset="test-hard"` 三行示例与 `test` 的对应关系（每任务 12 或 3 局、档序、候选序）、`HARD_MAX_STEPS=2658` 的来源、`resolve_episode` 取 tier、`override_metadata_path`、两阶段生产命令（注明不随包分发）；
  - ⑥ 红线 R1～R5、R11；
  - ⑦ `dataset_for_parent="test"` 绕行说明。
