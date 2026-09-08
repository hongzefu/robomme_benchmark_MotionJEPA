"""从同一份场景记录生成固定英文任务指令，不引入第二套目标定义。"""


_NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen", "twenty",
)


def _number(value):
    if type(value) is not int or value <= 0:
        raise ValueError("任务指令中的次数必须为正整数")
    return _NUMBER_WORDS[value] if value < len(_NUMBER_WORDS) else str(value)


def _join_phrases(phrases):
    if len(phrases) == 1:
        return phrases[0]
    return ", ".join(phrases[:-1])+" and "+phrases[-1]


def language_goal(spec):
    """返回面向模型的固定指令；对象身份、位姿与交换后位置不进入语言。"""
    data = spec.to_dict() if hasattr(spec, "to_dict") else spec
    kind, params = data["task_kind"], data["task_parameters"]
    if kind == "BinFill":
        counts = params["target_counts"]
        phrases = []
        # 显式顺序确保 JSON 中的键顺序不会改变生成的自然语言。
        for color in ("red", "blue", "green"):
            count = counts.get(color, 0)
            if type(count) is not int or count < 0:
                raise ValueError("逐色目标数必须为非负整数")
            if count:
                noun = "cube" if count == 1 else "cubes"
                phrases.append(f"{_number(count)} {color} {noun}")
        if set(counts)-{"red", "blue", "green"} or not phrases:
            raise ValueError("BinFill 必须有至少一种受支持的非零目标颜色")
        return f"put exactly {_join_phrases(phrases)} into the bin in any order, then press the button to stop"
    if kind == "RouteStick":
        segments = params["walk_steps"]
        words = _number(segments)
        if len(params["path_indices"]) != segments+1 or len(params["directions"]) != segments:
            raise ValueError("RouteStick 语言目标与路径/绕行段数不一致")
        noun = "segment" if segments == 1 else "segments"
        return ("watch the video carefully, then use the stick attached to the robot to follow "
                "the same target sequence and pass each obstacle on the same side as shown, "
                f"completing exactly {words} {noun}")
    if kind == "VideoUnmaskSwap":
        parents = {}
        for actor in data["actors"]:
            if actor["kind"] == "cube" and "parent_id" in actor:
                parent = actor["parent_id"]
                if parent in parents:
                    raise ValueError("一个目标容器不能映射到多个藏块")
                parents[parent] = actor["color_name"]
        targets = params["target_container_ids"]
        if not targets:
            raise ValueError("VideoUnmaskSwap 的目标容器顺序不能为空")
        phrases = []
        for container in targets:
            if container not in parents:
                raise ValueError(f"目标容器缺少藏块颜色映射: {container}")
            phrases.append(f"pick up the container hiding the {parents[container]} cube")
        return "watch the video carefully, then "+", then ".join(phrases)
    if kind == "VideoRepick":
        count = params["repeat_count"]
        noun = "time" if count == 1 else "times"
        # 只说明重复次数；不能把 target_ids、颜色或目标的当前位置泄露给模型。
        return ("watch the video carefully, then pick up and put down the same cube shown in "
                f"the demonstration exactly {_number(count)} {noun}, then press the button to stop")
    raise ValueError(f"不支持的任务: {kind}")
