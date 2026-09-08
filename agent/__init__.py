"""SmartAgent —— 基于 LangGraph 的通用助手 Agent。

模块说明：
- config.py : 环境配置（模型 / BaseURL / Key / 温度）
- llm.py    : LLM 工厂，统一创建绑定了工具列表的模型
- tools.py  : 内置工具集（计算 / 时间 / 事实记忆 / 可选联网搜索）
- memory.py : 记忆合并逻辑（reducer），承载长期事实记忆
- state.py  : Agent 图状态定义
- graph.py  : LangGraph 状态机编排（agent <-> tools 循环）
"""
