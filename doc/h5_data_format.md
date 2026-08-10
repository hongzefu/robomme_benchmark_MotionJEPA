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
| `front_rgb_masked` | `uint8 (256, 256, 3)` | 纯色棕遮蔽图（本仓库新增；口径分两版，见下方 `masked-rgb-v1` 与 `masked-rgb-v2` 两节，产物属于哪一版看 `setup/masked_rgb_schema_version`） |

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

---

# 纯色棕遮蔽图（`masked-rgb-v1`）

> ⚠ 这一节描述的是 **`scripts/data-generation-v2/`** 的口径。后续 `scripts/data-generation-v2.1/`
> 换了遮蔽口径，schema 升到 `masked-rgb-v2`，见再下面一节。判断手里的产物属于哪一版，
> 看 `episode_<i>/setup/masked_rgb_schema_version`。

由 `scripts/data-generation-v2/` 链路在开启 `--masked-rgb` 时写入（默认开启），落点是
`timestep_<k>/obs/front_rgb_masked`，与 `front_rgb` 并列、**同 dtype 同 shape、不压缩**。

它是一张**可控的干净底图**：把机械臂与桌面刷成单一棕色，只留下夹爪接触部位与任务物体。
做 flow 目视检查时箭头不会淹没在木纹里，下游用它也不会被桌面纹理与臂杆外观干扰。

## 怎么算出来的

**纯粹的分割后处理**，复用同一帧已有的 `base_camera` segmentation 缓冲：把命中涂色集的像素
直接赋成纯棕色。**不改任何渲染材质、不做二次渲染**，因此 `front_rgb` 本身逐位不变。

计算全部发生在 `close()` 里而不是 `step()` 里，`step()` 一个字没动——热路径零开销，规划器那
1 秒墙钟预算不受任何影响。

## 白名单口径

只有两类东西会被涂棕，其余**一律原样保留**：

1. 机器人 articulation 下的 link（减去下面的保留集）；
2. 桌面 actor `table-workspace`。

坚持白名单而不是「除了 XX 都涂」，是因为黑名单遇到新出现的未知物体会默认涂掉它、静默毁掉数据；
白名单遇到未知物体默认保留，最多是少涂一块，肉眼一看就知道。

**保留集**（保留原始像素的机器人部位）：

```text
若 agent.finger1_link 存在（有手指的机器人，如 panda_wristcam）：
    保留 = {finger1_link, finger2_link, finger1pad_link, finger2pad_link} 里非 None 的那些
否则（无手指的机器人，如 panda_stick）：
    保留 = {tcp 所在 joint 的 parent_link}
```

三条实测依据：

- **`panda_hand_tcp` 恒为 0 像素**。urdf 里它有 `<visual>`，但渲染不出任何像素（查
  `flow/panda_hand_tcp__*` 的 `seg_pixel_count`，全 0）。拿 tcp 本身当「stick 末端」是空操作。
- **`panda_stick` 的那根棍挂在 `panda_hand` 上**：`panda_stick.urdf` 里 `panda_hand` 有两个
  visual——手掌 mesh，加一个 `radius=0.008 / length=0.1` 的圆柱。**segmentation 是 link 级的**，
  棍与手掌同属一个 link，所以「保留 stick 末端」唯一可行的粒度就是保留整个 `panda_hand`，
  RouteStick / PatternLock 的遮蔽图里手掌会连着棍一起留下。
- **`panda_leftfinger_pad` / `rightfinger_pad` 在 `panda_v3.urdf`（panda_wristcam 用的那份）里
  根本不存在**，`agent.finger1pad_link` 是 `None`。保留它们只为 urdf 换版后规则不失效。

解析一律**优先走对象身份**而非 `panda_` 字符串前缀：`camera_base_link` / `camera_link` 也是真实的
机器人 link 却不带该前缀，用前缀规则会把腕部相机支架整个漏掉。名字兜底则限定在「所属 articulation
是机器人」的 link 里找，否则任务物体一旦重名就会被误保留。

**地面 `ground` 不在白名单里，原样保留**。它占画面顶部约 4.9% 的一条棋盘格横带；机械臂举高穿过
这条带时，那部分臂杆会被涂成桌面棕、看起来像一块浮空的棕色。这是口径的必然结果，不是 bug。

## 棕色取值

`(179, 107, 67)`——桌面棕色区的**实测中位 RGB**，跨 MoveCube / ButtonUnmask / VideoPlaceOrder
与跨帧完全一致。用它而不是随便挑一个「标准棕」，是为了让涂掉的机械臂无缝融进涂平的桌面，
而不是在画面里形成第二块颜色不同的色板。取值同时写进 `setup/masked_rgb_paint_color`。

## `setup/` 新增字段

```text
episode_<i>/setup/
  masked_rgb_schema_version        str        固定为 "masked-rgb-v1"
  masked_rgb_paint_color           uint8 (3,) 实际使用的棕色 RGB
  masked_rgb_painted/              group      ← 被涂成纯棕色的对象字典
    <原名>__<seg_id>/              group
      original_name                str
      seg_id                       int64
      kind                         str        "actor" / "link"
      articulation_name            str
      reason                       str        "robot_link" / "table_actor"
  masked_rgb_kept/                 group      ← 保留原始像素的对象字典
    <原名>__<seg_id>/              group
      original_name                str
      seg_id                       int64
      kind                         str
      articulation_name            str
      reason                       str        "gripper_finger" / "gripper_finger_pad" /
                                              "stick_end_link" / "not_whitelisted"
      resolved_by                  str        "object_identity" / "name_fallback"；
                                              白名单外的对象写空串
```

`painted` 与 `kept` **两个字典都写**：白名单机制下，日后要回答的审计问题是「`ground` 到底涂没涂」
「左手指是靠对象身份找到的还是退回字符串了」，只记涂掉的那一半答不了。`resolved_by` 正是
ManiSkill 升级后对象身份这条路静默失效时的唯一探针——它变成 `name_fallback` 就说明该查了。

## 两个已知代价

- **涂色区域不可从遮蔽图无损反推**。棕色取的就是桌面中位色，画面里本来就偏棕的物体会撞色，
  `np.all(img == paint_color)` 会误判。真需要精确 mask 的话正确做法是另开字段
  （父类里 `front_camera_segmentation` 的 `create_dataset` 本来就只是被注释掉了），
  不要试图从颜色反解。
- **硬边界、无阴影**。`minimal` shader 是单采样光栅化、无 MSAA，所以 rgb 与 segmentation 逐像素
  对齐（没有边缘光晕，这是好事），代价是涂色区边界完全硬，且物体投在桌面上的接触阴影会连桌面
  一起被抹平。

## 相关工具

- `scripts/data-generation-v2/export_masked_preview.py`：导出 `front_rgb` 与 `front_rgb_masked`
  的并排对照图，白名单涂对没有最终只能靠这个用眼睛判定
- `scripts/data-generation-v2/verify_joint_action_bitexact.py`：自对拍时 flow 与 masked rgb
  是两个独立计数器，`--no-masked-rgb` 开关坏掉不会躲在正常工作的 `--flow` 后面

---

# 纯色棕遮蔽图（`masked-rgb-v2`）

由 `scripts/data-generation-v2.1/` 链路在开启 `--masked-rgb` 时写入（默认开启）。落点、dtype、
shape、压缩与「在 `close()` 里算、`front_rgb` 逐位不变」这几条与 `masked-rgb-v1` 完全一样，
**只有涂色口径不同**。

## 与 `masked-rgb-v1` 的三处口径差别

| 方面 | `masked-rgb-v1` | `masked-rgb-v2` |
|---|---|---|
| 机器人 | 涂全部 link，但**整根手指 link 保留原像素** | 涂全部 link，只在手指 link 内**按像素**豁免黑色指尖 |
| `panda_stick` | 保留整个 `panda_hand`（手掌连着棍一起留下） | **不保留任何东西**，整个机器人连棍一起涂掉 |
| 桌面 `table-workspace` | 涂成纯棕 | **不涂**，木纹原样保留 |

结果是画面里与机器人有关的东西**只剩夹爪指尖那一小块黑色接触面**，桌面与全部任务物体原样保留。

## 白名单口径

只有一类东西会被涂棕：**机器人 articulation 下的 link**。其余一律原样保留——桌面、地面
`ground`、全部任务物体、以及任何没认出来的东西。白名单而非黑名单的理由与 v1 一致：黑名单遇到
新出现的未知物体会默认涂掉它、静默毁掉数据。

**唯一例外是逐像素的黑色豁免**：

```text
若 agent.finger1_link 存在（有手指的机器人，如 panda_wristcam）：
    豁免 link = {finger1_link, finger2_link, finger1pad_link, finger2pad_link} 里非 None 的那些
    豁免像素 = 这些 link 内三通道均值 ≤ masked_rgb_black_luminance_max 的像素
否则（无手指的机器人，如 panda_stick）：
    豁免集为空，整个机器人全涂
```

为什么必须按像素而不是按 seg id：`panda_v3.urdf` 里 `panda_leftfinger` 只有**一个** visual
（`franka_description/meshes/visual/finger.glb`），白色指身与黑色指尖是同一个 mesh 上的两种
材质，而 ManiSkill 的 segmentation 是 **link 级**的——seg id 这一层根本切不开指身与指尖。

阈值默认 `100`，依据是在 16 任务既有产物上实测的手指像素亮度分布：**暗簇 38–59、亮簇 142–231，
中间 60–141 完全是空档**，阈值落在空档正中，往两边挪 40 个灰度级结果都不变。实现用整数和
`R+G+B ≤ 3×阈值` 判定，与「均值 ≤ 阈值」严格等价。实际使用的阈值写进
`setup/masked_rgb_black_luminance_max`。

豁免**只作用于手指 link**：手掌 `panda_hand` 与腕部相机支架上也有黑色方块，那些不属于夹爪
接触面，按口径一起涂掉。

## 棕色取值

仍是 `(179, 107, 67)`，桌面棕色区的实测中位 RGB。v2.1 已经不涂桌面了，但涂色仍沿用这个值——
机械臂在画面里几乎总是压在桌面上，用桌面中位色涂它，涂掉的部分会融进木纹底色而不是形成第二块
扎眼的色板。取值同时写进 `setup/masked_rgb_paint_color`。

## `setup/` 新增字段

```text
episode_<i>/setup/
  masked_rgb_schema_version        str        固定为 "masked-rgb-v2"
  masked_rgb_paint_color           uint8 (3,) 实际使用的棕色 RGB
  masked_rgb_black_luminance_max   int64      黑色豁免的三通道均值阈值（默认 100）
  masked_rgb_painted/              group      ← 被涂成纯棕色的对象字典（= 全部机器人 link）
    <原名>__<seg_id>/              group
      original_name                str
      seg_id                       int64
      kind                         str        固定 "link"
      articulation_name            str
      reason                       str        "robot_link" / "robot_link_black_exempt"
  masked_rgb_kept/                 group      ← 保留原始像素的对象字典（桌面 / 地面 / 任务物体）
    <原名>__<seg_id>/              group
      original_name                str
      seg_id                       int64
      kind                         str        "actor" / "link"
      articulation_name            str
      reason                       str        固定 "not_whitelisted"
  masked_rgb_black_exempt/         group      ← 参与黑色像素豁免的 link；panda_stick 下为空 group
    <原名>__<seg_id>/              group
      original_name                str
      seg_id                       int64
      kind                         str        固定 "link"
      articulation_name            str
      reason                       str        "gripper_finger" / "gripper_finger_pad"
      resolved_by                  str        "object_identity" / "name_fallback"
```

与 v1 的字段差别有三处，都要注意：

- `masked_rgb_kept` 里**不再有 `resolved_by`**——v2 口径下 kept 只剩「白名单之外」一种情形，
  解析途径挪到了 `masked_rgb_black_exempt`；
- 手指 link 同时出现在 `masked_rgb_painted`（`reason = robot_link_black_exempt`）与
  `masked_rgb_black_exempt` 两处。它属于涂色集，只是黑色像素被逐像素扣掉，**不是整块保留**；
- `masked_rgb_black_exempt` 是空 group 时也照写。`panda_stick` 任务的「豁免集为空」本身就是
  要记录的事实，group 缺失与「有 group 但没条目」在审计时是两回事。

`resolved_by` 仍是 ManiSkill 升级后对象身份解析静默失效时的唯一探针——它变成 `name_fallback`
就说明该查了。

## 两个已知代价（与 v1 相同）

- **涂色区域不可从遮蔽图无损反推**。棕色取的就是桌面中位色，画面里本来就偏棕的物体会撞色。
  v2.1 保留了桌面木纹，这条反而更严重了：桌面本身就有大量接近该棕色的像素。真需要精确 mask
  的话正确做法是另开字段，不要试图从颜色反解。
- **硬边界、无阴影**。`minimal` shader 是单采样光栅化、无 MSAA，所以 rgb 与 segmentation 逐像素
  对齐（没有边缘光晕，这也正是逐像素亮度判定能干净分开指身与指尖的前提）。

## 相关工具

- `scripts/data-generation-v2.1/export_masked_preview.py`：导出
  `front_rgb` / `paint_mask`（涂色区红色半透明叠加）/ `front_rgb_masked` **三列拼接图**
  目视核对，**核对清单与 v1 逐条不同**（桌面木纹应当保留、棍应当消失、只剩黑指尖，
  且中列红色掩码在指尖处应当有个小缺口）
- 生成报告里的 `masked_rgb_black_exempt_pixels`：黑色豁免生效与否的自动信号。手指在 256×256
  里只占几十个像素，光看涂色总数看不出来，这个计数恒为 0 就说明阈值或手指 seg id 解析出了问题
