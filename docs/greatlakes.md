# greatlakes 实测记录（本仓库）

本文只收**在本仓库的工作中亲自跑出来、有判定行或原始报错为证**的结论，逐条带日期与证据。
不复述没验过的传闻，也不收纯配置抄写。

> 与全局约定的关系：`~/.claude/greatlakes.md`（源为 MotionJEPA 仓库根目录的同名文件）是**提交规约**的权威源；
> 本文是**本仓库实测补充**，两者冲突时以那份为准，本文只补它没写或写得不够的部分。

适用集群：University of Michigan Great Lakes，账户 `chaijy2`。
**分区只用 `spgpu`**（2026-09-22 用户明令，其他分区一律不提交）。

---

## 一、GPU compute mode：必须显式 `--gpu_cmode=shared`

**这是最容易踩、也最致命的一条。**

`sbatch`／`srun` 都有这个选项，且**默认值是 `exclusive`**：

```
--gpu_cmode=<shared|exclusive|prohibited>
        Set the GPU compute mode on the allocated GPUs to
        shared, exclusive or prohibited. Default is exclusive
```

### 为什么会炸

`Exclusive_Process` 下整张卡**只允许存在一个 CUDA context**。而本链路一个进程里要两个：

1. torch 的 CUDA context（观测张量与动作都在 GPU 上）；
2. svulkan2 建 Vulkan logical device 时，NVIDIA 驱动为 CUDA-Vulkan 互操作单独开的那个
   （渲染结果零拷贝喂给 torch）。

torch 先拿到名额，Vulkan 再要就被拒，报错固定是：

```
[svulkan2] [warning] CUDA device 0 is in EXCLUSIVE or EXCLUSIVE_PROCESS mode. ...
RuntimeError vk::PhysicalDevice::createDeviceUnique: ErrorInitializationFailed
```

### 正确写法（2026-09-22 实测）

```bash
srun --jobid=<占位job> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared <命令>
```

```
MODE=Default
RUN_PATH path=B identities=1 ok=1 failed=0 exit=0 elapsed_s=35.336
VULKAN_FAILS=0
```

**不加这个参数**（同一个占位 job、同一条身份）：

```
RUN_PATH path=B identities=1 ok=0 failed=1 exit=1 elapsed_s=21.148
VULKAN_FAILS=1
```

### 排查时已经排除掉的方向（别再走一遍）

| 试过的 | 结果 |
|---|---|
| 换 `--gres=gpu:1` / 去掉 `--exact` | 无效，compute mode 与这些参数无关 |
| 换分区（`gpu` V100、`gpu-rtx6000` Blackwell、`gpu_mig40`） | 全部同样 `Exclusive_Process` 同样失败；且**已被用户禁止** |
| 自己改回来 `nvidia-smi -c 0` | `Insufficient Permissions`，需要 root |
| 怀疑残留进程占卡 | `nvidia-smi` 显存 0 MiB、无 compute app |
| 怀疑驱动变更／节点重启 | 驱动前后同为 595.71.05；三节点 BootTime 均为一两个月前、期间未重启 |
| MPS | 集群没配（`sinfo` 的 GRES 只有 `gpu:`，无 `mps:`），且 **Vulkan 不走 MPS**，配了也没用 |

**教训记在这里**：这个解法就写在 `sbatch --help` 里。当时我据"设备属性、用户改不了"直接下了
"全集群阻塞、只能报 ARC-TS"的结论，还照此往三个非 spgpu 分区提了探针 job。
排查外部环境问题，先把命令自带帮助读完再说"无解"。

---

## 二、逐位可复现性：四条实测边界

### 1. 必须单 worker

`mplib` 的 RRT 用的是**墙钟时间预算**（`planning_time=1`），并行争抢下同样 1 秒内迭代次数不同，
搜出不同路径。

| 配置 | 实测 |
|---|---|
| `--workers 4` | `BASELINE_REPEAT=FAIL different=3064`、`VIDEO_PARITY=FAIL pixels_mismatch=342`；`PickHighlight/episode_3` 出现 641 vs 643 帧 |
| `--workers 1` | 同一片 36 条身份全部 PASS |

**所有进判据的数据都必须单 worker 跑。**（2026-09-21，步 5c／5d）

**但单 worker 也只在同一次运行内可复现。**（2026-09-22 补充）同一条 `PickHighlight/episode_3`，
两次都单 worker，5d 在 gl1517 跑出 647 帧、次日在 gl1508 跑出 641 帧，从 `timestep_549` 起分叉。
`planning_time=1` 是墙钟预算，机器快慢与当时负载同样会改变 1 秒内搜到的路径。

**推论**：判据只能建立在**同一次运行内**五路之间的比较上（它们背靠背产出、共享同一段机器时间）；
**不能承诺「换台机器按同一份清单重跑得到同样的字节」**。要复现某批确切产物，只能用那批存档本身。

### 2. 进程复用是安全的

同一个 worker 进程里连续跑「甲→乙→甲」，与各自独立进程跑的结果逐位相同：
`WORKER_ISOLATION=PASS tasks=2 mismatch=0 input_mutation=0`（步 P6）。
**不可复现的来源是并行争抢，不是进程复用。**

### 3. 跨节点同配置逐位相同

`NODE_PARITY=PASS identities=1 jobs=4 mismatch=0`——同一条身份在四个不同 A40 节点上产物字节相同。
所以分片时不必在意落到哪台机器。（步 P0）

**注意覆盖面**：这条只验了**一条**身份，撑不起「任意身份跨节点都可复现」——
对时序临界的身份（如 `PickHighlight/episode_3`）就不成立，见上一条。

### 4. 跨 GPU 架构必然不同

本机 RTX 6000 Ada（sm_89）与集群 A40（sm_86），同一条身份产物**不是**逐位相同。
历史发布集当时跑在 sm_89 上，这是 R1a 的 38 条帧数差与 R1b 动作数值 `failed` 的根源，
与接口改动无关（同批环境的 `A1↔A2`、`A1↔D` 在 A40 上全部逐字节相同）。

**推论**：跨硬件的对拍只能比"结构/契约"，不能比字节；要比字节，两边必须同一款卡。

---

## 三、占用资源与进去跑

### 占位 job 模式（本轮一直在用）

```bash
sbatch --account=chaijy2 --partition=spgpu --gres=gpu:1 --cpus-per-task=4 --mem=32G \
       --time=48:00:00 --job-name=hold-4cpu-1 --wrap='sleep infinity'
```

拿到后反复进去跑，不用重新排队：

```bash
srun --jobid=<JOBID> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared <命令>
```

`--overlap` 允许与 job 内已有步骤共存，`--exact` 只取声明的那份资源。

### 配额（实测撞到过）

chaijy2 的 CPU 配额是 80。2026-09-21 提第 4 个占位 job 时卡在 `AssocGrpCpuLimit`
（他人 job 加上自己三个共占满），等别人释放才调度。**并行分片数受配额约束，不是想开多少开多少。**

### 其他占资源的办法（可用，但都不改 compute mode）

`salloc` 交互申请、`srun --pty bash` 直接抢 shell、`--exclusive` 整节点独占、
`--begin=` / `--dependency=singleton` / job array 排队接力。
真正能改 compute mode 的只有 `--gpu_cmode`，以及管理员侧的 reservation。

### 账户与分区权限（实测）

```
chaijy2      QOS=foe,normal
eecs542f2x   QOS=class
engin1       QOS=normal
```

`viz` / `viz-long` 分区用 chaijy2 提交直接 `Access/permission denied`。

---

## 四、数据与存储

- **本机可以直接读集群 NFS**（`/nfs/turbo/coe-chaijy-unreplicated/...` 已挂载）。
  跨端核对、拉日志、跑只读审计都不需要搬数据；`git pull` 也可以在本机对 NFS 克隆直接执行。
- **产物体积量级**：144 条身份 × 五路 = 720 次生成约 **189 GB**（步 5d 实测）。
  按这个比例估算 Turbo 余量再开跑。
- **官方隔离源码树可跨运行复用**：`--official-root` 指向已有目录时，
  `materialize_official_source` 校验 `.official_tree` 标记后直接返回、不写盘，
  多个 job 并发只读同一份是安全的。

## 五、生成耗时参考（单 worker，一条身份一路）

| 环境 | A40（集群） | RTX 6000 Ada（本机） |
|---|---|---|
| SwingXtimes | ~35–44 s | ~19 s |
| PickHighlight | — | ~18 s |
| VideoPlaceButton | — | ~37 s |
| VideoPlaceOrder | — | ~45 s |

本机单条比 A40 快约一倍，但**只有 A40 的结果能进判据**（见第二节第 4 条）。

## 六、观测与等待

- 超过 5 分钟的任务一律 **tmux detached** 起，不要用 `run_in_background`——
  曾有一个 40 分钟的审计被 harness 回收管道，孤儿进程 broken pipe 死掉、零输出。
- **tmux 里的任务 harness 感知不到退出，Monitor 是唯一完成信号，必须挂。**
- 日志落盘用 `tee` 不用纯重定向；管道每一级都要行缓冲
  （`stdbuf -oL tr`、`grep --line-buffered`），否则**任务一结束最后几行卡在缓冲区，Monitor 永远不唤醒**。
- 一份日志挂一个 Monitor，不要一条 `tail -F` 挂多个文件。

## 七、登录

认证走 **Okta Verify**，每次发起 ssh 前先问用户用哪种方式（6 位 TOTP 填 `Okta passcode`，
或留空触发 push + 数字匹配）。已有 ControlMaster 复用连接时，
`ssh -o BatchMode=yes` 可直接用、不触发认证——**先用 BatchMode 探一下，通了就不必打扰用户。**

`--qos=interactive` 在 chaijy2/spgpu 实测报 `Invalid qos specification`，别用。

---

## 八、aspen（sled 组自有机器，2026-09-22 打通）

- 主机 `sled-aspen.eecs.umich.edu`；登录**必须显式带密钥**：
  `ssh -i ~/.ssh/id_ed25519_umich hongzefu@sled-aspen.eecs.umich.edu`
  （公钥由用户在 sled-vail 上 `ssh-copy-id -i ~/.ssh/id_ed25519_umich.pub` 装上；文件名非默认，不带 `-i` 会被拒 `Permission denied (publickey,password)`——这就是第一次复测失败的原因。）
- 2× RTX A6000 48 GB（Ampere GA102，与 A40 同代，容差档位归 **a40**）、compute_mode `Default`（无 exclusive 问题）、驱动 570.195.03（CUDA 12.8）、16 核 / 251 GB、无 Slurm。
- `/nfs/turbo/coe-chaijy-unreplicated/hongzefu` 已挂载（与 sled-vail、greatlakes 同一份）；`/data` 14 T 余 5.8 T，`/data/hongzefu` 已存在。
- **NFS 克隆的 `.venv` 可直接用**：`python 3.11.14 / torch 2.9.1+cu128 / cuda.is_available()=True`，torch 走 NFS 导入约 32 s。零环境搭建即可跑 `train_split_parity.py run`，输出写 NFS，本机直读。
- 用法：`tmux` 在 aspen 上起，`CUDA_VISIBLE_DEVICES=0` 锁单卡；用户定为**只当算力、只测单 worker**，不进容差标定。
