# xhard-1011 最终批次：launch（第一段，起跑前写）

档案名 `xhard-1011`，按 AGENTS.md 第 13 条留档。本文件写于最终批次起跑之前；跑完后的实测与结论写在同目录 `result.md`。

## ① 一句话

在官方 16 任务 hard 母样本（VideoRepick 为 medium）上，用 `robomme_xhard` 子类按计划 `1006-xhard12-env-plan.html` 四.7 表的 52 个有效“任务 × 难度”配置，每任务取 rank0 母 seed，各生成 1 条 xhard 轨迹（共 52 条），另用当前代码按同 seed 重生成 16 条母档作对照（R9、R26）。

## ② 版本与代码状态

- 代码版本：本文件所在的 Beta 提交（subject `2.50Beta …`）。起跑前 `git status --short` 只剩不属于本轮的未跟踪文件 `.nonexistent`（约 215 KB，来源不明，未动、未提交）。
- 本轮代码链路（均已合入并推送）：
  - 2.43 S0 新包骨架与 52 档配置表（`src/robomme_xhard/configs.py`、`base.py::XHardMixin`）。
  - 2.44 S0-P1 `src/robomme/robomme_env/utils/task_goal.py` 四个派生分支（R13 已批）。
  - 2.45～2.48 合并 S1（9 个子类）、S2（5 个子类）、S3（生成器 xhard 开关）、S4（母 seed 清单、汇总、对比视频工具）。
  - 2.49 合并 F1（测试与注释小修）。
- 保护目录：`git diff da32a8b1..HEAD -- src/robomme/` 只含 `task_goal.py` 四分支；`pyproject.toml`、`uv.lock` 零 diff。
- ManiSkill 钉 `07be6fbc66350ddca200abfb0a11b692f078f7fd`（不变）；`.venv` python 3.11。

## ③ 启动与配置还原

运行位置：sled-aspen 本机主检出 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，GPU 1（起跑前现场核实空闲），tmux 会话 `xh-final-1012`。

```bash
tmux new-session -d -s xh-final-1012 "set -o pipefail; cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006; PYTHONUNBUFFERED=1 uv run --no-sync python scripts/data-generation-newSeed/generate_dataset_newseed.py --difficulty xhard12,xhard14,xhard16,xhard18,xhard20 --mother-manifest artifacts/xhard/xhard-1011/mother_seeds.json --mother-rank 0 --with-mother --gpus 1 --workers 12 --output-dir artifacts/xhard/xhard-1011/final 2>&1 | tee artifacts/xhard/xhard-1011/logs/final.log; echo \"EXIT_CODE=\$?\" >> artifacts/xhard/xhard-1011/logs/final.log"
```

可复现面（全部参数）：

| 项 | 值 | 说明 |
|---|---|---|
| `--difficulty` | `xhard12,xhard14,xhard16,xhard18,xhard20` | 缺档不出卡，共 52 张 xhard 卡 |
| `--mother-manifest` | `artifacts/xhard/xhard-1011/mother_seeds.json`（副本 `records/mother_seeds.json`） | S4 工具产出，32 条，`XHARD_MOTHER_NO_FAILRECOVER=PASS seeds=32 min_episode=7` |
| `--mother-rank` | `0` | 每任务锁定较小 episode 的母 seed |
| `--with-mother` | 开 | 16 张母卡，原任务名、source_difficulty |
| `--gpus` / `--workers` | `1` / `12` | 本机 16 核；小规模实测 4 worker 峰值 RSS 9.2 GB。计划写的 32 为另一台机器的实测上限，本机按核数取 12 |
| `--output-dir` | `artifacts/xhard/xhard-1011/final` | 起跑前不存在；一轮一个新目录 |
| attempt | 固定 0 | 失败不换 seed、不重试正常失败（RL3） |

rank0 母 seed：BinFill 7/4701、PickXtimes 7/1700、SwingXtimes 7/3700、StopCube 59/7900、VideoUnmask 7/6700、ButtonUnmask 7/8700、VideoUnmaskSwap 7/5700、ButtonUnmaskSwap 7/7700、PickHighlight 7/12700、VideoRepick 46/13600（medium）、VideoPlaceButton 7/10701、VideoPlaceOrder 7/11705、MoveCube 7/14700、InsertPeg 7/13700、PatternLock 7/15700、RouteStick 7/16700。

盯盘：一份日志一个 Monitor，过滤 `succeeded with seed|EXIT_CODE=|failed|进程池已损坏|ERROR:|Traceback|BrokenProcessPool|svulkan2|out of memory|NO RECORD`。注意任一卡失败时生成器退出码为 1（既定语义），成败以 `run_summary.json` 的 `cards[]` 为准。

本轮 tmux 会话清单：`xh-pilot-1011`（小规模实测，已随命令结束自行退出）、`xh-final-1012`（最终批次）。

## ④ 用户决策记录（原话逐字）

- 2026-10-11 开工令：「@[H5文件生成评估] 开始正式实现 有问题问用户」
- 2026-10-11：「为什么不是用子代理做」
- 2026-10-12 审阅小规模实测后：「PickXtimes 全部+1可行吗」「2不动」「3不动」「4先不动」，随后「那就先不动pickxtimes」「生成最终批次」「小规模的删除」。
  - 对应：PickXtimes 保留原档名与旋钮、标实测倍数；VideoUnmask、ButtonUnmask 不满足 8 帧必漏（xhard14 两 seed 零遗漏）照实记录、不改；BinFill 母 seed 5501 xhard14～20 失败照实记录、不追查；交换类第 4 次起 idx1 按 1,2,3 循环复用的配对规则先不动（R6）。

## ⑤ 前置阶段实测（产物已按 R28 删除，记录在 records/）

### GPU 首条（runbook 步骤 5，records/first/）

ButtonUnmaskSwap xhard20、seed 7700、单 worker、GPU1：task_success=1，908 timestep（估算 916），23 s。
`DIFFICULTY_LABEL=PASS files=1`；`XHARD_RECORD_NONEMPTY=PASS files=1`；`XHARD_CHOICE_GROUNDING=PASS files=1 button_steps=6 empty=0`；goal 与计划拟稿逐字一致。`INTERMEDIATE_CLEANUP=PASS stage=first h5=0 mp4=0`。

### 主检出 gpu 用例

合并 S4 后 43 例中 42 passed；唯一失败为 VideoPlaceOrder xhard12 占位 seed 7101 父类撒点失败（父类把模块名当异常类调用致 TypeError，母任务原样缺陷，按 R1 不动），改用真实 seed 11705、12501 均扩到 4 个不同目标。F1 已把 gpu 用例 seed 改为 rank0 母 seed。

### 小规模实测（runbook 步骤 7，records/pilot/）

运行代理 R1，tmux `xh-pilot-1011`，HEAD 143f29e2，GPU1，`--workers 4`，2026-10-11 18:35:35 EDT 起跑，1042 s，7.6 ep/min，峰值 RSS 9.2 GB。136 卡（104 xhard + 32 母档）132 成功；4 失败均为 BinFill 母 seed 5501 的 xhard14/16/18/20（failure_class=task，环境报告失败，失败发生在投第 4 块红色方块阶段，未逐帧确认原因）。`EXIT_CODE=1` 为有卡失败的既定语义。

判定行：

- `DIFFICULTY_LABEL=PASS files=132`
- `XHARD_RECORD_NONEMPTY=PASS files=132`
- `GRADIENT_REVIEW=INFO groups=32 rows=136 failed=4 missing_mother=0 non_monotonic=1 (PatternLock/15700)`
- `XHARD_CHOICE_GROUNDING`：按钮步骤 4362 个全部 first→A、second→B，空值 0；按计划原口径（整条轨迹空值比例不高于母档）VideoRepick、VideoUnmaskSwap 显示偏高，但拆开后执行段空值在所有任务上均为 0，空值全部来自演示段（母档同样无 choice），见 `records/pilot/choice_exec.txt`。按执行段口径判 PASS。
- `XHARD_8FRAME_LONGEST=FAIL tasks=14 episodes=27 zero_miss=4`：零遗漏的 4 条全是 VideoUnmask、ButtonUnmask 的 xhard14（两 seed），其余 12 任务最长档均有遗漏；用户裁决不动。

实测倍数（两 seed，timestep 相对同 seed 母档）见 `records/pilot/pilot_summary.md`；PickXtimes 每档偏低约半档（xhard20 为 1.91/1.82），用户裁决不动。

删除：用户「小规模的删除」后，按 R28 删除 `artifacts/xhard/xhard-1011/pilot/` 下全部 H5 与 MP4（逐文件清单删除）及 `report/pilot_compare.mp4`，日志、json、md 保留。判定行见 result.md。
