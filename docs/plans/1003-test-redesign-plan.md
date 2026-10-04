测试套件重设计计划（2026-10-03）：以现有测试为蓝本，按「测什么、证明什么」从头设计，覆盖 benchmark 全部现行部分

> **权威性与边界**：本计划取代 [`1003-code-test-maintenance-todo.md`](../../1003-code-test-maintenance-todo.md) 第四节（测试彻底重构）及其分配表里的 T1、T2 两行；该文件其余各节（HF 上传、全库清理 V7／V8、改名、`gen-regress` 闸门）不变，下文称「清理计划」。代码锚点 `PLAN_BASE=86e5a015`（12.377），分支 `newtaskRelease-taskV9`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。**只规划不实施**，实施须用户批准；批准后第二部分的子代理分配表即为派发授权。
>
> 用户原话（2026-10-03，按时间）：
> 1. 「现在的test是否完全覆盖了所有所有的内容就是你可以破坏性的对整个test进行修改我需要覆盖所有关键都是正确的。然后都尽可能不要跑GPU的任务如果有GPU任务就只做一个最简单的初始或者reset这样的 可以彻底重构这个test你可以派出SubAgent确定方案也可以实测然后再给我一个重构的计划我希望重构完的test能够覆盖这个benchmark的所有部分」
> 2. 「就是你可以结合现在的test作为蓝本根据你对于一个正确项目的test应该怎么设计的一个思想完全重新设计这个test。」
> 3. 「subagent全部opus」
> 4. 「你现在测试的reset我一并授权直接开始。」
>
> 事实来源：本会话的三项实测（行覆盖率、59 格 reset 扫描、另一会话跑出的逐文件耗时基线）与六份只读盘点（opus 子代理，各管一个分区）；盘点里的关键疑点我逐条读源码复核过，复核结论见第一节。实测记录在 [`docs/validation/test-redesign-20261003/`](../validation/test-redesign-20261003/README.md)。

# 第一部分（给人看）

## 一、先回答：现在的测试覆盖全了吗？——没有

### 1.1 三项实测

| 实测 | 命令要点 | 结果 |
|---|---|---|
| 日常门禁耗时（另一会话，`artifacts/maintenance/baseline-durations.log`） | `pytest tests/lightweight/ -m 'not gpu and not slow' --durations=0` | `6 failed, 1885 passed, 3 skipped, 80 deselected in 518.44s`，是 5 分钟预算的 1.7 倍；`test_v8_eval_orchestration.py` 一个文件占 172.8 s，前 10 个文件合计约 400 s |
| 行覆盖率（本会话，tmux `tcov-1003`，coverage 7.16.2） | 同一条命令外套 `coverage run --include='src/*,scripts/*'` | `6 failed, 1885 passed in 611.47s`；分区覆盖率见下表 |
| reset 扫描（本会话，tmux `tsweep-1003`，GPU 1，单 worker，只 reset 不 step） | `xhard0 16 任务 × 1 局 + xhard1～5 共 43 格 × 1 局 = 59` 次 reset | `RESET_SWEEP=PASS cells=59 ok=59`，合计 162.6 s，中位 0.73 s，最慢 RouteStick xhard3 13.86 s（reset 内含 701 帧示教） |

行覆盖率（被测试执行过的行 ÷ 可执行行；起子进程跑的脚本不计入，所以 `eval_video_mover.py` 一类靠子进程测的文件被低估）：

| 分区 | 覆盖行／总行 | 覆盖率 |
|---|---|---|
| 官方包 wrapper 层 `src/robomme/env_record_wrapper/` | 286／1933 | 14.8% |
| 官方包工具 `src/robomme/robomme_env/utils/` | 695／3933 | 17.7% |
| 官方包 16 个任务环境 | 837／3905 | 21.4% |
| hard 包发布契约层（`hard_specs`、`hard_builder`、三个 wrapper 复制件） | 767／2103 | 36.5% |
| hard 包 16 个任务环境 | 3072／6549 | 46.9% |
| hard 包工具 | 3195／5366 | 59.5% |
| `scripts/parity/` | 4076／6414 | 63.5% |
| `scripts/injection-dev/` | 3406／5191 | 65.6% |
| `scripts/eval-official/` | 5906／7448 | 79.3% |

**从未被任何测试导入的现行文件**：`scripts/parity/upstream_guard.py`、`hard_pull.py`、`train_split_runner.py`、`train_split_worker.py`；`scripts/injection-dev/site/site_server.py`、`v8_site.py`、`v8_semantic_diff.py`、`v8_eval_transcode.py`、`v7_render_xhard0.py`；四个入口 `scripts/{dataset_replay,evaluation,run_example,evaluation_hard}.py`。

### 1.2 六份盘点的共同结论

现有测试「零件密、契约缺」。按问题类型归并：

1. **总闸门自己没人守**。`upstream_guard.py`（P1、P2 的唯一守卫）零测试。读源码确认两点：`check_upstream_bytes` 在不加 `--require-upstream` 时对字节差异只打 `PENDING` 并返回通过；全文件不检查 `dataset_replay.py`、`evaluation.py`、`run_example.py` 三个上游入口（`AGENTS.md` P1 以为它在守）。
2. **真实交付数据没被测过**。五份包内规格共 800 局正式行，只被数过局数。没有测试钉住文件字节 sha；没有测试把每一行过 builder 参数解析（800 局里只抽了约 2 局）；`hard_regression` 的 `delivery-set`、`tier-values` 只在合成夹具或 V8 格表上跑过；包内 header 里的 `sampling_config`（V9 运行时真正生效的取值）从没和档位表对过。
3. **测的档位不是交付的档位**。BinFill、VideoRepick、两个 Swap 任务的测试主要覆盖 xhard4，而 V9 这些任务只交付 xhard1、xhard2；两个 Swap 任务 V9 实际走的均衡外环与内环预规划函数（`_plan_swap_distractors_balanced`、`plan_inner_swaps_v6` 等约 10 个）没有任何测试调用。
4. **链路没有贯通测试**。评估侧没有一个用例用「假环境 + 假策略」把成功／失败／超时／step 抛异常／server 断连五种回合从 `SeatRunner` 一路走到报告并核对分母；生成侧 `_rollout.run_batch`（解析 runner 产物的适配层）被三份 FakeRunner 整个替换掉，零覆盖；`Mover` 产物 → `noise_run ship` → `hard_pull` 之间没有契约测试。
5. **不算测试的测试**。三个文件（`test_waypoint_dense_dedup`、`test_record_info_is_completed`、`test_record_waypoint_pending_flow`）只有 `main()` 没有 `test_` 函数，pytest 收集 0 条；四个纯 numpy／h5py 文件错标 `gpu`，从不进门禁；约 120 处 AST／源码字符串锁；若干在测试里内联复刻一份逻辑再自测的同义反复；四个 `test_zz_*` 依赖执行顺序；`test_step_error_handling` 往 `sys.modules` 塞空模块，污染整个会话；`TIER_MAX_STEPS` 在 3 处、格表合计在 6 处、档位取值在至少 8 处重复断言。
6. **守历史**。全部 `test_v7_*`、V8 1070／1262 口径、靠 `monkeypatch` 把格表钉回 V8 才能过的用例、恒 skip 的 3 个 `history_*`。

### 1.3 盘点发现的疑似生产代码问题（需你裁决是否随本计划修，见第七节）

| 编号 | 位置 | 问题 | 我的核对 |
|---|---|---|---|
| F1 | `upstream_guard.py::check_upstream_bytes` | 默认档放行字节差异；不守三个入口 | 读源码属实 |
| F2 | `v8_manifest.py::check_source` | xhard0 期望数写成 `len(ALL_TASKS) * XHARD0_PER_TASK`（192），不读开关 `XHARD0_IN_TEST_HARD`（默认关，导出为 800 行） | 读到该行；是否真会让 800 行导出过不了，未实跑 |
| F3 | `v8_report.py::build_reuse` | 只核「新评 80 + 复用 720」，不比对 800 总表是否逐格等于 `V9_CELLS` | 全文件无 `V9_CELLS`／`EXPECTED_CELLS` 引用，属实 |
| F4 | `run_seat.sh` | 看门狗轮询写死 `sleep 10`，测试无法提速 | 耗时基线 172.8 s 佐证 |
| F5 | 五份规格 header 的 `provenance.hard_fingerprint` | xhard2／3／5 记 `c026f57d…`、xhard4 记 `36483e4d…`，与当前源码不符只发警告，测试又全局吞警告 | 属实；属于「规格冻结后源码又改过」的正常结果，校验形同虚设 |

### 1.4 清理计划里需要更正的四处（不改该文件，由本计划覆盖）

- **第 4.4 节「`test_eepose_error_handling` 改为断言异常向上抛」是错的**：`EndeffectorDemonstrationWrapper.step` 在 IK 失败时显式 `return ({}, 0.0, True, False, {"status": "error", …})`，原断言与官方一致，保留。
- **第 4.3 节把 `test_audit_fix`、`test_audit_fix_scripts` 列为删除**：它们守的是 V9 仍在用的代码（分割中心刷新、`validate_place_sequence`、PickHighlight／VideoPlaceButton 目标文本、`parse_task_max_reset_attempts`、`_movecube_way`），必须迁移。
- **清理 W1、W2 会让两个测试文件整体导入失败**：`test_eval_official_env_client.py` 在模块顶层加载 `claim_queue`，`test_v8_delivery_flow.py` 在模块顶层 `import _report`。清理这两处之前，对应契约须已在新测试里有着落（阶段 A 的作用）。
- **第 2.3 节漏列 `generate_h5.py` 的单文件 `/2` continue 分支**（`--redo`、`--tasks`、`--self-check`）：`/2` schema 删除后它是死代码，`test_hard_state_machine.py` 也跟着失效；第 2.5 节保留 `noise_gate run-fresh` 的理由不成立（`noise_run_gl.sh` 用的 `RUN_FRESH` 行由 `noise_run.py` 打出）。两条交清理计划的执行会话处理，本计划的新测试只针对 `/4` 与 `noise_run`。

## 二、设计思想：一个正确的测试套件应当满足的七条

1. **按「证明什么」分层，不按版本号分文件**。每层回答一个问题，成本逐层升高，越贵的层用例越少。
2. **每条契约只在一处断言**。常量（格表、局数、`TIER_MAX_STEPS`、seed 偏移、档位取值）只在契约层断言一次，其他测试只引用常量，不写字面数字。
3. **调用真代码**。禁止在测试里复刻被测逻辑再自测；AST／源码扫描只允许用于「锁定与官方的差异」这一类，且以逐字节或 diff 白名单的形式出现，不再逐行 grep。
4. **对真实交付数据跑**。五份包内规格的 800 局每一行都过校验、过 builder、过回归子命令；合成夹具只用来造负例。
5. **每个判定器都有负例**。比较器、闸门、守卫，凡是会打 `PASS／FAIL` 的，都要有「该 FAIL 时确实 FAIL」的用例；写入方与读取方之间有贯通测试（用真写入方的产物喂真读取方）。
6. **用例相互独立**。不依赖执行顺序、不依赖别的测试文件、不污染 `sys.modules`、不断言「整个会话失败数」。公共替身只有一份，放 `tests/_support/`。
7. **「全覆盖」可机检**。一张进 git 的「源码文件 → 负责它的测试文件」对照表，由一条元测试守着：`src/robomme_hard/`、`scripts/`（vendor 除外）下任何 `.py` 不在表里就失败。新增源码文件必须同时登记测试归属或写明豁免理由。

## 三、新结构：六层

| 层 | 目录 | 回答的问题 | 手段 | 进日常门禁 | 预计耗时 |
|---|---|---|---|---|---|
| L0 静态与上游 | `tests/static/` | 官方代码与入口是否被动过？复制件与官方只差白名单吗？源码都有测试归属吗？ | 逐字节比对、diff 白名单、对照表元测试 | 是 | 约 5 s |
| L1 契约 | `tests/contract/` | 交付的 800 局身份、规格、常量是否正确且没变？ | 读真实包内规格逐行核对；常量唯一断言处 | 是 | 约 20 s |
| L2 单元 | `tests/unit/robomme/`、`tests/unit/hard/` | 每个纯逻辑模块、每个任务的取值／布局／子目标是否正确？ | 纯函数；离线场景（假仿真）跑真 `_load_scene` | 是 | 约 60 s |
| L3 流水线 | `tests/pipeline/{parity,gen,eval}/` | 对拍、生成、评估三条链路的记账与判定是否正确？ | 假 runner、假环境、假策略、合成 h5；进程内调用 `main()` | 是（起 bash／ffmpeg／websocket 的标 `slow`，不进） | 门禁部分约 30 s |
| L4 仿真冒烟 | `tests/sim/` | 真仿真里每个任务 × 每档能否建出来、观测与回注是否正确？ | 每格只做一次 `make` + `reset`，不 step | 否（有 GPU 时跑） | 实测约 163 s |
| L5 生成一致性 | 不在 pytest 内 | 改代码后生成结果变没变？ | 清理计划第三节的 `gen-regress`（GL A40） | 否 | — |

日常门禁 = L0～L3 的非 `slow` 部分，目标 ≤ 120 s（现状 518 s）；这个数是按现有纯函数用例的实测耗时（约 450 条合计几十秒）外推的估计，阶段 B 末实测校准。

原 `tests/dataset/` 七个文件要跑完整 episode，移到 `tests/sim/episode/`，标 `slow`，不进任何默认口径（用户口径：GPU 只做最简 reset）。

## 四、每层具体守什么

### 4.1 L0 静态与上游（`tests/static/`）

- **`test_upstream_bytes.py`**：进程内调 `upstream_guard` 的各检查函数。正例对真实仓库跑（`src/robomme` 102 个文件与官方 `1fadc0ec` 逐字节相同、三个入口与 `git show 1fadc0ec:scripts/<名>.py` 相同）；负例把模块级 `REPO`／`HARD`／`MANIFEST` 指到 `tmp_path` 下的小目录树，逐个造「改 1 字节、多 1 文件、shim 多 1 行、非法绝对导入、清单被篡改」，每个都必须 FAIL。为什么能逐字节：`src/robomme` 按 P2 冻结，官方 commit 在本仓库 git 对象里可取。
- **`test_copies_vs_upstream.py`**：hard 包三个复制件与官方的 diff 必须恰好等于白名单——`RecordWrapper.py` 只差 `fail_safe_limit` 2000→5000 与一行 import，`OraclePlannerDemonstrationWrapper.py` 只差一行 import，`DemonstrationWrapper.py` 逐字节相同；`UPSTREAM.json` 的 18 个 shim 与自签 sha 成立。取代三个只扫官方源码的 `test_record_*`。
- **`test_entry_scripts.py`**：`evaluation_hard.py` 与 `evaluation.py` 的 diff 恰好 3 个单行 hunk（import、`dataset="test-hard"`、`max_steps`）；`scripts/*.py` 恰好四个入口；`scripts/` 不 import `tests/`；`run_example.EPISODE_LIMITS` 与 metadata 局数一致。
- **`test_source_map.py`**：第二节第 7 条的对照表元测试（表在 `tests/source_map.json`）。

### 4.2 L1 契约（`tests/contract/`）

- **`test_constants.py`**：全套件唯一写字面数字的地方。`V9_CELLS` 逐格值、`43 格`、每任务 50 局、`16 任务 × 50 局 = 800`、开关打开时 `800 + 16 任务 × 12 局 = 992`、`TIER_MAX_STEPS`、按档 seed 偏移、`XHARD0_EPISODES`、`XHARD4_ONLY`、16 任务名单与注册 id 集合相等。
- **`test_packaged_specs.py`**：五份 `specs.jsonl` 的文件字节 sha256 钉值（钉值表 `tests/contract/packaged_specs.sha256` 进 git）；逐份 `load_specs` 通过；逐行核对 `spec.task == row.task`、`spec.identity` 的 seed／difficulty 与行一致、`sampling_config` 键集合等于任务集合、`exec_steps ≤ 1600`；seed 全局唯一（盘点核过 1518 行唯一）且与官方 metadata 的 seed 不相交。过了说明：交付规格没被动过，且每一行内部自洽。
- **`test_builder_800.py`**：把 `gym.make` 换成「记录参数后抛哨兵异常」的替身，对 `16 任务 × 50 局 = 800` 局逐局调 `make_env_for_episode`，断言交给 `gym.make` 的完整 kwargs（runtime 四项、seed、difficulty、`sampling_config`、`native_episode_spec`）与规格行一致；开关打开时 992 局、xhard0 的 seed 等于官方 test 集 hard 子集；规格根覆盖与各拒绝路径。
- **`test_tier_table.py`**：唯一一份 V9 档位取值表，同时对三处：进程内 `native_blocks`、包内 header 的 `sampling_config`、包内逐行规格。取代 `_shared/v7_tier_values.py` 与散在各 v4／v5 文件里的取值断言。
- **`test_regression_on_packaged.py`**：对包内真实规格进程内跑 `hard_regression` 的 `delivery-set`、`tier-values`、`step-headroom`、`movecube-layout`（包内 MoveCube 50 局）。
- **`test_schema_v4.py`**：`hard-specs/4` 校验器的负例（篡改、重签、越界、跨档 seed 相交）。
- **`test_gate_set.py`**（129／48 身份集，现有用例质量好，原样迁入）、**`test_v9_subset_specs.py`**（原样迁入，补 assemble 两条拒绝分支）、**`test_metadata.py`**（官方 train／val／test 每 split 16 文件、局数、episode 连续；hard 包四个 Unmask 任务 train 元数据各 400 条）、**`test_registry.py`**（三种导入顺序后 16 个 id 归 `robomme_hard`；起子进程，标 `slow`）。

### 4.3 L2 单元

**官方包（`tests/unit/robomme/`）**——官方代码不能改，测试的意义是锁定行为契约：

| 文件 | 守什么 |
|---|---|
| `test_env_builder.py` | `BenchmarkEnvBuilder`：dataset／action_space 白名单、`resolve_episode`、`get_task_list` 顺序、`max_steps + 2`；替身 `gym.make` 下四种动作空间的 wrapper 链类名与顺序 |
| `test_fail_paths.py` | `FailAwareWrapper` 把异常转成 `(None, 0.0, True, False, {status, error_message, exception_type})`；ee wrapper IK 失败的返回形状；取代污染 `sys.modules` 的 `test_step_error_handling` |
| `test_demo_wrapper_status.py` | 终局判定优先级 success > fail > timeout > ongoing、无示教步数截断、动作维度规整（stick 7 维、其余 8 维） |
| `test_step_batch.py` | `planner_denseStep` 的 batch 构造与拼接（决定 obs 的 dict-of-lists 形状） |
| `test_dataset_resolver.py` | 合成 h5 上的 waypoint 去重、multi_choice 读取、joint 补 8 维；收编三个「0 条用例」文件里的 `_case_*` |
| `test_choice.py` | label 匹配、3D 最近、像素投影与最近、`_resolve_command` 的 `[y,x]→[x,y]`；去掉错标的 `gpu` |
| `test_task_goal.py`、`test_vqa_options.py` | 16 任务的目标文本与选项（修正 2 条与官方不符的断言：未知环境返回 `[]`、`back-and-forth`） |

**hard 包（`tests/unit/hard/`）**——按任务一个文件，不再按版本号：

- 公共夹具 `tests/_support/offline_scene.py`：把现有最完整的 `test_v5_xhard_pickswing::OfflineScene`（`object.__new__` 造实例 + 假 `TableSceneBuilder`／`build_cube`／`get_actor_obb`，再调真 `_load_scene`）提成唯一一份，取代 6 个文件里各自复制的 `_FakeActor`。
- `test_<任务>.py` × 14（PickXtimes／SwingXtimes／PickHighlight 合一，PatternLock／RouteStick 合一，其余各一）：**参数化维度 = 该任务 V9 实际交付的档**。每格断言：离线 `_load_scene` 得到的数量、间距、判失败集合（干扰块在 `non_target_cubes` 里、误抓判失败）；自导出规格回放零差；**包内该格前 3 行规格作 `native_episode_spec` 回放，`mismatches == 0`**。
- `test_swap_planning.py`：V9 实际走的均衡外环、内环预规划、S5 均衡（现在零覆盖的约 10 个函数）。
- `test_native_golden.py`：原三档（easy／medium／hard）离线导出的摘要等于金标准，取代约 10 个文件里的「原三档逐字不变」AST 锁与 `test_v8_native_blocks_unchanged`。
- 纯函数模块各一：`test_collision.py`、`test_unmask_sampler.py`、`test_home_site.py`、`test_peg_flip.py`、`test_route_walk.py`、`test_segmentation.py`（从 `test_audit_fix` 迁入）、`test_goal_text.py`（16 任务新值档目标文本）、`test_sampling_guard.py`、`test_episode_spec.py`（含 `spec_binding` 非分层路径：`injected_mismatch`、`recorded_drift` 的 1e-5 容差、`unused`）。

### 4.4 L3 流水线

**对拍（`tests/pipeline/parity/`）**：`test_h5_comparators.py`（同一批合成 h5 变体同时喂三个比较器，逐个钉死各自的比较范围，含「两侧都新增同一字段且只在该字段不同」）；`test_gen_compare.py`（五类互斥，补缺的负例：重复行、档位冲突、h5 打不开、dtype 改变、帧号不连续）；`test_hard_parity_compare.py`（native／xhard0／v9 的终态与分母负例，从将删的 v8 档迁来）；`test_mover_ship_pull.py`（`Mover.handle` → `noise_run ship --finalize` → `hard_pull` 贯通）；`test_xhard0_reset_verdict.py`；`test_env_digest.py`；`test_noise_run.py`；`test_train_split.py`；`test_configs.py`（容差文件自洽）；`test_noise_run_shell.py`（6 个 bash 用例，`slow`）。`gen-regress` 与参照文件的测试由清理计划 G 块写，落在本目录。

**生成（`tests/pipeline/gen/`）**：唯一一份 FakeRunner 放 `tests/_support/gen_world.py`。`test_freeze.py`（`/4` 契约与三个拒绝分支、选签、MoveCube 逐方式 17／17／16、dry-run 预算数）；`test_rollout_state_machine.py`（全部改用 `/4`：失败递补、基础设施重试、崩溃恢复、恢复歧义、超配额、回写身份变化）；`test_run_batch.py`（monkeypatch `subprocess.run`，替身直接写 `results.json`／partial／不写）；`test_shard_aggregate.py`（分片不重不漏、聚合四种状态、rebase 三种错误、A40 检查）；`test_eval_identities.py`；`test_site_server.py`（媒体白名单、Range、不跟随符号链接；进程内线程 + 端口 0）；`test_site_catalog.py`（V9 小子表进门禁，59 格全量标 `slow`）；`test_site_build.py`。

**评估（`tests/pipeline/eval/`）**：公共替身（`FakeConn`、假 env、假录制器）收进 `tests/_support/eval_fakes.py`。

- **`test_seat_runner_e2e.py`**（新，核心）：参数化七种回合——成功、失败、上限超时、step 抛非基础设施异常、step 抛基础设施异常（重试）、server 断连（重试后 missing）、reset 额度耗尽——走真 mme／smvla 客户端加假连接，跑完把产物目录直接喂 `v8_report.build_report`，核对分母、结局计数、判定行。
- `test_identity_contract.py`（6 档 `TIER_MAX_STEPS` 含 xhard0 1300；三处 key 函数一致）、`test_attempt_ledger.py`、`test_env_session.py`、`test_policy_clients.py`、`test_eval_manifest.py`（只测 `build_v9`；**导出产物直接喂清单**，开关开／关两种）、`test_eval_report.py`（进程内调用；分母负例补全；800 总表逐格等于 `V9_CELLS`）。
- 标 `slow`：`test_smvla_server_protocol.py`、`test_recorder.py`（ffmpeg）、`test_eval_video_mover.py`（ffmpeg）、`test_seat_scripts.py`（bash）。

### 4.5 L4 仿真冒烟（`tests/sim/`，唯一用 GPU 的层）

**`test_reset_matrix.py`**：`xhard0 16 任务 × 1 局 + xhard1～5 共 43 格 × 1 局 = 59` 次 reset，单进程顺序跑，每格只 `make_env_for_episode` + `reset`，不 step。本会话已实跑一遍（`RESET_SWEEP=PASS cells=59 ok=59`，162.6 s），每格断言的内容都是那次扫描里实际观测到的：

- wrapper 链恰为 `FailAwareWrapper → DemonstrationWrapper → TimeLimitWrapper → OrderEnforcing → <任务类>`，任务类来自 `robomme_hard`；
- obs 恰有五个键，`front_rgb_list`／`wrist_rgb_list` 为 `(256,256,3) uint8`，`joint_state_list` 为 `(7,) float32`，`eef_state_list` 为 `(6,) float64`，`gripper_state_list` 为 `(2,) float32`，五个列表等长；
- info 恰有七个键（`elapsed_steps`、`success`、`fail`、`simple_subgoal_online`、`grounded_subgoal_online`、`task_goal`、`status`），`status == "ongoing"`，`task_goal` 为 1～4 条非空字符串；
- 带示教的 9 个任务（四个 Video 系、VideoUnmaskSwap、InsertPeg、MoveCube、PatternLock、RouteStick）帧数 > 1，其余 7 个 = 1；
- xhard1～5 的 43 格：`spec_binding` 的 `mode == "replay"`、`spec_sha256` 等于规格行、`injected_mismatch == 0`、`unused == 0`——**证明规格回注真的被环境消费**，这是唯一必须起仿真才能证明的契约；
- `unwrapped` 的 seed、difficulty 与规格行一致。

**`test_official_one_reset.py`**：官方 `robomme` 包 1 次 `make` + `reset`（`ee_pose`，全部 `include_*` 打开），断言 depth／内外参的形状与 `available_multi_choices`；再发 1 步不可达的 ee 动作，断言 `status == "error"`（只做 IK，不推进仿真）。

每次跑 L4 = `59 + 1 = 60` 次 reset、0 条轨迹生成。按 P3 超过单 worker 10 次，**请你在批准本计划时一并给长期授权**：以后任何会话跑 `tests/sim/` 的这 60 次 reset 不再逐次申请（见第七节 D3）。

## 五、现有测试的去向

- **原样迁入**（质量好）：`test_gate_set`、`test_env_digest_compare`、`test_v9_subset_specs`、`test_v9_movecube_layout`、`test_xhard_movecube_region`、`test_bin_collision`、`test_swap_uniform`、`test_episode_spec_recorder`、`test_seed_layout`、`test_comparator_scope`、`test_h5_parity_compare`、`test_eval_official_recorder`、`test_v8_eval_client` 的记账用例、`test_v8_eval_video_mover` 的 v8 用例。
- **按任务合并**：约 45 个 `test_v4_xhard_*`／`test_v5_*`／`test_xhard_*` 收成 `tests/unit/hard/` 的约 25 个文件；真调用的用例保留并把参数化维度换成交付档，AST 锁与同义反复删除。
- **先迁出现行用例再删壳**：`test_audit_fix*`、`test_v7_seed_rule`、`test_v7_tier_values`、`test_v8_specs_schema`、`test_v8_difficulty_tiers`、`test_v8_regression_cmds`、`test_v8_delivery_flow`、`test_v8_site_catalog`、`test_v8_append_candidates`、`test_eval_official_env_client`、`test_v8_eval_manifest`、`test_noise_gate`。
- **删除**：其余 `test_v7_*`、`test_v8_native_blocks_unchanged`、`test_native_restore_step2`、`test_v8_continue_fixtures`、`test_eval_video_mover_official`、`test_eval_official_run_seat`、被清理计划删掉代码的六个 `test_eval_official_*`、四个 `test_zz_*`、三个恒 skip 的 `history_*`、`test_TaskGoalI_isList`（64 次 reset，契约已由 L2 + L4 覆盖）。
- **删之前出对照表**：每行「旧 nodeid → 它守的契约 → 新 nodeid／删除理由」，落 `docs/validation/test-redesign-20261003/nodeid-map.md`，交你过目后才删旧目录。

## 六、验收

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 每个现行源码文件都有测试归属 | `tests/static/test_source_map.py` | 「覆盖所有部分」可机检，以后新增文件漏测会失败 | `TEST_SOURCE_MAP=PASS files=<n> unowned=0 exempt=<n>` |
| 日常门禁通过且够快 | `timeout 280s uv run --no-sync python -m pytest tests/static tests/contract tests/unit tests/pipeline -m 'not slow and not sim' -q` | 6 个长期失败消失，门禁回到预算内 | `TEST_CORE=PASS failed=0 wall_s=<实测>`（≤120） |
| 慢测试通过 | 同上换 `-m 'slow and not sim'` | bash、ffmpeg、websocket、子进程用例不受影响 | `TEST_SLOW=PASS failed=0 wall_s=<实测>` |
| 仿真冒烟通过 | `CUDA_VISIBLE_DEVICES=<空闲卡> uv run --no-sync python -m pytest tests/sim -m 'sim and not slow' -q` | 16 任务 × 全部档能建出来，观测形状与规格回注正确 | `TEST_SIM=PASS cells=59 official=1 failed=0 wall_s=<实测>` |
| 收集无错误 | `pytest --collect-only -q`（`testpaths = ["tests"]`） | 不再扫 `third_party/`，没有 0 条用例的文件 | `TEST_COLLECT=PASS errors=0 empty_files=0` |
| 覆盖率不低于重设计后的水位 | 第一节同一条 coverage 命令换新目录 | 行覆盖率较现状实测上升 | `TEST_COVERAGE=PASS`，逐分区列「现状 → 新值」；目标：hard 契约层 ≥ 90%、hard 工具 ≥ 80%、三个 scripts 分区 ≥ 85%、官方 wrapper 层 ≥ 50%（CPU）；任务环境的 step 与规划路径 CPU 测不到，不设硬线，如实报告 |
| 测试有牙齿 | 在一次性 worktree 里逐个植入 12 处故意改坏（清单见第二部分第三节），每处跑日常门禁 | 每个关键契约被改坏时，确实有测试报错；为什么成立：植入点一一对应第 1.2 节的缺口 | `TEST_TEETH=PASS seeded=12 caught=12` |
| 旧契约没丢 | 对照表每行都有去向 | 重设计没有悄悄丢掉仍有用的负例 | `TEST_NODEID_MAP=PASS old=<n> mapped=<n> dropped_with_reason=<n> unexplained=0` |
| 官方源码与入口未动 | `upstream_guard.py check --require-upstream` | P1、P2 守住 | `UPSTREAM_GUARD=PASS` |

## 七、需要你定的三件事（批准计划时一并裁决）

- **D1：第 1.3 节 F1～F4 的生产代码小修是否随本计划做？** 建议做（F 块）：F1 让守卫默认严格并加三个入口检查；F2 清单读开关；F3 报告对照 `V9_CELLS`；F4 轮询间隔可用环境变量覆盖（默认值不变，生产行为不变）。不做的话，对应测试写成 `xfail(strict=True)`，把问题钉在案上。F5（指纹）只在测试里把警告如实报告，不改规格文件。全部不涉及 `src/robomme/`。
- **D2：与清理计划的先后。** 建议分两阶段：**阶段 A 在清理之前**，只新增测试（L0、L1、L4 与两条贯通测试），给清理当安全网——现在的测试挡不住「删分支删坏 V9 路径」；**阶段 B 在清理与改名合入之后**，做合并、迁移、删旧目录。清理计划正由另一个会话执行，阶段 A 只新建 `tests/` 下的新目录，不碰它要改的任何文件。
- **D3：L4 的长期 reset 授权**：每次 `59 + 1 = 60` 次 reset、单 worker、0 条轨迹。

## 八、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| A0 | 主会话：`tests/_support/`（离线场景、生成世界、评估替身的骨架）、`pyproject.toml` pytest 段（`testpaths`、markers `slow`／`sim`）、`tests/source_map.json` 初版 | 现行日常命令结果不变（6 failed 照旧） |
| A1 | 并行：S1（L0 静态）、S2（L1 契约）、S7（L4 仿真冒烟）、F（生产小修，若 D1 同意） | 各块定向测试通过，`PRE_MERGE_REVIEW=PASS`；S7 合并后主会话实跑 `TEST_SIM` |
| A2 | 并行：S5 的 `test_run_batch`／`test_mover_ship_pull`、S6 的 `test_seat_runner_e2e` | 同上 |
| — | （清理计划的 W1～W4、R 在此期间或之后合入；每块合并后加跑阶段 A 的新测试） | 新测试持续 PASS |
| B1 | 并行：S3（官方包单元）、S4（hard 包单元）、S5 余下（对拍与生成流水线）、S6 余下（评估流水线） | 各块定向通过，`PRE_MERGE_REVIEW=PASS` |
| B2 | 主会话：对照表交用户过目 → 删 `tests/lightweight/`、迁 `tests/dataset/` → README、`AGENTS.md`「覆盖第 4 条」同步 | `TEST_NODEID_MAP`、`TEST_CORE`、`TEST_SLOW`、`TEST_COLLECT` |
| B3 | 主会话：覆盖率复测、12 处植入验证、仿真冒烟终跑 | `TEST_COVERAGE`、`TEST_TEETH`、`TEST_SIM` |

## 九、子代理分工与合并（简述）

按目录切开，互不重叠：S1 管 `tests/static/`，S2 管 `tests/contract/`，S3 管 `tests/unit/robomme/`，S4 管 `tests/unit/hard/`，S5 管 `tests/pipeline/parity/` 与 `tests/pipeline/gen/`，S6 管 `tests/pipeline/eval/`，S7 管 `tests/sim/`，F 管四个生产文件的小修。公共夹具 `tests/_support/`、`tests/conftest.py`、`pyproject.toml`、对照表和旧目录的删除归主会话，避免多人写同一文件。写入型子代理全部用 opus、各自在隔离 worktree 里只新增文件、提交带 `sub/<编号>: ` 前缀；按用户 2026-10-03「subagent全部opus」，合并前的只读审查子代理也用 opus。每块合并前审两件事：改动没越出自己的目录、新测试确实调用真代码且有负例；合并后主会话跑当时的日常门禁与 `UPSTREAM_GUARD`，PASS 即 push。旧测试在阶段 B2 之前一个不删，所以任何时刻门禁都不比现在弱。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`、三个上游入口、五份交付规格、`uv.lock`；不新增依赖（coverage 只用 `uv run --no-sync --with coverage` 临时环境）。
- R2：阶段 A 只新增 `tests/` 下新目录与 F 块四个文件，不碰清理计划可写集合里的任何文件；`tests/lightweight/`、`tests/dataset/` 在 B2 之前只读。
- R3：新测试不得 AST／字符串扫描被测逻辑（L0 的逐字节与 diff 白名单除外）；不得在测试里复刻被测公式；不得 `sys.modules` 注入；不得依赖用例顺序；常量字面值只许出现在 `tests/contract/test_constants.py` 与钉值文件。
- R4：GPU 只允许 `tests/sim/` 的 `59 + 1 = 60` 次 reset 与 1 步 ee 动作；worktree 内不跑 `tests/sim/`（合并后主会话串行跑，避免抢卡）。
- R5：`scripts/` 顶层不新增文件；`scripts/` 不 import `tests/`；测试夹具不放生产模块（`noise_gate.py` 里的 `_fx_*` 随清理 G 块处理，本计划不动）。
- R6：worktree 内环境取法 `UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest …`，先打印 `robomme_hard.__file__` 确认以 `<worktree>/src/` 开头。
- R7：不碰未跟踪的 `docs/validation/newtask-v9/hf-20261003*`（并行会话在途）；判 clean 用 `git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'`。

## 一、逐文件清单

第一部分第四节的各表即文件清单。补充实现要点：

- `pyproject.toml::tool.pytest.ini_options`：`testpaths = ["tests"]`；markers 留 `slow`、`sim` 两个（`gpu`、`dataset`、`lightweight` 在 B2 删除；A 阶段先并存）。`tests/sim/conftest.py` 给目录内用例统一加 `sim`，无可用 GPU 时 skip 并打印原因。
- `tests/source_map.json`：`{"<源码相对路径>": {"tests": ["<测试文件>", …]} | {"exempt": "<理由>"}}`。豁免候选：`scripts/parity/official/**`（vendor）、`v9_movecube_region_fig.py`（一次性出图，模块顶层读 `sys.argv`）、浏览器检查脚本、`src/robomme/**`（由 L0 逐字节 + `tests/unit/robomme/` 覆盖，按目录登记）。
- `tests/contract/packaged_specs.sha256`：五行，A 阶段由 S2 从 `PLAN_BASE` 的文件算出；与 `scripts/configs/gate-set-v9-129.json` 的 `identity_sha256`／`delivery_sha256` 交叉核对。
- `test_builder_800.py` 的替身：`monkeypatch.setattr(gym, "make", recorder)`，`recorder` 存 kwargs 后 `raise _Sentinel`；builder 每个 (task) 构造一次，规格根每档只校验一次。
- `test_reset_matrix.py`：格表由 `BenchmarkEnvBuilder(dataset="test-hard").resolve_episode` 取每档第一局生成（与本会话扫描脚本同法）；xhard0 用 `dataset="test"`、episode 3。单进程顺序、每格 `env.close()`；不落任何产物。
- `test_seat_runner_e2e.py`：复用 `test_v8_eval_client` 的假 builder／假 env，把 `StepPolicy` 换成真 `mme_client`／`smvla_client` + `FakeConn`；产物根在 `tmp_path`，随后进程内 `v8_report.build_report`。
- F 块：`upstream_guard.py`（`check_upstream_bytes` 默认严格，保留 `--allow-pending` 逃生阀并打醒目警告；新增 `check_entry_scripts`）；`v8_manifest.py::check_source`（`xhard0_expected` 改读 `hs.xhard0_prefix()`）；`v8_report.py::build_reuse`（`totals.cells` 与 `hs.V9_CELLS` 逐格比，不等记 `count_mismatch`）；`run_seat.sh`（`SEAT_POLL_S`、`SEAT_READY_POLL_S`，默认 10、2）。清理计划 R 块改名时这三个 py 文件名会变，F 块须在 R 之前合入。

## 二、子代理分配表

派发前核对：`worktree.baseRef="head"`；主检出 clean（R7 口径；并行会话的未跟踪留档若仍在，按 `CLAUDE.md` 计划执行模式交用户裁决）；`git check-ignore -q .claude/worktrees/probe`；记 `BASE`。全部子代理 `model: "opus"`。

| 编号 | 目标 | 可写集合 | 禁触 | 依赖／合并顺序 | 验收（worktree 内，CPU） | 资源 |
|---|---|---|---|---|---|---|
| 主会话 A0 | 公共夹具骨架、pytest 配置、对照表初版 | `tests/_support/`、`tests/conftest.py`、`pyproject.toml` pytest 段、`tests/source_map.json` | 生产代码 | 最先；提交后记 `BASE` | 现行日常命令结果不变 | CPU |
| F | 生产小修四处（D1 同意才派） | `scripts/parity/upstream_guard.py`、`scripts/eval-official/v8_manifest.py`、`v8_report.py`、`run_seat.sh` | 其余一切；`src/robomme/` | A1，第 1 个合并；须早于清理 R 块 | `pytest tests/lightweight/test_v8_eval_manifest.py tests/lightweight/test_v8_eval_report.py tests/lightweight/test_v8_eval_orchestration.py -q`；`upstream_guard.py check` 末行 `UPSTREAM_GUARD=PASS` | CPU |
| S1 | L0 静态与上游 | `tests/static/` | 生产代码、其他测试目录 | A1，F 之后合并（依赖 F 的 `check_entry_scripts`；D1 不同意则对应用例写 `xfail(strict=True)`） | `pytest tests/static -q` | CPU |
| S2 | L1 契约 | `tests/contract/` | 同上；规格文件只读 | A1 | `pytest tests/contract -m 'not slow' -q` | CPU |
| S7 | L4 仿真冒烟 | `tests/sim/`（含 `conftest.py`） | 同上 | A1；合并后主会话实跑 | `pytest tests/sim --collect-only -q` 收集到 `59 + 1` 条；不在 worktree 实跑 | 合并后主会话占 1 张空闲卡约 3 分钟 |
| S6a | 评估贯通测试 | `tests/pipeline/eval/test_seat_runner_e2e.py`、`test_eval_manifest.py`、`test_eval_report.py` | 同上 | A2 | `pytest tests/pipeline/eval -q` | CPU |
| S5a | 生成与对拍贯通测试 | `tests/pipeline/gen/test_run_batch.py`、`tests/pipeline/parity/test_mover_ship_pull.py` | 同上 | A2 | 定向 | CPU |
| S3 | 官方包单元 | `tests/unit/robomme/` | 同上 | B1 | `pytest tests/unit/robomme -q` | CPU |
| S4 | hard 包单元 | `tests/unit/hard/` | 同上；`tests/_support/offline_scene.py` 只读（要改先报主会话） | B1（清理 W4 合入后） | `pytest tests/unit/hard -q` | CPU |
| S5b | 对拍与生成流水线余下 | `tests/pipeline/parity/`、`tests/pipeline/gen/` 余下文件 | 同上；清理 G 块写的 `gen-regress` 测试文件 | B1（清理 W2、W3、R 合入后） | `pytest tests/pipeline/parity tests/pipeline/gen -q` | CPU |
| S6b | 评估流水线余下 | `tests/pipeline/eval/` 余下文件 | 同上 | B1（清理 W1、R 合入后） | `pytest tests/pipeline/eval -q` | CPU |
| 主会话 B2／B3 | 对照表、删旧目录、迁 `tests/dataset/` → `tests/sim/episode/`、文档、覆盖率复测、植入验证、仿真终跑 | `tests/lightweight/`（删）、`tests/dataset/`（迁）、`tests/_shared/`（并入 `_support`）、`tests/README.md`、`AGENTS.md` 覆盖第 4 条、`docs/validation/test-redesign-20261003/` | — | 最后 | 验收表 | B3 占 1 张卡约 3 分钟 |
| 审查 | 每块合并前一个，只读 | — | 一切写入 | 每块一个 | `PRE_MERGE_REVIEW=PASS`；额外核「真调用、有负例、无字面常量」 | — |

共享文件裁决：`tests/_support/**`、`tests/conftest.py`、`pyproject.toml`、`tests/source_map.json` 只归主会话；子代理需要新公共替身时在自己目录的 `conftest.py` 里先放，交回时列出，由主会话在合并后上提。合并顺序：F → S1 → S2 → S7 → S6a → S5a →（清理计划各块）→ S3 → S4 → S5b → S6b。

## 三、闸门总表与植入清单

| 时点 | 判定行 |
|---|---|
| 每块合并前 | `PRE_MERGE_REVIEW=PASS`；`git diff --name-only <BASE>..<TIP>` ⊆ 可写集合 |
| 每块合并后 | 现行日常命令（B2 前为旧命令 + 已合入的新目录）；`UPSTREAM_GUARD=PASS`；`ls -1 scripts/*.py` 恰好四个；`POST_MERGE_REVIEW=PASS` |
| S7 合并后 | `TEST_SIM=PASS cells=59 official=1` |
| B2 后 | `TEST_NODEID_MAP`、`TEST_CORE`、`TEST_SLOW`、`TEST_COLLECT`、`TEST_SOURCE_MAP` |
| B3 后 | `TEST_COVERAGE`、`TEST_TEETH`、`TEST_SIM` |

`TEST_TEETH` 的 12 处植入（一次性 worktree，逐个植入、跑日常门禁、还原；全部 CPU）：①`src/robomme` 任一文件改 1 字节；②`evaluation.py` 加一行；③`RecordWrapper.py` 复制件 `fail_safe_limit` 改回 2000；④包内 `xhard1/specs.jsonl` 某正式行 seed 加 1（不重签）；⑤同一行重签后再改 `spec` 里一个取值；⑥`V9_CELLS` 某格 +1；⑦`TIER_MAX_STEPS["xhard1"]` 改 1500；⑧`hard_builder._hard_env_kwargs` 丢掉 `native_episode_spec`；⑨PickXtimes xhard2 的抓放次数表改一个值；⑩`noise_gate.compare_h5` 跳过一个数据集；⑪`env_client` 把 timeout 记成 fail；⑫`v8_report` 分母改用结果行数。

## 四、预算（P3、P5）

| 项 | 乘式 | reset | 轨迹 |
|---|---|---|---|
| 本会话已做（用户原话 4 授权） | 探针 1 任务 × 1 档 × 1 局 + 扫描（xhard0 16 任务 × 1 局 + 43 格 × 1 局） | 1 + 59 = 60 | 0 |
| L4 每次运行（D3 长期授权） | xhard0 16 任务 × 1 局 + 43 格 × 1 局 + 官方包 1 任务 × 1 局 | 59 + 1 = 60 | 0（另 1 步 ee 动作） |
| 本计划实施期间 L4 运行次数 | S7 合并后 1 次 + B3 终跑 1 次 + 失败重跑上限 2 次 | ≤ 4 × 60 = 240 | 0 |

其余阶段 0 次 reset。`tests/sim/episode/`（原 `tests/dataset/`）本计划内不跑。

## 五、runbook

```bash
# 日常门禁（B2 后）
timeout 280s uv run --no-sync python -m pytest tests/static tests/contract tests/unit tests/pipeline -m 'not slow and not sim' -q --durations=20
# 慢测试
uv run --no-sync python -m pytest tests -m 'slow and not sim' -q
# 仿真冒烟（先 nvidia-smi 选空闲卡）
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m pytest tests/sim -m 'sim and not slow' -q
# 覆盖率复测（>5 分钟时进 tmux，会话名前缀 tcov-）
COVERAGE_FILE=artifacts/test-coverage/.coverage uv run --no-sync --with coverage python -m coverage run --include='src/*,scripts/*' -m pytest tests -m 'not slow and not sim' -q -p no:cacheprovider
```

## 六、风险登记

| 风险 | 应对 |
|---|---|
| 与清理计划的执行会话撞文件 | 阶段 A 只新增目录；F 块四个文件在派发前与该会话的当前 HEAD 对一遍 diff，有在途改动则 F 让位、对应测试先 `xfail` |
| 清理改名后阶段 A 的新测试 import 失效 | 新测试按路径加载脚本的地方集中在 `tests/_support/loaders.py` 一处，R 块改名时只改这一处（列入 R 块引用点） |
| 离线场景夹具与真仿真行为漂移 | L4 的 59 格 reset 每格核 `spec_binding` 零差，离线测试错了会在这里暴露 |
| 钉了规格文件字节 sha 后，合法的规格更新要同步改钉值 | 钉值文件单独一份，更新规格的 commit 必须同时改它，review 时一眼可见 |
| 门禁 120 s 目标达不到 | 目标是估计；B2 实测后把最慢的用例降为 `slow`，不删断言 |
| `tests/sim/` 与他人评估进程抢卡 | 只在主会话串行跑，先看 `nvidia-smi` 选空闲卡；实测只占约 3 分钟 |

## 七、盲区诚实清单

- 行覆盖率不计子进程里执行的脚本；现状数字对靠子进程测的文件偏低，B3 复测时进程内调用增多，数字上升里有一部分是口径效应。
- L4 只 reset 不 step：环境的 step 逻辑、子目标推进、成功判定、规划器，在 CPU 上只有纯函数部分被测；整局行为的正确性靠 L5 的生成一致性闸门（177 局逐字节）与已封存的 800 局交付，不靠 pytest。
- 六份盘点是静态阅读，盘点里的「未核实」项（SwingXtimes `too_many_swings`、StopCube xhard5 运行路径、`mani_skill` 在纯 CPU 下导入 wrapper 的可行性、html 字段正则抽取的可行性）实施时遇到再定；F2 是否真会失败未实跑。
- 第三节的耗时除 L4（实测 162.6 s）外都是估计。
- 官方包的潜在问题（`evaluation.py` error 分支 `outcome` 未赋值、`run_example._validate_episode_index(-1)` 与 docstring 矛盾）只用测试记录现状，不改源码。
- 本会话的覆盖率与 reset 扫描启动时，工作区有并行会话的两项未跟踪留档，跟踪文件与 `86e5a015` 一致。

## 八、留档与 commit 纪律

- 本会话实测留档：`docs/validation/test-redesign-20261003/`（`README.md`、`records/coverage-report.txt`、`records/reset-sweep.jsonl`）；实施期间的对照表与判定行追加到同一目录。
- 每块合并提交按 `<大>.<小> <中文描述>` 递增，body 详写；子代理提交用 `sub/<编号>: ` 前缀。
- 自检：`grep -c '^# 第一部分\|^# 第二部分' docs/plans/1003-test-redesign-plan.md` 必须等于 2。
