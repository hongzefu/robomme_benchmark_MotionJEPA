"""S5 Astra 测试的公共替身：规划、监视、VLA、环境全部替身，零外联。

Astra 上游源码只读引用 ``$SGEVAL_THIRD_PARTY/Astra-on-RoboMME``，未设时取当前检出的 ``third_party``（worktree 里子模块为空，
须显式指向主检出）；源码不在时直接失败（不 skip）。所读上游文件逐个打印 sha256。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from tests._support.loaders import REPO, load_script

ASTRA_MODULES = ("runner", "core", "api_client", "release_utils", "input_contract", "train_entry")
#: 上游 runner.episode 默认的单局规划次数上限
MAX_PLANNER_CALLS = 24


def third_party() -> Path:
    # 未设 SGEVAL_THIRD_PARTY 时取当前检出的 third_party（主检出日常门禁即走此路）；worktree 里子模块为空，
    # 须显式设为主检出路径，否则下面的断言直接失败（不 skip）。
    value = os.environ.get("SGEVAL_THIRD_PARTY") or str(REPO / "third_party")
    root = Path(value) / "Astra-on-RoboMME"
    assert (root / "examples" / "champ" / "runner.py").is_file(), f"Astra 上游源码不在 {root}"
    return root


def print_upstream_digests(runner_mod) -> dict:
    champ = third_party() / "examples" / "champ"
    files = ("run.sh", "runner.py", "api_client.py", "core.py", "input_contract.py", "release_utils.py",
             "prepare_cases.py", "weights.json")
    digests = {}
    for name in files:
        digests[name] = hashlib.sha256((champ / name).read_bytes()).hexdigest()
        print(f"ASTRA_UPSTREAM_READ {champ / name} sha256={digests[name]}")
    return digests


def load_runner():
    return load_script("eval-official/astra_hard_runner.py")


def load_guard():
    return load_script("eval-official/astra_cost_guard.py")


@contextlib.contextmanager
def astra_session():
    """导入 Astra 上游模块并在退出时恢复 ``sys.path`` 与 ``sys.modules``，避免污染同一 pytest 会话的其他测试。"""
    saved_path = list(sys.path)
    saved_mods = {name: sys.modules.get(name) for name in (*ASTRA_MODULES, "trace_writer")}
    mod = load_runner()
    try:
        astra = mod.bootstrap(third_party())
        yield mod, astra
    finally:
        sys.path[:] = saved_path
        for name, old in saved_mods.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class NetCounter:
    """把 ``urllib.request.urlopen`` 换成计数后抛错的替身：``api_calls`` 由它实测。"""

    def __init__(self, raise_exc=None) -> None:
        self.calls = 0
        self.raise_exc = raise_exc

    def __call__(self, *a, **k):
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc()
        raise RuntimeError("测试中禁止外联：urlopen 被调用")

    def install(self, monkeypatch):
        monkeypatch.setattr(urllib.request, "urlopen", self)
        return self


# ── 环境替身 ─────────────────────────────────────────────────────────────

def _frame(value: int) -> np.ndarray:
    return np.full((256, 256, 3), value % 251, dtype=np.uint8)


class FakeEnv:
    """最小 RoboMME 环境：``terminal_step`` 步后 success；``None`` 则永不结束（由循环上限截住）。"""

    def __init__(self, terminal_step: int | None = 40, demo_frames: int = 3, step_error_at: int | None = None) -> None:
        self.t = 0
        self.terminal_step = terminal_step
        self.demo_frames = demo_frames
        self.step_error_at = step_error_at
        self.closed = False
        self.steps_taken = 0

    def _obs(self, n: int) -> dict:
        return {
            "front_rgb_list": [_frame(self.t * 7 + i) for i in range(n)],
            "wrist_rgb_list": [_frame(self.t * 11 + i + 1) for i in range(n)],
            "joint_state_list": [np.full(7, self.t + i, dtype=np.float64) for i in range(n)],
            "gripper_state_list": [np.full(2, 0.5, dtype=np.float64) for _ in range(n)],
        }

    def reset(self):
        return self._obs(self.demo_frames + 1), {"task_goal": ["pick up the cube"], "status": "ongoing"}

    def step(self, action):
        self.t += 1
        self.steps_taken += 1
        if self.step_error_at is not None and self.t == self.step_error_at:
            return self._obs(1), 0.0, False, False, {"status": "error", "error_message": "sim crash (fake)"}
        done = self.terminal_step is not None and self.t >= self.terminal_step
        return self._obs(1), 0.0, done, False, {"status": "success" if done else "ongoing"}

    def close(self):
        self.closed = True


def recording_builder_cls(env_plan=None):
    """真实 S1 ``BenchmarkEnvBuilder`` 的子类：构造参数照常走真实校验并被记录；``make_env_for_episode`` 打桩。

    ``env_plan``：可调用 ``(builder, episode) -> FakeEnv``，或抛异常模拟基础设施故障。
    """
    from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

    class RecordingBuilder(BenchmarkEnvBuilder):
        constructed: list = []
        make_calls: list = []

        def __init__(self, env_id, **kwargs):
            RecordingBuilder.constructed.append({"env_id": env_id, **kwargs})
            super().__init__(env_id, **kwargs)
            self.envs = []

        def make_env_for_episode(self, episode_idx, *args, **kwargs):
            RecordingBuilder.make_calls.append({"env_id": self.env_id, "episode": episode_idx,
                                                "args": args, "kwargs": kwargs})
            env = env_plan(self, episode_idx) if env_plan else FakeEnv()
            self.envs.append(env)
            return env

    RecordingBuilder.constructed = []
    RecordingBuilder.make_calls = []
    return RecordingBuilder


# ── 监视器、VLA、规划应答替身 ───────────────────────────────────────────

class FakeMonitor:
    """与 Astra ``Monitor.predict`` 同签名；写 ``input.json`` 与一张图，按序列返回布尔预测（默认恒 False）。"""

    def __init__(self, predictions=None) -> None:
        self.calls = 0
        self.predictions = list(predictions or [])

    def predict(self, task, goal, subgoal, frames, command_start, wrist, out):
        from PIL import Image
        out = Path(out)
        Image.fromarray(np.asarray(frames[-1])).save(out / "0.png")
        (out / "input.json").write_text(json.dumps({"task": task, "goal": goal, "subgoal": subgoal,
                                                    "command_start": command_start, "images": [str(out / "0.png")]}))
        pred = self.predictions[self.calls] if self.calls < len(self.predictions) else False
        self.calls += 1
        return pred, [0], 0.0


class FakeVLA:
    def __init__(self) -> None:
        self.infers = 0
        self.resets = 0

    def reset(self):
        self.resets += 1

    def infer(self, element):
        self.infers += 1
        assert element["observation/image"].shape == (256, 256, 3)
        return {"actions": np.zeros((16, 8), dtype=np.float32)}


def template_text(champ: Path, task: str) -> str:
    templates = json.loads((champ / "prompts" / "index.json").read_text())[task]["templates"]
    import re
    text = re.sub(r"\{[^}]+\}", "red", templates[0])
    return text.replace("<y, x>", "<100, 100>")


class FakeResponder:
    """Astra ``Planner`` 的 ``responder`` 替身：直接写 ``response.json``（OpenAI usage 原样结构），不联网。

    ``fail_on_episode_index``：第 k 次出现的新局号（按请求顺序，从 1 计）上返回 ``status=error``。
    ``after_write``：每次写完后的回调（模拟同时在跑的费用守卫）。
    """

    def __init__(self, champ: Path, usage=None, fail_on_episode_index: int | None = None, after_write=None) -> None:
        self.champ = champ
        self.calls = 0
        self.usage = usage or {"input_tokens": 1000, "output_tokens": 100,
                               "input_tokens_details": {"cached_tokens": 0},
                               "output_tokens_details": {"reasoning_tokens": 50}}
        self.fail_on = fail_on_episode_index
        self.after_write = after_write
        self.seen = []

    def __call__(self, out):
        out = Path(out)
        self.calls += 1
        request = json.loads((out / "request.json").read_text())
        key = (request["task"], request["episode"])
        if key not in self.seen:
            self.seen.append(key)
        if self.fail_on is not None and len(self.seen) == self.fail_on:
            body = {"status": "error", "error": "HTTP 500: fake planner outage"}
        else:
            body = {"status": "ok", "text": template_text(self.champ, request["task"]), "model": "gpt-6-astra",
                    "effort": "medium", "response_status": "completed", "usage": self.usage}
        (out / "response.json").write_text(json.dumps(body))
        if self.after_write is not None:
            self.after_write(out)


def make_args(tmp: Path, cases_path: Path, *, max_steps: int, group: str = "group_0", run: str = "run",
              max_planner_calls: int = MAX_PLANNER_CALLS) -> SimpleNamespace:
    run_dir = tmp / group / run
    vla = tmp / "ckpt" / "symbolic-grounded-subgoal" / "79999"
    return SimpleNamespace(cases=str(cases_path), output=str(run_dir / "results"), spool=str(run_dir / "planner_calls"),
                           max_steps=max_steps, max_planner_calls=max_planner_calls, vla_checkpoint=str(vla),
                           monitor_adapter=str(tmp / "ckpt" / "monitor"), monitor_base="fake-base", port=0,
                           trace_root=None)


def make_deps(astra, builder_cls, *, monitor=None, vla=None, responder=None, check_calls=None):
    """测试依赖：``validate_checkpoints`` 换成记录调用的替身（真实校验另有用例证明会被调用并拒绝假目录）。"""
    if check_calls is not None:
        astra.release_utils.validate_checkpoints = lambda v, m: check_calls.append((v, m))
    return SimpleNamespace(astra=astra, builder_cls=builder_cls,
                           make_client=lambda: vla, make_monitor=lambda base, adapter: monitor,
                           make_responder=lambda: responder)


def write_cases(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path
