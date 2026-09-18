# 注入重构实施留档

## 阶段 0：基线冻结

用户指令原话：`/data/hongzefu/robomme\_benchmark\_MotionJEPANewTask/INJECTION\_REFACTOR\_PLAN.md`、`开始实现`。

实施起点为 `newtask-v2.1refractor` 的 `2bcd9cc`（11.08），初始工作区干净。按计划先冻结旧代码、配置、依赖锁和运行 10 已跟踪的小产物；阶段 1 建立候选包并验证 3400 条旧规格。阶段 2 及之后按计划的阶段边界另行推进。

[`baseline.sha256`](baseline.sha256) 保存旧注入工具、跑前图工具、生成器、种子布局、配置、全部已跟踪环境源码、依赖声明和锁、运行 10 已跟踪的小产物及计划的文件字节散列。大型 HDF5 与视频不在本阶段重新扫描，阶段 7 迁移前另做完整清单和散列核验。

在仓库根执行下列命令，退出 0 表示冻结清单中的文件未变：

```bash
sha256sum -c docs/validation/newtask-v2/20260917-injection-refactor/baseline.sha256 --quiet
```

本阶段实测退出 0。`command -v uv` 返回 `/home/hongzefu/.local/bin/uv`。本阶段只新增留档并更新账本，无生产代码改动，因此没有启动仿真或运行代码测试。未推送远端。
