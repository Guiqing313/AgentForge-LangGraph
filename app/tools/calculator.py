"""安全计算器工具。

不使用裸 ``eval``，而是基于 ``ast`` 白名单解析，只允许：
数字字面量、四则运算、math 模块中的纯函数。
"""

from __future__ import annotations

import ast
import math
import operator

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_ALLOWED_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}


def safe_eval(expression: str) -> float:
    """安全求值数学表达式，拒绝一切非白名单语法。"""
    if not isinstance(expression, str) or len(expression) > 200:
        raise ValueError("表达式必须是非空字符串且不超过 200 字符")
    tree = ast.parse(expression.strip(), mode="eval")
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _BIN_OPS[type(node.op)](left, right)

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))

    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return _ALLOWED_NAMES[node.id]

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_NAMES:
            fn = _ALLOWED_NAMES[node.func.id]
            args = [_eval_node(a) for a in node.args]
            return fn(*args)

    raise ValueError("不支持的表达式（仅允许数字、四则运算与 math 函数）")


class CalculatorTool:
    """对外提供 ``calculate`` 方法。"""

    def calculate(self, expression: str) -> str:
        try:
            return str(safe_eval(expression))
        except Exception as exc:  # noqa: BLE001 —— 对外统一转成可读文本
            return f"计算错误：{exc}"