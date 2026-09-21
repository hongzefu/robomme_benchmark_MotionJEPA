# 步 0 留档：切分支与身份冻结（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 0，闸门 G1。本步只读官方 Git 对象、只写冻结产物，未启动仿真、未改动 `src/robomme/`。

## 一、分支与冻结基线

| 项 | 值 |
|---|---|
| 新分支 | `newtaskRelease-v3` |
| 父提交 | `ce72b04fdb7806dbc98de2baa3c92118b98e6902`（`11.33 登记四个4CPU占位job编号`） |
| 官方基线提交 | `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`（`RoboMME/robomme_benchmark` 的 `dataset-gen`） |
| 官方对象来源 | 本仓库已含该提交对象，`git show <ref>:<path>` 直接读取，未联网取回 |
| `pyproject.toml` | `d03537d6c77a8d8213bc881da6ac470b2d8a80cf5f883df587d9df634374db36` |
| `uv.lock` | `ff0ffd847a55f77d61c3d11efe4ad11e8776534e044f0ddb2b22396d838fa5f3` |
| 录像器 | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 通过（R2 冻结） |
| 本机设备 | 2×NVIDIA RTX 6000 Ada Generation，驱动 570.211.01，Python 3.11.14 |
| 本机存储 | `/data` 14T，已用 12T，可用 1.8T（87%） |

两个锁文件散列与方案 9.5 记录的指纹一致，未重建环境。本机设备只用于离线核验与脚本开发；按方案第四节，五路生成全部在 greatlakes `spgpu` 的 A40 上跑。

## 二、新增入口与冻结产物

新增 [scripts/train_split_parity.py](../../../scripts/train_split_parity.py)，三个子命令：`freeze-identities`（本步已实现）、`run` 与 `compare`（步 1b 实现，当前只有 `--help` 与参数校验）。

实跑命令与输出：

```bash
uv run --no-sync python scripts/train_split_parity.py freeze-identities --output artifacts/train-parity/v3-native
```

```text
TRAIN_IDENTITY=PASS tasks=16 rows=1600 mismatch=0
TRAIN_SUBSET=PASS tasks=16 per_cell=3 rows=144
# 非公式 seed 170 条；全量恢复配置 z=48 xy=48 off=1504；子集恢复配置 z=48 xy=32 off=64
# records_sha256=a57655d601c7e974c688b2b5c3602e7eb8606e2bd312dcc4ba00a1abb29d73bf
```

冻结产物（git 跟踪，本机与 NFS 副本共用同一份）：

- `scripts/configs/newtask-v3/official_train/record_dataset_<env>_metadata.json`：十六份官方 metadata 原文字节，未改一字。
- `scripts/configs/newtask-v3/official_train/sources.json`：来源仓库、提交、每份文件的 git blob 与 SHA-256。
- `scripts/configs/newtask-v3/train_manifest.json`：1600 条全量身份，逐条带 `recovery_mode`、`formula_base_seed`、`seed_matches_formula`。
- `scripts/configs/newtask-v3/subset_manifest.json`：144 条运行子集，附 `episodes_by_task` 与恢复配置计数。
- `artifacts/train-parity/v3-native/freeze_report.json`：运行留档（时间、argv、判定计数、全部冻结文件散列）；`artifacts/` 不入 git。

`--verify` 模式复跑一次，全部冻结文件字节一致，可用作后续步骤的 G1 回归闸门。

## 三、G1 实测结论

- **身份双向相等**：manifest 与官方 metadata 从原始字节独立再解析后逐条顺序比较，再做集合双向比较（抓重复、漏项、额外项），`mismatch=0`。
- **170 条非公式 seed 原样保留**：与方案 9.1 实读结论一致，例如 `BinFill/episode_3` 为 `difficulty=hard, seed=4301`，公式值 `4300` 未被替代。
- **串接散列命中**：十六份 records 按 `ALL_TASKS` 规范序串接后按 `json.dumps(sort_keys=True, separators=(',',':'))` 取 SHA-256，等于方案记录的 `a57655d6…`。
- **子集规则固定**：每 task 每难度按官方 metadata 原顺序取前 3 条，十六环境命中的 episode 集合一律为 `[0,1,2,3,4,6,7,10,11]`（easy `0,1,4`、medium `2,6,10`、hard `3,7,11`），与方案第四节实读一致；不符即报错。
- **恢复配置计数**：全量 z=48／xy=48／off=1504，子集 z=48／xy=32／off=64，与方案口径 3 一致。子集不含每环境 episode 5，共 16 条配置 xy 恢复的身份未纳入（方案已登记的覆盖缺口）。

## 四、来源文件散列

| 环境 | git blob | SHA-256（前 16 位） | 字节 |
|---|---|---|---|
| PickXtimes | `10d4f7d326e1` | `8e74205d7b2a6e44` | 11020 |
| StopCube | `89af82eae119` | `a25b595c7db754fe` | 10828 |
| SwingXtimes | `4bf38b58b015` | `800fe030a9602a8e` | 11141 |
| BinFill | `363b9718e1c9` | `9f8d193a7792cbc8` | 10747 |
| VideoUnmaskSwap | `61c4a6d6d90f` | `4bc3157f2df0d136` | 11565 |
| VideoUnmask | `bd74fb0eb58a` | `e2b220cd931df411` | 11171 |
| ButtonUnmaskSwap | `3194c886496f` | `ab83b540638d4314` | 11686 |
| ButtonUnmask | `ed832369f6fc` | `1dce0d86fc611bd7` | 11292 |
| VideoRepick | `c4f0a052c4bf` | `bf4e30c0f858fb6c` | 11201 |
| VideoPlaceButton | `d8430a693925` | `2f86ccd55df940ef` | 11716 |
| VideoPlaceOrder | `a1038a66d21a` | `26f4ec3db11dc029` | 11615 |
| PickHighlight | `65c657351f71` | `4ecfe6d79ec86bb1` | 11413 |
| InsertPeg | `c45da812a304` | `bb7b9e16fbcd3b31` | 11009 |
| MoveCube | `8086d2037abb` | `ffdd7404b3aa10ea` | 10908 |
| PatternLock | `d6dfe1ced459` | `636431f1fa2375dd` | 11211 |
| RouteStick | `4ebccde5133e` | `758fed27d275d167` | 11110 |

## 五、测试

```bash
uv run --no-sync python -m pytest tests/lightweight/test_train_split_parity.py -q
```

新增 [tests/lightweight/test_train_split_parity.py](../../../tests/lightweight/test_train_split_parity.py)，8 项全过（0.03 s）：恢复模式规则、全量 1600 条结构与 170 条非公式 seed、子集前 3 条规则与回指全量行、把实际 seed 换成公式值必须判 mismatch 的反例、metadata 结构反例（重复 episode／条数不符／多余字段／非法难度）、per_cell 不足时报错、`--paths`／`--shard` 参数反例、以及 `run` 拒绝不在子集内的 `episode 5`。

## 六、本步之后的状态

- G1 通过；P0／P1 等需要 A40 的闸门尚未开始。
- 占位 job：61673583／61673584／61673585 RUNNING，61673586 因 chaijy2 账户 80 CPU 配额用满仍在 `AssocGrpCpuLimit` 排队。按用户决策，步 1b 先用 3 个 RUNNING 的 job 跑，`NODE_PARITY` 先出 `jobs=3` 版判定行，第 4 个 job 起来后补跑第 4 份 A1 再改写为 `jobs=4`。
- 下一步：步 1a 冻结历史证据，随后步 1b 实现 `run`／`compare` 与比较器范围适配（G5 离线夹具），再上集群跑 `BinFill/easy/episode_0` 的 A1／A2 冒烟。
