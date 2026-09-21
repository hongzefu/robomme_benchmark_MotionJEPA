# 步 2 报告：恢复原值默认路径（A↔B）（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 2、闸门 P2、口径 8。
本报告即用户 2026-09-21 要求的「`src/robomme` 改完出 md 报告」。

## 一、src/robomme 改动清单

| 文件／锚点 | 改了什么 | 为什么 | 怎么验的 |
|---|---|---|---|
| `src/robomme/robomme_env/RouteStick.py::step` | 白球尾迹 `end_step=cur_step + 10` → 读 `self._sampling["positions"]["tcp_trail"]`，默认值为官方的 **40** 步；`disk_radius` 一并外提 | 尾迹是会渲进 `front/wrist` 的 rgb 与 depth 的场景物体，属于进对拍的观测输入；写死任何值都让「原值对拍」与「产品想要的短尾迹」二选一 | A40 上复跑 A↔B：`H5_PARITY pair=RouteStick.A1\|RouteStick.B compared=1 sha_equal=1 field_mismatch=0` |
| `src/robomme/robomme_env/RouteStick.py::NATIVE_SAMPLING["positions"]` | 新增 `tcp_trail`（40 步 / 半径 0.005）与 `button_highlight`（40 步 / 1.002） | 把高亮渲染参数纳入原值快照，C 路才能显式传入核验；`button_highlight` 官方与现行本来一致，记下来防止被顺手改掉 | 源码级测试锁定 |

**录像器 `RecordWrapper.py` 未改动**（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 通过）。本步没有改其他任何 `src/robomme` 文件。

⚠ **需要用户知晓的行为变化**：本步之后，默认生成的 RouteStick 白球尾迹从 2026-09-12 决定的 10 步恢复为官方的 40 步。要切回 10 步，传 `sampling_config.positions.tcp_trail.end_offset_steps = 10` 即可，不必改源码；建议等原值对拍做完、进入新值模式时再作为 `decision` 打开。

## 二、A↔B 怎么做的

B 路＝**同一份官方编排代码**（`d53f21a…` 的 `_worker`、求解器选择与任务执行）加载**本工作副本的 `src`**。官方 `_worker` 只用 `repo_root` 定位 `src`，所以把 `repo_root` 指向工作副本即可，零镜像代码、零补丁；A↔B 的任何差异都只可能来自环境源码本身，不掺入编排差异。同时，`scripts/generate_dataset_newseed.py` 里的 `_binfill_demo_deliverable` 轨迹复制天然不在这条链路上，红线 R6 的「第一轮关闭轨迹复制」自动成立。

五个环境各取 `episode 0`（其中四个是相对官方改过的环境，`PickXtimes` 为未改动的对照），在 4 个占位 job 上并行跑。

## 三、实测结果

改动前：

| 比较对 | 结果 |
|---|---|
| `BinFill.A1↔B` | `sha_equal=1 field_mismatch=0` |
| `VideoUnmaskSwap.A1↔B` | `sha_equal=1 field_mismatch=0` |
| `VideoRepick.A1↔B` | `sha_equal=1 field_mismatch=0` |
| `PickXtimes.A1↔B`（对照） | `sha_equal=1 field_mismatch=0` |
| `RouteStick.A1↔B` | `sha_equal=0 **field_mismatch=736**`，另有 1 个 MP4 不同 |

RouteStick 的 736 处差异分布（来自 `compare/h5_pairs.jsonl`）：

```
184 obs/front_depth [value]      184 obs/front_rgb [value]
184 obs/wrist_depth [value]      184 obs/wrist_rgb [value]
timestep_count {'left': 200, 'right': 200}   missing 0/0
```

即 200 帧里 184 帧的四路相机观测不同，而 `action/joint_action`、状态、`info/*` 与帧数完全相同——「只改了渲染」的典型特征，与白球尾迹一致。

改动后复跑：

```text
H5_PARITY pair=RouteStick.A1|RouteStick.B compared=1 sha_equal=1 field_mismatch=0
```

**P2 在本步抽取的样本上通过。**

## 四、这一步同时澄清的三件事

1. **另三个改过的环境没污染默认路径**：`BinFill`／`VideoUnmaskSwap`／`VideoRepick` 的注入接口与新增的 `bin_collision` 检查全部挂在 `self._episode_spec is not None` 分支下，B 路一次都不会走到，与方案「现行碰撞检查新增拒绝条件只作只读诊断」一致。
2. **工具文件的改动是加通道而非改默认**：`utils/object_generation.py` 新增的 `fixed_xy/fixed_yaw` 路径只在传入固定位姿时生效；`utils/route.py` 的 `walk_config` 只在显式传入时做一致性校验；`utils/difficulty.py` 仅把 `xhard` 加进白名单（本轮不使用 xhard）。
3. **其余 12 个环境源文件与官方逐字节相同**，相对官方仍有差异的只有 8 个文件：`BinFill.py`、`RouteStick.py`、`VideoRepick.py`、`VideoUnmaskSwap.py`、`utils/bin_collision.py`（新增）、`utils/difficulty.py`、`utils/object_generation.py`、`utils/route.py`。

## 五、覆盖边界（不外推）

- 本步只对 5 个环境的 `episode 0` 做了 A↔B，**不代表 16 环境全部已验**；完整的 16 环境各一条在步 5a，48 格子集在步 5b。
- 4 个 Unmask 系环境的本地 metadata 被扩到 400 条，本轮不使用（A 路读官方冻结件，B／C／D 按冻结 manifest 的身份跑）。

## 六、测试

```bash
uv run --no-sync python -m pytest tests/lightweight/test_native_restore_step2.py tests/lightweight/test_train_split_parity.py -q
```

17 passed。新增 [tests/lightweight/test_native_restore_step2.py](../../../tests/lightweight/test_native_restore_step2.py) 三项源码级断言（不导入 sapien/torch）：尾迹必须是 40 步、`step` 必须读配置而不是写死、按钮高亮的 40 步不被顺手改动。

## 七、下一步

步 3：逐环境切出 `sampling_config`（`decision`／`native`），每环境先过 B↔C 再进下一个。C／D 路的运行通道本步已接好——`scripts/train_split_worker.py` 是官方 `_worker` 的最小镜像，**只多传 `sampling_config` 与 `episode_spec` 两个参数**，其余直接调用官方的 `_planner_classes`／`_execute_tasks`／`_raw_summary`，并在返回体里记录两个输入的散列供 G4 核验。
