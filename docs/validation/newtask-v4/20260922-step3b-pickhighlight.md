# V4 步 3b：PickHighlight 的 xhard（clutter 8~10 块 + 高亮 5~7 块 + 颜色任意）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`），计划依据 `NEWTASK_RELEASE_V4_PLAN.md` 2.12、2.21「PickHighlight 简图」、
> 1.3 的 B1 / B5 / C3 / D4 / H2 / H3。录像器未改（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 通过）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `src/robomme/robomme_env/PickHighlight.py::PickHighlight.config_xhard`（新增，进 `configs`） | `{"spawn": [8, 10], "pickup": [5, 7]}`（闭区间，每局各抽一次） | 用户原文「highlight number [5,7]」；B5 定 spawn `[8,10]`；区域与 `min_gap` 不动（B1/B5） | `test_v4_xhard_pickhighlight.py::test_xhard新值`；reset 冒烟 spawn/highlight 全部落在区间内 |
| `PickHighlight.py::_native_decision` / 新增模块常量 `XHARD_DECISION` | `highlight_count` / `spawn_count` 随 `configs` 自动多出 `xhard` 项（改为深拷贝，避免外部改导出值回写类属性）；顶层新增 `xhard` 子键 `{"block_color_policy": "uniform_rgb", "subgoal_color_suffix": "omit"}` | xhard 专属新 decision 键放在 `xhard` 子键下，守卫去掉 xhard 后原三档可见部分与原值逐字相同 | `test_decision去掉xhard后与原值相同`（与 00e2ef4 的原值 decision 逐字对照）、`test_守卫放行…`、`test_守卫拒绝…` |
| `PickHighlight.py::_closed_range`（新增） | 校验 xhard 闭区间 `[lo, hi]`（1≤lo≤hi 的整数），写坏即 `SamplingConfigError` | 外部 `sampling_config` 可以收窄 xhard 区间（端点单测就靠它），必须挡住写坏的值 | `test_区间校验` |
| `PickHighlight.py::_load_scene`（xhard 分支） | ① 校验 `xhard.block_color_policy`／`subgoal_color_suffix` 只接受已实现取值；② **spawn≥highlight 硬断言**：按生效区间最坏情形 `spawn_lo ≥ highlight_hi`，否则 `SamplingConfigError`；③ 新增取值点 `objects.n_cubes`（`decision_key=spawn_count.xhard`）；④ 逐块颜色改为 `torch.rand(3)` 均匀 RGB＋alpha 1，取值点 `objects.color_rgba.<i>`（`decision_key=xhard.block_color_policy`），actor 名 `cube_rgb_<i>`、颜色标签置 `None`；⑤ 放不满（原 `except RuntimeError: break`）改抛 `SceneGenerationError`，报「请求 N 实际 M」；⑥ 记 `objects.n_cubes_spawned`（请求数 vs 实际数）；⑦ 保留原 `randperm(len(all_cubes))` 原位，**之后**再抽 `objects.highlight_count`，`k > len` 显式抛 `SceneGenerationError`（挡住 `randperm[:k]` 静默截断），`objects.highlight_ids` 带 `decision_key=highlight_count.xhard` | 计划 2.12 实施要点与 2.2④「不许静默截断」 | reset 冒烟 24/24；spawn=10 压力 39/40（失败 1 条即 `SceneGenerationError`，不再静默少块）；导出→回注 5/5 位姿、任务表、`highlight_ids` 全同且 `mismatches=0` |
| `PickHighlight.py::_load_scene`（按钮任务 `failure_func`） | **D4 只在 xhard 修**：xhard 分支包成 `lambda: is_any_obj_pickup(...)`；原三档仍是构造时求值（判据从未生效，按 H2 原样保留） | D4 / H2 / N12 | `test_源码xhard分支不静默截断且D4只在xhard修`；冒烟里 `callable(task_list[0]["failure_func"])` 24/24 为真；演示 13 条成功说明补上的判据不误报 |
| `PickHighlight.py::_load_scene`（pick 子目标文案） | xhard 下去掉 `, which is {color}` 整段后缀：多目标 `pick up the {idx} highlighted cube[ at <>]`，单目标 `pick up the highlighted cube[ at <>]` | 任意 RGB 没有颜色名；「omit」是不输出任何可能错误颜色词的最保守方案（**待用户决策**，见第五节） | 冒烟 24/24 任务名无 `which is`；演示 h5 的 subgoal 全部无后缀 |
| `PickHighlight.py::step` | xhard 下本局高亮数取 `len(target_cubes)`（decision 里是区间，不能再 `min(int, len)`） | 否则 `min(list, int)` 直接 `TypeError` | 演示 h5 中 pick 子目标条数与声明一致（h7 端点 7 条、h5 端点 5 条） |
| `utils/statechange.py::highlight_obj` | **不改**：`disk_radius` 保持 0.05、不改同心环（C3） | 用户决定先不动 | —— |
| `tests/lightweight/test_v4_xhard_pickhighlight.py`（新增） | 9 项纯 CPU 结构测试（不起 sapien） | 必做验证第 4 条 | `9 passed` |

### 随机流位置（N5）说明

- **原三档**：一次随机调用都没有增删换序（xhard 判断全部挂在 `self.difficulty == "xhard"` 上），reset 探针逐字节零差异（第二节）。
- **xhard 自身**：`objects.highlight_count` 追加在原 `randperm` 之后，符合「追加在既有取值点之后」。但有两处无法追加到末尾：
  ① `objects.n_cubes` 决定方块循环长度，只能排在方块循环之前（按钮取值之后）；
  ② 「颜色任意」把原逐块 `randint(0,3)` 换成逐块 `torch.rand(3)`，与每块的位姿抽样交错。
  两者只影响 xhard 自己的随机流（xhard 在本轮之前不存在，没有既有产物可被平移），与计划 2.3 对 BinFill `dynamic` 的处理口径一致（「改变 xhard 自己的随机流，可接受；绝不能影响原三档」）。

## 二、原三档零差异（必做验证 1）

```bash
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks PickHighlight --out /tmp/g6_probe.json
# PROBE_DONE rows=9 ok=9
uv run --no-sync python -m scripts.parity.v4_reset_probe diff \
  /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/probe/base-13e.json /tmp/g6_probe.json
# RESET_REGRESSION=FAIL compared=9 diff=0 missing=135
```

`compared=9 diff=0`：PickHighlight 的 9 条（easy/medium/hard 各 3）逐字节相同；`FAIL` 仅来自 `missing=135`（其余 15 个环境不在本探针里，预期），diff 输出中不出现 PickHighlight。**判定：PASS。**

## 三、实测数字

### 3.1 xhard reset 冒烟（必做验证 2）

脚本：scratchpad `g6_xr.py`，seed `900000 + 101·i`，i=0..23，`difficulty="xhard"`，GPU 1。

- `XHARD_RESET ok=24/24 range_bad=0 fails={}`；
- spec_kind 24/24 为 `native-newvalue/1`；
- spawn 分布 `{8: 6, 9: 7, 10: 11}`，highlight 分布 `{5: 6, 6: 7, 7: 11}`，全部落在 `[8,10]`／`[5,7]`；
- 请求数＝实际数＝`len(all_cubes)` 24/24；`highlight_ids` 无重复且长度＝k 24/24；
- 颜色：全部 RGB 分量 ∈ [0,1]、alpha＝1；任务表长度＝`2k`（按钮 1 + pick k + 放下 k−1）24/24；
- 九个 (highlight, spawn) 组合在 24 条里全部出现：`(5,8)2 (5,9)3 (5,10)1 (6,8)2 (6,9)1 (6,10)4 (7,8)2 (7,9)3 (7,10)6`。

### 3.2 导出→回注一致性

scratchpad `g6_replay.py`：同 seed 先导出规格，再以 `native_episode_spec` 回注重建。`REPLAY ok=5/5`，
方块位姿、任务名、`highlight_ids` 全同，`mismatches=0`（方块数 9/10/9/8/10）。

### 3.3 spawn=10 放置压力（B5「只稳放 8~10」复核）

用外部配置把 xhard 收窄到 `highlight [7,7]`、`spawn [10,10]`，只做 make+reset，40 个 seed（`970000 + 101·i`）：
`STRESS_SPAWN10 ok=39/40 fails={'SceneGenerationError': 1}`（seed 970505：请求 10 实际 9）。
即 spawn=10 的 reset 级成功率约 97.5%，失败被显式判为该局生成失败、不再静默少块。

### 3.4 xhard 演示小样本（必做验证 3，本机 sm_89，仅调试不进判据）

入口 `scripts.parity.v4_demo_probe`，`--gpu 1`，episode 9（无 recovery）。端点组合用 `native_blocks(cls)` 导出后改 xhard 条目的
`{"decision","native"}` 配置收窄（`highlight_count.xhard=[h,h]`、`spawn_count.xhard=[s,s]`）。

| 组合 | 输出目录（`artifacts/newtask-v4/demo-probe/`，已 gitignore） | 演示成功 / 尝试 | 失败分类 | 步数（成功局） |
|---|---|---|---|---|
| 默认区间（随机） | `PickHighlight-g6` | 4 / 4 | — | 883 / 1077 / 1166 / 860（高亮 5 / 6 / 7 / 5） |
| highlight 7 × spawn 8 | `PickHighlight-g6-h7s8` | 2 / 2 | — | 1155 / 1146 |
| highlight 5 × spawn 10 | `PickHighlight-g6-h5s10` | 2 / 2 | — | 913 / 941 |
| highlight 5 × spawn 8 | `PickHighlight-g6-h5s8` | 2 / 2 | — | 891 / 814 |
| highlight 7 × spawn 10 | `PickHighlight-g6-h7s10` | 2 / 4 | `task:SceneGenerationError` ×2（seed 940101「请求 10 实际 8」、941101「请求 10 实际 9」，均为 reset 级放不满） | 1204 / 1192 |

- 读回演示 h5：pick 子目标条数与声明一致（h7 端点 7 条、h5 端点 5 条），subgoal 全部无 `which is` 后缀。
- **口径 14：四个端点组合演示均 ≥1 成功，没有「0 成功」组合**（h7×s8、h5×s10、h5×s8 均 2/2，h7×s10 为 2/4，四个端点都满足「至少 2 条成功」）；
  演示级失败全部是 spawn=10 的 reset 级放不满，没有规划／执行失败。
- 单条 70~132 s；合计 16 次尝试、14 条演示成功（本机）。

### 3.5 定向单测与既有测试（必做验证 4）

- `tests/lightweight/test_v4_xhard_pickhighlight.py`：`9 passed`。
- 涉及文件（`test_native_sampling_config` / `test_native_sampling_evidence` / `test_v4_decision_guard` / `test_sampling_config_split` /
  `test_TaskGoal` / `test_TaskGoalI_isList` / `test_train_split_parity` / `test_subgoal_ordinal_v4`）改动前：`15 failed, 193 passed`
  （13 项 `test_native_sampling_config` + 2 项 `test_TaskGoal`，均属已知 46 项基线失败）。
  改动后（另加本环境新测试与 `test_xhard_utils`；因与演示抢资源首轮超 600 s，拆两组重跑）：
  `test_train_split_parity` 单独 `12 passed`；其余 9 个文件 `16 failed, 194 passed`。失败集合＝改动前的 15 项
  **＋1 项 `test_sampling_config_split.py::test_snapshot_matches_source`**：`train_split_config.py extract --verify` 报
  v4 快照与源码不一致，逐键比对后差异**只有** `tasks.PickHighlight.decision.highlight_count.xhard`、`spawn_count.xhard`、
  `xhard` 三个新增 xhard 条目——这是源码新增 xhard 后的必然结果，按公共说明快照由主 agent 统一重导，本提交**不改也不提交**
  `scripts/configs/newtask-v4/sampling_config.json`；重导后该项应恢复通过。

## 四、计划外

1. **B5 的「稳放 8~10」在 spawn=10 端点并非 100%**：reset 压力 39/40（97.5%），演示探针 h7×s10 的 4 条里有 2 条 reset 即放不满（请求 10 实际 8／9）；合计 spawn=10 的 reset 失败 3/46（约 6.5%）。
   现在这种局会显式抛 `SceneGenerationError`（2.2④），生成链路按 reset 失败补抽（F2），不影响「能生成」判定，但 h7×s10 组合的尝试数会偏高。
2. **步数余量偏紧**：高亮 7 块的演示 1146~1204 步，`scripts/evaluation.py` 的 `max_steps=1300`，余量仅约 8~12%；高亮 5 块约 814~941 步。
   计划 2.12 未估算本环境步数，建议写回计划「步数逼近评估上限」风险行（与 ButtonUnmaskSwap、RouteStick 并列）。
3. **`_load_scene` 在 `gym.make` 阶段就执行**：xhard 放不满时 `SceneGenerationError` 从 `gym.make` 抛出（不是 `reset`），
   `v4_demo_probe` / 主入口按 `task:SceneGenerationError` 正确归类；自写脚本需把 `make` 放进 try。
4. **N5 的两处例外**（见第一节「随机流位置」）：`objects.n_cubes` 只能排在方块循环前；逐块颜色抽样替换在原位。只影响 xhard 自身随机流。
5. `test_sampling_config_split.py::test_snapshot_matches_source` 在快照重导前会因 PickHighlight 的 3 个新 xhard 条目失败（见 3.5），需主 agent 合并后统一重导 v4 快照。
6. 本 worktree 创建时 HEAD 为 `3a5951a`（不是公共说明写的 `00e2ef4`）；工作区干净，已 `git reset --hard 00e2ef4` 对齐后再开工。

## 五、待用户决策

1. **subgoal 的 `, which is {color}` 后缀**（计划 2.12 点名要处理、未给定做法）：任意 RGB 没有颜色名。代码先取最保守的
   `decision.xhard.subgoal_color_suffix = "omit"`（整段去掉，只剩序数，如 `pick up the third highlighted cube`），可经外部 sampling_config 覆盖该键，
   但目前只实现 `omit`，其余取值直接拒绝。可选方案：
   - (a) 维持 `omit`；
   - (b) 映射到最近的基本颜色名（需定色名表与距离度量，存在误标风险，如棕/橄榄色被叫成红/绿）；
   - (c) 输出数值（如 `rgb(0.57, 0.16, 0.12)`），语义可判但不自然。
2. **「颜色任意」的取值域**：现按 `[0,1]^3` 均匀 RGB、alpha 1 实现，未排除任何颜色。风险：近白色方块与白色高亮圆盘（C3 未改）、
   与桌面颜色相近的方块可能难以辨认。是否需要排除近白／近桌面色（以及阈值）请用户定；实施方未自行加限制。
3. **高亮 7 块的步数余量**（计划外第 2 条）：是否接受 1300 上限下约 8~12% 的余量，或需要额外对冲。

## 六、复现

```bash
ln -s /data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv .venv
uv run --no-sync python -m pytest tests/lightweight/test_v4_xhard_pickhighlight.py -q
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks PickHighlight --out /tmp/g6_probe.json
uv run --no-sync python -m scripts.parity.v4_demo_probe --task PickHighlight --n 4 --gpu 1 --out artifacts/newtask-v4/demo-probe/PickHighlight-g6
# 端点：导出 native_blocks(cls)，把 decision.highlight_count.xhard / spawn_count.xhard 改成 [h,h] / [s,s]，经 --sampling-config 传入
```
