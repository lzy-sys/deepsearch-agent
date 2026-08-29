# 深度研搜评测集（LLM-as-judge）

对主智能体端到端研搜质量进行自动评分：每个评测任务执行一次完整研搜，收集最终
回答，再用大模型按 **完整性 / 准确性 / 结构化** 三个维度打分，输出可读报告。

## 目录

```text
evals/
├── tasks.yaml        # 评测任务集（12 个任务，含参考答案要点）
├── run_evals.py      # 评测运行器（python -m evals.run_evals）
└── report/           # 运行后生成的 CSV / Markdown 评分报告
```

## 运行要求

- 已按 README 配置好 `.env`（LLM API Key 必须可用，评测会真实调用模型）
- 网络可用（网络搜索类任务依赖 Tavily）
- 数据库类任务需要 MySQL 已启动并导入教学数据
- 依赖运行时会真实消耗模型 Token，建议先用 `--tasks` 跑子集

## 基本用法

```bash
# 只跑前 3 个任务
uv run python -m evals.run_evals --tasks 1,2,3

# 并发 2 个任务（默认）
uv run python -m evals.run_evals --concurrency 2

# 全部非依赖任务
uv run python -m evals.run_evals
```

## 特殊任务

| 依赖 | 如何开启 |
| --- | --- |
| 上传附件（files 类） | `--fixtures-dir ./evals/fixtures`，把样例附件放入该目录，运行器会自动带入会话工作目录 |
| RAGFlow 服务 | `--include-ragflow`（需要本机 RAGFlow 可用） |

## 输出

运行结束后在 `evals/report/` 生成：

- `eval_report_<时间戳>.csv`：逐任务明细，可直接用表格软件打开
- `eval_report_<时间戳>.md`：汇总报告（任务、类别、各维度分、平均分、点评）

## 评分说明

| 维度 | 含义 |
| --- | --- |
| completeness | 完整性：是否覆盖参考答案要点，信息是否充分 |
| accuracy | 准确性：事实、数据与引用是否准确，有无明显编造 |
| structure | 结构化与可执行性：条理是否清晰，结论是否可落地 |

每个维度 1-5 分，judge 复用项目同一个大模型（`app/agent/llm.py` 的 `model`），
输出要求为严格 JSON，运行器会做容错解析。
