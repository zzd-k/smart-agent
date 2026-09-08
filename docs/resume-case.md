# 简历案例素材（直接可用）

> 用途：把本项目写进简历 + 作为「Agent 开发案例及方案材料」提交。
> 附件清单建议：README.md（项目文档）+ architecture.md（架构方案）+ 本页（案例摘要/复盘）+ **在线 Demo 链接** + Demo 录屏（GIF）+ 代码仓库链接。

## 在线 Demo（可外链，直接点开）

**http://18ec3ab9bff64bc2932f2eaf052fb60b.codebuddy.cloudstudio.run**

已部署上线，国内可直接访问。建议同时在附件里放一段 30 秒录屏，防止链接失效或沙箱休眠（长时间无访问会休眠，首次打开需等待唤醒）。

## 一、简历项目描述（两版，按篇幅选用）

### 精简版（约 3 行）
> **SmartAgent —— 基于 LangGraph 的通用助手 Agent（个人独立开发，0-1 落地）**
> 独立设计并实现基于 LangGraph 状态机的通用 Agent，支持知识问答、工具调用循环（ReAct）与长期记忆。手写 StateGraph 节点与条件路由（拒绝 prebuilt 黑盒），自定义 facts 记忆 reducer 实现跨话题长期记忆；内置安全计算器（AST 白名单）、时间、事实记忆等工具，支持按 Key 动态注册 Tavily 联网搜索；统一事件流同时支撑 CLI 与 FastAPI Web Demo（SSE 流式），并处理工具异常隔离与防死循环等工程问题。配套架构方案与项目复盘文档。

### 详细版（约 6 行，突出量化与工程性）
> **SmartAgent · LangGraph 通用助手 Agent（独立开发）**
> - 手写 LangGraph 状态机（agent↔tools 循环 + 条件路由），实现 LLM 自主工具调用；不使用 prebuilt 黑盒，状态流转完全可控；
> - 自研两层记忆：短期（messages Checkpointer 持久化）+ 长期（facts reducer 去重 + 系统提示词注入，通过 remember_fact 工具显式写入），实现跨话题记忆且避免无限扩上下文；
> - 工具集可插拔：安全计算器（AST 白名单防任意代码执行）、时间/日期、事实记忆，支持配置 TAVILY_API_KEY 后动态启用实时联网搜索；
> - 采用 stream_mode=updates 事件化推理，CLI / Web 双端复用，FastAPI + SSE 流式呈现思考过程（工具调用→结果→答复）；
> - 工程健壮性：单工具异常隔离不中断整轮、recursion_limit 防死循环、按 thread_id 多会话隔离；
> - 完整测试与文档：无网络 mock 验证图循环/记忆跨轮/会话隔离；附架构方案（Mermaid）、项目复盘。

## 二、案例方案摘要（提交附件用，约 1 页 A4）

**项目目标**：实现一个通用对话 Agent，能在多轮对话中自主调用工具解决计算/时间/联网类问题，并能长期记住用户关键信息。

**技术方案**：
1. **图状态**：`messages`（对话上下文，add_messages）+ `facts`（长期记忆，自定义 add_facts 去重 reducer）；
2. **图编排**：`START→agent→tools→agent→…→END`，agent 节点将 facts 注入系统提示词后调用 LLM，有 tool_calls 则条件路由到 tools 执行并回填；
3. **记忆模块**：短期记忆存完整历史于 Checkpointer；长期记忆由 remember_fact 工具显式写入 facts，每轮注入系统提示词，做到跨话题不忘；
4. **会话隔离**：以 thread_id 为 Checkpointer 键，天然支持多用户；
5. **工具安全与扩展**：计算器 AST 白名单、联网搜索按 Key 动态注册，新增能力 = 新增一个 @tool 函数。

**效果**：可通过"记住我叫王明、做前端"→跨话题追问"我做什么工作"完整演示记忆闭环；通过计算/时间问题演示工具调用；全部能力在 CLI 与 Web Demo 双端可用。

## 三、面试高频追问与应答要点

| 可能的追问 | 应答要点 |
|---|---|
| 为什么不用 `create_react_agent` / LangChain 内置 Agent？ | 需要可控状态流转与记忆注入时机；手写让条件边清晰表达 ReAct 循环本质，也便于扩展多 Agent 与人工审批断点 |
| 记忆模块和直接堆上下文有什么区别？ | 堆上下文是无差别回溯、随会话变长 cost 爆炸且不可控；facts 显式去重存储 + 仅注入关键事实，省 token、可解释、跨会话可迁移 |
| 工具异常了怎么办？ | 单工具 try/except 隔离，异常转为 ToolMessage 回填给模型，模型可修正参数重试或直接回答，不中断整轮 |
| 如何防止 Agent 死循环/失控？ | LangGraph recursion_limit 全局兜底 + 条件路由仅在真有 tool_calls 时才进 tools |
| 如何换模型？ | OpenAI 兼容协议，改 .env 的 base_url/model/key 即可（已验证 DeepSeek / 通义等） |
| 记忆重启会丢吗？ | 当前 InMemorySaver 是进程内，已明确规划接 SQLite/Postgres Checkpointer；接口已抽象，改动集中在 checkpointer 一行 |
| 计算器安全怎么保证？ | AST 解析后按白名单节点类型递归求值，仅允许数字/有限函数/算术运算，杜绝 eval/exec |
| Web 如何做到流式？ | 推理层统一产出事件（tool_start/tool_result/token/done），FastAPI 以 text/event-stream 推送，前端逐事件渲染 |
| 有没有评测？ | 已用 mock LLM 写自动化用例验证图循环、工具调用不重复、记忆跨轮注入、会话隔离；计划引入工具选择准确率量化评测 |

## 四、Demo 演示脚本（录屏/现场用，3 分钟）

1. 启动 `python server.py`，打开页面；
2. 输入 `帮我算一下 (1800-120)*0.85` → 展示调用 calculator 工具并给出 1428.0；
3. 输入 `现在几点、今天星期几` → 展示调用 get_current_time；
4. 输入 `记住我叫王明，是做前端开发的，回答尽量简洁` → 展示 remember_fact；
5. 换话题问 `我做什么工作？` → 展示 Agent 记得（记忆闭环）；
6. 点「新会话」问同样问题 → 展示会话隔离（不记得了）。
7. （可选）若配了 Tavily：问一个实时问题，展示 web_search。
