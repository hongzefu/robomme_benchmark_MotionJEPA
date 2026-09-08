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
    fingerprint = runtime_fingerprint()
    if certification["runtime_fingerprint"] != fingerprint:
        from .errors import ReproducibilityError
        raise ReproducibilityError("当前运行环境与套件认证指纹不同")
    return make_env_from_spec(spec, **kwargs)


def make_env_from_spec(spec, *, record_demonstration=True):
    """认证器内部入口：创建待认证候选，不把其视作已发布清单。"""
    configure_runtime()
    import gymnasium as gym
    from .envs import register_envs
    from .envs.wrapper import ICLJointAngleEnv
    from .suite import EpisodeSpec

    spec = spec if isinstance(spec, EpisodeSpec) else EpisodeSpec.from_dict(spec)
    register_envs()
    raw = gym.make(spec.env_id, episode_spec=spec, disable_env_checker=True)
    return ICLJointAngleEnv(raw, record_demonstration=record_demonstration)
