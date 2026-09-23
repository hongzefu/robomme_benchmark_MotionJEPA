# V4 步 3b：BinFill 的 xhard（clutter、12 块、3 色、put_in [5,7]、dynamic 固定 False）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`），组名 g3，本机 GPU 0。录像器未改（`RECORDER_FROZEN=PASS`）。
> 依据：计划 2.3、2.21 BinFill 简图、1.3 的 B1 / D1 / D6 / H2 / E2、第二部分一「步 3 BinFill」行。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `src/robomme/robomme_env/BinFill.py::BinFill.config_xhard`（新增，进 `configs`） | `{color 3, spawn_cubes [12,12], put_in_color [2,3], put_in_numbers [5,7], layout_mode "clutter"}`；`put_in_color` 沿用 hard 的 `[2,3]`（计划 2.3：native 规则不改） | 计划 1.2「全部clutter, 12, color 3 个, put_in_number [5,7]」；2.1 派生自 hard | `test_v4_xhard_binfill.py::test_xhard_values_match_plan`；xhard reset 冒烟 24/24 |
| `BinFill.py::_native_decision` | 每档条目由 `_entry(cfg)` 生成；**只有带 `layout_mode` 的档（即 xhard）** 才多输出 `layout_mode`；顶层 `layout_mode: "native_dynamic"` 不动 | 公共说明：xhard 专属 decision 键放在名为 `xhard` 的子键下，守卫剥掉 xhard 子树后原三档可见部分逐字不变 | `test_native_decision_without_xhard_is_original`（剥掉 xhard 后与 00e2ef4 逐字相同，原三档条目键集合不变） |
| `BinFill.py::XHARD_LAYOUT_DYNAMIC`（新增模块常量） | `{"clutter": False}`：xhard 已实现的摆放模式 → 是否动态出现 | D6：clutter＝全部方块开局在场，dynamic 固定 False；表外模式直接拒绝、不静默回退 | `test_guard_rejects_unimplemented_xhard_layout` |
| `BinFill.py::_resolve_sampling_config` | 顶层硬守卫 `layout_mode != "native_dynamic" ⇒ raise` **原样保留**（管原三档）；新增一道只看 `decision.configs.xhard.layout_mode` 的守卫，只放行 `XHARD_LAYOUT_DYNAMIC` 里的模式 | 计划「放开 layout_mode 守卫，仅对 xhard/clutter」 | 守卫放行端点收窄 `[5,5]`/`[7,7]`；拒绝 xhard `native_dynamic`/`grid`/`None`、拒绝申报外键 `configs.xhard.dynamic`、拒绝改 hard、拒绝把顶层改成 clutter；无 xhard 条目的旧快照照旧放行 |
| `BinFill.py::BinFill.__init__`（dynamic 取值点） | 新增 `self.difficulty == "xhard"` 分支：**不抽**那次 `torch.randint`，`self.dynamic = spec.value("layout.dynamic", XHARD_LAYOUT_DYNAMIC[mode], decision_key="configs.xhard.layout_mode")`，并 `record("layout.mode", mode)`；原三档走 `elif` 原分支，那一行逐字未动 | D6；`dynamic` 是播种后第一次抽样。xhard 是新档，其自身随机流整体前移一位可接受（公共说明授权由实施方定）；照抽一次只会留下一个无意义的占位抽样 | reset 探针原三档 9 行 diff=0；xhard 冒烟 `dyn=False`、规格 `layout.mode=clutter`、`layout.dynamic=false` |
| `BinFill.py::_load_scene`（`objects.spawn_numbers` / `objects.target_numbers` 取值点） | 追加 `decision_key=f"configs.{难度}.spawn_cubes"` / `"...put_in_numbers"` | 新值回注出现不等时可归因；原值模式 `decision_key` 被忽略（`SpecRecorder._mismatch` 只在 newvalue 下写） | reset 探针原三档 diff=0 |
| `BinFill.py::_load_scene`（方块生成循环） | `min_gap` 外提：xhard 读 `positions.cubes.min_gap_value`（0.02），原三档仍用调用点原来的 `self.cube_half_size` | 第二部分一「min_gap 从调用点字面量外提」；B1 间距不动（两值相等） | `test_xhard_values_match_plan` 锁 `min_gap_value == 0.02`；冒烟全部 12 块放下 |
| `BinFill.py::_load_scene`（生成循环之后，D1 前半） | 仅 xhard：`record("objects.spawn_requested")` / `record("objects.spawn_actual")`，不等即抛 `SceneGenerationError`（带逐色 实际/请求）；原三档的 `except RuntimeError: logger.debug` 原样保留 | 2.2④ 静默截断；D1 只在 xhard 修（H2/N12）。`SceneGenerationError` 是 `RuntimeError` 子类，所以放在循环外抛，不会被逐块的 `except RuntimeError` 吞掉 | 冒烟 24/24 规格里 `spawn_requested=spawn_actual=12` |
| `BinFill.py::_initialize_episode`（D1 后半） | 仅 xhard：某色 `len(cube_collection) < target_number` 时抛 `SceneGenerationError`，不再走到 `cube_collection[i]` 的 `IndexError` | D1 | 前半已保证不缺块，此处为兜底；原三档路径不进该 `if` |
| `scripts/generate_dataset_newseed.py::SAMPLING_SOURCES` / `SAMPLING_OPERAND_PATHS` / `extract_native_sampling` 注释 | BinFill 锚点加 `config_xhard`；操作元 `parameters.BinFill.configs` 整块比对改为 easy/medium/hard 三条（与 RouteStick 等同一写法） | 否则新增的 xhard 档会被 `--source-ref` 的原版操作元比对误判为「原版不一致」；计划 2.3 末条提到 `SAMPLING_OPERAND_PATHS` 冻结了整块 | 轻量测试见 3.4 |
| `tests/lightweight/test_v4_xhard_binfill.py`（新增） | 11 项纯 CPU 结构测试（不起 sapien 场景） | 必做验证 4 | 11 passed（3.2 s） |

**未改**：录像器、链路甲、`NEWTASK_RELEASE_V4_PLAN.md`、`scripts/configs/**`（v4 快照由主 agent 统一重导）。

## 二、「全部 clutter」的解读（结合源码）

源码里 BinFill 的原摆放模式 `native_dynamic`：12 块照常一次性散布在方块区里，`dynamic=True` 时 `step()` 用
`lift_and_drop_objects_back_to_original` 把每色第 2 块起临时抬走、按 `idx*100` 步陆续落回——即**动态出现**；
`dynamic=False` 时全部方块开局就在桌上。全仓 grep `clutter` 在 BinFill 只命中一行注释，没有别的「clutter 摆放」实现。

因此本次把 `clutter` 实现为：**全部方块开局即在场（dynamic 固定 False，D6）＋在原方块区、原间距里一次性散布 12 块
（B1）＋放不满即判失败（D1）**。它和「hard 抽到 dynamic=False」的差别只在块数固定 12、投入数 [5,7] 与失败显式化——
这是 B1（区域与间距不动）直接推出的结果，**若用户心目中的 clutter 还包含「更密／更挤／贴靠」的含义，需另行定数**（见第六节）。

## 三、实测数字

### 3.1 原三档 reset 零差异（必做 1）

```bash
CUDA_VISIBLE_DEVICES=0 uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks BinFill --out /tmp/g3_probe.json
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json /tmp/g3_probe.json
# RESET_REGRESSION=FAIL compared=9 diff=0 missing=135   ← missing 全是其余 15 个环境（预期）
# diff 输出中 BinFill 出现 0 次
```

判定：**BinFill 9 行（easy/medium/hard 各 3）diff=0，PASS**。

### 3.2 xhard reset 冒烟（必做 2）

脚本（scratchpad，未入库）对 seed `900000 + 101·i`，i=0..23 只 `make → reset`，逐条核对：块数、逐色生成数之和、
投入总数 ∈ [5,7]、出现颜色数 = 3、逐色 spawn ≥ target、`dynamic is False`、全部方块中心在方块区
`x∈[-0.3,0.1]、y∈[-0.25,0.25]` 内、`spec_kind == native-newvalue/1`、规格 `spawn_requested == spawn_actual == 12`、
`layout.mode == clutter`、`layout.dynamic == false`。

- `XHARD_RESET ok=24/24 fails={} bad_checks=[]`（24 条全部通过全部核对项）
- 投入总数分布 `{5: 10, 6: 9, 7: 5}`；`put_in_color` 分布 `{2: 15, 3: 9}`
- 单色最大投入数 5（本样本）；任务表长度 11/13/15（= 2×投入数 + 1）
- 方块坐标实测范围 x ∈ [-0.279, 0.080]、y ∈ [-0.230, 0.229]

### 3.3 xhard 演示小样本（必做 3，口径 14 端点）

`v4_demo_probe`（`--episode 9` 无 recovery，本机 sm_89、GPU 0；三路曾同时跑在同一张卡上）：

| 组合 | 命令要点 | seed | 演示成功 | 失败分类 |
|---|---|---|---|---|
| 声明全范围 `put_in [5,7]` | `--n 4` | 910000/910101/910202/910303 | **4/4** | — |
| 端点 `put_in [5,5]` | `--sampling-config` 收窄 | 930000/930101 | **2/2** | — |
| 端点 `put_in [7,7]` | `--sampling-config` 收窄 | 920000/920101 | **1/2** | `task:DatasetGenerationError`（环境报告失败） |
| 端点 `put_in [7,7]` 追加 | 同上 | 940000/940101 | **2/2**（156 s / 133 s） | — |

- 全范围 4 条的任务文本：投 6/5/7/6 块（例：`put one red cube three blue cubes and three green cubes into the bin`），
  时长 970~1393 步、单条 64~90 s。
- `put_in 7` 失败那条（seed 920000，「三红四蓝」）：第 7 次抓取（`pick up the fourth blue cube`，task_index 12）前
  连续 3 次 `screw plan failed`，随后环境报失败；末帧可见剩余蓝块与红块贴靠在一起。归类：**clutter 下相邻贴靠方块的抓取规划失败**。
- 口径 14：本环境 xhard 声明里唯一可变的参数是 `put_in_numbers ∈ [5,7]`（spawn 固定 12、color 固定 3、layout 固定 clutter），
  两端点演示级均 **>0 成功**（`[5,5]` 2/2，`[7,7]` 3/4），未出现 0 成功组合。合计 xhard 演示 **9/10**。

输出目录（gitignored）：`artifacts/newtask-v4/demo-probe/BinFill-g3{,-putin5,-putin7,-putin7b}/`（每条 h5 约 860 MB）。

### 3.4 测试（必做 4）

- `tests/lightweight/test_v4_xhard_binfill.py`：11 passed（3.2 s）。
- 轻量全量（`tests/lightweight`）本机此时有多组并行占用，两次都超过 590 s 被 `timeout` 杀掉（基线约 123 s），**未拿到全量结果**；
  改跑与本次改动相关的 10 个文件：`test_native_sampling_config` / `test_v4_decision_guard` / `test_sampling_config_split` /
  `test_episode_spec_recorder` / `test_episode_specs` / `test_binfill_demo_duplicate` / `test_subgoal_ordinal_v4` /
  `test_xhard_utils` / `test_v4_xhard_binfill` / `test_episode_action_sampling` ⇒ **34 failed / 137 passed / 4 skipped（13.8 s）**。
  - `test_episode_action_sampling` 20 项、`test_native_sampling_config` 13 项＝已知基线失败；后者把两份改动文件临时换回
    `00e2ef4` 原文重跑，失败集合逐条相同（13 条同名）。
  - **新增 1 项**：`test_sampling_config_split::test_snapshot_matches_source`，报「`scripts/configs/newtask-v4/sampling_config.json`
    与源码提取结果不一致」——BinFill 加了 `config_xhard` 且源码 sha256 变了，快照必然过期；按公共说明快照由主 agent 统一重导、
    本组不提交，重导后即恢复。

## 四、计划外

1. **worktree 起点不对**：分配给本组的 worktree 起初停在 `3a5951a`（远早于 `00e2ef4`，连 `utils/xhard.py` 都没有）；
   工作区干净，已 `git checkout -B g3-binfill-v4 00e2ef4` 后再开工。
2. **计划 2.3 表把 `layout_mode` 写成 `decision.layout_mode`（顶层）**：顶层是一个标量，被原三档共用、且守卫要求它等于
   `native_dynamic`；按公共说明改放在 `decision.configs.xhard.layout_mode`，顶层原值不动。计划表的字段路径需主 agent 同步。
3. **`positions.cubes.min_gap` 字符串与 `min_gap_value`**：计划说 `min_gap` 运行时不被读；现在 xhard 读 `min_gap_value`（0.02），
   原三档仍读调用点字面量 `self.cube_half_size`（同为 0.02）。今后若有人改 `min_gap_value` 只会影响 xhard。
4. **既有配额规则的一个性质**：`put_in_color=2` 时投入数逐块随机分给 2 色、不保证每色 ≥1，实测出现 `tgt=[0,0,5]`（名义 2 色、
   实际只投 1 色）。这是 hard 原规则（计划 2.3「规则不改」），xhard 照搬，未改。
5. **v4 快照必然与源码不符**：BinFill 新增 `config_xhard` 后，`scripts/configs/newtask-v4/sampling_config.json` 里
   BinFill 的 `configs` 与源码 sha256 都会过期，依赖该快照的测试会报红，需主 agent 统一重导（按约定本组不提交快照）。
   实测即 `test_sampling_config_split::test_snapshot_matches_source` 这 1 项。
6. **轻量全量跑不完**：本机负载下两次超过 590 s，改跑相关子集（见 3.4）；主 agent 合并后建议在空闲时补一次全量。

## 五、当前状态

- BinFill xhard 已可 `difficulty="xhard"` 直接生成：reset 24/24，演示小样本见 3.3。
- 原三档 reset 零差异；H2/N5 满足（xhard 分支全部挂在 `self.difficulty == "xhard"` 下，原三档随机调用序列未增减、未换序）。

## 六、待用户决策

1. **「全部 clutter」是否只等于「全部开局在场（dynamic=False）＋原区域原间距散布 12 块」**（本次实现）。若还要求更密的
   摆放（缩小区域或间距、刻意贴靠），与 B1「区域与间距不动」冲突，需用户明确；代码已把摆放模式做成
   `decision.configs.xhard.layout_mode` 表驱动（`XHARD_LAYOUT_DYNAMIC`），新增模式只需加表项与摆放分支。
2. **`put_in_color` 在 xhard 是否仍取 hard 的 `[2,3]`**：用户原文只给了 color 3，未提投入颜色数；本次按计划 2.3「规则不改」沿用 `[2,3]`
   （属 native 块，可由外部配置覆盖）。
