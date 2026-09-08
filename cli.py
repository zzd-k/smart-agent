"""SmartAgent 命令行交互入口。

用法：
    python cli.py                 # 直接对话
    python cli.py "今天几号？"     # 单次问答

交互命令：
    /new    开启新会话（清空上下文与记忆）
    /mem    查看当前记忆
    /help   帮助
    /exit   退出
"""

from __future__ import annotations

import sys
import uuid

from langchain_core.messages import AIMessage, HumanMessage


def _print_help() -> None:
    print("  /new   开启新会话（清空上下文与记忆）")
    print("  /mem   查看已记住的事实")
    print("  /help  显示帮助")
    print("  /exit  退出")


def run_cli() -> None:
    from agent.config import check_env_ready, load_settings
    from agent.graph import create_agent
    from agent.llm import build_model
    from agent.tools import build_tool_list

    settings = load_settings()
    problems = check_env_ready(settings)
    if problems:
        for p in problems:
            print(f"[配置错误] {p}")
        print("提示：请先复制 .env.example 为 .env 并填写 OPENAI_API_KEY 等参数。")
        sys.exit(1)

    agent = create_agent(
        model=build_model(settings, build_tool_list(settings.tavily_api_key)),
        tools=build_tool_list(settings.tavily_api_key),
    )
    session_id = str(uuid.uuid4())

    print("=" * 56)
    print("  SmartAgent · 基于 LangGraph 的通用助手")
    print(f"  模型: {settings.model}   会话: {session_id[:8]}...")
    print("  输入 /help 查看命令；/exit 退出")
    print("=" * 56)

    # 单次问答模式
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        result = agent.run(session_id, user_input)
        print(f"\n🤖 {result['reply']}\n")
        if result["tool_steps"]:
            print("  · 调用工具:", ", ".join(s["tool"] for s in result["tool_steps"]))
        return

    # 交互模式
    while True:
        try:
            user_input = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if not user_input:
            continue

        if user_input in ("/exit", "/quit"):
            print("再见！")
            break
        if user_input == "/help":
            _print_help()
            continue
        if user_input == "/new":
            session_id = str(uuid.uuid4())
            print(f"已开启新会话：{session_id[:8]}...")
            continue
        if user_input == "/mem":
            state = agent.app.get_state(
                {"configurable": {"thread_id": session_id}}
            ).values
            facts = state.get("facts", []) if isinstance(state, dict) else []
            print("已记住：" + ("；".join(facts) if facts else "（暂无）"))
            continue

        result = agent.run(session_id, user_input)
        steps = result["tool_steps"]
        if steps:
            print("  🤖 [工具调用]", end="")
            for s in steps:
                args = ", ".join(f"{k}={v}" for k, v in s["args"].items())
                print(f"\n     · {s['tool']}({args})", end="")
            print()
        print(f"🤖 {result['reply']}")


if __name__ == "__main__":
    run_cli()
