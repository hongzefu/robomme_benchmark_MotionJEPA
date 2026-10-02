# newtask v9 运行档案：launch（起跑时写定）

计划：根目录 `1002-newtask-v9-movecube-region-800-plan.md`（12.318 首版，12.321 获批，12.324 定稿）。本文件按计划第二部分 §2.4.2 记录各运行阶段的席位、tmux 会话名、命令与 env 覆盖；结果见同目录 `result.md`。

## 一、用户授权口径

- 「1002-newtask-v9-movecube-region-800-plan.md 开始实施 有问题问用户但不要阻塞 应该可以执行到底 所有预算job都批准」（2026-10-02）
- P3 预算：计划 §2.4.3 表内每行上限 × 10（用户 2026-10-02「2同意各类预算在上浮十倍的基础上。都可以自行决策不用来问我」），占位 job 14 个一并获批。

## 二、代码锚点

- 阶段 1 合入：12.325（S1-A，`8b9726c0`）、12.326（S1-B，`0ec11702`）、12.327（主会话配合项，`fa1d856c`）。
- 阶段 2 合入：12.328（S1-E，`33be4f8c`）、12.329（S1-F，`203399aa`）、12.330（S1-D，`e9f247b1`）、12.331（S1-C，`d121ee52`）。
- 阶段 3 起跑冻结点：12.332（本文件所在提交）。NFS 生成克隆 `$N/robomme_benchmark-v9gen` 前移到该 sha，各 GL 脚本开头核对 `EXPECT=` 与工作区干净；本机 InsertPeg extend 在主检出同一 HEAD 上跑。阶段 3 起跑到 3b 换包提交之间不 commit（计划 R8）。
- 阶段 2b 冒烟跑在 `fa1d856c`（生成链路自 12.327 起未再改动）。

## 三、席位（清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-v9gen-20261002.txt`）

| 用途 | JobID | 规格 |
|---|---|---|
| 生成席 v9gen-hold-1（MoveCube 冻结与生成） | 63107829 | 1 A40／4 CPU／48 G／48 h，spgpu，shared |
| 生成席 v9gen-hold-2（InsertPeg 生成） | 63107830 | 同上 |
| 生成席 v9gen-hold-3（2b 冒烟；之后 H2 片） | 63107831 | 同上 |
| 生成席 v9gen-hold-4（H2 片） | 63107832 | 同上 |

评估 10 席 `v9ev-hold-00～09` 在阶段 4b 前提交，另记于评估留档。

## 四、本轮 tmux 会话清单

| 会话名 | 位置 | 用途 |
|---|---|---|
| `v9-glsetup` | sled-vail | 建 NFS 克隆 `robomme_benchmark-v9gen` 与 venv（已结束，EXIT_CODE=0） |
| `v9-x0reset-s1` | sled-vail | 阶段 1b `XHARD0_RESET_PARITY`（GPU 0，已结束） |
| `v9-smoke2b` | GL 登录节点 | 阶段 2b 冒烟（席 3，已结束） |
| `v9-freeze-movecube` | GL 登录节点 | 阶段 3 MoveCube 冻结（席 1） |
| `v9-extend-insertpeg` | sled-vail | 阶段 3 InsertPeg extend 抽签（GPU 1） |
| `v9-gen-movecube` | GL 登录节点 | 阶段 3 MoveCube 生成（席 1） |
| `v9-gen-insertpeg` | GL 登录节点 | 阶段 3 InsertPeg 生成（席 2） |
| `v9-h2-insertpeg`、`v9-h2-movecube` | GL 登录节点 | 阶段 4 H2 二次生成（席 2、席 1） |
| `v9-3b-verify`、`v9-3b-replay`、`v9-x0reset-3b` | sled-vail | 3b 子集逐字节核对、回注回放（GPU 1）、换包后 xhard0 对拍（GPU 0） |
| `v9-compare` | sled-vail | 阶段 4 H 侧登记与 H:H2 对拍 |
| `v9-site-build`、`site-v9-8082` | sled-vail | 阶段 4c 建站；V9 站常驻服务（保留） |
| `v9-transcode`、`v9-nfs-cleanup` | sled-vail | 评估视频转码；NFS 产物搬回与清理 |

评估侧会话见 `docs/validation/v9-two-policy-gl10-20261002-01/launch.md` §七。

## 五、阶段 3 命令（逐字）

`N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu`，`V=$N/robomme_benchmark-v9gen`，`O=$N/v9gen-out`。GL 脚本统一导出 `ROBOMME_ENV_PACKAGE=robomme_hard OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1`，解释器 `$V/.venv/bin/python`；包装为 GL 登录节点 `tmux new-session -d -s <名> "cd /tmp && srun --jobid=<席> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared bash <脚本> 2>&1 | tee -a <日志>; echo EXIT_CODE=\${PIPESTATUS[0]} >> <日志>"`。

1. MoveCube 冻结（席 1，脚本 `$O/scripts/freeze_movecube.sh`）：
   ```bash
   $PY scripts/injection-dev/freeze_specs.py --tier xhard4 --seed-profile v8 --cells v9shard1 \
     --candidates-per-env MoveCube=80 --task-max-reset-attempts MoveCube@xhard4=124 \
     --workers 4 --gpus 0 --run-id v9-movecube-xhard4 --out $O/movecube-frozen/xhard4/specs.jsonl
   ```
2. MoveCube 切片（sled-vail，用 NFS 克隆 venv）：`generate_h5.py --mode split --specs $O/movecube-frozen --cells v9shard1 --output $O/gen/shard-movecube`。
3. MoveCube 生成（席 1）：`generate_h5.py --mode continue --specs $O/gen/shard-movecube/specs --cells v9shard1 --output $O/gen/shard-movecube --workers 4 --gpu 0`。
4. InsertPeg extend（sled-vail 主检出，GPU 1）：
   ```bash
   CUDA_VISIBLE_DEVICES=1 uv run --no-sync python scripts/injection-dev/v9_subset_specs.py extend --task InsertPeg --tier xhard4 \
     --v8-frozen artifacts/newtask-v8/specs-root --v8-shard artifacts/newtask-v8/gen1/shard3 \
     --quota 50 --append 35 --max-reset-attempts 55 --gpus 0 --out artifacts/newtask-v9/gen/insertpeg-root
   ```
   产出的片根 rsync 到 `$O/gen/insertpeg-root`。
5. InsertPeg 生成（席 2）：`generate_h5.py --mode continue --cells $O/gen/insertpeg-root/cells.json --specs $O/gen/insertpeg-root/specs --output $O/gen/insertpeg-root --resume --workers 4 --gpu 0`（片收尾自动聚合打 `V8_DELIVERY_SET=FAIL bad_h5=20` 属预期：20 局 V8 已交付局的 NFS 路径已删）。
6. 回传与聚合：逐局产物 rsync 回本机 `artifacts/newtask-v9/gen/`，本机 `generate_h5.py --mode aggregate ... --rebase $O/gen=$PWD/artifacts/newtask-v9/gen --rebase $N/v8gen-out/gen1=$PWD/artifacts/newtask-v8/gen1`，NFS 侧在核对后删除。

Monitor 过滤：`全部完成|EXIT_CODE=|Traceback|NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|SceneGenerationError|exhausted|FREEZE_WAYS|V8_|V9_`。

## 六、P3 预算（计划 §2.4.3，上限 × 10 获批）

| 项目 | 计划上限（reset／rollout） | 本轮实耗 |
|---|---|---|
| xhard0 对拍 1b | 768／0 | 768／0（16 任务 × 1 档 × 12 局 × 2 侧 × 2 次） |
| 冒烟 2b | 6／2 | ≤10（冻结 reset 上限 2 任务 × 5）／2 |
| 抽签 MoveCube | 124／0 | 待填 |
| 抽签 InsertPeg 追加 | 55／0 | 待填 |
| 生成新局 | 126／126 | 待填 |

冒烟冻结的 reset 上限 10 超过计划表的 6，在 × 10 授权内。
