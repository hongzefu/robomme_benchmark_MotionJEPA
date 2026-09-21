# 步 3 报告：十六环境切出 `sampling_config`（decision／native）（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 3，闸门 G2／G3（离线部分）与 P4 的 B↔C 部分。本报告即用户要求的「`src/robomme` 改完出 md 报告」。

## 一、形态：一个新工具 + 每环境两块

新增 [src/robomme/robomme_env/utils/sampling_config.py](../../../src/robomme/robomme_env/utils/sampling_config.py)：

- `split_sampling_config(override, native_default, decision_default)` 接受三种传法——不传、新格式 `{decision, native}`、旧格式 `{parameters, positions}`（等价于只给 `native`）。**保留旧格式**是为了不砸掉既有产物与工具（`scripts/injection/`、`--extract-config`），对应红线 R9。两块都 deepcopy，因为 gymnasium 会把 kwargs 字典的引用存进 `env.unwrapped.spec.kwargs`。
- `assert_native_decision(...)` 是原值模式的守卫：`decision` 必须逐键等于原值快照（红线 R7）。
- 全程不抽随机数；每个环境的解析调用点都落在 `torch.Generator()` 创建与 `super().__init__()` 之前——这里多抽或少抽一次会平移其后全部取值。

每个环境新增模块级 `native_blocks(cls) -> (decision, native)`，**外部导出与内部解析共用同一份**，杜绝两套真值漂移。

## 二、十六环境的 decision 归属（按第二节字段表逐条对）

| 环境 | decision（原值阶段＝原值） | 本轮不启用的拟修改值 |
|---|---|---|
| BinFill | layout_mode、color／spawn_cubes／put_in_numbers | clutter、12 块、投入 [5,7] |
| PickXtimes | color、number_range、目标方块与圆盘各自的采样区域 | 角落偏置、num [6,15]、distractor |
| SwingXtimes | number_range、color | number [4,10]、distractor |
| StopCube | move_interval_choices、stop_time_range | 只留 [60]、停止序号 [6,15] |
| VideoUnmask | pick_count、bin_layout_policy | pick=3、clutter bin、distractor |
| ButtonUnmask | pick_count、bin_layout_policy | pick=3、clutter bin、distractor |
| VideoUnmaskSwap | swap/pick 次数范围、swap_speed_multiplier(1) | swap [8,12]、pick=3、×1.5 |
| ButtonUnmaskSwap | swap/pick 次数范围、swap_speed_multiplier(1) | swap [6,8]、pick=3、×1.5 |
| PickHighlight | layout_mode/cube_region、highlight_count、spawn_count、block_color_policy | clutter、高亮 [5,7]、任意颜色 |
| VideoRepick | layout_mode、num_repeats_range、block_color_policy、swap 次数 | clutter、pick [4,6]、swap [8,12] |
| VideoPlaceButton | demo_object_count(1)、demo_return_policy、color/targets/swap | 演示 2 块、各自回原位 |
| VideoPlaceOrder | 同上 | 同上 |
| MoveCube | demo/execution 两套 {peg,cube} 位置策略、peg_yaw_range | 边角偏置、更大转角 |
| InsertPeg | peg_count、peg_offsets、near_target_distractor、peg_yaw_range | 4 根杆、近目标干扰杆、更大转角 |
| PatternLock | 演示时长（None）＋ grid/length 原值记录 | 最难档 20～30 s |
| RouteStick | 演示时长（None）；length/backtrack 按字段表属 native | 最难档 20～30 s |

## 三、被特意保留的「无效抽样」（红线 R8）

这些抽样的结果要么立刻被覆盖、要么被乘 0 消掉，删掉任何一个都会平移随机流，全部原样保留并在 `native` 里写明来历：

- `StopCube`：`randint(27, 33)` 抽完立刻被常量 30 覆盖。
- `InsertPeg`：`random_peg_idx = randint(0, 3)` 抽完立刻被 0 覆盖；长度与半径两次 `rand` 被 `(0.01 - 0.01)`、`(0.005 - 0.005)` 乘 0 消掉。
- `MoveCube`：同样被乘 0 消掉的长度／半径两次 `rand`；`dir_sample` 抽了但未使用。
- `ButtonUnmaskSwap`：三角／直线两套锚点各自的 x 偏移都要抽，**未被选中的那一套照样消费随机数**。

## 四、实测：十六环境的 A↔B 与 B↔C

全部在 greatlakes A40 的 4 个占位 job 上跑，每个环境取 `episode 0`，比较用全字段逐位对拍器。

| 环境 | A↔B | B↔C |
|---|---|---|
| BinFill | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| RouteStick | `sha_equal=1 field_mismatch=0`（尾迹恢复 40 步后） | `sha_equal=1 field_mismatch=0` |
| VideoRepick | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| VideoUnmaskSwap | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| PickXtimes | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| StopCube | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| SwingXtimes | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| VideoUnmask | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| ButtonUnmask | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| PickHighlight | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| MoveCube | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| InsertPeg | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| PatternLock | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| ButtonUnmaskSwap | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| VideoPlaceButton | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |
| VideoPlaceOrder | `sha_equal=1 field_mismatch=0` | `sha_equal=1 field_mismatch=0` |

**十六个环境的 A↔B 与 B↔C 全部逐字节相同。** 

**覆盖边界**：每环境只跑了 `episode 0` 一条，不代表 48 格全部已验；48 格与三种恢复模式在步 5b。

## 五、导出：`scripts/train_split_config.py`

`extract` 子命令把十六个环境的原值块汇成 [scripts/configs/newtask-v3/native_sampling.json](../../../scripts/configs/newtask-v3/native_sampling.json)（只读类属性与模块常量，不创建环境、不抽随机数），`--verify` 可比对文件与源码是否一致。实测 `SAMPLING_CONFIG_EXTRACT=WRITE ready=16 pending=0`。

## 六、测试

```bash
uv run --no-sync python -m pytest tests/lightweight/test_sampling_config_split.py -q   # 33 passed
```

每个环境三项：不传／新格式显式传原值／旧格式三种传法解析结果逐字相同；`decision` 被改一个键必须拒绝；快照与源码提取一致。另外全仓库已无 `self.configs[self.difficulty]` 直读，难度配置一律经 `decision`／`native` 消费（G2／G3 的「每个键都有落点」）。

## 七、下一步

步 4：`episode_spec` 的只读导出与原值回注（B↔C↔D）。机制已就位并通过单测——见 [src/robomme/robomme_env/utils/episode_spec.py](../../../src/robomme/robomme_env/utils/episode_spec.py)，其中回注模式**一定返回冻结值**（哪怕原抽样恰好抽出同样的数），从结构上杜绝方案点名拒绝的「重抽相同却绕过规格」。
