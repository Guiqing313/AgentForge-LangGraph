"""安全计算器测试。"""

import pytest

from app.tools.calculator import CalculatorTool, safe_eval


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("1+2*3", 7),
        ("(1+2)*3", 9),
        ("sqrt(16)", 4.0),
        ("-5+3", -2),
        ("2**10", 1024),
    ],
)
def test_safe_eval_valid(expr, expected):
    assert safe_eval(expr) == expected


@pytest.mark.parametrize(
    "expr",
    ["__import__('os')", "open('x')", "[1,2]", "1;2", "import sys", "().__class__"],
)
def test_safe_eval_rejects_dangerous(expr):
    with pytest.raises(Exception):
        safe_eval(expr)


def test_calculator_tool_returns_error_string():
    tool = CalculatorTool()
    result = tool.calculate("__import__('os')")
    assert result.startswith("计算错误")
