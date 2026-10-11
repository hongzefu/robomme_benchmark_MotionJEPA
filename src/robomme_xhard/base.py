"""XHardMixin：派生档子类的公共行为。

子类写法（每任务一个，放 ``envs/<task>.py``）::

    @register_env("PickXtimesXHard")
    class PickXtimesXHard(XHardMixin, PickXtimes):
        robomme_base_id = "PickXtimes"

混入后的行为：
1. ``configs``：子类创建时自动生成 ``configs[<xhard 值>] = {**父类 configs[母来源], **覆盖}``，
   父类三档原样保留；父类代码 ``self.configs[self.difficulty][...]`` 读到的就是派生档配置。
2. ``difficulty``：对外传入 ``difficulty="xhard12"`` 等；混入把母来源（hard，VideoRepick 为
   medium）交给父类 ``normalize_robomme_difficulty``，父类随后 ``self.difficulty = "hard"``
   时被属性拦截成 ``"xhard12"``。因此录像器写入 HDF5 的 ``setup/difficulty`` 是 xhard 值，
   父类里 ``self.difficulty == "hard"`` 的字面比较为假（只有 VideoRepick 有，母来源本就是 medium）。
3. ``spec``：gym.make 挂身份牌时把 id 换回原任务名，四个 wrapper、语言目标、VQA 查表都按原任务走。
4. 实例属性 ``xhard_label``、``xhard_knobs``、``source_difficulty`` 是语言目标与子类实现读取的公共契约。
"""

from __future__ import annotations

import dataclasses

from .configs import SOURCE_DIFFICULTY, TIER_CONFIGS, is_xhard, tier


class XHardMixin:
    robomme_base_id: str | None = None
    # 母配置来源，子类创建时按 SOURCE_DIFFICULTY 填好
    source_difficulty: str = "hard"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        base_id = cls.__dict__.get("robomme_base_id")
        if not base_id:
            return
        if base_id not in TIER_CONFIGS:
            raise KeyError(f"{base_id} 没有任何 xhard 档，不应定义派生子类")
        cls.source_difficulty = SOURCE_DIFFICULTY[base_id]
        parent_configs = getattr(cls, "configs", None)
        if isinstance(parent_configs, dict) and cls.source_difficulty in parent_configs:
            merged = {k: v for k, v in parent_configs.items() if not is_xhard(k)}
            for label, entry in TIER_CONFIGS[base_id].items():
                merged[label] = {**parent_configs[cls.source_difficulty], **entry["config"]}
            cls.configs = merged

    def __init__(self, *args, difficulty=None, **kwargs):
        if not is_xhard(difficulty):
            raise ValueError(
                f"{type(self).__name__} 只接受 xhard12..xhard20，收到 {difficulty!r}；母档请用原任务名"
            )
        label = difficulty.strip().lower()
        entry = tier(self.robomme_base_id, label)
        # 必须在父类 __init__ 之前设好：父类给 self.difficulty 赋值时要靠它拦截
        self.__dict__["_xhard_label"] = label
        self.xhard_label = label
        self.xhard_knobs = dict(entry["knobs"])
        super().__init__(*args, difficulty=self.source_difficulty, **kwargs)

    @property
    def difficulty(self):
        return self.__dict__.get("_xhard_difficulty")

    @difficulty.setter
    def difficulty(self, value):
        label = self.__dict__.get("_xhard_label")
        if label is not None and value == self.source_difficulty:
            value = label
        self.__dict__["_xhard_difficulty"] = value

    @property
    def spec(self):
        return self.__dict__.get("_xhard_spec")

    @spec.setter
    def spec(self, value):
        if value is not None and self.robomme_base_id:
            value = dataclasses.replace(value, id=self.robomme_base_id)
        self.__dict__["_xhard_spec"] = value
