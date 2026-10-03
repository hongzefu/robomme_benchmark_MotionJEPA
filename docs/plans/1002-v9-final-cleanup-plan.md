# 1002 V9 定稿收尾计划：README 换 V9 口径、800 局校验、历史产物清理

> 权威性：本计划只规划不实施，分阶段 A（仓库与站点改动，无删除）与阶段 B（其余清理，破坏性），每阶段须单独获批后执行；代码（`src/`、`scripts/`）**一律不改**（用户 2026-10-02 原话「代码不改了」）。锚点 commit `6da7a93d`（12.337），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，工作区 clean。commit 编号接 12.338。外部锚点：官方 `1fadc0ec`。本计划文件落 `docs/plans/1002-v9-final-cleanup-plan.md`（用户 2026-10-02 改口「移到 Docs 文件夹里面」，与 AGENTS.md 覆盖项一致）。

# 第一部分（给人看）

## 一、总览

**一句话方案**：不动任何代码，把 `scripts/README.md` 改成 V9 定稿口径，加一个只读测试把「包内 test-hard 正式局恰好 800、每任务 50、`max_steps` 固定表」钉死，然后把 2.1 TB 本机产物收敛成「V9 生成 800 局 + V9 评估 800 局 × 2 模型」两棵树，其余历史产物按清单删除，NFS 删 651 GB；HuggingFace 上传下轮单独做，本轮只写好命令。

**已定死口径**（用户本轮原话逐字保留）：

1. 「我现在只需要保留最新版本的 task，就是 taskV9」「调用 dataset 等于 test-hard 的时候给我固定数量的 episode，就是我现在所定义的 800 个 episode，每个 task 50 个」→ 800 = 16 任务 × 50 局（xhard1～5 共 43 格），依据 §二。
2. xhard0 去留：用户选「**保留 xhard0，但它不算在 800 里**」→ test-hard 每任务仍是 xhard0 官方 hard 12 局 + V9 50 局 = 62 局，16 任务共 992；README 必须把「800」与「992」两个数都写清。
3. 规格 jsonl：「不裁，只加校验」→ 五份 `env_metadata/test-hard/xhard{1..5}/specs.jsonl` 原样保留（含 718 条未入选候选行），只加测试断言正式局 800。
4. 「max_steps 应该是一个固定的数值……不需要再从 episode 里面读」→ 现状已是常量表 `TIER_MAX_STEPS = {xhard0: 1300, xhard1～5: 1600}`，规格文件 header 与行里都没有 `max_steps`，只需 README 写明并由测试钉住。
5. 「调用和传统的 RoboMME 完全一样，只是 `evaluation_hard.py` 有一个小区别」→ 已核对 `diff scripts/evaluation.py scripts/evaluation_hard.py` 恰好 4 处，本轮不碰入口，README 第 6 节核查清单保留此 diff 判据。
6. 「历史的产物也要清理……只需要保留最新版本 V9 的生成的 H5 文件和评估的文件，需要上传 HuggingFace」→ 评估树选「拼出 V9 专属评估树：800 局报告 + 视频」；上传选「本轮只做本地清理，上传下轮单独做」；NFS 选「删除 train-parity 651 GB」；删除清单用户已认可（§四）。
7. 「代码不改了」→ 取消此前「一并删除旧代码」的选项；`src/robomme_hard`、`scripts/` 零 diff。

## 二、为什么现在 README 是错的，改成什么

`scripts/README.md`（12.237 写、v8 更新）仍写「合计 1262 局（xhard0 192 + 新值档 1070）」「PickXtimes 12 + 17 + 17 + 16 = 62 局……VideoUnmask 92 局」、v7 实测长度表、`EXPECTED_CELLS＝V8_CELLS`。代码真源 `src/robomme_hard/env_record_wrapper/hard_specs.py` 自 12.333 起 `EXPECTED_CELLS = V9_CELLS`，且模块级断言 `len(V9_CELLS)==43 and sum==800`、`每任务恰为 50`。实测（只读 python 统计包内五份 jsonl 的 `selected and rollout.status=="ok"` 行）：

| 任务 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | 合计 |
|---|---|---|---|---|---|---|
| PickXtimes、RouteStick、PatternLock | 17 | 17 | 16 | — | — | 各 50 |
| SwingXtimes、StopCube | 10 | 10 | 10 | 10 | 10 | 各 50 |
| VideoUnmask、ButtonUnmask | 13 | 13 | 12 | 12 | — | 各 50 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 25 | 25 | — | — | — | 各 50 |
| MoveCube、InsertPeg | — | — | — | 50 | — | 各 50 |
| **合计** | 272 | 272 | 92 | 144 | 20 | **800** |

builder（`hard_builder.py::_test_hard_entries`）按「xhard0 12 局在前（官方 test 元数据 `difficulty=="hard"`，seed 与原 episode 号不变）→ xhard1→xhard5、档内按 `candidate` 升序」排 episode 号；逐格校验 `len(chosen) != EXPECTED_CELLS[(task,tier)]` 即抛错，(task,tier) 不在表内即抛错。所以 `get_episode_num()` = 62（每任务）。

`max_steps`：`make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])`，内部 `max_steps + 2` 传给 `DemonstrationWrapper`；不传就用构造 builder 时的 `max_steps`。xhard0 用 1300（与官方 `evaluation.py` 默认相同），xhard1～5 一律 1600（`V8_EXEC_CAP`，抽样时已过滤执行步超 1600 的候选；V9 交付实测最大执行步 1469，`V9_STEP_CAP=PASS max=1469 cap=1600 over=0`，xhard0 最大 1074 ≤ 1300）。

README 重写范围：第 1 节局数句与第 2 点改 V9；第 3 节「局数表」换上表并加「992 = 192 + 800」说明；「episode 长度」v7 实测表删除，改为 V9 的 `V9_STEP_CAP` 与 xhard0 上限两行；第 4 节生成链路改为 V9 口径（720 复用 V8 + 80 新生成，`v9_subset_specs.py` 五子命令）并把 v7 派生链路、v8 分片命令标为「历史，V9 不调用」；第 5 节对拍只留 V9 实跑过的（xhard0 O:H、V9 H:H2）；第 6 节核查清单加本轮新测试。`src/robomme_hard/README.md` 只改口径数字（「62／32／92（合计 1262）」→「每任务 62（合计 992）」，`EXPECTED_CELLS＝V9_CELLS`、800），不动其余段落。仓库根 `readme.md`「Data Generation」陈旧指向，本轮不动（P1 之外、属官方 readme，另立项）。

## 三、校验：怎么证明「test-hard 一定是严格 800」

新增 `tests/lightweight/test_v9_packaged_800.py`（只读、纯 CPU、秒级；不改 src/scripts）：

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 包内五份 jsonl 正式局 | `hard_specs.read_jsonl` + `hard_specs.delivered(row)` 逐档计数 | 正式局恰 800、每任务 50、逐格 == `V9_CELLS`、档内 seed 不重复 | `V9_PACKAGED=PASS total=800 per_task=50 cells=43` |
| builder 实际发出的 episode | 16 任务各建 `BenchmarkEnvBuilder(dataset="test-hard")`，`get_episode_num()`、`resolve_episode(i)` 的档位序列 | 每任务 62 = 12 xhard0 + 50，前 12 局档位为 xhard0、后 50 局按 xhard1→5 单调不降 | 同上 `episodes_per_task=62 total=992` |
| `max_steps` 固定 | 断言 `TIER_MAX_STEPS == {"xhard0":1300, xhard1～5:1600}`，且五份 header 与行里都没有 `max_steps` 键 | 上限只来自常量表，不从 episode 读 | `V9_MAX_STEPS=PASS` |
| 入口差异 | `difflib` 比 `evaluation.py`/`evaluation_hard.py`，非空 hunk 恰 3 个（4 行改动） | 调用方式与官方只差那几处 | `HARD_ENTRY_DIFF=PASS hunks=3` |

与既有 `test_hard_builder_xhard0.py::test_逐任务局数常量合计1262`（已断 V9 992）、`test_xhard0_native.py` 的 `TIER_MAX_STEPS` 断言有重叠，新文件以「用户定义的 800/50/固定 1600」为名集中钉住，不删旧测试。实施前先核对重叠面，重复断言不写两遍。

## 四、产物收敛与清理（给人看的版本）

现状 `artifacts/` 2.1 TB，盘 `/data` 已用 11 TB / 14 TB。V9 交付树 `artifacts/newtask-v9/delivery/episodes/` 已是 800 h5 + 800 mp4（436 GB，全部是硬链接：720 局指向 `newtask-v8/gen1`，80 局指向 `newtask-v9/gen`），删掉源目录不丢数据。评估分两处：`v9-evaluation/…/videos` 只有新 80 局 × 2 模型 = 160 条记录目录（29 GB）；720 复用局的记录在 `v8-evaluation/…/videos`（254 GB，含 V9 不用的 350 局），`report/video-index.jsonl` 2140 条里按 `manifest/reused.json` 的 720 个键挑 `accepted` 恰得 1440 条（两模型各 720，全在本机）。

**先搬、再拼、再核、最后删**，顺序不可倒：

1. **搬 V9 站点还在用的小件**到 `artifacts/newtask-v9/`：V7 的 xhard0 生成视频 `newtask-v7/site-media/xhard0-gen`（341 MB，站点 380 条引用）、V8 的 xhard0 评估 `newtask-v8/xhard0-eval`（576 MB，384 条）、`newtask-v8/site-eval`（4 MB）、`newtask-v8/specs-root`（3 MB，V9 子集的来源规格）。
2. **拼 V9 评估树** `artifacts/v9-evaluation/final/`：`videos/<policy>/<tier>/<task>/<key>.aN` 1440 条硬链接自 V8 + 160 条硬链接自 V9，`report/`（V9 的 report.json/md + 新写 800 局 `video-index.jsonl`）、`manifest/`（V9 manifest + reused.json + V8 manifest.json）、`nfs-records/`（两边都拷，合计约 350 MB）、`inputs/`（两边的 identities）。判定行 `V9_EVAL_TREE=PASS keys=800 policies=2 records=1600 linked_v8=1440 linked_v9=160 missing=0`。
3. **改写站点媒体映射** `newtask-v9/site/media-private.json`（这是产物不是代码）：2140 条 `v8-evaluation`→`v9-evaluation/final`、720 条 `newtask-v8/gen1`→`newtask-v9/delivery`、380 条 `newtask-v7/site-media`→`newtask-v9/site-media`、384 条 `newtask-v8/xhard0-eval`→`newtask-v9/xhard0-eval`；逐条 `os.path.exists`，`MEDIA_REMAP=PASS entries=3164 missing=0`。重启 8082 站并用 `v8_oracle_browser_check.py --port 8082` 复检 `V8_ORACLE_BROWSER=PASS cells=59`。
4. **删除**（每个目录删前 `ls -ld` 确认是实体目录非 symlink，`du` 记前后）：`newtask-v6` 35 G、`newtask-v7` 971 G、`newtask-v8` 618 G（搬走小件后整删）、`v7.5eval` 120 G、`v8-evaluation` 257 G（硬链接后整删）、`branch-alignment` 611 M、`v8-probe`、`eval-reload-20260929`、`train-parity` 21 M。保留：`newtask-v9/` 全部（含 parity 23 G，用户已定）、`v9-evaluation/` 全部、`artifacts/injection/`（进 git）。预计 2.1 TB → 约 0.5 TB。
5. **8080、8081 两个 V8 站点**的数据随 `newtask-v8` 一起消失，删前停掉这两个进程（PID 684283、3255653，均为本仓库 `.venv` 起的 `v8_site.py`）；8082 V9 站保留。
6. **NFS**：删 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/train-parity`（651 GB）；克隆的源码与未提交改动不动，其余 NFS 目录不动。
7. **HF 上传**：不执行；在留档里写好下轮命令（`hf upload <owner>/<repo> artifacts/newtask-v9/delivery …` 与 `SHA256SUMS` 生成），repo 名下轮定。

本轮零 reset、零 rollout（P3 预算 0）。

## 五、子代理分工与合并（简述）

本轮改动面是 2 份 README、1 个新测试、2 份留档，主要工作是破坏性删除与硬链接拼树。**全部主会话自做**：删除与搬迁按规则必须由主会话逐目录核实后执行；README 与测试体量小且互相引用同一组数字，拆给子代理反而要二次对账。只读子代理只用于合并前的审查（一个 sonnet 审查者审 README 数字与测试断言是否与 §二表一致）。

## 六、实施步骤表（分两个阶段，各自独立 commit）

**阶段 A：仓库与站点改动（不删任何东西）**——commit `12.338`。

| 步 | 内容 | 判据 |
|---|---|---|
| A0 | 计划落 `docs/plans/1002-v9-final-cleanup-plan.md`（已落） | 文件存在 |
| A1 | 新测试 `tests/lightweight/test_v9_packaged_800.py`；跑定向测试 | `V9_PACKAGED=PASS total=800 per_task=50 cells=43`、`V9_MAX_STEPS=PASS`、`HARD_ENTRY_DIFF=PASS hunks=3` |
| A2 | 重写 `scripts/README.md`、改 `src/robomme_hard/README.md` 数字 | `git diff --check` 零输出；README 局数表与测试断言同源（审查者核对） |
| A3 | 搬 8082 站引用的小件到 `newtask-v9/`（§四第 1 条） → 拼 V9 评估树 `v9-evaluation/final/`（§四第 2 条） → 改写 `media-private.json`（§四第 3 条） → 重启 8082 | `V9_EVAL_TREE=PASS … missing=0`、`MEDIA_REMAP=PASS … missing=0`、`V8_ORACLE_BROWSER=PASS cells=59` |
| A4 | 留档 `docs/validation/newtask-v9/cleanup-20261002.md` 第一段（搬迁清单、拼树判定行、媒体映射统计、HF 下轮命令）；`docs/1002-pending-decisions.md` B3/B4/F1 追加裁决 | 核心短测失败数不超过基线 6 个；`UPSTREAM_GUARD=PASS`；四入口；录像器零 diff |
| A5 | commit 12.338 并 push | `git status -sb` 无 ahead |

阶段 A 结束时：`artifacts/` 体积不减（硬链接与 mv 不占新空间，仅多约 350 MB 的 nfs-records 拷贝），8080/8081/8082 三个站都还在，历史产物一个不少。

**阶段 B：其余清理（破坏性）**——commit `12.339`，阶段 A 的判定行全 PASS 且已 push 后才开始。

| 步 | 内容 | 判据 |
|---|---|---|
| B1 | 停 8080、8081 两个 V8 站进程（§四第 5 条） | `ss -ltnp` 只剩 8082 |
| B2 | 按清单删本机产物（§四第 4 条；每目录删前 `ls -ld`，大目录进 tmux + Monitor） | 清单逐项「不存在」；`newtask-v9/delivery` 800 h5 + 800 mp4 可读、硬链接数回 1；`v9-evaluation/final` 1600 条记录可读 |
| B3 | 删 NFS `robomme_benchmark-newtask-gl/artifacts/train-parity` 651 GB（§四第 6 条） | 删后 `du` |
| B4 | 留档第二段（删前/删后 `du`、逐目录 `ls -ld` 原文）；`docs/1002-pending-decisions.md` F3/F4 追加裁决 | `du -sh artifacts` 约 0.5 TB |
| B5 | commit 12.339 并 push | `git status -sb` 无 ahead |

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- R1 `src/`、`scripts/` 零改动：实施末 `git diff --name-only HEAD` 只许含 `scripts/README.md`、`src/robomme_hard/README.md`、`tests/lightweight/test_v9_packaged_800.py`、`docs/validation/newtask-v9/cleanup-20261002.md`、`docs/1002-pending-decisions.md`、`docs/plans/1002-v9-final-cleanup-plan.md`。
- R2 删除只按 §四清单；每目录删前 `ls -ld` + `test -L` 判非 symlink；禁止 glob 跨目录删、禁止 `git clean`；`artifacts/injection/` 不动。
- R3 拼树只用硬链接（`os.link`）与小文件拷贝，不复制视频；源与目标同在 `/data` 一个文件系统（已验证 V9 交付树硬链接可行）。
- R4 删除顺序：`V9_EVAL_TREE=PASS` 且 `MEDIA_REMAP=PASS` 之后才删 `v8-evaluation`、`newtask-v8`、`newtask-v7`。
- R5 本轮 reset/rollout 预算 0；8082 站复检只走浏览器检查脚本，不起环境。
- R6 NFS 只删 `robomme_benchmark-newtask-gl/artifacts/train-parity`，删前 `du -sh` 记数、`git -C <克隆> status --short` 存档（不提交、不清理该克隆的在途改动）。
- R7 一次性脚本写在 scratchpad，正文贴进留档；不落 `scripts/` 顶层（P1）。

## 一 逐文件改动清单

1. `scripts/README.md`（重写，保留章节骨架 1～6 节）
   - 引言块：改「按 V9 12.333 换包定稿」；官方锚点不变。
   - 第 1 节：diff 四处不变；第 2 点局数句改「`test-hard` 每任务 = xhard0 12 + V9 50 = 62 局，16 任务 992；用户定义的交付集是 xhard1～5 的 800 局（每任务 50）」；第 4 点写明 `TIER_MAX_STEPS` 是固定常量表、不从 episode 读。
   - 「每一局的场景从哪里来」：五份文件描述改 V9（720 行逐字节复用 V8、80 行新生成；未入选候选行仍在文件里，builder 用 `delivered()` 过滤）。
   - 第 3 节：配置对比表保留（取值未变）并注「V9 每格局数见下表」；局数表换 §二表；长度表删，改两行 `V9_STEP_CAP` / xhard0 1074。
   - 第 4 节：改成「V9 链路 = `v9_subset_specs.py derive/extend/assemble/link/verify` + MoveCube 整任务重抽（`freeze_specs.py --seed-profile v8`）+ `generate_h5.py --mode continue`」；v7 派生、v8 四席分片命令移入「历史（V9 不调用）」小节一段话。
   - 第 5 节：留 xhard0 O:H、V9 H:H2（含 `PARITY_H_H2=FAIL` 交用户裁决的现状）；native/xhard 回归标历史。
   - 第 6 节：加 `uv run --no-sync python -m pytest tests/lightweight/test_v9_packaged_800.py -q`。
2. `src/robomme_hard/README.md`：① 节第 5 行、⑤ 节「62／32／92 局」处改 992/62；不动 ②～④ 正文。
3. `tests/lightweight/test_v9_packaged_800.py`（新增）：复用 `tests/_shared/repo_paths.py` 取仓库根；`from robomme_hard.env_record_wrapper import hard_specs as H, BenchmarkEnvBuilder, TIER_MAX_STEPS`；四个测试函数按 §三表；判定行用 `print` 末行输出（沿用 `test_zz_summary_line` 体例）。标记：不加 `gpu`/`slow`。
4. `docs/validation/newtask-v9/cleanup-20261002.md`（新增）：删前/删后 `du -sh artifacts/*`、每目录 `ls -ld`、三条判定行、搬迁清单、媒体映射改写统计、NFS 删除记录、HF 下轮命令、用户原话。
5. `docs/1002-pending-decisions.md`：B3（README）、B4（硬链接删除责任）、F1（站点去留：只留 8082）、F3（NFS）、F4（大产物）各追加「**裁决**：2026-10-02 <原话>」。

## 二 拼树与删除 runbook（主会话逐步执行）

```bash
# 2.1 搬小件（mv 同盘即 rename）
mkdir -p artifacts/newtask-v9/site-media artifacts/newtask-v9/from-v8
mv artifacts/newtask-v7/site-media/xhard0-gen artifacts/newtask-v9/site-media/xhard0-gen
mv artifacts/newtask-v8/xhard0-eval artifacts/newtask-v9/xhard0-eval
mv artifacts/newtask-v8/site-eval artifacts/newtask-v9/from-v8/site-eval
mv artifacts/newtask-v8/specs-root artifacts/newtask-v9/from-v8/specs-root
# 2.2 拼评估树（scratchpad 脚本 build_v9_eval_tree.py：读 reused.json 720 键 + V8 video-index accepted → os.link 记录目录内每个文件；
#     V9 160 条同法；写 final/report/video-index.jsonl 1600 行；拷 report/manifest/nfs-records/inputs）→ V9_EVAL_TREE=PASS
# 2.3 改写媒体映射（scratchpad remap_media.py：四组前缀替换 + exists 检查，原文件先备份为 media-private.json.bak-20261002）→ MEDIA_REMAP=PASS
# 2.4 重启 8082：kill 18367 → 原命令行重起（tmux 会话 v9site-8082）→ v8_oracle_browser_check.py --port 8082
# 2.5 停 8080/8081：kill 684283 3255653
# 2.6 删本机（逐条，删前 ls -ld）
for d in newtask-v6 newtask-v7 newtask-v8 v7.5eval v8-evaluation branch-alignment v8-probe eval-reload-20260929 train-parity; do ls -ld artifacts/$d; done
rm -rf artifacts/newtask-v6 … （逐条单独一次 Bash）
# 2.7 核验交付树仍完整
find artifacts/newtask-v9/delivery -name '*.h5' | wc -l   # 800
find artifacts/newtask-v9/delivery -name '*.h5' -links +1 | wc -l   # 0（源已删，链接数回 1）
# 2.8 NFS
du -sh /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/train-parity
rm -rf /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl/artifacts/train-parity
```

`rm -rf` 971 GB 级目录可能超过 5 分钟：放 detached tmux（`cleanup-rm-<名>`）并挂 Monitor 盯 `EXIT_CODE=`。

## 三 子代理分配表

| 子任务 | 目标 | 可写集合 | 说明 |
|---|---|---|---|
| 主会话自做 | 全部实施 | 上述 6 个文件 + artifacts/、NFS 删除 | 破坏性操作与数字一致性由主会话亲自把关 |
| R-1（只读审查，sonnet） | 合并前审 README 数字与测试断言 | 无 | 输出 `PRE_MERGE_REVIEW=PASS/FAIL` |

## 四 闸门总表

`V9_PACKAGED`、`V9_MAX_STEPS`、`HARD_ENTRY_DIFF`、`V9_EVAL_TREE`、`MEDIA_REMAP`、`V8_ORACLE_BROWSER`、核心短测（失败 ≤ 基线 6）、`UPSTREAM_GUARD=PASS`、四入口、录像器零 diff、`git diff --name-only` ⊆ R1 集合。

## 五 风险登记

- 媒体映射改写后 8082 站若有引用遗漏，表现为站点视频 404：以 `MEDIA_REMAP missing=0` + 浏览器检查双保险；原映射留 `.bak`。
- `rm -rf` 中途中断：目录残留但不影响 V9 树；重跑同一条即可。
- NFS 删除慢（NFS 上 651 GB 小文件）：进 tmux，不阻塞本机步骤。
- 硬链接树上传 HF 时每条记录目录按独立文件计，体积 = 真实占用（约 436 GB + 约 150 GB 评估），下轮按 bucket 规约核 sha。

## 六 盲区诚实清单

- 未逐条读 `v8-evaluation` 的 `site-media`（2.8 GB）是否被 8082 引用；`media-private.json` 统计里没有该前缀，实施时再 grep 一次 `catalog.json`。
- 未核实 `tests/lightweight/test_hard_builder_xhard0.py` 的 builder 构造在无 GPU 下耗时；若 16 任务各建 builder 超过 60 s，新测试只建 2 个任务做抽样。

## 七 留档与 commit 纪律

阶段 A commit `12.338 V9 定稿收尾（阶段 A）：README 换 V9 口径、800 局校验测试、V9 评估树与站点媒体重定向`；阶段 B commit `12.339 V9 定稿收尾（阶段 B）：历史产物清理（本机 ≈1.6 TB、NFS 651 GB）`，body 按第 11 条六项（用户原话含「我现在只需要保留最新版本的 task…」「代码不改了」「把计划落下根目录」），push。
