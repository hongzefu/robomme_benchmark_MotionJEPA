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
| `front_camera_segmentation` | `int16 (256, 256)` | GT 分割图（本仓库新增，见下方 `segmentation-v1` 一节） |

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

# GT segmentation（`segmentation-v1`）

> 以下为本仓库新增字段，权威口径以本节为准。上面的英文部分是上游 benchmark 的原始内容，原样保留。

由 `scripts/data-generation/gt-data/` 链路生成时写入，**全部来自仿真真值**：逐帧 segmentation
图直接取自 ManiSkill 的 `obs`（父类 `RecordWrapper` 本来就缓存着它，只是写盘那行是注释状态），
seg_id 的语义表直接取自 `env.unwrapped.segmentation_id_map` 在 `reset()` 那一刻的快照。链路中
不含任何从像素估计的成分。

新增内容全部在 `close()` 里落盘，`step()` 一个字不动——既有字段的数值、dtype、shape、group
层级、timestep 数量与写入时序全部不变。

## `timestep_<k>/obs/` 新增字段

| Field | Type | Description |
|---|---|---|
| `front_camera_segmentation` | `int16 (256, 256)` | 前视相机的 GT 分割图，像素值 = seg_id |

## `setup/` 新增字段

除 `segmentation_schema_version` 外，是两个**字典 group**：保留对象与被剔除对象。它们合起来
就是「seg_id → 语义」的唯一依据——没有它，上面那张图只是一堆无法解释的整数。

```text
setup/
  segmentation_schema_version      str        固定为 "segmentation-v1"
  segmentation_objects/            group      ← 任务物体（含 TCP）
    <原名>__<seg_id>/
      original_name                str        未拼接的原始 actor.name / link.name
      seg_id                       int64      per_scene_id，与分割图像素值一一对应
      kind                         str        "actor" / "link" / "tcp"
      articulation_name            str        link/tcp 所属 articulation 名；actor 写空串
  segmentation_excluded/           group      ← 被剔除的对象
    <原名>__<seg_id>/
      original_name                str
      seg_id                       int64
      kind                         str
      reason                       str        "robot_link" / "background_prop"
```

### 三类映射（下游按此读，见 `gt-data/color_model.py` 的 `class_ids_from_setup`）

| 类 | 收哪些 seg_id |
|---|---|
| 机械臂 | `segmentation_excluded` 里 `reason == "robot_link"`；外加 `segmentation_objects` 里 `kind == "tcp"` |
| 背景 | `segmentation_excluded` 里 `reason == "background_prop"`；外加 seg_id 0（未命中任何几何体） |
| 物体 | `segmentation_objects` 里除 tcp 外的全部；**外加一切认不出的 seg_id（兜底，偏保守）** |

⚠ **`setup/` 的两张表是 `reset()` 那一刻的快照，episode 运行中动态创建的对象不在里面**
（实测有 5 个任务会出现这种 id，全是任务的目标 / 路径标记物）。它们走「归物体」兜底并被单独
计数，不许静默。

## 字典 key 的稳定性

key 一律是 `<原名>__<seg_id>`。ManiSkill 保证 actor 名全局唯一，但 link 名只在自己 articulation
内唯一（两个 button articulation 可以各有一个同名 link），带上 seg_id 才能保证 group 名不撞。

⚠ 代价是 `per_scene_id` 每个 episode 都可能不同，所以 **key 跨 episode 不稳定**。下游若要按物体
跨 episode 聚合，必须走 `segmentation_objects/<key>/original_name` 反查，不能直接把 key 当稳定主键。

## 相关工具

- `scripts/data-generation/gt-data/record_wrapper.py`：唯一写入点
- `scripts/data-generation/gt-data/seg_id_table.py`：枚举表的冻结与落盘
- `tests/lightweight/test_seg_id_table.py`：三类映射与落盘字段名的端到端闭环测试

## ⚠ 已删除的历史字段

以下字段**曾经存在于本仓库的历史产物中，现已不再生成**，新数据里不会有：

| 历史字段 | 说明 |
|---|---|
| `setup/flow_*`、`timestep_<k>/flow/` | 稀疏逐物体 2D flow ground truth。其中 `flow_objects`/`flow_excluded` 那张表实质是 seg_id 语义表，已保留并改名为上面的 `segmentation_objects`/`segmentation_excluded`；逐帧位移采集整体删除 |
| `obs/front_rgb_masked` | 纯色棕遮蔽图（`masked-rgb-v1` / `v2`）。有了真 GT segmentation 之后不再需要 |

读取历史产物时若遇到这些字段，请回到对应的历史 commit 查看当时的文档。
