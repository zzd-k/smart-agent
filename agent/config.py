"""集中读取环境配置（.env / 系统环境变量）。"""

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（agent/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    temperature: float
    tavily_api_key: str
    port: int


def load_settings() -> Settings:
    import os

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    try:
        temperature = float(os.getenv("TEMPERATURE", "0.3"))
    except ValueError:
        temperature = 0.3
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    try:
        port = int(os.getenv("PORT", "8000"))
    except ValueError:
        port = 8000
    return Settings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        tavily_api_key=tavily_key,
        port=port,
    )


def check_env_ready(settings: Settings) -> list[str]:
    """返回缺失/异常配置项说明，空列表表示一切就绪。"""
    problems: list[str] = []
    if not settings.api_key or settings.api_key == "sk-xxxx":
        problems.append("缺少 OPENAI_API_KEY，请在 .env 中填写（可从 .env.example 复制）。")
    if not settings.base_url.startswith(("http://", "https://")):
        problems.append("OPENAI_BASE_URL 格式不正确。")
    return problems
