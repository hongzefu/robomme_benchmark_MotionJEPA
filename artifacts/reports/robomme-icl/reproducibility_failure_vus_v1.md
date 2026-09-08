# VideoUnmaskSwap 首轮严格复现失败记录

本报告记录 `smoke-four-v1` 中 `VideoUnmaskSwap` 的既有失败证据。两次运行虽然最终都返回 `success=True`、`fail=False`，但物体位姿、后续动作、机器人状态和 RGB 均出现字节差异，**严格复现认证失败**。不能用差值较小或任务都成功替代严格认证。两个原始 HDF5 均保留，不覆盖、不删除。

本报告初次写入时，`ICLBaseEnv.finish_animation()` 已改为固定排序恢复刚体，并使用冻结清单的交换端点，修复后的复测仍在进行。后续结果以文末追加记录为准，原失败结论保持不变。

## 失败产物与运行口径

任务为 `VideoUnmaskSwap`，难度 `easy`，`seed=2000000002`，`candidate_index=0`。两次运行均有 262 帧，EpisodeSpec 和运行指纹相同。

| 产物 | 大小（字节） | 内容摘要 |
| --- | ---: | --- |
| [第一次运行](../../generated/robomme-icl/smoke-four-v1/certification/VideoUnmaskSwap/easy/0000/candidate_0000/repeat_0_infra_0.h5) | 103424706 | `0a44c607285a5ed58afde88010d8d54ad5a422f5a7a2bbadc42b1ab0d02b77cd` |
| [第二次运行](../../generated/robomme-icl/smoke-four-v1/certification/VideoUnmaskSwap/easy/0000/candidate_0000/repeat_1_infra_0.h5) | 103417454 | `1845abb2e445d2891782cb3e1a0e0425284974dfaf59a2c16a89300be59bd4d1` |

两次记录均保存以下来源与运行指纹：

- `source_commit=1143477cba681bbb803b52324828634719a3f5a0`；这是运行时 Git HEAD，具体实现状态由源码内容摘要另外绑定。
- `spec_hash=8fc53dbc1f402a6b1abc017572c08cf97d7d49207c525d0e4fcde11a592f7cba`。
- 新版源码摘要：`bdba673eb9fe51b89c74df0f1721c71374933eb808225c937dc5525b7eca8dab`。
- 原版源码摘要：`84244136a262eec164e60beac38abb02a1f630f8de4b6ddb908b33e1d3e00378`。
- `uv.lock` 摘要：`983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`。
- Python 3.11.14、ManiSkill 3.0.0b21、SAPIEN 3.0.2、torch 2.9.1、NumPy 1.26.4、mplib 0.1.1、h5py 3.15.1；本机 RTX 6000 Ada，驱动 570.211.01。
- 控制频率 20 Hz，物理频率 100 Hz，每个控制步包含 5 个物理子步。

同一轮中，BinFill 的两次 638 帧记录内容摘要完全相同，RouteStick 的两次 451 帧记录也完全相同；该事实不能替代 VideoUnmaskSwap 的失败结论。

## 首次分叉与时间线

下表中的“帧索引”从零开始，`info.step` 是记录中实际保存的控制步。演示结束时另保存一帧无动作的执行阶段初始观测，因此二者不始终相差 1。

交换对象为 `container_0` 和 `container_1`：第一次交换相对时间为 `20→70`，第二次为 `80→130`，第二次交换使两容器回到原槽位。`container_2` 是本局真正应提起的目标，未参与这两次交换。

`Oracle.demonstrate()` 先执行一个控制步检查初始场景，然后 `Oracle._swap_demonstration()` 开始动画，因此动画时间原点是 `info.step=1`。相对结束时间 130 对应全局控制步 131。

| 帧索引 | `info.step` | 阶段 | 实测结果 |
| ---: | ---: | --- | --- |
| 0–129 | 1–130 | demonstration | 已记录的所有字段逐字节相同。 |
| 130 | 131 | demonstration | 两次运行均到达第二次交换终点；所有字段仍相同。 |
| 131 | 132 | demonstration | `finish_animation()` 恢复动态刚体并恢复藏块后的第一个控制步；四个物体位姿同时首次分叉，动作、qpos、qvel、RGB 和 info 此时仍相同。 |
| 150 | 151 | demonstration | 最后一帧演示，物体位姿差异已持续存在。 |
| 151 | 151 | evaluation | 新阶段初始观测，`joint_action=None`，没有额外执行控制步。 |
| 161 | 161 | evaluation | `joint_action`、机器人 qpos、qvel 首次出现差异。 |
| 168 | 168 | evaluation | wrist RGB 首次不同：462 个通道值不同，首次最大差为 1。 |
| 217 | 217 | evaluation | base RGB 首次不同：3 个通道值不同，首次最大差为 1。 |
| 261 | 261 | evaluation | 两边最终均 `success=True`、`fail=False`，但严格复现仍失败。 |

第一处比较器报错为 `frames/131/observation/actor_poses/container_1`。同一帧实际同时分叉的还有 `container_2`、`cube_0` 和 `cube_1`，不是只有该容器不同。四者的位姿数组均为 `float32`、形状 `(7,)`，依次存储 xyz 和 wxyz。

| 物体 | 首帧不同元素数 | 首帧七维数组最大绝对差 |
| --- | ---: | ---: |
| `container_1` | 6 | `2.9802322387695312e-08` |
| `container_2` | 7 | `1.0110937864737934e-06` |
| `cube_0` | 5 | `2.4882501747924834e-07` |
| `cube_1` | 6 | `1.4711235962749925e-07` |

以上七维数组同时包含位置和无量纲四元数分量，其最大差不能全部解释为米。`container_0` 与 `cube_2` 在整个 262 帧序列内保持字节相同。所有 info，包括阶段、任务事件、成功/失败标志和禁止接触列表，两次运行始终相同。

## 后续差异幅度

| 字段 | 首次不同帧索引 | 不同帧数 | 全序列最大绝对差 |
| --- | ---: | ---: | ---: |
| `joint_action` | 161 | 101 | `2.2682089474901357e-04` |
| qpos | 161 | 101 | `1.7642974853515625e-04` |
| qvel | 161 | 101 | `2.696773037314415e-03` |
| wrist RGB | 168 | 93 | 164（uint8 通道值） |
| base RGB | 217 | 36 | 189（uint8 通道值） |

目标 `container_2` 的位置分量最大差为 `3.589121624827385e-04` 米，出现在帧索引 261 的 y 分量；四元数分量最大差为 `5.838877223141026e-04`，出现在帧索引 250。说明交换后刚体分叉进一步传播到了目标抓取规划、机器人运动和最终图像，不是仅存在于无关元数据的差异。

## 定位与修复状态

失败版本的 [ICLBaseEnv.finish_animation()](../../../src/robomme_icl/envs/base.py) 使用 `list(self._kinematic - self._parked)` 遍历集合，再调用 `restore()` 将刚体由 kinematic 改回 dynamic。字符串集合的迭代顺序可随独立 Python 进程变化，因此刚体恢复顺序没有被确定性协议固定。旧实现还在循环中重新调用 `snapshot()`，以刚体求解器的末帧近似位姿作为恢复位置。

证据能够确定分叉发生在交换终点之后、恢复动态刚体后的第一个控制步；它与上述恢复顺序问题一致。仅凭这两份记录不能把因果修复效果视为已验证。

当前修复使用 `sorted(self._kinematic - self._parked)` 固定恢复顺序，并在恢复前通过 `pose_at_step(self.episode_spec, end)` 一次计算冻结的交换端点。`restore()` 仍会将线速度和角速度清零。这里没有放宽比较精度、没有屏蔽物体状态或 RGB，也没有通过重新抽 seed 绕过旧失败。

修复后需要在新的输出目录重新运行同一规格的独立进程认证，逐帧比较所有字段；原 `smoke-four-v1` 两份失败记录继续作为失败证据保留。本报告初次写入时复测尚在进行。

## 复核命令

在仓库根目录执行以下只读命令，原失败数据应继续被严格比较器拒绝：

```bash
command -v uv
UV_CACHE_DIR="$PWD/.cache/uv" uv run --no-sync python - <<'PY'
from pathlib import Path
from robomme_icl.io.hdf5 import read_episode, assert_records_identical

root = Path("artifacts/generated/robomme-icl/smoke-four-v1/certification/VideoUnmaskSwap/easy/0000/candidate_0000")
assert_records_identical(
    read_episode(root / "repeat_0_infra_0.h5"),
    read_episode(root / "repeat_1_infra_0.h5"),
)
PY
```

数据分析命令均只读打开 HDF5。原始帧数、来源摘要、首次差异字段和最大差已通过独立遍历记录复核；这些诊断命令退出 0，仅代表分析完成，不能解释为原数据严格认证通过。

上述严格复核命令已实跑，退出码为 **1**，原始异常为：`ReproducibilityError: frames/131/observation/actor_poses/container_1: 数组字节不同`。这是对原失败证据的预期拒绝，未修改任何 HDF5。

## 追加：固定顺序与冻结端点的独立复测

`smoke-vus-v2` 中的[第一次复测](../../generated/robomme-icl/smoke-vus-v2/certification/VideoUnmaskSwap/easy/0000/candidate_0000/repeat_0_infra_0.h5)与[第二次复测](../../generated/robomme-icl/smoke-vus-v2/certification/VideoUnmaskSwap/easy/0000/candidate_0000/repeat_1_infra_0.h5)已完成。将上面的只读复核命令改为这两个文件后实跑，退出码为 **0**，262 帧全部通过类型、形状和字节严格比较，包括 RGB；双方终态均为 `success=True`、`fail=False`。

此次复测仍使用 `seed=2000000002` 和原 `spec_hash=8fc53dbc1f402a6b1abc017572c08cf97d7d49207c525d0e4fcde11a592f7cba`，没有改换候选。两份记录的内容摘要均为 `42edf47f598b7cef61f46297d1744f8daa58a59fc3c58f80a98890ac796b5cb1`，新版源码摘要均为 `d871ec01cedba1d90983a3cca1d06e667949a03ce12e3f3423c1b79ee7c2437c`。

该结果证明固定顺序与冻结端点后的这一条规格在这两个独立进程中严格一致；不能外推为其他规格已认证。其后 I/O 恢复边界的代码调整会再次改变源码指纹，因此最终发布仍须以最终冻结源码重新认证，不能直接把本次较早的指纹作为最终版本认证。原 `smoke-four-v1` 失败产物继续保留。
