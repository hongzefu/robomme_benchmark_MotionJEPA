"""Utility helpers for validating and normalizing Robomme difficulty hints."""

from __future__ import annotations

from typing import Optional


# ⚠ 白名单是 16 个任务共享的；某任务是否支持某档由它自己的 configs 决定
# （2026-09-11 加 xhard，只有 RouteStick／VideoUnmaskSwap／VideoRepick 有 config_xhard，其余任务传 xhard 会在 configs 查表处 KeyError）
VALID_DIFFICULTIES = {"easy", "medium", "hard", "xhard"}


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
