# V4 步 3b（g1 组）：SwingXtimes 与 PickXtimes 的 xhard

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`）。录像器 `RecordWrapper.py` 未改。
> 对应计划 `NEWTASK_RELEASE_V4_PLAN.md` 2.4（PickXtimes）、2.5（SwingXtimes）、2.21 PickXtimes 简图。
> 本机（sm_89）结果只用于调试，不进判据（口径 10）。

## 一、改动清单

### PickXtimes（`src/robomme/robomme_env/PickXtimes.py`）

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `PickXtimes.config_xhard`（新增，进 `configs`） | `{color: 3, number_min: 6, number_max: 15}` | 1.2 原文「color 3, num [6, 15]」，派生自 hard（口径 7） | `test_v4_xhard_pickxtimes.py::test_xhard_config_values`；reset 冒烟 20 条 num 覆盖 6~15 |
| 模块级 `XHARD_DECISION` ＋ `_native_decision` 的 `"xhard"` 子键 | 原 `distractor: None`、原 `target_cube_position_policy` / `goal_position_policy` **原值不动**；另加 `xhard: {target_cube_position_policy{区域, corner_bias=1.0}, goal_position_policy{独立区域}, distractor{colors, 区域}}` | 公共说明：xhard 专属 decision 放在名为 `xhard` 的子键下，守卫自动放行、原三档可见部分不变；C1 圆盘区域拆成独立一套（值沿用原区域，可在中间） | `test_decision_visible_part_unchanged`（去掉 xhard 后与 `00e2ef4` 原值逐字相同）、`test_decision_xhard_entries`、守卫放行／拒绝参数化用例 |
| `PickXtimes.__init__` 的 `objects.num_repeats` 取值点 | 加 `decision_key=f"number_range.{难度}"` | 新值 mismatch 归因（步 2 机制）；原值模式下 `_mismatch` 不带该字段，形态不变 | reset 探针原三档零差异 |
| `PickXtimes._load_scene` | 中段按难度分叉：xhard → `_spawn_scene_objects_xhard`，其余 → `_spawn_scene_objects_native`；函数末尾（恢复动作抽样之后）xhard 追加 `_spawn_distractors_xhard` | H2/N12：修复与换序只挂在 xhard；N5：新增随机调用追加在全部既有取值点之后 | reset 探针 `compared=18 diff=0` |
| `PickXtimes._spawn_scene_objects_native`（新方法） | 原 `_load_scene` 中段**逐字搬出**（含原来的 `color_groups` 字面量、`for idx` 变量遮蔽、D2 未绑定分支、`randint(0, len(all_cubes))`、三色 if 回填） | 原三档行为逐字不变，原缺陷按 H2 保留 | 同上 |
| `PickXtimes._spawn_scene_objects_xhard`（新方法） | ①颜色取自 `NATIVE_SAMPLING.parameters.color_pool`（xhard 路径的单一真值）；②**G1 先放圆盘再放方块**；③圆盘失败抛 `SceneGenerationError`（**D2 修复，只在 xhard**）；④三个有色方块（目标候选）加 `corner_bias`；⑤方块失败抛错、记 `objects.cube_count{requested, actual}` 不等即抛（2.2④）；⑥目标从 `self.target_candidates` 抽（与 `all_cubes` 解耦）；⑦`target_color_name` 按对象查表回填；⑧消除 `for idx` 遮蔽 | 2.4 实施要点全部条目 | reset 冒烟 20/20；demo 探针 |
| 模块级 `_disk_avoid_obb` | 把圆盘换成预制 OBB `(中心, eye(2), [c, c])`，`c = 圆盘半径 + 圆盘间距 − 方块间距`（PickXtimes = 0.04+0.04−0.02 = 0.06） | **计划外发现**：圆盘是纯视觉 actor，`get_actor_obb` 取不到网格，直接放进 `avoid` 会被 `spawn_random_cube` 静默忽略；G1 换序后方块必须显式避让圆盘 | `test_disk_avoid_obb_shape`；reset 冒烟圆盘中心到任一方块中心最小 0.112 m（≥ 轴向下界 0.10） |
| `PickXtimes._spawn_distractors_xhard`（新方法） | 3 个干扰方块（黄／青／品红各一，`DISTRACTOR_COLORS`），在方块区域均匀放置；进 `all_cubes` 与 `non_target_cubes`（抓错即 failure_func 判失败；按按钮前抓任何方块也判失败），不进 `target_candidates`；记 `objects.distractors`、`layout.distractors.<色>_0`、`objects.distractor_count{requested, actual}`，放不下抛 `SceneGenerationError` | A5/B2；2.4 的三处污染 | reset 冒烟逐条断言 3 个干扰物、`non_target_cubes` 5 个、目标永不为干扰物 |
| `PickXtimes._color_name_of`（新方法） | 按对象查颜色名，查不到直接抛错 | 原三色 if 链对新颜色不命中时会残留上一次的值 | reset 冒烟 `target_color_name ∈ {red, blue, green}` |

### SwingXtimes（`src/robomme/robomme_env/SwingXtimes.py`）

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `SwingXtimes.config_xhard`（新增，进 `configs`） | `{color: 3, number_min: 4, number_max: 10}` | 1.2 原文「number [4, 10]」 | `test_v4_xhard_swingxtimes.py`；reset 冒烟 20 条 num 覆盖 4~10 |
| 模块级 `XHARD_DECISION` ＋ `_native_decision` 的 `"xhard"` 子键 | `xhard: {distractor: {colors, region_center [-0.1,0], region_half_size 0.25}}`；原 `distractor: None` 不动 | 同 PickXtimes | 同上 |
| `SwingXtimes.__init__` 的 `objects.num_repeats` 取值点 | 加 `decision_key` | 同上 | 同上 |
| `SwingXtimes._load_scene` 的 `_color_lists` | 颜色池里出现红蓝绿以外的名字时**按名动态建表**（`setattr(self, f"{名}_cubes", …)`），不再 KeyError；同时维护 `_cube_color_of` 登记表 | 2.5 要点「第一道硬墙是 KeyError」；原快照只含红蓝绿，这段一次都不进，原三档不变 | 原三档零差异；这段是确定性的非随机代码 |
| `SwingXtimes._load_scene` 的目标选择 | xhard 走 `_select_target_xhard`（候选池解耦、按对象回填颜色、记 `objects.cube_count` 与 `objects.target_candidates`），其余难度走原代码 | 2.5「与 PickXtimes 完全同构」 | reset 冒烟 |
| `SwingXtimes._load_scene` 末尾 | xhard 在恢复动作抽样之后追加 `_spawn_distractors_xhard` | N5 | 同上 |
| `SwingXtimes._spawn_distractors_xhard`（新方法） | 与 PickXtimes 同构；两个圆盘经 `_disk_avoid_obb` 显式避让（c = 0.04+0.02−0.02 = 0.04） | A5/B2；圆盘取不到 OBB 同上 | reset 冒烟：干扰物中心到圆盘中心最小 0.103 m（下界 0.08） |

### 测试（新增）

| 文件 | 内容 |
|---|---|
| `tests/lightweight/test_v4_xhard_pickxtimes.py` | 17 项：原三档 configs 与 decision 可见部分逐字不变、xhard 新值、`native_blocks` 返回独立副本、守卫放行 num 端点／corner_bias 收窄并经真实 `_resolve_sampling_config`、拒绝改原三档或加申报外键、`NATIVE_SAMPLING` 颜色池不变、`_disk_avoid_obb` 形态、序数表覆盖 num=15 |
| `tests/lightweight/test_v4_xhard_swingxtimes.py` | 11 项：同上结构；另断言干扰色**没有**并入 `native.color_pool` |

均为纯 CPU、不起 sapien 场景（只 import 模块），合计 28 项 3 秒内通过。

## 二、四项必做验证

### 1. 原三档 reset 零差异

```bash
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks PickXtimes,SwingXtimes --out <scratch>/g1_probe.json
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json <scratch>/g1_probe.json
# RESET_REGRESSION=FAIL compared=18 diff=0 missing=126
```

18 条（两环境 × 三档 × 3 身份）全部 reset 成功、**diff=0**；FAIL 只因基线里其余 14 个环境的 126 行不在本次 probe 中（预期）。本组判定：**PASS**。

### 2. xhard reset 冒烟（每环境 20 seed，`900000 + 101·i`）

| 环境 | 成功 | num 分布 | 关键核验 |
|---|---|---|---|
| PickXtimes（corner_bias 1.0） | **20/20** | `{6:3, 7:1, 9:1, 10:3, 11:3, 12:2, 13:1, 14:2, 15:4}` ⊂ [6,15] | spec_kind 全为 `native-newvalue/1`；干扰物恰为黄/青/品红、`distractor_count={3,3}`；目标候选 3、`all_cubes` 6、`non_target_cubes` 5；目标颜色 ∈ 红蓝绿且从不为干扰物；圆盘中心到方块中心最小 0.112 m；方块两两中心最小 0.056 m |
| PickXtimes（corner_bias 0.5） | **20/20** | 同上（num 抽样与 corner_bias 无关） | 同上；方块两两中心最小 0.043 m |
| SwingXtimes | **20/20** | `{4:2, 5:6, 6:3, 7:1, 8:4, 9:2, 10:2}` ⊂ [4,10] | 同上；干扰物中心到圆盘中心最小 0.103 m；（有色方块到圆盘最小 0.072 m，来自原路径「圆盘避让方块」判据，与 hard 同一代码，未改） |

失败类型：无。

**边角偏置效果**（目标方块中心到可行域边界的最小距离，可行域 x∈[-0.28,0.08]、y∈[-0.18,0.18]）：

| corner_bias | 实测 reset 20 条：均值 / 中位 / 最大 | 纯映射蒙特卡洛 10 万点：均值 / 中位 / 距边 <2 cm 占比 |
|---|---|---|
| 0（均匀，参照） | — | 0.060 / 0.053 / 21.1% |
| 0.5 | 0.018 / 0.015 / 0.059 m | 0.026 / 0.020 / 50.7% |
| 1.0 | 0.013 / 0.010 / 0.038 m | 0.016 / 0.012 / 69.1% |

### 3. xhard 演示小样本（`scripts.parity.v4_demo_probe`，GPU 0，seed `910000 + 101·i`，每条 num 由 seed 决定）

| 组 | 配置 | 结果 | 逐条（seed：num → 结果，步数） |
|---|---|---|---|
| PickXtimes cb=1.0 | 默认 | **2/4** | 910000：10 → 成功 1516 步；910101：15 → FailsafeTimeout；910202：15 → FailsafeTimeout；910303：7 → 成功 1102 步 |
| PickXtimes cb=0.5 | `corner_bias=0.5` | **2/4** | 910000：10 → 成功 1536；910101：15 → FailsafeTimeout；910202：15 → FailsafeTimeout；910303：7 → 成功 1113 |
| PickXtimes num=6 端点 | `number_range.xhard=[6,6]` | **1/2** | 910000 成功 967 步；910101 任务失败（`环境报告失败`，录像显示第 4 次抓取时夹爪紧贴品红/黄干扰物，疑似碰到干扰物或抓错，归「任务失败」） |
| PickXtimes num=13 | `[13,13]` | **1/2** | 910000 成功 **1940 步**（距 2000 仅 60 步）；910101 FailsafeTimeout |
| PickXtimes num=14 | `[14,14]` | **0/2** | 两条均 FailsafeTimeout |
| PickXtimes num=15 端点 | `[15,15]` | **0/2** | 910404、910505 均 FailsafeTimeout；连同上面 cb 两组里 num=15 的 4 条，**num=15 共 0/6** |
| SwingXtimes 默认 | 默认 | **4/4** | 910000：10 → 953 步；910101：10 → 1046；910202：5 → 590；910303：8 → 913 |
| SwingXtimes num=4 端点 | `[4,4]` | **2/2** | 517、561 步 |
| SwingXtimes num=10 端点 | `[10,10]` | **2/2** | 953、1046 步 |

**口径 14 端点结论**：

- **PickXtimes num=15 端点演示 0 成功（0/6），num=14 也 0/2 ⇒ 按口径 14 / H3 属「传入了但生成不出来」，必须回报用户重定参数。**
  根因是录像器 `RecordWrapper.step` 里写死的 `fail_safe_limit = 2000`（录像器冻结，N2 不可改）：实测每个抓放循环约 138 步，
  `步数 ≈ 136 + 138·num`（num=7 → 1102、10 → 1516、13 → 1940），⇒ num ≥ 14 理论上必超 2000，num=13 已贴线（1940，单条就有一条超限）。
  **本组没有自行收窄范围**（N11），`config_xhard` 仍按用户原文 `[6,15]`。
- PickXtimes num=6 端点 1/2，非零，满足。
- SwingXtimes num=4 与 10 两端各 2/2；num=10 约 1000 步，离 2000 余量充足。

corner_bias 0.5 与 1.0 在同 4 个 seed 上成败完全一致（都只败在 num=15），成功条步数相差 < 2%，**4 条样本区分不出演示难度差异**。

### 4. 定向单测与既有测试

- 新增两文件 28 项全过（3.1 s）。
- `tests/lightweight/test_TaskGoalI_isList.py -k "PickXtimes or SwingXtimes"`：8 passed（该文件会真实起 16 个环境，本机当时负载 13~20，全文件单跑超 10 分钟，只跑本组相关参数化）。
- 轻量全量（去掉 `test_TaskGoalI_isList.py` 后）：除快照过期 1 项（预期，见「实测数字」）外与基线 46 项逐文件相同，无新增失败。

## 三、实测数字

- reset 探针：`compared=18 diff=0`。
- xhard reset：PickXtimes 20/20（cb 1.0）、20/20（cb 0.5），SwingXtimes 20/20（两次独立运行结果一致）。
- 演示：PickXtimes 合计 6/16（全部失败中 9 条 FailsafeTimeout、1 条任务失败）；SwingXtimes 8/8。
- 单条墙钟：PickXtimes 78~211 s（num=13~15 约 170~210 s），SwingXtimes 44~97 s。
- 轻量测试（`tests/lightweight/`，去掉 `test_TaskGoalI_isList.py`）：47 failed / 559 passed / 22 skipped / 12 errors（124 s）。
  与基线 46 项逐文件对照：test_episode_action_sampling 20、test_native_sampling_config 13、test_candidates_refactor 12 errors、
  test_candidate_loader 4、test_rollout_state 4、test_step_error_handling 2、test_TaskGoal 2、test_injection_migration 1 **全部与基线相同**；
  唯一多出的是 `test_sampling_config_split.py::test_snapshot_matches_source`——源码 decision 新增 xhard 条目后
  `scripts/configs/newtask-v4/sampling_config.json` 快照必然与源码不符，按公共说明快照由主 agent 统一重导、本组不提交，属预期。

## 四、计划外

1. **圆盘取不到 OBB，`avoid` 静默失效**：`spawn_random_target` 建的圆盘 `add_collision=False`，`get_actor_obb` 抛
   `AssertionError: can not get actor mesh`，被 `spawn_random_cube::_push_actor_as_obb2d` 的 `except Exception: pass` 吞掉。
   原代码因为圆盘总是最后放、由圆盘去避让方块，所以没暴露；G1 换序后方块放在圆盘之后就会穿到圆盘上。
   处置：两个环境各加 `_disk_avoid_obb` 预制外接正方形（不改共用 `object_generation.py`）。
2. **PickXtimes num ≥ 14 被录像器 2000 步硬上限截断**（见验证 3）。计划 2.4 只担心了圆盘容量与序数表，没算步数预算；
   计划 2.5 提醒过 SwingXtimes「注意步数预算」，实测 SwingXtimes 10 轮只要约 1000 步，反而是 PickXtimes 超限。
3. **SwingXtimes 干扰色没有并入 `native.color_pool`**：计划 2.5 表写「`native.color_pool` 扩入干扰色」，但 `color_pool`
   对所有难度都被消费（`randperm(len(color_groups))`、`idx < color` 截取），并入会①改原三档随机流、②让干扰色有机会成为
   目标色。改为 `decision.xhard.distractor` 单列三个干扰物；`_color_lists` 仍按计划改成动态建表（外部传入扩展色池时不再 KeyError）。
4. **「目标推向边角」的落点**：原代码的 `target_cube_position_policy` 实际作用于**全部有色方块**（目标是放完后才抽的）。
   为不把 `target_cube_idx` 抽样挪到方块之前（避免在 xhard 里额外改动既有取值点顺序），corner_bias 施加在三个有色方块
   （目标候选）上，干扰方块均匀放置 ⇒ 目标一定在边角附近，但另两个候选也在。是否只推目标一块见「待用户决策」②。
5. **PickXtimes 双真值**：xhard 路径改读 `NATIVE_SAMPLING.parameters.color_pool`；原三档仍读硬编码字面量（H2，两者当前值相同）。
6. worktree 起点不是 `00e2ef4`（初始在 `3a5951a`），开工前 `git reset --hard 00e2ef4` 对齐（当时工作区干净）。

## 五、待用户决策

1. **PickXtimes `num` 上界（口径 14 必须回报）**：`[6,15]` 中 14、15 在录像器 2000 步上限下演示 0 成功（num=15 0/6，num=14 0/2），
   num=13 1/2 且成功条 1940 步贴线。可选：(a) 把 xhard `num` 改为 `[6,12]`（约 1790 步，留约 10% 余量）或 `[6,13]`；
   (b) 放开录像器 `fail_safe_limit`（违反 N2，需用户明确解冻）；(c) 其他。**本组未改范围**，等用户定。
2. **PickXtimes `corner_bias` 取值**：现按用户原文「尽可能推向边角」取 1.0（可经 `decision.xhard.target_cube_position_policy.corner_bias`
   外部覆盖）。0.5 / 1.0 同 seed 各 4 条演示成败一致（2/4 vs 2/4，失败全为 num=15 超步数），区分不出难度；几何上 1.0 让目标距边中位 1.0 cm、
   0.5 为 1.5 cm（均匀为 5.3 cm）。请确认 1.0 还是 0.5。另请确认边角偏置施加对象：现为「三个有色候选方块」，若要求「只推目标一块」
   需在 xhard 里把 `target_cube_idx` 抽样提前到放方块之前。
3. PickXtimes 干扰方块的区域（现与有色方块同区域、均匀、不加边角偏置）与 SwingXtimes 干扰方块区域（原方块区域）是本组按计划未写明处的保守取法，可经 `decision.xhard.distractor` 覆盖；如有不同意见请指出。
