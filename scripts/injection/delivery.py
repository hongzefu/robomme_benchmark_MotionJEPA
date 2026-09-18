"""为冻结的 HF 发布工具保留纯判定行格式化；不提供旧交付流程。"""
from typing import Any


def render_verdict_line(verdict: dict[str, Any]) -> str:
    """判定行渲染成 ``NAME=PASS k=v k=v``（与 campaign 的 ``Verdicts`` 同式）。"""
    status = "PASS" if verdict.get("passed") else "FAIL"
    fields = " ".join(f"{key}={value}" for key, value in (verdict.get("fields") or {}).items())
    return f"{verdict['name']}={status}" + (f" {fields}" if fields else "")
