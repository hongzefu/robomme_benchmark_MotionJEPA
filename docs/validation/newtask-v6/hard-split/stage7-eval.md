# 拆包阶段 7～8：test-hard 两策略评估与收尾（2026-09-28）

计划：`docs/plans/0927-robomme-hard-layered-plan.md` 第一部分 §6.4、§八，第二部分 §3.3。评估身份：`records/eval-identities-1100.jsonl`（xhard1/2/3 各 13 任务 × 20 局 + xhard4 16 任务 × 20 局 = 1100）；每策略两轮 55 格 × 10 局 = 550。顺序（U-9「先各做55*10 然后在做10」）：SimpleMemVLA 第一轮 → MME-VLA 第一轮 → SimpleMemVLA 第二轮 → MME-VLA 第二轮，同一批 10 张卡串接。

## 一、判定行

SimpleMemVLA（`records/stage7/smvla-gates.txt`）：

```text
EVAL_ROUND1=PASS policy=simplememvla episodes=550 normal=550 error_left=0 retries=0/55(max_per_shard=0) shards=10 per_shard=55-55 shape=55x10
EVAL_ROUND2=PASS policy=simplememvla episodes=550 normal=550 error_left=0 retries=0/55(max_per_shard=0) shards=10 per_shard=55-55 shape=55x10
EVAL_IDENTITY_SET=PASS policy=simplememvla rounds=2 shards=10 per_shard=55 episodes=1100 missing=0 extra=0 dup=0
EVAL_BINDING=PASS policy=simplememvla episodes=1100 replay=1100 injected_mismatch=0 recorded_drift=62 max_abs=1.2e-07 unused=0
EVAL_TIER_CAP=PASS policy=simplememvla episodes=1100 mismatch=0
EVAL_DEMO_FRAMES=INFO policy=simplememvla episodes=1100 exact=1054 within_5=1096 max_diff=19
```

MME-VLA（`records/stage7/mmevla-gates.txt`）：

```text
EVAL_ROUND1=PASS policy=mmevla episodes=550 normal=550 error_left=0 retries=47/55(max_per_shard=9) shards=10 per_shard=55-55 shape=55x10
EVAL_ROUND2=PASS policy=mmevla episodes=550 normal=550 error_left=0 retries=0/55(max_per_shard=0) shards=10 per_shard=55-55 shape=55x10
EVAL_IDENTITY_SET=PASS policy=mmevla rounds=2 shards=10 per_shard=55 episodes=1100 missing=0 extra=0 dup=0
EVAL_BINDING=PASS policy=mmevla episodes=1100 replay=1100 injected_mismatch=0 recorded_drift=62 max_abs=1.2e-07 unused=0
EVAL_TIER_CAP=PASS policy=mmevla episodes=1100 mismatch=0
EVAL_DEMO_FRAMES=INFO policy=mmevla episodes=1100 exact=1054 within_5=1096 max_diff=19
```

收尾：`EVAL_HOLD_RELEASE=PASS released=62177614,62177615,62177616,62177617,62177618,62177619,62177620,62177621,62177622,62177623 kept=62126062 others_unchanged=1`（删前 11 个 job、各评估 job 内只有 batch／extern 步骤；删后只剩 `62126062`）。

## 二、分档成功率（每策略 4 档 × 每格 20 局）

| 档 | 局数 | SimpleMemVLA success／fail／timeout | 成功率 | MME-VLA success／fail／timeout | 成功率 |
|---|---|---|---|---|---|
| xhard1 | 13 任务 × 20 = 260 | 91／140／29 | 35.0% | 14／233／13 | 5.4% |
| xhard2 | 13 任务 × 20 = 260 | 47／183／30 | 18.1% | 11／232／17 | 4.2% |
| xhard3 | 13 任务 × 20 = 260 | 30／202／28 | 11.5% | 7／232／21 | 2.7% |
| xhard4 | 16 任务 × 20 = 320 | 52／236／32 | 16.3% | 18／268／34 | 5.6% |

逐格明细 `records/stage7/{smvla,mmevla}-cells.json`。

## 三、与上次 SimpleMemVLA 评估的对比（计划 §六 留档与 commit 纪律）

上次（SimpleMemVLA `aab093f`，benchmark `robomme` 12.191）同 1100 个身份、同按档上限：四档 success／fail／timeout 计数与本次**逐档完全相同**；逐局比对终态 1100/1100 相同、步数 1099/1100 相同，唯一不同为 VideoPlaceOrder／xhard3／seed 13100901（两次均 fail，步数 463 → 494）。差异来源只剩 benchmark 由 `robomme`（12.191）换成 `robomme_hard`（12.210）与演示回放的 RRT 墙钟噪声；本次结果说明拆包未改变评估行为。

## 四、计划外事件与处置

1. **SimpleMemVLA 冒烟 `--resume` 不被官方 `parse_args` 识别**：移入 `testhard_eval.py` 自有参数（`3534e2d`）。
2. **MME-VLA NFS 权重副本缺官方 `history_config.txt`**：逐字节核对 `79999` 与官方 HF 下载相同后，另建 run 根补文件 + symlink（`a2f1378`）。
3. **GL 计算节点 HTTP 代理拒绝本机 websocket**：评估进程去代理变量并连 `127.0.0.1`（`b93fef5`）。
4. **MME-VLA server 显存不足**：VideoPlace 两任务新值档演示约 1419 帧，`add_buffer` 需 6.8～8.5 GB，显存上限 0.4 不够 → 改 0.75（`51c59b3`）。计划风险 17 所写的 0.4 在长演示下不成立。
5. **MME-VLA 记录缺陷（本方案引入）**：异常局沿用上一局 `success_flag`，20 个异常局被误记为上一局终态，另一局触发官方整轮中止（第 9 片后续任务当时未评）。`7fc7128` 修复；对 20 个身份追加更正记录（保留原字段、`status=error`、写明原因），续评重评；续评首个长演示局触发 server 端 keepalive 超时，同进程第二遍编译已缓存全部评完。实际重评 27 局，每轮上限 55 以内。
6. **MME-VLA 视频**：官方每局存视频 1100 条，按计划每格保留 1 条（55 条，`records/stage7/mmevla-videos-kept.txt`），删除 1046 条（清单 `records/stage7/mmevla-videos-deleted.txt`）；保留的 55 条与全部 `episodes.jsonl`、server 日志在 `artifacts/hard-split/eval-out-mmevla/`（不进 git），NFS 上 23 个评估目录已按清单删除（只留权重 run 根 `eval-out/mmevla-ckpt/`）。SimpleMemVLA 本次未录视频。

## 五、预算（U-14，评估侧名义 2202、基础设施重跑硬上限每策略每轮 55、合计 220）

| 项 | 局数（每局一次 reset） |
|---|---|
| 冒烟 | SimpleMemVLA 1 + MME-VLA 1 = 2（另有 3 次冒烟因参数、权重配置、代理问题在首局前或首局即中止：SimpleMemVLA argparse 0 局；MME-VLA server 构造失败 0 局；MME-VLA 代理拒绝 1 局 reset） |
| 两轮正式 | 2 策略 × 55 格 × 10 局 × 2 轮 = 2200 |
| 基础设施重评 | SimpleMemVLA 0；MME-VLA 第一轮 27（每轮上限 55） |
| **合计** | **约 2230 局（上限 2422）** |

## 六、留档位置

- SimpleMemVLA：分支 `testhard-eval-0928-0134`，`docs/eval-doc/testhard-0928/{launch.md,result.md,records/}`（提交 `c359d32`）。
- MME-VLA：分支 `official-testhard-eval-0928-0137`（`hongzefu/robomme_policy_learning_MotionJEPA`），`docs/eval-doc/testhard-0928/{launch.md,result.md,records/}`（提交 `b22fc9c`）。
