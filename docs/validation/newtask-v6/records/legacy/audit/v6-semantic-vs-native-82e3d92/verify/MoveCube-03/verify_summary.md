# MoveCube-03 独立复核（AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1）

## 结论：CONFIRMED（核心事实），category 建议改为 native_same（原 new_tier_only 依据不成立）

## 复现的核心事实
- `scan_all_output.txt`：直接读 S2 xhard4 seed 6100002 的 H5
  （MoveCube-xhard4-6100002/hdf5_files/MoveCube_ep9_seed6100002.h5, episode_9）：
  step105（is_subgoal_boundary=True, is_video_demo=True）起，`info/grounded_subgoal`
  = `"Hook the cube to the target with the peg"`（simple_subgoal 与之逐字相同），
  两个坐标槽全部丢失，与 finding 描述一致。
- **纠正**：该退化不是单帧现象，而是整段 demo 期「Hook the cube」子目标
  （step105–228，连续 124 帧）全程退化；同一 episode 里同一子目标在
  execution 阶段（is_video_demo=False，step397–507，111 帧）**全程正常**，
  文本为 `"Hook the cube at <95, 171> to the target at <123, 159> with the peg"`。
  finding 原文「At that frame the lifted peg/arm hides the cube」暗示单帧遮挡，
  实测是整个 demo 子目标区间无一帧恢复。
- `front_rgb_step105.png`：peg 已被抓起举到画面右上，方块完全不在画面可见范围
  （被机械臂/peg遮住或移出视野），核实遮挡属实。
- `front_rgb_step200.png`：demo 段中段方块其实已经**可见**（peg 尖端旁的红色方块），
  但该帧文本仍是退化态——说明这不是「每帧重新判定、只有边界帧撞上遮挡」，
  而是demo 段这次子目标从第一帧起就没有 latch 成功、此后也未再次成功过。
  `front_rgb` 与分割用的 `sensor_data.base_camera` 是同一路相机
  （`RecordWrapper.py::_capture_step` 里 `front_rgb`≡`base_camera_frame`，
  segmentation 同样来自 `base_camera`），所以不是"看到的视频"和"算坐标的相机"
  不一致，具体为何 200 帧可见仍未回填，本次复核未能进一步定位（需要 sensor
  segmentation dataset，本次 H5 未存该数据集，无法离线复算）。

## 机制核对（源码，AUDIT_BASE，只读 git show）
- `src/robomme/robomme_env/MoveCube.py`：`self.ways=["peg_push","gripper_push",
  "grasp_putdown"]` 在 `_load_scene`/reset 中**无难度条件**被设置，
  `way_idx` 用 `torch.randint(len(self.ways),...)` 随机抽取，
  三档难度（含 easy/medium/hard 原生档）与 xhard4 用的是**同一段代码**。
  即 `peg_push` 任务（含 "Hook the cube at <> to the target at <> with the peg"
  模板）在原生档同样存在，并非 xhard4 专属机制。
- `src/robomme/env_record_wrapper/DemonstrationWrapper.py::
  _compute_segmentation_and_fill_subgoal`：占位符填充失败时
  "degrade to current_task_name as whole sentence"（docstring 原文），
  即当前实测的退化文本正是该函数按文档设计的**既有兜底行为**，
  不是 xhard4 新增逻辑，也没有难度分支。
- `0925-newtask-release-v6-plan.md`（AUDIT_BASE）第 6 节「MoveCube（只有
  xhard4：圆环 U）」通篇只涉及方块/goal/杆的空间采样区域（圆环、可达带、
  杆间隙等），**未提及 grounded_subgoal 坐标填充或遮挡兜底逻辑**——该机制
  确实不在 V6 计划改动范围内，属继承自基线的通用行为。

## 原生 vs xhard4 样本对照（本次独立统计，`scan_all_output.txt`）
| 分组 | 用 peg_push 的 episode 数 | 出现退化的 episode 数 |
|---|---|---|
| 原生 easy/medium/hard（`v1/base/B/`，9 ep） | 4（ep0,2,7,10） | 0 |
| S2 xhard4（`v6-s2-20260926-01`，9 delivered ep） | 3（6100001,6100002,6100006） | 1（6100002） |

样本量极小（原生 4 局、xhard4 3 局用到 peg_push），**不足以判断 xhard4 是否
真的提高了遮挡退化率**；finding 自己也承认"annulus places cubes closer to
the robot base... which may raise the rate"是未验证假说。

## category 判定
finding 原始 category = `new_tier_only`（"only exists in xhard1-4 mechanics"）。
但源码证实：peg_push 任务与坐标填充/遮挡退化机制在 easy/medium/hard 与
xhard1-4 之间**完全同一套代码、无难度分支**，plan 文档也未改动这段逻辑。
「只在 xhard4 观测到」只是极小样本下的偶然，不代表机制只存在于新档位。
按题目给的分类口径（"native_same = identical behavior in easy/medium/
hard"）更贴切——机制是继承基线、跨档完全相同的行为，只是触发所需的
（遮挡）条件在此样本里恰好只在一局 xhard4 episode 命中。
**建议 category_corrected = native_same**，但保留低置信度标注：
样本太小、无法排除 xhard4 新区域布局确实提高了触发概率（若要坐实/证伪
这一点需要新增仿真，见 simulation_request）。

## 排重检查
对照 EXCLUDED 清单 F1–F6、D1–D7、swap/binfill/VPB 等及"任何左右用词"、
"纯网站文案"条目：均不匹配（最接近的 F4"stale grounded_subgoal coordinates
after swap"是 swap 后坐标未更新，与本条"遮挡导致坐标整体丢失/退化为任务名"
是不同触发机制、不同代码路径）。判定：**不是重复项**。

## 证据文件
- `scan_all_output.txt`：独立脚本对全部 9 个 S2 xhard4 delivered episode 与
  全部 9 个原生 episode 的逐帧 grounded_subgoal 扫描结果。
- `front_rgb_step{100,104,105,110,150,200,228,229}.png`：seed 6100002 demo
  段关键帧（base_camera=front_rgb），可见 105 帧方块完全不可见、200 帧方块
  已可见但文本仍退化。
