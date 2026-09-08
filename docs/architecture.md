# SmartAgent 架构方案

## 1. 总体架构

系统采用「单进程多会话」架构：一份编译好的 LangGraph 图全局复用，通过 `thread_id`（会话 ID）在 Checkpointer 中隔离每个会话的上下文与记忆，天然支持多用户并发。

```
┌─────────────────────────────────────────────────────────┐
│                      接入层 Entry                       │
│   CLI (cli.py)  /  Web Demo (server.py, FastAPI+SSE)    │
└──────────────────────┬──────────────────────────────────┘
                       │  user_input + session_id
                       ▼
┌─────────────────────────────────────────────────────────┐
│               AgentGraph (agent/graph.py)               │
│                                                         │
│   ┌────────────┐    tool_calls     ┌──────────────┐     │
│   │   agent    │ ────────────────► │    tools     │     │
│   │  (LLM调用) │                   │  (工具执行)   │     │
│   │            │ ◄──────────────── │              │     │
│   └────────────┘   tool_results    └──────────────┘     │
│        │    ▲                                            │
│        │    │ 无 tool_calls → 结束，输出最终回答           │
│        ▼    │                                            │
│   StateGraph 状态: messages[] + facts[]                  │
└───────────────┬──────────────────────────────────────────┘
                │  每次流式输出 (state updates)
                ▼
        Checkpointer (InMemorySaver)
        按 thread_id 保存 messages + facts
```

## 2. 核心设计决策

### 2.1 状态结构（state.py）

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]  # 对话上下文
    facts:    Annotated[list[str], add_facts]            # 长期事实记忆
```

- `messages` 使用 LangGraph 内建 `add_messages` reducer，自动追加合并；
- `facts` 自定义 `add_facts` reducer：按序去重追加 —— 这是「记忆模块」的状态层基础。

### 2.2 图结构（graph.py）

| 节点 | 职责 |
|---|---|
| `agent` | 拼接 `系统提示词(facts 注入) + 历史消息`，调用 LLM；模型可返回文本或工具请求 |
| `tools` | 顺序执行模型请求的工具；`remember_fact` 的返回值同步写入 `facts` |

| 边 | 语义 |
|---|---|
| `START → agent` | 每轮从 agent 开始 |
| `agent --条件路由--> tools / END` | 有 `tool_calls` 进 tools，否则结束出最终回答 |
| `tools → agent` | 工具结果回填后回到 agent 继续推理（循环直至无需工具） |

选择**手写节点 + 条件路由**而非 `create_react_agent` 黑盒的原因：
1. 对图的状态流转、记忆注入时机完全可控，便于讲解与调试；
2. 条件边清晰表达 ReAct 循环的本质（"决定行动 → 观察结果 → 再决定"）；
3. 便于后续扩展（多 Agent、Human-in-the-loop、子图等）。

### 2.3 记忆模块（两层记忆）

| 层级 | 载体 | 生命周期 | 说明 |
|---|---|---|---|
| 短期记忆 | `messages`（Checkpointer 持久化） | 随会话 | 完整对话历史，模型据此连续对话 |
| 长期记忆 | `facts` + 系统提示词注入 | 跨话题 | 用户关键信息显式记住，**不依赖无限上下文**，更省 token、更可控 |

长期记忆写入路径：用户告知信息 → 模型判断调用 `remember_fact(fact)` → tools 节点返回值写入 state.facts（reducer 去重）→ 下一轮 agent 将 facts 拼入系统提示词。形成 **写 → 存 → 注入 → 用** 的闭环。

### 2.4 多会话隔离

```
thread_id = "user-A"  →  Checkpointer 独立状态
thread_id = "user-B"  →  Checkpointer 独立状态
```

同一次交互传同一 `thread_id` 即可续聊；换 ID 即为全新会话。

### 2.5 工具注册（tools.py）

- 本地工具：`calculator`（AST 白名单安全求值）、`get_current_time`、`remember_fact`；
- 可选联网工具：配置 `TAVILY_API_KEY` 后动态注册 `web_search`，实现"Agent 是否具备实时信息能力"可配置化；
- 每新增一种能力 = 新增一个 `@tool` 函数 + 注册进 `build_tool_list`，扩展成本极低。

## 3. 数据流（一轮完整对话）

1. 用户输入 + `thread_id` 进入图；
2. `agent` 节点读取 Checkpointer 中的历史 `messages` 与 `facts`，构造系统提示词后调用 LLM；
3. LLM 决策：返回 `tool_calls`（如 `calculator`）或最终文本；
4. 若为 `tool_calls`：条件路由到 `tools` 节点执行，结果以 `ToolMessage` 回填，回到第 2 步；
5. 若无 `tool_calls`：节点输出最终文本，本轮结束，状态写入 Checkpointer；
6. 接入层以 `stream_mode="updates"` 逐事件接收（`tool_start → tool_result → token → done`），CLI 打印、Web 端 SSE 推送。

## 4. 非功能设计

| 关注点 | 方案 |
|---|---|
| 安全性 | 计算器 AST 白名单，杜绝 eval/exec 任意代码执行 |
| 健壮性 | 工具异常隔离（try/except 包住单工具）、`recursion_limit` 防死循环 |
| 可观测性 | 流式事件暴露每一步工具调用，便于前端展示"思考过程" |
| 兼容性 | OpenAI 兼容协议，切换 DeepSeek/通义等仅需改环境变量 |
| 扩展性 | 新工具即新函数；未来可平滑升级为多 Agent / 知识库 RAG / 持久化 SQLite |

## 5. 后续演进方向（Roadmap）

1. 接入持久化 Checkpointer（如 SQLite/Postgres），服务重启后记忆不丢；
2. 增加向量检索工具（RAG），支持私有知识库问答；
3. 增加多 Agent 编排（Planner-Executor / 审核-Agent）与人工审批断点（interrupt）；
4. 增加结构化输出（JSON schema）以对接业务系统。
