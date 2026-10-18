# test 布局 xhard 五档全量生成启动档案（1017 计划生成侧）

本文件记录起跑当时的状态，按正本第 13 条两段式写成：起跑前先写「版本与代码状态」「启动与配置还原」，跑完后的实测与结论写进 [result.md](result.md)，不追溯改写本文件的启动口径。权威计划是仓库根目录 [`1017-test-xhard5-12per-plan.html`](../../../1017-test-xhard5-12per-plan.html)（第一部分三节、第二部分一节）。

本轮只做生成侧的全量：在 test 布局下，为 14 个任务生成 xhard 五档，每格 12 条，按档数分五组，共 624 条。MoveCube、InsertPeg 没有 xhard 档，不生成；官方 test 的 easy/medium/hard（ep0–49）不重生成。评估在策略仓库分支 `v2-motionmem-eval-test1017` 上进行，不属于本档。

## 用户决策原话

1. 「分布范围和 train seed 完全一样，只不过 seed 是从 test seed 开始派生」（T1，2026-10-17）
2. 「官方的 Test Easy Medium Hard 就不用生成了，直接生成 X Hard 的系列」（T2）
3. 「X hard 是每档十二条」（T3）
4. 「全部认可 写入计划」（T10：公式 seed 任务性失败 attempt+1 重试、上限 100；非任务性失败连续 3 次放弃、记缺条；属对 P8 的显式例外）
5. 「把这个仓库迁移到 Aspen之后都用 aspen 来执行，还是放在 data 盘里」（T25）
6. 「/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/1017-test-xhard5-12per-plan.html 开工 有问题问用户 尽可能不要阻塞」（2026-10-18 开工令）
7. 「1a」「2同意现在交」「同意你再追加四个 job 去并行。」（2026-10-18：冒烟等 tag；GL 占位 job 立即提交，并增至 12 个）

## 版本与代码状态

- 工作副本：sled-aspen 上的 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006`，分支 `newtask-v3-MotionJepa1006`。
- 本档随 Beta commit 一起提交，起跑时 HEAD 就是这个 Beta commit。启动脚本第一行打印 `SOURCE_HEAD=`，作为实际跑的代码版本。
- 生成代码相对计划锚点 `026c43a1` 没有改动；本轮合入的只有校验工具 `src/robomme_xhard/tools/check_mixed_h5.py` 的 `--layout`／`--tasks`（W3，合并提交 `6d4dc017`）和计划文字修订，都不影响生成行为。
- `git diff --quiet HEAD -- src/robomme/` 零 diff（P1）；`pyproject.toml`、`uv.lock` 未改；ManiSkill 钉在 `07be6fbc66350ddca200abfb0a11b692f078f7fd`。
- 冻结期（计划 F4）：从 Beta commit 起，到全部生成 worker 结束为止，本仓库不做任何 commit。之后按顺序做的追加 metadata commit、tag、留档 commit、handoff commit 都是计划内的 commit。

## 启动与配置还原

运行位置是本机 GPU0、32 个 worker（`nproc=16`；smoke 二在 28 个 worker 下单批 270 s，可用内存 222 G）。detached tmux 会话是 `xh-testx-full`，日志写到 `artifacts/test-xhard/logs/full.log`。显式环境覆盖只有两项：

| 变量 | 值 | 用途 |
|---|---|---|
| `UV_CACHE_DIR` | `/home/hongzefu/.cache/uv` | 本机缓存 |
| `PYTHONUNBUFFERED` | `1` | 日志实时输出 |

五组共用的参数：`--layout test --episode-start 50 --workers 32 --gpus 0 --max-attempts 100 --difficulty-cycle xhard12,xhard14,xhard16,xhard18,xhard20`。各组如下：

| 组 | `--env` | `--episodes` | episode 区间 | 条数 |
|---|---|---|---|---|
| G5 | BinFill,PickXtimes,SwingXtimes,VideoUnmaskSwap,ButtonUnmaskSwap,VideoRepick,PatternLock,RouteStick | 60 | ep50–109 | 480 |
| G4 | StopCube | 48 | ep50–97 | 48 |
| G3 | PickHighlight | 36 | ep50–85 | 36 |
| G2 | VideoPlaceButton | 24 | ep50–73 | 24 |
| G1 | VideoUnmask,ButtonUnmask,VideoPlaceOrder | 12 | ep50–61 | 36 |

seed = 500000 + env_code×10000 + ep×100 + attempt。每个任务的有效循环会剔除该任务缺失的档。生成器对已存在的卡片 H5 一律拒绝覆盖；启动脚本另外断言各组输出目录在起跑前都不存在。

启动脚本是 `artifacts/test-xhard/full/run_full.sh`（不进 git，sha256 `cf90b71f67c41db93d14d77c0e4efd83e212a6257b91f82192284fa4c4f0eaa5`，`bash -n` 退出 0）。它只包上述五条生成命令，外加 `SOURCE_HEAD`、各组 `GROUP_EXIT` 与末行 `FULL_DONE`：

```bash
tmux new-session -d -s xh-testx-full "set -o pipefail; bash /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/test-xhard/full/run_full.sh 2>&1 | tee /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/test-xhard/logs/full.log; echo \"EXIT_CODE=\$?\" >> /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/artifacts/test-xhard/logs/full.log"
```

失败处置：任务性失败按 attempt+1 换 seed，最多 100 次；非任务性失败连续 3 次放弃并记 exhausted；池崩溃的产物以 `CRASHED_` 前缀隔离。任何 exhausted 都会让 metadata 出现空洞，追加工具会整体拒绝。这时停在追加之前，把缺失清单交给用户，不自动补 seed（P8）。生成中断后不重跑已完成的组；未完成的任务换新的输出目录（如 `full/G5-r2`），只跑缺的 `--env`。

## 起跑前冒烟

| 冒烟 | 规模 | 判定 | 日志 |
|---|---|---|---|
| smoke 一 | VideoUnmaskSwap ep50、1 worker | `SMOKE1=PASS`：seed 555000，attempt 0，xhard12，46 s | `artifacts/test-xhard/logs/smoke1.log`，`EXIT_CODE=0` |
| smoke 二 | 14 任务 × ep50–51、28 worker | `SMOKE2=PASS requested=28 success=28 exhausted=0`，270 s | `artifacts/test-xhard/logs/smoke2.log`，`EXIT_CODE=0` |

smoke 二中有 5 次任务性失败，都在 attempt 1–2 换 seed 后成功：VideoRepick ep50、ep51 与 ButtonUnmaskSwap ep50 是 SwapCollisionError；VideoPlaceButton ep51、VideoPlaceOrder ep50 与 ep51 是 SceneGenerationError（VideoPlaceOrder ep51 的 attempt 0 记为 DatasetGenerationError）。

## 盯盘项与会话清单

- Monitor 过滤词：`succeeded with seed|GROUP_EXIT|FULL_DONE|EXIT_CODE=|failed|进程池已损坏|ERROR:|Traceback|BrokenProcessPool|svulkan2|out of memory|NO RECORD|exhausted_count`
- 本轮在本机起过的 tmux 会话：`xh-testx-smoke2`（已结束）、`xh-testx-full`。
- 同时在 GL 上的 12 个占位 job（64233473–64233480、64233525–64233528）属于评估侧，清单在 NFS 的 `v1-store/logs/hold-jobs-testx.txt`，与本档生成无关。
