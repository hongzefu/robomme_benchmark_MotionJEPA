# 噪声基线上传 HF 与读回校验（2026-10-04）

计划：`1003-code-test-maintenance-todo.md` 第二部分「细则 3.0」、H 块（阶段 3a）。

## 结论

噪声基线四遍（`v9-a`、`v9-b`、`x0-a`、`x0-b`，共 1890 个文件，其中 h5 为 `(43 格 × 3 局) × 2 遍 + (16 任务 × 1 档 × 3 局) × 2 遍 = 258 + 96 = 354` 个）加三份清单，已传到 HF **公开** bucket `HongzeFu/robomme-hard-v9-noise-baseline`，共 1893 个对象；在 greatlakes `standard` 分区纯 CPU job 内逐对象流式读回比对 sha256，1890 个数据文件全部一致（一个对象首传损坏，重传后单独复核通过）。

| 判定 | 来源 |
|---|---|
| `HF_VERIFY=FAIL objects=1893 checked=1890 sha_match=1889 size_equal=1889 missing=0 extra=0`（全量，job 63168009） | `records/hf/noise-hfverify_63168009.out.summary.txt` |
| `MISMATCH x0-a/episodes/PickXtimes_episode_11/hdf5_files/PickXtimes_ep11_seed511100.h5 got=b08add8d… want=9397cd92…` | 同上 |
| `HF_VERIFY=PASS objects=1893 checked=1 sha_match=1 size_equal=1 missing=0 extra=0 partial_only=1`（重传后单对象复核，job 63172806） | `records/hf/noise-hfverify-fix_63172806.out.summary.txt` |
| 冒烟 `HF_VERIFY=PASS objects=603 checked=1 sha_match=1 smoke_limit=1`（job 63167783，私有版阶段） | `records/hf/noise-hfverify-smoke_63167783.out.summary.txt` |

合并口径：1889（全量一致）+ 1（重传复核一致）= 1890 个数据文件全部 sha 一致；三份清单只核存在与字节数（`SHA256SUMS` 本身是比对依据）。

## 过程与用户决策

1. 用户原话（2026-10-03）：「上传HUGingFace的文件需要校验。但是校验不要在本机进行你可以生成一个在greatlake上的纯CPUJ0B来实现。以后都要这么做写进AgentMetarule」。AskUserQuestion「阶段 3a 现在就做吗」答「现在就做」。
2. 首次按计划建**私有** bucket 上传，传到 603 个对象（约 60.8 GB）时 HF 返回 `403 Forbidden: You need to setup automatic credit recharge in order to upload more data`。当时账户私有 bucket 合计 997.6 GB（公开 2902.7 GB），推断私有额度约 1 TB 已满。
3. 用户原话（2026-10-04）：「公开bocket的额度应该是实体。可以上传公开的」「额度应该是10TB。」「同意上传公开的」。据此删除私有版（只含 603 个半截对象，原件均在本机），同名重建为公开 bucket 后整目录 `hf buckets sync` 上传（四遍各数十秒，HF 按内容去重：v9-a 与公开交付集 `robomme-hard-v9` 128 局 h5 同字节），三份清单同步到根目录。
4. 清单生成：`SHA256SUMS`（1890 行）的 h5／mp4 行取自各局 `SHIPPED`（生成时节点逐局计算、暂存与拉回复核过），并与 `identities.jsonl` 交叉核对一致（`HF_MANIFEST=PASS`）；json／log 等小文件在本机计算。`identities.jsonl` 354 行、`manifest.json` 记锚点 `f8f76fba`、四遍节点与作业号。
5. 校验脚本 `records/hf/verify.py`：只用标准库 urllib 流式读取（`certifi` 证书包，GL 节点 uv 解释器无系统 CA；首个冒烟 job 63167742 因此报 `CERTIFICATE_VERIFY_FAILED`），token 只经环境变量（经 ssh stdin 读入、`--export=ALL`），不落盘。
6. 全量校验发现 `x0-a` 一个 h5 字节与大小均不符（本机原件、`SHIPPED`、`SHA256SUMS` 三处一致为 `9397cd92…`，`x0-b` 同名文件通过），判断为私有阶段上传中断遗留的损坏对象；`hf buckets cp` 单独重传后复核通过。

## 下一步

- 本机 `artifacts/noise-baseline/gen` 保留（对拍比对读本机文件，HF 是异地副本）。
- GL 上 `maint-regress/hfverify/` 目录在对拍收尾时逐个列名删除。
