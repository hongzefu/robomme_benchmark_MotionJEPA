# 旧实验维护源码

这里保留从 `.cache/` 移入的五个历史维护脚本。移动前后已逐字节核对，再只修正仓库根定位、自身路径及归档入口路径；实验参数、提交检查和默认历史产物路径保持原样。

- `icl-formal-v1.sh`、`icl-formal-dualgpu-v2.sh`、`icl-formal-v3.sh`：三次旧认证与验收启动器。
- `icl-final-report.py`：旧 `VERIFIED_ROOT` 汇总工具。
- `plot-icl-certified.py`：旧已认证套件绘图工具。

旧来源清单、生成数据和历史报告已经按用户要求清理。这些文件只供历史维护和查看实现，不能把缺失旧来源或提交不匹配视为可以跳过的检查。本次归档只验证语法和帮助入口，没有运行旧实验、仿真或绘图。

日常生成清单、生成数据及视频、回放及视频、绘制分布图，统一使用 [scripts/README.md](../../../README.md) 中的四个主入口：`prepare_suite.py`、`generate_dataset.py`、`replay_dataset.py`、`plot_distribution.py`。
