# 前端速成理解指南（面向不会前端的你）

> 目标：读完本指南（约 20 分钟），你能**讲清楚**前端如何与后端协作、每个部分是干什么的、
> 流式答案怎么渲染，并能回答面试官的高频追问。不需要会写 React。

## 1. 前端在项目里的角色

前端（`frontend/`，React + Vite + Ant Design + Tailwind）本质是**后端的"显示器 + 遥控器"**：

- 遥控器：提交任务、取消任务、上传附件、下载文件。
- 显示器：展示 WebSocket 实时事件流、最终答案（含流式打字机效果）、输出文件列表。

它不产生任何业务逻辑，所有智能与数据都在后端。

## 2. 目录与各文件职责

| 文件 | 职责 |
| --- | --- |
| `src/lib/config.ts` | 计算 API 与 WebSocket 地址。默认相对路径 `/`（开发由 Vite 代理、生产由 Nginx 反代），可用 `VITE_API_BASE_URL` 覆盖 |
| `src/lib/api.ts` | 封装 HTTP 接口：`startTask` / `cancelTask` / `uploadSessionFiles` / `listSessionFiles` / `getDownloadUrl` |
| `src/lib/thread.ts` | 会话 ID 的生成与本地持久化（刷新页面仍保持同一会话） |
| `src/hooks/useDeepAgentSession.ts` | **核心 Hook**：WebSocket 连接、心跳、断线重连、事件分发、任务/上传/取消/文件刷新 |
| `src/types.ts` | 前后端共享的类型定义（事件、响应体） |
| `src/App.tsx` | 页面骨架：侧边栏状态、对话流、输入区 |
| `src/components/ConversationThread.tsx` | 对话消息流：用户消息 + 助手消息（事件时间线 + 答案 + 文件） |
| `src/components/AgentTopology.tsx` | 侧边「多智能体路由」示意图（纯展示） |
| `src/components/EventStream.tsx` | 渲染思考事件时间线（工具调用、助手调用） |
| `src/components/MarkdownRenderer.tsx` | 把 Markdown 文本渲染成界面（流式答案也走这里） |
| `src/components/FileDock.tsx` | 输出文件列表 + 下载入口 |
| `src/components/ChatComposer.tsx` / `UploadPanel.tsx` | 输入框与上传区 |
| `src/components/ResultPanel.tsx` / `StatusStrip.tsx` / `MissionComposer.tsx` | 辅助面板（部分为界面增强） |

## 3. 数据流（一句话版）

```text
提交任务 → POST /api/task（拿到 thread_id）
    → 建立 WebSocket /ws/{thread_id}
    → 后端跑 Agent，持续推送 monitor_event
    → 前端按事件类型更新界面
    → task_result 到达 → 显示最终答案，停止加载态
```

## 4. WebSocket 连接的生命周期

在 `useDeepAgentSession` 中：

1. `connect()` 创建 `new WebSocket(WS_BASE_URL + "/ws/" + threadId)`。
2. `onopen`：置为 connected，并启动 25s 心跳定时器（发 `ping`，后端回 `pong`）。
3. `onmessage`：解析 JSON；`pong` 只更新时间；`monitor_event` 进入事件分发。
4. `onclose`：若组件未卸载，2s 后自动重连（reconnecting 状态）。
5. 组件卸载时关闭连接并清理定时器。

## 5. 事件分发逻辑（面试重点）

`onmessage` 收到 `monitor_event` 后按 `event` 字段处理：

| 事件 | 前端动作 |
| --- | --- |
| `session_created` | 记住会话目录路径 → 开始轮询文件列表 |
| `tool_start` / `assistant_call` | 追加到事件时间线（思考过程展示） |
| `answer_delta` | **追加到 result**（流式渲染，不进事件列表，避免刷爆 120 条上限） |
| `task_result` | 用完整结果覆盖 result（与流式内容一致，幂等），结束运行态 |
| `task_cancelled` / `error` | 结束运行态，展示取消/错误信息 |

**要点**：事件列表有 `MAX_EVENTS = 120` 上限；`answer_delta` 数量多，所以单独处理、不入时间线。

## 6. 流式答案渲染原理

- 后端以 `stream_mode="messages"` 拿到模型 token 增量，通过 `answer_delta` 事件推送。
- 前端 `setResult(prev => prev + delta)` 每次追加一段文本。
- `result` 变化 → `App` 的 `useEffect` 同步到最新一轮对话 → `ConversationThread` 里的 `MarkdownRenderer` 增量渲染。
- 因为 Markdown 渲染是幂等的（同一段文本渲染结果一致），所以"边写边渲染"不会闪烁或重复。

## 7. 任务 / 上传 / 下载接口对照

| 操作 | 接口 | 触发点 |
| --- | --- | --- |
| 启动任务 | `POST /api/task` | 提交问题 |
| 取消任务 | `POST /api/task/{id}/cancel` | 点取消按钮 |
| 上传附件 | `POST /api/upload`（multipart） | 上传区 |
| 文件列表 | `GET /api/files?path=...` | 收到 session_created 后轮询（运行中 2.5s / 空闲 6s） |
| 下载文件 | `GET /api/download?path=...` | 点文件卡片 |

## 8. 面试高频追问与标准答法

1. **前端是怎么知道任务进度的？**
   WebSocket 长连接，后端每个关键动作（工具调用、助手调度、答案增量、结果、错误）都推 `monitor_event`，前端按事件类型渲染。

2. **为什么用 WebSocket 而不是轮询？**
   研搜任务长且事件频繁，WebSocket 是双向实时通道，事件零延迟到达、省去大量轮询请求；前端 25s 心跳保活，断开自动重连。

3. **流式答案会不会把事件列表撑爆？**
   不会。`answer_delta` 在事件分发里单独分支处理，直接追加到 result，不进入 120 条上限的事件时间线。

4. **刷新页面会丢会话吗？**
   `thread_id` 存在 `localStorage`，刷新后同一会话重连 WebSocket；已完成的对话轮次在内存里，刷新会回到空白（这是当前版本的边界，可讲成后续改进点）。

5. **前端怎么拿到生成的文件？**
   收到 `session_created` 后拿到会话目录路径，轮询 `GET /api/files`，下载走 `GET /api/download`（后端做了路径安全校验）。

6. **Vite 代理是干什么的？**
   开发时前端跑在 5173、后端在 8000，Vite 把 `/api` 与 `/ws` 代理到 8000，前端代码用相对路径即可，无需关心跨域。

7. **生产环境前端怎么部署？**
   `pnpm build` 出静态文件，Nginx 托管；`/api` 与 `/ws` 反代到后端容器（WebSocket 需要 Upgrade 头），同源部署天然无 CORS 问题。

8. **你负责前端哪部分？**
   数据交互层：WebSocket 事件协议对接、流式答案渲染、任务/上传/下载联调；UI 视觉与组件库使用由项目既有代码承接。

9. **前端状态是怎么管理的？**
   没有引入 Redux，用 React Hooks：`useDeepAgentSession` 集中管理连接、事件、结果、文件等会话状态，`App` 再同步到对话轮次列表。

10. **如何验证前端链路正常？**
    提交任务后依次观察：侧边栏 WebSocket 变"已连接"→ 事件时间线出现工具/助手事件 → 答案逐字出现 → 文件列表出现产物并可下载。
