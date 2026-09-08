# robomme-ICL

新版与原版 `robomme` 并列安装，共享根目录的 `pyproject.toml`、`uv.lock` 和 `.venv`。四个新版环境直接继承 ManiSkill 基类，不继承旧任务；旧任务、生成器、metadata 和回放入口不变。

## 使用流程

在本仓库根目录运行以下命令。`prepare` 先搜索候选，检查完整物体运动几何，再分别在两个全新进程中执行真实机器人轨迹；只有所有帧、任务结果和原始图像逐位相同才发布 `suite.json`。

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
uv sync --locked --extra dev
uv run robomme-icl prepare --output /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/validation24 --workers 4
```

默认每任务 24 条，easy、medium、hard 各 8 条，共 96 个新 seed。首次验证应先使用 `--tasks BinFill --episodes-per-task 1 --workers 1`，对四任务分别完成最小 smoke，再运行整批。超过五分钟的运行按根 `AGENTS.md` 要求放入登记的 detached tmux。

任务分布和位置分布分别由 [task_distribution.json](configs/task_distribution.json) 和 [position_distribution.json](configs/position_distribution.json) 控制；可用 `--task-config`、`--position-config` 指向修改后的配置。次数配额和位置层在候选搜索前固定；拒绝候选不能改变次数、seed 或所属位置层。

```bash
uv run robomme-icl generate --suite /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/validation24 --output-dir /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/dataset24 --workers 4
uv run robomme-icl replay --h5 /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/dataset24/<实际记录名>.h5 --output /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/replay/<新记录名>.h5
```

生成失败保留证据且不换 seed。已完成文件仅在完整内容与认证信息核对通过后才能断点复用；坏文件或来源不明的文件不自动删除。回放读取 HDF5 自带的完整场景记录，不使用旧 train metadata。

```python
import robomme_icl

env = robomme_icl.make_env(
    task="BinFill",
    seed=2_000_000_000,
    suite="/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/validation24",
)
obs, info = env.reset()
demonstration = info["demonstration"]
# RouteStick 动作为 7 维关节角；其余任务为 7 维关节角加 1 维夹爪控制。
# action 必须是精确维度的有限数组；env.step(action) 返回标准五项结果。
env.close()
```

## 配置与任务语义

| 任务 | easy | medium | hard |
| --- | --- | --- | --- |
| BinFill | 放入1–3个；场上4–6个、1色；目标1色 | 放入2–4个；场上8–10个、2色；目标1–2色 | 放入3–5个；场上10–12个、3色；目标2–3色 |
| RouteStick | 游走2–3段，非边界不立即折返 | 游走4–5段，非边界不立即折返 | 游走4–7段，允许立即折返 |
| VideoUnmaskSwap | 3容器；pick1–2；swap1–2 | 4容器；pick1；swap1–2 | 4容器；pick2；swap2–3 |
| VideoRepick | 3个同色方块；重复抓放1–3；swap1–2 | 3个同色方块；重复抓放1–3；swap2–3 | 三色各5个方块；重复抓放1–3；swap0 |

VideoUnmaskSwap 始终有红绿蓝三个藏块；三容器全占用，四容器有一个空容器，空容器角色按场景轮转。VideoRepick 的重复次数只统计评测阶段，演示阶段另有一次抓放。BinFill 保留任意颜色顺序，按实际投入的唯一方块逐色严格计数，再按按钮结束；动态出现时间也写入场景记录。

位置按任务的合法自由参数分层：BinFill 分别配置按钮、孔板、方块区域；RouteStick 保持九点拓扑并整排旋转；Video 任务保留指定布局及锚点附近窗口。候选只在原层内调整，位置均匀不表示任意工作台位置均可用。小样本未覆盖的次数组合会在报告中明确列出。

## 几何、判定与复现

容器视觉和碰撞使用同一份 compound 几何定义。中央 box 厚度30mm、顶部72mm，藏块尺寸不变，名义顶部净距8.67mm。初始布局与完整 swap 路径采用连续运动上界检查，另在物理子步中检查实际接触；正常支撑、抓取、投入和按按钮按角色允许，其他接触导致失败。接触读取异常不能视为安全。

所有失败保持到 reset，成功不能与失败同时成立。演示不能增加执行计数。夹爪抬起正确物体、逐色入孔、完整抓放转换、Route 目标顺序与绕行侧别由真实观测判定；oracle 不能直接写入成功或计数。

固定单环境CPU物理、GPU0渲染和线程数。每次 reset 重建物理场景以清除求解器历史，恢复所有对象、控制器、计数器和动画缓存。动作使用固定 screw 或固定初值/迭代预算的 CLIK，失败不转入随机规划。

场景记录与认证绑定配置、源代码、依赖锁、关键库和设备驱动指纹。比较内容包括两路原始RGB、机器人与物体状态、关节动作、任务事件和终止步；日志时间和视频封装字节不属于轨迹比较。复现差异必须停止认证，不能通过换 seed 或放宽容差继续发布。

## 检查入口与实现边界

```bash
uv run python -m pytest tests/robomme_icl/ -q
uv run python -m robomme_icl.suite.preflight --output /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/reports/robomme-icl/<新几何报告名>.json
```

`suite.preflight` 仅证明记录中物体的几何条件，不创建认证套件，不代表机器人可达或真实物理通过。正式认证必须使用 `prepare`。

原版调用只允许集中在 `legacy_bridge`；纯配置解析和编译不会导入旧环境或仿真库。首版只实现 joint_angle，不提供 ee_pose、waypoint 或 multi_choice 兼容分支。
