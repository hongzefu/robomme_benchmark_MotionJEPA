代码与测试维护计划（2026-10-03）

> 三件事：①讲清并处理步数上限表 `TIER_MAX_STEPS`；②**全代码库**清理只服务 V7／V7.5／V8 历史的代码（不只测试）；③**彻底重构全部测试**。另写改完后如何保证生成结果仍在噪声范围内一致。
>
> 用户原话（2026-10-03，按时间）：「你这个项目只需要部署上限的问题和清理V7V8的就用例以及短测内容的问题就是纯代码的改动」「然后写的时候也分开写这三个点分别怎么改。然后如何保证噪声的一致性」「完全彻底重构这个计划只保留我说的这些部分。」「TMMAXTEP这个问题我没有看懂。然后这个清理B7V8指的是所有代码库里面全部清理了不要只清理测试然后核心短测内容怎么改我也没看懂就是你要详细的说可以彻底重构所有的test」
>
> 锚点 `PLAN_BASE=9a765cc4`，分支 `newtaskRelease-taskV9`。事实来源：2026-10-03 三份只读盘点（包内代码、scripts、tests），未跑任何测试。实施须用户说「执行」；文末「待你决定」四项先定。

# 第一部分（给人看）

## 总览与已定口径

一句话：先等噪声基线冻结；然后分块删掉 V7／V8 专用代码、把仍在用但名字带 v8 的文件改成中性名、把测试按「测什么」重新分层并合并；最后用噪声基线的生成闸门跑一遍，证明 V9 生成结果没有超出噪声。

1. **清理判据不是文件名，是「谁还在调用它」**：被 V9 生成、V9 评估、V9 站点（8082）、噪声基线工具、官方对拍任一调用的，保留；只被 V7／V8 历史调用的，删。git 历史随时可取回。
2. **不改的东西**：`src/robomme/`（P2）；三个上游入口（P1）；交付规格五份与 HDF5 的字节；已封存产物里的格式名与键名（`hard-specs/4`、`v8-delivery/1`、`v8-shard/1`、`v9-eval-reused/1`、`reused.json` 的 `v8_manifest`／`v8_key` 等键——它们的 sha256 被清单钉住）；判定行前缀 `V8_*`（V9 闸门沿用）。
3. **噪声基线工具在测量期间一字不动**：`scripts/parity/noise_gate.py`、`noise_run.py`、`noise_run_gl.sh`、`gate_set.py`，以及它们依赖的 `hard_parity.py generate` 的 v9／xhard0 路径、`hard_regression.py` 的 `delivery_index` 与 `env-digest` 三件套、`hard_pull.py`、`train_split_runner/worker/config`。
4. **只测生成噪声**：沿用噪声基线方案的用户决定「之后改代码也只测生成的噪声就可以」。
5. 局数一律写乘式（P5）。

## 一、步数上限表 `TIER_MAX_STEPS`：到底是什么问题

### 1.1 「步数上限」是什么

评估时，策略每一步给一个动作、环境走一步。为了不让一局无限跑下去，环境有一个上限：执行段走满 N 步还没成功，就判这局 timeout（失败）。演示段的步数不计入。N 就是 `max_steps`。

### 1.2 现在有两套写法，数值不一样

**写法一：公开评估入口直接写死一个数。**
- 官方 `scripts/evaluation.py`（与上游逐字节相同，不能改）：`max_steps=1300`。
- 我们的 `scripts/evaluation_hard.py`：12.339 起构造 builder 时写死 `max_steps=1600`，每局不再单独传。用户当时原话：「max_steps 应该是一个固定的数值……不需要再从 episode 里面读」「可以，全部 1600」。

**写法二：包里一张按难度档查的表。**
- `src/robomme_hard/env_record_wrapper/hard_specs.py::TIER_MAX_STEPS = {xhard0: 1300, xhard1: 1600, …, xhard5: 1600}`。
- xhard0 就是官方的 hard 档，所以沿用官方 1300；xhard1～5 是新值档，抽样时已经把执行步超过 1600 的候选过滤掉，所以给 1600。

### 1.3 谁还在用这张表

公开入口已经不用它了，但以下地方仍然逐局查它：

| 使用者 | 怎么用 |
|---|---|
| `scripts/eval-official/v8_manifest.py` | 生成评估清单时，每局写一个字段 `effective_max_steps = TIER_MAX_STEPS[tier]` |
| `scripts/eval-official/env_client.py::tier_max_steps`、`EnvSession.step` | 起环境前核对清单里的 `effective_max_steps` 与表相等；跑的时候走满这么多步后，第 N+1 步不再进环境，记 timeout |
| `scripts/parity/hard_regression.py` | `reset-replay`、`eval-smoke`、`step-headroom` 三个子命令与 `env-digest` 内部按表取上限 |
| `scripts/injection-dev/site/v8_subgoal_lengths.py` | 站点出图时 xhard0 的上限取表值 |
| 3 个测试 | `test_xhard0_native.py`、`test_v8_specs_schema.py`、`test_v9_packaged_800.py` 各把表值断言一遍 |

已经跑完的评估就是按这张表跑的：V9 两模型 800 局评估执行段严格 1600 步（`docs/validation/v9-two-policy-gl10-20261002-01/launch.md`）；xhard0 的 16 任务 × 1 档 × 12 局 = 192 局评估按 1300 步。生成链路不读这张表（生成用规格 header 里的 `exec_cap`＝1600）。

### 1.4 所以问题是什么

不是 bug，是**两处口径并存**：公开入口说「全部 1600」，评估流水线说「xhard0 1300、其余 1600」。xhard1～5 两边都是 1600，没有冲突；唯一不一致的是 xhard0：用公开入口跑是 1600，用评估流水线跑是 1300。这件事 10-02 记成待定 B5。

### 1.5 三个选项

| 选项 | 改什么 | 结果 |
|---|---|---|
| **(a) 保留表（推荐）** | 代码不动；README 写明「公开入口固定 1600；表只服务评估流水线，xhard0 1300 是为了和官方 hard 档、和已跑的 192 局评估同口径」；三处重复断言收成一处 | 零行为变化；已有评估记录都能原样复现 |
| (b) 表拉平成全 1600 | `hard_specs.py` 一行，三个测试，`env_client` 校验 | 流水线的 xhard0 变 1600；和已跑的 192 局（1300）不再同口径，以后 xhard0 评估结果不能和历史直接比 |
| (c) 删表，改单常量 1600 | 包代码与上表全部使用者 | 同 (b)，改动最多 |

推荐 (a)：xhard0 用 1300 是有意的（和官方同档对齐），拉平只换来「看起来统一」，代价是 xhard0 评估与历史断代。

## 二、全代码库清理 V7／V8

### 2.1 清理后的样子

- 规格只剩一种格式 `hard-specs/4`（V9 用的就是它），`/2`（V5～V6 单档）、`/3`（V7 母布局派生）的读写校验代码全部删掉。
- 「母布局 → 派生低档」「分层回注」「白名单」「外环弧」「BinFill 嵌套」这一整套 V7 机制从包和脚本里删掉。
- V7.5 评估的一次性车道脚本、编排器、认领队列删掉。
- V8 专用的分片合并、V8 1070 局清单的构建分支、V8 单次评估的站点分支删掉。
- 名字带 v8、实为 V9 现行的文件和常量改成中性名（见 2.4）。

### 2.2 整文件删除

| 位置 | 文件 | 为什么能删 |
|---|---|---|
| `scripts/eval-official/v75-lanes/` | 整个目录（`gl/` 25 个 .sh、`local/` 25 个 .sh、README） | V7.5 评估当时的一次性车道脚本，无代码、无测试引用；V8／V9 评估都是重写的席位脚本 |
| `scripts/eval-official/` | `orchestrate.py`、`watchdog.sh` | V7.5 通用编排器，只被 v75-lanes 调用 |
| 同上 | `claim_queue.py` | V7.5 NFS 认领队列；先删 `env_client.py`、`run_seat.sh` 的 `--queue` 分支 |
| 同上（待你决定 Q2） | `official_observer/`（8 个文件）、`policy_replay.py`、`run_policy_replay.sh`、`step6_summary.py`、`compare.py` | V7.5 的 xhard0「官方路线」旁路录制、开环回放与第 6 步汇总；它们依赖的三份官方检出与 `artifacts/v7.5eval/` 已在资源清理中删掉，现在已经跑不起来 |
| `scripts/injection-dev/` | `derive_specs.py` | V7 母布局派生（产 `/3` 规格），V9 每档独立冻结不用它 |
| 同上 | `_report.py` | 生产代码零引用，只有一个测试导入 |
| 同上 | `v8_watchdog.py` | V8 gen1 接续脚本的看门狗，V9 留档无使用记录 |
| `scripts/injection-dev/site/` | `v7_site.py`、`v7_site.html`、`v7_site_catalog.py`、`v7_subgoal_lengths.py`、`v7_site_browser_check.py`、`v7_oracle_browser_check.py` | V7 站点全套，只互相引用 |
| `src/robomme_hard/env_metadata/test-hard/` | `layout_whitelist.json` | V7 白名单，V9 builder 不读；交付规格五份不动 |
| `tests/` | `_shared/v7_specs_fixture.py`、`fixtures/v7_specs_sample/`（先把 `test_v8_regression_cmds.py` 里借它做的反例改用 `/4` 夹具）、`fixtures/injection_legacy/`（全库无引用） | 只服务 V7 测试 |

### 2.3 文件内删分支（文件保留）

| 文件 | 删掉 | 保留 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | `SCHEMA`(/2)、`SCHEMA_V7`(/3)、`SCHEMAS`、`V7_TIERS`、`V7_XHARD4_ONLY`、`V7_SEED_OFFSET`、`load_specs_v7`、`_check_layout_parent`、`validate_specs` 的 /2 /3 分支、`IDENTITY_KEYS_BY_SCHEMA` 的 /2 /3 项、`seed_rule_for`／`SEED_PROFILES` 的 v5／v7 项；`V8_CELLS`／`_v8_cells`（先把 `_v9_cells` 里对它的循环与集合断言改成直接用档位表）及 `CELL_TABLES["v8"]` | `/4` 读写校验、V9 格表、seed 偏移、`TIER_MAX_STEPS`（按 Q1） |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | `layout_parent` 透传与 v7 注释 | 只读 `/4` 的现行逻辑 |
| `src/robomme_hard/robomme_env/utils/episode_spec.py` | `SPEC_KIND_LAYERED`、`NEST_RULES`、`nest_binfill_targets`、`nest_outer_arc`、`SpecRecorder` 的 layered 分支 | `native-newvalue` 全量规格（V9 现行） |
| `BinFill.py`、`utils/unmask_swap_xhard.py`、`utils/unmask_distractor_sampler.py` | layered 判断与 `_choose_outer_arc` | 其余（V9 现行取值） |
| `scripts/injection-dev/_freeze.py` | `freeze()` 的 /2、/3 分支、`_FOUR`、`DEFAULT_SELECT` | /4、`V8_DEFAULT_CANDIDATES`（V9 仍用来核格局数）、分层选签 |
| `scripts/injection-dev/freeze_specs.py` | `--seed-profile v7`、`candidates_v7`、`--whitelist`；默认 profile 改 v8 | v8 profile（V9 MoveCube 就用它） |
| `scripts/injection-dev/_rollout.py` | V7 候选池整段（`initial_pool`、`sync_drop_and_backfill`、`run_continue_v7`、`V7_DELIVERY_SET`）、`run_replay` 的 v7 根、`merge_v8` 与 V8 四席分片表 | `split_v8`、`aggregate_v8`、`load_v8_root`、`run_continue_v8`（V9 现行） |
| `scripts/injection-dev/generate_h5.py` | `replay`／`continue` 的 v7 分支、`--mode merge` | `split`／`continue`／`aggregate`（V9 用） |
| `scripts/injection-dev/eval_video_mover.py` | `--mode v7`；默认改 v8 | v8 账本模式（V9 用） |
| `scripts/injection-dev/v8_continue_after_gen.py` | V8 gen1 专用的等报告、守卫步骤与心跳 | `--site-only --cells v9` 建站路径（8082 用） |
| `scripts/injection-dev/site/v8_site_catalog.py` | V8 单次评估运行分支（`eval_run`、`xhard0_eval`） | V9 复用口径 |
| `scripts/eval-official/env_client.py` | `--queue`、`--canary` 分支与 `claim_queue` 导入 | `--v8` 模式；非 v8 的 `--identities` 路线（未开工的 Oracle 计划要用） |
| `scripts/eval-official/run_seat.sh` | `--queue`、`--canary`、`--client-per-task`、`--no-record`；默认 `SMVLA_PY` 指向已删目录，改成必须显式传 | `--v8` 与非 v8 `--identities` 路线 |
| `scripts/eval-official/v8_manifest.py` | V8 1070 局 `build()` 分支 | `build_v9` 与读取 V8 清单做对账的函数 |
| `scripts/parity/hard_regression.py` | `layout-shared`、`prefix-geometry` 两个子命令及其辅助函数；`_step_headroom_v7` 与 `--v7`；`reset-replay`／`eval-smoke` 的 v7 口径；`xhard0-eval-parity`（随 Q2） | `delivery-set`、`tier-values`、`reset-replay`、`xhard0-reset-parity`、`step-headroom`、`movecube-layout`、`env-digest` 三件套 |
| `scripts/parity/hard_parity.py` | `generate --tier xhard`（V6 四档）与 `--tier v8` 档、`compare` 里对应分支、`import-delivery --tier v8` | `native`（官方三档对拍）、`xhard0`、`v9`、`anchor`、`binding`、`export-xhard0-manifest`；`publish` 归 HF 发布方案处理，本计划不动 |

### 2.4 改名（文件仍在用，只是名字误导）

| 现名 | 新名 |
|---|---|
| `scripts/eval-official/run_v8_gl.sh` | `run_eval_gl.sh` |
| `scripts/eval-official/v8_manifest.py`／`v8_report.py` | `eval_manifest.py`／`eval_report.py` |
| `scripts/injection-dev/v8_continue_after_gen.py` | `site_build.py` |
| `scripts/injection-dev/site/v8_*.py`、`v8_site.html` | 去掉 `v8_` 前缀 |
| `scripts/injection-dev/site/v7_render_xhard0.py` | `render_xhard0.py`（V9 站的 xhard0 视频由它产出） |
| `scripts/configs/newtask-v7/xhard0_manifest.json` | `scripts/configs/xhard0/xhard0_manifest.json`（内容是官方 xhard0 192 局清单，不是 V7 数据） |
| `hard_specs.py`：`V8_EXEC_CAP`、`V8_TIERS`、`SCHEMA_V8`、`V8_LAYOUT_RULE`、`load_specs_v8`、`_validate_specs_v8` | `EXEC_CAP`、并入 `TIERS`、`SCHEMA`、`LAYOUT_RULE`、`load_specs`、`_validate_specs` |
| `tests/_shared/v7_tier_values.py` | 并入新测试结构（见第三节） |

改名后同步改所有引用点，包括 `noise_run.py`、`noise_gate.py` 里按路径加载 `v8_manifest.py`／`v8_report.py` 的常量，以及 `site/*` 之间按文件名 `importlib` 加载的字符串，所以改名必须等噪声基线测完（口径 3）。`scripts/README.md` 加一张新旧名对照表；`docs/validation/**` 历史留档里的旧命令不回改。

## 三、测试彻底重构

### 3.1 现在的测试有什么问题

- **太慢**：日常命令 `pytest tests/lightweight/ -m 'not gpu and not slow'` 实测 476.7 s（1758 passed／6 failed／3 skipped），超过 5 分钟预算，280 s 限时在 85% 处被截断。慢的不是断言多（约 450 条纯函数断言合计几十秒），而是少数文件起子进程、`sleep` 等超时被杀（`test_v8_eval_orchestration`、`test_v8_continue_fixtures`、`test_noise_run_wrapper`、`test_eval_official_orchestrate`、`test_eval_official_run_seat`、`test_official_observer`、`test_registry_owner` 等），它们没有标 `slow`。（此为按代码特征估计，阶段 0 实测校准。）
- **6 个长期失败**，自 `30f36e44` 起每次都失败，靠「与基线相同」放行。
- **按版本号命名、同一个东西散在多处**：`test_v4_xhard_binfill.py`、`test_v5_xhard_binfill.py`、`test_v7_binfill_nested.py` 测的是同一个任务；约 45 个 v4／v5／xhard 文件其实只对应 14 个任务。
- **重复断言**：`TIER_MAX_STEPS` 在 3 处、`EXPECTED_CELLS` 合计在 4 处各断一遍。
- **测历史**：9 个 `test_v7_*`、5 个 `test_v8_eval_*` 的一部分、`test_v8_native_blocks_unchanged` 等守的是 V7／V8 链路；4 个用例靠 `monkeypatch` 把格表钉回 V8 的 1070／1262 才能过。
- **marker 标错**：`test_ChoiceLabel.py` 等标了 `gpu` 却不起环境；起子进程的反而没标 `slow`。
- **收集范围**：裸 `pytest` 会扫到 `third_party/`，报 53 个收集错误。
- `tests/dataset/test_eepose_error_handling.py` 断言 `status == "error"`，与官方实现矛盾，只是因为从不进日常口径才没暴露。
- 没有任何测试守 `scripts/parity/upstream_guard.py`。

### 3.2 新结构：按「测什么」分目录

| 目录 | 放什么 | 日常门禁 | 预计耗时 |
|---|---|---|---|
| `tests/unit/robomme/` | 官方 `src/robomme` 行为：TaskGoal、ChoiceLabel、ChoicePositionNearest、pixel_mapping、StopcubeIncrement、waypoint 去重、choice_action 流程、subgoal 序数 | 是 | 秒级 |
| `tests/unit/hard/` | `src/robomme_hard` 按任务一个文件：`test_binfill.py`、`test_insertpeg.py`、`test_movecube.py`、`test_pickswing.py`（PickXtimes、SwingXtimes、PickHighlight）、`test_unmaskswap.py`、`test_unmask.py`、`test_videorepick.py`、`test_videoplace.py`、`test_stopcube.py`、`test_patternlock_routestick.py`、`test_collision.py`、`test_shared_sampling.py`、`test_xhard_utils.py`、`test_sampling_config.py`、`test_difficulty_seed.py`、`test_episode_spec.py`、`test_taskgoal_hard.py` | 是 | 几十秒 |
| `tests/contract/` | V9 规格与身份契约：`test_v9_spec_contract.py`（合并 `v9_packaged_800`、`hard_builder_xhard0`、`xhard0_native`、`v8_specs_schema` 的 V9 部分；`TIER_MAX_STEPS`、`EXPECTED_CELLS`、800／992 局数只在这里断言一次）、`test_tier_values.py`（取代 `_shared/v7_tier_values.py`）、`test_v9_subset_specs.py`、`test_scripts_do_not_import_tests.py` | 是 | 十几秒 |
| `tests/upstream/` | 官方对齐：新增 `test_upstream_guard.py`（`src/robomme` 与三个入口与官方 `1fadc0ec` 逐字节相同）、`test_official_behaviors.py`（改写后的 step_error 用例）、record_* 三个源码扫描用例、`test_train_split_parity.py` | 是 | 秒级 |
| `tests/parity/` | 对拍设施：h5 全字段比较器、`hard_parity`、`comparator_scope`、`env_digest_compare`、`gate_set`、`noise_gate`、`hard_regression` 的 V9 子命令 | 纯合成数据的进门禁；起子进程的标 `slow` | 门禁部分几十秒 |
| `tests/pipeline/eval/` | 评估流水线：`env_client`、`mme_client`、`smvla_client`、`recorder`、`eval_manifest`、`eval_report`、`eval_video_mover`、`run_seat`（同一被测脚本的 `eval_official_*` 与 `v8_eval_*` 合并成一个文件） | 否（改评估代码时跑） | 分钟级 |
| `tests/pipeline/gen/` | 生成流水线：状态机、分片聚合、`noise_run` 包装、站点建站 | 否（改生成或站点时跑） | 分钟级 |
| `tests/gpu/` | 需要 GPU／ManiSkill 环境：原 `tests/dataset/` 全部、`TaskGoalI_isList`、`wrapper_chain`、gym.make 用例 | 否（有 GPU 时跑） | — |

公共夹具：`tests/_shared/repo_paths.py` 并入根 `tests/conftest.py`；`_shared/dataset_generation.py` 随 `gpu/` 搬走；`tests/lightweight/` 目录取消；`tests/README.md` 重写为上表。

### 3.3 现有文件去向

- **删除（只测被删代码或历史）**：`test_v7_candidate_pool`、`test_v7_freeze_schema`、`test_v7_layered_recorder`、`test_v7_site_catalog`、`test_v7_whitelist_semantics`、`test_v7_outer_arc`、`test_v7_binfill_nested`、`test_v8_native_blocks_unchanged`、`test_native_restore_step2`、`test_audit_fix`、`test_audit_fix_scripts`、`test_eval_official_orchestrate`、`test_eval_official_queue`；Q2 选删时再加 `test_official_observer`、`test_eval_official_policy_replay`、`test_eval_official_step6`、`test_eval_official_compare`。
- **先抽出 V9 部分再删壳**：`test_v7_seed_rule`、`test_v7_tier_values`、`test_v8_specs_schema`、`test_v8_difficulty_tiers`、`test_v8_regression_cmds`、`test_v8_delivery_flow`、`test_v8_continue_fixtures`、`test_v8_site_catalog`、`test_v8_append_candidates`；4 个 `monkeypatch` 钉 V8 格表的用例改断言 V9（800／992）或删除。
- **合并**：v4／v5／xhard 按任务合并（约 45 个文件收成 17 个）；`eval_official_*` 与 `v8_eval_*` 按被测脚本合并。
- **抽出前先列「旧 nodeid → 它守的契约 → 新 nodeid／删除理由」对照表**，交你过目后才删；仍有用的负例（空集、重复／漏身份、错签名、错绑定）必须在新位置有对应用例。

### 3.4 6 个长期失败逐条改法（只改测试，官方源码不动）

| 测试 | 为什么失败 | 改法 |
|---|---|---|
| `test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal` | 官方 `task_goal.py::get_language_goal` 对未知环境返回 `[]`，测试期望 `[""]` | 断言改为 `[]`，函数名改「未知环境返回空列表」，进 `unit/robomme/` |
| `test_TaskGoal.py::test_swingxtimes_multiple` | 官方文本是 `back-and-forth`，测试写 `back and forth` | 改成官方文本 |
| `test_step_error_handling.py::test_step_error_returns_status_error` | 官方 `DemonstrationWrapper.step` 没有 try（docstring 说会捕获，实现没有） | 改成「锁定官方现状」：断言 `step` 内没有 try、异常向上抛，进 `upstream/`，注明是官方行为；同文件两条只测内联复刻代码的同义反复用例删除 |
| `test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except` | `dataset_replay.py` 实际写法是 `try: env.step … except Exception` 加 `info.get("status", "unknown")` | 拆开：`run_example.py` 保留原断言；`dataset_replay.py` 改为断言官方现状 |
| `test_v8_eval_report.py::test_zz_summary_line`、`test_v8_eval_video_mover.py::test_zz_summary_line` | 断言整个 pytest 会话失败数为 0，前面任何文件失败就连带失败 | 删掉这种「会话汇总」用例；判定行由 pytest 退出码生成 |

`tests/gpu/test_eepose_error_handling.py` 同样改为断言官方现状（异常向上抛）。

### 3.5 日常门禁与配置

- `pyproject.toml::tool.pytest.ini_options`：`testpaths = ["tests"]`（不再扫 `third_party/`）；markers 改为 `slow`、`gpu`、`pipeline`；`-m` 默认不变，目录本身就是分层。
- 日常命令：`timeout 280s uv run --no-sync python -m pytest tests/unit tests/contract tests/upstream tests/parity -m 'not slow and not gpu' -q --durations=20`，目标 ≤ 120 s。
- 改评估代码加跑 `tests/pipeline/eval`；改生成或站点加跑 `tests/pipeline/gen`；有 GPU 时跑 `tests/gpu`。
- `AGENTS.md`「覆盖第 4 条」与 `tests/README.md` 同步改。

## 四、怎样保证噪声一致性

目标：清理和重构完成后，V9 与 xhard0 的生成结果与改前相比，变化不超过「同一份代码重跑两遍本来就会有的差别」。分四层保证：

**第 1 层：没改的文件，字节相同。** 合并后跑 `git diff --name-only <BASE> <HEAD> -- src scripts`，逐个文件归到第二节的删除／删分支／改名三张表之一；表外出现的文件即越界，判 `MAINT_SCOPE=FAIL`。`uv.lock` 必须零 diff。

**第 2 层：改了的文件，只删 V9 走不到的分支。** 每个删分支的文件，审查子代理对照「V9 调用入口」逐个核对被删函数在 V9 路径上不可达：
- 生成入口：`generate_h5.py --mode split|continue|aggregate`、`v9_subset_specs.py`、`hard_parity.py generate --tier v9|xhard0`；
- 规格入口：`BenchmarkEnvBuilder(dataset="test-hard")` 读 `/4`；
- 评估入口：`run_seat.sh --v8`、`env_client.py --v8`。
- 判定行 `MAINT_DEAD_BRANCH=PASS files=<n>`。

**第 3 层：测试证明 V9 现行路径行为不变。** `tests/contract/` 守住规格、格表、局数、seed 规则、档位取值；`tests/pipeline/gen/` 用合成夹具跑生成状态机与分片聚合；`tests/pipeline/eval/` 守住评估客户端的步数截断与账本。这三组在重构前后都要通过，且「旧 nodeid → 新 nodeid」对照表保证覆盖不缩水。

**第 4 层：真跑一遍生成噪声闸门。** 前三层是静态和合成数据的论证，最后用噪声基线方案冻结的判据实跑：
- 时机：噪声基线 `NOISE_BASELINE=PASS`、线冻结进 `scripts/configs/noise-baseline.json` 之后；全部清理、改名、测试重构合并之后只跑一次。
- 内容：`noise_gate.py check-gen`，两批固定检查集各重新生成一遍——V9 的 43 格 × 3 局 = 129、xhard0 的 16 任务 × 1 档 × 3 局 = 48，共 129 + 48 = 177 条轨迹；GL A40、4 worker，与基线同条件。
- 判据（`GEN_NOISE_GATE`）：structural 与 unknown 两类必须为 0；diverge + gen_fail ≤ 冻结的线；gen_fail ≤ 冻结的线。
- 预算：轨迹 177 条，reset 上限按每条 3 次计 177 × 3 = 531 次；超 P3 阈值，须事先授权（「待你决定」Q4）。
- FAIL 时：不改线、不改判据，按分任务个数定位到哪块改动，回退或修该块后重跑，重跑另报预算。

**评估侧**：按用户决定只测生成噪声，评估侧不跑真实模型。评估代码只删了 `--queue`／`--canary` 这类 V9 不传的开关分支，由第 2、3 层保证；`--v8` 主路径不改。

**`TIER_MAX_STEPS`**：选 (a) 时不涉及任何运行时代码，噪声不受影响。

## 验收

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| 改动不越界 | `git diff --name-only <BASE>..<HEAD>` 逐个归入第二、三节清单 | `MAINT_SCOPE=PASS files=<n>` |
| 官方源码与入口未动 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `UPSTREAM_GUARD=PASS` |
| 交付规格未动 | 五份 `specs.jsonl` sha256 与改前相同 | `MAINT_SPECS=PASS changed=0` |
| scripts 顶层仍四入口 | `ls -1 scripts/*.py` | 恰好四个 |
| 删的分支 V9 走不到 | 审查子代理逐文件核对 | `MAINT_DEAD_BRANCH=PASS files=<n>` |
| 无残留引用 | `grep -rn "load_specs_v7\|SCHEMA_V7\|v75-lanes\|claim_queue\|derive_specs\|v7_site" src scripts tests` 为空 | `MAINT_NO_LEGACY=PASS` |
| 覆盖不缩水 | 旧 nodeid 对照表每行有去向 | `MAINT_TEST_COVERAGE=PASS` |
| 6 个失败消失、日常门禁够快 | 第 3.5 节日常命令 | `MAINT_CORE=PASS failed=0 wall_s=<实测>`（≤120） |
| 流水线测试通过 | `pytest tests/pipeline -q` | `MAINT_PIPELINE=PASS failed=0` |
| 收集无错误 | `pytest --collect-only -q` | `MAINT_COLLECT=PASS errors=0` |
| 生成噪声 | `noise_gate.py check-gen` | `GEN_NOISE_GATE=PASS` |

## 步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 定「待你决定」四项；跑一次现状全量测试取逐文件耗时（`--durations=0`，CPU，tmux，约 8 分钟） | 决定落档；耗时表落 `artifacts/maintenance/` |
| 1 | W1～W3 并行：scripts 三块删除与删分支（不碰噪声工具与改名） | 各块定向测试通过，`PRE_MERGE_REVIEW=PASS` |
| 2 | W4：`src/robomme_hard` 删 V7 常量与 layered 机制（依赖阶段 1 先删掉调用方） | 同上，`MAINT_SPECS=PASS` |
| 3 | T1、T2：测试重构（新目录、合并、6 个失败、对照表） | `MAINT_CORE`、`MAINT_PIPELINE`、`MAINT_TEST_COVERAGE` |
| 4 | 等噪声基线冻结 → R：改名（含噪声工具的路径常量） | 全部测试通过、`MAINT_NO_LEGACY=PASS` |
| 5 | 生成噪声闸门实跑一次 | `GEN_NOISE_GATE=PASS` |
| 6 | 文档：`scripts/README.md`（含新旧名对照）、`scripts/parity/README.md`、`src/robomme_hard/README.md`、`tests/README.md`、`AGENTS.md`、待定清单 B5／C1／C2 结案 | 验收表全部判定行 |

## 子代理分工与合并（简述）

拆成七块，按文件切开、互不重叠：W1 管 `scripts/eval-official/`，W2 管 `scripts/injection-dev/`，W3 管 `scripts/parity/` 里 `hard_regression.py` 与 `hard_parity.py` 的历史分支，W4 管 `src/robomme_hard/`；T1 管单元与契约测试，T2 管流水线与 GPU 测试；R 做改名。W1～W3 先并行，各自顺带删掉只测自己被删代码的测试文件；W4 等它们合入后再做（它删的常量 W1～W3 的文件还在用）；T1、T2 在全部代码清理合入后做；R 最后做，且要等噪声基线测完。每次合并前一个只读审查子代理核对改动是否越出该块的文件清单、被删分支是否 V9 走不到；合并后主会话跑日常门禁、`UPSTREAM_GUARD`、`MAINT_SPECS`。

## 待你决定

| 编号 | 问题 | 推荐 |
|---|---|---|
| Q1 | 步数上限表选 (a)／(b)／(c)（第 1.5 节） | (a) 保留 |
| Q2 | V7.5 xhard0「官方路线」复核工具（`official_observer/`、`policy_replay.py`、`run_policy_replay.sh`、`step6_summary.py`、`compare.py`、`hard_regression.py xhard0-eval-parity`）删不删。它们依赖的官方检出与 `artifacts/v7.5eval/` 已被资源清理删掉，现在跑不起来；资源清理时你说过「xhard0 也都要保留」，指的是产物，这里问的是代码 | 删（git 历史可取回） |
| Q3 | 名字带 v8 的现行文件和常量是否改名（第 2.4 节） | 改，放在噪声基线测完之后 |
| Q4 | 第四节第 4 层的生成噪声闸门实跑授权：177 条轨迹（V9 43 格 × 3 局 + xhard0 16 任务 × 1 档 × 3 局）、reset 上限 531 次、GL A40 一个占位席 | 授权 |

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`、`scripts/{dataset_replay,evaluation,run_example}.py`、交付规格五份、`uv.lock`；不改格式名、`reused.json` 键名、`V8_*` 判定行前缀。
- R2：噪声基线 `NOISE_BASELINE=PASS` 之前，不改第一部分口径 3 列出的噪声工具及依赖路径，不做 R 块。
- R3：阶段 1～4 只跑 CPU 测试；生成闸门只在阶段 5、经 Q4 授权后跑。
- R4：不新增 `scripts/` 顶层文件；`scripts/` 不得 import `tests/`。
- R5：worktree 内用 `UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync`，先打印 `robomme_hard.__file__` 核实指向 worktree。

## 一、子代理分配表

`BASE` 于派发前记录；派发前核对 `worktree.baseRef="head"`、主检出 `git status --short --ignore-submodules=dirty` 为空、`.claude/worktrees/` 被忽略。

| 编号 | 目标 | 可写集合 | 禁触 | 依赖／合并顺序 | 验收（worktree 内，CPU） | 资源 |
|---|---|---|---|---|---|---|
| W1 | eval-official 清理 | `scripts/eval-official/` 下第 2.2、2.3 节所列文件（不含改名）；只测这些被删代码的测试文件 | 噪声工具；`run_v8_gl.sh`、`v8_report.py` 内容；他块文件 | 阶段 1 并行 | `pytest tests/lightweight/test_eval_official_env_client.py tests/lightweight/test_v8_eval_client.py tests/lightweight/test_v8_eval_manifest.py -q` | CPU |
| W2 | injection-dev 清理 | `scripts/injection-dev/` 下第 2.2、2.3 节所列文件（含 `eval_video_mover.py`、`site/v7_*`、`site/v8_site_catalog.py`）；对应测试 | 同上 | 阶段 1 并行 | 相关 `test_v8_delivery_flow`、`test_v8_site_catalog`、`test_hard_state_machine`、`test_v9_subset_specs` 定向 | CPU |
| W3 | parity 历史分支 | `scripts/parity/hard_regression.py`、`hard_parity.py` 第 2.3 节所列分支；`test_v8_regression_cmds.py`、`test_hard_parity*.py`、`test_v7_whitelist_semantics.py`；`tests/fixtures/v7_specs_sample/` 与 `_shared/v7_specs_fixture.py` | `env-digest` 三件套、`delivery_index`、`generate --tier v9|xhard0`、噪声工具 | 阶段 1 并行 | 上述测试 + `test_env_digest_compare`、`test_gate_set`、`test_noise_gate` 不受影响 | CPU |
| W4 | 包内 V7 清理 | `src/robomme_hard/` 第 2.2、2.3 节所列；对应 `test_v7_*`、`test_v8_specs_schema` | 交付规格五份 | 阶段 2，W1～W3 合入后派 | `test_v9_packaged_800`、`test_hard_builder_xhard0`、`test_xhard0_native`、各任务 xhard 测试 | CPU |
| T1 | 单元／契约／官方对齐测试重构 | `tests/unit/`、`tests/contract/`、`tests/upstream/`、`tests/conftest.py`、`tests/_shared/`；对照表 | `tests/pipeline/`、`tests/gpu/`、生产代码 | 阶段 3，W4 合入后；与 T2 并行 | 第 3.5 节日常命令 | CPU |
| T2 | 流水线／GPU 测试重构 | `tests/parity/`、`tests/pipeline/`、`tests/gpu/`（原 `tests/dataset/`）；对照表 | T1 目录、生产代码 | 阶段 3，与 T1 并行 | `pytest tests/parity tests/pipeline -q` | CPU |
| R | 改名 | 第 2.4 节所列文件及全部引用点（含噪声工具路径常量、`site/*` 的 importlib 字符串、测试 import） | 格式名、键名、判定行前缀 | 阶段 4，噪声基线冻结后 | 全部 CPU 测试 + `MAINT_NO_LEGACY` | CPU |
| 主会话 | 决定落档、耗时基线、`pyproject.toml`、文档、闸门实跑 | `pyproject.toml` pytest 段、各 README、`AGENTS.md`、待定清单、本文 | — | 各阶段 | 验收表 | 阶段 5 一个 GL 占位席 |
| 审查 | 每块合并前 | 只读（sonnet） | 一切写入 | 每块一个 | `PRE_MERGE_REVIEW=PASS`、`MAINT_DEAD_BRANCH` | — |

共享文件裁决：`tests/lightweight/test_v8_regression_cmds.py` 归 W3；`test_v8_specs_schema.py` 归 W4；跨块的测试文件以「被测代码在哪块」定归属，阶段 3 前不做目录搬迁。

## 二、闸门

| 时点 | 判定行 |
|---|---|
| 每块合并前 | `PRE_MERGE_REVIEW=PASS`；`git diff --name-only <BASE>..<TIP>` ⊆ 可写集合 |
| 每块合并后 | 现日常命令（阶段 3 前用旧命令）通过；`UPSTREAM_GUARD=PASS`；`MAINT_SPECS=PASS`；`ls -1 scripts/*.py` 四入口 |
| 阶段 4 后 | `MAINT_NO_LEGACY=PASS`、`MAINT_COLLECT=PASS` |
| 阶段 5 | `GEN_NOISE_GATE=PASS` |

## 三、预算（P3、P5）

| 项 | 乘式 | 轨迹 | reset 上限 |
|---|---|---|---|
| 生成噪声闸门 | V9 43 格 × 3 局 + xhard0 16 任务 × 1 档 × 3 局 | 129 + 48 = 177 | 177 × 3 = 531 |
| 其余阶段 | — | 0 | 0 |

失败重试与递补默认 0；闸门 FAIL 后的重跑另报。

## 四、风险与盲区

- 删分支后 V9 路径上某处隐式依赖被删常量：靠第 2 层审查 + 第 3 层测试 + 第 4 层实跑三重兜底。
- 噪声闸门只覆盖 177 局样本，PASS 说明「没检出超出噪声带的变化」，不等于逐字节等价。
- 评估侧不实跑，`--v8` 主路径不改是前提；若审查发现必须改主路径，暂停并另报。
- 改名会让 `docs/validation/**` 里的历史命令不能原样复现，用对照表说明。
- 耗时数字（120 s 目标、约 8 分钟全量）在阶段 0 实测前是估计。
- 未开工的 Oracle 计划依赖 `env_client.py`／`run_seat.sh` 的非 v8 `--identities` 路线，本计划保留它；Q2 选删时，该计划引用的 `policy_replay.py::extract_defs` 需从 git 历史取回。
