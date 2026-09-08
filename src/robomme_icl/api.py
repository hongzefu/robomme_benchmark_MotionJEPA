"""新版公开 API；旧环境注册、旧记录器与旧 seed 解析器均不参与。"""

from .runtime import configure_runtime


def make_env(*, task, seed, suite, **kwargs):
    """只允许读取已认证且运行指纹匹配的冻结清单。"""
    configure_runtime()
    from .suite import find_spec, load_suite
    from .io.fingerprint import runtime_fingerprint

    catalog = load_suite(suite)
    spec = find_spec(catalog, task=task, seed=seed)
    certification = catalog["certification"][spec.spec_hash]
    if "render_gpu" not in certification:
        raise ValueError("旧认证未记录固定 GPU 绑定，请用当前版本重新 prepare")
    render_gpu = certification["render_gpu"]
    if "render_gpu" in kwargs and kwargs.pop("render_gpu") != render_gpu:
        raise ValueError("不能更改已认证 seed 的 GPU 绑定")
    fingerprint = runtime_fingerprint(render_gpu=render_gpu)
    if certification["runtime_fingerprint"] != fingerprint:
        from .errors import ReproducibilityError

        raise ReproducibilityError("当前运行环境与套件认证指纹不同")
    return make_env_from_spec(spec, render_gpu=render_gpu, **kwargs)


def make_env_from_spec(spec, *, record_demonstration=True, render_gpu=0):
    """认证器内部入口：创建待认证候选，不把其视作已发布清单。"""
    configure_runtime()
    if type(render_gpu) is not int or render_gpu < 0:
        raise ValueError("render_gpu 必须是非负的物理 GPU 序号")
    import gymnasium as gym
    from .envs import register_envs
    from .envs.wrapper import ICLJointAngleEnv
    from .specs import EpisodeSpec

    spec = spec if isinstance(spec, EpisodeSpec) else EpisodeSpec.from_dict(spec)
    register_envs()
    from .io.fingerprint import runtime_fingerprint

    expected_device = runtime_fingerprint(render_gpu=render_gpu)

    def raw_factory():
        raw = gym.make(
            spec.env_id,
            episode_spec=spec,
            render_gpu=render_gpu,
            disable_env_checker=True,
        )
        actual = raw.unwrapped.scene.sub_scenes[0].render_system.device
        if (
            actual.cuda_id != render_gpu
            or actual.pci_string != expected_device["render_gpu_pci"]
        ):
            raw.close()
            raise RuntimeError("实际渲染GPU与冻结的物理设备绑定不一致")
        return raw

    return ICLJointAngleEnv(
        raw_factory,
        task_kind=spec.task_kind,
        seed=spec.seed,
        record_demonstration=record_demonstration,
    )
