"""LangGraph RAG 工作流

把「检索 → 生成」组织为一张标准 RAG 图：retrieve 节点按知识库召回
Top-K 分块，generate 节点基于检索上下文生成带来源的回答。
"""

from typing import TypedDict

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

from app.rag.config import RAG_TOP_K
from app.rag.generator import generate_answer
from app.rag.retriever import doc_to_chunk, get_retriever


class RagState(TypedDict):
    """RAG 图状态：问题 + 知识库 + 检索上下文 + 最终回答"""

    kb_name: str
    question: str
    context: list[Document]
    answer: str


def _retrieve_node(state: RagState) -> dict:
    """检索节点：按知识库召回 Top-K 相关分块"""
    retriever = get_retriever(state["kb_name"])
    # EnsembleRetriever 融合后块数可能超过 K，收敛到配置的 Top-K
    documents = retriever.invoke(state["question"])[:RAG_TOP_K]
    return {"context": documents}


def _generate_node(state: RagState) -> dict:
    """生成节点：基于检索上下文生成带来源回答"""
    chunks = [
        doc_to_chunk(doc, state["kb_name"], rank)
        for rank, doc in enumerate(state.get("context", []))
    ]
    return {"answer": generate_answer(state["kb_name"], state["question"], chunks)}


def build_rag_graph():
    """构建标准 RAG 图：START -> retrieve -> generate -> END"""
    builder = StateGraph(RagState)
    builder.add_node("retrieve", _retrieve_node)
    builder.add_node("generate", _generate_node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()


# 模块级单例：进程内复用同一张编译图
rag_graph = build_rag_graph()