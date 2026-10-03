# 噪声基线与改码回归闸门计划（2026-10-03）

> **本文件的地位**：这是「把生成两次的噪声、评估重复的噪声到底有多大定下来，并写成以后可调阅的文档」这件事的唯一计划。只规划、不实施；第二部分的预算表与子代理分配表须经用户批准后才执行，批准前不改代码、不提交作业、不启动任何生成或评估。
>
> **锚点**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，规划依据 `6a8c1368`（12.350）。提交编号沿用 `12.<小版本>`。现有 `third_party/SimpleMemVLA` 的在途改动不动。
>
> **用户原话（2026-10-03，语音转写，按时间顺序）**：
> 1. 「之前我用户没有再去管生成和对拍时候的一致性或者说一致性检验现在看来还是不行就是我可能后面还会修改代码我需要保证修改后和修改前生成和valuation的时候噪声和以前是一样的在原来的噪声范围内」
> 2. 「写一个根目录文件确定下来与的这个噪声到底有多大就是生成两次然后EVUation的噪声有多大」
> 3. 「有一个根目录计划计划。」
> 4. 「就是我要写一个计划来确定下来这些东西然后把它写在文档里以后调阅」
>
> **与其他文件的关系**：生成侧已有事实见 [`docs/1003-generation-parity-reproducibility.md`](docs/1003-generation-parity-reproducibility.md)（数据集已冻结、现行容差不改）；评估侧已有事实见 `docs/validation/v7.5eval/`；未定事项 A1～A5 见 [`docs/1002-pending-decisions.md`](docs/1002-pending-decisions.md)。根目录 [`1003-oracle-subgoal-groundsg-eval-plan.md`](1003-oracle-subgoal-groundsg-eval-plan.md) 管的是两组 GroundSG 新模型的接入与「原 hard 入口完全一致」，本计划管的是现有两模型（SimpleMemVLA、MME-VLA FrameSamp + Modulation）与生成链路的噪声基线，两者互不替代；新模型接入后按本计划的同一流程补测，不在本计划预算内。

# 第一部分（给人看）

## 一、总览

**一句话方案**：把「同一份代码、同一批身份重复跑」的差异量成一组冻结的整数阈值（噪声基线），写进一份长期文档和一个机器可读文件；以后每次改代码，先跑零噪声的逐字节层，再把改后结果与基线比，落在阈值内才算「没有改坏」。

**交付物（三件）**：

| 交付物 | 位置 | 作用 |
|---|---|---|
| 噪声基线文档 | `docs/1003-noise-baseline.md` | 以后调阅：每一层噪声多大、在什么条件下测的、阈值怎么来的、怎么用 |
| 冻结阈值文件 | `scripts/configs/noise-baseline.json` | 闸门脚本只从这里读整数阈值，文件自带 sha256 防改 |
| 固定闸门身份集与闸门脚本 | `scripts/configs/gate-set-v9-192.json`、`scripts/parity/noise_gate.py` | 测基线和以后每次回归都用同一批身份、同一个判定入口 |

**已定死口径**（依据见括号内小节）：

1. 噪声分三层，各层判据不同，不混用（第二节）。
2. 逐字节层（reset、开环打包）没有噪声，改码后任何差异都是回归，不设容差（第二节）。
3. 生成与 MME 闭环评估是真噪声层，判据只数「个数」：不可复现局数、成败翻转局数；不再使用动作／状态幅度容差（第三节；依据是 2250 局里不存在「有差但在幅度容差内」的局）。
4. 阈值在基线阶段一次算成整数并冻结，之后只做整数比较，不在回归时临时解释（第四节）。
5. 噪声只在固定条件下成立：GL A40、驱动 595.71.05、生成 4 worker／4 CPU、评估每席串行、确定性标志关；换 GPU 型号不可比（第三节实测：RTX 与 A40 之间 44/48 身份 reset 即有差）。
6. 交付的 800 局 h5、现行容差文件 `scripts/configs/hard-parity-tolerances.json`、`hard_parity.py` 判定逻辑都不动；`src/robomme/` 零改动。

## 二、噪声分哪几层、各层现在已知多大

下表全部来自已留档的实测，不需要新算力。「待测」的格子就是本计划要补的。

| 层 | 查什么 | 已知噪声 | 证据 |
|---|---|---|---|
| L0 环境 reset | 同一 seed、规格重置后的场景状态与观测 | **0**：同型号 GPU 内逐字节相同（`ENV_DIGEST_PARITY` C5:C6、C5:C7 48/48；`XHARD0_RESET_PARITY=PASS compared=192 det_diff=0`；`V8_RESET_REPLAY=PASS resets=43`） | `docs/validation/v7.5eval/env-parity.md`、`docs/validation/newtask-v9/records/gates.txt` |
| L1 生成（同一局生成两次） | 两份 h5 是否逐字节相同、成败是否翻转 | V9 交付 16 任务 × 50 局 = 800：不可复现 18 局（2.25%），成败翻转 1 局；V8 1070 局 1.12%；V7 1100 局 1.27%；V9 新增 80 局 10.0%。集中在 MoveCube 8.9%、InsertPeg 8.6%、BinFill 4.4%，另 8 个任务为 0。只有两种局：逐字节相同，或从某一步（最早第 63 步）起走另一条轨迹 | `docs/1003-generation-parity-reproducibility.md` |
| L1′ 生成噪声的性质 | 分叉是固定落在某些身份上，还是每次随机换一批；单 worker 是否就没有噪声 | **待测**。每批只有一次重复（H:H2），无法区分；根因留档指向 mplib RRT 的墙钟预算（`planning_time=1`）在多 worker 争抢下结果不同 | `docs/validation/newtask-v3/20260921-worker-nondeterminism.md` |
| L2 策略开环（同一输入重放） | 同一份录制输入下模型输出的动作 | SimpleMemVLA：**0**（16 次比较全部逐位）。MME：同一 server 内 0；跨 server 启动最大绝对差 0.0034～0.0096 | `docs/validation/v7.5eval/policy-replay.md` |
| L3 闭环评估，xhard0（16 任务 × 1 档 × 12 局 = 192） | 同一批局重复评估，逐局成败是否翻转 | SimpleMemVLA：**0 翻转**，三对官方重跑与正式跑法 192 局终态、步数全同（141/192）。MME：官方三对翻转 7、16、19 局（成功→失败／失败→成功为 4／3、9／7、10／9），成功数 50、49、48、51；V8 两入口 18 局状态不同 | `docs/validation/v7.5eval/official-rerun.md`、`prod-vs-official.md`；`docs/1002-pending-decisions.md` A3、A4 |
| L3′ 闭环评估，V9 test-hard（800 局） | 同上 | **待测**。两模型都只评过一遍（SimpleMemVLA 178/800，MME 39/800），没有任何重复 | `docs/validation/v9-two-policy-gl10-20261002-01/result.md` |

读法：L0、L2（SimpleMemVLA）、L3（SimpleMemVLA，xhard0）是零噪声层，可以当逐字节闸门；L1 与 MME 的 L3 是真噪声层，只能用「个数不超过基线」来判。

## 三、判据怎么定

**零噪声层（L0，SimpleMemVLA 的 L2／L3）**：改码前后必须全等。reset 层沿用现成判定行 `XHARD0_RESET_PARITY`（`scripts/parity/hard_regression.py::cmd_xhard0_reset_parity`）与 `V9_RESET_REPLAY`（同文件 `cmd_reset_replay`，43 格 × 1 次）；SimpleMemVLA 闭环要求闸门身份集上逐局终态与步数全同。⚠ SimpleMemVLA 的零翻转目前只在 xhard0 上证实过；V9 test-hard 上是否也为零是待测项，若实测有翻转，则改按下面的真噪声层处理。

**真噪声层（L1 生成，MME 的 L3）**：统计量只取个数。

- 生成：闸门身份集上「与交付 h5 不逐字节相同的局数」`K_gen`（整体与分任务）、「成败翻转局数」`F_gen`；另有一条结构硬线——身份、`setup`、文件结构必须相同且首次分叉步 > 0，否则直接 FAIL（沿用 `hard_parity.py::_classify_over` 的 noise／fail 划分）。
- 评估：闸门身份集上「成败翻转局数」`T_eval`（两个方向之和），以及配对检验 McNemar 的 p 值。⚠ 不再用「成功率差的点估计落在基线各对的最小最大值之间」：A3 的教训是三对基线的区间只有 1 局宽，正常波动也会判出界。

**阈值公式（写死，基线阶段由脚本算成整数）**：设基线里有 m 对重复比较，每对 n 局，第 i 对的个数为 x_i。合并比例 p̂ = Σx_i ÷ (m·n)；取其单侧 95% Clopper–Pearson 上界 p_U；阈值 K_max = 二项分布 Binomial(n, p_U) 的 99% 分位数，且不小于 max(x_i)。回归时个数 ≤ K_max 即在噪声内。MME 另加一条 McNemar p ≥ 0.05。

为什么这样能成立：阈值由「比例的不确定性」和「单次抽样的波动」两层保守量叠出来，同一份代码重跑时误报概率约 1%；而真正的改坏（例如某任务全部分叉、成败成片翻转）会让个数远超阈值。示意（最终以脚本输出为准）：MME 在 xhard0 上按官方三对 7／16／19 计，p̂ = 42 ÷ 576 = 7.3%，192 局的阈值约 28 局；生成按交付集 18 ÷ 800 计，192 局的整体阈值约 13 局。

**固定条件**：基线与以后的回归都在 GL A40（驱动 595.71.05）上跑；生成 `--workers 4`、每席 4 CPU、`OMP_NUM_THREADS=1`；评估每席串行、MME server `--seed=7`、确定性标志关、执行步上限 1600（xhard0 为 1300）。条件不同的结果不与基线比。

## 四、要补测什么

**固定闸门身份集 G9**：从 V9 交付集里每任务取 12 局，16 任务 × 12 局 = 192，按档位比例、候选号从小到大确定性选取，清单冻结进 git。生成与评估共用这一份；xhard0 的 16 任务 × 1 档 × 12 局 = 192（记 D0）沿用已有清单。

**生成（回答 L1′）**：在当前 HEAD 上把 G9 再生成四遍——4 worker 两遍（与交付条件相同）、1 worker 两遍（看单 worker 是否零噪声）。得到「交付:重跑」「重跑:重跑」多对比较，可以回答：分叉是否固定在某些身份、个数的波动范围、单 worker 是否可逐字节复现。若 1 worker 两遍逐字节全同，则以后回归可以多一条零噪声的生成闸门（单 worker 重跑对冻结的摘要）。

**评估（回答 L3′）**：两模型在 G9 上各重跑两遍。连同已有的一遍（V8／V9 正式评估的终态）共三遍、三对比较。xhard0 的基线直接用已有的官方三对与正式跑法，不新跑。

**规模（P5 乘式）**：生成 4 遍 × 16 任务 × 12 局 = 768；评估 2 模型 × 2 遍 × 16 任务 × 12 局 = 768；冒烟 3 局；基础设施重试上限 40。合计上限 1579 条轨迹（预算表见第二部分 §四）。

## 五、以后改代码怎么用

| 改动范围 | 必跑闸门 | 预算（每次） |
|---|---|---|
| 任何代码改动 | 核心短测 + `UPSTREAM_GUARD` | 0 |
| 动到环境、规格、builder、评估入口 | L0：`XHARD0_RESET_PARITY`（16 × 1 × 12 = 192 次 reset）+ `V9_RESET_REPLAY`（43 格 × 1 = 43 次 reset），要求全等 | 235 次 reset |
| 动到生成链路（`scripts/injection-dev/`、`src/robomme_hard/` 的求解与录制） | L1：G9 重生成一遍，`GEN_NOISE_GATE` | 16 × 12 × 1 = 192 条轨迹 |
| 动到评估接口、客户端、打包 | L2 开环重放（0 局）+ L3：两模型在 G9 与 D0 上各一遍，`EVAL_NOISE_GATE` | 2 模型 × (192 + 192) = 768 条轨迹 |

这些回归运行都超过 P3 的 50 条阈值，是否给一次性长期授权列在第七节待拍板项。

## 六、验收

| 判定行 | 查什么 | 怎么查 | 过了说明什么 |
|---|---|---|---|
| `GATE_SET=PASS tasks=16 per_task=12 total=192 in_delivery=192 sha=<…>` | 闸门身份集确定、可重算、全部属于交付集 | `noise_gate.py gate-set --check` 重算清单与冻结文件逐字节比 | 以后每次比的是同一批局 |
| `GEN_BASELINE=INFO pairs=<m> n=192 byte_diff=<x_1,…> flip=<…> single_worker_byte_equal=<a>/192 same_identity_overlap=<…>` | 生成噪声个数、是否固定身份、单 worker 是否零噪声 | `noise_gate.py baseline-gen` 读各遍 `hard_parity.py compare` 的逐局结果 | L1′ 有了实测答案 |
| `EVAL_BASELINE=INFO policy=<p> set=<G9\|D0> pairs=<m> flips=<x_1,…> success=<…>` | 评估翻转个数 | `noise_gate.py baseline-eval` 读逐局终态 | L3′ 有了实测答案 |
| `NOISE_BASELINE=PASS thresholds=<k> file_sha=<…>` | 阈值文件自洽 | 重算公式与文件值比；顶层 sha256 = 去掉该键后的规范 JSON 哈希 | 阈值不会被悄悄改动 |
| `GATE_SELFTEST=PASS same_code=PASS injected=FAIL` | 闸门本身有效 | 用基线内一对「同代码重跑」喂闸门须 PASS；用测试夹具人为加翻转须 FAIL | 闸门既不误报也不漏报 |

基线阶段的两行 `*_BASELINE` 只报告、不判 PASS／FAIL——噪声多大是测出来的事实，不预设。

## 七、实施步骤与待拍板项

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用现有留档写出基线文档初稿（第二节表格的全部已知值），0 算力 | `git diff --check` |
| 1 | 写闸门身份集与闸门脚本、测试（子代理） | `GATE_SET=PASS`；定向测试通过 |
| 2 | 冒烟：生成 1 局、两模型评估各 1 局 | 三局均取得终态 |
| 3 | GL 补测：生成四遍、评估两模型各两遍 | 每遍 192 局身份齐全 |
| 4 | 算阈值、冻结文件、补全基线文档、提交 | `GEN_BASELINE`、`EVAL_BASELINE`、`NOISE_BASELINE=PASS`、`GATE_SELFTEST=PASS` |

**需要用户拍板的三项**（批准本计划即视为同意下列推荐值）：

1. **补测预算**：上限 1579 条轨迹、3158 次 reset，GL 4 个占位 job（各 1 A40／4 CPU／48 G／48 h）。
2. **评估只测现有两模型**（SimpleMemVLA、MME-VLA FrameSamp + Modulation）；两组 GroundSG 新模型接入后另按同流程补测。
3. **以后回归运行的长期授权**：第五节表里的每次预算（生成 192、评估 768、reset 235）是否一次性授权，以后改码后直接跑、不再逐次申请。

## 八、子代理分工与合并（简述）

代码只有两块，互不碰对方文件：一块是「闸门身份集」的生成脚本、冻结清单和它的测试；另一块是「闸门判定脚本」（算基线、算阈值、做回归判定）和它的测试。两块各交一个 worktree 子代理，先合身份集、再合判定脚本；每次合并前由一个只读审查子代理核对改动范围与计划条目，合并后主会话跑核心短测。基线文档、GL 实跑、阈值冻结由主会话自己做，因为它们依赖 GPU 与 `artifacts/`。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`、不改交付 h5 与规格、不改 `scripts/configs/hard-parity-tolerances.json`、不改 `hard_parity.py` 的判定逻辑（只读调用其 `compare`）。
- R2：`scripts/` 顶层不新增文件（P1）；新脚本落 `scripts/parity/`，冻结配置落 `scripts/configs/`。
- R3：预算以 §四 为唯一上限；成功、失败、重试、冒烟全部计入；超出即停并一次性补充申请（P3）。
- R4：`*_BASELINE` 只出 INFO；阈值公式写死在脚本，冻结后不因某次回归没过而改阈值，裁决交用户（第 22 条）。
- R5：不为挑结果重试；重试只用于 0 步基础设施失败，记原因与次数。
- R6：补测期间冻结 HEAD（阶段 3 起跑到全部身份齐全之间不提交）；GL 执行副本用独立克隆并记 commit。

## 一、逐文件改动清单

| 文件 | 性质 | 内容 |
|---|---|---|
| `scripts/parity/noise_gate.py` | 新增 | 子命令：`gate-set`（`--build`／`--check`，从包内 V9 规格按任务、档位比例、候选号升序取每任务 12 局）、`baseline-gen`、`baseline-eval`、`freeze`（按第一部分第三节公式算阈值写 JSON，顶层 `sha256`）、`check-gen`（输出 `GEN_NOISE_GATE=PASS\|FAIL n= byte_diff=/K_max flip=/F_max structural= per_task_over=`）、`check-eval`（输出 `EVAL_NOISE_GATE=PASS\|FAIL policy= set= flips=/T_max s2f= f2s= mcnemar_p= exact_required=`）、`selftest` |
| `scripts/configs/gate-set-v9-192.json` | 新增 | 192 个身份（task、tier、候选号、seed、spec_sha256）与清单 sha256 |
| `scripts/configs/noise-baseline.json` | 新增（阶段 4） | 固定条件、各层基线原始个数、阈值整数、公式说明、来源 commit 与留档路径、顶层 sha256 |
| `tests/lightweight/test_noise_gate.py` | 新增 | 纯 CPU：阈值公式的手算对照、Clopper–Pearson 与二项分位的边界（x=0、x=n）、McNemar 精确检验、结构硬线、sha 防改、同代码对 PASS／注入翻转 FAIL |
| `tests/lightweight/test_gate_set.py` | 新增 | 清单确定性（两次构建字节相同）、16 × 12、全部属于交付集、档位比例 |
| `docs/1003-noise-baseline.md` | 新增 | 长期基线文档（阶段 0 初稿、阶段 4 补全） |
| `scripts/parity/README.md` | 修改 | 表格加 `noise_gate.py` 一行 |
| `docs/validation/noise-baseline-20261003/` | 新增 | `launch.md`、`result.md`、`records/`（各遍 compare 摘要与逐局 jsonl、评估逐局终态、判定行原文） |

现有能力（直接复用）：`hard_parity.py generate／compare`、`hard_regression.py xhard0-reset-parity／reset-replay`、`scripts/eval-official/compare.py eval-parity`、`run_v8_gl.sh` 与 `v8_manifest.py` 的评估编排。拟新增：上表。待验证：`generate_h5.py`／`hard_parity.py generate` 能否直接吃 G9 子集清单与 `--workers 1`；V8／V9 正式评估的逐局终态文件位置（预期在 `artifacts/v8-evaluation/`、`artifacts/v9-evaluation/`）——两项在阶段 1 开头只读核实，核实不通过时把具体缺口并入一次补充说明。

## 二、子代理分配表

| 编号 | 目标 | 可写文件集合 | 禁触 | 接口契约与依赖 | 合并顺序 | 验收（worktree 内，CPU） | 资源 |
|---|---|---|---|---|---|---|---|
| S1 | 闸门身份集 | `scripts/configs/gate-set-v9-192.json`、`tests/lightweight/test_gate_set.py`、`scripts/parity/gate_set.py`（纯函数库，供 S2 的 `gate-set` 子命令导入） | `src/robomme/`、其余全部 | 导出 `build_gate_set() -> list[dict]`、`load_gate_set(path)`；只读包内 V9 规格 | 1 | `UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<wt>/src uv run --no-sync python -m pytest tests/lightweight/test_gate_set.py -q`；判定行 `GATE_SET=PASS` | 无 GPU |
| S2 | 闸门判定脚本 | `scripts/parity/noise_gate.py`、`tests/lightweight/test_noise_gate.py` | 同上；不改 `gate_set.py` | 依赖 S1 的两个函数签名（分配表即契约，S1 合入后派发）；输入为 `hard_parity.py compare` 的逐局 jsonl 与评估逐局终态 jsonl | 2 | 同上取法跑 `test_noise_gate.py` | 无 GPU |
| M | 文档、README、GL 实跑、阈值冻结、留档 | 其余全部 | — | 主会话自做：依赖 GPU、`artifacts/` 与集群 | 3 | 见 §三 | GL 4 席 |

共享文件归属：`scripts/parity/README.md` 归主会话。S2 依赖 S1，串行派发。模型：写入型 opus，审查 sonnet。

## 三、闸门总表

| 时点 | 判定行 |
|---|---|
| 阶段 1 每次合并前 | `PRE_MERGE_REVIEW=PASS …` |
| 阶段 1 每次合并后 | `POST_MERGE_REVIEW=PASS …`（核心短测 `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`；`test_scripts_do_not_import_tests.py`；`ls -1 scripts/*.py` 仍四个入口；`UPSTREAM_GUARD=PASS`） |
| 阶段 3 起跑前 | `GATE_SET=PASS`；GL 克隆 HEAD 与本机一致；A40 与驱动断言；`ASSETS` 资产锁（沿用 `artifacts/v7.5eval/assets-lock.json`，过滤规则与 `hash_assets.sh` 一致） |
| 阶段 3 每遍结束 | 身份齐全 192/192、0 条未解决 error |
| 阶段 4 | `GEN_BASELINE`、`EVAL_BASELINE`、`NOISE_BASELINE=PASS`、`GATE_SELFTEST=PASS` |

## 四、预算表（P3 一次性授权，P5 乘式）

| 项 | 乘式 | 轨迹上限 |
|---|---|---|
| 生成，4 worker | 2 遍 × 16 任务 × 12 局 | 384 |
| 生成，1 worker | 2 遍 × 16 任务 × 12 局 | 384 |
| 评估，G9 | 2 模型 × 2 遍 × 16 任务 × 12 局 | 768 |
| 冒烟 | 生成 1 任务 × 1 局 + 评估 2 模型 × 1 任务 × 1 局 | 3 |
| 基础设施重试 | 生成 20 + 评估 20 | 40 |
| **合计** | | **1579 条轨迹；reset 上限按每条 2 次计 3158** |

xhard0（D0）基线：0 条新轨迹，全部取自 V7.5 留档。停止条件：任一遍 0 步失败超过 20 局即停该遍查因；合计触上限即停。预计耗时：生成 4 worker 每遍约 1～2 h、1 worker 每遍约 4～6 h；评估四遍分 4 席约 3 h。占位 job 4 个，开工先提交，JobID 记入 `launch.md`，跑完按清单逐个 `scancel`。

## 五、runbook

1. 阶段 0：主会话写 `docs/1003-noise-baseline.md` 初稿，提交。
2. 阶段 1：派发前四项核对（`worktree.baseRef`、主检出 clean、`check-ignore`、`git worktree list`）→ S1 → 审查 → `--no-ff` 合并 → 短测 → push → S2 同流程。
3. 阶段 2：本机或 GL 冒烟三局。
4. 阶段 3：GL 独立克隆到锚点 commit；席 1、2 各跑一遍 4 worker 生成（`OMP_NUM_THREADS=1`、`--workers 4 --gpu 0`、`--gpu_cmode=shared`），随后席 1、2 各跑一遍 1 worker 生成；席 3、4 跑评估四遍（每席串行，SimpleMemVLA 与 MME 分席）。全部在登录节点 tmux 内 `srun --jobid=<hold> --overlap --exact --ntasks=1 --gpu_cmode=shared`，会话前缀 `nb-`，每份日志挂一个监听，过滤词含 `EXIT_CODE=`、`NO RECORD`、`svulkan2`、`EXCLUSIVE`、`RRT`、`Traceback`。逐局产物先落节点 `/tmp`、核 sha 后搬回 `/data`，NFS 不留大文件。
5. 每遍生成后在本机跑 `hard_parity.py compare`（对交付 H，及遍与遍之间），逐局 jsonl 归档到 `docs/validation/noise-baseline-20261003/records/`。
6. 阶段 4：`noise_gate.py baseline-gen／baseline-eval／freeze／selftest`；补全基线文档；提交并 push；`scancel` 四席；删除对拍用 h5 与 worktree，只留摘要与逐局 jsonl。

## 六、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | G9 每任务只有 12 局，分任务阈值很松（基线为 0 的任务阈值约 2） | 以整体个数为主判据，分任务只作定位；需要更严时扩大身份集另行申请 |
| 2 | 基线的多对比较共用同几遍结果，并不独立，阈值的统计含义是近似 | 阈值另取「不小于已观测最大值」兜底；文档写明 |
| 3 | 生成噪声随节点负载变化（墙钟预算），不同节点、不同时段的比例可能不同 | 记录每遍节点名与同节点并发；条件写进基线文件；回归须同条件 |
| 4 | SimpleMemVLA 在 V9 test-hard 上未必零翻转（执行步上限 1600、任务更长） | 实测为准；非零则该模型在 G9 上改用个数阈值 |
| 5 | V8／V9 首遍评估与补测两遍相隔数日，节点组成不同 | 与 V7.5 官方噪声带同样处理：节点效应计入噪声带并写明 |
| 6 | GL 带 `shared` 的步骤结束后整卡被重置为独占 | 同席只让干活步骤带 `shared`，辅助 `srun` 不带 |

## 七、盲区诚实清单

- 生成分叉的根因只有 V3 时期的诊断（RRT 墙钟预算），V8／V9 的 32 个分叉局没有逐局归因；本计划只量大小，不做根因诊断。
- 噪声基线只对 A40 成立；本机 RTX 6000 Ada 上的回归不能与它比。
- MME 的翻转来自 server 每次启动的编译／自动调优，本计划不消除它（确定性标志减速约五成，已按规则关）。
- 闸门只能发现「个数明显超出噪声」的改坏；被噪声淹没的小幅退化（例如个别局成败变化）检不出，这类改动靠 L0／L2 的逐字节层把关。
- 两组 GroundSG 新模型、xhard1～5 的全量 800 局重复评估不在本计划内。

## 八、留档与 commit 纪律

- 留档目录 `docs/validation/noise-baseline-20261003/`：`launch.md` 在阶段 3 起跑时写（commit、席位、tmux 会话清单、完整命令、env 覆盖项），`result.md` 在阶段 4 写；`records/` 只放 git 还原不出来的逐局结果与判定行。
- 子代理提交前缀 `sub/S1: `、`sub/S2: `；合并提交与主会话提交按 `12.<小版本> <中文描述>`，body 按第 11 条六项；每次提交后立即 push。
- 局数一律写乘式（P5）；判定行内联原文。
