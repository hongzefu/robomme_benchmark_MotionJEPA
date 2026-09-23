# V4 步 3b：两个 UnmaskSwap 环境 xhard 交换期等待遇碰撞拒绝的死循环核查与修复

> 红线 N1 的逐步报告。起点 `12.77`（`6cc656f`），隔离 worktree，GPU 1，本机 sm_89（结果只作调试，口径 10）。
> 录像器、链路甲、`scripts/configs/**`、计划文件、共享函数 `utils/subgoal_planner_func.py` 均未改。
> 背景：VideoRepick 子任务（报告 `20260922-step3b-videorepick.md` 第四节 1）发现共享 `solve_hold_obj` 的裸 `except:`
> 会吞掉 D5/H1 几何检查在 `env.step` 里抛出的 `BinCollisionError`，等待循环不前进而死循环。

## 一、判定

| 环境 | xhard 交换期等待 | 检查抛错时 | 结论 |
|---|---|---|---|
| VideoUnmaskSwap | 首个 static 任务 `solve_hold_obj(... static_steps=self.swap_schedule[-1][3])`，全部 8~12 段交换都在此循环里发生 | **被吞掉、死循环**（实证见二） | **有问题，已修** |
| ButtonUnmaskSwap | 按钮任务里的 `_solve_press_then_wait_swaps` → `solve_hold_obj_absTimestep`；前几段交换发生在 `solve_button` 的规划器运动中 | 原样上抛，干净失败（实证见二） | **无问题，不改** |

## 二、实证（强制触发碰撞的反例）

做法：测试进程内 monkeypatch 环境模块里的 `check_swap_sweep`（先调真函数，再在指定 `sweep_index` 把结果替换成
`CollisionRejection(reason="contact", gap=-0.01)`），其余全部走正式入口 `generate_dataset_newseed._worker`
（同 gym.make 参数、录像器、规划器、失败分类）。生产代码不落盘改动。外部 `timeout 150`。
脚本：scratchpad `g10/force_reject.py` + `g10/run_force.sh`（不入库）。

| 场景 | seed | 强制判撞段 | 结果 | 墙钟 | 检查调用次数 |
|---|---|---|---|---|---|
| VideoUnmaskSwap **修前** | 910000 | sweep#0 | 无结果，外部超时 rc=124 | 151 s | 挂死（该轮只打印到前 4 次） |
| VideoUnmaskSwap **修前** | 910101 | sweep#0 | 无结果，外部超时 rc=124 | 150 s | **≥420 次**同一段反复判撞 |
| VideoUnmaskSwap **修后** | 910000 | sweep#0 | `ok=false failure_class=task error_type=BinCollisionError` | 11.1 s（进程 16 s） | 1 |
| VideoUnmaskSwap **修后** | 910101 | sweep#7（末段附近） | 同上，`sweep#7 bin_2 与 bin_1 g=-0.01` | 21.0 s（进程 26 s） | 8 |
| ButtonUnmaskSwap（未改） | 910000 | sweep#0（按钮运动期） | `ok=false task BinCollisionError` | 9.2 s（进程 14 s） | 1 |
| ButtonUnmaskSwap（未改） | 910101 | sweep#5（按调度第 5 段起点 64+33×5=229 步，晚于按完两个按钮的约 200 步，即落在 `solve_hold_obj_absTimestep` 等待里） | `ok=false task BinCollisionError` | 18.1 s（进程 23 s） | 6 |

修前死循环机理：`step` 在交换开始那一步解析最近邻后立即做扫掠检查并抛错，`elapsed_steps` 不前进；裸 `except:` 吞掉后
`while elapsed_steps < target` 条件不变，下一轮再 step、再解析、再判撞、再往 `_runtime_checks` 追加一条拒绝，无限重复
（150 s 内累计 ≥420 次）。正式生成里这意味着被拒局既不产出也不失败，只能靠外部超时或内存崩溃结束。

## 三、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `utils/unmask_swap_xhard.py::solve_hold_obj_xhard`（新增） | 与 `solve_hold_obj(close=False)` 同语义的原地等待，只吞 `AttributeError`，其余异常（含 `BinCollisionError`）原样上抛 | 共享函数按 N12 不就地修；放在两个 UnmaskSwap 共用件里，本模块本来就只在 xhard 分支被引用 | 单测 `test_专用等待遇碰撞拒绝立即上抛`、`test_专用等待正常等满且只吞AttributeError` |
| `VideoUnmaskSwap.py` 的 import 块 | 从 `utils.unmask_swap_xhard` 追加导入 `solve_hold_obj_xhard` | — | — |
| `VideoUnmaskSwap.py::_load_scene`（任务表组装末尾、`self.task_list = tasks` 之前） | 新增 `if self._is_xhard: tasks[0]["solve"] = lambda env, planner: solve_hold_obj_xhard(env, planner, static_steps=self.swap_schedule[-1][3])`；原 static 任务字面量一字未动 | 只在 xhard 分支替换；与 ButtonUnmaskSwap 已有的 `tasks[1]["solve"] = ...` 同一写法。static 任务不是抓取任务，`inject_fail_grasp` 不会替换它（且 V4 不开 recover） | 单测 `test_VideoUnmaskSwap只有xhard换用专用等待`（AST：原 lambda 仍在、替换只在 `if self._is_xhard` 体内、全函数只此一处）；二节修后反例；reset 探针 diff=0 |
| `tests/lightweight/test_v4_xhard_swap_hold.py`（新增） | 6 项纯 CPU 测试（假 env / 假 planner，不起 sapien） | 必做验证 | 6 passed |

VideoRepick 已有自己的 `_solve_hold_obj_xhard`（12.77），语义与新共用函数相同；为不扩大改动面，本提交**没有**把它改成引用共用件（可在后续清理时合并）。

## 四、全环境核查：xhard 打开检查时还有哪些路径调用两个等待函数

`grep` 全部环境：运行期（`env.step` 内）会抛 `BinCollisionError` 的只有 VideoRepick、VideoUnmaskSwap、ButtonUnmaskSwap
三个（`utils/bin_collision.py` 的调用方仅此三处）。

| 调用方 | 函数 | step 里有运行期几何检查？ | 结论 |
|---|---|---|---|
| VideoRepick（xhard 已换 `_solve_hold_obj_xhard`，12.77） | `solve_hold_obj` 仅原三档 | 有（甲通道或 xhard） | 已修；原三档在甲通道下同样有隐患（甲已退役，不动） |
| VideoUnmaskSwap | `solve_hold_obj` → xhard 换 `solve_hold_obj_xhard` | 有（xhard 乙通道） | **本提交修复** |
| ButtonUnmaskSwap | `solve_hold_obj_absTimestep`（无 try） | 有（xhard） | 无问题 |
| VideoPlaceButton、VideoPlaceOrder、MoveCube、InsertPeg、VideoUnmask | `solve_hold_obj` | 无（step 里不抛碰撞/绑定错误） | 当前不受影响；但裸 except 会吞掉 step 里**任何**异常，将来若给它们的 step 加运行时判据须同样绕开 |

## 五、实测数字

| 项 | 数 |
|---|---|
| 原三档 reset 探针（VideoUnmaskSwap + ButtonUnmaskSwap） | `RESET_REGRESSION=FAIL compared=18 diff=0 missing=126`（missing 全为其他 14 环境，预期；两环境 diff=0） |
| 强制碰撞反例 修前 | VideoUnmaskSwap 2/2 挂死至 150 s 超时（≥420 次重复判撞） |
| 强制碰撞反例 修后 | VideoUnmaskSwap 2/2 在 11~21 s 以 `task:BinCollisionError` 结束；ButtonUnmaskSwap 2/2 在 9~18 s 结束 |
| 正常 xhard 演示（`v4_demo_probe --n 2 --gpu 1`） | VideoUnmaskSwap 2/2（43 s、45 s）；ButtonUnmaskSwap 2/2（38 s、38 s） |
| 新单测 | 6 passed |
| 涉及的既有测试文件（v4_xhard_unmaskswap / swap_schedule_generic / episode_action_sampling / window_timeline / operand_scope / episode_specs / TaskGoal / native_sampling_config） | 改前 35 failed / 191 passed / 10 skipped；改后（加新文件）35 failed / 197 passed / 10 skipped，**失败集合逐条相同** |

## 六、计划外

1. **规划器回退层会短暂吞掉碰撞拒绝**：`generate_dataset_newseed.py::_planner_classes` 的 `ScrewThenRRT.move_to_pose_with_screw`
   在 screw 三次都返回 -1 之后走 RRTStar，那一段用 `except Exception` 捕获并重试。若恰在 RRTStar 运动中遇到交换起点被判撞，
   `BinCollisionError` 会被 RRTStar 三次尝试各吞一次，之后抛 `PlannerExhausted`（仍在 retryable 列表里，归为任务性失败，但 `error_type`
   不再是碰撞，碰撞证据只留在 `_runtime_checks` 里）。不会死循环，只影响失败分类的准确性；属于主入口，本任务未改，建议主 agent 决定是否收窄。
2. `utils/subgoal_planner_func.py` 另有 `solve_swingonto`、`solve_strong_reset` 两处裸 `except:` 包单次夹爪动作（不在循环里，
   吞一次就继续）。当前调用它们的环境 step 里没有运行期几何检查，不受影响。
3. 两个 xhard 反例都证明「检查抛错 → `_worker` 归 `task`」链路完整：`BinCollisionError` 在 retryable 列表里，`failure_class=task`。

## 七、待用户决策

无（本项是缺陷修复，行为按既定口径：被拒即失败、不换 seed）。
