"""无网络 mock 测试：验证图循环 / 工具去重 / 记忆跨轮生效。

运行：python -m tests.test_graph
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.graph import create_agent
from agent.tools import build_tool_list


class MockModel(BaseChatModel):
    """模拟模型：第 1 轮调 calculator，第 2 轮调 remember_fact，之后直接回答。

    第 3 轮起检查系统提示词中是否已注入记忆（[MEM] 标记），以此断言记忆模块生效。
    """

    i: int = 0

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.i += 1
        has_fact = any("喜欢简洁回答" in str(m.content) for m in messages if isinstance(m, SystemMessage))
        if self.i == 1:
            msg = AIMessage(
                content="",
                tool_calls=[{"name": "calculator", "args": {"expression": "1200*0.85"}, "id": "c1", "type": "tool_call"}],
            )
        elif self.i == 2:
            msg = AIMessage(
                content="",
                tool_calls=[
                    {"name": "remember_fact", "args": {"fact": "用户叫小明，喜欢简洁回答"}, "id": "c2", "type": "tool_call"}
                ],
            )
        else:
            msg = AIMessage(content="算好了 1020.0 [MEM]" if has_fact else "算好了 1020.0")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_graph_loop_and_memory():
    tools = build_tool_list("")
    agent = create_agent(MockModel(), tools)
    sid = "sess-test-1"

    r1 = agent.run(sid, "帮我算 1200*0.85，并记住我喜欢简洁回答")
    assert r1["reply"].startswith("算好了"), r1["reply"]
    assert len(r1["tool_steps"]) == 2, f"工具应各记录一次，实际 {len(r1['tool_steps'])}"
    assert [s["tool"] for s in r1["tool_steps"]] == ["calculator", "remember_fact"]
    assert r1["facts"] == ["用户叫小明，喜欢简洁回答"], r1["facts"]

    # 跨轮：记忆应注入第二轮的上下文
    r2 = agent.run(sid, "你还记得我吗？")
    assert "[MEM]" in r2["reply"], f"记忆未跨轮注入: {r2['reply']}"

    # 会话隔离：新会话不应有旧记忆
    r3 = agent.run("sess-other-1", "你还记得我吗？")
    assert "[MEM]" not in r3["reply"], "新会话不应继承旧会话记忆"

    print("✓ 图循环 OK：calculator + remember_fact 各调用一次，无重复")
    print("✓ 长期记忆 OK：跨轮注入生效")
    print("✓ 会话隔离 OK：不同 thread_id 记忆互不干扰")
    print("\n全部测试通过 ✅")


if __name__ == "__main__":
    test_graph_loop_and_memory()
