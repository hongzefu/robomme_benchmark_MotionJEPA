# newtaskRelease-v3 原值对拍：怎么跑

本目录是 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 的执行记录。
本文只讲**怎么复现**，结论看各步报告。

> **路径迁移（2026-09-22）**：六个 `train_split_*.py` 与 `comparator_fixtures.py` 已从 `scripts/` 顶层
> 移进 [`scripts/parity/`](../../../scripts/parity/README.md)（该目录由 `scripts/test-vs-original/` 改名而来），
> `hf_release.py` 移进 `scripts/injection/`。**本文的命令已更新为新路径**；
> 下面各步报告（`20260921-*.md`、`20260922-*.md`）是当时的留档，其中的旧路径与链接按原样保留、不回改，
> 读的时候按 `scripts/<文件>.py` → `scripts/parity/<文件>.py`、`scripts/test-vs-original/` → `scripts/parity/` 换算。

## 零、两条硬性前提

1. **正式验收必须单 worker**（`--workers 1`）。`mplib` 的 RRT 用墙钟时间预算，多 worker 争抢会
   让同一条身份搜出不同路径 → 产物不可逐位复现。实测见
   [worker 非确定性专题](20260921-worker-nondeterminism.md)。
2. **判据只认 A40**。本机（RTX 6000 Ada，sm_89）与 greatlakes A40（sm_86）同一身份产物不同；
   本机只用于调试。

## 一、冻结身份与历史证据（步 0／1a，只读，秒级）

```bash
uv run --no-sync python scripts/parity/train_split_parity.py freeze-identities --output artifacts/train-parity/v3-native
uv run --no-sync python scripts/parity/train_split_parity.py freeze-history    --output artifacts/train-parity/v3-native
```

产出 `scripts/configs/newtask-v3/` 下的 1600 条全量与 144 条子集 manifest、官方十六份 metadata 原文
与来源散列、历史报告原文与 R1a 投影。加 `--verify` 可只校验既有文件字节不重写。

## 二、离线核对器（G2／G3／G5／C1／5b，纯 CPU）

```bash
uv run --no-sync python scripts/parity/train_split_audit.py config-map        # G2 SAMPLING_ORIGINAL
uv run --no-sync python scripts/parity/train_split_audit.py field-ownership   # G3 FIELD_OWNERSHIP
uv run --no-sync python scripts/parity/train_split_comparison.py check --official-root <官方源码目录>  # G5
uv run --no-sync python scripts/parity/train_split_audit.py coverage        --run <运行目录>... --paths A1,A2,B,C,D  # C1
uv run --no-sync python scripts/parity/train_split_audit.py branch-coverage --run <运行目录>...          # 5b 分支覆盖
```

## 三、生成与对拍（步 1b～5d）

一次运行可跑任意路径子集；`--sampling-config` 给 C／D，`--episode-specs` 不给时 D 自动消费
同一运行里 C 刚导出的规格（方案 8.2：规格来源固定为 C 路只读导出）。

```bash
# 单条冒烟
uv run --no-sync python scripts/parity/train_split_parity.py run \
  --env BinFill --episode 0 --paths A1,A2,B,C,D --workers 1 --gpus 0 \
  --sampling-config scripts/configs/newtask-v3/native_sampling.json \
  --output artifacts/train-parity/<运行名>

# 按 task 分片跑 144 条（方案第二部分「十」的分片表）
... --shard 1/4 --paths A1,A2,B,C,D --workers 1 ...

# P6：甲→乙→甲 在同一 worker 进程连续跑
... --sequence BinFill/0,PickXtimes/0,BinFill/1 --paths A1,C --workers 1 ...

# P3：让 B 路也产出随机流轨迹
... --trace ...
```

比较与闸门（`--gate` 可重复）：

```bash
uv run --no-sync python scripts/parity/train_split_parity.py compare \
  --run <运行目录> --pair A1:A2 --pair A1:B --pair B:C --pair C:D --pair A1:D \
  --gate BASELINE_REPEAT --gate SPEC_BINDING --gate VIDEO_PARITY \
  --gate RECOVERY_PARITY --gate RNG_PARITY \
  --history scripts/configs/newtask-v3/history/history_projection.json --history-path A1 \
  --output <运行目录>/compare
```

跨运行比较（P0 跨 job、5c 多 worker）写成 `--run <标签>=<目录>` 再用 `<标签>/<路径>` 组 pair。

## 四、发布集审计（步 5e／R1b）

```bash
# 1) 合并成官方比较器吃的格式（调官方 _merge，元数据按 144 条投影）
uv run --no-sync python scripts/parity/train_split_parity.py merge \
  --run <分片目录>... --path A1 --official-root <官方源码目录> --output <合并目录>

# 2) 跑官方合同校验与 joint_action 逐元素比较
uv run --no-sync python scripts/parity/train_split_comparison.py audit \
  --official-root <官方源码目录> --generated <合并目录> \
  --reference /data/hongzefu/robomme_data_h5 \
  --manifest scripts/configs/newtask-v3/subset_manifest.json \
  --output <结果 JSON>
```

发布集在本机 `/data/hongzefu/robomme_data_h5`，已核验为 revision `a5e4e25f`（16/16 文件大小与
SHA-256 与历史报告清单一致，见 [reference_set_verification.json](../../../scripts/configs/newtask-v3/history/reference_set_verification.json)）。
本机可直接读集群 NFS，因此审计在本机跑、读 NFS 产物比本地发布集，不需要搬数据。

## 五、集群怎么起

四个占位 job（1 GPU / 4 CPU / 32G / 48h）已在跑；把任务用
`srun --jobid=<占位> --overlap --exact ...` 塞进去，登录节点用 tmux 守着。
脚本模板在 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/slurm-holds/gl_*.sh`。

⚠ **超过 5 分钟的任务一律用 tmux detached 起**，不要用会被 harness 回收管道的后台方式——
本轮有一次 40 分钟的审计因此白跑。

## 六、各步报告

| 步 | 报告 |
|---|---|
| 0 | [身份冻结](20260921-step0-freeze-identities.md) |
| 1a | [历史证据冻结](20260921-step1a-freeze-history.md) |
| 1b | [A 路与比较器](20260921-step1b-a-path-and-comparators.md)、[A40 上的 P0／P1](20260921-step1b-cluster-p0-p1.md) |
| 2 | [恢复原值默认路径](20260921-step2-restore-native-defaults.md) |
| 3 | [sampling_config 拆分](20260921-step3-sampling-config.md) |
| 4 | [episode_spec 导出与回注](20260921-step4-episode-spec.md) |
| 5a | [十六环境五路冒烟](20260921-step5a-smoke.md) |
| 5c | [多 worker 等价性](20260921-step5c-worker-parity.md) |
| 5d | [144 条五路完整验收](20260922-step5d-full-subset.md) |
| 5e | [发布集审计（预演）](20260921-step5e-reference-audit.md) |
| 专题 | [多 worker 非确定性](20260921-worker-nondeterminism.md) |
