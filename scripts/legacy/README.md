# 归档入口

当前四项工作统一使用上一级 `scripts/` 的入口：生成环境清单 `prepare_suite.py`、生成数据 `generate_dataset.py`、严格回放 `replay_dataset.py`、生成分布图 `plot_distribution.py`。用法见 [scripts/README.md](../README.md)。

本目录保留旧工具及其配套说明，供历史实验维护。新链路不导入本目录业务脚本。归档保留原有行为，包括部分旧生成器的自动换 seed 逻辑；ICL 当前四入口只消费冻结规格。

## 路径对应

原 `scripts/` 下的 36 个 Python 文件整体按以下规则迁移，文件名不变：

| 原位置 | 归档位置 |
| --- | --- |
| `scripts/{dataset_replay,evaluation,run_example}.py` | 本目录同名文件 |
| `scripts/data-generation/*.py` | [data-generation/](data-generation/) |
| `scripts/data-generation-newSeed/*.py` 及 `utils/*.py` | [data-generation-newSeed/](data-generation-newSeed/) 下同相对路径 |
| `scripts/data-generation-MotionJEPALabel/*.py` | [data-generation-MotionJEPALabel/](data-generation-MotionJEPALabel/) |
| `scripts/400ep-dataset/*.py` | [400ep-dataset/](400ep-dataset/) |
| `scripts/patternlock-routestick-params/*.py` | [patternlock-routestick-params/](patternlock-routestick-params/) |

这些工具目录的 7 个 `README.md` / `CLAUDE.md` 随源码移动。ICL 维护入口统一在 [robomme_icl/](robomme_icl/)：

| 原入口 | 归档文件 |
| --- | --- |
| `src/robomme_icl/cli.py` | `robomme_icl/cli.py` |
| `src/robomme_icl/__main__.py` | `robomme_icl/module_entry.py` |
| `src/robomme_icl/suite/preflight.py` | `robomme_icl/preflight.py` |
| `tests/robomme_icl/run_acceptance.py` | `robomme_icl/run_acceptance.py` |
| `tests/robomme_icl/run_interruption.py` | `robomme_icl/run_interruption.py` |
| `tests/robomme_icl/check_manifest.py` | `robomme_icl/check_manifest.py` |
| `tests/robomme_icl/report_acceptance.py` | `robomme_icl/report_acceptance.py` |
| `tests/robomme_icl/plot_suite.py` | `robomme_icl/plot_suite.py` |

归档入口仍通过 `uv run scripts/legacy/<相对路径>.py ...` 调用。旧 `uv run robomme-icl` 和 `uv run python -m robomme_icl` 不再注册。

## 历史数据与运行记录

用户追加要求只保留本次产物。旧 `outputs/`、`reports/`、`run_*.json`、`run-log.md` 等生成数据和报告已按验收后的明确清单删除；官方参考数据未触碰。

当前产物统一位于 [scripts-v1数据目录](../../artifacts/generated/robomme-icl/scripts-v1/)，本次执行与清理证据位于 [scripts-v1报告目录](../../artifacts/reports/robomme-icl/scripts-v1/)。本目录和根账本中的旧数据路径、历史结论仅记录当时执行情况，不表示旧文件仍然存在；已跟踪的历史报告可从Git历史查询。

源码导入路径指向归档目录；由脚本位置推导的仓库根、默认输入和历史报告目录已经分别修正。旧命令的代码路径已改为归档路径，重新运行归档工具时须明确指定新的仓库内输出目录。
