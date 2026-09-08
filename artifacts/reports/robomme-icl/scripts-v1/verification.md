# scripts 整批产物验收

状态：通过。96 条环境、每任务 24 条，逐遍 63,689 帧。

384 份 HDF5（两份新认证、生成和回放）均通过内容摘要与原始帧逐位比较；192 个 MP4 均通过来源、摘要、帧数、FPS、512×256 尺寸及完整解码检查。

四任务图表摘要、实际次数及位置分层覆盖通过；原版 src/robomme 与 uv.lock 对 a69e9bc 逐文件相同。

检查范围：重新验签96条冻结spec、两份新认证及生成/回放原始记录；逐位比较；192视频完整解码；四任务真实分布；未重新运行物理。源清单使用本批 provenance 快照或显式指定文件；旧记录仅核对快照中的路径，允许清理后不存在，旧帧不再读取。旧原始帧的跨版本一致性采用新认证中的source_frames_equal证据。

旧记录实体仍存在：192/192；本次未读取旧帧，跨版本对照依据新认证的 source_frames_equal。

- 新清单：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/scripts-v1/suite/suite.json`
- 来源清单：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/generated/robomme-icl/scripts-v1/provenance/source_suite.json`
- 新清单摘要：`2e19b64f8d7d839f5d643f69fb9f996fb8394d6b73cef401d6c530a0b5384e0f`
- 入口摘要：`c6e4697e9b034f4583c75b19d088712e4a81fed42625c40d042077c79040f6c1`
- 并发：4；总耗时：594.44 秒。

逐条视频摘要、原/新运行指纹和验收证据保存在同目录 verification.json。
