# 生成噪声基线运行留档（2026-10-03）

长期结论与判据见 [`docs/1003-noise-baseline.md`](../../1003-noise-baseline.md)；计划见 [`1003-noise-baseline-plan.md`](../../../1003-noise-baseline-plan.md)（文首「实施中范围变更」优先）。本文件只记这一轮实测的启动状态、命令、结果与归档清单。

## 一、一句话结论

同一份代码（锚点 `f8f76fba`）在 GL A40 上跨两台节点各生成一遍：V9 129 局 128 局逐字节相同、1 局（BinFill xhard1 候选 0）会抖；xhard0 48 局 46 局逐字节相同、2 局为官方原版就生成失败的已知局（三方失败产物逐字节相同）。与永久参照相比，非逐字节相同的局 V9 2/129（1.6%）、xhard0 0/48，均低于用户定的 10%。

## 二、版本与环境

| 项 | 值 |
|---|---|
| 锚点提交 | `f8f76fbabc27d0b95ea9acbd57288e49411c7fb4`（12.364）；工作区干净 |
| GL 执行克隆 | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-noise`（本机 `git clone --no-hardlinks`，`--detach` 到锚点），只建 bench venv：NFS uv-python 3.11.14、`uv sync --frozen --group eval-client`（torch 2.9.1+cu128） |
| GPU／驱动 | NVIDIA A40，595.71.05（四遍来源报告一致） |
| 占位作业 | `nb-hold-1～4` = 63153922～63153925（1 A40／4 CPU／48G／48 h，`--gpu_cmode=shared`），节点 gl1525（1、2）、gl1527（3、4）；清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-nb-20261003.txt` |
| NFS 运行根 | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/noise-baseline-20261003/`（`inputs/`、`scripts/`、`logs/`、`prov/`、`gen/`、`budget-ledger.jsonl`） |
| 本机产物 | `artifacts/noise-baseline/gen/{smk-v9,smk-x0,v9-a,v9-b,x0-a,x0-b}`（逐局 h5 与 mp4，经 `hard_pull.py` 拉回并核 sha，`PULL_DONE=PASS segments=6 failed=[]`）；比对输出 `artifacts/noise-baseline/compare/` |

## 三、启动与命令

GL 登录节点 gl-login3 的 tmux 会话（本轮清单，均已自然退出）：`nb-smk-v9`、`nb-smk-x0`、`nb-v9-a`、`nb-v9-b`、`nb-x0-a`、`nb-x0-b`。本机 tmux：`nb-setup`（首建，中途停掉）、`nb-setup2`（续建失败）、`nb-setup3`（重建成功）、`nb-pull`（拉回）。

```bash
# 登录节点：launch.sh <作业> gen <遍名> <V9|X0> 4 [smoke]，等作业 RUNNING 后清 SLURM_* 再 srun
srun --jobid=$JOB --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared bash $NB/scripts/pass.sh gen <遍名> <V9|X0> 4 [smoke]
# pass.sh 内（V9）
bash $C/scripts/parity/noise_run_gl.sh --pass <遍名> --log $NB/logs/<遍名>.log --provenance-out $NB/prov/<遍名>.json \
  --budget-ledger $NB/budget-ledger.jsonl --budget-caps $NB/inputs/budget-caps.json --kind gen --out-root $NB/gen/<遍名> \
  --attempts 129 --resets 387 --retries 0 -- \
  $C/.venv/bin/python $C/scripts/parity/hard_parity.py generate --side H2 --tier v9 --manifest $NB/inputs/delivery.local.json \
  --identities $NB/inputs/v9-129-generate.jsonl --specs-root $NB/inputs/specs-root --src-root $C --workers 4 --gpu 0 \
  --out /tmp/nb-<遍名> --stage $NB/gen/<遍名>
# pass.sh 内（xhard0）：export ROBOMME_HARD_XHARD0_IN_TEST_HARD=1；generate --side H --tier xhard0 \
#   --manifest $NB/inputs/xhard0_manifest.json --identities $NB/inputs/x0-48-generate.jsonl（其余同上，--attempts 48 --resets 144）
# 收尾（辅助步骤不带 shared）：srun --jobid=$JOB --overlap --ntasks=1 $C/.venv/bin/python $C/scripts/parity/noise_run.py ship --src /tmp/nb-<遍名> --stage $NB/gen/<遍名> --finalize
# 本机：hard_pull.py --stage $NB/gen --dest artifacts/noise-baseline/gen --segments smk-x0,smk-v9,x0-a,x0-b,v9-a,v9-b --interval 5
# 比对：noise_gate.py gen-compare --ref <参照或另一遍> --new artifacts/noise-baseline/gen/<遍名> --identities scripts/configs/gate-set-{v9-129,xhard0-48}.json --out <jsonl>
```

输入（NFS `inputs/`，`SHA256SUMS` 覆盖早期文件）：`v9-129-generate.jsonl`（`gate_set.py export --set v9 --kind generate`，129 行）、`x0-48-generate.jsonl`（48 行）、冒烟各取首行；`delivery.local.json`、`specs-root/`（V9 五档规格）、`xhard0_manifest.json`（与 `scripts/configs/newtask-v7/xhard0_manifest.json` 逐字节相同）、`budget-caps.json`、`ANCHOR_COMMIT`。

## 四、执行与耗时

| 遍 | 节点（作业） | 起 | 止 | 结果 |
|---|---|---|---|---|
| 冒烟 V9（PickXtimes xhard1 seed 16100000） | gl1525（63153922） | 19:56 | 19:57 | 成功；与交付 h5 sha `7a260f9758904d9c` 相同 |
| 冒烟 xhard0（PickXtimes seed 510300） | gl1527（63153924） | 19:56 | 19:57 | 成功；与官方参照 sha `cd2fb305dabb5a0a` 相同 |
| V9 第 1 遍 `v9-a` | gl1525（63153922） | 19:57:53 | 20:33:45 | 129/129 成功 |
| V9 第 2 遍 `v9-b` | gl1527（63153924） | 19:57:53 | 20:35:32 | 128/129 成功 |
| xhard0 第 1 遍 `x0-a` | gl1525（63153923） | 19:57:53 | 20:07:19 | 46/48 成功 |
| xhard0 第 2 遍 `x0-b` | gl1527（63153925） | 19:57:53 | 20:08:08 | 46/48 成功 |

预算：上限 2 遍 × (129 + 48) = 354 + 冒烟 2 + 基础设施重试 20 = 376 条轨迹、reset 1128；账本登记 356 条（四遍 354 + 冒烟 2）、reset 1068，基础设施重试 0，六遍 `finish` 的 `exit_code` 均为 0。各遍 `RUN_FRESH=PASS`（输出根 `state=absent`）、`BUDGET=PASS`、`NOISE_SHIP=PASS … sha_bad=0 missing=0 node_leftover_media=0`。

## 五、结果

```text
GEN_PAIR=INFO ref=v9-a new=v9-b n=129 byte_equal=128 diverge=0 gen_fail=1 structural=0 unknown=0
GEN_PAIR=INFO ref=delivery.local.json new=v9-a n=129 byte_equal=127 diverge=2 gen_fail=0 structural=0 unknown=0
GEN_PAIR=INFO ref=delivery.local.json new=v9-b n=129 byte_equal=127 diverge=1 gen_fail=1 structural=0 unknown=0
GEN_PAIR=INFO ref=x0-a new=x0-b n=48 byte_equal=46 diverge=0 gen_fail=2 structural=0 unknown=0
GEN_PAIR=INFO ref=O-xhard0-bucket new=x0-a n=48 byte_equal=46 diverge=0 gen_fail=2 structural=0 unknown=0
GEN_PAIR=INFO ref=O-xhard0-bucket new=x0-b n=48 byte_equal=46 diverge=0 gen_fail=2 structural=0 unknown=0
```

非逐字节相同的局：BinFill xhard1 seed 16400000（第 1 遍第 819 步起分叉、第 2 遍生成失败）；MoveCube xhard4 seed 23400200（两遍彼此相同、都与交付 h5 自第 376 步起不同）。xhard0 VideoPlaceOrder seed 610701、611101 两遍与官方三方都是同一份 800 字节失败文件（sha256 前缀 `26c4d449632ea072`）。逐局解读见长期文档第五节。

## 六、用户决策

见长期文档第一节（原话 1～8）。本轮关键：只测生成、每格 3 局、两遍、多 worker、跨机器；「并非逐字节相同的一定要是小于百分之10」。

## 七、计划外事件与处置

1. **GL 克隆 bench venv 两次失败**：首建时主会话误把 `eval-client` 组里的 `openpi-client` 当成 MME 步骤，停掉了正在进行的 bench `uv sync`；续跑后 16 个包缺文件、cudnn 未装，torch 报 `libcudnn.so.9` 缺失。按 RECORD 核对后整目录删除重建（`nb-setup3`，115 个包、37 分钟）。
2. **xhard0 两局失败**：主会话一度误判为回归（把 v7「192/192 逐字节相同」读成「全部成功」）；只读核实为官方原版就失败的已知局（v7 `both_fail=2`），更正。
3. **首次拉回超时**：拉取清单含两个尚未收尾的冒烟段，`hard_pull.py` 等待 `SEGMENT_DONE` 被 25 分钟超时杀掉；补做冒烟 `ship --finalize` 后在 tmux 重拉成功（断点续拉）。
4. **未复用 V9 评估克隆 `v9two`**：资源清理方案闸门 G8 要求其 HEAD 前后不变，改为新建克隆。

## 八、归档文件（`records/`）

| 文件 | 内容 |
|---|---|
| `compare/*.jsonl` | 六组逐局比对（两遍互比、各遍对交付／官方） |
| `identities/*.identities.jsonl` | 六遍逐局 sha256、帧数、成败 |
| `provenance/*.json` | 六遍来源报告（commit、主机、GPU、驱动、作业号、起止时间、退出码） |
| `budget-ledger.jsonl`、`budget-caps.json` | 预算账本与上限 |

h5 本体（本机 `artifacts/noise-baseline/gen/`）不进 git；按 2026-10-03 用户关键决策（历来所有二次生成对拍产物不删）保留。
