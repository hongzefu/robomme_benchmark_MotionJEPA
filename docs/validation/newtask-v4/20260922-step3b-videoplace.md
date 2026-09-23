# V4 步 3b：VideoPlaceButton / VideoPlaceOrder 的 xhard（计划 2.14 / 2.15）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`）。录像器未改（`RECORDER_FROZEN=PASS`）。
> 用户原文：「VideoPlaceButton, VideoPlaceOrder,  video 里面完成2 个 block, 各自放回原位，其余不变」。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `VideoPlaceButton.py::config_xhard`、`VideoPlaceOrder.py::config_xhard`（新增，进 `configs`） | 从 hard 逐字拷贝：`color 3 / targets 4 / swap True`（VPB 另有 `additional_place False`） | 口径 7 / 2.1：派生自 hard，「其余不变」 | `test_v4_xhard_videoplace.py::test_xhard_derived_from_hard`、`test_original_three_configs_unchanged` |
| 两环境 `_native_decision` + 模块常量 `XHARD_DEMO_DECISION` | 原两键 `demo_object_count=1` / `demo_return_policy="native_random_goal_site"` **不动**；新增子键 `"xhard": {"demo_object_count": 2, "demo_return_policy": "return_to_origin"}` | 守卫去掉 `xhard` 后原三档可见部分与原值逐字相同；xhard 值可被外部配置收窄 | `test_decision_visible_part_equals_original`、`test_guard_accepts_declared_and_rejects_undeclared` |
| `VideoPlaceButton.py::_load_scene`（在目标台循环之后插一处分叉） | `difficulty == "xhard"` 时转入 `_load_scene_xhard_tail(generator)` 并 `return`；原三档加一行 `validate_demo_plan(decision_cfg["demo_object_count"], …)` 作真实消费点（不抽随机数），其余原代码一行不改 | 演示模板是内联硬编码（在 `_load_scene` 末段）⇒ xhard 另写按对象循环的模板 | reset 探针 VPB 9 条零差异 |
| `VideoPlaceButton.py::_load_scene_xhard_tail`（新增） | 见第二节「VideoPlaceButton 模板」 | 2.14 | xhard reset 冒烟 20/20；演示探针见第四节 |
| `VideoPlaceButton.py::_xhard_pick_place` / `_xhard_closing_tasks`（新增） | 演示段的 pick+drop 对（闭包按默认参数绑定对象）、演示收尾与执行段（与原三档同构） | 同上 | 同上 |
| `VideoPlaceOrder.py::_load_scene`（目标台循环之后一处分叉） | 同 VPB：xhard 转入 `_load_scene_xhard_tail()` 并 `return`；原三档加一行 `validate_demo_plan` 消费点 | 2.15 | reset 探针 VPO 9 条零差异 |
| `VideoPlaceOrder.py::_load_scene` 的方块与目标台 spawn 调用 | 追加 `**self._xhard_spec_kwargs(path)`：原三档返回 `{}`（调用形态与原来等价），xhard 传 `recorder=self._spec, spec_path="layout.cubes.*" / "layout.targets.*"` | VPO 原来不记方块／目标台位姿，xhard 规格要能回注布局；记录器只冻结已接受的取值、不多抽随机数 | reset 探针零差异；xhard 规格含 `layout.cubes/targets` |
| `VideoPlaceOrder.py::_initialize_episode`（隐藏 goal_site 之后一处分叉） | xhard 转入 `_build_xhard_task_list()` 并 `return` | 2.15：VPO 的演示模板在 `_initialize_episode`（与 VPB 位置不同） | 同上 |
| `VideoPlaceOrder.py::_load_scene_xhard_tail` / `_build_xhard_task_list` / `_xhard_pick_place` / `xhard_button_task_index`（新增） | 见第二节「VideoPlaceOrder 模板」与按钮公式 | 2.15：`k*2+2` 在 2 对象下失效 | `test_button_index_*`；冒烟逐条核对按钮前一步是「访问放置」且下标与公式一致 |
| `utils/xhard_home_site.py`（新增） | `validate_demo_plan`（演示数与返回策略的合法组合，不合法抛 `SceneGenerationError`）、`build_home_sites`（按方块初始位姿直接调 `build_gray_white_target` 建隐藏落点，当场自检两条验收）、`home_pose_record` | 2.14「放回原位需要落点 actor」；**不用** `spawn_random_target(randomize=False)`（形参未被读、照样 `torch.rand`；BinFill 原三档在用、不许改，N12） | `test_build_home_sites_*` 三条（替身 builder：位姿逐位相等、RNG 逐字节相等；漂移 1e-6 与偷抽随机数都被拒）；真实环境冒烟中 reset 成功的 29 局（VPB 20＋VPO 9）自检全部通过 |
| `utils/vqa_options.py::_videoplace_drop_available`（新增）及 `_options_videoplaceorder` / `_options_videoplacebutton` 的 `"available"` | 原三档原样返回 `env.targets`（同一对象）；xhard（`base.xhard_home_sites` 非空）返回 `targets + 两个落点` | 「放回原位」这步若走 choice-action 匹配，落点不在 `targets` 里会选不到 | `test_vqa_drop_available`；冒烟核对 `available` 长度 6 且含两个落点 |
| `scripts/parity/train_split_audit.py::NEUTRAL_KEYS` | 撤销 `VideoPlaceButton/Order.decision.demo_object_count` 两条豁免 | 计划第二部分步 2：xhard 按对象循环后已有真实消费点 | `config-map`：`SAMPLING_ORIGINAL=PASS unmapped=0`（说明键 34→30）；`test_audit_exemptions_revoked` |
| `tests/lightweight/test_v4_xhard_videoplace.py`（新增） | 22 项纯 CPU 结构性测试 | 必做验证 4 | 22 passed / 3.5 s |

## 二、xhard 语义（实现口径）

### 共用

- **演示对象**：原 `randint(0, len(all_cubes))` 选 1 块 → xhard 改 `randperm(len(all_cubes))[:demo_object_count]`（取值点
  `objects.demo_ids`，`decision_key="xhard.demo_object_count"`）。只平移 xhard 自己的随机流（计划已允许）。
- **放回原位**：所有 spawn 之后，对每个演示方块在其 `initial_pose` 上建 `home_site_<方块名>`（kinematic、无碰撞、
  `radius=cube_half_size`），登记进 `env._hidden_objects`——**传感器画面（录像器用的 base/hand camera）里不可见**，
  与原三档把 goal_site 压到桌面以下同理，画面不多出「答案标记」。`solve_putonto_whenhold` 取落点 `pose.p`（z=方块半边长
  0.02，即方块底面贴桌），`is_obj_dropped_onto` 只看水平距离 ≤0.05。落点位姿记进 `actions.return_pose_by_object_id`。
- **两条验收当场自检**（不过即抛 `SceneGenerationError`）：落点 `raw_pose` 与方块 `initial_pose.raw_pose` 7 个 float32 逐位相等
  （CPU 仿真下再比一次实体位姿）；建 actor 前后 `generator.get_state()` 逐字节相等。
- **「放回原位」只保证位置**：夹爪抓放不改姿态，方块 yaw 经抓取几何保持（模 90° 对称），不另行强制。
- 执行段（NO RECORD 之后）与原三档同构：拿答案方块、放到正确的台；拿错其他方块（含另一个演示方块）或放错台判失败。
- 新增子目标名：`put the cube back to its original position`（`subgoal_segment` 同名加 ` at <>`，`choice_label="drop onto"`）。

### VideoPlaceButton 模板

```text
对每个演示方块 k：pick(k) → drop(targets[2k])        ← 按钮前
press button（全程只按一次）
对每个演示方块 k：pick(k) → drop(targets[2k+1])      ← 按钮后
对每个演示方块 k：pick(k) → drop(home_k)             ← 放回原位（取代原「放随机 goal_site」）
static20 → static60(swap) → NO RECORD → pick(答案方块) → drop(target_target)
```

- 答案（task_mapping 的 2 对象推广，**待用户决策 Q1**）：先按原规则抽 `task_flag` 定 before/after（取值点 `objects.task_flag`），
  再**新抽**「问哪一个演示方块」`answer_demo_index = randint(0, 2)`（追加在 `task_flag` 之后）；
  before → 该方块按钮前放上的台 `targets[2k]`，after → 按钮后放上的台 `targets[2k+1]`。指令文本模板不变，只是 `{color}`
  换成答案方块的颜色。
- 随机流顺序（xhard）：`demo_ids randperm` → swap `randperm`（原样，xhard 下挂取值点 `objects.swap_pair_ids`）→ `task_flag` →
  `answer_demo_index`；`additional_place` 在 xhard 固定 False（传 True 直接拒绝，原 target_2/target_3 死分支不进 xhard 模板）。
- 需要 `targets ≥ 2×demo_object_count`，不满足直接抛 `SceneGenerationError`。

### VideoPlaceOrder 模板

```text
对每个演示方块 k 依次：
    按原规则访问若干目标台：[pick(k) → drop(visit_k[0])] … [pick(k) → drop(visit_k[n_k-1])]
    pick(k) → drop(home_k)                     ← 走完立即放回原位，再轮到下一个方块（台面不被占着）
press button 插在「全局第 (b+1) 次访问放置」之后（全程一次）
static20 → static60(swap) → NO RECORD → pick(答案方块) → drop(target_target)
```

- 每个演示方块各自按原规则抽访问数 `randint(2, len(targets)+1)` 与访问顺序 `randperm[:n]`
  （取值点 `objects.num_targets_by_object.<k>` / `objects.visit_ids_by_object.<k>`）。
- 答案（**待用户决策 Q1**）：新抽 `answer_demo_index`；`which_in_subset` 在**答案方块自己的访问序列**里按原规则抽
  （`randint(1, n_answer+1)`）；指令「把 {答案方块颜色} 方块放到它第 n 次放上的台」文本不变。
- **按钮公式重推**（取代 `k*2+2`）：`b = randint(0, 总访问数)`，
  `button_task_index = 2 × (b + 1 + 在这之前已完成的「放回原位」单元数)`。每个单元（访问或放回原位）都是 pick+drop 两条，
  按钮永远落在两个单元之间；某对象最后一次访问恰为插点时按钮排在它放回原位**之前**。单对象时退化为原 `k*2+2`
  （测试逐 k 核对）。取值点 `objects.button_after_visit_index`，派生量记 `actions.button_task_index`。
- 随机流顺序（xhard）：`demo_ids randperm` → swap `randperm`（原样）→ 逐对象 [访问数, 访问序] → `answer_demo_index` →
  `which_in_subset` → 按钮插点。

## 三、原三档零差异（必做验证 1）

```bash
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m scripts.parity.v4_reset_probe probe \
    --tasks VideoPlaceButton,VideoPlaceOrder --out /tmp/g8_probe.json
uv run --no-sync python -m scripts.parity.v4_reset_probe diff \
    artifacts/newtask-v4/probe/base-13e.json /tmp/g8_probe.json
# RESET_REGRESSION=FAIL compared=18 diff=0 missing=126
```

本组 18 条（两环境各 easy/medium/hard 各 3 条）全部 reset 成功、`diff=0`；`missing=126` 全是基线里其他 14 个环境的行（预期）。

## 四、实测数字

### 4.1 xhard reset 冒烟（必做验证 2，本机 GPU1，seed = 900000 + 101·i，i=0..19）

| 环境 | reset 成功 | 失败类型 | 核对项全部通过 |
|---|---|---|---|
| VideoPlaceButton | **20/20** | — | 20/20：kind=`native-newvalue/1`；3 块 4 台；演示 2 块互异；2 个落点、位姿逐位＝方块 `initial_pose`（reset 后仍相等，且等于方块当前位姿）、`rng_state_equal=True`、登记隐藏；放回原位 2 步；按钮 1 次且前一步是放置；before/after 映射正确（before 10 / after 10；问第 1/2 块 = 11/9）；vqa `available` = 6（4 台＋2 落点） |
| VideoPlaceOrder | **9/20** | 11 条 `spawn_random_target` 放不下第 4 个目标台（表现为 `TypeError`，见计划外 ①②） | 成功的 9/9 全部通过：同上各项，另核 `button_task_index` 与实际下标一致、按钮前一步是「访问放置」且不在放回原位之后、`which_in_subset` 映射正确；访问数分布 `[3,4]×3、[4,3]×3、[3,3]、[3,2]、[2,4]` |

对照（`g8_hard_cmp.py`）：同一 20 个 seed 以 **hard** reset，VideoPlaceOrder 同样 **9/20**，失败 seed 集合与 xhard **完全一致**
（agree=20/20），两档都成功的 9 条方块＋目标台 `initial_pose` 逐位相同 ⇒ reset 失败是 hard 布局段的既有性质，不是 xhard 引入的。

### 4.2 xhard 演示小样本（必做验证 3，`v4_demo_probe`，本机 GPU1，只调试不进判据）

| 环境 | seed | 演示 | 帧数 | 墙钟 |
|---|---|---|---|---|
| VideoPlaceButton | 900000 / 900101 / 900202 / 900303 | **4/4 成功** | 1561 / 1613 / 1642 / 1583 | 155~174 s |
| VideoPlaceOrder | 900000 / 900202 / 900303 / 900505 | **4/4 成功** | 1931 / 1828 / 1917 / 1890 | 159~204 s |

产物在 `artifacts/newtask-v4/demo-probe/VideoPlace{Button,Order}-g8{a,b}/`（gitignore，不入库）。
口径 14：本组 xhard 声明的参数只有离散的单值组合（`demo_object_count=2`、`return_to_origin`，其余与 hard 相同），
**唯一组合演示 8/8 成功，不存在 0 成功的端点组合**。

### 4.3 定向单测与审计（必做验证 4）

- 新增 `test_v4_xhard_videoplace.py`：**22 passed**（3.5 s，纯 CPU）。
- `train_split_audit.py config-map`：`SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0`（叶子键 851→862，
  说明键 34→30：两条豁免撤销后 `demo_object_count` 由真实消费点覆盖）。
- 既有测试（CUDA_VISIBLE_DEVICES=1）：
  - `test_TaskGoalI_isList.py -k VideoPlace` + `test_choice_action_pixel_mapping.py` + `test_TaskGoal.py` + `test_native_sampling_config.py`
    + `test_native_sampling_evidence.py` + `test_episode_action_sampling.py`：35 failed / 110 passed（82 s）；失败分布
    `test_episode_action_sampling` 20、`test_native_sampling_config` 13、`test_TaskGoal` 2，**与已知基线逐文件同数**，无一涉及 VideoPlace。
  - `test_episode_spec_recorder.py`（11）、`test_ChoiceLabel.py`（3）、`test_v4_decision_guard.py` 全过。
  - `test_sampling_config_split.py`：37 passed / **1 failed**（`test_snapshot_matches_source`，快照未重导，预期，见计划外 ⑤）。
  - `test_TaskGoalI_isList.py` 其余 14 个环境的参数化项每项要起整环境，本机被多 agent 并发占满时 10 分钟跑不完，未跑（未改这些环境）。
- 录像器：`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` ⇒ `RECORDER_FROZEN=PASS`。

## 五、计划外

① **VideoPlaceOrder 的 `SceneGenerationError` 被模块对象遮蔽（既有缺陷，四档共有）。** `VideoPlaceOrder.py` 的导入顺序是
先 `from .utils.SceneGenerationError import SceneGenerationError`、后 `from .utils import *`，后者把**同名子模块**导进来
覆盖了异常类。于是 `_load_scene` 里任何布局失败都会变成 `TypeError: 'module' object is not callable`，
再在 `except SceneGenerationError:` 处变成 `TypeError: catching classes that do not inherit from BaseException`。
`generate_dataset_newseed._worker` 只把 `SceneGenerationError` 等列为可重试的任务性失败，`TypeError` 会被记成
`failure_class="code"`。VideoPlaceButton 的导入顺序相反，没有这个问题。按 H2/N12 **本轮未修**（修了会改变原三档失败时的异常类型），
列入待用户决策 Q2。

② **VideoPlaceOrder hard 布局段本身 reset 成功率只有约 45%**（20 个 seed 中 9 个成功；失败全是第 4 个目标台放不下：
goal_site 半径系数 5、目标台半径系数 2、区域半边长 0.2 太挤）。xhard 布局段与 hard 逐字相同，成功率随之相同。
对 F2「每环境 10 条 reset 成功、尝试上限 30」：按 p≈0.45 估算，30 次里凑不满 10 条的概率约 7%（二项分布 P(X<10 | n=30, p=0.45) ≈ 0.069），
叠加 ① 的 `TypeError` 分类，抽签段需按 `SceneGenerationError` 以外的异常也计为 reset 失败来处理。

③ 计划 2.14 写 `native.task_mapping` 是字段、并称「注入 `objects.task_flag`、`actions.target_target_id`」：源码里原三档
`task_flag` 与 swap 抽样（VideoPlaceButton）**都没有挂取值点**。本轮只在 xhard 分支给它们挂了 `objects.task_flag` /
`objects.swap_pair_ids`，原三档保持不记（避免改原值规格）。

④ VideoPlaceOrder 原三档**不记**方块与目标台位姿（`spawn_*` 没传 recorder）；xhard 用 `_xhard_spec_kwargs` 补记
`layout.cubes.*` / `layout.targets.*`，原三档调用形态等价（传空字典）。

⑤ 快照 `scripts/configs/newtask-v4/sampling_config.json` 与源码不再一致（`test_sampling_config_split.py::test_snapshot_matches_source`
失败，属新增失败但为预期）：提取结果与现快照的差异**只有**两环境 `targets/swap/additional_place/color` 各多一项 `xhard`、
decision 多一个 `xhard` 子键。按公共说明不提交快照，由主 agent 统一重导。

⑥ 新增 `utils/xhard_home_site.py` 是一个新工具文件（计划第二部分一「工具文件若确需改动须列出函数与理由」）：
`validate_demo_plan` / `build_home_sites` / `home_pose_record` 三个函数，两环境共用，理由见第一节；未改任何既有工具函数。

## 六、待用户决策

- **Q1 两对象下的答案定义（task_mapping）**——计划只说「须重新定义」。本轮代码先用我认为最自然、可被推翻的方案：
  - VideoPlaceButton：按钮只按一次；两个演示方块各在按钮前放一个台、按钮后放另一个台（`targets[2k]` / `targets[2k+1]`，
    4 台正好用满）；新抽「问哪一个演示方块」，before/after 仍由原 `task_flag` 决定。
  - VideoPlaceOrder：两个演示方块**依次**各走一遍原规则的访问序列、走完立即放回原位；新抽「问哪一个演示方块」，
    `which_in_subset` 在它自己的访问序列里抽；按钮全程一次，插在全局某次访问放置之后。
  - 可替代方案：固定问第一个演示方块（不新增抽样）；VideoPlaceOrder 两方块共用同一访问序列交错放置（需处理台被占用）；
    VideoPlaceButton 每个方块各按一次按钮（「按钮前/后」会变歧义，不推荐）。若用户改定，只动两个 `_load_scene_xhard_tail` 与模板。
- **Q2 VideoPlaceOrder 的 `SceneGenerationError` 遮蔽缺陷是否修（计划外 ①）**：修法是把导入挪到 `from .utils import *` 之后
  （与 VideoPlaceButton 一致）。**会改变原三档**「布局失败时抛出的异常类型」（`TypeError` → `SceneGenerationError`，
  失败分类 code → task），成功局与随机流不受影响；按 H2 须用户点头。不修的话 xhard 抽签段要把这类 `TypeError` 也当 reset 失败。
- **Q3 放回原位的落点是否在画面上可见**：本轮登记为隐藏（传感器画面不可见，与原 goal_site 压到桌下同理）。若希望视频里看得到
  「原位标记」，只需去掉 `_hidden_objects` 登记。
- **Q4 VideoPlaceOrder reset 成功率约 45%（计划外 ②）** 是否需要在 xhard 放宽目标台采样（例如收小 goal_site 半径系数）——
  用户原文是「其余不变」，本轮**未改**布局；若 F2 凑不满 10 条，需用户定是否放宽。

## 七、复现

冒烟与对照脚本留档在 `docs/validation/newtask-v4/step3b-videoplace-scripts/`（在仓库根执行）：

```bash
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python docs/validation/newtask-v4/step3b-videoplace-scripts/g8_xr.py VideoPlaceButton 20
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python docs/validation/newtask-v4/step3b-videoplace-scripts/g8_xr.py VideoPlaceOrder 20
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python docs/validation/newtask-v4/step3b-videoplace-scripts/g8_hard_cmp.py VideoPlaceOrder 20
uv run --no-sync python -m scripts.parity.v4_demo_probe --task VideoPlaceButton --seeds 900000,900101 --gpu 1 \
    --out artifacts/newtask-v4/demo-probe/VideoPlaceButton-g8a
```
