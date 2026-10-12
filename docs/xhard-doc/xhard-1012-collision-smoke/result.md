# 交换碰撞实现：已整合，GPU 端点对齐失败

**最新接续状态（2026-10-12，方案 X）**：时序修复已实现并以 `b7be8956`（2.89）合并推送，CPU 为 381 通过、四项获准保留的基线失败、2 跳过。真实首探针的第 0 段起点通过；第 1 段共享端点仅 `a_q` 逐位不一致，已按计划停止后续阶段。完整实测见文末「方案 X 接续结果」；下段及原有各节保留此前实施的历史状态。

本轮实现已整合并推送，主检出 CPU 为 **375 通过、4 既有失败、2 跳过**，按用户追加批准的基线对照闸门通过。GPU 的三任务失败送达、reset 契约、五档前缀均通过；真实首段端点对齐失败，已停止后续阶段。正常生成冒烟与 180 卡全量未启动。以下保留 CPU 准备阶段的原始 FAIL 和独立分支记录，最新整合与 GPU 证据在文末，不能把先前状态当作当前状态。

## 用户指令与边界

用户原话：「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-collision-plan.html 同意开工」。授权对应根目录该 HTML 的阶段 A–D；阶段 E 仍按 D6、P5，须在冒烟后报告 180 卡的实测耗时与磁盘需求，再取得该批次确认。

最初向用户请求裁定：是否将核心短测闸门改为「四项基线失败保留，其余原有测试与本轮定向测试全部通过」。询问依据为计划 `XHARD_CORE_SHORT` 与 `AGENTS.md` 第 22 条的「判据 FAIL 时……不自行改判据、不自行放宽」。用户随后明确答复：「采用基线对照闸门，保留这 4 项失败」。据此继续整合；原始 pytest 退出 1 与历史 FAIL 记录保留，新的合并判据要求失败集合精确等于这四项，任何新增失败均 FAIL，不修改受保护源码以绕过闸门。

## CPU 准备阶段的环境与版本快照

- 环境 B：`sled-vail`，指定 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006` 主检出，2 张 RTX 6000 Ada；初检 GPU0 为 1286 MiB、0%，可用磁盘约 6.4 TB。没有启动 GPU 任务，没有新建 tmux 会话，没有干预其他进程。
- 开工时主检出：`0ec9951bfcb95646f2f8970854f566c34361c003`，工作区干净。
- 阶段 A 提交：`1599fedd265e6726a979df3a649f48ac0f0cf131`（2.77），已推送。导入判据 SHA256 为 `bbe87eec3c36ab54e703a6ff741a5fdd3217c11e2a1541eb95d8f013c852302b`，与固定来源逐字节一致。
- 全局 Codex `[agents] max_concurrent_threads_per_session` 已按规则从 16 改为 32 并读回；本次宿主实际仍提供 16 个子代理槽位，未验证 32 个同时运行。

| 子任务 | 分支末端提交 | 实际写集与验证 |
|---|---|---|
| C1 | `895940856423d467e6ddce1daf90be24a7abf558` | `swap_plan.py` 与两份 CPU 测试；54 通过；发起者、最近邻、前缀、连续扫掠、首条 fatal、端点证据 |
| C3 | `78b16efe389dea4215afd760b230f49aa4251ebc` | 生成器与两份测试；32 通过、2 排除；结构化失败、独立成功字段、失败产物保留、崩溃卡隔离；GPU 测试只编写 |
| C4 | `4db9ea8d5bfead14fa0434bb1d2e8aff55b6515f` | 母清单、作业、归一化、汇总、六列视频与测试；57 通过；30 母 seed 展开 180 卡 |
| C2 | `7a4b786540e5fb93931b2cd8859f3c407ad627cb` | 三子类、GPU 测试与必要的既有 MRO 断言维护；38 通过、23 排除 |

当时四个分支均已作 `sub/` 提交，尚未推送或合入主分支。C2 以固定 C1 提交为基线先完成接线，属于主代理在既有授权内调整依赖，未跳过合并闸门。各工作树曾位于 `/home/hongzefu/.codex/remote-control-host/worktrees/swap-collision-c1/`、`swap-collision-c3/`、`swap-collision-c4/`、`swap-collision-c2/` 下的同名仓库目录；整合后四个开发工作树和临时组合工作树均通过宿主管理工具归档，源码提交全部保留在主分支历史。

## 验证证据

主会话复跑的每条命令均在 5 分钟内完成，未安装或同步依赖。各 worktree 统一使用主检出 `.venv`，并通过 `PYTHONPATH=<工作树>/src` 选择实际源码；产物日志只落主检出 `artifacts/logs/`。

```bash
UV_CACHE_DIR=/home/hongzefu/.cache/uv \
UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/.venv \
PYTHONPATH=<工作树>/src uv run --no-sync python -m pytest <测试集合> -q -m 'not gpu'
```

| 检查 | 测试集合或入口 | 主会话结果 / 退出码 | 证据 |
|---|---|---|---|
| 改动前核心短测 | `tests/lightweight/ src/robomme_xhard/tests/ -m 'not gpu and not slow'`，`timeout 280s` | 281 通过、4 失败、2 跳过、118 排除；7.23 秒；1 | `records/xh-coll-baseline-cpu-1012.log` |
| C1 | `test_swap_plan.py test_bin_collision_vendored.py` | 54 通过；4.19 秒；0 | `records/xh-coll-c1-cpu-1012.log` |
| C3 修复版 | `test_worker_evidence.py test_jobs.py test_fatal_catch.py -k 'not generator_cli_xhard'` | 32 通过、2 排除；3.41 秒；0 | `records/xh-coll-c3-fix-cpu-1012.log` |
| C4 修复版 | `test_contract.py test_jobs.py test_episode_strip_video.py test_collision_tools.py` | 57 通过；4.22 秒；0 | `records/xh-coll-c4-fix-cpu-1012.log` |
| C2 | `test_s2_configs.py test_swap_collision_gpu.py` | 38 通过、23 排除；2.69 秒；0 | `records/xh-coll-c2-cpu-1012.log` |
| 临时组合核心短测 | 同改动前测试集合，`timeout 280s` | 375 通过、4 失败、2 跳过、134 排除；9.63 秒；1 | `records/xh-coll-combined-cpu-1012.log` |

临时组合目录为 `/home/hongzefu/.codex/remote-control-host/worktrees/swap-collision-check/robomme_benchmark_newtask-v3-MotionJepa1006`：以 C2 末端提交（包含 C1）为基线，用 `apply_patch` 应用固定 C3 与 C4 差异，逐文件比较组合目录字节与对应固定提交，`COMPOSITION_BYTES=PASS files=12`。该组合目录带本轮未提交改动，只用于短 CPU 接口检查，不冒充正式运行的 clean HEAD 锚点，不用于 GPU 起跑。

组合环境额外直接调用生成器 `_args`，传 `--difficulty xhard12 --mother-manifest docs/xhard-doc/xhard-1011/records/mother_seeds.json --mother-rank 9 --output-dir artifacts/not-launched-rank-check`，只解析参数、未调用生成入口：`RANK_CLI=PASS rank=9 generation_started=0`，退出 0。C3 独立测暂排除的旧 CLI 用例已在组合全套中执行，结果通过。

原样判定：

```text
XHARD_COLL_VENDOR=PASS
COMPOSITION_BYTES=PASS files=12
RANK_CLI=PASS rank=9 generation_started=0
REGRESSION_DELTA=PASS baseline_failures=4 current_failures=4 added=0 removed=0
XHARD_BASELINE_EQ=PASS argv_sets=6 jobs_compared=3253 jobs_diff=0 names_diff=0
XHARD_JOBS=PASS jobs=52 mothers=16 attempt0=1
XHARD_CORE_SHORT=FAIL baseline_failures=4 new_failures=0
```

四项基线失败均未修、未跳过：

`REGRESSION_DELTA` 通过脚本提取两份原始 pytest 日志中全部 `FAILED ` 开头的用例标识并比较集合所得，退出 0；它只证明失败集合相同，不代替仍为 FAIL 的核心短测闸门。

1. `test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal`：空目标返回 `[]`，旧断言要求 `[""]`。
2. `test_TaskGoal.py::test_swingxtimes_multiple`：实际文案含 `back-and-forth`，旧断言要求无连字符版本。
3. `test_step_error_handling.py::test_step_error_returns_status_error`：旧断言要求 `DemonstrationWrapper.step` 内有 `try/except`。
4. `test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except`：旧断言要求 `dataset_replay.py` 有状态检查。

## 独立审查与修复

四个最终分支均获固定提交静态审查 `PRE_MERGE_REVIEW=PASS findings=0`。C1、C3、C4 的审查基线为阶段 A 提交，C2 基线为 C1 末端提交；审查没有执行测试，动态结果由主会话另行复跑。

- C3 首审发现：可读 H5 空壳与已写失败视频共存时，崩溃卡仍会重跑。修复为先搜四种同卡视频前缀，任一存在即整体隔离；四个调度替身反例验证只提交一次、两个文件隔离、邻卡不动。无视频且无 episode 内容的空壳仍保留普通基础设施重试。
- C4 首审发现：缺少独立成功字段时从 `ok` 或 H5 存在推成功。修复为缺字段保持未知，未知结果覆盖 H5 推断；无结果时仅用末帧独立 `info/is_completed` 明确值报告 0/1。C3 同时让 worker 与 cards 显式保留真实终态成功字段。
- 主会话已亲眼读取六列失败视频的位图预览：灰底与 `SwapCollisionError` 标注完整，六列对齐，无溢出、遮挡或字体方块。预览来自测试的临时目录，不是实跑 episode 视频。
- `src/robomme/` 未改；判据未改；没有改 seed 公式、attempt 或既有 retryable 类型。

## CPU 阶段结束时的下一步与未验证项

待用户裁定核心短测闸门后，按 C1 → C3 → C4 → C2 合并、整体验证和推送，再从确定的主分支版本串行执行 D0 与 GPU 契约、三任务各一张 xhard20 冒烟。任何 GPU 闸门失败即保留证据交用户，不换 seed 或放宽端点对齐。D0 沿计划旧母 seed 5700 / 7700 / 13600；阶段 E 新清单按 K13 取升序前 10，VideoRepick 的首条为 seed9600，两者用途不同。

`XHARD_FATAL_CATCH`、`XHARD_COLL_GPU_RESET`、`XHARD_TIER_PREFIX` 的真实 GPU 验证、`XHARD_SEG_START_ALIGN`、`XHARD_SMOKE_E2E`、耗时倍数、每卡磁盘占用均未验证。没有全量成功率或实跑拼接视频。历史 `solve_s` 证据在当前 vail 留档中未找到，不将计划中的旧数字冒充本机新实测。

## 用户放行后的整合与 GPU 实测

用户追加裁决后，主会话依次整合 C1（`d05767ea` / 2.80）、C3+C4（`96a6ecd0` / 2.81，两者母 rank 接口与测试一起整合）、C2（`20838a33` / 2.82），每次保留全部 `sub/` 提交，并在主检出重测后立即推送。三个主检出 CPU 结果依次为 335 / 372 / 375 项通过，失败集合均精确等于用户批准的四项，原始 pytest 均退出 1，对照包装均退出 0。最后一次耗时 8.87 秒。

```text
XHARD_CORE_SHORT=PASS baseline_failures=4 new_failures=0 pytest_exit=1
POST_MERGE_REVIEW=PASS base=0ec9951bfcb95646f2f8970854f566c34361c003 tip=09900b371cfe5d643d704b93485267a6a585ea59 findings=0
```

第二行来自独立的整条接口静态审查；未把它冒充 GPU 验证。完整合并日志见 `records/xh-coll-merge-c1-cpu-1012.log`、`xh-coll-merge-c3c4-cpu-1012.log`、`xh-coll-merge-c2-cpu-1012.log`。原始日志带 pytest 的尾空白，原字节保留；源码与文档范围 `git diff --check` 通过，日志全范围检查的尾空白不作为代码缺陷。

GPU 两次测试均从 clean HEAD **`09900b371cfe5d643d704b93485267a6a585ea59`**（2.83）启动，本机 GPU0，串行单进程，无重试。第一会话为 `xh-coll-d0-1012`，第二会话为 `xh-coll-gpu-contract-1012`；均已正常退出，无本轮会话残留，其他原有会话未动。

| 闸门 | 命令与证据 | 实测 / 判定 |
|---|---|---|
| 运行拒绝送达 | `CUDA_VISIBLE_DEVICES=0 timeout 300s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_fatal_catch.py -q -s -m gpu -x`；`records/xh-coll-d0-1012.log` | 1 项测试通过，内部串行 3 张真实 worker 卡；120.47 秒；`EXIT_CODE=0`；`XHARD_FATAL_CATCH=PASS tasks=3 hang=0` |
| 真实几何与时序 | `CUDA_VISIBLE_DEVICES=0 timeout 280s uv run --no-sync python -m pytest src/robomme_xhard/tests/test_swap_collision_gpu.py -q -s -m gpu -x`；`records/xh-coll-gpu-contract-1012.log` | 6 通过、1 失败、3 CPU 用例排除；41.10 秒；`EXIT_CODE=1`；首次失败后停止 |
| reset 配对契约 | 上行最先执行的三个 `test_reset_certifies_all_pairs` | `XHARD_COLL_GPU_RESET=PASS tasks=3`，由三个真实通过用例归纳 |
| 五档前缀 | 随后三个 `test_five_tiers_share_pair_prefix`，每任务五档 | `XHARD_TIER_PREFIX=PASS tasks=3 tiers=5`，由三个真实通过用例归纳 |
| 第 1 段端点对齐 | `test_real_step_first_start_and_shared_endpoint` 首个 VideoUnmaskSwap 用例 | `XHARD_SEG_START_ALIGN=FAIL task=VideoUnmaskSwap seed=5700 segment=0 executed_step=64 fatal_control_step=65 mismatches=a_p,a_q,b_p,b_q` |

运行拒绝闸门使用第二段必拒注入并屏蔽其他运行检查，仅证明送达；不能据此证明正常碰撞检查通过。三张结果均为预期的 `ok=false`、`task_success=false`、`failure_class=task`、`error_type=SwapCollisionError`、`stage=segment_start`，对应产物被改为 `FAILED_` 并保留。

| 任务 | 母 seed | worker 耗时 / 求解耗时（秒） | 原始结果归档 |
|---|---|---|---|
| 2.3 VideoUnmaskSwap | 5700 | 32.285 / 21.714 | `records/fatal-VideoUnmaskSwap.json` |
| 2.4 ButtonUnmaskSwap | 7700 | 38.273 / 28.637 | `records/fatal-ButtonUnmaskSwap.json` |
| 3.2 VideoRepick | 13600 | 47.232 / 37.453 | `records/fatal-VideoRepick.json` |

原始 H5 / 视频保留在 `artifacts/tests/fatal-catch/run-1791838201278127954/`，不进 git。`records/xh-coll-gpu-evidence-manifest.json` 记 10 个文件（含 3 个结果 JSON）的绝对路径、字节数与逐文件 SHA256：`GPU_EVIDENCE=PASS files=10 bytes=2164345903`。这些是故障注入产物，不能作为正常生成成功率或正常检测耗时的基线。

## 失败诊断与候选修法（尚未批准、未实施）

已确认的时序：`VideoUnmaskSwap::step` 先调用 `statechange.py::swap_flat_two_lane` 捕获段起点并 `set_pose`，然后 ManiSkill `BaseEnv::step` 内的 `_step_action` 执行多个 `scene.step()`，最后才增加步数并返回。`SwapCollisionMixin::step` 在完整父类 step 返回后读取实际 actor 位姿，与物理积分之前的缓存做逐位比较。交换容器由 `object_generation.py::build_bin` 的 `builder.build_dynamic` 构建，因此原计划「返回后仍逐位等于缓存」没有保证。本次实际发现两个对象的位置和四元数共四字段不同，拒绝类型为 `SwapBindingError`、检查为 `endpoint_binding`。

`keep_upright` 在父类交换函数中仅为签名参数、未在函数体读取，不能据此声称姿态被冻结。四元数还经过混合归一化、SAPIEN 写入读回与判据正规化；当前 pytest 异常输出缩略了完整数值，**未量化漂移幅度，也不能把差异逐项归因于重力、接触或浮点往返**。没有为补数值而重跑该 seed。

候选修法是在 `SwapCollisionMixin::_before_simulation_step` 的该段首个子步进行段起点绑定与扫掠证明：父类已应用动画起点，物理积分尚未发生；每段只检查一次，随后继续原有每子步前后实际几何检查。逐位判据、几何阈值、seed、母 seed 规模保持原约束。该时序改变须先修订并完整呈现计划、再获用户开工认可；四元数往返仍可能导致逐位差异，候选方案没有实测，不保证一改就通过。

已按失败闸门停止：其余真实时序用例、reset 拒绝注入、运行期留证用例、三任务正常冒烟及 180 卡全量均未执行。`XHARD_SMOKE_E2E`、正常钩子统计、检测开销倍数、正常每卡磁盘量仍未验证；没有正常生成成功率表或新实跑六列视频。

## 2026-10-12：方案 X 接续结果——共享端点四元数逐位闸门失败

用户本次原话：「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1012-swap-collision-plan.html 按照最新计划 继续执行完」。执行最新 K14/T1：删除 `SwapCollisionMixin::step` 覆写，改在 `_before_control_step` 复核真实段起点，使用当前控制步号，零新增实例状态。保持最近邻、`np.array_equal` 四字段逐项比较、vendored 阈值、每个物理子步前后检查和首条 fatal 处理；没有修改生成器、环境子类、依赖或受保护的 `src/robomme/`。

### 版本、独立审查与 CPU

接续基线为 `b81a820f1c3e2ce93a4291e2666782f093320a63`。T1 的独立工作树分支 `codex/swap-timing-x` 保留两个子提交 `c15acbe7400f30e412e762dbff282ee394982550`、`2122a20179a6ad5d51835ae14832c940d5638dc8`。写入与审查代理显式使用 `gpt-6.1-sol`，只读盘点使用 `gpt-6-luna`。

首审发现三处既定验收缺口：JSON 没有代码 SHA 和逐键差值、CPU 未模拟积分及共享端点捕获、GPU 追踪器重复无保护读姿态可能丢失失败 JSON。原写者在相同三文件范围内补齐，没有调整生产机制、接口或验收判据；独立复审通过。主会话核整合三文件字节与固定 TIP 相同，保留两个子提交 `--no-ff` 整合为 **`b7be8956e8399b33ea6fe7d889107f7a94e80ec8`（2.89）**，已推送。

主检出期间另一会话同步 `AGENTS.md`，主会话未碰其在途修改。同步自行落地为 `1ef3dacd`、主检出与远端一致且干净后才整合；未将同步的规则文件混入 T1 三文件写集。配置原已为并发 32，本会话实际只有 16 个子代理槽位，未宣称 32 个同时运行。

| 检查 | 命令入口与口径 | 实测 / 退出状态 | 清洗日志 |
|---|---|---|---|
| 改动前核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ src/robomme_xhard/tests/ -m 'not gpu and not slow' -q` | 375 通过、4 失败、2 跳过、134 排除；8.83 秒；pytest 退出 1 | `records/xh-coll-timing-baseline-cpu-1012.summary.log` |
| T1 首次定向测 | 工作树借主 `.venv`、`PYTHONPATH` 指向工作树 `src`，同一 uv 入口；`test_swap_plan.py test_swap_collision_gpu.py -q -m 'not gpu'` | 30 通过、15 排除；3.21 秒；退出 0 | `records/xh-coll-timing-T1-cpu-final-1012.summary.log` |
| T1 审查修复后定向测 | 同上；补积分后拒绝、共享边界捕获、极小 q 的 JSON 读回反例 | 31 通过、15 排除；3.26 秒；退出 0 | `records/xh-coll-timing-T1-reviewfix-final-cpu-1012.summary.log` |
| 主检出整合核心短测 | 与改动前完全相同的测试入口与选择条件 | 381 通过、4 失败、2 跳过、134 排除；8.72 秒；pytest 退出 1；四项失败集合精确对照包装退出 0 | `records/xh-coll-timing-merged-cpu-1012.summary.log` |

```text
PRE_MERGE_REVIEW=PASS base=b81a820f1c3e2ce93a4291e2666782f093320a63 tip=2122a20179a6ad5d51835ae14832c940d5638dc8 findings=0
XHARD_TIMING_CPU=PASS tests=31
XHARD_CONTROL_CONTEXT=PASS cpu=1 gpu=未验证
XHARD_CORE_SHORT=PASS baseline_failures=4 new_failures=0 pytest_exit=1 passed=381
XHARD_P1_ZERO=PASS
POST_MERGE_REVIEW=PASS component_tip=2122a20179a6ad5d51835ae14832c940d5638dc8 files=3 conflicts=0 bytes_equal=1
```

前三项中静态审查与 CPU 验证分别报告，不把静态审查当成 GPU 通过。vendored SHA256 仍为 `bbe87eec3c36ab54e703a6ff741a5fdd3217c11e2a1541eb95d8f013c852302b`。

### 唯一 GPU 首探针与完整数值

从上述 **clean HEAD** 于 **2026-10-12 17:56:49 EDT** 在 sled-vail GPU0 起跑，单环境 CPU PhysX、GPU 渲染，单任务 VideoUnmaskSwap、seed5700、xhard12。实际命令为：

```bash
PYTHONUNBUFFERED=1 CUDA_VISIBLE_DEVICES=0 \
XHARD_TIMING_EVIDENCE_ROOT=/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/tests/swap-timing/run-1791842209792896638 \
UV_CACHE_DIR=/home/hongzefu/.cache/uv timeout 280s uv run --no-sync python -m pytest \
src/robomme_xhard/tests/test_swap_collision_gpu.py -q -s -m gpu -x \
-k 'test_real_step_first_start_and_shared_endpoint and VideoUnmaskSwap'
```

唯一实际启动会话为 `xh-coll-timing-probe-1012`，pane PID 3631415；日志开头原样记录 `LAUNCH_SHA`、时间、空 `LAUNCH_PORCELAIN` 与 `LAUNCH_PREFLIGHT=PASS`。测试 **1 失败、17 排除，14.94 秒，`EXIT_CODE=1`**，没有超时、没有重试。tmux 会话已自行退出，其他六个原有会话保持原样。监听的 `tail --pid` 一度因已结束 pane 的僵尸 PID 而仍等待，主会话核对后仅停止自己启动的 tail PID 3632021；监听退出 143 与测试退出 1 分开记，不把监听退出当成 GPU 结果。

| 位置 / 检查 | 实测 |
|---|---|
| 第 0 段起点，控制步 64 | `endpoint_match=true`，四字段 delta 全零，整段扫掠 `rejection=null`；粗筛间隙下界 0.03739392318516008 米 |
| 第 1 段共享端点，控制步 114 | 最近邻绑定通过，`endpoint_match=false`，`mismatches=["a_q"]`；`SwapBindingError / segment_start / endpoint_binding` |
| 时序与次数 | 起点 64、114 的 `_before_control_step` 各调用一次；失败前累计 `substep_before=250`、`substep_after=250`；段起点证据均标注 `before_physics` |
| 完整数值留证 | 每个控制步断言前写 JSON，共 115 份；最后文件的返回计数为 115，但 fatal 的实际控制步为 114；代码 SHA 全部与起跑版本相同 |

第 1 段的 `a_p`、`b_p`、`b_q` 逐位相同，只有 `a_q` 在 float64 正规化后不同：

```text
actual a_q = [2.296002475828282e-05, -0.9874737339297874, 0.15778340521615863, 0.0001459794304943155]
cached a_q = [2.2960025639515637e-05, -0.9874737345758703, 0.15778340117270856, 0.00014597942751888953]
delta a_q = [-8.812328172952757e-13, 6.460828538834562e-10, 4.043450074764365e-09, 2.975425976567067e-12]
```

```text
XHARD_SEG_START_ALIGN=FAIL task=VideoUnmaskSwap seed=5700 segment=1 control_step=114 mismatches=a_q max_abs_delta=4.043450074764365e-09
XHARD_TIMING_PROBE_PHASE=PASS first_start=64 shared_start=114 calls=1,1 before=250 after=250
XHARD_EVIDENCE_JSON=PASS files=115 sha=b7be8956e8399b33ea6fe7d889107f7a94e80ec8
TIMING_ARCHIVE=PASS originals=120 bytes=2896211 snapshots=2 logs=5
```

时序/证据通过不替代仍为 FAIL 的端点闸门。这是端点绑定失败，**不是已证实碰撞**：该段 fatal 的 `rejection=null`，源码在端点失败后返回，尚未执行第 1 段实际扫掠。

### 只读诊断、证据归档与停止边界

固定源码 `statechange.py::swap_flat_two_lane` 在起点仍执行 float32 四元数混合及归一化，再经 `sapien.Pose` / `set_pose`；判据把真实读回及缓存分别转换成 float64 并正规化。对已保存的缓存原始四元数仅做离线数组计算：`a` 的 float32 范数为 **1.0000001192092896**，重新执行父类的起点 float32 归一化后，数组逐位等于 JSON 中实际原始四元数；缓存与实际原始 q 的最大差为 **1.1920928955078125e-07**。`b` 的 float32 范数为 1.0，原始 q 没变。这是对已有数值的重放，没有再次创建环境或重跑 seed；它证明该样本的数值变化可被此计算复现，不独断 SAPIEN 中间步骤的全部贡献，也不推及其他 seed、任务或档位。

独立审查只读固定起跑 SHA 与完整 JSON，确认首段通过、共享端点仅 q 差异、拒绝字段和源码链路：`SOURCE_DIAG_REVIEW=PASS sha=b7be8956e8399b33ea6fe7d889107f7a94e80ec8 evidence=完整JSON`。没有新执行仓库脚本、测试或仿真。

两份关键 JSON 原样归档为 `records/timing-first-start-seed5700.json` 与 `records/timing-shared-start-failure-seed5700.json`。五份日志按回车转行、剔除 tqdm、清除行末空白后归档；原始字节继续留在 `artifacts/logs/`。`records/timing-evidence-manifest.json` 记录五份原始日志和 115 份原始 JSON 的绝对路径、字节数、SHA256，另记清洗日志的归档 SHA256。所有 JSON 原始值无舍入，源产物不删除。

按计划 R10-T/runbook 停止：其余 GPU 契约、新时序 D0、三任务正常 smoke、180 卡全量、成功率统计与六列视频均未执行。因此 `XHARD_SMOKE_E2E`、正常检测耗时倍数、每卡磁盘量仍未验证，本轮不能交付全量成功率或视频。

下一步需要用户裁决端点契约方向。按现行 `AGENTS.md` 第 2 条「执行中调整计划：必须彻底停止实施，等待用户重新完整审查」，不能自行把缓存 q 改为父类写入后的预期 q、改为容差比较或覆写父类姿态写入。候选方向可优先讨论“按父类确定的 float32 起点变换，从缓存独立构造预期输入，仍精确比较”，但这会改变端点契约，必须先修订完整 HTML 并经用户审查；当前没有实施该方向、没有改判据。
