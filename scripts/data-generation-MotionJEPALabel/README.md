# data-generation-MotionJEPALabel — swap 变体派生数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep90-93**（MotionJEPA eval 集前 4 条），
每个 episode **场景布局逐比特不变，只把「哪几对 bin 交换」穷举一遍**，生成
**318 条变体**（Video 54 + Button 264）的官方格式数据集，并为每条变体写出
timestep 级与 chunk 级的 swap ground truth 标签，供 MotionJEPA 做 swap 子事件
区分性评估。细节与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

## 结论速览（2026-08-18 全量实测）

| 项 | 结果 |
| --- | --- |
| 生成 | **318/318 成功**（穷举无缺口；其中 85 条经「抓取前 hold」补救，见下） |
| 布局不变性 | 全部变体布局指纹与无注入控制跑**逐位相同**（0 失配） |
| 控制跑 ↔ 官方数据 | 8/8 episode 的 joint_action 逐元素差 ≤ 1.1e-17（机器精度） |
| is_original 变体 ↔ 官方 | 7/8 在 1.4e-6 以内；Button/ep91 为 1.55e-3（交换角色规范化的浮点混沌放大，子目标边界逐步相同、无逻辑分叉，见 CLAUDE.md §八） |
| 标签规则回归 | 对 v7 人工资产 **319/319 全对**（smoothstep 进度阈值 ε=0.10） |
| chunk 标签 | 7268 条（swap=1 共 2784 条），主键网格与 merged h5 完全对账 |
| 体量 | merged h5 共 **85 GiB**（Video 12.7 + Button 72.3） |

## 产物（`outputs/full/`，已 gitignore）

```
record_dataset_{Task}.h5              官方格式，episode 密集 0..M-1；每 timestep 内嵌
                                      swap_gt/（是否在 swap、哪对在换、双方绝对位置、
                                      进度、全部候选 bin 与 cube 的逐帧位置），
                                      setup/swap_gt/ 存整条变体的交换序列/颜色/净置换等
record_dataset_{Task}_metadata.json   seed 字段 = variant_seed（与派生 episode 一一对应）
episode_map_{Task}.json               dense ↔ 源ep/变体号/env_seed/variant_seed/交换序列/
                                      is_original/质量指标 的完整映射（适配任何编号方案）
swap_labels_swapvar.json              chunk 级二值标签，与 MotionJEPA swap_labels_v7 同
                                      schema，load_manual_swap 零改动可读
swap_events_swapvar.json              chunk 级富标签（交换对、进度连续值、净置换、
                                      is_original、min_clearance、旁观扰动等）
verification_report.{json,md}         端到端验收报告
videos/ traces/                       rollout 视频与逐帧位姿 npz
```

## 关键口径（详见 CLAUDE.md）

- **注入**：reset 后覆写 `swap_pair{1,2,3}_idx1/idx2` + `_refresh_swap_schedule()`，
  零 RNG 消耗、零 src 改动；swap 次数保持原值。
- **编号**：`variant_seed = env_seed×1000 + variant_idx`（可反解）；环境播种用 env_seed，
  复现须 env_seed + 注入（episode_map 有完整信息）。
- **hold 补救**：ButtonUnmaskSwap/ep91 的抓取子目标（step≈200）与第三 swap 窗口
  （164-214）重叠，85/216 条变体必须在最后一个按钮后 hold 到 swap 结束才能成功；
  仅重试 attempt 启用（`attempt`/`pickup_hold_step` 逐条记录），天然可成功的变体
  （含全部 is_original）轨迹与官方逐位可比。
- **⚠ 数据质量**：穷举引入的对角/远距交换会**穿过被锁定的旁观 bin**（原始数据因
  最近邻配对天然避开）：**193/318 条变体 min_clearance < 0.055 m**（min 0.0007、
  中位 0.0504）。这是环境原行为，不修改；逐条量化在 episode_map 与富标签的
  `min_clearance` / `bystander_net_max` / `disturbed_bins` 字段，下游按需过滤。

## 复现命令

```bash
uv run python -m pytest tests/lightweight/test_swap_variant_plan.py -q   # 枚举单测
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0 --workers 8
uv run python scripts/data-generation-MotionJEPALabel/make_chunk_labels.py --regression
tmux new-session -d -s swapvar-full "set -o pipefail; PYTHONUNBUFFERED=1 uv run python \
  scripts/data-generation-MotionJEPALabel/generate_swap_variants.py \
  --output-dir scripts/data-generation-MotionJEPALabel/outputs/full --gpus 0 --workers 32 \
  2>&1 | tee scripts/data-generation-MotionJEPALabel/outputs/full_run.log"
uv run python scripts/data-generation-MotionJEPALabel/merge_variant_h5.py \
  --input-dir scripts/data-generation-MotionJEPALabel/outputs/full --delete-source
uv run python scripts/data-generation-MotionJEPALabel/make_chunk_labels.py \
  --input-dir scripts/data-generation-MotionJEPALabel/outputs/full --dataset-name dataset-swapvar
uv run python scripts/data-generation-MotionJEPALabel/verify_variants.py \
  --gen-dir scripts/data-generation-MotionJEPALabel/outputs/full
```

MotionJEPA 侧适配提示：merged h5 已满足其 `build_data_raw_from_h5` 的「episode 0-based
密集连续」断言；标签主键 `(task, episode, variant, start_frame)` 与 scope 机制与
`swap_labels_v7.json` 完全同构。
