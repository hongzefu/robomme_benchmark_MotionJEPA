"""robomme-ICL：配置驱动的独立环境入口；导入时不启动仿真。"""

__version__ = "0.1.0"


def make_env(*, task, seed, suite, **kwargs):
    """从已经认证的场景清单中创建一局环境。"""
    from .api import make_env as create

    return create(task=task, seed=seed, suite=suite, **kwargs)
