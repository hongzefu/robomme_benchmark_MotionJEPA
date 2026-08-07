# HDF5 Training Data Format

Structure inside each `record_dataset_<EnvID>.h5` file:

```text
episode_1/
  setup/
  timestep_1/
    obs/
    action/
    info/
  timestep_2/
    obs/
    action/
    info/
  ...
...
```

Each episode contains:
- `setup/`: episode-level configuration.
- `timestep_<K>/`: per-timestep data.

## `setup/` fields (episode configuration)

| Field | Type | Description |
|-------|------|-------------|
| `seed` | `int` | Environment seed (fixed for benchmarking) |
| `difficulty` | `str` | Difficulty level (fixed for benchmarking) |
| `task_goal` | `list[str]` | Possible language goals for the task |
| `front_camera_intrinsic` | `float32 (3, 3)` | Front camera intrinsic matrix |
| `wrist_camera_intrinsic` | `float32 (3, 3)` | Wrist camera intrinsic matrix |
| `available_multi_choices` | `str` | Available options for the multi-choice Video-QA problem |

## `obs/` fields (observations)

| Field | Type / shape | Description |
|-------|---------------|-------------|
| `front_rgb` | `uint8 (256, 256, 3)` | Front camera RGB |
| `wrist_rgb` | `uint8 (256, 256, 3)` | Wrist camera RGB |
| `front_depth` | `int16 (256, 256, 1)` | Front camera depth (mm) |
| `wrist_depth` | `int16 (256, 256, 1)` | Wrist camera depth (mm) |
| `joint_state` | `float32 (7,)` | Absolute joint positions (7 joints) |
| `eef_state` | `float32 (6,)` | Absolute end-effector pose `[x, y, z, roll, pitch, yaw]` |
| `gripper_state` | `float32 (2,)` | Gripper opening width in [0, 0.04] |
| `is_gripper_close` | `bool` | Whether gripper is closed |
| `front_camera_extrinsic` | `float32 (3, 4)` | Front camera extrinsic matrix |
| `wrist_camera_extrinsic` | `float32 (3, 4)` | Wrist camera extrinsic matrix |

## `action/` fields

| Field | Type / shape | Description |
|-------|---------------|-------------|
| `joint_action` | `float32 (8,)` | Absolute joint-space action: 7 joint angles + gripper |
| `eef_action` | `float32 (7,)` | Absolute end-effector action `[x, y, z, roll, pitch, yaw, gripper]` |
| `waypoint_action` | `float32 (7,)` | Absolute end-effector action at discrete time steps; a subtask may contain multiple waypoint actions. Used for data generation. |
| `choice_action` | `str` | JSON string for multi-choice selection with an optional grounded pixel location on the front image, e.g., `{"choice": "A", "point": [y, x]}` |

In RoboMME, a gripper action of -1 means close and 1 means open.

## `info/` fields (metadata)

| Field | Type | Description |
|-------|------|-------------|
| `simple_subgoal` | `bytes (UTF-8)` | Simple subgoal text (built-in planner view) |
| `simple_subgoal_online` | `bytes (UTF-8)` | Simple subgoal text (online view; may advance to the next subgoal earlier than planner view) |
| `grounded_subgoal` | `bytes (UTF-8)` | Grounded subgoal text (built-in planner view) |
| `grounded_subgoal_online` | `bytes (UTF-8)` | Grounded subgoal text (online view; may advance to the next subgoal earlier than planner view) |
| `is_video_demo` | `bool` | Whether this frame is from the conditioning video shown before execution |
| `is_subgoal_boundary` | `bool` | Whether this is a keyframe (i.e., a boundary between subtasks) |
| `is_completed` | `bool` | Whether the task is finished |

---

# 2D flow ground truth（`flow-2d-v1`）

> 以下为本仓库新增字段，权威口径以本节为准。上面的英文部分是上游 benchmark 的原始内容，原样保留。

由 `scripts/data-generation-v2/` 链路生成时写入，**全部来自仿真真值**：物体的 3D 世界坐标直接取自
仿真状态，再经仓库唯一的投影入口 `project_world_to_pixel_subpixel`（`choice_action_mapping.py`）
反投影到 `base_camera` 像素平面。链路中不含任何从像素估计的成分。

只有开启生成入口的 `--flow` 时才会写入；`--no-flow` 时 h5 内容与既有链路**逐位一致**。

## `setup/` 新增字段

除 `flow_schema_version` 外，分成两个**字典 group**：保留对象与黑名单剔除对象。

```text
episode_<i>/setup/
  flow_schema_version              str        固定为 "flow-2d-v1"
  flow_objects/                    group      ← 参与 flow 统计的对象字典
    <原名>__<seg_id>/              group
      original_name                str        未拼接的原始 actor.name / link.name
      seg_id                       int64      per_scene_id，与 front 分割图像素值一一对应
      kind                         str        "actor" / "link" / "tcp"
      articulation_name            str        link/tcp 所属 articulation 名；actor 写空串
  flow_excluded/                   group      ← 被黑名单剔除的对象字典
    <原名>__<seg_id>/              group
      original_name                str
      seg_id                       int64
      kind                         str
      reason                       str        "robot_link" / "background_prop"
```

**黑名单口径**：剔除机器人 articulation 的全部 link（判据是「所属 articulation 是不是
`agent.robot`」，不靠名字前缀——stick 环境命名不同，靠前缀会漏），剔除名字命中
`table-workspace` / `table` / `ground` / `floor` 的背景道具，再把 `agent.tcp` 单独加回来
（`kind="tcp"`）。TCP 通常没有视觉体，其 `seg_pixel_count` 恒为 0，属预期。

## `timestep_<k>/flow/` 新增字段

每个保留对象一个 **compound dtype 的标量 dataset**，dataset 名就是 `flow_objects` 里的同一个 key。
读法是字典式的：`f["episode_0/timestep_37/flow/button_cap__19"]["pos_3d"]`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `pos_3d` | `float64 (3,)` | 世界系参考点（米），取自物体位姿的平移分量；坐标系以 [env_format.md](env_format.md) 为准 |
| `pos_2d_uv` | `float64 (2,)` | `[u=列, v=行]`，OpenCV 约定，**子像素、不裁剪**；深度非正时写 NaN |
| `pos_2d_yx` | `int32 (2,)` | `[y=行, x=列]` 整数，与 `action/choice_action` 的 `point` 完全同口径；无效写 `-1` |
| `z_cam` | `float64` | 相机系深度（米）；无效写 NaN |
| `in_frame` | `bool` | 深度为正且 `(u,v)` 落在 `[0,256)×[0,256)` 内 |
| `seg_pixel_count` | `int32` | 该物体在 front 分割图里的像素数（0 = 整体不可见） |
| `point_unoccluded` | `bool` | 投影点所在像素的分割 id 恰为该物体自身（参考点本身未被遮挡） |
| `flow_2d_uv` | `float64 (2,)` | 到**下一个记录帧**的 2D 位移 `(Δu, Δv)`；无效写 NaN |
| `flow_2d_yx` | `float64 (2,)` | 同一位移的 `[Δy, Δx]` 轴序；无效写 NaN |

### 三条必须知道的口径

**① `z_cam` 是必备字段，不是附加信息。** 只有 `(u, v)` 反解不出 3D——一个像素对应一整条射线，是
一对多映射。必须同时存下相机系深度，`(u, v, z_cam) ↔ (X, Y, Z)_world` 才构成严格双射。反向公式为
`X_c = z·K⁻¹·[u, v, 1]ᵀ`、`X_w = R⁻¹·(X_c − t)`。

反解时有两个坑，都实测踩过：

- ⚠ h5 里的 extrinsic 是 `float32`，其旋转部分的正交性误差实测约 `1.4e-7`，因此**必须解线性方程组
  而不是用 `Rᵀ`**——后者实测重投影误差达 `4e-4` 像素，前者只有 3 ulp。
- ⚠ 投影**只按 `extrinsic_cv` 即 world→camera 这一种解释**，深度非正时直接判为不可投影。既有的
  `project_world_to_pixel` 在深度非正时会改用「extrinsic 求逆」再试一次，那对求单个像素点是无害的
  防御，但对双射是致命的：投影走了求逆矩阵、反投影只认主解释，闭环还原会错到米级。实测在 MoveCube
  里，藏匿中的 `goal_site` 主解释深度 `-4.87`、求逆解释 `+3.98`，落盘了一个看似合法的投影点，闭环
  误差 **8.63 米**。`project_world_to_pixel_subpixel` 因此不做这个兜底。

**② 两套像素坐标各有分工。** `pos_2d_uv` 是数学载体（子像素、可逆），`pos_2d_yx` 与既有
`choice_action` 的 `{"choice": "A", "point": [y, x]}` 逐位对齐，供既有消费方直接复用。二者关系是
`pos_2d_yx == [rint(v), rint(u)]`（仅在 `in_frame` 处成立）。位移两套都保 `float`——帧间位移常常
小于 1 像素，整数化会把它直接量化成 0。

**③ 位移的时间基准是「下一个记录帧」，不是「下一个物理步」。** 名为 `NO RECORD` 的段里的物理步既不进
buffer 也不落 h5，相邻两个记录帧之间可能隔了任意多个真实步。位移无效时一律写 NaN 哨兵（与既有
`action/waypoint_action` 的体例一致），三种情况：末帧、本帧或下帧深度非正、两帧之间是断点
（`elapsed_steps` 差 ≠ 1，或 `is_video_demo` 翻转即 demo↔执行相位间发生过场景重置）。

> 顺带一提，ManiSkill 会把尚未登场的物体「藏」到 `(10, 10, 10)` 附近，这类物体在藏匿期间深度为负，
> `z_cam` 与 `pos_2d_uv` 都是 NaN，从藏匿到登场那一帧的假位移正好被上述规则②自动屏蔽。

## 字典 key 的稳定性

key 一律是 `<原名>__<seg_id>`。ManiSkill 保证 actor 名全局唯一（`actor_builder.py` 的 `build()` 里有
断言），但 link 名只在自己 articulation 内唯一——两个 button articulation 可以各有一个同名 link，
带上 segmentation id 才能保证 h5 group 名不撞。

⚠ **代价是 key 跨 episode 不稳定**：`per_scene_id` 每个 episode 都可能不同。下游若要按物体跨 episode
聚合，必须走 `setup/flow_objects/<key>/original_name` 反查，不能直接把 key 当稳定主键。

## 相关工具

- `scripts/data-generation-v2/verify_flow_math.py`：六条判据验证正反变换严格一一对应
- `scripts/data-generation-v2/verify_joint_action_bitexact.py`：自对拍，验证开 flow 后除 flow 外逐位不变
- `scripts/data-generation-v2/replay_flow_video.py`：渲染带 flow 箭头的对照视频
