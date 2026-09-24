# S3d InsertPeg xhard 改动报告（V5 计划 2.8；L24～L29、L52、L53；红线 N17）

日期 2026-09-24。worktree `/data/hongzefu/robomme_v5_wt/insertpeg`（分支 `v5wt-insertpeg`，基于 `f5b6a17`），改动未提交。
本机（sm_89）演示结果只作调试参考（N16：规划期/本机数字不是验收结论）。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/InsertPeg.py` | 顶部 import | `SpecRecorder` 旁加导入 `EpisodeSpecError` | 回放守卫报错用 |
| 同上 | 模块级新函数 `_rect_corners` / `_point_segment_distance` / `_rects_overlap` / `footprint_gap` / `peg_footprint` / `box_footprint`（位于 `NATIVE_SAMPLING` 之后、`native_blocks` 之前） | 有向矩形精确距离：SAT 判相交（含接触）返回 0，否则取 32 个「顶点到边」距离最小值；杆/孔板轮廓从建模参数推出 | L25 |
| 同上 | `InsertPeg.config_xhard` | 删 `near_target_distractor`；新增 `peg_min_pair_gap_m: 0.03`、`peg_box_min_gap_m: 0.01`、`peg_x_max_m: 0.1` | L24 / L26 / L28 / L52 |
| 同上 | `_native_decision` 文档串与 `xhard` 注释 | 说明 V5 键变化；原三档可见四键不动 | — |
| 同上 | `_load_scene` 里「xhard 改读 xhard 子键」注释 | 去掉 `near_target_distractor` 字样 | 注释与代码一致 |
| 同上 | `_initialize_episode` xhard 分支 | `uniform_pegs = self.pegs[:-1]` → `uniform_pegs = []`（原生循环在 xhard 下一根都不跑，循环体逐字不动）；原生循环之后、「Store initial poses」之前加 `if xhard: self._xhard_sample_pegs(box_xy, box_yaw, xhard_cfg)`；obj/dir 之后删掉 `_xhard_place_near_target_peg` 调用，只保留 `_peg_grasp_flipped` 两行重置 | L27a：4 根一个循环、在 obj/dir 之前 |
| 同上 | 删除方法 `_xhard_place_near_target_peg`，新增方法 `_xhard_sample_pegs` | 见下节 | L27 / L28 / L29 / N17 / N18 |
| `tests/lightweight/test_v4_xhard_insertpeg.py` | `test_configs_three_tiers_identical_to_native`、`test_decision_visible_part_unchanged_and_guard`、模块文档串 | V4 断言改为 V5 语义：xhard 不再有 `near_target_distractor`，三个新键取值锁定；守卫放行样例改为收紧 `peg_min_pair_gap_m` | 规则 6 |
| `tests/lightweight/test_v5_xhard_insertpeg.py`（新建） | 全文件 | 见第四节 | 计划 LIGHTWEIGHT 行 |

范围外共享文件：**无改动**。`scripts/README.md` 1.14 节仍写着 V4 的 `near_target_distractor`，按计划第二部分 S4「README 补 V5 节」由 S4 处理，本步未动。

## 二、`_xhard_sample_pegs` 设计

签名：`InsertPeg._xhard_sample_pegs(self, box_xy, box_yaw, xhard_cfg) -> None`（`box_xy` 为 float32 的 2 维数组、`box_yaw` 为回放后的孔板朝向、`xhard_cfg = self._sampling["decision"]["xhard"]`）。
只读 `self.pegs / self._hb_generator / self._spec / self._sampling / self.length / self.radius / self._native_init_index`，可在假环境上直接调（单测即如此）。

每根杆（`i = 0..3`，目标恒为 peg_0，只是第一个被抽）最多 `peg_sampling.max_attempts = 512` 次：
1. `x = rand·(peg_x_max_m − x_offset) + x_offset`、`y = rand·y_span + y_offset`（与原生同一取法，只把 x 的跨度从 0.4 换成 0.1−(−0.2)=0.3，L52）；
2. 原生规则保留（L25）：`|xy − box| ≤ radius·6 = 0.06` 或对任一已放杆根 `≤ length·1.5 = 0.075` → 重抽；
3. 通过后才抽 `yaw = (rand·2−1)·π`（lazy）；
4. `footprint_gap(杆, 孔板) ≤ 0.01` → 重抽（L26）；对任一已放杆 `footprint_gap ≤ 0.03` → 重抽（L24，严格不等号）；
5. 接受后才调一次 `_spec.value("initializations.<k>.pegs.<i>", [[x,y], yaw], decision_key="xhard.peg_yaw_range")`（N18）；
6. **回放守卫（N17 / L29）**：对 `value` 返回的值（回放时即冻结值）重算两种轮廓间隔，违反即抛 `EpisodeSpecError`（导出模式下恒成立，复查不抽随机数）；
7. 耗尽抛真 `SceneGenerationError`（不静默少放）。

新增规格字段（全部 `record()`）：`initializations.<k>.peg_attempts`（4 根各自的尝试次数）、`initializations.<k>.min_pair_gap_m`、`initializations.<k>.min_box_gap_m`（本局实测最小轮廓间隔）。
删除的规格字段：`peg_placement`、`near_target_distance`、`near_target_attempts`。

xhard 随机流顺序（L1a 允许原地移位）：`_load_scene`（length、radius、head_rgb×3、randint(0,4)）→ 每次初始化：孔板 3 个 rand → 4 根杆循环（每次尝试 2 个 rand，过原生判据后再 1 个 yaw）→ obj、dir 各一次 randint。

### 几何常数核实（计划要求从实际建模核实）

- `build_peg`：根链接 = 杆头（`peg.set_pose` 设的是杆头位姿），杆尾经固定关节在 `root − length·u`；两段视觉盒半尺寸各 `(length/2, radius, radius)`，碰撞盒半长 `0.9·length/2`。
  ⇒ 整根视觉轮廓：中心 `root − (length/2)·u`、半尺寸 `(length, radius)` = **中心 root − 0.025u、半尺寸 (0.05, 0.01)**，与计划一致；碰撞盒被视觉轮廓完全包住，按视觉量更保守。
- `build_box_with_hole(inner=1.7r, outer=4r, depth=length)`：四块板局部 x 半长 = depth = 0.05，y 外沿 = outer = 0.04 ⇒ **半尺寸 (0.05, 0.04)**，与计划一致。
- 实现不写死常数，由 `self.length`、`self.radius`、`box.outer_radius_factor` 推出；单测用捕获式假 builder 真调 `build_peg` / `build_box_with_hole` 量出轮廓并与 `peg_footprint` / `box_footprint` 对比。

## 三、V0（原三档零改动）

- `git diff` 不触及 `config_native`（即 `configs["easy"/"medium"/"hard"]`）与 `NATIVE_SAMPLING`；`_native_decision` 顶层四键不动（`near_target_distractor: None` 仍在原三档可见部分）。
- 原生杆循环逐字未动；xhard 之外不执行任何新增语句、不多抽随机数（`_xhard_sample_pegs` 只在 `if xhard:` 下被调，单测用 AST 锁定）。
- **真实 reset 逐位对拍**：用 `git archive HEAD src` 导出基线源码，与改后源码分别跑 `reset_probe.py native`（seed 5300000、5300100、1、2、3、42 × easy/medium/hard = 18 局），对比 4 根/3 根杆头尾链接位置、四元数、孔板位姿、obj/dir、完整 episode_spec：`NATIVE_BITWISE PASS 18 18`。

## 四、测试

### 轻量测试

`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`（日志 `artifacts/newtask-v5/s3d-insertpeg/lw_final.log`）：
`47 failed, 1073 passed, 22 skipped, 74 deselected, 12 errors in 166.35s`。

与基线（58 条）比对：**多 1 条** `tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`，其余 58 条逐条相同。
原因：该测试跑 `scripts/parity/train_split_config.py extract --verify`，把源码提取结果与 **V4 快照** `scripts/configs/newtask-v4/sampling_config.json` 逐字节比；已核实 16 个任务里只有 InsertPeg 不一致（xhard 键形状变了），正是计划 1.4④ 写明的「V4 快照被形状检查拒绝」。
规则 6 禁止改 `scripts/configs/newtask-v4/**`，而把该测试改指 V5 快照属于 S4（`scripts/configs/newtask-v5/sampling_config.json` 一次性重导），本步不动；**其余 S3 各环境改 xhard 键后都会触发同一条**，交主会话在 S4 统一收口。

新测试 `test_v5_xhard_insertpeg.py`（234 条用例全过；与 V4 文件合跑 321 条全过）：
- `footprint_gap`：解析样例（端对端 0.04、侧对侧 0.04、T 形 0.02、45° 旋转方块 0.018284…）、对称性；接触/交叉/包含/部分重叠恒为 0 且 `0 > 0` 为假（严格不等号的必要性）；300 对随机矩形与密采样边界点暴力距离一致（精确值 ≤ 暴力值，差 < 采样步长）。
- 几何常数：捕获 `build_peg` / `build_box_with_hole` 的建模调用量出的轮廓与 `peg_footprint` / `box_footprint` 一致，且等于 (0.05, 0.01)/−0.025u 与 (0.05, 0.04)。
- 假环境 200 个 seed：4 根全部放下，两两轮廓 > 0.03、离孔板 > 0.01、原生杆根判据仍成立、x ∈ [−0.2, 0.1]、y ∈ [−0.3, 0.3]、`peg_attempts` 与两个最小间隔已记录。
- 随机流顺序：20 个 seed 与按计划伪码独立写的参考实现逐位一致，且采样后生成器下一个 rand 相同。
- 耗尽抛 `SceneGenerationError`。
- 回放：自导出规格回放零 mismatch、位姿一致；篡改（两杆侧距 0.02、杆压孔板）抛 `EpisodeSpecError`；V4 v4-01 seed 5300000 的冻结布局（逐字抄录）抛 `EpisodeSpecError`；V4 header 的 `decision.xhard`（带 `near_target_distractor`）被 `_resolve_sampling_config` 以 `SamplingConfigError` 拒绝。
- AST：`_xhard_sample_pegs` 只在 `if xhard:` 下被调用一次；`_xhard_place_near_target_peg` 已不存在；`_initialize_episode` 源码不读任何 V5 新键。

### 20 次真实 reset（`artifacts/newtask-v5/s3d-insertpeg/reset_probe.py xhard`）

seed：v4-01 的 10 个（5300000…5300900）+ 1…10。几何全部从真实链接位姿量（杆头/杆尾链接中点与连线方向），不借用采样器内部约定。

```
INSERTPEG_V5_SPACING=PASS n=20 min_pair_gap_m=0.0315 min_box_gap_m=0.0170 max_root_x=0.0972
INSERTPEG_V5_RNG_ORDER=PASS exact=20/20      （独立参考实现重放整条随机流，两次初始化的孔板/4 根杆/obj/dir 逐位一致）
INSERTPEG_V5_SETTLE=PASS max_dxy_mm=0.0010   （静置 20 步最大横移）
```
每局 `peg_attempts` 最大 7；V4 规格回放被拒见单测（`INSERTPEG_V4_SPEC_REJECTED` 由单测覆盖）。

## 五、本机演示（`scripts.parity.v4_demo_probe`，GPU 1）

seed 取 v4-01 的 10 个，episode 号按 P6 的 recovery 分档（0～2 用 `--episode 0`、3～5 用 `--episode 3`、6～9 用 `--episode 9`），输出 `artifacts/newtask-v5/demo-probe/s3d-insertpeg/ep{0,3,9}/`。
注意：L52 改了 x 跨度，随机流随之移位，**同一 seed 的布局与 P6 不同**，只能按比例对比。

**成功 4/10**（P6 原型 4/10，V4 2/10）。失败诱因由 `diag_probe.py` 对 6 个失败 seed 重跑主入口 `_worker`（真实 V5 代码）逐阶段记录（`diag.jsonl`），6 局全部复现：

| seed | 结果 | obj（抓哪端） | 抓取点离基座 | 插入后插入端离孔板中心（示范段 / 执行段） | 诱因 |
|---|---|---|---|---|---|
| 5300000 | 成功 | −1（抓头插尾） | 0.618 | — | — |
| 5300100 | 成功 | −1 | 0.717 | — | — |
| 5300200 | 失败 DatasetGenerationError | 1（抓尾插头） | 0.643 | 0.0724 / 0.0724 | 插入不到位 |
| 5300300 | 失败 PlannerExhausted | 1 | 0.713 | 0.0498（示范段成功） | 其他：复位阶段后目标杆被弹飞 13.6 m，执行段抓取规划失败 |
| 5300400 | 失败 DatasetGenerationError | 1 | 0.485 | 0.0736 / 0.0749 | 插入不到位 |
| 5300500 | 成功 | −1 | 0.501 | — | — |
| 5300600 | 失败 DatasetGenerationError | 1 | 0.452 | 0.0721 / 0.0721 | 插入不到位 |
| 5300700 | 失败 DatasetGenerationError | 1 | 0.614 | 0.0744 / 0.0744 | 插入不到位 |
| 5300800 | 成功 | −1 | 0.628 | — | — |
| 5300900 | 失败 DatasetGenerationError | 1 | 0.533 | 0.0506 / 0.0506 | 插入不到位 |

```
INSERTPEG_DEMO=REPORT ok=4/10 by_cause={可达极限:0, 插入不到位:5, 规划失败:0, 其他(复位后目标杆被弹飞→PlannerExhausted):1}
```

- **可达极限清零**：抓取点离基座最大 0.717 m（P6 为 0.815 / 0.832 m 各致 1 局失败），L52 起效。
- **间隔类失败保持为零**：6 局失败里非目标杆全程最大抬升 0 mm、最大横移 0 mm，与间隔无关。
- **插入不到位 5 局全是 obj=1（抓尾插头）**，插入端离孔板中心 0.0506～0.0749 > 判据 0.05，与 P6 的 3 局同型；这是 L53 已决定「本轮不修」的 `insert_peg` 求解器问题。本组 obj=1 共 6 局全部失败、obj=−1 4 局全部成功（P6 里 obj=1 为 4/7 成功，所以不是 obj=1 必败，但本组偏得很明显）。
- **5300300 是新现象**：示范段插入成功（0.0498），`solve_strong_reset` 复位 30 步后，接下来的静置 100 步里目标杆被弹飞约 13.6 m（插入端离孔板 13.88 m），执行段抓取无从规划 → `PlannerExhausted`。邻杆与孔板未动，与间隔规则无关；推测是复位期间逐步 `set_pose` 到 z=0 的初始位姿却不清根链接速度（杆是 0 自由度，`set_qvel` 分支不执行），释放时积累的接触冲量把杆弹飞，属原生机制，原三档同样存在这段代码。未深挖，列入待决。
- 静置 20 步横移见第四节（0.001 mm）。

## 六、与计划不符之处

1. 计划写「原生循环逐字不动」：本实现保留循环体逐字不动，只把 xhard 下的 `uniform_pegs` 置为空列表，4 根杆改由紧随其后的 `_xhard_sample_pegs` 抽；循环体内 V4 留下的 `if xhard: raise SceneGenerationError` 从此在 xhard 下不可达（死分支，未删以免改动原生循环文本）。
2. 计划的「注入 `min_pair_gap_m` / `min_box_gap_m`」理解为把本局实测最小间隔 `record()` 进规格（`initializations.<k>.min_pair_gap_m` / `min_box_gap_m`）；配置键名按计划为 `peg_min_pair_gap_m` / `peg_box_min_gap_m`。
3. L52 的 x 上界用新键 `config_xhard.peg_x_max_m = 0.1` 表达（原生 `x_offset/x_span` 属原三档消费的 `NATIVE_SAMPLING`，不能动）。
4. 回放守卫只复核两种轮廓间隔（计划 L29 原文）；原生杆根规则与 x 上界未复核。违反时抛 `EpisodeSpecError`（环境侧 `utils/episode_spec.py` 的那个，`ValueError` 子类）而不是记 mismatch。
5. 孔板轮廓直接取建模的外包矩形，孔板中空部分不计（保守）。
6. `decision_key` 沿用 V4 的 `"xhard.peg_yaw_range"`（一个取值点只能归因一个键；任何不等都算已归因）。

## 七、待用户决策

1. **InsertPeg 演示成功率约 40%，失败主体是 L53 的插入不到位（本组 5/10，全是抓尾插头）**。L53 已答「不修」；本组数据（obj=1 6/6 失败）比 P6 更偏，正式生成按约 40% 通过率留余量是否仍可接受，或是否重开 L53（只在 xhard 修求解器插入末段）——请用户确认。
2. **新现象：复位阶段后目标杆被弹飞（seed 5300300，13.6 m）**，与 V5 采样无关、疑为原生 `step` 复位逻辑不清根速度；是否另立事项排查（改动会落在 `src/robomme` 的原生代码路径，需对原三档做 V1 评估）。

## 八、给合并者的注意

- 新 API：`footprint_gap(rect_a, rect_b) -> float`，`rect = (center_xy, yaw, (half_x, half_y))`；`peg_footprint(root_xy, yaw, length, radius)`；`box_footprint(box_xy, box_yaw, depth, outer_radius)`；均为 `robomme.robomme_env.InsertPeg` 模块级纯函数（为避免与其他 S3 子任务在共享的 `utils/xhard.py` 冲突，没放那里；如需复用可再挪）。
- `InsertPeg._xhard_sample_pegs(self, box_xy, box_yaw, xhard_cfg)`，签名与行为见第二节。
- `test_sampling_config_split.py::test_snapshot_matches_source` 在 S4 重导 V5 快照（并把该测试 / `train_split_config.py` 的默认路径改指 V5）之前会一直失败；本步唯一的失败集合差异就是它。
- `scripts/README.md` 1.14 节的 InsertPeg 字段表需在 S4 更新为 V5（删 `near_target_distractor`，加三个新键与三个新规格字段，删三个旧规格字段）。
- 探针脚本与结果（git 忽略的 `artifacts/` 下）：`artifacts/newtask-v5/s3d-insertpeg/{reset_probe.py, diag_probe.py, xhard_resets.json/.log, native_new.json, native_base.json, diag.jsonl, diag.log, lw_final.log}`、`artifacts/newtask-v5/demo-probe/s3d-insertpeg/{run_demo.sh, run.log, ep0, ep3, ep9}`。diag 进程退出码 139 是 sapien 退出时段错误（P6 同样），结果已写完。
