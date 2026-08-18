"""JSON 提取工具测试。"""

import pytest

from app.agents.base import extract_json


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_in_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_with_extra_text():
    assert extract_json('结果是：{"a": 1}，以上。') == {"a": 1}


def test_invalid_json_raises():
    with pytest.raises(ValueError):
        extract_json("这不是 JSON")