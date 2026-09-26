"""Utility helpers for validating and normalizing Robomme difficulty hints."""

from __future__ import annotations

from typing import Optional


# ⚠ 白名单是 16 个任务共享的；某任务是否支持某档由它自己的 configs 决定
# V6：四个新值档按难度升序排列，全部沿用同一生成机制并按档读取数值。
NATIVE_DIFFICULTIES = ("easy", "medium", "hard")
#: 新值族，按难度升序。
NEWVALUE_DIFFICULTIES = ("xhard1", "xhard2", "xhard3", "xhard4")
VALID_DIFFICULTIES = set(NATIVE_DIFFICULTIES) | set(NEWVALUE_DIFFICULTIES)
#: 新值族在全序里的档位号。
_NEWVALUE_TIER = {name: i + 1 for i, name in enumerate(NEWVALUE_DIFFICULTIES)}
#: 原版无梯度、V6 不加档的环境，只认 xhard4 这一个新值档。
NO_TIER_ENVS = ("StopCube", "MoveCube", "InsertPeg")


def is_newvalue_difficulty(value: Optional[str]) -> bool:
    """族判断：本局难度是否属于新值族；None 与原三档返回 False。"""
    return isinstance(value, str) and value.strip().lower() in _NEWVALUE_TIER


def newvalue_tier(value: Optional[str]) -> int:
    """新值族档位号：xhard1=1 至 xhard4=4；不在族内返回 0。"""
    if not isinstance(value, str):
        return 0
    return _NEWVALUE_TIER.get(value.strip().lower(), 0)


def require_xhard4_only(difficulty: Optional[str], env_name: str) -> None:
    """无梯度环境拒绝 xhard1/2/3，只允许 xhard4，不静默映射。"""
    if is_newvalue_difficulty(difficulty) and difficulty.strip().lower() != "xhard4":
        raise ValueError(
            f"{env_name} 原版无难度梯度，V6 不加档，只支持新值档 'xhard4'；收到 {difficulty!r}"
        )


def normalize_robomme_difficulty(value: Optional[str]) -> Optional[str]:
    """Return a canonical difficulty string or ``None`` if no override was provided."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            "difficulty must be a string (got "
            f"{type(value).__name__!r})."
        )

    normalized = value.strip().lower()
    if normalized not in VALID_DIFFICULTIES:
        raise ValueError(
            "Unsupported difficulty level. Available options: "
            f"{sorted(VALID_DIFFICULTIES)}."
        )

    return normalized
