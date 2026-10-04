# 测试套件重设计：现状实测留档（2026-10-03）

对应计划：[`1003-code-test-maintenance-todo.md`](../../../1003-code-test-maintenance-todo.md)（第四版；原 `docs/plans/1003-test-redesign-plan.md` 已并入，原文 `git show 63f34817:docs/plans/1003-test-redesign-plan.md`）。本目录只放实测原始记录，结论与解读在计划第一部分第四节；扫描脚本见 [`records/reset_sweep.py`](records/reset_sweep.py)。

## 运行环境与代码状态

- 机器 sled-vail（环境 A），2 × RTX 6000 Ada；HEAD `86e5a015b7ba3a85c2c03cc50f5de482b9476c1d`（12.377），分支 `newtaskRelease-taskV9`。
- 启动时跟踪文件与 HEAD 一致；工作区另有并行会话的未跟踪留档 `docs/validation/newtask-v9/hf-20261003*`（不属本次）。
- 本次起过的 tmux 会话：`tcov-1003`、`tsweep-1003`，均已自行结束。

## 用户指令原话

1. 「现在的test是否完全覆盖了所有所有的内容就是你可以破坏性的对整个test进行修改我需要覆盖所有关键都是正确的。然后都尽可能不要跑GPU的任务如果有GPU任务就只做一个最简单的初始或者reset这样的 可以彻底重构这个test你可以派出SubAgent确定方案也可以实测然后再给我一个重构的计划我希望重构完的test能够覆盖这个benchmark的所有部分」
2. 「你现在测试的reset我一并授权直接开始。」

## 实测一：行覆盖率（CPU）

```bash
COVERAGE_FILE=artifacts/test-coverage-1003/.coverage uv run --no-sync --with coverage python -m coverage run \
  --include='src/*,scripts/*' -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider
```

结果：`6 failed, 1885 passed, 3 skipped, 80 deselected, 24 warnings in 611.47s (0:10:11)`，`PYTEST_EXIT=1`（6 个失败即长期失败的那 6 个），`EXIT_CODE=0`。逐文件报告见 [`records/coverage-report.txt`](records/coverage-report.txt)，日志尾见 [`records/coverage-run-summary.txt`](records/coverage-run-summary.txt)。口径限制：子进程里执行的脚本不计入。

## 实测二：reset 扫描（GPU 1，单 worker，只 reset 不 step）

规模：`xhard0 16 任务 × 1 局 + xhard1～5 共 43 格 × 1 局 = 59` 次 reset；此前另有 1 次探针（PickXtimes，`PROBE import=3.2s make=2.2s reset=0.0s total=5.5s`）。合计 60 次 reset、0 条轨迹。

判定行：`RESET_SWEEP=PASS cells=59 ok=59`，`EXIT_CODE=0`。合计 162.6 s，中位 0.73 s，最大 13.86 s（RouteStick xhard3，reset 内含 701 帧示教）。逐格记录（耗时、obs 形状、info 键、目标文本、wrapper 链、首帧摘要）见 [`records/reset-sweep.jsonl`](records/reset-sweep.jsonl)。

59 格共同观测：wrapper 链 `FailAwareWrapper → DemonstrationWrapper → TimeLimitWrapper → OrderEnforcing → <任务类>`；info 七个键；`status=ongoing`；`task_goal` 条数 1～4。

## 引用的他人实测

逐文件耗时基线由并行会话跑出（`artifacts/maintenance/baseline-durations.log`，不进 git）：`6 failed, 1885 passed, 3 skipped, 80 deselected, 24 warnings in 518.44s (0:08:38)`；最慢文件 `test_v8_eval_orchestration.py` 172.8 s。

## 重构后实测（阶段 2c，2026-10-04）

代码状态：最终 HEAD `64da6d8d`（12.419，T11、T14、T15 均已合入）；仿真冒烟在 `90025b2b` 上跑，此后的改动只涉及 `tests/` 与文档，不改生产代码与 `tests/sim`。本节起过的 tmux 会话有 `tcov-final`、`tcov-sub`、`tcov-final2`，均已自行结束。

| 项 | 命令 | 判定行 |
|---|---|---|
| 日常门禁 | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | `2716 passed, 4 skipped, 599 deselected in 126.22s`；`TEST_RESOURCE=PASS native_reset=0 gpu_init=0 weights=0 network=0 violations=0 not_verified=4`（4 个 skip 都是「未验证：缺 flask」一类） |
| 慢测试 | `uv run --no-sync python -m pytest -m slow -q` | `598 passed, 1 skipped, 2720 deselected in 175.73s`；`TEST_RESOURCE=PASS … not_verified=1`（缺 flask） |
| 仿真冒烟 | `CUDA_VISIBLE_DEVICES=<空闲卡> uv run --no-sync python -m pytest tests/sim --allow-sim-reset -q`（59 + 1 = 60 次 reset） | `60 passed in 243.31s`；`TEST_SIM=PASS cells=59 official=1 failed=0` |
| 契约清单 | `uv run --no-sync python -m pytest tests/static/test_inventory.py -q -s` | `TEST_INVENTORY=PASS unclassified=0 stale=0 exempt=14`；`TEST_CONTRACTS=FAIL entries=184 verified=166 conditional=13 blocked=3 planned=2 missing=0 pending=2`（pending 剩 C14-14〔待定 D4，用户裁决不修〕与 T3-C02-task-order〔默认任务顺序无字面值断言〕） |
| 植入 | `uv run --no-sync python tests/mutation/run_mutants.py --tag post-t15` | `TEST_MUTATION=PASS seeded=107 caught=107 survived=0 not_executable=1 not_applied=0 no_recipe=0 baseline_fail=0 repo_changed=0`（not_executable 只有 challenge:M19，用户裁决不修）；逐项记录见 [`records/mutation-post-t15.jsonl`](records/mutation-post-t15.jsonl) |
| 覆盖率 | `COVERAGE_FILE=artifacts/test-coverage/.coverage uv run --no-sync --with coverage python -m coverage run --include='src/*,scripts/*,challenge_interface/*' -m pytest tests/static tests/contract tests/unit tests/pipeline -m 'not slow' -q -p no:cacheprovider` | `TEST_COVERAGE=PASS`，逐分区对照见下表 |

覆盖率按分区对照（现状为旧测试 `tests/lightweight/`，口径见「实测一」；两次都不计子进程）：

| 分区 | 现状 | 新值 |
|---|---|---|
| 官方 wrapper 层 `src/robomme/env_record_wrapper` | 14.7% | 85.0% |
| 官方任务环境 `src/robomme/robomme_env` | 19.5% | 65.5% |
| hard 包 wrapper 与发布契约 `src/robomme_hard/env_record_wrapper` | 34.8% | 83.5% |
| hard 任务环境 `src/robomme_hard/robomme_env` | 52.6% | 72.9% |
| `scripts/parity` | 63.5% | 73.2% |
| `scripts/injection-dev` | 65.6% | 79.3% |
| `scripts/eval-official` | 79.3% | 85.8% |
| 合计（include 范围不同，只作参考） | 52%（42842 行） | 74%（36323 行） |

- 分母变化：清理删掉了 V7/V8 代码（`scripts/eval-official` 从 7448 行降到 2798 行），合计的分母因此不同。
- 计划第一部分第四节写的现状数字（官方 wrapper 14.8%、发布契约 36.5%、hard 任务 46.9%、parity 63.5%）来自不同的分区口径，本表按目录重新计算，两者略有出入。
- 首测（`e64c8f1d`）的结果：`scripts/parity` 是 61.9%，低于现状；两次都存在的文件中，`hard_parity` 74.4→60.8、`noise_gate` 85.5→78.7、`mme_client` 87.7→44.8。用 `patch = subprocess` 补测计入子进程，有 38 份子进程数据合并失败，数字与首测相同，所以判定这是真实的测试缺口。随后补派 T15 写契约测试（12.419），补完后为上表数值。
- 两次都存在的文件中，仍低于旧测试的只剩 `scripts/eval-official/env_client.py`（82.0→76.8）。
- 测不到的仿真路径（真实 SAPIEN 场景构建、渲染、GPU）由 `tests/sim` 的 60 次 reset 覆盖，不计入上表。

记录文件：[`records/coverage-report-final.txt`](records/coverage-report-final.txt)、[`records/coverage-compare-final.txt`](records/coverage-compare-final.txt)、[`records/coverage-run-summary-final.txt`](records/coverage-run-summary-final.txt)。
