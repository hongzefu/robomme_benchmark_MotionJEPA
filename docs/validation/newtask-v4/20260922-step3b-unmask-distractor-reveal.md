# V4 步 3b：四个 Unmask 环境 xhard 干扰容器「参与揭示 + 误抓即失败」

> 红线 N1 的逐步报告。起点 `12.78`（`42179c2`，本组上一个提交），隔离 worktree，GPU 1，本机 sm_89（结果只作调试，口径 10）。
> 依据：用户 2026-09-22 新决策（选项原话「参与揭示+误抓即失败」），主 agent 转述的四条要求。
> 录像器、链路甲、`scripts/configs/**`、计划文件未改；干扰容器的生成（位置、个数、颜色、随机流）一字未动。

## 一、行为定义（xhard 专属，原三档不进）

### 1. 揭示时序

四个环境的区域内容器揭示用的都是 `utils/statechange.py::lift_and_drop_objects_back_to_original`：
窗口 `[start, end)` 的前半段每一步把容器瞬移到远处 `(10, 10, 10)`（露出内部方块），在 `drop_step = start + (end-start)//2`
那一步瞬移回原位姿（速度清零），之后不再干预。干扰容器现在逐个走**同一个函数、同一窗口**：

| 环境 | 窗口来源 | 窗口 | 移到远处的步 | 放回的步 | 与区域容器同步？ |
|---|---|---|---|---|---|
| VideoUnmask / ButtonUnmask | `positions.reveal_window` | [0, 64) | 0~31 | 32 | 同步（同一窗口、同一 drop_step） |
| VideoUnmaskSwap / ButtonUnmaskSwap | `swap_window_start`（预交换锁定段） | [0, 64) | 0~31 | 32 | 同步 |

「抬多高」：沿用原机制，不是物理抬升，而是瞬移到 `(10,10,10)`（实测 z≈9.87~10.09，远处多个容器重叠互推造成的抖动，
与原区域容器同样）；放回后 xy 误差 ≤4e-5 m、z=0.052~0.053（与原位相同）。空的干扰容器同样移走（露出无物）。
干扰容器仍**不进 `spawned_bins`**、不参与 swap / 最近邻 / 揭示外的任何逻辑，命名仍是 `distractor_bin_<i>`。

### 2. 误抓即失败

xhard 下任务表里每个**已有 `failure_func`** 的条目（抓取与放下两类；static、按钮等原本 `failure_func=None` 的条目不动）
把判据改为 `[原结果, 任一干扰容器被抬起]`，由 `subgoal_evaluate_func._coerce_failure_result` 取 any。
「被抬起」与区域内容器同一判据：`is_bin_pickup`，即容器中心 z > 0.15。

- ButtonUnmask 首抓的「单元素列表」返回形态原样保留在列表第一项里；
- 只改 `failure_func` 一个键，`inject_fail_grasp` 替换的是 `solve`，两者互不干扰（V4 本就不开 recover）；
- 揭示期（0~31 步）干扰容器在远处 z≈10 会满足「被抬起」，但此时当前任务是 static（Video 系）或按钮（Button 系，failure 为 None），
  抓取/放下任务的 failure_func 不会被求值；区域内非目标容器在同一时段同样在远处，原判据本来就有同样的时序前提，干扰容器没有引入新风险。

## 二、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `utils/unmask_distractors.py::reveal_distractor_bins`（新增） | 对 `env.distractor_bins` 逐个调 `lift_and_drop_objects_back_to_original`（同窗口参数） | 四环境共用；与区域容器同一机制保证同步 | 单测 `test_揭示时序与区域容器同一机制`；真环境核查（四节） |
| `utils/unmask_distractors.py::any_distractor_bin_lifted`（新增） | `is_any_bin_pickup(env, distractor_bins)` | 与区域容器同一判据（z>0.15） | 单测 |
| `utils/unmask_distractors.py::add_distractor_misgrasp_failure`（新增） | 包装已有 failure_func 为 `[原结果, 干扰判据]` | 见一.2 | 单测 `test_误抓判失败只包装已有failure_func且保留原形态`、`test_原判据为真时仍判失败` |
| `VideoUnmask.py` / `ButtonUnmask.py`：import 块；`_load_scene` 里 `if xhard:` 生成干扰容器之后；`step` 的区域容器揭示循环之后 | 导入两个函数；生成干扰容器后 `add_distractor_misgrasp_failure(self, self.task_list)`；`step` 里 `if self.difficulty == "xhard": reveal_distractor_bins(...reveal_window...)` | 只挂 xhard；原揭示循环一字未动 | AST 单测（参数化四环境）；reset 探针 diff=0 |
| `VideoUnmaskSwap.py`：import 块；`_load_scene` 里 `if self._is_xhard:` 的 `_spawn_xhard_distractors()` 之后；`step` 的预交换锁定循环之后 | 同上，窗口用 `[0, self.swap_window_start)` | 同上 | 同上 |
| `ButtonUnmaskSwap.py`：import 块；`_initialize_episode` 里 recovery 分支之后（任务表在这里组装，晚于 `_load_scene` 的干扰容器生成）；`step` 的预交换锁定循环之后 | 同上 | 同上 | 同上 |
| `tests/lightweight/test_v4_xhard_unmask_distractor_reveal.py`（新增） | 12 项纯 CPU 测试（假 actor / 假 env + AST 锁挂接点只在 xhard 条件下） | 必做验证 | 12 passed |

两份干扰容器生成实现（`unmask_distractors.py` 与 `unmask_swap_xhard.py`）没有合并：生成逻辑的随机流、避让判据不同，
合并会碰到原有 xhard 的取值序列，收益小、风险大；本次只把新增的共同逻辑（揭示、判失败）放在一处。

## 三、实测数字

| 项 | 数 |
|---|---|
| 原三档 reset 探针（四环境） | `RESET_REGRESSION=FAIL compared=36 diff=0 missing=108`（missing 为其他 12 环境，预期；四环境 diff=0） |
| 真环境揭示核查（seed 910000，xhard，reset 后 70 步保持姿态） | 四环境：干扰容器与区域容器远处步均为 0~31、第 32 步同时放回；干扰容器放回 xy 误差 1e-5~4e-5 m |
| 真环境误抓核查（同上，把第 0 个干扰容器抬到 z=0.3） | 四环境各 5 条被包装的任务（抓取 3 + 放下 2）：抬起前 failure 全 False，抬起后全 True；static / 按钮任务未包装 |
| xhard 演示（`v4_demo_probe --n 2 --gpu 1`，seed 910000/910101，_worker 同路径） | **8/8 成功**：VideoUnmask 2/2（21 s、21 s）、ButtonUnmask 2/2（23 s、24 s）、VideoUnmaskSwap 2/2（42 s、46 s）、ButtonUnmaskSwap 2/2（37 s、39 s） |
| 新单测 | 12 passed |
| 涉及的既有测试文件（加 v4_xhard_videounmask_buttonunmask） | 35 failed / 222 passed / 10 skipped，失败集合与 6cc656f 基线逐条相同 |

核查脚本：scratchpad `g10/reveal_check.py`（不入库）。

## 四、计划外

1. 远处 `(10,10,10)` 本来就重叠着全部区域容器，现在再多 3 个干扰容器；每步都会重新瞬移、放回步速度清零，实测放回精度不受影响。
2. 放下任务也挂了干扰判据：用户原话是「误抓即失败」，放下阶段抬起干扰容器同样是误抓；主 agent 转述写的是「每个 pickup 任务」，
   如只想限于抓取任务，改 `add_distractor_misgrasp_failure` 的筛选条件即可（见待用户决策）。

## 五、待用户决策

1. 「误抓即失败」是否也覆盖放下任务（现实现：覆盖；抓取、放下两类都挂）。
