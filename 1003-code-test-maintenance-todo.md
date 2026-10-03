代码与短测维护计划（2026-10-03）

> 三件纯代码改动：①步数上限表 `TIER_MAX_STEPS`；②清理 V7／V8 旧用例；③核心短测内容。另写改完后如何保证噪声一致性。
>
> 锚点 `PLAN_BASE=5fe14d79`，分支 `newtaskRelease-taskV9`。实施须用户说「执行」。

# 第一部分（给人看）

## 一、步数上限表 `TIER_MAX_STEPS` 怎么改

**现状**：`src/robomme_hard/env_record_wrapper/hard_specs.py::TIER_MAX_STEPS = {xhard0: 1300, xhard1～5: 1600}`。公开入口 `scripts/evaluation_hard.py` 已固定 `max_steps=1600`、不查表。仍在用表的：`scripts/eval-official/env_client.py::tier_max_steps`、`scripts/eval-official/v8_manifest.py`（写 `effective_max_steps`）、`scripts/parity/hard_regression.py`、`scripts/injection-dev/site/v8_subgoal_lengths.py`。生成链路不读这张表（生成用规格 header 的 `exec_cap`＝1600）。

| 选项 | 改动 | 影响 |
|---|---|---|
| **(a) 保留（推荐）** | 代码不动；三处重复的值断言收成一处（见第三节）；`src/robomme_hard/README.md` 的「去留待定」改为「保留：只服务 eval-official 流水线，公开入口固定 1600」 | 零行为变化 |
| (b) 拉平 1600 | `hard_specs.py` 的 xhard0 改 1600；`test_xhard0_native.py`、`test_v8_specs_schema.py`、`test_v9_packaged_800.py` 断言；README | eval-official 的 xhard0 上限变 1600，与已跑的 16 任务 × 1 档 × 12 局 = 192 局 xhard0 评估记录不一致 |
| (c) 删表 | 改单常量 `EXEC_CAP=1600`，上面四个使用者全改 | 同 (b)，改动面最大 |

## 二、清理 V7／V8 旧用例怎么改

先列表、再迁移、最后删：

1. **契约去向表**：每个候选用例列「nodeid → 它守的契约 → 去向（迁到某现行用例／已被某 nodeid 覆盖／契约已废直接删）」，用户过目后才动手。
2. **处理对象**：
   - `tests/lightweight/test_v7_*.py` 共 9 个（`binfill_nested`、`candidate_pool`、`freeze_schema`、`layered_recorder`、`outer_arc`、`seed_rule`、`site_catalog`、`tier_values`、`whitelist_semantics`）：V9 仍用的部分（取值表、/2、/3 schema 反例）迁走，其余删。
   - 靠 `monkeypatch.setattr(EXPECTED_CELLS, V8_CELLS)` 钉回 V8 数字（1070／1262）的用例：`test_v8_delivery_flow.py::test_四片生成合并聚合43格`、`test_v8_eval_manifest.py` 三条、`test_v8_regression_cmds.py::test_delivery_set三种格表往返[full]`——改断言包内 V9（800／992），或已有同类覆盖则删。
   - `tests/_shared/v7_tier_values.py` 改名 `tier_values.py`（内容不变），引用方 `test_v7_tier_values.py`、`test_v8_regression_cmds.py`、`test_sampling_config_split.py` 同步改 import；`test_hard_builder_xhard0.py` 函数名与断言值对齐。
   - `tests/_shared/v7_specs_fixture.py`：引用方删完后删。
   - `tests/fixtures/injection_legacy/*.json`：`grep -r injection_legacy tests scripts src` 无引用才删。
   - `test_hard_state_machine.py`、`test_v4_xhard_stopcube.py`、`test_v5_xhard_*.py` 里的 v7 字样：逐条核对，只是注释则不动。
3. **保留**：`tests/fixtures/v7_specs_sample/` 仍被 `test_v8_regression_cmds.py` 当反例用。被删用例里仍有用的负例（空集、重复／漏身份、错签名、错绑定）先迁再删。

## 三、核心短测内容怎么改

**修 6 个长期失败**（只改测试，官方源码不动）：

| 测试 | 改法 |
|---|---|
| `test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal` | 断言改为官方真实返回 `[]`，函数名同步 |
| `test_TaskGoal.py::test_swingxtimes_multiple` | 文本改 `back-and-forth`，保留次数／颜色检查 |
| `test_step_error_handling.py::test_step_error_returns_status_error` | 官方 `DemonstrationWrapper.step` 无 try：改为断言异常向上传播；或标 `xfail(strict=True, reason=官方未实现)` |
| `test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except` | 匹配官方实际写法 `info.get("status", "unknown")`；裸 try 检查不适用于上游逐字节的 `dataset_replay.py`，限定到自有脚本 |
| `test_v8_eval_report.py`、`test_v8_eval_video_mover.py` 的 `test_zz_summary_line` | 去掉「整个会话失败数为 0」的耦合，只断言本文件业务 |

**拆核心集**：`pyproject.toml` 加 `core` 标记，选定文件顶部 `pytestmark = pytest.mark.core`。候选 `test_v9_packaged_800`、`test_hard_builder_xhard0`、`test_xhard0_native`、`test_v9_*`、`test_upstream_*`、`test_scripts_do_not_import_tests`，以实测 ≤120 s（硬上限 280 s）增删；其余用例照旧可显式跑。

**合并重复断言**：`TIER_MAX_STEPS` 值只留 `test_xhard0_native.py` 一处；`EXPECTED_CELLS` 合计只留 `test_v9_packaged_800.py` 一处。

**收窄收集**：`pyproject.toml` 加 `testpaths = ["tests"]`，不再扫 `third_party/`。

**补测试**：新增 `tests/lightweight/test_xhard0_disabled_paths.py`，覆盖 `hard_regression.py::cmd_xhard0_reset_parity` 关档 `SystemExit` 与 `export_eval_identities.py` 关档 `official=skipped`。

**更新命令**：`AGENTS.md`「覆盖第 4 条」核心命令改为 `timeout 280s uv run --no-sync python -m pytest -m 'core and not gpu and not slow' -q`，附实测耗时。

## 四、怎样保证噪声一致性

**情况 1：步数上限表选 (a)——三件事都只改测试与 pytest 配置，用「运行时代码零 diff」静态保证，不跑 reset。**

生成与评估运行时只执行 `src/` 与 `scripts/` 的代码；`tests/` 不被生产入口导入（`test_scripts_do_not_import_tests.py` 用 AST 钉死，属 core 集）；`pyproject.toml` 只改 `[tool.pytest.ini_options]`，`uv.lock` 不变。下面三条成立，生成与评估执行的字节与改前完全相同，噪声分布不会因本次改动变化：

1. `git diff --quiet <BASE> <HEAD> -- src scripts uv.lock` 退出 0 → `MAINT_RUNTIME_CODE=PASS changed=0`
2. `pyproject.toml` 的 diff 全在 `[tool.pytest.ini_options]` 段内 → `MAINT_PYPROJECT=PASS scope=pytest-only`
3. `UPSTREAM_GUARD=PASS`

对应 [噪声基线方案](1003-noise-baseline-plan.md) 第五节「任何代码改动：核心短测 + `UPSTREAM_GUARD`，预算 0」。

**情况 2：选 (b) 或 (c)——动了规格模块与评估客户端，按噪声基线方案跑回归闸门，且须等 `NOISE_BASELINE=PASS` 冻结之后。**

- `RESET_GATE`：G9 + D0 九层摘要一遍与冻结摘要比，九层全等。预算 `(16 任务 × 12 局 + 16 任务 × 1 档 × 12 局) = 384` 次探针，reset `384 × 2 + 43 格 × 1 = 811` 次。
- `EVAL_NOISE_GATE`：两模型在 G9 与 D0 各评一遍。预算 `2 模型 × (192 + 192) = 768` 条轨迹，reset 上限 1536 次。
- 生成链路不读此表，不跑 `GEN_NOISE_GATE`，以 `git diff --quiet <BASE> <HEAD> -- scripts/injection-dev` 为零佐证（站点出图文件除外）。
- 判读分开：G9（xhard1～5，上限本就 1600）按闸门原判据 PASS／FAIL；D0（xhard0，上限 1300→1600）是有意变化，单列「预期变化」报告（逐局列出步数 >1300 的局与终态迁移），交用户裁决，不改阈值。
- 预算超 P3 阈值，运行前一次性报批。

## 验收

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| 运行时代码零改动 | `git diff --quiet <BASE> <HEAD> -- src scripts uv.lock` | `MAINT_RUNTIME_CODE=PASS changed=0` |
| pyproject 只改 pytest 段 | 看 diff 的 hunk 位置 | `MAINT_PYPROJECT=PASS scope=pytest-only` |
| 官方源码未动 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `UPSTREAM_GUARD=PASS` |
| 6 个失败消失 | 定向跑 C1 四个文件 | `MAINT_C1=PASS failed=0` |
| 核心集非空且够快 | `timeout 280s uv run --no-sync python -m pytest -m 'core and not gpu and not slow' -q --durations=20` | `MAINT_CORE=PASS collected=<n> wall_s=<实测>` |
| 收集不扫 third_party | `uv run --no-sync python -m pytest --collect-only -q` | `MAINT_COLLECT=PASS errors=0` |
| 删用例不丢契约 | 去向表每行有去向；迁移后的正反例通过 | `MAINT_TEST_COVERAGE=PASS` |
| 噪声闸门（仅情况 2） | 噪声基线方案 `check-reset`／`check-eval` | `RESET_GATE=PASS`；G9 `EVAL_NOISE_GATE=PASS`；D0 预期变化报告 |

## 步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 1 | 用户定步数上限表选项；M1 交契约去向表给用户过目 | 选项与去向表获准 |
| 2 | M2 修 6 个失败、补 2 条测试，合并 | `MAINT_C1=PASS` |
| 3 | M1 按去向表迁移、删除、改名，合并 | `MAINT_TEST_COVERAGE=PASS` |
| 4 | 主会话：步数上限表、重复断言、core 标记、testpaths、AGENTS／README | 验收表全部判定行 |
| 5 | 仅情况 2：噪声基线冻结后报批并跑闸门 | `RESET_GATE`、`EVAL_NOISE_GATE` |

## 子代理分工与合并（简述）

M2 修 6 个失败并补 2 条测试；M1 清 V7／V8 旧用例；主会话做步数上限表、重复断言、pytest 配置与文档。先合 M2，再合 M1，最后主会话改并实测核心集耗时。每次合并前审改动是否越出可写集合、定向测试是否通过；合并后跑核心集、`UPSTREAM_GUARD`、`MAINT_RUNTIME_CODE`。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`、三个上游入口、交付规格与 HDF5、`uv.lock`。
- R2：情况 1 只跑 `tests/lightweight/` 的 CPU 用例，不启动生成、reset、评估。
- R3：worktree 内用 `UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<worktree>/src uv run --no-sync`，先打印 `robomme_hard.__file__` 核实。

## 一、逐文件清单

1. M2：`test_TaskGoal.py`、`test_step_error_handling.py`、`test_v8_eval_report.py`、`test_v8_eval_video_mover.py`（仅 `test_zz_summary_line`）、新增 `test_xhard0_disabled_paths.py`。
2. M1：`test_v7_*.py`（9 个）、`tests/_shared/v7_specs_fixture.py`、`tests/_shared/v7_tier_values.py`→`tier_values.py` 及引用方、`test_v8_delivery_flow.py`、`test_v8_eval_manifest.py`、`test_v8_regression_cmds.py`、`test_hard_builder_xhard0.py`（仅函数改名）、`tests/fixtures/injection_legacy/`（核实无引用后）。
3. 主会话：`test_xhard0_native.py`、`test_v8_specs_schema.py`、`test_v9_packaged_800.py`、`test_hard_builder_xhard0.py`（删重复合计行，M1 合入后）、`pyproject.toml` pytest 段、core 标记所在文件、`src/robomme_hard/README.md`、`AGENTS.md`；选 (b) 时另加 `hard_specs.py` 与 `hard_regression.py` 文档串。

## 二、子代理分配表

| 编号 | 可写集合 | 禁触 | 合并顺序 | 验收（worktree 内，CPU） |
|---|---|---|---|---|
| M2 | 第一节第 1 项 | R1；M1／主会话文件 | 1 | 定向 pytest，`failed=0` |
| M1 | 第一节第 2 项 | R1；M2／主会话文件 | 2（去向表获准后派） | 受影响文件定向 pytest；`grep -r v7_tier_values tests/` 为空 |
| 主会话 | 第一节第 3 项 | R1 | 3 | 验收表全部判定行 |
| 审查 | 只读（sonnet） | 一切写入 | 每分支一个 | `PRE_MERGE_REVIEW=PASS` |

共享裁决：`test_v8_regression_cmds.py` 归 M1；`test_hard_builder_xhard0.py` 函数改名归 M1、断言去重归主会话。

## 三、闸门

| 时点 | 判定行 |
|---|---|
| 合并前 | `PRE_MERGE_REVIEW=PASS`；`git diff --name-only <BASE>..<TIP>` ⊆ 可写集合 |
| 合并后 | 核心集通过；`UPSTREAM_GUARD=PASS`；`MAINT_RUNTIME_CODE=PASS changed=0`（情况 1） |

## 四、风险与盲区

- 删旧用例可能丢负例：表外不删。
- `xfail` 只用于官方确未实现的两项，`strict=True`。
- 「代码零 diff ⇒ 噪声不变」只覆盖本仓库代码；依赖、驱动、节点引起的漂移归噪声基线方案。
