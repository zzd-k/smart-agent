"""LLM 工厂：统一创建绑定了工具列表的 ChatOpenAI（OpenAI 兼容）。"""

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

from .config import Settings


def build_model(settings: Settings, tools: list[BaseTool]) -> BaseChatModel:
    """创建模型并绑定工具。

    bind_tools 会把工具 schema 注入请求，使模型具备"自主决定调用哪个工具"的能力，
    这是 Agent 工具调用循环（ReAct 模式）的前提。
    """
    model = ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        timeout=60,
        max_retries=2,
    )
    if tools:
        model = model.bind_tools(tools)
    return model
