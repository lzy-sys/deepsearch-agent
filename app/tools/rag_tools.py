"""自研知识库 RAG 工具模块

对外暴露两个 LangChain 工具，供知识库子智能体使用：
- list_knowledge_bases：列出可用知识库及其文档/分块统计
- ask_knowledge_base：向指定知识库提问（检索 + LLM 生成带来源回答）
内部复用 app/rag 的摄取、索引、检索与生成链路。
"""

from langchain_core.tools import tool

from app.api.monitor import monitor
from app.rag.generator import generate_answer
from app.rag.indexer import _collection, ensure_indexed
from app.rag.kb_registry import get_kb_path, list_knowledge_bases as _list_kb_registry
from app.rag.retriever import retrieve


def _kb_stats() -> dict[str, dict]:
    """返回 {kb_name: {"doc_count": int, "chunk_count": int}}"""
    stats: dict[str, dict] = {}
    try:
        collection = _collection()
        for kb in _list_kb_registry():
            result = collection.get(where={"kb_name": kb.name}, include=["metadatas"])
            metadatas = result.get("metadatas") or []
            doc_count = len({m.get("doc_name") for m in metadatas if m.get("doc_name")})
            stats[kb.name] = {"doc_count": doc_count, "chunk_count": len(metadatas)}
    except Exception:  # noqa: BLE001
        pass
    return stats


@tool
def list_knowledge_bases() -> str:
    """
    查询当前可用的内部知识库

    返回每个知识库的名称、描述、已索引文档数与分块数，供模型判断该向哪个
    知识库提问。调用 ask_knowledge_base 之前，应先用本工具确认知识库名称。
    :return: 知识库列表；无知识库时返回中文提示
    """
    monitor.report_tool(tool_name="知识库列表查询工具：list_knowledge_bases", args={})

    kbs = _list_kb_registry()
    if not kbs:
        return "当前没有任何可用知识库。"

    stats = _kb_stats()
    lines = []
    for kb in kbs:
        stat = stats.get(kb.name, {"doc_count": 0, "chunk_count": 0})
        lines.append(
            f"知识库名称:{kb.name};描述:{kb.description or '无'};"
            f"文档数:{stat['doc_count']};分块数:{stat['chunk_count']}"
        )
    return "\n".join(lines)


@tool
def ask_knowledge_base(kb_name: str, question: str) -> str:
    """
    向指定的内部知识库提问

    系统会先在该知识库中检索相关内容，再基于检索结果生成带来源的回答。
    注意：调用前必须先通过 list_knowledge_bases 确认知识库名称存在。
    :param kb_name: 知识库名称，必须来自 list_knowledge_bases 返回结果
    :param question: 本次提问的问题
    :return: 回答文本 + 来源文档列表；异常时返回中文错误提示
    """
    monitor.report_tool(
        tool_name="知识库提问工具：ask_knowledge_base",
        args={"kb_name": kb_name, "question": question},
    )

    if not get_kb_path(kb_name):
        return f"错误：知识库 '{kb_name}' 不存在，请先调用 list_knowledge_bases 确认可用知识库。"

    try:
        ensure_indexed(kb_name)
    except Exception as exc:  # noqa: BLE001
        return f"知识库 '{kb_name}' 索引建立失败：{exc}"

    try:
        chunks = retrieve(kb_name, question)
    except Exception as exc:  # noqa: BLE001
        return f"知识库检索失败：{exc}"

    answer = generate_answer(kb_name, question, chunks)

    source_lines = [f"- {chunk.doc_name}（相关度 {chunk.score}）" for chunk in chunks]
    sources = "\n".join(source_lines) if source_lines else "无"
    return f"【回答】\n{answer}\n\n【来源】\n{sources}"
