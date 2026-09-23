# V4 步 3c：V6 组合覆盖（本机 14 worker）

> 口径 14 / N11 / H3 / J8。组合清单 `scripts/configs/newtask-v4/combos.json`（91 个组合，提交 12.82 冻结），
> 代码为 12.81 之后的 HEAD。每组合 5 条演示，seed 段 `7_000_000 + env_code×100_000 + combo×100 + sample`。
> 入口与正式生成同一个 `generate_dataset_newseed._worker`；产物只留成败（J9：V6 不留回放）。

## 一、判定行

```text
COMBO_COVERAGE=PASS combos=91 missing_combinations=0 zero_success_combinations=0
samples=455 reset_ok=452 demo_ok=402
```

命令：`scripts/parity/v4_combos.py run --samples 5 --shard k/14`（两卡各 7 个 worker，tmux `v4-v6`），
`summarize` 汇总；原始逐样本记录在 `artifacts/newtask-v4/combos/v6-01/samples-*.jsonl`，逐组合表在同目录 `summary.json`。

## 二、按环境汇总（reset 级 / 演示级）

| 环境 | 组合数 | reset | 演示 | 失败类别 |
|---|---|---|---|---|
| PickXtimes | 10 | 50/50 | 46/50 | DatasetGenerationError 4（num=15 仍 4/5 成功：5000 步上限生效） |
| StopCube | 10 | 50/50 | 50/50 | — |
| SwingXtimes | 7 | 35/35 | 34/35 | DatasetGenerationError 1 |
| BinFill | 6 | 30/30 | 19/30 | DatasetGenerationError 11（put_in=5/7 × 投入 2 色、put_in=7 × 3 色 各仅 2/5） |
| VideoUnmaskSwap | 10 | 50/50 | 49/50 | BinCollisionError 1 |
| VideoUnmask | 2 | 10/10 | 10/10 | — |
| ButtonUnmaskSwap | 6 | 30/30 | 24/30 | BinCollisionError 6 |
| ButtonUnmask | 2 | 10/10 | 10/10 | — |
| VideoRepick | 15 | 75/75 | 50/75 | BinCollisionError 23、DatasetGenerationError 2（J2：接受，靠 H4 递补） |
| VideoPlaceButton | 1 | 4/5 | 4/5 | SceneGenerationError 1 |
| VideoPlaceOrder | 1 | 3/5 | 3/5 | **code:TypeError 2**（既有缺陷：布局失败被 `SceneGenerationError` 名字遮蔽成 TypeError，见 step3b-videoplace Q2） |
| PickHighlight | 9 | 45/45 | 43/45 | DatasetGenerationError 2 |
| InsertPeg | 1 | 5/5 | 5/5 | — |
| MoveCube | 1 | 5/5 | 5/5 | — |
| PatternLock | 6 | 30/30 | 30/30 | —（⚠ 见第三节） |
| RouteStick | 4 | 20/20 | 20/20 | — |

## 三、判定被掩盖的一处：PatternLock 长度 25

V6 把 `path_length_range.xhard` 收窄到 `[25,25]` 时 5/5 演示成功，但这**不能**说明 25 节点能生成：
`PatternLock._load_scene` 的路径搜索在 1000 次预算耗尽后按原逻辑**静默采用最后一条路径**（`exhausted_rule`），
长度可以不在声明范围内，演示照样成功。单独 reset 实测（各 10 个 seed，只看 `actions.path_nodes` 长度）：

| 收窄到 | 实际得到该长度 | 说明 |
|---|---|---|
| 20 | 10/10 | 尝试次数 1～68 |
| 24 | 10/10 | 尝试次数 27～771 |
| 25 | **4/10** | 另 6 次预算耗尽，实际长度 21/17/9/9/19/22 |

在正常 xhard 范围 `[20,25]` 下搜索接受首条落在范围内的路径，25 节点的出现概率约 0.4%（20000 次单次尝试里 25 节点只 7 次）。
按口径 14，这属于「传入了但基本生成不出来」，**须用户重定**（例如把上界改为 24，或允许 xhard 加大搜索预算并在预算耗尽时报错而不是静默用错长路径）。

## 四、其他需要用户知情的

- VideoPlaceOrder 的 `code:TypeError` 是四档共有的既有缺陷（H2 约束下没修），它会被主入口归为代码类失败；是否在 xhard 修，待用户决定（step3b-videoplace 报告 Q2）。
- BinFill 投入 2 色、put_in 取端点时演示只 2/5；失败均为演示期规划失败（`DatasetGenerationError`），非生成期问题。
