# 步 1b（上半）留档：A 路编排、HDF5 对拍器与比较器范围适配（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 1b 的离线与本机部分，闸门 G5 已过；**P0／P1 属于 A40 上的判据，本文的本机结果只是调试参考，不进判据**（方案第四节：sm_89 与 A40 的 sm_86 不逐位一致）。未改动 `src/robomme/`。

## 一、新增的三个文件

| 文件 | 作用 |
|---|---|
| [scripts/train_split_runner.py](../../../scripts/train_split_runner.py) | A 路隔离运行器：加载官方固定源码、按冻结身份构造官方 `EpisodeJob`、用官方自己的 `ProcessPoolExecutor(spawn)` 调官方 `_worker` |
| [scripts/train_split_comparison.py](../../../scripts/train_split_comparison.py) | 官方两个比较器的稀疏范围适配（9.6），`check` 子命令输出 `COMPARATOR_SCOPE` |
| [scripts/comparator_fixtures.py](../../../scripts/comparator_fixtures.py) | G5 离线夹具：连续对齐、稀疏精确对应、非法范围拒绝 |

`scripts/train_split_parity.py` 补齐 `run` 与 `compare` 两个子命令。

## 二、A 路怎么做到「原链路」

方案红线 R4 要求 A1／A2 用独立进程加载固定 `d53f21a…` 源码执行原 `_worker`。实现要点：

1. `run` 用 `git archive <ref> | tar -x` 把官方整棵树导出到 `<output>/official-src`（7.5 MB），并写入 `.official_tree` 标记（本次为 `1d4c1369…`），重复运行复用同一棵树。
2. 官方 `generate_dataset.generate_dataset()` 会先 `_ensure_layout()` 要求 `data/robomme_data_h5` 存在，而该发布集当前缺失；但 **`_worker` 本身不依赖它**，且方案比较的正是 `hdf5_files/<task>_ep<ep>_seed<seed>.h5` 原始产物，因此运行器只调 `_worker`，不做官方的合并、报告与发布集比较。
3. 官方 `_worker` 会 `sys.path.insert(0, <repo_root>/src)`。本工作副本把 `src` 以 editable `.pth` 注入了 venv，为防遮蔽：运行器先把含 `robomme/__init__.py` 的工作副本路径从 `sys.path` 移除（`spawn` 子进程继承父进程 `sys.path`），再用干净子进程探针确认 `import robomme` 解析到官方源码，落档到结果 JSON 的 `robomme_module`。本次实测值为 `…/official-src/src/robomme/__init__.py`。
4. 身份不重算：运行器再调一次官方 `read_train_metadata()`，逐条核对 manifest 的 `seed`／`difficulty`，不符即停。
5. 与官方编排保持一致的细节：父进程钉 `CUDA_VISIBLE_DEVICES`、`ProcessPoolExecutor(mp_context=spawn)`、`worker_dir` 命名 `<task>_episode_<n>`、结果按 `(task, episode)` 排序、异常分类与官方 `_worker` 返回体一致。
6. 续跑：worker 目录已存在且已有 HDF5 的身份直接跳过（job 被回收后从缺失身份续跑），存在但无 HDF5 则报错而不是静默复用。

## 三、HDF5 对拍器

按方案第二部分「十一」实现 `compare_h5_pair`：先整文件 SHA-256，相同即返回 `sha_equal=1`；不同则 `visititems` 收集两边完整路径集合，逐个比 group／dataset 的 attribute、`dtype`、`shape` 与原始字节，**浮点按位模式比较、不设容差、NaN 也按位比**，`object` 字符串解码后比；时间步数不同先记差异再只比共有步；每处差异记录路径／dtype／shape／首个不同元素的展平索引。结果落 `compare/h5_pairs.jsonl`，汇总行为 `H5_PARITY pair=… compared=N sha_equal=k field_mismatch=m`。

`compare` 同时比身份目录下的伴生文件（MP4、图像、JSON）散列，差异计入 `sidecar_mismatch` 单列报告；`--gate BASELINE_REPEAT|NODE_PARITY` 额外输出闸门判定行；`--history` 按 R1a 的四类可比字段与步 1a 的历史投影逐条比对。

## 四、G5：比较器范围适配

```bash
uv run --no-sync python scripts/train_split_comparison.py check --official-root <official-src> --output artifacts/train-parity/g5-fixtures
COMPARATOR_SCOPE=PASS contiguous_mismatch=0 sparse_mismatch=0 invalid_accepts=0
# 连续范围对齐：joint_vector_count=12，passed=True
# 稀疏范围：向量数 32、非零元素 1、最大差 0.0010000000000047748、错误 1 条
```

- **不改官方源文件**：适配器从冻结源码目录 `import` 原模块，直接复用 `add_error/episode_groups/timestep_indices/_audit_metadata/_audit_file/_summary` 等比较核心，只重写最外层的范围守卫与预期集合；`diff` 子命令可打印逐函数最小 diff（差异集中在 `episodes must be a contiguous range starting at 0` 这条守卫与按 task 的显式 episode 列表）。
- **连续范围**：与官方原函数逐字段同结果（合同校验与动作比较各一次比对）。
- **稀疏范围**：官方原函数照旧拒绝 `[0,1,2,3,4,6,7,10,11]`（证明守卫仍在原处）；适配器在注入已知差异（episode 6 的 timestep 2、元素 5 差 `1e-3`；episode 10 少一帧）时，向量数、`delta!=0` 计数、最大差定位、错误条目与 `1e-8` 判定全部精确对应；干净夹具通过且不会把未选中的 episode 拉进来。
- **非法范围必须拒绝**：重复 episode、官方 metadata 里没有的 episode、seed 与官方不符、未知任务名、范围列表内重复；生成文件多一条或少一条选中 episode 必须记成合同错误且 `passed=False`。
- **原失败保留**：dtype 变为 float32、注入非有限值时，原字段检查照旧报错，不被适配器吞掉。

另有 pytest 版 [tests/lightweight/test_comparator_scope.py](../../../tests/lightweight/test_comparator_scope.py)，其中一项用**真实的 144 条子集**与仓库里冻结的官方 metadata 跑 `validate_manifest_scope`，16 个环境的 episode 列表均为 `[0,1,2,3,4,6,7,10,11]`。

## 五、本机冒烟（调试参考，不进判据）

```bash
uv run --no-sync python scripts/train_split_parity.py run --env BinFill --episode 0 --paths A1,A2 --workers 1 --gpus 0 --output artifacts/train-parity/local-smoke-01
uv run --no-sync python scripts/train_split_parity.py compare --run artifacts/train-parity/local-smoke-01 --pair A1:A2 --history scripts/configs/newtask-v3/history/history_projection.json --gate BASELINE_REPEAT
```

```text
RUN_PATH path=A1 identities=1 ok=1 failed=0 exit=0 elapsed_s=66.649
RUN_PATH path=A2 identities=1 ok=1 failed=0 exit=0 elapsed_s=65.791
H5_PARITY pair=local-smoke-01.A1|local-smoke-01.A2 compared=1 sha_equal=1 field_mismatch=0
DATASET_GEN_REPORT_PARITY=PASS compared=1 fields=identity,recovery_mode,success,timestep_count outcome_mismatch=0 detail_mismatch=0
BASELINE_REPEAT=PASS compared=1 different=0
```

- 身份：`BinFill/episode_0`、`seed=4000`、`difficulty=easy`、`recovery_mode=z`（保留 z 恢复）。
- A1↔A2 **整文件 SHA-256 相同**，伴生文件（含 MP4）散列也全部相同，`sidecar_mismatch=0`。
- 本次生成 `timestep_count=550`，与官方历史报告中同一身份的 550 帧一致（R1a 的四类可比字段全中）。
- 运行环境：`sled-vail`、2×RTX 6000 Ada、驱动 570.211.01、Python 3.11.14、单 worker 每条约 66 s；历史报告的运行主机同为 `sled-vail`，所以帧数一致属预期，不能据此宣称已在 A40 上复现。

## 六、本步之后的状态与下一步

- 已过：G1（步 0）、历史冻结（步 1a）、**G5**。
- 未做：P0（跨 job 等价，先出 `jobs=3` 版）、P1（A40 上的 A1↔A2）、R1a 的集群侧复跑。
- 下一步：把 NFS 副本 `robomme_benchmark-newtask-gl` 切到 `newtaskRelease-v3`，在 3 个 RUNNING 的占位 job（61673583／84／85）里跑同一条 `BinFill/easy/episode_0` 的 A1／A2 与跨 job A1，出 `BASELINE_REPEAT` 与 `NODE_PARITY jobs=3`。
