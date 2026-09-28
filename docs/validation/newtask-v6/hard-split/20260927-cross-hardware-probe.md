# 跨硬件逐位对拍探针（2026-09-27）

用户问题原话：「easymediumhard的验收和v6的验收 是否能做到 在greatlakes上进行 spawn一堆job？跨硬件怎么做验收？先验证这个问题 然后再告诉我」，并开放四个占位 job（62126060／61／62、62018665）。

## 一句话结论

**h5 逐位一致只在「同一 GPU 型号 + 同一驱动」内成立**；软件栈逐位相同（三端均 Python 3.11.14 / mani_skill 3.0.0b21 / sapien 3.0.2 / torch 2.9.1+cu128 / CUDA 12.8）也挡不住跨硬件差异。RTX 6000 Ada（本机）与 RTX A6000（aspen）几乎一致（仅 16 个 `joint_action` 值差 ≤ 2.24e-18，状态与图像逐位相同）；A40（greatlakes，驱动 595）从第 7 步起物理状态与图像全面分叉（`joint_state` 最大 0.029 rad、`front_depth` 最大 2.67e3）。因此 **原三档 V1′ 的基线（S0，本机 Ada 产）只能在 Ada 上对拍；xhard 侧与 S4 交付（A40 产）的 sha 对拍只能在 A40 上做**；跨硬件只能做「结构一致 + 数值容差内一致」，不能做字节级。

## 口径

- 身份：`BinFill / episode 0 / seed 4000 / easy`；官方 A 路（官方编排 `generate_dataset.py` + 官方 `src`，隔离树 `.official_tree=1d4c13697f0c5fbd7a8b05e01c196c984a07406c`），单 worker，不开 recovery；runner／worker 为本仓库 `scripts/parity/train_split_{runner,worker}.py` @ `2d460ab7` 的副本。
- 本机 Ada 侧不重跑，直接取 S0 基线产物 `artifacts/newtask-v6/v1/base/B/BinFill_episode_0/hdf5_files/BinFill_ep0_seed4000.h5`（2026-09-26 生成）。
- 预算：GL 2 次 rollout（两个不同节点）、aspen 1 次 rollout，共 3 次，均 < 2 分钟，按单 worker ≤ 10 的 smoke 口径执行。

## 结果

| 侧 | 主机 / 节点 | GPU（sm） | 驱动 | h5 sha256 前 16 位 |
|---|---|---|---|---|
| Ada | sled-vail | RTX 6000 Ada（8.9） | 570.211.01 | `951bc0f5bcf8e85c` |
| A40-1 | greatlakes gl1517（job 62126060） | A40（8.6） | 595.71.05 | `d350b5207ffd1bc0` |
| A40-2 | greatlakes gl1506（job 62126062） | A40（8.6） | 595.71.05 | `d350b5207ffd1bc0` |
| A6000 | sled-aspen（GPU 1） | RTX A6000（8.6） | 570.195.03 | `3ce9c931567b47e7` |

三份 h5 结构相同（各 11556 个 dataset、550 步）。`compare_h5_pair`（浮点按位、无容差）：

```text
H5_PARITY pair=A40-1|A40-2       sha_equal=1
H5_PARITY pair=Ada|A6000         sha_equal=0 field_mismatch=16    steps=7..22  by_leaf={joint_action:16}  max_abs_diff{joint_action:2.24e-18}
H5_PARITY pair=Ada|A40           sha_equal=0 field_mismatch=5063  steps=7..549 by_leaf={joint_state:540, wrist_rgb:512, eef_action:508, eef_state:506, wrist_camera_extrinsic:506, joint_action:505, wrist_depth:487, front_depth:412, front_rgb:392, waypoint_action:358, gripper_state:334, choice_action:3}
                                 max_abs_diff{front_depth:2.67e3, wrist_rgb:235, wrist_depth:227, front_rgb:211, wrist_camera_extrinsic:0.0439, eef_state:0.0377, joint_state:0.029, gripper_state:0.00305, joint_action:8.17e-4, eef_action:3.23e-4}
H5_PARITY pair=A40|A6000         sha_equal=0 field_mismatch=5079  （分布与幅度同上一行）
XHW_PROBE=DONE rollouts=3 hosts=3 gpu_models=3 same_model_same_driver_bitwise=1 cross_model_bitwise=0
```

与历史留档一致：`docs/validation/newtask-v3/20260921-step1b-cluster-p0-p1.md` 第四节记 Ada `951bc0f5bcf8e85c97b7` vs A40 `d350b5207ffd1bc07077`，本轮两值逐字相同，说明 Ada 与 A40 各自跨周、跨代码版本（官方 A 路）稳定。

## 边界

- Ada↔A6000 的 16 处 1e-18 级差异发生在 `joint_action`（float64，planner 输出），未传导到状态与图像；不能据此宣称 sm_86 与 sm_89 逐位等价，只能说「本条身份在数值容差 1e-17 内一致」。
- A40 的分叉原因（驱动 595 vs 570、PhysX GPU 内核、渲染器）本轮未拆分；同型号同驱动内逐位稳定是已证的，跨型号的容差判据须另行标定。
- 探针 h5 已删（NFS／aspen 不留大文件）；`sha.txt`、`results.json` 留在 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/hs-xhw-probe-20260927/out-*/` 与 aspen `/data/hongzefu/hs-xhw-probe-20260927/`。
