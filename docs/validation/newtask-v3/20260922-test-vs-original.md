# 多 worker 生成 vs 原版发布集：容差校验方案与三机实测（2026-09-22）

对应用户 2026-09-22 的要求：原版发布集本身是 20 worker 生成的，给出容差方案，让以后多 worker 生成后能对原版判"在差距内"；
先跑实测标定；容差范围与全部调用方法写成 md；比较脚本全部放 `scripts/test-vs-original/`，生成沿用现有流水线；
两台本地机只测单 worker、greatlakes 测单 + 多 worker；三机同步发；全部比较一律"产物 vs 原版"，不做产物互比。

交付物：[`scripts/test-vs-original/`](../../../scripts/test-vs-original/README.md)
（`compare_vs_original.py`、`calibrate.py`、`tolerance.json`、`identities_16x3.txt`、`manifest_16x3.json`、`results/`、README）。
本文只记结论、判定行原文与过程中推翻的假设；方法与命令以 README 为准。

## 一、结论

1. **容差按硬件分两档**，判定行必须标档位：
   - `ada` 紧档（sled-vail RTX 6000 Ada）：手臂通道 1e-6、帧号/像素类全 0、`replan_max=0.0357`；
   - `a40` 松档（greatlakes A40 / aspen A6000）：手臂 p99 0.04 / max 0.04～0.06、帧差 ≤ 4、边界坐标 ≤ 2 px、边界帧号 ≤ 4、夹爪翻转 ≤ 2、ts0 图像 ≤ 5.06% / 深度 130、`replan_max=0.2188`。
2. **每局四类**（IDENTICAL / DRIFT / REPLAN / FAIL）+ 数据集级 `FAIL=0 且 REPLAN 率 ≤ 上限`。FAIL 只来自合同层（seed/difficulty/结局/主指令）与布局层（ts0 目标中心、ts0 深度/rgb 图像）；规划层差异一律 REPLAN。
3. **同架构单 worker 对原版是精确复现**：sled-vail 48 局 5 局全字段按位相同、42 局只剩 1e-16 舍入；**aspen 48 局 47 局按位相同**——原版发布集几乎可以确定产自 aspen（A6000）。
4. **跨架构（A40）**：无一局按位相同；同一条规划下手臂 p99 ≤ 0.019；REPLAN 率 10～15%；三局 reset 前物理沉降有微小差异（ts0 图像差 0.13%～2.5%）。
5. **松档的局限如实写明**：ts0 图像阈值放到 5%/130 后，对负例那种 3 cm/5° 的布局扰动（2.1%/62）没有检出力；布局级回归须用紧档查。

## 二、三机实测判定行

### sled-vail（紧档）

```text
VS_ORIGINAL=PASS tier=ada compared=48 identical=5 drift=42 replan=1 fail=0 replan_rate=0.0208 replan_max=0.0357
# 手臂通道 DRIFT 局 p99 最大值：joint_action=6.66e-16 eef_action=0 joint_state=0 eef_state=0
# 布局层：ts0 grounded 相同=48/48；ts0 图像最大像素差比例=0.0000，深度 max=0；边界坐标最大像素差=0；边界帧号最大偏移=2；夹爪翻转最大偏移=2；帧数最大差=4
REFERENCE_AUDIT_COMPLETE=PASS compared=48 contract_errors=0 missing=0
VS_ORIGINAL=PASS tier=ada compared=36 identical=0 drift=36 replan=0 fail=0 replan_rate=0.0000 replan_max=0.0357   ← local-recheck 36 局
```

### aspen（A6000，按松档判，旁证）

```text
VS_ORIGINAL=PASS tier=a40 compared=48 identical=47 drift=0 replan=1 fail=0 replan_rate=0.0208 replan_max=0.2188
# 布局层：ts0 grounded 相同=48/48；ts0 图像最大像素差比例=0.0000，深度 max=0；边界帧号最大偏移=1；夹爪翻转最大偏移=1；帧数最大差=1
```
唯一例外 `PickHighlight/ep3` 653 vs 652 帧。

### greatlakes A40（松档，定稿阈值）

```text
VS_ORIGINAL=PASS tier=a40 compared=48 identical=0 drift=43 replan=5 fail=0 replan_rate=0.1042 replan_max=0.2188    ← 16×3 48 局单 worker
VS_ORIGINAL=PASS tier=a40 compared=144 identical=0 drift=130 replan=14 fail=0 replan_rate=0.0972 replan_max=0.2188   ← 144 局 4 worker（新跑）
VS_ORIGINAL=PASS tier=a40 compared=144 identical=0 drift=130 replan=14 fail=0 replan_rate=0.0972 replan_max=0.2188   ← gl-5e 144 局单 worker（5d A1）
VS_ORIGINAL=PASS tier=a40 compared=144 identical=0 drift=130 replan=14 fail=0 replan_rate=0.0972 replan_max=0.2188   ← gl-5e-w4 144 局 4 worker（5d 首轮）
```

三份 A40 144 局的四类计数完全相同（130/14/0）：松档判定对 worker 数与运行批次稳定；多 worker（9.7%）与单 worker（10.4%）REPLAN 率同量级。

负例在松档下：`# BinFill/ep0: REPLAN replan:frames:558vs550,…,subgoal:px=8,boundary_shift=13,gripper:flip_shift=13`——
不再是布局层 FAIL，只因单局 REPLAN 率 100% 才使数据集 FAIL（松档局限）。

### 跨档与正负例

```text
VS_ORIGINAL=FAIL tier=ada compared=144 identical=0 drift=11 replan=122 fail=11 replan_rate=0.8472 replan_max=0.0357   ← A40 产物用紧档判，必须 FAIL
# BinFill/ep0: FAIL layout:ts0_depth_over_tol,ts0_rgb_over_tol   ← 负例（改 layout.board.offsets），紧档 FAIL、由 ts0 图像抓到
```

## 三、过程中推翻的假设（按时间）

1. **"ts0 目标中心足以做布局指纹"**——负例改了 board 位置，目标中心不变，是 ts0 深度图抓到的。布局层因此加 ts0 图像。
2. **"合同层文本可精确比"**——发布集（v0.5）与现行源码有纯标点差异（SwingXtimes `right-side`、VideoPlaceButton 多一个逗号），VideoPlaceButton `task_goal` 现行 3 条改写、发布集 2 条。改为只比主指令 `task_goal[0]` 的归一化文本。
3. **"帧数差 1 可以直接逐帧比"**——末段多/少 1 帧让后续整段错位一帧，p99 被抬到 0.03 误判 REPLAN。手臂比较改为允许 ±`frame_delta_max` 帧错位取最小差。
4. **"ts0 目标中心不同就是布局错"**——A40 上 BinFill/ep2 的 ts0 图像与原版逐像素相同，但首目标物是 red 而非 green；VideoPlaceOrder/ep0 的主指令由示范执行结果生成（first→second target）。这两类是规划层差异：松档记 REPLAN、紧档 FAIL（`strict_*` 字段）。
5. **"夹爪元素可与手臂一起逐元素比"**——`joint_action[7]` 取 ±1，翻 1 帧就是 2.0 的差；改为按翻转事件比。
6. **"sled-vail 是原版的同机器"**——aspen 47/48 按位复现，比 vail 更紧；原版应产自 aspen。本轮按用户决定仍两档交付，建议后续给 A6000 单独成档。
7. **"松档 ts0 图像能抓布局扰动"**——跨架构 reset 前物理沉降差异（InsertPeg/1、PickHighlight/7、VideoRepick/11）把阈值推到 5%/130，超过负例量级。已在 README 写明局限。

## 四、产物与清理

- 比较结果（JSON/JSONL，824 KB）随本次提交入库：`scripts/test-vs-original/results/`。
- 生成的 h5/mp4：本机 `artifacts/train-parity/tvo-*`、NFS `gl-tvo-16x3`、`gl-tvo-w4`、`aspen-tvo-16x3` 及各自 `merged-B`，按用户要求在汇报并确认后删除；`gl-5e`、`gl-5e-w4` 等既有验收产物与发布集不动。
