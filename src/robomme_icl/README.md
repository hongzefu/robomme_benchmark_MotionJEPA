# robomme-ICL

新版只负责分布输入、记录和数据流程。四个任务分别继承原版 `BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick`；素材、任务列表、动作、判定与显隐事件来自原版。

## 从哪里读代码

| 问题 | 入口 |
| --- | --- |
| 两个 JSON 固定哪些输入 | [config.py](config.py)、[configs/](configs/) |
| 次数、seed 和位置层如何分配 | [sampling/tasks.py](sampling/tasks.py)、[sampling/positions.py](sampling/positions.py) |
| 一局环境保存什么 | [specs.py](specs.py) 的 `EpisodeSpec` |
| BinFill 如何接原版 | [envs/bin_fill.py](envs/bin_fill.py) |
| 另外三个任务如何接原版 | [envs/route_stick.py](envs/route_stick.py)、[envs/video_unmask_swap.py](envs/video_unmask_swap.py)、[envs/video_repick.py](envs/video_repick.py) |
| 位置如何套到真实素材 | [native/parameters.py](native/parameters.py) 的 `NativePlacements` |
| 演示与执行怎样运行 | [envs/wrapper.py](envs/wrapper.py)、[execution/episode.py](execution/episode.py) |
| 哪些步骤会被保存 | [execution/recording.py](execution/recording.py) |
| 认证、生成、回放与进程调度 | [workflows/](workflows/) |
| 原版对照与逐位验证 | [native/reference.py](native/reference.py)、[validation/](validation/) |
| HDF5、套件和恢复凭证 | [io/](io/) |

调用顺序为：

```text
两份 JSON → 任务配额 → 位置分位数 → EpisodeSpec
         → 对应原版子类 → 原版 task_list/solve/evaluate/step
         → 完整操作记录 → 认证、生成、回放与视频
```

## 配置边界

任务 JSON 保留任务顺序、各难度条数、次数候选和 seed 分配。默认每任务三档各8条，共96条。BinFill 的 `target_color_count` 是原版选中的目标颜色池大小；实际非零目标颜色数可能更少，记录原版分配结果。

位置 JSON 为版本2，保留范围、角度、拓扑、分层及候选预算；不再包含 `geometry` 或 `schedule`。按钮和孔板配置中心位置；方块和容器配置完整物体支持区域。位置分位数先固定，创建素材后根据原版真实碰撞组件的旋转投影计算合法中心区间。每个候选只能在原层内取值，不改变任务次数或 seed。

原版对象的最终位置同时写入 `initial_pose` 和当前 pose，确保 ManiSkill 建场景时不会恢复到临时位置。实际初态保存在记录的 `initial_state`，不是从配额或演示结束位置推测。

`safety_clearance` 只用于初态候选筛选。运行时遵守原版成功／失败条件，不额外增加新版碰撞、落稳或抓持判据。

## 接口和版本

公开入口保持 `make_env(task, seed, suite)`，仅接受已认证、指纹匹配的版本2套件。旧清单必须重新编译认证，旧数据保留。

```python
from robomme_icl import make_env

env = make_env(task="BinFill", seed=2000000000, suite="artifacts/generated/robomme-icl/native-v2/suite")
observation, info = env.reset()
demonstration = info["demonstration"]
env.close()
```

RouteStick 使用7维关节动作；其余任务使用7维关节角加1维夹爪动作。演示由原版 `DemonstrationWrapper` 在 reset 内执行。再次 reset 会重建原版实例，以清除上一局对象、计数器和事件缓存。

四个业务脚本、参数及命令见 [scripts/README.md](../../scripts/README.md)。

## 记录协议

版本2 HDF5保留 `setup/steps`，每项操作的 `info.operation` 为：

- `step`：真实物理步，保留输入动作、原始双路RGB和完整状态。
- `evaluate`：调用方原本就需要的显式判定，保留 `solve_complete_eval`。
- `reset_complete`：演示结束的边界，附初始素材、状态、相机参数、任务列表、原版参数和运行配置。

记录器给 `get_obs` 传入已有 info，避免它隐式再调用 evaluate。原版 `NO RECORD` 与终止时的内部额外一步仍完整保存；`deliver_frame` 控制视频交付。回放使用原版包装器，使额外终止步自然产生，逐项核对整段内部操作。

原版高亮对象名包含进程地址。记录层按“所属目标＋实例号”建立一一对应的稳定标识，不修改原版对象；原始名字映射在 HDF5 中独立保存和校验。

## 验证口径

固定原版为 `76ae12bf1e71f79e1c3f608eede10ac7430b406f`。原版对照在独立进程中逐个校验源码 blob，只注入允许覆盖的输入，不调用新版任务子类。

素材、初态、相机参数、任务列表、实际参数、事件时间线、所有操作和原始RGB分别比较。原版自身有特殊判据时保留原判据，例如容器抓起只按原版高度条件判断。自身重复运行相同与原版行为相同分别报告。

```bash
command -v uv
uv run python -m pytest tests/robomme_icl/ -q
ICL_NATIVE_SMOKE=1 uv run python -m pytest tests/robomme_icl/test_native_runtime.py -q
```

普通测试中的真实运行跳过项不算验收通过；正式批次还需完成原版对照、回放和连续 reset。
