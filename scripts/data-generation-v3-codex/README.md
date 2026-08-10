# RoboMME 数据生成 v3-codex：保留桌面的纯 CV 去机械臂

本目录完整复刻 `scripts/data-generation-v2/` 的 flow 生成与验收链路，只替换
`front_rgb_masked` 的生成规则：

- 桌面原像素保留，不再像 v2 一样整张涂成纯棕色；
- 机械臂、腕部与夹爪通过 RGB-D 通用计算机视觉规则删除；
- 去臂生产链路不读取 simulator segmentation、不读取机器人 link 名称、不依赖任务名称；
- 被机械臂挡住的区域优先用同一 episode 的未遮挡时序像素恢复木纹，空间补洞只作兜底；
- mask 外严格满足 `output == front_rgb`（逐位相等）。

flow 本身仍全部来自仿真 3D 真值，和 v2 完全一致；“纯 CV”只描述 RGB 去机械臂支路，不改变 flow
的 ground-truth 性质。

## 与 v2 的差别

| 方面 | v2 | v3-codex |
|---|---|---|
| RecordWrapper | `RobommeRecordWrapperV2` | `RobommeRecordWrapperV3`（父类仍零改动） |
| 机械臂 mask | simulator segmentation ID | HSV + RGB-D 桌面平面 + 边界连通 + 形态学 |
| 桌面 | 整张涂成纯棕 | 非 arm mask 区域逐位保留；遮挡处恢复木纹 |
| 夹爪 | 显式保留 | 跟机械臂一起删除 |
| 背景填充 | 常量 `(179, 107, 67)` | episode 时序背景 + 横向纹理补洞 + Telea 兜底 |
| h5 字段名 | `front_rgb_masked` | 同名，保持下游兼容；setup schema 改为 `masked-rgb-cv-v3` |

去臂全部在 `close()` 中发生，不进入仿真/规划热路径、不消费随机数，原始 `front_rgb`、控制轨迹与
`joint_action` 不会被改写。

## 目录内容

| 文件 | 作用 |
|---|---|
| `generate_dataset.py` | 生成唯一入口：生成 → 合并 → 契约校验 → 与参考对拍 → 写报告 |
| `record_wrapper_v3.py` | 薄子类，只 override `reset` / `step` / `close`，其余全部调用父类原函数 |
| `flow_tracker.py` | 物体枚举（黑名单）、逐帧投影、可见性/遮挡、位移计算、h5 写入 |
| `cv_arm_removal.py` | 纯 CV arm mask、RGB-D 桌面平面、时序背景与补洞 |
| `masked_rgb.py` | 调用纯 CV 模块并写 `front_rgb_masked` / setup 审计字段 |
| `validate_generated_dataset_contract.py` | 契约校验（结构 / seed / difficulty / joint_action shape 与 dtype） |
| `compare_joint_actions.py` | 与官方参考逐元素对拍 `joint_action` |
| `write_generation_report.py` | 报告写入（也可只读复核） |
| `verify_flow_math.py` | **六条判据**验证 flow 与 3D 真值严格一一对应 |
| `verify_joint_action_bitexact.py` | **自对拍**：验证开 flow 后除 flow 外逐位不变 |
| `verify_cv_arm_removal.py` | 用 v2 产物作只读代理真值，检查 arm-body 召回与逐位不变契约 |
| `replay_flow_video.py` | 可直接从旧 h5 的原始 RGB-D 在线去臂并渲染 flow 视频 |
| `export_masked_preview.py` | 导出三列概览，或时序抽稀后纯红删除图的 episode contact sheet |
| `fetch_reference_h5.py` | 从 HuggingFace 补齐官方参考 h5 |

## 常用命令

从仓库根目录执行。输出目录必须在仓库内，且不存在或为空。

### 16 任务 × episode_0：时序 4 倍降采样纯红删除拼图

本口径**只生成 16 张 PNG，不生成 H5 或视频**。每个任务读取既有 H5 的完整 `episode_0`，先在
完整原始 RGB-D 时序上计算通用 CV arm mask，再保留 `0,4,8,...,末帧`。每个保留帧保持原始
256×256 空间分辨率：mask 内写纯红 `(255, 0, 0)`，mask 外与 `front_rgb` 逐位相等，不使用
时序背景、邻近纹理或 inpaint 填充删除区域。最后按每行 8 帧、从左到右再从上到下的时间顺序
拼成一张 episode contact sheet。

```bash
uv run --locked python scripts/data-generation-v3-codex/export_masked_preview.py \
  --h5 artifacts/generated/v21-16env/record_dataset_*.h5 \
  --episode 0 --contact-sheet --temporal-stride 4 --columns 8
```

默认输出：

```text
scripts/data-generation-v3-codex/products/temporal4-red-mask-contact-sheets/
```

`products/.gitignore` 只跟踪产物目录约定；PNG 本身留在本机，不进入 Git。

### 直接重渲染现有 16 个 episode_0（本次使用的路径）

```bash
uv run --locked python scripts/data-generation-v3-codex/replay_flow_video.py \
  --h5 artifacts/generated/v21-16env/record_dataset_*.h5 \
  --episode 0 --arrow-scale 5 --base-image front_rgb_cv_arm_removed \
  --output-dir artifacts/flow-viz/v3-codex
```

现有 `artifacts/flow-viz/*.mp4` 已经把桌面纹理不可逆地涂掉，不能作为 v3 输入。上面命令从
`v21-16env` h5 内的原始 `front_rgb + front_depth` 重新计算，只处理 `episode_0`。

### 三列目视检查与 CV 数值验收

```bash
uv run --locked python scripts/data-generation-v3-codex/export_masked_preview.py \
  --h5 artifacts/generated/v21-16env/record_dataset_*.h5 \
  --episode 0 --frames 8 --output-dir artifacts/flow-viz/v3-codex-preview

uv run --locked python scripts/data-generation-v3-codex/verify_cv_arm_removal.py \
  --h5 artifacts/generated/v21-16env/record_dataset_*.h5 --episode 0 \
  --min-proxy-recall 0.99 --json artifacts/flow-viz/v3-codex-cv-verification.json
```

目视逐帧核对：桌面木纹保留、臂杆/腕部/夹爪无灰黑残边、补洞不带入旧位置物体、flow 点和箭头
仍贴在相应任务物体上；接触帧还要单独检查被抓物体是否被夹爪遮挡或与 mask 一起删除。

纯 RGB-D 规则存在一个明确边界：灰白任务物体与灰白夹爪实际接触、且两者在颜色和深度上连续时，
单帧连通、深度断桥和 watershed 都无法把两者可靠分开；跨帧光流/LK 补回又会带回灰色指端或产生
形状漂移。因此默认策略按本项目的目标优先保证机械臂与夹爪删净，不伪造被夹爪真实遮挡的物体
像素。当前 16 个 episode_0 中，`ButtonUnmask`、`VideoUnmask`、`VideoUnmaskSwap` 的少量接触帧
会连带删除灰白被抓物；这是纯 CV 输入下的已验收取舍，不是桌面补洞残影。

### 用 v3 完整生成 16 任务 × episode_0

加 `--no-reference-validation` 可以把生成与校验拆成两步（生成阶段本身与参考数据无关，跳过的只是
末尾那次对拍），验证脚本随后单独跑。`--workers 1` 用来消除多进程抢同一张卡带来的调度扰动。

```bash
env CUDA_VISIBLE_DEVICES=0 uv run --locked python scripts/data-generation-v3-codex/generate_dataset.py \
  --output-dir artifacts/generated/v3-codex-16env \
  --env all --episodes 1 --workers 1 --gpus 0 \
  --reference-root /data/hongzefu/robomme_data_h5 --flow --no-reference-validation
```

⚠ `--gpus` 只接受 `0`（脚本内硬编码），传其它值直接报错。
⚠ 超过 5 分钟的生成一律用 tmux detached session 起，再挂 Monitor 等，不要在前台阻塞。

### 单任务单 episode 生成冒烟

```bash
env CUDA_VISIBLE_DEVICES=0 uv run --locked python scripts/data-generation-v3-codex/generate_dataset.py \
  --output-dir artifacts/generated/v3-codex-smoke \
  --env ButtonUnmask --episodes 1 --workers 1 --gpus 0 \
  --reference-root /data/hongzefu/robomme_data_h5 --flow
```

### 自对拍：确认除新增字段外逐位不变

同一份代码，两个开关全关 / 全开各生成一次，比较除新增字段之外的全部内容。这是「只增不改」的
**权威验收口径**，不是跟官方参考对拍。基准侧**必须两个开关都关**，否则 verifier 会判基准侧被污染。

```bash
# 基准
env CUDA_VISIBLE_DEVICES=0 uv run --locked python scripts/data-generation-v3-codex/generate_dataset.py \
  --output-dir artifacts/generated/v3-codex-baseline \
  --env all --episodes 1 --workers 1 --gpus 0 \
  --reference-root /data/hongzefu/robomme_data_h5 \
  --no-flow --no-masked-rgb --no-reference-validation

# 对拍
uv run --locked python scripts/data-generation-v3-codex/verify_joint_action_bitexact.py \
  --baseline artifacts/generated/v3-codex-baseline \
  --candidates artifacts/generated/v3-codex-16env
```

flow 与 masked rgb 的存在性是**两个独立断言**：合成一个计数器的话，`--no-masked-rgb` 开关坏掉时
就能躲在正常工作的 `--flow` 后面不被发现。

### 数学验证：六条判据

```bash
uv run --locked python scripts/data-generation-v3-codex/verify_flow_math.py \
  --h5 artifacts/generated/v3-codex-16env/record_dataset_*.h5 --episode 0
```

### 补齐官方参考 h5

数据源是 HuggingFace 的 `Yinpei/robomme_data_h5`，16 个任务各一个 `.tar.xz`，压缩态合计约 56 GB。
脚本会跳过本机已有且校验通过的任务，只下缺的那些。下载与解压是小时级长任务，务必用 tmux 起。

**本机现状：16 个任务全部齐全**（2026-08-07 补完，共 530 GB，每个任务都通过了 100-episode 校验）。
因此与官方参考的契约校验与 `joint_action` 对拍现在可以覆盖全部 16 个任务，`--no-reference-validation`
不再是必需的——只有在生成与校验想拆成两步跑时才需要它。

```bash
uv run --locked python scripts/data-generation-v3-codex/fetch_reference_h5.py --tasks all
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

scripts/data-generation-v3-codex/reports/
├── generation_report.json
└── generation_report.md
```

⚠ 报告是**固定两个文件**，每次生成或只读复核都会原子替换它们。要留档必须在跑下一次之前手动抄走。
