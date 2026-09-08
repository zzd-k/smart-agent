"""LangGraph 状态机编排 —— Agent 核心大脑。

图结构（ReAct 工具调用循环）：

    START ──> agent ──┬─(有 tool_calls)──> tools ──> agent(回到循环)
                      └─(无 tool_calls)──> END

- agent 节点：调用 LLM，注入系统提示词（含长期记忆 facts）与全部历史消息；
- tools 节点：执行模型请求的工具，返回结果继续让模型推理；
- checkpointer：按 thread_id 持久化整张图状态，实现多轮对话/会话隔离。
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterator

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .state import AgentState

# 单轮最多工具调用数（防死循环）
_MAX_TOOL_ROUNDS = 10


def build_system_prompt(facts: list[str]) -> str:
    """提示词工程：让模型明确自身定位、能力边界与记忆使用方式。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    memory_part = (
        "\n\n## 关于用户，你已经记住以下事实（对话中请自然运用）:\n" + "\n".join(f"- {f}" for f in facts)
        if facts
        else ""
    )
    return f"""你是一个名叫 SmartAgent 的通用智能助手，具备知识问答、工具调用与记忆能力。

## 使用工具的原则（必须严格遵守）
1. 需要**精确计算**时**必须**调用 calculator，禁止心算或用已有知识直接给数；
2. 用户询问**时间/日期**时**必须**调用 get_current_time，禁止凭印象作答；
3. 需要**实时或外部信息**时**必须**调用 web_search（若可用），不要编造最新事实；
4. **只要**用户透露了任何值得记住的信息（姓名、职业/身份、偏好、约定、目标等），
   **必须立刻调用 remember_fact 工具**把它存下来。只回答"我记住了"而不调用工具，
   等于没有真正记住，这是严重错误。存完后再用自然语言确认。
5. 工具不能解决的内容，基于自身知识直接作答，不要强行调用工具。

## 严禁编造（重要）
- 当对话中没有"关于用户的事实"或历史上下文可以支撑时，必须如实回答"我不清楚，你还没告诉过我"，
  **绝对不要**猜测或编造用户的身份、职业、经历与偏好。
- 只有被明确记住（见下方"已记住的事实"）或本轮对话中用户亲口说明的信息，才可以当作事实使用。
- 工具没有返回结果或执行失败时，如实说明无法获取，不得自行编造数值或结论。

## 回答风格
- 用简体中文、结构化、要点清晰；必要时给出可操作建议。
- 记住用户身份与偏好，前后回答保持一致。

当前系统时间：{now}。{memory_part}"""


class AgentGraph:
    """封装图构建与推理调用，屏蔽 LangGraph 细节。"""

    def __init__(self, model, tools: list[BaseTool]):
        self.model = model
        self.tool_map = {t.name: t for t in tools}
        self.checkpointer = InMemorySaver()
        self.app = self._build()

    # ---------- 节点 ----------
    def _call_agent(self, state: AgentState) -> dict:
        """agent 节点：系统提示词(注入记忆) + 历史消息 -> 模型。"""
        facts = state.get("facts", []) or []
        history = state.get("messages", []) or []
        messages = [SystemMessage(content=build_system_prompt(facts)), *history]
        response = self.model.invoke(messages)
        return {"messages": [response]}

    def _call_tools(self, state: AgentState) -> dict:
        """tools 节点：顺序执行本轮模型请求的所有工具调用。"""
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {}

        outputs: list[ToolMessage] = []
        for call in last_message.tool_calls:
            tool = self.tool_map.get(call["name"])
            try:
                if tool is None:
                    result = f"未知工具: {call['name']}"
                else:
                    result = tool.invoke(call.get("args", {}))
                result = str(result)
            except Exception as exc:  # noqa: BLE001 —— 工具异常不应中断整轮
                result = f"工具 {call['name']} 执行失败: {exc}"
            outputs.append(
                ToolMessage(content=result, tool_call_id=call["id"], name=call["name"])
            )

        # remember_fact 的返回值同步写入 facts 长期记忆
        new_facts: list[str] = []
        for call in last_message.tool_calls:
            if call["name"] == "remember_fact":
                fact = (call.get("args", {}) or {}).get("fact", "").strip()
                if fact:
                    new_facts.append(fact)
        return {"messages": outputs, "facts": new_facts}

    # ---------- 路由 ----------
    @staticmethod
    def _route(state: AgentState) -> str:
        """条件边：最后一条 AI 消息请求了工具 -> 进入 tools；否则结束。"""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return END

    # ---------- 构建 ----------
    def _build(self):
        graph = StateGraph(AgentState)
        graph.add_node("agent", self._call_agent)
        graph.add_node("tools", self._call_tools)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", self._route, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
        return graph.compile(checkpointer=self.checkpointer)

    # ---------- 对外推理接口 ----------
    def _stream_events(self, session_id: str, user_input: str) -> Iterator[tuple[str, dict]]:
        """低层事件流：产出 (event_type, payload)。

        event_type ∈ {"tool_start", "tool_result", "token", "done"}
        采用 stream_mode="updates"（每个事件只含增量），避免历史消息重复。
        """
        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": 50,
        }
        for event in self.app.stream(
            {"messages": [("user", user_input)]}, config=config
        ):
            for _node, update in (event or {}).items():
                if not update:
                    continue
                for msg in update.get("messages", []) or []:
                    if isinstance(msg, AIMessage):
                        for call in getattr(msg, "tool_calls", None) or []:
                            yield ("tool_start", {"tool": call["name"], "args": call.get("args", {})})
                        if msg.content:
                            text = msg.content if isinstance(msg.content, str) else str(msg.content)
                            yield ("token", {"text": text})
                    elif isinstance(msg, ToolMessage):
                        yield ("tool_result", {"tool": getattr(msg, "name", ""), "result": str(msg.content)[:600]})

        state = self.app.get_state(config).values
        facts = state.get("facts", []) if isinstance(state, dict) else []
        yield ("done", {"facts": facts})

    def run(self, session_id: str, user_input: str) -> dict:
        """执行一轮对话，返回 {reply, tool_steps, tool_outputs, facts}。"""
        reply_parts: list[str] = []
        tool_steps: list[dict] = []
        tool_outputs: list[str] = []
        for event_type, payload in self._stream_events(session_id, user_input):
            if event_type == "token":
                reply_parts.append(payload["text"])
            elif event_type == "tool_start":
                tool_steps.append(payload)
            elif event_type == "tool_result":
                tool_outputs.append(payload["result"])
            elif event_type == "done":
                facts = payload["facts"]

        return {
            "reply": "".join(reply_parts).strip() or "（没有生成回复，请重试）",
            "tool_steps": tool_steps,
            "tool_outputs": tool_outputs,
            "facts": facts if "facts" in locals() else [],
        }

    def peek_facts(self, session_id: str) -> list[str]:
        """查看某会话当前长期记忆（不触发推理）。"""
        state = self.app.get_state({"configurable": {"thread_id": session_id}}).values
        return state.get("facts", []) if isinstance(state, dict) else []

    def dump_state(self, session_id: str) -> str:
        """调试用：导出某会话消息数 / 记忆 / 最近内容。"""
        state = self.app.get_state({"configurable": {"thread_id": session_id}}).values
        if not isinstance(state, dict):
            return "{}"
        messages = state.get("messages", []) or []
        summary = {
            "messages": len(messages),
            "facts": state.get("facts", []),
            "last_user": (messages[-2].content if len(messages) >= 2 else ""),
            "last_assistant": (messages[-1].content if messages else ""),
        }
        return json.dumps(summary, ensure_ascii=False, indent=2)


def create_agent(model, tools: list[BaseTool]) -> AgentGraph:
    """对外统一入口：创建已编译的 Agent 图。"""
    return AgentGraph(model, tools)
