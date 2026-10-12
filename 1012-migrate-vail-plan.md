# 1012 仓库迁到 sled-vail 的方案（只带 git，产物在 vail 重新生成）

> 权威性：本文件是本轮唯一计划。代码锚点：aspen 主检出 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `newtask-v3-MotionJepa1006`，HEAD `3a52b444`（2.72），与 `origin` 一致，`ahead=0`。
> 授权边界：只规划，不实施。用户看过不改、直接说「开工」才执行。本方案不删除 aspen 上的任何东西。
> 用户原话：「给出方案 把这个仓库整体搬迁到vail也是 data hongzefu」「现在这些生成的产物应该都不需要了。你再检查一下是不是都不用了就在那边只需要一个git然后重新生成然后继续做这个新的计划就可以了」「写方案md 不用html了」。

# 第一部分（给人看）

## 一、一句话与已定口径

**一句话**：在 vail 的 `/data/hongzefu/` 下重新 clone 同一个分支，用 `uv sync --frozen` 重建环境，再补上 vail 的运行环境判据表，迁移即告完成。aspen 上的产物一律不搬；1012 碰撞计划不在本次范围，由用户在 vail 上另行确定再开工。

| # | 口径 | 依据 |
|---|---|---|
| M1 | 只带 git，不拷 `artifacts/`、`.venv`、`outputs/` | 用户原话；可行性核查见第二节 |
| M2 | 路径保持 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006` | 用户「也是 data hongzefu」。路径不变，`CLAUDE.md` 里的 worktree 取法、计划里的绝对路径都不用改 |
| M3 | 一切生成只在 vail 本机做，不走任何 gl 机制 | AGENTS P7（2.72） |
| M4 | 生成用卡口径不变，仍是本机 GPU0 | 「改为在本机用gpu0」。vail 上起跑前先核对 GPU0 是否空闲，被占满就停下问用户 |
| M5 | 不删除 aspen 上的副本、产物和他人的在途改动 | 第 11、14 条。删除需用户另行决定 |

## 二、核查：aspen 上的产物是否都可以不要

2026-10-12 在 aspen 只读核查，结论是**全部不需要搬**。

| 东西 | 大小 | 1012 计划用不用 | 结论 |
|---|---|---|---|
| `artifacts/xhard/`（xhard-1011 的 pilot/first/final/vpbfix-1012） | 38 GB | 不用。1012 计划只引用它新建的 `artifacts/xhard/xhard-1012-coll/…` 和 smoke 目录。D7 的视频版式写在 `src/robomme_xhard/tools/episode_strip_video.py` 代码里，不依赖旧 mp4 | 不搬。需要时可在 vail 用同一条命令重生成：母 seed 清单在 git 的 `docs/xhard-doc/xhard-1011/records/mother_seeds.json`，命令在 `launch.md`。今天 VideoPlaceButton 重生成的 timesteps（958/1132/1265）和旧卡逐一相同，说明固定 seed 可复现 |
| `artifacts/plan-site`、`vis-site` | 约 120 MB | 不用。这是计划网页的构建产物，aspen 上的 tmux `xh-plan-web`、`xh-vis-web` 在提供服务 | 不搬。需要时在 vail 用 `scripts/plan-site/` 重建 |
| `artifacts/audit-1011` 及十几个 `*-20261010/11` 分析目录 | 约 40 MB | 不用。结论和关键记录已经进了 git 的 `docs/` | 不搬 |
| `artifacts/logs`、`cache` | 约 1 MB | 不用 | 不搬 |
| `.venv` | 7.5 GB | — | 不搬。vail 上用 `uv sync --frozen` 重建（`uv.lock` 和 ManiSkill git rev `07be6fbc…` 都已锁定） |
| 官方参考集 `/data/hongzefu/data_0226`（仓库外，493 GB） | — | 生成不需要。`mother_seeds.py` 只拿它做可选核验，读不到时记 `unverified`，不会失败 | 不搬。四个 Unmask 系 metadata 已在 2.69 逐字核对过官方版本；vail 上生成母 seed 清单时加 `--no-verify` |
| 2.8.1 的 ep100–399 h5 | 不在本仓库 | 不用。metadata 已撤回 | 不涉及 |

**不属于本轮、需要你知道的两样东西**（迁移时不处理，留在 aspen 原地）：
1. **Codex worktree 里有未提交的改动**：`~/.codex/worktrees/goals-comparison/robomme_benchmark_newtask-v3-MotionJepa1006` 里的 `1006-xhard12-env-plan.html` 有 +562/−263 行没提交。这个 worktree 的分支提交 `eb35ea04` 已经在远端，丢不了；但这部分未提交改动只存在于 aspen，只 clone git 的话 vail 上不会有。
2. **主检出里的 `.nonexistent`**：未跟踪文件，内容是某一版 1006 计划的 HTML，和任何已提交版本都对不上，是你的文件。

## 三、在 vail 上要做的事

| 步 | 内容 | 判据 |
|---|---|---|
| V0 | 按 AGENTS 第 0 条做运行环境判定，记录 hostname、GPU、核数、内存、`~/.ssh/config`、NFS、`uv`、`gh auth status`。aspen 上 ssh vail 报 `Host key verification failed`，所以这些事实要在 vail 本机现场核实 | 原始输出写进第一条回复 |
| V1 | 确认目标路径 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006` 不存在后再 clone，并 checkout 分支 | `git rev-parse HEAD` 等于 `3a52b444` 或更新的远端 HEAD；`git status` 干净 |
| V2 | `uv sync --frozen --extra dev` 重建环境，然后核对 editable 指向 | `ENV_EDITABLE=PASS`：`robomme.__file__` 在 vail 仓库的 `src/` 下 |
| V3 | 核心短测 | `CORE_SHORT=PASS failed=4`：只有已知的 4 个既有失败（test_TaskGoal 两条、test_step_error_handling 两条），没有新增失败 |
| V4 | 跨机复现冒烟：在 vail 上重跑今天的 VideoPlaceButton 三卡（母卡、xhard12、xhard14，seed 10701），固定 `--gpus 0`。约 1 分钟，不需要 tmux | `VAIL_REPRO=PASS`：3/3 成功，timesteps 为 958/1132/1265，和 aspen 一致；xhard 档 goal 为 3 句 |
| V5 | 文档补齐并提交推送：AGENTS 第 0 条加「环境 B：sled-vail」一列（以 V0 实测为准）；P3 补一句「vail 没有官方参考集，生成母 seed 清单用 `--no-verify`」；CLAUDE.md 项目专属补充里的「本机 sled-aspen 无集群访问」改成按环境区分；1012 计划里 aspen 专属的事实（16 核、12 worker、GPU1 被他人占用）加注「vail 以 V0 实测为准，worker 数在 smoke 时按 vail 核数重新标定」 | `SYNC_SUMMARY=PASS`；两个 h1 计数仍为 2 |
| V6 | **不在本次范围**。用户 2026-10-12 原话：「不用继续这个碰撞计划就是你只要做好迁移就好了碰撞计划我在那边再确定再开工」。迁移做完即止，碰撞计划由用户在 vail 上另行确定、另下开工令 | — |

**子代理分工（简述）**：
- V0～V4 由主会话在 vail 上串行做。这些步骤是一路依赖下来的，而且要用 GPU，拆开没有好处。
- V5 只改文档，交给一个写入型子代理在 worktree 里改，审查后用 `--no-ff` 合并、推送。
- V6 不在本次范围（见上表）。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线
- R1：不删除、不移动 aspen 上的任何东西，包括主检出、`artifacts/`、Codex worktree、`.nonexistent`、tmux 会话。
- R2：vail 上 clone 前必须先 `ls -ld <目标>`，目标已存在就停下交用户，不覆盖、不 `--force`。
- R3：不走任何集群路径（P7）。生成只用本机 detached tmux，固定 `--gpus 0`。
- R4：V1～V5 期间不起正式生成。V4 只做 3 卡复现冒烟，产物放 `artifacts/vail-repro-1012/`，验证完保留，不进 git。

## 一、命令（vail 本机）
```bash
# V0：运行环境判定（照 AGENTS 第 0 条的命令；另加以下几条）
hostname; nproc; free -g | sed -n 2p; nvidia-smi --query-gpu=index,name,memory.used,utilization.gpu --format=csv
ls ~/.ssh/config && grep -i '^Host ' ~/.ssh/config; command -v uv gh; gh auth status
# V1
ls -ld /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006   # 必须报不存在
git clone -b newtask-v3-MotionJepa1006 https://github.com/hongzefu/robomme_benchmark_MotionJEPA.git /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006
# V2
cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006 && uv sync --frozen --extra dev
uv run --no-sync python -c "import robomme,robomme_xhard;print(robomme.__file__, robomme_xhard.__file__)"
# V3
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ src/robomme_xhard/tests/ -m 'not gpu and not slow' -q
# V4（manifest 用 git 里的副本）
uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --env VideoPlaceButton --difficulty xhard12,xhard14 \
  --mother-manifest docs/xhard-doc/xhard-1011/records/mother_seeds.json --mother-rank 0 --with-mother --gpus 0 --workers 3 \
  --output-dir artifacts/vail-repro-1012 2>&1 | tee artifacts/vail-repro-1012.log
```
V4 判定：读 `artifacts/vail-repro-1012/run_summary.json`，三卡都要 `ok=True`，timesteps 依次为 958、1132、1265。用 h5py 读 `episode_7/setup/task_goal`：xhard12、xhard14 各 3 句，且都不含 "previously placed"。

## 二、V5 逐文件改动
- `AGENTS.md`：第 0 条判据表加「环境 B：sled-vail」列；如果有冲突，按「冲突即停」处理，原始输出交用户。P3 补 vail 的说明。标记块不动。
- `CLAUDE.md`：只改「项目专属补充」里的环境描述，`common-claude` 标记块不动。
- `1012-swap-collision-plan.html`：aspen 专属的资源事实加注 vail 以实测为准，不改任何已定口径。

## 三、风险与盲区
- vail 上要能访问 GitHub：clone 需要，ManiSkill 也是 git 依赖。另外还要有 `uv`，以及 `gh` 凭据用于推送。这三样都没法在 aspen 上核实（ssh 报 host key 错误）。
- vail 的 GPU0 可能被别人占着。按 M4 停下问你。
- 本机记忆 `~/.claude/projects/-data-hongzefu-robomme-benchmark-newtask-v3-MotionJepa1006/memory/` 只在 aspen 上。可以选择由你手动拷到 vail 同一路径（两边的项目路径相同，slug 也相同）。不拷的话，vail 上的新会话就没有这些偏好记忆。
- xhard-1011 的产物留在 aspen，vail 上没有。以后要对比的话，在 vail 用同一条命令重新生成。

## 四、留档与 commit
- V5 走 `sub/V5:` 子代理提交，主会话用 `--no-ff` 合并，subject 按 `git log` 最近一次接续。合并后核心短测通过，并且 `SYNC_SUMMARY=PASS` 后立即 push。
- 本方案已原样存进仓库根目录 `1012-migrate-vail-plan.md`（用户说「写方案md 不用html了」，2.73 提交），vail 上 clone 后即可读到。
