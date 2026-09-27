# 抽查：MoveCube xhard 执行段方块被演示段方块 OBB 挡住的既有缺陷（真仿真 reset）
import sys, json, traceback
sys.path.insert(0, "src"); sys.path.insert(0, ".")
import gymnasium as gym
import robomme.robomme_env  # noqa
from scripts.parity.v4_specs import env_kwargs, task_sampling
doc = json.load(open("scripts/configs/newtask-v4/sampling_config.json"))
samp = task_sampling(doc, "MoveCube")
for seed in (1000442, 1000446, 1000000):
    env = None
    try:
        env = gym.make("MoveCube", sampling_config=samp, **env_kwargs(seed, 9))
        env.reset(); print(seed, "RESET_OK")
    except Exception as e:
        print(seed, "FAIL", type(e).__name__, str(e)[:160])
    finally:
        if env is not None: env.close()
