"""Agent 图状态定义。

- messages：对话消息（LangGraph 内置 add_messages reducer，自动累积）
- facts    ：长期事实记忆（自定义 reducer，去重追加）
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def add_facts(current: list[str] | None, updates: list[str] | None) -> list[str]:
    """长期事实记忆的合并策略：按序去重追加。

    agent 每次会话开始时把 facts 注入系统提示词，让模型"记住"跨轮次的关键事实，
    实现显式记忆模块（区别于仅依赖上下文窗口的隐式记忆）。
    """
    merged = list(current or [])
    for item in updates or []:
        if item not in merged:
            merged.append(item)
    return merged


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    facts: Annotated[list[str], add_facts]
