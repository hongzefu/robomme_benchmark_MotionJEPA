# v75-lanes：v7.5eval 实跑车道辅助脚本（2026-09-30 执行记录）

本目录保存 v7.5eval 实跑期间**实际执行过**的一次性车道辅助脚本，目的是让「当时跑的是哪版脚本」可追溯；它们不是通用工具，不保证可直接复用。正式工具在上一级 `scripts/eval-official/`（`env_client.py`、`run_seat.sh`、`orchestrate.py`、`official_observer/` 等），这里的脚本只是把正式工具串成车道、传参、暂存产物。

- `gl/`：GL 侧（NFS `v75eval/lanes/`，由编排器在占位 job 内经 `srun --overlap` 调用，或在登录节点 tmux 里运行）。
  - `step.sh`：编排器步骤包装（写报告 JSON 与 `STEP_RC=`；支持 `skip/<报告名>.skip` 跳过标记与 `V75_NOSKIP=1` 豁免，用于把分片改派到别的席位）。
  - `seat_run.sh`：单席位单策略执行 `run_seat.sh`，输出先写节点 `/tmp` 再暂存到 NFS `stage/` 并按内容核对。
  - `official_mme_resume.sh`、`official_smvla_resume.sh`：GPU 计算模式事故后，用历史启动器自带的 `done_keys`／`--resume` 续跑官方分片。
  - `restage.sh`：补暂存节点 `/tmp` 遗留产物（只处理显式点名的条件／策略）。
  - `keeper.sh`：取消点名的等待步骤后起一个永不结束的 `--gpu_cmode=shared` 保持步骤（GPU 计算模式事故急救）。
  - `orch_*.sh`：各编排器实例的启动器（official、main、o2x、mmeprod、retry、final、final2～final8）；对应计划 JSON 与状态目录归档在 `artifacts/v7.5eval/nfs-archive/state/`（不进 git）。
  - `env-gl*.sh`、`replay-gl.sh`、`norec_smvla.sh`、`det_of.sh`、`run_logged.sh`：2.1 环境检测、第 4 步回放、2.2 无录制对照、确定性结论读取、日志包装。
- `local/`：本机 sled-vail 侧（`artifacts/v7.5eval/lanes/`）：卡 0／卡 1 接力（`chain-card0.sh`、`chain-card1.sh`）、`eval-local.sh`、`replay-local*.sh`、`mover.sh`（NFS 暂存 → `/data` 搬运）、`aggregate*.sh`（事件汇总日志）等。

注意：`seat_run.sh`、`step.sh`、`restage.sh` 在实跑中途修改过（NFS ACL 误判暂存失败、MME 权重符号链接、跳过标记、通配符误删），这里保存的是**最终版本**；中途版本的缺陷、触发时刻与影响见 `docs/validation/v7.5eval/incidents.md`。
