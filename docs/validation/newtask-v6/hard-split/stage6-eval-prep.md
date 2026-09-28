# 拆包阶段 6：评估准备（2026-09-28）

计划：`0927-robomme-hard-layered-plan.md` 第一部分 §八、第二部分 §1.5、§3.3。用户裁决 U-8「MME-VLA 官方基底选干净 main 检出」「MME-VLA 从官方policy learning库切出 再push到https://github.com/hongzefu/robomme_policy_learning_MotionJEPA/这里的一个branch」「branch命名和我之前约定一致」「simplemem也是这样官方切出 push到我要的地方！」、U-9「先各做55*10 然后在做10」、U-12（SimpleMemVLA 切出点 `OpenBMB/SimpleMemVLA@c564c17`）。

## 一、分支与提交

| 仓库 | 切出点 | 分支 | 推到 | 提交 |
|---|---|---|---|---|
| benchmark | 12.210 `31e61259f9885f7dba8a321d0b6e699eb5061866` | `PolicyEvalThirdParty-simplememvla-0928-0311`、`PolicyEvalThirdParty-mmevla-0928-0311`（不加提交） | `hongzefu/robomme_benchmark_MotionJEPA` | — |
| SimpleMemVLA（NFS 检出） | `OpenBMB/SimpleMemVLA@c564c17d276d7294200122b286c21901a3bfb99f`（`git ls-remote` 复核 upstream main 未前进；`git diff --stat 9fce41c upstream/main -- robomme_sim pyproject.toml requirements.txt scripts` 为空） | `testhard-eval-0928-0134` | `hongzefu/SimpleMemVLA` | `f229e6a`（接入）→ `3534e2d`（`--resume` 修复） |
| MME-VLA（NFS 新 clone `robomme_policy_learning-official-testhard`） | `RoboMME/robomme_policy_learning@ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`（`origin/main` 核对） | `official-testhard-eval-0928-0137` | `hongzefu/robomme_policy_learning_MotionJEPA` | `812d542`（接入）→ `3532acf`（`ONLY_TASKS`）→ `a2f1378`（权重 run 根）→ `b93fef5`（去代理） |

推送前均 `git ls-remote` 核对远端无同名分支；未 force。

## 二、判定行

```text
POLICY_DIFF=PASS repo=smvla src_files=3 src_lines=47(<=60) meta_files=3
  （git diff --numstat c564c17 HEAD：robomme_sim/robomme_env.py +30/-8、inproc_pool.py +5/-1、eval_success.py +2/-1；
    元数据 pyproject.toml +19、.gitignore +7、.gitmodules +4；新增 testhard_eval.py、scripts/run_testhard.sh、scripts/gl_run_testhard.sh、gitlink）
POLICY_DIFF=PASS repo=mmevla src_files=2 src_lines=34(<=45) meta_files=1
  （git diff --numstat ecf086c HEAD：examples/robomme/env_runner.py +8/-4、eval.py +18/-4；元数据 .gitmodules +2/-1；
    新增 scripts/gl_eval_shard.sh、merge_eval_shards.py、robomme_env.overrides.txt、robomme_env.lock.txt；gitlink 856bc3a → 31e61259）
SUBMODULE_PIN=PASS commit=31e6125 repos=2   （git ls-tree HEAD third_party/robomme_benchmark 两仓库均为 31e61259f9885f7dba8a321d0b6e699eb5061866）
EVAL_SMOKE=PASS policy=simplememvla ckpt=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme ckpt_ok=1 status=fail steps=1014 max_steps=1500 wall_s=161.0 rss_gb=25.4 binding_available=1 injected_mismatch=0 recorded_drift=0 unused=0 value_points=23 demo_frames=0 tier=xhard1 candidate=0 seed=8400000
  （config.json sha256 5c5c1506cd7b6120c2e82a456b509e0ff92ab02862f188b22317b5aa8719bc5d；job 62177614，gl1504）
EVAL_SMOKE=PASS policy=mmevla ckpt=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-frameSamp-continue/runs/ckpts/perceptual-framesamp-modul/79999 ckpt_ok=1 status=fail steps=833 max_steps=1500 binding_available=1 injected_mismatch=0 unused=0 demo_frames=0 tier=xhard1
  （server 日志：「You are using None, changing to perceptual-framesamp-modul.yaml」「Restoring checkpoint from …/perceptual-framesamp-modul/79999/params」，6.4 GiB 31 s；单局约 5.5 分钟；job 62177615，gl1504；成功步骤 MaxRSS 17.8 GB < 28 G）
```

两局冒烟均为正常终态 `fail`（BinFill@xhard1 candidate 0），只证明链路、权重、按档上限与回注通；成功率以正式两轮为准。冒烟计 2 局评估、2 次 reset（U-14 评估侧预算）。

## 三、计划外事件与处置

1. **SimpleMemVLA 首次冒烟 argparse 退出**：官方 `eval_success.parse_args` 没有 `--resume`（上次评估分支是自己加的），`gl_run_testhard.sh` 每遍都传它 → 三遍都 `unrecognized arguments: --resume`，一局未跑。`3534e2d` 把 `--resume` 放进 `testhard_eval.py` 自己的参数，官方文件不再多改。
2. **MME-VLA 权重缺 `history_config.txt`**：官方加载器从 `checkpoint_dir.parent/history_config.txt` 读 history 配置，NFS 上 `robomme_policy_learning-frameSamp-continue/runs/ckpts/perceptual-framesamp-modul/` 只有 `79999/` → `history_config=None` → `HistoryPi0.__init__` 报 `AttributeError: 'NoneType' object has no attribute 'integration_type'`。先核对该 `79999/` 与本机官方下载 `/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/perceptual-framesamp-modul/79999`（HF `Yinpei/perceptual-framesamp-modul@c0f565dd…`，zip 按 LFS sha256 核过）`diff -rq` 18 个文件全部逐字节相同，确认是官方原权重而非续训产物；随后在评估自己的目录 `eval-out/mmevla-ckpt/perceptual-framesamp-modul/` 放官方 `history_config.txt`（内容 `perceptual-framesamp-modul.yaml`）与指向该 `79999` 的 symlink，未改动其它仓库的目录。
3. **GL 计算节点 HTTP 代理拒绝 websocket**：`Error evaluating episode 0 for task BinFill: proxy rejected connection: HTTP 403` → `API calling error, aborting...`（登录节点无代理变量，计算节点有）。`b93fef5` 让评估进程 `env -u http_proxy …` 去掉代理变量、`NO_PROXY=127.0.0.1,localhost`、`--args.host=127.0.0.1`。第二次冒烟会话按清单 `kill-session -t '=hs-evsmoke-mme2'`，残留步骤已自行结束。
4. **ManiSkill 依赖钉版**：官方 `examples/robomme/requirements.txt` 写 `git+https://github.com/YinpeiDai/ManiSkill.git@dev`（移动分支），安装时用 `uv pip install --override scripts/robomme_env.overrides.txt` 钉到 benchmark 同一提交 `07be6fbc66350ddca200abfb0a11b692f078f7fd`，官方文件不改；`robomme_env.lock.txt` 为安装后 `uv pip freeze`。

## 四、环境

- SimpleMemVLA：沿用 NFS 检出里既有的 `.venv-robomme`（cpython 3.10.19，pip 管理，benchmark 经 `sys.path` 引入，含 `robomme_hard`）与 `checkpoints/simplememvla_robomme`。
- MME-VLA：JAX 侧 `uv sync --frozen --python <NFS cpython 3.11.14>`（208 包，jax 0.5.3）；`robomme_env`：`uv venv` + `uv pip install -r examples/robomme/requirements.txt --override … -e third_party/robomme_benchmark -e packages/openpi-client`（229 包），预检 `robomme_env/bin/python -c "import robomme_hard, robomme"` 均解析到 `third_party/robomme_benchmark/src`。

## 五、评估占位 job

阶段 4 末 `HOLD_RELEASE=PASS` 之后提交（`sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:1 --gpu_cmode=shared --cpus-per-task=1 --mem=32G --time=48:00:00 --wrap='sleep infinity'`）：

| k | JobID | 首见节点 |
|---|---|---|
| 1 | 62177614 | gl1504 |
| 2 | 62177615 | gl1504 |
| 3 | 62177616 | gl1508 |
| 4 | 62177617 | gl1525 |
| 5 | 62177618 | gl1527 |
| 6 | 62177619 | gl1517 |
| 7 | 62177620 | gl1510 |
| 8 | 62177621 | gl1518 |
| 9 | 62177622 | gl1526 |
| 10 | 62177623 | gl1510 |

10 个 job 在提交后约 10 分钟内全部 RUNNING。收尾只按本表逐个 `scancel`；`62126062` 保留（U-7）。

GL 登录节点 tmux 会话：`hs-evsmoke-smvla`、`hs-evsmoke-smvla2`、`hs-evsmoke-mme`、`hs-evsmoke-mme3`（均自行退出）、`hs-evsmoke-mme2`（按清单停止）；第一轮起 `hs-eval-smvla-r1-s0`～`s9`。
