# robomme-ICL

新版与原版 `robomme` 并列安装，共享根目录的 `pyproject.toml`、`uv.lock` 和 `.venv`。四个新版环境直接继承 ManiSkill 基类，不继承旧任务；原版任务源码保持不变，旧生成与回放脚本已归档至 `scripts/legacy/`。数据与报告按批次独立管理。

## 使用流程

所有业务命令只放在仓库根目录的 `scripts/`。四个入口的参数、输出结构、视频和断点规则见 [scripts/README.md](../../scripts/README.md)。本包只提供可导入的实现，不注册控制台命令或模块运行入口。

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
uv sync --locked --extra dev
uv run scripts/prepare_suite.py --output-dir artifacts/generated/robomme-icl/my-run --gpus 0,1 --workers 32
uv run scripts/generate_dataset.py --suite artifacts/generated/robomme-icl/my-run/suite --output-dir artifacts/generated/robomme-icl/my-run
```

默认每任务24条、每档8条，共96个seed；先验证几何，再用两个新进程严格比较全部帧后发布清单。首次验证使用 `--tasks BinFill --episodes-per-task 1 --workers 1`。超过五分钟的运行按根 `AGENTS.md` 放入登记的detached tmux。

双GPU默认0,1、总并发32。每seed固定物理设备，生成、回放和reset继承绑定，不因worker数或完成顺序改变。不要设置 `CUDA_VISIBLE_DEVICES`；新配置认证通过 `--gpus` 选卡，源清单重新认证保持原卡。

任务分布和位置分布分别由 [task_distribution.json](configs/task_distribution.json) 和 [position_distribution.json](configs/position_distribution.json) 控制；可用 `--task-config`、`--position-config` 指向修改后的配置。次数配额和位置层在候选搜索前固定；拒绝候选不能改变次数、seed 或所属位置层。

```bash
uv run scripts/replay_dataset.py --input artifacts/generated/robomme-icl/my-run/hdf5_files --output-dir artifacts/generated/robomme-icl/my-run/replay
uv run scripts/plot_distribution.py --suite artifacts/generated/robomme-icl/my-run/suite --output-dir artifacts/generated/robomme-icl/my-run/distributions
```

生成失败保留证据且不换 seed。已完成文件仅在完整内容与认证信息核对通过后才能断点复用；坏文件或来源不明的文件不自动删除。回放读取 HDF5 自带的完整场景记录，不使用旧 train metadata。

```python
import robomme_icl

env = robomme_icl.make_env(
    task="BinFill",
    seed=2_000_000_000,
    suite="/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/scripts-v1/suite",
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

所有失败保持到 reset，成功不能与失败同时成立。演示不能增加执行计数。BinFill 初态必须空孔，方块实际从孔外进入并落稳后才能计数；隐藏对象的停车位不提供孔外观测证据。夹爪抬起正确物体、逐色入孔、完整抓放转换、Route 目标顺序与绕行侧别由真实观测判定；oracle 不能直接写入成功或计数。

固定单环境CPU物理、每seed绑定的GPU和线程数。每次 reset 重建物理场景以清除求解器历史，恢复所有对象、控制器、计数器和动画缓存。动作使用固定 screw 或固定初值/迭代预算的 CLIK，失败不转入随机规划。仿真与HDF5核对都在独立工作进程中执行，协调进程只接收摘要。

场景记录与认证绑定配置、源代码、依赖锁、关键库和设备驱动指纹。比较内容包括两路原始RGB、机器人与物体状态、关节动作、任务事件和终止步；日志时间和视频封装字节不属于轨迹比较。复现差异必须停止认证，不能通过换 seed 或放宽容差继续发布。

## 检查入口与实现边界

```bash
uv run python -m pytest tests/robomme_icl/ -q
uv run scripts/legacy/robomme_icl/preflight.py --output artifacts/reports/robomme-icl/<新几何报告名>.json
```

归档的 `preflight.py` 只做几何诊断，不创建认证套件。正式认证使用 `scripts/prepare_suite.py`。入口迁移引起源码指纹变化时，使用它的 `--source-suite` 对旧清单原spec重新认证并与旧记录逐位比较；不能覆盖旧数据或跳过版本检查。

原版调用只允许集中在 `legacy_bridge`；纯配置解析和编译不会导入旧环境或仿真库。首版只实现 joint_angle，不提供 ee_pose、waypoint 或 multi_choice 兼容分支。
