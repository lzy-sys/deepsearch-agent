# 深度研搜 · 简历项目描述模板与面试指南

> 面向求职者：本文提供可直接复制进简历的项目描述（中英双语）、面试 Q&A、演示路径，以及「不会前端怎么讲前端」的定位话术。请根据目标岗位裁剪，**只写你真正负责并讲得清的部分**。

## 一、项目一句话定位

**中文**：一个基于 DeepAgents 的对话式多智能体深度研究系统：主智能体调度网络搜索 / 数据库查询 / 私有知识库三类专家助手完成多来源检索，自动生成 Markdown / PDF 交付物，并通过 WebSocket 向前端实时推送执行过程与流式答案。

**English**: A conversational multi-agent deep research system built on DeepAgents: an orchestrator agent dispatches network-search, database-query, and knowledge-base sub-agents to gather multi-source information, generates Markdown/PDF deliverables, and streams execution progress and token-level answers to the frontend over WebSocket.

## 二、简历项目描述模板

### 中文版（后端 / AI Agent 方向）

```text
深度研搜 - 对话式多智能体深度研究系统（FastAPI + DeepAgents + LangGraph）

技术栈：Python / DeepAgents / LangGraph / LangChain / FastAPI / WebSocket /
        MySQL / Tavily / 知识库 RAG(LangChain + ChromaDB/BM25) / React / Docker

项目职责：
- 基于 DeepAgents Orchestrator-Workers 模式搭建"一主三从"多智能体架构：
  主智能体负责任务规划、助手调度与结果汇总，三个专家助手分别接入
  Tavily 网络搜索、MySQL 结构化查询、自研知识库 RAG 检索。
- 实现 9 个 LangChain 工具（搜索 / SQL 查询 / 知识库问答 / 附件解析 /
  Markdown / PDF 生成），覆盖"检索 → 分析 → 文件交付"完整链路。
- 设计 WebSocket 实时事件协议（tool_start / assistant_call /
  answer_delta / task_result），基于 LangGraph stream_mode=messages
  实现最终答案 token 级流式输出，前端打字机式渲染。
- 通过 ContextVar + thread_id + 会话目录实现并发任务上下文隔离，
  并统一收敛文件读写路径，防止越权访问。
- 完成全栈容器化部署：Docker 多阶段镜像 + Nginx 反向代理（/api、/ws），
  一条 docker compose up 启动整套系统。
- 搭建 LLM-as-judge 评测集（12 个典型研搜任务，完整性/准确性/结构化
  三维评分），用于 Agent 质量回归。
```

### English Version

```text
DeepSearch Agents - Conversational Multi-Agent Deep Research System

Tech Stack: Python / DeepAgents / LangGraph / LangChain / FastAPI / WebSocket /
            MySQL / Tavily / RAG (LangChain + ChromaDB/BM25) / React / Docker

Highlights:
- Built a 1-orchestrator + 3-worker agent architecture on DeepAgents:
  the main agent plans, dispatches and synthesizes; sub-agents integrate
  Tavily web search, MySQL structured queries, and a self-built RAG (ChromaDB + BM25) for private KB retrieval.
- Implemented 9 LangChain tools covering search / SQL / KB QA / attachment
  parsing / Markdown / PDF generation for an end-to-end research-to-delivery flow.
- Designed a WebSocket event protocol (tool_start / assistant_call /
  answer_delta / task_result) and token-level answer streaming via
  LangGraph stream_mode="messages" for typewriter-style UI output.
- Isolated per-session context with ContextVar + thread_id + session dirs,
  and centralized path resolution to prevent path traversal.
- Containerized the full stack with multi-stage Docker images + Nginx reverse
  proxy (/api, /ws); one docker compose up boots MySQL + backend + frontend.
- Built an LLM-as-judge evaluation harness (12 research tasks scored on
  completeness / accuracy / structure) for agent quality regression.
```

## 三、面试 Q&A（约 10 题）

1. **为什么用多智能体而不是单个 Agent？**
   单 Agent 面对"查公开资料 + 查数据库 + 查内部文档 + 生成文件"的复合任务，工具列表过长会稀释模型注意力。拆成三个专家助手后，每个助手只持有与自身领域相关的少量工具，主智能体按任务语义路由，工具调用更精准、上下文更聚焦，也便于独立扩展某个信息来源。

2. **主智能体如何决定调用哪个子智能体？**
   子智能体以 `name / description / system_prompt / tools` 字典注册，主智能体根据每个助手的 `description`（路由描述）判断任务归属。调度发生时，DeepAgents 在主智能体消息流里产生名为 `task` 的工具调用，参数带 `subagent_type` 和 `description`，系统据此识别并上报前端。

3. **DeepAgents 和 LangGraph 是什么关系？**
   DeepAgents 是基于 LangGraph 的上层框架，`create_deep_agent` 返回的就是一个 `CompiledStateGraph`（LangGraph 编译图）。项目在高层用 DeepAgents 声明式组装智能体与子智能体，底层复用 LangGraph 的图运行时、检查点（InMemorySaver）和流式能力。

4. **流式回答是怎么实现的？**
   `astream` 使用 `stream_mode=["updates","messages"]`。`updates` 给节点级状态（工具/助手/最终结果）；`messages` 给模型回答的 token 增量 `(message_chunk, metadata)`，只在 `langgraph_node == "model"` 且无工具调用时推 `answer_delta`，避免把工具参数当答案流。前端收到增量追加渲染，`task_result` 用完整结果幂等兜底。

5. **多个并发任务的上下文为什么不会串？**
   每个任务有独立 `thread_id` 和会话目录；`run_deep_agent` 把 `thread_id`、`session_dir` 写入 `ContextVar`，工具在调用链深处读取当前任务的上下文，任务结束在 `finally` 中 reset。`ContextVar` 是协程级隔离，天然适配 FastAPI 异步模型，不会出现全局变量串台。

6. **文件工具如何防止模型写坏路径？**
   模型拿到的提示词只给会话相对路径；`resolve_path` 统一清洗模型返回的虚拟前缀（/workspace 等）、绝对路径和相对路径，最终收敛到当前会话目录内；浏览/下载接口以 output 目录为安全边界做路径校验，防止 `../` 穿越。

7. **WebSocket 事件在后台任务里怎么推给前端？**
   后台 Agent 任务可能运行在非主事件循环的线程/循环中，WebSocket 发送必须回到创建连接的循环。`ConnectionManager.set_loop` 在启动时绑定主循环，`monitor` 通过 `asyncio.run_coroutine_threadsafe` 把发送协程投递回主循环，并按 `thread_id` 找到对应连接定向推送。

8. **为什么用 LLM-as-judge 做评测？**
   研搜答案没有标准唯一解，规则匹配无法衡量"信息充分性/结构"这类质量。用大模型当 judge，按参考答案要点对「完整性 / 准确性 / 结构化」三维打分，能低成本对 Agent 质量做回归；评测任务集覆盖网络/数据库/文件/混合场景，可随功能迭代持续跑。

9. **Docker 部署里 Nginx 起什么作用？**
   托管前端构建产物；把 `/api` 与 `/ws` 同源反向代理到后端，其中 `/ws` 需要配置 `Upgrade`/`Connection` 头与长连接超时。同源部署后浏览器请求不再跨域，前端默认用相对路径，省去 CORS 配置。

10. **这个项目的不足或后续方向？**
   目前是单机内存态：检查点是 InMemorySaver、事件未持久化、无用户认证与权限隔离、SQL 工具依赖提示词约束只读。后续可做事件落库与历史会话恢复、任务队列与分布式执行、SQL 白名单校验、评测自动化 CI。

## 四、前端怎么定位（不会前端也能讲）

- **简历口径**：写「设计 WebSocket 事件协议并完成前后端联调」，不写「开发 React 界面」。突出协议、事件流、接口契约，这些是你真正参与的部分。
- **一句话话术**："前端基于 React + Ant Design，我的工作集中在与后端交互的数据层：定义 WebSocket 事件协议、处理流式答案增量渲染、联调任务与文件接口；UI 视觉与组件库使用由项目既有代码承接。"
- **能讲清楚的三件事**（详见 `docs/FRONTEND_GUIDE.md`）：
  1. 前端如何建立 WebSocket 连接、心跳与重连；
  2. 收到不同事件后如何更新界面（事件流 / 文件列表 / 流式答案）；
  3. 任务提交、取消、上传、下载分别调哪个接口。

## 五、演示路径（10 分钟）

1. `docker compose up --build` 起全栈，打开 http://localhost:8080（或本地 `uvicorn` + `pnpm dev`）。
2. 提交一个数据库任务（如"库存大于 100 的药品"），展示：WebSocket 事件流 → 工具调用 → 最终答案 → 输出文件下载。
3. 提交一个混合任务（如"结合数据库与网络动态输出库存优化建议并生成 Markdown"），展示多智能体分派与文件交付。
4. 强调流式回答打字机效果；有精力再演示 `uv run python -m evals.run_evals --tasks 1,2,3` 出评测报告。
