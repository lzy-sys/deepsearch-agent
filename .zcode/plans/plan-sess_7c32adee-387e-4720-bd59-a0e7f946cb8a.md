## 目标

降低一次研搜任务的耗时。根因（已探索确认）：主智能体提示词鼓励反复调度子智能体（实测一次知识库任务发起 13 次 ask_knowledge_base + 6 次网络搜索）、无任何迭代上限兜底（langgraph recursion_limit 默认 10007）、每次知识库提问都全量重建 BM25 检索器。按用户确认，三项全做。

## A. 提示词调度收敛（app/prompt/prompts.yml）

修改主智能体 `system_prompt` 的「你的工作流程」部分，改动 2 处 + 新增 1 节：

1. 改「信息获取」节中「可以…**再次调用网络搜索助手**进行深入问题检索」→ 改为「一般只调用一次，若结果不足可针对缺口再查一次，但同一信息源对同一主题最多调用 2 次子智能体」。
2. 改「可以尝试使用三种方式获取信息，如果边界并不明确，则全部使用」→ 保留「三种方式都能用」，补上限「每种信息源最多尝试 1 次」。
3. 新增「调度效率要求」小节（约束反复调度这一主因）：
   - 信息获取以能回答用户问题为限；信息足够后立即停止获取，进入汇总或文件生成。
   - 同一信息源（网络 / 知识库 / 数据库）对同一主题最多调用 2 次子智能体；已获取的信息不得重复获取。
   - 需要多个助手的信息时，尽量在同一条回复中同时下发多个子智能体调用（它们可并行执行）。
   - 禁止「边获取边反复验证」式的轮询；信息确有缺口时，基于已有信息给出结论并注明局限。

子智能体的 name/description/system_prompt 不动（其内部「最多 1~2 次提问」约束继续有效）；「生成内容不少于 1000 字」等质量要求保留。

## B. RAG 检索器缓存（app/rag/retriever.py + app/rag/indexer.py）

- `retriever.py`：新增模块级 `_retriever_cache: dict[tuple, BaseRetriever]`，`get_retriever` 以 `(kb_name, RAG_RETRIEVER, k)` 为键缓存构建结果（BM25Retriever 与 EnsembleRetriever 均为无状态可复用对象）；新增 `invalidate_retriever_cache(kb_name=None)`（清单个知识库或全部）。
- `indexer.py`：`sync_knowledge_base_dir` 重建完成后调用 `invalidate_retriever_cache(kb_name)`，保证重索引后检索器自动失效重建（避免缓存到旧语料）。
- 收益：一次知识库会话内多次 `ask_knowledge_base` 只构建一次检索器，消除每次 jieba 全量分词 + BM25 重建。

## C. recursion_limit 保险丝（app/agent/main_agent.py）

- `run_deep_agent` 中传给 `astream` 的 config 增加顶层 `"recursion_limit": 200`（langgraph 顶层配置项）。
- 依据：实测最重的知识库任务约 24 次工具调用 + 模型轮 ≈ 60~100 super-step，200 留有充足余量；对失控循环（如主智能体反复重派助手）形成早期截断，替代 10007 的形同虚设。若未来任务超限，异常会走现有 `except Exception` 路径经 monitor 上报前端。

## 验证

1. `prompts.yml` 加载正常：导入 `app.agent.prompts` 确认 YAML 解析无报错。
2. 检索器缓存：连续两次 `retrieve()`，第二次不重新分词构建（对比耗时 / 缓存命中）；`ingest --rebuild` 后确认缓存已失效。
3. 端到端（本地 .venv 直跑 `run_deep_agent`，MySQL 走 3307、RAG 走 data/rag，与 Docker 同源）：
   - 数据库任务：事件流与耗时正常，回答质量不下降。
   - 知识库任务：`ask_knowledge_base` / 网络搜索调用次数较实测（13 次 / 6 次）明显下降，整体耗时下降。
4. `ask_knowledge_base` 工具输出格式不变（【回答】/【来源】）。

## 备注

- 修改的是宿主机代码；Docker 容器内是旧镜像（`app` 非 bind mount），要生效需 `docker compose build backend && docker compose up -d backend`——会重启你正在运行的服务，**本次不执行**，实施完成后由你决定何时重建。
- 提示词收敛会让主智能体行为更简洁（这正是耗时下降的来源），eval 的「完整性」维度仍要求覆盖参考要点，不受影响。