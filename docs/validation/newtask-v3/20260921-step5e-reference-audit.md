# 步 5e 预演：发布集审计 R1b（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 5e、闸门 R1b。
**本文是用 4 worker 那批数据做的预演**，用来验证链路并拿到数量级；正式结论以单 worker 的 5d 产物重跑为准。

## 一、前置：发布集在本机且已核验

用户指示「查找本机 /data/hongzefu 有吗 没有的话下载」——本机已有，无需下载。
`/data/hongzefu/robomme_data_h5`，16 个文件，大小与 SHA-256 **逐一**与步 1a 冻结的历史报告清单一致
（总 512,595,968,744 字节，revision `a5e4e25ffe8af34f64944f9533d06455ce5f8337`），落档见
[reference_set_verification.json](../../../scripts/configs/newtask-v3/history/reference_set_verification.json)。

本机可直接访问集群 NFS，因此审计在本机跑、读 NFS 上的产物比本地发布集，不需要搬 39 GB 数据。

## 二、链路

1. `train_split_parity.py merge`：把 A1 路 144 条逐 episode 产物合并成官方比较器吃的
   `record_dataset_<task>.h5`（直接调用官方 `_merge`／`_write_metadata`），元数据按 144 条子集投影。
   产物 16 个文件、约 35 GB。
2. `train_split_comparison.py audit`：用 9.6 的稀疏范围适配器跑官方合同校验与 `joint_action` 逐元素比较。

## 三、结果：两件事分开报

**审计完整性 —— 通过**

```text
REFERENCE_AUDIT_COMPLETE=PASS compared=144 contract_errors=0 missing=0
```

144 条身份全部在发布集里找到、合同校验零错误。官方原函数本来会因为 episode 不连续直接拒绝这个范围，
这一条同时也是范围适配器（G5）在真实数据上的验证。

**动作数值 —— 不通过，原始数字原样记录**

```text
passed=False
vectors=50228  elements=401824  different_elements=291961
max_abs_diff=0.019696838469699163
errors=39（全部是 timestep sets do not match）
最大差位置：InsertPeg/episode_1/timestep_486/element_5
            reference=2.218913556815163  generated=2.199216718345464
```

## 四、怎么解读这个 failed

对照历史那轮（官方 dataset-gen 自己跑的全集 1600 条对同一发布集）：

| | 历史（全集 1600 条） | 本次预演（子集 144 条） |
|---|---|---|
| 状态 | `status=failed` | `passed=False` |
| 非零差异元素 | 217242 | 291961 |
| 最大绝对差 | 0.007857919612339614 | 0.019696838469699163 |
| 帧数不符 | 10 条 | 39 条 |

**历史自己与发布集比也是失败的**，本次量级相当、方向一致。差异来源与 R1a 的帧数差同源：
我们的 A 路跑在 A40（sm_86），发布集来自 sm_89 的机器，数值差异经求解器（三次 screw 后回退 RRTStar）放大。

**这不影响本轮的核心结论**：注入前后的严格对拍（`B↔C`、`C↔D`、`A1↔D`）是**逐字节相同**的；
与发布集的差异属于「A40 基线 vs 官方 sm_89 发布集」这条外部对照线。方案对 R1b 的要求正是
「审计完整 ≠ 数值相等，原 `1e-8` 失败照记、不改写成 PASS」，本文照此执行。

## 五、待办

- 正式 R1b：用单 worker 的 5d 产物重跑合并与审计，替换本文数字。
- 逐条差异明细已落 `artifacts/train-parity/r1b-w4-audit.json`（含每个 task 的审计段与动作比较段）。
