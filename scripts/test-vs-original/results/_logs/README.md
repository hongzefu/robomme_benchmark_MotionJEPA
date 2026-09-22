# 证据留档索引（2026-09-22）

本目录是本轮"多 worker 生成 vs 原版发布集"容差校验的**原始证据**，来自 Claude Code 会话的后台任务输出、
Monitor 捕获与只读探针。文件名前缀标明类别，`__` 后是会话任务 id。全部一律"产物 vs 原版发布集"。

| 前缀 | 内容 | 份数 |
|---|---|---|
| `gen-48局-monitor` | sled-vail / aspen 48 局单 worker 生成的 Monitor 捕获（`RUN_PATH … ok=48 failed=0 elapsed_s=…`） | 2 |
| `gen-GL单worker分片-monitor` | greatlakes 四片各 12 局单 worker 的 `RUN_PATH` 行与耗时 | 4 |
| `gen-GL-4worker分片-monitor` | greatlakes 四片各 36 局 4 worker 的 `RUN_PATH` 行与耗时 | 4 |
| `merge` | `train_split_parity.py merge` 输出（`MERGE_DONE …`） | 8 |
| `compare` | `compare_vs_original.py` 各次输出（含初值与定稿阈值两轮、正负例、跨档、逐局 verbose） | 12 |
| `calibrate` | `calibrate.py` 标定输出（观测值与建议阈值 JSON） | 1 |
| `probe-同架构36局对原版` | 只读探针：sled-vail local-recheck 36 局 vs 原版，逐局帧数与 `joint_action max|Δ|`（全部 ≤ 1.9e-17） | 1 |
| `probe-跨架构36局逐字段分布` | 只读探针：sled-vail vs A40（同代码同配置，仅用于理解噪声结构，不进标定）逐字段分布 | 1 |
| `probe-跨架构整文件对拍` | 只读探针：同上，整文件 108 对 0 相同 | 1 |
| `probe-夹爪元素与边界文本` | 只读探针：2.0 差异来自 `joint_action[7]`；边界文本差 1 px 的局 | 1 |
| `probe-aspen-venv` | aspen 上 NFS 克隆 venv 可用性（torch 2.9.1+cu128、cuda 可用） | 1 |
| `inventory-待删体积` | 删除前的六个测试目录体积（本机 52 G、NFS 126 G） | 1 |

另有 `../_runs/aspen-16x3-48-w1/`：aspen 那次生成的 `run.log`、`run_config.json`（含 hostname/GPU/驱动指纹）、
`run_summary.json`、`results/B.json`（逐局 ok/timestep_count）、`jobs/`、`logs/`、合并后 16 份 metadata。
sled-vail 与 greatlakes 两条线的同类文件随测试目录一起删除了（用户确认删除在先），它们的 `RUN_PATH` 行由上表 Monitor 捕获保留；
比较结果 `summary.json` 里的 `tier_source`（如 `auto:NVIDIA RTX 6000 Ada Generation`）保留了机器证据。

## 只在会话记录里、未落成任务文件的前台探针（原样抄录）

reset 后第一帧（`timestep_0`）深度图/rgb 在三种配对下的差异（读 `local-recheck/new`、`gl-recheck`、发布集）：

```text
配对                         身份                   front_depth | front_rgb | 相机外参同
vail vs 原版(同架构)            SwingXtimes/ep0      不同像素 0/65536（0.00%）max=0 | 不同像素 0/196608（0.00%）max=0 | True
vail vs A40(跨架构)           SwingXtimes/ep0      不同像素 0/65536（0.00%）max=0 | 不同像素 0/196608（0.00%）max=0 | True
A40 vs 原版(跨架构)             SwingXtimes/ep0      不同像素 0/65536（0.00%）max=0 | 不同像素 0/196608（0.00%）max=0 | True
vail vs 原版(同架构)            PickHighlight/ep3    0 | 0 | True
vail vs A40(跨架构)           PickHighlight/ep3    0 | 0 | True
A40 vs 原版(跨架构)             PickHighlight/ep3    0 | 0 | True
vail vs 原版(同架构)            VideoPlaceOrder/ep0  0 | 0 | True
vail vs A40(跨架构)           VideoPlaceOrder/ep0  不同像素 786/65536（1.20%）max=10 | 不同像素 2335/196608（1.19%）max=189 | True
A40 vs 原版(跨架构)             VideoPlaceOrder/ep0  不同像素 786/65536（1.20%）max=10 | 不同像素 2335/196608（1.19%）max=189 | True
vail vs 原版(同架构)            VideoPlaceButton/ep4 0 | 0 | True
vail vs A40(跨架构)           VideoPlaceButton/ep4 0 | 0 | True
A40 vs 原版(跨架构)             VideoPlaceButton/ep4 0 | 0 | True
```

官方 vs `gl-5e/merged-A1`（A40）的 ts0 grounded 与全部子目标边界坐标/文本（3 局）全部相同，只有边界帧号后移（PickHighlight/ep3：321→320、392→382、496→486、552→542）。

指令文本差异：SwingXtimes `task_goal[0]` 现行 `right-side`/`left-side` vs 发布集 `right side`；VideoPlaceButton `task_goal[1]` 多一个逗号，且现行 3 条、发布集 2 条；
VideoPlaceOrder/ep0 在 A40 上主指令 `second target`、原版与 sled-vail 产物均 `first target`。
BinFill/ep2 在 A40 上 ts0 grounded `pick up the first red cube at <60, 83>`，原版 `pick up the first green cube at <85, 76>`，ts0 图像逐像素相同。

完整方案与全部探针数字见 `docs/validation/newtask-v3/20260922-test-vs-original-plan.md`（计划文件原样入库）与 `20260922-test-vs-original.md`。
