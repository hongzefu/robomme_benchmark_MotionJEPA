# docs/

本目录保存**验证留档**：重要对拍、回归与一致性判断的可复现入口、中文实测报告与轻量证据。

与仓库已有的 `doc/`（安装与使用说明）并存，用途不同：`doc/` 面向使用者，`docs/` 面向验证与复现。

- [validation/README.md](validation/README.md)：通用记录与比较规范
- [validation/newtask-v2/README.md](validation/newtask-v2/README.md)：newtask-v2 三路对拍的用例说明与运行索引
- [plans/](plans/)：历次计划（V2～V9、robomme_hard 拆包、v7.5 评估），根目录不放计划文件
- [1002-pending-decisions.md](1002-pending-decisions.md)：截至 2026-10-02 的全部未定事项（来源、判定行、证据路径、可选处置）

体积约定：完整 HDF5、视频、详细日志与全部关键帧 PNG 留在仓库内 `artifacts/`（不入 Git）；
Git 只入指纹、目视记录与压缩数值证据，与 `AGENTS.md` 禁止提交图片、视频、HDF5 的规则一致。
