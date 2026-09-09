# 实测报告：第五步清理后的抽样复验与定向检查（运行编号 20260909T1441Z-postclean）

## 1. 目的、对拍编号、参考与候选

方案第五步要求：按第七节清单清理旧脚本目录之后，做**抽样复验**并跑完定向检查清单，
确认清理没有改变运行行为、也没有留下旧依赖。

- **参考**：清理前的运行 [20260908T2255Z-parity15-3804e87](../20260908T2255Z-parity15-3804e87/README.md)
  的 `B` / `C` 产物（源码提交 `1f51108`，`10.2`）。
- **候选**：清理后同一批用例重跑的 `B` / `C` 产物。
- 覆盖对拍编号：③（HDF5 产物内容）为主；重试分支的定向检查对应方案第六节第 6 条。
  本轮**不重复** ①②④⑤ 的全量登记，那些结论属于清理前那次运行。

## 2. 源码、依赖与设备

| 项目 | 值 |
| --- | --- |
| 清理前候选提交 | `1f51108`（`10.2`） |
| 清理内容 | 见 [NEWTASK_V2_PLAN.md 第十一节 10.3](../../../NEWTASK_V2_PLAN.md)；随 `10.3` 提交 |
| 固定原版 | `94449db0a068a6b454b55a13ebd48f0394d89cc8`（基线 worktree，未受清理影响） |
| 依赖锁 | `uv.lock` 未变，SHA-256 前 16 位 `983de83f7b22c98b` |
| 设备 | NVIDIA RTX 6000 Ada Generation |

## 3. 命令、耗时与退出码

全部在 tmux 会话 `postclean` 内串行执行，日志
`artifacts/logs/postclean-20260909T1441Z-postclean.log`；比较在会话 `pcmp` 内执行，
日志 `artifacts/logs/postclean-compare.log`。两者退出码均为 0。

```bash
# 定向检查
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8
uv run --no-sync python -c "import sys; sys.path.insert(0,'scripts'); import generate_dataset_newseed, seed_layout"

# 轻量测试全量
uv run --no-sync python -m pytest tests/lightweight -q

# 抽样复验：每任务 easy 一格的 B/C 重跑
uv run --no-sync python -m tests._shared.parity_runner --run-id 20260909T1441Z-postclean \
  --cell BinFill-easy-dynamicTrue --cell RouteStick-easy \
  --cell VideoUnmaskSwap-easy --cell VideoRepick-easy --path B --path C

# attempt 重试分支（原版已知首次失败的用例，--max-attempts 2），A/B/C 各一次
<各自入口> --env BinFill --episodes 1 --episode-start 0 --difficulty 010 \
  --workers 1 --gpus 0 --layout train --max-attempts 2 --max-tasks-per-child 8

# 其余任务的生成能力：--env all 加 --sampling-config
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/parity/20260909T1441Z-postclean-12tasks \
  --env all --episodes 1 --episode-start 0 --workers 8 --gpus 0,1 \
  --layout train --difficulty 100 --max-attempts 3 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

## 4. 结果

### 4.1 定向检查清单

| 检查项 | 结果 |
| --- | --- |
| 配置提取与 `--check-config`（工作树） | 通过 |
| `--source-ref 94449db` 的原版操作元对照 | 61 项一致，通过 |
| 同级 `seed_layout` 独立导入 | 通过（16 任务规范序完整） |
| 提取模式不加载仿真 | 通过（`tests/lightweight/test_native_sampling_config.py` 的子进程断言） |
| 清理后无旧依赖 | 通过：`scripts/` 下产品 Python 文件恰为 5 个，产品路径不 import `tests/` |
| `--env all` 加 `--sampling-config` | **16/16 成功**，`exhausted_count=0`，attempt 全为 0，72.7 s |
| attempt 重试分支（第六节第 6 条） | 通过，见 4.3 |

`--env all` 的运行摘要里 `sampling_config_tasks` 为
`["BinFill","RouteStick","VideoRepick","VideoUnmaskSwap"]`，其余 12 个任务没有拿到配置、
照原默认值生成且全部成功 —— 即「配置只覆盖四任务、其余 12 个任务生成能力必须保留」成立。

### 4.2 抽样复验：清理前后逐位一致

每任务 easy 一格，`B` 与 `C` 各重跑一次，与清理前同格同路的产物做 HDF5 全字段逐元素比较
（浮点按位模式、不设容差）：

| 格 | B 路差异 | C 路差异 |
| --- | ---: | ---: |
| BinFill-easy-dynamicTrue | 0 | 0 |
| RouteStick-easy | 0 | 0 |
| VideoUnmaskSwap-easy | 0 | 0 |
| VideoRepick-easy | 0 | 0 |

**八项全部 0 差异。** 其余 11 格沿用清理前的证据，其源码版本为 `1f51108`（`10.2`），
在 [上一份报告](../20260908T2255Z-parity15-3804e87/README.md) 中登记。

### 4.3 attempt 重试分支的三路对照

用原版已知在 attempt 0 就失败的用例（`BinFill` / `medium` / episode 0 / seed 4000，
即上一轮记为受阻的那一格），把 `--max-attempts` 放到 2，三路各跑一次：

| 路 | attempt 0 | attempt 1 |
| --- | --- | --- |
| A（固定原版） | 失败，`failure_class=task`，`DatasetGenerationError`，seed 4000 | 成功，seed 4001 |
| B（新版不传配置） | 同上 | 同上 |
| C（新版显式原值配置） | 同上 | 同上 |

**失败分类、错误类型与第二次 seed 三路完全相同**；三路 attempt 1 的产物做 HDF5 全字段
逐元素比较，`A-B`、`A-C`、`B-C` 差异均为 **0**。即原 seed 演进公式
`base_seed + attempt` 与失败分类逻辑在接入配置后未变。

### 4.4 轻量测试

`tests/lightweight` 全量：**4 failed / 176 passed，172.4 s**。
四项失败为 `test_TaskGoal` 2 项与 `test_step_error_handling` 2 项，
已在固定基线 worktree 上复测确认**在 `94449db` 上同样失败**（4 failed / 27 passed），
属既有失败，与本轮改动和清理无关。

通过数由清理前的 258 降到 176，是因为三个只服务已删功能的测试文件随旧目录退出
（`test_append_train_metadata.py`、`test_no_patch_report_debug_environment.py`、
`test_swap_clip_plan.py`，三者都在模块导入期就依赖已删目录）。

## 5. 首个分歧、失败、受阻与未覆盖项

- **没有任何分歧**：抽样复验八项与重试分支三对比较全部 0 差异。
- 未覆盖项（沿用上一份报告，并加本轮的）：
  - 其余 11 格未在清理后重跑，沿用清理前证据（这是方案「抽样复验」的既定口径）。
  - ① 的 BinFill 六格目视仍未完成。
  - 触发 RRT\* 回退的局仍未出现，容差退出路径仍未验证。
  - 合并（`--merge-only`）产物的结构与内容比较（③.4）本轮仍未做。

## 6. 证据索引

本轮的机器结果在日志与运行目录里，未另建证据包（抽样复验的结论是「与既有证据逐位一致」，
不产生新的基准）：

| 内容 | 位置 |
| --- | --- |
| 阶段日志与退出码 | `artifacts/logs/postclean-20260909T1441Z-postclean.log` |
| 逐位比较输出 | `artifacts/logs/postclean-compare.log` |
| 抽样复验产物 | `artifacts/parity/20260909T1441Z-postclean/` |
| 重试分支产物 | `artifacts/parity/20260909T1441Z-postclean-retry/`（B/C）与基线 worktree 下的 A |
| 16 任务 smoke 产物 | `artifacts/parity/20260909T1441Z-postclean-12tasks/` |

以上都在 `artifacts/` 内，不入 Git。
