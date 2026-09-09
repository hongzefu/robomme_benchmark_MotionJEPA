# scripts/ 使用说明（newtask-v2）

本目录是数据生成侧的全部入口。内容与结构按 [NEWTASK_V2_PLAN.md](../NEWTASK_V2_PLAN.md)
在分支 `newtask-v2` 上重建，提交 `10.0`–`10.4`。

**一句话：** 把 `BinFill` / `RouteStick` / `VideoUnmaskSwap` / `VideoRepick` 四个任务
**已经在用**的位置分布与参数候选，从散落在源码里的字面量提取成可检查、可显式传入的配置；
取值、抽样方式与整条执行链保持原版行为不变（已用逐位对拍验证，见文末）。

---

## 一、目录内容

```text
scripts/
├── generate_dataset_newseed.py     生成 + 配置提取 + 按需合并（三种入口模式，见第三节）
├── seed_layout.py                  seed 公式、难度循环、16 任务规范序（只依赖标准库）
├── configs/newtask-v2/
│   └── native_sampling.json        四任务的原版采样输入快照（冻结原值）
├── dataset_replay.py               原有回放脚本（未改动）
├── evaluation.py                   原有评估示例（未改动）
└── run_example.py                  原有运行示例（未改动）
```

目录下再无其它 `.py`。

---

## 二、本轮改了什么

### 2.1 生成侧从子目录平铺到这里

原来生成链路散在 `scripts/data-generation-newSeed/`、`scripts/data-generation/` 等目录里，
现在合并成上面两个文件，旧目录已删除（可从 Git 历史追溯）：

| 原位置 | 迁入内容 | 现落点 |
| --- | --- | --- |
| `data-generation-newSeed/generate_dataset_newseed.py` | 生成主体：进程池、worker、规划回退、任务执行、metadata、摘要 | `generate_dataset_newseed.py` |
| `data-generation-newSeed/seed_layout.py` | `SeedLayout`、`LAYOUTS`、`env_code`、难度循环 | `seed_layout.py` |
| `data-generation-newSeed/merge_episode_h5.py` | 合并逻辑 | 并入主文件的 `--merge-only` |
| `data-generation/validate_generated_dataset_contract.py` | 16 任务规范序、`parse_tasks`、轨迹末帧检查 | 拆进两个文件 |
| `data-generation/write_generation_report.py` | 原子写文件 | 主文件 |

生成行为、seed 公式、重试规则、记录格式**都没有改**，只是换了文件位置。

### 2.2 四个任务接入 `sampling_config`

每个任务模块顶层新增一份 `NATIVE_SAMPLING` 字典，里面是这个任务**原来就在用**的位置与
参数原值。它同时是两件事：

- 不传配置时的**运行默认值**（`_load_scene` 等处从实例副本读它）；
- `--extract-config` 的 **AST 提取目标**。

所以「提取到的原值」和「实际跑的默认值」永远是同一处，不存在两套真值。
难度字典仍只在类属性 `config_easy` / `config_medium` / `config_hard` 一处，不重复。

任务构造函数新增 `sampling_config=None` 形参，在任何随机数调用之前深拷贝一份实例专属副本。
**不传时，`gym.make` 的 kwargs 与原版逐字相同。**

`src/` 下只改了这四个任务加 `utils/object_generation.py`（给 `spawn_random_bin` 加了一个
`yaw_scale_deg=90.0`，默认值就是原来的内联常量，其它调用方不受影响），共 +336 / −55 行。

### 2.3 什么**没有**开放为可配

物体尺寸、材质、碰撞几何、相机、速度、交换时序、失败恢复、成功阈值都属于原实现，没有动。
`cube_half_size`（=0.02）是 `min_gap`、容器半边长、方块可行域收缩的共同来源，
被冻结为派生输入并记进快照，但**不开放为可配**。

源码里的若干旧问题（RouteStick 无条件覆盖难度、未使用的局部 generator、死代码、
与实际不符的注释等）按计划**原样保留、没有顺手修**，只在快照与计划里记录。

---

## 三、怎么用

主文件有三种模式，**互斥**，靠参数区分。所有命令在仓库根目录执行。

### 3.1 生成（默认模式）

```bash
# 最小例子：BinFill 一局
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/binfill-smoke \
  --env BinFill --episodes 1 --workers 1 --gpus 0 \
  --layout train --difficulty 100 --max-attempts 1

# 全量例子：16 任务 × 100 局，双卡
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/full-16x100 \
  --env all --episodes 100 --workers 20 --gpus 0,1 \
  --layout train --difficulty 211
```

加 `--sampling-config` 就是**显式传入原值配置**（结果与不传时逐位相同，已验证）：

```bash
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/binfill-explicit \
  --env BinFill --episodes 1 --workers 1 --gpus 0 --difficulty 100 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

配置只覆盖四个任务；`--env all` 时其余 12 个任务照原默认值生成，不报错。

**常用参数**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--output-dir` | 必填 | 输出目录，**必须在仓库内** |
| `--env` | `all` | `all` 或逗号分隔的任务名 |
| `--episodes` / `--episode-start` | `100` / `0` | 条数与起始 episode 号（接续生成用后者） |
| `--workers` / `--gpus` | `20` / `0` | 总 worker 数；`--gpus 0,1` 为每卡一个进程池 |
| `--layout` | `train` | seed 布局代：`train` / `test` / `val` / `heldout` |
| `--difficulty` | `211` | **三位数字的 easy/medium/hard 循环配额**，见下 |
| `--max-attempts` | `100` | 单个 episode 最多尝试几次 |
| `--max-tasks-per-child` | `8` | 每个池进程跑多少 job 后回收 |
| `--sampling-config` | 不传 | 显式传入四任务的采样输入 |

> ⚠️ `--difficulty` 是**配额**不是难度值。`211` = 每 4 局里 2 easy + 1 medium + 1 hard；
> `100` = 全 easy，`010` = 全 medium，`001` = 全 hard。它不是「难度 100」。

**seed 怎么来的**（`seed_layout.py`，不读表、由公式现算）：

```text
seed = offset + env_code × env_block + episode × 100 + attempt
```

`env_code` 是任务在 16 任务规范序里的 1-indexed 位置（BinFill=4、VideoUnmaskSwap=5、
VideoRepick=9、RouteStick=16）；train 布局是 `offset=0, env_block=1000`。
所以 BinFill 的 episode 0 首次尝试就是 `4000`，失败重试变 `4001`。

难度只由 `--difficulty` 的循环决定，**不进入 seed**。

### 3.2 核对／导出原值快照（`--extract-config`）

只读源码 AST，不加载仿真、不占 GPU、不采样。

```bash
# 只核对：快照必须与当前工作树源码逐项一致
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config

# 再加一层：与固定基线提交的原版取值对照
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8

# 不带 --check-config 就是重新导出快照
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json
```

第二条的作用值得单独说：它用另一套「旧式提取器」直接从**改造之前的源码**里还原 61 项
运算元（区间、常量、布尔、锚点等），与快照逐项比对。这是「接入过程一个原值都没改」的
自动化证据，而不是靠人眼比 diff。

### 3.3 合并逐 episode 文件（`--merge-only`）

生成期**不会**自动合并（避免体量翻倍、也让单条失败不牵连其它产物）。需要时单独跑：

```bash
uv run --no-sync python scripts/generate_dataset_newseed.py --merge-only \
  --input-dir artifacts/generated/binfill-smoke \
  --output-dir artifacts/generated/binfill-merged \
  --env BinFill
```

`--output-dir` 不给时默认写回 `--input-dir`；加 `--delete-source` 会在合并成功后删掉
逐 episode 源文件（默认保留；合并期间两份并存，需要双倍空间）。

源文件按生成期写出的 metadata 逐条定位，不 glob —— 目录里混有失败残留也不会被误吸。

---

## 四、生成路径与产物结构

一次生成的输出目录长这样：

```text
<--output-dir>/
├── hdf5_files/
│   └── BinFill_ep0_seed4000.h5              逐 episode 轨迹，文件名含 任务_ep号_seed
├── videos/
│   └── BinFill_ep0_seed4000_<难度与目标描述>.mp4
├── episode_results.jsonl                    边跑边写，一行一次 attempt
├── record_dataset_BinFill_metadata.json     每任务一份：episode / seed / difficulty
├── run_parameters.json                      本次运行的全部参数
├── run_summary.json                         成功数、放弃数、耗时、吞吐、峰值内存
└── sampling_config_used.json                仅在传了 --sampling-config 时才有
```

跑过 `--merge-only` 之后另有：

```text
<--output-dir 或 --input-dir>/
└── record_dataset_BinFill.h5                整任务合并文件
```

几点值得知道：

- **文件名天然唯一**（含任务、episode、seed），所以多 worker 共享同一个输出根不会打架。
- `episode_results.jsonl` 每行含 `ok` / `attempt` / `seed` / `failure_class` / `error_type` /
  各阶段耗时 / 峰值 RSS / 绑到哪张卡，中途崩溃也不丢已完成的部分。
- 失败的 attempt 不会留下空 h5（会被删掉），但 `FAILED_` 视频保留作为失败演进的证据。
- HDF5 内部结构：`episode_<n>/setup/`（seed、difficulty、任务目标、相机内参）与
  `episode_<n>/timestep_<i>/` 下的 `obs` / `action` / `info`。
- 产物很大：单局 BinFill 约 350 MB（h5）+ 11 MB（视频）。`artifacts/` 已整体 gitignore。

---

## 五、想改采样值时

初版只支持原来就存在的表达形式（区间、固定值、原抽取方式），**不支持**新增非连续候选、
权重或新拓扑。改 `native_sampling.json` 时会被这几道闸拦住：

1. **结构与类型逐项校验** —— 字段缺失、多出未知字段、类型或数组长度不对，直接报错。
2. **来源指纹校验** —— 生成时核对七份源码文件的 SHA-256；改过源码就必须重新
   `--extract-config` 导出快照，否则拒绝运行。
3. **表达形式约束** —— JSON 里只存源码里真实出现的运算元（如 `scale` / `subtract` /
   `base_position`），**不允许**折算成 `[min, max]` 区间：
   `0.15 + (u*0.2 - 0.2)` 与 `-0.05 + u*0.2` 数学上等价，但 float64 位模式不同。

另外，配置值一律以 Python 标量参与运算，不要包成 `torch.tensor` —— 那会把下游的
float32 路径提升成 float64。

---

## 六、这些改动验证到什么程度

三路对拍：**A** = 固定原版（基线提交 `94449db` 的 detached worktree）、
**B** = 新版不传配置、**C** = 新版显式传原值配置。比较口径是**全字段、逐元素、
浮点按位模式、不设容差**。

| 项目 | 结论 |
| --- | --- |
| HDF5 产物内容 | 15 格全部通过，差异 0；合并产物三路也是 0 差异 |
| 随机流（调用序列、上下界、流状态） | 15 格通过 |
| 内部状态与物体事件 | 15 格通过 |
| 同一 worker 连续生成互不污染 | 两路通过 |
| 关键帧目视 | 9 格通过、6 格待目视（354 张关键帧机检全部一致） |
| 其余 12 任务生成能力 | `--env all` 加配置，16/16 成功 |

完整报告、逐格数据与轻量证据在
[docs/validation/newtask-v2/](../docs/validation/newtask-v2/README.md)，
交付清单与**未覆盖项**在
[DELIVERY.md](../docs/validation/newtask-v2/DELIVERY.md)（第十节）。
