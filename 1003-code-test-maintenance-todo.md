待办清单：代码与短测维护（2026-10-03）

> **范围只有三件纯代码改动**：①步数上限表 `TIER_MAX_STEPS` 的去留（B5）；②清理 V7／V8 旧用例与只服务它们的夹具（C2-3、C2-4、C2-5、C2-8）；③核心短测本身的问题（C1 六个长期失败、C2-1 核心集拆分、C2-6 重复断言、C2-7 收集范围、C2-9 测试缺口）。三件分别在第一节、第二节、第三节写怎么改；第四节写怎样保证改完后生成与评估仍在噪声范围内一致。
>
> **不在本方案**：资源清理归 [资源清理方案](1003-resource-cleanup-plan.md)；重复运行噪声的测量与回归闸门归 [噪声基线方案](1003-noise-baseline-plan.md)（正在实施），本方案只消费它的闸门、不另测噪声。本文旧版写入的「生成与 test evaluation 全量 A/B 对拍合同」（`N_V9`／`N_TEST`／`N_COMPAT`、E1／E2／E3、6784 次轨迹预算）已整段撤出。小修 G1（`_freeze.py` 档位预检）、D3（V8 评估脚本收尾与重启计数）、B6（站点常量与身份文件导出跟进）、`export_eval_identities.py` 过时说明文字也不在本方案，仍留在 [未定事项清单](docs/1002-pending-decisions.md) 原条目。
>
> 用户本轮原话（2026-10-03）：「这个的代办是这样说错了你看我现在已经有一个噪声的计划并且正在实施我有一个清除data的计划也正在准备实施了你这个项目只需要部署上限的问题和清理V7V8的就用例以及短测内容的问题就是纯代码的改动」「然后写的时候也分开写这三个点分别怎么改。然后如何保证噪声的一致性」。
>
> 规划锚点 `PLAN_BASE=194356b84f2d035e9fc51b3394a92e2ad631a10d`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`；commit 体例 `<大>.<小>[.<修订>] 中文描述`。本文只是待办与方案，实施须用户说「执行」。

# 第一部分（给人看）

## 已完成

- [x] 生成对拍的事实与结论成文：[`docs/1003-generation-parity-reproducibility.md`](docs/1003-generation-parity-reproducibility.md)（12.346）
- [x] `.gitignore` 忽略 `runs/` 与 mp4、mkv、h5 等媒体文件（12.348）

## 总览与已定口径

一句话：改测试与 pytest 配置让短测变绿、变快、去掉历史包袱；步数上限表推荐原样保留；用「生成与评估代码零 diff」这条静态事实保证不影响噪声一致性，只有当 B5 选了改表才去跑噪声基线方案的回归闸门。

1. 第二、三节只改 `tests/`、`pyproject.toml` 的 pytest 段、`AGENTS.md`、README 与待定清单；不改 `src/`、`scripts/` 任何文件（第一节选 (b)(c) 时除外）。
2. 不改 `src/robomme/`（P2）、三个上游入口（P1）、交付规格与 HDF5、旧容差。
3. B5 推荐 (a)；选 (b)(c) 属评估行为变更，须先等噪声基线冻结、再按第四节报预算跑闸门。
4. 删旧用例以「契约去向表」为准，不按文件名批删。
5. 本方案 (a) 路线 reset／轨迹预算为 0；(b)(c) 路线的预算见第四节，需另行一次性授权（P3）。

## 一、步数上限表 `TIER_MAX_STEPS`（B5）怎么改

**现状**：公开入口 `scripts/evaluation_hard.py` 已固定 `max_steps=1600`、不查表；包内表 `src/robomme_hard/env_record_wrapper/hard_specs.py::TIER_MAX_STEPS = {xhard0: 1300, xhard1～5: 1600}` 只剩这些使用者：`scripts/eval-official/env_client.py::tier_max_steps`（客户端起环境前核对 `effective_max_steps` 并以 `step_cap` 截断）、`scripts/eval-official/v8_manifest.py`（清单写 `effective_max_steps`）、`scripts/parity/hard_regression.py`（reset-replay、eval-smoke、step-headroom）、`scripts/injection-dev/site/v8_subgoal_lengths.py`（站点出图）。**生成链路不读这张表**（生成用规格 header 的 `exec_cap`＝`V8_EXEC_CAP`＝1600），已核：`scripts/injection-dev/` 下只有站点出图引用它。

| 选项 | 具体改动 | 影响 |
|---|---|---|
| **(a) 保留（推荐）** | 代码不动；把三个测试里重复的值断言收成一处（归第三节 C2-6）；`src/robomme_hard/README.md`、`docs/1002-pending-decisions.md` 把「去留待定」改为「保留：表只服务 eval-official 流水线与历史评估口径，公开入口固定 1600」 | 零行为变化 |
| (b) 拉平 1600 | `hard_specs.py` 中 xhard0 值 1300→1600；`test_xhard0_native.py::test_TIER_MAX_STEPS六档且xhard0为1300`（改名＋改值）、`test_v8_specs_schema.py`、`test_v9_packaged_800.py` 的断言；`hard_regression.py` step-headroom 的 xhard0 口径说明；README | eval-official 与 `hard_regression` 的 xhard0 上限变 1600；已跑的 xhard0 16 任务 × 1 档 × 12 局 = 192 局评估记录（1300）与表不再一致 |
| (c) 删表 | 改成单常量 `EXEC_CAP=1600`，上面四个使用者全部改引用；`__init__.py` 导出同改 | 同 (b)，改动面最大 |

推荐 (a) 的理由：它是纯代码、零行为变化，正好落在本方案边界内；(b)(c) 只换来「两处口径统一」，代价是评估流水线行为变化与一轮回归闸门（第四节）。

- [ ] 用户定 (a)／(b)／(c)
- [ ] 按结论改（(a) 只改文档与测试去重）

## 二、清理 V7／V8 旧用例与夹具怎么改

**做法分三步：先列表、再迁移、最后删。**

1. **列契约去向表**（交用户过目后才动手删）：对每个候选文件逐条列「旧 nodeid → 它守的契约 → 去向」，去向三选一：迁到哪个现行用例／已被哪个现行用例覆盖（写出 nodeid）／契约已废、直接删。
2. **候选对象与各自处理**：
   - `test_v7_*.py` 共 9 个（`binfill_nested`、`candidate_pool`、`freeze_schema`、`layered_recorder`、`outer_arc`、`seed_rule`、`site_catalog`、`tier_values`、`whitelist_semantics`）：测的是 V9 不再调用的 v7 链路（母布局派生、白名单、v7 seed 规则等）。V9 仍用的部分（如 `tier_values` 的取值表、`freeze_schema` 中 /2、/3 的 schema 反例）迁走，其余删除。
   - 靠 `monkeypatch.setattr(EXPECTED_CELLS, V8_CELLS)` 钉回 V8 数字（1070／1262）才能过的用例：`test_v8_delivery_flow.py::test_四片生成合并聚合43格`、`test_v8_eval_manifest.py` 三条（`test_夹具规模` 等）、`test_v8_regression_cmds.py::test_delivery_set三种格表往返[full]`——改成断言包内 V9（800／992）；若该用例只是 V8 格表的回归、V9 已有同类覆盖，则删。
   - 名不副实：`tests/_shared/v7_tier_values.py` 改名 `tests/_shared/tier_values.py`（内容不变），三个引用方 `test_v7_tier_values.py`、`test_v8_regression_cmds.py`、`test_sampling_config_split.py` 同步改 import；`test_hard_builder_xhard0.py` 里函数名与断言值对齐。
   - `tests/_shared/v7_specs_fixture.py`：所有引用方删完后才删。
   - `tests/fixtures/injection_legacy/*.json`：`grep -r injection_legacy tests scripts src` 无引用才删。
   - `test_hard_state_machine.py`、`test_v4_xhard_stopcube.py`、`test_v5_xhard_*.py` 里的 v7 字样：逐条核对，只是注释提及就不动。
3. **保留项**：`tests/fixtures/v7_specs_sample/` 仍被活跃的 `test_v8_regression_cmds.py` 当反例用，保留；名字带 v7／v8 不是删除依据。被删用例里仍有用的负例（空集、重复／漏身份、错签名、错绑定、跨版本数量）必须先迁到现行用例再删。

- [ ] 契约去向表（用户过目）
- [ ] 迁移仍有用的正反例
- [ ] 按表删除与改名
- [ ] 核对 `injection_legacy`、v4／v5 测试里的 v7 字样

## 三、核心短测内容怎么改

**C1 修 6 个长期失败**（只改测试，被测官方源码与 `1fadc0ec` 逐字节相同，不动）：

| 测试 | 改法 |
|---|---|
| `test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal` | 断言改成官方真实返回 `[]`，函数名同步改 |
| `test_TaskGoal.py::test_swingxtimes_multiple` | 文本改为 `back-and-forth`，保留次数／颜色检查 |
| `test_step_error_handling.py::test_step_error_returns_status_error` | 官方 `DemonstrationWrapper.step` 没有 try：改为调用真实 `step` 断言异常向上传播；若要保留「应捕获」的诉求，标 `xfail(strict=True, reason=官方未实现)` |
| `test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except` | 子串断言改为匹配官方实际写法 `info.get("status", "unknown")`；裸 try 的检查对 `dataset_replay.py`（上游逐字节）不适用，限定到我们自己的脚本或标 `xfail` |
| `test_v8_eval_report.py`、`test_v8_eval_video_mover.py` 的 `test_zz_summary_line` | 去掉「整个会话失败数为 0」的耦合，只断言本文件业务报告；会话退出码由 pytest 自己给 |

**C2-1 拆核心集**：`pyproject.toml::tool.pytest.ini_options.markers` 加 `core`；在选定文件顶部 `pytestmark = pytest.mark.core`。候选：`test_v9_packaged_800`、`test_hard_builder_xhard0`、`test_xhard0_native`、`test_v9_*`、`test_upstream_*`、`test_scripts_do_not_import_tests`，以实测 ≤120 s（硬上限 280 s）为准增删。不靠把其余全标 `slow` 凑时间：非 core 用例照旧可用 `-m 'not gpu and not slow'` 全跑（预计约 8 分钟，走 tmux）。

**C2-6 合并重复断言**：`TIER_MAX_STEPS` 六档值只留 `test_xhard0_native.py` 一处；`EXPECTED_CELLS` 合计只留 `test_v9_packaged_800.py` 一处；另外三处删重复行（与 B5 (a) 合做）。

**C2-7 收窄收集**：`pyproject.toml` 加 `testpaths = ["tests"]`，裸 `pytest` 不再扫 `third_party/`（现报 53 个收集错误）。

**C2-9 补测试**：新增 `tests/lightweight/test_xhard0_disabled_paths.py`，覆盖 `hard_regression.py::cmd_xhard0_reset_parity` 关档时的 `SystemExit` 与 `export_eval_identities.py` 关档时 `official=skipped`；用 `pytest.raises`，不吞异常。

**收尾**：`AGENTS.md`「覆盖第 4 条」的核心命令改为 `timeout 280s uv run --no-sync python -m pytest -m 'core and not gpu and not slow' -q`，附实测耗时。

- [ ] C1 六个失败
- [ ] C2-1 core 标记与实测耗时
- [ ] C2-6 重复断言
- [ ] C2-7 testpaths
- [ ] C2-9 两条新测试
- [ ] AGENTS.md 核心命令

## 四、怎样保证噪声一致性

目标：改完以后，生成出的 h5 与评估结果相对改前仍落在噪声基线方案定下的噪声带内（理想是完全不变）。分两种情况：

**情况 1：B5 选 (a)，三件事全部只改测试与文档——靠「代码零 diff」静态保证，不用跑任何 reset。**

- 生成与评估在运行时只执行 `src/` 与 `scripts/` 下的代码；`tests/` 不会被生产入口导入（`tests/lightweight/test_scripts_do_not_import_tests.py` 用 AST 钉死这一点，属 core 集）。`pyproject.toml` 只改 `[tool.pytest.ini_options]`，不进依赖解析，`uv.lock` 不变。
- 所以只要下面三条成立，生成与评估执行的字节就与改前完全相同，噪声分布不可能因本方案改变——这是比「跑一遍落在噪声带内」更强的结论：
  1. `git diff --quiet <BASE> <HEAD> -- src scripts uv.lock` 退出码 0 → `MAINT_RUNTIME_CODE=PASS changed=0`
  2. `git diff --name-only <BASE>..<HEAD> -- pyproject.toml` 若非空，`git diff <BASE>..<HEAD> -- pyproject.toml` 的 hunk 全在 `[tool.pytest.ini_options]` 段内 → `MAINT_PYPROJECT=PASS scope=pytest-only`
  3. `UPSTREAM_GUARD=PASS`（官方源码逐字节）
- 这正对应噪声基线方案第五节「任何代码改动：核心短测 + `UPSTREAM_GUARD`，预算 0」那一行；不触发 `RESET_GATE`／`GEN_NOISE_GATE`／`EVAL_NOISE_GATE`。

**情况 2：B5 选 (b) 或 (c)——动了 `hard_specs.py` 与评估客户端，必须跑噪声闸门，且要等噪声基线先冻结。**

- 按噪声基线方案第五节对号：动到规格模块 → `RESET_GATE`（G9 + D0 九层摘要一遍，与冻结摘要比，九层全等）；动到评估客户端 → `EVAL_NOISE_GATE`（两模型在 G9 与 D0 上各评一遍）。生成链路不读这张表，不跑 `GEN_NOISE_GATE`，但用上面的 `git diff` 证明 `scripts/injection-dev/` 生成部分零改动。
- 预算（按噪声基线方案第五节，P5 乘式）：reset 闸门 `(16 任务 × 12 局 + 16 任务 × 1 档 × 12 局) = 384` 次探针、reset `384 × 2 + 43 格 × 1 = 811` 次；评估闸门 `2 模型 × (192 + 192) = 768` 条轨迹、reset 上限 1536 次。超 P3 阈值，回归无长期授权（噪声方案裁决 4），须先一次性报批。
- ⚠ 判读要分开：G9 是 xhard1～5，上限本来就是 1600，(b) 下应与基线一样落在噪声带内，按闸门原判据 PASS／FAIL；D0 是 xhard0，(b) **有意**把上限从 1300 放到 1600——原先在 1300 步被截断的局现在能多走，成功率可能上升、步数分布必然变。所以 D0 的 `EVAL_NOISE_GATE` 不能当「一致」证据，只能作为「预期变化」单列报告（逐局列出步数 >1300 的局及终态迁移），由用户裁决是否接受；不为让它 PASS 改阈值。
- 次序：噪声基线 `NOISE_BASELINE=PASS` 之前不做 (b)(c)；否则没有冻结参照可比。

## 验收

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| 运行时代码零改动（情况 1） | `git diff --quiet <BASE> <HEAD> -- src scripts uv.lock` | `MAINT_RUNTIME_CODE=PASS changed=0` |
| pyproject 只改 pytest 段 | 看 `pyproject.toml` diff 的 hunk 位置 | `MAINT_PYPROJECT=PASS scope=pytest-only` |
| 官方源码未动 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `UPSTREAM_GUARD=PASS` |
| 录像器冻结 | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` | 退出码 0 |
| 6 个长期失败消失 | 定向跑 C1 四个文件 | `MAINT_C1=PASS failed=0` |
| 核心集非空且够快 | `timeout 280s uv run --no-sync python -m pytest -m 'core and not gpu and not slow' -q --durations=20` | `MAINT_CORE=PASS collected=<n> wall_s=<实测>` |
| 收集不扫 third_party | `uv run --no-sync python -m pytest --collect-only -q` | `MAINT_COLLECT=PASS errors=0` |
| 删用例不丢契约 | 去向表每行有去向；迁移后的正反例通过 | `MAINT_TEST_COVERAGE=PASS` |
| 噪声闸门（仅情况 2） | 噪声基线方案 `check-reset`／`check-eval` | `RESET_GATE=PASS`；G9 `EVAL_NOISE_GATE=PASS`；D0 单列预期变化报告 |

## 子代理分工与合并（简述）

拆三块：M2 修 C1 六个失败并补 C2-9 两条测试；M1 清 V7／V8 旧用例与夹具（含 `tier_values` 改名）；主会话自己做 B5、重复断言合并（与 B5 同在那几个文件里）、`pyproject.toml`（core 标记、testpaths）、AGENTS／README／待定清单。先合 M2（短测先变绿），再合 M1，最后主会话打 core 标记并实测耗时。每次合并前审改动文件是否越界、定向测试是否通过；合并后跑核心集、`UPSTREAM_GUARD` 与 `MAINT_RUNTIME_CODE`。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`（P2）、`scripts/` 三个与上游逐字节相同的入口（P1）、交付规格／HDF5、旧容差与历史判定。
- R2：情况 1 不启动生成、reset、评估、GPU、长任务或集群作业；只跑 `tests/lightweight/` 的 CPU 用例。情况 2 的闸门运行由噪声基线方案的包装执行，预算另批。
- R3：测试内 mock／patch 限定在测试进程且不落盘；不新增 `scripts/` 顶层文件；不改 `uv.lock`。
- R4：Python 一律 `uv run --no-sync`；worktree 内按 `CLAUDE.md` 取法 `UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<worktree>/src`，先打印 `robomme_hard.__file__` 核实。

## 一、逐文件清单

1. **C1**：`tests/lightweight/test_TaskGoal.py`、`tests/lightweight/test_step_error_handling.py`；`tests/lightweight/test_v8_eval_report.py`、`tests/lightweight/test_v8_eval_video_mover.py` 的 `test_zz_summary_line`。
2. **C2-9**：新增 `tests/lightweight/test_xhard0_disabled_paths.py`。
3. **V7／V8 清理**：`tests/lightweight/test_v7_*.py`（9 个）、`tests/_shared/v7_specs_fixture.py`、`tests/_shared/v7_tier_values.py`→`tier_values.py` 及引用方（`test_v7_tier_values.py`、`test_v8_regression_cmds.py`、`test_sampling_config_split.py`）、`test_v8_delivery_flow.py`、`test_v8_eval_manifest.py`、`test_v8_regression_cmds.py`、`test_hard_builder_xhard0.py`（仅函数改名）、`tests/fixtures/injection_legacy/`（核实无引用后）。`tests/fixtures/v7_specs_sample/` 保留。
4. **重复断言**：`test_xhard0_native.py`（保留权威 `TIER_MAX_STEPS` 断言）、`test_v8_specs_schema.py`、`test_v9_packaged_800.py`（保留权威 `EXPECTED_CELLS` 合计）、`test_hard_builder_xhard0.py`（删重复合计行）。
5. **pytest 配置**：`pyproject.toml::tool.pytest.ini_options` 加 `testpaths` 与 `core` 标记；`tests/conftest.py` 不改（打标用文件内 `pytestmark`）。
6. **B5**：(a) `src/robomme_hard/README.md` 去留表述；(b) 另加 `src/robomme_hard/env_record_wrapper/hard_specs.py::TIER_MAX_STEPS`、`scripts/parity/hard_regression.py` 文档串、相关测试；(c) 另列清单再批。
7. **文档**：`AGENTS.md`「覆盖第 4 条」；`docs/1002-pending-decisions.md` B5／C1／C2 结案。

## 二、子代理分配表

派发前核对 `worktree.baseRef="head"`、主检出 `git status --short --ignore-submodules=dirty` 为空、记 `BASE`。

| 编号 | 目标 | 可写集合 | 禁触 | 依赖／合并顺序 | 验收（worktree 内，CPU） | 资源 |
|---|---|---|---|---|---|---|
| M2 | C1 + C2-9 | 第一节 1、2 项 | R1；M1／主会话文件 | 第 1 个合并 | 定向 pytest 四个 C1 文件与新文件，`failed=0` | CPU，≤5 分钟 |
| M1 | V7／V8 清理与改名 | 第一节 3 项；交回契约去向表 | R1；M2 文件；第一节 4 项中除 `test_hard_builder_xhard0.py` 函数名外的内容 | 第 2 个合并；去向表须用户先过目才派删改 | 受影响文件定向 pytest；`grep -r v7_tier_values tests/` 为空 | CPU，≤5 分钟 |
| 主会话 | B5、重复断言、pytest 配置、文档 | 第一节 4～7 项 | R1 | 最后；`test_hard_builder_xhard0.py` 在 M1 合入后再动 | 第一部分验收表全部判定行 | CPU |
| 审查 | 合并前审 | 无（只读，sonnet） | 一切写入 | 每个分支一个审查者 | `PRE_MERGE_REVIEW=PASS` | — |

共享文件裁决：`test_v8_regression_cmds.py` 归 M1；`test_hard_builder_xhard0.py` 函数改名归 M1、重复断言删除归主会话（M1 合入后）。

## 三、闸门总表

| 时点 | 判定行 |
|---|---|
| 每次合并前 | `PRE_MERGE_REVIEW=PASS`；`git diff --name-only <BASE>..<TIP>` ⊆ 可写集合 |
| 每次合并后 | 核心集通过；`UPSTREAM_GUARD=PASS`；`MAINT_RUNTIME_CODE=PASS changed=0`（情况 1）；`ls -1 scripts/*.py` 恰为四入口 |
| 收尾 | 第一部分验收表全部判定行；情况 2 另加噪声闸门 |

## 四、风险与盲区

- 删旧用例可能丢负例：靠契约去向表兜底，表外不删。
- `xfail` 可能掩盖真问题：只用于「官方确实没实现」的两项，`strict=True` 并写原因。
- 核心集耗时依机器负载浮动，以实测为准。
- 情况 1 的「零 diff ⇒ 噪声不变」只覆盖本仓库代码；依赖、驱动、节点变化引起的噪声漂移归噪声基线方案管，本方案不声称覆盖。
- 情况 2 的 D0 评估是有意的行为变化，不能读成「一致」。
- 噪声基线方案第五节末句写「确定性严格对拍（固定动作环境、客户端协议）按维护方案执行」；本方案已撤出该对拍，那一句需要噪声方案的负责会话改写（本方案不改他人文件）。

## 五、留档与提交

每块按 `--no-ff` 合入、主会话逐路径暂存；commit body 写用户原话、改动、定向测试与核心集实测、`MAINT_RUNTIME_CODE` 判定行。情况 1 不建 `docs/validation/` 运行档案（无长跑）；情况 2 的闸门运行按噪声基线方案留档。文档本身交付只做 `git diff --check` 与两部分结构自检。
