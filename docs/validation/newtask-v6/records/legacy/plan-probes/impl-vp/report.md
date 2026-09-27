# impl-vp：V6 计划 2.10～2.12 与 S2 单调性检查器（副本实施报告）

- 副本 `/data/hongzefu/v6-draft/vp`，分支 `v6-draft-vp`，commit `9b51421`（`12.139-draft-vp …`，未 push）；主仓库源码未改动。
- 本机真演示产物目录 `/data/hongzefu/v6-draft/vp/artifacts/impl-vp/`：h5 和视频已删除，保留 summary/日志、配置和探针脚本。逐局汇总见 `demo_summary.jsonl`。

## 一、改动清单

| 文件 | 改动 |
|---|---|
| `src/robomme/robomme_env/utils/xhard_home_site.py` | 新增三个常量：`RETURN_LAST_ONLY`、`NO_RETURN`（= `native_random_goal_site`）、`NEWVALUE_RETURN_POLICIES`。<br>`validate_demo_plan` 的 xhard 分支放行三种策略，原三档不变。<br>新增 `returned_mask`、`goal_drop_obstacles`、`plan_goal_drop_xy`、`build_goal_drop_sites`（不抽随机数，并当场核验 generator 状态）。 |
| `VideoPlaceButton.py` / `VideoPlaceOrder.py` | 新增 `_build_xhard_final_sites`：`return_to_origin` 与 V5 同一条路径；其余策略下，放回的块建 home 落点，不放回的块建 goal 落点。<br>新增规格记录 `actions.goal_drop_pose_by_object_id`。<br>`_xhard_pick_place` 增加 `"goal"` 模式，文本为 "drop the cube onto table"。 |
| `VideoPlaceOrder.py` | 新增已申报键 `decision.xhard.visit_count_range`，默认 [2,4]，与 V5 同抽；下界固定 2，上界不超过目标台数。V5 快照缺这个键时自动补 [2,4]。 |
| `utils/vqa_options.py` | drop 的候选落点追加 goal 落点。 |
| `scripts/parity/v6_tier_monotone.py` | 新增单调性检查器（见第四节）。 |
| `tests/lightweight/test_v4_xhard_videoplace.py`、`test_v6_tier_monotone.py` | 覆盖以下单测：新策略校验、returned_mask、落点避障与确定性、V5 快照补键、vqa 候选、检查器。 |

## 二、审计三点（作为计划待决项 M11 的实测依据）

### ① 各档实际的 pick-place 段数与总步数

原三档本来就有一段「pick → 放到 goal_site（放桌）」。计划 2.10 的「放置次数」没把放桌算进去，而真实的演示段数要把它算上。

| 档（计划 2.10） | 计划的放置次数 | 实际演示 pick-place 段 | 其中放桌 / 回原位 | 实测总步数（均值 [最小,最大]） |
|---|---|---|---|---|
| VPB hard（k1，不放回） | 2 | 3 | 1 / 0 | 原三档，本轮未跑 |
| VPB xhard1（k1，放回） | 3 | 3 | 0 / 1 | 957 [919,994] |
| VPB xhard2（k2，不放回） | 4 | **6** | 2 / 0 | 1562 [1499,1602] |
| VPB xhard3（k2，只放回末块） | 5 | **6** | 1 / 1 | 1551 [1500,1601] |
| VPB xhard（k2，全放回） | 6 | 6 | 0 / 2 | 1562 [1505,1604] |
| VPO xhard1（k1，v[2,4]，放回） | 4 | 4（v=3） | 0 / 1 | 1107 [1061,1137] |
| VPO xhard2（k2，v[2,3]，不放回） | 5 | 7～8 | 2 / 0 | 1750 [1658,1851] |
| VPO xhard3（k2，v[2,4]，不放回） | 6 | 8～9 | 2 / 0 | 1851 [1740,2000] |
| VPO（k2，v[2,4]，只放回末块，补测组合） | — | 6～9 | 1 / 1 | 1748 [1450,1996] |
| VPO xhard（k2，v[2,4]，全放回） | 8 | 8～9 | 0 / 2 | 1848 [1762,1987] |

结论：

- VPB 的 xhard2、xhard3、xhard 三档实际都是 6 段，总步数几乎相同（约 1550～1560）。三档的差别只在于演示结束时方块落在桌面还是原位。
- VPO 的 xhard3（不放回）与 xhard（全放回）段数相同。
- 「放置次数逐档 +1」只有在不计放桌那一段时才成立。如果 M11 要求步数或段数真正递增，需要换一个难度标尺，或者让「不放回」不产生放桌段。后者会导致答案泄漏或撞台，见 ②。

### ② 不放回时的落点定义（已实现）

**为什么不能留在台上**：不放回的块如果留在按钮后放上的那张台上，执行段会直接暴露答案（"after" 那张台上摆着方块）。VPO 是逐块顺序演示，下一块还可能访问同一张台而撞台。所以不放回的块一律挪到 goal_site 附近的桌面。

**落点选取规则**：

- 候选点是 goal_site 中心周围 ±0.12 m 范围内的 1 cm 网格点。
- 按离中心的距离排序，距离相同时按 (x,y) 字典序。
- 贪心取第一个同时满足以下条件的点：与全部方块初始位置 ≥0.07 m、与全部目标台 ≥0.08 m、与按钮 ≥0.10 m、与已选落点 ≥0.07 m。多块按演示顺序依次选。
- 中心空着时，第 1 块正好落在中心，与原三档同处。
- 落点 z 取方块半边长，朝向为单位四元数。
- 找不到可行点时抛 `SceneGenerationError`（可重试）。

**随机流**：不抽任何随机数，建落点前后 generator 状态逐字节相等，否则抛错。

**X0 对拍**：`return_to_origin` 仍走原路径。VPB/VPO 的 xhard 在 seed 910000/910101 上，与 e1755f9 基线副本的 h5 SHA-256 **4/4 逐字节相同**。

**按档读取**：校验读的是 decision 里 xhard 子块的 `demo_return_policy`。管道那一路把 `== "xhard"` 改成族判断后，新档各自读自己那份 decision。

**首版的坑（已修）**：首版落点是「中心沿 y 轴 ±spacing」，不避障。VPO 两组不放回在 seed 910101 各失败 1 局（`DatasetGenerationError`：跑完 task_list 仍未成功）。

- 该局绿块初始位置 (-0.12,-0.035) 离 goal 中心只有 3.9 cm；第一个落点 (-0.10,-0.05) 离绿块仅 2.5 cm。
- 蓝块放上去后压撞绿块，task_index 停在第 7 条（drop the cube onto table），绿块再也抓不起来。
- 根因：goal_site 先于方块生成，方块只避让 goal 圆盘的外缘，所以可能离中心很近。
- 改成避障网格之后重跑，该 seed 两组都成功。首版结果留在 `demo_v1_before_fix/`。

### ③ `return_last_only` 的语义

前 k−1 块按不放回规则落到 goal 落点，最后一块（演示顺序中的末块）放回原位。实现为 `returned_mask("return_last_only", k) = [False]*(k-1) + [True]`。

## 三、真演示结果

本机 sm_89，`scripts.parity.v4_demo_probe --sampling-config`，seed 取 910000+101·i。

| 格 | 成功 | 总步数 均值 [最小,最大] | 演示步均值 | 执行步最大 | 单局墙钟均值 (s) |
|---|---|---|---|---|---|
| VPB k1 放回（xhard1） | 3/3 | 957 [919,994] | 756 | 205 | 219 |
| VPB k2 不放回（xhard2） | 3/3 | 1562 [1499,1602] | 1357 | 211 | 70 |
| VPB k2 只放回末块（xhard3） | **4/4** | 1551 [1500,1601] | 1348 | 210 | 69 |
| VPB xhard（对照） | 4/4 | 1562 [1505,1604] | 1359 | 210 | 236 |
| VPO k1 v[2,4] 放回（xhard1） | 3/3 | 1107 [1061,1137] | 911 | 206 | 221 |
| VPO k2 v[2,3] 不放回（xhard2） | 3/3 | 1750 [1658,1851] | 1541 | 215 | 77 |
| VPO k2 v[2,4] 不放回（xhard3） | 3/3 | 1851 [1740,2000] | 1642 | 215 | 82 |
| VPO k2 v[2,4] 只放回末块 | **4/6** | 1748 [1450,1996] | 1540 | 217 | 76 |
| VPO xhard（对照） | 3/4 | 1848 [1762,1987] | 1643 | 218 | 293 |
| PatternLock xhard1 [9,12] | 3/3 | 619 [542,668] | 309 | 334 | 197 |
| PatternLock xhard2 [13,17] | 3/3 | 893 [840,924] | 447 | 462 | 217 |
| PatternLock xhard3 [18,22] | 3/3 | 1249 [1212,1280] | 625 | 640 | 256 |
| PatternLock xhard（25，对照） | 3/3 | 1641 [1614,1676] | 820 | 838 | 288 |
| RouteStick xhard1 L[8,10] | 3/3 | 933 [900,1000] | 467 | 500 | 227 |
| RouteStick xhard2 L[11,12] | 3/3 | 1167 [1100,1200] | 583 | 600 | 262 |
| RouteStick xhard3 L[13,14] | 3/3 | 1367 [1300,1400] | 683 | 700 | 269 |
| RouteStick xhard（[15,21]，对照） | 3/3 | 1833 [1600,2000] | 917 | 1000 | 314 |

**失败局**：VPO 只放回末块在 910404/910606 失败、VPO xhard 对照在 910303 失败，三局都是 reset 阶段的 `SceneGenerationError: Target 4 sampling failed`。这是 VPO 的既有布局拒绝，发生在我的代码之前，xhard 默认配置下同样失败。补跑 910505 后凑满 4 局成功。

**墙钟**：各格墙钟受并行负载影响很大（第一批约 18 路并行、机器负载约 100；修复后重跑时负载约 15），只能作参考。

**`__ALT__` 文本样例**：任务文本与放回策略无关，放回策略不改变问题本身。

- VPB k2 只放回末块（seed 910000）：`watch the video carefully, then place the green cube on the target right before the button was pressed __ALT__ … immediately before the button was pressed __ALT__ … previously placed before the button was pressed __ALT__ … where it was last placed before the button was pressed`
- VPO k2 只放回末块 / 不放回（seed 910000）：`watch the video carefully, then place the green cube on the third target it was previously placed on __ALT__ watch the video carefully and place the green cube on the third target where it was placed`
- 演示中放桌那一段的 subgoal 为 "drop the cube onto table"，回原位那一段为 "put the cube back to its original position"。

**步数约束**：

- PatternLock、RouteStick 的新档总步数和执行步都逐档递增，而且都低于 xhard，满足「新档步数 ≤ xhard」。执行段：PatternLock ≤640、RouteStick ≤700，都低于 1301。
- PatternLock xhard3 约 1249 步，与计划估计的「约 735 帧」口径不同：计划估的是演示帧，实测演示约 625 步。
- VP 各新档总步数不超过 xhard 均值加小幅波动（VPO xhard3 单局最大 2000，对照 xhard 最大 1987），执行段 ≤218。但 VP 的 xhard 本身总步数就有 1500～2000，**超过评估侧的 1301**。如果 1301 约束的是总步数，VP 的 xhard 自身就不满足；如果只约束执行段，则满足。这是计划口径需要确认的问题，本轮只报告。

**规格回放**（`replay_check.py`，7 个组合 × 3 个 seed）：回注模式下 mismatch 全为 0，重建出的任务表逐项相等。

**PatternLock 路径预算**（离线，与环境搜索循环同构，每档 300 局，预算 20000）：

- 耗尽次数全部为 0。
- 平均尝试次数：xhard1 4.6（最多 45）、xhard2 3.5（最多 20）、xhard3 5.3（最多 30）。
- 对照 xhard（25 节点）平均 2470、最多 15181。
- 结论：新档的预算非常充裕。

**PatternLock / RouteStick 未改源码**：节点区间 `path_length_range.xhard` 和段数 `xhard.segment_count_range` 都已是 xhard 的已申报键，直接用 sampling_config 覆盖即可。

## 四、单调性检查器

模块 `scripts/parity/v6_tier_monotone.py`，入口为 `check_all` / `format_report` / `tiers_from_decisions`。

- **计入判定的链**：hard→xhard1→xhard2→xhard3→xhard。判定口径 5：各维度均值单调不减，且每一步至少有一个维度严格上升。
- **只作参照的链**：easy→medium→hard 输出为 NATIVE_NOTE，不计入判定。
- **取值口径**：闭区间取中点；样本输入写成 `{"samples": [...]}`；值为 None 的维度跳过（例如 VideoRepick hard 的块数是聚簇口径）。

用计划表数值（`PLAN_TIERS`）运行的输出：

```
VIOLATION env=PickHighlight step=xhard2->xhard3 dim=distractors 3.5→3
TIER_MONOTONE=FAIL envs=13 violations=1
```

- 违例原因：PH 总块数从 8 → [8,9]，只多 0.5；pick 从 [4,5] → [5,6]，多 1。所以干扰均值下降。建议把 xhard3 的总块数改为 [9,9] 或 [9,10]，需要计划方定。
- 其余 12 个环境的闸门链都单调。
- 用 tiers 探针配置（`plan-probes/tiers/configs`，VP 按本实现的策略重算）运行，结论相同。
- 原三档参照链有 10 条非单调记录（如 SwingXtimes easy [1,3] → medium [1,2]），原版冻结，不计入。

## 五、测试

- `tests/lightweight` 全量：两边都跑了 8 分 58 秒，超过 5 分钟要求，因为全量集合本身就需要约 9 分钟，负载降下后两边同时跑。

  | | failed | errors | passed |
  |---|---|---|---|
  | e1755f9 基线副本（git archive） | 46 | 12 | 1426 |
  | 本副本 | 47 | 12 | 1434 |

  - 基线的 46/12 与计划 S0 的基线数一致。
  - 失败集合只多一条：`test_sampling_config_split.py::test_snapshot_matches_source`。原因是新增已申报键 `visit_count_range` 后，冻结的 v5 快照与源码提取结果不一致，属于预期内。V6 快照重新 extract 后这条会消失；如果不接受新键，就需要另想办法表达 VPO 的 v 上界。
  - 新增和改动的单测都通过（`test_v4_xhard_videoplace` 26 条、`test_v6_tier_monotone` 5 条）。

## 六、与计划不一致之处和待决

1. **放置次数标尺**：计划没计放桌段。VPB 的 xhard2、xhard3、xhard 实际段数都是 6，步数几乎相同，放回策略只改变终点。建议在 M11 里决定是否换标尺，或把段数变化作为已知现象接受。
2. **PickHighlight xhard3**：干扰均值下降，TIER_MONOTONE 判 FAIL。
3. **VP 步数与 1301**：VP 的 xhard 自身总步数 1500～2000，需要确认 1301 约束的是总步数还是执行段。
4. **VPO v 上界**：需要新的 decision 键 `visit_count_range`，会让 v5 快照一致性测试失败，需由管道那一路并入 v6 快照。
5. **计划 2.10 的 reset 成功率**：计划写 VPO reset 成功率 50%。本机 VPO seed 910303/910404/910606 都是布局拒绝，新策略没有增加拒绝。
6. **`validate_demo_plan` 的档位判断**：仍是 `difficulty != "xhard"`，待管道那一路改成族判断 `is_newvalue_difficulty()`。
