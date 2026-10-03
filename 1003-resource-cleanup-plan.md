# 历史资源清理方案（2026-10-03）

> 权威性：本方案只规划、不实施；全部删除动作须用户明确说「执行」后才开始，且只按本文件清单删。代码锚点 commit `3ec045f6`（12.347），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`。commit 编号接 12.348。本方案取代 `docs/plans/1002-v9-final-cleanup-plan.md` 中被叫停的阶段 B。按用户 2026-10-03 指示放在仓库根目录。

# 第一部分（给人看）

## 一、总览

**一句话方案**：V9 交付集（16 任务 × 50 局 = 800 局）及其评估结果原样保留、一个字节不动；V6、V7、V7.5、V8 的全部本机产物与 NFS 上的历史目录删除；4 个旧站点停掉，只留 8082。

**已定死口径**

1. 数据集冻结。用户 2026-10-03：「我现在不能够再去改和 Main branch TestHard 一致的数据集了……就必须保持完全一致」。→ `artifacts/newtask-v9/delivery` 与包内规格在清理前后逐文件 sha256 相同（验收 V1）。
2. 只保留最新版本。用户 2026-10-02：「历史的产物也要清理……只需要保留最新版本 V9 的生成的 H5 文件和评估的文件」。
3. NFS 不量体积、直接按清单删。用户 2026-10-03：「我都说了不要去量这个NFS目录的体积了只告诉我哪些要删除直接删了就好了」。
4. 站点、MME 评估对拍、未开工的新评估都不在本方案范围内（用户 2026-10-03：「站点先不管MMEVLA的这个也不管……没开工的你也不用管」）。8082 站只保证清理后照现状能打开，不做任何内容修改。
5. 本方案 reset／轨迹生成预算为 0，不起任何仿真环境。
6. 分支与 worktree 不在本轮清理范围。

**预计效果**：本机 `artifacts/` 从约 2.1 T 降到约 0.7 T（按硬链接估算，未实测，以执行后 `du` 为准）；NFS 释放 651 G 加 4 份代码克隆约 52 G。

## 二、保留什么

| 位置 | 内容 | 为什么留 |
|---|---|---|
| `artifacts/newtask-v9/` 全部 | 交付树 `delivery`（800 个 h5 + 视频）、`gen`、规格、闸门记录、站点目录、`parity`（23 G） | 冻结的数据集本体与证据。`parity` 是新增 80 局（MoveCube 50 + InsertPeg 30）第二次生成的唯一副本 |
| `artifacts/v9-evaluation/` 全部 | 800 局双模型评估报告与录像（`final` 树） | V9 评估结果 |
| NFS `robomme_benchmark-v9two` | V9 评估用克隆，含三套 venv | 之后若再上 GL 评估可直接复用，重建 venv 很慢 |
| NFS `eval-out/`、`SimpleMemVLA/` | 两个模型的权重 | 评估必需 |
| NFS `robomme_benchmark-newtask-gl` 的源码 | 集群侧主克隆 | 仍是 `<GL_REPO>`，只删它里面的 `artifacts/train-parity` |

## 三、删什么

**本机 `artifacts/` 下 9 个目录**

| 目录 | 名义体积 | 说明 |
|---|---|---|
| `newtask-v7` | 971 G | 先把官方 xhard0 的 h5（67 G）与对拍逐局记录搬到 V9 目录，见第五节 |
| `newtask-v8` | 618 G | 其中 720 局与 V9 交付树是硬链接，实际释放约 230 G |
| `v8-evaluation` | 257 G | 多数与 `v9-evaluation/final` 是硬链接，实际释放约 60 G |
| `v7.5eval` | 120 G | 先把权重锁文件搬出 |
| `newtask-v6` | 35 G | — |
| `branch-alignment` | 611 M | — |
| `train-parity` | 21 M | — |
| `v8-probe` | 6 M | — |
| `eval-reload-20260929` | 20 K | — |

**NFS（根 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/`）**

| 目录 | 说明 |
|---|---|
| `robomme_benchmark-newtask-gl/artifacts/train-parity` | 651 G，用户 2026-10-02 已同意删 |
| `robomme_benchmark-v8gen`、`robomme_benchmark-v8eval`、`robomme_benchmark-v8two`、`robomme_benchmark-v9gen` | 4 份历史代码克隆。数据冻结后不再重新生成，`v9gen` 也不需要了 |
| `v7`、`v7-eval`、`v7-eval-stage`、`v7-logs`、`v7-scripts`、`v7-stage` | V7 期的脚本、日志与暂存 |
| `v8eval-xhard0`、`v8gen-out`、`v9gen-out`、`v9two-out`、`v9two-scripts` | V8、V9 的输出与脚本目录，产物早已搬回本机 |
| `SimpleMemVLA-official-xhard0`、`robomme_policy_learning-official-xhard0`、`robomme_policy_learning-testhard-v7` | V7、V8 评估用的策略侧检出 |

**站点进程**：停 `site-v12-8060`、`site-v7-8070`、`site-v8beta-8080`、`site-v8-8081` 四个 tmux 会话。

**明确不动**：NFS 上其余目录（其他项目的、`hs-*`、`newtask-v4-gl` 等没有核对过内容的）；tmux 里不属于本清单的会话（`claude-newtask`、`codex-812`、`corlvis-site`、`site-v9-8082`）；仓库的分支与 worktree。

## 四、为什么删旧目录不会碰到 V9

1. **硬链接**。V9 交付树里 720 个复用局的文件、V9 评估树里的录像，与 V8 目录里的文件是同一份磁盘数据的两个名字。删掉 V8 那个名字，数据仍由 V9 这个名字持有，内容不变，只是暂时不释放空间。已实测：`delivery` 下 800 个 h5 全部链接数大于 1；`v9-evaluation/final` 下 16717 个文件中 16000 个链接数大于 1。
2. **符号链接**。符号链接指向的目标被删就会断。已实测：`newtask-v9` 与 `v9-evaluation` 两棵树里共 80 条符号链接，全部指向 `artifacts/newtask-v9` 内部。
3. **站点媒体映射**。8082 站的 `media-private.json` 已在 12.338 改指 V9 目录，现文件里没有任何旧目录路径。`catalog.json` 里只剩一处 `eval.reuse.site_eval` 记着 `newtask-v8/site-eval`，那是建站时的出处字段（`v8_site_catalog.py::load_site_eval` 只在建目录时读），服务时不读。
4. **⚠ 代价**：删完后 8082 站只能照现状服务，不能再重建目录（重建要读 V8 的站点目录与生成树）。若以后要改站点内容，需先另想办法。

## 五、删之前要搬出来的四样小件

| 搬什么 | 从哪 | 到哪 | 为什么 |
|---|---|---|---|
| 官方 xhard0 的 h5（16 任务 × 12 局 = 192 局，67 G） | `artifacts/newtask-v7/parity/h5/H-xhard0` | `artifacts/newtask-v9/xhard0-h5` | 与官方 test 集一致的原版数据，`step-headroom` 闸门与规划中的 test-hard0 接口会用；同盘 `mv` 瞬间完成 |
| V7、V8 二次生成对拍的逐局记录（约 27 M） | `artifacts/newtask-v7/parity/compare`、`artifacts/newtask-v8/parity/compare` | `artifacts/newtask-v9/from-history/parity-compare-v7`、`…/parity-compare-v8` | `docs/1003-generation-parity-reproducibility.md` 的按任务统计靠它重算 |
| 权重锁与建锁脚本（36 K） | `artifacts/v7.5eval/assets-lock.json`、`artifacts/v7.5eval/preflight/` | `artifacts/v9-evaluation/inputs/assets-lock-v7.5/` | 待定清单 A6（权重核对）的依据 |
| V8 站点目录（JSON，小） | `artifacts/newtask-v8/site-eval` | `artifacts/newtask-v9/from-v8/site-eval` | `catalog.json` 出处字段指向它，留作凭据 |

## 六、验收

| 编号 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| V1 | 交付集没变 | 删前、删后各对 `delivery` 下 800 个 h5 算 sha256，两份清单 `diff` | 数据集逐字节未动 | `V9_DELIVERY_SHA=PASS files=800 changed=0` |
| V2 | 包内规格没变 | `git status --short` 中 `src/` 无改动；`tests/lightweight/test_v9_packaged_800.py` 通过 | 规格仍是冻结版本 | `V9_PACKAGED=PASS` |
| V3 | 评估树完整 | `v9-evaluation/final` 文件数删前删后相同（16717） | 评估录像与报告都在 | `V9_EVAL_TREE=PASS files=16717` |
| V4 | 没有断链 | `find artifacts/newtask-v9 artifacts/v9-evaluation -xtype l` 输出为空 | 没有符号链接指向被删目录 | `V9_LINKS=PASS broken=0` |
| V5 | 8082 站还能用 | `v8_oracle_browser_check.py --port 8082` | 页面与视频可打开 | `V8_ORACLE_BROWSER=PASS cells=59` |
| V6 | 清单删净 | 逐目录 `ls -ld` 报不存在 | 没有漏删、没有多删 | `CLEANUP_LOCAL=PASS removed=9`、`CLEANUP_NFS=PASS removed=19` |

V1 之所以能逐字节成立：清理全程只做 `rm` 与同盘 `mv`，不写 `delivery` 下任何文件；硬链接的另一个名字被删不改变文件内容。

## 七、实施步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 记删前状态：`du`、`df`、`tmux ls`、`git status`；算 sha 基线与文件数基线 | 基线文件落盘 |
| 1 | 搬出第五节四样小件 | 目标路径存在，源路径不存在 |
| 2 | 停 4 个旧站点 | `tmux ls` 差集恰为这 4 个 |
| 3 | 删本机 9 个目录（大的进 tmux） | V6 本机判定行 |
| 4 | 删 NFS 19 个目录（进 tmux，不量体积） | V6 NFS 判定行 |
| 5 | 验收 V1～V5 | 五条判定行 |
| 6 | 写留档 `docs/validation/newtask-v9/cleanup-20261003.md`，待定清单 F1、F3、F4 写结案，提交推送 | `git status -sb` 无 ahead |

## 八、子代理分工与合并（简述）

本方案没有代码改动，全部是破坏性的文件操作，不拆给子代理，由主会话一条一条亲自执行、亲自核对。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- R1 只删第三节清单内的目录；每条 `rm -rf` 写完整绝对路径，一条命令只删一个目录；禁止 glob、禁止变量拼接后不回显、禁止 `git clean`。
- R2 每个目录删前先 `ls -ld <路径>` 并 `test ! -L <路径>`，确认是实体目录不是符号链接；是符号链接即停。
- R3 `artifacts/newtask-v9`、`artifacts/v9-evaluation` 下除第五节的搬入外零写入。
- R4 tmux 只用 `tmux kill-session -t '=<完整会话名>'`，删前删后各 `tmux ls`；不在清单的会话不动。
- R5 NFS 克隆 `robomme_benchmark-newtask-gl` 只删 `artifacts/train-parity`，其源码与在途改动不动；删前 `git -C <克隆> status --short` 存档。
- R6 不提交 GL 作业、不 ssh 集群；NFS 删除从本机挂载点执行。
- R7 sha 基线没算完不得开始任何删除。
- R8 任何一步的实际输出与预期不符即停，原始输出交用户。

## 一 逐项清单

**本机（前缀 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/`）**，删除顺序由小到大：
`eval-reload-20260929`、`v8-probe`、`train-parity`、`branch-alignment`、`newtask-v6`、`v7.5eval`、`v8-evaluation`、`newtask-v8`、`newtask-v7`。

**NFS（前缀 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/`）**，共 19 个：
`robomme_benchmark-newtask-gl/artifacts/train-parity`、`robomme_benchmark-v8gen`、`robomme_benchmark-v8eval`、`robomme_benchmark-v8two`、`robomme_benchmark-v9gen`、`v7`、`v7-eval`、`v7-eval-stage`、`v7-logs`、`v7-scripts`、`v7-stage`、`v8eval-xhard0`、`v8gen-out`、`v9gen-out`、`v9two-out`、`v9two-scripts`、`SimpleMemVLA-official-xhard0`、`robomme_policy_learning-official-xhard0`、`robomme_policy_learning-testhard-v7`。

**tmux 会话**：`site-v12-8060`、`site-v7-8070`、`site-v8beta-8080`、`site-v8-8081`。

## 二 子代理分配表

| 子任务 | 目标 | 可写集合 | 说明 |
|---|---|---|---|
| 主会话自做 | 全部步骤 | 第三节清单、第五节搬入目标、留档与待定清单两份文档 | 破坏性操作不外包；无代码改动，无可并行拆分的写入任务 |

## 三 闸门总表

`V9_DELIVERY_SHA`、`V9_PACKAGED`、`V9_EVAL_TREE`、`V9_LINKS`、`V8_ORACLE_BROWSER`、`CLEANUP_LOCAL`、`CLEANUP_NFS`（定义见第一部分第六节）。任一 FAIL 即停，不自行改判据。

## 四 runbook

日志与基线统一落 `artifacts/newtask-v9/logs/cleanup-20261003/`（记为 `$L`）。每条 git、每条 `rm` 单独一次执行。

```bash
# 阶段 0：基线
mkdir -p $L
du -sh artifacts/* > $L/du-before.txt; df -h /data > $L/df-before.txt; tmux ls > $L/tmux-before.txt
find artifacts/newtask-v9 artifacts/v9-evaluation -type l -printf '%p -> %l\n' > $L/symlinks-before.txt
find artifacts/v9-evaluation/final -type f | wc -l > $L/final-count-before.txt        # 预期 16717
# sha 基线（436 G，超过 5 分钟，进 tmux，会话名 cleanup-sha-before）
tmux new-session -d -s cleanup-sha-before "set -o pipefail; cd <仓库根>; find artifacts/newtask-v9/delivery -name '*.h5' -print0 | sort -z | xargs -0 sha256sum 2>&1 | tee $L/sha-before.txt; echo \"EXIT_CODE=\$?\" >> $L/sha-before.log"

# 阶段 1：搬小件（同盘 mv）
mv artifacts/newtask-v7/parity/h5/H-xhard0            artifacts/newtask-v9/xhard0-h5
mkdir -p artifacts/newtask-v9/from-history
mv artifacts/newtask-v7/parity/compare                artifacts/newtask-v9/from-history/parity-compare-v7
mv artifacts/newtask-v8/parity/compare                artifacts/newtask-v9/from-history/parity-compare-v8
mkdir -p artifacts/v9-evaluation/inputs/assets-lock-v7.5
cp -a artifacts/v7.5eval/assets-lock.json artifacts/v7.5eval/preflight artifacts/v9-evaluation/inputs/assets-lock-v7.5/
mv artifacts/newtask-v8/site-eval                     artifacts/newtask-v9/from-v8/site-eval   # 须在停 8081 之后

# 阶段 2：停站（每个会话三步）
tmux ls; tmux kill-session -t '=site-v12-8060'; tmux ls      # 其余三个同样逐个做

# 阶段 3：删本机（小目录直接删；v7.5eval 起进 tmux，会话名 cleanup-rm-<目录名>）
ls -ld <绝对路径>; test ! -L <绝对路径> && rm -rf <绝对路径>
tmux new-session -d -s cleanup-rm-newtask-v7 "rm -rf <绝对路径> 2>&1 | tee $L/rm-newtask-v7.log; echo \"EXIT_CODE=\${PIPESTATUS[0]}\" >> $L/rm-newtask-v7.log"

# 阶段 4：删 NFS（一个 tmux 会话 cleanup-rm-nfs，脚本先落 scratchpad，逐目录 ls -ld、test ! -L、rm -rf，每删完一个打一行 DONE <路径>）
git -C /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl status --short > $L/newtask-gl-status.txt

# 阶段 5：验收
find artifacts/newtask-v9/delivery -name '*.h5' -print0 | sort -z | xargs -0 sha256sum > $L/sha-after.txt   # 进 tmux
diff $L/sha-before.txt $L/sha-after.txt
find artifacts/newtask-v9 artifacts/v9-evaluation -xtype l
find artifacts/v9-evaluation/final -type f | wc -l
uv run --no-sync python -m pytest tests/lightweight/test_v9_packaged_800.py -q
uv run --no-sync python scripts/injection-dev/site/v8_oracle_browser_check.py --port 8082
du -sh artifacts/* > $L/du-after.txt; df -h /data > $L/df-after.txt
```

tmux 会话清单（本方案自起，收尾按清单逐个确认已自行退出）：`cleanup-sha-before`、`cleanup-rm-v7.5eval`、`cleanup-rm-v8-evaluation`、`cleanup-rm-newtask-v8`、`cleanup-rm-newtask-v7`、`cleanup-rm-nfs`、`cleanup-sha-after`。每个会话的日志各挂一个 Monitor，过滤 `EXIT_CODE=|DONE|No such file|Permission denied|cannot remove`。

## 五 风险登记

1. **8082 站点引用遗漏**：表现为视频 404。删前已核对 `media-private.json` 无旧路径；删后以浏览器检查为准。若 FAIL，旧数据已不可恢复，只能记录缺口交用户。为降低此风险，阶段 3 的顺序把与站点相关的 `v8-evaluation`、`newtask-v8`、`newtask-v7` 放在最后，且在删它们之前先跑一次浏览器检查确认当前基线是 PASS。
2. **`rm -rf` 中途中断**：目录残留，不影响 V9；重跑同一条。
3. **NFS 删除慢**：651 G 可能要几十分钟到数小时，放 tmux，不阻塞本机步骤。
4. **搬 xhard0 h5 后旧路径失效**：`hard_regression.py step-headroom --xhard0 artifacts/newtask-v7/parity/h5/H-xhard0` 这类历史命令要改用新路径 `artifacts/newtask-v9/xhard0-h5`；文档里的旧路径不逐个改，在留档里写一条对照。
5. **留档里的证据路径失效**：`docs/validation/` 下 V6～V8 留档引用的 `artifacts/` 路径删后都打不开，属预期，留档正文不改。
6. **NFS 上 A1 的 H2 原件**：早已删除，本机 `artifacts/newtask-v9/parity/h2-nfs` 是唯一副本，本方案保留。

## 六 盲区诚实清单

- 实际能释放多少空间没有实测，「约 1.4 T」是按硬链接比例估算。
- NFS 上 14 个小目录没有逐个打开核对内容，依据是待定清单 F3 的记载与目录名；`robomme_benchmark-v8two`、`robomme_policy_learning-testhard-v7` 的体积与工作区状态这次没有复查（上次复查为 10-02，五份克隆工作区干净）。
- 删除后 8082 站点无法重建目录，这一点只从代码读出，没有做过「删后重建」的实验。
- `artifacts/newtask-v8/site-eval` 的体积没有量；若它不是纯 JSON 小目录，阶段 1 改为只留 `catalog.json` 等索引文件。
- V7、V8 的评估录像、生成 h5 删除后不可恢复：本机是唯一副本，没有上传过 HuggingFace（拆包期的三侧 h5 在公开 bucket `HongzeFu/robomme-hard-parity`，与本次删除对象不同）。

## 七 留档与 commit 纪律

- 留档 `docs/validation/newtask-v9/cleanup-20261003.md`：用户原话、删前删后 `du`／`df` 原文、逐目录 `ls -ld` 原文、七条判定行、tmux 会话清单、旧路径到新路径对照。
- `docs/1002-pending-decisions.md` 的 F1、F3、F4、B4 各追加裁决与执行结果。
- commit `12.349 历史资源清理：本机 9 个目录、NFS 19 个目录、停 4 个旧站点`，body 按第 11 条六项，随即 push。只 `git add` 上述两份文档。
