"""SmartAgent Web Demo —— FastAPI 服务端（含 SSE 流式回复）。

用法：python server.py   然后浏览器打开 http://localhost:8000
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.config import Settings, check_env_ready, load_settings
from agent.graph import create_agent
from agent.llm import build_model
from agent.tools import build_tool_list

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

settings = load_settings()

app = FastAPI(title="SmartAgent Demo", description="基于 LangGraph 的通用助手 Agent Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent 实例缓存：按“模型配置”维度复用编译好的图（会话状态仍由 thread_id 隔离）
_agents: dict[str, object] = {}


def _cache_key(s: Settings) -> str:
    """按模型配置生成缓存键（哈希，避免明文 Key 出现在任何日志/结构中）。"""
    import hashlib

    raw = f"{s.base_url}|{s.model}|{s.api_key}|{s.tavily_api_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_agent_for(s: Settings):
    """按配置获取（或创建）Agent 实例，同配置复用同一张编译好的图。"""
    key = _cache_key(s)
    agent = _agents.get(key)
    if agent is None:
        # 防止不同访客的自定义配置无限增长（简单淘汰）
        if len(_agents) > 20:
            _agents.clear()
        tools = build_tool_list(s.tavily_api_key)
        agent = create_agent(build_model(s, tools), tools)
        _agents[key] = agent
    return agent


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户输入")
    session_id: str | None = Field(None, description="会话 ID，缺省自动生成")

    # 可选：访客自带模型配置（仅本次请求使用，不落服务端、不写日志）
    api_key: str | None = Field(None, description="自定义 API Key（可选）")
    base_url: str | None = Field(None, description="自定义 OpenAI 兼容端点（可选）")
    model: str | None = Field(None, description="自定义模型名（可选）")
    tavily_api_key: str | None = Field(None, description="自定义联网搜索 Key（可选）")


def resolve_settings(req: ChatRequest) -> Settings:
    """优先使用请求中携带的自定义配置，否则回落到服务端 .env 默认配置。"""
    has_custom = any([req.api_key, req.base_url, req.model, req.tavily_api_key])
    if not has_custom:
        return settings
    return Settings(
        api_key=(req.api_key or settings.api_key).strip(),
        base_url=(req.base_url or settings.base_url).strip().rstrip("/"),
        model=(req.model or settings.model).strip(),
        temperature=settings.temperature,
        tavily_api_key=(req.tavily_api_key or settings.tavily_api_key).strip(),
        port=settings.port,
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _safe_error_message(exc: Exception) -> str:
    """把模型调用异常映射为对用户友好、且不泄露敏感信息的提示。"""
    msg = str(exc).lower()
    if "401" in msg or "unauthorized" in msg or "invalid api key" in msg or "authentication" in msg:
        return "API Key 无效或无权访问（401）。请点右上角「设置」检查 Key 是否正确。"
    if "403" in msg or "forbidden" in msg:
        return "该 Key 无权限访问此模型（403）。请更换模型名或检查账户权限。"
    if "404" in msg or "not found" in msg:
        return "模型不存在或端点地址有误（404）。请检查「设置」中的 Base URL 与模型名。"
    if "429" in msg or "rate limit" in msg or "quota" in msg or "insufficient" in msg:
        return "触发限流或账户额度不足（429）。请稍后重试或检查账户余额。"
    if "timed out" in msg or "timeout" in msg or "connection" in msg or "connect" in msg:
        return "无法连接模型服务，请检查 Base URL 是否正确、网络是否可达。"
    return "模型调用失败，请检查「设置」中的端点、Key 与模型名是否正确。"


@app.get("/")
def index():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/api/health")
def health():
    problems = check_env_ready(settings)
    return {
        "status": "ok" if not problems else "need_config",
        "issues": problems,
        "model": settings.model,
        # 是否允许访客在页面自填配置（无服务端 Key 时依赖此能力）
        "allow_custom": True,
        "default_ready": not problems,
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    s = resolve_settings(req)
    problems = check_env_ready(s)
    if problems:
        raise HTTPException(status_code=400, detail="；".join(problems))
    session_id = req.session_id or str(uuid.uuid4())
    agent = get_agent_for(s)

    def event_stream():
        # 复用 Agent 图的事件流（tool_start / tool_result / token / done）
        try:
            for event_type, payload in agent._stream_events(session_id, req.message):
                body = dict(payload)
                body["session_id"] = session_id
                yield _sse(event_type, body)
        except Exception as exc:  # noqa: BLE001
            # 注意：不回显原始异常，避免 Key / 端点等敏感信息泄露给前端
            safe = _safe_error_message(exc)
            yield _sse("error", {"message": safe})
            yield _sse("done", {"session_id": session_id, "facts": []})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 静态资源
app.mount("/static", StaticFiles(directory=PUBLIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    problems = check_env_ready(settings)
    if problems:
        print("[警告] 尚未配置 LLM，可先打开页面，但对话前需在 .env 填写 Key。")
        for p in problems:
            print("  -", p)
    print(f"SmartAgent Demo 已启动：http://localhost:{settings.port}")
    print("按 Ctrl+C 停止。")
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="warning")
