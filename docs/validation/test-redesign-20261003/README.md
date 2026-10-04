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
