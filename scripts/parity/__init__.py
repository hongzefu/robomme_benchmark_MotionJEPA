"""对拍链路：原始 train 五路逐位对拍（train_split_*）与 vs 原版发布集的容差校验。

两族脚本都在本目录下，既可按路径直跑
``uv run --no-sync python scripts/parity/train_split_parity.py <子命令>``，
也可作包导入（``from scripts.parity import train_split_parity``）。
模块之间沿用同目录裸 import，各入口自行把本目录插进 ``sys.path``；
``seed_layout`` 仍在 ``scripts/`` 顶层。现行说明见 scripts/README.md 与本目录 README.md。
"""
