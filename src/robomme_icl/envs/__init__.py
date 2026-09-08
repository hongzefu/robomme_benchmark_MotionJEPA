"""新版环境采用独立注册 ID；注册仅在显式创建环境时发生。"""


def register_envs():
    """幂等注册四任务，不覆盖任何原版注册。"""
    from .registry import register_envs as register
    register()
