#!/usr/bin/env python3
"""轻量测试：V4 E2 的序数表扩容（NEWTASK_RELEASE_V4_PLAN 2.0①）。

四条配套测试：①idx 0…9 与改动前逐字相同；②idx 10…19 给 eleventh … twentieth；
③idx 20/21/22/112 给 21st / 22nd / 23rd / 113th；④负数仍 ValueError。

    uv run --no-sync python -m pytest tests/lightweight/test_subgoal_ordinal_v4.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests._shared.repo_paths import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from robomme.robomme_env.utils.subgoal_language import get_subgoal_with_index  # noqa: E402

TEMPLATE = "pick up the {idx} {color} cube"
# 改动前 if/elif 链的十个分支，逐字抄录
LEGACY = ["first", "second", "third", "fourth", "fifth",
          "sixth", "seventh", "eighth", "ninth", "tenth"]


def test_first_ten_unchanged() -> None:
    for idx, word in enumerate(LEGACY):
        assert get_subgoal_with_index(idx, TEMPLATE, color="red") == f"pick up the {word} red cube"


def test_eleven_to_twenty() -> None:
    words = ["eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
             "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth"]
    for offset, word in enumerate(words):
        assert get_subgoal_with_index(10 + offset, "{idx}") == word


def test_fallback_suffixes() -> None:
    assert [get_subgoal_with_index(i, "{idx}") for i in (20, 21, 22, 112, 110, 111)] == [
        "21st", "22nd", "23rd", "113th", "111th", "112th",
    ]


def test_negative_raises() -> None:
    with pytest.raises(ValueError):
        get_subgoal_with_index(-1, "{idx}")


def test_tensor_index_still_works() -> None:
    torch = pytest.importorskip("torch")
    assert get_subgoal_with_index(torch.tensor(3), "{idx}") == "fourth"
