"""内置工具集。

设计原则：
1. 每个工具独立、自描述、有明确入参 schema（供模型 tool-calling 决策）；
2. 纯本地工具零成本可演示，联网工具按 Key 可选注册；
3. 统一通过 @tool 装饰，后续接入数据库 / HTTP API / RPA 只需"加一个函数"。
"""

from __future__ import annotations

import ast
import datetime
import math
import operator as op

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# 1) 本地计算器：安全求值（AST 白名单，绝不 exec/eval）
# ---------------------------------------------------------------------------
_ALLOWED_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "floor": math.floor, "ceil": math.ceil, "pi": math.pi, "e": math.e,
}
_ALLOWED_OPERATORS = {
    ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
    ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod, ast.Pow: op.pow, ast.USub: op.neg, ast.UAdd: op.pos,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _ALLOWED_FUNCS:
        return _ALLOWED_FUNCS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        args = [_safe_eval(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValueError(f"不支持的表达式片段: {ast.dump(node)}")


@tool
def calculator(expression: str) -> str:
    """计算数学表达式并返回结果。

    适合数值计算、单位换算辅助运算等。支持 + - * / // % ** 括号，
    以及 sqrt/log/sin/cos/tan/floor/ceil/abs/round/min/max/pi/e 等函数。

    参数 expression: 要计算的数学表达式，例如 "1200 * 0.85 + 45"。
    """
    tree = ast.parse(expression, mode="eval")
    value = _safe_eval(tree.body)
    # 避免浮点尾巴：0.1+0.2 -> 0.30000000000000004
    if isinstance(value, float):
        value = round(value, 10)
    return str(value)


# ---------------------------------------------------------------------------
# 2) 本地时间工具
# ---------------------------------------------------------------------------
@tool
def get_current_time() -> str:
    """获取当前日期与时间（系统本地时区）。

    适合回答"今天星期几 / 现在几点 / 当前日期"等问题。无需参数。
    """
    now = datetime.datetime.now()
    week_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    return now.strftime(f"%Y-%m-%d %H:%M:%S（{week_cn}）")


# ---------------------------------------------------------------------------
# 3) 事实记忆工具：显式写入/读取长期记忆
# ---------------------------------------------------------------------------
@tool
def remember_fact(fact: str) -> str:
    """把一条关于用户或任务的关键事实存入长期记忆。

    当用户在对话中提到：自己的身份/偏好/背景，或双方约定的事项（例如"我叫王明"、
    "我偏好简洁的回答"、"目标是把项目部署上线"），调用本工具显式记忆，
    后续所有轮次都会自动记住该事实。

    参数 fact: 一句话的事实描述，例如 "用户叫王明，是前端工程师"。
    """
    return fact


# ---------------------------------------------------------------------------
# 4) 可选联网搜索（需 TAVILY_API_KEY）
# ---------------------------------------------------------------------------
def _register_web_search(tavily_api_key: str):
    """仅当配置了 Tavily Key 时才注册联网搜索工具。"""

    @tool
    def web_search(query: str) -> str:
        """在互联网上实时搜索信息。

        当问题涉及：实时新闻、最新资讯、需要外部知识或本地工具无法回答的内容时，
        调用本工具获取网页搜索结果摘要。

        参数 query: 搜索关键词，尽量具体，如 "2026 年 AI Agent 招聘趋势"。
        """
        import requests

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": tavily_api_key,
            "query": query,
            "max_results": 5,
            "search_depth": "basic",
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return f"联网搜索失败：{exc}"

        results = data.get("results", [])
        if not results:
            return "未搜索到相关信息。"
        lines = []
        for i, item in enumerate(results, 1):
            title = item.get("title", "")
            content = item.get("content", "")
            url_ = item.get("url", "")
            lines.append(f"{i}. {title}\n   {content[:300]}\n   来源: {url_}")
        return "\n".join(lines)

    return web_search


def build_tool_list(tavily_api_key: str = "") -> list:
    """组装最终可用工具列表（联网工具按 Key 可选）。"""
    tools = [calculator, get_current_time, remember_fact]
    if tavily_api_key:
        tools.append(_register_web_search(tavily_api_key))
    return tools
