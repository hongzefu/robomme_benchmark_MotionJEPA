# 交换碰撞实现：已整合，GPU 端点对齐失败

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
