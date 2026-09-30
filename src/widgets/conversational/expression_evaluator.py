import ast
import math
import operator


class ExpressionError(ValueError):
    pass


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_MAX_EXPRESSION_LENGTH = 80
_MAX_AST_NODES = 64
_MAX_ABS_VALUE = 1e12


def evaluate_number_expression(text):
    expression = text.strip()
    if not expression:
        raise ExpressionError("Expression is empty.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ExpressionError("Expression is too long.")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError("Expression is invalid.") from exc

    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise ExpressionError("Expression is too complex.")

    value = _eval_node(tree.body)
    if not math.isfinite(value):
        raise ExpressionError("Expression did not produce a finite value.")
    if abs(value) > _MAX_ABS_VALUE:
        raise ExpressionError("Expression result is too large.")
    return value


def evaluate_integer_expression(text):
    value = evaluate_number_expression(text)
    if not float(value).is_integer():
        raise ExpressionError("Expression result is not an integer.")
    return int(value)


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError("Only numeric literals are allowed.")
        return float(node.value)

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPERATORS.get(type(node.op))
        if op is None:
            raise ExpressionError("Operator is not allowed.")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return op(left, right)
        except ZeroDivisionError as exc:
            raise ExpressionError("Division by zero.") from exc

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPERATORS.get(type(node.op))
        if op is None:
            raise ExpressionError("Operator is not allowed.")
        return op(_eval_node(node.operand))

    raise ExpressionError("Expression contains unsupported syntax.")
