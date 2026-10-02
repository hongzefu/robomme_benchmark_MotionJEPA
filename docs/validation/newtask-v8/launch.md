# newtask v8 运行档案：launch（起跑时写定）

计划：根目录 `1001-newtask-v8-xhard-gradient-plan.md`（12.290 获批）。本文件按计划第二部分 §2.4.2 记录各运行阶段的席位、tmux 会话名、命令与 env 覆盖；结果见同目录 `result.md`。

## 一、用户授权口径

- 「…1001-newtask-v8-xhard-gradient-plan.md 开始实施 可以问用户问题但不得中断 一路跑到底」（2026-10-01）
- 「如果reset预算不够可以在10倍内扩张」（2026-10-01，开工后追加）：reset 上限由 §2.4.3 的 7,715 扩至 ≤ 77,150；rollout 上限 3,272 与基础设施重试 ≤ 3,263 不变。

## 二、席位（清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-v8gen-20261001.txt`）

| 用途 | JobID | 规格 |
|---|---|---|
| 生成席 v8gen-hold-1～4 | 63003408～63003411 | 各 1 A40／4 CPU／48 G，spgpu |
| 评估席 v8eval-hold-1～2 | 63003486、63003487 | 同上 |
| 编排席 v8eval-orch | 63003488 | standard，1 CPU／4 G，无 GPU |

## 三、本轮 tmux 会话清单

| 会话名 | 位置 | 用途 |
|---|---|---|
| `v8-glsetup` | sled-vail | 建 NFS 克隆 `robomme_benchmark-v8gen`、`robomme_benchmark-v8eval` 与 venv（已结束） |
| `v8-x0reset-s1` | sled-vail | 阶段 1 `XHARD0_RESET_PARITY`（GPU 0） |
| `v8-x0eval` | GL 登录节点 | 阶段 3′ 编排器 |
| `v8-smoke2b` | GL 登录节点 | 阶段 2b 冒烟（生成席 63003408） |
| `v8-freeze-1`～`4` | GL 登录节点 | 阶段 3 五档冻结（四个生成席） |
| `v8-gen1-1`～`4` | GL 登录节点 | 阶段 3 gen1 四片生成 |
| `v8-h2-1`、`v8-h2-2`、`v8-h2-2b`、`v8-h2-3`、`v8-h2-4` | GL 登录节点 | 阶段 4 H2 回放 |
| `v8-sup` | GL 登录节点 | BinFill xhard2 补抽 + 片 2 续跑 |
| `v8-sync`、`v8-sync-1`～`4` | sled-vail | gen1 回传（单路后改四路并行） |
| `v8-beta`、`v8-beta-site` | sled-vail | beta 站合并与 catalog |
| `site-v8beta-8080` | sled-vail | beta 站服务（保留） |
| `v8-official`、`v8-watchdog` | sled-vail | 正式链路（aggregate + P4 接续）与独立 watchdog |
| `site-v8-8081` | sled-vail | 正式站服务（保留） |
| `v8-import`、`v8-compare` | sled-vail | H 侧登记与 H:H2 对拍 |
| `v8-gate3b-gpu0`、`v8-gate3b-gpu1`、`v8-gate3b-replay` | sled-vail | 换包 GPU 闸门 |
| `v8-nfs-cleanup` | sled-vail | 收尾删除 NFS 大文件 |

## 四、NFS 克隆

`N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu`。两份克隆自本机工作副本 `git clone --no-hardlinks --branch newtaskRelease-taskV8`，`origin` 指回本机路径（git 操作只在 sled-vail 发起）；venv 用 `uv venv --python $N/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11` + `UV_LINK_MODE=copy uv sync --frozen`。

- `$N/robomme_benchmark-v8eval`：冻结在阶段 1 合入后的 `047fa39511e258dcae3fb27ecb3a2184fd1bbf20`（12.292），供 3′ 的 hard 路线。
- `$N/robomme_benchmark-v8gen`：冒烟在 `48857961` 上跑；阶段 3 冻结、gen1、补抽与 H2 全部冻结在 `348c5a38`（阶段 2 生成链路代码的最终版；其后 S2-D 只新增本机接续脚本，生成链路零 diff）。

## 五、阶段 3′：xhard0 评估（16 任务 × 1 档 × 12 局 × 2 策略 × 2 路线 = 768 局）

工作根 `X=$N/v8eval-xhard0`，`V8=$N/robomme_benchmark-v8eval`。

**身份文件**：
- 官方路线：`$N/v7-eval/eval-official-xhard0-192.jsonl`（sha256 前缀 `b3229e83c28399f8`，10 片、每片 19～20 行），原样复用。
- hard 路线：`$X/eval-identities-xhard0-192.jsonl`（sha256 前缀 `ef0faef774567e2e`）＝ `$N/v7-eval/eval-identities-1292.jsonl` 过滤 `tier == xhard0` 的 192 行，`round` 置 1、`shard` 取官方清单中同一 (task, seed) 的片号，使同一身份的两条路线落在同一张卡上。

**四组命令**（逐字，取自 `$X/lanes/x0_step.sh`；`S` 为片号，`PORT` 见下）：

```bash
# 1. SimpleMemVLA 官方路线（SimpleMemVLA-official-xhard0 @ 4e0c04f，vendored 官方 robomme，--dataset_split test，max_steps 1300）
MANIFEST=$N/v7-eval/eval-official-xhard0-192.jsonl SHARD=$S/10 OUTDIR=$X/official/smvla VIDEO_DIR= \
  bash $N/SimpleMemVLA-official-xhard0/scripts/run_official_xhard0.sh --resume
# 2. SimpleMemVLA hard 路线（SimpleMemVLA @ 1ca6d1e，testhard_eval；BENCH 指向 v8eval 克隆）
REPO=$N/SimpleMemVLA BENCH=$V8 OUT=$X/hard/smvla ROUND=1 SHARD=$S/10 IDENTITIES=$X/eval-identities-xhard0-192.jsonl VIDEO_DIR= \
  bash $N/SimpleMemVLA/scripts/run_testhard.sh --resume
# 3. MME-VLA 官方路线（robomme_policy_learning-official-xhard0 @ 927c56d，客户端 PYTHONPATH=官方子模块 src；server 在 testhard-v7 .venv）
cd $N/robomme_policy_learning-official-xhard0 && MANIFEST=$N/v7-eval/eval-official-xhard0-192.jsonl SHARD=$S PORT=$PORT RUN_TAG=v8x0 \
  SAVE_ROOT=$X/official/mme/s$S VIDEO_DIR=$X/official/mme/s$S/videos bash scripts/gl_eval_official_xhard0.sh
# 4. MME-VLA hard 路线（robomme_policy_learning-testhard-v7 @ 4f9e40f；PYTHONPATH=$V8/src 覆盖 editable .pth）
cd $N/robomme_policy_learning-testhard-v7 && PYTHONPATH=$V8/src IDENTITIES=$X/eval-identities-xhard0-192.jsonl ROUND=1 SHARD=$S PORT=$PORT \
  RUN_TAG=v8x0 SAVE_ROOT=$X/hard/mme/s$S VIDEO_DIR= bash scripts/gl_eval_shard.sh
```

- 权重：SimpleMemVLA `$N/SimpleMemVLA/checkpoints/simplememvla_robomme`（`.venv-robomme`，group_size 1）；MME-VLA `$N/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999`，server `--seed=7`、`XLA_PYTHON_CLIENT_MEM_FRACTION=0.75`、`--policy.config=mme_vla_suite`。
- 导入预检（2026-10-01，sled-vail，只 import 不 reset）：MME hard 客户端 `PYTHONPATH=$V8/src` 下 `robomme_hard`、`robomme` 均解析到 `$V8/src`；SimpleMemVLA `.venv-robomme` 在 `sys.path` 前置 `$V8/src` 后同样解析到 v8eval，`ALL_NEWVALUE_TIERS` 五档。
- 单步包装 `$X/lanes/x0_step.sh <报告> <off|hard> <smvla|mme> <片> <端口>`：首遍后若终态（success/fail/timeout）数小于应有数，带 `--resume` 续跑一次（基础设施重试每局 ≤ 1 次）；末行 `X0_SHARD_DONE route= policy= shard= expect= final= rc= retried=` 并写报告 JSON。MME 两脚本内部最多 3 遍只补 `error` 局，属脚本既有行为，如实记录。正常失败不重试。
- 编排：`$X/state/plan.json`，2 条线 × 20 步。线 A（63003486）片 5、1、3、7、0，端口 22000+4S（官方）／+2（hard）；线 B（63003487）片 9、2、4、8、6，端口 23000+4S。每片顺序：官方 SMVLA → hard SMVLA → 官方 MME → hard MME。编排器派发 `srun --jobid=<席> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared`，每席同一时刻只有一个步骤。
- 启动：GL 登录节点 `tmux new-session -d -s v8-x0eval "bash $X/lanes/orch_launch.sh"`（清 `SLURM_*` 后 `srun --jobid=63003488 --overlap --ntasks=1 --cpus-per-task=1 python3.11 $V8/scripts/eval-official/orchestrate.py --plan $X/state/plan.json --state $X/state/run1 --workdir $X`）。本机 `--dry-run` 结果 `DRYRUN_OK lanes=2 steps=40`。
- 对拍：结果拷回本机后逐策略 `uv run --no-sync python scripts/parity/hard_regression.py xhard0-eval-parity --manifest scripts/configs/newtask-v7/xhard0_manifest.json --official <官方结果目录> --hard <hard 结果目录> --policy <simplememvla|mmevla> --out docs/validation/newtask-v8/records/xhard0-eval-parity-<策略>.jsonl`（`--out` 写的是差异 jsonl）。只出 `XHARD0_EVAL_PARITY=INFO`。
