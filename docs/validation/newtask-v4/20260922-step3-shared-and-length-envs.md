# V4 步 3（一）：共用底座 + PatternLock / RouteStick 的 xhard

> 红线 N1 的逐步报告。起点 `12.64`（`2fa3742`）。录像器未改（`RECORDER_FROZEN=PASS`）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/subgoal_language.py::get_subgoal_with_index` | 改为查 `_ORDINALS`（20 项）＋`_ordinal_word` 规范英文序数兜底 | E2：PickXtimes `num [6,15]`、BinFill `put_in [5,7]` 会超出原 idx<10 上限 | `test_subgoal_ordinal_v4.py`：前十项与改前 if/elif 逐字相同、11~20、`21st/22nd/23rd/113th/111th/112th`、负数报错、张量下标 |
| `src/robomme/robomme_env/utils/xhard.py`（新增） | `DISTRACTOR_COLORS`（黄/青/品红，B2）与 `corner_push`（边角偏置映射） | 2.0①：干扰色全局一致；边角采样仓库里没有现成工具 | `test_xhard_utils.py`：`corner_push(u,0) is u`、单调／保端点／对称、越界报错、色池逐字 |
| `utils/object_generation.py::spawn_random_cube` | 新增形参 `corner_bias=0.0`；非零时对已抽出的 `u1/u2` 做确定性映射，**不多抽随机数** | PickXtimes 目标方块推向边角要用 | 默认 0 时整段 `if` 不进入，与原均匀采样逐字等价；reset 探针 144 条零差异 |
| `PatternLock.py::config_xhard`（新增，进 `configs`） | `{"grid": 5, "length": [20, 25]}`；路径取值点带 `decision_key=path_length_range.<难度>` | B8：布局与搜法都不动 | xhard reset 冒烟 6/6，节点数 20/20/22/20/23/22，kind 为 `native-newvalue/1` |
| `RouteStick.py::config_xhard` | 覆盖旧值 `[8,10]` 为 `[12,15]`（A7/B9）；段数取值点带 `decision_key` | B9 | xhard reset 冒烟 6/6，L = 13/14/12/13/12/12 |
| `scripts/parity/train_split_config.py` | 默认导出改到 `scripts/configs/newtask-v4/sampling_config.json`；v3 快照冻结不再覆盖 | 源码加了 xhard 条目后 v3 快照必然与源码不符；v3 是 V3 证据，不能改 | `extract` 写出 v4 快照 `sha256=50e7b975…`；`test_snapshot_matches_source` 改看 v4 |
| `scripts/parity/v4_reset_probe.py`（新增） | 原三档身份只 `reset`，抓「规格文档＋取值点轨迹＋generator 终态＋任务表＋全部 actor 位姿（float.hex）」，两次结果逐字节比 | V1 的本机快速前置：每改一组环境都要先证明原三档 reset 零差异 | 同一代码连跑两次 `RESET_REGRESSION=PASS`；见下 |

## 二、原三档零差异

```bash
# 基线：在 13e5151 的临时 worktree 里采（改动前的原始代码）
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --out artifacts/newtask-v4/probe/base-13e.json
# 当前代码
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --out artifacts/newtask-v4/probe/cur.json
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json artifacts/newtask-v4/probe/cur.json
# RESET_REGRESSION=PASS compared=144 diff=0 missing=0
```

144 条全部 reset 成功，每条约 1.5 s。

## 三、V1 口径变更（用户 2026-09-22）

用户原话「原值回归只需要在本机器跑」。计划口径 10、V1 行、N7、盲区清单已同步：V1 改为本机上 `13e5151` 基线与改动后代码
各跑一遍 144 条（B 路、单 worker），HDF5 逐位比；不再对 A40 的 V3 留档。基线运行已在 tmux 会话 `v4-v1-base` 里起跑
（`artifacts/newtask-v4/v1-base-13e/`，日志 `artifacts/logs/v4-v1-base-13e.log`）。

## 四、测试

- 轻量全量：46 failed / 522 passed / 22 skipped / 12 errors（123 s）；失败集合与基线完全相同（8 个文件、同样计数）。
