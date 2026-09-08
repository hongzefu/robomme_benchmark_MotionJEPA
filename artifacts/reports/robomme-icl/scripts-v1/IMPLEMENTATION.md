# 四个scripts入口、视频和产物清理实施记录

本轮从 `a69e9bc2692e5a16e8be78c4cfe779d9b8da6065` 的干净工作区开始，分支为newtask-v1，使用已有上游origin/newtask-v1。本机为/data NVMe/ext4、两张RTX6000 Ada；共享根uv环境，原版src/robomme、challenge_interface、uv.lock不修改。

## 用户要求与实施

用户要求生成环境清单、生成数据、回放、绘制分布图四个入口都在scripts；生成和回放均须保存视频，保持当前ICL HDF5格式、逐episode存储、不合并。已建立prepare_suite.py、generate_dataset.py、replay_dataset.py、plot_distribution.py，以及无独立入口的scripts/_icl公共模块。

36个旧脚本、7份配套文档与8个ICL维护入口已迁入scripts/legacy；历史路径映射保留在其README。归档时修复根路径、跨目录导入和轻量测试引用；数据在认证结束前保持原位。原版工具自测和challenge_interface按用户确认不处理。旧console脚本注册移除，uv sync后本项目venv不再存在robomme-icl命令。

视频使用当前原始双RGB横拼及演示红框，FPS来自spec（当前20）、libx264/yuv420p/CRF18/单编码线程。只操作图像副本，校验可解码性、帧数、尺寸和来源后发布；相同来源完整视频可复用，缺失视频可重建，未知或损坏输出不会覆盖HDF5。图表采用既有四任务组合图，增加实际计数、位置分层覆盖和来源摘要。

删除包内入口改变源码指纹，因此source-suite模式只保持原spec/seed/GPU重认证，每条两次新物理运行都与旧原始帧严格对照，不重新选择候选。恢复上下文升级为schema2：合法身份的中断记录保留后新attempt重试；任务失败和帧差异锁存；完整坏记录或完成凭证丢失均硬失败。

## 集成发现与修正

- 阶段身份最初只逐阶段绑定，现增加本地suite与生成输入一致性，防止一个批次混入两个清单。
- 总状态改为聚合所有阶段，后续prepare成功不能掩盖已有generate失败。
- 回放输出不能嵌入实际HDF5扫描根，且回放根与prepare/generate根隔离；正常批次/replay仍可用。
- 配置tuple在运行身份中规范化为JSON形态，避免恢复时tuple/list差异。
- 旧版全轻量测试在280秒上限停止，未宣称全套通过；直接复核旧失败文件仍为4 failed、27 passed，0.96秒，四失败与已知基线相同。

## 已有验证证据

- 新版完整测试170 passed、4 skipped，40.15秒；四个skip需要显式仿真清单，后续真实入口验收覆盖。
- 媒体8项真实FFmpeg/恢复负例通过；归档94 passed、2 skipped，14个help及44个Python语法检查通过。
- 最小BinFill单episode/单worker，两次新运行与旧600帧逐位相同。
- 四任务共8条开发认证（每任务前2条）通过；最终源码四任务各一条双卡认证通过，帧数641/451/271/1045，均与旧记录逐位一致。
- 最终四任务生成与回放分别产4个HDF5和4个MP4，全部原始帧与认证逐位一致；独立plot入口验证同来源复用成功。development.json保存8个HDF5/视频的来源、帧数、校验结果和原始开发日志。以上为开发验证，不提前记为全96条交付。

## 用户追加清理要求

用户原话：“本仓库只保留这一次的产物 之前的都删除”；随后明确“只删旧生成产物和报告，保留官方参考集”。本次96条及192个视频、四图全部完成并验收后，才按明确清单删除旧生成数据、旧报告和本轮临时smoke产物。

最终保留artifacts/generated/robomme-icl/scripts-v1和本报告目录；保留本次provenance/source_suite.json以说明原96条来源，旧原始大数据清理后不再声称可重做旧帧对照。新的认证、HDF5、MP4和回放保持自足。官方data路径、源码、配置、静态assets与依赖缓存不删；当前工作副本的data/robomme_data_h5实际不存在，不访问或清理仓库外副本。

正式执行已从c139a522c2c05e8fc5d206ec0d32103f13fbd237干净基线，在gen-icl-scripts-v1-20260908完成，全部阶段退出0。96条、每遍63689帧、384份HDF5逐位一致、192个视频及四图均独立验收通过；90根旧产物清理和清理后复核也通过。最终路径、可复现命令与清理证据见[FINAL.md](FINAL.md)，逐条原始验收见[verification.json](verification.json)，清理后的保留检查见[post_cleanup.json](post_cleanup.json)。
