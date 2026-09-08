# 四入口、视频与唯一保留批次：最终交付

本次已完成96条环境重新认证、生成、严格回放及独立整包验收，并按用户要求删除旧生成产物和报告。数据仅保留 `artifacts/generated/robomme-icl/scripts-v1/`，报告仅保留本目录。原版源码、配置、依赖环境和官方参考数据未触碰；当前工作副本原本没有 `data/robomme_data_h5/`，没有访问或删除仓库外副本。

## 四个日常入口

| 功能 | 入口 |
| --- | --- |
| 根据配置生成清单，或按来源清单保持原spec重新认证 | [prepare_suite.py](../../../../scripts/prepare_suite.py) |
| 生成HDF5、生成视频及分布图 | [generate_dataset.py](../../../../scripts/generate_dataset.py) |
| 严格回放，保存回放HDF5及视频 | [replay_dataset.py](../../../../scripts/replay_dataset.py) |
| 从真实清单独立绘制分布图 | [plot_distribution.py](../../../../scripts/plot_distribution.py) |

完整命令见 [scripts/README.md](../../../../scripts/README.md)。旧命令注册已移除；归档维护工具留在 `scripts/legacy/`，不属于日常入口。旧工具目录的缓存及空目录已清理。

## 保留产物

| 产物 | 位置与数量 |
| --- | --- |
| 冻结清单 | [suite/suite.json](../../../generated/robomme-icl/scripts-v1/suite/suite.json)，四任务各24条，每档各8条 |
| 认证记录 | 清单内部引用192份新认证HDF5，均在本批 `suite/` 内 |
| 生成数据 | [hdf5_files/](../../../generated/robomme-icl/scripts-v1/hdf5_files/)，96个逐episode文件 |
| 生成视频 | [videos/](../../../generated/robomme-icl/scripts-v1/videos/)，96个MP4及对应来源JSON |
| 回放数据与视频 | [replay/](../../../generated/robomme-icl/scripts-v1/replay/)，96个HDF5、96个MP4及来源JSON |
| 分布图 | [BinFill](../../../generated/robomme-icl/scripts-v1/distributions/binfill.png)、[RouteStick](../../../generated/robomme-icl/scripts-v1/distributions/routestick.png)、[VideoUnmaskSwap](../../../generated/robomme-icl/scripts-v1/distributions/videounmaskswap.png)、[VideoRepick](../../../generated/robomme-icl/scripts-v1/distributions/videorepick.png) |
| 实际分布统计 | [distribution_summary.json](../../../generated/robomme-icl/scripts-v1/distributions/distribution_summary.json)，实际次数、位置分层覆盖、来源摘要 |

所有位置和数量均来自冻结spec，没有补造样本。视频按原始顺序横拼前视/腕部图像，在图像副本上给演示阶段加红框；192个视频均为20fps、512×256、libx264/yuv420p/CRF18/编码线程1。MP4用于观看，逐位一致性比较HDF5原始图像、动作、状态、事件和判定数据。

## 运行与验收证据

正式基线为 `c139a522c2c05e8fc5d206ec0d32103f13fbd237`，从干净已提交代码启动。两张RTX6000 Ada分别绑定48条，物理为CPU单环境，生成和回放使用32 workers，视频导出4 workers，独立验收4 workers，单条物理墙钟上限1200秒。存储为本机 `/data` NVMe/ext4；完整配置、设备及源码/依赖指纹见 [run_context.json](run_context.json)。

启动命令为 `bash scripts/legacy/robomme_icl/run_scripts_v1.sh c139a522c2c05e8fc5d206ec0d32103f13fbd237`，运行于登记的detached tmux `gen-icl-scripts-v1-20260908`。主进程和采样进程均正常退出，原有七个tmux会话未动。

| 阶段 | 结果 | 墙钟秒 |
| --- | --- | ---: |
| 原96个spec重新认证 | 两次新物理运行分别与旧原始帧逐位一致，保持spec、配置、seed和GPU | 577.61 |
| 生成 | 96个HDF5、96个MP4、四图 | 521.02 |
| 严格回放 | 96个HDF5、96个MP4，原始记录逐位一致 | 533.91 |
| 独立绘图入口 | 同来源图表核对与复用通过 | 0.41 |
| 独立整包验收 | 384份HDF5、192视频和四图全部通过 | 594.64 |

五阶段命令及tee均退出0，主任务 `EXIT_CODE=0`。每遍63,689帧；没有任务失败、基础设施重试或换seed。新清单摘要为 `2e19b64f8d7d839f5d643f69fb9f996fb8394d6b73cef401d6c530a0b5384e0f`。

[verification.json](verification.json) 和 [verification.md](verification.md) 保存逐条全帧比较、视频完整解码、帧数/FPS/尺寸/哈希、图表及源码边界检查。两个新认证记录、生成记录和回放记录来自四个独立物理过程；内部 `.staging` 硬链接不冒充额外独立记录。原版102个源码文件及uv.lock对 `a69e9bc` 逐文件一致，原版Git树仍为 `1d0154117e58c783cd3466dbad910aeaaff573a8`。

开发验证为新版170 passed、4 skipped；清理维护另有18项可重跑回归，9.64秒，通过默认不删、固定清单删除、符号链接、保护目录、未知文件及失败验收等行为测试。旧产物删除后重跑整个新版目录，188 passed、4 skipped，49.72秒；随后显式设置 `ICL_TEST_SUITE` 为保留的新清单，四项同环境连续reset测试全部通过，156.20秒，各任务首条600/463/199/639帧均与认证记录及第二次运行逐位一致。结果见 [final_tests.json](final_tests.json) 和 [final_reset_tests.json](final_reset_tests.json)。

旧完整lightweight在280秒上限停止，旧失败文件定向复核仍为4 failed、27 passed，属于已知原版差异；没有声称旧全套测试通过。开发与清理维护的原始记录见 [development.json](development.json) 和 [cleanup_tool_tests.json](cleanup_tool_tests.json)。

## 清理与清理后复核

用户明确要求“本仓库只保留这一次的产物 之前的都删除”，并确认“只删旧生成产物和报告，保留官方参考集（推荐）”。全部验收成功后，先默认盘点，再显式执行 `cleanup_previous_outputs.py --apply`；均退出0。

[cleanup-plan.json](cleanup-plan.json) 和 [cleanup-result.json](cleanup-result.json) 记录90个明确根及逐项删除结果，合计约265.05 GiB逻辑文件大小，含硬链接名称，因此不等同于实际释放空间。随后删除9个已确认源码归档的编译缓存和10个空目录；补充清除13个可恢复的临时提交文本、旧项目wheel、重复库存、字节码和已完整收录的日志。维护源码保留于legacy，依赖缓存保留。

额外发现的5个临时维护源码已移入 `scripts/legacy/robomme_icl/historical_helpers/`，只修正仓库根及已归档入口路径；原始和归档SHA、最小改动及10项语法/帮助检查保存在 [source_archive.json](source_archive.json)。补充产物删除见 [supplemental_cleanup_result.json](supplemental_cleanup_result.json)。

[post_cleanup.json](post_cleanup.json) 确认90个旧根和192份旧来源物理记录均已不存在，本次384份HDF5的头信息/spec/内容摘要、192视频文件哈希、四图、运行指纹和原版源码仍一致。生成和报告目录各仅剩本批。旧v3的完整帧对照在重新认证时已经完成；清理后只保留 [provenance/source_suite.json](../../../generated/robomme-icl/scripts-v1/provenance/source_suite.json) 来源快照和认证证据，不能再声称可读取已删除的旧帧重做对照。

后续按本批 `suite/suite.json` 生成、回放或重新认证只依赖保留的spec和新记录，不读取旧train metadata或旧物理数据。各项清理库存和结果均保存在本报告目录，根AGENTS.md保留历史执行摘要；已删除的旧跟踪报告仍可从Git历史查询。
