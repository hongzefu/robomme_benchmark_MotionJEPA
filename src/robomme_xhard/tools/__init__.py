"""robomme_xhard 的离线工具（只读已有产物，不起仿真）。

- ``mother_seeds``：按计划“固定配置参照子集”与 R11 选每任务 2 个母 episode/seed。
- ``summarize``：读一个输出根，出逐条实测表（timestep、stride-16 窗口数、相对母档倍数）。
- ``compare_video``：每个“任务＋母 seed”六栏同屏对比，接成一个 MP4。
- ``layout``：上面两个工具共用的产物发现与 HDF5 读取。
"""
