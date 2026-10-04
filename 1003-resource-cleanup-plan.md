# 历史资源清理方案（2026-10-03，三轮对抗验证后修订版）

> 权威性：本方案只规划、不实施。全部删除动作须用户明确说「执行」后才开始，且只按本文件清单删。
>
> - 代码锚点：commit `39ccc6cc`（12.361）；工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`；分支 `newtaskRelease-taskV9`。并行会话（噪声基线计划）仍在本检出提交，执行时以当时 HEAD 为准。
> - commit 编号不写死：执行时取 `git log -1` 最新号加 1。
> - 取代关系：本方案取代 `docs/plans/1002-v9-final-cleanup-plan.md` 中被叫停的阶段 B，也取代 12.348 提交的本文件初版。按用户 2026-10-03 指示放在仓库根目录。
> - 本版经三轮共 14 个只读子代理对抗验证，并按用户五轮决策重写，改动记录见第一部分第八节。
> - 外部锚点：HF bucket `HongzeFu/robomme-hard-parity`（公开，978 个对象，454.75 GB）。

# 第一部分（给人看）

## 一、总览

**一句话方案**：以下内容一律原地保留、一个字节不动：

- V9 的 800 局（`16 任务 × 50 局`）数据与评估，连同它们在旧目录里的原件、生成记录与评估记录；
- xhard0（`16 任务 × 1 档 × 12 局 = 192`）的全部数据与评估；
- 历来所有比对、判定与审计记录。

其余删除，范围包括：V6、V7、V8 的大件产物（不属于 V9 也不属于 xhard0 的生成 h5、录像、venv、旧站点），NFS 上本项目的旧克隆与旧目录，旧 worktree，仓库缓存，/tmp 残留。HF 只删一个探针文件。

删除分两步走：

1. 先把要删的东西同盘改名，移进隔离区；
2. 在旧路径已消失的状态下跑完全部闸门，确认无事后，再一次性删掉隔离区。

**已定死口径**（用户原话逐字保留，依据小节写在括号里）

1. **V9 内容不删（用户关键决策，必须保证）**。用户 2026-10-03 原话：「本次V9数据及之前跑过的所有的两次生成都不要删。」「这个是用户关键决策必须保证。」「本次V9数据所包括的内容生成和Evaluate都不要删。」（落实于第二节、第四节、第五节 G1～G8）
2. **两次生成只留与 V9 800 局有关的**。用户在选项中选「只留与 V9 800 局有关的」：
   - 保留：V9 的 H 与 H2；720 个复用局（`14 任务 × 50 局 + InsertPeg 20 局`）在 `newtask-v8/gen1` 里的原件与元数据；所有比对记录。
   - 删除：V7 gen1；V8 gen1 里 350 个非 V9 局（V9 区域示意图用到的 1 局除外，见第四节第 3 条）；NFS `train-parity` 的生成产物；V6 残片。
   - 物理现状：V7、V8 的 H2 实体早已删除（V7 于 09-29，V8 于 10-02）；现存 H2 实体只有 V9 新增的 80 局（`MoveCube 50 局 + InsertPeg 30 局`，都在 xhard4）。（第三节）
3. **所有比对记录都保留**。用户在选项中选「包括，小记录原地保留」：评估、环境、reset 对拍、审计与判定的小记录都算比对记录，原地保留；所在目录里的 h5、视频、venv 照删。（第二节「比对、判定与审计记录」表）
4. **xhard0 全部保留**。
   - 用户原话：「xhard0也都要保留」，随后「xhard0也都要保留 再次审查」。
   - 选项：「数据与评估全留，代码检出照删」。
   - 保留范围：两份 xhard0 h5、冒烟、V7 的 xhard0 评估录像、整个 `v7.5eval`（只删其 venvs）、NFS 上的 xhard0 评估目录与 xhard0 生成脚本。（第二节）
5. **MME 原始材料按只留 V9 删**，用户在选项中选「按只留 V9 删」。xhard0 部分已由口径 4 改为保留，实际只删两样：
   - NFS `hs-logs`：拆包期阶段 7 MME-VLA 在 xhard1～4 上的评估日志，`xhard1/2/3 各 13 任务 × 20 局 + xhard4 16 任务 × 20 局 = 1100`，第三轮核实不含 xhard0；
   - 官方路线的代码检出。

   （第三节 NFS 表）
6. **未开工计划依赖的官方检出照删**。用户在选项中选「照删」：NFS `robomme_policy_learning-official-xhard0` 与 `robomme_policy_learning-testhard-v7` 删除；`SimpleMemVLA-official-xhard0` 按口径 4 的「代码检出照删」一并删除。`1003-oracle-subgoal-groundsg-eval-plan.md` 声明的官方源码 `856bc3a1` 随之不在本地。（第五节风险 9）
7. **只保留最新版本**：
   - 用户 2026-10-03 原话：「我要的就是保留最新的V9其他的都要删除你看现在做的对吗」；
   - 用户 2026-10-02 原话：「历史的产物也要清理……只需要保留最新版本 V9 的生成的 H5 文件和评估的文件」。
8. **数据集冻结**。用户 2026-10-03 原话：「我现在不能够再去改和 Main branch TestHard 一致的数据集了……就必须保持完全一致」。
   - `delivery/` 下 1601 个文件逐字节不变。
   - `delivery.local.json` 不改写，因此它引用的旧目录路径必须原地保留。（第四节第 2 条、G1、G2）
9. **HF 纳入清理，只删 `_probe`**。
   - 用户原话：「把HUGingFace远端的也加入这个计划的清理范围。HUGFace也只保留生成的H5」。
   - 选项：「只删 _probe，留校验清单」。（第三节 HF 行）
10. **artifacts 之外的旧资源全删**。用户勾选「两个旧 worktree 目录, /tmp 下旧会话残留, 仓库内缓存与 runs/」。worktree 只删目录，分支与提交留在 `.git` 里。（第三节）
11. **NFS 不量体积**。用户原话：「我都说了不要去量这个NFS目录的体积了只告诉我哪些要删除直接删了就好了」。按名字遍历、列文件名与大小可以，不跑 `du`。（R6）
12. **站点与未开工的新评估不在本方案范围**。用户原话：「站点先不管MMEVLA的这个也不管……没开工的你也不用管」。
    - 8082 站只保证清理后照现状能打开。
    - 停掉 4 个旧站，是因为它们服务的目录在删除范围内或早已不存在，见第三节。
13. **不用 workflow**。用户原话：「不要使用workflow」。对抗验证只用 Agent 子代理。
14. **零生成、零改码**：reset／轨迹生成预算为 0，不起仿真、不用 GPU；代码（`src/`、`scripts/`、`tests/`）一律不改。
15. **子代理超时统计文件不在清理范围**。`docs/subagent-stats/over-15min.jsonl` 由 12.360 起的 SubagentStop hook 只追加写入，本方案不删、不改；判定工作区 clean 时排除它（`AGENTS.md` 第 11 条例外）。
16. **与并行会话共存**：
    - 噪声基线计划正在本检出提交，在 GL 上持有占位 job 63153922～63153925，并会新建 `artifacts/noise-baseline` 与一个 NFS 克隆。
    - 本方案不碰它的任何东西：worktree、tmux、占位作业记录、新目录都不碰。
    - 闸门判据按「本方案删除集恰好删净、他人新增逐项报告」来写，不按整体相等。
    - 它在运行期间冻结 HEAD 时，本方案阶段 8 的 commit 顺延。（R17）

**预计效果**（按文件实际字节估算，以执行前后 `df` 之差为准）

- 本机 `/data` 释放约 1.15 TiB：`artifacts/` 内约 1.14 TiB，加上 `.cache` 8.9 G、两个旧 worktree 8.4 G。
- 系统盘 `/` 只能释放约 0.85 GB。
  - /tmp 里约 12.6 GB 的旧会话目录，被 57 个仍在运行的 Claude 会话占用。
  - 按 R12，有进程占用的目录不删。
  - 要腾出这部分，需要用户自己关掉那些闲置会话。
- NFS 释放量未量：主要来自 `train-parity` 的生成产物与 3 份 V8 克隆。
- 清理后 `artifacts/` 实际占用约 0.89 TiB：V9 约 0.64 TiB，xhard0 两份 h5 133 GiB，`v7.5eval` 114 GiB，其余小件。
- V9 的交付集与评估树清理后在本机是唯一副本，HF 从未上传过它们（风险 6）。

## 二、保留什么

原则：凡是要留的东西都**原地保留、不搬家**。这样 V9 的索引、评估清单、站点映射、闸门命令里写死的路径全部继续有效。

**V9 本体与它在旧目录里的来源（本机 `artifacts/`）**

| 位置 | 内容 | 为什么留 |
|---|---|---|
| `newtask-v9/` 全部 | `delivery`（800 h5、800 mp4、`delivery.local.json`）；`gen`（80 个新局的第一次生成，站点引用 80 条）；`parity`（80 个新局的第二次生成 23 G，唯一副本，含比对记录）；`specs-root`、`subset-root`、`gates`、`logs`、`site`、`site-media`、`site-checks`、`continue-site`、`xhard0-eval`、`from-v8` | V9 数据集本体、规格、闸门证据、8082 站在用文件 |
| `v9-evaluation/` 全部 | `final`（16717 个文件：800 局 × 2 模型的录像、报告、清单）；`v9-two-policy-gl10-20261002-01`（站点引用 160 条）；`inputs`、`logs` | V9 评估 |
| `branch-alignment/` 全部（611 M） | 12.340「V9 定稿合入 main」时，被压缩的 178 个提交的 `repository.bundle` 与恢复校验记录 | V9 定稿的历史备份与证据 |
| `newtask-v8/gen1` 中 765 个局目录 | 720 个 V9 复用局（h5、mp4 与 `delivery` 硬链接；另有 149 个不在交付集里的 mp4；`rng_trace.json`、`spec_replay.json`）；44 个失败局（V9 冻结规格把其中 41 个记作 V9 生成时的失败行，共 1.02 GB）；`shard1/episodes/xhard4/MoveCube_episode_21`（V9 区域示意图脚本 `v9_movecube_region_fig.py` 从这局读底图与相机参数，306 MiB） | V9 那 720 局的生成原件与元数据，以及 V9 工具的输入；`delivery.local.json` 有 2165 处路径指向这里 |
| `newtask-v8/gen1` 的分片级文件 | `gen1/delivery.local.json`（V9 清单字段 `sources.v8_delivery_sha256` 钉住的那份）；`shard{1..4}/` 下的 `results.jsonl`、`delivery.json`、`shard.json`、`summary.json`、`launch-*.json`、`_rounds/`、`specs/` | 720 局的生成账本；`delivery.local.json` 的 `ledgers` 字段指向它们 |
| `newtask-v8/` 下的 `parity`（`H-v8` 中 349 个非 V9 局的目录除外）、`gates`、`logs`、`sync_gen1*.{sh,stop}` | V8 二次生成比对记录 `HH2-v8`；`H-v8/identities.jsonl` 与 5 个 `launch-*.json`；保留局的软链接；闸门、导入与比对日志 | 720 局的二次生成对拍证据 |
| `v8-evaluation/` 中与 V9 有关的部分 | 1440 个评估记录目录（720 局 × 2 模型，与 `final` 硬链接）；1440 个站点视频；`report/`、`manifest/`、`gl-scripts/`、`nfs-records/`、`interim-0930/`、`inputs/`、`logs/`、`openpi-data/`；`videos/` 下的两个索引文件与 `.incoming/`；`videos.stop`；`site-media/manifest.jsonl` | V9 那 720 局评估所属运行的报告、清单、脚本与 tokenizer；`final/manifest/reused.json` 的 `v8_manifest` 指向这里 |
| `newtask-v7/official-1fadc0ec`（2.7 M） | 官方 `1fadc0ec` 的 `src` 只读快照 | V9 闸门 `XHARD0_RESET_PARITY`（`hard_regression.py xhard0-reset-parity --src-root`）要读 |
| `v7.5eval/assets-lock.json` 与 `preflight/` | 权重锁与建锁脚本 | V9 评估核对权重时用的锁 |

**噪声基线（2026-10-03 补记，本方案执行后新增）**

| 位置 | 内容 | 为什么留 |
|---|---|---|
| `noise-baseline/gen/{v9-a,v9-b,x0-a,x0-b}`（170 G，1890 个文件、354 个 h5） | 噪声基线四遍生成（锚点 `f8f76fba`，GL A40 两节点） | 改码后生成对拍的逐局参照（[`1003-code-test-maintenance-todo.md`](1003-code-test-maintenance-todo.md) 第三节）；计划上传私有 bucket `HongzeFu/robomme-hard-v9-noise-baseline` 作异地副本，本机仍保留 |

**xhard0（口径 4）**

| 位置 | 内容 |
|---|---|
| `newtask-v7/parity/h5/H-xhard0`、`O-xhard0-bucket` | 两份 192 局 h5（各 66.55 GiB，逐字节相同；HF bucket 里另有一份）。V9 闸门 `V9_STEP_CAP` 的 xhard0 那一半、8082 站 subgoal 重建都读它 |
| `newtask-v7/smoke/H-xhard0`、`smoke/O-xhard0`、`smoke/stage3.log` | xhard0 冒烟生成（1.2 G），以及记着两侧冒烟判定行 `NATIVE_SMOKE=PASS … tier=xhard0` 的总日志 |
| `newtask-v7/eval-videos/{mmevla,simplememvla}/xhard0`、`eval-videos/*/moved.jsonl`、`eval-videos-official/` 全部 | V7 两模型在 xhard0 上的评估录像（新路线、官方路线各约 0.53 GiB，sha256 已逐个核对）与索引 |
| `newtask-v7/` 下的 `eval/`、`eval-identities-1292.jsonl`、`eval-official-xhard0-192.jsonl`、`rerun11/`、`xhard0-reset-parity/`、`probe-hard-counts/`、`v7-lengths.json` | xhard0 评估表、身份清单、官方重跑、reset 对拍；xhard0 放置数探针原始日志（`7 任务 × 1 档 × 12 局 = 84` 次 reset，重跑超过授权阈值）；含 xhard0 条目的执行步数统计 |
| `v7.5eval/` 中除 `venvs/` 外的全部（约 114 G） | V7.5 官方路线对这 192 局的完整评估：`official-rec`、`newiface`、`env`、`replay`、`nfs-archive`、`summary`、`lanes`、`logs`、身份与队列清单 |
| NFS `v7-eval`、`v7-eval-stage`、`v7-logs`、`v8eval-xhard0` | MME 与 SimpleMemVLA 在 xhard0 上的官方全量结果、V7 评估结果（1292 = 192 xhard0 + 1100，只有 jsonl 与日志）、xhard0 重跑、评估日志、V8 的 xhard0 评估 |
| NFS `v7-scripts` | xhard0 生成与 V7 评估的启动脚本（`stage5x.sh`、`v7_common.sh`、`eval_v7_shard_remote.sh` 等 12 个小文件），git 里没有 |
| NFS `v7-stage/` 下的 `H-xhard0`、`O-xhard0`、`smoke-H-xhard0`、`smoke-O-xhard0` | xhard0 生成暂存（元数据，加 2 局冒烟） |

**比对、判定与审计记录（口径 3；均为几十 KB 到几 MB 的文本）**

| 位置 | 内容 |
|---|---|
| `newtask-v7/parity/compare`、`newtask-v7/parity/*.log`、`parity/pull-v6.log.{O-native,P-native,P-xhard}.sync` | V7 二次生成与三侧比对记录（`HH2-v7`、`OH-xhard0` 等）与拉取日志 |
| `newtask-v7/logs/` 整个目录（19 个日志，1.1 M） | V7 H:H2 原始判定行 `cmp-h2.log`、xhard0 渲染与官方评估录像搬运日志、stage7 reset 回放日志等 |
| `newtask-v7/` 下的 `smoke/reset-replay.jsonl`、`smoke/step-headroom.json`、`stage7/`、`step-headroom-gen1.json`、`whitelist-check/` | reset 回放比对、步数余量与白名单判定 |
| `newtask-v6/` 下的 `hard-split/compare`、`hard-split/lightweight-baseline-0b.txt`、`hard-split/legacy-keep-list.json`、`audit-fix-02/` | 拆包期三侧比对（与 git 中 `records/stage4/compare-*` 逐字节相同）、短测基线判定、V6 审计修复记录 |
| `train-parity/` 下的 8 个 `local-*/compare`、8 个 `local-*/run_summary.json`、`r1b-final-audit.json`、`r1b-w4-audit.json`、`r1b-final.log`、`r1b-w4.log`、`release-hash-check.log`、`release-hash-full.log` | V3 本机对拍比对、运行摘要、审计判定（`REFERENCE_AUDIT_COMPLETE=PASS compared=144 …`） |
| NFS `robomme_benchmark-newtask-gl/artifacts/train-parity` 下所有名为 `compare` 的目录（68 个） | V3 步 5d／6b 的逐局比对 |
| NFS `hs-stage/reset-replay` | 拆包期 reset 回放比对 |

**NFS 上的环境、权重与他人在用的记录**

| 目录 | 为什么留 |
|---|---|
| `robomme_benchmark-v9two`、`v9two-out`、`v9two-scripts` | V9 评估克隆、三套 venv、分片输入、tokenizer、席位脚本（后两者本机无副本） |
| `robomme_benchmark-v9gen`、`v9gen-out` | V9 生成克隆；冻结规格 `movecube-frozen`、生成与二次生成的日志、脚本、`h2-manifests`（本机无副本） |
| `v8gen-out` | V8 生成（含 V9 的 720 局）的日志、脚本、冻结规格与 H2 重放清单 |
| `eval-out`、`robomme_policy_learning-frameSamp-continue` | `eval-out` 里只有一条软链接，**MME 权重本体在 `frameSamp-continue/runs/ckpts/perceptual-framesamp-modul/79999`**，两者都不能动 |
| `SimpleMemVLA` | SimpleMemVLA 权重（`model.safetensors` 12688542952 字节）与 venv |
| `uv-python` | 所有保留 venv 的解释器 |
| `robomme_benchmark-newtask-gl` 的源码，以及 `artifacts/` 下的 `injection`、`logs` | `<GL_REPO>`，带他人在途改动 93 条 |
| `gl-hold-logs`、`gl-setup-logs` 整个目录 | 占位作业与建环境日志；其中有并行会话今天新建的 `hold-jobs-nb-20261003.txt`、`nb-hold-*`（JobID 63153922～63153925），以及 `AGENTS.md` 记载的 V6 保留占位 job 的日志。别人 `scancel` 时要按这些记录取消，整目录不动 |
| 其他项目的目录 | policy learning、MotionJEPA、sam2act、CoppeliaSim、evalgl 留档等 |

**HF**：bucket `HongzeFu/robomme-hard-parity` 里的全部 h5 与校验清单（`SHA256SUMS`、`identities.jsonl`、`manifest.json`）。

**仓库**：所有分支，包括 `v7-impl`，以及 `v6-draft-*` 上 10 个只在本地的提交；主 `.venv`；`third_party/*`；`docs/subagent-stats/`。

**除 h5 外，V9 最重要的几样**（用户问「除了生成的H5还有哪些是比较重要的可以保留的。最新的数据集的」；以下都在上表）：

- 不可再得的：
  - 交付索引 `delivery.local.json`；
  - 每局 `rng_trace.json`／`spec_replay.json`（720 个在 `newtask-v8/gen1`，80 个在 `newtask-v9/gen`）；
  - 第二次生成 `parity`；
  - NFS 独有的冻结规格 `movecube-frozen`；
  - 评估报告与清单 `final/report`、`final/manifest`；
  - 8082 站的 `site/` 四个 JSON。
- 重要但可重建的：
  - 生成规格 `specs-root`／`subset-root`；
  - 闸门记录 `gates`；
  - 每局 mp4；
  - 权重锁 `assets-lock.json`；
  - `eval-identities` 身份清单。

## 三、删什么

**本机 `artifacts/`**：全部先移进隔离区 `artifacts/.cleanup-quarantine-20261003/`，闸门过后整删。

| 对象 | 规模 | 说明 |
|---|---|---|
| `v8-probe`、`eval-reload-20260929` 整目录 | 6 M、20 K | V8 探针、评估重载测速 |
| `newtask-v6` 中，除第二节列出的比对与审计记录外的全部 | 约 34 GiB | `v6-02`（S4 的 xhard1～4 rollout，h5 在 HF bucket）、`v1`（V6 S3 base 残片 4.8 G）、`smvla-smoke-0927`、两个旧站点、`smvla-0927-logs`、`s4-relaunch-02` 等 |
| `newtask-v7` 中的 `gen1` | 771.5 GiB | V7 第一次生成：`13 任务 × 3 档 × 20 局 + 16 任务 × 1 档 × 20 局 = 1100` 局，不属于 V9 |
| `newtask-v7/parity/h5/P-native`、`parity/h5/H-v7` | 46.7 GiB、软链接 | 拆包期 P 侧 native 拉回缓存（HF bucket 有同名同字节副本）；指向 `gen1` 的 1100 条软链接 |
| `newtask-v7/smoke/{gen,color,v7}`、`smoke-swap` | 约 11.4 GiB | 非 xhard0 冒烟 |
| `newtask-v7/eval-videos/{mmevla,simplememvla}/xhard{1,2,3,4}`、`eval-videos/mmevla/_errors` | 约 5.0 GiB | V7 在 xhard1～4 上的评估录像（不属于 V9 也不属于 xhard0），以及 xhard4 的错误录像 |
| `newtask-v7` 中的 `site`、`site-checks`、`site-media`、`site-oracle-layout-20260930-01`、`site-r11`、`site-task-table-20260930-01`、`impl`、`run` | 约 20 M | V7 站点与实施记录（站点里 xhard0 的 subgoal 快照与 V9 站点逐字节相同） |
| `newtask-v8/gen1` 中 349 个非 V9 局目录 | 218.56 GB | V8 交付了、但 V9 没复用的局：`11 任务 × 30 局 + MoveCube 旧区域 19 局`（原本 20 局，示意图用的那 1 局保留） |
| `newtask-v8/parity/h5/H-v8/episodes` 下对应的 349 个局目录 | 可忽略 | 每个目录里只有一条指向上述局的软链接，不移会悬空 |
| `newtask-v8/` 下的 `beta`、`beta-scripts`、`continue`、`site`、`site-eval-checks`、`tmp` | 约 29 M | V8 beta 站、建站流水、站点目录与截图 |
| `v8-evaluation` 中 700 个非 V9 评估记录目录、700 个非 V9 站点视频、`videos-smoke/` | 91.91 GB、1.00 GB、0.22 GB | 350 个非 V9 局 × 2 模型 |
| `v7.5eval/venvs` | 5.47 GiB | 本机 smvla python 环境，可按 `scripts/eval-official/smvla-env` 重建 |
| `train-parity` 中，除第二节列出的比对与审计记录外的全部 | 约 20 M | V3 本机对拍的官方源码副本、夹具、小 h5、pytest 临时目录、日志 |

**artifacts 之外（本机）**

| 对象 | 规模 | 删法 |
|---|---|---|
| worktree `.claude/worktrees/v7`（分支 `v7-impl`） | 7.6 G | `git worktree remove`，单独一步。核查时 PID 2006672（`claude bg-spare`，已运行 4 天多）的 cwd 就在这里；执行前请用户定：关掉那个进程，还是跳过这个 worktree |
| worktree `/data/hongzefu/v6-draft/{movecube,pipeline,swap,vp}` | 875 M | `git worktree remove`（不加 `--force`，被拒即停）；分支 `v6-draft-*` 与 10 个本地提交保留 |
| 残留 worktree `/tmp/claude-114466650/…/34637e22-…/baseline-wt` | 16 M | `git worktree remove --force`（detached HEAD `504daee5` 已包含在多个分支里） |
| 仓库根 `.cache/`、`runs/` | 约 8.9 G、6.6 M | `rm -rf` |
| `/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/` 下的旧会话目录 | 约 37 MB 可删 | 按 R12 生成清单。约 12.6 GB 的目录被仍在运行的 Claude 会话占用，不删 |
| `/tmp/pytest-of-hongzefu/` 下的旧编号目录 | 约 0.69 GB | 按 R12 规则：mtime 早于 10-02，且没有进程占用。核查时 1085、1086、1141、1153 符合；1158、1162、1201 被孤儿测试服务占用，1218、1227 被活进程占用，都不动 |
| `/tmp/v8-s4a-*` 共 13 个条目，以及本会话产生的 `/tmp/claude-114466650/adv` | 约 0.12 GB | `rm -rf` |

**NFS**：先移进 NFS 隔离区 `.cleanup-quarantine-20261003/`，闸门过后整删。

| 对象 | 说明 |
|---|---|
| `robomme_benchmark-newtask-gl/artifacts/train-parity` 中所有不在 `compare` 目录里的子树 | V3 步 5d／6b 的生成产物（含官方基线的两次生成，不属于 V9）；保留 68 个 `compare` 目录 |
| `robomme_benchmark-newtask-gl/artifacts/` 下的 `audit`、`gl-probe`、`hold-logs` | V6 语义审计、吞吐探针、V6 占位日志 |
| `robomme_benchmark-v8gen`、`robomme_benchmark-v8eval`、`robomme_benchmark-v8two` | V8 代码克隆，HEAD 均已在 `origin/newtaskRelease-taskV8`；删前过门禁（R15） |
| `v7` | V7 的 xhard1～4 规格与候选池 |
| `v7-stage/` 下的 `H2-v7`、`H-native`、`H-xhard` | V7 H2 元数据与拆包期暂存（媒体早已搬空，身份文件里没有 xhard0） |
| `SimpleMemVLA-official-xhard0`、`robomme_policy_learning-official-xhard0`、`robomme_policy_learning-testhard-v7` | 官方路线策略代码检出（口径 6），分支都在 origin |
| `newtask-v4-gl`、`slurm-holds`、`hs-scripts`、`hs-xhw-probe-20260927`、`hs-logs` | V4 占位记录、V3 的 GL 脚本与日志、拆包期脚本（原文已在 git）、跨硬件探针（阶段 0 先把 4 个结果小文件抄进 git）、拆包期 MME 对 xhard1～4 的评估日志（口径 5） |
| `hs-stage/` 中除 `reset-replay` 外的 8 个子目录 | 拆包期暂存，媒体早已搬空 |

**HF**：只删 `HongzeFu/robomme-hard-parity/_probe/bucket-probe.txt` 这一个探针对象。核查结果：

- 本项目在 HF 上只有这一个 bucket，其余对象都是 h5 与校验清单；
- V7、V8、V9 的生成与评估从未上传；
- 名下其余 16 个 bucket 以及 model／dataset／space 都属于其他项目。

**站点进程**：停 `site-v12-8060`、`site-v7-8070`、`site-v8beta-8080`、`site-v8-8081` 四个 tmux 会话，原因如下：

- 8060、8070 服务的是 `newtask-v6`、`newtask-v7` 里的站点目录；
- 8080 服务的 `newtask-v8/beta/site` 在删除范围内；
- 8081 的 `--site-dir artifacts/newtask-v8/site-eval` 10-02 已搬走，进程实际在空转。

**明确不动**：

- 分支；
- `robomme_benchmark-newtask-gl` 的源码与在途改动；
- `gl-hold-logs`、`gl-setup-logs`；
- 他人的 worktree（如 `.claude/worktrees/agent-*`）；
- tmux 里不属于本清单的会话：`claude-newtask`、`codex-812`、`corlvis-site`、`site-v9-8082` 及并行会话新起的会话；
- 非本方案起的进程：PID 214366、3506944、3522984、2006672 等；
- `docs/subagent-stats/`；
- `/data/hongzefu/robomme_benchmark_MotionJEPA` 等其他仓库。

## 四、为什么删这些不会碰到要留的东西

1. **硬链接：V9 数据字节由 V9 的名字持有，另一个名字也不动。**
   - `delivery/` 下 1601 个文件中，1600 个链接数为 2：720 局的另一个名字在 `newtask-v8/gen1`，80 局的在 `newtask-v9/gen`。
   - `final` 的 16717 个文件中，16000 个链接数为 2：14400 个的另一个名字在 `v8-evaluation`，1600 个在 `v9-two-policy-gl10-20261002-01`。
   - 本方案对 V8 目录按局目录、评估记录目录来划分，V9 文件的两个名字都留下。
   - 第三轮模拟：移走集里所有文件的链接数都是 1，没有任何一个与保留文件共享 inode。
2. **原地保留：V9 写死的路径全部有效。** V9 有以下几处路径写死在旧目录里：
   - `delivery.local.json` 中，720 行的 `path`／`h5`／`video`，加上 `ledgers` 与 `sources`，共 2165 处指向 `newtask-v8/gen1`；
   - `final/manifest/reused.json` 的 `v8_manifest` 字段；
   - V9 评估核对权重时读 `v7.5eval/assets-lock.json`；
   - 闸门 `XHARD0_RESET_PARITY` 读 `newtask-v7/official-1fadc0ec`；
   - `V9_STEP_CAP` 读 `H-xhard0/identities.jsonl`；
   - 站点 subgoal 重建读两份 xhard0 h5。

   第三轮按方案规则精确模拟（本机移走 2204 条、NFS 移走 783 条），上述引用全部落在保留集，缺失 0。
3. **V9 工具的输入也留下。**
   - `v9_movecube_region_fig.py` 写死读 `newtask-v8/gen1/shard1/episodes/xhard4/MoveCube_episode_21`，这一局单独保留。
   - V9 冻结规格的 `rollout.status=failed` 行中，有 41 个指向 V8 的失败局；44 个失败局全部保留。
   - 另有 330 个「生成成功、试过、但没选进 V9」的局按口径 2 删除，V9 规格里只剩它们的 sha 与路径记录。
4. **软链接。** 保留树里共 801 条软链接，删后全部仍指向保留对象：
   - V9 的 80 条指向 `newtask-v9/gen`；
   - `H-v8` 保留的 721 条：720 个 V9 局加示意图那一局。

   `H-v8` 中指向被删 349 局的那些，连同所在局目录一起移走。
5. **8082 站。**
   - 服务进程把 `site/media-private.json` 的 3164 条路径解析成 `artifacts/` 下的相对路径，收到请求时逐级打开。
   - 3164 条全部落在 `newtask-v9` 与 `v9-evaluation`。
   - 删前基线：3164 个媒体的 HEAD 请求全部返回 200，长度等于文件大小。
6. **先隔离、后删除。**
   - 要删的对象用 `mv -T --no-copy` 同盘改名、移进隔离区：瞬间完成、可原样移回；跨设备时直接报错，不会退化成复制。
   - 每条移动前先写 `INTENT`、成功后写 `QUARANTINED`，回滚以 `INTENT` 为准。
   - 在旧路径已消失的状态下跑全部闸门，漏网的引用这时就会暴露；全部 PASS 后才删隔离区。
7. **⚠ 代价**（删后跑不动的是「重跑」，不是「复核」）：
   - **本机 SimpleMemVLA 新接口的 xhard0 重跑与开环重放**：
     - `run_seat.sh`、`run_policy_replay.sh`、`v75-lanes/local/*.sh` 默认的 `SMVLA_PY` 指向被删的 `v7.5eval/venvs`；
     - 解决办法：设 `SMVLA_PY=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-v9two/artifacts/v8-two/venvs/smvla-env/bin/python`（保留，同为 uv-python 3.10.19），或按 `scripts/eval-official/smvla-env` 重建。
   - **xhard0 官方路线的重跑与观察**：
     - 涉及 `official_observer/*.sh`、`policy_replay.py` 的 `OLD_*`、`v75-lanes/gl/*`、`rerun11/run_rerun11.sh`、`newtask-v9/xhard0-eval/lanes/*`；
     - 依赖被删的三个官方检出与 `robomme_benchmark-v8eval` 克隆；
     - 代码可从 origin 分支取回，venv 要重建。
   - **V8 级旧入口**：`hard_parity.py --tier v8`、`v8_report.py`／`v8_site_catalog.py` 的非 V9 模式、`v7_site_catalog.py`、`v8gen-out/scripts/*.sh` 会因读不到被删对象而报 missing。
   - **复核不受影响**：`compare.py`、`step6_summary.py`、`hard_regression.py xhard0-reset-parity/xhard0-eval-parity` 读的全是保留对象，照常可跑。
   - **其他历史默认路径失效**：例如 `site_server.py` 的 `DEFAULT_SITE_DIR`、`docs/validation/parity-anchors.json` 登记的 `H-v7`。
   - 代码按口径 14 不改；失效清单与恢复办法写进留档。

## 五、验收

| 编号 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| G1 | 交付集逐字节没变 | 删前、隔离后、删后三次，对 `delivery/` 下全部 1601 个文件算 sha256（`LC_ALL=C` 排序，stderr 单独落盘），三份清单完全相同；再与 `delivery.local.json` 中 800 个 `h5_sha256`、800 个 `video_sha256` 逐条对照 | 数据集与索引都没被碰，基线本身也没坏 | `V9_DELIVERY_SHA=PASS files=1601 changed=0 recorded_match=1600` |
| G2 | V9 交付清单仍可用 | 逐行解析 `delivery.local.json` 的 `path`（按 `hard_parity.delivery_h5` 的口径）、`h5`、`video`、`ledgers`、`sources`，全部存在；`h5` 与 `delivery/episodes/...` 同 inode；`sources` 中三份 sha256 与记录相等 | 2165 处 V8 路径与 V9 路径都没断 | `V9_DELIVERY_INDEX=PASS rows=800 refs_v8=2165 missing=0 sources_sha=3/3` |
| G3 | 765 个保留局与分片文件没变 | 删前与隔离后，各生成一份「相对路径、大小、inode、mtime」清单（只含常规文件与软链接，不含目录项），逐行相同 | V9 720 局、44 个失败局、示意图那一局，以及分片账本都在 | `V9_REUSE_META=PASS episodes=765 files_equal=1` |
| G4 | 评估没变 | 对 `v9-evaluation/` 全树与 `v8-evaluation` 保留部分做同口径清单的前后对比；`reused.json` 的 `v8_manifest` 存在且 sha256 相等 | 800 局 × 2 模型的评估与出处都在 | `V9_EVAL_TREE=PASS final_files=16717 v8_kept_records=1440 equal=1` |
| G5 | 两次生成、xhard0、比对记录没变 | 对第二节「xhard0」与「比对、判定与审计记录」两张表的全部本机对象，以及 `newtask-v9/parity`、`newtask-v7/official-1fadc0ec`、`branch-alignment`、`newtask-v8/{parity,gates,logs,sync_gen1*}`，做同口径清单的前后对比；三处 `parity/compare` 逐文件 sha256 前后相同 | 用户口径 2、3、4 要保留的全部在原处 | `KEEP_RECORDS=PASS objects=<n> files_equal=1 compare_sha=equal` |
| G6 | 没有断链 | 对保留目录逐个先 `[ -d ]`，再 `find … -xtype l -print 2>>err \| wc -l`，结果为 0 且 err 为空 | 801 条软链接都没断 | `V9_LINKS=PASS broken=0 find_err=0` |
| G7 | 8082 站照常 | (a) 对 catalog 全部 3164 个媒体 ID 发 HEAD，全部 200 且长度等于文件大小；`/`、`/api/catalog`（753043 B）、`/api/subgoals`（1793706 B）、`/api/semantic`（183940 B）字节数与基线相同。(b) 用第二部分第四节的命令跑浏览器检查 | 页面与全部视频可打开 | `V9_SITE_MEDIA=PASS ids=3164 ok=3164`；`V8_ORACLE_BROWSER=PASS cells=59 missing=0 mismatch=0 page_errors=0`；`V9_SITE=PASS cells=59 eval_reused=720 eval_new=80 eval_empty=0 port=8082` |
| G8 | NFS 保留项与权重没变 | 删前与隔离后，对 `v9two-out`、`v9two-scripts`、`v9gen-out`、`v8gen-out`、`v7-eval`、`v7-eval-stage`、`v7-logs`、`v7-scripts`、`v8eval-xhard0`、`v7-stage` 的 4 个 xhard0 子目录、`hs-stage/reset-replay`、train-parity 的 68 个 `compare` 目录，以及两份权重目录（`SimpleMemVLA/checkpoints/simplememvla_robomme`、`frameSamp-continue/runs/ckpts/perceptual-framesamp-modul/79999`），生成「路径、大小」清单逐行相同；`v9two`、`v9gen`、`newtask-gl` 的 HEAD 与 `git --no-optional-locks status --short` 前后相同；`v9two` 三套 venv 的 `bin/python -c 'import sys'` 能起，`.pth` 指向存在；`eval-out/.../79999` 的软链接目标存在 | V9 与 xhard0 在 NFS 上的记录、环境、权重都在 | `V9_NFS=PASS files_equal=1 git_equal=3 venvs=3 weights_equal=2 mme_ckpt=ok` |
| G9 | 包内规格与测试不受影响 | `pytest tests/lightweight/test_v9_packaged_800.py -q -s`；核心短测在删前、隔离后、删后各跑满一次（不加 280 s 超时，实测约 490 s），每次记录当时的 HEAD、`passed`／`skipped`／`failed` 与 FAILED 的 nodeid 集合。两次 HEAD 相同时，三个数与 FAILED 集合都必须相同；HEAD 被并行会话推进时，只比较两次之间未改动的测试文件，要求没有新增失败 | 冻结规格没动，测试不依赖被删目录 | `V9_PACKAGED=PASS total=800 per_task=50 cells=43`；`CORE_TESTS=SAME head_same=<0\|1> new_failures_in_unchanged=0` |
| G10 | 清单删净、没多删 | 本机：第一节全部移走路径在删后都不存在；`ls -1A artifacts` 删后包含且只多出不属于本方案的条目，即 9 个目录加上逐项报告的他人新增（如 `noise-baseline`）；部分保留目录里只剩第二节列出的对象。NFS：顶层 `comm -23 前 后` 恰为第三节 12 个整删目录名，`comm -13` 的新增逐项报告归属。worktree：删掉的恰为第三节 6 个，他人的不动。HF：用 JSON 列表比较，文件数少 1，字节数少探针大小 | 没有漏删、没有多删 | `CLEANUP_LOCAL=PASS moved=2204 leftover=0 others_new=<n>`；`CLEANUP_NFS=PASS removed_top=12 leftover=0 others_new=<n>`；`CLEANUP_OTHER=PASS worktrees=6 tmp=<n>`；`CLEANUP_HF=PASS files=977 bytes_delta=<探针字节数>` |

**G1 能逐字节成立的理由**：全程不写 `delivery/`；本方案也不碰 V9 文件的另一个名字。

**G9 中「失败数」的口径**：`docs/validation/newtask-v9/cleanup-20261002.md` 记录核心短测基线已有 6 个失败（4 个真失败，加 2 个连带的 `test_zz_summary_line`）。G9 只要求删除不新增失败，不要求为 0。

## 六、实施步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 前置核对与基线：<br>· 记录 `BASE=HEAD`、工作区、`df`、`tmux ls`、`git worktree list`、NFS 顶层 `ls -1A`；<br>· 与并行会话对齐：其 tmux 会话、GL 占位、是否声明冻结 HEAD；<br>· 把 `hs-xhw-probe` 的 4 个结果文件抄进 `docs/validation/newtask-v6/hard-split/records/xhw-probe/` 并 `cmp`；<br>· 过 R15 门禁（4 个整仓 + 2 个官方 worktree）；<br>· 生成 11 份清单并断言计数；派只读审查者审清单与脚本；<br>· 起 sha 基线与核心短测基线（tmux，各挂 Monitor）；<br>· 做 G3～G5、G8 指纹基线与 G7 站点基线 | `XHW_COPY=PASS files=4`；`CLONE_GATE=PASS repos=6`；`CLEANUP_LIST_REVIEW=PASS lists=11 scripts=<n> findings=0`；sha 日志末行为 `EXIT_CODE=0 lines=1601 errbytes=0`；`CORE_RUN tag=before …` |
| 1 | 确认 sha 基线与核心短测基线都已结束，再停 4 个旧站点（每个都走三步）；之后查端口释放、8082 仍通 | 每次 `comm -23 前 后` 恰为目标会话；`ss -ltn` 中没有 8060／8070／8080／8081 |
| 2 | 本机隔离：按 9 份本机清单把对象移进 `artifacts/.cleanup-quarantine-20261003/`，保持相对路径 | `INTENT` 与 `ALREADY` 行数之和等于清单行数，没有 `REFUSE` |
| 3 | NFS 隔离：同样移进 NFS 隔离区 | 同上；`REFUSE-XDEV` 只登记、不直删，交用户；其他 `REFUSE` 即停 |
| 4 | 在隔离状态下跑 G1～G9（sha 跑完、核心短测跑完才判） | 全部 PASS；任一 FAIL，按 INTENT 逆序移回，停下交用户 |
| 5 | 删本机隔离区（tmux `cl-rm-local`）与 NFS 隔离区（tmux `cl-rm-nfs`，带进度心跳）；对 `SimpleMemVLA` 跑 `git worktree prune` | 两份日志末行 `EXIT_CODE=0`；隔离区不存在；`SimpleMemVLA` 的 worktree 只剩主检出 |
| 6 | artifacts 之外：<br>· 先扫描进程；<br>· 删 v6-draft 四个与 `baseline-wt`；<br>· V7 worktree 按用户对 PID 2006672 的裁决处理；<br>· 跑 `git worktree prune`；<br>· 删仓库 `.cache`、`runs`；<br>· 按清单删 /tmp 残留；<br>· HF 先存 JSON 快照，再 dry-run 与删除 | 逐条 `DONE`；HF 前后 JSON 差恰为 1 个文件 |
| 7 | 删后复验 G1、G2、G6、G7、G9，并跑 G10 | 全部 PASS；记录 `df` 前后差 |
| 8 | 写留档 `docs/validation/newtask-v9/cleanup-20261003.md`；更新以下文档：<br>· `CLAUDE.md`「现有 worktree 不动清单」；<br>· `docs/1002-pending-decisions.md` 的 A2（V7／V8 H2 已删的现状）、A3、A4、F1、F3、F4、B4；<br>· `1003-code-test-maintenance-todo.md` 的对应复选框。<br>commit 并 push。并行会话冻结 HEAD 期间顺延 | `git status -sb` 无 ahead |

阶段 0～4 全部可逆。不可逆的只有阶段 5、6 的删除，它们只在阶段 4 全部闸门通过之后执行。

## 七、子代理分工与合并（简述）

本方案没有代码改动，全部是对数据的破坏性操作，所以不拆给写入型子代理，由主会话逐条执行、逐条核对，也就没有合并步骤。

只在一处用只读子代理：阶段 0 生成删除清单与执行脚本后，派 1 个审查者（sonnet）核对以下几点：

- 11 份清单与本方案第二、三节逐项一致，计数断言成立；
- 没有任何路径落在 R3 冻结区；
- 没有任何删除路径是保留对象的祖先或后代；
- 脚本与第二部分第四节一致。

闸门由主会话自己跑，审查者不跑命令。

## 八、对抗验证记录

**第一轮**：8 个只读子代理，核查初版方案。

| 初版问题 | 本版处理 |
|---|---|
| 把 V9 内容列进删除：NFS `v9gen-out`、`v9two-out`、`v9two-scripts`、`robomme_benchmark-v9gen` | 改为保留 |
| 整删 `newtask-v8`／`v8-evaluation`，会让 V9 交付清单 2165 处路径悬空，并丢失 720 局的元数据、账本、评估报告 | 原地保留与 V9 相关的部分 |
| 要搬已经搬走的 `newtask-v8/site-eval`；写成「`eval-out` 是权重」；HF 表述不准 | 删去这一步；按事实改写 |
| 漏删 NFS 旧目录、GL 克隆内的旧子目录、artifacts 之外的旧资源；没写 `SimpleMemVLA` 的 worktree 善后 | 补进清单；加 prune |
| runbook 多处缺陷 | 重写 |

**第二轮**：3 个只读子代理，核查第一轮修订版。

| 发现 | 本版处理 |
|---|---|
| V9 闸门与工具还读 `official-1fadc0ec`、xhard0 h5、示意图那一局 | 三处保留；xhard0 按用户裁决全留 |
| 比对记录被我写窄；44 个失败局被 V9 规格引用；`branch-alignment` 是 V9 定稿的提交 bundle | 都改为保留 |
| `hs-xhw-probe` 的抄录排在删除之后；R3 与 `H-v8` 移走自相矛盾；`pytest-1158`／`1162` 被孤儿服务占用；核心短测会被 280 s 截断；移动函数与回滚的若干缺口 | 逐项修复 |

**第三轮**：3 个只读子代理（xhard0 漏网搜查、保留集精确模拟、runbook 与完备性），核查第二轮修订版。

| 发现 | 本版处理 |
|---|---|
| xhard0 的 h5、录像、评估结果表无一漏网；本机移走 2204 条、NFS 783 条精确模拟，没有任何保留路径落进删除集，801 条保留软链接全部有效 | 结论写入第四节 |
| 4 处小 xhard0 记录仍在删除集：`probe-hard-counts`、`v7-lengths.json`、`smoke/stage3.log`、NFS `v7-scripts` | 改为保留 |
| `hs-logs` 被我误归为 xhard0，实为拆包期 MME 对 xhard1～4 的评估日志 | 按口径 5 删除 |
| `train-parity` 的 `r1b-*.log` 与 `run_summary.json`、`newtask-v6` 的审计与基线判定记录是判定类记录 | 补进保留 |
| G4 的权重核对用的是 V8 版脚本，V9 判 PASS 的版本只在临时目录，照做必然 FAIL | 删去该项，改由 G8 核对权重目录的文件名与大小 |
| `gl-hold-logs` 里有并行会话今天新建的活占位记录（JobID 63153922～63153925） | 两个日志目录整个不动 |
| 并行会话在推进 HEAD、新建 worktree 与目录 | G9、G10 改成能容忍他人新增；加 R17 |
| /tmp 实际只能释放约 0.85 GB；pytest 排除名单已过期 | 预期改为实数；pytest 改为按规则判定 |
| PID 2006672 的 cwd 在 V7 worktree，会让阶段 6 整段卡住 | V7 worktree 拆成单独一步，执行前请用户裁决 |
| NFS 删除心跳与进度无关、子 shell 延迟 `tee` 结束；清单循环对空清单或缺尾换行不设防；R15 漏了两个官方 worktree；R-1 不审脚本 | 第二部分逐项修复 |
| 子代理核查的副作用：对 8082 发了 3164 次 HEAD，访问日志多出约 3200 行；有子代理误起过 `find /`，已停，只读 | 如实记录 |

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- **R1 只删清单内对象。**
  - 所有路径写字面绝对路径，不用 glob，不用未回显的变量拼接；禁止 `git clean`。
  - 批量对象只能来自阶段 0 生成、断言计数、经 R-1 审查的清单文件。
  - 清单每行格式 `kind<TAB>绝对路径`，`kind ∈ {dir, link, file}`，文件以换行结尾。
- **R2 移动前过 `q1` 守卫**（见第四节），任一项不满足就打印 `REFUSE-*` 并停：
  - 路径在根之下；
  - 路径形式合法（无尾斜杠、无 `//`、`.`、`..`）；
  - `kind` 合法，且对象类型与 `kind` 相符；
  - 祖先不是软链接；
  - 目标不存在；
  - 与隔离区同设备。

  移动一律用 `mv -T --no-copy`。
- **R3 冻结区零写入。** 第二节所列全部保留对象构成冻结区。例外：
  - `newtask-v8/parity/h5/H-v8/episodes` 下，清单 `h-v8-drop.txt` 列出的 349 个局目录可移走；
  - `newtask-v9/logs/` 下允许两种追加：新建的 `cleanup-20261003/`（日志与基线，记为 `L`），以及 8082 访问日志随 G7 媒体扫描的追加；
  - 允许新建隔离区 `artifacts/.cleanup-quarantine-20261003/`（阶段 5 删除）。
- **R4 tmux 只用精确停。** 只用 `tmux kill-session -t '=<完整名>'`。停之前、停之后各取 `tmux ls | cut -d: -f1 | sort`，要求 `comm -23 前 后` 恰为目标会话（他人新建的只记录，不判失败）。本方案自起的会话名不含 `.`，统一前缀 `cl-`。
- **R5 GL 克隆只动 artifacts 下的指定部分。** `robomme_benchmark-newtask-gl` 只动 `artifacts/train-parity` 中的非 `compare` 子树，以及 `artifacts/` 下的 `audit`、`gl-probe`、`hold-logs`；`git --no-optional-locks status --short` 前后逐字相同。
- **R6 不碰集群、不量 NFS。** 不提交 GL 作业、不 ssh 集群；NFS 从本机挂载点操作，按名字遍历、列文件名与大小可以，不跑 `du`。
- **R7 基线先行。** sha 基线日志末行出现 `EXIT_CODE=0 lines=1601 errbytes=0`、且核心短测基线 `CORE_RUN tag=before` 已出现之前，不移动任何对象。各个比对脚本先断言对应日志已完成，否则报 `NOT_READY`，不判 FAIL。
- **R8 不符即停。** 任何一步的实际输出与预期不符就停，原始输出交用户；不自行改判据。
- **R9 闸门 FAIL 就回滚。** 阶段 4 任一闸门 FAIL：按 `INTENT` 逆序，凡是隔离区有、原处无的就移回；复跑 G1～G6 确认已恢复，停下交用户。
- **R10 HF 只删一个对象。** 只删 `_probe/bucket-probe.txt`。删前用 `--format json` 存全量快照，断言该对象存在；删后再存一份，只比 `type=file` 的条目。token 不打印。
- **R11 worktree 只用官方命令删。**
  - 只用 `git worktree remove`：`v7` 与 `v6-draft` 都不加 `--force`，被拒即停；`baseline-wt` 加 `--force`。
  - 分支一律不删。
  - 删前扫描 `/proc/*/cwd`，有进程落在目标里就停下交用户（V7 worktree 现有 PID 2006672）。
  - 绝不对 worktree 路径用 `rm -rf`：V7 worktree 里有一条指向主检出 `artifacts/` 的软链接。
- **R12 /tmp 条目的删除条件**，四条同时满足才删：
  - 是第三节列出的类型；
  - 不是本会话目录 `88a7da99-…`；
  - 目录内所有文件的 mtime 都早于本机时间 2026-10-02 00:00；
  - 扫描 `/proc/*/cwd` 与 `/proc/*/fd`，没有任何进程落在其中；对 `find`、`bfs`、`du` 这类正在遍历的进程造成的瞬时命中，10 秒后复扫一次再判。

  以上规则对会话目录、`/tmp/pytest-of-hongzefu/*`、`/tmp/v8-s4a-*` 一视同仁；清单在阶段 6 执行前现场生成。`34637e22-…` 要先对其中的 `baseline-wt` 跑 `worktree remove`。
- **R13 不碰别人的进程。** 不 kill 非本方案起的进程（PID 214366、3506944、3522984、2006672 等），只报告给用户。
- **R14 零生成。** reset／轨迹生成预算为 0，不用 GPU。
- **R15 整仓删除门禁。** 对 `robomme_benchmark-v8gen`、`robomme_benchmark-v8eval`、`robomme_benchmark-v8two`、`robomme_policy_learning-testhard-v7`、`robomme_policy_learning-official-xhard0`、`SimpleMemVLA-official-xhard0` 共 6 个：
  - `git --no-optional-locks status --short --ignore-submodules=dirty` 为空；
  - `git log --branches --not --remotes --oneline` 为空；
  - `git stash list` 为空；
  - 若存在 `artifacts/`，其下没有 h5、mp4、mkv、`report*.json`、`results.jsonl`；目录不存在视为通过。

  判定行：`CLONE_GATE=PASS repos=6`。
- **R16 grep 一律用 `/usr/bin/grep`**，或用 Python 解析。本机 `grep` 是 ugrep 包装，会跳过 gitignore 路径。
- **R17 与并行会话共存。**
  - 不碰他人的 worktree、tmux、占位作业记录、新建目录（`artifacts/noise-baseline`、NFS 新克隆等）。
  - 判据只要求本方案的删除集删净；他人新增的条目逐项报告，不判失败。
  - 他人声明冻结 HEAD 期间，本方案不 commit。
  - 核心短测按 G9 的 HEAD 规则比较。

## 一 逐项清单

以下路径中，`A` = `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts`，`N` = `/nfs/turbo/coe-chaijy-unreplicated/hongzefu`。

**部分保留目录的统一算法**（`cl_lists.py::prune_plan`）：

- 输入：一个根，以及该根下的保留路径集合（第二节逐项展开为具体路径）。
- 输出：根下「既不是保留路径、也不是保留路径祖先」的**最大子树**集合，即要移走的对象。
- 断言三条：
  - 保留集 ∪ 移走集覆盖根下全部叶子；
  - 两集之间没有祖先或后代关系；
  - 保留集中每条路径都存在。

**本机清单 9 份**（根统一为 `A`，隔离区统一为 `Q`，日志 `$L/quarantine-local.log`）

| 清单文件 | 内容与断言 |
|---|---|
| `local-whole.txt` | 2 行：`v8-probe`、`eval-reload-20260929` |
| `local-prune-v6.txt` | `A/newtask-v6` 保留 `hard-split/compare`、`hard-split/lightweight-baseline-0b.txt`、`hard-split/legacy-keep-list.json`、`audit-fix-02` |
| `local-prune-v7.txt` | `A/newtask-v7` 保留第二节三张表中的 `newtask-v7` 条目；断言移走集包含 `gen1`、`parity/h5/P-native`、`parity/h5/H-v7`、`smoke/gen`、`smoke/color`、`smoke/v7`、`smoke-swap`、8 个 `eval-videos/*/xhard{1..4}`、`eval-videos/mmevla/_errors`，以及 6 个 site 目录和 `impl`、`run`；不含 `probe-hard-counts`、`v7-lengths.json`、`smoke/stage3.log` |
| `local-prune-trainparity.txt` | `A/train-parity` 保留 8 个 `local-*/compare`、8 个 `local-*/run_summary.json` 与 6 个审计、哈希、判定文件 |
| `v8-gen1-drop.txt` | `A/newtask-v8/gen1` 局目录：`all=1114 v9=720 failed=44 fig=1 drop=349` |
| `h-v8-drop.txt` | `A/newtask-v8/parity/h5/H-v8/episodes` 下目标落在上述 349 局的局目录：`total=1070 drop=349 keep=721` |
| `v8-top-drop.txt` | 6 行：`beta`、`beta-scripts`、`continue`、`site`、`site-eval-checks`、`tmp` |
| `v8-eval-drop.txt` | `A/v8-evaluation/v8-two-policy-gl10-20261002-01` 下：记录目录 `all=2140 shared=1440 drop=700 mixed=0`；站点视频 `drop=700`；`videos-smoke` |
| `local-v75-drop.txt` | 1 行：`v7.5eval/venvs` |

**NFS 清单 1 份 `nfs-drop.txt`**（根 `N`，隔离区 `NQ`，日志 `$L/quarantine-nfs.log`）

- 整删 12 个顶层目录：`robomme_benchmark-v8gen`、`robomme_benchmark-v8eval`、`robomme_benchmark-v8two`、`v7`、`SimpleMemVLA-official-xhard0`、`robomme_policy_learning-official-xhard0`、`robomme_policy_learning-testhard-v7`、`newtask-v4-gl`、`slurm-holds`、`hs-scripts`、`hs-xhw-probe-20260927`、`hs-logs`。
- 子目录：
  - `robomme_benchmark-newtask-gl/artifacts/` 下的 `audit`、`gl-probe`、`hold-logs`；
  - `v7-stage/` 下的 `H2-v7`、`H-native`、`H-xhard`；
  - `hs-stage/` 下的 `H-native`、`H-xhard`、`H-xhard-r2`、`O-native`、`P-native`、`smoke-H-native`、`smoke-O-native`、`smoke-P-native`。
- `robomme_benchmark-newtask-gl/artifacts/train-parity`：按 `prune_plan` 算出，保留所有名为 `compare` 的目录（68 个）；只按名字遍历。核查时移走 721 条（541 个目录、180 个文件）。
- 合计断言 `n=783`。

**/tmp 清单 1 份 `tmp-drop.txt`**：在阶段 6 执行前按 R12 现场生成，覆盖会话目录、`pytest-of-hongzefu` 编号目录、`/tmp/v8-s4a-*` 13 个条目、`/tmp/claude-114466650/adv`。

**worktree**（不进清单，逐条命令）：

- `…/robomme_benchmark_MotionJEPANewTask/.claude/worktrees/v7`；
- `/data/hongzefu/v6-draft/movecube`、`pipeline`、`swap`、`vp`；四个删完后 `rmdir /data/hongzefu/v6-draft`；
- `/tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/34637e22-b1a7-4754-a153-cae509fb6261/baseline-wt`。

**仓库缓存**：`…/.cache`、`…/runs`。

**HF**：`HongzeFu/robomme-hard-parity/_probe/bucket-probe.txt`。

**tmux**：`site-v12-8060`、`site-v7-8070`、`site-v8beta-8080`、`site-v8-8081`。

## 二 子代理分配表

| 子任务编号 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（在哪里、以什么环境跑） | 资源占用 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| 主会话自做 | 阶段 0～8 | 第三节对象；R3 允许新增的目录；`docs/validation/newtask-v6/hard-split/records/xhw-probe/`；`CLAUDE.md`「现有 worktree 不动清单」一行；`docs/1002-pending-decisions.md`；`1003-code-test-maintenance-todo.md`；留档 | R3 冻结区；R17 他人对象 | 无 | 无（不派写入型子代理） | G1～G10，均在主检出、主 `.venv` 下跑（`cd $R && uv run --no-sync …`）；浏览器检查用 `uv run --no-project --with playwright` | 不用 GPU；tmux 前缀 `cl-` | 全部归主会话 |
| R-1（只读，sonnet） | 审查 11 份清单与 `cl_*` 脚本 | 无 | 全部 | 读阶段 0 的清单、脚本与本方案 | 无 | `CLEANUP_LIST_REVIEW=PASS\|FAIL lists=11 scripts=<n> findings=<n>` | 无 | 无 |

## 三 闸门总表

| 判定项 | 何时跑 |
|---|---|
| `XHW_COPY`、`CLONE_GATE`、`CLEANUP_LIST_REVIEW` | 阶段 0 |
| G1 `V9_DELIVERY_SHA` | 阶段 0 基线、阶段 4、阶段 7 |
| G2 `V9_DELIVERY_INDEX` | 阶段 4、阶段 7 |
| G3 `V9_REUSE_META`、G4 `V9_EVAL_TREE`、G5 `KEEP_RECORDS` | 阶段 0 基线、阶段 4 |
| G6 `V9_LINKS` | 阶段 4、阶段 7 |
| G7 `V9_SITE_MEDIA` + `V8_ORACLE_BROWSER` + `V9_SITE` | 阶段 0 基线、阶段 4、阶段 7 |
| G8 `V9_NFS` | 阶段 0 基线、阶段 4 |
| G9 `V9_PACKAGED` + `CORE_TESTS` | 阶段 0 基线、阶段 4、阶段 7 |
| G10 `CLEANUP_LOCAL`、`CLEANUP_NFS`、`CLEANUP_OTHER`、`CLEANUP_HF` | 阶段 7 |

任一 FAIL 即停，不改判据。

## 四 runbook

所有脚本落在本会话 scratchpad，开头写死下面的固定量，不依赖上一条命令的 shell 状态；用 `bash <文件>` 启动；Python 一律 `cd $R && uv run --no-sync python …`。

```bash
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask
A=$R/artifacts
L=$A/newtask-v9/logs/cleanup-20261003
Q=$A/.cleanup-quarantine-20261003
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
NQ=$N/.cleanup-quarantine-20261003
```

**阶段 0**

```bash
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask rev-parse HEAD           # 记为 BASE
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'   # 非空只记录，不碰
mkdir /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v9/logs/cleanup-20261003   # 必须是新建
# 以下各条的输出落到 $L 下：df-before.txt、tmux-before.txt、worktree-before.txt、nfs-ls-before.txt
df -B1 --output=target,avail /data /
tmux ls | cut -d: -f1 | sort
git -C $R worktree list
ls -1A $N
# 与并行会话对齐：读其计划文件与 tmux 会话名，确认是否冻结 HEAD，结果记入 $L/peer.txt
# 抄 hs-xhw-probe 的 4 个结果文件（隔离之前）
D=$R/docs/validation/newtask-v6/hard-split/records/xhw-probe; mkdir -- "$D"
for g in gl1506 gl1517; do for f in results.json sha.txt; do
  cp -p -- "$N/hs-xhw-probe-20260927/out-$g/$f" "$D/$g-$f" && cmp -- "$N/hs-xhw-probe-20260927/out-$g/$f" "$D/$g-$f" || echo "REFUSE-COPY $g $f"
done; done
[ "$(ls -1 "$D" | wc -l)" = 4 ] && echo "XHW_COPY=PASS files=4"
# R15 门禁 → CLONE_GATE=PASS repos=6（每条 git 命令单独执行）
# cl_lists.py 生成第一节 11 份清单并打印断言行；派 R-1 审查清单与 cl_* 脚本 → CLEANUP_LIST_REVIEW=PASS
tmux new-session -d -s cl-sha-before  "bash <scratchpad>/cl_sha.sh before"
tmux new-session -d -s cl-core-before "bash <scratchpad>/cl_core.sh before"
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py fp before     # G3/G4/G5 指纹，只含常规文件与软链接
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py nfs before    # G8 指纹（只按名字与大小，不跑 du）
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py site before   # G7a 基线
```

`cl_sha.sh` 全文（trap 保证任何退出都写 `EXIT_CODE=`；每次运行先清空同名日志）：

```bash
#!/usr/bin/env bash
set -o pipefail; export LC_ALL=C
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask; L=$R/artifacts/newtask-v9/logs/cleanup-20261003; tag=$1; LOG=$L/sha-$tag.log
trap 'rc=$?; echo "EXIT_CODE=$rc lines=$(wc -l <"$L/sha-$tag.txt" 2>/dev/null) errbytes=$(stat -c %s "$L/sha-$tag.err" 2>/dev/null)" >>"$LOG"' EXIT
: >"$LOG"; cd "$R" && [ -d "$L" ] || exit 9
{ find artifacts/newtask-v9/delivery -type f -print0 | sort -z | xargs -0 sha256sum >"$L/sha-$tag.txt"; } 2>"$L/sha-$tag.err"
```

`cl_core.sh` 全文（不加 280 s 超时，跑满后解析；`EXIT_CODE=` 只是完成标记，基线已有失败时它会是 1，判定看 `CORE_RUN`）：

```bash
#!/usr/bin/env bash
R=/data/hongzefu/robomme_benchmark_MotionJEPANewTask; L=$R/artifacts/newtask-v9/logs/cleanup-20261003; tag=$1
trap 'echo "EXIT_CODE=${rc:-9}" >> "$L/core.log"' EXIT
cd "$R" || exit 9
head=$(git rev-parse HEAD)
uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -rf -p no:cacheprovider >"$L/core-$tag.txt" 2>&1; rc=$?
p=$(/usr/bin/grep -oE '[0-9]+ passed' "$L/core-$tag.txt" | tail -1 | cut -d' ' -f1)
s=$(/usr/bin/grep -oE '[0-9]+ skipped' "$L/core-$tag.txt" | tail -1 | cut -d' ' -f1)
f=$(/usr/bin/grep -oE '[0-9]+ failed' "$L/core-$tag.txt" | tail -1 | cut -d' ' -f1)
/usr/bin/grep -E '^FAILED ' "$L/core-$tag.txt" | cut -d' ' -f2 | LC_ALL=C sort > "$L/core-$tag.failed"
echo "CORE_RUN tag=$tag head=$head rc=$rc passed=${p:-NA} skipped=${s:-0} failed=${f:-0}" | tee -a "$L/core.log"
```

`CORE_TESTS` 的判法：两次 `passed` 都不是 NA。

- 两次 `head` 相同：三个数与 `.failed` 集合都相等，记 `head_same=1`。
- `head` 不同：取 `git diff --name-only <head1> <head2> -- tests` 之外的测试文件，要求后一次 `.failed` 在这些文件里不比前一次多，记 `head_same=0`。

每个 `sha-*.log` 与 `core.log` 各挂一个 Monitor：

```bash
tail -n +1 -F <日志> | stdbuf -oL tr '\r' '\n' | /usr/bin/grep --line-buffered -E 'EXIT_CODE=|CORE_RUN'
```

**阶段 1：停站**

前置：`! tmux has-session -t '=cl-sha-before'`、`! tmux has-session -t '=cl-core-before'`，且两份日志都已出完成行。对每个站点会话做：

```bash
tmux ls | cut -d: -f1 | sort > $L/tmux-pre-<名>.txt
tmux kill-session -t '=<名>'
tmux ls | cut -d: -f1 | sort > $L/tmux-post-<名>.txt
[ "$(comm -23 $L/tmux-pre-<名>.txt $L/tmux-post-<名>.txt)" = "<名>" ] && echo "STOP_SITE=PASS name=<名>" || echo "STOP_SITE=FAIL name=<名>"
```

四个都停完后检查：

```bash
ss -ltn | /usr/bin/grep -E ':(8060|8070|8080|8081)\b'          # 必须无输出
curl -sf -o /dev/null http://127.0.0.1:8082/api/catalog && echo "SITE_8082=PASS"
```

**阶段 2／3：隔离**

隔离区必须新建：`[ ! -e "$Q" ] && [ ! -L "$Q" ] && mkdir "$Q"`，NFS 的 `$NQ` 同理。本机全部清单用 `root=$A qroot=$Q`，NFS 清单用 `root=$N qroot=$NQ`，两边日志分开。`q1` 全文：

```bash
q1() { local p=$1 kind=$2 root=$3 qroot=$4 rel t par
  case $p in "$root"/?*) ;; *) echo "REFUSE-OUTSIDE $p"; return 3;; esac
  case $p in */|*//*|*/./*|*/../*|*/.|*/..) echo "REFUSE-FORM $p"; return 3;; esac
  case $kind in dir|link|file) ;; *) echo "REFUSE-KINDARG $kind"; return 3;; esac
  rel=${p#"$root"/}; t=$qroot/$rel; par=$(dirname -- "$p")
  if [ ! -e "$p" ] && [ ! -L "$p" ]; then
    [ -e "$t" ] || [ -L "$t" ] && { echo "ALREADY $rel"; return 0; }
    echo "REFUSE-MISSING $p"; return 3
  fi
  [ "$(readlink -f -- "$par")" = "$par" ] || { echo "REFUSE-ANCESTOR $p"; return 3; }
  case $kind in dir) [ -d "$p" ] && [ ! -L "$p" ];; link) [ -L "$p" ];; file) [ -f "$p" ] && [ ! -L "$p" ];; esac \
     || { echo "REFUSE-KIND $p"; return 3; }
  [ ! -e "$t" ] && [ ! -L "$t" ] || { echo "REFUSE-EXISTS $t"; return 3; }
  [ "$(stat -c %d -- "$par")" = "$(stat -c %d -- "$qroot")" ] || { echo "REFUSE-XDEV $p"; return 4; }
  echo "INTENT $rel"
  mkdir -p -- "$(dirname -- "$t")" || { echo "REFUSE-MKDIR $t"; return 5; }
  mv -T --no-copy -- "$p" "$t" && echo "QUARANTINED $rel" || { echo "REFUSE-MV-ERR $p"; return 5; }
}
```

外层骨架要满足三点：日志一律 `tee -a`；遇到 REFUSE 即停；用文件重定向读清单，避免 `while` 跑在子 shell 里。

```bash
[ -s "$LIST" ] && [ "$(tail -c1 "$LIST" | od -An -c | tr -d ' ')" = '\n' ] || { echo "REFUSE-LIST $LIST"; exit 3; }
{ rc=0; while IFS=$'\t' read -r kind p; do q1 "$p" "$kind" "$root" "$qroot" || { rc=$?; break; }; done <"$LIST"
  echo "EXIT_CODE=$rc"; exit "$rc"; } 2>&1 | tee -a "$LOG"; exit "${PIPESTATUS[0]}"
```

每份清单跑完后核对：`INTENT` 与 `ALREADY` 的行数之和等于清单行数。

回滚脚本 `cl_unquarantine.sh <root> <qroot> <LOG>`：

- 对日志中每条 `INTENT <rel>` 逆序处理；
- 若 `$qroot/$rel` 存在且 `$root/$rel` 不存在，先确认父目录存在，再 `mv -T --no-copy` 移回；
- 每移回一条输出 `RESTORED <rel>`。

**阶段 4：隔离状态下的闸门**

```bash
tmux new-session -d -s cl-sha-q  "bash <scratchpad>/cl_sha.sh quarantined"      # 挂 Monitor，等 EXIT_CODE
tmux new-session -d -s cl-core-q "bash <scratchpad>/cl_core.sh quarantined"     # 挂 Monitor，等 CORE_RUN
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py sha before quarantined   # → V9_DELIVERY_SHA（日志未完成报 NOT_READY）
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py index                    # → V9_DELIVERY_INDEX
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py fp check                 # → V9_REUSE_META / V9_EVAL_TREE / KEEP_RECORDS
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py links                    # → V9_LINKS
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py site check               # → V9_SITE_MEDIA
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-project --with playwright python scripts/injection-dev/site/v8_oracle_browser_check.py \
  --port 8082 --shots <scratchpad>/oracle-q \
  --delivery artifacts/newtask-v9/delivery/delivery.local.json --expect-reused 720 --expect-new 80
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py nfs check                # → V9_NFS
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python -m pytest tests/lightweight/test_v9_packaged_800.py -q -s   # → V9_PACKAGED
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py core before quarantined  # → CORE_TESTS
```

**阶段 5：删隔离区**

`cl_rm_local.sh`、`cl_rm_nfs.sh` 各写死一个路径，步骤如下：

1. 守卫隔离区是实体目录、不是软链接。
2. 后台起 `rm -rf -- <隔离区> &`，记下 `RMPID=$!`。
3. 前台每 300 秒直接往 `$LOG` 追加一行进度心跳：`HEARTBEAT <时间> remaining_top=<隔离区下顶层条目数> avail=<df 可用字节>`。心跳不走管道，所以不会拖住 `tee`；数字不再变化即判卡住。
4. `wait $RMPID` 取退出码，追加 `EXIT_CODE=<rc>`；再断言隔离区已不存在，否则追加 `LEFTOVER`。

```bash
tmux new-session -d -s cl-rm-local "bash <scratchpad>/cl_rm_local.sh"
tmux new-session -d -s cl-rm-nfs   "bash <scratchpad>/cl_rm_nfs.sh"
git -C /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA worktree prune
git -C /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA worktree list      # 只剩主检出
```

Monitor 过滤词：`EXIT_CODE=|HEARTBEAT|REFUSE|LEFTOVER|Directory not empty|Device or resource busy|Stale file handle|Operation not permitted|Permission denied|cannot remove|Input/output error|Transport endpoint|Read-only file system|Disk quota`。

**阶段 6：artifacts 之外与 HF**

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py procscan   # 列出 cwd/fd 落在 6 个 worktree 与 /tmp 候选里的进程（遍历器 10 秒后复扫）
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask worktree remove /data/hongzefu/v6-draft/movecube        # pipeline、swap、vp 各单独一条
rmdir /data/hongzefu/v6-draft
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask worktree remove --force /tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/34637e22-b1a7-4754-a153-cae509fb6261/baseline-wt
# V7 worktree：按用户对 PID 2006672 的裁决；若删，不加 --force：
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask worktree remove /data/hongzefu/robomme_benchmark_MotionJEPANewTask/.claude/worktrees/v7
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask worktree prune
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask worktree list          # 输出落到 $L/worktree-after.txt
rm -rf -- /data/hongzefu/robomme_benchmark_MotionJEPANewTask/.cache
rm -rf -- /data/hongzefu/robomme_benchmark_MotionJEPANewTask/runs
bash <scratchpad>/cl_tmp_rm.sh            # 按 R12 现场生成 tmp-drop.txt，逐条复核后删，打印 DONE
hf buckets list HongzeFu/robomme-hard-parity -R --format json      # 输出落到 $L/hf-before.json，并断言含 _probe/bucket-probe.txt
hf buckets rm HongzeFu/robomme-hard-parity/_probe/bucket-probe.txt --dry-run
hf buckets rm HongzeFu/robomme-hard-parity/_probe/bucket-probe.txt -y
hf buckets list HongzeFu/robomme-hard-parity -R --format json      # 输出落到 $L/hf-after.json；只比 type=file 的条目
```

**阶段 7：删后复验**

```bash
tmux new-session -d -s cl-sha-after  "bash <scratchpad>/cl_sha.sh after"
tmux new-session -d -s cl-core-after "bash <scratchpad>/cl_core.sh after"
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py sha before after     # 另跑 index、links、site check、V9_PACKAGED、core quarantined after
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && uv run --no-sync python <scratchpad>/cl_check.py final                # → CLEANUP_LOCAL/NFS/OTHER/HF
df -B1 --output=target,avail /data /                                  # 输出落到 $L/df-after.txt
```

本方案自起的 tmux 会话清单（收尾逐个用 `tmux has-session -t '=<名>'` 确认已自行退出）：`cl-sha-before`、`cl-core-before`、`cl-sha-q`、`cl-core-q`、`cl-rm-local`、`cl-rm-nfs`、`cl-sha-after`、`cl-core-after`。

## 五 风险登记

1. **隔离状态下有闸门 FAIL**：按 R9 回滚，零损失。
2. **NFS 改名跨设备**：`REFUSE-XDEV`，只登记、不直删，交用户。核查时 NFS 各对象与根同为 dev=57，预期不会发生。
3. **NFS 删除慢或挂住**：进度心跳的两个数不再变化即判卡住；`.nfsXXXX` 残留等持有它的进程释放后重删。
4. **8082 进程意外重启**：3164 条映射已逐条核实都在保留树内，不会失败。本方案不主动重启。
5. **并行会话**：
   - 它在推进 HEAD、新建 worktree、目录与 GL 占位；本方案按 R17 不碰。
   - 判据只看本方案的删除集。
   - commit 号执行时现取，冻结期间顺延。
6. **删后 V9 交付集与评估在本机是唯一副本**：HF 从未上传过，交用户另行决定是否上传。
7. **`git worktree remove` 被拒，或有进程 cwd 在目标里**：停，交用户。
8. **重跑类流程失效**（第四节第 7 条）：列进留档，写明恢复办法，不改代码。
9. **未开工计划的官方源码 `856bc3a1` 不在本地了**：`1003-oracle-subgoal-groundsg-eval-plan.md` 写明「已有源缺失就阻塞，不下载」。该计划开工前要改取源方式，留档写明。
10. **G7 的媒体扫描让 8082 访问日志每轮多出约 3200 行**：预期内，R3 已列为允许的追加。
11. **孤儿测试服务**：PID 214366、3506944、3522984 已运行 20～26 小时，占着端口 23200、23110、23010。本方案不处理，报告给用户。
12. **/tmp 大头不能释放**：约 12.6 GB 属于仍在运行的 Claude 会话，本方案不动，报告给用户。

## 六 盲区诚实清单

- NFS 没有量体积，释放量未知。
- `hs-stage`、`v7-stage` 只按目录名、`find` 的媒体计数与身份文件中的 tier 判断，没有逐个打开元数据文件。
- G7(b) 浏览器检查与核心短测，本轮核查中没有实跑，基线在阶段 0 现跑。
- 删后 V9 交付集与评估在本机是唯一副本，HF 上没有备份。
- `robomme_benchmark-newtask-gl` 的 93 条在途改动是否已进主仓库，没有核对；本方案不动它们。
- 按用户选项，以下删后不可恢复（HF 上没有副本）：V7 gen1、V8 的 349 个非 V9 局（其中 330 个在 V9 冻结规格里记作「试过未选」）、NFS `train-parity` 的生成产物。
- 第二节「比对、判定与审计记录」是按文件名、目录结构与内容抽查枚举的，没有逐个文件读内容；漏判会表现为某个小记录被删，属于可接受的残余风险，因为清单要过 R-1 审查。
- 路径引用扫描只覆盖文本文件；h5、mp4、mkv、npz 等二进制内部的路径没有扫。

## 七 留档与 commit 纪律

- **留档** `docs/validation/newtask-v9/cleanup-20261003.md`，内容包括：
  - 用户原话：第一部分口径全部条目与五轮选项答案；
  - 删前、删后的 `df`；
  - 11 份清单的计数与 `CLEANUP_LIST_REVIEW`；
  - 全部判定行原文；
  - tmux 会话清单；
  - 失效与恢复对照：第四节第 7 条的重跑流程与恢复办法、`parity-anchors.json`、`docs/validation` 中 V6～V8 留档的证据路径；
  - `xhw-probe` 抄录说明；
  - 孤儿进程与 /tmp 占用报告。
- **`CLAUDE.md`**：项目专属补充「现有 worktree 不动清单」改为记录已删除的 worktree，分支保留。
- **其他文档**：
  - `docs/1002-pending-decisions.md`：A2 更正「H2 本地副本继续保留」为现状；A3、A4、F1、F3、F4、B4 追加裁决与执行结果；
  - `1003-code-test-maintenance-todo.md`：勾选对应项。
- **commit**：
  - subject 为 `<最新号+1> 历史资源清理：保留 V9 及其来源、xhard0 与全部比对记录，删 V6～V8 其余大件、NFS 旧克隆与旧目录、旧 worktree 与缓存`；
  - body 按第 11 条六项写；
  - 只逐个路径 `git add` 上述文件，`docs/subagent-stats/over-15min.jsonl` 若有新增行一并带入；
  - 随即 push。
