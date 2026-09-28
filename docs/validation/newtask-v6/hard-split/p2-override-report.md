# P2 覆盖项实施报告（阶段 1，U-3「现在一次批准这两项」）

用户 2026-09-27 批准两项 P2「覆盖」，本报告按「改完出报告」记录实现。两项都只改变**导入了 `robomme_hard` 的进程**里的行为；`src/robomme` 源文件本阶段零改动。

## 1. 16 个环境 id 的运行时接管

- **文件／锚点**：`src/robomme_hard/robomme_env/<Task>.py` × 16 的类装饰器 `@register_env("<id>", override=True)`。
- **做了什么**：ManiSkill `mani_skill/utils/registration.py::register_env` 在 `override=True` 时先把 `REGISTERED_ENVS` 与 gymnasium `registry` 里的旧登记弹出再注册。借用 shim 导入官方模块会顺带执行 `robomme/robomme_env/__init__.py`、先注册官方 16 个类；随后本包的类定义以 `override=True` 接管。之后官方包再次导入时以 `override=False` 注册，只打日志、保留已登记的本包类。结果：导入过 `robomme_hard` 的进程里 16 个 id 一律归本包，与导入顺序无关。
- **防线**：`robomme_hard/__init__.py` 末尾断言 `REGISTERED_ENVS[uid].cls.__module__` 以 `robomme_hard.` 开头，否则 `ImportError`；另断言 16 个环境模块与 `utils` 包命名空间里本包同名可调用对象都属于本包。三种导入顺序的子进程测试见 `tests/lightweight/test_registry_owner.py`（官方态 PASS）。
- **注册期日志**：用 `from mani_skill import logger` 取到的对象本身（名字带尾随空格 `"mani_skill "`）临时提到 ERROR，在 `finally` 里恢复。

## 2. `BenchmarkEnvBuilder` 子类覆写

- **文件／锚点**：`src/robomme_hard/env_record_wrapper/hard_builder.py::BenchmarkEnvBuilder`，父类 `robomme.env_record_wrapper.episode_config_resolver.BenchmarkEnvBuilder`（官方源码不改）。
- **覆写的成员**：`__init__`（接受 `test-hard`；以 `dataset="test"` 过父类白名单后改回 `test-hard`，父类读到的 test 元数据清空不用）、`_resolve_metadata_path`（train × 四个 Unmask 任务改读包内 400 条）、`resolve_episode`（test-hard 返回 `(seed, tier)`）、`get_episode_num`、`make_env_for_episode`（整段与官方同构，wrapper 取本包类；test-hard 加 `sampling_config` 与 `native_episode_spec` 回注）。新增只读 `resolve_identity(episode)`；`from_v4_specs`／`v4_episodes` 为旧快照薄包装。
- **验证**：`WRAPPER_CHAIN=PASS action_spaces=4 chain_equal=4 hard_modules_ok=4`（官方态，test 与 test-hard 包装链类名序列逐项相同）；单局冒烟 `HARD_RESET_REPLAY=PASS resets=1 … injected_mismatch=0 goal_mismatch=0`。

阶段 3 对 `src/robomme` 的回退属另一组 P2 改动，已由 U-21 预先批准，另见 `stage3.md`。
