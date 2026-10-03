# HuggingFace 只保留 V9 数据集方案（2026-10-03）

> 权威性：本方案只规划、不实施。上传、删除都要等用户明确说「执行」后才开始，而且只按本文件清单操作。
>
> - 代码锚点：commit `119e1140`（12.366）；工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`；分支 `newtaskRelease-taskV9`。commit 编号执行时取 `git log -1` 最新号加 1。
> - 外部锚点：HF 账号 `HongzeFu`；现有本项目 bucket `HongzeFu/robomme-hard-parity`（公开，977 个文件，454754615798 B，快照 `artifacts/newtask-v9/logs/cleanup-20261003/hf-after.json`）；`hf` CLI 1.8.0。
> - 前置：`1003-resource-cleanup-plan.md` 已执行完（12.365、12.366），本机 V9 交付集是唯一副本。

# 第一部分（给人看）

## 一、总览

**一句话方案**：新建公开 bucket `HongzeFu/robomme-hard-v9`，把本机 V9 交付集 `artifacts/newtask-v9/delivery/`（800 个 h5、800 个 mp4、索引 `delivery.local.json`），再加上三份校验清单，原样上传。上传后逐个对象下载回来核对 sha256，全部相同后，整个删除旧 bucket `HongzeFu/robomme-hard-parity`。你名下其他 16 个 bucket 一律不动。

**已定死口径**（用户原话逐字保留）

1. **HF 只保留最新的 V9 数据集**。用户 2026-10-03 原话：「出方案落在根目录。只要在HUGingFace上保留最新的与9Dataset的内容其他的都要删掉。」（第三节）
2. **删除范围只限本项目 bucket**。用户在选项中选「只删本项目 bucket」：`robomme-hard-parity` 的 977 个文件全删（含官方 xhard0 192 局与校验清单）；其他 16 个 bucket（policy learning、MotionJEPA、sam2act 等项目）一律不动。（第三节、G6）
3. **上传内容**。用户在选项中选「h5 + mp4 + 索引」：800 个 h5（453.57 GB）、800 个 mp4（14.01 GB）、`delivery.local.json`（1005346 B）。另加三份由本方案生成的小清单：`SHA256SUMS`、`identities.jsonl`、`manifest.json`，用来让下载方能逐文件核对。（第二节）
4. **落点**。用户在选项中选「新建 bucket」：新 bucket 的名字与内容一致，旧 bucket 清空后整个删除。（第二节）
5. **本机 V9 交付集不动**。延续 12.362 的口径 8「数据集冻结」：`delivery/` 下 1601 个文件逐字节不变，本方案只读它们。新生成的清单写在 `artifacts/newtask-v9/hf-publish/`，不写进 `delivery/`。（G1）
6. **先上传、核对，后删旧**。新 bucket 读回核对全部通过之前，旧 bucket 一个文件都不删。（第四节）
7. **零改码、零生成**：不改 `src/`、`scripts/`、`tests/`，不起仿真、不用 GPU。上传与核对用 scratchpad 里的一次性脚本，命令原文写进留档。

**待你定的一件事**：新 bucket 是公开还是私有。旧 bucket 是公开的，本方案默认沿用**公开**；你选私有，只需在 `create` 时加 `--private`，其余不变。

**预计规模与耗时**

- 上传对象 `800 h5 + 800 mp4 + 1 索引 + 3 清单 = 1604` 个，共约 467.6 GB。
- 耗时按 09-28 上传 xhard0 的实测速率 174 MB/s 估算：
  - 上传约 45 分钟；
  - 逐个读回核 sha 约 45～60 分钟；
  - 开头重算本机 sha 约 10 分钟。
- 合计约 2 小时，长步骤全部放进 tmux。

## 二、上传什么、放在哪

**新 bucket 布局**（与本机 `delivery/` 完全相同，另在根目录加三份清单）

```
hf://buckets/HongzeFu/robomme-hard-v9/
  delivery.local.json                         ← 原样上传（含本机绝对路径，冻结不改）
  episodes/<档>/<任务>_episode_<n>/hdf5_files/<任务>_ep<n>_seed<seed>.h5
  episodes/<档>/<任务>_episode_<n>/videos/<…>.mp4
  identities.jsonl                            ← 800 行，每局一行
  SHA256SUMS                                  ← 1601 行，覆盖 delivery 下全部文件
  manifest.json                               ← 出处与计数
```

- 局数：`16 任务 × 50 局 = 800`，分布在 43 格；按档是 xhard1 272、xhard2 272、xhard3 92、xhard4 144、xhard5 20。
- 为什么另做 `identities.jsonl`：`delivery.local.json` 每行的 `path` 指向 `../../newtask-v8/gen1/...`，`h5`、`video` 是本机绝对路径，下载方拿到也对不上。`identities.jsonl` 每行写：
  - bucket 内相对路径 `h5`、`video`；
  - `task`、`tier`、`seed`、`episode`、`role`、`source`（`v8-reuse` 或 V9 新生成）；
  - `exec_steps`；
  - `h5_sha256`、`video_sha256`。

  映射方法：用 inode 把每行的 `h5` 对到 `delivery/episodes/...`（12.365 实测 `h5_same_inode=800`）。
- `manifest.json` 写：仓库与分支、交付时的判定行（`delivery.local.json` 自带的 `line` 字段：`V9_DELIVERY_SET=PASS tasks=16 cells=43 total=800 … reused=720 new=80`）、`delivery.local.json` 的 sha256（`3c21839d…dd40`）、`SHA256SUMS` 的 sha256、三种文件各自的个数与字节数、上传时间、本方案 commit。

## 三、删什么

**整个删除 `HongzeFu/robomme-hard-parity`**（`hf buckets delete`），里面是拆包期（09-27～09-28）三侧对拍的生成 h5：

| 目录 | 内容 | 局数 |
|---|---|---|
| `H-34a1cea-a40/native`、`O-1fadc0e-a40/native`、`P-7c7118f-a40/native` | 原版三档，本仓库／官方／修改前三侧 | 各 `16 任务 × 3 档 × 3 局 = 144` |
| `H-b1afc80-a40/xhard`、`P-ca32e9b-s4/xhard` | V6 的 xhard1～4 | 各 `xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165` |
| `O-1fadc0e-a40/xhard0` | 官方 xhard0 | `16 任务 × 1 档 × 12 局 = 192` |

**⚠ 删后哪些就没了**

- 原版三档三侧的 h5（`144 × 3`），以及 V6 xhard 两侧的 h5（`165 × 2`）：本机在 12.365 已删（`P-native` 拉回缓存与 `newtask-v6/v6-02`），HF 是最后一份，删后不可恢复。
- 官方 xhard0 192 局：本机仍有两份，`newtask-v7/parity/h5/H-xhard0` 和 `O-xhard0-bucket`，各 66.55 GiB，逐字节相同，不受影响。
- 比对结论不受影响：判定行与逐局比对记录都在 git（`docs/validation/newtask-v6/hard-split/records/stage4/compare-*`）和本机 `parity/compare` 里。

**删前先把旧 bucket 的「目录」存进 git**：6 份 `SHA256SUMS`、6 份 `identities.jsonl`、6 份 `manifest.json`、5 份 `launch-*.json`，以及全量列表 JSON（977 行），都是 KB 级。存到 `docs/validation/newtask-v9/hf-20261003/robomme-hard-parity/`。这样删后仍能查到当时上传过哪些对象、各自的 sha 是什么。

**明确不动**：

- 其他 16 个 bucket：`robomme-vla-*`、`robomme-4task-*`、`motionjepa-*`、`robomme-motionjepa-vla-v1`、`sam2act_historybench`、`MotionJEPA` 等；
- 你名下所有 model／dataset／space；
- 本机 `delivery/`。

## 四、为什么这样做是安全的

1. **上传不改本机数据**。`hf buckets sync <本机目录> <远端>` 只读本机文件。G1 在上传前后各算一次 `delivery/` 的 sha，三份清单逐行相同才算过。
2. **读回核对是真校验**。按 `AGENTS.md` 第 15 条，同源判定只认 sha256，不拿 HF 的 `xet_hash` 代替：
   - 每个对象都用 `hf buckets cp` 下载到本机临时文件、算 sha256、与 `SHA256SUMS` 比对，然后立刻删掉临时文件；
   - 同一时刻只占一个文件的磁盘空间（最大约 1 GB）；
   - 做法沿用 `scripts/parity/hard_parity.py::cmd_publish` 的读回段，09-28 上传 xhard0 时实测 `BUCKET_SYNC=PASS … readback_sha_equal=192 mismatch=0`。
3. **删旧有闸门**。`hf buckets delete HongzeFu/robomme-hard-parity` 只在下面三条全部 PASS 之后才执行：G3 上传完整、G4 读回全等、G5 旧目录已存进 git。命令里写死字面 bucket ID，不用变量。
4. **其他 bucket 不受牵连**。删前删后各存一份 `hf buckets list HongzeFu` 的结果。要求：前后相差恰好只少 `robomme-hard-parity` 这一行，其余 16 行的 ID、大小、文件数完全相同（G6）。
5. **⚠ 代价与失效**：
   - `scripts/parity/hard_parity.py` 的常量 `BUCKET = "HongzeFu/robomme-hard-parity"`，`publish` 子命令会指向一个已删除的 bucket。按口径 7 不改码，写进失效清单；以后要再发布，先改常量或另立计划。
   - `docs/validation/parity-anchors.json` 的 `bucket_prefix` 字段、`docs/validation/newtask-v6/hard-split/stage0.md`、`stage4.md`、`docs/validation/newtask-v7/README.md`、`docs/plans/0927-*`、`docs/plans/0928-*` 里提到的旧 bucket 路径都会成为死链接。这些是历史留档，正文不改，只在留档里列出。
   - `1003-resource-cleanup-plan.md` 口径 9 写的是「只删 _probe，留校验清单」，被本方案口径 1、2 取代。

## 五、验收

| 编号 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| G1 | 本机交付集没被碰 | 上传前、全部完成后，各对 `delivery/` 全部文件算 sha256（`LC_ALL=C` 排序），与 12.365 的 `sha-after.txt` 逐行相同 | 数据集冻结口径守住 | `V9_DELIVERY_SHA=PASS files=1601 changed=0 cmp=<两次>` |
| G2 | 三份清单正确 | `identities.jsonl` 800 行：每行 `h5_sha256`、`video_sha256` 与 `delivery.local.json` 记录相同，路径存在；`SHA256SUMS` 1601 行，与 G1 结果逐行相同 | 下载方拿到的清单可信 | `V9_HF_STAGE=PASS identities=800 sums=1601 sha_match=1600 tasks=16 per_task=50` |
| G3 | 上传完整 | 新 bucket 的 `hf buckets list -R --format json`：文件数 1604，每个路径的大小等于本机大小 | 没有漏传、没有截断 | `V9_HF_UPLOAD=PASS objects=1604 size_equal=1604 missing=0 extra=0` |
| G4 | 远端内容逐字节正确 | 1604 个对象逐个 `hf buckets cp` 下载回来算 sha256，与本机比对 | 远端与本机逐字节相同 | `V9_HF_READBACK=PASS objects=1604 sha_equal=1604 mismatch=0` |
| G5 | 旧 bucket 的「目录」已留存 | 23 个小文件下载进 `docs/validation/newtask-v9/hf-20261003/robomme-hard-parity/`；`SHA256SUMS` 的总行数等于 h5 总数 `144 × 3 + 165 × 2 + 192 = 954`；全量列表 977 行 | 删后仍能查当时内容 | `HF_OLD_RECORDS=PASS files=23 sums_rows=954 listing=977` |
| G6 | 只删了旧 bucket | 删前删后 `hf buckets list HongzeFu --format json` 比较 | 其他 16 个 bucket 没被碰 | `HF_OLD_BUCKET_DELETED=PASS removed=robomme-hard-parity others_equal=16` |
| G7 | 最终状态 | 本项目在 HF 上只剩新 bucket，内容等于 G3 的列表 | 「HF 只保留 V9」成立 | `HF_FINAL=PASS project_buckets=1 objects=1604` |

## 六、实施步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 记 `BASE`；存 17 个 bucket 的快照与旧 bucket 全量列表；建 `artifacts/newtask-v9/hf-publish/`；tmux `hf-sha-pre` 重算 `delivery/` sha | G1（前） |
| 1 | 生成三份清单 | G2 |
| 2 | 下载旧 bucket 的 23 个小文件进 git 留档目录 | G5 |
| 3 | `hf buckets create HongzeFu/robomme-hard-v9`（若你选私有则加 `--private`）；tmux `hf-up` 中执行 `hf buckets sync delivery/ hf://buckets/HongzeFu/robomme-hard-v9`，再用 `hf buckets cp` 传三份清单 | 日志 `EXIT_CODE=0`；G3 |
| 4 | tmux `hf-readback` 逐个读回核 sha | G4 |
| 5 | `hf buckets delete HongzeFu/robomme-hard-parity -y` | G6、G7 |
| 6 | 再算一次本机 sha；写留档 `docs/validation/newtask-v9/hf-20261003.md`；更新 `docs/1002-pending-decisions.md` F4（HF 上传已完成）；commit 并 push | G1（后）；`git status -sb` 无 ahead |

阶段 0～4 都可逆：新 bucket 有问题可以删掉重传，旧 bucket 原样还在。唯一不可逆的是阶段 5，它只在 G3、G4、G5 全部 PASS 之后执行。

## 七、子代理分工与合并（简述）

本方案没有代码改动，全部是对远端数据的上传和删除，所以不派写入型子代理，由主会话逐步执行、逐步核对，也就没有合并步骤。阶段 1 生成清单后，派 1 个只读审查者（sonnet）核对两件事：三份清单与 `delivery.local.json` 一致，脚本只写 `hf-publish/` 和留档目录。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- **R1 本机只读**：`artifacts/newtask-v9/delivery/` 全程只读。可写的只有：
  - `artifacts/newtask-v9/hf-publish/`（新建，放清单与日志，记为 `P`）；
  - `docs/validation/newtask-v9/hf-20261003/` 与 `docs/validation/newtask-v9/hf-20261003.md`；
  - `docs/1002-pending-decisions.md` 的 F4 条。
- **R2 只删一个 bucket**：唯一的删除命令是 `hf buckets delete HongzeFu/robomme-hard-parity -y`，ID 写死为字面量。禁止 `hf buckets remove -R` 批量删、禁止通配、禁止对其他 bucket 发任何写命令。
- **R3 删前闸门**：G3、G4、G5 任一不是 PASS，就不执行 R2。
- **R4 凭据**：只用 `hf` 已登录的 token（`hf auth whoami` 显示 `HongzeFu`），不打印、不落盘、不写进留档。
- **R5 长任务**：sha 重算、上传、读回都放进 detached tmux。会话名前缀 `hf-`，清单为 `hf-sha-pre`、`hf-up`、`hf-readback`、`hf-sha-post`。日志按 `AGENTS.md` 第 7 条三件套写入 `P/logs/`，每份日志挂一个 Monitor。
- **R6 不改码**：一次性脚本 `hf_v9.py` 放在会话 scratchpad，命令原文写进留档；不在 `scripts/` 新增文件（`AGENTS.md` P1）。
- **R7 失败即停**：任一闸门 FAIL，停下把原始输出交用户。上传中断可以重跑同一条 `sync`（按大小与 mtime 跳过已传对象，幂等），但最多重跑 2 次，并记录次数与原因。

## 一 逐项改动清单

| 对象 | 动作 | 规模 |
|---|---|---|
| `hf://buckets/HongzeFu/robomme-hard-v9` | 新建（公开，或按你的选择设私有） | — |
| 同上 | 上传 `delivery/` 全部文件 | 1601 个对象：800 h5（453.57 GB）、800 mp4（14.01 GB）、1 json |
| 同上 | 上传 `P/identities.jsonl`、`P/SHA256SUMS`、`P/manifest.json` | 3 个对象 |
| `hf://buckets/HongzeFu/robomme-hard-parity` | 整个删除 | 977 个文件，454754615798 B |
| `docs/validation/newtask-v9/hf-20261003/robomme-hard-parity/` | 新增旧 bucket 目录留存：6 个 `SHA256SUMS`、6 个 `identities.jsonl`、6 个 `manifest.json`、5 个 `launch-*.json`，按原相对路径存放；外加全量列表 `listing.json` | 24 个文件，KB 级 |
| `docs/validation/newtask-v9/hf-20261003.md` | 新增留档 | — |
| `docs/1002-pending-decisions.md` F4 | 追加「HF 上传已完成、旧 bucket 已删」 | 1 条 |

## 二 子代理分配表

| 子任务编号 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（在哪里、以什么环境跑） | 资源占用 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| 主会话自做 | 阶段 0～6 | R1 所列 | `delivery/`；其他 16 个 bucket | 无 | 无（不派写入型子代理；理由：全部是远端数据操作，无代码改动） | G1～G7，在主检出、主 `.venv` 下跑（`cd $R && uv run --no-sync python <scratchpad>/hf_v9.py …`） | 不用 GPU；出网带宽约 174 MB/s；tmux 前缀 `hf-` | 全部归主会话 |
| H-1（只读，sonnet） | 审查三份清单与 `hf_v9.py` | 无 | 全部 | 读 `P/` 与本方案 | 无 | `HF_STAGE_REVIEW=PASS\|FAIL findings=<n>` | 无 | 无 |

## 三 闸门总表

| 判定项 | 何时跑 |
|---|---|
| G1 `V9_DELIVERY_SHA` | 阶段 0、阶段 6 |
| G2 `V9_HF_STAGE`、`HF_STAGE_REVIEW` | 阶段 1 |
| G5 `HF_OLD_RECORDS` | 阶段 2 |
| G3 `V9_HF_UPLOAD` | 阶段 3 |
| G4 `V9_HF_READBACK` | 阶段 4 |
| G6 `HF_OLD_BUCKET_DELETED`、G7 `HF_FINAL` | 阶段 5 |

## 四 runbook

```bash
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
D=$R/artifacts/newtask-v9/delivery
P=$R/artifacts/newtask-v9/hf-publish
K=$R/docs/validation/newtask-v9/hf-20261003/robomme-hard-parity
NEW=HongzeFu/robomme-hard-v9
```

**阶段 0**

```bash
mkdir $P $P/logs                                                  # 必须是新建
hf buckets list HongzeFu --format json > $P/buckets-before.json   # 17 行
hf buckets list HongzeFu/robomme-hard-parity -R --format json > $P/old-listing.json   # 977 个文件
tmux new-session -d -s hf-sha-pre "bash <scratchpad>/hf_sha.sh pre"   # 写 $P/sha-pre.txt；尾行 EXIT_CODE=0 lines=1601 errbytes=0
```

**阶段 1**：`hf_v9.py stage`

- 读 `$D/delivery.local.json` 的 800 行。
- 按 inode 把每行的 `h5` 对到 `$D/episodes/...` 下的同一文件，`video` 同理。
- 写 `$P/identities.jsonl`（字段见第一部分第二节）。
- 把 `sha-pre.txt` 的路径前缀 `artifacts/newtask-v9/delivery/` 去掉，写成 `$P/SHA256SUMS`。
- 写 `$P/manifest.json`。
- 打印 `V9_HF_STAGE=…`。

**阶段 2**：`hf_v9.py keep-old`

- 从 `old-listing.json` 选出路径以 `SHA256SUMS`、`identities.jsonl`、`manifest.json`、`launch-*.json` 结尾的 23 个对象，逐个 `hf buckets cp` 到 `$K/<原相对路径>`。
- 把 `old-listing.json` 复制为 `$K/listing.json`。
- 打印 `HF_OLD_RECORDS=…`。

**阶段 3**

```bash
hf buckets create HongzeFu/robomme-hard-v9            # 私有则加 --private
tmux new-session -d -s hf-up "set -o pipefail; hf buckets sync $D hf://buckets/HongzeFu/robomme-hard-v9 2>&1 | tee $P/logs/up.log; echo \"EXIT_CODE=\$?\" >> $P/logs/up.log"
# 完成后
hf buckets cp $P/identities.jsonl hf://buckets/HongzeFu/robomme-hard-v9/identities.jsonl
hf buckets cp $P/SHA256SUMS       hf://buckets/HongzeFu/robomme-hard-v9/SHA256SUMS
hf buckets cp $P/manifest.json    hf://buckets/HongzeFu/robomme-hard-v9/manifest.json
hf buckets list HongzeFu/robomme-hard-v9 -R --format json > $P/new-listing.json   # hf_v9.py upload-check → V9_HF_UPLOAD
```

Monitor 过滤词：`EXIT_CODE=|Sync completed|Error|Traceback|429|rate limit|quota|Forbidden|Unauthorized|timed out|Connection`。

**阶段 4**

```bash
tmux new-session -d -s hf-readback "bash <scratchpad>/hf_readback.sh"
```

- 逐个 `hf buckets cp hf://buckets/HongzeFu/robomme-hard-v9/<rel> $P/rb.tmp`，算 sha256 与 `SHA256SUMS`（三份清单自己的 sha 记在 `manifest` 外的 `$P/meta-sha.txt`）比对，然后删掉 `rb.tmp`。
- 每 100 个对象打一行 `PROGRESS n=<已核> mismatch=<n>`；最后打 `V9_HF_READBACK=…` 和 `EXIT_CODE=`。

**阶段 5**

```bash
hf buckets delete HongzeFu/robomme-hard-parity -y
hf buckets list HongzeFu --format json > $P/buckets-after.json    # hf_v9.py final → HF_OLD_BUCKET_DELETED、HF_FINAL
```

**阶段 6**：tmux `hf-sha-post` 重算 sha，与 `sha-pre.txt`、12.365 的 `sha-after.txt` 都比对（G1）；写留档；`git add` 逐个路径；commit；push。

## 五 风险登记

1. **上传中断或被限速**：同一条 `sync` 重跑幂等，最多 2 次；仍失败就停下交用户。旧 bucket 此时还在，没有损失。
2. **HF 账号存储额度**：未核实。你名下现有约 4 TB，新增约 468 GB，删旧 455 GB 后净增约 13 GB。若上传报额度错误，按 R7 停下。
3. **公开可见**：选公开时，V9 数据集一上传就对外可见，`delivery.local.json` 里的本机绝对路径（`/data/hongzefu/…`）也随之公开。旧 bucket 同样公开，属同类情况。
4. **删旧不可逆**：原版三档与 V6 xhard 的三侧对拍 h5 删后就没有任何副本了（见第一部分第三节）；比对结论与 sha 目录留在 git。
5. **读回耗时**：约 468 GB 的下载流量；只占一个文件的临时磁盘。
6. **并行会话**：噪声基线只用本机的 xhard0 h5，不读 HF（`1003-noise-baseline-plan.md` 核查项 j 写的是「本机是否还在」），删旧 bucket 不影响它。

## 六 盲区诚实清单

- HF 存储额度、速率限制没有事先查询。
- 上传速率 174 MB/s 是 09-28 单次实测，当前网络未测。
- `hf buckets sync` 对 1600 个大文件的断点续传行为，只依据命令说明（按大小与 mtime 跳过），没有实测。
- 删除后 HF 侧存储空间的统计会延迟刷新（`AGENTS.md` 第 15 条：`usedStorage` 不采信），G6 只比 bucket 列表。

## 七 留档与 commit 纪律

- **留档** `docs/validation/newtask-v9/hf-20261003.md`，内容包括：
  - 用户原话与三项选择；
  - 新 bucket 的 ID、可见性与布局；
  - G1～G7 判定行原文；
  - 上传与读回的耗时、平均速率；
  - 已删旧 bucket 的内容表与「不可恢复」说明；
  - 失效清单（第一部分第四节第 5 条）；
  - tmux 会话清单；
  - `hf_v9.py` 的命令原文。
- **commit**：
  - subject 为 `<最新号+1> HF 只保留 V9 数据集：新建 robomme-hard-v9 上传 800 局 h5／mp4／索引并逐对象读回核对，删除旧 bucket robomme-hard-parity`；
  - body 按 `AGENTS.md` 第 11 条六项写；
  - 逐个路径 `git add`，随即 push。
