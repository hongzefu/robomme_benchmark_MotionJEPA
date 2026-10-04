代码与测试维护计划（2026-10-03，第三版：只管全库清理与测试重构，生成对拍改为与噪声基线单遍比对）

> 两件事：①**全代码库**清理只服务 V7／V7.5／V8 历史的代码（不只测试）；②**彻底重构全部测试**。另写改完后怎样证明生成结果没变：把噪声基线那两遍生成当参照，改后**只生成一遍**，逐局比 sha256，翻转的局单独重跑确认。
>
> 用户原话（2026-10-03，按时间）：
> 1. 「你这个项目只需要部署上限的问题和清理V7V8的就用例以及短测内容的问题就是纯代码的改动」
> 2. 「然后写的时候也分开写这三个点分别怎么改。然后如何保证噪声的一致性」
> 3. 「完全彻底重构这个计划只保留我说的这些部分。」
> 4. 「TMMAXTEP这个问题我没有看懂。然后这个清理B7V8指的是所有代码库里面全部清理了不要只清理测试然后核心短测内容怎么改我也没看懂就是你要详细的说可以彻底重构所有的test」
> 5. 「参考最新的noise baseline做好对拍的设置你不再需要生成两次了而是和之前的生成的结果做对拍。你看一下这个结果在HUGingFace上有没有如果没有的话需要上传你需要在改之后重新生成一次。还是这些episode然后和之前生成的做对比」
> 6. 「现在步数上线这个已经废弃了只负责全代码库清理测试的重构。」
> 7. 「给我你现在的噪声闸门我用户订的是10不一致你能不能订一个更加准确的闸门。」
>
> 第三版改动：删掉步数上限一节，步数上限整件事不归本计划（1600／1300 由 [`1003-oracle-subgoal-groundsg-eval-plan.md`](1003-oracle-subgoal-groundsg-eval-plan.md) 负责）；噪声一致性从「改后再生成两遍、套 10% 线」改成「与噪声基线逐局比对 + 翻转重跑确认」；新增「噪声基线上传 HF」一步。
>
> 锚点 `PLAN_BASE=2b113ca9`（12.366），分支 `newtaskRelease-taskV9`。事实来源是 2026-10-03 的三份只读盘点（包内代码、scripts、tests），以及本版写作时的只读核查（HF bucket 列表、`artifacts/noise-baseline/gen` 的文件计数、`docs/validation/noise-baseline-20261003/records/compare/*.jsonl` 的逐局记录）。本计划只规划，实施须用户说「执行」。

# 第一部分（给人看）

## 总览与已定口径

一句话：先把噪声基线的四遍生成传到 HF 私有 bucket，再在 `noise_gate.py` 里做好逐局比对闸门；然后分块删掉 V7／V8 专用代码，把仍在用、但名字带 v8 的文件改成中性名，把测试按「测什么」重新分层合并；最后用改完的代码把同一批 `129 + 48 = 177` 局生成一遍，逐局与噪声基线比对。

1. **清理判据不是文件名，而是「谁还在调用它」**：只要被 V9 生成、V9 评估、V9 站点（8082）、噪声闸门或官方对拍中的任一处调用，就保留；只被 V7／V8 历史调用的，删掉。删掉的东西随时能从 git 历史取回。
2. **不改的东西**：
   - `src/robomme/`（P2）与三个上游入口（P1）；
   - 交付规格五份与 HDF5 的字节；
   - 已封存产物里的格式名与键名，包括 `hard-specs/4`、`v8-delivery/1`、`v8-shard/1`、`v9-eval-reused/1`，以及 `reused.json` 的 `v8_manifest`／`v8_key` 等键（它们的 sha256 被清单钉住）；
   - 判定行前缀 `V8_*`；
   - **步数上限相关的一切**：`evaluation_hard.py` 的 `max_steps=1600` 那一行、`hard_specs.py::TIER_MAX_STEPS` 及其使用者。用户已声明本计划不再处理这件事（原话 6）。
3. **只测生成噪声**（噪声基线计划的用户决定），评估侧不跑真实模型。
4. **对拍参照 = 噪声基线的两遍**（原话 5）：V9 是 `v9-a`／`v9-b`，xhard0 是 `x0-a`／`x0-b`（锚点 `f8f76fba`，GL A40，两台节点）。改后只生成一遍。
5. **闸门 = 逐局 sha + 翻转重跑确认**（第三节，用户 2026-10-03 经 AskUserQuestion 选定），取代 `docs/1003-noise-baseline.md` 第六节的「翻转少于 10%」。
6. 局数一律写乘式（P5）。

## 一、噪声基线上传 HF（先做，与代码改动无关）

**现状**（2026-10-03 22:2x 只读核查）：
- `hf buckets list HongzeFu` 显示，V9 交付集在公开 bucket `HongzeFu/robomme-hard-v9` 上（1604 个对象，即 `16 任务 × 50 局 = 800` 局的 h5 与 mp4 加索引）。V9 这 129 局的交付 h5 都在里面。
- 噪声基线的四遍**不在 HF 上**。它们只存在本机 `artifacts/noise-baseline/gen/`：`v9-a` 69G、`v9-b` 68G、`x0-a` 17G、`x0-b` 17G，共 1890 个文件，其中 h5 有 `(43 格 × 3 局) × 2 遍 + (16 任务 × 1 档 × 3 局) × 2 遍 = 258 + 96 = 354` 个。dataset／model repo 也查过，只有 `panda-demonstrations`、`sam2act_robomme` 两个无关仓库。
- xhard0 原先的官方参照在 `HongzeFu/robomme-hard-parity` 里。这个 bucket 已按 V9 发布方案进入整删流程：留档 `docs/validation/newtask-v9/hf-20261003.md` 写的是已删，但本次列表里它仍然显示（该留档属于并行会话、尚未提交，本计划不碰）。删除之后，`x0-a`／`x0-b` 就是 xhard0 参照唯一的远端副本：它们能成功的 46 局与官方参照逐字节相同，2 局失败的产物也与官方相同。

**做法**（用户选定「四遍全传，新私有 bucket」）：
- 新建私有 bucket `HongzeFu/robomme-hard-v9-noise-baseline`。用 `hf buckets sync` 把 `artifacts/noise-baseline/gen/{v9-a,v9-b,x0-a,x0-b}` 整目录传上去（h5、mp4、`results.jsonl`、`summary.json`、`launch-*.json`、`generate.log` 原样上传）。两个冒烟遍 `smk-*` 不传。
- 另传三份清单：
  - `SHA256SUMS`：1890 行，本机逐文件计算；
  - `identities.jsonl`：`129 × 2 + 48 × 2 = 354` 行，每行写遍名、task、tier、seed、h5 相对路径、sha256、成功或失败；
  - `manifest.json`：写锚点 `f8f76fba`、四遍各自的节点与作业号（gl1525／63153922、gl1527／63153924、gl1525／63153923、gl1527／63153925）、驱动 595.71.05、对应的 git 记录路径。
- 传完逐对象读回，核对大小与 sha256。公开的 `robomme-hard-v9` 保持只有交付集，不动。
- 本机 `artifacts/noise-baseline/gen` 保留，比对时直接读本机文件，HF 是异地副本。[`1003-resource-cleanup-plan.md`](1003-resource-cleanup-plan.md) 第二节已补一行把它列为保留项。
- 预计约 15 分钟（上次 V9 上传实测约 208 MB/s）。不占 GPU，不做任何生成。

## 二、全代码库清理 V7／V8

### 2.1 清理后的样子

- 规格只剩一种格式 `hard-specs/4`（V9 用的就是它）。`/2`（V5～V6 单档）和 `/3`（V7 母布局派生）的读写校验代码全部删掉。
- V7 那一整套机制从包和脚本里删掉：「母布局 → 派生低档」「分层回注」「白名单」「外环弧」「BinFill 嵌套」。
- V7.5 评估的一次性车道脚本、编排器、认领队列、xhard0「官方路线」复核工具删掉。
- V8 专用的分片合并、V8 1070 局清单的构建分支、V8 单次评估的站点分支删掉。
- 噪声工具里只服务「统计线」和「评估／reset 噪声」的子命令删掉，只留生成比对（第 2.5 节）。
- 名字带 v8、但实际是 V9 现行的文件和常量，改成中性名（第 2.4 节）。

### 2.2 整文件删除

| 位置 | 文件 | 为什么能删 |
|---|---|---|
| `scripts/eval-official/v75-lanes/` | 整个目录（`gl/` 25 个 .sh、`local/` 25 个 .sh、README） | V7.5 评估当时的一次性车道脚本，没有任何代码或测试引用；V8／V9 评估用的都是重写过的席位脚本 |
| `scripts/eval-official/` | `orchestrate.py`、`watchdog.sh` | V7.5 通用编排器，只被 v75-lanes 调用 |
| 同上 | `claim_queue.py` | V7.5 的 NFS 认领队列；先删掉 `env_client.py`、`run_seat.sh` 里的 `--queue` 分支 |
| 同上（用户决定：删） | `official_observer/`（8 个文件）、`policy_replay.py`、`run_policy_replay.sh`、`step6_summary.py`、`compare.py` | V7.5 的 xhard0「官方路线」复核工具：旁路录制、开环回放、第 6 步汇总。它们依赖的三份官方检出与 `artifacts/v7.5eval/` 已在资源清理中删掉，现在已经跑不起来 |
| `scripts/injection-dev/` | `derive_specs.py` | V7 母布局派生（产出 `/3` 规格）；V9 每档独立冻结，不用它 |
| 同上 | `_report.py` | 生产代码没有引用，只有一个测试导入 |
| 同上 | `v8_watchdog.py` | V8 gen1 接续脚本的看门狗，V9 留档里没有使用记录 |
| `scripts/injection-dev/site/` | `v7_site.py`、`v7_site.html`、`v7_site_catalog.py`、`v7_subgoal_lengths.py`、`v7_site_browser_check.py`、`v7_oracle_browser_check.py` | V7 站点全套，只互相引用 |
| `src/robomme_hard/env_metadata/test-hard/` | `layout_whitelist.json` | V7 白名单，V9 builder 不读；交付规格五份不动 |
| `tests/` | `_shared/v7_specs_fixture.py`、`fixtures/v7_specs_sample/`、`fixtures/injection_legacy/` | 只服务 V7 测试。`test_v8_regression_cmds.py` 里有反例借用了 `v7_specs_sample`，先把它改用 `/4` 夹具；`injection_legacy` 全库无引用 |

### 2.3 文件内删分支（文件保留）

| 文件 | 删掉 | 保留 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | `SCHEMA`(/2)、`SCHEMA_V7`(/3)、`SCHEMAS`、`V7_TIERS`、`V7_XHARD4_ONLY`、`V7_SEED_OFFSET`、`load_specs_v7`、`_check_layout_parent`；`validate_specs` 的 /2、/3 分支；`IDENTITY_KEYS_BY_SCHEMA` 的 /2、/3 项；`seed_rule_for`／`SEED_PROFILES` 的 v5、v7 项；`V8_CELLS`／`_v8_cells`（先把 `_v9_cells` 里对它的循环与集合断言改成直接用档位表）；`CELL_TABLES["v8"]` | `/4` 读写校验、V9 格表、seed 偏移、`TIER_MAX_STEPS`（一字不动） |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | `layout_parent` 透传与 v7 注释 | 只读 `/4` 的现行逻辑、`max_steps + 2` 写法 |
| `src/robomme_hard/robomme_env/utils/episode_spec.py` | `SPEC_KIND_LAYERED`、`NEST_RULES`、`nest_binfill_targets`、`nest_outer_arc`、`SpecRecorder` 的 layered 分支 | `native-newvalue` 全量规格（V9 现行） |
| `BinFill.py`、`utils/unmask_swap_xhard.py`、`utils/unmask_distractor_sampler.py` | layered 判断与 `_choose_outer_arc` | 其余部分（V9 现行取值） |
| `scripts/injection-dev/_freeze.py` | `freeze()` 的 /2、/3 分支、`_FOUR`、`DEFAULT_SELECT` | /4、`V8_DEFAULT_CANDIDATES`（V9 仍用它核对每格局数）、分层选签 |
| `scripts/injection-dev/freeze_specs.py` | `--seed-profile v7`、`candidates_v7`、`--whitelist`；默认 profile 改成 v8 | v8 profile（V9 的 MoveCube 就用它） |
| `scripts/injection-dev/_rollout.py` | V7 候选池整段（`initial_pool`、`sync_drop_and_backfill`、`run_continue_v7`、`V7_DELIVERY_SET`）、`run_replay` 的 v7 根、`merge_v8` 与 V8 四席分片表 | `split_v8`、`aggregate_v8`、`load_v8_root`、`run_continue_v8`（V9 现行） |
| `scripts/injection-dev/generate_h5.py` | `replay`／`continue` 的 v7 分支、`--mode merge` | `split`／`continue`／`aggregate`（V9 用） |
| `scripts/injection-dev/eval_video_mover.py` | `--mode v7`；默认改成 v8 | v8 账本模式（V9 用） |
| `scripts/injection-dev/v8_continue_after_gen.py` | V8 gen1 专用的等报告、守卫步骤与心跳 | `--site-only --cells v9` 建站路径（8082 用） |
| `scripts/injection-dev/site/v8_site_catalog.py` | V8 单次评估运行分支（`eval_run`、`xhard0_eval`） | V9 复用口径 |
| `scripts/eval-official/env_client.py` | `--queue`、`--canary` 分支与 `claim_queue` 导入 | `--v8` 模式；非 v8 的 `--identities` 路线（尚未开工的 Oracle 计划要用） |
| `scripts/eval-official/run_seat.sh` | `--queue`、`--canary`、`--client-per-task`、`--no-record`；默认 `SMVLA_PY` 指向已删目录，改成必须显式传入 | `--v8` 与非 v8 的 `--identities` 路线 |
| `scripts/eval-official/v8_manifest.py` | V8 1070 局的 `build()` 分支 | `build_v9`，以及读取 V8 清单做对账的函数 |
| `scripts/parity/hard_regression.py` | `layout-shared`、`prefix-geometry` 两个子命令及辅助函数；`_step_headroom_v7` 与 `--v7`；`reset-replay`／`eval-smoke` 的 v7 口径；`xhard0-eval-parity` | `delivery-set`、`tier-values`、`reset-replay`、`xhard0-reset-parity`、`step-headroom`、`movecube-layout`、`env-digest` 三件套、`delivery_index` |
| `scripts/parity/hard_parity.py` | `generate --tier xhard`（V6 四档）与 `--tier v8`、`compare` 里对应的分支、`import-delivery --tier v8` | `native`、`xhard0`、`v9`、`anchor`、`binding`、`export-xhard0-manifest`；`publish` 的 `BUCKET` 常量指向已删 bucket，归 HF 发布方案处理，本计划不动 |

### 2.4 改名（文件仍在用，只是名字误导）

| 现名 | 新名 |
|---|---|
| `scripts/eval-official/run_v8_gl.sh` | `run_eval_gl.sh` |
| `scripts/eval-official/v8_manifest.py`、`v8_report.py` | `eval_manifest.py`、`eval_report.py` |
| `scripts/injection-dev/v8_continue_after_gen.py` | `site_build.py` |
| `scripts/injection-dev/site/v8_*.py`、`v8_site.html` | 去掉 `v8_` 前缀 |
| `scripts/injection-dev/site/v7_render_xhard0.py` | `render_xhard0.py`（V9 站的 xhard0 视频由它产出） |
| `scripts/configs/newtask-v7/xhard0_manifest.json` | `scripts/configs/xhard0/xhard0_manifest.json`（内容是官方 xhard0 192 局清单，不是 V7 数据） |
| `hard_specs.py` 里的 `V8_EXEC_CAP`、`V8_TIERS`、`SCHEMA_V8`、`V8_LAYOUT_RULE`、`load_specs_v8`、`_validate_specs_v8` | `EXEC_CAP`、并入 `TIERS`、`SCHEMA`、`LAYOUT_RULE`、`load_specs`、`_validate_specs` |
| `tests/_shared/v7_tier_values.py` | 并入新测试结构（见第四节） |

改名后要同步改所有引用点：
- `noise_run.py`、`noise_gate.py` 里按路径加载 `v8_manifest.py`／`v8_report.py` 的常量；
- `site/*` 之间按文件名 `importlib` 加载的字符串；
- `docs/1003-noise-baseline.md` 第七节回归命令里的 `scripts/configs/newtask-v7/xhard0_manifest.json`。

`scripts/README.md` 加一张新旧名对照表。`docs/validation/**` 历史留档里的旧命令不回改。

### 2.5 噪声工具瘦身

噪声基线已经测完，用户口径是以后只测生成噪声。所以噪声工具只留生成这一条线，外加第三节新增的逐局闸门：
- `scripts/parity/noise_gate.py`：
  - **保留** `gen-compare`、`run-fresh`（`noise_run_gl.sh` 判 `RUN_FRESH` 要用）、`selftest`；
  - **删除** `eval-extract`、`baseline-reset`、`baseline-gen`、`baseline-eval`、`freeze`、`verify`、`check-reset`、`check-gen`、`check-eval`，以及只为它们服务的统计函数（`binom_cdf`、`cp_upper` 等）和 `_extract_v8_root`／`extract_legacy`；
  - **新增** `gen-regress`（第三节）。
- `scripts/parity/noise_run.py`：删 `eval-shard`。
- `scripts/parity/noise_run_gl.sh`：删 `--kind eval|digest` 分支。
- 以上每一项先由审查子代理核实「只有评估／统计在用」才删。`run-fresh` 如果在 gen 路径上也读评估抽取结果，就把那部分改成只认 gen 输出，而不是整个删掉。

## 三、噪声一致性：与噪声基线逐局比对（新闸门）

### 3.1 现行闸门为什么不够准

`docs/1003-noise-baseline.md` 第六节的现行判据是：改后生成一遍，与永久参照（V9 交付 h5、xhard0 官方参照）比较，非逐字节相同的局少于 n 的 10%，即 V9 129 局里不超过 12 局、xhard0 48 局里不超过 4 局；另要求结构不同 = 0、原因不明 = 0。

问题出在**余量比真实噪声大一个数量级**。实测基线（`records/compare/*.jsonl`）：
- V9 两遍跨节点只有 1 局不同（BinFill xhard1 seed 16400000，第 2 遍失败）；
- xhard0 两遍 0 局不同（VideoPlaceOrder seed 610701、611101 两遍都确定性失败，失败产物逐字节相同）。

照 10% 的线，改坏一整个任务也能过。V9 里一个任务约 8 局（例如 SwingXtimes 在 5 个档里各 3 局 = 15 局，StopCube 也是 15 局），某个任务的局全部翻转仍可能不超过 12。

### 3.2 新闸门：每一局都有自己的期望

参照文件 `scripts/configs/noise-ref-20261003.json` 进 git。它由第二部分 G 块的 `gen-regress build-ref` 生成：从本机四遍 h5 重算 sha256，与 git 里的比对记录交叉核对一致后，把每一局归入三类之一。

| 类 | 局 | 期望 |
|---|---|---|
| 稳定局 | V9：除 BinFill xhard1 seed 16400000 外的 128 局（含 MoveCube xhard4 seed 23400200，它两遍彼此相同，只是与交付 h5 不同，参照以基线为准）；xhard0：除 VideoPlaceOrder seed 610701、611101 外的 46 局 | 新跑的 sha256 ∈ {a 遍 sha, b 遍 sha}。稳定局两遍 sha 本来相同，所以等价于「与基线逐字节相同」 |
| 确定性失败局 | xhard0 VideoPlaceOrder seed 610701、611101 | 新跑也必须失败，且失败产物 sha 与基线相同（800 字节，sha256 前缀 `26c4d449632ea072`） |
| 已知抖动局 | V9 BinFill xhard1 seed 16400000（a 遍成功，b 遍失败；交付集里本就是 18 局不可复现之一） | 不参与判定，结果写进报告：与 a 同、与交付同、走另一条轨迹还是失败 |

**一局稳定局（或确定性失败局）的结果不符合期望，就叫「出问题」（翻转）。** 只看第一次跑无法判断原因。噪声基线里已有反例：BinFill xhard1 seed 16400000 两遍新跑在第 819 步一起偏离交付 h5，走的是同一条新轨迹；MoveCube xhard4 seed 23400200 两遍新跑彼此相同，却与交付 h5 不同。也就是说，同一份代码换时间、换节点，也可能稳定地走出另一条轨迹，因此「两次相同但和之前不同」不能直接判为代码改坏了。

所以出问题的局要再跑一轮，在**同一台节点**上用两份代码各跑 1 次：改后代码 1 次，旧代码（噪声基线锚点 `f8f76fba`）1 次，作对照。之后按下表定性（用户 2026-10-03 确认）：

| 改后代码第二次 | 旧代码这一次 | 定性 | 含义 |
|---|---|---|---|
| 与 a 或 b 逐字节相同 | （不看） | **噪声** | 改后代码仍能跑出基线结果，第一次只是 RRT* 墙钟预算下的偶发抖动。这一局登记进抖动名单：写回参照文件的 `jitter_observed`，须经用户确认 |
| 与第一次相同，不同于基线 | 与 a 或 b 相同 | **回归**（代码改坏了） | 旧代码在同一节点仍能出基线结果，新代码稳定地不同 |
| 与第一次相同，不同于基线 | 也不同于基线 | **环境变了** | 新旧代码在这台节点上都出不了基线结果，原因在节点或驱动，不在代码；交用户裁决 |
| 与第一次不同，也不同于基线 | — | **每次都不同**（不稳定） | 交用户裁决，不自行归类 |

**第三次默认不跑**：两轮之后每一局都已落进上表某一格。只有用户看了逐局表后点名要求，才另报预算再跑。

**逐局报告**：只列出问题的局和已知抖动局。每行写：
- 任务、档、seed；
- 第一次、改后第二次、旧代码这一次各自的 sha 前缀，以及成功或失败；
- 三者两两是否相同；
- 与基线从第几步开始分叉、在哪个子目标（拉回本机对照 a 遍 h5 算出）；
- 定性结论。

### 3.3 通过条件（`GEN_REGRESS=PASS`）

两个集合（V9、xhard0）各自都要满足：
1. 回归 = 0，每次都不同 = 0，环境变了 = 0；
2. 确认为噪声的翻转：V9 ≤ 2 局，xhard0 ≤ 1 局。超出时不判 PASS，把逐局明细交用户裁决；
3. 结构不同 = 0（字段缺失、dtype／shape 变化、第 0 帧不同、`setup` 组不同），原因不明 = 0（文件打不开、缺文件、sha 与记录不符）。出现任何一局，直接 FAIL，不进重跑；
4. 跑法前提：GL A40、`--workers 4`、每局都有结果、`RUN_FRESH=PASS`、`BUDGET=PASS`。不满足则本遍无效，重跑，不判通过或失败；
5. 只报告、不判定：已知抖动局的结果；翻转按任务的分布；与 V9 交付 h5 的附带比较（沿用 `gen-compare --ref delivery.local.json`，供对照历史）。

**为什么比 10% 准**：每一局都有自己的期望。只要一局在改后代码上稳定地变了，就会被抓到；真正的偶发抖动由第二次跑认出来，不会误报。旧代码同时跑一次作对照，能把「代码改坏了」和「环境变了」分开，而不是只凭「两次相同」下结论。

**限制**：
- 只在 GL A40 上成立。换 GPU 型号后整文件不再一致，历史上 RTX 6000 Ada 对 A40 是 0/108。驱动版本按来源报告核对，与基线的 595.71.05 不同时先报告用户。
- PASS 说明「177 局里没有检出超出噪声的变化」，不证明全部 800 局逐字节等价。
- 新闸门写进 `docs/1003-noise-baseline.md` 第六节，取代 10% 判据（用户选定）。旧判据原文保留在该节末尾，作为历史记录。

### 3.4 改后实跑一次

- **时机**：第二、四节的全部代码清理、改名、测试重构都合并完成后，跑且只跑一次（原话 5「你需要在改之后重新生成一次」）。
- **内容**：同一批局各生成一遍，与基线命令相同，只换代码版本（命令见第二部分 runbook）：
  - V9 `43 格 × 3 局 = 129`；
  - xhard0 `16 任务 × 1 档 × 3 局 = 48`。
- **地点**：GL A40，2 个占位席（V9、xhard0 各一席，1 A40／4 CPU／48G）。V9 约 37 分钟，xhard0 约 10 分钟。
- **两份代码**：
  - NFS 上的 `robomme_benchmark-noise` **保持在 `f8f76fba` 不动**，作为旧代码对照。
  - 改后代码另建一个 NFS 检出 `robomme_benchmark-maint`，切到合并后的 HEAD，不建 venv。运行时借用 noise 克隆的 `.venv`，加 `PYTHONPATH=<maint 检出>/src`（editable 指向的是 noise 克隆的 src，所以必须先打印 `robomme_hard.__file__`，确认指向 maint 检出）。前提是 `uv.lock` 零 diff，否则停下另报。
- **预算**（P3／P5，用户选定方案时一并授权，见第二部分预算表）：
  - 首跑 `43 格 × 3 局 + 16 任务 × 1 档 × 3 局 = 177` 条；
  - 第二次跑：每个出问题的局 2 条（改后 1 + 旧代码 1），上限 20 条；出问题的局超过 10 个就不进第二次，直接交用户；
  - 合计 197 条，reset 上限按每条 3 次计 `197 × 3 = 591`。
  - 冒烟：V9、xhard0 各 1 局，共 2 条、reset 6（AGENTS 第 4 条）。
  - 总上限 199 条、reset 597，用户 2026-10-03 已确认。
- **边生成边判定，只回传有问题的局**（用户 2026-10-03 原话：「现在每次都要回传Turbo的Data能否不用回传?直接现场计算计算完了有问题的再回传。」「是否可以每次一边生成一边计算SHA256。」「要生成完了统一计算就是async的去做。」——按「不要等生成完了统一算，要异步地边生成边算」理解）：
  - **sha 本来就是边生成边算的**：`hard_parity.py generate` 里的 `Mover` 是一个后台线程，每 5 秒扫一次各轮的 `results.partial.jsonl`。某一局一完成，它就在节点上算这局 h5 的 sha256，写一行 `identities.jsonl`，打印 `EPISODE_DONE … sha=<前 12 位>`。这时其他 worker 还在继续生成，所以已经是异步的。现在缺的只是「拿这个 sha 当场和参照比」这一步。
  - **新增 `generate --expect-ref <参照文件>`**（G 块）：`Mover.handle` 算完 sha 后立刻查参照里这一局的期望，在同一行 `identities.jsonl` 写入 `verdict`。
    - `match`：稳定局 sha 与基线相同，或确定性失败局失败且 sha 相同。直接删掉节点 `/tmp` 里的 h5 和 mp4，**不复制到 NFS**。这份字节本机和 HF 上都已经有了。
    - `jitter_info`：已知抖动局。照常复制到 NFS，供报告使用。
    - `flip`：期望不符，也包括稳定局生成失败。照常复制到 NFS 并核对 sha，同时追加一行到 `flips.jsonl`（格式可直接作为 `--identities` 使用），打印 `EPISODE_FLIP <tier>/<task>/<seed>`。
  - **当场就能看到**：Monitor 盯 `EPISODE_FLIP`，第一局翻转出现就会通知，不用等 37 分钟跑完。生成结束时，翻转清单已经现成，紧接着在同一席位上起第二次跑（改后代码与旧代码各一遍，只含翻转局），同样带 `--expect-ref`、边跑边判定。旧代码 `f8f76fba` 没有 `--expect-ref`，所以旧代码那一遍不带此参数，照常复制到 NFS（局数 ≤ 10，体量小）。
  - **生成本身一字不改**：仿真、worker、运行器都不动，只改生成后的搬运线程，所以被测的生成路径与基线相同。没给 `--expect-ref` 时，行为与现在完全一样。
  - **收尾判定很快**：`gen-regress check` 读 `identities.jsonl` 里已经写好的 sha 与 verdict 汇总出判定行，不重读 h5，在 GL 登录节点或占位作业里秒级完成。`noise_run.py ship --finalize` 相应改成认 `verdict=match` 的局「按设计不复制」，不算 missing。
  - **只回传翻转局**：`hard_pull.py --identities <flips.jsonl>` 只拉这些局（首跑和重跑的 h5、mp4），以及各遍的 `results.jsonl`、`identities.jsonl`、`summary.json`、来源报告。到本机后与 a 遍 h5 跑 `compare_h5`，区分「结构不同」和「走了另一条轨迹」，并给出分叉步。没有翻转时只拉报告，约几 MB。NFS 上本来就只有翻转局，判定落档后逐目录列名删除。
  - **不会漏判**：结构不同只需要对翻转局判。sha 相同的局与基线逐字节相同，结构必然相同。
- **FAIL 时**：不改参照、不改判据。按翻转局所属任务定位到是哪块改动导致，回退或修好那一块后重跑。重跑预算另报。

## 四、测试彻底重构

### 4.1 现在的测试有什么问题

- **太慢**：日常命令 `pytest tests/lightweight/ -m 'not gpu and not slow'` 实测 476.7 s（1758 passed／6 failed／3 skipped），超出 5 分钟预算，280 s 限时会在 85% 处截断。慢的原因不是断言多（约 450 条纯函数断言合计只要几十秒），而是少数文件起子进程，或者 `sleep` 等超时被杀，却没有标 `slow`。这类文件有 `test_v8_eval_orchestration`、`test_v8_continue_fixtures`、`test_noise_run_wrapper`、`test_eval_official_orchestrate`、`test_eval_official_run_seat`、`test_official_observer`、`test_registry_owner` 等。以上是按代码特征估计的，阶段 0 实测校准。
- **6 个长期失败**：自 `30f36e44` 起每次都失败，一直靠「与基线相同」放行。
- **按版本号命名，同一个东西散在多处**：`test_v4_xhard_binfill.py`、`test_v5_xhard_binfill.py`、`test_v7_binfill_nested.py` 测的是同一个任务。约 45 个 v4／v5／xhard 文件，其实只对应 14 个任务。
- **重复断言**：`TIER_MAX_STEPS` 在 3 处各断一遍，`EXPECTED_CELLS` 合计在 4 处各断一遍。
- **测的是历史**：9 个 `test_v7_*`、5 个 `test_v8_eval_*` 的一部分、`test_v8_native_blocks_unchanged` 等，守的是 V7／V8 链路。另有 4 个用例靠 `monkeypatch` 把格表钉回 V8 的 1070／1262 才能通过。
- **marker 标错**：`test_ChoiceLabel.py` 等标了 `gpu`，却不起环境；起子进程的反而没标 `slow`。
- **收集范围**：裸 `pytest` 会扫到 `third_party/`，报 53 个收集错误。
- **与官方矛盾**：`tests/dataset/test_eepose_error_handling.py` 断言 `status == "error"`，与官方实现不符，只是因为从不进日常口径才没暴露。
- **缺测试**：没有任何测试守 `scripts/parity/upstream_guard.py`。

### 4.2 新结构：按「测什么」分目录

| 目录 | 放什么 | 日常门禁 | 预计耗时 |
|---|---|---|---|
| `tests/unit/robomme/` | 官方 `src/robomme` 行为：TaskGoal、ChoiceLabel、ChoicePositionNearest、pixel_mapping、StopcubeIncrement、waypoint 去重、choice_action 流程、subgoal 序数 | 是 | 秒级 |
| `tests/unit/hard/` | `src/robomme_hard` 按任务一个文件：`test_binfill.py`、`test_insertpeg.py`、`test_movecube.py`、`test_pickswing.py`（PickXtimes、SwingXtimes、PickHighlight）、`test_unmaskswap.py`、`test_unmask.py`、`test_videorepick.py`、`test_videoplace.py`、`test_stopcube.py`、`test_patternlock_routestick.py`、`test_collision.py`、`test_shared_sampling.py`、`test_xhard_utils.py`、`test_sampling_config.py`、`test_difficulty_seed.py`、`test_episode_spec.py`、`test_taskgoal_hard.py` | 是 | 几十秒 |
| `tests/contract/` | V9 规格与身份契约：`test_v9_spec_contract.py`（合并 `v9_packaged_800`、`hard_builder_xhard0`、`xhard0_native`、`v8_specs_schema` 中的 V9 部分；`TIER_MAX_STEPS` 现值、`EXPECTED_CELLS`、800／992 局数只在这里断言一次，值保持现状）、`test_tier_values.py`（取代 `_shared/v7_tier_values.py`）、`test_v9_subset_specs.py`、`test_scripts_do_not_import_tests.py`、新增 `test_noise_ref.py`（参照文件自洽：V9 129 局、xhard0 48 局，三类计数 128／1／0 与 46／0／2，顶层 sha 防篡改） | 是 | 十几秒 |
| `tests/upstream/` | 官方对齐：新增 `test_upstream_guard.py`（`src/robomme` 与三个入口与官方 `1fadc0ec` 逐字节相同）、`test_official_behaviors.py`（改写后的 step_error 用例）、三个 record_* 源码扫描用例、`test_train_split_parity.py` | 是 | 秒级 |
| `tests/parity/` | 对拍设施：h5 全字段比较器、`hard_parity`、`comparator_scope`、`env_digest_compare`、`gate_set`、`noise_gate`（`gen-compare`、`gen-regress` 的合成夹具：稳定／第二次回基线（噪声）／新代码稳定偏离而旧代码回基线（回归）／新旧都偏离（环境变了）／每次都不同／结构不同／失败 sha 不符七种情形）、`hard_regression` 的 V9 子命令 | 纯合成数据的进门禁；起子进程的标 `slow` | 门禁部分几十秒 |
| `tests/pipeline/eval/` | 评估流水线：`env_client`、`mme_client`、`smvla_client`、`recorder`、`eval_manifest`、`eval_report`、`eval_video_mover`、`run_seat`（同一被测脚本的 `eval_official_*` 与 `v8_eval_*` 合并成一个文件） | 否（改评估代码时跑） | 分钟级 |
| `tests/pipeline/gen/` | 生成流水线：状态机、分片聚合、`noise_run` 包装、站点建站 | 否（改生成或站点时跑） | 分钟级 |
| `tests/gpu/` | 需要 GPU／ManiSkill 环境的：原 `tests/dataset/` 全部、`TaskGoalI_isList`、`wrapper_chain`、gym.make 用例 | 否（有 GPU 时跑） | — |

公共夹具：`tests/_shared/repo_paths.py` 并入根 `tests/conftest.py`；`_shared/dataset_generation.py` 随 `gpu/` 一起搬走；取消 `tests/lightweight/` 目录；`tests/README.md` 按上表重写。

### 4.3 现有文件去向

- **删除**（只测被删代码或历史）：`test_v7_candidate_pool`、`test_v7_freeze_schema`、`test_v7_layered_recorder`、`test_v7_site_catalog`、`test_v7_whitelist_semantics`、`test_v7_outer_arc`、`test_v7_binfill_nested`、`test_v8_native_blocks_unchanged`、`test_native_restore_step2`、`test_audit_fix`、`test_audit_fix_scripts`、`test_eval_official_orchestrate`、`test_eval_official_queue`、`test_official_observer`、`test_eval_official_policy_replay`、`test_eval_official_step6`、`test_eval_official_compare`；`test_noise_gate.py` 里测被删统计线和评估子命令的用例。
- **先抽出 V9 部分再删壳**：`test_v7_seed_rule`、`test_v7_tier_values`、`test_v8_specs_schema`、`test_v8_difficulty_tiers`、`test_v8_regression_cmds`、`test_v8_delivery_flow`、`test_v8_continue_fixtures`、`test_v8_site_catalog`、`test_v8_append_candidates`。4 个用 `monkeypatch` 钉 V8 格表的用例，改成断言 V9（800／992）或删除。
- **合并**：v4／v5／xhard 按任务合并（约 45 个文件收成 17 个）；`eval_official_*` 与 `v8_eval_*` 按被测脚本合并。
- **删之前先列对照表**：每行写「旧 nodeid → 它守的契约 → 新 nodeid／删除理由」，交你过目后才删。仍然有用的负例（空集、身份重复或遗漏、错签名、错绑定）必须在新位置有对应用例。

### 4.4 6 个长期失败逐条改法（只改测试，官方源码不动）

| 测试 | 为什么失败 | 改法 |
|---|---|---|
| `test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal` | 官方 `task_goal.py::get_language_goal` 对未知环境返回 `[]`，测试期望 `[""]` | 断言改为 `[]`，函数名改成「未知环境返回空列表」，移进 `unit/robomme/` |
| `test_TaskGoal.py::test_swingxtimes_multiple` | 官方文本是 `back-and-forth`，测试写的是 `back and forth` | 改成官方文本 |
| `test_step_error_handling.py::test_step_error_returns_status_error` | 官方 `DemonstrationWrapper.step` 里没有 try（docstring 说会捕获，实现里没有） | 改成锁定官方现状：断言 `step` 内没有 try、异常向上抛，移进 `upstream/` 并注明这是官方行为；同文件两条只测内联复刻代码的同义反复用例删掉 |
| `test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except` | `dataset_replay.py` 的实际写法是 `try: env.step … except Exception` 加 `info.get("status", "unknown")` | 拆开：`run_example.py` 保留原断言；`dataset_replay.py` 改为断言官方现状 |
| `test_v8_eval_report.py::test_zz_summary_line`、`test_v8_eval_video_mover.py::test_zz_summary_line` | 断言整个 pytest 会话的失败数为 0，前面任何文件失败都会连带它失败 | 删掉这种「会话汇总」用例，判定行改由 pytest 退出码生成 |

`tests/gpu/test_eepose_error_handling.py` 同样改为断言官方现状（异常向上抛）。

### 4.5 日常门禁与配置

- `pyproject.toml::tool.pytest.ini_options`：`testpaths = ["tests"]`（不再扫 `third_party/`）；markers 改为 `slow`、`gpu`、`pipeline`。
- 日常命令：`timeout 280s uv run --no-sync python -m pytest tests/unit tests/contract tests/upstream tests/parity -m 'not slow and not gpu' -q --durations=20`，目标 ≤ 120 s。
- 改评估代码时加跑 `tests/pipeline/eval`；改生成或站点时加跑 `tests/pipeline/gen`；有 GPU 时跑 `tests/gpu`。
- `AGENTS.md` 的「覆盖第 4 条」与 `tests/README.md` 同步改。

## 五、验收

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 基线已上 HF | 逐对象读回，比大小与 sha256 | 参照有了异地副本，xhard0 参照不再只剩本机 | `NOISE_HF_UPLOAD=PASS objects=1893 size_equal=1893 missing=0 extra=0`；`NOISE_HF_READBACK=PASS sha_match=1890` |
| 参照文件可信 | `gen-regress build-ref` 重算四遍 h5 sha，再与 git 比对记录逐局对照 | 参照里每局期望都来自真实文件且与已提交记录一致 | `NOISE_REF=PASS v9=129 stable=128 jitter=1 xhard0=48 stable=46 fail=2 mismatch=0` |
| 改动不越界 | `git diff --name-only <BASE>..<HEAD>` 逐个文件归入第二节清单 | 没有清单外的改动 | `MAINT_SCOPE=PASS files=<n>` |
| 官方源码与入口未动 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | P1、P2 守住 | `UPSTREAM_GUARD=PASS` |
| 交付规格未动 | 五份 `specs.jsonl` 的 sha256 与改前相同 | 生成输入不变 | `MAINT_SPECS=PASS changed=0` |
| scripts 顶层仍是四个入口 | `ls -1 scripts/*.py` | P1 | 恰好四个 |
| 删掉的分支 V9 走不到 | 审查子代理逐文件核对 | 删除不影响 V9 路径 | `MAINT_DEAD_BRANCH=PASS files=<n>` |
| 没有残留引用 | `grep -rn "load_specs_v7\|SCHEMA_V7\|v75-lanes\|claim_queue\|derive_specs\|v7_site\|check-gen\|baseline-gen" src scripts tests` 为空 | 清干净了 | `MAINT_NO_LEGACY=PASS` |
| 覆盖不缩水 | 旧 nodeid 对照表每一行都有去向 | 重构没丢契约 | `MAINT_TEST_COVERAGE=PASS` |
| 6 个失败消失、日常门禁够快 | 第 4.5 节日常命令 | 门禁可信且在预算内 | `MAINT_CORE=PASS failed=0 wall_s=<实测>`（≤120） |
| 流水线测试通过 | `pytest tests/pipeline -q` | 评估与生成流水线不受影响 | `MAINT_PIPELINE=PASS failed=0` |
| 收集无错误 | `pytest --collect-only -q` | 不再扫 `third_party/` | `MAINT_COLLECT=PASS errors=0` |
| 生成结果没变 | `noise_gate.py gen-regress`（GL 现场按 sha 判定首跑与翻转重跑；只把翻转局回传到本机做结构细分） | 改后代码生成的 177 局逐局与基线相同，或翻转已被认定为噪声 | `GEN_REGRESS=PASS set=v9 n=129 match=<n> jitter_info=1 flip=<n> noise=<≤2> regress=0 env_changed=0 unstable=0 structural=0 unknown=0`；xhard0 同格式 `noise=<≤1>` |

## 六、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 跑一次现状全量测试，取逐文件耗时（`--durations=0`，CPU，tmux，约 8 分钟） | 耗时表落到 `artifacts/maintenance/` |
| 1 | H：噪声基线上传 HF（主会话自做，可与阶段 2 并行） | `NOISE_HF_UPLOAD`、`NOISE_HF_READBACK` |
| 2 | G：`gen-regress` 闸门与参照文件、噪声工具瘦身 | `NOISE_REF=PASS`，`tests/parity` 的 noise 用例通过，`PRE_MERGE_REVIEW=PASS` |
| 3 | W1～W3 并行：scripts 三块的删除与删分支 | 各块定向测试通过，`PRE_MERGE_REVIEW=PASS` |
| 4 | W4：`src/robomme_hard` 删 V7 常量与 layered 机制（要等阶段 3 先删掉调用方） | 同上，并要求 `MAINT_SPECS=PASS` |
| 5 | R：改名（含噪声工具的路径常量） | 全部 CPU 测试通过，`MAINT_NO_LEGACY=PASS` |
| 6 | T1、T2：测试重构（新目录、合并、6 个失败、对照表） | `MAINT_CORE`、`MAINT_PIPELINE`、`MAINT_TEST_COVERAGE`、`MAINT_COLLECT` |
| 7 | 生成闸门：冒烟 2 局 → 第一次 177 局（边跑边判）→ 出问题的局第二次（改后 1 + 旧代码 1）→ 逐局报告 | `GEN_REGRESS=PASS`（两个集合） |
| 8 | 文档：`docs/1003-noise-baseline.md` 第六节换成新闸门、第七节换命令；`scripts/README.md`（含新旧名对照）、`scripts/parity/README.md`、`src/robomme_hard/README.md`、`tests/README.md`、`AGENTS.md`；待定清单 B5／C1／C2 结案；运行留档 `docs/validation/maintenance-regress-<日期>/` | 验收表全部判定行 |

## 七、子代理分工与合并（简述）

拆成八块，按文件切开、互不重叠：
- **G** 管 `noise_gate.py`／`noise_run.py`／`noise_run_gl.sh` 和新参照文件；
- **W1** 管 `scripts/eval-official/`；
- **W2** 管 `scripts/injection-dev/`；
- **W3** 管 `scripts/parity/` 里 `hard_regression.py` 与 `hard_parity.py` 的历史分支；
- **W4** 管 `src/robomme_hard/`；
- **R** 做改名；
- **T1** 管单元、契约与官方对齐测试；
- **T2** 管对拍、流水线与 GPU 测试。

顺序：
1. G 与 W1～W3 一起先派，因为它们的文件互不相交；
2. W4 等 W1～W3 合入后再派，因为它要删的常量在 W1～W3 的文件里还有人用；
3. R 等前面全部合入后再做；
4. T1、T2 最后并行。

上传 HF、跑 GL 闸门、改文档由主会话自己做。每块合并前派一个只读审查子代理，核对改动有没有越出该块的文件清单、被删的分支 V9 是否确实走不到。每块合并后主会话跑日常门禁、`UPSTREAM_GUARD`、`MAINT_SPECS`，PASS 后立即 push。

## 八、用户决定（2026-10-03，经 AskUserQuestion 选定）

| 编号 | 问题 | 用户选择 |
|---|---|---|
| Q1 | 步数上限 | 本计划不再处理（原话 6）；1600／1300 归 Oracle 计划 |
| Q2 | V7.5 xhard0「官方路线」复核工具 | 删除（git 历史可取回） |
| Q3 | 名字带 v8 的现行文件和常量改中性名 | 改；格式名、键名、`V8_*` 判定行前缀不改 |
| Q4 | 方案写在哪 | 重写本文件；资源清理方案只在保留清单补一行 |
| Q5 | 噪声基线上 HF | 四遍全传，新建私有 bucket `HongzeFu/robomme-hard-v9-noise-baseline` |
| Q6 | 闸门 | 逐局 sha + 翻转重跑确认 |
| Q7 | 每局怎么跑 | 第一次 177 局全跑、边跑边算；出问题的局第二次改后代码与旧代码 `f8f76fba` 各 1 次；第三次默认不跑；逐局报告「两次相同且与之前不同」还是「每次都不同」。预算 冒烟 2 + 177 + 第二次 ≤ 20 = 199 条，reset 597（用户「确认」） |
| Q8 | 回传 | 不整遍回传，边生成边比 sha，只回传出问题的局 |

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`、`scripts/{dataset_replay,evaluation,run_example}.py`、交付规格五份、`uv.lock`；不改格式名、`reused.json` 键名、`V8_*` 判定行前缀；不碰 `evaluation_hard.py` 的 `max_steps` 行与 `TIER_MAX_STEPS`。
- R2：参照文件 `scripts/configs/noise-ref-20261003.json` 生成后只读；闸门 FAIL 时不改参照、不改通过条件。
- R3：阶段 0～6 只跑 CPU 测试；GPU 生成只在阶段 7 进行，且不超出预算表。
- R4：不新增 `scripts/` 顶层文件；`scripts/` 不得 import `tests/`。
- R5：worktree 内用 `UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync`，先打印 `robomme_hard.__file__` 确认指向 worktree。
- R6：HF 只新建并写入 `HongzeFu/robomme-hard-v9-noise-baseline`；不碰 `robomme-hard-v9`、`robomme-hard-parity` 和其他 16 个 bucket。token 只走环境，不落文件。
- R7：本机 `artifacts/noise-baseline/gen` 只读，上传与比对都不改它。
- R8：不碰未跟踪的 `docs/validation/newtask-v9/hf-20261003*`（并行会话在途）。

## 一、逐项改动清单

第二节的表格就是逐文件清单。以下为补充：

**G 块（新增 `gen-regress`）**——`scripts/parity/noise_gate.py`：
- `gen-regress build-ref --runs v9=artifacts/noise-baseline/gen/v9-a,artifacts/noise-baseline/gen/v9-b --runs xhard0=artifacts/noise-baseline/gen/x0-a,artifacts/noise-baseline/gen/x0-b --identities-v9 scripts/configs/gate-set-v9-129.json --identities-xhard0 scripts/configs/gate-set-xhard0-48.json --records docs/validation/noise-baseline-20261003/records/compare --out scripts/configs/noise-ref-20261003.json`
  - 每局写入 `{id, task, tier, seed, class: stable|known_fail|jitter, shas: [a, b] 去重, ok_a, ok_b, h5_a, h5_b}`，顶层写 `anchor=f8f76fba`、`hf_bucket`、剔除自身后的 canonical sha；
  - 交叉核对规则：记录里 `byte_equal` 的局，两遍 sha 必须相同；记录里有 `ref_sha256`／`new_sha256` 的，必须与重算值相同。不符即打印 `NOISE_REF=FAIL`；
  - 失败局的 sha 从 800 字节占位 h5 直接计算（记录里失败侧 sha 为 None）。
- `gen-regress check --ref scripts/configs/noise-ref-20261003.json --set {v9,xhard0} --new <新跑根> [--rerun <重跑根> ...] --out <jsonl> --rerun-identities-out <jsonl>`
  - 首跑时不给 `--rerun`。有翻转就输出 `GEN_REGRESS=NEED_RERUN flip=<n>`，并把翻转局写成 `hard_parity.py generate --identities` 可直接用的格式；
  - 给 `--rerun-new <改后第二次根> --rerun-old <旧代码根>` 时，按第 3.2 节四格定性，打印最终判定行，并输出逐局报告 `<out>.episodes.md`（第 3.2 节「逐局报告」各列）；
  - 默认读各遍 `identities.jsonl` 里由 `Mover` 边生成边写的 sha 与 `verdict`（不重读 h5），在 GL 上秒级出判定行；翻转局类别先写 `flip_pending`；
  - `--local-ref-root artifacts/noise-baseline/gen`（只在本机给）：对已回传的翻转局复用 `compare_h5` 对照 a 遍 h5，把 `flip_pending` 细分为 `structural`／`diverge`／`gen_fail`；
- `scripts/parity/hard_pull.py` 加 `--identities <jsonl>`：只拉清单里的局目录与各遍顶层报告文件（不传时行为不变）。
- `scripts/parity/hard_parity.py`：`generate` 加 `--expect-ref`；`Mover.__init__` 载入参照，`Mover.handle` 在算出 sha 后写 `verdict`，`match` 时删本地大文件而不调 `_ship`，`flip` 时追加 `flips.jsonl` 并打印 `EPISODE_FLIP`；不给参数时代码路径不变。测试用假 `results.partial.jsonl` 与假 h5 覆盖 match／jitter_info／flip／失败局四种。
- `scripts/parity/noise_run.py ship --finalize`：`verdict=match` 的局不要求有 `SHIPPED`。
- 删除第 2.5 节所列子命令与函数；`selftest` 同步删掉对应自检项。
- 测试：`tests/lightweight/test_noise_gate.py` 加合成夹具六情形，阶段 6 由 T2 移到 `tests/parity/`。

**H 块（主会话）**：
- 一次性脚本放 scratchpad，生成三份清单。
- `hf buckets create` 建私有 bucket。参数先用 `/home/hongzefu/.local/bin/hf buckets create --help` 核实，并用绝对路径的 hf 1.8.0（venv 里的旧版没有 `buckets`）。
- 逐遍 `hf buckets sync artifacts/noise-baseline/gen/<遍> hf://buckets/HongzeFu/robomme-hard-v9-noise-baseline/<遍>`，三份清单用 `hf buckets cp`。
- 读回：`hf buckets list … -R` 比较大小与对象数，再逐对象下载到 scratchpad、核对 sha 后删掉。
- 对象数 = 1890 + 3 = 1893。

**主会话文档**：
- `docs/1003-noise-baseline.md` 第六节改成新闸门（10% 原文移到节末「历史判据」）；第七节比较命令改成 `gen-regress check`，`xhard0_manifest.json` 路径随 R 块更新；
- `1003-resource-cleanup-plan.md` 第二节保留清单补一行（本次已补）。

## 二、子代理分配表

派发前核对：`worktree.baseRef="head"`；主检出 `git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空（目前有未跟踪的 `docs/validation/newtask-v9/hf-20261003*` 属并行会话，届时它若仍未提交，按 CLAUDE.md 计划执行模式「有他人在途改动不派」交用户裁决）；`git check-ignore -q .claude/worktrees/probe`；记 `BASE`。

| 编号 | 目标 | 可写集合 | 禁触 | 依赖／合并顺序 | 验收（worktree 内，CPU） | 资源 |
|---|---|---|---|---|---|---|
| G | 逐局闸门 + 参照文件 + 噪声工具瘦身 | `scripts/parity/noise_gate.py`、`noise_run.py`、`noise_run_gl.sh`、`scripts/configs/noise-ref-20261003.json`（新）、`scripts/parity/hard_pull.py`（只加 `--identities`）、`scripts/parity/hard_parity.py` 的 `Mover` 类与 `generate` 参数段（只加 `--expect-ref`）、`tests/lightweight/test_noise_gate.py`、`test_noise_run_wrapper.py`、`hard_pull` 的测试 | `artifacts/noise-baseline/`（只读）、他块文件、`v8_manifest.py`／`v8_report.py` 内容 | 阶段 2，与 W1、W2 并行，第 1 个合并 | `pytest tests/lightweight/test_noise_gate.py tests/lightweight/test_noise_run_wrapper.py -q`；`gen-regress build-ref` 打印 `NOISE_REF=PASS …`（读主检出的 `artifacts/noise-baseline/gen`，绝对路径只读） | CPU，读约 170G |
| W1 | eval-official 清理 | `scripts/eval-official/` 下第 2.2、2.3 节所列文件（不含改名）；只测这些被删代码的测试文件 | 噪声工具；`run_v8_gl.sh`、`v8_report.py` 内容；他块文件 | 阶段 3 并行，第 2 个合并 | `pytest tests/lightweight/test_eval_official_env_client.py tests/lightweight/test_v8_eval_client.py tests/lightweight/test_v8_eval_manifest.py -q` | CPU |
| W2 | injection-dev 清理 | `scripts/injection-dev/` 下第 2.2、2.3 节所列文件（含 `eval_video_mover.py`、`site/v7_*`、`site/v8_site_catalog.py`）及对应测试 | 同上 | 阶段 3 并行，第 3 个合并 | `test_v8_delivery_flow`、`test_v8_site_catalog`、`test_hard_state_machine`、`test_v9_subset_specs` 定向 | CPU |
| W3 | parity 历史分支 | `scripts/parity/hard_regression.py`、`hard_parity.py` 中第 2.3 节所列分支（基于 G 合入后的版本）；`test_v8_regression_cmds.py`、`test_hard_parity*.py`、`test_v7_whitelist_semantics.py`；`tests/fixtures/v7_specs_sample/`、`_shared/v7_specs_fixture.py` | `env-digest` 三件套、`delivery_index`、`generate --tier v9|xhard0`、噪声工具 | 阶段 3，**等 G 合入后再派**（与 G 共用 `hard_parity.py`，同一文件不并行写），第 4 个合并 | 上述测试，并确认 `test_env_digest_compare`、`test_gate_set`、`test_noise_gate` 不受影响 | CPU |
| W4 | 包内 V7 清理 | `src/robomme_hard/` 中第 2.2、2.3 节所列；对应的 `test_v7_*`、`test_v8_specs_schema` | 交付规格五份、`TIER_MAX_STEPS` | 阶段 4，W1～W3 合入后派 | `test_v9_packaged_800`、`test_hard_builder_xhard0`、`test_xhard0_native`、各任务 xhard 测试 | CPU |
| R | 改名 | 第 2.4 节所列文件及全部引用点（含噪声工具路径常量、`site/*` 的 importlib 字符串、测试 import、`docs/1003-noise-baseline.md` 第七节路径） | 格式名、键名、判定行前缀 | 阶段 5 | 全部 CPU 测试 + `MAINT_NO_LEGACY` | CPU |
| T1 | 单元／契约／官方对齐测试重构 | `tests/unit/`、`tests/contract/`、`tests/upstream/`、`tests/conftest.py`、`tests/_shared/`；对照表（落 `docs/validation/maintenance-regress-<日期>/nodeid-map-T1.md`） | `tests/pipeline/`、`tests/gpu/`、`tests/parity/`、生产代码 | 阶段 6，与 T2 并行 | 第 4.5 节日常命令（只含 T1 目录部分） | CPU |
| T2 | 对拍／流水线／GPU 测试重构 | `tests/parity/`、`tests/pipeline/`、`tests/gpu/`（原 `tests/dataset/`）；对照表 `nodeid-map-T2.md` | T1 目录、生产代码 | 阶段 6，与 T1 并行 | `pytest tests/parity tests/pipeline -q` | CPU |
| 主会话 | H 上传、耗时基线、`pyproject.toml`、文档、GL 闸门实跑 | `pyproject.toml` pytest 段、各 README、`AGENTS.md`、待定清单、`docs/1003-noise-baseline.md` 第六节、本文 | — | 各阶段 | 验收表 | 阶段 7 两个 GL 占位席 |
| 审查 | 每块合并前一个 | 只读（sonnet） | 一切写入 | 每块一个 | `PRE_MERGE_REVIEW=PASS`、`MAINT_DEAD_BRANCH` | — |

共享文件裁决：
- `test_v8_regression_cmds.py` 归 W3，`test_v8_specs_schema.py` 归 W4，`test_noise_gate.py` 归 G；
- 跨块的测试文件以「被测代码在哪块」定归属；
- 阶段 6 之前不做测试目录搬迁；
- `pyproject.toml` 只归主会话。

## 三、闸门总表

| 时点 | 判定行 |
|---|---|
| 阶段 1 后 | `NOISE_HF_UPLOAD=PASS`、`NOISE_HF_READBACK=PASS` |
| 每块合并前 | `PRE_MERGE_REVIEW=PASS`；`git diff --name-only <BASE>..<TIP>` ⊆ 可写集合 |
| 每块合并后 | 现日常命令通过（阶段 6 前用旧命令，6 个已知失败照旧）；`UPSTREAM_GUARD=PASS`；`MAINT_SPECS=PASS`；`ls -1 scripts/*.py` 恰好四个入口；`POST_MERGE_REVIEW=PASS` |
| G 合并后 | `NOISE_REF=PASS` |
| 阶段 5 后 | `MAINT_NO_LEGACY=PASS` |
| 阶段 6 后 | `MAINT_CORE`、`MAINT_PIPELINE`、`MAINT_TEST_COVERAGE`、`MAINT_COLLECT` |
| 阶段 7 | 冒烟 2 局 `GEN_REGRESS` 子集通过 → 首跑 → `GEN_REGRESS=PASS`（v9、xhard0 各一行） |

## 四、预算（P3、P5）

| 项 | 乘式 | 轨迹 | reset 上限 |
|---|---|---|---|
| 冒烟（已确认） | V9 PickXtimes xhard1 seed 16100000 × 1 + xhard0 PickXtimes seed 510300 × 1 | 2 | 6 |
| 首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 1 档 × 3 局 | 129 + 48 = 177 | 531 |
| 第二次跑 | 每个出问题的局 ×（改后 1 + 旧代码 1），合计上限 | ≤ 20 | ≤ 60 |
| 合计 | — | ≤ 199 | ≤ 597 |

基础设施重试默认 0（节点故障时另报）。翻转局超过 10 个时，不进入重跑，直接交用户（此时通过条件 2 已经不可能满足）。其余阶段 0 条。

## 五、runbook

```bash
# 阶段 1（本机，主会话）
H=/home/hongzefu/.local/bin/hf
$H buckets create --help        # 核实私有参数后再建
for p in v9-a v9-b x0-a x0-b; do  # 实际执行时每遍一条命令，日志 tee 到 artifacts/noise-baseline/hf/
  $H buckets sync artifacts/noise-baseline/gen/$p hf://buckets/HongzeFu/robomme-hard-v9-noise-baseline/$p
done
# 阶段 7（GL；开工先占两席：1 A40／4 CPU／48G／48h，--gpu_cmode=shared，JobID 记入本会话清单）
# 两份代码（每条 git 单独执行）：<NOISE>=robomme_benchmark-noise 保持 f8f76fba 不动（旧代码对照）；
#   <MAINT>=NFS 新检出 robomme_benchmark-maint：git clone <本仓库 origin> <MAINT>；git -C <MAINT> checkout <合并后 HEAD sha>
#   改后代码一律用 <NOISE>/.venv/bin/python 加 PYTHONPATH=<MAINT>/src，先打印 robomme_hard.__file__ 确认以 <MAINT>/src/ 开头
# 下文 <克隆> 在改后代码的步骤里指 <MAINT>（解释器仍取 <NOISE>/.venv）
# 身份清单：uv run --no-sync python scripts/parity/gate_set.py export --set {v9,xhard0} --kind generate --out <文件>
# 生成：与 docs/1003-noise-baseline.md 第七节相同，--pass rg-v9 / rg-x0，--attempts 129／48，--resets 387／144，--retries 0
# 生成命令末尾加 --expect-ref <克隆>/scripts/configs/noise-ref-20261003.json，边生成边判定；Monitor 另盯 EPISODE_FLIP
# 生成结束、ship --finalize 之后汇总（GL，占位作业内辅助步骤，不带 --gpu_cmode=shared）：
srun --jobid=<占位作业> --overlap --ntasks=1 <克隆>/.venv/bin/python <克隆>/scripts/parity/noise_gate.py gen-regress check \
  --ref <克隆>/scripts/configs/noise-ref-20261003.json --set v9 --new <NFS>/gen/rg-v9 \
  --out <NFS>/regress/rg-v9.regress.jsonl --rerun-identities-out <NFS>/regress/rg-v9.rerun.jsonl
# 若 NEED_RERUN：rerun.jsonl（= flips.jsonl）作 --identities，在同一席位同一节点依次生成
#   rg-v9-new2：改后代码（maint 检出，借 noise 克隆 .venv + PYTHONPATH=<maint>/src，带 --expect-ref）
#   rg-v9-old2：旧代码（noise 克隆 f8f76fba 原样，不带 --expect-ref）
# 再 gen-regress check … --rerun-new <NFS>/gen/rg-v9-new2 --rerun-old <NFS>/gen/rg-v9-old2 汇总
# 只回传翻转局（无翻转时只拉报告）：
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/gen --dest artifacts/maint-regress \
  --segments rg-v9,rg-v9-new2,rg-v9-old2 --identities <NFS>/regress/rg-v9.rerun.jsonl
# 本机细分翻转类别：gen-regress check … --new artifacts/maint-regress/rg-v9 --rerun-new … --rerun-old … --local-ref-root artifacts/noise-baseline/gen
# 收尾：按清单 scancel 自己的两个 JobID；判定行与 regress jsonl 拷进留档后，NFS 暂存逐目录列名删除（不跨运行 glob）
```

Monitor 过滤词：`EPISODE_FLIP|NOISE_RUN_START|EXIT_CODE=|RUN_FRESH=|BUDGET=|NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|Traceback|Error`，每份日志各挂一个。

## 六、风险登记

| 风险 | 应对 |
|---|---|
| 删分支后，V9 路径上有地方隐式依赖被删常量 | 审查子代理逐文件核对 + 合成测试 + 阶段 7 实跑，三重兜底 |
| 改后代码在 GL 上换到新节点或新驱动，出现未见过的抖动 | 第二次跑同节点带旧代码对照，判为「环境变了」交用户；驱动与基线 595.71.05 不同时先报告用户再跑 |
| 噪声认定的翻转把真实小改动也放过（重跑恰好回到基线） | 改动造成的差异是确定性的，重跑回到基线说明改后代码仍能产出基线字节；放过的上限是 V9 2 局、xhard0 1 局，且逐局列出 |
| 参照文件被手改 | 顶层 canonical sha 防篡改；`test_noise_ref.py` 守三类计数 |
| HF 上传中断 | `hf buckets sync` 断点续传；以读回判定为准 |
| 改名让 `docs/validation/**` 的历史命令无法原样复现 | 用 `scripts/README.md` 的新旧名对照表说明 |
| `run-fresh` 与评估抽取耦合，删不干净 | G 块先核实；如有耦合，只改成认 gen 输出 |

## 七、盲区诚实清单

- 新闸门只覆盖 177 局，PASS 不等于 800 局逐字节等价。
- 稳定局的认定只基于两遍样本；某局真实抖动率很低时可能没被观察到，只能靠第二次跑兜底；第二次只跑 1 次改后代码，某局真实抖动率高于一半时可能被判成「每次都不同」而交用户，不会被误放过。
- 借用 noise 克隆 venv 跑改后代码依赖 `PYTHONPATH` 覆盖 editable 指向；起跑前打印 `__file__` 核实，不符即停。
- 评估侧不实跑，前提是 `--v8` 主路径不改；审查若发现必须改主路径，暂停并另报。
- 耗时数字（120 s 目标、约 8 分钟全量）在阶段 0 实测前都是估计。
- `robomme-hard-parity` 的删除状态以并行会话为准，本计划不验证、不操作。
- 尚未开工的 Oracle 计划依赖 `env_client.py`／`run_seat.sh` 的非 v8 `--identities` 路线，本计划保留它；该计划引用的 `policy_replay.py::extract_defs` 删除后需从 git 历史取回。

## 八、留档与 commit 纪律

- 每块合并提交按 `<大>.<小> <中文描述>` 递增，body 详写（第 11 条）；子代理提交用 `sub/<编号>: ` 前缀。
- 阶段 1 留档：`docs/validation/noise-baseline-20261003/hf.md`，内联判定行原文。
- 阶段 7 运行留档：`docs/validation/maintenance-regress-<日期>/README.md` + `records/`（regress jsonl、重跑身份、来源报告、预算账本）。h5 不进 git，按「只保留最终产物」处理：闸门 PASS 后新跑的 h5 是否删除，交用户决定。
- 自检：`grep -c '^# 第一部分\|^# 第二部分' 1003-code-test-maintenance-todo.md` 必须等于 2。
