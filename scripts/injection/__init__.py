"""新值注入链路（候选分布 plan/check、生成 h5 的 run、对拍 compare、出图 plot/report）。

运行方式（须在仓库根目录执行，``scripts`` 是命名空间包）：

    uv run --no-sync python -m scripts.injection.campaign <子命令> ...

本包不依赖 ``tests/``；``tests/`` 反向 import 本包做单测。生产入口
``scripts/generate_dataset_newseed.py`` 与 ``src/robomme`` 不导入本包。
"""
