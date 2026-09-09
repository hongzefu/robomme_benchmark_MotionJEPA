# newtask-v2 交付清单（方案第六步）

本页保留此前 schema 2 脚本平铺与清理轮次的历史记录。schema 3 对象／动作冻结和
完整重跑的最新结果见 [20260909-actions-v3](20260909-actions-v3/README.md)，
不要将本页历史待验项当作本轮状态。

对应 [NEWTASK_V2_PLAN.md](../../../NEWTASK_V2_PLAN.md) 第八节第六步要求的交付内容。
分支 `newtask-v2`，从固定基线 `94449db0a068a6b454b55a13ebd48f0394d89cc8` 重建。

## 一、冻结配置

[scripts/configs/newtask-v2/native_sampling.json](../../../scripts/configs/newtask-v2/native_sampling.json)，
schema 2，含四任务的 12 份难度字典、额外构造参数、位置输入、原始锚点、单位、
`native_semantics` 语义说明与七份来源文件的 SHA-256。

两级防漂移检查（都不加载仿真）：

```bash
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8
```

第一条比对当前工作树源码；第二条用**旧式提取器**从未改动的基线内联源码还原 **61 项操作元**，
与快照逐项一致 —— 这是「接入过程没有改动任何原版取值」的自动化证据。

## 二、与固定基线的最小 diff

`src/` 下**只改了五个文件**，其余源码零改动：

| 文件 | 增 | 删 |
| --- | ---: | ---: |
| `src/robomme/robomme_env/BinFill.py` | 100 | 14 |
| `src/robomme/robomme_env/RouteStick.py` | 63 | 8 |
| `src/robomme/robomme_env/VideoRepick.py` | 106 | 20 |
| `src/robomme/robomme_env/VideoUnmaskSwap.py` | 63 | 11 |
| `src/robomme/robomme_env/utils/object_generation.py` | 4 | 2 |

四个任务的增量绝大部分是模块级 `NATIVE_SAMPLING` 原值字典与 `_resolve_sampling_config`；
`object_generation.py` 只加了 `spawn_random_bin` 的 `yaw_scale_deg=90.0`（默认值即原内联常量），
另外三个范围外调用方（`ButtonUnmask`、`ButtonUnmaskSwap`、`VideoUnmask`）照原样调用、行为不变。

`scripts/generate_dataset_newseed.py`（1954 行）与 `scripts/seed_layout.py`（153 行）
是从旧目录迁出并合并了必要函数后的平铺文件，对基线是「新增」。

## 三、最终五脚本清单

```text
scripts/
  dataset_replay.py               原有回放脚本，保留、未改
  evaluation.py                   原有评估示例，保留、未改
  run_example.py                  原有运行示例，保留、未改
  generate_dataset_newseed.py     生成 + 配置提取 + 按需合并（三种入口模式）
  seed_layout.py                  seed / 难度 / 16 任务规范序，只依赖标准库
  configs/newtask-v2/native_sampling.json
```

`scripts/` 下再无其它 `.py`；产品路径不 import `tests/` 下任何模块。

## 四、函数迁入对应表

| 旧来源（均已删除，可从 Git 历史追溯） | 迁入内容 | 落点 |
| --- | --- | --- |
| `data-generation/validate_generated_dataset_contract.py` | `ALL_TASKS`（16 任务规范序）、`MAX_EPISODES=100`、`DatasetContractError`、`parse_tasks` | `scripts/seed_layout.py` |
| 同一模块 | `TIMESTEP_RE`、`timestep_indices`、`inspect_episode_terminal`（连续 timestep、`setup` 排除、末帧严格布尔） | `scripts/generate_dataset_newseed.py` |
| `data-generation/write_generation_report.py` | `write_text_atomic` | 同上 |
| `data-generation-newSeed/merge_episode_h5.py` | `MergeError`、`_sources`、`merge_task` | 同上，由 `--merge-only` 分支调用 |
| `data-generation-newSeed/seed_layout.py` | `SeedLayout`、`LAYOUTS`、`env_code`、`get_layout`、`parse_difficulty_ratio`、`difficulty_for`、`plan_episodes`、`EPISODE_STRIDE`、`MAX_ATTEMPTS` | `scripts/seed_layout.py`（原样保留） |
| `data-generation-newSeed/generate_dataset_newseed.py` | `EpisodeJob`、进程池与 worker、规划回退、任务执行、metadata、摘要 | `scripts/generate_dataset_newseed.py`（原样保留，仅新增 `sampling_config` 字段与一处 kwarg） |
| —（本轮新增） | 配置 AST 提取、跨文件交叉核对、旧式提取器、校验、按任务切片 | 同上 |

## 五、更新后的调用链

```text
scripts/generate_dataset_newseed.py::main()
  |
  +-- --extract-config <JSON>  [--check-config] [--source-ref <ref>]
  |      `--> 读工作树源码 AST（可选另读某提交）-> 提取原值 -> 写出或核对 -> 返回
  |             +--> 四任务模块顶层 NATIVE_SAMPLING + 类属性 config_easy/medium/hard
  |             +--> 跨文件交叉核对：build_button.randomize_range、spawn_random_bin.yaw_scale_deg
  |             `--> 七份来源文件 SHA-256
  |
  +-- --merge-only --input-dir ...
  |      `--> _sources() -> merge_task()（临时 HDF5 + 原子替换）-> 返回
  |
  `-- 常规生成
         +--> _args() / _ensure_layout() / _prepare_output() / parse_tasks() / get_layout()
         +--> parse_difficulty_ratio("211") -> (easy, easy, medium, hard)
         +--> [可选] load_sampling_config()   只读、只校验、只复制；零随机数、不导入仿真
         |       `--> 结构与类型逐项核对 + 七份来源 SHA-256 核对 -> 按任务切片
         +--> seed 天花板护栏
         +--> 逐 episode：difficulty_for() + layout.seed(task, episode, 0) -> EpisodeJob
         |       `--> 每个 job 带一份 deepcopy 的本任务配置（不传配置时为 None）
         +--> 原子写 run_parameters.json（+ sampling_config_used.json）
         |
         +--> _run_jobs()  每张 GPU 一个 spawn 进程池
         |      `--> _worker(job)
         |             +--> gym.make(task, obs_mode, control_mode, render_mode, reward_mode,
         |             |             seed=job.seed, difficulty=job.difficulty,
         |             |             [robomme_failure_recovery=...], [sampling_config=job.sampling_config])
         |             |      `--> 原任务 __init__(seed=..., difficulty=..., sampling_config=None)
         |             |             +--> _resolve_sampling_config()  深拷贝，早于任何随机数与 super()
         |             |             +--> 原难度解析、参数抽样（读实例副本）、随机流初始化
         |             |             `--> BaseEnv.__init__() -> 内部 reset(seed=2022, reconfigure=True)
         |             |                    +--> _load_scene()（读实例副本）
         |             |                    `--> _initialize_episode()  第一次
         |             +--> RobommeRecordWrapper(...) -> reset()  -> _initialize_episode() 第二次
         |             +--> 原规划器（screw×3 -> RRTStar×3 回退）
         |             +--> _execute_tasks() 按原 task_list 顺序执行
         |             `--> finally close() -> _raw_summary() 检查末帧契约
         |
         +--> 父进程沿用原重试规则（MAX_NON_TASK_STRIKES=3、池崩溃插队、原 seed 公式）
         `--> _write_metadata() + run_summary.json
```

`seed` 仍是 `gym.make` 的 kwarg、被任务 `__init__` 的显式形参接住；`record_env.reset()` 不传 seed。
`sampling_config` 是**唯一**新增的 kwarg，且只在显式传了 `--sampling-config` 时才出现，
不传时 `gym.make` 的 kwargs 与原版逐字相同。

## 六、15 格覆盖矩阵与 `rrt_fallback_count`

详见 [20260908T2255Z-parity15-3804e87/README.md](20260908T2255Z-parity15-3804e87/README.md) 第 4 节。
**15 格的 A1 与 A2 全部 `rrt_fallback_count = 0`**，即 30 次原版运行一次都没触发
screw→RRTStar 回退，全部落在「原版逐位可复现」的适用范围内，未动用 4.0 的容差退出路径。

| 任务 | 格 | 结论 |
| --- | --- | --- |
| `BinFill` | easy/medium/hard × `dynamic=True/False`，6 格 | ②③④ 通过；① 待目视 |
| `RouteStick` | easy/medium/hard，3 格 | ②③④ 通过；① 通过 |
| `VideoUnmaskSwap` | easy/medium/hard，3 格 | ②③④ 通过；① 通过 |
| `VideoRepick` | easy/medium/hard（hard 为原五轮循环共 15 块），3 格 | ②③④ 通过；① 通过 |

受阻并已补足 1 项：`BinFill-medium-dynamicTrue` 原 ep0（seed 4000）原版首次尝试即失败，
换同格 ep2（seed 4200）补足，原记录保留。

## 七、五项对拍的结论与证据

| 编号 | 结论 | 证据 |
| --- | --- | --- |
| ① 关键帧目视 | **9 格通过、6 格待目视**。354 个关键帧全部出图，差分 `max_abs`=0、非零像素 0、逐帧 SHA-256 三路一致 708/708；目视 217/354 | [visual_inspection.md](20260908T2255Z-parity15-3804e87/visual_inspection.md)、[keyframe_index.json](20260908T2255Z-parity15-3804e87/keyframe_index.json) |
| ② 状态与事件对照 | 15 格通过。边界 4 个/格（含两次 `_initialize_episode` 分别记录）、事件 748–17014 条/格、逐步状态 652–1886 条/格 | [result.json](20260908T2255Z-parity15-3804e87/result.json)、`evidence/` |
| ③ HDF5 全字段 | 15 格通过，差异全为 0；**原始与合并文件都比过**：A 路用基线的原合并脚本、B/C 用平铺主文件的 `--merge-only`，合并产物三路 0 差异 | 同上 + `artifacts/logs/merge-check.log` |
| ④ 随机流 | 15 格通过。覆盖任务级 `torch.Generator`（局部与实例）、全局 numpy 流、全局 torch 流；拒绝采样保留全部尝试 | 同上 |
| ⑤ 连续 worker 隔离 | 两路通过。同一 worker 甲→乙→甲，逐局与独立运行 0 差异；类级与父进程配置散列前后不变 | [worker_isolation.json](20260908T2255Z-parity15-3804e87/worker_isolation.json) |

补充的定向检查（第五步）：attempt 重试分支三路一致且产物 0 差异；
`--env all` 加 `--sampling-config` 下 16 任务各一局全部成功；
清理后抽样复验八项 0 差异。详见
[20260909T1441Z-postclean/README.md](20260909T1441Z-postclean/README.md)。

## 八、真实命令、会话与退出码

| 阶段 | tmux 会话 | 退出码 | 日志 |
| --- | --- | --- | --- |
| 15 格 × 四路首轮（2229.3 s） | `parity15` | 1（受阻格） | `artifacts/logs/parity/<run>.log` |
| RouteStick 三格重跑（1079.5 s） | `parityfix` / `parityfix2` | 0 | `<run>-rerun*.log` |
| 替补扫描 + 替补格四路 | `parityfix` / 后台 | 0 | 同上 |
| ⑤ 连续 worker 两路 | 后台 | 0 | `worker-isolation-<run>.log` |
| 打包 + ⑤ 比较 + 替补格 A1 | `packrun` / `fix3` | 0 | `<run>-pack.log`、`<run>-fix3.log` |
| ① 全量出图（354 张） | `keyframes3` | 0 | `<run>-keyframes-all.log` |
| 清理后验证五阶段 | `postclean` | 0 | `postclean-<run>.log` |
| 清理前后逐位比较 | `pcmp` | 0 | `postclean-compare.log` |
| ③.4 合并比较 | `mergechk` | 0 | `merge-check.log` |

完整命令见两份实测报告的第 3 节。

## 九、轻量证据索引

| 位置 | 内容 | 体积 |
| --- | --- | --- |
| `docs/validation/newtask-v2/20260908T2255Z-parity15-3804e87/` | 15 格实测报告、目视记录、result / manifest / keyframe_index / worker_isolation、去重证据 30 份（120 处引用） | 约 1.3 MB |
| `docs/validation/newtask-v2/20260909T1441Z-postclean/` | 清理后复验报告 | 约 8 KB |
| `docs/validation/newtask-v2/legacy-measurements.md` | 旧链路退出前的历史实测摘录 | 约 4 KB |

完整 HDF5（约 20 GB）、视频、原始逐步证据（21 MB gzip）与 354 张关键帧 PNG（74 MB）
全部留在 `artifacts/`，不入 Git。

**能力边界：** 轻量证据能判断内容是否相同，并把首个分歧定位到字段／记录、
大段时定位到一个 64 条的块、HDF5 定位到具体哪一帧；**不能还原画面、不能算像素差幅度**。
需要展开时按冻结命令重跑，或从 `artifacts/` 按散列取回 PNG。轻量包不是完整 HDF5 备份。

离线复验（不碰 `artifacts/`、不加载仿真、不占 GPU）由
`tests/lightweight/test_native_sampling_evidence.py` 的三项测试覆盖：
证据包自洽、只用 Git 里的轻量证据重新推出四路一致的结论、以及篡改引用后必须失败的反例。

## 十、全部失败、受阻与未覆盖项

**失败**：无。15 格四对比较、⑤ 两路、清理后抽样复验、重试分支、合并产物比较全部 0 差异。

**受阻并已补足**：`BinFill-medium-dynamicTrue` 原 ep0（原版首次尝试即失败），换 ep2 补足，
原记录保留在 `artifacts/parity/<run>/BinFill-medium-dynamicTrue-blocked-ep0/`
与 `cases.json` 的 `blocked_original` 字段。

**未覆盖（如实登记，不计入通过）**：

1. **① 的 BinFill 六格目视**：138 张关键帧只目视了 1 张，其余 137 张仅有机检结论。
   原因是负责该组的目视 agent 因会话额度中断，随后用户要求停止目视。
2. **RRT\* 回退局**：30 次原版运行一次都没触发回退，因此 4.0 的「受阻-规划器非确定」
   容差退出路径**未被启用、也未被验证**。
3. **其余 11 格的清理后重跑**：按方案的抽样复验口径沿用清理前证据（源码版本 `1f51108`）。
4. **③.4 的覆盖范围**：合并产物只在 `BinFill-easy-dynamicTrue` 一格上比过，未逐格做。
5. 观察器本身的开销与副作用只在 BinFill 一格上做过带／不带观察器的校准（约 4%）。

## 十一、本次验收不包含的内容

按方案，首版验收只覆盖「原值显式注入、原链保持、平铺清理」。**不包含**：
修改分布、扩大候选、新增非连续候选或权重、新拓扑，以及全量数据生成。
