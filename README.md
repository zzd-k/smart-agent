# SmartAgent · 基于 LangGraph 的通用助手 Agent

> 一个 **0-1 独立开发落地** 的通用 Agent 案例：知识问答 + 工具调用 + 长期记忆 + Web Demo。
> 面向岗位要求手写的 LangGraph 状态机实现，非 prebuilt 黑盒拼接。

🔗 **在线 Demo**：http://18ec3ab9bff64bc2932f2eaf052fb60b.codebuddy.cloudstudio.run
（已部署上线，可直接点开体验：计算器 / 时间 / 长期记忆 三类工具调用）

📦 **源码仓库**：https://github.com/zzd-k/smart-agent

| 维度 | 说明 |
|---|---|
| 框架 | LangGraph（手写 StateGraph + 条件路由，非黑盒） |
| 模型 | 任意 OpenAI 兼容接口（智谱 GLM / OpenAI / DeepSeek / 通义 / Moonshot / vLLM），默认 `glm-5.3-flash` |
| 核心能力 | 工具调用循环（ReAct）、长期记忆（facts reducer）、多会话隔离（thread_id） |
| 界面 | 命令行 CLI + FastAPI Web Demo（SSE 流式） |
| 依赖 | langgraph、langchain-openai、fastapi（详见 requirements.txt） |

---

## 功能演示

```text
你> 帮我算一下 (1800 - 120) * 0.85 是多少？
🤖 [工具调用]
     · calculator(expression=(1800 - 120) * 0.85)
🤖 结果是 1428.0。

你> 记住：我叫王明，是做前端开发的，回答尽量简洁。
🤖 [工具调用]
     · remember_fact(fact=用户叫王明，是做前端开发的，回答尽量简洁)
🤖 好的王明，已记住你的身份。

你> 那我是做什么的？现在几点了？
🤖 [工具调用]
     · get_current_time()
🤖 你是前端开发工程师。当前时间是 2026-09-08 18:41（周二）。
```

**关键亮点：** 第二轮用 `remember_fact` 显式写入记忆；第三轮即使换了话题，Agent 依然记得用户身份 —— 这就是「记忆模块」的作用（不依赖无限扩上下文窗口）。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置模型

```bash
cp .env.example .env
# 编辑 .env，填入你的 OpenAI 兼容服务信息
```

可选：填写 `TAVILY_API_KEY`（免费申请 https://app.tavily.com ）即可获得实时联网搜索能力。

### 3. 运行

```bash
# 方式一：命令行交互
python cli.py

# 方式二：Web Demo（浏览器打开 http://localhost:8000）
python server.py
```

Web Demo 里依次试试下面的输入，直观看到 Agent「思考 → 调工具 → 回答」：

| 想验证的能力 | 输入 |
|---|---|
| 工具调用（计算器） | `帮我算 (1800-120)*0.85` |
| 工具调用（时间） | `现在几点了？今天星期几？` |
| 长期记忆 | `记住我是前端工程师，叫王明`，随后问 `我做什么工作？` |
| 联网搜索 | `搜索一下 2026 年大模型 Agent 最新进展`（需 Tavily Key） |

---

## 目录结构

```
smart-agent/
├── agent/                    # Agent 核心（无框架封装，全部手写）
│   ├── state.py              # 图状态：messages + facts（自定义 reducer）
│   ├── tools.py              # 工具集：计算器 / 时间 / 记忆 / 可选联网搜索
│   ├── llm.py                # LLM 工厂（bind_tools 工具注入）
│   ├── graph.py              # LangGraph 状态机编排（agent <-> tools 循环）
│   └── config.py             # 环境配置
├── public/                   # Web Demo 前端（原生 HTML/CSS/JS + SSE）
├── docs/
│   ├── architecture.md       # 架构方案（图 + 数据流 + 设计决策）
│   ├── retrospective.md      # 项目复盘
│   └── resume-case.md        # 简历与面试素材（简历描述 / 答辩点 / 追问）
├── cli.py                    # 命令行入口
├── server.py                 # FastAPI Web Demo 入口
├── .env.example
└── requirements.txt
```

## 测试

内置无网络 mock 测试（无需 Key，验证图循环 / 工具去重 / 记忆跨轮生效）：

```bash
python -m tests.test_graph
```

---

## 技术要点速览

- **工具调用循环**：`agent` 节点产出 `tool_calls` → 条件边路由到 `tools` 节点执行 → 结果回填给模型 → 若无工具请求则输出最终答案。全程在 LangGraph 图内完成，天然支持断点 / 重放 / 状态持久化。
- **长期记忆**：`facts` 字段 + `remember_fact` 工具，自定义 `add_facts` reducer 去重合并，每轮注入系统提示词。
- **多会话隔离**：`thread_id` 作为 checkpointer 键，不同会话上下文与记忆互不干扰，天然支持多用户。
- **安全性**：计算器使用 AST 白名单求值，不执行任意代码。
- **工程健壮性**：工具异常隔离（单工具失败不中断整轮）、单轮工具次数上限、SSE 流式输出。
