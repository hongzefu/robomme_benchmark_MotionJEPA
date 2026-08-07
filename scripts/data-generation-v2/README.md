# RoboMME 数据生成 v2：带 2D flow ground truth

本目录是 `scripts/data-generation/`（v1，已冻结）的演进版本，在保持既有生成链路**逐位不变**的前提下，
新增了一件事：

> 从 ManiSkill 仿真本身取 3D 物体的 ground-truth 位置，反投影到 `base_camera` 相机平面，
> 得到**稀疏逐物体的 2D flow ground truth**，随数据生成同步写进 HDF5。

flow 全部来自仿真真值。链路里**不存在任何从像素估计的成分**——没有光流网络、没有特征点匹配。
一旦掺进估计量，这份数据集的全部价值就没了。

## 与 v1 的差别

| 方面 | v1 | v2 |
|---|---|---|
| RecordWrapper | `RobommeRecordWrapper` | `RobommeRecordWrapperV2`（**薄子类，父类零改动**） |
| flow 字段 | 无 | `setup/flow_*` 与 `timestep_<k>/flow/` |
| 参考数据路径 | 硬编码仓库内 `data/robomme_data_h5` | 新增 `--reference-root` |
| 规划器兜底 | 不可观测 | 报告里记录 `planner_fallback` 计数 |
| 参考校验 | 强制 | 新增 `--no-reference-validation` 可跳过 |

**「只增不改」是这条链路的生命线**：新增 flow 不得改变任何既有 h5 内容，`joint_action` 必须逐位一致。
v2 之所以做成薄子类而不是复制重构，正是为了让这一点在结构上就成立——父类 `RecordWrapper.py` 一个字都
没动，flow 全部挂在 `super()` 调用之后。

## 目录内容

| 文件 | 作用 |
|---|---|
| `generate_dataset.py` | 生成唯一入口：生成 → 合并 → 契约校验 → 与参考对拍 → 写报告 |
| `record_wrapper_v2.py` | 薄子类，只 override `reset` / `step` / `close`，其余全部调用父类原函数 |
| `flow_tracker.py` | 物体枚举（黑名单）、逐帧投影、可见性/遮挡、位移计算、h5 写入 |
| `validate_generated_dataset_contract.py` | 契约校验（结构 / seed / difficulty / joint_action shape 与 dtype） |
| `compare_joint_actions.py` | 与官方参考逐元素对拍 `joint_action` |
| `write_generation_report.py` | 报告写入（也可只读复核） |
| `verify_flow_math.py` | **六条判据**验证 flow 与 3D 真值严格一一对应 |
| `verify_joint_action_bitexact.py` | **自对拍**：验证开 flow 后除 flow 外逐位不变 |
| `replay_flow_video.py` | 渲染带 flow 箭头的对照视频 |
| `fetch_reference_h5.py` | 从 HuggingFace 补齐官方参考 h5 |

## 常用命令

从仓库根目录执行。输出目录必须在仓库内，且不存在或为空。

### 单任务单 episode 冒烟

```bash
env CUDA_VISIBLE_DEVICES=0 uv run --locked scripts/data-generation-v2/generate_dataset.py \
  --output-dir artifacts/generated/flow-smoke \
  --env ButtonUnmask --episodes 1 --workers 1 --gpus 0 \
  --reference-root /data/hongzefu/robomme_data_h5 --flow
```

### 16 任务 × episode_0

参考数据不覆盖全部 16 个任务时加 `--no-reference-validation`，生成阶段本身与参考数据无关，
跳过的只是末尾那次对拍。`--workers 1` 用来消除多进程抢同一张卡带来的调度扰动。

```bash
env CUDA_VISIBLE_DEVICES=0 uv run --locked scripts/data-generation-v2/generate_dataset.py \
  --output-dir artifacts/generated/flow-16env \
  --env all --episodes 1 --workers 1 --gpus 0 \
  --reference-root /data/hongzefu/robomme_data_h5 --flow --no-reference-validation
```

⚠ `--gpus` 只接受 `0`（脚本内硬编码），传其它值直接报错。
⚠ 超过 5 分钟的生成一律用 tmux detached session 起，再挂 Monitor 等，不要在前台阻塞。

### 自对拍：确认除 flow 外逐位不变

同一份代码，flow 关 / 开各生成一次，比较除 flow 之外的全部内容。这是「只增不改」的**权威验收口径**，
不是跟官方参考对拍。

```bash
uv run --no-sync python scripts/data-generation-v2/verify_joint_action_bitexact.py \
  --baseline artifacts/generated/flow-16env-baseline \
  --candidates artifacts/generated/flow-16env
```

### 数学验证：六条判据

```bash
uv run --no-sync python scripts/data-generation-v2/verify_flow_math.py \
  --h5 artifacts/generated/flow-16env/record_dataset_*.h5 --episode 0
```

### flow 回放可视化

```bash
uv run --no-sync python scripts/data-generation-v2/replay_flow_video.py \
  --h5 artifacts/generated/flow-16env/record_dataset_ButtonUnmask.h5 \
  --episode 0 --arrow-scale 5
```

### 补齐官方参考 h5

数据源是 HuggingFace 的 `Yinpei/robomme_data_h5`，16 个任务各一个 `.tar.xz`，压缩态合计约 56 GB。
脚本会跳过本机已有且校验通过的任务，只下缺的那些。下载与解压是小时级长任务，务必用 tmux 起。

**本机现状：参考数据只覆盖 7 个任务**（`ButtonUnmask` / `ButtonUnmaskSwap` / `VideoUnmask` /
`VideoUnmaskSwap` / `PickXtimes` / `StopCube` / `SwingXtimes`）。因此与官方参考的对拍目前只能覆盖
这 7 个；生成 16 个任务时需要加 `--no-reference-validation`。

```bash
uv run --no-sync python scripts/data-generation-v2/fetch_reference_h5.py --tasks all
```

## flow 写入格式

权威 schema 见 [doc/h5_data_format.md](../../doc/h5_data_format.md) 的「2D flow ground truth」一节。
要点：

- `setup/` 下两个字典 group：`flow_objects`（保留对象 → seg id + 种类）与 `flow_excluded`（黑名单 → 剔除原因）；
- `timestep_<k>/flow/<key>` 是 compound dtype 的标量 dataset，读法仍是字典式；
- key 一律 `<原名>__<seg_id>`，**跨 episode 不稳定**，按物体聚合要走 `original_name` 反查；
- `z_cam` 是必备字段——只有 `(u, v)` 反解不出 3D。

## 六条数学判据

`verify_flow_math.py` 逐帧逐物体全量跑：

| # | 判据 | 阈值 | 证明了什么 |
|---|---|---|---|
| 1 | 闭环还原 `‖X_w' − pos_3d‖∞` | ≤ 1e-9 m | 反向变换精确还原 3D 真值 |
| 2 | 重投影 `‖(u',v') − (u,v)‖∞` | ≤ 1e-9 px 且 ≤ 100 ulp | 正向∘反向 = 恒等，双射闭合 |
| 3 | `pos_2d_yx == [rint(v), rint(u)]` | 逐元素相等 | 与 `choice_action` 整数口径不漂移 |
| 4 | 雅可比二阶收敛 `r(Δ/2)/r(Δ)` | 0.25 ± 0.05 | 2D 位移确实是 3D 位移的正确微分像 |
| 5 | 静止物体零位移 | < 1e-12 px | 相机静止 ⇒ 静止物零流 |
| 6 | **充分可见**帧上投影点落在自身掩码内的比例 | ≥ 95% | 投影结果与真实渲染图像一致 |

判据 1、2 只能证明「存下来的 `(u,v,z)` 与存下来的 `X_w` 自洽」；判据 6 才把它锚到真实渲染图像上；
判据 4 才把「位移」这一层锁死。六条缺一不可。

> 判据 2 的阈值原本定的是 `1e-12 px`，实测不成立。原因不是实现有问题，而是阈值与坐标量级挂钩：
> `pos_2d_uv` 刻意不裁剪，出界物体的子像素坐标可以到几百上千，float64 在那个量级的 ulp 已经是
> `1e-13`，复合运算累积十几个 ulp 是必然的。因此改成量级无关的判据：绝对误差压在 `1e-9 px`，
> 同时叠加「不超过该坐标量级 100 ulp」的相对判据。后者才是这条判据的实质。

> 判据 6 的口径修正过一次。最初是「全部 `in_frame` 帧上比例 ≥ 90%」，实测三个任务过不了
> （PickXtimes 63.5%、VideoPlaceButton 87.0%、VideoPlaceOrder 87.6%）。逐物体拆开发现，低比例
> 全出在名字带 `target` 的物体上——那是**目标位置标记**，任务过程中方块最终会盖到它上面，
> **被遮挡正是任务语义本身**（PickXtimes 的 `target` 全帧只有 29.9% 未被遮挡）。也就是说原口径
> 度量的是「场景里发生了多少遮挡」，而不是「投影对不对」。
>
> 修正后只在物体**充分可见**的帧上统计：取该物体本 episode 的 `seg_pixel_count` 75 分位数，只看
> 达到这个水平的帧。这么算之后 16 个任务的每一个 actor 都是 **100%**（唯一例外
> VideoPlaceOrder 的 `cube_blue_0`，299/300 = 99.7%）。全帧比例保留为诊断量打印。
>
> `link` 与 `tcp` 始终只诊断不设阈值：articulation link 的原点常落在关节处（可能在自身几何内部），
> tcp 没有视觉体。

判据 1 实测抓出过一个真 bug：`project_world_to_pixel_subpixel` 早期沿用了既有函数「深度非正时改用
extrinsic 求逆再试一次」的兜底，导致投影与反投影用上不同的矩阵，MoveCube 的闭环误差高达 8.63 米。
现在新函数只按主解释（`extrinsic_cv` 即 world→camera），深度非正一律判为不可投影。回归测试在
`tests/lightweight/test_flow_projection_roundtrip.py` 里，用的就是当时那组真实相机参数。

## 规划器兜底是唯一的非确定性来源

`_planner_classes` 里的 `ScrewThenRRT` 在 screw 连续三次失败后会退避到 **RRTStar**——采样式规划器，
带墙钟预算，依赖当时的 CPU 负载。这是整条链路里唯一的非确定性来源。

生成报告里每个 episode 都记录了 `planner_fallback` 计数（`screw_calls` / `screw_rounds_failed` /
`rrtstar_attempts` / `rrtstar_successes`）。**`joint_action` 做不到逐位一致时，第一步永远是查这个计数，
而不是默认怀疑 flow 改动引入了回归。** 计数器只做自增，不改变任何控制流，对生成结果零影响。

## 产物与报告

```text
artifacts/generated/<名字>/
├── record_dataset_<任务>.h5
└── record_dataset_<任务>_metadata.json

scripts/data-generation-v2/reports/
├── generation_report.json
└── generation_report.md
```

⚠ 报告是**固定两个文件**，每次生成或只读复核都会原子替换它们。要留档必须在跑下一次之前手动抄走。
