# gen-regress 逐局报告：v9

- 判定行：`GEN_REGRESS=NEED_RERUN flip=1 set=v9 n=129 match=127 jitter=1 flip=1 structural=0 unknown=0 missing=0 invalid=0 rerun_rows=4 filler=3`
- 参照：`scripts/configs/noise-ref-20261003.json`（sha256 `5119e2ac71ca`）
- 首跑：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/maint-regress/gen/rg-v9r`；改后第二次：`—`；旧代码：`—`

| 任务 | 档 | seed | 参照类 | 陪跑 | 第一次 | 改后第二次 | 旧代码 | 一=二 | 一=旧 | 二=旧 | 分叉步 | 子目标 | 定性 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| StopCube | xhard4 | 22200000 | stable | 是 | `d4b7aaab77c2` 成功 | — | — | — | — | — | — | — | 陪跑（只报告） |
| StopCube | xhard4 | 22200100 | stable | 是 | `dd1bae03cd98` 成功 | — | — | — | — | — | — | — | 陪跑（只报告） |
| StopCube | xhard4 | 22200200 | stable | 是 | `732002d8cfe1` 成功 | — | — | — | — | — | — | — | 陪跑（只报告） |
| BinFill | xhard1 | 16400000 | jitter |  | `26c4d449632e` 失败 | — | — | — | — | — | — | — | 已知抖动（只报告：fail） |
| MoveCube | xhard4 | 23400200 | stable |  | `6b85dd3239e0` 成功 | — | — | — | — | — | — | — | flip_pending |
