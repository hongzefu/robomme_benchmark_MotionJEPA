# VPB xhard4 ep5 离线结果

身份：VideoPlaceButton / xhard4 / episode 5 / seed 7000500；spec SHA-256 f08a26a6450a8fd1f20be62b25914f97f8ea287873fbbd6dadfde87233b18a31。源码锚点0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8。仅读取主代理批准的单次运行，未重试或生成。

结论：**同台放置之后，本应抓蓝块的步骤实际抓走红块，后续在线子目标因此未推进。** 这比单纯任务失败提供了更具体的证据；没有原始位姿/接触数据，不能断言精确穿透、碰撞次数或堆叠高度。

## 证据

- results.jsonl匹配预定seed与spec_sha256；ok=false、DatasetGenerationError、did not succeed after the complete task_list。
- run.log：ROUND 0 jobs=1 ok=0 wall_s=151，EXIT_CODE=0。CLI正常结束不等于任务成功。
- HDF5实际仅800字节，根键和属性均空，不能提取任务边界、深度或物体状态。文件路径：../../evidence_resources/vpb-ep5-run1/episodes/VideoPlaceButton_episode_5/hdf5_files/VideoPlaceButton_ep5_seed7000500.h5。
- 失败视频2129帧，30fps，1280×816。图中已有前视、腕视及任务叠字，可离线复核；下文编号为视频帧号，不能冒充HDF5 timestep。
- frame880：task_index=8，红块向台1下降，蓝块仍在台1。该步骤源码应是红→台1。
- frame960：task_index=9，放下红块并撤手后，红蓝处于同一个目标台附近；前视/腕视有遮挡，不能仅此帧判精确堆叠。
- 补查frame940、950、960：红块留在目标台附近，前视夹爪已在高处，腕视两指张开且与红块分离；frame975、990再次下降，frame1040重新带红抬起。因此可排除“上一步一直没有释放红块”的替代解释。连续证据见ep5-release-regrasp.png。
- frame1000：开始对同一位置执行下一次抓取；按固定任务列表，index9应抓蓝块。
- frame1060：夹爪持红块离开，蓝块仍在台1；两相机可直接识别颜色。
- frame1160：红块被放到台3，蓝块仍在台1。规划器已经执行了本应“蓝→台3”的动作，但在线目标仍显示抓取子目标，task_index=9。
- 后续总览仍可见在线任务停滞，最终未完成，和结果文件一致。

主证据图：[同台放置后抓错颜色](ep5-wrong-cube-evidence.png)；[释放、撤手、再次抓取的连续证据](ep5-release-regrasp.png)。原分辨率帧：ep5-frame-880.png、ep5-frame-960.png、ep5-frame-1000.png、ep5-frame-1060.png、ep5-frame-1160.png。总览ep5-video-overview.jpg覆盖全程。

## 根因与排除范围

VideoPlaceButton::_load_scene_xhard_tail在选择额外before平台时只排除before基础平台和答案平台，没有模拟按钮后后续动作的占用。ep5让蓝先占台1，然后又让红放台1；后续solve_pickup仍以蓝为目标规划，但实体抓取结果是红。可确认的链条是“未避让的共台布局→下一次蓝目标抓取实际抓红→蓝抓取子目标不成立”。

排除：不是last-before答案映射错误（本局答案红/台0正确）；不是after首台映射；不是平台交换造成（出错发生在演示中段、交换阶段之前）；不是从失败日志推测有误抓（双相机明确显示夹爪携红而蓝留桌）；不是CLI崩溃（退出0）。

限度：没有对照运行和接触状态，不能量化共台如何改变抓握接触，也不能排除规划器自身对近邻物体不鲁棒的共同作用；不把单局推广到所有同台布局必然失败。此例不是并排共存后成功的反例，因为已经观察到后续抓错实体。

IDENTITY=PASS；H5_COMPLETENESS=FAIL bytes=800 root_keys=0；SHARED_TARGET=CONFIRMED；WRONG_OBJECT_PICKUP=CONFIRMED intended=blue observed=red video_frame=1060；TASK_SUCCESS=0；EXACT_CONTACT_GEOMETRY=NOT_AVAILABLE。
