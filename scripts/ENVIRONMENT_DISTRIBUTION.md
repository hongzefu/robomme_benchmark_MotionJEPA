# ICL 分布输入与原版执行

## 两份配置

| 文件 | 负责什么 | 默认值 |
| --- | --- | --- |
| [task_distribution.json](../src/robomme_icl/configs/task_distribution.json) | 任务顺序、各难度条数、任务参数候选、配额随机流和 episode seed | compiler_seed=20260907；起始seed=2000000000；每档8条 |
| [position_distribution.json](../src/robomme_icl/configs/position_distribution.json) | 位置／角度范围、拓扑、位置随机流、分层和初态筛选 | 版本2；compiler_seed=20260908；stratified；最多1024候选；净距0.005米 |

几何与时序不是配置覆盖项。实际素材由原版构建，任务由原版 `task_list`、`solve`、`evaluate`、`step` 执行。

## 任务参数

| 任务 | easy | medium | hard |
| --- | --- | --- | --- |
| BinFill | 投入1–3、生成4–6、目标色池1、场景色1 | 投入2–4、生成8–10、目标色池1–2、场景色2 | 投入3–5、生成10–12、目标色池2–3、场景色3 |
| RouteStick | 2–3段，非边界不立即折返 | 4–5段，非边界不立即折返 | 4–7段，允许立即折返 |
| VideoUnmaskSwap | 3容器、抓1–2、交换1–2 | 4容器、抓1、交换1–2 | 4容器、抓2、交换2–3 |
| VideoRepick | 3方块、重复1–3、交换1–2 | 3方块、重复1–3、交换2–3 | 15方块、重复1–3、不交换 |

BinFill 各档动态／静态均作为候选。目标颜色池不等于实际非零颜色数，次数分配沿用原版，允许池中某色目标为零。

配额算法位于 [sampling/tasks.py](../src/robomme_icl/sampling/tasks.py) 的 `plan_slots`：完整组合先轮转，余数按边际缺额分配；动态两态优先平衡。每任务占固定seed区段，筛选任务不重编号。

## 位置如何固定

[sampling/positions.py](../src/robomme_icl/sampling/positions.py) 按“任务、难度、拓扑、物体数”分组。组内每个可变维度的每一层恰好分配一次；候选只改变层内分位数。密集方块组协调两个轴的层编号，避免可用网格内重复分配同一二维格子。

`EpisodeSpec.placements` 保存 `x_fraction`、`y_fraction` 和 yaw；`layout.supports` 保存 JSON 对应的物理范围。对于方块和容器，创建原版素材后读取真实碰撞组件，计算各轴相对中心的最小／最大投影偏移：

```text
合法中心下界 = 支持区域下界 - 物体最小投影偏移
合法中心上界 = 支持区域上界 - 物体最大投影偏移
最终中心 = 下界 + 固定分位数 × (上界 - 下界)
```

区间为空则拒绝，不修改素材或把越界值裁到边缘。按钮与孔板使用配置的中心范围。最终位姿同时写入原版 actor 的 `initial_pose` 和 pose。

空间默认值：

| 对象 | x/y或拓扑 | 角度 |
| --- | --- | --- |
| BinFill按钮 | x=[-0.25,-0.15]，y=[-0.2,0.2] | 原版按钮姿态 |
| BinFill孔板 | x=[-0.05,0.15]，y=[-0.2,0.2] | [-20,20]度 |
| BinFill方块 | x=[-0.3,0.1]，y=[-0.25,0.25] | [0,360]度 |
| RouteStick | 中心[-0.1,0]、九点间距0.07 | 整排[-30,30]度 |
| Video三物体 | 三角形或直线，锚点窗口半宽0.07 | 布局[0,180]度 |
| Video四物体 | 矩形，锚点窗口半宽0.07 | 容器[0,90]度 |
| VideoRepick按钮 | x=[-0.25,-0.15]，y=[-0.05,0.05] | 原版按钮姿态 |
| VideoRepick hard方块 | x=[-0.3,0.1]，y=[-0.25,0.25] | [0,360]度 |

完整锚点坐标以位置 JSON 为准。原版颜色身份、目标选择、路径方向和最近邻交换逻辑继续由原版处理。

## 认证与输出

[workflows/prepare.py](../src/robomme_icl/workflows/prepare.py) 固定名额后搜索候选；实际初态必须通过 [validation/geometry.py](../src/robomme_icl/validation/geometry.py) 的真实碰撞组件筛选。合法候选运行原版完整任务，再用两个独立进程逐位核对全部操作和RGB。重复不一致时停止，不能换候选掩盖。

场景、套件与HDF5采用版本2；版本1以及不同位置协议不能直接加载。实际初态、任务参数、相机、素材与任务列表保存在完整记录，认证清单另保存初态摘要。分布图读取这些真实初态，不把分位数当世界坐标，也不把演示后位置当初态。

物理事件时序、抓放、按钮、强制复位和 `NO RECORD` 均来自原版。几何筛选只约束候选初态，不改变原版运行时成功／失败规则。

## 修改与运行

改任务数量或候选值只改任务 JSON；改位置域、角度或拓扑只改位置 JSON。两者任一变化都新建批次，不覆盖旧数据。

首次验证：

```bash
uv run scripts/prepare_suite.py --tasks BinFill --episodes-per-task 1 \
  --workers 1 --gpus 0 --output-dir artifacts/generated/robomme-icl/native-v2-smoke
```

通过后按 [四入口说明](README.md) 扩大规模。完整验收需要原版对照、自身重复、动作回放和连续reset，不能只看最终success或视频观感。
