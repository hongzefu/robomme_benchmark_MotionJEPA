"""新值注入链路：候选冻结与实跑分别由 candidates、rollout 两包提供。

在仓库根目录使用 ``uv run python -m scripts.injection.candidates`` 或
``uv run python -m scripts.injection.rollout``；现行说明见 scripts/INJECTION.md。
生成器只读 candidates.io 的封套校验接口；生产包不依赖 tests。
"""
