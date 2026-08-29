"""
深度研搜评测运行器（LLM-as-judge）

逐任务调用 run_deep_agent 执行一次完整研搜，收集最终回答，再用同一个大模型
作为 judge，按「完整性 / 准确性 / 结构化」三个维度打分，最后输出 CSV 与
Markdown 评测报告。

用法：
    uv run python -m evals.run_evals --tasks 1,2,5 --concurrency 2
    uv run python -m evals.run_evals --fixtures-dir ./evals/fixtures --include-ragflow
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from app.agent.llm import model
from app.agent.main_agent import run_deep_agent

DIMENSIONS = [
    ("completeness", "完整性：回答是否覆盖参考答案要点，信息是否充分"),
    ("accuracy", "准确性：事实、数据与引用是否准确，有无明显编造"),
    ("structure", "结构化与可执行性：条理是否清晰，结论是否可落地"),
]


def load_tasks(path: Path) -> list[dict]:
    """读取 tasks.yaml 评测任务集"""
    with path.open(encoding="utf-8") as f:
        tasks = yaml.safe_load(f) or []
    return tasks


def select_tasks(
    tasks: list[dict],
    task_ids: set[int] | None,
    include_ragflow: bool,
    fixtures_dir: Path | None,
) -> list[dict]:
    """按命令行参数过滤任务：--tasks 指定 id；upload/ragflow 依赖按条件跳过"""
    selected = []
    for task in tasks:
        if task_ids and int(task["id"]) not in task_ids:
            continue
        requirement = task.get("requires")
        if requirement == "upload" and not fixtures_dir:
            print(f"[skip] task {task['id']} 需要上传附件，请用 --fixtures-dir 指定夹具目录")
            continue
        if requirement == "ragflow" and not include_ragflow:
            print(f"[skip] task {task['id']} 需要 RAGFlow 服务，请用 --include-ragflow 开启")
            continue
        selected.append(task)
    return selected


def build_judge_prompt(task: dict, answer: str) -> str:
    points = "\n".join(f"- {p}" for p in task.get("reference_points", []))
    dimensions = "\n".join(f"- {key}：{desc}" for key, desc in DIMENSIONS)
    return f"""你是一个严谨的 AI 评测员。请根据「参考答案要点」对下面的 AI 研搜回答进行评分。

## 任务
{task['query']}

## 参考答案要点
{points}

## AI 研搜回答
{answer}

## 评分维度（1-5 分，5 为最佳）
{dimensions}

只输出一个 JSON 对象，不要输出其他内容，格式如下：
{{"completeness": 5, "accuracy": 4, "structure": 5, "comment": "一句话点评"}}"""


def parse_score(text: str) -> dict:
    """从 judge 输出中稳健提取 JSON 评分"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    result = {}
    for key, _ in DIMENSIONS:
        try:
            result[key] = max(1, min(5, int(round(float(data.get(key, 0))))))
        except (TypeError, ValueError):
            result[key] = 0
    result["comment"] = str(data.get("comment", ""))[:200]
    return result


def judge_task(task: dict, answer: str) -> dict:
    """用大模型作为 judge 对单个回答打分"""
    empty = {key: 0 for key, _ in DIMENSIONS}
    empty["comment"] = "无回答（执行可能异常）"
    if not answer.strip():
        return empty
    try:
        response = model.invoke(
            [
                ("system", "你是专业的 AI 评测员，只输出 JSON 评分。"),
                ("human", build_judge_prompt(task, answer)),
            ]
        )
        content = getattr(response, "content", "") or ""
        score = parse_score(str(content))
        if not score:
            empty["comment"] = "judge 输出无法解析"
            return empty
        return score
    except Exception as exc:  # noqa: BLE001
        empty["comment"] = f"judge 调用失败: {exc}"
        return empty


async def run_one(
    task: dict,
    semaphore: asyncio.Semaphore,
    fixtures_dir: Path | None,
) -> dict:
    """执行单个评测任务：研搜 -> 打分 -> 汇总一行结果"""
    async with semaphore:
        task_id = int(task["id"])
        session_id = f"eval_{task_id}_{uuid.uuid4().hex[:8]}"

        # 上传类任务：把夹具文件复制到 updated/session_xxx，run_deep_agent 启动时自动带入工作目录
        if task.get("requires") == "upload" and fixtures_dir:
            updated_dir = Path("app") / "updated" / f"session_{session_id}"
            updated_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(fixtures_dir.glob("*")):
                if src.is_file():
                    shutil.copy2(src, updated_dir / src.name)

        answer = ""
        try:
            answer = await run_deep_agent(task["query"], session_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            answer = f"[执行异常] {exc}"

        # judge 是同步阻塞调用，放到线程池避免卡住事件循环
        score = await asyncio.to_thread(judge_task, task, answer)

        row = {
            "task_id": task_id,
            "category": task.get("category", ""),
            "query": task["query"],
            "answer_len": len(answer),
            **{key: score[key] for key, _ in DIMENSIONS},
            "avg": round(sum(score[key] for key, _ in DIMENSIONS) / len(DIMENSIONS), 2),
            "comment": score.get("comment", ""),
        }
        print(f"[eval] task {task_id} ({task.get('category')}) 完成，平均分 {row['avg']}")
        return row


def write_reports(rows: list[dict], report_dir: Path) -> tuple[Path, Path]:
    """输出 CSV 与 Markdown 评测报告"""
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = report_dir / f"eval_report_{timestamp}.csv"
    md_path = report_dir / f"eval_report_{timestamp}.md"

    fieldnames = ["task_id", "category", "query", "answer_len", "completeness", "accuracy", "structure", "avg", "comment"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    overall_avg = round(sum(row["avg"] for row in rows) / len(rows), 2) if rows else 0.0
    lines = [
        "# 深度研搜评测报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 评测任务数：{len(rows)}",
        f"- 平均分（满分 5）：**{overall_avg}**",
        "",
        "| 任务 | 类别 | 完整性 | 准确性 | 结构化 | 平均 | 点评 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['task_id']} | {row['category']} | {row['completeness']} | "
            f"{row['accuracy']} | {row['structure']} | {row['avg']} | {row['comment']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, csv_path


async def async_main(args: argparse.Namespace) -> int:
    tasks_file = Path(args.tasks_file)
    tasks = load_tasks(tasks_file)
    task_ids = {int(x) for x in args.tasks.split(",")} if args.tasks else None
    fixtures_dir = Path(args.fixtures_dir) if args.fixtures_dir else None
    if fixtures_dir and not fixtures_dir.is_dir():
        print(f"[error] 夹具目录不存在: {fixtures_dir}")
        return 1

    selected = select_tasks(tasks, task_ids, args.include_ragflow, fixtures_dir)
    if not selected:
        print("没有可执行的任务，请检查 --tasks / --include-ragflow / --fixtures-dir 参数")
        return 1

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    rows = await asyncio.gather(*(run_one(task, semaphore, fixtures_dir) for task in selected))
    rows.sort(key=lambda row: row["task_id"])

    md_path, csv_path = write_reports(rows, Path(args.report_dir))
    overall_avg = round(sum(row["avg"] for row in rows) / len(rows), 2)
    print(f"\n评测完成：{len(rows)} 个任务，平均分 {overall_avg}")
    print(f"Markdown 报告：{md_path}")
    print(f"CSV 报告：{csv_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="深度研搜 LLM-as-judge 评测运行器")
    parser.add_argument("--tasks", help="要运行的任务 id，逗号分隔，例如 1,2,5")
    parser.add_argument("--concurrency", type=int, default=2, help="并发任务数（默认 2）")
    parser.add_argument("--fixtures-dir", default=None, help="上传类任务的夹具文件目录")
    parser.add_argument("--include-ragflow", action="store_true", help="包含依赖 RAGFlow 的任务")
    parser.add_argument("--tasks-file", default=str(Path(__file__).parent / "tasks.yaml"), help="任务集文件路径")
    parser.add_argument("--report-dir", default=str(Path(__file__).parent / "report"), help="报告输出目录")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
