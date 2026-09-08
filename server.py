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

from agent.config import check_env_ready, load_settings
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

# 提前构建 Agent（图只编译一次，全局复用；按会话 thread_id 隔离状态）
_tools = build_tool_list(settings.tavily_api_key)
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(build_model(settings, _tools), _tools)
    return _agent


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="用户输入")
    session_id: str | None = Field(None, description="会话 ID，缺省自动生成")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    problems = check_env_ready(settings)
    if problems:
        raise HTTPException(status_code=400, detail="；".join(problems))
    session_id = req.session_id or str(uuid.uuid4())
    agent = get_agent()

    def event_stream():
        # 复用 Agent 图的事件流（tool_start / tool_result / token / done）
        for event_type, payload in agent._stream_events(session_id, req.message):
            body = dict(payload)
            body["session_id"] = session_id
            yield _sse(event_type, body)

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
